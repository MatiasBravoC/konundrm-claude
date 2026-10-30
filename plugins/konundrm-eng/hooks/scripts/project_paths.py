"""Locates the project a hook event belongs to and expresses tool paths relative to it."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path, PurePosixPath
from typing import Any, NamedTuple

_GIT_TIMEOUT_SECONDS = 10


class _GitLocation(NamedTuple):
    """Where a folder sits in Git: its checkout's Git directory, the repository's shared one, and the checkout's top."""

    git_dir: Path
    common_dir: Path
    top_level: Path


def project_root(event: dict[str, Any]) -> Path:
    """Resolves the project directory for a hook event.

    When CLAUDE_PROJECT_DIR is set, the root is the top level of the linked worktree (one added
    with `git worktree add`, never the main checkout) that contains the event's cwd, provided
    that worktree belongs to the same repository as CLAUDE_PROJECT_DIR and is a different
    checkout from the one holding it; in every other case it is CLAUDE_PROJECT_DIR. When that
    variable is unset, the root is the Git top level of the cwd, or else the cwd itself. Any Git
    failure (missing, timed out, not a repository) falls through to the next option.

    Args:
        event: Hook event; its optional "cwd" is the session's working directory.

    Returns:
        The project root directory.

    Side effects:
        Runs `git rev-parse` (at most twice, each bounded by a timeout).
    """
    cwd = Path(event.get("cwd") or os.getcwd())
    configured = os.environ.get("CLAUDE_PROJECT_DIR")
    if configured:
        return _worktree_of_same_repository(cwd, Path(configured)) or Path(configured)
    location = _git_location(cwd)
    return location.top_level if location else cwd


def _worktree_of_same_repository(cwd: Path, configured: Path) -> Path | None:
    """Returns the linked worktree containing cwd when it shares configured's repository but is another checkout.

    A checkout is linked when its Git directory differs from the repository's common directory;
    the main checkout is never returned, so a cwd there keeps configured as the root. The two
    checkouts are told apart by their top levels, not by comparing cwd's top level with
    configured itself, because configured may be a package folder inside its checkout (a monorepo).
    """
    cwd_location = _git_location(cwd)
    if cwd_location is None:
        return None
    is_linked = not _same_path(cwd_location.git_dir, cwd_location.common_dir)
    if not is_linked or _same_path(cwd_location.top_level, configured):
        return None  # Main checkout, or configured tops cwd's own checkout: skip the second call.
    configured_location = _git_location(configured)
    if configured_location is None:
        return None
    is_same_repository = _same_path(configured_location.common_dir, cwd_location.common_dir)
    is_other_checkout = not _same_path(configured_location.top_level, cwd_location.top_level)
    return cwd_location.top_level if is_same_repository and is_other_checkout else None


def _git_location(directory: Path) -> _GitLocation | None:
    """Returns where directory sits in Git, with absolute paths, or None outside Git."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--git-dir", "--git-common-dir", "--show-toplevel"],
            cwd=directory,
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    lines = result.stdout.splitlines()
    if result.returncode != 0 or len(lines) != 3 or not all(lines):
        return None
    # Git may print both directories relative to the cwd; resolve them here.
    return _GitLocation(directory / lines[0], directory / lines[1], Path(lines[2]))


def _same_path(first: Path, second: Path) -> bool:
    """Tells whether two paths name the same location, ignoring case and short-name differences."""
    try:
        return os.path.normcase(first.resolve()) == os.path.normcase(second.resolve())
    except OSError:
        return False


def relative_path(path: str, root: Path) -> str | None:
    """Expresses a tool path relative to the project root, with forward slashes.

    Args:
        path: Absolute or project-relative path from a tool call.
        root: Project root directory.

    Returns:
        The relative POSIX path, or None when the path lies outside the project.
    """
    candidate = Path(path)
    if not candidate.is_absolute():
        return PurePosixPath(path.replace("\\", "/")).as_posix()
    try:
        return candidate.resolve().relative_to(root.resolve()).as_posix()
    except (ValueError, OSError):
        return None
