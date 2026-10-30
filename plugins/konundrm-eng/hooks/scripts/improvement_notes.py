"""Appends a slice's or feature's improvement notes to the plugin's central notes file.

The file lives at a fixed path inside Claude's configuration folder and is shared by every
project, so the project and feature names only ever go into its content, each on one line, and
never into the path.

Sections:
    NOTES_FILE     — where the notes file lives, relative to Claude's configuration folder.
    append_notes() — adds one dated entry tagged with project, feature and scope.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

NOTES_FILE = Path("konundrm-eng") / "improvements.md"


def append_notes(
    notes: str,
    *,
    project: str,
    feature: str,
    scope: str,
    today: date,
    config_dir: Path,
    fallback_dir: Path,
) -> tuple[Path, bool]:
    """Adds one dated entry with the notes to the end of the central notes file.

    Earlier content is never erased or changed. Project, feature and scope are written on a
    single line each (any line break or run of whitespace becomes one space), so a hostile name
    can neither change the path nor forge a new line in the file.

    Args:
        notes: Text of the notes, written as given.
        project: Name of the project the notes come from.
        feature: Name of the feature the notes are about.
        scope: What the notes cover, such as "slice 2" or "feature".
        today: Date stamped on the entry.
        config_dir: Claude's configuration folder; the file is ``config_dir / NOTES_FILE``.
        fallback_dir: Folder for the notes when the central file cannot be written (not used yet).

    Returns:
        The path written to and whether it was the fallback.

    Raises:
        OSError: If the folder or the file cannot be created or written.

    Side effects:
        Creates ``config_dir / NOTES_FILE`` and its folder when missing, then appends to it.
    """
    del fallback_dir  # the fallback arrives with T48
    path = config_dir / NOTES_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = (
        f"\n## {today.isoformat()} · {_single_line(scope)}\n\n"
        f"- Project: {_single_line(project)}\n"
        f"- Feature: {_single_line(feature)}\n\n"
        f"{notes.rstrip()}\n"
    )
    with path.open("a", encoding="utf-8", newline="\n") as notes_file:
        notes_file.write(entry)
    return path, False


def _single_line(value: str) -> str:
    return " ".join(value.split())
