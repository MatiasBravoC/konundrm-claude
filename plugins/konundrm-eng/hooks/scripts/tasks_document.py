"""Reads a feature's tasks.md: its status, and each task's ID, title, box, risk and review rounds.

writing-plans creates the file from its template and develop-feature checks the boxes and adds a
``Rounds:`` line per task. The impact report and the session doctor both read it, so the format
has this one parser. HTML comments are ignored: the template carries a commented example.

Sections:
    Task, TasksDocument — what a tasks.md says.
    read_tasks()        — parses one file.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

STATUS = re.compile(r"(?mi)^-\s*\*\*Status:\*\*\s*(?P<status>[A-Za-z]+)")
TASK = re.compile(r"(?m)^- \[(?P<box>[ xX])\] \*\*(?P<id>T\d+)\*\*[ \t]*(?P<rest>[^\n]*)")
RISK = re.compile(r"\bRisk:\s*(?P<risk>low|medium|high)\b", re.IGNORECASE)
SLICE_HEADING = re.compile(r"(?m)^#{2,3}\s+Slice\s+(?P<slice>S\d+)\b")
ROUNDS = re.compile(r"Rounds:\s*spec\s*(\d+)\D+code\s*(\d+)\D+escalations\s*(\d+)", re.IGNORECASE)
HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)


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
    """

    id: str
    title: str
    done: bool
    risk: str | None
    slice: str | None
    rounds: tuple[int, int, int] | None


@dataclass(frozen=True)
class TasksDocument:
    """A parsed tasks.md.

    Attributes:
        status: ``Draft``, ``Approved`` or ``Done`` as written, or an empty string when missing.
        tasks: The tasks in file order.
    """

    status: str
    tasks: tuple[Task, ...]


def _rounds(block: str) -> tuple[int, int, int] | None:
    match = ROUNDS.search(block)
    if match is None:
        return None
    spec, code, escalations = (int(value) for value in match.groups())
    return spec, code, escalations


def _task(match: re.Match[str], block: str, slice_: str | None) -> Task:
    rest = match.group("rest")
    risk = RISK.search(rest)
    return Task(
        id=match.group("id"),
        title=rest.split(" · ", 1)[0].strip(),
        done=match.group("box").lower() == "x",
        risk=risk.group("risk").lower() if risk else None,
        slice=slice_,
        rounds=_rounds(block),
    )


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
    matches = list(TASK.finditer(text))
    ends = [*(match.start() for match in matches[1:]), len(text)]
    tasks = tuple(
        _task(match, text[match.end() : end], _slice_at(match.start(), headings))
        for match, end in zip(matches, ends, strict=True)
    )
    return TasksDocument(status=status.group("status") if status else "", tasks=tasks)
