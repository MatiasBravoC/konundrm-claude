"""Measures what a run cost, per role, from its Claude Code session transcripts.

A person runs it as ``sh "${CLAUDE_PLUGIN_ROOT}/hooks/run.sh" session_costs.py <folder>...``, where
each folder holds a project's transcripts (``~/.claude/projects/<project>/``). Every session
transcript ``<folder>/<session-id>.jsonl`` belongs to the role ``orchestrator``; every subagent
transcript ``<folder>/<session-id>/subagents/agent-<id>.jsonl`` belongs to the ``agentType`` of its
``agent-<id>.meta.json``. The per-role table it prints has, for each role: dispatches (transcripts),
turns, input, cache-write, cache-read and output tokens, weighted tokens, the role's share of all
weighted tokens, its active minutes (median and total over its transcripts), its check runs with
their total minutes, its test runs and its messages that dispatched two or more subagents at once.
After the table comes the session transcript with the most turns: its turns and the context of
its turns (first, median, 90th percentile by nearest rank, maximum).
``--check-pattern REGEX`` says what a check run is; by default it is the check command that
``quality_check`` finds from the current folder.

It prints nothing read from a transcript except the agent type and numbers. When a transcript cannot
be read, it writes one line to stderr naming the error's type and the file, never the error's
message, and exits with 1.

Sections:
    TOKEN_WEIGHTS          — input-equivalent weight of each token type.
    TEST_RUN                — what a test run looks like.
    TranscriptCosts         — what one transcript cost.
    default_check_pattern() — what a run of the project's check looks like.
    read_transcript()       — measures one transcript, its tool calls counted by a private tally.
    TranscriptReadError    — a transcript, or its subagent's meta.json, could not be read.
    find_transcripts()     — lists the transcripts of a folder with their role.
    RoleCosts              — what every transcript of one role cost together.
    RunCosts               — what a run cost per role, and its busiest orchestrator session.
    collect_run_costs()    — measures every transcript of the given folders as one run.
    format_role_table()    — renders the per-role table.
    format_busiest_orchestrator() — renders the busiest orchestrator's turns and context per turn.
    main()                 — CLI.
"""

from __future__ import annotations

import argparse
import itertools
import json
import re
import statistics
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from quality_check import find_check_command
from shell_commands import iter_commands

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

CONTEXT_TOKEN_TYPES = ("input", "cache_write", "cache_read")
"""Token types that make up the context a turn was sent with; its output is not part of it."""

TOKEN_WEIGHTS = {"input": 1.0, "cache_write": 1.25, "cache_read": 0.1, "output": 5.0}
"""Input-equivalent weight of each token type, the ratio of their prices."""

MAX_ACTIVE_GAP_SECONDS = 5 * 60
"""Longest gap between two transcript lines that still counts as active time; longer is a pause."""


JsonObject = dict[str, Any]
"""A transcript line, or a block of one, as json.loads returns it."""

SHELL_TOOLS = frozenset({"Bash", "PowerShell"})
"""Tools whose ``command`` input is a shell command line."""

DISPATCH_TOOL = "Agent"
"""The tool that dispatches a subagent."""

TEST_RUN = re.compile(r"^(?:python3? -m (?:unittest|pytest)|pytest|npm (?:run )?test)(?:\s|$)")
"""A simple command (program plus arguments) that runs tests."""


@dataclass
class TranscriptCosts:
    """What one transcript cost.

    Attributes:
        turns: Distinct API messages the model sent.
        tokens: Tokens per type (keys of TOKEN_TYPES), each message's usage counted once.
        active_minutes: Sum of the gaps between consecutive lines, pauses left out.
        check_runs: Shell calls that ran the check.
        check_minutes: Time from each check run's call to its result, summed.
        test_runs: Simple commands, other than the check, that ran tests.
        parallel_dispatch_messages: Messages that dispatched two or more subagents.
        turn_contexts: Context of each turn (its input, cache-write and cache-read tokens), in the
            order the turns are first written.
    """

    turns: int = 0
    tokens: dict[str, int] = field(default_factory=lambda: dict.fromkeys(TOKEN_TYPES, 0))
    active_minutes: float = 0.0
    check_runs: int = 0
    check_minutes: float = 0.0
    test_runs: int = 0
    parallel_dispatch_messages: int = 0
    turn_contexts: list[int] = field(default_factory=list)


def _parse_timestamp(text: str) -> datetime:
    # Python 3.10's fromisoformat does not accept the trailing "Z" Claude Code writes.
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def _active_minutes(moments: list[datetime]) -> float:
    gaps = (later - earlier for earlier, later in itertools.pairwise(moments))
    seconds = sum(gap.total_seconds() for gap in gaps if gap.total_seconds() <= MAX_ACTIVE_GAP_SECONDS)
    return seconds / 60


def _simple_command_texts(command_line: str) -> list[str]:
    """Returns each simple command of a command line as its program and arguments, space-joined."""
    return [" ".join((command.program, *command.arguments)) for command in iter_commands(command_line)]


def default_check_pattern(root: Path) -> re.Pattern[str] | None:
    """Returns the pattern of the project's check command, as quality_check finds it from `root`.

    The pattern matches a simple command that is the check's first simple command, with any further
    arguments, so a grep or echo that only mentions the check's text does not match.

    Args:
        root: Directory the project's check is looked up from.

    Returns:
        The pattern, or None when the project has no check command.
    """
    check = find_check_command(root)
    texts = _simple_command_texts(check) if check else []
    return re.compile(rf"^{re.escape(texts[0])}(?:\s|$)") if texts else None


def _content_blocks(entry: JsonObject, block_type: str) -> list[JsonObject]:
    content = entry.get("message", {}).get("content", [])
    if not isinstance(content, list):  # A user line's content can be plain text.
        return []
    return [block for block in content if isinstance(block, dict) and block.get("type") == block_type]


@dataclass
class _ToolCallTally:
    """Counts one transcript's tool calls into its costs while the transcript is read in order.

    Attributes:
        costs: The transcript's costs, whose tool-call fields this fills.
        check_pattern: What a check run looks like; None counts none.
        check_started_at: When each check run still waiting for its result started, by tool_use id.
        dispatches_by_message_id: Agent calls per assistant message.
    """

    costs: TranscriptCosts
    check_pattern: re.Pattern[str] | None
    check_started_at: dict[str, datetime | None] = field(default_factory=dict)
    dispatches_by_message_id: dict[str | None, int] = field(default_factory=dict)

    def add_tool_uses(self, entry: JsonObject, moment: datetime | None) -> None:
        """Counts the Agent and shell calls of one assistant line written at `moment`."""
        message_id = entry.get("message", {}).get("id")
        for block in _content_blocks(entry, "tool_use"):
            if block.get("name") == DISPATCH_TOOL:
                self.dispatches_by_message_id[message_id] = self.dispatches_by_message_id.get(message_id, 0) + 1
            elif block.get("name") in SHELL_TOOLS:
                self._add_shell_call(block, moment)

    def _add_shell_call(self, block: JsonObject, moment: datetime | None) -> None:
        is_check_run = False
        for text in _simple_command_texts(str(block.get("input", {}).get("command", ""))):
            if self.check_pattern is not None and self.check_pattern.search(text):
                is_check_run = True
            elif TEST_RUN.match(text):
                self.costs.test_runs += 1
        if is_check_run:
            self.costs.check_runs += 1
            self.check_started_at[block.get("id", "")] = moment

    def add_tool_results(self, entry: JsonObject, moment: datetime | None) -> None:
        """Adds the time of every check run whose result one user line, written at `moment`, carries."""
        for block in _content_blocks(entry, "tool_result"):
            started_at = self.check_started_at.pop(block.get("tool_use_id", ""), None)
            if started_at is not None and moment is not None:
                self.costs.check_minutes += (moment - started_at).total_seconds() / 60

    def finish(self) -> None:
        """Counts the messages with two or more dispatches, once every line was read."""
        self.costs.parallel_dispatch_messages = sum(1 for count in self.dispatches_by_message_id.values() if count >= 2)


def read_transcript(path: Path, check_pattern: re.Pattern[str] | None = None) -> TranscriptCosts:
    """Measures one transcript.

    Claude Code writes one API message as one line per content block, each repeating the message's
    id. A message counts as one turn and its usage once, taken from its last line: earlier lines
    can carry a partial ``output_tokens`` written while the message was still streaming.

    A Bash or PowerShell call is a check run when one of its simple commands (as
    ``shell_commands.iter_commands`` splits it, program plus arguments) matches `check_pattern`;
    its time runs from the call's line to the line that carries its result. Every other simple
    command that runs ``python -m unittest``, ``python -m pytest``, ``pytest``, ``npm test`` or
    ``npm run test`` is a test run.

    Args:
        path: A JSON Lines transcript.
        check_pattern: Searched in each simple command's text; None counts no check runs.

    Returns:
        Its turns, tokens per type, active minutes, check runs and their minutes, test runs,
        parallel-dispatch messages and each turn's context. A transcript without assistant lines
        has 0 turns and 0 tokens.

    Raises:
        OSError: If the file cannot be read.
        ValueError: If a line is not JSON or a timestamp is not ISO 8601.
    """
    costs = TranscriptCosts()
    tool_calls = _ToolCallTally(costs, check_pattern)
    usage_by_message_id: dict[str | None, dict[str, int]] = {}
    moments: list[datetime] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        moment = _parse_timestamp(entry["timestamp"]) if "timestamp" in entry else None
        if moment is not None:
            moments.append(moment)
        if entry.get("type") == "user":
            tool_calls.add_tool_results(entry, moment)
        if entry.get("type") != "assistant":
            continue
        tool_calls.add_tool_uses(entry, moment)
        message = entry.get("message", {})
        # Each later line of a message overwrites the earlier ones, so its last line's usage wins.
        usage_by_message_id[message.get("id")] = message.get("usage", {})
    costs.turns = len(usage_by_message_id)
    # A dict keeps each message where its first line put it, so the turns stay in written order.
    for usage in usage_by_message_id.values():
        for token_type, usage_field in USAGE_FIELDS.items():
            costs.tokens[token_type] += usage.get(usage_field, 0)
        costs.turn_contexts.append(sum(usage.get(USAGE_FIELDS[token_type], 0) for token_type in CONTEXT_TOKEN_TYPES))
    costs.active_minutes = _active_minutes(sorted(moments))
    tool_calls.finish()
    return costs


class TranscriptReadError(Exception):
    """A transcript, or its subagent's meta.json, could not be read.

    Its message is only the file's path: the original error, whose message can repeat what the file
    holds (a timestamp, a line of JSON), stays in ``__cause__`` and is never printed.

    Attributes:
        path: The file that could not be read.
    """

    def __init__(self, path: Path) -> None:
        super().__init__(str(path))
        self.path = path


@contextmanager
def _reading(path: Path) -> Iterator[None]:
    """Turns any error raised inside the block into a TranscriptReadError for `path`."""
    try:
        yield
    # Every error, current or future, so that none can carry the file's content to the output.
    except Exception as error:
        raise TranscriptReadError(path) from error


def _subagent_role(transcript: Path) -> str:
    meta_path = transcript.with_suffix(".meta.json")
    with _reading(meta_path):
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

    Raises:
        TranscriptReadError: If a subagent's meta.json cannot be read, is not JSON or names no
            agentType.
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
        check_runs: Check runs over all of them.
        check_minutes: Minutes of those check runs.
        test_runs: Test runs over all of them.
        parallel_dispatch_messages: Messages with two or more dispatches over all of them.
    """

    dispatches: int = 0
    turns: int = 0
    tokens: dict[str, int] = field(default_factory=lambda: dict.fromkeys(TOKEN_TYPES, 0))
    active_minutes: list[float] = field(default_factory=list)
    check_runs: int = 0
    check_minutes: float = 0.0
    test_runs: int = 0
    parallel_dispatch_messages: int = 0

    def add(self, transcript: TranscriptCosts) -> None:
        """Adds one transcript of the role as one more dispatch."""
        self.dispatches += 1
        self.turns += transcript.turns
        for token_type in TOKEN_TYPES:
            self.tokens[token_type] += transcript.tokens[token_type]
        self.active_minutes.append(transcript.active_minutes)
        self.check_runs += transcript.check_runs
        self.check_minutes += transcript.check_minutes
        self.test_runs += transcript.test_runs
        self.parallel_dispatch_messages += transcript.parallel_dispatch_messages

    @property
    def weighted_tokens(self) -> float:
        """Input-equivalent tokens: each token type times its TOKEN_WEIGHTS weight, summed."""
        return sum(self.tokens[token_type] * TOKEN_WEIGHTS[token_type] for token_type in TOKEN_TYPES)


@dataclass
class RunCosts:
    """What one run cost: per role, and the orchestrator session that took the most turns.

    Attributes:
        costs_by_role: Each role's costs, keyed by role, in the order roles were first found.
        busiest_orchestrator: The session transcript with the most turns (the first found on a
            tie), or None when no session has a turn. Subagent transcripts are never it.
    """

    costs_by_role: dict[str, RoleCosts] = field(default_factory=dict)
    busiest_orchestrator: TranscriptCosts | None = None

    def add(self, role: str, transcript: TranscriptCosts) -> None:
        """Adds one transcript of `role` to the run."""
        self.costs_by_role.setdefault(role, RoleCosts()).add(transcript)
        busiest_turns = self.busiest_orchestrator.turns if self.busiest_orchestrator else 0
        if role == ORCHESTRATOR_ROLE and transcript.turns > busiest_turns:
            self.busiest_orchestrator = transcript


def collect_run_costs(folders: list[Path], check_pattern: re.Pattern[str] | None = None) -> RunCosts:
    """Measures every transcript of the given folders as one run.

    Args:
        folders: Project transcript folders, read as one run.
        check_pattern: What a check run looks like, as read_transcript takes it.

    Returns:
        The run's costs per role and its busiest orchestrator session.

    Raises:
        TranscriptReadError: If a transcript or a subagent's meta.json cannot be read or measured,
            whatever the error; the original error is its ``__cause__``.
    """
    run = RunCosts()
    for folder in folders:
        for role, transcript in find_transcripts(folder):
            with _reading(transcript):
                costs = read_transcript(transcript, check_pattern)
            run.add(role, costs)
    return run


ROLE_TABLE_COLUMNS = (
    "role",
    "dispatches",
    "turns",
    *TOKEN_TYPES,
    "weighted",
    "share",
    "active_min_median",
    "active_min_total",
    "check_runs",
    "check_min_total",
    "test_runs",
    "parallel_dispatch_msgs",
)
"""Header of the per-role table."""


def format_role_table(costs_by_role: dict[str, RoleCosts]) -> list[str]:
    """Renders the per-role table, one line per role under a header of column names.

    Args:
        costs_by_role: Each role's costs, as RunCosts.costs_by_role holds them.

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
                str(costs.check_runs),
                f"{costs.check_minutes:.1f}",
                str(costs.test_runs),
                str(costs.parallel_dispatch_messages),
            ]
        )
    return _align_columns(rows)


BUSIEST_ORCHESTRATOR_TITLE = "busiest orchestrator session"
"""Line that introduces the busiest orchestrator's block."""

BUSIEST_ORCHESTRATOR_COLUMNS = ("turns", "context_first", "context_median", "context_p90", "context_max")
"""Header of the busiest orchestrator's block."""


def _nearest_rank_percentile(values: list[int], percent: int) -> int:
    """Returns the sorted value at rank ceil(percent/100 · n), 1-based; `values` must not be empty."""
    # Integer ceiling division: 0.9 * n in floats can land just above an integer and skip a rank.
    rank = -(-percent * len(values) // 100)
    return sorted(values)[rank - 1]


def _format_count(value: float) -> str:
    """Writes a token count without decimals when it is whole, as a median of two counts may not be."""
    return str(int(value)) if value == int(value) else f"{value:.1f}"


def format_busiest_orchestrator(busiest: TranscriptCosts | None) -> list[str]:
    """Renders the turns and per-turn context of the orchestrator session with the most turns.

    Args:
        busiest: That session's costs, as RunCosts.busiest_orchestrator holds them.

    Returns:
        A title line, a header of column names and one line of values: its turns, and the context
        of its first written turn, the median, the 90th percentile (nearest rank, always the
        context of a real turn) and the maximum. No lines when `busiest` is None.
    """
    if busiest is None:
        return []
    contexts = busiest.turn_contexts
    values = [
        str(busiest.turns),
        str(contexts[0]),
        _format_count(statistics.median(contexts)),
        str(_nearest_rank_percentile(contexts, 90)),
        str(max(contexts)),
    ]
    return ["", BUSIEST_ORCHESTRATOR_TITLE, *_align_columns([list(BUSIEST_ORCHESTRATOR_COLUMNS), values])]


def _align_columns(rows: list[list[str]]) -> list[str]:
    """Joins each row's cells, every column padded to its widest cell and separated by two spaces."""
    widths = [max(len(row[column]) for row in rows) for column in range(len(rows[0]))]
    return ["  ".join(cell.ljust(width) for cell, width in zip(row, widths, strict=True)).rstrip() for row in rows]


def _compile_pattern(text: str) -> re.Pattern[str]:
    try:
        return re.compile(text)
    except re.error as error:
        # argparse turns only this error type into a usage error; it does not print the pattern.
        raise argparse.ArgumentTypeError(f"not a valid regular expression: {error.msg}") from error


def main(argv: list[str] | None = None) -> int:
    """Prints the per-role cost table of the given folders' transcripts and their busiest orchestrator.

    Args:
        argv: Command-line arguments without the program name; ``sys.argv[1:]`` when None.

    Returns:
        0, or 1 when a transcript cannot be read: then stderr gets one line with the error's type
        and the file's path, never the error's message nor a traceback, and stdout gets nothing.
        argparse exits with 2 on a usage error.
    """
    parser = argparse.ArgumentParser(description="konundrm-eng session costs per role")
    parser.add_argument("folders", nargs="+", type=Path, help="project transcript folders of one run")
    parser.add_argument(
        "--check-pattern",
        type=_compile_pattern,
        help="regex searched in each simple shell command; default: the current project's check command",
    )
    arguments = parser.parse_args(argv)
    check_pattern = arguments.check_pattern
    if check_pattern is None:
        check_pattern = default_check_pattern(Path.cwd())
    try:
        run = collect_run_costs(arguments.folders, check_pattern)
    except TranscriptReadError as error:
        sys.stderr.write(f"session_costs: cannot read {error.path}: {type(error.__cause__).__name__}\n")
        return 1
    lines = [*format_role_table(run.costs_by_role), *format_busiest_orchestrator(run.busiest_orchestrator)]
    sys.stdout.write("\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
