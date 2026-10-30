"""Integration tests: run each hook script as Claude Code does, with a JSON event on stdin."""

from __future__ import annotations

import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOKS = Path(__file__).resolve().parents[2]
SCRIPTS = HOOKS / "scripts"
sys.path.insert(0, str(SCRIPTS))

import quality_check  # noqa: E402 - needs the scripts folder on sys.path first

PASSING = f'"{sys.executable}" -c "raise SystemExit(0)"'
FAILING = f'"{sys.executable}" -c "print(\'1 failed\'); raise SystemExit(1)"'


def install_fake_python(data: Path) -> tuple[Path, Path]:
    """Caches a fake Python in run.sh's data folder that leaves a marker and saves its stdin.

    Args:
        data: The folder run.sh reads as $CLAUDE_PLUGIN_DATA.

    Returns:
        The marker the fake creates when it starts, and the file that holds the stdin it received.
    """
    marker = data / "python-started"
    stdin_copy = data / "python-stdin"
    fake_python = data / "fake-python"
    fake_python.write_text(f'#!/bin/sh\n: > "{marker.as_posix()}"\ncat > "{stdin_copy.as_posix()}"\n', newline="\n")
    fake_python.chmod(0o755)
    (data / "python-path").write_text(fake_python.as_posix() + "\n", newline="\n")
    return marker, stdin_copy


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

    @unittest.skipIf(shutil.which("sh") is None, "no POSIX sh on PATH")
    def test_run_sh_skips_python_for_a_command_that_is_not_the_check(self) -> None:
        # R5.1
        marker, _ = install_fake_python(Path(self._data.name))
        event = {
            "session_id": "it-session",
            "cwd": str(self.root),
            "hook_event_name": "PostToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "ls -la"},
            "tool_response": {"stdout": "x" * 200_000, "stderr": "", "interrupted": False},
        }

        result = subprocess.run(
            [shutil.which("sh") or "sh", str(HOOKS / "run.sh"), "record_check_result.py"],
            input=json.dumps(event),
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=self.env,
            timeout=60,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(marker.exists(), "run.sh started Python for a command that is not the check")

    @unittest.skipIf(shutil.which("sh") is None, "no POSIX sh on PATH")
    def test_run_sh_runs_python_for_the_check_and_a_custom_check(self) -> None:
        # R5.2: the discovered check and a check set in KONUNDRM_CHECK_CMD both reach Python, which
        # reads the event byte for byte, past the 8 KB run.sh reads before it decides.
        marker, stdin_copy = install_fake_python(Path(self._data.name))
        (self.root / "package.json").write_text('{"scripts": {"check": "x"}}')
        discovered_env = {key: value for key, value in self.env.items() if key != "KONUNDRM_CHECK_CMD"}
        custom_env = {**self.env, "KONUNDRM_CHECK_CMD": "make verify"}

        def launch(command: str, env: dict[str, str]) -> bytes:
            event = {
                "session_id": "it-session",
                "cwd": str(self.root),
                "hook_event_name": "PostToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": command},
                "tool_response": {"stdout": "ok ñ " * 6_000, "stderr": "", "interrupted": False},
            }
            sent = (json.dumps(event, ensure_ascii=False) + "\n").encode("utf-8")
            marker.unlink(missing_ok=True)
            stdin_copy.unlink(missing_ok=True)
            result = subprocess.run(
                [shutil.which("sh") or "sh", str(HOOKS / "run.sh"), "record_check_result.py"],
                input=sent,
                capture_output=True,
                env=env,
                timeout=60,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            return sent

        sent = launch("npm run check", discovered_env)
        self.assertGreater(len(sent), 32_000)
        self.assertTrue(marker.exists(), "run.sh skipped Python for the project's check")
        self.assertEqual(stdin_copy.read_bytes(), sent, "Python received a different event than run.sh")

        launch("make verify", custom_env)
        self.assertTrue(marker.exists(), "run.sh skipped Python for the check set in KONUNDRM_CHECK_CMD")

    @unittest.skipIf(shutil.which("sh") is None, "no POSIX sh on PATH")
    def test_run_sh_runs_python_when_it_cannot_tell_the_command(self) -> None:
        # R5.3: none of these commands is the check, so Python starting proves run.sh ran the full
        # recorder because it could not read the command, not because it recognized the check.
        marker, _ = install_fake_python(Path(self._data.name))
        base = {"session_id": "it-session", "cwd": str(self.root), "hook_event_name": "PostToolUse"}
        base["tool_name"] = "Bash"
        response = {"stdout": "ok", "stderr": "", "interrupted": False}
        events = {
            "escaped quotes in the command": {
                **base,
                "tool_input": {"command": 'ls "my dir"'},
                "tool_response": response,
            },
            "command after the first 8 KB": {
                **base,
                "tool_response": {**response, "stdout": "x" * 10_000},
                "tool_input": {"command": "ls -la"},
            },
            "no command in the event": {**base, "tool_input": {}, "tool_response": response},
        }
        started = {}
        for case, event in events.items():
            marker.unlink(missing_ok=True)

            result = subprocess.run(
                [shutil.which("sh") or "sh", str(HOOKS / "run.sh"), "record_check_result.py"],
                input=json.dumps(event),
                capture_output=True,
                text=True,
                encoding="utf-8",
                env=self.env,
                timeout=60,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            started[case] = marker.exists()
        self.assertEqual(started, dict.fromkeys(events, True), "run.sh skipped Python without reading the command")

    @unittest.skipIf(shutil.which("sh") is None, "no POSIX sh on PATH")
    def test_run_sh_passes_the_event_intact_to_the_gate_and_the_guard(self) -> None:
        # R5.4: only the check recorder takes the fast path, so the commit gate and the dependency
        # guard read every byte of the event, past the 8 KB the recorder's fast path reads, even
        # for a command the recorder would skip; and without Python the gate still denies commits.
        data = Path(self._data.name)
        marker, stdin_copy = install_fake_python(data)
        sh = shutil.which("sh") or "sh"

        def pre_tool_use(command: str, description: str) -> bytes:
            event = {
                "session_id": "it-session",
                "cwd": str(self.root),
                "hook_event_name": "PreToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": command, "description": description},
            }
            return (json.dumps(event, ensure_ascii=False) + "\n").encode("utf-8")

        def launch(script: str, sent: bytes, env: dict[str, str]) -> subprocess.CompletedProcess:
            return subprocess.run(
                [sh, str(HOOKS / "run.sh"), script], input=sent, capture_output=True, env=env, timeout=60
            )

        events = {
            (command, size): pre_tool_use(command, "lista ñ " * (3_000 if size == "large" else 1))
            for command in ("ls", "git commit -m x")
            for size in ("small", "large")
        }
        self.assertGreater(len(events["ls", "large"]), 3 * 8192)
        altered = []
        for script in ("gate_git_commit.py", "guard_new_dependencies.py"):
            for case, sent in events.items():
                marker.unlink(missing_ok=True)
                stdin_copy.unlink(missing_ok=True)

                result = launch(script, sent, self.env)

                self.assertEqual(result.returncode, 0, result.stderr)
                received = stdin_copy.read_bytes() if marker.exists() else None
                if received != sent:
                    altered.append((script, *case, len(sent), None if received is None else len(received)))
        self.assertEqual(altered, [], "Python got other bytes for (script, command, size, sent, got)")

        (data / "python-path").unlink()
        no_python = {**self.env, "PATH": str(data / "empty-bin")}  # no Python here
        denied = launch("gate_git_commit.py", events["git commit -m x", "large"], no_python)
        self.assertEqual(denied.returncode, 0, denied.stderr)
        self.assertEqual(json.loads(denied.stdout)["hookSpecificOutput"]["permissionDecision"], "deny")

    @unittest.skipIf(shutil.which("sh") is None, "no POSIX sh on PATH")
    def test_without_python_the_gate_denies_a_commit_past_the_first_8_kb(self) -> None:
        # R5.4: without Python the commit gate fails closed on the whole event, not on the 8 KB
        # the check recorder's fast path reads, so a commit hidden behind a long prefix is denied.
        event = {
            "session_id": "it-session",
            "cwd": str(self.root),
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": f"echo {'a' * 9_000} && git commit -m x"},
        }
        sent = (json.dumps(event) + "\n").encode("utf-8")
        self.assertGreater(sent.index(b"git commit"), 8192)
        self.assertNotIn(b"commit", sent[:8192])
        no_python = {**self.env, "PATH": str(Path(self._data.name) / "empty-bin")}  # no cached or PATH Python

        result = subprocess.run(
            [shutil.which("sh") or "sh", str(HOOKS / "run.sh"), "gate_git_commit.py"],
            input=sent,
            capture_output=True,
            env=no_python,
            timeout=60,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotEqual(result.stdout.strip(), b"", "without Python run.sh allowed a commit past the first 8 KB")
        self.assertEqual(json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"], "deny")


# Whitespace Python's str.split() and str.strip() remove, including some a C-locale shell does not.
PYTHON_WHITESPACE = (" ", "  ", "\t", "\n", "\u00a0", "\u2003", "\u3000")
PADDING = ("", *PYTHON_WHITESPACE)
OVERRIDE_CORES = ("npm run check", "uv run poe check", "poe check", "make check", "pytest -q", "cargo clippy --all")
DISCOVERED_PROJECTS = (
    ({"package.json": '{"scripts": {"check": "x"}}'}, None),
    ({"package.json": '{"scripts": {"check": "x"}}', "pnpm-lock.yaml": ""}, None),
    ({"package.json": '{"scripts": {"check": "x"}}', "yarn.lock": ""}, None),
    ({"package.json": '{"scripts": {"check": "x"}}'}, ""),
    ({"package.json": '{"scripts": {"check": "x"}}'}, "   "),
    ({"package.json": '{"scripts": {"check": "x"}}'}, "\u00a0"),
)
SUFFIX_PARTS = (";", " ;", "2>&1", " 2>&1", " ")


def _respace(rng: random.Random, words: str) -> str:
    return "".join(word + " " * rng.randint(1, 3) for word in words.split(" ")[:-1]) + words.split(" ")[-1]


def _suffix(rng: random.Random) -> str:
    return "".join(rng.choice(SUFFIX_PARTS) for _ in range(rng.randint(0, 3)))


# Generators for events run.sh cannot read (R5.3). Every command is built from words without "check",
# so Python starting can only come from the launcher's doubt, never from recognizing the check.
ORDINARY_WORDS = ("ls", "-la", "git", "status", "echo", "hi", "make", "lint", "npm", "test", "pytest", "-q", "cat")
# Characters json.dumps(ensure_ascii=True) writes as an escape: \" \\ \n \t \r \b \f and \uXXXX.
ESCAPED_CHARS = ('"', "\\", "\n", "\t", "\r", "\b", "\f", "\x01", "\x1f", "ñ", "€", "\u00a0", "😀")
# (item separator, key separator) pairs whose key separator is not ":" plus optional spaces.
UNEXPECTED_SEPARATORS = (
    (", ", " : "),
    (",", " :"),
    (",", "\t:"),
    (", ", ":\n"),
    (",\n", ":\t"),
    (", ", ": \t"),
    (", ", ":\r\n"),
    (", ", ":  \n "),
)
NON_ASCII_CHARS = ("é", "ñ", "€", "\u00a0", "\u3000", "😀")
FILL_ALPHABET = "abcdefxyz0123456789-_/. "  # no "k", so a fill never spells the check word
BLOCK = 8192  # the bytes run.sh's dd reads before it decides


def _ordinary_command(rng: random.Random) -> str:
    return " ".join(rng.choice(ORDINARY_WORDS) for _ in range(rng.randint(1, 5)))


def _bash_event(tool_input: object = None, **fields: object) -> dict:
    """A PostToolUse Bash event with a fixed cwd, so its bytes never depend on the machine."""
    event: dict = {"session_id": "it-session", "cwd": "/home/dev/project", "hook_event_name": "PostToolUse"}
    event["tool_name"] = "Bash"
    event.update(fields)
    if tool_input is not None:
        event["tool_input"] = tool_input
    event.setdefault("tool_response", {"stdout": "ok", "stderr": "", "interrupted": False})
    return event


def _escaped_case(rng: random.Random) -> tuple[bytes, str | None]:
    words = _ordinary_command(rng)
    at = rng.randint(0, len(words))
    command = words[:at] + "".join(rng.choice(ESCAPED_CHARS) for _ in range(rng.randint(1, 3))) + words[at:]
    return json.dumps(_bash_event({"command": command})).encode("ascii"), None


def _far_case(rng: random.Random) -> tuple[bytes, str | None]:
    """Pushes "command": past byte 8192, or makes its value start before it and end after it."""
    where = rng.choice(("tool_response", "cwd", "transcript_path", "description"))
    straddles = rng.random() < 0.4
    command = _ordinary_command(rng)
    if straddles:
        command = (command + " ") * rng.randint(20, 60)
    if where == "tool_response":
        response = {"stdout": "@FILL@", "stderr": "", "interrupted": False}
        event = {"tool_response": response, **_bash_event({"command": command}, tool_response=response)}
    elif where == "description":
        event = _bash_event({"description": "@FILL@", "command": command})
    else:
        event = _bash_event(**{where: "@FILL@"})
        event["tool_input"] = event.pop("tool_input", {"command": command})
        event["tool_response"] = event.pop("tool_response")
    text = json.dumps(event)
    key_end = text.index('"command":') + len('"command":')
    opening = text.index('"', key_end)
    closing = text.index('"', opening + 1)
    if straddles:
        shift = rng.randint(BLOCK - closing, BLOCK - 1 - opening)
    else:
        shift = rng.randint(BLOCK + 1 - key_end, BLOCK + 3000 - key_end)
    fill = "".join(rng.choice(FILL_ALPHABET) for _ in range(shift + len("@FILL@")))
    return text.replace("@FILL@", fill).encode("ascii"), None


def _missing_case(rng: random.Random) -> tuple[bytes, str | None]:
    shape = rng.choice(("no command", "no tool_input", "number", "null", "list", "object", "bool"))
    values = {
        "number": rng.randint(-5, 10**6),
        "null": None,
        "list": [_ordinary_command(rng)],
        "object": {"command": _ordinary_command(rng)},
        "bool": rng.choice((True, False)),
    }
    if shape == "no tool_input":
        return json.dumps(_bash_event()).encode("ascii"), None
    tool_input = {"description": _ordinary_command(rng)} if rng.random() < 0.5 else {}
    if shape != "no command":
        tool_input["command"] = values[shape]
    return json.dumps(_bash_event(tool_input)).encode("ascii"), None


def _separator_case(rng: random.Random) -> tuple[bytes, str | None]:
    separators = rng.choice(UNEXPECTED_SEPARATORS)
    return json.dumps(_bash_event({"command": _ordinary_command(rng)}), separators=separators).encode("ascii"), None


def _non_ascii_override_case(rng: random.Random) -> tuple[bytes, str | None]:
    override = _ordinary_command(rng) + " verify"
    at = rng.randint(0, len(override))
    override = override[:at] + rng.choice(NON_ASCII_CHARS) + override[at:]
    return json.dumps(_bash_event({"command": _ordinary_command(rng)})).encode("ascii"), override


UNREADABLE_CASES = (_escaped_case, _far_case, _missing_case, _separator_case, _non_ascii_override_case)

# Generators for the scripts run.sh must hand their event untouched (R5.4).
SKILL_SCRIPTS = ("quality_check.py", "metrics_report.py", "improvement_notes.py")  # skills call these via run.sh
RECORDER_NEAR_MISSES = (
    "Record_check_result.py",
    "RECORD_CHECK_RESULT.PY",
    "_record_check_result.py",
    "record_check_result.pyc",
    "record_check_result",
    "./record_check_result.py",
    "scripts/record_check_result.py",
    "record_check_result.py ",
)
SKIPPED_COMMANDS = ("ls -la", "git status", "git commit -m x")  # the recorder's fast path skips these
CHECK_COMMANDS = ("npm run check",)  # and sends these to Python


def _hooks_json_scripts() -> list[str]:
    """Every script hooks.json runs through run.sh, so a new hook is covered without editing the test."""
    config = json.loads((HOOKS / "hooks.json").read_text(encoding="utf-8"))
    commands = [hook["command"] for groups in config["hooks"].values() for group in groups for hook in group["hooks"]]
    return sorted({command.split('run.sh" ', 1)[1].split()[0] for command in commands if "run.sh" in command})


def _launcher_event(rng: random.Random) -> bytes:
    """A PreToolUse or PostToolUse Bash event of a few hundred bytes to a few blocks, as bytes."""
    command = rng.choice(SKIPPED_COMMANDS * 2 + CHECK_COMMANDS)
    if rng.random() < 0.5:
        event = _bash_event({"command": command, "description": "@FILL@"}, hook_event_name="PreToolUse")
        del event["tool_response"]
    else:
        event = _bash_event(
            {"command": command}, tool_response={"stdout": "@FILL@", "stderr": "", "interrupted": False}
        )
    head, tail = json.dumps(event, ensure_ascii=False).encode("utf-8").split(b"@FILL@")
    newline = rng.choice((b"", b"\n"))
    size = rng.choice((rng.randint(300, 1_500), BLOCK + rng.randint(-3, 3), rng.randint(2 * BLOCK, 3 * BLOCK + 100)))
    room = size - len(head) - len(tail) - len(newline)
    fill = b""
    while len(fill) < room:
        piece = rng.choice((*FILL_ALPHABET, *NON_ASCII_CHARS)).encode("utf-8")
        fill += piece if len(fill) + len(piece) <= room else b"x"
    return head + fill + tail + newline


@unittest.skipIf(shutil.which("sh") is None, "no POSIX sh on PATH")
class RunShFastPathPropertyTest(unittest.TestCase):
    """run.sh's fast path, outside HookScriptsTest so the slow property runs once per check."""

    def test_run_sh_starts_python_for_every_command_that_runs_the_check(self) -> None:
        # R5.1 invariant: the fast path never skips a command quality_check would record as the check.
        with tempfile.TemporaryDirectory() as data_name:
            data = Path(data_name)
            marker, _ = install_fake_python(data)
            rng = random.Random(29)  # noqa: S311 - seeded for reproducible test data, not cryptography
            skipped = []
            checked = 0
            for index in range(24):
                root = data / f"project{index}"
                root.mkdir()
                if rng.random() < 0.3:
                    files, override = rng.choice(DISCOVERED_PROJECTS)
                    for name, content in files.items():
                        (root / name).write_text(content)
                else:
                    core = _respace(rng, rng.choice(OVERRIDE_CORES)) + _suffix(rng)
                    override = rng.choice(PADDING) + core + rng.choice(PADDING)
                env = {**os.environ, "CLAUDE_PLUGIN_DATA": data_name, "CLAUDE_PROJECT_DIR": str(root)}
                env.pop("KONUNDRM_CHECK_CMD", None)
                if override is not None:
                    env["KONUNDRM_CHECK_CMD"] = override
                check = quality_check.find_check_command(root, env)
                self.assertIsNotNone(check)
                form = rng.choice(sorted(quality_check._equivalent_forms(check)))
                command = rng.choice(("", " ")) + _respace(rng, form) + _suffix(rng)
                if rng.random() < 0.4:
                    command = f"cd{' ' * rng.randint(1, 2)}'{root.as_posix()}'{' ' * rng.randint(0, 2)}&& {command}"
                runs_check = quality_check.is_check_invocation(command, check, root, root)
                if not runs_check or "\\" in command or '"' in command:
                    continue
                event = {
                    "session_id": "it-session",
                    "cwd": str(root),
                    "hook_event_name": "PostToolUse",
                    "tool_name": "Bash",
                    "tool_input": {"command": command},
                    "tool_response": {"stdout": "ok", "stderr": "", "interrupted": False},
                }
                marker.unlink(missing_ok=True)

                subprocess.run(
                    [shutil.which("sh") or "sh", str(HOOKS / "run.sh"), "record_check_result.py"],
                    input=json.dumps(event, ensure_ascii=False),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    env=env,
                    timeout=60,
                )

                checked += 1
                if not marker.exists():
                    skipped.append((override, command))
            self.assertGreaterEqual(checked, 15, "the generator produced too few commands that run the check")
            self.assertEqual(skipped, [], "run.sh skipped Python for (KONUNDRM_CHECK_CMD, command) pairs")

    def test_run_sh_hands_python_every_check_event_byte_for_byte(self) -> None:
        # R5.2 invariant: for an event whose command runs the check, the bytes Python reads are the
        # bytes that reached run.sh, whatever the size, trailing newlines or where 8192 falls.
        block = 8192
        near_block = tuple(block + delta for delta in (-2, -1, 0, 1, 2))
        sizes = (300, 1_500, *near_block, 2 * block - 1, 2 * block + 1, 3 * block + 7)
        multibyte = ("ñ", "€", "😀")
        pieces = ("ok ", "ñ", "€", "😀", "\r\n", "x", "\\r\\n")
        with tempfile.TemporaryDirectory() as data_name:
            data = Path(data_name)
            marker, stdin_copy = install_fake_python(data)
            root = data / "project"
            root.mkdir()
            (root / "package.json").write_text('{"scripts": {"check": "x"}}')
            base_env = {**os.environ, "CLAUDE_PLUGIN_DATA": data_name, "CLAUDE_PROJECT_DIR": str(root)}
            base_env.pop("KONUNDRM_CHECK_CMD", None)
            rng = random.Random(41)  # noqa: S311 - seeded for reproducible test data, not cryptography
            mismatches = []
            for index, size in enumerate(sizes):
                newlines = "\n" * rng.choice((0, 1, 1, 3))
                if index % 2:
                    command, env = "make verify", {**base_env, "KONUNDRM_CHECK_CMD": "make verify"}
                else:
                    command, env = "npm run check", base_env
                event = {
                    "session_id": "it-session",
                    "cwd": str(root),
                    "hook_event_name": "PostToolUse",
                    "tool_name": "Bash",
                    "tool_input": {"command": command},
                    "tool_response": {"stdout": "@FILL@", "stderr": "", "interrupted": False},
                }
                head, tail = json.dumps(event, ensure_ascii=False).encode("utf-8").split(b"@FILL@")
                room = size - len(head) - len(tail) - len(newlines)
                fill = b""
                char = rng.choice(multibyte).encode("utf-8")
                if room >= block - len(head) + len(char):
                    # A multibyte character that starts 1..len-1 bytes before byte 8192, so it straddles it.
                    fill = b"x" * (block - len(head) - rng.randint(1, len(char) - 1)) + char
                while len(fill) < room:
                    piece = rng.choice(pieces).encode("utf-8")
                    fill += piece if len(fill) + len(piece) <= room else b"x"
                sent = head + fill + tail + newlines.encode("ascii")
                self.assertEqual(len(sent), size)
                marker.unlink(missing_ok=True)
                stdin_copy.unlink(missing_ok=True)

                result = subprocess.run(
                    [shutil.which("sh") or "sh", str(HOOKS / "run.sh"), "record_check_result.py"],
                    input=sent,
                    capture_output=True,
                    env=env,
                    timeout=60,
                )

                self.assertEqual(result.returncode, 0, result.stderr)
                received = stdin_copy.read_bytes() if marker.exists() else None
                if received != sent:
                    mismatches.append((command, size, len(newlines), None if received is None else len(received)))
            self.assertEqual(mismatches, [], "Python got other bytes for (command, size, trailing newlines, got)")

    def test_run_sh_runs_python_for_every_event_it_cannot_read(self) -> None:
        # R5.3 invariant: when run.sh cannot read the command (escapes, keys past the first 8 KB, no
        # string command, unexpected separators, a non-ASCII override), Python starts. No command
        # holds the check word, so the marker can only come from that doubt.
        with tempfile.TemporaryDirectory() as data_name:
            marker, _ = install_fake_python(Path(data_name))
            base_env = {**os.environ, "CLAUDE_PLUGIN_DATA": data_name}
            base_env.pop("KONUNDRM_CHECK_CMD", None)
            skipped = []
            for index in range(18):
                # One generator per case, so each case's draws never depend on another case or the machine.
                rng = random.Random(53 + index)  # noqa: S311 - seeded for reproducible test data, not cryptography
                build = UNREADABLE_CASES[index % len(UNREADABLE_CASES)]
                sent, override = build(rng)
                self.assertNotIn(b"check", sent)
                env = base_env if override is None else {**base_env, "KONUNDRM_CHECK_CMD": override}
                marker.unlink(missing_ok=True)

                result = subprocess.run(
                    [shutil.which("sh") or "sh", str(HOOKS / "run.sh"), "record_check_result.py"],
                    input=sent,
                    capture_output=True,
                    env=env,
                    timeout=60,
                )

                self.assertEqual(result.returncode, 0, result.stderr)
                if not marker.exists():
                    skipped.append((index, build.__name__, override, sent[:200], len(sent)))
            self.assertEqual(skipped, [], "run.sh skipped Python for events it could not read")

    def test_run_sh_hands_every_other_script_its_event_untouched(self) -> None:
        # R5.4 invariant: only record_check_result.py takes the fast path, so every other script,
        # including near-misses of the recorder's name, starts Python and reads the event byte for
        # byte, even one whose command the recorder would skip. The fake Python only saves its stdin.
        hook_scripts = _hooks_json_scripts()
        self.assertIn("gate_git_commit.py", hook_scripts)
        self.assertIn("record_check_result.py", hook_scripts)
        scripts = [name for name in hook_scripts if name != "record_check_result.py"]
        scripts += [*SKILL_SCRIPTS, *RECORDER_NEAR_MISSES]
        with tempfile.TemporaryDirectory() as data_name:
            marker, stdin_copy = install_fake_python(Path(data_name))
            env = {**os.environ, "CLAUDE_PLUGIN_DATA": data_name, "CLAUDE_PROJECT_DIR": data_name}
            env.pop("KONUNDRM_CHECK_CMD", None)
            altered = []
            for index, script in enumerate(scripts):
                # One generator per case, so each case's draws never depend on another case or the machine.
                rng = random.Random(67 + index)  # noqa: S311 - seeded for reproducible test data, not cryptography
                sent = _launcher_event(rng)
                marker.unlink(missing_ok=True)
                stdin_copy.unlink(missing_ok=True)

                result = subprocess.run(
                    [shutil.which("sh") or "sh", str(HOOKS / "run.sh"), script],
                    input=sent,
                    capture_output=True,
                    env=env,
                    timeout=60,
                )

                self.assertEqual(result.returncode, 0, result.stderr)
                received = stdin_copy.read_bytes() if marker.exists() else None
                if received != sent:
                    altered.append((index, script, sent[:160], len(sent), None if received is None else len(received)))
            self.assertEqual(altered, [], "Python got other bytes for (case, script, event start, sent, got)")


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
