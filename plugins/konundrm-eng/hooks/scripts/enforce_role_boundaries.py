"""PreToolUse hook on Edit, Write, MultiEdit and NotebookEdit: keeps subagents inside their role.

It denies an edit to a file the subagent's role may not change, before the edit happens. This is
the fast-feedback path for the rules in roles.py. Changes made any other way (Bash, a script, a
generator) are caught when the subagent stops, by audit_subagent_changes.py.
"""

from __future__ import annotations

import sys
from pathlib import PurePosixPath

from hook_io import deny_tool_use, read_hook_input
from project_paths import project_root, relative_path
from roles import agent_role, change_denial_reason


def main() -> int:
    """Runs the hook for a PreToolUse event read from stdin."""
    event = read_hook_input()
    role = agent_role(event)
    if role is None:
        return 0
    tool_input = event.get("tool_input") or {}
    path = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not path:
        return 0
    project_path = relative_path(str(path), project_root(event)) or PurePosixPath(str(path)).name
    reason = change_denial_reason(role, project_path)
    if reason:
        deny_tool_use(reason)
    return 0


if __name__ == "__main__":
    sys.exit(main())
