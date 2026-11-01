"""Tests for hooks/scripts/session_costs.py, run as the CLI over synthetic session transcripts."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
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
        if tokens[0] in {ORCHESTRATOR, TEST_WRITER, IMPLEMENTER} and len(tokens) == len(header):
            rows[tokens[0]] = dict(zip(header, tokens, strict=True))
    return rows


def number(row: dict[str, str], key: str) -> float:
    """Returns the value of the column named by COLUMNS[key], a percentage sign allowed."""
    return float(row[COLUMNS[key]].rstrip("%"))


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


if __name__ == "__main__":
    unittest.main()
