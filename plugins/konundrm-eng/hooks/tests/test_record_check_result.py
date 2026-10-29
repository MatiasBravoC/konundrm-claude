"""Unit tests for hooks/scripts/record_check_result.py."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from record_check_result import succeeded


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


if __name__ == "__main__":
    unittest.main()
