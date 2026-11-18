"""Answers the orchestrator's bookkeeping questions about a feature's plan in one command per call.

The orchestrator runs it as ``sh "${CLAUDE_PLUGIN_ROOT}/hooks/run.sh" task_ledger.py <subcommand>``.
A task counts as built when a commit after the plan's base names it (task_commits), whatever its
box in tasks.md says, so the next task is the first one in plan order without such a commit, or,
while a slice's partitions run in parallel, the first such task of each partition of the wave in
progress (tasks_document.next_tasks). A plan that cannot be read, has no usable base commit or
names a base Git cannot find is reported as ``<file>:<line>`` on stderr with exit code 2.
``message`` writes a task's commit message (subject and body only) under the Git directory, so the
flow can ``git commit -F`` it, and the pending note with the ``Task:`` and ``Rounds:`` lines that
task_commits reads back once ``record`` attaches it; it refuses, with exit code 1, a task the plan
lacks or one already built. ``close-slice`` does a slice
pause's bookkeeping: it checks the boxes of the slice's built tasks and writes their rounds from
their commits, keeping every other byte of the plan; it refuses, with exit code 1, a slice the
plan lacks. ``record`` attaches the pending note (``KONUNDRM_TASK_NOTE`` under the Git
directory) to HEAD under task_commits.NOTES_REF once HEAD was committed from the pending message,
then deletes both pending files; it refuses, with exit code 1 and nothing changed, when there is
no pending note or HEAD's subject is not the pending message's.

Sections:
    UnreadablePlanError — the plan cannot answer, and where.
    RefusedTaskError    — ``message`` will not write for this task, and why.
    RefusedSliceError   — ``close-slice`` will not close this slice.
    RefusedRecordError  — ``record`` will not attach the pending note to HEAD.
    status_lines()      — the ``key: value`` lines ``status`` prints.
    write_task_message() — writes a task's commit message and pending note under the Git directory.
    close_slice()       — checks a slice's built tasks and writes their rounds into the plan.
    record_task_note()  — attaches the pending note to the commit made from the pending message.
    main()              — CLI: ``status``, ``message``, ``close-slice`` and ``record``.
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from project_paths import project_root
from quality_check import green_tree
from task_commits import NOTES_REF, GitError, TaskCommit, task_commits, task_key
from tasks_document import HTML_COMMENT, SLICE_HEADING, TASK, Task, TasksDocument, next_tasks, read_tasks, rounds_field
from working_tree import GitCommandError, git_path, head_tree, run_git, run_git_checked, snapshot_tree

REFUSED_EXIT = 1
"""Exit code when ``message`` refuses its task (not in the plan, or already committed),
``close-slice`` refuses its slice (not in the plan) or ``record`` refuses to attach the note."""

UNREADABLE_PLAN_EXIT = 2
"""Exit code, for any subcommand, when the plan cannot be read or names no usable base commit."""

TASK_MESSAGE_FILE = "KONUNDRM_TASK_MSG"
"""Name, under the Git directory, of the commit message ``message`` writes."""

TASK_NOTE_FILE = "KONUNDRM_TASK_NOTE"
"""Name, under the Git directory, of the pending note ``record`` attaches to the task's commit."""

_OPEN_BOX = "- [ ] "
_CHECKED_BOX = "- [x] "


class UnreadablePlanError(Exception):
    """The plan cannot be read or does not name a usable base commit.

    Its message starts with the place to fix: the plan's path, or ``<path>:<line>``.
    """


class RefusedTaskError(Exception):
    """The task is not in the plan, or a commit after the plan's base already built it.

    Its message starts with the task ID as given and names the plan's path or the commit's SHA.
    """


class RefusedSliceError(Exception):
    """No slice heading of the plan names the slice; its message starts with the slice ID as given."""


class RefusedRecordError(Exception):
    """``record`` cannot attach the pending note; its message says why.

    None is pending, HEAD was committed from another message, or Git failed.
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
    document, commits = _plan_and_task_commits(root, plan)
    built = [task.id for task in document.tasks if task_key(task.id) in commits]
    snapshot = snapshot_tree(root)
    is_clean = snapshot is not None and snapshot == head_tree(root)
    is_green = snapshot is not None and snapshot == green_tree(root)
    return [
        f"feature: {plan.parent.name}",
        f"plan: {plan.as_posix()}",
        f"base: {document.base_commit}",
        f"committed: {', '.join(built) or 'none'}",
        _next_line(next_tasks(document, set(built))),
        f"tree: {'clean' if is_clean else 'dirty'}",
        f"check: {'green for this tree' if is_green else 'not recorded'}",
    ]


def _plan_and_task_commits(root: Path, plan: Path) -> tuple[TasksDocument, dict[str, TaskCommit]]:
    """Reads the plan and lists the task commits after its base, keyed by task_key().

    Raises:
        UnreadablePlanError: As documented in status_lines().
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
        return document, task_commits(root, base)
    except GitError as error:
        raise UnreadablePlanError(f"{base_location}: base commit {base} is not in this repository") from error


def _next_line(resume_tasks: tuple[Task, ...]) -> str:
    """The ``next per partition:`` line for several resume tasks, else the ``next:`` line."""
    if len(resume_tasks) > 1:
        return "next per partition: " + ", ".join(f"{task.partition} {task.id}" for task in resume_tasks)
    return f"next: {f'{resume_tasks[0].id} {resume_tasks[0].title}' if resume_tasks else 'none'}"


def write_task_message(root: Path, plan: Path, task_id: str, subject: str, rounds: str, body: str | None) -> Path:
    """Writes the commit message and the pending note for one task of the plan under the Git directory.

    The message is the subject, then the body when given, separated by a blank line. The pending
    note, which ``record`` attaches to the task's commit, holds two lines:
    ``Task: <id> · Covers: <ids>`` with the covers that end the task's plan line, and
    ``Rounds: <rounds>``.

    Args:
        root: Project root inside the feature's Git repository.
        plan: The feature's tasks.md, absolute or relative to the current directory.
        task_id: ID of a task in the plan, such as ``T3``, matched by number (``T03`` is ``T3``).
        subject: The commit's subject line.
        rounds: The note's Rounds value, ``spec <n> · code <n> · escalations <n>``.
        body: Paragraphs after the subject, or None for none.

    Returns:
        The message file's path, ``<git-path KONUNDRM_TASK_MSG>``.

    Raises:
        UnreadablePlanError: When the plan cannot be read or names no usable base commit (as in
            status_lines()), or ``root`` is not in a Git repository.
        RefusedTaskError: When the plan has no such task, or a commit in ``<base>..HEAD``
            already names it.

    Side effects:
        Unless it raises, overwrites the message file and ``<git-path KONUNDRM_TASK_NOTE>``, as
        UTF-8 with bare line feeds whatever the platform; nothing in the working tree changes.
    """
    document, commits = _plan_and_task_commits(root, plan)
    key = task_key(task_id)
    task = next((task for task in document.tasks if task_key(task.id) == key), None)
    if task is None:
        raise RefusedTaskError(f"{task_id}: no such task in {plan.as_posix()}")
    if key in commits:
        raise RefusedTaskError(f"{task_id}: already committed in {commits[key].sha}")
    message_path = git_path(root, TASK_MESSAGE_FILE)
    note_path = git_path(root, TASK_NOTE_FILE)
    if message_path is None or note_path is None:
        raise UnreadablePlanError(f"{plan.as_posix()}: not inside a Git repository")
    paragraphs = [subject, *([body] if body else [])]
    _write_git_file(message_path, "\n\n".join(paragraphs) + "\n")
    _write_git_file(note_path, f"Task: {task.id} · Covers: {', '.join(task.covers)}\nRounds: {rounds}\n")
    return message_path


def _write_git_file(path: Path, text: str) -> None:
    """Overwrites a file under the Git directory with ``text`` as UTF-8 with bare line feeds."""
    # Under a C locale Python decodes non-ASCII argv bytes as surrogate escapes; surrogateescape
    # writes those bytes back as they came, so the `·` the caller typed stays UTF-8.
    path.write_text(text, encoding="utf-8", errors="surrogateescape", newline="\n")


@dataclass(frozen=True)
class _TaskBlock:
    """Where one task sits in the plan's lines: its task line, its Rounds line and its last line.

    The block is the task line plus the indented lines right below it; indices count from 0.
    """

    task_id: str
    task_line: int
    rounds_line: int | None
    last_line: int


def close_slice(root: Path, plan: Path, slice_id: str) -> list[str]:
    """Checks the box and writes the rounds of every task of a slice that has its commit.

    A task of the slice whose commit (task_commits) comes after the plan's base gets its ``- [ ]``
    box checked (``[x]`` and ``[X]`` stay as written) and, when that commit has a ``Rounds:``
    line, the same rounds as ``  - Rounds: spec <n> · code <n> · escalations <n>``: in place of
    the block's indented Rounds line, or as the block's last line. Each line not changed comes
    back byte-identical, its own ending included, and an added line takes the ending of the line
    it follows, so CRLF, LF and mixed files keep their endings. When the block ends the file
    without a line break, its last line gets the ending of the nearest line above that has one
    (LF if none has) and the added Rounds line becomes the file's last line, still without a
    break. HTML comments are not tasks.
    Running it again changes nothing.

    Args:
        root: Project root inside the feature's Git repository.
        plan: The feature's tasks.md, absolute or relative to the current directory.
        slice_id: A slice of the plan as its ``## Slice`` heading names it, such as ``S2``.

    Returns:
        The IDs, as the plan writes them and in plan order, of the slice's tasks without a commit.

    Raises:
        UnreadablePlanError: As in status_lines(), or when the plan cannot be read as bytes.
        RefusedSliceError: When no slice heading of the plan names ``slice_id``.

    Side effects:
        Rewrites the plan when a box or Rounds line changes; nothing is written when it raises.
    """
    _, commits = _plan_and_task_commits(root, plan)
    try:
        original = plan.read_bytes()
    except OSError as error:
        raise UnreadablePlanError(f"{plan.as_posix()}: cannot read the plan") from error
    # surrogateescape gives back every byte as read, whatever the file holds.
    text = original.decode("utf-8", errors="surrogateescape")
    blocks = _slice_task_blocks(text, slice_id)
    if blocks is None:
        raise RefusedSliceError(f"{slice_id}: no such slice in {plan.as_posix()}")
    lines = _lines_with_endings(text)
    not_committed: list[str] = []
    for block in reversed(blocks):  # bottom-up, so an added line never shifts a block still to close
        commit = commits.get(task_key(block.task_id))
        if commit is None:
            not_committed.insert(0, block.task_id)
        else:
            _close_task(lines, block, commit.rounds)
    closed = "".join(lines).encode("utf-8", errors="surrogateescape")
    if closed != original:
        plan.write_bytes(closed)
    return not_committed


def _lines_with_endings(text: str) -> list[str]:
    """Splits text at line feeds only, each line keeping its ending: LF, CRLF, or none for the last."""
    pieces = text.split("\n")
    return [f"{piece}\n" for piece in pieces[:-1]] + ([pieces[-1]] if pieces[-1] else [])


def _slice_task_blocks(text: str, slice_id: str) -> list[_TaskBlock] | None:
    """Locates the task blocks of one slice, or returns None when no heading names the slice.

    Lines are read with HTML comments blanked out the way tasks_document reads them, so a
    commented example task is no task and line indices still match the file.
    """
    masked = HTML_COMMENT.sub(lambda comment: "\n" * comment.group().count("\n"), text).split("\n")
    is_slice_found = False
    current_slice = None
    blocks: list[_TaskBlock] = []
    for index, line in enumerate(masked):
        heading = SLICE_HEADING.match(line)
        if heading is not None:
            current_slice = heading.group("slice")
            is_slice_found = is_slice_found or current_slice == slice_id
        task = TASK.match(line)
        if task is not None and current_slice == slice_id:
            blocks.append(_task_block(masked, index, task.group("id")))
    return blocks if is_slice_found else None


def _task_block(masked: list[str], task_line: int, task_id: str) -> _TaskBlock:
    """The block of the task whose line is at ``task_line``: it and the indented lines below it."""
    last_line = task_line
    rounds_line = None
    while last_line + 1 < len(masked) and masked[last_line + 1][:1] in (" ", "\t") and masked[last_line + 1].strip():
        last_line += 1
        if rounds_line is None and rounds_field(masked[last_line]) is not None:
            rounds_line = last_line
    return _TaskBlock(task_id, task_line, rounds_line, last_line)


def _close_task(lines: list[str], block: _TaskBlock, rounds: tuple[int, int, int] | None) -> None:
    """Checks an open box and writes the commit's rounds into the block, editing ``lines`` in place."""
    task_line = lines[block.task_line]
    if task_line.startswith(_OPEN_BOX):
        lines[block.task_line] = _CHECKED_BOX + task_line[len(_OPEN_BOX) :]
    if rounds is None:
        return
    field = f"- Rounds: spec {rounds[0]} · code {rounds[1]} · escalations {rounds[2]}"
    if block.rounds_line is not None:
        old = lines[block.rounds_line]
        indent = old[: len(old) - len(old.lstrip(" \t"))]
        lines[block.rounds_line] = f"{indent}{field}{_line_ending(old)}"
        return
    previous = lines[block.last_line]
    ending = _line_ending(previous)
    if ending:
        lines.insert(block.last_line + 1, f"  {field}{ending}")
    else:  # the block ends the file without a line break: break it, and keep the file's last line bare
        lines[block.last_line] = previous + _ending_above(lines, block.last_line)
        lines.insert(block.last_line + 1, f"  {field}")


def _ending_above(lines: list[str], line_index: int) -> str:
    """The ending of the nearest line above ``line_index`` that has one, or LF when none has."""
    return next((_line_ending(line) for line in reversed(lines[:line_index]) if _line_ending(line)), "\n")


def _line_ending(line: str) -> str:
    """The ending a line was written with: CRLF, LF, or an empty string for none."""
    if line.endswith("\r\n"):
        return "\r\n"
    return "\n" if line.endswith("\n") else ""


def record_task_note(root: Path) -> str:
    """Attaches the pending note to HEAD when HEAD was committed from the pending message.

    HEAD counts as made from the pending message when its subject (the first line of its message)
    equals the first line of ``<git-dir>/KONUNDRM_TASK_MSG``. The note is added without ``-f``, so
    a HEAD that already has a note under NOTES_REF is refused rather than overwritten.

    Args:
        root: Directory inside the Git repository whose HEAD is the task's commit.

    Returns:
        ``recorded: <short sha> <first line of the note>``.

    Raises:
        RefusedRecordError: When there is no pending note or message, HEAD's subject differs from
            the pending message's, Git cannot read HEAD, or Git cannot add the note (the
            message then carries Git's own error).

    Side effects:
        Unless it raises, adds a note to HEAD under NOTES_REF and deletes both pending files.
        When it raises, no note and no pending file has changed.
    """
    message_path = git_path(root, TASK_MESSAGE_FILE)
    note_path = git_path(root, TASK_NOTE_FILE)
    if message_path is None or note_path is None:
        raise RefusedRecordError("not inside a Git repository")
    if not note_path.is_file() or not message_path.is_file():
        raise RefusedRecordError(f"no pending note: {note_path.as_posix()} or {message_path.as_posix()} is missing")
    pending_subject = _first_line(message_path.read_bytes())
    head = run_git(["log", "-1", "--format=%h%n%B", "HEAD"], root)
    if head is None:
        raise RefusedRecordError("cannot read HEAD")
    short_sha, _, head_message = head.partition(b"\n")
    if _first_line(head_message) != pending_subject:
        raise RefusedRecordError(f"HEAD {short_sha.decode()} was not committed from {message_path.as_posix()}")
    # -F hands Git the note file's bytes as they are, so its UTF-8 `·` survives any locale.
    try:
        run_git_checked(["notes", f"--ref={NOTES_REF}", "add", "-F", str(note_path), "HEAD"], root)
    except GitCommandError as error:
        # Git's own words cover every cause, an existing note as much as a missing identity.
        raise RefusedRecordError(f"git notes add failed for HEAD {short_sha.decode()}: {error}") from error
    note_summary = _first_line(note_path.read_bytes())
    note_path.unlink()
    message_path.unlink()
    return f"recorded: {short_sha.decode()} {note_summary}"


def _first_line(text: bytes) -> str:
    """The first line of UTF-8 bytes, without its line ending; undecodable bytes stay escaped."""
    return text.decode("utf-8", errors="surrogateescape").split("\n", 1)[0].rstrip("\r")


def main(argv: list[str] | None = None) -> int:
    """Runs one subcommand and prints its answer to stdout as UTF-8.

    Args:
        argv: Command-line arguments; defaults to sys.argv[1:].

    Subcommands:
        ``status <tasks.md>`` prints status_lines(). ``message <tasks.md> T<n> --subject S
        --rounds R [--body B]`` runs write_task_message() and prints only the file's path.
        ``close-slice <tasks.md> S<k>`` runs close_slice() and prints ``not committed: <ids>``
        (comma-separated, or ``none``). ``record`` runs record_task_note() and prints its line.
        Every line ends in a bare line feed, so ``msg=$(…)``
        keeps no carriage return on Windows.

    Returns:
        0 on success; ``REFUSED_EXIT`` (1) with the reason on stderr when ``message`` refuses
        an unknown or already committed task, ``close-slice`` an unknown slice, or ``record``
        finds no pending note or a HEAD made from another message;
        ``UNREADABLE_PLAN_EXIT`` (2) with the plan's
        ``<file>:<line>`` on stderr when the plan cannot be read. On 1 or 2 nothing reaches stdout
        and nothing is written. argparse exits with 2 on a usage error.
    """
    for stream in (sys.stdout, sys.stderr):  # Claude Code reads UTF-8; Windows pipes default to a code page
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace", newline="\n")
    parser = argparse.ArgumentParser(prog="task_ledger.py", description="Reports where a feature's plan stands.")
    subcommands = parser.add_subparsers(dest="subcommand", required=True)
    status = subcommands.add_parser("status", help="show the base, built tasks, next task, tree and check")
    status.add_argument("plan", type=Path, help="the feature's tasks.md")
    message = subcommands.add_parser("message", help="write a task's commit message and pending note")
    message.add_argument("plan", type=Path, help="the feature's tasks.md")
    message.add_argument("task_id", metavar="T<n>", help="the task the commit builds")
    message.add_argument("--subject", required=True, help="the commit's subject line")
    message.add_argument("--rounds", required=True, help='"spec <n> · code <n> · escalations <n>"')
    message.add_argument("--body", help="paragraphs after the subject")
    close = subcommands.add_parser("close-slice", help="check a slice's built tasks and write their rounds")
    close.add_argument("plan", type=Path, help="the feature's tasks.md")
    close.add_argument("slice_id", metavar="S<k>", help="the slice to close")
    subcommands.add_parser("record", help="attach the pending note to the commit made from the pending message")
    arguments = parser.parse_args(argv)
    root = project_root({"cwd": os.getcwd()})
    try:
        lines = _run_subcommand(root, arguments)
    except UnreadablePlanError as error:
        sys.stderr.write(f"task_ledger.py: {error}\n")
        return UNREADABLE_PLAN_EXIT
    except (RefusedTaskError, RefusedSliceError, RefusedRecordError) as error:
        sys.stderr.write(f"task_ledger.py: {error}\n")
        return REFUSED_EXIT
    sys.stdout.write("".join(f"{line}\n" for line in lines))
    return 0


def _run_subcommand(root: Path, arguments: argparse.Namespace) -> list[str]:
    """Runs the parsed subcommand and gives the lines it prints."""
    if arguments.subcommand == "message":
        path = write_task_message(
            root, arguments.plan, arguments.task_id, arguments.subject, arguments.rounds, arguments.body
        )
        return [path.as_posix()]
    if arguments.subcommand == "close-slice":
        not_committed = close_slice(root, arguments.plan, arguments.slice_id)
        return [f"not committed: {', '.join(not_committed) or 'none'}"]
    if arguments.subcommand == "record":
        return [record_task_note(root)]
    return status_lines(root, arguments.plan)


if __name__ == "__main__":
    sys.exit(main())
