"""Unit tests for hooks/scripts/package_registry.py (with a fake fetcher, never the network)."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import package_registry
from package_registry import PackageFacts, lookup

REACT_PAGES = {
    "/last-week/react": {"downloads": 50_000_000},
    "/react/latest": {"name": "react", "version": "19.2.0", "license": "MIT"},
}
GITHUB_MALWARE = {
    "id": "GHSA-9wxw-8f6c-qx2p",
    "summary": "Malicious Package in tiny-lib",
    "database_specific": {"cwe_ids": ["CWE-506"]},
}


class FakeRegistry:
    """Answers registry URLs from a dict and records what was asked."""

    def __init__(self, pages: dict[str, Any], unreachable: tuple[str, ...] = ()) -> None:
        self.pages, self.unreachable, self.requested = pages, unreachable, []

    def __call__(self, url: str) -> tuple[int, Any]:
        self.requested.append(url)
        if any(fragment in url for fragment in self.unreachable):
            raise OSError("unreachable")
        for fragment, body in self.pages.items():
            if url.endswith(fragment):
                return 200, body
        return 404, None


class FakeOsv:
    """Answers OSV queries with the records configured per package name and records each query."""

    def __init__(self, vulns: dict[str, list[dict[str, Any]]] | None = None, unreachable: bool = False) -> None:
        self.vulns, self.unreachable = vulns or {}, unreachable
        self.queries: list[tuple[str, dict[str, Any]]] = []

    def __call__(self, url: str, payload: dict[str, Any]) -> tuple[int, Any]:
        self.queries.append((url, payload))
        if self.unreachable:
            raise OSError("unreachable")
        records = self.vulns.get(payload["package"]["name"], [])
        return 200, ({"vulns": records} if records else {})


def vulns(*ids: str) -> list[dict[str, Any]]:
    return [{"id": advisory, "summary": f"Advisory {advisory}"} for advisory in ids]


class LookupTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        patcher = mock.patch.dict(os.environ, {"CLAUDE_PLUGIN_DATA": self._tmp.name})
        patcher.start()
        self.addCleanup(patcher.stop)
        for variable in (
            "KONUNDRM_NPM_REGISTRY",
            "KONUNDRM_NPM_DOWNLOADS_API",
            "KONUNDRM_PYPI_URL",
            "KONUNDRM_PYPISTATS_URL",
            "KONUNDRM_OSV_URL",
        ):
            os.environ.pop(variable, None)  # restored by the patcher above
        network = mock.patch("urllib.request.urlopen", side_effect=AssertionError("tests must not use the network"))
        network.start()
        self.addCleanup(network.stop)

    def test_an_npm_package_with_many_downloads_is_established_without_a_large_fetch(self) -> None:
        registry = FakeRegistry(REACT_PAGES)
        facts = lookup("npm", "react", registry, FakeOsv())
        self.assertEqual((facts.exists, facts.weekly_downloads), (True, 50_000_000))
        self.assertEqual(
            registry.requested,
            ["https://api.npmjs.org/downloads/point/last-week/react", "https://registry.npmjs.org/react/latest"],
        )

    def test_npm_reads_the_latest_version_and_its_license_from_the_small_manifest(self) -> None:
        facts = lookup("npm", "react", FakeRegistry(REACT_PAGES), FakeOsv())
        self.assertEqual((facts.latest_version, facts.license), ("19.2.0", "MIT"))

    def test_npm_reads_license_objects_and_legacy_license_lists(self) -> None:
        manifests = [
            ("ISC", {"version": "1.0.0", "license": {"type": "ISC", "url": "https://opensource.org/licenses/ISC"}}),
            ("MIT OR Apache-2.0", {"version": "1.0.0", "licenses": [{"type": "MIT"}, {"type": "Apache-2.0"}]}),
            ("BSD-2-Clause", {"version": "1.0.0", "licenses": {"type": "BSD-2-Clause", "url": "https://x.test"}}),
            (None, {"version": "1.0.0"}),
        ]
        for index, (expected, manifest) in enumerate(manifests):
            with self.subTest(expected=expected):
                name = f"lib-{index}"
                registry = FakeRegistry({f"/last-week/{name}": {"downloads": 20_000}, f"/{name}/latest": manifest})
                self.assertEqual(lookup("npm", name, registry, FakeOsv()).license, expected)

    def test_a_little_used_npm_package_reports_its_creation_date(self) -> None:
        registry = FakeRegistry(
            {"/last-week/tiny-lib": {"downloads": 12}, "/tiny-lib": {"time": {"created": "2026-10-01T10:00:00.000Z"}}}
        )
        facts = lookup("npm", "tiny-lib", registry, FakeOsv())
        self.assertEqual(facts.first_published, datetime(2026, 10, 1, 10, tzinfo=timezone.utc))
        self.assertEqual(facts.weekly_downloads, 12)

    def test_scoped_npm_names_are_escaped_for_the_registry(self) -> None:
        registry = FakeRegistry({"/@acme%2Fwidget": {"time": {}}, "/@acme%2Fwidget/latest": {"version": "1.0.0"}})
        lookup("npm", "@acme/widget", registry, FakeOsv())
        self.assertEqual(
            registry.requested[1:],
            ["https://registry.npmjs.org/@acme%2Fwidget", "https://registry.npmjs.org/@acme%2Fwidget/latest"],
        )

    def test_an_npm_package_without_a_latest_manifest_still_exists(self) -> None:
        facts = lookup("npm", "react", FakeRegistry({"/last-week/react": {"downloads": 50_000}}), FakeOsv())
        self.assertEqual((facts.exists, facts.latest_version, facts.license), (True, None, None))

    def test_a_missing_package_does_not_exist(self) -> None:
        osv = FakeOsv()
        self.assertEqual(
            lookup("pypi", "reqeusts-pro", FakeRegistry({}), osv), PackageFacts(reachable=True, exists=False)
        )
        self.assertEqual(osv.queries, [])

    def test_pypi_reports_the_earliest_upload_and_recent_downloads(self) -> None:
        releases = {
            "1.0": [{"upload_time_iso_8601": "2019-03-01T00:00:00Z"}],
            "0.1": [{"upload_time_iso_8601": "2018-01-01T00:00:00Z"}],
            "2.0": [],
        }
        registry = FakeRegistry(
            {"/pypi/attrs/json": {"releases": releases}, "/attrs/recent": {"data": {"last_week": 9}}}
        )
        facts = lookup("pypi", "attrs", registry, FakeOsv())
        self.assertEqual(facts.first_published, datetime(2018, 1, 1, tzinfo=timezone.utc))
        self.assertEqual(facts.weekly_downloads, 9)

    def test_pypi_reads_the_latest_version_and_prefers_its_license_expression(self) -> None:
        info = {
            "version": "25.4.0",
            "license_expression": "MIT",
            "license": None,
            "classifiers": ["License :: OSI Approved :: Apache Software License"],
        }
        facts = lookup("pypi", "attrs", FakeRegistry({"/pypi/attrs/json": {"info": info, "releases": {}}}), FakeOsv())
        self.assertEqual((facts.latest_version, facts.license), ("25.4.0", "MIT"))

    def test_pypi_falls_back_to_a_short_license_field_then_to_the_classifiers(self) -> None:
        classifiers = [
            "Programming Language :: Python :: 3",
            "License :: OSI Approved :: GNU Lesser General Public License v2 or later (LGPLv2+)",
            "License :: OSI Approved :: MIT License",
        ]
        from_classifiers = "GNU Lesser General Public License v2 or later (LGPLv2+) OR MIT License"
        cases = [
            ("BSD-3-Clause", " BSD-3-Clause ", classifiers),
            (from_classifiers, "Copyright (c) 2026 Acme\n\nPermission is hereby granted...", classifiers),
            (from_classifiers, "x" * 101, classifiers),
            (from_classifiers, "UNKNOWN", classifiers),
            (None, "", ["Programming Language :: Python :: 3"]),
        ]
        for index, (expected, license_field, package_classifiers) in enumerate(cases):
            with self.subTest(license_field=license_field[:20]):
                info = {"version": "1.0", "license": license_field, "classifiers": package_classifiers}
                registry = FakeRegistry({f"/pypi/lib-{index}/json": {"info": info, "releases": {}}})
                self.assertEqual(lookup("pypi", f"lib-{index}", registry, FakeOsv()).license, expected)

    def test_pypistats_failures_do_not_hide_the_package(self) -> None:
        registry = FakeRegistry({"/pypi/attrs/json": {"releases": {}}}, unreachable=("pypistats",))
        self.assertTrue(lookup("pypi", "attrs", registry, FakeOsv()).exists)

    def test_osv_is_asked_about_the_latest_version(self) -> None:
        registry = FakeRegistry({"/pypi/tiny-lib/json": {"info": {"version": "0.3.1"}, "releases": {}}})
        osv = FakeOsv()
        lookup("pypi", "tiny-lib", registry, osv)
        self.assertEqual(
            osv.queries,
            [
                (
                    "https://api.osv.dev/v1/query",
                    {"package": {"name": "tiny-lib", "ecosystem": "PyPI"}, "version": "0.3.1"},
                )
            ],
        )

    def test_osv_advisories_are_listed_once_and_sorted(self) -> None:
        osv = FakeOsv({"react": vulns("PYSEC-2026-1", "GHSA-aaaa-bbbb-cccc", "PYSEC-2026-1")})
        facts = lookup("npm", "react", FakeRegistry(REACT_PAGES), osv)
        self.assertEqual(facts.advisories, ("GHSA-aaaa-bbbb-cccc", "PYSEC-2026-1"))
        self.assertEqual(facts.malware_advisories, ())
        self.assertEqual(osv.queries[0][1]["package"], {"name": "react", "ecosystem": "npm"})

    def test_a_version_without_advisories_has_an_empty_list(self) -> None:
        facts = lookup("npm", "react", FakeRegistry(REACT_PAGES), FakeOsv())
        self.assertEqual((facts.advisories, facts.malware_advisories), ((), ()))

    def test_openssf_and_github_malware_reports_are_told_apart_from_vulnerabilities(self) -> None:
        def github(identifier: str, summary: str, *cwe_ids: str) -> dict[str, Any]:
            return {"id": identifier, "summary": summary, "database_specific": {"cwe_ids": list(cwe_ids)}}

        records = [
            *vulns("MAL-2026-0042", "GHSA-1111-2222-3333"),
            GITHUB_MALWARE,
            github("GHSA-5555-6666-7777", "Embedded malicious code in the install script", "CWE-506"),
            github("GHSA-2222-3333-4444", "Malicious code injection in tiny-lib templates", "CWE-94"),
            github("GHSA-8888-9999-aaaa", "Malicious Package in tiny-lib"),
        ]
        facts = lookup("npm", "react", FakeRegistry(REACT_PAGES), FakeOsv({"react": records}))
        self.assertEqual(facts.malware_advisories, ("GHSA-5555-6666-7777", "GHSA-9wxw-8f6c-qx2p", "MAL-2026-0042"))
        self.assertEqual(len(facts.advisories or ()), 6)

    def test_an_osv_failure_keeps_the_registry_facts_and_is_not_cached(self) -> None:
        facts = lookup("npm", "react", FakeRegistry(REACT_PAGES), FakeOsv(unreachable=True))
        self.assertEqual((facts.reachable, facts.exists, facts.license, facts.advisories), (True, True, "MIT", None))
        osv = FakeOsv()
        self.assertEqual(lookup("npm", "react", FakeRegistry(REACT_PAGES), osv).advisories, ())
        self.assertEqual(len(osv.queries), 1)

    def test_osv_answers_without_an_advisory_list_count_as_failures(self) -> None:
        answers = [(404, None), (200, {"vulns": "none"}), (200, ["not", "an", "object"])]
        for index, answer in enumerate(answers):
            with self.subTest(answer=answer):
                pages = {f"/last-week/lib-{index}": {"downloads": 20_000}, f"/lib-{index}/latest": {"version": "1"}}
                facts = lookup("npm", f"lib-{index}", FakeRegistry(pages), lambda _url, _payload, a=answer: a)
                self.assertEqual((facts.exists, facts.advisories), (True, None))

    def test_osv_is_not_asked_without_a_latest_version(self) -> None:
        osv = FakeOsv()
        lookup("npm", "react", FakeRegistry({"/last-week/react": {"downloads": 50_000}}), osv)
        self.assertEqual(osv.queries, [])

    def test_an_unreachable_registry_is_reported_and_not_cached(self) -> None:
        self.assertFalse(lookup("npm", "x", FakeRegistry({}, unreachable=("npmjs",)), FakeOsv()).reachable)
        registry = FakeRegistry({"/last-week/x": {"downloads": 20_000}})
        self.assertTrue(lookup("npm", "x", registry, FakeOsv()).exists)
        self.assertTrue(registry.requested)

    def test_answers_are_cached_for_a_day_with_every_fact(self) -> None:
        pages = {
            "/last-week/tiny-lib": {"downloads": 12},
            "/tiny-lib": {"time": {"created": "2026-10-01T10:00:00.000Z"}},
            "/tiny-lib/latest": {"version": "0.1.0", "license": "AGPL-3.0-only"},
        }
        first = lookup("npm", "tiny-lib", FakeRegistry(pages), FakeOsv({"tiny-lib": [GITHUB_MALWARE]}))
        registry, osv = FakeRegistry({}), FakeOsv()
        restored = lookup("npm", "tiny-lib", registry, osv)
        self.assertEqual((registry.requested, osv.queries), ([], []))
        self.assertEqual(restored, first)  # the date and the advisory tuples come back as they were
        self.assertEqual(restored.malware_advisories, ("GHSA-9wxw-8f6c-qx2p",))

    def test_entries_cached_by_an_older_version_are_fetched_again(self) -> None:
        old_facts = {"reachable": True, "exists": True, "first_published": None, "weekly_downloads": 50_000}
        cache = {"npm:react": {"fetched": time.time(), "facts": old_facts}}
        (Path(self._tmp.name) / "registry-cache.json").write_text(json.dumps(cache), encoding="utf-8")
        registry = FakeRegistry(REACT_PAGES)
        self.assertEqual(lookup("npm", "react", registry, FakeOsv()).license, "MIT")
        self.assertTrue(registry.requested)


class HttpHelpersTest(unittest.TestCase):
    def test_fetch_json_refuses_urls_that_are_not_http(self) -> None:
        with self.assertRaises(OSError):
            package_registry.fetch_json("file:///etc/passwd")

    def test_post_json_refuses_urls_that_are_not_http(self) -> None:
        with self.assertRaises(OSError):
            package_registry.post_json("file:///etc/passwd", {"package": {"name": "x"}})


if __name__ == "__main__":
    unittest.main()
