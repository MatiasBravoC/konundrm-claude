"""Answers the orchestrator's bookkeeping questions about a feature's plan in one command per call.

The orchestrator runs it as ``sh "${CLAUDE_PLUGIN_ROOT}/hooks/run.sh" task_ledger.py <subcommand>``.
A task counts as built when a commit after the plan's base names it (task_commits), whatever its
box in tasks.md says, so the next task is the first one in plan order without such a commit, or,
while a slice's partitions run in parallel, the first such task of each partition of the wave in
progress (tasks_document.next_tasks).

Sections:
    status_lines() — the ``key: value`` lines ``status`` prints.
    main()         — CLI: ``status <tasks.md>``.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from project_paths import project_root
from quality_check import green_tree
from task_commits import task_commits
from tasks_document import Task, next_tasks, read_tasks
from working_tree import head_tree, snapshot_tree


def status_lines(root: Path, plan: Path) -> list[str]:
    """Describes where a feature stands: its base, built tasks, next task, tree and check.

    Args:
        root: Project root inside the feature's Git repository.
        plan: The feature's tasks.md, absolute or relative to the current directory.

    Returns:
        One ``key: value`` line each for ``feature``, ``plan``, ``base`` (or ``none``),
        ``committed`` (built task IDs in plan order, comma-separated, or ``none``), ``next``
        (``T<n> <title>``, or ``none`` when every task is built) or, in its place, ``next per
        partition`` (``P1 T1, P2 T4``) when tasks_document.next_tasks returns one task per
        partition of the wave in progress, ``tree`` (``clean`` or
        ``dirty``, untracked non-ignored files included) and ``check`` (``green for this tree``
        or ``not recorded``).

    Raises:
        task_commits.GitError: When Git cannot list the commits after the base.
    """
    document = read_tasks(plan)
    base = document.base_commit
    commits = task_commits(root, base) if base else {}
    built = [task.id for task in document.tasks if task.id in commits]
    snapshot = snapshot_tree(root)
    is_clean = snapshot is not None and snapshot == head_tree(root)
    is_green = snapshot is not None and snapshot == green_tree(root)
    return [
        f"feature: {plan.parent.name}",
        f"plan: {plan.as_posix()}",
        f"base: {base or 'none'}",
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


def main(argv: list[str] | None = None) -> int:
    """Runs one subcommand and prints its answer to stdout as UTF-8.

    Args:
        argv: Command-line arguments; defaults to sys.argv[1:].

    Returns:
        0 on success; argparse exits with 2 on a usage error.
    """
    for stream in (sys.stdout, sys.stderr):  # Claude Code reads UTF-8; Windows pipes default to a code page
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(prog="task_ledger.py", description="Reports where a feature's plan stands.")
    subcommands = parser.add_subparsers(dest="subcommand", required=True)
    status = subcommands.add_parser("status", help="show the base, built tasks, next task, tree and check")
    status.add_argument("plan", type=Path, help="the feature's tasks.md")
    arguments = parser.parse_args(argv)
    root = project_root({"cwd": os.getcwd()})
    sys.stdout.write("".join(f"{line}\n" for line in status_lines(root, arguments.plan)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
