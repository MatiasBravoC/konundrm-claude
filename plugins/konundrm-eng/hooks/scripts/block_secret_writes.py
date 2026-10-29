"""PreToolUse hook on Edit, Write, MultiEdit and NotebookEdit: credentials stay out of files.

Before any agent, the main conversation included, writes content that contains what looks like a
real credential (secret_patterns.py), it pauses the edit and asks the person. Secrets belong in
the environment or a secret manager (Standards → Security); only the person can say that a value
is a deliberately fake test value. Files the tools write as a side effect are not checked. The
commit gate checks the same patterns again for content that reached a file another way (Bash,
a generator).

Sections:
    written_text()  — the text a tool call would write.
    main()          — the hook.
"""

from __future__ import annotations

import sys
from pathlib import PurePosixPath
from typing import Any

from hook_io import ask_before_tool_use, read_hook_input


def written_text(tool_input: dict[str, Any]) -> str:
    """Collects the text an Edit, Write, MultiEdit or NotebookEdit call would put in a file.

    Args:
        tool_input: The tool call's input from the hook event.

    Returns:
        The new text joined by newlines; empty when the call writes none.
    """
    pieces = [tool_input.get(key) for key in ("content", "new_string", "new_source")]
    edits = tool_input.get("edits")
    if isinstance(edits, list):
        pieces.extend(edit.get("new_string") for edit in edits if isinstance(edit, dict))
    return "\n".join(piece for piece in pieces if isinstance(piece, str))


def main() -> int:
    """Runs the hook for a PreToolUse event read from stdin."""
    event = read_hook_input()
    tool_input = event.get("tool_input") or {}
    text = written_text(tool_input)
    if not text:
        return 0
    # Runs before every edit: scan first, and pay for Git and the project lookup only on a match.
    from secret_patterns import describe, find_secrets

    if not find_secrets(text):
        return 0
    from file_kinds import is_tool_artifact
    from metrics_log import record_event
    from project_paths import project_root, relative_path

    root = project_root(event)
    path = str(tool_input.get("file_path") or tool_input.get("notebook_path") or "")
    shown_path = (relative_path(path, root) or PurePosixPath(path.replace("\\", "/")).name) if path else ""
    if shown_path and is_tool_artifact(shown_path):
        return 0
    matches = find_secrets(text, shown_path)

    record_event(root, "secret_flagged", event.get("session_id"), where="edit", count=len(matches))
    ask_before_tool_use(
        "konundrm-eng: this edit writes what looks like a real credential:\n"
        f"{describe(matches)}\n\nSecrets come only from the environment or a secret manager "
        "(Standards → Security): read them with an environment variable and keep a placeholder in "
        "examples. Approve only if every value is a deliberately fake test value."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
