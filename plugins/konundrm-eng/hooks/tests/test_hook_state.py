"""Unit tests for hooks/scripts/hook_state.py."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from hook_state import SessionState, SubagentRecord


class HookStateTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        patcher = mock.patch.dict(os.environ, {"CLAUDE_PLUGIN_DATA": self._tmp.name})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self._tmp.cleanup)


class SessionStateTest(HookStateTestCase):
    def test_persists_flags_between_instances(self) -> None:
        state = SessionState("abc/123")
        state.dirty, state.stop_blocks, state.turn_start_tree = True, 2, "tree"
        state.save()
        reloaded = SessionState("abc/123")
        self.assertEqual((reloaded.dirty, reloaded.stop_blocks, reloaded.turn_start_tree), (True, 2, "tree"))

    def test_mark_green_clears_dirty_flag_and_block_counter(self) -> None:
        state = SessionState("s1")
        state.dirty, state.stop_blocks = True, 3
        state.mark_green("fp")
        self.assertEqual((state.dirty, state.stop_blocks, state.green_fingerprint), (False, 0, "fp"))

    def test_start_turn_records_the_tree_and_resets_turn_flags(self) -> None:
        state = SessionState("s1")
        state.dirty, state.stop_blocks, state.green_fingerprint = True, 2, "fp"
        state.start_turn("tree-0")
        self.assertEqual((state.turn_start_tree, state.dirty, state.stop_blocks), ("tree-0", False, 0))
        self.assertEqual(state.green_fingerprint, "fp")

    def test_a_corrupt_record_loads_as_defaults(self) -> None:
        state = SessionState("s1")
        state.save()
        state._path.write_text("{not json", encoding="utf-8")
        reloaded = SessionState("s1")
        self.assertEqual((reloaded.dirty, reloaded.stop_blocks, reloaded.green_fingerprint), (False, 0, None))


class SubagentRecordTest(HookStateTestCase):
    def test_persists_until_deleted(self) -> None:
        record = SubagentRecord("s1", "agent-7")
        record.role, record.before_tree, record.blocks = "implementer", "tree", 1
        record.save()
        reloaded = SubagentRecord("s1", "agent-7")
        self.assertEqual((reloaded.role, reloaded.before_tree, reloaded.blocks), ("implementer", "tree", 1))
        reloaded.delete()
        self.assertIsNone(SubagentRecord("s1", "agent-7").role)

    def test_records_are_separate_per_agent(self) -> None:
        first = SubagentRecord("s1", "a")
        first.role = "test-writer"
        first.save()
        self.assertIsNone(SubagentRecord("s1", "b").role)


if __name__ == "__main__":
    unittest.main()
