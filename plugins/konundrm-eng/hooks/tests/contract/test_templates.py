"""Contract tests for the templates setup-project copies into a project (skills/setup-project/templates/)."""

from __future__ import annotations

import re
import shlex
import unittest
from pathlib import Path

from .plugin_files import SKILLS_DIR

CLAUDE_REVIEW_TEMPLATE = SKILLS_DIR / "setup-project" / "templates" / "claude-review.yml"

# The header of a YAML literal block scalar under the `claude_args` key: `claude_args: |`, `|-` or `|+`.
_CLAUDE_ARGS_HEADER = re.compile(r"(?P<indent> *)claude_args: *\|[-+]? *(?:#.*)?")


def _claude_args_blocks(path: Path) -> list[list[str]]:
    """Return the command-line arguments in each `claude_args: |` block of a workflow file.

    A block is the lines after its header that are blank or indented deeper than the `claude_args` key. Its text is
    split into arguments as a shell does, dropping `#` comments, so a flag in a YAML comment, under another key or in
    another step does not count. Lines are read with universal newlines.
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    blocks = []
    for index, line in enumerate(lines):
        header = _CLAUDE_ARGS_HEADER.fullmatch(line)
        if header is None:
            continue
        body = []
        for body_line in lines[index + 1 :]:
            if body_line.strip() and len(body_line) - len(body_line.lstrip(" ")) <= len(header["indent"]):
                break
            body.append(body_line)
        blocks.append(shlex.split("\n".join(body), comments=True))
    return blocks


def _flag_values(args: list[str], flag: str) -> list[str | None]:
    """Return the value of each occurrence of a flag in a list of command-line arguments.

    The value is the next argument (`--flag value`) or the text after the equals sign (`--flag=value`). A flag that
    is the last argument has the value None.
    """
    values: list[str | None] = []
    for position, arg in enumerate(args):
        if arg == flag:
            values.append(args[position + 1] if position + 1 < len(args) else None)
        elif arg.startswith(f"{flag}="):
            values.append(arg[len(flag) + 1 :])
    return values


class ClaudeReviewTemplateTest(unittest.TestCase):
    def test_ci_review_runs_on_opus_at_medium_effort(self) -> None:
        """R1.7: the pull request review in CI runs on Opus 5.5 (claude-opus-5-5) at medium effort.

        The review template's only `claude_args: |` block, which claude-code-action passes to the Claude Code CLI,
        holds exactly one `--model claude-opus-5-5` and exactly one `--effort medium`.
        """
        blocks = _claude_args_blocks(CLAUDE_REVIEW_TEMPLATE)
        args = [arg for block in blocks for arg in block]

        actual = {
            "claude_args blocks": len(blocks),
            "--model": _flag_values(args, "--model"),
            "--effort": _flag_values(args, "--effort"),
        }

        self.assertEqual(actual, {"claude_args blocks": 1, "--model": ["claude-opus-5-5"], "--effort": ["medium"]})


if __name__ == "__main__":
    unittest.main()
