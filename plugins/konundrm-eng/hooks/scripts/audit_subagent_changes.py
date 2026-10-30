"""SubagentStart and SubagentStop hook: audits what each konundrm-eng subagent actually changed.

At start it snapshots the working tree and remembers which project root it snapshotted. At stop it
compares that same root with the snapshot and checks every changed file against the role's rules
(roles.py), whatever tool made the change: Edit, Bash, a script or a generator. The first time it
finds a violation it blocks the stop and tells the subagent how to put those files back. If the
subagent stops again with the violation still there, the hook restores the files itself and warns
the person.

The stop never resolves the root again from its own event: a session can work in a linked worktree
that shares the repository's objects with the main checkout, so comparing one checkout with the
other's snapshot would see every difference between them as the subagent's change and restore or
delete files in the wrong tree.

Changes are attributed to a subagent by time, so konundrm-eng subagents must run one at a time on
a working tree; develop-feature already works that way.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from file_kinds import is_tool_artifact
from hook_io import block_stop, read_hook_input, warn_user
from hook_state import SubagentRecord
from metrics_log import record_event
from project_paths import project_root
from roles import agent_role, change_denial_reason
from working_tree import changed_paths, restore_paths, snapshot_tree

MAX_BLOCKS = 1
STATUS_NAMES = {"A": "created", "M": "modified", "D": "deleted", "T": "changed type"}


@dataclass(frozen=True)
class Violation:
    """One file a subagent changed although its role may not change it."""

    status: str
    path: str
    reason: str


def find_violations(role: str, changes: list[tuple[str, str]]) -> list[Violation]:
    """Keeps the changes the role was not allowed to make.

    Args:
        role: The subagent's konundrm-eng role.
        changes: ``(status, path)`` pairs from working_tree.changed_paths().

    Returns:
        One Violation per offending file; tool artifacts such as caches are never violations.
    """
    violations = []
    for status, path in changes:
        if is_tool_artifact(path):
            continue
        reason = change_denial_reason(role, path)
        if reason:
            violations.append(Violation(status, path, reason))
    return violations


def restore_instructions(role: str, tree: str, violations: list[Violation]) -> str:
    """Builds the message that asks a subagent to undo the changes outside its role."""
    listed = "\n".join(f"- {v.path} ({STATUS_NAMES.get(v.status, v.status)}): {v.reason}" for v in violations)
    commands = "\n".join(
        f'  rm -- "{v.path}"' if v.status == "A" else f'  git restore --source={tree} --worktree -- "{v.path}"'
        for v in violations
    )
    return (
        f"You changed files your role ({role}) may not change:\n{listed}\n\n"
        "Put each one back exactly as it was when you started, then finish again and mention this "
        f"in your report:\n{commands}"
    )


def on_start(event: dict[str, Any]) -> int:
    """Snapshots the working tree when a konundrm-eng subagent starts and records which root it snapshotted."""
    role = agent_role(event)
    agent_id = event.get("agent_id")
    if role is None or not agent_id:
        return 0
    root = project_root(event)
    tree = snapshot_tree(root)
    if tree is None:
        return 0
    record = SubagentRecord(event.get("session_id"), str(agent_id))
    record.role, record.root, record.before_tree, record.blocks = role, str(root), tree, 0
    record.save()
    return 0


def on_stop(event: dict[str, Any]) -> int:
    """Blocks, then reverts, changes a stopping subagent made outside its role.

    Compares and restores only in the root the subagent's start snapshotted. A record without that
    root (written by a plugin version before the upgrade) is unauditable: it is dropped and nothing
    is checked, because guessing the root from this event could restore files in another checkout.
    When the stored root is gone or no longer a Git tree, no snapshot is taken and nothing changes.
    """
    agent_id = event.get("agent_id")
    if not agent_id:
        return 0
    record = SubagentRecord(event.get("session_id"), str(agent_id))
    if not record.role or not record.before_tree:
        return 0
    if not record.root:
        record.delete()
        return 0
    root = Path(record.root)
    after = snapshot_tree(root)
    violations = [] if after is None else find_violations(record.role, changed_paths(root, record.before_tree, after))
    if not violations:
        record.delete()
        return 0

    session_id = event.get("session_id")
    if record.blocks >= MAX_BLOCKS or event.get("stop_hook_active"):
        failed = restore_paths(root, record.before_tree, [(v.status, v.path) for v in violations])
        record.delete()
        restored = [v.path for v in violations if v.path not in failed]
        record_event(root, "role_restored", session_id, role=record.role, paths=restored, failed=failed)
        message = f"konundrm-eng: the {record.role} changed files its role may not change."
        if restored:
            message += f" Restored to their state when it started: {', '.join(restored)}."
        if failed:
            message += f" Could not restore: {', '.join(failed)}; check them by hand."
        warn_user(message)
        return 0

    record.blocks += 1
    record.save()
    record_event(root, "role_violation", session_id, role=record.role, paths=[v.path for v in violations])
    block_stop(restore_instructions(record.role, record.before_tree, violations))
    return 0


def main() -> int:
    """Runs the hook for a SubagentStart or SubagentStop event read from stdin."""
    event = read_hook_input()
    if event.get("hook_event_name") == "SubagentStart":
        return on_start(event)
    return on_stop(event)


if __name__ == "__main__":
    sys.exit(main())
