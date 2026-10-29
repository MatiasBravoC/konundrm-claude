"""Integration tests: run each hook script as Claude Code does, with a JSON event on stdin."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOKS = Path(__file__).resolve().parents[2]
SCRIPTS = HOOKS / "scripts"
PASSING = f'"{sys.executable}" -c "raise SystemExit(0)"'
FAILING = f'"{sys.executable}" -c "print(\'1 failed\'); raise SystemExit(1)"'


class HookScriptsTest(unittest.TestCase):
    def setUp(self) -> None:
        self._project = tempfile.TemporaryDirectory()
        self._data = tempfile.TemporaryDirectory()
        self.root = Path(self._project.name)
        self.env = {
            **os.environ,
            "CLAUDE_PROJECT_DIR": str(self.root),
            "CLAUDE_PLUGIN_DATA": self._data.name,
            "KONUNDRM_CHECK_CMD": PASSING,
            # An empty config directory, so the person's real skills never leak into a test.
            "CLAUDE_CONFIG_DIR": self._data.name,
        }
        self.env.pop("KONUNDRM_GATE", None)

    def tearDown(self) -> None:
        self._project.cleanup()
        self._data.cleanup()

    def run_hook(self, script: str, event: dict, **env: str) -> subprocess.CompletedProcess:
        event = {"session_id": "it-session", "cwd": str(self.root), **event}
        return subprocess.run(
            [sys.executable, str(SCRIPTS / script)],
            input=json.dumps(event),
            capture_output=True,
            text=True,
            encoding="utf-8",
            env={**self.env, **env},
            timeout=60,
        )

    def decision(self, result: subprocess.CompletedProcess) -> str | None:
        if not result.stdout.strip():
            return None
        return json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"]

    def edit_event(self, agent_type: str | None, relative: str) -> dict:
        event = {"tool_name": "Write", "tool_input": {"file_path": str(self.root / relative)}}
        return {**event, "agent_type": agent_type} if agent_type else event

    # enforce_role_boundaries.py

    def test_implementer_is_denied_editing_a_test(self) -> None:
        result = self.run_hook(
            "enforce_role_boundaries.py", self.edit_event("konundrm-eng:implementer", "tests/test_a.py")
        )
        self.assertEqual(self.decision(result), "deny")

    def test_test_writer_may_write_a_test(self) -> None:
        result = self.run_hook(
            "enforce_role_boundaries.py", self.edit_event("konundrm-eng:test-writer", "tests/test_a.py")
        )
        self.assertIsNone(self.decision(result))
        self.assertEqual(result.returncode, 0)

    def test_main_conversation_is_not_restricted(self) -> None:
        result = self.run_hook("enforce_role_boundaries.py", self.edit_event(None, "tests/test_a.py"))
        self.assertIsNone(self.decision(result))

    # gate_git_commit.py

    def commit_event(self, command: str, agent_type: str | None = None) -> dict:
        event = {"tool_name": "Bash", "tool_input": {"command": command}}
        return {**event, "agent_type": agent_type} if agent_type else event

    def test_commit_is_denied_when_the_check_fails(self) -> None:
        result = self.run_hook("gate_git_commit.py", self.commit_event("git commit -m x"), KONUNDRM_CHECK_CMD=FAILING)
        self.assertEqual(self.decision(result), "deny")
        self.assertIn("1 failed", result.stdout)

    def test_commit_is_allowed_when_the_check_passes(self) -> None:
        result = self.run_hook("gate_git_commit.py", self.commit_event("git commit -m x"))
        self.assertIsNone(self.decision(result))

    def test_no_verify_is_denied_even_with_gates_off(self) -> None:
        result = self.run_hook(
            "gate_git_commit.py", self.commit_event("git commit --no-verify -m x"), KONUNDRM_GATE="off"
        )
        self.assertEqual(self.decision(result), "deny")

    def test_subagents_may_not_commit(self) -> None:
        result = self.run_hook("gate_git_commit.py", self.commit_event("git commit -m x", "konundrm-eng:implementer"))
        self.assertEqual(self.decision(result), "deny")

    def test_non_commit_commands_pass_through_without_running_the_check(self) -> None:
        result = self.run_hook("gate_git_commit.py", self.commit_event("git status"), KONUNDRM_CHECK_CMD=FAILING)
        self.assertIsNone(self.decision(result))

    # block_secret_writes.py

    def test_writing_a_credential_asks_the_person(self) -> None:
        value = "sk" + "_live_" + "4eC39HqLyjWDarjtT1zdp7dc"  # Stripe's published test-mode shape, made live
        event = {"tool_name": "Write", "tool_input": {"file_path": str(self.root / "src" / "pay.py"), "content": value}}
        result = self.run_hook("block_secret_writes.py", event)
        self.assertEqual(self.decision(result), "ask")
        self.assertNotIn(value, result.stdout)

    def test_writing_ordinary_code_passes_silently(self) -> None:
        event = {"tool_name": "Edit", "tool_input": {"file_path": "src/a.py", "new_string": "key = os.environ['K']"}}
        result = self.run_hook("block_secret_writes.py", event)
        self.assertEqual((result.returncode, result.stdout.strip()), (0, ""))

    # format_and_lint.py + quality_gate.py

    def mark_dirty(self) -> None:
        source = self.root / "src" / "a.py"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("x = 1\n")
        result = self.run_hook("format_and_lint.py", self.edit_event(None, "src/a.py"))
        self.assertEqual(result.returncode, 0, result.stderr)

    def stop_block_reason(self, result: subprocess.CompletedProcess) -> str | None:
        """Returns the reason when the stop gate blocked the turn, None when it let it end."""
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout) if result.stdout.strip() else {}
        return output.get("reason") if output.get("decision") == "block" else None

    def stop(self, **env: str) -> str | None:
        return self.stop_block_reason(self.run_hook("quality_gate.py", {"hook_event_name": "Stop"}, **env))

    def test_stop_is_allowed_when_nothing_was_edited(self) -> None:
        self.assertIsNone(self.stop(KONUNDRM_CHECK_CMD=FAILING))

    def test_stop_is_blocked_after_an_edit_while_the_check_fails(self) -> None:
        self.mark_dirty()
        self.assertIn("1 failed", self.stop(KONUNDRM_CHECK_CMD=FAILING) or "")

    def test_stop_is_allowed_on_a_deliberate_red_handoff(self) -> None:
        self.mark_dirty()
        event = {"hook_event_name": "Stop", "last_assistant_message": "RED: rejects short passwords"}
        self.assertIsNone(self.stop_block_reason(self.run_hook("quality_gate.py", event, KONUNDRM_CHECK_CMD=FAILING)))

    def test_stop_gives_up_with_a_warning_after_three_blocks(self) -> None:
        self.mark_dirty()
        blocked = [self.stop(KONUNDRM_CHECK_CMD=FAILING) is not None for _ in range(3)]
        final = self.run_hook("quality_gate.py", {"hook_event_name": "Stop"}, KONUNDRM_CHECK_CMD=FAILING)
        self.assertEqual(blocked, [True, True, True])
        self.assertIsNone(self.stop_block_reason(final))
        self.assertIn("systemMessage", final.stdout)

    def test_stop_passes_and_clears_the_dirty_flag_when_green(self) -> None:
        self.mark_dirty()
        self.assertIsNone(self.stop())
        self.assertIsNone(self.stop(KONUNDRM_CHECK_CMD=FAILING))

    def test_editing_documentation_does_not_trigger_the_stop_gate(self) -> None:
        (self.root / "README.md").write_text("# x\n")
        self.run_hook("format_and_lint.py", self.edit_event(None, "README.md"))
        self.assertIsNone(self.stop(KONUNDRM_CHECK_CMD=FAILING))

    # session_doctor.py and run.sh

    def test_session_start_tells_claude_the_check_command(self) -> None:
        result = self.run_hook("session_doctor.py", {"hook_event_name": "SessionStart"})
        output = json.loads(result.stdout)
        self.assertIn(PASSING, output["hookSpecificOutput"]["additionalContext"])
        self.assertNotIn("systemMessage", output)

    def test_session_start_names_the_feature_in_progress(self) -> None:
        folder = self.root / "specs" / "003-coupons"
        folder.mkdir(parents=True)
        (folder / "tasks.md").write_text("- **Status:** Approved\n\n- [x] **T1** One\n- [ ] **T2** Two\n")
        result = self.run_hook("session_doctor.py", {"hook_event_name": "SessionStart", "source": "compact"})
        self.assertIn("specs/003-coupons: 1 of 2 tasks checked, next T2: Two", result.stdout)

    def test_session_start_warns_about_replaced_skills_still_installed(self) -> None:
        skill = Path(self._data.name) / "skills" / "tdd"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text("---\nname: tdd\n---\n")
        result = self.run_hook("session_doctor.py", {"hook_event_name": "SessionStart"})
        self.assertIn("tdd", json.loads(result.stdout)["systemMessage"])

    @unittest.skipIf(shutil.which("sh") is None, "no POSIX sh on PATH")
    def test_launcher_finds_python_and_runs_the_named_script(self) -> None:
        result = subprocess.run(
            ["sh", str(HOOKS / "run.sh"), "session_doctor.py"],
            input=json.dumps({"cwd": str(self.root)}),
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=self.env,
            timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("additionalContext", result.stdout)

    @unittest.skipIf(shutil.which("sh") is None, "no POSIX sh on PATH")
    def test_without_python_the_launcher_denies_commits_and_nothing_else(self) -> None:
        sh = shutil.which("sh") or "sh"

        def launch(command: str) -> str:
            return subprocess.run(
                [sh, str(HOOKS / "run.sh"), "gate_git_commit.py"],
                input=json.dumps({"tool_name": "Bash", "tool_input": {"command": command}}),
                capture_output=True,
                text=True,
                encoding="utf-8",
                env={**self.env, "PATH": str(Path(self._data.name) / "empty-bin")},  # no Python here
                timeout=60,
            ).stdout

        self.assertEqual(json.loads(launch("git commit -m x"))["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertEqual(launch("git status").strip(), "")


def git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        cwd=root,
        capture_output=True,
        check=True,
    )


@unittest.skipIf(shutil.which("git") is None, "Git is not installed")
class GitProjectHookScriptsTest(HookScriptsTest):
    """The same hooks inside a Git repository, where they compare tree snapshots."""

    def setUp(self) -> None:
        super().setUp()
        git(self.root, "init", "-q")
        (self.root / "src").mkdir()
        (self.root / "tests").mkdir()
        (self.root / "src" / "a.py").write_text("x = 1\n")
        (self.root / "tests" / "test_a.py").write_text("def test_a(): pass\n")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "init")

    # quality_gate.py

    def test_stop_is_blocked_after_a_change_made_through_bash(self) -> None:
        self.run_hook("quality_gate.py", {"hook_event_name": "UserPromptSubmit"})
        (self.root / "src" / "a.py").write_text("x = 2\n")  # as sed or a generator would: no Edit hook fired
        self.assertIsNotNone(self.stop(KONUNDRM_CHECK_CMD=FAILING))

    def test_stop_ignores_changes_that_were_already_there_when_the_turn_began(self) -> None:
        (self.root / "src" / "a.py").write_text("x = 2\n")
        self.run_hook("quality_gate.py", {"hook_event_name": "UserPromptSubmit"})
        self.assertIsNone(self.stop(KONUNDRM_CHECK_CMD=FAILING))

    def test_stop_is_blocked_when_the_turn_silences_a_gate_even_on_green(self) -> None:
        self.run_hook("quality_gate.py", {"hook_event_name": "UserPromptSubmit"})
        (self.root / "src" / "a.py").write_text("x = compute()  # type: ignore\n")
        reason = self.stop() or ""
        self.assertIn("silenced a gate", reason)
        self.assertIn("src/a.py:1", reason)

    def test_stop_accepts_a_silencer_with_its_reason(self) -> None:
        self.run_hook("quality_gate.py", {"hook_event_name": "UserPromptSubmit"})
        (self.root / "src" / "a.py").write_text("x = compute()  # type: ignore[no-untyped-call]  # vendored module\n")
        self.assertIsNone(self.stop())

    def test_stop_ignores_silencers_that_were_there_before_the_turn(self) -> None:
        (self.root / "src" / "a.py").write_text("x = compute()  # type: ignore\n")
        self.run_hook("quality_gate.py", {"hook_event_name": "UserPromptSubmit"})
        (self.root / "src" / "b.py").write_text("y = 1\n")
        self.assertIsNone(self.stop())

    # gate_git_commit.py content checks

    def test_commit_adding_an_unjustified_silencer_is_denied(self) -> None:
        (self.root / "tests" / "test_a.py").write_text("import pytest\n\n\n@pytest.mark.skip\ndef test_a(): pass\n")
        result = self.run_hook("gate_git_commit.py", self.commit_event("git commit -am x"))
        self.assertEqual(self.decision(result), "deny")
        self.assertIn("tests/test_a.py:4", result.stdout)

    def test_commit_with_justified_silencers_runs_the_check(self) -> None:
        (self.root / "src" / "a.py").write_text("x = 1  # noqa: E501 - generated table row\n")
        result = self.run_hook("gate_git_commit.py", self.commit_event("git commit -am x"))
        self.assertIsNone(self.decision(result))

    def test_commit_adding_a_credential_asks_the_person(self) -> None:
        (self.root / "src" / "a.py").write_text(
            "TOKEN = '" + "gh" + "p_" + "aB3dE5fG7hI9jK1lM3nO5pQ7rS9tU1vW3xY5" + "'\n"
        )
        result = self.run_hook("gate_git_commit.py", self.commit_event("git commit -am x"))
        self.assertEqual(self.decision(result), "ask")

    # record_check_result.py + gate_git_commit.py

    def test_a_check_claude_ran_is_reused_by_the_commit_gate_even_after_committing(self) -> None:
        (self.root / "src" / "a.py").write_text("x = 2\n")
        recorded = {"hook_event_name": "PostToolUse", "tool_input": {"command": FAILING}, "tool_response": {}}
        # The event says the command succeeded; FAILING as the check proves the gate did not rerun it.
        self.run_hook("record_check_result.py", recorded, KONUNDRM_CHECK_CMD=FAILING)
        first = self.run_hook("gate_git_commit.py", self.commit_event("git commit -am x"), KONUNDRM_CHECK_CMD=FAILING)
        self.assertIsNone(self.decision(first))
        git(self.root, "commit", "-q", "-am", "x")
        second = self.run_hook("gate_git_commit.py", self.commit_event("git commit -m y"), KONUNDRM_CHECK_CMD=FAILING)
        self.assertIsNone(self.decision(second))

    def test_wrapped_bypass_is_denied(self) -> None:
        for command in ("env HUSKY=0 git commit -m x", "bash -c 'git commit -n -m x'", "& git commit -n -m x"):
            with self.subTest(command=command):
                self.assertEqual(self.decision(self.run_hook("gate_git_commit.py", self.commit_event(command))), "deny")

    # audit_subagent_changes.py

    def subagent_event(self, hook: str, agent_type: str, **extra: object) -> dict:
        return {"hook_event_name": hook, "agent_type": agent_type, "agent_id": "agent-1", **extra}

    def test_implementer_editing_a_test_through_bash_is_blocked_then_restored(self) -> None:
        self.run_hook("audit_subagent_changes.py", self.subagent_event("SubagentStart", "konundrm-eng:implementer"))
        (self.root / "src" / "a.py").write_text("x = 3\n")
        (self.root / "tests" / "test_a.py").write_text("def test_a(): assert True\n")

        first = self.run_hook(
            "audit_subagent_changes.py", self.subagent_event("SubagentStop", "konundrm-eng:implementer")
        )
        decision = json.loads(first.stdout)
        self.assertEqual(decision["decision"], "block")
        self.assertIn("tests/test_a.py", decision["reason"])
        self.assertNotIn("src/a.py", decision["reason"])

        second = self.run_hook(
            "audit_subagent_changes.py",
            self.subagent_event("SubagentStop", "konundrm-eng:implementer", stop_hook_active=True),
        )
        self.assertIn("Restored", json.loads(second.stdout)["systemMessage"])
        self.assertEqual((self.root / "tests" / "test_a.py").read_text(), "def test_a(): pass\n")
        self.assertEqual((self.root / "src" / "a.py").read_text(), "x = 3\n")

    def test_test_writer_adding_a_test_passes_the_audit(self) -> None:
        self.run_hook("audit_subagent_changes.py", self.subagent_event("SubagentStart", "konundrm-eng:test-writer"))
        (self.root / "tests" / "test_b.py").write_text("def test_b(): assert False\n")
        result = self.run_hook(
            "audit_subagent_changes.py", self.subagent_event("SubagentStop", "konundrm-eng:test-writer")
        )
        self.assertEqual(result.stdout.strip(), "")

    def test_reviewer_running_the_tests_is_not_blamed_for_coverage_files(self) -> None:
        self.run_hook("audit_subagent_changes.py", self.subagent_event("SubagentStart", "konundrm-eng:code-reviewer"))
        (self.root / ".coverage").write_text("data")
        result = self.run_hook(
            "audit_subagent_changes.py", self.subagent_event("SubagentStop", "konundrm-eng:code-reviewer")
        )
        self.assertEqual(result.stdout.strip(), "")


if __name__ == "__main__":
    unittest.main()
