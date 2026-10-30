"""Contract tests for the plugin's agent definitions in agents/*.md."""

from __future__ import annotations

import re
import unittest

from .plugin_files import AGENTS_DIR, read_frontmatter

RETHINKER = AGENTS_DIR / "rethinker.md"
RETHINKER_FIELDS = {"name": "rethinker", "model": "opus", "effort": "max"}
WRITING_TOOLS = frozenset({"Edit", "Write", "NotebookEdit"})
RETHINK_VERDICTS = ("NEW APPROACH", "ADJUST", "PLAN CHANGE")

# R8.1's two questions, in plain words. They run on text from _plain_words, so a reworded or wrapped sentence counts.
_WHY_ATTEMPTS_FAIL = re.compile(r"\b(?:why|reasons?|root[- ]causes?)\b[^.]{0,80}?\bfail(?:s|ed|ing|ures?)?\b")
_WHAT_TO_DO_DIFFERENTLY = re.compile(r"\b(?:different(?:ly)?|instead|alternatives?)\b")


def _plain_words(text: str) -> str:
    """Return a Markdown text lowercased, without emphasis or code marks (`*`, `_`, backticks), single-spaced."""
    return " ".join(re.sub(r"[`*_]", "", text).lower().split())


def _tool_names(tools: str) -> set[str]:
    """Return the tool names of a comma-separated `tools:` value, dropping any `(pattern)` after a name."""
    return {entry.split("(", 1)[0].strip() for entry in tools.split(",") if entry.strip()}


def _fenced_blocks(text: str) -> list[str]:
    """Return the text inside each fenced (```) block of a Markdown text, one string per block."""
    blocks: list[list[str]] = []
    inside = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            inside = not inside
            if inside:
                blocks.append([])
        elif inside:
            blocks[-1].append(line)
    return ["\n".join(block) for block in blocks]


def _rethinker_frontmatter_gaps(fields: dict[str, str]) -> list[str]:
    """Return one message per frontmatter field of the rethinker that breaks R1.1 or makes it able to write files.

    An agent without a `tools:` list inherits every tool, Edit and Write included, so a missing list is a gap.
    """
    gaps = [
        f"frontmatter {key}: is {fields.get(key)!r}, expected {expected!r}"
        for key, expected in RETHINKER_FIELDS.items()
        if fields.get(key) != expected
    ]
    tools = _tool_names(fields.get("tools", ""))
    if not tools:
        gaps.append("frontmatter has no comma-separated tools: list, so the agent inherits every tool, Edit included")
    if tools & WRITING_TOOLS:
        gaps.append(f"frontmatter tools: lists the writing tools {sorted(tools & WRITING_TOOLS)}")
    return gaps


def _rethinker_purpose_gaps(text: str) -> list[str]:
    """Return a message for each of R8.1's questions the description and body do not say the agent answers."""
    plain = _plain_words(text)
    gaps = []
    if _WHY_ATTEMPTS_FAIL.search(plain) is None:
        gaps.append("neither the description nor the body says it explains why the attempts keep failing")
    if _WHAT_TO_DO_DIFFERENTLY.search(plain) is None:
        gaps.append("neither the description nor the body says it tells what to do differently")
    return gaps


def _rethink_report_gaps(text: str) -> list[str]:
    """Return what the report format lacks: a fenced report whose first line starts with `RETHINK:`, or a verdict."""
    reports = "\n".join(block for block in _fenced_blocks(text) if block.strip().startswith("RETHINK:"))
    if not reports:
        return ["no fenced report whose first line starts with 'RETHINK:'"]
    return [
        f"the RETHINK: report does not offer the verdict {verdict}"
        for verdict in RETHINK_VERDICTS
        if re.search(rf"\b{re.escape(verdict)}\b", reports) is None
    ]


class AgentModelsTest(unittest.TestCase):
    def test_each_role_has_its_agreed_model_and_effort(self) -> None:
        """R1.1, R10.1: each role runs on its agreed model and effort."""
        expected = {
            "test-writer": ("opus", "medium"),
            "implementer": ("opus", "medium"),
            "spec-reviewer": ("sonnet", "high"),
            "code-reviewer": ("opus", "high"),
            "security-reviewer": ("opus", "xhigh"),
            "finding-verifier": ("opus", "high"),
        }

        actual = {}
        for role in expected:
            fields = read_frontmatter(AGENTS_DIR / f"{role}.md")
            actual[role] = (fields.get("model"), fields.get("effort"))

        self.assertEqual(actual, expected)


class RethinkerAgentTest(unittest.TestCase):
    maxDiff = None  # a failure lists every gap, not the first one

    def test_the_rethinker_is_a_read_only_opus_max_agent(self) -> None:
        """R8.1, R1.1: agents/rethinker.md defines the rethinker on opus at max effort, read-only by its tools (its
        tools: list has no Edit, Write or NotebookEdit), that explains why a stuck task's attempts keep failing and
        what to do differently, in a fenced report that starts with a `RETHINK:` line and offers the verdicts
        NEW APPROACH, ADJUST and PLAN CHANGE.

        The hooks' read-only rule for the rethinker role is tested in test_roles.py.
        """
        self.assertTrue(RETHINKER.is_file(), f"{RETHINKER} does not exist")
        text = RETHINKER.read_text(encoding="utf-8")  # universal newlines, like read_frontmatter

        gaps = (
            _rethinker_frontmatter_gaps(read_frontmatter(RETHINKER))
            + _rethinker_purpose_gaps(text)
            + _rethink_report_gaps(text)
        )

        self.assertEqual(gaps, [])


if __name__ == "__main__":
    unittest.main()
