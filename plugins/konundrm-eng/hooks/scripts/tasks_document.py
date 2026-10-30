"""Reads a feature's tasks.md: its status and each task's fields, partition and review rounds.

writing-plans creates the file from its template and develop-feature checks the boxes and adds a
``Rounds:`` line per task. The header's ``- **Parallel:** yes | no`` line says whether partitions
run in parallel (no line means serial). Each slice ends with a ``### Partitions`` table
(``| Wave | Partition | Tasks | Depends on |``) that assigns its tasks to partitions; a Tasks cell
lists IDs and ranges (``T1-T3``, ``T4..T6``, ``T7 to T9``; en and em dashes too), bold or not. The impact
report and the session doctor both read it, so the format has this one parser. HTML comments are
ignored: the template carries a commented example.

Sections:
    Task, TasksDocument — what a tasks.md says.
    read_tasks()        — parses one file.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

STATUS = re.compile(r"(?mi)^-\s*\*\*Status:\*\*\s*(?P<status>[A-Za-z]+)")
PARALLEL = re.compile(r"(?mi)^-\s*\*\*Parallel:\*\*\s*(?P<parallel>[A-Za-z]+)")
TASK = re.compile(r"(?m)^- \[(?P<box>[ xX])\] \*\*(?P<id>T\d+)\*\*[ \t]*(?P<rest>[^\n]*)")
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
    """

    id: str
    title: str
    done: bool
    risk: str | None
    slice: str | None
    rounds: tuple[int, int, int] | None
    partition: str | None = None


@dataclass(frozen=True)
class TasksDocument:
    """A parsed tasks.md.

    Attributes:
        status: ``Draft``, ``Approved`` or ``Done`` as written, or an empty string when missing.
        tasks: The tasks in file order.
        parallel: Whether the header's ``Parallel:`` line says ``yes`` (in any case), so the
            partitions run in parallel; False when it says anything else or is missing.
    """

    status: str
    tasks: tuple[Task, ...]
    parallel: bool = False


def _rounds(block: str) -> tuple[int, int, int] | None:
    match = ROUNDS.search(block)
    if match is None:
        return None
    spec, code, escalations = (int(value) for value in match.groups())
    return spec, code, escalations


def _task(match: re.Match[str], block: str, slice_: str | None, partitions: dict[str, str]) -> Task:
    rest = match.group("rest")
    risk = RISK.search(rest)
    task_id = match.group("id")
    return Task(
        id=task_id,
        title=rest.split(" · ", 1)[0].strip(),
        done=match.group("box").lower() == "x",
        risk=risk.group("risk").lower() if risk else None,
        slice=slice_,
        rounds=_rounds(block),
        partition=partitions.get(task_id),
    )


def _partitions(text: str) -> dict[str, str]:
    """Maps each task ID to the partition of the first Partitions row that lists it."""
    partitions: dict[str, str] = {}
    for table in PARTITION_TABLE.finditer(text):
        for row in table.group("rows").splitlines():
            cells = [cell.strip() for cell in row.strip().strip("|").split("|")]
            if len(cells) < 3 or SEPARATOR_CELL.match(cells[0]):
                continue
            partition = _unbold(cells[1])
            for task_id in _task_ids(_unbold(cells[2])):
                partitions.setdefault(task_id, partition)
    return partitions


def _unbold(cell: str) -> str:
    """A table cell without its Markdown bold markers."""
    return cell.replace("**", "").strip()


def _task_ids(cell: str) -> list[str]:
    """The task IDs in a Tasks cell, with ranges such as ``T1-T3`` expanded.

    A range whose end comes before its start (``T5-T3``) lists no task. Anything that is not a
    task ID, such as an empty cell or ``—``, is ignored.
    """
    ranged = [
        f"T{number}"
        for found in TASK_RANGE.finditer(cell)
        for number in range(int(found.group("first")), int(found.group("last")) + 1)
    ]
    return ranged + TASK_ID.findall(TASK_RANGE.sub(" ", cell))


def _slice_at(position: int, headings: list[re.Match[str]]) -> str | None:
    """The slice whose heading comes last before a position in the text."""
    current = None
    for heading in headings:
        if heading.start() > position:
            break
        current = heading.group("slice")
    return current


def read_tasks(path: Path) -> TasksDocument:
    """Parses a tasks.md file.

    Args:
        path: The file to read.

    Returns:
        Its status and tasks; an empty document when the file cannot be read.
    """
    try:
        text = HTML_COMMENT.sub("", path.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return TasksDocument(status="", tasks=())
    status = STATUS.search(text)
    headings = list(SLICE_HEADING.finditer(text))
    partitions = _partitions(text)
    matches = list(TASK.finditer(text))
    ends = [*(match.start() for match in matches[1:]), len(text)]
    tasks = tuple(
        _task(match, text[match.end() : end], _slice_at(match.start(), headings), partitions)
        for match, end in zip(matches, ends, strict=True)
    )
    parallel = PARALLEL.search(text)
    return TasksDocument(
        status=status.group("status") if status else "",
        tasks=tasks,
        parallel=parallel is not None and parallel.group("parallel").lower() == "yes",
    )
