"""Unit tests for hooks/scripts/hook_io.py."""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import hook_io


def read_from(raw: bytes) -> dict:
    with mock.patch.object(sys, "stdin", io.TextIOWrapper(io.BytesIO(raw), encoding="utf-8")):
        return hook_io.read_hook_input()


def emitted(function: object, *args: str) -> dict:
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        function(*args)  # type: ignore[operator]  # typed as object so any emitter fits
    return json.loads(buffer.getvalue())


class ReadHookInputTest(unittest.TestCase):
    def test_decodes_a_json_object(self) -> None:
        self.assertEqual(read_from(b'{"session_id": "s1"}'), {"session_id": "s1"})

    def test_coerces_the_fields_hooks_read_so_odd_types_cannot_crash_them(self) -> None:
        event = read_from(
            json.dumps(
                {"session_id": 123, "agent_id": {"x": 1}, "cwd": 12, "tool_input": {"command": 5, "file_path": 7}}
            ).encode()
        )
        self.assertEqual((event["session_id"], event["agent_id"]), ("123", '{"x": 1}'))
        self.assertNotIn("cwd", event)
        self.assertEqual(event["tool_input"], {"command": "5", "file_path": "7"})
        self.assertEqual(read_from(b'{"tool_input": "git commit -n"}')["tool_input"], {})

    def test_returns_an_empty_event_for_anything_else(self) -> None:
        for raw in (b"", b"   ", b"not json", b"[1, 2]", b'"text"', b"\xff\xfe\x00"):
            with self.subTest(raw=raw):
                self.assertEqual(read_from(raw), {})


class DecisionOutputTest(unittest.TestCase):
    def test_deny_and_ask_use_the_pre_tool_use_contract(self) -> None:
        for function, decision in ((hook_io.deny_tool_use, "deny"), (hook_io.ask_before_tool_use, "ask")):
            with self.subTest(decision=decision):
                output = emitted(function, "because")["hookSpecificOutput"]
                self.assertEqual(
                    (output["hookEventName"], output["permissionDecision"], output["permissionDecisionReason"]),
                    ("PreToolUse", decision, "because"),
                )

    def test_block_stop_and_warn_user_use_top_level_fields(self) -> None:
        self.assertEqual(emitted(hook_io.block_stop, "keep going"), {"decision": "block", "reason": "keep going"})
        self.assertEqual(emitted(hook_io.warn_user, "heads up"), {"systemMessage": "heads up"})


class PluginDataDirectoryTest(unittest.TestCase):
    def test_prefers_the_directory_claude_code_assigns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"CLAUDE_PLUGIN_DATA": tmp}):
            self.assertEqual(hook_io.plugin_data_directory(), Path(tmp))

    def test_falls_back_to_a_temporary_folder_named_after_the_plugin(self) -> None:
        with mock.patch.dict(os.environ, {"CLAUDE_PLUGIN_DATA": ""}):
            self.assertEqual(hook_io.plugin_data_directory().name, hook_io.PLUGIN_NAME)


if __name__ == "__main__":
    unittest.main()
