"""Unit tests for hooks/scripts/shell_commands.py."""

from __future__ import annotations

import base64
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from shell_commands import iter_commands


def programs(command_line: str) -> list[str]:
    return [command.program for command in iter_commands(command_line)]


class IterCommandsTest(unittest.TestCase):
    def test_splits_on_every_separator_and_newline(self) -> None:
        self.assertEqual(programs("a && b || c; d | e & f\ng"), ["a", "b", "c", "d", "e", "f", "g"])

    def test_keeps_quoted_separators_and_comments_inside_arguments(self) -> None:
        (command,) = iter_commands("echo 'a; b # c' \"d && e\"")
        self.assertEqual(command.arguments, ("a; b # c", "d && e"))

    def test_drops_comments_outside_quotes(self) -> None:
        self.assertEqual(programs("git status # then npm install x"), ["git"])

    def test_unwraps_wrappers_and_normalises_program_names(self) -> None:
        for command_line in ("env A=1 npm i x", "sudo -u dev npm i x", "& npm.exe i x", "/usr/bin/npm i x"):
            with self.subTest(command_line=command_line):
                self.assertEqual(programs(command_line), ["npm"])

    def test_expands_nested_shell_strings(self) -> None:
        encoded = base64.b64encode("uv add x".encode("utf-16-le")).decode()
        for command_line in (
            "bash -c 'uv add x'",
            'pwsh -NoProfile -Command "uv add x"',
            f"powershell -EncodedCommand {encoded}",
            'cmd /c "uv add x"',
        ):
            with self.subTest(command_line=command_line):
                self.assertEqual(programs(command_line), ["uv"])

    def test_collects_environment_from_prefixes_and_earlier_assignments(self) -> None:
        for command_line in ("HUSKY=0 git commit", "export HUSKY=0; git commit", "$env:HUSKY = '0'; git commit"):
            with self.subTest(command_line=command_line):
                (command,) = iter_commands(command_line)
                self.assertIn("HUSKY=0", command.env)

    def test_tolerates_unbalanced_quotes(self) -> None:
        self.assertEqual(programs("git commit -m 'oops && npm i x"), ["git", "npm"])


if __name__ == "__main__":
    unittest.main()
