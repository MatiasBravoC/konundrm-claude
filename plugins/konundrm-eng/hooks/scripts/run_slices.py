"""Builds a feature from a terminal by chaining headless ``claude`` sessions, one per slice.

A person runs it from their repository as ``sh "${CLAUDE_PLUGIN_ROOT}/hooks/run.sh" run_slices.py
specs/<NNN-slug> [--claude PATH] [--max-sessions N] [-- ARGS...]`` from inside the feature's
repository. Before the first session it refuses, opening none, unless the plan
``<feature>/tasks.md`` is readable, ``Approved``, says ``Checkpoints: pre-approved`` (no person
approves the slices it chains) and names a base commit in this repository; a plan already ``Done``
opens no session either. Each session is ``claude -p "/konundrm-eng:develop-feature
specs/<NNN-slug>" ARGS``, started without a shell: the runner adds no flag of its own, so a session
has exactly the permissions the person's settings and ARGS give it. Everything after the first
``--`` is ARGS, passed on unchanged even when it looks like one of the runner's own options.

It opens at most one session per pending slice plus one, fewer with ``--max-sessions N``. After each
session the last stdout line, echoed after the sessions' own output, says how the run ended, checked
in this order:

- ``FAILED: exit <n>``: the session exited non-zero.
- ``BLOCKED: <reason>`` or ``RED: <reason>`` (it waits for a person's decision): the session printed
  that line, read as the stop gate reads it (deliberate_stops.py).
- ``STALLED: session <k> added no commit``: HEAD did not move during session k.
- ``DONE``: the plan's status reads ``Done``.
- ``STALLED: reached the cap of <n> sessions``: none of the above after the last allowed session.

Sections:
    SessionResult          — what one session reported.
    run_session()          — runs one session, echoing its output.
    PlanNotStartableError,
    check_startable()      — refuses a plan that may not be built unattended.
    count_pending_slices() — counts the slices still to build, which sets the session cap.
    run_slices()           — runs sessions until the feature ends, and says how.
    main()                 — CLI.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from deliberate_stops import find_deliberate_stop
from task_commits import GitError, task_commits, task_key
from tasks_document import TasksDocument, read_tasks
from working_tree import run_git

SEPARATOR = "--"
APPROVED_STATUS = "Approved"
DONE_STATUS = "Done"
PRE_APPROVED_CHECKPOINTS = "pre-approved"
DONE_LINE = "DONE"
STOPPED_EXIT = 1
"""Exit code when a session failed, printed a ``BLOCKED:`` or ``RED:`` line or added no commit, or
the session cap was reached."""
UNSTARTABLE_EXIT = 2
"""Exit code when the plan may not run or ``claude`` cannot be found or started (argparse uses it
for usage errors too)."""


@dataclass(frozen=True)
class SessionResult:
    """What one headless session reported.

    Attributes:
        exit_code: The session's exit status.
        stop_line: Its first stdout line that stops on purpose, undecorated (``BLOCKED: <reason>``
            or ``RED: <reason>``), or None.
    """

    exit_code: int
    stop_line: str | None


class PlanNotStartableError(Exception):
    """The plan may not be built unattended; the message names the plan and the reason."""


def resume_command(claude: str, feature: str, passthrough: list[str]) -> list[str]:
    """Builds the command line of one session.

    Args:
        claude: The ``claude`` executable.
        feature: The feature folder exactly as the person gave it, such as ``specs/001-demo``.
        passthrough: The person's arguments after ``--``, kept in order.

    Returns:
        ``[claude, "-p", "/konundrm-eng:develop-feature <feature>", *passthrough]``.
    """
    return [claude, "-p", f"/konundrm-eng:develop-feature {feature}", *passthrough]


def run_session(command: list[str]) -> SessionResult:
    """Runs one session, echoing each stdout line as UTF-8.

    The session's stderr goes straight to the runner's, and its stdin is empty so it never waits
    on the terminal.

    Args:
        command: The session's command line, run without a shell.

    Returns:
        The session's exit status and its first ``BLOCKED:`` or ``RED:`` line, undecorated.

    Raises:
        OSError: If the command cannot be started.
    """
    stop_line = None
    with subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE) as session:
        for raw_line in session.stdout:  # type: ignore[union-attr]  # stdout=PIPE always sets it
            line = raw_line.decode("utf-8", errors="replace").rstrip("\r\n")
            print(line, flush=True)
            if stop_line is None:
                stop_line = find_deliberate_stop(line)
    return SessionResult(exit_code=session.returncode, stop_line=stop_line)


def check_startable(plan: TasksDocument, plan_path: Path) -> None:
    """Refuses a plan that may not be built unattended.

    Args:
        plan: The parsed plan.
        plan_path: Where it was read from, named in the refusal.

    Raises:
        PlanNotStartableError: If the plan could not be read, its status is not ``Approved``, or
            its ``Checkpoints:`` line does not say ``pre-approved`` (a missing one reads as ``ask``).
    """
    if not plan.is_readable:
        raise PlanNotStartableError(f"cannot read the plan {plan_path}")
    if plan.status != APPROVED_STATUS:
        raise PlanNotStartableError(f"the plan {plan_path} has Status {plan.status or '(none)'}, not Approved")
    if plan.checkpoints != PRE_APPROVED_CHECKPOINTS:
        raise PlanNotStartableError(
            f"the plan {plan_path} has Checkpoints: {plan.checkpoints}, not pre-approved, "
            "so each pause waits for a person"
        )


def count_pending_slices(plan: TasksDocument, plan_path: Path, root: Path) -> int:
    """Counts the slices with at least one task no commit after the plan's base names.

    A task is built under the rule ``task_ledger.py status`` uses: a ``Task: T<n>`` commit in
    ``<base>..HEAD`` (task_commits). Tasks outside any slice count as one slice together.

    Args:
        plan: The parsed plan.
        plan_path: Where it was read from, named in the refusal.
        root: Directory inside the feature's Git repository.

    Returns:
        The number of pending slices, 0 when every task is built.

    Raises:
        PlanNotStartableError: If the plan has no base commit SHA, or Git cannot list the commits
            after it (for instance because it is not in this repository).
    """
    base = plan.base_commit
    if base is None:
        raise PlanNotStartableError(f"the plan {plan_path} has no Base commit SHA")
    try:
        commits = task_commits(root, base)
    except GitError as error:
        raise PlanNotStartableError(f"the plan {plan_path} has base commit {base}, not in this repository") from error
    return len({task.slice for task in plan.tasks if task_key(task.id) not in commits})


def _head(root: Path) -> bytes | None:
    """The SHA HEAD points at, or None when Git cannot tell."""
    return run_git(["rev-parse", "HEAD"], root)


def _session_ending(
    session: SessionResult, number: int, has_committed: bool, plan_path: Path
) -> tuple[str, int] | None:
    """Says how the run ends after a session, in the order FAILED, stop line, STALLED, DONE.

    Returns:
        The summary line and exit code, or None when the run may open another session.
    """
    if session.exit_code != 0:
        return f"FAILED: exit {session.exit_code}", STOPPED_EXIT
    if session.stop_line is not None:
        return session.stop_line, STOPPED_EXIT
    if not has_committed:
        return f"STALLED: session {number} added no commit", STOPPED_EXIT
    if read_tasks(plan_path).status == DONE_STATUS:
        return DONE_LINE, 0
    return None


def run_slices(claude: str, feature: str, passthrough: list[str], max_sessions: int | None = None) -> tuple[str, int]:
    """Runs sessions, one after another, until the feature ends or the session cap is reached.

    The cap is the number of pending slices (count_pending_slices) plus one, for the session that
    marks the plan Done; ``max_sessions`` can only lower it.

    Args:
        claude: The ``claude`` executable.
        feature: The feature folder, relative to the current directory, which is inside the
            feature's Git repository; its plan is ``<feature>/tasks.md``.
        passthrough: The person's arguments for every session.
        max_sessions: The most sessions to open, at least 1, or None for no limit beyond the cap.

    Returns:
        The summary line and the exit code, decided after each session in this order:
        ``FAILED: exit <n>`` and ``STOPPED_EXIT`` when it exits non-zero; its undecorated
        ``BLOCKED:`` or ``RED:`` line and ``STOPPED_EXIT`` when it prints one;
        ``STALLED: session <k> added no commit`` (k counts from 1) and ``STOPPED_EXIT`` when HEAD
        did not move; ``DONE`` and 0 once the plan's status is ``Done`` (without any session when
        it already is); ``STALLED: reached the cap of <n> sessions`` and ``STOPPED_EXIT`` when the
        cap is reached first.

    Raises:
        PlanNotStartableError: Before any session, if check_startable() or count_pending_slices()
            refuses the plan.
        OSError: If ``claude`` cannot be started.
    """
    plan_path = Path(feature) / "tasks.md"
    plan = read_tasks(plan_path)
    if plan.status == DONE_STATUS:
        return DONE_LINE, 0
    check_startable(plan, plan_path)
    root = Path.cwd()
    cap = count_pending_slices(plan, plan_path, root) + 1
    if max_sessions is not None:
        cap = min(cap, max_sessions)
    command = resume_command(claude, feature, passthrough)
    for number in range(1, cap + 1):
        head_before = _head(root)
        session = run_session(command)
        ending = _session_ending(session, number, _head(root) != head_before, plan_path)
        if ending is not None:
            return ending
    return f"STALLED: reached the cap of {cap} sessions", STOPPED_EXIT


def _split_at_separator(arguments: list[str]) -> tuple[list[str], list[str]]:
    """Splits arguments at the first ``--`` into the runner's own and the sessions' ones."""
    if SEPARATOR not in arguments:
        return arguments, []
    separator_at = arguments.index(SEPARATOR)
    return arguments[:separator_at], arguments[separator_at + 1 :]


def _positive_int(text: str) -> int:
    """Parses ``--max-sessions``: an integer of at least 1."""
    try:
        value = int(text)
    except ValueError:
        value = 0
    if value < 1:
        raise argparse.ArgumentTypeError(f"{text!r} is not a positive integer")
    return value


def main(argv: list[str] | None = None) -> int:
    """Runs the sessions and prints the summary line last, all as UTF-8.

    Args:
        argv: Command-line arguments; defaults to sys.argv[1:]. Everything after the first
            ``--`` is passed to every session unchanged.

    Returns:
        The exit code from run_slices(), or ``UNSTARTABLE_EXIT`` with the reason on stderr and
        nothing on stdout when the plan may not run, or when ``claude`` is not on PATH or cannot
        be started. argparse exits with 2 on a usage error.
    """
    for stream in (sys.stdout, sys.stderr):  # sessions print UTF-8; Windows consoles default to a code page
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace", newline="\n")
    own, passthrough = _split_at_separator(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(
        prog="run_slices.py", description="Builds a feature in headless claude sessions, one per slice."
    )
    parser.add_argument("feature", help="the feature folder, such as specs/001-demo")
    parser.add_argument("--claude", help="the claude executable (default: claude on PATH)")
    parser.add_argument(
        "--max-sessions",
        type=_positive_int,
        metavar="N",
        help="open at most N sessions (default and upper bound: pending slices + 1)",
    )
    options = parser.parse_args(own)
    claude = options.claude or shutil.which("claude")
    if claude is None:
        print("run_slices.py: claude is not on PATH; pass --claude PATH", file=sys.stderr)
        return UNSTARTABLE_EXIT
    try:
        summary, exit_code = run_slices(claude, options.feature, passthrough, options.max_sessions)
    except PlanNotStartableError as refusal:
        print(f"run_slices.py: {refusal}", file=sys.stderr)
        return UNSTARTABLE_EXIT
    except OSError as error:
        print(f"run_slices.py: cannot start {claude}: {error}", file=sys.stderr)
        return UNSTARTABLE_EXIT
    print(summary, flush=True)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
