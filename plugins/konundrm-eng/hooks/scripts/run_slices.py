"""Builds a feature from a terminal by chaining headless ``claude`` sessions, one per slice.

A person runs it from their repository as ``sh "${CLAUDE_PLUGIN_ROOT}/hooks/run.sh" run_slices.py
specs/<NNN-slug> [--claude PATH] [-- ARGS...]``. Before the first session it refuses, opening none,
unless the plan ``<feature>/tasks.md`` is readable, ``Approved`` and says ``Checkpoints:
pre-approved``, since no person approves the slices it chains; a plan already ``Done`` opens no
session either. Each session is ``claude -p "/konundrm-eng:develop-feature specs/<NNN-slug>" ARGS``,
started without a shell: the runner adds no flag of its own, so a session has exactly the
permissions the person's settings and ARGS give it. Everything after the first ``--`` is ARGS,
passed on unchanged even when it looks like one of the runner's own options. Sessions go on until
one exits non-zero, one prints a ``BLOCKED:`` line or a ``RED:`` line (it waits for a person's
decision), read as the stop gate reads them (deliberate_stops.py), or the plan's status reads
``Done``. Each session's output is echoed and the last stdout line says how the run ended.

Sections:
    SessionResult          — what one session reported.
    run_session()          — runs one session, echoing its output.
    PlanNotStartableError,
    check_startable()      — refuses a plan that may not be built unattended.
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
from tasks_document import TasksDocument, read_tasks

SEPARATOR = "--"
APPROVED_STATUS = "Approved"
DONE_STATUS = "Done"
PRE_APPROVED_CHECKPOINTS = "pre-approved"
DONE_LINE = "DONE"
STOPPED_EXIT = 1
"""Exit code when a session printed a ``BLOCKED:`` or ``RED:`` line, or failed."""
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


def run_slices(claude: str, feature: str, passthrough: list[str]) -> tuple[str, int]:
    """Runs sessions, one after another, until the feature ends.

    Args:
        claude: The ``claude`` executable.
        feature: The feature folder, relative to the current directory; its plan is
            ``<feature>/tasks.md``.
        passthrough: The person's arguments for every session.

    Returns:
        The summary line and the exit code: ``DONE`` and 0 once the plan's status is ``Done``,
        without any session when it already is; ``FAILED: exit <n>`` and ``STOPPED_EXIT`` when a
        session exits non-zero; its undecorated ``BLOCKED:`` or ``RED:`` line and
        ``STOPPED_EXIT`` when it prints one.

    Raises:
        PlanNotStartableError: Before any session, if check_startable() refuses the plan.
        OSError: If ``claude`` cannot be started.
    """
    plan_path = Path(feature) / "tasks.md"
    plan = read_tasks(plan_path)
    if plan.status == DONE_STATUS:
        return DONE_LINE, 0
    check_startable(plan, plan_path)
    command = resume_command(claude, feature, passthrough)
    while True:
        session = run_session(command)
        if session.exit_code != 0:
            return f"FAILED: exit {session.exit_code}", STOPPED_EXIT
        if session.stop_line is not None:
            return session.stop_line, STOPPED_EXIT
        if read_tasks(plan_path).status == DONE_STATUS:
            return DONE_LINE, 0


def _split_at_separator(arguments: list[str]) -> tuple[list[str], list[str]]:
    """Splits arguments at the first ``--`` into the runner's own and the sessions' ones."""
    if SEPARATOR not in arguments:
        return arguments, []
    separator_at = arguments.index(SEPARATOR)
    return arguments[:separator_at], arguments[separator_at + 1 :]


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
    options = parser.parse_args(own)
    claude = options.claude or shutil.which("claude")
    if claude is None:
        print("run_slices.py: claude is not on PATH; pass --claude PATH", file=sys.stderr)
        return UNSTARTABLE_EXIT
    try:
        summary, exit_code = run_slices(claude, options.feature, passthrough)
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
