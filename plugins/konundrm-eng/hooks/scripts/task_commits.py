"""Finds each task's commit among the commits made after a feature's base commit.

develop-feature commits every task with a ``Task: T<n> · Covers: …`` line and, once its reviews
end, a ``Rounds: spec <n> · code <n> · escalations <n>`` line. Only commits in ``<base>..HEAD``
count, so a task with the same number in an earlier feature is never mistaken for this one's.
A line names a task only when it starts with ``Task: T`` followed by the whole number, so ``T10``
is not ``T1`` and a ``Task:`` quoted mid-line is ignored; numbers match without their zero
padding (``T01`` is ``T1``). When several commits in the range name the same task (a slice
summary repeats it, say), the oldest is the task's commit.

Sections:
    TASK_TRAILER       — the ``Task: T<n>`` line, shared with the impact report.
    GitError           — Git could not list the range.
    TaskCommit         — one task's commit and its review rounds.
    task_key()         — the unpadded ID a plan's task is looked up by.
    task_commits()     — every task's commit in ``<base>..HEAD``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from working_tree import run_git

TASK_TRAILER = re.compile(r"(?m)^Task: T0*(?P<number>\d+)(?= |$)")
_TASK_ID = re.compile(r"T0*(?P<number>\d+)")
ROUNDS_TRAILER = re.compile(r"(?m)^Rounds: spec (?P<spec>\d+) · code (?P<code>\d+) · escalations (?P<escalations>\d+)")


class GitError(Exception):
    """Git failed to list a commit range: not a repository, an unknown base, or no Git at all."""


@dataclass(frozen=True)
class TaskCommit:
    """The commit that delivered one task.

    Attributes:
        task_id: ``T<n>`` without zero padding (``T01`` in the message gives ``T1``).
        sha: Full SHA of the commit.
        rounds: Spec review rounds, code review rounds and escalations from the commit's own
            ``Rounds:`` line, or None when it has none.
    """

    task_id: str
    sha: str
    rounds: tuple[int, int, int] | None


def task_key(task_id: str) -> str:
    """Gives the key task_commits() files a task under, so a plan's ``T02`` finds a ``Task: T2`` commit.

    Args:
        task_id: A task ID as written in a plan or typed by a person, such as ``T02``.

    Returns:
        ``T<n>`` without zero padding (``"T2"``), or ``task_id`` unchanged when it is not ``T``
        followed by digits, so it matches no commit.
    """
    match = _TASK_ID.fullmatch(task_id)
    return f"T{int(match['number'])}" if match else task_id


def task_commits(root: Path, base: str) -> dict[str, TaskCommit]:
    """Lists the commit of every task committed after a base commit, with one ``git log`` call.

    Args:
        root: Directory inside the Git repository.
        base: Revision the feature started from, such as the plan's base commit SHA. It is
            always read as a revision, never as a Git option.

    Returns:
        Each task's oldest commit in ``<base>..HEAD``, keyed by its unpadded ID (``"T1"``).

    Raises:
        GitError: When Git cannot list the range, for instance because ``base`` does not resolve.
    """
    # -z ends each commit with NUL, which a commit message cannot hold; --reverse puts the oldest
    # first, so the first commit seen for a task is the one kept.
    output = run_git(["log", "-z", "--reverse", "--format=%H%n%B", "--end-of-options", f"{base}..HEAD"], root)
    if output is None:
        raise GitError(f"git log {base}..HEAD failed in {root}")
    found: dict[str, TaskCommit] = {}
    for record in output.decode("utf-8", errors="replace").split("\0"):
        sha, _, message = record.partition("\n")
        task_line = TASK_TRAILER.search(message)
        if task_line is None:
            continue
        task_id = task_key(f"T{task_line['number']}")
        if task_id not in found:
            found[task_id] = TaskCommit(task_id, sha, _rounds(message))
    return found


def _rounds(message: str) -> tuple[int, int, int] | None:
    match = ROUNDS_TRAILER.search(message)
    if match is None:
        return None
    return int(match["spec"]), int(match["code"]), int(match["escalations"])
