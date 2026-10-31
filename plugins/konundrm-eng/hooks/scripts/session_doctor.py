"""SessionStart hook: checks what the konundrm-eng gates need and tells Claude where things stand.

Warns the person when Git is missing or when the account-level skills this plugin replaced are
still installed, since Claude would then choose between two versions of each skill. Adds context
for Claude: the project's check command, the same one every hook runs, and the features in
progress under specs/ with their next task, or the next task of each partition of the wave in
progress while a slice's partitions run in parallel. The hook runs on every session start, including the
one after a compaction, so a long develop-feature run finds its place again. A missing Python is
reported by run.sh, which cannot start this script without one.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from hook_io import emit_json, read_hook_input
from project_paths import project_root
from quality_check import find_check_command, gates_disabled
from tasks_document import TasksDocument, next_tasks, read_tasks

LEGACY_SKILLS = ("deployer", "documentator", "engineer", "mapper", "tdd", "tester")
MAX_FEATURES_SHOWN = 3


def claude_config_directory() -> Path:
    """Returns the directory that holds the person's Claude Code configuration and skills."""
    configured = os.environ.get("CLAUDE_CONFIG_DIR")
    return Path(configured) if configured else Path.home() / ".claude"


def installed_legacy_skills(config_directory: Path) -> list[str]:
    """Lists the replaced account-level skills that are still installed."""
    skills = config_directory / "skills"
    return [name for name in LEGACY_SKILLS if (skills / name / "SKILL.md").is_file()]


def environment_warnings(config_directory: Path) -> list[str]:
    """Collects the problems the person should fix for the gates to work as documented."""
    warnings = []
    if shutil.which("git") is None:
        warnings.append("Git is not on PATH, so the commit gate, the stop gate and the subagent audit are off.")
    legacy = installed_legacy_skills(config_directory)
    if legacy:
        folders = ", ".join(legacy)
        warnings.append(
            f"The skills {folders} in {config_directory / 'skills'} were replaced by this plugin. "
            "Move those folders out of that directory (and turn off their copies in claude.ai) so "
            "Claude does not choose between two versions."
        )
    return warnings


def check_command_context(check: str | None) -> str:
    """Describes the project's check command for Claude."""
    if gates_disabled():
        return "konundrm-eng: quality gates are off in this session (KONUNDRM_GATE=off)."
    if check is None:
        return (
            "konundrm-eng: this project has no check command, so the quality gates do nothing here. "
            "/konundrm-eng:setup-project creates one."
        )
    return (
        f"konundrm-eng: this project's check command is `{check}`. The commit gate and the stop "
        "gate run this same command; use it wherever a skill says 'the check command'."
    )


def next_step(document: TasksDocument) -> str:
    """Describes where a feature resumes: its next task, or each partition's while they run in parallel.

    Args:
        document: The feature's parsed tasks.md.

    Returns:
        ``next per partition: P1 T3, P2 T2`` when tasks_document.next_tasks, counting checked
        boxes as built, returns one task per partition of the wave in progress; otherwise
        ``next T<n>: <title>`` for the first unchecked task, or the finish-phase text when every
        box is checked.
    """
    resume_tasks = next_tasks(document, {task.id for task in document.tasks if task.done})
    if not resume_tasks:
        return "every box checked; the finish phase is left"
    if len(resume_tasks) > 1:
        return "next per partition: " + ", ".join(f"{task.partition} {task.id}" for task in resume_tasks)
    return f"next {resume_tasks[0].id}: {resume_tasks[0].title}"


def feature_progress_context(root: Path) -> str | None:
    """Describes the features whose plan is approved and not done yet, with each one's next task.

    Returns:
        One paragraph for Claude, or None when no feature is in progress.
    """
    lines = []
    for tasks_file in sorted(root.glob("specs/*/tasks.md")):
        document = read_tasks(tasks_file)
        if document.status.lower() != "approved" or not document.tasks:
            continue
        done = sum(task.done for task in document.tasks)
        lines.append(
            f"- specs/{tasks_file.parent.name}: {done} of {len(document.tasks)} tasks checked, {next_step(document)}"
        )
    if not lines:
        return None
    shown = lines[:MAX_FEATURES_SHOWN] + (
        [f"- … and {len(lines) - MAX_FEATURES_SHOWN} more"] if lines[MAX_FEATURES_SHOWN:] else []
    )
    return (
        "konundrm-eng: features in progress (resume one with /konundrm-eng:develop-feature <its folder>; a "
        "checked box counts only when its `Task: T<n>` commit exists):\n" + "\n".join(shown)
    )


def main() -> int:
    """Runs the hook for a SessionStart event read from stdin."""
    event = read_hook_input()
    root = project_root(event)
    context = [check_command_context(find_check_command(root)), feature_progress_context(root)]
    payload: dict[str, object] = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": "\n\n".join(part for part in context if part),
        }
    }
    warnings = environment_warnings(claude_config_directory())
    if warnings:
        payload["systemMessage"] = "konundrm-eng: " + " ".join(warnings)
    emit_json(payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
