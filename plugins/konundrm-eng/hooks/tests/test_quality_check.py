"""Unit tests for hooks/scripts/quality_check.py."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import quality_check
from hook_state import SessionState

PASSING = f'"{sys.executable}" -c "raise SystemExit(0)"'
FAILING = f'"{sys.executable}" -c "print(\'1 failed\'); raise SystemExit(1)"'


class FindCheckCommandTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_prefers_the_environment_override(self) -> None:
        (self.root / "package.json").write_text(json.dumps({"scripts": {"check": "x"}}))
        self.assertEqual(quality_check.find_check_command(self.root, {"KONUNDRM_CHECK_CMD": "just ci"}), "just ci")

    def test_uses_the_package_manager_of_the_lockfile(self) -> None:
        (self.root / "package.json").write_text(json.dumps({"scripts": {"check": "x"}}))
        self.assertEqual(quality_check.find_check_command(self.root, {}), "npm run check")
        (self.root / "pnpm-lock.yaml").write_text("")
        self.assertEqual(quality_check.find_check_command(self.root, {}), "pnpm run check")

    def test_finds_poe_check_task_and_runs_it_through_uv_when_locked(self) -> None:
        (self.root / "pyproject.toml").write_text('[tool.poe.tasks]\ncheck = ["lint", "test"]\n')
        self.assertEqual(quality_check.find_check_command(self.root, {}), "poe check")
        (self.root / "uv.lock").write_text("")
        self.assertEqual(quality_check.find_check_command(self.root, {}), "uv run poe check")

    def test_returns_none_when_project_exposes_no_check(self) -> None:
        (self.root / "package.json").write_text(json.dumps({"scripts": {"test": "vitest"}}))
        (self.root / "pyproject.toml").write_text("[tool.ruff]\nline-length = 100\n")
        self.assertIsNone(quality_check.find_check_command(self.root, {}))


class GatesDisabledTest(unittest.TestCase):
    def test_reads_the_escape_hatch_variable(self) -> None:
        for value, expected in (("off", True), ("OFF", True), ("0", True), ("on", False), ("", False)):
            with self.subTest(value=value), mock.patch.dict(os.environ, {"KONUNDRM_GATE": value}):
                self.assertEqual(quality_check.gates_disabled(), expected)


class IsCheckInvocationTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def invocation(self, command: str, check: str = "npm run check", cwd: Path | None = None) -> bool:
        return quality_check.is_check_invocation(command, check, self.root, cwd or self.root)

    def test_accepts_the_check_alone_or_after_cd_to_the_root(self) -> None:
        for command in (
            "npm run check",
            "  npm  run check ",
            "npm run check 2>&1",
            f'cd "{self.root}" && npm run check',
        ):
            with self.subTest(command=command):
                self.assertTrue(self.invocation(command))

    def test_treats_uv_run_poe_and_poe_as_the_same_check(self) -> None:
        self.assertTrue(self.invocation("poe check", check="uv run poe check"))
        self.assertTrue(self.invocation("uv run poe check", check="poe check"))

    def test_rejects_pipelines_other_commands_and_other_directories(self) -> None:
        for command in ("npm run check | tail -5", "npm run check || true", "npm run lint", "npm run check -- --watch"):
            with self.subTest(command=command):
                self.assertFalse(self.invocation(command))
        with tempfile.TemporaryDirectory() as other:
            self.assertFalse(self.invocation("npm run check", cwd=Path(other)))
            self.assertFalse(self.invocation(f'cd "{other}" && npm run check'))


class RunCheckTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        patcher = mock.patch.dict(os.environ, {"CLAUDE_PLUGIN_DATA": self._tmp.name})
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_records_a_pass_and_reuses_it_for_the_same_fingerprint(self) -> None:
        state = SessionState("s")
        first = quality_check.run_check(self.root, PASSING, state, "tree-1")
        second = quality_check.run_check(self.root, FAILING, SessionState("s"), "tree-1")
        self.assertEqual((first.passed, first.cached), (True, False))
        self.assertEqual((second.passed, second.cached), (True, True))

    def test_runs_again_when_the_fingerprint_changes(self) -> None:
        quality_check.run_check(self.root, PASSING, SessionState("s"), "tree-1")
        result = quality_check.run_check(self.root, FAILING, SessionState("s"), "tree-2")
        self.assertFalse(result.passed)
        self.assertIn("1 failed", result.output_tail)

    def test_never_reuses_a_result_without_a_fingerprint(self) -> None:
        quality_check.run_check(self.root, PASSING, SessionState("s"), None)
        self.assertFalse(quality_check.run_check(self.root, FAILING, SessionState("s"), None).passed)


if __name__ == "__main__":
    unittest.main()
