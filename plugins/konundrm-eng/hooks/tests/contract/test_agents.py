"""Contract tests for the plugin's agent definitions in agents/*.md."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from .plugin_files import AGENTS_DIR, SKILLS_DIR, read_frontmatter, read_section
from .test_flows import _NEGATION, _in_one_sentence, _section_blocks, _sentences

RETHINKER = AGENTS_DIR / "rethinker.md"
RETHINKER_FIELDS = {"name": "rethinker", "model": "opus", "effort": "max"}
PROCESS_REVIEWER = AGENTS_DIR / "process-reviewer.md"
PROCESS_REVIEWER_FIELDS = {"name": "process-reviewer", "model": "sonnet", "effort": "high"}
# The tools the role hook guards: the PreToolUse matcher in hooks/hooks.json.
WRITING_TOOLS = frozenset({"Edit", "Write", "MultiEdit", "NotebookEdit"})
RETHINK_VERDICTS = ("NEW APPROACH", "ADJUST", "PLAN CHANGE")
TEST_WRITER = AGENTS_DIR / "test-writer.md"
WRITERS = (TEST_WRITER, AGENTS_DIR / "implementer.md")

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
# R2.1 (002): which tests an agent runs, as keywords that must share one sentence of its `## Rules` section.
_RUNS = re.compile(r"\b(?:run|runs|running|execute|executes|executing|invoke|invokes)\b")
_ONLY = re.compile(r"\bonly\b")
_TESTS = re.compile(r"\btests?\b")
_IT_WROTE = re.compile(r"\b(?:wrote|written|writes)\b")
_IT_CHANGED = re.compile(r"\b(?:chang(?:ed|es)|edit(?:ed|s)|updat(?:ed|es)|modifi(?:ed|es))\b")
_CHECK_COMMAND = re.compile(r"\bcheck\b")
_FULL_SUITE = re.compile(r"\b(?:full|whole|entire|complete)\b(?: \S+){0,3}? suites?\b")
_TEST_WRITER_RUN_SCOPE = {
    "it runs only the tests it wrote or changed": (_RUNS, _ONLY, _TESTS, _IT_WROTE, _IT_CHANGED),
    "it never runs the project's check command": (_NEGATION, _RUNS, _CHECK_COMMAND),
    "it never runs the full test suite": (_NEGATION, _RUNS, _FULL_SUITE),
}
# R2.2 (002): the reviewers rely on the verification output the orchestrator gives them instead of rerunning it.
REVIEWERS = tuple(AGENTS_DIR / f"{role}-reviewer.md" for role in ("spec", "code", "security"))
DISPATCH_PROMPTS = SKILLS_DIR / "develop-feature" / "reference" / "dispatch-prompts.md"
REVIEWER_PROMPTS = ("spec-reviewer (task)", "spec-reviewer (whole feature)", "code-reviewer", "security-reviewer")
_ORCHESTRATOR = re.compile(r"\borchestrator'?s?\b")
_VERIFICATION = re.compile(r"\b(?:verif\w*|checks?)\b")
_OUTPUT = re.compile(r"\boutputs?\b")
_OUTPUT_FIELD = (_ORCHESTRATOR, _VERIFICATION, _OUTPUT, re.compile(r"<[^<>]+>"))  # one prompt line, with a placeholder
_MINIMAL_REPRODUCTION = re.compile(r"\b(?:minimal|smallest)\b(?: \S+){0,2}? repro\w*")
_REVIEWER_RUN_SCOPE = {
    "it uses the verification output the orchestrator gives it": (_ORCHESTRATOR, _VERIFICATION, _OUTPUT),
    "it never runs the project's check command": (_NEGATION, _RUNS, _CHECK_COMMAND),
    "it never runs the full test suite": (_NEGATION, _RUNS, _FULL_SUITE),
    "a finding that needs running something runs only that test or a minimal reproduction": (
        _RUNS,
        _ONLY,
        _TESTS,
        _MINIMAL_REPRODUCTION,
    ),
}
# R2.3 (002): the finding verifier runs only what its finding needs, never the check command.
FINDING_VERIFIER = AGENTS_DIR / "finding-verifier.md"
_FINDING_NEEDS = re.compile(r"\b(?:needs?|requires?)\b")
_FINDING_VERIFIER_RUN_SCOPE = {
    "it runs only the tests or reproductions its finding needs": (
        _RUNS,
        _ONLY,
        _TESTS,
        re.compile(r"\brepro\w*"),
        _FINDING_NEEDS,
    ),
    "it never runs the project's check command": (_NEGATION, _RUNS, _CHECK_COMMAND),
}
# R2.4 (002): the implementer runs the full suite only in the check, once at the end; before, its test and nearby tests.
IMPLEMENTER = AGENTS_DIR / "implementer.md"
_RUNS_OR_RERUNS = re.compile(r"\b(?:re)?(?:run|runs|running|execute|executes|executing|invoke|invokes)\b")
_SUITE = re.compile(r"\bsuites?\b")
_CODE_IT_CHANGES = re.compile(r"\b(?:chang|edit|touch|modif)\w*")
_IMPLEMENTER_RUN_SCOPE = {
    "it runs the full test suite only inside the check command": (_RUNS, _FULL_SUITE, _ONLY, _CHECK_COMMAND),
    "it runs the check once, at the end of each dispatch": (
        _RUNS,
        _CHECK_COMMAND,
        re.compile(r"\bonce\b"),
        re.compile(r"\b(?:end|last|final(?:ly)?)\b"),
    ),
    "before that it runs only the task's test and the tests of the code it changes": (
        _RUNS,
        _ONLY,
        re.compile(r"\btask'?s?\b"),
        _TESTS,
        _CODE_IT_CHANGES,
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
    """Return what the report format lacks: a fenced report whose first line starts with `RETHINK:`, its `Verdict:`
    line, or a verdict on that line; a verdict outside R8.1's three is a gap too.

    The verdicts are read from the `Verdict:` line alone, split on `|`, so a verdict named elsewhere in the report
    does not count as offered.
    """
    reports = [block for block in _fenced_blocks(text) if block.strip().startswith("RETHINK:")]
    if not reports:
        return ["no fenced report whose first line starts with 'RETHINK:'"]
    verdict_lines = [
        line.strip()[len("Verdict:") :]
        for block in reports
        for line in block.splitlines()
        if line.strip().startswith("Verdict:")
    ]
    if not verdict_lines:
        return ["the RETHINK: report has no 'Verdict:' line"]
    offered = [part.strip() for line in verdict_lines for part in line.split("|")]
    missing = [
        f"the RETHINK: report's Verdict: line does not offer {verdict}"
        for verdict in RETHINK_VERDICTS
        if verdict not in offered
    ]
    extra = [
        f"the RETHINK: report's Verdict: line offers {verdict!r}, which is not one of {list(RETHINK_VERDICTS)}"
        for verdict in offered
        if verdict not in RETHINK_VERDICTS
    ]
    return missing + extra


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


def _section_rule_gaps(path: Path, heading: str, rules: dict[str, tuple[re.Pattern[str], ...]]) -> list[str]:
    """Return `<file>: ## <heading> does not say <rule>` for each rule whose patterns share no sentence of the section.

    Each rule maps its description to keyword patterns that must all match one sentence of one paragraph or list
    item of the file's `## <heading>` section (lowercased, without backticks, wrapped lines joined).
    """
    blocks = _section_blocks(path, heading)
    return [
        f"{path.name}: ## {heading} does not say {rule}"
        for rule, patterns in rules.items()
        if not any(_in_one_sentence(block, *patterns) for block in blocks)
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
        tools: list has no Edit, Write, MultiEdit or NotebookEdit), that explains why a stuck task's attempts keep
        failing and what to do differently, in a fenced report that starts with a `RETHINK:` line and whose
        `Verdict:` line offers exactly the verdicts NEW APPROACH, ADJUST and PLAN CHANGE, separated by `|`.

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
        read-only by its tools (its tools: list has no Edit, Write, MultiEdit or NotebookEdit), that reviews the
        flow's record (review rounds, escalations, rethinks, blocked subagents, gate events, user corrections) and
        proposes improvements to the plugin in a fenced report that starts with an `IMPROVEMENT NOTES:` line and gives
        each note's title, evidence, affected skill or agent and suggested change; its notes never carry source code,
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


class AgentRunScopeTest(unittest.TestCase):
    maxDiff = None  # a failure lists every gap, not the first one

    def test_test_writer_runs_only_its_own_tests(self) -> None:
        """R2.1: 002 the `## Rules` section of agents/test-writer.md, where its other "never" rules live, says it runs
        only the tests it wrote or changed (a new test and an existing one it changed), never the project's check
        command and never the full test suite, each in one sentence.

        Only that section is read: Process step 3 ("Run only that test") names only the new test, and the
        test-driven-development skill the agent loads is outside this rule.
        """
        gaps = _section_rule_gaps(TEST_WRITER, "Rules", _TEST_WRITER_RUN_SCOPE)

        self.assertEqual(gaps, [])

    def test_reviewers_rely_on_the_orchestrators_verification_output(self) -> None:
        """R2.2: 002 the `## Rules` section of the spec, code and security reviewers says, each part in one sentence,
        that they use the verification output the orchestrator gives them, never run the project's check command nor
        the full test suite, and run only that test or a minimal reproduction when a finding depends on running
        something; and the fenced prompt of each reviewer section of develop-feature's dispatch-prompts.md has a line
        with a `<…>` placeholder for the orchestrator's verification output.

        The code-reviewer prompt's "implementer's GREEN report says" line is the implementer's claim, not that output.
        """
        gaps = [gap for reviewer in REVIEWERS for gap in _section_rule_gaps(reviewer, "Rules", _REVIEWER_RUN_SCOPE)]
        for heading in REVIEWER_PROMPTS:
            prompt = "\n".join(_fenced_blocks(read_section(DISPATCH_PROMPTS, heading))).lower()
            if not any(all(p.search(line) for p in _OUTPUT_FIELD) for line in prompt.splitlines()):
                gaps.append(f"dispatch-prompts.md: ## {heading} prompt has no field for the orchestrator's output")

        self.assertEqual(gaps, [])

    def test_finding_verifier_runs_only_what_its_finding_needs(self) -> None:
        """R2.3: 002 the `## Rules` section of agents/finding-verifier.md, where its other rules live, says, each part
        in one sentence, that it runs only the tests or reproductions its finding needs and never runs the project's
        check command ("only" already rules out the full suite).

        Process step 4 ("run the existing tests") and the frontmatter description are outside this rule.
        """
        gaps = _section_rule_gaps(FINDING_VERIFIER, "Rules", _FINDING_VERIFIER_RUN_SCOPE)

        self.assertEqual(gaps, [])

    def test_implementer_runs_the_full_suite_only_in_the_final_check(self) -> None:
        """R2.4: 002 the `## Process` section of agents/implementer.md, whose steps run the tests and the check, says,
        each part in one sentence, that it runs the full test suite only inside the project's check command, runs the
        check once at the end of each dispatch, and before that runs only the task's test and the tests of the code it
        changes; and no sentence of `## Process` or `## Rules` that runs or reruns a suite leaves out the check.

        Step order, not keywords, places the check after the other runs. Step 5's "Rerun the tests" names no suite, so
        only the "only" rule narrows it; the GREEN report's `Check:` line is the report format, not an instruction.
        """
        gaps = _section_rule_gaps(IMPLEMENTER, "Process", _IMPLEMENTER_RUN_SCOPE)
        for heading in ("Process", "Rules"):
            gaps += [
                f"implementer.md: ## {heading} runs a suite outside the check: {sentence.strip()}"
                for block in _section_blocks(IMPLEMENTER, heading)
                for sentence in _sentences(block)
                if _RUNS_OR_RERUNS.search(sentence) and _SUITE.search(sentence) and not _CHECK_COMMAND.search(sentence)
            ]

        self.assertEqual(gaps, [])


# A task that lists several tests, and an adjustment (004 R2.1-R2.6, R3.9, R4.3): what the writers, the spec
# reviewer, the rethinker and the test-driven-development skill say about them. Keywords of each rule inside one
# sentence of the named `## ` section.
TDD_SKILL = SKILLS_DIR / "test-driven-development" / "SKILL.md"
SPEC_REVIEWER = AGENTS_DIR / "spec-reviewer.md"
_MANY_TESTS_FIELD = re.compile(r"\btests:")
_MANY_EVERY = re.compile(r"\b(?:every|each|all)\b")
_MANY_ONE_BEHAVIOR_PER_TEST = re.compile(r"\bone behaviou?r per test\b|\bone test per behaviou?r\b")
_MANY_REPORT_PER_TEST = re.compile(r"\breports?\b(?: \S+){0,3} per test\b")
_MANY_ONE_TEST_PER_DISPATCH = re.compile(r"\bone test per dispatch\b")
_MANY_PROPERTY_TESTS = re.compile(r"\bproperty tests\b")
_MANY_INVARIANTS = re.compile(r"\binvariants\b")
_MANY_LEAVE_AS_THEY_ARE = re.compile(r"\bleave as they are\b")
_MANY_ONLY = re.compile(r"\bonly\b")
_MANY_BLOCKED = re.compile(r"\bblocked\b")
_MANY_DECISION = re.compile(r"\bdecision\b")
_MANY_WHOLE_TASK = re.compile(r"\bwhole task\b")
_MANY_RED_REPORTS = re.compile(r"\bred reports\b")
_MANY_FAILING_TESTS = re.compile(r"\bfailing tests\b")
_MANY_ONE_AT_A_TIME = re.compile(r"\bone at a time\b")
_MANY_STILL_FAIL = re.compile(r"\bstill fail\b")
_MANY_FIX_ROUND = re.compile(r"\bfix[- ]round\b")
_MANY_ADJUSTMENT = re.compile(r"\badjustment\b")
_MANY_GREEN_BY_DESIGN = re.compile(r"\bgreen by design\b")
_MANY_ADJUSTMENTS_REQUEST = re.compile(r"\badjustment's request\b")
_MANY_DEMAND = re.compile(r"\bdemands?\b")
_MANY_EVERY_LINE = re.compile(r"\bevery line\b")
_MANY_OWN_TEST = re.compile(r"\bown test\b")
_MANY_CONSOLIDATED_TASK = re.compile(r"\bconsolidated task\b")
_MANY_SPLIT = re.compile(r"\bsplit\b")
_MANY_PLAN_CHANGE = re.compile(r"\bplan change\b")
_MANY_TEST_WRITER_SUBAGENT = re.compile(r"\btest-writer subagent\b")
_MANY_BEFORE_STOPPING = re.compile(r"\bbefore you stop\b|\bbefore stopping\b|\bbefore the stop\b")
_MANY_USER = re.compile(r"\buser\b")
_MANY_ONE_TEST_THEN_STOP = re.compile(r"\bone test\b.{0,40}?\bstop\b")
_MANY_GREEN_TESTS_LINE = re.compile(r"^\s*tests:", re.MULTILINE)
_MANY_GREEN_PER_TEST_LINE = re.compile(r"^- <path>::<name>: red before its code, green after\b", re.MULTILINE)
# (file, `## ` section, the rule, the patterns one of its sentences must all match).
_MANY_TESTS_RULES: tuple[tuple[Path, str, str, tuple[re.Pattern[str], ...]], ...] = (
    (
        TEST_WRITER,
        "Process",
        "R2.1 it writes every test the task lists under Tests:, one behavior per test",
        (_MANY_TESTS_FIELD, _MANY_EVERY, _MANY_ONE_BEHAVIOR_PER_TEST),
    ),
    (TEST_WRITER, "Process", "R2.1 it returns one report per test", (_MANY_REPORT_PER_TEST,)),
    (
        TEST_WRITER,
        "Process",
        "R3.9 it writes the property tests the dispatch lists for the task's invariants",
        (_MANY_PROPERTY_TESTS, _MANY_INVARIANTS),
    ),
    (
        TEST_WRITER,
        "Process",
        "R2.2 it leaves the tests the dispatch names as they are and writes or fixes only the one asked for",
        (_MANY_LEAVE_AS_THEY_ARE, _MANY_ONLY),
    ),
    (
        TEST_WRITER,
        "Rules",
        "R2.1 a BLOCKED or a DECISION is for the whole task",
        (_MANY_BLOCKED, _MANY_DECISION, _MANY_WHOLE_TASK),
    ),
    (
        IMPLEMENTER,
        "Process",
        "R2.3 it reads the RED reports and the failing tests of the task",
        (_MANY_RED_REPORTS, _MANY_FAILING_TESTS),
    ),
    (
        IMPLEMENTER,
        "Process",
        "R2.3 it makes several failing tests pass one at a time, seeing each still fail before its code",
        (_MANY_FAILING_TESTS, _MANY_ONE_AT_A_TIME, _MANY_STILL_FAIL),
    ),
    (
        IMPLEMENTER,
        "Process",
        "R4.3 in a fix round or an adjustment the task's tests are green by design",
        (_MANY_FIX_ROUND, _MANY_ADJUSTMENT, _MANY_GREEN_BY_DESIGN),
    ),
    (
        IMPLEMENTER,
        "Rules",
        "R4.3 nothing beyond what the task's tests, or an adjustment's request, demand",
        (_MANY_ADJUSTMENTS_REQUEST, _MANY_DEMAND),
    ),
    (
        SPEC_REVIEWER,
        "Process",
        "R2.6 it checks every line of a Tests: list against that line's own test",
        (_MANY_TESTS_FIELD, _MANY_EVERY_LINE, _MANY_OWN_TEST),
    ),
    (
        RETHINKER,
        "Process",
        "R2.5 a consolidated task whose behaviors do not belong together is split, as a PLAN CHANGE",
        (_MANY_CONSOLIDATED_TASK, _MANY_SPLIT, _MANY_PLAN_CHANGE),
    ),
    (
        TDD_SKILL,
        "Contract",
        "R2.4 only for the test-writer subagent a task may list several behaviors under Tests:",
        (_MANY_ONLY, _MANY_TEST_WRITER_SUBAGENT, _MANY_TESTS_FIELD),
    ),
    (
        TDD_SKILL,
        "Workflow",
        "R2.4 as the test-writer subagent, every test of a task that lists several is written before stopping",
        (_MANY_TEST_WRITER_SUBAGENT, _MANY_EVERY, _MANY_BEFORE_STOPPING),
    ),
    (
        TDD_SKILL,
        "Workflow",
        "R2.4 with the user the rule stays one test, then stop",
        (_MANY_USER, _MANY_ONE_TEST_THEN_STOP),
    ),
)


class TaskWithSeveralTestsTest(unittest.TestCase):
    maxDiff = None  # a failure lists every gap, not the first one

    def test_writers_handle_a_task_that_lists_several_tests(self) -> None:
        """R2.1, R2.2, R2.3, R2.4, R2.5, R2.6, R3.9, R4.3: 004 the roles build a task that lists several tests.

        agents/test-writer.md's `## Process` writes every test the task lists under `Tests:`, one behavior per test,
        returns one report per test, writes the property tests the dispatch lists for the task's invariants and
        leaves as they are the tests the dispatch names; its `## Rules` make a BLOCKED or a DECISION a report for
        the whole task; and no sentence of the file still limits it to one test per dispatch.
        agents/implementer.md's `## Process` reads the RED reports and the failing tests, makes several failing tests
        pass one at a time, seeing each still fail before its code, and treats the task's tests as green by design in
        a fix round or an adjustment; its `## Rules` allow nothing beyond what the task's tests, or an adjustment's
        request, demand; and its GREEN report has a `Tests:` line and a line per test that says it was red before
        its code. agents/spec-reviewer.md's `## Process` checks every line of a `Tests:` list against that line's own
        test. agents/rethinker.md's `## Process` names a consolidated task whose behaviors do not belong together, to
        split as a PLAN CHANGE. The test-driven-development skill's `## Contract` lets a task list several behaviors
        under `Tests:` only for the test-writer subagent, and its `## Workflow` says that, as that subagent, every
        test of such a task is written before stopping, and that with the user the rule stays one test, then stop.
        """
        gaps = [
            f"{path.parent.name if path.name == 'SKILL.md' else path.name}: ## {section} does not say {rule}"
            for path, section, rule, patterns in _MANY_TESTS_RULES
            if not any(_in_one_sentence(block, *patterns) for block in _section_blocks(path, section))
        ]
        test_writer = TEST_WRITER.read_text(encoding="utf-8")
        if _MANY_ONE_TEST_PER_DISPATCH.search(_plain_words(test_writer)):
            gaps.append("test-writer.md: still limits the test-writer to one test per dispatch")
        fenced = _fenced_blocks(IMPLEMENTER.read_text(encoding="utf-8"))
        green_reports = [block for block in fenced if block.strip().startswith("GREEN:")]
        if not any(_MANY_GREEN_TESTS_LINE.search(report.lower()) for report in green_reports):
            gaps.append("implementer.md: the GREEN report has no `Tests:` line for the task's tests")
        if not any(_MANY_GREEN_PER_TEST_LINE.search(report) for report in green_reports):
            gaps.append("implementer.md: the GREEN report has no line per test saying it was red before its code")

        self.assertEqual(gaps, [])


if __name__ == "__main__":
    unittest.main()
