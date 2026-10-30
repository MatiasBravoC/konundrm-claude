"""Contract tests for the plugin's agent definitions in agents/*.md."""

from __future__ import annotations

import re
import unittest

from .plugin_files import AGENTS_DIR, read_frontmatter

RETHINKER = AGENTS_DIR / "rethinker.md"
RETHINKER_FIELDS = {"name": "rethinker", "model": "opus", "effort": "max"}
WRITING_TOOLS = frozenset({"Edit", "Write", "NotebookEdit"})
RETHINK_VERDICTS = ("NEW APPROACH", "ADJUST", "PLAN CHANGE")
WRITERS = (AGENTS_DIR / "test-writer.md", AGENTS_DIR / "implementer.md")

# R8.1's two questions, in plain words. They run on text from _plain_words, so a reworded or wrapped sentence counts.
_WHY_ATTEMPTS_FAIL = re.compile(r"\b(?:why|reasons?|root[- ]causes?)\b[^.]{0,80}?\bfail(?:s|ed|ing|ures?)?\b")
_WHAT_TO_DO_DIFFERENTLY = re.compile(r"\b(?:different(?:ly)?|instead|alternatives?)\b")

# R5.2's DECISION report: a `Status:` line offering DECISION, and a `Decision:` field naming these parts.
_DECISION_STATUS = re.compile(r"^\s*status:[^\n]*\bdecision\b", re.MULTILINE)
_DECISION_FIELD = re.compile(r"^\s*decision:", re.MULTILINE)
_DECISION_PARTS = {
    "the options": re.compile(r"\b(?:options?|approach(?:es)?|alternatives?)\b"),
    "each option's advantages": re.compile(r"\b(?:advantages?|pros|benefits?|upsides?|strengths?)\b"),
    "each option's disadvantages": re.compile(r"\b(?:disadvantages?|cons|drawbacks?|downsides?|weaknesses?)\b"),
    "a recommendation": re.compile(r"\brecommend(?:s|ed|ations?)?\b"),
}
# R5.2's rule, in plain words outside the report format, so a reworded or wrapped sentence counts.
_DECISION_RULE = {
    "the task admits two or more reasonable approaches": re.compile(
        r"\b(?:two or more|2 or more|more than one|several|multiple)\b[^.]{0,60}?\b(?:approach|option|alternative|way)"
    ),
    "the plan did not decide between them": re.compile(
        r"\b(?:plan|design|tasks md|design md)\b[^.]{0,80}?\b(?:not|never|nor)\b"
        r"[^.]{0,30}?\b(?:decide|settle|choose|pick)|\bundecided\b"
    ),
    "the agent does not choose one itself": re.compile(
        r"\binstead of (?:choosing|picking|deciding)\b"
        r"|\b(?:do not|don't|never|without) (?:choos|pick|decid)"
    ),
    "it returns the DECISION report": re.compile(r"\bstatus: decision\b|\bdecision report\b"),
}


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


def _prose(text: str) -> str:
    """Return a Markdown text without its fenced blocks, in plain words, with `.md` as ` md` so a sentence goes on."""
    kept: list[str] = []
    inside = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            inside = not inside
        elif not inside:
            kept.append(line)
    return _plain_words(re.sub(r"\.md\b", " md", "\n".join(kept)))


def _decision_report_gaps(text: str) -> list[str]:
    """Return what R5.2's report lacks: a fenced report offering `Status: DECISION`, its `Decision:` field and parts."""
    reports = [block.lower() for block in _fenced_blocks(text) if _DECISION_STATUS.search(block.lower())]
    if not reports:
        return ["no fenced report offers 'Status: DECISION'"]
    with_field = [block for block in reports if _DECISION_FIELD.search(block)]
    if not with_field:
        return ["the fenced report offering 'Status: DECISION' has no 'Decision:' field"]
    fields = _plain_words("\n".join(with_field))
    return [
        f"the DECISION report does not name {part}"
        for part, pattern in _DECISION_PARTS.items()
        if pattern.search(fields) is None
    ]


def _decision_rule_gaps(text: str) -> list[str]:
    """Return a message for each part of R5.2's rule that the instructions outside the report format do not state."""
    prose = _prose(text)
    return [
        f"the instructions do not say {part}"
        for part, pattern in _DECISION_RULE.items()
        if pattern.search(prose) is None
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


class WritersDecisionTest(unittest.TestCase):
    maxDiff = None  # a failure lists every gap, not the first one

    def test_writers_return_a_decision_instead_of_choosing(self) -> None:
        """R5.2: when a task admits two or more reasonable approaches that the plan (tasks.md, design.md) did not
        decide, the test-writer and the implementer do not choose one: their instructions say to return a fenced
        report offering `Status: DECISION`, whose `Decision:` field gives the options, each one's advantages and
        disadvantages, and a recommendation.

        Pausing the task and asking the user is develop-feature's side of R5.2, not tested here.
        """
        gaps = []
        for agent in WRITERS:
            text = agent.read_text(encoding="utf-8")  # universal newlines, like read_frontmatter
            gaps += [f"{agent.name}: {gap}" for gap in _decision_report_gaps(text) + _decision_rule_gaps(text)]

        self.assertEqual(gaps, [])


if __name__ == "__main__":
    unittest.main()
