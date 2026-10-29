"""Unit tests for hooks/scripts/metrics_log.py."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import metrics_log


class MetricsLogTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        patcher = mock.patch.dict(os.environ, {"CLAUDE_PLUGIN_DATA": self._tmp.name})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_reads_back_events_in_order_with_their_details(self) -> None:
        root = Path(self._tmp.name) / "project"
        metrics_log.record_event(root, "stop_blocked", "s1", attempt=1)
        metrics_log.record_event(root, "commit_denied", "s1", reason="bypass")
        events = metrics_log.read_events(root)
        self.assertEqual([event["kind"] for event in events], ["stop_blocked", "commit_denied"])
        self.assertEqual((events[0]["attempt"], events[1]["reason"], events[0]["session"]), (1, "bypass", "s1"))

    def test_keeps_one_log_per_project(self) -> None:
        metrics_log.record_event(Path(self._tmp.name) / "a", "stop_blocked")
        self.assertEqual(metrics_log.read_events(Path(self._tmp.name) / "b"), [])

    def test_skips_corrupt_lines_and_never_raises(self) -> None:
        root = Path(self._tmp.name) / "project"
        metrics_log.record_event(root, "stop_blocked")
        with metrics_log._log_path(root).open("a", encoding="utf-8") as log:
            log.write("{not json\n")
        metrics_log.record_event(root, "role_violation", paths={"not", "serialisable"})  # type: ignore[arg-type]  # deliberately not JSON
        self.assertEqual([event["kind"] for event in metrics_log.read_events(root)], ["stop_blocked"])


if __name__ == "__main__":
    unittest.main()
