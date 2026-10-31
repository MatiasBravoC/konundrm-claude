"""Reads a feature's tasks.md: its header and each task's fields, partition, wave and review rounds.

writing-plans creates the file from its template and develop-feature checks the boxes and adds a
``Rounds:`` line per task. The header's ``- **Base commit:** `<sha>``` line names the commit the
feature branch started from; only a hex SHA, full or short, is read from it, since callers hand
it to git as a revision. A task's covers come from the ``· Covers:`` field that ends its line, so
a ``Covers:`` quoted in its title is not mistaken for it. The header's ``- **Parallel:** yes | no``
line says whether partitions run in parallel: only a whole value of ``yes`` does, so a missing or
unfilled line means serial.
Each slice ends with a ``### Partitions`` table (``| Wave | Partition | Tasks | Depends on |``)
that assigns its tasks to partitions and each partition to a numbered wave. The Wave and Partition
cells are read bold or not; a Tasks cell lists IDs and inclusive ranges (``T1-T3``, ``T4..T6``,
``T7 to T9``; en and em dashes too), bold or not. IDs match by number, so ``T01`` lists task
``T1``; a range is never expanded, only the document's own tasks are checked against its bounds.
A number longer than ``MAX_TASK_NUMBER_DIGITS`` significant digits is not a usable task number: a
cell ID, range bound or task with one lists or belongs to nothing, and a Wave cell that is not a
number that short gives no wave, so no cell text can make the reader raise. The impact report and
the session doctor both read it, so the format has this one parser. HTML comments are ignored:
the template carries a commented example.

Sections:
    Task, TasksDocument — what a tasks.md says.
    read_tasks()        — parses one file.
    next_tasks()        — the task, or the task per partition, a feature resumes with.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Set
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

STATUS = re.compile(r"(?mi)^-\s*\*\*Status:\*\*\s*(?P<status>[A-Za-z]+)")
PARALLEL = re.compile(r"(?mi)^-\s*\*\*Parallel:\*\*[ \t]*(?P<parallel>[^\r\n]*)")
TASK = re.compile(r"(?m)^- \[(?P<box>[ xX])\] \*\*(?P<id>T\d+)\*\*[ \t]*(?P<rest>[^\n]*)")
BASE_COMMIT = re.compile(r"(?mi)^-\s*\*\*Base commit:\*\*[ \t]*`(?P<sha>[0-9a-f]{4,64})`")
COVERS = re.compile(r" · Covers:[ \t]*(?P<covers>[^·]*?)\s*$")
RISK = re.compile(r"\bRisk:\s*(?P<risk>low|medium|high)\b", re.IGNORECASE)
SLICE_HEADING = re.compile(r"(?m)^#{2,3}\s+Slice\s+(?P<slice>S\d+)\b")
ROUNDS = re.compile(r"Rounds:\s*spec\s*(\d+)\D+code\s*(\d+)\D+escalations\s*(\d+)", re.IGNORECASE)
HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
PARTITION_TABLE = re.compile(
    r"(?mi)^\|\s*Wave\s*\|\s*Partition\s*\|\s*Tasks\s*\|\s*Depends on\s*\|[ \t]*\n"
    r"(?P<rows>(?:\|[^\n]*(?:\n|$))*)"
)
SEPARATOR_CELL = re.compile(r"^:?-+:?$")
TASK_RANGE = re.compile(r"\bT(?P<first>\d+)\s*(?:\u2013|\u2014|-|\.\.|to)\s*T(?P<last>\d+)\b")
TASK_ID = re.compile(r"\bT\d+\b")
WAVE_NUMBER = re.compile(r"[0-9]+")
MAX_TASK_NUMBER_DIGITS = 18
"""Significant digits a task number may have: far above any real plan, far below CPython's limit."""


@dataclass(frozen=True)
class Task:
    """One task of a feature.

    Attributes:
        id: Task ID such as ``T3``.
        title: The task's description, without its type, risk and coverage fields.
        done: Whether its box is checked.
        risk: ``low``, ``medium`` or ``high``, or None when the line has no Risk field.
        slice: The pull-request slice it belongs to (``S1``), or None.
        rounds: Spec review rounds, code review rounds and escalations, once recorded.
        partition: The partition (``P1``) of the first ``### Partitions`` row that lists it, or
            None when no row lists it.
        wave: The Wave of that same first row, or None when no row lists it or its Wave cell is
            not a number of at most ``MAX_TASK_NUMBER_DIGITS`` significant digits.
        covers: The requirement IDs (``R1.2``) of the ``· Covers:`` field that ends the task's
            line, in order; empty when that field is ``—`` or the line does not end with one.
    """

    id: str
    title: str
    done: bool
    risk: str | None
    slice: str | None
    rounds: tuple[int, int, int] | None
    partition: str | None = None
    wave: int | None = None
    covers: tuple[str, ...] = ()


class _Placement(NamedTuple):
    """Where the first Partitions row listing a task puts it."""

    partition: str
    wave: int | None


@dataclass(frozen=True)
class TasksDocument:
    """A parsed tasks.md.

    Attributes:
        status: ``Draft``, ``Approved`` or ``Done`` as written, or an empty string when missing.
        tasks: The tasks in file order.
        parallel: Whether the rest of the header's ``Parallel:`` line, comments removed, is
            exactly ``yes`` (in any case, surrounding spaces allowed), so the partitions run in
            parallel; False when the line says anything else, is unfilled or is missing.
        base_commit: The hex SHA, full or short, between backticks in the header's
            ``Base commit:`` line, or None when the line is missing or holds anything else, such
            as the template's placeholder.
    """

    status: str
    tasks: tuple[Task, ...]
    parallel: bool = False
    base_commit: str | None = None


def _rounds(block: str) -> tuple[int, int, int] | None:
    match = ROUNDS.search(block)
    if match is None:
        return None
    spec, code, escalations = (int(value) for value in match.groups())
    return spec, code, escalations


def _covers(rest: str) -> tuple[str, ...]:
    """The requirement IDs of the Covers field that ends a task line, or () when it is ``—``."""
    match = COVERS.search(rest)
    if match is None:
        return ()
    ids = (item.strip() for item in match.group("covers").split(","))
    return tuple(item for item in ids if item and item != "—")


def _task(match: re.Match[str], block: str, slice_: str | None, placements: dict[str, _Placement]) -> Task:
    rest = match.group("rest")
    risk = RISK.search(rest)
    placement = placements.get(match.group("id"))
    return Task(
        id=match.group("id"),
        title=rest.split(" · ", 1)[0].strip(),
        done=match.group("box").lower() == "x",
        risk=risk.group("risk").lower() if risk else None,
        slice=slice_,
        rounds=_rounds(block),
        partition=placement.partition if placement else None,
        wave=placement.wave if placement else None,
        covers=_covers(rest),
    )


def _placements(text: str, task_ids: list[str]) -> dict[str, _Placement]:
    """Maps each of the document's task IDs to the partition and wave of the first row listing it.

    Only the given IDs are tested against each row, so a range as wide as ``T1-T10000000000``
    costs one comparison per task instead of one per number it spans.
    """
    placements: dict[str, _Placement] = {}
    for table in PARTITION_TABLE.finditer(text):
        for row in table.group("rows").splitlines():
            cells = [cell.strip() for cell in row.strip().strip("|").split("|")]
            if len(cells) < 3 or SEPARATOR_CELL.match(cells[0]):
                continue
            placement = _Placement(partition=_unbold(cells[1]), wave=_wave_number(_unbold(cells[0])))
            listed = _TasksCell.parse(_unbold(cells[2]))
            for task_id in task_ids:
                if task_id not in placements and listed.lists(task_id):
                    placements[task_id] = placement
    return placements


def _wave_number(cell: str) -> int | None:
    """The wave an unbolded Wave cell such as ``2`` names, or None when it is not a short number."""
    if WAVE_NUMBER.fullmatch(cell) is None:
        return None
    return _task_number(cell)


def _unbold(cell: str) -> str:
    """A table cell without its Markdown bold markers."""
    return cell.replace("**", "").strip()


@dataclass(frozen=True)
class _TasksCell:
    """The tasks a Partitions row's Tasks cell lists: explicit IDs and inclusive ranges.

    Both are kept as task numbers, so zero padding never matters: ``T01`` and ``T1`` name the same
    task, in the cell and in the task list alike. Ranges stay as their bounds rather than being
    expanded, so their width costs nothing. A range whose end comes before its start (``T5-T3``)
    lists no task. An ID or range bound with more than ``MAX_TASK_NUMBER_DIGITS`` significant digits
    is not a usable task number, so it lists no task, and neither does a range with such a bound.
    Anything that is not a task ID, such as an empty cell or ``—``, is ignored.
    """

    numbers: frozenset[int]
    ranges: tuple[tuple[int, int], ...]

    @classmethod
    def parse(cls, cell: str) -> _TasksCell:
        bounds = (
            (_task_number(found.group("first")), _task_number(found.group("last")))
            for found in TASK_RANGE.finditer(cell)
        )
        ranges = tuple((first, last) for first, last in bounds if first is not None and last is not None)
        explicit = (_task_number(task_id[1:]) for task_id in TASK_ID.findall(TASK_RANGE.sub(" ", cell)))
        return cls(numbers=frozenset(number for number in explicit if number is not None), ranges=ranges)

    def lists(self, task_id: str) -> bool:
        """Whether the cell names the task's number or one of its ranges covers it."""
        number = _task_number(task_id[1:])
        if number is None:
            return False
        return number in self.numbers or any(first <= number <= last for first, last in self.ranges)


def _task_number(digits: str) -> int | None:
    """The number the digits of a task ID such as ``T03`` stand for, without their zero padding.

    Returns None when the digits, zero padding removed, are more than ``MAX_TASK_NUMBER_DIGITS``
    long: that is not a usable task number, and ``int()`` could reject it outright.
    """
    significant = digits.lstrip("0") or "0"
    if len(significant) > MAX_TASK_NUMBER_DIGITS:
        return None
    return int(significant)


def _slice_at(position: int, headings: list[re.Match[str]]) -> str | None:
    """The slice whose heading comes last before a position in the text."""
    current = None
    for heading in headings:
        if heading.start() > position:
            break
        current = heading.group("slice")
    return current


def next_tasks(document: TasksDocument, built: Set[str]) -> tuple[Task, ...]:
    """Picks the tasks a feature resumes with: its next task, or each partition's while they run in parallel.

    Args:
        document: The feature's parsed tasks.md.
        built: IDs of the tasks already built, by whatever evidence the caller counts (checked
            boxes, or task commits after the plan's base).

    Returns:
        The first unbuilt task of each partition of the wave in progress, in numeric partition
        order (``P2`` before ``P10``), when the plan runs partitions in parallel, at least two
        partitions of that wave have unbuilt tasks and every unbuilt task of its slice has a
        partition. The wave in progress is the earliest wave of the first unbuilt task's slice
        that still has unbuilt tasks; when an unbuilt task of that slice has no numeric wave, the
        slice's waves are not filtered at all, since the order of its partitions is then unknown.
        Otherwise just the first unbuilt task in plan order, or an empty tuple when every task is
        built.
    """
    pending = [task for task in document.tasks if task.id not in built]
    if not pending:
        return ()
    if document.parallel:
        by_partition = _next_task_by_partition(pending)
        if by_partition is not None:
            return by_partition
    return (pending[0],)


def _next_task_by_partition(pending: list[Task]) -> tuple[Task, ...] | None:
    """The first pending task of each partition of the wave in progress, in partition order.

    Returns None when fewer than two partitions of that wave remain or a pending task of the
    first pending task's slice has no partition, since a single next task then describes the
    resume point fully.
    """
    current_slice = [task for task in pending if task.slice == pending[0].slice]
    if any(task.partition is None for task in current_slice):
        return None
    next_by_partition: dict[str, Task] = {}
    for task in _current_wave(current_slice):
        next_by_partition.setdefault(str(task.partition), task)
    if len(next_by_partition) < 2:
        return None
    return tuple(task for _, task in sorted(next_by_partition.items(), key=lambda item: _partition_number(item[0])))


def _current_wave(slice_pending: list[Task]) -> list[Task]:
    """Keeps the pending tasks of the slice's earliest wave, or all of them when a wave is unknown."""
    waves = [task.wave for task in slice_pending]
    if None in waves:
        return slice_pending
    earliest = min(wave for wave in waves if wave is not None)
    return [task for task in slice_pending if task.wave == earliest]


def _partition_number(partition: str) -> tuple[int, str]:
    """Sorts ``P2`` before ``P10``; IDs without a number sort after numbered ones, by name."""
    digits = partition.lstrip("Pp")
    return (int(digits), partition) if digits.isdigit() else (sys.maxsize, partition)


def read_tasks(path: Path) -> TasksDocument:
    """Parses a tasks.md file.

    Args:
        path: The file to read.

    Returns:
        Its header fields and tasks; an empty document when the file cannot be read.
    """
    try:
        text = HTML_COMMENT.sub("", path.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return TasksDocument(status="", tasks=())
    status = STATUS.search(text)
    headings = list(SLICE_HEADING.finditer(text))
    matches = list(TASK.finditer(text))
    placements = _placements(text, [match.group("id") for match in matches])
    ends = [*(match.start() for match in matches[1:]), len(text)]
    tasks = tuple(
        _task(match, text[match.end() : end], _slice_at(match.start(), headings), placements)
        for match, end in zip(matches, ends, strict=True)
    )
    parallel = PARALLEL.search(text)
    base_commit = BASE_COMMIT.search(text)
    return TasksDocument(
        status=status.group("status") if status else "",
        tasks=tasks,
        parallel=parallel is not None and parallel.group("parallel").strip().lower() == "yes",
        base_commit=base_commit.group("sha") if base_commit else None,
    )
