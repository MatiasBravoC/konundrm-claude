"""Locates the project a hook event belongs to and expresses tool paths relative to it."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path, PurePosixPath
from typing import Any


def project_root(event: dict[str, Any]) -> Path:
    """Resolves the project directory for a hook event.

    Prefers CLAUDE_PROJECT_DIR, then the Git top level of the event's cwd, then the cwd itself.
    """
    configured = os.environ.get("CLAUDE_PROJECT_DIR")
    if configured:
        return Path(configured)
    cwd = Path(event.get("cwd") or os.getcwd())
    try:
        top = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return cwd
    return Path(top.stdout.strip()) if top.returncode == 0 and top.stdout.strip() else cwd


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
