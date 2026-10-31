"""Answers the orchestrator's bookkeeping questions about a feature's plan in one command per call.

The orchestrator runs it as ``sh "${CLAUDE_PLUGIN_ROOT}/hooks/run.sh" task_ledger.py <subcommand>``.
A task counts as built when a commit after the plan's base names it (task_commits), whatever its
box in tasks.md says, so the next task is the first one in plan order without such a commit, or,
while a slice's partitions run in parallel, the first such task of each partition of the wave in
progress (tasks_document.next_tasks). A plan that cannot be read, has no usable base commit or
names a base Git cannot find is reported as ``<file>:<line>`` on stderr with exit code 2.
``message`` writes a task's commit message, ending in the ``Task:`` and ``Rounds:`` trailers that
task_commits reads back, under the Git directory, so the flow can ``git commit -F`` it.

Sections:
    UnreadablePlanError — the plan cannot answer, and where.
    status_lines()      — the ``key: value`` lines ``status`` prints.
    write_task_message() — writes a task's commit message under the Git directory.
    main()              — CLI: ``status <tasks.md>`` and ``message <tasks.md> T<n> …``.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from project_paths import project_root
from quality_check import green_tree
from task_commits import GitError, task_commits
from tasks_document import Task, next_tasks, read_tasks
from working_tree import git_path, head_tree, snapshot_tree

UNREADABLE_PLAN_EXIT = 2
"""Exit code for a plan ``status`` cannot read; 1 stays for a refused request."""

TASK_MESSAGE_FILE = "KONUNDRM_TASK_MSG"
"""Name, under the Git directory, of the commit message ``message`` writes."""


class UnreadablePlanError(Exception):
    """The plan cannot be read or does not name a usable base commit.

    Its message starts with the place to fix: the plan's path, or ``<path>:<line>``.
    """


def status_lines(root: Path, plan: Path) -> list[str]:
    """Describes where a feature stands: its base, built tasks, next task, tree and check.

    Args:
        root: Project root inside the feature's Git repository.
        plan: The feature's tasks.md, absolute or relative to the current directory.

    Returns:
        One ``key: value`` line each for ``feature``, ``plan``, ``base``,
        ``committed`` (built task IDs in plan order, comma-separated, or ``none``), ``next``
        (``T<n> <title>``, or ``none`` when every task is built) or, in its place, ``next per
        partition`` (``P1 T1, P2 T4``) when tasks_document.next_tasks returns one task per
        partition of the wave in progress, ``tree`` (``clean`` or
        ``dirty``, untracked non-ignored files included) and ``check`` (``green for this tree``
        or ``not recorded``).

    Raises:
        UnreadablePlanError: When the plan cannot be read, has no ``Base commit:`` line (reported
            at line 1), holds no hex SHA on it, or names a base Git cannot list commits after
            (both reported at that line). Nothing is changed before it is raised.
    """
    document = read_tasks(plan)
    if not document.is_readable:
        raise UnreadablePlanError(f"{plan.as_posix()}: cannot read the plan")
    base_location = f"{plan.as_posix()}:{document.base_commit_line or 1}"
    base = document.base_commit
    if base is None:
        problem = "no Base commit line" if document.base_commit_line is None else "Base commit is not a hex SHA"
        raise UnreadablePlanError(f"{base_location}: {problem}")
    try:
        commits = task_commits(root, base)
    except GitError as error:
        raise UnreadablePlanError(f"{base_location}: base commit {base} is not in this repository") from error
    built = [task.id for task in document.tasks if task.id in commits]
    snapshot = snapshot_tree(root)
    is_clean = snapshot is not None and snapshot == head_tree(root)
    is_green = snapshot is not None and snapshot == green_tree(root)
    return [
        f"feature: {plan.parent.name}",
        f"plan: {plan.as_posix()}",
        f"base: {base}",
        f"committed: {', '.join(built) or 'none'}",
        _next_line(next_tasks(document, set(built))),
        f"tree: {'clean' if is_clean else 'dirty'}",
        f"check: {'green for this tree' if is_green else 'not recorded'}",
    ]


def _next_line(resume_tasks: tuple[Task, ...]) -> str:
    """The ``next per partition:`` line for several resume tasks, else the ``next:`` line."""
    if len(resume_tasks) > 1:
        return "next per partition: " + ", ".join(f"{task.partition} {task.id}" for task in resume_tasks)
    return f"next: {f'{resume_tasks[0].id} {resume_tasks[0].title}' if resume_tasks else 'none'}"


def write_task_message(root: Path, plan: Path, task_id: str, subject: str, rounds: str, body: str | None) -> Path:
    """Writes the commit message for one task of the plan under the Git directory.

    The message is the subject, then the body when given, then a final paragraph Git reads as the
    trailer block: ``Task: <id> · Covers: <ids>`` with the covers that end the task's plan line,
    and ``Rounds: <rounds>``.

    Args:
        root: Project root inside the feature's Git repository.
        plan: The feature's tasks.md, absolute or relative to the current directory.
        task_id: ID of a task in the plan, such as ``T3``.
        subject: The commit's subject line.
        rounds: The Rounds trailer's value, ``spec <n> · code <n> · escalations <n>``.
        body: Paragraphs between the subject and the trailers, or None for none.

    Returns:
        The message file's path, ``<git-path KONUNDRM_TASK_MSG>``.

    Raises:
        UnreadablePlanError: When the plan cannot be read or ``root`` is not in a Git repository.

    Side effects:
        Overwrites the message file, as UTF-8 with bare line feeds whatever the platform; nothing
        in the working tree changes.
    """
    document = read_tasks(plan)
    if not document.is_readable:
        raise UnreadablePlanError(f"{plan.as_posix()}: cannot read the plan")
    task = next(task for task in document.tasks if task.id == task_id)
    path = git_path(root, TASK_MESSAGE_FILE)
    if path is None:
        raise UnreadablePlanError(f"{plan.as_posix()}: not inside a Git repository")
    trailers = f"Task: {task.id} · Covers: {', '.join(task.covers)}\nRounds: {rounds}"
    paragraphs = [subject, *([body] if body else []), trailers]
    # Under a C locale Python decodes non-ASCII argv bytes as surrogate escapes; surrogateescape
    # writes those bytes back as they came, so the `·` the caller typed stays UTF-8.
    path.write_text("\n\n".join(paragraphs) + "\n", encoding="utf-8", errors="surrogateescape", newline="\n")
    return path


def main(argv: list[str] | None = None) -> int:
    """Runs one subcommand and prints its answer to stdout as UTF-8.

    Args:
        argv: Command-line arguments; defaults to sys.argv[1:].

    Subcommands:
        ``status <tasks.md>`` prints status_lines(). ``message <tasks.md> T<n> --subject S
        --rounds R [--body B]`` runs write_task_message() and prints only the file's path.
        Every line ends in a bare line feed, so ``msg=$(…)`` keeps no carriage return on Windows.

    Returns:
        0 on success, or ``UNREADABLE_PLAN_EXIT`` (2) with the plan's ``<file>:<line>`` on stderr
        and nothing on stdout when the plan cannot be read; argparse exits with 2 on a usage error.
    """
    for stream in (sys.stdout, sys.stderr):  # Claude Code reads UTF-8; Windows pipes default to a code page
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace", newline="\n")
    parser = argparse.ArgumentParser(prog="task_ledger.py", description="Reports where a feature's plan stands.")
    subcommands = parser.add_subparsers(dest="subcommand", required=True)
    status = subcommands.add_parser("status", help="show the base, built tasks, next task, tree and check")
    status.add_argument("plan", type=Path, help="the feature's tasks.md")
    message = subcommands.add_parser("message", help="write a task's commit message and print its path")
    message.add_argument("plan", type=Path, help="the feature's tasks.md")
    message.add_argument("task_id", metavar="T<n>", help="the task the commit builds")
    message.add_argument("--subject", required=True, help="the commit's subject line")
    message.add_argument("--rounds", required=True, help='"spec <n> · code <n> · escalations <n>"')
    message.add_argument("--body", help="paragraphs between the subject and the trailers")
    arguments = parser.parse_args(argv)
    root = project_root({"cwd": os.getcwd()})
    try:
        if arguments.subcommand == "message":
            lines = [
                write_task_message(
                    root, arguments.plan, arguments.task_id, arguments.subject, arguments.rounds, arguments.body
                ).as_posix()
            ]
        else:
            lines = status_lines(root, arguments.plan)
    except UnreadablePlanError as error:
        sys.stderr.write(f"task_ledger.py: {error}\n")
        return UNREADABLE_PLAN_EXIT
    sys.stdout.write("".join(f"{line}\n" for line in lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
