"""Measures what a run cost, per role, from its Claude Code session transcripts.

A person runs it as ``sh "${CLAUDE_PLUGIN_ROOT}/hooks/run.sh" session_costs.py <folder>...``, where
each folder holds a project's transcripts (``~/.claude/projects/<project>/``). Every session
transcript ``<folder>/<session-id>.jsonl`` belongs to the role ``orchestrator``; every subagent
transcript ``<folder>/<session-id>/subagents/agent-<id>.jsonl`` belongs to the ``agentType`` of its
``agent-<id>.meta.json``. The per-role table it prints has, for each role: dispatches (transcripts),
turns, input, cache-write, cache-read and output tokens, weighted tokens, the role's share of all
weighted tokens and its active minutes (median and total over its transcripts).

It prints nothing read from a transcript except the agent type and numbers.

Sections:
    TOKEN_WEIGHTS          — input-equivalent weight of each token type.
    TranscriptCosts        — what one transcript cost.
    read_transcript()      — measures one transcript.
    find_transcripts()     — lists the transcripts of a folder with their role.
    RoleCosts              — what every transcript of one role cost together.
    collect_role_costs()   — measures every transcript of the given folders, per role.
    format_role_table()    — renders the per-role table.
    main()                 — CLI.
"""

from __future__ import annotations

import argparse
import itertools
import json
import statistics
import sys
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

ORCHESTRATOR_ROLE = "orchestrator"
"""Role of every session transcript, the session that dispatches the subagents."""

TOKEN_TYPES = ("input", "cache_write", "cache_read", "output")
"""Token types in table order."""

USAGE_FIELDS = {
    "input": "input_tokens",
    "cache_write": "cache_creation_input_tokens",
    "cache_read": "cache_read_input_tokens",
    "output": "output_tokens",
}
"""The API usage field that holds each token type."""

TOKEN_WEIGHTS = {"input": 1.0, "cache_write": 1.25, "cache_read": 0.1, "output": 5.0}
"""Input-equivalent weight of each token type, the ratio of their prices."""

MAX_ACTIVE_GAP_SECONDS = 5 * 60
"""Longest gap between two transcript lines that still counts as active time; longer is a pause."""


@dataclass
class TranscriptCosts:
    """What one transcript cost.

    Attributes:
        turns: Distinct API messages the model sent.
        tokens: Tokens per type (keys of TOKEN_TYPES), each message's usage counted once.
        active_minutes: Sum of the gaps between consecutive lines, pauses left out.
    """

    turns: int = 0
    tokens: dict[str, int] = field(default_factory=lambda: dict.fromkeys(TOKEN_TYPES, 0))
    active_minutes: float = 0.0


def _parse_timestamp(text: str) -> datetime:
    # Python 3.10's fromisoformat does not accept the trailing "Z" Claude Code writes.
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def _active_minutes(moments: list[datetime]) -> float:
    gaps = (later - earlier for earlier, later in itertools.pairwise(moments))
    seconds = sum(gap.total_seconds() for gap in gaps if gap.total_seconds() <= MAX_ACTIVE_GAP_SECONDS)
    return seconds / 60


def read_transcript(path: Path) -> TranscriptCosts:
    """Measures one transcript.

    Claude Code writes one API message as one line per content block, each repeating the message's
    id. A message counts as one turn and its usage once, taken from its last line: earlier lines
    can carry a partial ``output_tokens`` written while the message was still streaming.

    Args:
        path: A JSON Lines transcript.

    Returns:
        Its turns, tokens per type and active minutes. A transcript without assistant lines has 0
        turns and 0 tokens.

    Raises:
        OSError: If the file cannot be read.
        ValueError: If a line is not JSON or a timestamp is not ISO 8601.
    """
    costs = TranscriptCosts()
    usage_by_message_id: dict[str | None, dict[str, int]] = {}
    moments: list[datetime] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        if "timestamp" in entry:
            moments.append(_parse_timestamp(entry["timestamp"]))
        if entry.get("type") != "assistant":
            continue
        message = entry.get("message", {})
        # Each later line of a message overwrites the earlier ones, so its last line's usage wins.
        usage_by_message_id[message.get("id")] = message.get("usage", {})
    costs.turns = len(usage_by_message_id)
    for usage in usage_by_message_id.values():
        for token_type, usage_field in USAGE_FIELDS.items():
            costs.tokens[token_type] += usage.get(usage_field, 0)
    costs.active_minutes = _active_minutes(sorted(moments))
    return costs


def _subagent_role(transcript: Path) -> str:
    meta_path = transcript.with_suffix(".meta.json")
    return str(json.loads(meta_path.read_text(encoding="utf-8"))["agentType"])


def find_transcripts(folder: Path) -> Iterator[tuple[str, Path]]:
    """Lists the transcripts of one project folder with the role each belongs to.

    Args:
        folder: A project's transcript folder, holding ``<session-id>.jsonl`` files and
            ``<session-id>/subagents/agent-<id>.jsonl`` files.

    Yields:
        ``(role, path)`` for every session transcript (role ``orchestrator``) and every subagent
        transcript (the agentType of its meta.json). Other files, such as ``*.meta.json`` and
        ``*.prefix.json``, are skipped.
    """
    for session in sorted(folder.glob("*.jsonl")):
        yield ORCHESTRATOR_ROLE, session
    for subagent in sorted(folder.glob("*/subagents/agent-*.jsonl")):
        yield _subagent_role(subagent), subagent


@dataclass
class RoleCosts:
    """What every transcript of one role cost together.

    Attributes:
        dispatches: Transcripts of the role.
        turns: Turns over all of them.
        tokens: Tokens per type over all of them.
        active_minutes: Active minutes of each transcript, in reading order.
    """

    dispatches: int = 0
    turns: int = 0
    tokens: dict[str, int] = field(default_factory=lambda: dict.fromkeys(TOKEN_TYPES, 0))
    active_minutes: list[float] = field(default_factory=list)

    def add(self, transcript: TranscriptCosts) -> None:
        """Adds one transcript of the role as one more dispatch."""
        self.dispatches += 1
        self.turns += transcript.turns
        for token_type in TOKEN_TYPES:
            self.tokens[token_type] += transcript.tokens[token_type]
        self.active_minutes.append(transcript.active_minutes)

    @property
    def weighted_tokens(self) -> float:
        """Input-equivalent tokens: each token type times its TOKEN_WEIGHTS weight, summed."""
        return sum(self.tokens[token_type] * TOKEN_WEIGHTS[token_type] for token_type in TOKEN_TYPES)


def collect_role_costs(folders: list[Path]) -> dict[str, RoleCosts]:
    """Measures every transcript of the given folders and adds them up per role.

    Args:
        folders: Project transcript folders, read as one run.

    Returns:
        Each role's costs, keyed by role, in the order roles were first found.

    Raises:
        OSError: If a transcript or a subagent's meta.json cannot be read.
        ValueError: If one is not valid JSON.
        KeyError: If a subagent's meta.json names no agentType.
    """
    costs_by_role: dict[str, RoleCosts] = {}
    for folder in folders:
        for role, transcript in find_transcripts(folder):
            costs_by_role.setdefault(role, RoleCosts()).add(read_transcript(transcript))
    return costs_by_role


ROLE_TABLE_COLUMNS = (
    "role",
    "dispatches",
    "turns",
    *TOKEN_TYPES,
    "weighted",
    "share",
    "active_min_median",
    "active_min_total",
)
"""Header of the per-role table."""


def format_role_table(costs_by_role: dict[str, RoleCosts]) -> list[str]:
    """Renders the per-role table, one line per role under a header of column names.

    Args:
        costs_by_role: Each role's costs, as collect_role_costs returns them.

    Returns:
        The header line and one line per role, columns separated by whitespace. ``share`` is the
        role's percentage of all weighted tokens (0 when there are none); minutes have one decimal.
    """
    total_weighted = sum(costs.weighted_tokens for costs in costs_by_role.values())
    rows = [list(ROLE_TABLE_COLUMNS)]
    for role, costs in costs_by_role.items():
        share = 100 * costs.weighted_tokens / total_weighted if total_weighted else 0.0
        rows.append(
            [
                role,
                str(costs.dispatches),
                str(costs.turns),
                *(str(costs.tokens[token_type]) for token_type in TOKEN_TYPES),
                f"{costs.weighted_tokens:.0f}",
                f"{share:.1f}%",
                f"{statistics.median(costs.active_minutes):.1f}",
                f"{sum(costs.active_minutes):.1f}",
            ]
        )
    widths = [max(len(row[column]) for row in rows) for column in range(len(ROLE_TABLE_COLUMNS))]
    return ["  ".join(cell.ljust(width) for cell, width in zip(row, widths, strict=True)).rstrip() for row in rows]


def main(argv: list[str] | None = None) -> int:
    """Prints the per-role cost table of the transcripts in the given folders.

    Args:
        argv: Command-line arguments without the program name; ``sys.argv[1:]`` when None.

    Returns:
        0. argparse exits with 2 on a usage error.
    """
    parser = argparse.ArgumentParser(description="konundrm-eng session costs per role")
    parser.add_argument("folders", nargs="+", type=Path, help="project transcript folders of one run")
    arguments = parser.parse_args(argv)
    lines = format_role_table(collect_role_costs(arguments.folders))
    sys.stdout.write("\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
