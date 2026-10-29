"""Claude Code hook protocol: reads the event from stdin and writes the hook's decision.

Sections:
    PLUGIN_NAME              — the plugin's name, which scopes its agents and its data.
    plugin_data_directory()  — where the hooks keep state, caches and metrics.
    read_hook_input()        — parses the JSON event Claude Code sends on stdin.
    emit_json()              — prints a structured hook output on stdout.
    deny_tool_use()          — PreToolUse decision that blocks a tool call.
    ask_before_tool_use()    — PreToolUse decision that asks the person to confirm a tool call.
    block_stop()             — Stop/SubagentStop decision that keeps the agent working.
    warn_user()              — message shown to the person, not to Claude.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

PLUGIN_NAME = "konundrm-eng"
TEXT_FIELDS = ("session_id", "agent_id", "agent_type", "hook_event_name", "last_assistant_message")
TOOL_INPUT_TEXT_FIELDS = ("command", "file_path", "notebook_path")


def plugin_data_directory() -> Path:
    """Returns the plugin's persistent data directory (CLAUDE_PLUGIN_DATA, else a temp folder)."""
    return Path(os.environ.get("CLAUDE_PLUGIN_DATA") or os.path.join(tempfile.gettempdir(), PLUGIN_NAME))


# Windows consoles default to a legacy code page; Claude Code reads hook output as UTF-8.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")


def _normalized(event: dict[str, Any]) -> dict[str, Any]:
    """Gives every field the hooks read the type they expect, so an odd event cannot crash a hook."""
    for key in TEXT_FIELDS:
        value = event.get(key)
        if value is not None and not isinstance(value, str):
            event[key] = json.dumps(value) if isinstance(value, (dict, list)) else str(value)
    if not isinstance(event.get("cwd"), str):
        event.pop("cwd", None)  # a made-up working directory is worse than the hook's own
    tool_input = event.get("tool_input")
    if "tool_input" in event and not isinstance(tool_input, dict):
        event["tool_input"] = {}
    elif isinstance(tool_input, dict):
        for key in TOOL_INPUT_TEXT_FIELDS:
            if key in tool_input and not isinstance(tool_input[key], str):
                tool_input[key] = str(tool_input[key])
    return event


def read_hook_input() -> dict[str, Any]:
    """Reads the hook event from stdin.

    Returns:
        The decoded event with the fields the hooks read coerced to text (and ``tool_input`` to a
        dict), or an empty dict when stdin is empty or not a JSON object.
    """
    try:
        raw = sys.stdin.buffer.read().decode("utf-8", errors="replace")
        event = json.loads(raw) if raw.strip() else {}
    except (OSError, ValueError):
        return {}
    return _normalized(event) if isinstance(event, dict) else {}


def emit_json(payload: dict[str, Any]) -> None:
    """Prints a hook's structured output on stdout."""
    sys.stdout.write(json.dumps(payload, ensure_ascii=False))
    sys.stdout.flush()


def deny_tool_use(reason: str) -> None:
    """Emits a PreToolUse decision that blocks the tool call and tells Claude why."""
    emit_json(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        }
    )


def ask_before_tool_use(reason: str) -> None:
    """Emits a PreToolUse decision that pauses the tool call until the person confirms it."""
    emit_json(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "ask",
                "permissionDecisionReason": reason,
            }
        }
    )


def block_stop(reason: str) -> None:
    """Emits a Stop or SubagentStop decision that keeps the agent working on ``reason``."""
    emit_json({"decision": "block", "reason": reason})


def warn_user(message: str) -> None:
    """Emits a warning shown to the person in the Claude Code interface."""
    emit_json({"systemMessage": message})
