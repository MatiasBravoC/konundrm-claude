"""PostToolUse hook on Bash and PowerShell: remembers that the project's check just passed.

When Claude (or a subagent) runs the check command itself and it succeeds, the commit gate and the
stop gate reuse that result for the same tree content instead of running the whole check again.
Claude Code reports failing commands as PostToolUseFailure, which this hook never receives; as a
second guard it also ignores interrupted and background runs and any reported non-zero exit code.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from hook_io import read_hook_input

# Runs after every Bash command; the state, Git and check modules load only for a check command.
EXIT_CODE_FIELDS = ("exit_code", "exitCode", "returnCode", "return_code")


def succeeded(event: dict[str, Any]) -> bool:
    """Tells whether a PostToolUse event describes a command that finished with exit code 0."""
    if event.get("hook_event_name") not in (None, "PostToolUse"):
        return False
    if (event.get("tool_input") or {}).get("run_in_background"):
        return False
    response = event.get("tool_response")
    if not isinstance(response, dict):
        return True
    if response.get("interrupted") or response.get("backgroundTaskId"):
        return False
    return all(response.get(name) in (None, 0) for name in EXIT_CODE_FIELDS)


def main() -> int:
    """Runs the hook for a PostToolUse event read from stdin."""
    event = read_hook_input()
    command = str((event.get("tool_input") or {}).get("command") or "")
    # Cheap filter first: every discovered check command contains "check".
    if not command or ("check" not in command and not os.environ.get("KONUNDRM_CHECK_CMD")):
        return 0
    if not succeeded(event):
        return 0
    from hook_state import SessionState
    from project_paths import project_root
    from quality_check import find_check_command, is_check_invocation
    from working_tree import snapshot_tree

    root = project_root(event)
    check = find_check_command(root)
    if check is None or not is_check_invocation(command, check, root, Path(event.get("cwd") or root)):
        return 0
    state = SessionState(event.get("session_id"))
    state.mark_green(snapshot_tree(root))
    state.save()
    return 0


if __name__ == "__main__":
    sys.exit(main())
