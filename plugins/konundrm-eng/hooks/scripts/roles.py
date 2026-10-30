"""konundrm-eng subagent roles and which files each role may change.

The main conversation (the orchestrator) and agents from other plugins are not restricted.
"""

from __future__ import annotations

from typing import Any

from file_kinds import is_feature_document, is_test_path
from hook_io import PLUGIN_NAME

READ_ONLY_ROLES = frozenset(
    {"spec-reviewer", "code-reviewer", "security-reviewer", "finding-verifier", "rethinker", "process-reviewer"}
)
ROLES = frozenset({"test-writer", "implementer"}) | READ_ONLY_ROLES


def agent_role(event: dict[str, Any]) -> str | None:
    """Maps the event's agent_type to a konundrm-eng role.

    Accepts the plugin-scoped form (``konundrm-eng:implementer``) and the bare form used when the
    agents are copied into a project's ``.claude/agents/``.

    Returns:
        The role name, or None for the main conversation and for unrelated agents.
    """
    agent_type = str(event.get("agent_type") or "")
    if not agent_type:
        return None
    scope, _, name = agent_type.rpartition(":")
    if scope not in ("", PLUGIN_NAME):
        return None
    return name if name in ROLES else None


def change_denial_reason(role: str | None, path: str) -> str | None:
    """Decides whether a role may create, edit or delete a file.

    Args:
        role: konundrm-eng role making the change, or None for the main conversation.
        path: Project-relative path of the file.

    Returns:
        The reason the change is not allowed, or None to allow it.
    """
    if role is None:
        return None
    if role in READ_ONLY_ROLES:
        return f"The {role} is read-only. Describe the problem in your report instead of changing {path}."
    if is_feature_document(path):
        return (
            f"Only the orchestrator changes the feature documents, and {path} is one. Describe the "
            "change the plan needs in your report instead."
        )
    if role == "test-writer" and not is_test_path(path):
        return (
            f"The test-writer may only create or edit test files (Standards → Tests), and {path} "
            "is not one. Describe the production change the test needs under 'To make it pass' "
            "in your RED report instead."
        )
    if role == "implementer" and is_test_path(path):
        return (
            f"The implementer may not edit test files, and {path} is one. If the test is wrong, "
            "return Status: BLOCKED with the reason so the orchestrator routes it to the test-writer."
        )
    return None
