"""UserPromptSubmit and Stop hook: a turn that changed code cannot end on a red or silenced tree.

When a turn begins it snapshots the working tree. When the turn ends it compares: if any code or
configuration changed during the turn, through Edit, Bash, a generator or anything else, it runs
the project's check, reusing a green result for the same tree content, and looks for gate
silencers the turn added without their reason (suppressions.py). On either problem it blocks the
stop, so Claude keeps working with the details. Two escape valves keep it from trapping
deliberate stops: a final message with a line starting with ``RED:`` (test-driven-development
handoff) or ``BLOCKED:`` (escalation to the user), Markdown decoration allowed (deliberate_stops.py),
and a cap of MAX_CONSECUTIVE_BLOCKS attempts
after which the turn ends with a visible warning. Outside a Git repository it falls back to the
edits that format_and_lint.py recorded, and cannot see silencers.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from deliberate_stops import find_deliberate_stop
from file_kinds import is_documentation_path, is_tool_artifact
from hook_io import block_stop, read_hook_input, warn_user
from hook_state import SessionState
from metrics_log import record_event
from project_paths import project_root
from quality_check import find_check_command, gates_disabled, run_check
from suppressions import Suppression, describe, find_unjustified
from working_tree import added_lines, changed_paths, snapshot_tree

MAX_CONSECUTIVE_BLOCKS = 3


def is_deliberate_red_stop(last_message: str) -> bool:
    """Tells whether the final message hands off on purpose while the tree is red.

    It does when one of its lines is a ``RED:`` or ``BLOCKED:`` stop line as deliberate_stops
    reads it, Markdown decoration allowed.
    """
    return find_deliberate_stop(last_message or "") is not None


def turn_changed_code(state: SessionState, root: Path, current_tree: str | None) -> bool:
    """Tells whether this turn changed anything the check covers.

    Documentation and tool artifacts (caches, coverage files) do not count.
    """
    if state.turn_start_tree is None or current_tree is None:
        return state.dirty
    return any(
        not is_documentation_path(path) and not is_tool_artifact(path)
        for _, path in changed_paths(root, state.turn_start_tree, current_tree)
    )


def turn_silencers(state: SessionState, root: Path, current_tree: str | None) -> list[Suppression]:
    """Lists the gate silencers this turn added without their reason (empty without snapshots)."""
    if state.turn_start_tree is None or current_tree is None:
        return []
    return find_unjustified(added_lines(root, state.turn_start_tree, current_tree))


def on_prompt(event: dict[str, Any]) -> int:
    """Snapshots the working tree as the turn begins."""
    state = SessionState(event.get("session_id"))
    state.start_turn(snapshot_tree(project_root(event)))
    state.save()
    return 0


def _problems(root: Path, state: SessionState, current_tree: str | None) -> tuple[list[str], list[str]]:
    """Runs the check and the silencer scan for a turn that changed code.

    Returns:
        The problem descriptions for Claude, and their short names for the metrics log.
    """
    problems, kinds = [], []
    check = find_check_command(root)
    if check is not None:
        result = run_check(root, check, state, current_tree)
        if not result.passed:
            problems.append(f"Quality gate failed: `{check}` exited {result.exit_code}.\n\n{result.output_tail}")
            kinds.append("red_check")
    silencers = turn_silencers(state, root, current_tree)
    if silencers:
        problems.append(
            "This turn silenced a gate without saying why (Standards → Gate integrity):\n"
            f"{describe(silencers)}\nFix what each one hides and remove it, or give it its reason on the "
            "same line in the tool's own syntax. Focused tests (`.only`) are never kept."
        )
        kinds.append("suppression")
    return problems, kinds


def on_stop(event: dict[str, Any]) -> int:
    """Keeps Claude working while a turn that changed code leaves the check red or a gate silenced."""
    if gates_disabled():
        return 0
    root = project_root(event)
    state = SessionState(event.get("session_id"))
    current_tree = snapshot_tree(root)
    if not turn_changed_code(state, root, current_tree):
        return 0
    problems, kinds = _problems(root, state, current_tree)
    if not problems:
        return 0

    if is_deliberate_red_stop(str(event.get("last_assistant_message") or "")):
        state.stop_blocks = 0
        state.save()
        return 0

    if state.stop_blocks >= MAX_CONSECUTIVE_BLOCKS:
        state.stop_blocks = 0
        state.save()
        record_event(root, "stop_gave_up", event.get("session_id"), reason="+".join(kinds))
        warn_user(
            f"konundrm-eng: the turn ended after {MAX_CONSECUTIVE_BLOCKS} attempts with problems left "
            f"({', '.join(kinds)}): the tree is red or a gate is silenced."
        )
        return 0

    state.stop_blocks += 1
    state.save()
    record_event(root, "stop_blocked", event.get("session_id"), attempt=state.stop_blocks, reason="+".join(kinds))
    block_stop(
        f"Attempt {state.stop_blocks} of {MAX_CONSECUTIVE_BLOCKS}: fix these before finishing. Only if "
        "you are deliberately stopping, add a line starting with 'RED:' (TDD handoff) or 'BLOCKED:' "
        "(question for the user) that explains why.\n\n" + "\n\n".join(problems)
    )
    return 0


def main() -> int:
    """Runs the hook for a UserPromptSubmit or Stop event read from stdin."""
    event = read_hook_input()
    if event.get("hook_event_name") == "UserPromptSubmit":
        return on_prompt(event)
    return on_stop(event)


if __name__ == "__main__":
    sys.exit(main())
