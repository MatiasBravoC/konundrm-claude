"""PreToolUse hook on Bash and PowerShell: a commit happens only on a green, honest quality gate.

Denies commits that bypass Git hooks (--no-verify or any abbreviation of it, -n, HUSKY=0, SKIP=,
LEFTHOOK=0, core.hooksPath, GIT_CONFIG_* overrides), denies commits from konundrm-eng subagents
(only the orchestrator commits), denies commits whose uncommitted changes add a gate silencer
without its reason (suppressions.py), asks the person about anything that looks like a real
credential (secret_patterns.py), and runs the project's check command before any other commit,
reusing a green result for the same tree content. Commits are found by shell_commands.py, so a
commit behind a wrapper or inside ``bash -c`` is still a commit. It is a guardrail, not a sandbox:
a script can still call Git in ways no parser sees, which is why the Git pre-commit hook and CI run
the same check. It fails closed: if the hook itself breaks while handling a commit, it denies it.

Sections:
    CommitCall, find_commit_calls() — every ``git commit`` in a command line.
    bypass_reason()                 — how a commit would skip the Git hooks.
    gate_commit()                   — the decision for a command that commits.
    main()                          — the hook.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from hook_io import ask_before_tool_use, deny_tool_use, read_hook_input
from shell_commands import iter_commands

# Runs before every Bash command and few are commits, so the gate's modules load only for one.
GIT_OPTIONS_WITH_VALUE = frozenset({"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path"})
COMMIT_SHORT_OPTIONS_WITH_VALUE = frozenset("mFcCt")
COMMIT_SHORT_OPTIONS_ATTACHED_VALUE = frozenset("Su")
COMMIT_LONG_OPTIONS_WITH_VALUE = frozenset(
    {
        "--message",
        "--file",
        "--template",
        "--reuse-message",
        "--reedit-message",
        "--fixup",
        "--squash",
        "--author",
        "--date",
        "--cleanup",
        "--trailer",
        "--pathspec-from-file",
    }
)
# Git accepts any unambiguous prefix of a long option; "--no-ver" is ambiguous with --no-verbose.
NO_VERIFY = "--no-verify"
SHORTEST_NO_VERIFY_PREFIX = "--no-veri"
# When the command cannot even be parsed, any mention of a commit is treated as one.
COMMIT_WORD = re.compile(r"\bcommit\b")


@dataclass
class CommitCall:
    """One ``git commit`` invocation found in a shell command line."""

    env: list[str] = field(default_factory=list)
    git_options: list[str] = field(default_factory=list)
    arguments: list[str] = field(default_factory=list)


def _git_commit_call(arguments: list[str], env: list[str]) -> CommitCall | None:
    """Reads ``[options] commit [arguments]`` from a git command's arguments, if it is a commit."""
    index, git_options = 0, []
    while index < len(arguments) and arguments[index].startswith("-"):
        width = 2 if arguments[index] in GIT_OPTIONS_WITH_VALUE else 1
        git_options.extend(arguments[index : index + width])
        index += width
    if index < len(arguments) and arguments[index] == "commit":
        return CommitCall(env=env, git_options=git_options, arguments=arguments[index + 1 :])
    return None


def find_commit_calls(command: str) -> Iterator[CommitCall]:
    """Finds every ``git commit`` in a command line, including wrapped and nested ones.

    Args:
        command: The command string Claude is about to run.

    Yields:
        One CommitCall per commit invocation, with the environment assignments that apply to it.
    """
    for shell_command in iter_commands(command):
        if shell_command.program == "git":
            call = _git_commit_call(list(shell_command.arguments), list(shell_command.env))
            if call is not None:
                yield call


def _environment_bypass(assignment: str) -> str | None:
    name, _, value = assignment.partition("=")
    name, value = name.upper(), value.strip()
    if name == "HUSKY" and value == "0":
        return "HUSKY=0 disables the Git hooks"
    if name == "HUSKY_SKIP_HOOKS" and value not in ("", "0"):
        return "HUSKY_SKIP_HOOKS disables the Git hooks"
    if name == "LEFTHOOK" and value == "0":
        return "LEFTHOOK=0 disables the Git hooks"
    if name == "SKIP" and value:
        return "SKIP= skips pre-commit hooks"
    if name.startswith("GIT_CONFIG"):
        return f"{name} overrides Git configuration, which can disable the hooks"
    return None


def _short_options(cluster: str) -> tuple[bool, bool]:
    """Reads a cluster of short commit options such as ``-anm``.

    Returns:
        Whether the cluster includes ``-n``, and whether the next argument is an option's value.
    """
    for position, flag in enumerate(cluster[1:], start=1):
        if flag == "n":
            return True, False
        if flag in COMMIT_SHORT_OPTIONS_ATTACHED_VALUE:
            return False, False
        if flag in COMMIT_SHORT_OPTIONS_WITH_VALUE:
            return False, position == len(cluster) - 1
    return False, False


def _argument_bypass(arguments: list[str]) -> str | None:
    remaining = iter(arguments)
    for argument in remaining:
        if argument == "--":
            break
        if argument.startswith("--"):
            if (
                "=" not in argument
                and len(argument) >= len(SHORTEST_NO_VERIFY_PREFIX)
                and NO_VERIFY.startswith(argument)
            ):
                return f"{argument} (--no-verify) skips the Git hooks"
            if argument in COMMIT_LONG_OPTIONS_WITH_VALUE:
                next(remaining, None)
        elif argument.startswith("-") and len(argument) > 1:
            has_no_verify, value_follows = _short_options(argument)
            if has_no_verify:
                return "-n (--no-verify) skips the Git hooks"
            if value_follows:
                next(remaining, None)
    return None


def bypass_reason(call: CommitCall) -> str | None:
    """Explains how a commit would skip the Git hooks, or returns None if it would not."""
    for assignment in call.env:
        reason = _environment_bypass(assignment)
        if reason:
            return reason
    if any("core.hookspath" in option.lower() for option in call.git_options):
        return "overriding core.hooksPath disables the Git hooks"
    return _argument_bypass(call.arguments)


def _content_findings(root: Path, session_id: str | None, tree: str | None) -> bool:
    """Denies or asks about what the uncommitted changes add; True when it decided.

    Silencers without a reason are denied: the fix is to remove them or write the reason. A value
    that looks like a credential is asked about, because only the person knows whether it is a
    deliberately fake test value.
    """
    import secret_patterns
    import suppressions
    from metrics_log import record_event
    from working_tree import added_lines, head_tree

    base = head_tree(root)
    if tree is None or base is None:
        return False
    lines = added_lines(root, base, tree)
    silencers, secrets = suppressions.find_unjustified(lines), secret_patterns.find_secrets_in_lines(lines)
    if silencers:
        record_event(root, "commit_denied", session_id, reason="suppression", count=len(silencers))
        also = f"\n\nIt also adds what looks like a credential:\n{secret_patterns.describe(secrets)}" if secrets else ""
        deny_tool_use(
            "Blocked: these changes silence a gate without saying why (Standards → Gate integrity):\n"
            f"{suppressions.describe(silencers)}\n\nFix what each one hides and remove it, or keep it with "
            "its reason on the same line in the tool's own syntax (`# noqa: S603 - why`, "
            '`// eslint-disable-next-line rule -- why`, `@pytest.mark.skip(reason="why")`). A focused '
            f"test (`.only`) is never committed.{also}"
        )
        return True
    if secrets:
        record_event(root, "secret_flagged", session_id, where="commit", count=len(secrets))
        ask_before_tool_use(
            "konundrm-eng: these changes add what looks like a real credential:\n"
            f"{secret_patterns.describe(secrets)}\n\nSecrets come only from the environment or a secret "
            "manager (Standards → Security). Approve only if every value is a deliberately fake test value."
        )
        return True
    return False


def gate_commit(event: dict[str, Any], calls: list[CommitCall]) -> None:
    """Decides on a command line that commits: deny, ask, or let it run (no output)."""
    from hook_state import SessionState
    from metrics_log import record_event
    from project_paths import project_root
    from quality_check import find_check_command, gates_disabled, run_check
    from roles import agent_role
    from working_tree import snapshot_tree

    root = project_root(event)
    session_id = event.get("session_id")

    for call in calls:
        reason = bypass_reason(call)
        if reason:
            record_event(root, "commit_denied", session_id, reason="bypass", detail=reason)
            deny_tool_use(f"Blocked: {reason}. Fix what the hook reports instead of bypassing it (Standards → Git).")
            return

    role = agent_role(event)
    if role is not None:
        record_event(root, "commit_denied", session_id, reason="subagent", role=role)
        deny_tool_use(f"The {role} does not commit. Return your report; the orchestrator commits each task.")
        return

    if gates_disabled():
        return
    tree = snapshot_tree(root)
    if _content_findings(root, session_id, tree):
        return
    check = find_check_command(root)
    if check is None:
        return

    result = run_check(root, check, SessionState(session_id), tree)
    if not result.passed:
        record_event(root, "commit_denied", session_id, reason="red_check", exit_code=result.exit_code)
        deny_tool_use(
            f"Quality gate failed: `{check}` exited {result.exit_code}. Commit only on green "
            f"(Standards → Definition of Done). Fix the failures, then commit again.\n\n{result.output_tail}"
        )


def main() -> int:
    """Runs the hook for a PreToolUse event read from stdin."""
    event = read_hook_input()
    command = str((event.get("tool_input") or {}).get("command") or "")
    # A broken gate must not let a commit through unchecked, so every failure while handling one
    # becomes a denial. Commands that do not commit are never blocked by a failure here.
    try:
        calls = list(find_commit_calls(command))
    except Exception as error:  # any parser bug: deny what may be a commit
        if COMMIT_WORD.search(command):
            deny_tool_use(f"konundrm-eng could not parse this command to check it for a commit ({error!r}).")
        return 0
    if not calls:
        return 0
    try:
        gate_commit(event, calls)
    except Exception as error:  # any gate failure: deny the commit it could not verify
        deny_tool_use(
            f"konundrm-eng could not verify this commit ({type(error).__name__}: {error}). Fix the plugin "
            "problem and commit again, or turn the gates off deliberately with KONUNDRM_GATE=off."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
