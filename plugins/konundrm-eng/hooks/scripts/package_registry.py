"""Looks up public facts about a package: existence, age, downloads, license and known advisories.

Queries the npm registry and download API, and PyPI's JSON API (plus pypistats.org for recent
downloads, when it answers), then asks OSV.dev which advisories affect the latest version. Base
URLs can be overridden for mirrors and tests with KONUNDRM_NPM_REGISTRY, KONUNDRM_NPM_DOWNLOADS_API,
KONUNDRM_PYPI_URL, KONUNDRM_PYPISTATS_URL and KONUNDRM_OSV_URL. Answers are cached for a day in
the plugin's data directory. Only the standard library is used.

Sections:
    PackageFacts              — what the registry and OSV say about one package.
    fetch_json(), post_json() — the HTTP calls lookup() makes unless a test passes fakes.
    lookup()                  — facts for a package, from the cache or the registry.
"""

from __future__ import annotations

import contextlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hook_io import plugin_data_directory

REQUEST_TIMEOUT_SECONDS = 5
CACHE_TTL_SECONDS = 24 * 3600
# Part of every cache key. Bump it when PackageFacts changes, so entries older code wrote are fetched again.
CACHE_FORMAT = "v2"
# Above this many weekly npm downloads a package is established; its age is not worth a large fetch.
ESTABLISHED_WEEKLY_DOWNLOADS = 10_000
# PyPI's free-text license field often holds the whole license text; only a short line names a license.
MAX_LICENSE_NAME_LENGTH = 100
USER_AGENT = "konundrm-eng-dependency-guard"
OSV_ECOSYSTEMS = {"npm": "npm", "pypi": "PyPI"}
MALWARE_ID_PREFIX = "MAL-"  # OpenSSF malicious-packages data in OSV
MALWARE_CWE = "CWE-506"  # embedded malicious code, the weakness GitHub's malware advisories carry

# fetch(url) → (HTTP status, decoded JSON or None); raises OSError when the registry is unreachable.
Fetch = Callable[[str], tuple[int, Any]]
# post(url, payload) → the same for a JSON POST, such as an OSV query.
Post = Callable[[str, dict[str, Any]], tuple[int, Any]]


@dataclass(frozen=True)
class PackageFacts:
    """What a public registry, and OSV, say about one package.

    Attributes:
        reachable: False when the registry could not be queried; the other fields are then unknown.
        exists: Whether the registry has the package.
        first_published: When its first version was published, if known.
        weekly_downloads: Downloads in the last week, if the registry reports them.
        latest_version: The version an unpinned install gets, if known. The license and the
            advisories describe this version, so they are unknown while it is.
        license: The latest version's license as the registry declares it, an SPDX expression or a
            descriptive text; None when it declares none.
        advisories: OSV ids of the advisories that affect the latest version; None when OSV could
            not be queried.
        malware_advisories: The advisories among those that report the latest version as malware:
            OpenSSF ``MAL-`` ids and GitHub malware advisories (CWE-506).
    """

    reachable: bool
    exists: bool = False
    first_published: datetime | None = None
    weekly_downloads: int | None = None
    latest_version: str | None = None
    license: str | None = None
    advisories: tuple[str, ...] | None = None
    malware_advisories: tuple[str, ...] = ()


def _base(variable: str, default: str) -> str:
    return os.environ.get(variable, default).rstrip("/")


def _request_json(url: str, body: bytes | None = None) -> tuple[int, Any]:
    """Sends a GET, or a POST when there is a body, and decodes the JSON answer (see fetch_json)."""
    # Registry URLs are https, or an explicit KONUNDRM_* override for a mirror or a test server.
    if not url.startswith(("https://", "http://")):
        raise OSError(f"refusing a non-HTTP registry URL: {url}")
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=body, headers=headers)  # noqa: S310 - http(s) only, checked above
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:  # noqa: S310 - same URL
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return 404, None
        raise OSError(f"{url} answered {error.code}") from error
    except ValueError as error:
        raise OSError(f"{url} did not return JSON") from error


def fetch_json(url: str) -> tuple[int, Any]:
    """Fetches a JSON document over HTTPS.

    Returns:
        The HTTP status and the decoded body, or ``(404, None)`` when the registry has no such page.

    Raises:
        OSError: When the registry cannot be reached or answers with another error.
    """
    return _request_json(url)


def post_json(url: str, payload: dict[str, Any]) -> tuple[int, Any]:
    """Posts a JSON document over HTTPS and decodes the JSON answer.

    Args:
        url: Endpoint, such as OSV's ``/v1/query``.
        payload: JSON-serialisable request body.

    Returns:
        The HTTP status and the decoded body, or ``(404, None)`` when the service has no such page.

    Raises:
        OSError: When the service cannot be reached or answers with another error.
    """
    return _request_json(url, json.dumps(payload).encode("utf-8"))


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    with contextlib.suppress(ValueError):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


def _npm_license(manifest: dict[str, Any]) -> str | None:
    """Reads ``license`` (text or ``{"type": ...}``), or the legacy ``licenses`` list, of a manifest."""
    declared = manifest.get("license") or manifest.get("licenses")
    entries = declared if isinstance(declared, list) else [declared]
    names = [entry.get("type") if isinstance(entry, dict) else entry for entry in entries]
    return " OR ".join(name.strip() for name in names if isinstance(name, str) and name.strip()) or None


def _npm_latest(registry: str, escaped_name: str, fetch: Fetch) -> tuple[str | None, str | None]:
    """Reads the latest version and its license from the version's small manifest."""
    status, manifest = fetch(f"{registry}/{escaped_name}/latest")
    if status != 200 or not isinstance(manifest, dict):
        return None, None
    version = manifest.get("version")
    return (version if isinstance(version, str) and version else None), _npm_license(manifest)


def _npm_facts(name: str, fetch: Fetch) -> PackageFacts:
    registry = _base("KONUNDRM_NPM_REGISTRY", "https://registry.npmjs.org")
    escaped = name.replace("/", "%2F")  # a scoped name is one path segment: @scope%2Fname
    downloads_api = _base("KONUNDRM_NPM_DOWNLOADS_API", "https://api.npmjs.org")
    status, body = fetch(f"{downloads_api}/downloads/point/last-week/{name}")  # npm names are URL-safe
    weekly = body.get("downloads") if status == 200 and isinstance(body, dict) else None
    created = None
    if not (isinstance(weekly, int) and weekly >= ESTABLISHED_WEEKLY_DOWNLOADS):
        status, body = fetch(f"{registry}/{escaped}")  # the full document, only for its creation date
        if status == 404 or not isinstance(body, dict):
            return PackageFacts(reachable=True, exists=False)
        times = body.get("time")
        created = _parse_time(times.get("created")) if isinstance(times, dict) else None
    version, declared_license = _npm_latest(registry, escaped, fetch)
    return PackageFacts(
        reachable=True,
        exists=True,
        first_published=created,
        weekly_downloads=weekly,
        latest_version=version,
        license=declared_license,
    )


def _pypi_license(info: dict[str, Any]) -> str | None:
    """Reads the latest release's license: its SPDX expression, a short license field or classifiers."""
    expression = info.get("license_expression")
    if isinstance(expression, str) and expression.strip():
        return expression.strip()
    text = info.get("license")
    short = text.strip() if isinstance(text, str) else ""
    # One short, non-empty line names a license. UNKNOWN is what old setuptools wrote for none.
    if len(short.splitlines()) == 1 and len(short) <= MAX_LICENSE_NAME_LENGTH and short.upper() != "UNKNOWN":
        return short
    classifiers = info.get("classifiers")
    names = [
        classifier.rsplit(" :: ", 1)[-1]
        for classifier in (classifiers if isinstance(classifiers, list) else [])
        if isinstance(classifier, str) and classifier.startswith("License ::")
    ]
    return " OR ".join(names) or None


def _pypi_weekly_downloads(name: str, fetch: Fetch) -> int | None:
    """Reads last week's downloads from pypistats.org, a best-effort extra signal."""
    with contextlib.suppress(OSError):
        stats_api = _base("KONUNDRM_PYPISTATS_URL", "https://pypistats.org")
        status, stats = fetch(f"{stats_api}/api/packages/{urllib.parse.quote(name)}/recent")
        if status == 200 and isinstance(stats, dict):
            value = (stats.get("data") or {}).get("last_week")
            return value if isinstance(value, int) else None
    return None


def _pypi_facts(name: str, fetch: Fetch) -> PackageFacts:
    status, body = fetch(f"{_base('KONUNDRM_PYPI_URL', 'https://pypi.org')}/pypi/{urllib.parse.quote(name)}/json")
    if status == 404 or not isinstance(body, dict):
        return PackageFacts(reachable=True, exists=False)
    uploads = [
        _parse_time(file.get("upload_time_iso_8601"))
        for files in (body.get("releases") or {}).values()
        for file in files or []
        if isinstance(file, dict)
    ]
    known_uploads = [upload for upload in uploads if upload is not None]
    latest = body.get("info")  # describes the latest release
    info: dict[str, Any] = latest if isinstance(latest, dict) else {}
    version = info.get("version")
    return PackageFacts(
        reachable=True,
        exists=True,
        first_published=min(known_uploads, default=None),
        weekly_downloads=_pypi_weekly_downloads(name, fetch),
        latest_version=version if isinstance(version, str) and version else None,
        license=_pypi_license(info),
    )


def _reports_malware(vuln: dict[str, Any]) -> bool:
    """Tells whether an OSV record reports malicious code rather than a vulnerability.

    OpenSSF's malicious-packages data uses ``MAL-`` ids. GitHub publishes malware as GHSA advisories
    with CWE-506 and a summary such as "Malicious Package in x" or "Malicious code in x".
    """
    identifier = str(vuln.get("id"))
    if identifier.startswith(MALWARE_ID_PREFIX):
        return True
    summary = str(vuln.get("summary") or "").lower()
    details = vuln.get("database_specific")
    cwe_ids = details.get("cwe_ids") if isinstance(details, dict) else None
    return (
        identifier.startswith("GHSA-")
        and (summary.startswith("malicious package in") or "malicious code in" in summary)
        and isinstance(cwe_ids, list)
        and MALWARE_CWE in cwe_ids
    )


def _osv_vulns(ecosystem: str, name: str, version: str, post: Post) -> list[dict[str, Any]] | None:
    """Asks OSV for the records of the advisories that affect one version; None when it cannot answer."""
    query = {"package": {"name": name, "ecosystem": OSV_ECOSYSTEMS[ecosystem]}, "version": version}
    try:
        status, body = post(f"{_base('KONUNDRM_OSV_URL', 'https://api.osv.dev')}/v1/query", query)
    except OSError:
        return None
    # A version without advisories answers {}; pagination starts above 1,000, so one page is enough.
    vulns = body.get("vulns", []) if status == 200 and isinstance(body, dict) else None
    if not isinstance(vulns, list):
        return None
    return [vuln for vuln in vulns if isinstance(vuln, dict) and isinstance(vuln.get("id"), str)]


def _ids(vulns: Iterable[dict[str, Any]]) -> tuple[str, ...]:
    return tuple(sorted({str(vuln["id"]) for vuln in vulns}))


def _with_advisories(facts: PackageFacts, ecosystem: str, name: str, post: Post) -> PackageFacts:
    """Adds what OSV knows about the latest version; ``advisories`` stays None when OSV does not answer."""
    if facts.latest_version is None:  # OSV is asked about the version that would install, never the name
        return facts
    vulns = _osv_vulns(ecosystem, name, facts.latest_version, post)
    if vulns is None:
        return facts
    malware = [vuln for vuln in vulns if _reports_malware(vuln)]
    return replace(facts, advisories=_ids(vulns), malware_advisories=_ids(malware))


def _cache_path() -> Path:
    return plugin_data_directory() / "registry-cache.json"


def _load_cache() -> dict[str, Any]:
    try:
        data = json.loads(_cache_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _store(key: str, facts: PackageFacts) -> None:
    cache = _load_cache()
    record = asdict(facts)
    record["first_published"] = facts.first_published.isoformat() if facts.first_published else None
    cache[key] = {"fetched": time.time(), "facts": record}
    with contextlib.suppress(OSError):
        _cache_path().parent.mkdir(parents=True, exist_ok=True)
        _cache_path().write_text(json.dumps(cache), encoding="utf-8")


def _cached(key: str) -> PackageFacts | None:
    entry = _load_cache().get(key)
    if not isinstance(entry, dict) or time.time() - float(entry.get("fetched", 0)) > CACHE_TTL_SECONDS:
        return None
    record = entry.get("facts")
    if not isinstance(record, dict):
        return None
    record["first_published"] = _parse_time(record.get("first_published"))
    # JSON has no tuples: the advisory lists come back as lists.
    advisories, malware = record.get("advisories"), record.get("malware_advisories")
    record["advisories"] = tuple(advisories) if isinstance(advisories, list) else None
    record["malware_advisories"] = tuple(malware) if isinstance(malware, list) else ()
    try:
        return PackageFacts(**record)
    except TypeError:
        return None


def lookup(ecosystem: str, name: str, fetch: Fetch = fetch_json, post: Post = post_json) -> PackageFacts:
    """Returns what the public registry and OSV say about a package.

    Args:
        ecosystem: ``npm`` or ``pypi``.
        name: Normalised package name.
        fetch: JSON fetcher for the registries; tests pass a fake one.
        post: JSON poster for OSV queries; tests pass a fake one.

    Returns:
        The facts, from a cache younger than a day when available. Unreachable registries give
        ``PackageFacts(reachable=False)``; when only OSV does not answer, the registry's facts come
        back with ``advisories`` None. Neither case is cached, so the next lookup asks again.
    """
    key = f"{CACHE_FORMAT}:{ecosystem}:{name}"
    cached = _cached(key)
    if cached is not None:
        return cached
    try:
        facts = _npm_facts(name, fetch) if ecosystem == "npm" else _pypi_facts(name, fetch)
    except OSError:
        return PackageFacts(reachable=False)
    facts = _with_advisories(facts, ecosystem, name, post)
    if facts.latest_version is not None and facts.advisories is None:
        return facts  # OSV did not answer: ask it again next time instead of caching the gap
    _store(key, facts)
    return facts
