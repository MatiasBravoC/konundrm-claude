"""Unit tests for hooks/scripts/quality_gate.py."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from hook_state import SessionState
from quality_gate import is_deliberate_red_stop, turn_changed_code


class IsDeliberateRedStopTest(unittest.TestCase):
    def test_accepts_handoff_and_escalation_lines(self) -> None:
        for message in (
            "RED: rejects short passwords\nTest: tests/test_pw.py::test_short",
            "Summary first.\n**BLOCKED:** the design needs a decision",
            "**BLOCKED**: plan is wrong",
            "> RED: quoted handoff",
            "- BLOCKED: waiting on credentials",
        ):
            with self.subTest(message=message):
                self.assertTrue(is_deliberate_red_stop(message))

    def test_rejects_messages_without_a_marker_line(self) -> None:
        for message in ("All done.", "The test went RED: then green.", "Redirect: /home", "", "blocked: lowercase"):
            with self.subTest(message=message):
                self.assertFalse(is_deliberate_red_stop(message))


class TurnChangedCodeTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        patcher = mock.patch.dict(os.environ, {"CLAUDE_PLUGIN_DATA": self._tmp.name})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self._tmp.cleanup)
        self.state = SessionState("s")
        self.root = Path(self._tmp.name)

    def changes(self, *pairs: tuple[str, str]) -> Any:
        return mock.patch("quality_gate.changed_paths", return_value=list(pairs))

    def test_falls_back_to_the_dirty_flag_without_snapshots(self) -> None:
        self.state.dirty = True
        self.assertTrue(turn_changed_code(self.state, self.root, None))
        self.state.dirty = False
        self.assertFalse(turn_changed_code(self.state, self.root, "tree"))

    def test_counts_code_changes_whatever_tool_made_them(self) -> None:
        self.state.turn_start_tree = "before"
        with self.changes(("M", "src/a.py")):
            self.assertTrue(turn_changed_code(self.state, self.root, "after"))

    def test_ignores_documentation_and_tool_artifacts(self) -> None:
        self.state.turn_start_tree = "before"
        with self.changes(("M", "README.md"), ("A", ".coverage"), ("A", "src/__pycache__/a.pyc")):
            self.assertFalse(turn_changed_code(self.state, self.root, "after"))


if __name__ == "__main__":
    unittest.main()
