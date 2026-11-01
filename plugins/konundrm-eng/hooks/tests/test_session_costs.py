"""Tests for hooks/scripts/session_costs.py, run as the CLI over synthetic session transcripts."""

from __future__ import annotations

import json
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


if __name__ == "__main__":
    unittest.main()
