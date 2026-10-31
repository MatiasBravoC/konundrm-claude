"""Unit tests for hooks/scripts/record_check_result.py."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import quality_check
import record_check_result
from hook_state import SessionState
from record_check_result import succeeded
from working_tree import snapshot_tree

CHECK = f'"{sys.executable}" -c "raise SystemExit(0)"'
FAILING_CHECK = f'"{sys.executable}" -c "raise SystemExit(1)"'


def event(**overrides: object) -> dict:
    base: dict = {
        "hook_event_name": "PostToolUse",
        "tool_input": {"command": "npm run check"},
        "tool_response": {"stdout": "ok", "stderr": "", "interrupted": False},
    }
    return {**base, **overrides}


class SucceededTest(unittest.TestCase):
    def test_accepts_a_completed_command(self) -> None:
        self.assertTrue(succeeded(event()))
        self.assertTrue(succeeded(event(tool_response="plain text output")))

    def test_rejects_failures_interruptions_and_background_runs(self) -> None:
        for case in (
            event(hook_event_name="PostToolUseFailure"),
            event(tool_response={"interrupted": True}),
            event(tool_response={"exit_code": 1}),
            event(tool_response={"returnCode": 2}),
            event(tool_response={"backgroundTaskId": "b1"}),
            event(tool_input={"command": "npm run check", "run_in_background": True}),
        ):
            with self.subTest(case=case):
                self.assertFalse(succeeded(case))


def git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout


@unittest.skipIf(shutil.which("git") is None, "Git is not installed")
class GreenTreeBesideTheRepositoryTest(unittest.TestCase):
    def setUp(self) -> None:
        plugin_data = tempfile.TemporaryDirectory()
        repository = tempfile.TemporaryDirectory()
        self.addCleanup(plugin_data.cleanup)
        self.addCleanup(repository.cleanup)
        self.root = Path(repository.name).resolve()
        git(self.root, "init", "-q")
        (self.root / "a.txt").write_text("one\n")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "init")
        environment = {
            "CLAUDE_PLUGIN_DATA": plugin_data.name,
            "CLAUDE_PROJECT_DIR": str(self.root),
            "KONUNDRM_CHECK_CMD": CHECK,
        }
        patcher = mock.patch.dict(os.environ, environment)
        patcher.start()
        self.addCleanup(patcher.stop)

    def record(self, tool_response: dict) -> None:
        check_event = event(
            session_id="s", cwd=str(self.root), tool_input={"command": CHECK}, tool_response=tool_response
        )
        with mock.patch("record_check_result.read_hook_input", return_value=check_event):
            record_check_result.main()

    def green_tree_from_a_plain_shell(self) -> str | None:
        with mock.patch.dict(os.environ):
            del os.environ["CLAUDE_PLUGIN_DATA"]
            return quality_check.green_tree(self.root)

    def test_a_passing_check_remembers_its_tree_beside_the_repository(self) -> None:
        # R4.1: a shell without CLAUDE_PLUGIN_DATA can tell whether the current tree passed the check.
        quality_check.run_check(self.root, FAILING_CHECK, SessionState("s"), snapshot_tree(self.root))
        self.record({"stdout": "1 failed", "stderr": "", "interrupted": False, "exit_code": 1})
        self.assertIsNone(self.green_tree_from_a_plain_shell())

        self.record({"stdout": "ok", "stderr": "", "interrupted": False})
        self.assertEqual(self.green_tree_from_a_plain_shell(), snapshot_tree(self.root))
        green_file = self.root / git(self.root, "rev-parse", "--git-path", "konundrm-eng-green").strip()
        self.assertIn(str(snapshot_tree(self.root)), green_file.read_text(encoding="utf-8"))

        (self.root / "a.txt").write_text("two\n")
        fingerprint = snapshot_tree(self.root)
        quality_check.run_check(self.root, CHECK, SessionState("other"), fingerprint)
        self.assertEqual(self.green_tree_from_a_plain_shell(), fingerprint)


if __name__ == "__main__":
    unittest.main()
