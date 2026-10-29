"""Unit tests for hooks/scripts/gate_git_commit.py."""

from __future__ import annotations

import base64
import io
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import gate_git_commit
from gate_git_commit import bypass_reason, find_commit_calls


def calls(command: str) -> list:
    return list(find_commit_calls(command))


def reasons(command: str) -> list[str | None]:
    return [bypass_reason(call) for call in calls(command)]


class FindCommitCallsTest(unittest.TestCase):
    def test_finds_plain_chained_and_option_prefixed_commits(self) -> None:
        for command in (
            "git commit -m 'feat: x'",
            "git add -A && git commit -m x",
            "cd repo; git -C sub commit -m x",
            "git --no-pager commit",
            "(git commit -m x)",
            "git add .\ngit commit -m x",
            "git status & git commit -m x",
        ):
            with self.subTest(command=command):
                self.assertEqual(len(calls(command)), 1)

    def test_finds_commit_with_heredoc_message(self) -> None:
        command = "git commit -m \"$(cat <<'EOF'\nfeat(auth): add login\n\nBody.\nEOF\n)\""
        self.assertEqual(len(calls(command)), 1)

    def test_finds_commits_behind_wrappers(self) -> None:
        for command in (
            "env git commit -m x",
            "env -i PATH=/usr/bin git commit -m x",
            "command git commit -m x",
            "sudo -u dev git commit -m x",
            "nohup git commit -m x",
            "& git commit -m x",
            '& "C:\\Program Files\\Git\\cmd\\git.exe" commit -m x',
            "/usr/bin/git commit -m x",
        ):
            with self.subTest(command=command):
                self.assertEqual(len(calls(command)), 1)

    def test_finds_commits_inside_nested_shells(self) -> None:
        encoded = base64.b64encode("git commit -m x".encode("utf-16-le")).decode()
        for command in (
            "bash -c 'git commit -m x'",
            'sh -lc "git add . && git commit -m x"',
            'pwsh -NoProfile -Command "git commit -m x"',
            f"powershell -EncodedCommand {encoded}",
            'cmd /c "git commit -m x"',
            "bash -c \"bash -c 'git commit -m x'\"",
        ):
            with self.subTest(command=command):
                self.assertEqual(len(calls(command)), 1)

    def test_ignores_commands_that_do_not_commit(self) -> None:
        for command in (
            "git status",
            "git log --grep commit",
            "echo git commit",
            "git commit-tree abc",
            "bash script.sh",
            "git status # then git commit -n",
            'echo "git commit -n"',
            "",
        ):
            with self.subTest(command=command):
                self.assertEqual(calls(command), [])

    def test_collects_environment_prefixes(self) -> None:
        (call,) = calls("HUSKY=0 git commit -m x")
        self.assertEqual(call.env, ["HUSKY=0"])


class BypassReasonTest(unittest.TestCase):
    def test_detects_every_hook_bypass(self) -> None:
        for command in (
            "git commit --no-verify -m x",
            "git commit --no-verif -m x",
            "git commit --no-veri -m x",
            "git commit -n -m x",
            "git commit -anm x",
            "HUSKY=0 git commit -m x",
            "SKIP=ruff git commit -m x",
            "LEFTHOOK=0 git commit -m x",
            "GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=core.hooksPath GIT_CONFIG_VALUE_0=/x git commit -m x",
            "git -c core.hooksPath=/dev/null commit -m x",
            "env HUSKY=0 git commit -m x",
            "bash -c 'git commit --no-verify -m x'",
            "& git commit -n -m x",
            "command git commit -n -m x",
            "export HUSKY=0; git commit -m x",
            "$env:HUSKY='0'; git commit -m x",
            "$env:HUSKY = '0'; git commit -m x",
            "git commit \\\n  --no-verify -m x",
            "timeout 60 git commit -n -m x",
            "timeout -k 5 60 git commit -n -m x",
            "echo x | xargs -n1 git commit -n -m",
            "stdbuf -oL git commit -n -m x",
            "eval 'git commit -n -m x'",
            "iex 'git commit -n -m x'",
        ):
            with self.subTest(command=command):
                found = reasons(command)
                self.assertEqual(len(found), 1)
                self.assertIsNotNone(found[0])

    def test_does_not_flag_option_values_messages_or_comments(self) -> None:
        for command in (
            "git commit -am 'fix -n flag handling'",
            "git commit -m x --author 'N <n@x.com>'",
            "git commit -S -m x",
            "git commit --message=--no-verify-docs",
            "git commit -F msg.txt",
            "git commit --no-verify=yes -m x",
            "git commit --no-ver -m x",
            "git commit -m '#12 fix' -- --no-verify",
            "SKIP= git commit -m x",
            "git commit -m x # --no-verify",
        ):
            with self.subTest(command=command):
                self.assertEqual(reasons(command), [None])


class FailsClosedTest(unittest.TestCase):
    def decision(self, command: str) -> str | None:
        event = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
        stdout = io.StringIO()
        with mock.patch("sys.stdin", io.TextIOWrapper(io.BytesIO(event.encode()))), mock.patch("sys.stdout", stdout):
            gate_git_commit.main()
        output = stdout.getvalue()
        return json.loads(output)["hookSpecificOutput"]["permissionDecision"] if output else None

    def test_a_gate_failure_denies_the_commit(self) -> None:
        with mock.patch.object(gate_git_commit, "gate_commit", side_effect=RuntimeError("boom")):
            self.assertEqual(self.decision("git commit -m x"), "deny")

    def test_a_parser_failure_denies_only_what_mentions_a_commit(self) -> None:
        with mock.patch.object(gate_git_commit, "find_commit_calls", side_effect=ValueError("odd quoting")):
            self.assertEqual(self.decision("git commit -m x"), "deny")
            self.assertIsNone(self.decision("git status"))


if __name__ == "__main__":
    unittest.main()
