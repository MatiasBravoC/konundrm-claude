"""Unit tests for hooks/scripts/guard_new_dependencies.py."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from guard_new_dependencies import Finding, concerns, license_concern, new_public_packages, review_requests
from package_installs import PackageRequest
from package_registry import PackageFacts

NOW = datetime(2026, 10, 11, tzinfo=timezone.utc)
ESTABLISHED_MIT = PackageFacts(True, True, NOW - timedelta(days=900), 50_000, "2.1.0", "MIT", ())


class LicenseConcernTest(unittest.TestCase):
    def assert_acceptable(self, *licenses: str, accepted: tuple[str, ...] = ()) -> None:
        for declared in licenses:
            with self.subTest(license=declared):
                self.assertIsNone(license_concern(declared, accepted))

    def assert_flagged(self, kind: str, *licenses: str, accepted: tuple[str, ...] = ()) -> None:
        for declared in licenses:
            with self.subTest(license=declared):
                self.assertIn(f"({kind}", license_concern(declared, accepted) or "")

    def test_permissive_and_weak_copyleft_licenses_are_acceptable(self) -> None:
        self.assert_acceptable(
            "MIT", "Apache-2.0", "BSD-3-Clause", "ISC", "0BSD", "CC0-1.0", "CC-BY-4.0", "MPL-2.0", "EPL-2.0"
        )
        self.assert_acceptable("LGPL-2.1-or-later", "LGPL-3.0-only")

    def test_look_alikes_of_restricted_licenses_are_acceptable(self) -> None:
        self.assert_acceptable("Unlicense", "BSL-1.0")  # public domain and Boost, not UNLICENSED and BUSL

    def test_strong_copyleft_licenses_are_flagged(self) -> None:
        self.assert_flagged("strong copyleft", "GPL-3.0-only", "GPL-2.0+", "GPL-3.0-or-later", "GPLv3", "EUPL-1.2")

    def test_network_copyleft_licenses_are_flagged(self) -> None:
        self.assert_flagged("network copyleft", "AGPL-3.0-only", "AGPL-3.0-or-later", "OSL-3.0", "RPL-1.5", "CPAL-1.0")

    def test_licenses_that_are_not_open_source_are_flagged(self) -> None:
        self.assert_flagged(
            "not open source",
            "SSPL-1.0",
            "BUSL-1.1",
            "Business Source License 1.1",
            "Elastic-2.0",
            "Elastic License 2.0",
            "Commons Clause",
            "PolyForm-Noncommercial-1.0.0",
            "CC-BY-NC-4.0",
            "Creative Commons Attribution-NonCommercial 4.0",
        )

    def test_npm_markers_for_proprietary_and_custom_terms_are_flagged(self) -> None:
        self.assert_flagged("proprietary", "UNLICENSED")
        self.assert_flagged("custom terms", "SEE LICENSE IN LICENSE.md")

    def test_an_undeclared_license_is_flagged(self) -> None:
        for declared in (None, "", "   "):
            with self.subTest(license=declared):
                self.assertEqual(license_concern(declared), "declares no license")

    def test_or_is_acceptable_when_any_alternative_is(self) -> None:
        self.assert_acceptable("MIT OR GPL-3.0-only", "GPL-2.0-only OR Apache-2.0")
        self.assert_flagged("network copyleft", "GPL-2.0-only OR AGPL-3.0-only")

    def test_and_is_acceptable_only_when_every_license_is(self) -> None:
        self.assert_acceptable("MIT AND Apache-2.0")
        self.assert_flagged("strong copyleft", "MIT AND GPL-3.0-only")

    def test_with_binds_an_exception_to_its_license(self) -> None:
        self.assert_acceptable("Apache-2.0 WITH LLVM-exception", "MIT OR GPL-2.0-only WITH Classpath-exception-2.0")
        self.assert_flagged("strong copyleft", "GPL-2.0-only WITH Classpath-exception-2.0")
        self.assert_flagged("not open source", "Apache-2.0 WITH Commons-Clause")

    def test_parentheses_group_alternatives(self) -> None:
        self.assert_acceptable("(MIT OR GPL-3.0-only) AND Apache-2.0", "(MIT OR Apache-2.0)")
        self.assert_flagged("network copyleft", "(GPL-3.0-only OR AGPL-3.0-only) AND MIT")
        self.assert_flagged("not open source", "MIT AND (GPL-3.0-only OR SSPL-1.0)")

    def test_unbalanced_parentheses_never_drop_a_license(self) -> None:
        self.assert_acceptable("(MIT", "MIT)", "MIT OR")
        self.assert_flagged("not open source", "MIT ) AND SSPL-1.0", "(MIT AND SSPL-1.0")

    def test_descriptive_names_are_judged_by_their_words(self) -> None:
        self.assert_acceptable(
            "MIT License",
            "Apache Software License",
            "GNU Lesser General Public License v2 or later (LGPLv2+)",
            "GNU Library or Lesser General Public License (LGPL)",
        )
        self.assert_flagged("network copyleft", "GNU Affero General Public License v3")
        self.assert_flagged("strong copyleft", "GNU General Public License v2 or later (GPLv2+)")

    def test_pypi_classifiers_joined_with_or_are_alternatives(self) -> None:
        self.assert_acceptable("GNU General Public License v3 (GPLv3) OR MIT License")
        self.assert_flagged("proprietary", "Other/Proprietary License")
        self.assert_flagged("not open source", "Free To Use But Restricted", "Freeware")

    def test_accepted_globs_clear_a_license_case_insensitively(self) -> None:
        self.assert_acceptable("GPL-3.0-or-later", "MIT AND GPL-3.0-only", accepted=("gpl-3.0*",))
        self.assert_acceptable("GPL-2.0-only WITH Classpath-exception-2.0", accepted=("GPL-2.0-ONLY",))
        self.assert_acceptable("UNLICENSED", accepted=("unlicensed",))

    def test_accepted_globs_clear_only_what_they_match(self) -> None:
        self.assert_flagged("network copyleft", "AGPL-3.0-only", accepted=("GPL-3.0*",))
        self.assert_flagged("not open source", "MIT WITH Commons-Clause", accepted=("MIT",))
        self.assertEqual(license_concern(None, ("*",)), "declares no license")

    def test_the_reason_quotes_the_declared_license_and_its_kinds(self) -> None:
        self.assertEqual(license_concern("AGPL-3.0-only"), 'is licensed under "AGPL-3.0-only" (network copyleft)')
        self.assertEqual(
            license_concern("GPL-3.0-only OR SSPL-1.0"),
            'is licensed under "GPL-3.0-only OR SSPL-1.0" (not open source, strong copyleft)',
        )

    def test_long_license_texts_are_shortened_in_the_reason(self) -> None:
        reason = license_concern("GNU General Public License " + "terms " * 40) or ""
        self.assertLess(len(reason), 140)
        self.assertIn("…", reason)


class ConcernsTest(unittest.TestCase):
    def test_an_established_mit_package_raises_no_concern(self) -> None:
        self.assertEqual(concerns(ESTABLISHED_MIT, NOW, "npm"), [])

    def test_flags_missing_new_unpopular_and_unverifiable_packages(self) -> None:
        cases = {
            "does not exist": PackageFacts(True, False),
            "3 day(s) ago": replace(ESTABLISHED_MIT, first_published=NOW - timedelta(days=3)),
            "only 7 downloads": replace(ESTABLISHED_MIT, weekly_downloads=7),
            "could not be checked": PackageFacts(False),
        }
        for expected, facts in cases.items():
            with self.subTest(expected=expected):
                [reason] = concerns(facts, NOW, "npm")
                self.assertIn(expected, reason)

    def test_reports_every_concern_of_a_package_most_serious_first(self) -> None:
        facts = PackageFacts(True, True, NOW - timedelta(days=3), 7, "0.1.0", "AGPL-3.0-only", ("GHSA-1",))
        self.assertEqual(
            concerns(facts, NOW, "npm"),
            [
                "has known vulnerabilities in its latest version 0.1.0: GHSA-1",
                "was first published 3 day(s) ago",
                "had only 7 downloads last week",
                'is licensed under "AGPL-3.0-only" (network copyleft)',
            ],
        )

    def test_vulnerabilities_name_three_advisories_then_count_the_rest(self) -> None:
        facts = replace(ESTABLISHED_MIT, advisories=("GHSA-1", "GHSA-2", "GHSA-3", "PYSEC-4", "PYSEC-5"))
        self.assertEqual(
            concerns(facts, NOW, "PyPI"),
            ["has known vulnerabilities in its latest version 2.1.0: GHSA-1, GHSA-2, GHSA-3 and 2 more"],
        )

    def test_a_malware_report_is_named_apart_from_the_vulnerabilities(self) -> None:
        facts = replace(ESTABLISHED_MIT, advisories=("GHSA-1", "MAL-2026-7"), malware_advisories=("MAL-2026-7",))
        self.assertEqual(
            concerns(facts, NOW, "npm"),
            [
                "has a malware report for its latest version 2.1.0: MAL-2026-7",
                "has known vulnerabilities in its latest version 2.1.0: GHSA-1",
            ],
        )

    def test_advisories_osv_could_not_report_raise_no_concern(self) -> None:
        self.assertEqual(concerns(replace(ESTABLISHED_MIT, advisories=None), NOW, "npm"), [])

    def test_the_license_is_not_judged_without_the_latest_version(self) -> None:
        unread = replace(ESTABLISHED_MIT, latest_version=None, license=None, advisories=None)
        self.assertEqual(concerns(unread, NOW, "npm"), [])

    def test_a_restricted_or_missing_license_is_a_concern(self) -> None:
        for declared, expected in (("SSPL-1.0", "not open source"), (None, "declares no license")):
            with self.subTest(license=declared):
                [reason] = concerns(replace(ESTABLISHED_MIT, license=declared), NOW, "npm")
                self.assertIn(expected, reason)

    def test_licenses_the_project_accepts_raise_no_concern(self) -> None:
        facts = replace(ESTABLISHED_MIT, license="AGPL-3.0-only")
        self.assertEqual(concerns(facts, NOW, "npm", ["agpl-*"]), [])


class NewPublicPackagesTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def names(self, *requests: PackageRequest, trusted: str = "") -> list[str]:
        with mock.patch.dict(os.environ, {"KONUNDRM_TRUSTED_PACKAGES": trusted}):
            return [request.name for request in new_public_packages(list(requests), self.root)]

    def test_skips_declared_packages_and_local_binaries(self) -> None:
        (self.root / "package.json").write_text(json.dumps({"devDependencies": {"vitest": "3"}}))
        (self.root / "node_modules" / ".bin").mkdir(parents=True)
        (self.root / "node_modules" / ".bin" / "tsc").write_text("")
        self.assertEqual(
            self.names(PackageRequest("npm", "vitest"), PackageRequest("npm", "tsc", runs_binary=True)), []
        )

    def test_skips_private_scopes_and_trusted_patterns(self) -> None:
        (self.root / ".npmrc").write_text("@acme:registry=https://npm.acme.dev\n")
        requests = (
            PackageRequest("npm", "@acme/ui"),
            PackageRequest("pypi", "konundrm-core"),
            PackageRequest("npm", "x"),
        )
        self.assertEqual(self.names(*requests, trusted="konundrm-*"), ["x"])


class ReviewRequestsTest(unittest.TestCase):
    def review(self, facts: dict[str, PackageFacts], ecosystem: str = "npm", **options: list[str]) -> list[Finding]:
        requests = [PackageRequest(ecosystem, name) for name in facts]
        return review_requests(requests, lambda _, name: facts[name], NOW, **options)

    def test_lists_only_the_packages_with_a_concern(self) -> None:
        findings = self.review({"good": ESTABLISHED_MIT, "ghost": PackageFacts(True, False)}, "pypi")
        self.assertEqual([finding.package for finding in findings], ["ghost"])
        self.assertIn("- ghost (PyPI) does not exist", findings[0].line)
        self.assertFalse(findings[0].is_malware)

    def test_a_malware_report_marks_the_finding_and_its_line_keeps_every_concern(self) -> None:
        evil = replace(
            ESTABLISHED_MIT,
            first_published=NOW - timedelta(days=2),
            advisories=("MAL-2026-7",),
            malware_advisories=("MAL-2026-7",),
        )
        [finding] = self.review({"evil-colors": evil})
        self.assertTrue(finding.is_malware)
        self.assertEqual(
            finding.line,
            "- evil-colors (npm) has a malware report for its latest version 2.1.0: MAL-2026-7; "
            "was first published 2 day(s) ago.",
        )

    def test_vulnerabilities_and_licenses_only_need_confirmation(self) -> None:
        findings = self.review(
            {
                "vulnerable": replace(ESTABLISHED_MIT, advisories=("GHSA-1",)),
                "copyleft": replace(ESTABLISHED_MIT, license="GPL-3.0-only"),
            }
        )
        self.assertEqual(
            [(finding.package, finding.is_malware) for finding in findings],
            [("vulnerable", False), ("copyleft", False)],
        )

    def test_accepted_licenses_reach_the_license_policy(self) -> None:
        facts = {"copyleft": replace(ESTABLISHED_MIT, license="GPL-3.0-only")}
        self.assertEqual(self.review(facts, accepted_licenses=["gpl-3.0*"]), [])


if __name__ == "__main__":
    unittest.main()
