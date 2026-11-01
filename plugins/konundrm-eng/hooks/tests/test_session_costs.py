"""Tests for hooks/scripts/session_costs.py, run as the CLI over synthetic session transcripts."""

from __future__ import annotations

import json
import os
import random
import re
import shutil
import string
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[2]
SESSION_COSTS = PLUGIN / "hooks" / "scripts" / "session_costs.py"
START = datetime(2026, 11, 1, 16, 0, 0, tzinfo=timezone.utc)
SESSION_ID = "sess-1"
SECOND_SESSION_ID = "sess-2"
TEST_WRITER = "konundrm-eng:test-writer"
IMPLEMENTER = "konundrm-eng:implementer"
ORCHESTRATOR = "orchestrator"
# Role of a subagent whose meta.json is missing or names no usable agentType (T37, decision 2 A).
UNKNOWN_ROLE = "unknown"
# The table's header names its columns; rows start with the role. Values are read by column name,
# so later tasks may add columns or blocks without breaking this test.
COLUMNS = {
    "dispatches": "dispatches",
    "turns": "turns",
    "input": "input",
    "cache_write": "cache_write",
    "cache_read": "cache_read",
    "output": "output",
    "weighted": "weighted",
    "share": "share",
    "median_minutes": "active_min_median",
    "total_minutes": "active_min_total",
    "check_runs": "check_runs",
    "check_minutes": "check_min_total",
    "test_runs": "test_runs",
    "parallel_messages": "parallel_dispatch_msgs",
}


def stamp(minutes: float) -> str:
    """Returns the ISO timestamp `minutes` after START, written as Claude Code writes it."""
    moment = START + timedelta(minutes=minutes)
    return moment.strftime("%Y-%m-%dT%H:%M:%S.") + f"{moment.microsecond // 1000:03d}Z"


def user_line(minutes: float, sidechain: bool, *, session_id: str = SESSION_ID) -> dict:
    """Returns one user line of a transcript."""
    return {
        "type": "user",
        "timestamp": stamp(minutes),
        "sessionId": session_id,
        "isSidechain": sidechain,
        "message": {"role": "user", "content": "go"},
    }


def assistant_lines(
    minutes: float,
    message_id: str,
    usage: tuple[int, int, int, int],
    blocks: int,
    sidechain: bool,
    *,
    session_id: str = SESSION_ID,
) -> list[dict]:
    """Returns one API message written, as Claude Code does, as one line per content block.

    Every line repeats the message's id, so the message is one turn whose tokens count once. The
    input and cache fields are the same on every line, but `output_tokens` is not: as in real
    transcripts, earlier lines carry a partial count that never shrinks (1, then half the final
    count) and only the last line carries the final count `usage` gives.
    """
    input_tokens, cache_write, cache_read, final_output_tokens = usage
    block_kinds = ["thinking", "text", "tool_use"]

    def output_tokens_on_line(index: int) -> int:
        if index == blocks - 1:
            return final_output_tokens
        if index == 0:
            return min(1, final_output_tokens)
        return max(1, final_output_tokens // 2)

    return [
        {
            "type": "assistant",
            "timestamp": stamp(minutes),
            "sessionId": session_id,
            "isSidechain": sidechain,
            "message": {
                "id": message_id,
                "model": "claude-opus-5-5",
                "role": "assistant",
                "content": [{"type": block_kinds[index % len(block_kinds)], "text": "x"}],
                "usage": {
                    "input_tokens": input_tokens,
                    "cache_creation_input_tokens": cache_write,
                    "cache_read_input_tokens": cache_read,
                    "output_tokens": output_tokens_on_line(index),
                    "cache_creation": {"ephemeral_5m_input_tokens": cache_write, "ephemeral_1h_input_tokens": 0},
                    "server_tool_use": {"web_search_requests": 0},
                },
            },
        }
        for index in range(blocks)
    ]


def write_jsonl(path: Path, lines: list[dict]) -> None:
    """Writes one JSON object per line."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(line) + "\n" for line in lines), encoding="utf-8", newline="\n")


def write_subagent(subagents: Path, agent_id: str, agent_type: str, lines: list[dict]) -> None:
    """Writes a subagent transcript with its meta.json and a prefix.json that is not a transcript.

    The prefix.json holds a line shaped like a costly assistant message, so reading it as a
    transcript would show up in every count.
    """
    write_jsonl(subagents / f"agent-{agent_id}.jsonl", lines)
    meta = {
        "agentType": agent_type,
        "description": f"{agent_id} red: write the test",
        "toolUseId": f"toolu_{agent_id}",
        "spawnDepth": 1,
        "finished": True,
    }
    (subagents / f"agent-{agent_id}.meta.json").write_text(json.dumps(meta), encoding="utf-8")
    decoy = assistant_lines(0, f"msg-prefix-{agent_id}", (90000, 90000, 90000, 90000), 1, True)
    write_jsonl(subagents / f"agent-{agent_id}.prefix.json", decoy)


def build_transcripts(folder: Path, second_folder: Path) -> None:
    """Writes two orchestrator sessions, one per folder, and four subagent dispatches of two roles."""
    # Orchestrator: two turns. Message A is written on three lines. Active time: 1 min, then a 30-min
    # pause that does not count, then exactly 5 min that do: 6 min (capping the pause gives 11, keeping
    # it gives 36).
    write_jsonl(
        folder / f"{SESSION_ID}.jsonl",
        [
            user_line(0, False),
            *assistant_lines(1, "msg-orch-a", (100, 400, 1000, 20), 3, False),
            user_line(31, False),
            *assistant_lines(36, "msg-orch-b", (100, 0, 2000, 40), 2, False),
        ],
    )
    subagents = folder / SESSION_ID / "subagents"
    # Test-writer: three dispatches active 1, 2 and 9 min (median 2, mean 4, total 12); four turns of
    # 50 input + 10 output tokens each (100 weighted).
    turn = (50, 0, 0, 10)
    write_subagent(subagents, "a1", TEST_WRITER, [user_line(100, True), *assistant_lines(101, "msg-a1", turn, 2, True)])
    write_subagent(subagents, "a2", TEST_WRITER, [user_line(200, True), *assistant_lines(202, "msg-a2", turn, 1, True)])
    write_subagent(
        subagents,
        "a3",
        TEST_WRITER,
        [
            user_line(300, True),
            *assistant_lines(304, "msg-a3-1", turn, 2, True),
            user_line(308, True),
            *assistant_lines(309, "msg-a3-2", turn, 3, True),
        ],
    )
    # Second folder: an orchestrator session of a single user line (0 turns, 0 tokens, 0 active
    # minutes) and the implementer's only dispatch, active 3 min, one turn written on two lines. The
    # implementer's row exists only if the second folder is read.
    write_jsonl(second_folder / f"{SECOND_SESSION_ID}.jsonl", [user_line(390, False, session_id=SECOND_SESSION_ID)])
    write_subagent(
        second_folder / SECOND_SESSION_ID / "subagents",
        "b1",
        IMPLEMENTER,
        [
            user_line(400, True, session_id=SECOND_SESSION_ID),
            *assistant_lines(403, "msg-b1", (100, 80, 0, 20), 2, True, session_id=SECOND_SESSION_ID),
        ],
    )


def tool_use_line(minutes: float, message_id: str, tool: tuple[str, str, dict], sidechain: bool) -> dict:
    """Returns one assistant line holding a single tool_use block, as Claude Code writes it.

    Args:
        minutes: Minutes after START.
        message_id: The API message's id; a message with several blocks repeats it on each line.
        tool: ``(tool_use_id, tool name, tool input)``.
        sidechain: Whether the line belongs to a subagent transcript.
    """
    tool_use_id, name, tool_input = tool
    return {
        "type": "assistant",
        "timestamp": stamp(minutes),
        "sessionId": SESSION_ID,
        "isSidechain": sidechain,
        "message": {
            "id": message_id,
            "model": "claude-opus-5-5",
            "role": "assistant",
            "content": [{"type": "tool_use", "id": tool_use_id, "name": name, "input": tool_input}],
            "usage": {
                "input_tokens": 1,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 0,
                "output_tokens": 1,
            },
        },
    }


def tool_result_line(minutes: float, tool_use_id: str, sidechain: bool) -> dict:
    """Returns the user line that carries a tool's result back to the model."""
    return {
        "type": "user",
        "timestamp": stamp(minutes),
        "sessionId": SESSION_ID,
        "isSidechain": sidechain,
        "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": tool_use_id, "content": "ok"}]},
    }


def shell(tool_use_id: str, command: str, name: str = "Bash") -> tuple[str, str, dict]:
    """Returns a Bash (or PowerShell) tool call running `command`."""
    return tool_use_id, name, {"command": command, "description": "run it"}


def dispatch(tool_use_id: str) -> tuple[str, str, dict]:
    """Returns an Agent tool call, the one that dispatches a subagent."""
    return tool_use_id, "Agent", {"subagent_type": TEST_WRITER, "description": "red", "prompt": "write the test"}


def build_tool_transcripts(folder: Path) -> None:
    """Writes an orchestrator session and two subagents that run checks, tests and dispatches."""
    write_jsonl(
        folder / f"{SESSION_ID}.jsonl",
        [
            user_line(0, False),
            # One message with two Agent blocks, on two lines: one parallel-dispatch message.
            tool_use_line(1, "msg-o1", dispatch("toolu_o1a"), False),
            tool_use_line(1, "msg-o1", dispatch("toolu_o1b"), False),
            tool_result_line(1.5, "toolu_o1a", False),
            tool_result_line(1.5, "toolu_o1b", False),
            # A message with a single Agent block is not parallel.
            tool_use_line(2, "msg-o2", dispatch("toolu_o2"), False),
            tool_result_line(2.5, "toolu_o2", False),
            # The check (in a pipeline after a cd) and a grep for its text, run in parallel. The grep's
            # result arrives first; the check's arrives 1.5 min after it started.
            tool_use_line(3, "msg-o3", shell("toolu_o3", "cd /repo && npm run check 2>&1 | tail -5"), False),
            tool_use_line(3.25, "msg-o3", shell("toolu_o3g", 'grep -n "npm run check" notes.md'), False),
            tool_result_line(3.5, "toolu_o3g", False),
            tool_result_line(4.5, "toolu_o3", False),
            tool_use_line(5, "msg-o5", shell("toolu_o5", 'echo "remember: npm run check"'), False),
            tool_result_line(5.25, "toolu_o5", False),
            # A custom check, counted only when --check-pattern names it: 2 min.
            tool_use_line(6, "msg-o6", shell("toolu_o6", "cd /repo; make verify", "PowerShell"), False),
            tool_result_line(8, "toolu_o6", False),
            # Two test runs.
            tool_use_line(9, "msg-o7", shell("toolu_o7", "python -m unittest discover -s tests -k name"), False),
            tool_result_line(9.5, "toolu_o7", False),
            tool_use_line(10, "msg-o8", shell("toolu_o8", "npm test"), False),
            tool_result_line(10.5, "toolu_o8", False),
        ],
    )
    subagents = folder / SESSION_ID / "subagents"
    # Implementer: the check, 3 min, and two test runs.
    write_subagent(
        subagents,
        "c1",
        IMPLEMENTER,
        [
            user_line(100, True),
            tool_use_line(100, "msg-c1-1", shell("toolu_c1a", "npm run check"), True),
            tool_result_line(103, "toolu_c1a", True),
            tool_use_line(104, "msg-c1-2", shell("toolu_c1b", "pytest plugins/x -k foo"), True),
            tool_result_line(104.5, "toolu_c1b", True),
            tool_use_line(105, "msg-c1-3", shell("toolu_c1c", "python -m pytest -q"), True),
            tool_result_line(105.5, "toolu_c1c", True),
        ],
    )
    # Test-writer: one test run, nothing else.
    write_subagent(
        subagents,
        "c2",
        TEST_WRITER,
        [
            user_line(200, True),
            tool_use_line(200, "msg-c2-1", shell("toolu_c2a", "python -m unittest discover -s t -k one"), True),
            tool_result_line(200.5, "toolu_c2a", True),
        ],
    )


# Context (input + cache-write + cache-read tokens) of each turn of the busiest orchestrator, in the
# order its turns are written. Sorted: 100 200 300 400 500 700 800 900 1000 5000. First 500 (the
# smallest is 100); median 600 (mean 990); p90 by nearest rank, rank ceil(0.9 * 10) = 9, is 1000
# (linear interpolation gives 1400, the exclusive method 4600, the max is 5000).
BUSIEST_CONTEXTS = (500, 100, 900, 300, 1000, 200, 700, 400, 800, 5000)
# Lines each of those turns is written on: one counted per line would add two 500s and one 5000.
BUSIEST_BLOCKS = (3, 1, 1, 1, 1, 1, 1, 1, 1, 2)
# Output tokens of every turn: large enough that adding them to the context changes every value.
TURN_OUTPUT_TOKENS = 77


def context_usage(context: int) -> tuple[int, int, int, int]:
    """Splits a turn's context across input, cache-write and cache-read tokens, all three non-zero."""
    cache_read = context // 2
    return 10, context - 10 - cache_read, cache_read, TURN_OUTPUT_TOKENS


def build_busiest_transcripts(folder: Path, second_folder: Path) -> None:
    """Writes a busy session in the second folder and decoys that beat it on everything but turns.

    The first folder's session has 6 turns, each on three lines (18 lines against the busiest's
    13), 100 times the busiest's tokens and about 20 active minutes; its subagent has 12 turns. The
    second folder's session has 10 turns over less than a minute.
    """
    decoy_id = "sess-a"
    decoy_lines = [user_line(0, False, session_id=decoy_id)]
    for turn in range(6):
        decoy_lines += assistant_lines(
            4 * (turn + 1), f"msg-decoy-{turn}", context_usage(100000), 3, False, session_id=decoy_id
        )
    write_jsonl(folder / f"{decoy_id}.jsonl", decoy_lines)
    subagent_lines = [user_line(100, True)]
    for turn in range(12):
        subagent_lines += assistant_lines(100 + turn / 10, f"msg-sub-{turn}", context_usage(70), 1, True)
    write_subagent(folder / decoy_id / "subagents", "d1", TEST_WRITER, subagent_lines)

    busiest_id = "sess-b"
    busiest_lines = [user_line(200, False, session_id=busiest_id)]
    for turn, (context, blocks) in enumerate(zip(BUSIEST_CONTEXTS, BUSIEST_BLOCKS, strict=True)):
        moment = 200 + (turn + 1) / 20
        busiest_lines += assistant_lines(
            moment, f"msg-busy-{turn}", context_usage(context), blocks, False, session_id=busiest_id
        )
    write_jsonl(second_folder / f"{busiest_id}.jsonl", busiest_lines)


# Content planted where real transcripts carry it (R6.3, T36). Long and distinctive, so the report's
# role names and numbers cannot contain them by chance; each also has fragments checked on their own,
# so a truncated or partly rewritten leak fails too. No uppercase Z: the timestamp parser rewrites it.
PLANTED_TAG = "pl4nted-content-marker-q7vw"
PLANTED_EMAIL_LOCAL = "yolanda.quintavalle.leak"
PLANTED_EMAIL_DOMAIN = "planted-mail.example"
PLANTED_EMAIL = PLANTED_EMAIL_LOCAL + "@" + PLANTED_EMAIL_DOMAIN
# A key shaped like a real Anthropic key, built by parts so no literal key sits in the source.
PLANTED_KEY_TAIL = "Xq7Vb" + "Lm2Rk" + "9TwPd" + "Ha4Ns" + "Ej8Uy" + "Cf3Gx" + "_Kv6Q" + "o1Wt-" + "Jr5Mb"
PLANTED_KEY = "sk-" + "ant-api03-" + PLANTED_KEY_TAIL * 2 + "-planted"
PLANTED_CODE_IDENTIFIER = "leak_marker_payload_quux"
PLANTED_CODE = f"def {PLANTED_CODE_IDENTIFIER}(rows):\n    return sorted(rows)  # planted-code-comment-v9"
PLANTED_FRAGMENTS = (
    PLANTED_TAG,
    PLANTED_EMAIL,
    PLANTED_EMAIL_LOCAL,
    PLANTED_EMAIL_DOMAIN,
    PLANTED_KEY,
    PLANTED_KEY_TAIL,
    PLANTED_KEY_TAIL[:12],
    PLANTED_KEY_TAIL[-12:],
    PLANTED_CODE_IDENTIFIER,
    "planted-code-comment-v9",
)


def planted(place: str) -> str:
    """Returns text holding the email, the key and the code, tagged with where it was planted."""
    return f"{place} {PLANTED_TAG}: write to {PLANTED_EMAIL}, key {PLANTED_KEY}\n{PLANTED_CODE}"


def planted_command(place: str) -> str:
    """Returns shell-safe planted text, for an echo inside a command line."""
    return f"'{place} {PLANTED_TAG} {PLANTED_EMAIL} {PLANTED_KEY} {PLANTED_CODE_IDENTIFIER}'"


def with_planted_result(line: dict, content: object, place: str) -> dict:
    """Puts planted content in a tool_result line's content and in its top-level toolUseResult."""
    line["message"]["content"][0]["content"] = content
    line["toolUseResult"] = {"stdout": planted(f"{place}-stdout"), "stderr": planted(f"{place}-stderr")}
    return line


def build_planted_transcripts(folder: Path) -> None:
    """Writes a well-formed session and subagent with planted content in every place content lives."""
    user_text = user_line(0, False)
    user_text["message"]["content"] = planted("user-string")
    user_blocks = user_line(0.5, False)
    user_blocks["message"]["content"] = [{"type": "text", "text": planted("user-block")}]
    reply = assistant_lines(1, "msg-p1", (100, 0, 0, 10), 2, False)
    reply[0]["message"]["content"] = [{"type": "thinking", "thinking": planted("thinking"), "signature": "c2ln"}]
    reply[1]["message"]["content"] = [{"type": "text", "text": planted("assistant-text")}]
    check_run = shell("toolu_p2", f"npm run check && echo {planted_command('bash')}")
    test_run = shell(
        "toolu_p3", f"python -m pytest -k {PLANTED_CODE_IDENTIFIER}; echo {planted_command('ps')}", "PowerShell"
    )
    write_code = ("toolu_p4", "Write", {"file_path": f"src/{PLANTED_CODE_IDENTIFIER}.py", "content": planted("write")})
    agent_call = (
        "toolu_p5",
        "Agent",
        {"subagent_type": TEST_WRITER, "description": planted("dispatch-description"), "prompt": planted("prompt")},
    )
    attachment = {"type": "attachment", "timestamp": stamp(7), "attachment": {"content": planted("attachment")}}
    write_jsonl(
        folder / f"{SESSION_ID}.jsonl",
        [
            user_text,
            user_blocks,
            *reply,
            tool_use_line(2, "msg-p2", check_run, False),
            with_planted_result(tool_result_line(3, "toolu_p2", False), planted("result-string"), "check"),
            tool_use_line(4, "msg-p3", test_run, False),
            with_planted_result(
                tool_result_line(4.5, "toolu_p3", False), [{"type": "text", "text": planted("result-list")}], "test"
            ),
            tool_use_line(5, "msg-p4", write_code, False),
            with_planted_result(tool_result_line(5.5, "toolu_p4", False), planted("write-result"), "write"),
            tool_use_line(6, "msg-p5", agent_call, False),
            with_planted_result(tool_result_line(6.5, "toolu_p5", False), planted("agent-result"), "agent"),
            attachment,
        ],
    )
    subagents = folder / SESSION_ID / "subagents"
    sub_user = user_line(10, True)
    sub_user["message"]["content"] = planted("subagent-prompt")
    write_subagent(subagents, "p1", TEST_WRITER, [sub_user, *assistant_lines(11, "msg-p6", (50, 0, 0, 5), 1, True)])
    meta_path = subagents / "agent-p1.meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["description"] = planted("meta-description")
    meta_path.write_text(json.dumps(meta), encoding="utf-8")


def build_unreadable_meta_transcripts(folder: Path, meta_text: str) -> None:
    """Writes a well-formed session and subagent whose meta.json is replaced by `meta_text`."""
    session_lines = [user_line(0, False), *assistant_lines(1, "msg-m1", (10, 0, 0, 1), 1, False)]
    write_jsonl(folder / f"{SESSION_ID}.jsonl", session_lines)
    subagent_lines = [user_line(10, True), *assistant_lines(11, "msg-m2", (5, 0, 0, 1), 1, True)]
    subagents = folder / SESSION_ID / "subagents"
    write_subagent(subagents, "m1", TEST_WRITER, subagent_lines)
    (subagents / "agent-m1.meta.json").write_text(meta_text, encoding="utf-8")


def build_bad_timestamp_transcript(folder: Path) -> None:
    """Writes a session whose first line's timestamp field holds planted content instead of a time."""
    bad_line = user_line(0, False)
    bad_line["timestamp"] = planted("timestamp")
    write_jsonl(
        folder / f"{SESSION_ID}.jsonl",
        [bad_line, *assistant_lines(1, "msg-t1", (100, 0, 0, 10), 1, False)],
    )


# Usage of every invalid line: if one is read instead of skipped, a million tokens show in the table.
COSTLY_USAGE = (1_000_000, 0, 0, 1_000_000)
# An agentType that is free text, not a name; the report must never print it.
FREE_TEXT_AGENT_TYPE = "Free text agent zq9 with spaces"


def encoded_line(line: object, ending: bytes = b"\n") -> bytes:
    """Returns one transcript line as UTF-8 bytes, non-ASCII characters written raw, not escaped."""
    return json.dumps(line, ensure_ascii=False).encode("utf-8") + ending


def costly_assistant(minutes: float, message_id: str) -> dict:
    """Returns one assistant line with COSTLY_USAGE, written `minutes` after START."""
    return assistant_lines(minutes, message_id, COSTLY_USAGE, 1, False)[0]


def with_usage(line: dict, **fields: object) -> dict:
    """Overwrites fields of an assistant line's usage."""
    line["message"]["usage"].update(fields)
    return line


def build_invalid_line_transcripts(folder: Path) -> None:
    """Writes a session and three subagents mixing valid lines with 15 invalid ones (R6.4, T37).

    Valid lines sit at minutes 0 to 3; every invalid line that has a valid timestamp sits between
    3.25 and 5.5, within 5 minutes of them, so reading one adds active time as well as a million
    tokens and a turn.
    """
    # Built with chr so the source holds no raw separator; encoded_line writes them raw in the JSON.
    separator = chr(0x2028) + chr(0x2029) + chr(0x85)
    separated = assistant_lines(2, "msg-v2", (200, 0, 0, 20), 1, False)[0]
    separated["message"]["content"] = [{"type": "text", "text": f"one{separator}two"}]

    no_id = costly_assistant(3.25, "unused")
    del no_id["message"]["id"]
    string_usage = costly_assistant(3.5, "msg-bad-string-usage")
    string_usage["message"]["usage"] = "lots"
    bad_timestamp = costly_assistant(3.75, "msg-bad-timestamp")
    bad_timestamp["timestamp"] = "not a date"
    string_message = user_line(4, False)
    string_message["message"] = "plain text instead of an object"
    utf8_source = encoded_line(costly_assistant(5.25, "msg-bad-utf8"))
    partial = encoded_line(costly_assistant(5.5, "msg-bad-partial"), b"")

    session = [
        encoded_line(user_line(0, False)),
        encoded_line(assistant_lines(1, "msg-v1", (100, 0, 0, 10), 1, False)[0]),
        b"\n",  # A blank line in the middle: not counted.
        encoded_line(separated),  # Raw U+2028, U+2029 and U+0085 inside a string: one valid line.
        encoded_line(assistant_lines(3, "msg-v3", (300, 0, 0, 30), 1, False)[0], b"\r\n"),  # Valid.
        encoded_line({"type": "attachment", "attachment": {"kind": "file"}}),  # No timestamp: valid.
        # Invalid lines, skipped and counted:
        encoded_line([1, 2]),  # 1: a JSON array.
        encoded_line("just text"),  # 2: a bare JSON string.
        encoded_line({"type": "attachment", "timestamp": "yesterday"}),  # 3: other type, bad timestamp.
        encoded_line(bad_timestamp),  # 4: assistant whose timestamp is not a date.
        encoded_line(no_id),  # 5: assistant without message.id.
        encoded_line(string_usage),  # 6: usage is a string.
        encoded_line(string_message),  # 7: user line whose message is a string.
        encoded_line(with_usage(costly_assistant(4.25, "msg-bad-nan"), output_tokens=float("nan"))),  # 8: NaN.
        encoded_line(with_usage(costly_assistant(4.5, "msg-bad-inf"), output_tokens=float("inf"))),  # 9: Infinity.
        encoded_line(with_usage(costly_assistant(4.75, "msg-bad-negative"), output_tokens=-1_000_000)),  # 10.
        encoded_line(with_usage(costly_assistant(5, "msg-bad-float"), output_tokens=1_000_000.5)),  # 11: float.
        encoded_line(with_usage(costly_assistant(5.1, "msg-bad-bool"), cache_read_input_tokens=True)),  # 12: bool.
        utf8_source.replace(b'"text": "x"', b'"text": "\xff\xfe"'),  # 13: invalid UTF-8 bytes.
        partial[:-1],  # 14: a partial last line, no closing brace and no final newline.
    ]
    (folder / f"{SESSION_ID}.jsonl").parent.mkdir(parents=True, exist_ok=True)
    (folder / f"{SESSION_ID}.jsonl").write_bytes(b"".join(session))

    subagents = folder / SESSION_ID / "subagents"
    # Test-writer: one valid turn active 2 min, then 15: a line that is not JSON, then a trailing newline.
    writer_lines = [user_line(10, True), *assistant_lines(12, "msg-w1", (40, 0, 0, 4), 1, True)]
    write_subagent(subagents, "w1", TEST_WRITER, writer_lines)
    with (subagents / "agent-w1.jsonl").open("ab") as transcript:
        transcript.write(b"not json at all {\n")
    # Two subagents of role unknown: one without meta.json (active 1 min), one whose agentType is free
    # text (active 3 min).
    no_meta_lines = [user_line(20, True), *assistant_lines(21, "msg-u1", (50, 0, 0, 5), 1, True)]
    write_subagent(subagents, "u1", TEST_WRITER, no_meta_lines)
    (subagents / "agent-u1.meta.json").unlink()
    free_text_lines = [user_line(30, True), *assistant_lines(33, "msg-u2", (70, 0, 0, 7), 1, True)]
    write_subagent(subagents, "u2", FREE_TEXT_AGENT_TYPE, free_text_lines)


# Generated transcripts for the output-shape property (R6.3, T36 invariant). write_jsonl writes every
# non-ASCII character as an ASCII escape, so U+2028, U+2029 and U+0085 are left out of the alphabet;
# raw separators inside a valid line are covered by test_skips_and_counts_invalid_lines.
PROPERTY_SEEDS = 24
TEXT_ALPHABET = string.ascii_letters + string.digits + string.punctuation + " \t\n\\\"'" + "áéíóúñÜç€" + "🙂🚀"
LOOKALIKE_TEXTS = (
    "orchestrator  1  2  3  4  5  6.0  7.5%",
    "role  dispatches  turns  input  output",
    "busiest orchestrator session",
    "turns  context_first  context_max",
    "42",
    "12.5%",
    TEST_WRITER,
    "skipped lines: 7",
    "Traceback (most recent call last):",
    '{"type": "assistant", "message": {}}',
    "C:\\Users\\someone\\file.py",
)
AGENT_TYPES = (TEST_WRITER, IMPLEMENTER, "konundrm-eng:spec-reviewer", "general-purpose", "Explore")
MODELS = ("claude-opus-5-5", "claude-sonnet-5", "claude-haiku-4-5")
COMMAND_TEMPLATES = (
    ("check", "npm run check {}"),
    ("check", "cd /repo && npm run check 2>&1 | tail -5"),
    ("test", "python -m pytest {}"),
    ("test", "python -m unittest discover -s tests -k {}"),
    ("test", "npm test"),
    ("other", "echo {}"),
    ("other", "grep -n {} notes.md"),
    ("other", "git status {}"),
)
OTHER_LINE_TYPES = ("attachment", "system", "queue-operation", "last-prompt", "api-request-blob")
NUMBER_CELL = re.compile(r"\d+(?:\.\d+)?%?")
COLUMN_NAME = re.compile(r"[a-z][a-z0-9_]*")
SKIPPED_LINES = re.compile(r"skipped lines: \d+")


class TranscriptGenerator:
    """Draws well-formed transcripts with arbitrary content where real transcripts carry content.

    Attributes:
        rng: The seeded source of every choice.
        minutes: Minutes after START of the last line written; each line moves it forward.
        roles: The orchestrator and every agentType written.
        models: Every model name written.
        features: The kinds of structure drawn, so the test can show the domain was covered.
    """

    def __init__(self, rng: random.Random) -> None:
        self.rng = rng
        self.minutes = 0.0
        self.message_count = 0
        self.roles = {ORCHESTRATOR}
        self.models: set[str] = set()
        self.features: set[str] = set()

    def text(self) -> str:
        """Returns arbitrary text, sometimes shaped like a table row, a number or a role name."""
        noise = "".join(self.rng.choices(TEXT_ALPHABET, k=self.rng.randint(0, 40)))
        return self.rng.choice(LOOKALIKE_TEXTS) + noise if self.rng.random() < 0.3 else noise

    def _tick(self) -> float:
        self.minutes += self.rng.choice((0, 0.1, 0.5, 2, 7))
        return self.minutes

    def _message_id(self) -> str:
        self.message_count += 1
        return f"msg-gen-{self.message_count}"

    def _assistant(self, sidechain: bool, session_id: str) -> list[dict]:
        usage = tuple(self.rng.randint(0, 5000) for _ in range(4))
        lines = assistant_lines(
            self._tick(), self._message_id(), usage, self.rng.randint(1, 3), sidechain, session_id=session_id
        )
        model = self.rng.choice(MODELS)
        self.models.add(model)
        for line in lines:
            line["message"]["model"] = model
            kind = self.rng.choice(("text", "thinking"))
            line["message"]["content"] = [{"type": kind, kind: self.text()}]
        return lines

    def _user(self, sidechain: bool, session_id: str) -> dict:
        line = user_line(self._tick(), sidechain, session_id=session_id)
        if self.rng.random() < 0.5:
            line["message"]["content"] = self.text()
        else:
            line["message"]["content"] = [{"type": "text", "text": self.text()} for _ in range(self.rng.randint(1, 2))]
        return line

    def _tool_input(self, tool_use_id: str) -> tuple[str, str, dict]:
        roll = self.rng.random()
        if roll < 0.6:
            kind, template = self.rng.choice(COMMAND_TEMPLATES)
            self.features.add(f"{kind} command")
            return shell(tool_use_id, template.format(self.text()), self.rng.choice(("Bash", "PowerShell")))
        if roll < 0.8:
            self.features.add("dispatch")
            dispatch_input = {"subagent_type": TEST_WRITER, "description": self.text(), "prompt": self.text()}
            return tool_use_id, "Agent", dispatch_input
        return tool_use_id, "Write", {"file_path": self.text(), "content": self.text()}

    def _tool_call(self, sidechain: bool, session_id: str) -> list[dict]:
        tool_use_id = f"toolu_gen_{self.message_count}"
        call = tool_use_line(self._tick(), self._message_id(), self._tool_input(tool_use_id), sidechain)
        result = tool_result_line(self._tick(), tool_use_id, sidechain)
        for line in (call, result):
            line["sessionId"] = session_id
        if self.rng.random() < 0.5:
            self.features.add("string result")
            result["message"]["content"][0]["content"] = self.text()
        else:
            self.features.add("list result")
            result["message"]["content"][0]["content"] = [{"type": "text", "text": self.text()}]
        if self.rng.random() < 0.6:
            self.features.add("toolUseResult")
            result["toolUseResult"] = {"stdout": self.text(), "stderr": self.text(), "interrupted": False}
        return [call, result]

    def _other(self) -> dict:
        self.features.add("other line type")
        line = {"type": self.rng.choice(OTHER_LINE_TYPES), "content": self.text(), "data": {"text": self.text()}}
        if self.rng.random() < 0.5:
            line["timestamp"] = stamp(self._tick())
        return line

    def transcript(self, sidechain: bool, session_id: str) -> list[dict]:
        """Returns one transcript: a first user line, then user, assistant, tool and other lines."""
        lines = [self._user(sidechain, session_id)]
        for _ in range(self.rng.randint(0, 8)):
            roll = self.rng.random()
            if roll < 0.2:
                lines.append(self._user(sidechain, session_id))
            elif roll < 0.5:
                lines += self._assistant(sidechain, session_id)
            elif roll < 0.85:
                lines += self._tool_call(sidechain, session_id)
            else:
                lines.append(self._other())
        return lines

    def folders(self, root: Path) -> list[Path]:
        """Writes one or two project folders, each with sessions and their subagents."""
        folders = [root / f"project-{index}" for index in range(self.rng.randint(1, 2))]
        if len(folders) == 2:
            self.features.add("two folders")
        for folder_index, folder in enumerate(folders):
            for session_index in range(self.rng.randint(1, 2)):
                session_id = f"sess-{folder_index}-{session_index}"
                write_jsonl(folder / f"{session_id}.jsonl", self.transcript(False, session_id))
                agent_count = self.rng.randint(0, 2)
                self.features.add("subagents" if agent_count else "no subagent")
                for agent_index in range(agent_count):
                    agent_type = self.rng.choice(AGENT_TYPES)
                    self.roles.add(agent_type)
                    subagents = folder / session_id / "subagents"
                    agent_id = f"g{agent_index}"
                    write_subagent(subagents, agent_id, agent_type, self.transcript(True, session_id))
                    meta_path = subagents / f"agent-{agent_id}.meta.json"
                    meta = json.loads(meta_path.read_text(encoding="utf-8"))
                    meta["description"] = self.text()
                    meta_path.write_text(json.dumps(meta), encoding="utf-8")
        return folders


def lines_off_shape(stdout: str, roles: set[str], models: set[str]) -> list[str]:
    """Returns every stdout line that is not blank, a fixed header or title, a role row or numbers.

    A header is a line of column names starting with ``role`` or ``turns``; a role row starts with a
    role the transcripts named and has one cell per header column, each a number (a percentage
    allowed) or a model the transcripts named; the busiest orchestrator's row has only numbers.
    """
    off_shape = []
    widths: dict[str, int] = {}
    for line in stdout.splitlines():
        cells = line.split()
        if not cells or line == "busiest orchestrator session" or SKIPPED_LINES.fullmatch(line):
            continue
        if cells[0] in {"role", "turns"} and all(COLUMN_NAME.fullmatch(cell) for cell in cells):
            widths[cells[0]] = len(cells)
            continue
        if (
            cells[0] in roles
            and len(cells) == widths.get("role")
            and all(NUMBER_CELL.fullmatch(cell) or cell in models for cell in cells[1:])
        ):
            continue
        if len(cells) == widths.get("turns") and all(NUMBER_CELL.fullmatch(cell) for cell in cells):
            continue
        off_shape.append(line)
    return off_shape


def run_generated_example(seed: int) -> tuple[TranscriptGenerator, subprocess.CompletedProcess[str]]:
    """Writes the transcripts seed `seed` draws and runs the CLI on them from a project with a check."""
    generator = TranscriptGenerator(random.Random(seed))  # noqa: S311 - seeded test data, not cryptography
    with tempfile.TemporaryDirectory() as temporary:
        project = Path(temporary) / "app"
        project.mkdir()
        (project / "package.json").write_text(json.dumps({"scripts": {"check": "echo ok"}}), encoding="utf-8")
        folders = generator.folders(Path(temporary))
        completed = run_session_costs(folders[0], project, *(str(folder) for folder in folders[1:]))
    return generator, completed


def read_busiest_block(stdout: str) -> dict[str, str]:
    """Returns the busiest-orchestrator block: its header line of field names, zipped with the next line."""
    lines = [line.split() for line in stdout.splitlines() if line.strip()]
    header_index = next(index for index, tokens in enumerate(lines) if "context_first" in tokens)
    return dict(zip(lines[header_index], lines[header_index + 1], strict=True))


def run_session_costs(folder: Path, project: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    """Runs the CLI from `project`, with no KONUNDRM_CHECK_CMD override in its environment."""
    environment = {name: value for name, value in os.environ.items() if name != "KONUNDRM_CHECK_CMD"}
    return subprocess.run(
        [sys.executable, str(SESSION_COSTS), str(folder), *extra],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=60,
        cwd=project,
        env=environment,
    )


def read_table(stdout: str) -> dict[str, dict[str, str]]:
    """Returns each role's row of the per-role table, keyed by column name from its header line."""
    lines = [line.split() for line in stdout.splitlines() if line.strip()]
    header = next(tokens for tokens in lines if tokens[0] == "role")
    rows = {}
    for tokens in lines:
        if tokens[0] in {ORCHESTRATOR, TEST_WRITER, IMPLEMENTER, UNKNOWN_ROLE} and len(tokens) == len(header):
            rows[tokens[0]] = dict(zip(header, tokens, strict=True))
    return rows


def number(row: dict[str, str], key: str) -> float:
    """Returns the value of the column named by COLUMNS[key], a percentage sign allowed."""
    return float(row[COLUMNS[key]].rstrip("%"))


# Windows refuses paths of 260 characters or more unless they carry this prefix (and the registry's
# LongPathsEnabled is off); built with chr so no escape slips. Linux opens long paths natively.
EXTENDED_PATH_PREFIX = chr(92) * 2 + "?" + chr(92)
# Windows' limit, which the fixture's long paths must reach.
WINDOWS_PATH_LIMIT = 260


def extended_path(path: Path) -> Path:
    """Returns `path`, absolute and without "." or ".." parts, as this test can create and remove it.

    On Windows that is the path behind the extended-length prefix, so files past 260 characters can
    be written whatever the registry says; elsewhere it is `path` itself.
    """
    if sys.platform != "win32":
        return path
    return Path(EXTENDED_PATH_PREFIX + str(path))


def build_long_path_transcripts(root: Path) -> tuple[Path, Path, Path]:
    """Writes the transcripts of R6.5 (T38) under `root` (absolute, resolved) and returns their folders.

    Returns:
        ``(long_folder, short_folder, long_bad_folder)`` as a user would pass them, without prefix:
        a folder whose own path passes 260 characters, holding a session (100 + 10 tokens) and a
        test-writer subagent (50 + 5); a short folder whose session transcript (200 + 20) is short
        but whose implementer subagent (70 + 7) and its meta.json pass 260; and a folder past 260
        holding only a directory named like a session transcript, which cannot be read.
    """
    long_folder = root / ("p" * 110) / ("q" * 110)
    short_folder = root / "short"
    long_bad_folder = root / ("b" * 110) / ("c" * 110)
    long_session = "sess-long"
    write_jsonl(
        extended_path(long_folder / f"{long_session}.jsonl"),
        [user_line(0, False), *assistant_lines(1, "msg-l1", (100, 0, 0, 10), 1, False)],
    )
    write_subagent(
        extended_path(long_folder / long_session / "subagents"),
        "l1",
        TEST_WRITER,
        [user_line(10, True), *assistant_lines(11, "msg-l2", (50, 0, 0, 5), 1, True)],
    )
    # Claude Code names the session folder after the session id; a long id makes the subagent's
    # files pass the limit while the session transcript beside it stays under it.
    short_session = "s" * 120
    write_jsonl(
        extended_path(short_folder / f"{short_session}.jsonl"),
        [user_line(20, False), *assistant_lines(21, "msg-s1", (200, 0, 0, 20), 1, False)],
    )
    write_subagent(
        extended_path(short_folder / short_session / "subagents"),
        "a" * 100,
        IMPLEMENTER,
        [user_line(30, True), *assistant_lines(31, "msg-s2", (70, 0, 0, 7), 1, True)],
    )
    extended_path(long_bad_folder / f"{SESSION_ID}.jsonl").mkdir(parents=True)
    return long_folder, short_folder, long_bad_folder


class SessionCostsTest(unittest.TestCase):
    # R6.1 (first half, T33): per role, dispatches, turns, tokens by type, weighted tokens (1; 1.25;
    # 0.1; 5), share of the total and active minutes (median and total, pauses over 5 min left out).
    def test_reports_tokens_weights_shares_and_active_time_per_role(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary) / "project"
            second_folder = Path(temporary) / "project-2"
            build_transcripts(folder, second_folder)

            completed = subprocess.run(
                [sys.executable, str(SESSION_COSTS), str(folder), str(second_folder)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                timeout=60,
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        rows = read_table(completed.stdout)
        self.assertEqual(set(rows), {ORCHESTRATOR, TEST_WRITER, IMPLEMENTER}, completed.stdout)
        # Orchestrator: one dispatch per session (2); 200 + 400 * 1.25 + 3000 * 0.1 + 60 * 5 = 1300 of
        # 2000 weighted tokens; sessions active 6 and 0 min (median 3, total 6).
        # Test-writer: 4 turns * (50 + 10 * 5) = 400. Implementer: 100 + 80 * 1.25 + 20 * 5 = 300.
        expected = {
            ORCHESTRATOR: {
                "dispatches": 2,
                "turns": 2,
                "input": 200,
                "cache_write": 400,
                "cache_read": 3000,
                "output": 60,
                "weighted": 1300,
                "share": 65,
                "median_minutes": 3,
                "total_minutes": 6,
            },
            TEST_WRITER: {
                "dispatches": 3,
                "turns": 4,
                "input": 200,
                "cache_write": 0,
                "cache_read": 0,
                "output": 40,
                "weighted": 400,
                "share": 20,
                "median_minutes": 2,
                "total_minutes": 12,
            },
            IMPLEMENTER: {
                "dispatches": 1,
                "turns": 1,
                "input": 100,
                "cache_write": 80,
                "cache_read": 0,
                "output": 20,
                "weighted": 300,
                "share": 15,
                "median_minutes": 3,
                "total_minutes": 3,
            },
        }
        actual = {role: {key: number(rows[role], key) for key in values} for role, values in expected.items()}
        self.assertEqual(actual, expected, completed.stdout)

    # R6.1 (second half, T34): per role, full check runs with their total time, test runs and
    # messages with two or more parallel dispatches.
    def test_counts_check_runs_test_runs_and_parallel_dispatches(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary) / "transcripts"
            project = Path(temporary) / "app"
            project.mkdir()
            # The default check is the project's, found as the hooks find it: `npm run check`.
            (project / "package.json").write_text(json.dumps({"scripts": {"check": "echo ok"}}), encoding="utf-8")
            build_tool_transcripts(folder)

            default_check = run_session_costs(folder, project)
            custom_check = run_session_costs(folder, project, "--check-pattern", "^make verify")

        keys = ("check_runs", "check_minutes", "test_runs", "parallel_messages")
        # Default check: the orchestrator's `cd … && npm run check | tail` (1.5 min, paired with its own
        # result, not the grep's) counts; the grep, the echo and `make verify` do not. The implementer's
        # check counts in its own row. A check is not a test run.
        expected_default = {
            ORCHESTRATOR: {"check_runs": 1, "check_minutes": 1.5, "test_runs": 2, "parallel_messages": 1},
            IMPLEMENTER: {"check_runs": 1, "check_minutes": 3, "test_runs": 2, "parallel_messages": 0},
            TEST_WRITER: {"check_runs": 0, "check_minutes": 0, "test_runs": 1, "parallel_messages": 0},
        }
        # --check-pattern replaces the default: only `make verify` (2 min) is a check run.
        expected_custom = {
            ORCHESTRATOR: {"check_runs": 1, "check_minutes": 2, "test_runs": 2, "parallel_messages": 1},
            IMPLEMENTER: {"check_runs": 0, "check_minutes": 0, "test_runs": 2, "parallel_messages": 0},
            TEST_WRITER: {"check_runs": 0, "check_minutes": 0, "test_runs": 1, "parallel_messages": 0},
        }
        for completed, expected in ((default_check, expected_default), (custom_check, expected_custom)):
            self.assertEqual(completed.returncode, 0, completed.stderr)
            rows = read_table(completed.stdout)
            self.assertEqual(set(rows), set(expected), completed.stdout)
            self.assertLessEqual({COLUMNS[key] for key in keys}, set(rows[ORCHESTRATOR]), completed.stdout)
            actual = {role: {key: number(rows[role], key) for key in keys} for role in expected}
            self.assertEqual(actual, expected, completed.stdout)

    # R6.2 (T35): for the orchestrator session with the most turns, its turns and its context per
    # turn: the first, the median, the 90th percentile (nearest rank) and the maximum.
    def test_reports_the_busiest_orchestrators_context_per_turn(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary) / "project"
            second_folder = Path(temporary) / "project-2"
            build_busiest_transcripts(folder, second_folder)

            completed = run_session_costs(folder, Path(temporary), str(second_folder))

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("context_first", completed.stdout.split(), completed.stdout)
        block = read_busiest_block(completed.stdout)
        expected = {"turns": 10, "context_first": 500, "context_median": 600, "context_p90": 1000, "context_max": 5000}
        actual = {name: float(block[name]) for name in expected if name in block}
        self.assertEqual(actual, expected, completed.stdout)

    # R6.3 (T36; design.md Threats, row 4): the report shows only counts, times and token totals,
    # never the content of messages, commands or results, not even when reading a transcript fails.
    def test_never_prints_message_command_or_result_content(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary) / "transcripts"
            bad_folder = Path(temporary) / "bad-transcripts"
            project = Path(temporary) / "app"
            project.mkdir()
            (project / "package.json").write_text(json.dumps({"scripts": {"check": "echo ok"}}), encoding="utf-8")
            build_planted_transcripts(folder)
            build_bad_timestamp_transcript(bad_folder)

            clean = run_session_costs(folder, project)
            failing = run_session_costs(bad_folder, project)

        def leaks(text: str) -> list[str]:
            return [fragment for fragment in PLANTED_FRAGMENTS if fragment in text]

        # Well-formed transcripts: the table, with the planted commands counted, and nothing planted.
        self.assertEqual(clean.returncode, 0, clean.stderr)
        self.assertEqual(clean.stderr, "")
        self.assertEqual(leaks(clean.stdout), [], clean.stdout)
        rows = read_table(clean.stdout)
        self.assertEqual(set(rows), {ORCHESTRATOR, TEST_WRITER}, clean.stdout)
        self.assertEqual((number(rows[ORCHESTRATOR], "check_runs"), number(rows[ORCHESTRATOR], "test_runs")), (1, 1))
        # A timestamp holding planted text: whatever the outcome, neither stream repeats it, and no
        # traceback is printed.
        self.assertEqual(leaks(failing.stdout), [], failing.stdout)
        self.assertEqual(leaks(failing.stderr), [], failing.stderr)
        self.assertNotIn("Traceback", failing.stderr)

    # R6.3 (T36, decision A): a transcript that cannot be read exits 1 with one fixed stderr line that
    # names the file and the original error's type, never its message nor a traceback; stdout is empty.
    def test_unreadable_transcript_exits_1_with_one_line_naming_file_and_error_type(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary) / "unreadable-transcripts"
            # A directory named like a session transcript: the glob lists it and reading it fails with
            # an error that stays an error (PermissionError on Windows, IsADirectoryError on Linux).
            transcript = folder / f"{SESSION_ID}.jsonl"
            transcript.mkdir(parents=True)
            with self.assertRaises(OSError) as raised:
                transcript.read_text(encoding="utf-8")
            expected_type = type(raised.exception).__name__

            completed = run_session_costs(folder, Path(temporary))

        context = f"exit {completed.returncode}\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        self.assertEqual(completed.returncode, 1, context)
        self.assertEqual(completed.stdout, "", context)
        self.assertNotIn("Traceback", completed.stderr, context)
        self.assertTrue(completed.stderr.endswith("\n"), context)
        stderr_lines = completed.stderr.splitlines()
        self.assertEqual(len(stderr_lines), 1, context)
        line = re.fullmatch(r"session_costs: cannot read (?P<path>.+): (?P<error_type>\w+)", stderr_lines[0])
        self.assertIsNotNone(line, context)
        # Compared by its last two parts, so a long-path prefix (\\?\) or expanded short name still matches.
        self.assertEqual(Path(line["path"]).parts[-2:], (folder.name, transcript.name), context)
        self.assertEqual(line["error_type"], expected_type, context)

    # R6.3 (T36): a subagent's meta.json without agentType, or not JSON at all, never makes the script
    # print a traceback or any of the meta.json's text, whatever the exit code.
    def test_unusable_meta_json_prints_no_traceback_and_none_of_its_text(self) -> None:
        missing_agent_type = json.dumps({"description": planted("meta-description"), "toolUseId": "toolu_m1"})
        meta_texts = {"no agentType": missing_agent_type, "not JSON": planted("meta-not-json")}
        for case, meta_text in meta_texts.items():
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                folder = Path(temporary) / "transcripts"
                build_unreadable_meta_transcripts(folder, meta_text)

                completed = run_session_costs(folder, Path(temporary))

                context = f"exit {completed.returncode}\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
                self.assertNotIn("Traceback", completed.stderr, context)
                for stream in (completed.stdout, completed.stderr):
                    self.assertEqual([fragment for fragment in PLANTED_FRAGMENTS if fragment in stream], [], context)

    # R6.3 (T36 invariant): whatever well-formed transcripts hold, every output line is a fixed header
    # or title, a role row (a role name, then numbers or model names) or numbers. Generated text may
    # coincide with a number or a role name, so the property checks each line's shape, not absence.
    def test_every_output_line_is_a_fixed_header_a_role_or_numbers(self) -> None:
        # Each seed has its own folders and process, so the seeds run side by side to stay fast.
        with ThreadPoolExecutor(max_workers=8) as pool:
            examples = list(pool.map(run_generated_example, range(PROPERTY_SEEDS)))

        for seed, (generator, completed) in enumerate(examples):
            with self.subTest(seed=seed):
                context = f"seed {seed}\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
                self.assertEqual(completed.returncode, 0, context)
                self.assertEqual(completed.stderr, "", context)
                self.assertEqual(lines_off_shape(completed.stdout, generator.roles, generator.models), [], context)
                self.assertIn(ORCHESTRATOR, read_table(completed.stdout), context)
        drawn = set().union(*(generator.features for generator, _ in examples))
        expected_features = {
            "check command",
            "test command",
            "other command",
            "dispatch",
            "string result",
            "list result",
            "toolUseResult",
            "other line type",
            "two folders",
            "subagents",
            "no subagent",
        }
        self.assertLessEqual(expected_features, drawn, "the generator covers its domain")

    # R6.4 (T37, decisions 1 A and 2 A): a line that is not UTF-8, not JSON, not an object, has a bad
    # timestamp or lacks a field the report reads is skipped and counted; a subagent without a usable
    # agentType is read under role unknown; the report ends with "skipped lines: <n>".
    def test_skips_and_counts_invalid_lines(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary) / "transcripts"
            build_invalid_line_transcripts(folder)

            completed = run_session_costs(folder, Path(temporary))

        context = f"exit {completed.returncode}\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        self.assertEqual(completed.returncode, 0, context)
        self.assertEqual(completed.stderr, "", context)
        # Skipped: 14 in the session (numbered in build_invalid_line_transcripts) + 1 in the test-writer.
        self.assertEqual(completed.stdout.splitlines()[-1], "skipped lines: 15", context)
        self.assertNotIn("zq9", completed.stdout, context)
        rows = read_table(completed.stdout)
        keys = ("dispatches", "turns", *("input", "cache_write", "cache_read", "output"))
        keys += ("median_minutes", "total_minutes")
        # Only valid lines count. Orchestrator: turns of 100+10, 200+20 (the line with raw separators)
        # and 300+30 (the \r\n line), active 0 to 3 min. Unknown: 50+5 active 1 min, 70+7 active 3 min.
        expected = {
            ORCHESTRATOR: dict(zip(keys, (1, 3, 600, 0, 0, 60, 3, 3), strict=True)),
            TEST_WRITER: dict(zip(keys, (1, 1, 40, 0, 0, 4, 2, 2), strict=True)),
            UNKNOWN_ROLE: dict(zip(keys, (2, 2, 120, 0, 0, 12, 2, 4), strict=True)),
        }
        self.assertEqual(set(rows), set(expected), context)
        actual = {role: {key: number(rows[role], key) for key in keys} for role in expected}
        self.assertEqual(actual, expected, context)

    # R6.5 (T38, decision A): transcripts whose paths pass 260 characters are read on Windows: a folder
    # whose own path passes the limit, and a short folder whose subagent transcript and meta.json pass
    # it. A path the script prints never carries the \\?\ prefix it may add.
    def test_reads_transcripts_past_the_windows_path_limit(self) -> None:
        # ignore_cleanup_errors: on Windows only the explicit rmtree through the prefix can remove it.
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temporary:
            root = Path(temporary).resolve()
            try:
                long_folder, short_folder, long_bad_folder = build_long_path_transcripts(root)
                short_subagents = short_folder / ("s" * 120) / "subagents"
                long_paths = {
                    "long folder": long_folder,
                    "short folder's subagent transcript": short_subagents / f"agent-{'a' * 100}.jsonl",
                    "short folder's subagent meta.json": short_subagents / f"agent-{'a' * 100}.meta.json",
                }
                bad_transcript = extended_path(long_bad_folder / f"{SESSION_ID}.jsonl")
                with self.assertRaises(OSError) as raised:
                    bad_transcript.read_text(encoding="utf-8")
                expected_type = type(raised.exception).__name__

                completed = run_session_costs(long_folder, root, str(short_folder))
                failing = run_session_costs(long_bad_folder, root)
            finally:
                shutil.rmtree(extended_path(root), ignore_errors=True)

        for name, path in long_paths.items():
            self.assertGreater(len(str(path)), WINDOWS_PATH_LIMIT, name)
        self.assertLess(len(str(short_folder / f"{'s' * 120}.jsonl")), WINDOWS_PATH_LIMIT)
        context = f"exit {completed.returncode}\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        self.assertEqual(completed.returncode, 0, context)
        self.assertEqual(completed.stderr, "", context)
        self.assertEqual(completed.stdout.splitlines()[-1], "skipped lines: 0", context)
        rows = read_table(completed.stdout)
        keys = ("dispatches", "turns", "input", "cache_write", "cache_read", "output")
        # An empty table means a folder was listed as empty; a row "unknown" means a meta.json was
        # taken for missing; exit 1 means a transcript could not be opened.
        expected = {
            ORCHESTRATOR: dict(zip(keys, (2, 2, 300, 0, 0, 30), strict=True)),
            TEST_WRITER: dict(zip(keys, (1, 1, 50, 0, 0, 5), strict=True)),
            IMPLEMENTER: dict(zip(keys, (1, 1, 70, 0, 0, 7), strict=True)),
        }
        self.assertEqual(set(rows), set(expected), context)
        actual = {role: {key: number(rows[role], key) for key in keys} for role in expected}
        self.assertEqual(actual, expected, context)
        # The unreadable transcript in a long folder: T36's one error line, its path as the user gave it.
        failing_context = f"exit {failing.returncode}\nstdout:\n{failing.stdout}\nstderr:\n{failing.stderr}"
        self.assertEqual(failing.returncode, 1, failing_context)
        expected_line = f"session_costs: cannot read {long_bad_folder / f'{SESSION_ID}.jsonl'}: {expected_type}\n"
        self.assertEqual(failing.stderr, expected_line, failing_context)
        self.assertNotIn(EXTENDED_PATH_PREFIX, failing.stderr, failing_context)


if __name__ == "__main__":
    unittest.main()
