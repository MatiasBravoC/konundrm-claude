"""Content snapshots of the Git working tree, to tell whether files changed and which ones.

A snapshot is the SHA of a Git tree object holding every tracked and untracked, non-ignored file
as it is on disk. It depends only on file contents, not on HEAD, so committing leaves it unchanged.
Taking one writes blob and tree objects into the repository's object database (as
``git stash create`` does) but never touches the real index, HEAD, refs or any file on disk.

Sections:
    GitCommandError, run_git_checked() — runs one Git command and raises Git's own error on failure.
    run_git()        — runs one Git command with a timeout; the hooks' shared Git runner.
    git_path()       — where a file under the repository's Git directory lives.
    snapshot_tree()  — the working tree's content as a tree SHA.
    head_tree()      — the last commit's tree, or the empty tree before the first commit.
    changed_paths()  — files added, modified or deleted between two snapshots.
    AddedLine, added_lines() — the lines added between two snapshots, with their line numbers.
    restore_paths()  — puts files back the way they were in an earlier snapshot.
"""

from __future__ import annotations

import contextlib
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

GIT_TIMEOUT_SECONDS = 60
HUNK_HEADER = re.compile(rb"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


class GitCommandError(Exception):
    """A Git command could not run or exited with an error; the message is Git's own when it has one."""


def run_git_checked(
    args: list[str], root: Path, env: dict[str, str] | None = None, stdin: bytes | None = None
) -> bytes:
    """Runs one Git command in a repository, with a timeout, and fails with Git's own error.

    Args:
        args: Git's arguments, without the leading ``git``; passed as an argument list, never
            through a shell.
        root: Directory Git runs in, inside the repository.
        env: Environment for Git; None inherits this process's.
        stdin: Bytes fed to Git's standard input; None feeds nothing.

    Returns:
        Git's standard output.

    Raises:
        GitCommandError: When Git is missing or times out (the message says which), or exits with
            an error (the message is Git's standard error, stripped).
    """
    command = " ".join(["git", *args[:1]])
    try:
        completed = subprocess.run(
            ["git", *args], cwd=root, env=env, input=stdin, capture_output=True, timeout=GIT_TIMEOUT_SECONDS
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise GitCommandError(f"{command} could not run: {error}") from error
    if completed.returncode != 0:
        stderr = completed.stderr.decode("utf-8", errors="replace").strip()
        raise GitCommandError(stderr or f"{command} exited with {completed.returncode}")
    return completed.stdout


def run_git(args: list[str], root: Path, env: dict[str, str] | None = None, stdin: bytes | None = None) -> bytes | None:
    """Runs one Git command in a repository, with a timeout.

    Args:
        args: Git's arguments, without the leading ``git``; passed as an argument list, never
            through a shell.
        root: Directory Git runs in, inside the repository.
        env: Environment for Git; None inherits this process's.
        stdin: Bytes fed to Git's standard input; None feeds nothing.

    Returns:
        Git's standard output, or None when Git is missing, times out or exits with an error.
    """
    try:
        return run_git_checked(args, root, env, stdin)
    except GitCommandError:
        return None


def git_path(root: Path, name: str) -> Path | None:
    """Locates a file under the repository's Git directory, as ``git rev-parse --git-path`` does.

    Args:
        root: Directory inside the repository; a relative answer from Git is joined to it.
        name: Path inside the Git directory, such as ``index``.

    Returns:
        The file's path (it need not exist), or None outside a Git repository or when Git fails.
    """
    output = run_git(["rev-parse", "--git-path", name], root)
    if output is None:
        return None
    # Git answers relative to the directory it ran in, or absolute (linked worktrees).
    return root / output.decode("utf-8", errors="replace").strip()


def snapshot_tree(root: Path) -> str | None:
    """Records the working tree's current content as a Git tree object.

    Stages everything into a throwaway copy of the index, so only files whose stat data changed
    are hashed again.

    Args:
        root: Project root inside a Git repository.

    Returns:
        The tree SHA, or None outside a Git repository or when Git fails.
    """
    real_index = git_path(root, "index")
    if real_index is None:
        return None

    handle, temporary_index = tempfile.mkstemp(prefix="konundrm-index-")
    os.close(handle)
    try:
        if real_index.is_file():
            # copy2 keeps the index's mtime. Git compares it with each entry's mtime to spot "racily
            # clean" files edited in the same clock tick without a size change; a fresh mtime would
            # hide them and the snapshot would keep their old content.
            shutil.copy2(real_index, temporary_index)
        else:
            os.unlink(temporary_index)  # Git rejects an empty file but creates a missing index.
        env = {**os.environ, "GIT_INDEX_FILE": temporary_index}
        if run_git(["-c", "core.safecrlf=false", "add", "--all"], root, env) is None:
            return None
        tree = run_git(["write-tree"], root, env)
        if tree is None:
            return None
        return tree.decode("ascii", errors="replace").strip() or None
    except OSError:
        return None
    finally:
        for leftover in (temporary_index, f"{temporary_index}.lock"):
            with contextlib.suppress(OSError):
                os.unlink(leftover)


def head_tree(root: Path) -> str | None:
    """Returns the tree of the last commit, to compare a snapshot with what is committed.

    Args:
        root: Project root inside a Git repository.

    Returns:
        The tree SHA of HEAD; before the first commit, the empty tree (written to the object
        database, as Git does for an empty commit); None outside a Git repository.
    """
    tree = run_git(["rev-parse", "--verify", "--quiet", "HEAD^{tree}"], root)
    if tree is None:
        tree = run_git(["hash-object", "-t", "tree", "-w", "--stdin"], root, stdin=b"")
    if tree is None:
        return None
    return tree.decode("ascii", errors="replace").strip() or None


def changed_paths(root: Path, before: str, after: str) -> list[tuple[str, str]]:
    """Lists the files that differ between two snapshots.

    Args:
        root: Project root inside the Git repository that holds both snapshots.
        before: Earlier tree SHA from snapshot_tree().
        after: Later tree SHA from snapshot_tree().

    Returns:
        ``(status, path)`` pairs, where status is ``A`` (added), ``M`` (modified), ``D`` (deleted)
        or ``T`` (type changed) and path is relative to the root. Empty when nothing changed or
        Git fails.
    """
    if before == after:
        return []
    # --relative: when the project is a folder inside a larger repository (a monorepo package),
    # report only its files, relative to it, as the role rules and restore_paths expect.
    output = run_git(["diff-tree", "-r", "--relative", "--no-renames", "--name-status", "-z", before, after], root)
    if output is None:
        return []
    fields = output.decode("utf-8", errors="replace").split("\0")
    return [(fields[i][:1], fields[i + 1]) for i in range(0, len(fields) - 1, 2) if fields[i]]


@dataclass(frozen=True)
class AddedLine:
    """One line that exists in the later snapshot and not in the earlier one.

    Attributes:
        path: File path relative to the project root, with forward slashes.
        number: 1-based line number in the later version of the file.
        text: The line's content, without its newline.
    """

    path: str
    number: int
    text: str


def _diff_path(header: bytes) -> str | None:
    """Reads the path from a ``+++ b/<path>`` diff header; None for a deleted file."""
    # Git ends the header with a tab when the name contains a space.
    name = header[4:].rstrip(b"\r\n").removesuffix(b"\t")
    if name == b"/dev/null":
        return None
    if name.startswith(b'"') and name.endswith(b'"'):  # Git quotes paths with unusual characters
        name = name[1:-1].decode("unicode_escape").encode("latin-1")
    path = name.decode("utf-8", errors="replace")
    return path[2:] if path.startswith("b/") else path


def added_lines(root: Path, before: str, after: str) -> list[AddedLine]:
    """Lists the lines added between two snapshots, file by file.

    A modified line counts as added (its new version is new text); deleted lines are not listed,
    and neither are binary files.

    Args:
        root: Project root inside the Git repository that holds both snapshots.
        before: Earlier tree SHA (snapshot_tree() or head_tree()).
        after: Later tree SHA.

    Returns:
        The added lines in diff order. Empty when nothing was added or Git fails.
    """
    if before == after:
        return []
    options = ["-r", "-p", "-U0", "--relative", "--no-renames", "--no-color", "--no-ext-diff"]
    output = run_git(["-c", "core.quotepath=false", "diff-tree", *options, before, after], root)
    if output is None:
        return []
    lines: list[AddedLine] = []
    path: str | None = None
    number = 0
    in_header = False  # between "diff --git" and the first hunk, where "+++ b/<path>" lives
    for raw in output.splitlines():
        if raw.startswith(b"diff --git "):
            in_header, path, number = True, None, 0
        elif in_header and raw.startswith(b"+++ "):
            path = _diff_path(raw)
        elif raw.startswith(b"@@"):
            in_header = False
            match = HUNK_HEADER.match(raw)
            number = int(match.group(1)) if match else 0
        elif not in_header and raw.startswith(b"+") and path is not None and number:
            lines.append(AddedLine(path, number, raw[1:].decode("utf-8", errors="replace").rstrip("\r")))
            number += 1
    return lines


def restore_paths(root: Path, tree: str, changes: list[tuple[str, str]]) -> list[str]:
    """Undoes changes so each file matches an earlier snapshot again.

    Files added since the snapshot are deleted; modified, deleted or retyped files get their
    snapshot content back. The real index is not touched.

    Args:
        root: Project root inside the Git repository.
        tree: Tree SHA of the snapshot to go back to.
        changes: ``(status, path)`` pairs from changed_paths().

    Returns:
        The paths that could not be restored.
    """
    failed: list[str] = []
    to_checkout: list[str] = []
    for status, path in changes:
        if status == "A":
            try:
                (root / path).unlink()
            except FileNotFoundError:
                pass
            except OSError:
                failed.append(path)
        else:
            to_checkout.append(path)
    if to_checkout:
        pathspecs = [f":(literal){path}" for path in to_checkout]
        if run_git(["restore", f"--source={tree}", "--worktree", "--", *pathspecs], root) is None:
            failed.extend(to_checkout)
    return failed
