"""Integration test: the dependency guard hook against a local fake npm/PyPI registry and OSV server."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import metrics_log  # noqa: E402 - needs the scripts folder on sys.path first

OLD_RELEASES = {"1.0": [{"upload_time_iso_8601": "2019-05-01T00:00:00Z"}]}
PAGES = {
    "/downloads/point/last-week/react": {"downloads": 50_000_000},
    "/react/latest": {"name": "react", "version": "19.2.0", "license": "MIT"},
    "/downloads/point/last-week/evil-colors": {"downloads": 40_000},
    "/evil-colors/latest": {"name": "evil-colors", "version": "4.1.0", "license": "MIT"},
    "/downloads/point/last-week/vulnerable-parser": {"downloads": 40_000},
    "/vulnerable-parser/latest": {"name": "vulnerable-parser", "version": "2.0.1", "license": "BSD-3-Clause"},
    "/pypi/requests/json": {
        "info": {"version": "2.32.5", "license_expression": "Apache-2.0", "license": None},
        "releases": {"0.2": [{"upload_time_iso_8601": "2011-02-14T00:00:00Z"}]},
    },
    "/api/packages/requests/recent": {"data": {"last_week": 1_000_000}},
    "/pypi/copyleft-lib/json": {
        "info": {
            "version": "3.0",
            "license": "",
            "classifiers": ["License :: OSI Approved :: GNU Affero General Public License v3"],
        },
        "releases": OLD_RELEASES,
    },
    "/api/packages/copyleft-lib/recent": {"data": {"last_week": 50_000}},
}
# What the fake OSV answers to POST /v1/query, by (ecosystem, name, version).
ADVISORIES = {
    ("npm", "evil-colors", "4.1.0"): [{"id": "MAL-2026-0042", "summary": "Malicious code in evil-colors (npm)"}],
    ("npm", "vulnerable-parser", "2.0.1"): [{"id": "GHSA-1234-5678-9abc", "summary": "ReDoS in vulnerable-parser"}],
}


class FakeRegistryHandler(BaseHTTPRequestHandler):
    """Serves PAGES to GET requests and ADVISORIES to OSV queries."""

    def do_GET(self) -> None:
        self.answer(PAGES.get(self.path))

    def do_POST(self) -> None:
        query = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        package = query.get("package") or {}
        vulns = ADVISORIES.get((package.get("ecosystem"), package.get("name"), query.get("version")))
        self.answer(({"vulns": vulns} if vulns else {}) if self.path == "/v1/query" else None)

    def answer(self, body: object) -> None:
        self.send_response(200 if body is not None else 404)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(body if body is not None else {"error": "not found"}).encode())

    def log_message(self, *args: object) -> None:
        pass


def closed_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


class DependencyGuardFlowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeRegistryHandler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.registry = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self) -> None:
        self._project = tempfile.TemporaryDirectory()
        self._data = tempfile.TemporaryDirectory()
        self.addCleanup(self._project.cleanup)
        self.addCleanup(self._data.cleanup)
        self.root = Path(self._project.name)
        self.env = {
            **os.environ,
            "CLAUDE_PROJECT_DIR": str(self.root),
            "CLAUDE_PLUGIN_DATA": self._data.name,
            "KONUNDRM_NPM_REGISTRY": self.registry,
            "KONUNDRM_NPM_DOWNLOADS_API": self.registry,
            "KONUNDRM_PYPI_URL": self.registry,
            "KONUNDRM_PYPISTATS_URL": self.registry,
            "KONUNDRM_OSV_URL": self.registry,
        }
        for variable in ("KONUNDRM_DEPENDENCY_GUARD", "KONUNDRM_TRUSTED_PACKAGES", "KONUNDRM_ACCEPTED_LICENSES"):
            self.env.pop(variable, None)

    def guard(self, command: str, **env: str) -> dict | None:
        event = {"session_id": "s", "cwd": str(self.root), "tool_name": "Bash", "tool_input": {"command": command}}
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "guard_new_dependencies.py")],
            input=json.dumps(event),
            capture_output=True,
            text=True,
            encoding="utf-8",
            env={**self.env, **env},
            timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)["hookSpecificOutput"] if result.stdout.strip() else None

    def logged_kinds(self) -> list[str]:
        with mock.patch.dict(os.environ, {"CLAUDE_PLUGIN_DATA": self._data.name}):
            return [event["kind"] for event in metrics_log.read_events(self.root)]

    def test_established_packages_install_without_a_prompt(self) -> None:
        self.assertIsNone(self.guard("npm install react && uv add requests"))

    def test_a_package_that_does_not_exist_asks_the_person_and_is_logged(self) -> None:
        decision = self.guard("npm install react-codeshift-pro")
        self.assertEqual(decision["permissionDecision"] if decision else None, "ask")
        self.assertIn(
            "react-codeshift-pro (npm) does not exist", decision["permissionDecisionReason"] if decision else ""
        )
        self.assertEqual(self.logged_kinds(), ["dependency_flagged"])

    def test_a_package_whose_latest_version_is_malware_is_denied_and_logged(self) -> None:
        decision = self.guard("npm install react evil-colors react-codeshift-pro")
        self.assertEqual(decision["permissionDecision"] if decision else None, "deny")
        reason = decision["permissionDecisionReason"] if decision else ""
        self.assertIn("evil-colors (npm) has a malware report for its latest version 4.1.0: MAL-2026-0042", reason)
        self.assertIn("react-codeshift-pro (npm) does not exist", reason)  # one denial lists every finding
        self.assertIn("by hand, pinned", reason)
        self.assertEqual(self.logged_kinds(), ["dependency_denied"])

    def test_known_vulnerabilities_and_copyleft_licenses_ask_the_person(self) -> None:
        decision = self.guard("npm install vulnerable-parser && pip install copyleft-lib")
        self.assertEqual(decision["permissionDecision"] if decision else None, "ask")
        reason = decision["permissionDecisionReason"] if decision else ""
        self.assertIn("vulnerable-parser (npm) has known vulnerabilities in its latest version 2.0.1", reason)
        self.assertIn('copyleft-lib (PyPI) is licensed under "GNU Affero General Public License v3"', reason)
        self.assertEqual(self.logged_kinds(), ["dependency_flagged"])

    def test_licenses_the_project_accepts_install_without_a_prompt(self) -> None:
        self.assertIsNone(self.guard("pip install copyleft-lib", KONUNDRM_ACCEPTED_LICENSES="MIT, GNU Affero*"))

    def test_a_package_the_project_already_declares_is_not_checked(self) -> None:
        (self.root / "package.json").write_text(json.dumps({"dependencies": {"internal-only": "1"}}))
        self.assertIsNone(self.guard("npm install internal-only"))

    def test_an_unreachable_registry_asks_instead_of_guessing(self) -> None:
        offline = f"http://127.0.0.1:{closed_port()}"
        decision = self.guard("pip install some-new-lib", KONUNDRM_PYPI_URL=offline)
        self.assertEqual(decision["permissionDecision"] if decision else None, "ask")

    def test_an_unreachable_osv_does_not_hold_up_an_established_package(self) -> None:
        offline = f"http://127.0.0.1:{closed_port()}"
        self.assertIsNone(self.guard("npm install react", KONUNDRM_OSV_URL=offline))

    def test_the_guard_can_be_switched_off(self) -> None:
        self.assertIsNone(self.guard("npm install ghost-package", KONUNDRM_DEPENDENCY_GUARD="off"))


if __name__ == "__main__":
    unittest.main()
