"""Contract tests for the plugin's agent definitions in agents/*.md."""

from __future__ import annotations

import re
import unittest

from .plugin_files import AGENTS_DIR, read_frontmatter

RETHINKER = AGENTS_DIR / "rethinker.md"
RETHINKER_FIELDS = {"name": "rethinker", "model": "opus", "effort": "max"}
PROCESS_REVIEWER = AGENTS_DIR / "process-reviewer.md"
PROCESS_REVIEWER_FIELDS = {"name": "process-reviewer", "model": "sonnet", "effort": "high"}
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
# R7.1's flow record and purpose, in plain words, so a reworded or wrapped sentence counts.
_FLOW_RECORD_PARTS = {
    "review rounds": re.compile(r"\breview rounds?\b|\brounds? of (?:the )?reviews?\b"),
    "escalations": re.compile(r"\bescalat(?:ions?|ed|es|ing)\b"),
    "rethinks": re.compile(r"\brethink(?:s|ing)?\b"),
    "blocked subagents": re.compile(
        r"\bblocked\b[^.]{0,40}?\b(?:sub)?agents?\b|\b(?:sub)?agents?\b[^.]{0,40}?\bblocked\b"
    ),
    "gate events": re.compile(r"\bgates?\b[^.]{0,40}?\bevents?\b|\bevents?\b[^.]{0,40}?\bgates?\b"),
    "user corrections": re.compile(
        r"\b(?:user|person)\b[^.]{0,40}?\bcorrect(?:ions?|ed|s)\b|\bcorrect(?:ions?|ed)\b[^.]{0,40}?\b(?:user|person)\b"
    ),
}
_IMPROVES_THE_PLUGIN = re.compile(
    r"\bimprove(?:ments?|s)?\b[^.]{0,60}?\bplugin\b|\bplugin\b[^.]{0,60}?\bimprove(?:ments?|s)?\b"
)
# The parts R7.1 and the design give each note of the `IMPROVEMENT NOTES:` report.
_NOTE_PARTS = {
    "its title": re.compile(r"\btitle\b"),
    "its evidence": re.compile(r"\bevidence\b"),
    "the skill or agent it affects": re.compile(r"\bskill\b[^.]{0,30}?\bagent\b|\bagent\b[^.]{0,30}?\bskill\b"),
    "the suggested change": re.compile(
        r"\b(?:suggest(?:ed|s)?|propos(?:ed|es?)|recommend(?:ed|s)?)\b[^.]{0,30}?\bchanges?\b"
        r"|\bchanges?\b[^.]{0,30}?\b(?:suggest|propos|recommend)"
    ),
}
# R7.3: what a note never carries, each named in a sentence that leaves it out, and the general wording instead.
_LEAVE_OUT = r"\b(?:never|not|no|nor|without|leaves? out|omit\w*|exclud\w*|forbidden|prohibited)\b[^.]{0,160}?"
_NOTE_PRIVACY_RULE = {
    "notes leave out source code": re.compile(_LEAVE_OUT + r"\bcode\b"),
    "notes leave out secrets": re.compile(_LEAVE_OUT + r"\b(?:secrets?|credentials?)\b"),
    "notes leave out personal data": re.compile(_LEAVE_OUT + r"\bpersonal (?:data|information)\b"),
    "notes describe the problem in general terms instead": re.compile(
        r"\bgeneral(?:ly| terms)\b|\bgeneric(?:ally)?\b|\bin the abstract\b"
    ),
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


def _read_only_frontmatter_gaps(fields: dict[str, str], expected_fields: dict[str, str]) -> list[str]:
    """Return one message per frontmatter field that differs from R1.1's expected value or lets the agent write files.

    An agent without a `tools:` list inherits every tool, Edit and Write included, so a missing list is a gap.
    """
    gaps = [
        f"frontmatter {key}: is {fields.get(key)!r}, expected {expected!r}"
        for key, expected in expected_fields.items()
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


def _process_reviewer_purpose_gaps(text: str) -> list[str]:
    """Return a message for each part of R7.1's flow record, or its purpose, that the agent's text does not name."""
    plain = _plain_words(text)
    gaps = [
        f"neither the description nor the body says it reviews the {part}"
        for part, pattern in _FLOW_RECORD_PARTS.items()
        if pattern.search(plain) is None
    ]
    if _IMPROVES_THE_PLUGIN.search(plain) is None:
        gaps.append("neither the description nor the body says it proposes improvements to the plugin")
    return gaps


def _improvement_notes_report_gaps(text: str) -> list[str]:
    """Return what the report lacks: a fenced block starting with `IMPROVEMENT NOTES:`, or one of a note's parts."""
    reports = [block for block in _fenced_blocks(text) if block.strip().startswith("IMPROVEMENT NOTES:")]
    if not reports:
        return ["no fenced report whose first line starts with 'IMPROVEMENT NOTES:'"]
    fields = _plain_words("\n".join(reports))
    return [
        f"the IMPROVEMENT NOTES: report does not give {part} for each note"
        for part, pattern in _NOTE_PARTS.items()
        if pattern.search(fields) is None
    ]


def _note_privacy_gaps(text: str) -> list[str]:
    """Return a message for each part of R7.3's rule that the agent's text does not state."""
    plain = _plain_words(text)
    return [
        f"the instructions do not say {part}"
        for part, pattern in _NOTE_PRIVACY_RULE.items()
        if pattern.search(plain) is None
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
            _read_only_frontmatter_gaps(read_frontmatter(RETHINKER), RETHINKER_FIELDS)
            + _rethinker_purpose_gaps(text)
            + _rethink_report_gaps(text)
        )

        self.assertEqual(gaps, [])


class ProcessReviewerAgentTest(unittest.TestCase):
    maxDiff = None  # a failure lists every gap, not the first one

    def test_the_process_reviewer_is_a_read_only_sonnet_agent(self) -> None:
        """R1.1, R7.1, R7.3: agents/process-reviewer.md defines the process-reviewer on sonnet at high effort,
        read-only by its tools (its tools: list has no Edit, Write or NotebookEdit), that reviews the flow's record
        (review rounds, escalations, rethinks, blocked subagents, gate events, user corrections) and proposes
        improvements to the plugin in a fenced report that starts with an `IMPROVEMENT NOTES:` line and gives each
        note's title, evidence, affected skill or agent and suggested change; its notes never carry source code,
        secrets or personal data and describe the problem in general terms instead.

        Dispatching it and saving its notes belong to develop-feature (T50); the hooks' read-only rule for the
        process-reviewer role is tested in test_roles.py.
        """
        self.assertTrue(PROCESS_REVIEWER.is_file(), f"{PROCESS_REVIEWER} does not exist")
        text = PROCESS_REVIEWER.read_text(encoding="utf-8")  # universal newlines, like read_frontmatter

        gaps = (
            _read_only_frontmatter_gaps(read_frontmatter(PROCESS_REVIEWER), PROCESS_REVIEWER_FIELDS)
            + _process_reviewer_purpose_gaps(text)
            + _improvement_notes_report_gaps(text)
            + _note_privacy_gaps(text)
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
