"""Contract tests for the plugin's skill definitions in skills/*/SKILL.md."""

from __future__ import annotations

import importlib
import os
import re
import subprocess
import sys
import tempfile
import unittest
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .plugin_files import PLUGIN_ROOT, SKILLS_DIR, read_frontmatter
from .test_flows import _NEGATION, _blocks, _in_one_sentence, _sentences, _split_blocks

_WRITING_PLANS = SKILLS_DIR / "writing-plans" / "SKILL.md"
_PARTITIONS_HEADER = re.compile(r"\bwave\W+partition\W+tasks\W+depends on\b")
_AT_MOST_THREE = re.compile(r"\b(?:at most|no more than|up to|a maximum of) (?:three|3)\b")
_NO_DEPENDENCY = re.compile(r"\b(?:no|not|never|none|without)\b(?: \S+){0,6} depend|\bindependent\b")
_SHARE_NO_FILE = re.compile(
    r"\bshare no files?\b|\bno (?:shared|common) files?\b|\b(?:do not|don't|never) share\b(?: \S+){0,3} files?\b"
)
_LATER_WAVE = re.compile(r"\b(?:later|subsequent) waves?\b|\bwaves? after\b")
_EARLIER_WAVE = re.compile(r"\b(?:earlier|previous|prior) waves?\b")
_SEPARATE_PARTITIONS = re.compile(r"\b(?:different|separate|two|parallel) partitions\b|\bsame partition\b")
_IN_ORDER = re.compile(r"\b(?:list order|in order|in their order|in the order)\b")
_SLICE_END = re.compile(r"\b(?:end|last|closes?|after)\b")
_FEATURE_WIDE_IDS = re.compile(
    r"\bunique\b(?: \S+){0,6} (?:feature|slices)\b|\b(?:never|not|do not|don't) restart|\bcontinu\w* across\b"
)
_SHARED_FILE = re.compile(r"\bshared? (?:any |a )?files?\b")

# R3.1: each rule writing-plans must state about partitions and waves, outside its Self-review step.
_PARTITION_RULES: dict[str, Callable[[str], bool]] = {
    "a `### Partitions` table": lambda b: "### partitions" in b,
    "the Partitions table closing each slice": lambda b: (
        "partitions" in b and "slice" in b and _SLICE_END.search(b) is not None
    ),
    "the `| Wave | Partition | Tasks | Depends on |` column header": lambda b: _PARTITIONS_HEADER.search(b) is not None,
    "a partition is tasks one session builds in list order": lambda b: (
        "partition" in b and "one session" in b and _IN_ORDER.search(b) is not None
    ),
    "every task belongs to exactly one partition": lambda b: "exactly one partition" in b,
    "partitions of one wave do not depend on each other": lambda b: (
        "wave" in b and "partition" in b and _NO_DEPENDENCY.search(b) is not None
    ),
    "partitions of one wave share no file except tasks.md and evidence": lambda b: (
        "wave" in b and _SHARE_NO_FILE.search(b) is not None and "tasks.md" in b and "evidence" in b
    ),
    "a partition goes in a later wave than every partition it depends on": lambda b: (
        "depend" in b and _LATER_WAVE.search(b) is not None
    ),
    "at most three partitions per wave": lambda b: (
        "wave" in b and "partitions" in b and _AT_MOST_THREE.search(b) is not None
    ),
    "tasks adding a dependency touch the manifest and lockfile, so never in different partitions of one wave": (
        lambda b: "manifest" in b and "lockfile" in b and "wave" in b and _SEPARATE_PARTITIONS.search(b) is not None
    ),
    "partition IDs are unique across the whole feature": lambda b: (
        "partition" in b and _FEATURE_WIDE_IDS.search(b) is not None
    ),
}

# R3.1: what the Self-review step must check about the partitions.
_SELF_REVIEW_CHECKS: dict[str, Callable[[str], bool]] = {
    "every task is in exactly one partition": lambda b: "exactly one partition" in b,
    "`Depends on` names only partitions of earlier waves": lambda b: (
        "depends on" in b and _EARLIER_WAVE.search(b) is not None
    ),
    "no shared files inside a wave": lambda b: (
        "wave" in b and (_SHARE_NO_FILE.search(b) is not None or _SHARED_FILE.search(b) is not None)
    ),
}


def _is_section_heading(line: str) -> bool:
    """Return whether a SKILL.md line opens a `## ` or `### ` section."""
    return line.startswith(("## ", "### "))


def _split_self_review(lines: list[str]) -> tuple[list[str], list[str]]:
    """Return a skill's `### ... Self-review` subsection lines and the remaining lines after the frontmatter.

    The subsection runs from a `### ` heading that contains "Self-review" to the next `## ` or `### ` heading; it is
    empty when the skill has no such heading.
    """
    if lines[:1] == ["---"] and "---" in lines[1:]:
        lines = lines[lines.index("---", 1) + 1 :]
    start = next(
        (index for index, line in enumerate(lines) if line.startswith("### ") and "self-review" in line.lower()),
        None,
    )
    if start is None:
        return [], lines
    headings_after_start = (index for index in range(start + 1, len(lines)) if _is_section_heading(lines[index]))
    end = next(headings_after_start, len(lines))
    return lines[start:end], lines[:start] + lines[end:]


class SkillModelsTest(unittest.TestCase):
    def test_only_the_planning_skill_declares_effort(self) -> None:
        """R1.5, R1.6: only writing-plans declares an effort (xhigh) and no skill declares a model."""
        expected = {"writing-plans": (None, "xhigh")}

        actual = {}
        for skill_file in sorted(SKILLS_DIR.glob("*/SKILL.md")):
            fields = read_frontmatter(skill_file)
            if "model" in fields or "effort" in fields:
                actual[skill_file.parent.name] = (fields.get("model"), fields.get("effort"))

        self.assertEqual(actual, expected)


class WritingPlansPartitionsTest(unittest.TestCase):
    def test_writing_plans_partitions_each_slice(self) -> None:
        """R3.1: writing-plans splits each slice into partitions ordered in waves, with rules its self-review checks.

        Each slice ends with a `### Partitions` table; one session builds a partition in list order; every task is in
        exactly one partition; a wave holds at most three partitions that neither depend on each other nor share a
        file (tasks.md and evidence excepted); dependency-adding tasks stay out of parallel partitions; partition IDs
        are unique across the feature; and the Self-review step checks the partitions.
        """
        lines = _WRITING_PLANS.read_text(encoding="utf-8").splitlines()

        review_lines, other_lines = _split_self_review(lines)
        body_blocks = _split_blocks(other_lines)
        review_blocks = _split_blocks(review_lines)
        gaps = [f"rule missing: {label}" for label, says in _PARTITION_RULES.items() if not any(map(says, body_blocks))]
        if not review_lines:
            gaps.append("no `### ... Self-review` step")
        gaps += [
            f"Self-review does not check: {label}"
            for label, says in _SELF_REVIEW_CHECKS.items()
            if not any(map(says, review_blocks))
        ]

        self.assertEqual(gaps, [], "writing-plans/SKILL.md:\n" + "\n".join(gaps))


# R5.1, R5.4: design decisions in the plan. The patterns run on blocks from _split_blocks (lowercased, without
# backticks, single-spaced), each rule within one sentence so an unrelated sentence cannot satisfy it.
_WRITING_PLANS_TEMPLATE = SKILLS_DIR / "writing-plans" / "templates" / "tasks.md"
_DECISION_FIELD = re.compile(r"\bdecision:")
_TWO_OR_MORE = re.compile(r"\b(?:two or more|more than one|several|multiple)\b")
_APPROACHES = re.compile(r"\b(?:approach|option|alternative)e?s\b")
_OPTION = re.compile(r"\b(?:approach|option|alternative)(?:e?s)?\b")
_ADVANTAGES = re.compile(r"\b(?:advantages?|pros)\b")
_DISADVANTAGES = re.compile(r"\b(?:disadvantages?|cons|drawbacks?)\b")
_RECOMMENDATION = re.compile(r"\brecommend\w*")
_DECISIONS = re.compile(r"\bdecisions?\b")
_SHOWS = re.compile(r"\b(?:show|present|list|ask)\w*")
_USER = re.compile(r"\buser\b")
_CHOOSES = re.compile(r"\b(?:choos|chose|pick|select)\w*")
_ACCEPTS = re.compile(r"\baccept\w*")
_DECIDED_FORM = re.compile(r"\bdecision: <[^>]+> \(user \| recommended\)")
_REWRITES = re.compile(r"\b(?:rewrit|replac|record|becom|updat|turn)\w*")
_WHO_CHOSE = re.compile(r"\bwho\b(?: \S+){0,2} (?:chose|picked|decided|made)\b")
_SUMMARIES = re.compile(r"\bsummar\w*")
_CITE = re.compile(r"\b(?:cite|quote|reference)s?\b")
_NO_DECISION_FIELD = re.compile(r"\b(?:no|omit\w*|without|skip\w*)\b(?: \S+){0,3} decision:")
_NO_OPEN_CHOICE = re.compile(
    r"\b(?:only one|a single|one) (?:reasonable )?(?:approach|option|way)\b"
    r"|\b(?:no|without an?) (?:open |real )?(?:choice|alternative)s?\b|\bnothing to (?:choose|decide)\b"
)
_NAMED_OPTIONS = re.compile(r"(?<!<)\b(?:approach|option|alternative)(?:e?s)?\b(?!>)")
_KEEPS = re.compile(r"\b(?:keep\w*|kept|remain\w*|stay\w*|retain\w*|preserv\w*)\b")
_BELOW = re.compile(r"\b(?:below|under|underneath|beneath)\b")
_TEMPLATE_TASK_LINE = re.compile(r"- \[[ xX]\] \*\*(?P<id>T\d+)\*\*")
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_FINISHED_DECISION_LINE = re.compile(r"(?P<indent>\s*)- Decision: .+ \((?:user|recommended)\)\s*$")

# R5.1, R5.4: what writing-plans/SKILL.md must say about decisions, outside its Approval step.
_DECISION_RULES: dict[str, Callable[[str], bool]] = {
    "a task with two or more reasonable approaches records them in its `- Decision:` field": lambda b: _in_one_sentence(
        b, _TWO_OR_MORE, _APPROACHES, _DECISION_FIELD
    ),
    "the `- Decision:` field gives each option's advantages and disadvantages": lambda b: _in_one_sentence(
        b, _OPTION, _ADVANTAGES, _DISADVANTAGES
    ),
    "the `- Decision:` field gives a recommendation": lambda b: _in_one_sentence(
        _DECIDED_FORM.sub("", b), _DECISION_FIELD, _RECOMMENDATION
    ),
    "after choosing, the field is rewritten as `- Decision: <option> (user | recommended)`": lambda b: _in_one_sentence(
        b, _DECIDED_FORM, _REWRITES
    ),
    "the decided `- Decision:` line keeps the options below it": lambda b: _in_one_sentence(
        b, _DECIDED_FORM, _KEEPS, _NAMED_OPTIONS, _BELOW
    ),
    "the decided field records who chose": lambda b: _in_one_sentence(b, _DECISIONS, _WHO_CHOSE),
    "summaries cite the recorded decision": lambda b: _in_one_sentence(b, _DECISIONS, _SUMMARIES, _CITE),
    "a task without an open choice has no `- Decision:` field": lambda b: _in_one_sentence(
        b, _NO_DECISION_FIELD, _NO_OPEN_CHOICE
    ),
}

# R5.1: what the Approval step must say about the decisions. The decided form's "(user | recommended)" is dropped
# before the recommendation rules, so the format alone cannot stand in for offering or accepting a recommendation.
_APPROVAL_RULES: dict[str, Callable[[str], bool]] = {
    "shows the decisions to the user": lambda b: _in_one_sentence(b, _SHOWS, _DECISIONS),
    "the user picks an option or accepts the recommendation": lambda b: _in_one_sentence(
        _DECIDED_FORM.sub("", b), _USER, _CHOOSES, _ACCEPTS, _RECOMMENDATION
    ),
}


def _split_approval(lines: list[str]) -> tuple[list[str], list[str]]:
    """Return a skill's `### ... Approval` subsection lines and the remaining lines, as `_split_self_review` does."""
    start = next(
        (index for index, line in enumerate(lines) if line.startswith("### ") and "approval" in line.lower()),
        None,
    )
    if start is None:
        return [], lines
    headings_after_start = (index for index in range(start + 1, len(lines)) if _is_section_heading(lines[index]))
    end = next(headings_after_start, len(lines))
    return lines[start:end], lines[:start] + lines[end:]


def _decision_skill_gaps(skill_text: str) -> list[str]:
    """Return the decision rules (R5.1, R5.4) a writing-plans SKILL.md text lacks, one message per rule."""
    approval_lines, other_lines = _split_approval(skill_text.splitlines())
    body_blocks = _split_blocks(other_lines)
    approval_blocks = _split_blocks(approval_lines)
    gaps = [f"rule missing: {label}" for label, says in _DECISION_RULES.items() if not any(map(says, body_blocks))]
    if not approval_lines:
        gaps.append("no `### ... Approval` step")
    gaps += [
        f"Approval step does not say: {label}"
        for label, says in _APPROVAL_RULES.items()
        if not any(map(says, approval_blocks))
    ]
    return gaps


def _template_decision_items(template_text: str) -> dict[str, str]:
    """Return each template task's `- Decision:` sub-item by task ID, lowercased and single-spaced.

    The sub-item is its `- Decision:` line plus every following line indented deeper (wrapped text or nested
    options). HTML comments are dropped first, as `read_tasks` drops them, so only a real task's field counts.
    """
    items: dict[str, list[str]] = {}
    task_id = None
    decision_indent = None
    for line in _HTML_COMMENT.sub("", template_text).splitlines():
        indent = len(line) - len(line.lstrip())
        if decision_indent is not None and line.strip() and indent > decision_indent and task_id is not None:
            items[task_id].append(line)
            continue
        decision_indent = None
        match = _TEMPLATE_TASK_LINE.match(line)
        if match or line.startswith("#"):
            task_id = match.group("id") if match else None
        elif task_id is not None and indent and line.lstrip().startswith("- Decision:"):
            items[task_id] = [line]
            decision_indent = indent
    return {task: " ".join(" ".join(lines).replace("`", "").lower().split()) for task, lines in items.items()}


def _read_template_tasks(path: Path) -> dict[str, Any]:
    """Return a tasks.md's tasks by ID, parsed with the hooks' own `tasks_document.read_tasks`."""
    scripts = str(PLUGIN_ROOT / "hooks" / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    document = importlib.import_module("tasks_document").read_tasks(path)
    return {task.id: task for task in document.tasks}


def _decision_template_gaps(template_text: str, parsed_tasks: dict[str, Any]) -> list[str]:
    """Return what the tasks.md template lacks for R5.1: a task with a full `- Decision:` example that still parses.

    Args:
        template_text: The template's text.
        parsed_tasks: The template's tasks as `read_tasks` returns them, by task ID.
    """
    items = _template_decision_items(template_text)
    if not items:
        return ["no task carries a `- Decision:` example"]
    complete = [
        task
        for task, item in items.items()
        if all(pattern.search(item) for pattern in (_OPTION, _ADVANTAGES, _DISADVANTAGES, _RECOMMENDATION))
    ]
    if not complete:
        return ["no `- Decision:` example names options with advantages, disadvantages and a recommendation"]
    return [
        f"{task}, which carries the `- Decision:` example, does not parse with its risk, slice and partition"
        for task in complete
        if task not in parsed_tasks
        or None in (parsed_tasks[task].risk, parsed_tasks[task].slice, parsed_tasks[task].partition)
    ]


def _finished_decision_gaps(template_text: str) -> list[str]:
    """Return what the template's finished-task example lacks for R5.4: a decided line with its options kept.

    Looks inside the template's HTML comments for a `- Decision: <option> (user)` or `(recommended)` line followed by
    at least two deeper-indented lines that name an option, so summaries can still cite the options after the choice.
    """
    for comment in _HTML_COMMENT.findall(template_text):
        lines = comment.splitlines()
        for index, line in enumerate(lines):
            match = _FINISHED_DECISION_LINE.match(line)
            if match is None:
                continue
            nested_options = 0
            for nested in lines[index + 1 :]:
                if not nested.strip() or len(nested) - len(nested.lstrip()) <= len(match.group("indent")):
                    break
                if nested.lstrip().startswith("- ") and _NAMED_OPTIONS.search(nested.lower()):
                    nested_options += 1
            if nested_options >= 2:
                return []
    return ["the finished-task example does not keep two or more options under its decided `- Decision:` line"]


class WritingPlansDecisionsTest(unittest.TestCase):
    def test_writing_plans_lists_design_decisions(self) -> None:
        """R5.1, R5.4: the plan records design decisions with options and a recommendation, chosen at approval.

        writing-plans/SKILL.md says that a task with two or more reasonable approaches records them in a `- Decision:`
        field with each option's advantages and disadvantages and a recommendation; a task without an open choice has
        none; the Approval step shows the decisions to the user, who picks one or accepts the recommendation; and the
        field's first line is then rewritten as `- Decision: <option> (user | recommended)`, recording who chose, with
        the options kept below it so summaries can cite them. The tasks.md template shows such a field on a task that
        `read_tasks` still parses, and its finished-task example keeps the options under the decided line.
        """
        with _WRITING_PLANS.open(encoding="utf-8", newline=None) as handle:
            skill_text = handle.read()
        with _WRITING_PLANS_TEMPLATE.open(encoding="utf-8", newline=None) as handle:
            template_text = handle.read()
        parsed_tasks = _read_template_tasks(_WRITING_PLANS_TEMPLATE)

        gaps = [f"writing-plans/SKILL.md: {gap}" for gap in _decision_skill_gaps(skill_text)]
        gaps += [f"templates/tasks.md: {gap}" for gap in _decision_template_gaps(template_text, parsed_tasks)]
        gaps += [f"templates/tasks.md: {gap}" for gap in _finished_decision_gaps(template_text)]

        self.assertEqual(gaps, [], "\n".join(gaps))


# R9.1: the anchored, exact-ID form every skill must use to find a task's commit.
_EXACT_TASK_GREP = "-E --grep '^Task: T<n>( |$)'"
_INLINE_CODE = re.compile(r"`([^`\n]+)`")
_SKILLS_THAT_FIND_TASK_COMMITS = ("develop-feature", "opening-pull-requests")


def _git(repo: Path, *args: str) -> str:
    """Run git in repo with a fixed identity and no user or system config, returning stdout."""
    base_env = {key: os.environ[key] for key in ("PATH", "SYSTEMROOT") if key in os.environ}
    env = {**base_env, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": str(repo / "no-global-config")}
    command = ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", "-c", "commit.gpgsign=false", *args]
    return subprocess.run(
        command, cwd=repo, env=env, capture_output=True, text=True, encoding="utf-8", check=True
    ).stdout


class TaskCommitLookupTest(unittest.TestCase):
    def test_task_commits_are_found_by_exact_id(self) -> None:
        """R9.1: skills find a task's commit by its exact ID, so T1 never matches T10 to T19.

        No skill searches with a substring `--grep "Task: T<n>"`; develop-feature and opening-pull-requests use
        `git log -E --grep '^Task: T<n>( |$)'`, and that pattern, run by git, finds only the T1 commit among T1,
        T10 and T19.
        """
        docs = sorted([*SKILLS_DIR.glob("*/SKILL.md"), *SKILLS_DIR.glob("*/reference/*.md")])
        gaps = []
        for doc in docs:
            with doc.open(encoding="utf-8", newline=None) as handle:
                text = handle.read()
            name = doc.relative_to(SKILLS_DIR).as_posix()
            for code in _INLINE_CODE.findall(text):
                if "--grep" in code and "Task: T" in code and _EXACT_TASK_GREP not in code:
                    gaps.append(f"{name}: substring task search `{code}`")
        for skill in _SKILLS_THAT_FIND_TASK_COMMITS:
            text = (SKILLS_DIR / skill / "SKILL.md").read_text(encoding="utf-8")
            if _EXACT_TASK_GREP not in text:
                gaps.append(f"{skill}/SKILL.md: lacks `{_EXACT_TASK_GREP}`")

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _git(repo, "init", "-q")
            for task in ("T1", "T10", "T19"):
                _git(repo, "commit", "-q", "--allow-empty", "-m", f"feat: {task}", "-m", f"Task: {task} · Covers: R1")
            found = _git(repo, "log", "--format=%s", "-E", "--grep", "^Task: T1( |$)").split()
        if found != ["feat:", "T1"]:
            gaps.append(f"git log -E --grep '^Task: T1( |$)' found {found}, expected only the T1 commit")

        self.assertEqual(gaps, [], "\n".join(gaps))


# R6.2: opening-pull-requests builds a slice's pull request description from that slice's summary file.
_DELIVERY_OPENING_PULL_REQUESTS = SKILLS_DIR / "opening-pull-requests" / "SKILL.md"
_DELIVERY_SLICE_SUMMARY_PATH = re.compile(r"\bsummaries/s<k>\.md\b")
_DELIVERY_DESCRIPTION = re.compile(r"\bdescriptions?\b")
_DELIVERY_BUILT_FROM = re.compile(
    r"\b(?:use[sd]?|using|build\w*|built|fill\w*|draw\w*|based? on|deriv\w*|compos\w*|tak\w*|from)\b"
)
_DELIVERY_WHEN_IT_EXISTS = re.compile(
    r"\b(?:when|if|whenever|once)\b(?: \S+){0,8} (?:exists?|is present|is there|was written|has been written)\b"
)


def _delivery_slice_summary_gaps(blocks: list[str]) -> list[str]:
    """Return what opening-pull-requests' blocks lack to build each slice's description from its summary (R6.2)."""
    summary_blocks = [block for block in blocks if _DELIVERY_SLICE_SUMMARY_PATH.search(block)]
    if not summary_blocks:
        return ["never names the slice's summary file `summaries/S<k>.md`"]
    gaps = []
    if not any(
        any(
            _DELIVERY_SLICE_SUMMARY_PATH.search(sentence)
            and _DELIVERY_DESCRIPTION.search(sentence)
            and _DELIVERY_BUILT_FROM.search(sentence)
            and not _NEGATION.search(sentence)
            for sentence in _sentences(block)
        )
        for block in summary_blocks
    ):
        gaps.append("no sentence builds the slice's pull request description from `summaries/S<k>.md`")
    if not any(_DELIVERY_WHEN_IT_EXISTS.search(block) for block in summary_blocks):
        gaps.append("does not say the summary is used when `summaries/S<k>.md` exists")
    return gaps


class SlicePullRequestSummaryTest(unittest.TestCase):
    maxDiff = None

    def test_slice_pull_requests_use_the_slice_summary(self) -> None:
        """R6.2: when a slice's summary exists, its pull request description is built from it.

        opening-pull-requests/SKILL.md names the slice's summary file `summaries/S<k>.md` and, in one paragraph or
        list item, says that when that file exists the description of that slice's pull request is built from it
        (in one sentence, not negated).
        """
        gaps = [
            f"opening-pull-requests/SKILL.md: {gap}"
            for gap in _delivery_slice_summary_gaps(_blocks(_DELIVERY_OPENING_PULL_REQUESTS))
        ]

        self.assertEqual(gaps, [], "\n".join(gaps))


# R2.3: with stacked pull requests, `risk:high` goes only on the pull requests of slices that hold a high-risk task.
_DELIVERY_RISK_HIGH_LABEL = re.compile(r"\brisk:high\b")
_DELIVERY_SLICE = re.compile(r"\bslices?\b")
_DELIVERY_HIGH_RISK_TASK = re.compile(r"\bhigh[- ]risk tasks?\b|\btasks?\b(?: \S+){0,3} (?:high risk|risk: high)\b")
_DELIVERY_ONLY = re.compile(r"\b(?:only|solely|exclusively)\b")
_DELIVERY_NOT_ONLY = re.compile(r"\bnot (?:only|solely|just)\b")
# _NEGATION plus the forms it lacks ("doesn't", "isn't", "aren't", "none", "lacks"), so a negated condition counts as
# negated however it is phrased.
_DELIVERY_NEGATION = re.compile(rf"{_NEGATION.pattern}|\b\w+n['\u2019]t\b|\b(?:none|lacks?|lacking|absent|free of)\b")
# A colon breaks a clause only before a space, so the one inside "risk:high" does not.
_DELIVERY_CLAUSE_BREAK = re.compile(r"[,;()—]|:(?=\s|$)")
# A condition longer than this, from its first word to its high-risk task, is not read as one condition.
_DELIVERY_CONDITION_MAX_WORDS = 15
# Lazy, so "every pull request whose slice …" matches "every pull request" and leaves "whose …" as its clause.
_DELIVERY_EVERY_PULL_REQUEST = re.compile(r"\b(?:every|each|all)\b(?: \S+){0,3}? (?:pull requests?|prs?|slices?)\b")
_DELIVERY_RESTRICTIVE_CLAUSE = re.compile(r" (?:whose|that|which|with|where|holding|when|if)\b")
# A sentence about the single delivery, where one `risk:high` does cover every slice, not about stacked ones. "one pull
# request" is not enough: the stacked delivery also says "each slice is one pull request".
_DELIVERY_SINGLE_PULL_REQUEST = re.compile(r"\bsingle pull request\b")


def _delivery_clause_before(sentence: str, index: int) -> str:
    """Return the text of a sentence from the start of the clause holding `index` up to `index`."""
    breaks = [match.end() for match in _DELIVERY_CLAUSE_BREAK.finditer(sentence, 0, index)]
    return sentence[breaks[-1] if breaks else 0 : index]


def _delivery_high_risk_condition(sentence: str, start: int) -> str | None:
    """Return a sentence's text from `start` to the end of the first high-risk task after it, or None when none is.

    The text is returned only when it states the high-risk task positively: at most `_DELIVERY_CONDITION_MAX_WORDS`
    words and no negation anywhere in it ("does not hold", "doesn't hold", "never holds", "holds no", "is without").
    """
    task = _DELIVERY_HIGH_RISK_TASK.search(sentence, start)
    if task is None:
        return None
    condition = sentence[start : task.end()]
    if len(condition.split()) > _DELIVERY_CONDITION_MAX_WORDS or _DELIVERY_NEGATION.search(condition):
        return None
    return condition


def _delivery_only_limits_to_high_risk_slice(sentence: str, only: re.Match[str]) -> bool:
    """Return whether an "only" in a sentence limits it to a slice that holds a high-risk task.

    The text from "only" to the high-risk task must be a positive condition (`_delivery_high_risk_condition`) that names
    the slice, and nothing in the clause before "only" may negate it.
    """
    condition = _delivery_high_risk_condition(sentence, only.end())
    return bool(
        condition is not None
        and _DELIVERY_SLICE.search(condition)
        and not _DELIVERY_NEGATION.search(_delivery_clause_before(sentence, only.start()))
    )


def _delivery_labels_only_high_risk_slices(sentence: str) -> bool:
    """Return whether a sentence limits `risk:high` to the pull requests of slices that hold a high-risk task.

    The rule must be stated as exclusive and positive ("`risk:high` only when that slice holds a high-risk task"). A
    sentence whose condition is negated in any form ("only when that slice does not hold / doesn't hold / never holds /
    holds no / is without a high-risk task", "only a slice without a high-risk task") inverts the rule and is rejected,
    as is one without "only" ("a slice without a high-risk task gets `risk:high`") or saying "not only".
    """
    if not _DELIVERY_RISK_HIGH_LABEL.search(sentence) or _DELIVERY_NOT_ONLY.search(sentence):
        return False
    return any(_delivery_only_limits_to_high_risk_slice(sentence, only) for only in _DELIVERY_ONLY.finditer(sentence))


def _delivery_is_blanket(sentence: str, every: re.Match[str]) -> bool:
    """Return whether an "every pull request" in a sentence applies to all of them, whatever their tasks' risk.

    It does not when its own clause negates it ("never add `risk:high` to every pull request") or when a relative
    clause right after it restricts it with a positive high-risk-task condition ("every pull request whose slice holds
    a high-risk task"). Merely mentioning or negating a high-risk task elsewhere ("whether or not its slice holds a
    high-risk task") restricts nothing.
    """
    if _DELIVERY_NEGATION.search(_delivery_clause_before(sentence, every.start())):
        return False
    return not (
        _DELIVERY_RESTRICTIVE_CLAUSE.match(sentence, every.end())
        and _delivery_high_risk_condition(sentence, every.end()) is not None
    )


def _delivery_labels_every_pull_request(sentence: str) -> bool:
    """Return whether a sentence puts `risk:high` on every stacked pull request or slice, whatever its tasks' risk.

    A sentence about a single pull request is ignored: there one label does cover every slice, and R2.3 is only about
    the stacked delivery.
    """
    if not _DELIVERY_RISK_HIGH_LABEL.search(sentence) or _DELIVERY_SINGLE_PULL_REQUEST.search(sentence):
        return False
    return any(_delivery_is_blanket(sentence, every) for every in _DELIVERY_EVERY_PULL_REQUEST.finditer(sentence))


def _delivery_stacked_label_gaps(blocks: list[str]) -> list[str]:
    """Return what opening-pull-requests' blocks lack to label only the stacked slices with a high-risk task (R2.3)."""
    sentences = [sentence for block in blocks for sentence in _sentences(block)]
    gaps = []
    if not any(_delivery_labels_only_high_risk_slices(sentence) for sentence in sentences):
        gaps.append(
            "no sentence limits `risk:high` to the pull requests of slices that hold a high-risk task (only those)"
        )
    gaps.extend(
        f"puts `risk:high` on every pull request: {sentence.strip()!r}"
        for sentence in sentences
        if _delivery_labels_every_pull_request(sentence)
    )
    return gaps


class StackedDeliveryRiskLabelTest(unittest.TestCase):
    maxDiff = None

    def test_stacked_delivery_labels_only_high_risk_slices(self) -> None:
        """R2.3: with stacked pull requests, `risk:high` goes only on the pull requests of high-risk slices.

        opening-pull-requests/SKILL.md says, in one sentence with the `risk:high` label, that the label goes only on a
        slice that holds a high-risk task: from "only" to the high-risk task the condition names the slice and has no
        negation in any form, so a slice without one never gets it. And no sentence outside the single delivery puts
        `risk:high` on every pull request or slice unless its clause negates that or a positive high-risk-task
        condition right after it restricts it.
        """
        gaps = [
            f"opening-pull-requests/SKILL.md: {gap}"
            for gap in _delivery_stacked_label_gaps(_blocks(_DELIVERY_OPENING_PULL_REQUESTS))
        ]

        self.assertEqual(gaps, [], "\n".join(gaps))


if __name__ == "__main__":
    unittest.main()
