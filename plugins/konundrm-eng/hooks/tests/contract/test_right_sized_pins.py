"""Contract tests for the edges of the right-sized flow (004) that a single edit could remove unnoticed.

The feature's final review removed or inverted one rule at a time in the skills, agents, prompts and templates and ran
the contract tests after each edit. Every rule here is one whose loss left them all green. A rule is
`(source, the rule, the patterns one sentence of the source must all match)`, read on the blocks of `_split_blocks`
(lowercased, without backticks, single-spaced), as the `_EdgeRules` of test_flows.py are.
"""

from __future__ import annotations

import re
import unittest

from .plugin_files import AGENTS_DIR, SKILLS_DIR
from .test_flows import (
    _ADJUST_OUTPUT_FIELD,
    _EDGE_COMMITTING,
    _EDGE_SOURCES,
    _SIZED_SKILL,
    DEVELOP_FEATURE_DIR,
    _after_table_rows,
    _blocks,
    _in_one_sentence,
    _section_blocks,
    _sized_prompt_blocks,
    _subsection_blocks,
)

_PinRules = tuple[tuple[str, str, tuple[str, ...]], ...]

_PIN_SOURCES = {
    **_EDGE_SOURCES,
    "develop-feature Roles": lambda: _section_blocks(_SIZED_SKILL, "Roles"),
    "develop-feature Model and effort": lambda: _section_blocks(_SIZED_SKILL, "Model and effort"),
    "writing-plans": lambda: _blocks(SKILLS_DIR / "writing-plans" / "SKILL.md"),
    "engineering-standards": lambda: _blocks(SKILLS_DIR / "engineering-standards" / "SKILL.md"),
    "measure-impact": lambda: _blocks(SKILLS_DIR / "measure-impact" / "SKILL.md"),
    "committing-changes Inside develop-feature": lambda: _subsection_blocks(
        _section_blocks(_EDGE_COMMITTING, "Workflow"), "### inside develop-feature"
    ),
    "test-driven-development": lambda: _blocks(SKILLS_DIR / "test-driven-development" / "SKILL.md"),
    "the implementer agent": lambda: _blocks(AGENTS_DIR / "implementer.md"),
    "the rethinker agent": lambda: _blocks(AGENTS_DIR / "rethinker.md"),
    "the test-writer prompt's section": lambda: _section_blocks(
        DEVELOP_FEATURE_DIR / "reference" / "dispatch-prompts.md", "test-writer"
    ),
    "the implementer (adjustment) prompt": lambda: _sized_prompt_blocks("implementer (adjustment)"),
    "the adjustment review prompt": lambda: _sized_prompt_blocks("adjustment review"),
    "the slice-summary template": lambda: _blocks(DEVELOP_FEATURE_DIR / "templates" / "slice-summary.md"),
    "the feature-summary template": lambda: _blocks(DEVELOP_FEATURE_DIR / "templates" / "feature-summary.md"),
    "the tasks.md template": lambda: _blocks(SKILLS_DIR / "writing-plans" / "templates" / "tasks.md"),
}
_PHASE_0 = "develop-feature Phase 0"
_PHASE_3 = "develop-feature Phase 3"
_AFTER = "develop-feature Reviews after a change"
_RETHINK = "develop-feature Rethink"
_PARTITIONS = "develop-feature Parallel partitions"
_ADJUSTMENTS = "develop-feature Adjustments"
_PROCEDURE = "reference/adjustments.md"
_AFTER_ANCHOR = r"\(#reviews-after-a-change\)"

# Planning: what writing-plans and the Standards say about merging, beyond the conditions test_skills.py pins.
_PIN_PLAN_RULES: _PinRules = (
    (
        "writing-plans",
        "R1.1 the lines that belong together are merged first, and only then written as tasks",
        (r"\bmerges the lines that belong together\b", r"\bonly then writes the tasks\b"),
    ),
    (
        "writing-plans",
        "R1.8 the Consolidation: line is low unless the user says otherwise",
        (r"\bchoice: low unless the user says otherwise\b",),
    ),
    (
        "writing-plans",
        "R1.9 a plan change renumbers no task",
        (r"\bplan change adds tasks\b", r"\bno task is renumbered\b"),
    ),
    (
        "the tasks.md template",
        "R1.4 the consolidated example's verify command runs only its tests",
        (r"- verify: <command that runs only these tests>",),
    ),
    (
        "the tasks.md template",
        "R1.4 the first test of the consolidated example names the criterion it asserts",
        (r": <behaviou?r> \(r1\.2\)",),
    ),
    (
        "the tasks.md template",
        "R1.4 the second test of the consolidated example names the criterion it asserts",
        (r": <other behaviou?r> \(r1\.3\)",),
    ),
    (
        "measure-impact",
        "R5.4 features are compared within one version, by review cycles per behavior",
        (r"\bcompare features built with the same version\b", r"\breview cycles per behaviou?r\b"),
    ),
    (
        "writing-plans",
        "R3.9 an invariant goes on the Invariants of the medium or high line whose code makes it hold, and its"
        " property test is written with that line's test",
        (r"\binvariants\b", r"\bmakes it hold\b", r"\bthat line's test\b"),
    ),
    (
        "writing-plans",
        "R3.9 an invariant gets its own property line only when it takes several lines, or a low one, to make it hold",
        (r"\bown property line\b", r"\bonly when it takes several lines\b", r"\ba low one\b"),
    ),
    (
        "writing-plans",
        "R1.3 the lines of a consolidated task have the same owner in the first list",
        (r"\bsame owner in the first list\b", r"\bownership table\b"),
    ),
    (
        "writing-plans",
        "R1.5 a chore merges into the low-risk task it prepares or documents",
        (r"\bchore lines\b", r"\bprepare or document\b", r"\breadme or changelog lines\b"),
    ),
    (
        "writing-plans",
        "R1.7 the approval names the tasks the other Consolidation: choice would merge",
        (r"\bconsolidation: line\b", r"\bnaming the tasks that choice would merge\b"),
    ),
    (
        "engineering-standards",
        "R1.8 low and medium lets up to three cases of one rule share a task",
        (r"\blow and medium\b", r"\bup to three cases\b"),
    ),
    (
        "engineering-standards",
        "R1.4 related low-risk behaviors share one cycle of reviews, each with its own test",
        (r"\bone cycle of reviews\b", r"\beach with its own test\b"),
    ),
)

# Building a task with several tests in one cycle (Phase 3, Rethink, the agents and test-driven-development).
_PIN_BUILD_RULES: _PinRules = (
    (
        _PHASE_3,
        "R2.3 the verify command passes five times in a row",
        (r"\bfive times in a row\b", r"\bevery run must pass\b"),
    ),
    (
        _PHASE_3,
        "R3.5 after the fix round the verify command reruns",
        (r"\bafter the fix round, rerun the verify command yourself\b",),
    ),
    (
        _PHASE_3,
        "R3.9 step 5 dispatches a test-writer only for a property test that is still missing",
        (r"\bfor one still missing, dispatch test-writer\b",),
    ),
    (
        "the test-writer prompt",
        "R3.9 the prompt lists only the invariants no property task covers",
        (r"\binvariants that no property task covers\b",),
    ),
    (
        "the implementer agent",
        "R2.3 the implementer makes the tests pass one at a time, in the task's order",
        (r"\bone at a time\b", r"\btask's order\b|\border the task lists\b"),
    ),
    (
        _PHASE_3,
        "R2.2 a test that passes with a CHARACTERIZATION report is kept only if it asserts what its criterion requires",
        (r"\bif it asserts what its criterion requires, keep it\b",),
    ),
    (
        _PHASE_3,
        "R2.1 a DECISION or BLOCKED report is for the whole task",
        (r"\bdecision or blocked report\b", r"\bwhole task\b"),
    ),
    (
        _PHASE_3,
        "R2.3 a test the implementer reports green before its code is kept if it asserts its criterion, otherwise"
        " sent to a new test-writer",
        (r"\bgreen before its code\b", r"\bkeep it if it asserts its criterion\b", r"\bnew test-writer\b"),
    ),
    (
        _PHASE_3,
        "R2.3 a BLOCKED on one test sends that test back",
        (r"\bblocked on one test\b", r"\bsend that test back\b"),
    ),
    (
        _PHASE_3,
        "R2.2 tests that already pass skip the implementer and continue at step 3, the reviews",
        (r"\bskip\w*(?: \S+){0,2} step 2\b", r"\bfive verifications\b", r"\bcontinue at step 3\b"),
    ),
    (
        _PHASE_3,
        "R3.9 the same dispatch writes the property test only of the invariants no property task covers",
        (r"\bsame dispatch\b", r"\bno property task covers\b"),
    ),
    (
        _PHASE_3,
        "R3.2 after a fix round a high task repeats every review of step 3",
        (r"\bfix[- ]round\b", r"\bevery review of step 3\b", r"\bhigh task\b"),
    ),
    (
        _PHASE_3,
        "R3.1 a red check whose fix belongs in a test file goes to a new test-writer, as in step 4",
        (r"\bcheck fails\b", r"\bfix belongs in a test file\b", r"\bnew test-writer as in step 4\b"),
    ),
    (
        "the test-writer prompt's section",
        "R2.2 a test goes back to a test-writer also when the check failed in its file at the gate",
        (r"\bat the gate the check failed in its file\b",),
    ),
    (
        _RETHINK,
        "R2.5 the new parts are listed after the first, added to the Partitions row and to Depends on:, and the"
        " totals updated",
        (r"\bnew parts\b", r"\bpartition's row\b", r"\bdepends on: line\b", r"\btotals\b"),
    ),
    (_RETHINK, "R2.5 a new part counts its own failed reviews", (r"\bnew part counts its own failed reviews\b",)),
    (
        _RETHINK,
        "R3.1 after a rethink's KEEP every review runs again: a rethink is not under Reviews after a change",
        (r"\breview again from step 3\b", r"\bwith every review\b", _AFTER_ANCHOR),
    ),
    (
        "the rethinker agent",
        "R2.5 several behaviors in a consolidated task are by design, not a cause",
        (r"\bseveral behaviou?rs in a consolidated task are by design\b",),
    ),
    (
        "the rethinker agent",
        "R2.5 the test-writer line names each test that changes",
        (r"\bfor a task with several tests, each test that changes\b",),
    ),
    (
        "the rethinker agent",
        "R2.5 a split always sets the attempt aside",
        (r"\balways when you split the task\b",),
    ),
    (
        "the implementer agent",
        "R2.2 a test whose report is a CHARACTERIZATION is green by design",
        (r"\bcharacterization is green by design\b",),
    ),
    (
        "the implementer agent",
        "R2.3 a BLOCKED names the wrong test and the task's tests that already pass",
        (r"\bstatus: blocked\b", r"\bnaming that test\b", r"\balready pass\b"),
    ),
    (
        "the implementer agent",
        "R1.5 the implementer also makes a step the task's Files: line states for a file",
        (r"\bnothing they do not demand\b", r"\bfiles: line\b", r"\bmodify: <the step>"),
    ),
    (
        "test-driven-development",
        "R2.4 only the test-writer subagent, on a task that lists several tests, writes them in one dispatch",
        (r"\bonly the test-writer subagent\b", r"\bone dispatch\b"),
    ),
    (
        "engineering-standards",
        "R2.1 each behavior the change adds or changes has a test that failed before its code",
        (r"\beach behaviou?r the change adds or changes has a test that failed before its code\b",),
    ),
)

# `## Reviews after a change`: the sentences around its table.
_PIN_AFTER_RULES: _PinRules = (
    (
        _AFTER,
        "R3.1, R4.10 the rule covers a fix round, the verification by risk, the fix of a red check, a change asked on"
        " the task in progress and an adjustment",
        (
            r"\bfix round \(step 4\)",
            r"\bverifying by risk \(step 5\)",
            r"\bred check \(step 6\)",
            r"\btask in progress\b",
            r"\(#adjustments\)",
        ),
    ),
    (
        _AFTER,
        "R3.7 the reviews are never decided from how small the change sounded",
        (r"\bdiff\b", r"\bnever\b", r"\bhow small it sounded\b"),
    ),
    (
        _AFTER,
        "R4.4 an adjustment starts from a clean tree, so git diff HEAD is the change",
        (r"\badjustment starts from a clean tree\b", r"\bgit diff head\b"),
    ),
    (
        _AFTER,
        "R3.1 a hit of the message's old text in code or tests makes it code",
        (r"\bgit grep -n -f -e\b", r"\bhit in code or tests makes it code\b"),
    ),
    (
        _AFTER,
        "R3.1 the search runs with MSYS_NO_PATHCONV=1 when the text holds a /",
        (r"\bgit grep\b", r"\bmsys_no_pathconv=1\b"),
    ),
    (
        _AFTER,
        "R3.1 a change that matches several rows gets every review they name",
        (r"\bseveral rows\b", r"\bevery review they name\b"),
    ),
    (
        _AFTER,
        "R3.5 the verify command reruns first, with the command of a test the change added that it does not cover",
        (r"\brerun the verify command first\b", r"\bcommand of a test the change added\b"),
    ),
    (
        _AFTER,
        "R3.8 the slice summary lists the reviews not repeated and the process-reviewer's flow record carries them",
        (r"\bslice summary\b", r"\bnotes\b", r"\bprocess-reviewer's flow record\b"),
    ),
)
# (the rule, what the row's first cell must say, what its second cell must name, what that cell must not name).
_PIN_TABLE_RULES: tuple[tuple[str, tuple[str, ...], tuple[str, ...], tuple[str, ...]], ...] = (
    (
        "R3.1 a rename goes to the code review alone, with at most that name or path replaced in the tests that use it",
        (r"\bhow the code is built\b", r"\bat most that name or path replaced in the tests that use it\b"),
        (r"\bcode[- ]review(?:er)?\b",),
        (r"\bspec[- ]review(?:er)?\b",),
    ),
    (
        "R3.1 a change to what the code does goes to both reviews whether or not a test asserts it yet",
        (r"\btest that was there\b", r"\bwhat the code does\b", r"\bwhether or not a test asserts it\b"),
        (r"\bspec[- ]review(?:er)?\b", r"\bcode[- ]review(?:er)?\b"),
        (),
    ),
    (
        "R3.1 a message that was only reworded, in the code and in the tests that assert it, with its old text left"
        " nowhere in code, goes to the spec review alone",
        (r"\btest that was there\b", r"\bwhat the code does\b"),
        (
            r"\bspec[- ]review(?:er)? alone when\b",
            r"\bwording of a message\b",
            r"\btests that assert it\b",
            r"\bleft nowhere in code\b",
        ),
        (),
    ),
    (
        "R3.1 only comments that are not tool directives are text that nothing reads",
        (r"\bonly text\b", r"\bnothing reads\b", r"\bnot tool directives\b"),
        (r"\bnone\b",),
        (r"\breview\w*",),
    ),
    (
        "R3.1 a message's wording repeats no review only when no test asserts it, no criterion states it and no code"
        " matches it",
        (r"\bonly text\b", r"\bno test asserts\b", r"\bno criterion states\b", r"\bno code matches\b"),
        (r"\bnone\b",),
        (r"\breview\w*",),
    ),
)

# A change the user asks for: Phase 0, `## Adjustments`, the procedure, its prompts and where it is recorded.
_PIN_REQUEST_RULES: _PinRules = (
    (
        _PROCEDURE,
        "R4.11 an adjustment starts between tasks, from a clean tree, the task in progress committed first",
        (r"\bbetween tasks\b", r"\bclean tree\b", r"\bcommit the task in progress first\b"),
    ),
    (_PROCEDURE, "R4.6 the adjustment is committed alone", (r"\bcommit the adjustment alone\b",)),
    (
        _PROCEDURE,
        "R4.3 the tests are searched for what the request changes, a text that starts with a dash included",
        (r"\bsearch the tests\b", r"\bgit grep -n -f -e\b"),
    ),
    (
        "committing-changes Inside develop-feature",
        "R4.6 the adjustment's commit is typed by what it changes",
        (r"\btype the commit by what it changes\b",),
    ),
    (
        _ADJUSTMENTS,
        "R4.11 a request left for later is made at the next clean point when the session would hand the feature"
        " over first",
        (r"\bwhen it would hand the feature over first\b", r"\bnext clean point\b"),
    ),
    (
        _ADJUSTMENTS,
        "R4.11 a session that handed the feature over tells the user to ask in the session that is building it",
        (r"\bhanded the feature over\b", r"\btells the user to ask in the session that is building it\b"),
    ),
    (
        "develop-feature Slice checkpoint",
        "R1.9 the tasks a change at the pause adds are written as writing-plans writes them",
        (r"\bnew tasks in tasks\.md, written as writing-plans writes them\b",),
    ),
    (
        _PHASE_0,
        "R4.2 a plan change reopens a finished feature only while it is not merged, no later feature has commits"
        " after it and status still lists every one of its tasks as committed",
        (
            r"\breopens\b",
            r"\bnot merged\b",
            r"\bno later feature has commits after it\b",
            r"\bstatus still lists every one of its tasks as committed\b",
        ),
    ),
    (
        _PHASE_0,
        "R4.2 the new tasks of a reopened feature go in a new slice after the last one",
        (r"\breopens\b", r"\bnew slice after the last one\b"),
    ),
    (
        _PHASE_0,
        "R4.2 once a later feature has commits after it, or its notes are gone, the change is a new feature",
        (r"\ba later feature has commits after it\b", r"\bnotes are gone\b", r"\bnew feature\b"),
    ),
    (
        _ADJUSTMENTS,
        "R4.1 the user is told which of the two the request is",
        (r"\bclassif\w*", r"\btell the user which it is\b"),
    ),
    (
        _ADJUSTMENTS,
        "R4.2 on a finished feature a plan change first reopens it as Phase 0 says, or is proposed as a new feature",
        (r"\bfinished\b", r"\breopen\b", r"\(#phase-0-prepare\)", r"\bnew feature\b"),
    ),
    (
        _ADJUSTMENTS,
        "R4.2 a rename changes no design while nothing outside the feature's task files uses the old name, also when"
        " design.md gives that name",
        (
            r"\brename changes no design\b",
            r"\bnothing outside the files the feature's tasks list\b",
            r"\bdesign\.md gives that name\b",
        ),
    ),
    (
        _ADJUSTMENTS,
        "R4.5 a diff that turns out to be a plan change is never committed",
        (r"\bturns out to be a plan change\b", r"\bnever committed\b"),
    ),
    (
        _ADJUSTMENTS,
        "R4.6 a reported defect gets its test first and red for the reported reason, and its commit is typed fix",
        (r"\bdefect\b", r"\bits test first and red\b", r"\btype (?:its commit|it) fix\b"),
    ),
    (
        _ADJUSTMENTS,
        "R4.7, R4.10 a change on the task in progress also updates the plan's lines that state the old detail or name",
        (r"\bedit the criterion\b", r"\bplan's lines that still state the old detail or name\b"),
    ),
    (
        _ADJUSTMENTS,
        "R4.10 the steps the items of a change on the task in progress name by number are the task loop's",
        (r"\bone round\b", r"\bstep of the task loop\b"),
    ),
    (
        _ADJUSTMENTS,
        "R4.3 changes asked together are one adjustment when they make one logical change",
        (r"\bchanges asked together are one adjustment\b", r"\bone logical change\b"),
    ),
    (
        _PROCEDURE,
        "R4.9 at the last slice's pause in live mode the adjustment stays on that slice's branch",
        (r"\bafter the last slice, stay on its branch\b",),
    ),
    (
        _PROCEDURE,
        "R4.9 the new branch of a merged feature is cut from the default branch as the remote has it, without"
        " tracking it",
        (r"\bgit fetch origin <default-branch>", r"\bgit switch -c\b", r"--no-track origin/<default-branch>"),
    ),
    (
        _PROCEDURE,
        "R4.9 with Publish: live the first push of that branch sets its upstream",
        (r"\bpublish: live\b", r"\bfirst push\b", r"\bgit push -u origin\b"),
    ),
    (
        _PROCEDURE,
        "R4.9 a finished feature that is not merged is adjusted on its own branch",
        (r"\bnot merged\b", r"\banother feature's branch\b", r"\bswitch to the feature's own branch first\b"),
    ),
    (
        _PROCEDURE,
        "R4.7 the plan is searched for the old detail, for a rename too",
        (r"\bfor a rename too\b", r"\bsearch the plan\b", r"\bgit grep -n -f -e\b"),
    ),
    (
        _PROCEDURE,
        "R4.3 the tests of a change the code already makes do not stay in the tree",
        (r"\bdo not leave its changes in the tree\b", r"\bstash\b"),
    ),
    (
        _PROCEDURE,
        "R4.3 a prompt, a skill or a template goes to the writers",
        (r"\bprompt\b", r"\btemplate\b", r"\bgoes to the writers\b"),
    ),
    (
        _PROCEDURE,
        "R4.4 no file changes between the gate and the commit",
        (r"\bchange no file between the gate and the commit\b",),
    ),
    (
        _PROCEDURE,
        "R4.5 a Task: line of a commit made after the feature's final commit names a later feature's task",
        (r"\btask: line of a commit made after the feature's final commit\b", r"\blater feature's task\b"),
    ),
    (
        _PROCEDURE,
        "R4.5 where the notes are missing the plan's Files: lines decide, and a file a high task could have changed"
        " counts as changed by it",
        (r"\bnotes are missing\b", r"\bfiles: lines\b", r"\bhigh task could have changed\b"),
    ),
    (
        _PROCEDURE,
        "R4.5 the set-aside stages first and takes the untracked files",
        (r"\bgit add -a && git stash push --include-untracked\b", r"\badjustment set aside\b"),
    ),
    (
        _PROCEDURE,
        "R4.8 code changed after the final verification repeats its steps, or the entry says it was not repeated",
        (r"\bfinal verification\b", r"\brepeat the steps\b", r"\bnot repeated\b"),
    ),
    (
        "the test-writer (adjustment) prompt",
        "R4.3 every other test is left as it is",
        (r"\bleave every other test as it is\b",),
    ),
    (
        "the test-writer (adjustment) prompt",
        "R4.3 a test is added only when the request changes what the code does and none asserts it",
        (r"\badd a test\b", r"\bwhen the request changes what the code does and none asserts it\b"),
    ),
    (
        "the test-writer (adjustment) prompt",
        "R4.7 the acceptance criteria as they read now",
        (r"\bacceptance criteria covered, as they read now\b", r"<[^<>]+>"),
    ),
    (
        "the implementer (adjustment) prompt",
        "R4.3 the smallest edit, and nothing the request does not ask for",
        (r"\bsmallest edit\b", r"\bnothing the request does not ask for\b"),
    ),
    (
        "the adjustment review prompt",
        "R4.4 the uncommitted changes are the adjustment alone, not the whole task",
        (r"\bgit diff head\b", r"\badjustment alone\b", r"\bnot the whole task\b"),
    ),
    (
        "the slice-summary template",
        "R4.10 a change asked on a task in progress is listed too, from its - Change: line",
        (r"\btask in progress\b", r"- change:"),
    ),
    (
        "the feature-summary template",
        "R4.8 an entry is read from its commit: its note and what it changed in requirements.md",
        (r"\bread from its commit \(its note and what it changed in requirements\.md\)",),
    ),
    (
        "the feature-summary template",
        "R4.8 the entry says whether the final verification's steps were repeated",
        (r"\bfinal verification\b", r"\bsay whether its steps were repeated\b"),
    ),
    (
        "the tasks.md template",
        "R4.10 the finished task's example carries its - Change: line",
        (r"- change: <[^<>]+> \(user\)",),
    ),
    (
        "develop-feature Slice checkpoint",
        "R4.10 the summary adds the changes asked on a task in progress, from the - Change: lines",
        (r"\btask in progress\b", r"- change: lines\b"),
    ),
    (
        _PARTITIONS,
        "R4.11 a partition blocked only on a change the user asked needs no answer and goes on",
        (r"\bneeds no answer\b", r"\(#adjustments\)", r"\bgo on with its tasks\b"),
    ),
    (
        _PARTITIONS,
        "R3.2 the resolution of a conflict in a file a high task lists gets every review of step 3",
        (r"\breview the resolution\b", r"\bevery review of step 3 when the file is one a high task lists\b"),
    ),
    (
        "develop-feature Model and effort",
        "R4.3 an adjustment is a first attempt: its writers and reviews use their defaults",
        (r"\badjustments?\b", r"\bfirst attempt\b", r"\bdefaults\b"),
    ),
    (
        "develop-feature Roles",
        "R4.4 the Adjustment row: the writers, then only the reviews the change concerns",
        (r"\badjustment\b", r"\bonly the reviews the change concerns\b"),
    ),
    (
        _PHASE_3,
        "R4.9 in live mode each adjustment is pushed as soon as it is made",
        (r"\bpush every other commit\b", r"\beach adjustment\b"),
    ),
    (
        "opening-pull-requests",
        "R4.8 the summary's Adjustments feed What and why",
        (r'adjustments" also feed what and why\b',),
    ),
    (
        "opening-pull-requests",
        "R4.9 a branch that holds only adjustments to a merged feature is one pull request against the default branch",
        (r"\bholds only adjustments to a feature already merged\b", r"\bone pull request against the default branch\b"),
    ),
)
_PIN_OUTPUT_RUNS = (re.compile(r"\b5 runs\b"), re.compile(r"\b1 run\b"))


def _pin_gaps(rules: _PinRules) -> list[str]:
    """Return `<source> lacks: <rule>` for each rule whose patterns share no sentence of its source."""
    return [
        f"{source} lacks: {rule}"
        for source, rule, patterns in rules
        if not any(
            _in_one_sentence(block, *(re.compile(pattern) for pattern in patterns)) for block in _PIN_SOURCES[source]()
        )
    ]


def _pin_table_gaps() -> list[str]:
    """Return the table rules that no row of `## Reviews after a change` meets with both of its cells."""
    rows = _after_table_rows()
    return [
        f"develop-feature ## Reviews after a change, its table, lacks: {rule}"
        for rule, what, reviews, kept_out in _PIN_TABLE_RULES
        if not any(
            all(re.search(pattern, first) for pattern in what)
            and all(re.search(pattern, second) for pattern in reviews)
            and not any(re.search(pattern, second) for pattern in kept_out)
            for first, second in rows
        )
    ]


class RightSizedFlowPinsTest(unittest.TestCase):
    maxDiff = None  # a failure lists every gap, not the first one

    def test_planning_keeps_the_edges_of_what_it_merges(self) -> None:
        """R1.1, R1.3, R1.4, R1.5, R1.7, R1.8, R1.9, R3.9, R5.4: 004 planning keeps the edges of a merge.

        The lines are merged before the tasks are written, the default is `low` and a plan change renumbers no task.
        An invariant goes on the line whose code makes it hold and gets a `property` line of its own only when it
        takes several lines, or a low one; merged lines share the owner the first list gave them; a chore joins the
        low-risk task it prepares or documents; the approval names the tasks the other choice would merge; and the
        Standards state the medium limit and the one cycle of reviews. The template's consolidated task keeps its
        verify command and the criterion of each test, and measure-impact compares features within one version.
        """
        self.assertEqual(_pin_gaps(_PIN_PLAN_RULES), [])

    def test_a_task_with_several_tests_keeps_the_edges_of_its_one_cycle(self) -> None:
        """R1.5, R2.1, R2.2, R2.3, R2.4, R2.5, R3.1, R3.2, R3.5, R3.9: 004 the one-cycle build keeps its edges.

        Phase 3 says what happens to a CHARACTERIZATION, a report for the whole task, a test green before its code, a
        `BLOCKED` on one test, tests that already pass, the property tests of step 1, a high task's fix round and a
        red check whose fix belongs in a test file; Rethink says how a split is listed and counted and that a KEEP is
        reviewed by every review; and the agents, test-driven-development and the Standards carry their part.
        """
        self.assertEqual(_pin_gaps(_PIN_BUILD_RULES), [])

    def test_reviews_after_a_change_keep_what_surrounds_their_table(self) -> None:
        """R3.1, R3.5, R3.7, R3.8, R4.4, R4.10: 004 the rule on reviews after a change keeps its conditions.

        The section names the five changes it covers, decides from the diff, says what the change is for an
        adjustment, searches for a message's old text, gives a change that matches several rows every review they
        name, reruns the verify command with the command of an added test and sends the reviews not repeated to the
        summary and the flow record. Its table keeps the conditions of its rows, the reworded message included.
        """
        self.assertEqual(_pin_gaps(_PIN_AFTER_RULES) + _pin_table_gaps(), [])

    def test_a_requested_change_keeps_the_edges_of_its_path(self) -> None:
        """R1.9, R3.2, R4.1, R4.2, R4.3, R4.4, R4.5, R4.6, R4.7, R4.8, R4.9, R4.10, R4.11: 004 a request keeps its path.

        Phase 0 says when a finished feature reopens; `## Adjustments` says what the user is told, where a plan
        change on a finished feature goes, that a rename changes no design, that a diff that became a plan change is
        never committed and how a defect is made; the procedure keeps its branch, search, set-aside and recording
        rules; and the prompts, templates and neighbouring sections carry their part.
        """
        self.assertEqual(_pin_gaps(_PIN_REQUEST_RULES), [])

    def test_the_adjustment_review_gets_the_orchestrators_verification_runs(self) -> None:
        """R4.4: 004 the adjustment review prompt's output field says what it holds: 5 runs and 1 run.

        The field carries the orchestrator's verification output: the tests the adjustment changed or added, five
        runs, and the verify command of the task it adjusts, one run.
        """
        review = _PIN_SOURCES["the adjustment review prompt"]()

        stated = any(all(part.search(block) for part in (*_ADJUST_OUTPUT_FIELD, *_PIN_OUTPUT_RUNS)) for block in review)

        self.assertTrue(stated, "dispatch-prompts.md: the adjustment review prompt's output field lacks its runs")


if __name__ == "__main__":
    unittest.main()
