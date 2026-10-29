"""PreToolUse hook on Bash and PowerShell: a new dependency needs a real, established, safe package.

AI assistants sometimes name packages that do not exist, and attackers register those names
("slopsquatting"). Before a command installs or runs a package the project does not already use,
this hook asks the public registry and OSV.dev about it. It pauses the command and asks the person
to confirm, with every reason, when the package does not exist, is younger than
MIN_PACKAGE_AGE_DAYS, has fewer than MIN_WEEKLY_DOWNLOADS, cannot be verified, has known
vulnerabilities in its latest version, or declares no license or one the project should agree to
first (proprietary or custom terms, strong or network copyleft, not open source). When OSV reports
the latest version as malware, it denies the command instead. Established packages pass silently.

Packages the project already declares or has locked, local npx binaries, npm scopes served by a
private registry (.npmrc) and names matching KONUNDRM_TRUSTED_PACKAGES (comma-separated globs such
as ``@konundrm/*,konundrm-*``) are not checked. Licenses matching KONUNDRM_ACCEPTED_LICENSES
(comma-separated, case-insensitive globs such as ``GPL-3.0*,EUPL-1.2``) need no confirmation.
KONUNDRM_DEPENDENCY_GUARD=off turns the guard off.

Sections:
    license_concern()  — why a license needs the project's agreement, if it does.
    concerns()         — every reason a package deserves a human look.
    review_requests()  — the findings for the packages a command would fetch.
    main()             — the hook: deny malware, ask about everything else.
"""

from __future__ import annotations

import os
import re
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from fnmatch import fnmatchcase
from pathlib import Path
from typing import TYPE_CHECKING

from hook_io import ask_before_tool_use, deny_tool_use, read_hook_input
from package_installs import PackageRequest, find_package_requests

if TYPE_CHECKING:
    from package_registry import PackageFacts

# This hook runs before every Bash command and almost none install anything, so the registry,
# project and logging modules (urllib alone costs ~0.2 s on Windows) load only when one does.

MIN_PACKAGE_AGE_DAYS = 30
MIN_WEEKLY_DOWNLOADS = 100
MAX_LISTED_ADVISORIES = 3
MAX_QUOTED_LICENSE_LENGTH = 80
REGISTRY_NAMES = {"npm": "npm", "pypi": "PyPI"}

# Licenses a project should take on knowingly, searched case-insensitively in each license of an
# expression; the first match names the kind. Weak copyleft (LGPL, MPL, EPL) passes.
RESTRICTED_LICENSES = (
    (r"\bAGPL|Affero", "network copyleft"),
    (r"(?<![a-z])(?<!lesser )(?<!library )(?:GPL|General Public Licen[cs]e)", "strong copyleft"),  # not LGPL
    (r"\bEUPL|European Union Public Licen[cs]e", "strong copyleft"),
    (r"\bOSL\b|Open Software Licen[cs]e", "network copyleft"),
    (r"\bRPL\b|Reciprocal Public Licen[cs]e", "network copyleft"),
    (r"\bCPAL|Common Public Attribution Licen[cs]e", "network copyleft"),
    (r"\bSSPL|Server Side Public Licen[cs]e", "not open source"),
    (r"\bBUSL|Business Source", "not open source"),  # BSL-1.0 is the permissive Boost license
    (r"\bElastic(?:-2\.0| Licen[cs]e)", "not open source"),
    (r"Commons[- ]Clause", "not open source"),
    (r"PolyForm", "not open source"),
    (r"\bCC[- ]BY[- ]NC|Non[- ]?Commercial", "not open source"),
    (r"Free (?:To Use But Restricted|For (?:Educational|Home) Use)|Freeware", "not open source"),  # PyPI
    (r"Proprietary|\bUNLICENSED\b", "proprietary"),  # npm's UNLICENSED, not the public-domain Unlicense
    (r"\bSEE LICEN[CS]E IN\b", "custom terms"),  # npm's pointer to a license file
)
# SPDX operators are upper case: the "or" in "v2 or later" belongs to a license's name.
LICENSE_SYNTAX = ("(", ")", "AND", "OR")


@dataclass(frozen=True)
class Finding:
    """Why one package needs a human look before it is installed.

    Attributes:
        package: Registry name of the package.
        line: Message line with the package, its registry and every concern.
        is_malware: True when OSV reports its latest version as malware, which blocks the command.
    """

    package: str
    line: str
    is_malware: bool = False


def guard_disabled() -> bool:
    """Returns True when the person turned the guard off with KONUNDRM_DEPENDENCY_GUARD=off."""
    return os.environ.get("KONUNDRM_DEPENDENCY_GUARD", "").strip().lower() in {"off", "0", "false"}


def _glob_patterns(variable: str) -> list[str]:
    """Reads comma-separated globs from an environment variable, in lower case."""
    return [pattern.strip().lower() for pattern in os.environ.get(variable, "").split(",") if pattern.strip()]


def new_public_packages(requests: list[PackageRequest], root: Path) -> list[PackageRequest]:
    """Keeps the packages that are new to the project and come from the public registry.

    Args:
        requests: Packages a command would fetch.
        root: Project root, read once for its declared packages, npx binaries and private scopes.
    """
    from project_dependencies import declared_packages, local_binaries, private_npm_scopes

    declared, binaries, scopes = declared_packages(root), local_binaries(root), private_npm_scopes(root)
    trusted = _glob_patterns("KONUNDRM_TRUSTED_PACKAGES")

    def is_new(request: PackageRequest) -> bool:
        if (request.ecosystem, request.name) in declared or any(fnmatchcase(request.name, p) for p in trusted):
            return False
        if request.ecosystem == "npm" and request.runs_binary and request.name in binaries:
            return False
        return not (request.ecosystem == "npm" and request.name.split("/", 1)[0] in scopes)

    return [request for request in requests if is_new(request)]


def _license_tokens(expression: str) -> list[str]:
    """Splits a license expression into parentheses, AND, OR and the licenses between them.

    Consecutive words form one license, so descriptive names stay whole and ``X WITH Y`` stays one
    license. A parenthesis right after a word belongs to the name, as in "GNU Lesser General Public
    License v2 or later (LGPLv2+)": in SPDX a group never follows a license directly.
    """
    tokens: list[str] = []
    open_in_name = 0  # parentheses opened inside the current license's name
    for piece in re.findall(r"[()]|[^\s()]+", expression):
        in_name = bool(tokens) and tokens[-1] not in LICENSE_SYNTAX
        if open_in_name or (in_name and piece == "("):
            open_in_name += {"(": 1, ")": -1}.get(piece, 0)
            tokens[-1] += piece if piece == ")" or tokens[-1].endswith("(") else f" {piece}"
        elif in_name and piece not in LICENSE_SYNTAX:
            tokens[-1] += f" {piece}"
        else:
            tokens.append(piece)
    return tokens


def _is_accepted(license_name: str, accepted: Sequence[str]) -> bool:
    name = license_name.lower()
    return any(fnmatchcase(name, pattern.lower()) for pattern in accepted)


def _restriction_kind(license_part: str) -> str | None:
    return next(
        (kind for pattern, kind in RESTRICTED_LICENSES if re.search(pattern, license_part, re.IGNORECASE)), None
    )


def _restriction(license_name: str, accepted: Sequence[str]) -> str | None:
    """Names the restriction one license of an expression carries; None when the project may use it.

    ``X WITH Y`` is restricted when either part is (``Apache-2.0 WITH Commons-Clause``). An accepted
    glob clears the whole name or one of its parts.
    """
    if _is_accepted(license_name, accepted):
        return None
    parts = [part for part in license_name.split(" WITH ") if not _is_accepted(part, accepted)]
    return next((kind for kind in map(_restriction_kind, parts) if kind), None)


def _alternatives_hold(items: list[str | bool]) -> bool | None:
    """Tells whether some OR alternative has only acceptable licenses; None when there is no license."""
    alternatives: list[list[bool]] = [[]]
    for item in items:
        if item == "OR":
            alternatives.append([])
        elif isinstance(item, bool):
            alternatives[-1].append(item)
    present = [alternative for alternative in alternatives if alternative]
    return any(all(alternative) for alternative in present) if present else None


def _expression_holds(values: list[str | bool]) -> bool | None:
    """Evaluates licenses (True when acceptable) joined by AND, OR and parentheses.

    OR binds looser than AND, as in SPDX. Unbalanced parentheses are tolerated without dropping any
    license. None means that the expression names no license at all.
    """
    groups: list[list[str | bool]] = [[]]
    closing = [")"] * values.count("(")
    for value in [*values, *closing]:
        if value == "(":
            groups.append([])
        elif value == ")" and len(groups) > 1:
            inner = _alternatives_hold(groups.pop())
            groups[-1].extend([] if inner is None else [inner])
        elif value != ")":
            groups[-1].append(value)
    return _alternatives_hold(groups[0])


def _quoted(text: str) -> str:
    shown = " ".join(text.split())
    return shown if len(shown) <= MAX_QUOTED_LICENSE_LENGTH else f"{shown[: MAX_QUOTED_LICENSE_LENGTH - 1]}…"


def license_concern(license_text: str | None, accepted: Sequence[str] = ()) -> str | None:
    """Explains why a package's license needs the project's agreement before it is installed.

    The license is an SPDX expression or a descriptive name. It is fine when one of its ``OR``
    alternatives combines (``AND``, ``WITH``) only licenses that match an accepted glob or are none
    of: strong or network copyleft, proprietary, custom terms, or otherwise not open source. Weak
    copyleft such as LGPL or MPL is fine. npm's ``UNLICENSED`` and ``SEE LICENSE IN …`` markers mean
    proprietary and custom terms.

    Args:
        license_text: The license as the registry declares it; None when it declares none.
        accepted: Case-insensitive globs of licenses the project accepts (KONUNDRM_ACCEPTED_LICENSES).

    Returns:
        A short reason, or None when the license needs no agreement.
    """
    text = license_text or ""
    tokens = _license_tokens(text)
    restrictions = {token: _restriction(token, accepted) for token in tokens if token not in LICENSE_SYNTAX}
    holds = _expression_holds([restrictions[token] is None if token in restrictions else token for token in tokens])
    if holds is None:
        return "declares no license"
    if holds:
        return None
    kinds = sorted({kind for kind in restrictions.values() if kind})
    return f'is licensed under "{_quoted(text)}" ({", ".join(kinds)})'


def _listed(advisories: Sequence[str]) -> str:
    shown = ", ".join(advisories[:MAX_LISTED_ADVISORIES])
    hidden = len(advisories) - MAX_LISTED_ADVISORIES
    return f"{shown} and {hidden} more" if hidden > 0 else shown


def _advisory_concerns(facts: PackageFacts) -> list[str]:
    """Reasons from OSV: a malware report and known vulnerabilities in the latest version."""
    version = f"its latest version {facts.latest_version}" if facts.latest_version else "its latest version"
    vulnerabilities = [advisory for advisory in facts.advisories or () if advisory not in facts.malware_advisories]
    reasons = []
    if facts.malware_advisories:
        reasons.append(f"has a malware report for {version}: {_listed(facts.malware_advisories)}")
    if vulnerabilities:
        reasons.append(f"has known vulnerabilities in {version}: {_listed(vulnerabilities)}")
    return reasons


def _age_concern(facts: PackageFacts, now: datetime) -> str | None:
    if facts.first_published is None:
        return None
    age_days = (now - facts.first_published).days
    return f"was first published {age_days} day(s) ago" if age_days < MIN_PACKAGE_AGE_DAYS else None


def _popularity_concern(facts: PackageFacts) -> str | None:
    if facts.weekly_downloads is not None and facts.weekly_downloads < MIN_WEEKLY_DOWNLOADS:
        return f"had only {facts.weekly_downloads} downloads last week"
    return None


def concerns(facts: PackageFacts, now: datetime, registry: str, accepted_licenses: Sequence[str] = ()) -> list[str]:
    """Lists every reason a package deserves a human look before it is installed.

    Args:
        facts: What the registry and OSV said about the package.
        now: Current time, timezone-aware.
        registry: Registry name for the messages (npm, PyPI).
        accepted_licenses: Globs of licenses the project accepts (KONUNDRM_ACCEPTED_LICENSES).

    Returns:
        Short reasons, the most serious first; empty when the package looks established and safe.
        An unknown latest version or an OSV that did not answer raises no concern of its own.
    """
    if not facts.reachable:
        return [f"could not be checked: {registry} did not answer (offline, proxy or outage)"]
    if not facts.exists:
        return [f"does not exist on {registry}; the name may be invented, so check the spelling and the official docs"]
    reasons = [*_advisory_concerns(facts), _age_concern(facts, now), _popularity_concern(facts)]
    if facts.latest_version is not None:  # the license is read from the latest version's metadata
        reasons.append(license_concern(facts.license, accepted_licenses))
    return [reason for reason in reasons if reason]


def review_requests(
    requests: list[PackageRequest],
    lookup_facts: Callable[[str, str], PackageFacts],
    now: datetime,
    accepted_licenses: Sequence[str] = (),
) -> list[Finding]:
    """Checks each package against its registry and OSV.

    Args:
        requests: New public packages a command would fetch.
        lookup_facts: Returns the facts for an (ecosystem, name) pair.
        now: Current time, timezone-aware.
        accepted_licenses: Globs of licenses the project accepts (KONUNDRM_ACCEPTED_LICENSES).

    Returns:
        One finding per package that needs a human look, in command order.
    """
    findings = []
    for request in requests:
        registry = REGISTRY_NAMES[request.ecosystem]
        facts = lookup_facts(request.ecosystem, request.name)
        reasons = concerns(facts, now, registry, accepted_licenses)
        if reasons:
            line = f"- {request.name} ({registry}) {'; '.join(reasons)}."
            findings.append(Finding(request.name, line, is_malware=bool(facts.malware_advisories)))
    return findings


def _confirmation_request(lines: str) -> str:
    return (
        "konundrm-eng dependency guard: confirm these packages before installing them.\n"
        f"{lines}\n"
        "Approve only if the name matches the package's official documentation (AI assistants sometimes "
        "invent package names, and attackers register them) and the project can accept its license and "
        "known vulnerabilities (Standards → Security)."
    )


def _denial(lines: str) -> str:
    return (
        "konundrm-eng dependency guard: blocked. OSV reports the version this command would install as "
        "malware.\n"
        f"{lines}\n"
        "Do not install it another way: tell the person. If they really need the package, they can install "
        "a known-safe version by hand, pinned (name@1.2.3 or name==1.2.3), after checking its advisories "
        "on osv.dev."
    )


def main() -> int:
    """Runs the hook for a PreToolUse event read from stdin."""
    event = read_hook_input()
    command = str((event.get("tool_input") or {}).get("command") or "")
    if not command or guard_disabled():
        return 0
    requests = list(find_package_requests(command))
    if not requests:
        return 0
    from metrics_log import record_event
    from package_registry import lookup
    from project_paths import project_root

    root = project_root(event)
    now = datetime.now(timezone.utc)
    accepted_licenses = _glob_patterns("KONUNDRM_ACCEPTED_LICENSES")
    findings = review_requests(new_public_packages(requests, root), lookup, now, accepted_licenses)
    if not findings:
        return 0
    lines = "\n".join(finding.line for finding in findings)
    packages = sorted(finding.package for finding in findings)
    malware = sorted(finding.package for finding in findings if finding.is_malware)
    if malware:
        record_event(root, "dependency_denied", event.get("session_id"), packages=packages, malware=malware)
        deny_tool_use(_denial(lines))
    else:
        record_event(root, "dependency_flagged", event.get("session_id"), packages=packages)
        ask_before_tool_use(_confirmation_request(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
