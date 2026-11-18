"""Contract tests for the plugin's skill definitions in skills/*/SKILL.md."""

from __future__ import annotations

import importlib
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .plugin_files import AGENTS_DIR, PLUGIN_ROOT, SKILLS_DIR, read_frontmatter, read_section
from .test_flows import _NEGATION, _blocks, _in_one_sentence, _section_blocks, _sentences, _split_blocks

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


# R9.3: the unit of work each skill ships on its own branch and pull request, with the words that name it.
_ONE_BRANCH_PER_UNIT_SKILLS = {
    "migrate-code": ("batch", r"batch(?:es)?"),
    "tidy-codebase": ("task", r"(?:task|cleanup|finding)s?"),
}
_OWN_TARGET = {
    "branch": re.compile(r"\b(?:its own|own|a separate|a new|a fresh|a dedicated) branch\b|\bbranch of its own\b"),
    "pull request": re.compile(r"\b(?:its own|own|a separate|its) pull request\b|\bpull request of its own\b"),
}
_ONE_ITEM_PER = r"\bone (\w+) per {target}\b"


def _names_one_per_unit(block: str, unit: str, target: str) -> bool:
    """Return whether a block from `_split_blocks` gives each unit of work its own `target` (branch or pull request).

    Accepts "one <target> per <unit>", "a <target> for each <unit>", and a sentence about each <unit> that names "its
    own <target>", "a <target> of its own" or, for a pull request, "its pull request".
    """
    per_unit = re.compile(rf"\b{target}\b(?: \S+){{0,4}} (?:per|for each|for every) {unit}\b")
    if per_unit.search(block):
        return True
    each_unit = re.search(rf"\b(?:each|every|per) (?:\S+ ){{0,2}}{unit}\b", block)
    return each_unit is not None and _OWN_TARGET[target].search(block) is not None


def _shares_branch_or_pull_request(block: str, unit: str) -> list[str]:
    """Return the "one <thing> per branch|pull request" phrases in a block whose <thing> is not the skill's unit."""
    found = []
    for target in ("branch", "pull request"):
        for match in re.finditer(_ONE_ITEM_PER.format(target=target), block):
            if not re.fullmatch(unit, match.group(1)):
                found.append(match.group(0))
    return found


class OneBranchPerPullRequestTest(unittest.TestCase):
    maxDiff = None

    def test_migrations_and_cleanups_use_one_branch_per_pull_request(self) -> None:
        """R9.3: migrate-code puts each batch, and tidy-codebase each task, on its own branch with its own pull request.

        A skill that puts several batches or tasks on one branch or one pull request (for example "one migration per
        branch") fails, whatever the wording.
        """
        gaps = []
        for skill, (unit_name, unit) in _ONE_BRANCH_PER_UNIT_SKILLS.items():
            lines = (SKILLS_DIR / skill / "SKILL.md").read_text(encoding="utf-8").splitlines()
            if lines[:1] == ["---"] and "---" in lines[1:]:
                lines = lines[lines.index("---", 1) + 1 :]
            blocks = _split_blocks(lines)

            for target in ("branch", "pull request"):
                if not any(_names_one_per_unit(block, unit, target) for block in blocks):
                    gaps.append(f"{skill}: does not give each {unit_name} its own {target}")
            gaps += [
                f"{skill}: shares a branch or pull request across units: {phrase!r}"
                for block in blocks
                for phrase in _shares_branch_or_pull_request(block, unit)
            ]

        self.assertEqual(gaps, [], "\n".join(gaps))


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


# R2.4: with a single pull request and any high-risk task, the user is warned before it opens that `risk:high` covers
# the whole feature, and mutation testing runs locally on all the changed code first when the tool runs here.
_DELIVERY_DEVELOP_FEATURE = SKILLS_DIR / "develop-feature" / "SKILL.md"
_DELIVERY_WARNS = re.compile(r"\b(?:warn\w*|tell\w*|alert\w*|inform\w*|notif\w*)\b")
# No qualifier between "every" and the slices or tasks: "each high-risk task" is R2.3's stacked meaning, not the whole
# feature.
_DELIVERY_WHOLE_FEATURE = re.compile(
    r"\b(?:whole|entire) (?:feature|pull request)\b"
    r"|\b(?:every|each|all)(?: (?:the|its|of its|of the))? (?:slices?|tasks?)\b"
)
_DELIVERY_BEFORE_OPENING = re.compile(r"\bbefore\b(?: \S+){0,4}? (?:open\w*|push\w*|creat\w*)\b")
_DELIVERY_MUTATION = re.compile(r"\b(?:mutation|mutmut)\b")
_DELIVERY_LOCALLY = re.compile(r"\blocal(?:ly)?\b|\bon this machine\b")
_DELIVERY_RUNS = re.compile(r"\b(?:run|runs|running)\b")
# No qualifier before the changed code either: "all the high-risk changed code" is part of it.
_DELIVERY_ALL_CHANGED_CODE = re.compile(r"\b(?:all|every|whole|entire)(?: (?:of )?(?:the|its))? (?:chang\w*|diff)\b")
# A run scoped to part of the changed code: the high-risk tasks' own `Mutation:` commands (each covers only its task's
# files) or the high-risk code alone, while CI's `risk:high` job gates every changed function of the pull request.
_DELIVERY_NARROWED_RUN = re.compile(
    r"\bmutation:? commands?\b(?: \S+){0,3}? tasks?\b"
    r"|\btasks?['\u2019]?s?(?: own)? mutation:? commands?\b"
    r"|\bhigh[- ]risk (?:chang\w*|code|files?|functions?|diff)\b"
)
# What ties a run to part of the changed code when it comes after the run verb, wherever it sits: a high-risk mention
# ("of the high-risk tasks", "in the high-risk tasks' files", "tasks at risk: high") or any task or slice ("of those
# tasks", "in each task's files"), since the whole diff belongs to no task. Not the `risk:high` label, which has no
# space after its colon.
_DELIVERY_RUN_TIE = re.compile(
    r"\bhigh(?:er|est)?[- ]risk\b|\brisk:? high\b|\brisk(?:y|ier|iest)\b|\btasks?\b|\bslices?\b"
)
# Words that make the run optional instead of required ("optionally run", "you may run", "consider running", "if you
# like"), read anywhere in the sentence.
_DELIVERY_OPTIONAL = re.compile(
    r"\b(?:optional\w*|may|might|consider\w*|feel free|at your discretion|if desired|up to (?:you|the user)"
    r"|if (?:you|they|the user) (?:likes?|wants?|wish(?:es)?|prefers?|chooses?))\b"
)
# "can" and "could" make the run permissive too, but are read only from the start of the run's own clause, so a
# condition before it ("when the tool can run here, run mutation testing …") stays a condition.
_DELIVERY_PERMITS = re.compile(r"\b(?:can|could)\b")
# Where the clause that may negate a tie starts. Unlike _DELIVERY_CLAUSE_BREAK, no colon, so "rather than the
# `Mutation:` commands of the high-risk tasks" keeps its "rather than".
_DELIVERY_TIE_CLAUSE_BREAK = re.compile(r"[,;()—]")
# Ways to drop a step that _DELIVERY_NEGATION does not read as negations ("skip running mutation testing").
_DELIVERY_SKIPS = re.compile(r"\b(?:skip\w*|omit\w*|avoid\w*)\b")
_DELIVERY_TOOL = re.compile(r"\b(?:tool|mutmut|mutation)\b")
_DELIVERY_CANNOT_RUN = re.compile(
    r"\b(?:cannot|can't|can not|does not|doesn't|won't|fails? to)\b(?: \S+){0,2}? run\b|\b(?:un|not )available\b"
)
_DELIVERY_FALLBACK = re.compile(r"\bci\b|\bevidence\b|\brecord\w*\b|\b(?:tell|warn|inform)\w*\b(?: \S+){0,2} user\b")


def _delivery_single_high_risk_blocks(blocks: list[str]) -> list[str]:
    """Return the blocks about the single pull request that also name a high-risk task."""
    return [
        block
        for block in blocks
        if _DELIVERY_SINGLE_PULL_REQUEST.search(block) and _DELIVERY_HIGH_RISK_TASK.search(block)
    ]


def _delivery_warns_whole_feature(sentence: str) -> bool:
    """Return whether a sentence warns, unnegated, that one `risk:high` covers the whole single pull request.

    The sentence names the single pull request (so R2.3's check reads it as single delivery), a high-risk task, a
    warning, the `risk:high` label and the whole feature (or every slice or task, with no qualifier such as
    "high-risk" in between), with no negation in any form and no "skip", "omit" or "avoid".
    """
    return bool(
        _DELIVERY_SINGLE_PULL_REQUEST.search(sentence)
        and _DELIVERY_HIGH_RISK_TASK.search(sentence)
        and _DELIVERY_WARNS.search(sentence)
        and _DELIVERY_RISK_HIGH_LABEL.search(sentence)
        and _DELIVERY_WHOLE_FEATURE.search(sentence)
        and not _DELIVERY_NEGATION.search(sentence)
        and not _DELIVERY_SKIPS.search(sentence)
    )


def _delivery_clause_after(sentence: str, index: int) -> str:
    """Return the text of a sentence from `index` up to the end of the clause holding it."""
    end = _DELIVERY_CLAUSE_BREAK.search(sentence, index)
    return sentence[index : end.start() if end else len(sentence)]


def _delivery_mutation_run(sentence: str) -> re.Match[str] | None:
    """Return the first "run", "runs" or "running" whose own clause, from it on, names mutation testing, or None."""
    return next(
        (
            run
            for run in _DELIVERY_RUNS.finditer(sentence)
            if _DELIVERY_MUTATION.search(_delivery_clause_after(sentence, run.start()))
        ),
        None,
    )


def _delivery_ties_run_to_part(sentence: str, run: re.Match[str]) -> bool:
    """Return whether anything after a run verb ties the run to part of the changed code, unnegated.

    A `_DELIVERY_RUN_TIE` after the verb, anywhere up to the end of the sentence, ties it unless its own clause (from
    the last `_DELIVERY_TIE_CLAUSE_BREAK` before it) negates it ("not only the high-risk tasks' code", "rather than the
    `Mutation:` commands of the high-risk tasks"). A high-risk task named before the verb, as the condition, does not.
    """
    for tie in _DELIVERY_RUN_TIE.finditer(sentence, run.end()):
        breaks = [match.end() for match in _DELIVERY_TIE_CLAUSE_BREAK.finditer(sentence, 0, tie.start())]
        if not _DELIVERY_NEGATION.search(sentence[breaks[-1] if breaks else 0 : tie.start()]):
            return True
    return False


def _delivery_makes_run_optional(sentence: str, run: re.Match[str]) -> bool:
    """Return whether a sentence makes its run optional or permissive instead of required.

    `_DELIVERY_OPTIONAL` counts anywhere in the sentence; "can" and "could" only from the start of the run's clause on.
    """
    clause_start = run.start() - len(_delivery_clause_before(sentence, run.start()))
    return bool(_DELIVERY_OPTIONAL.search(sentence) or _DELIVERY_PERMITS.search(sentence, clause_start))


def _delivery_runs_local_mutation_first(sentence: str) -> bool:
    """Return whether a sentence requires running mutation testing locally on all the changed code before opening.

    The run is the first run verb whose clause names mutation testing (`_delivery_mutation_run`). From that verb on the
    sentence says "locally", all the changed code (unqualified: "all the high-risk changed code" is rejected) and
    before opening, and nothing after the verb ties the run to the high-risk tasks or to any task or slice
    (`_delivery_ties_run_to_part`). The sentence must not narrow the run to the tasks' `Mutation:` commands
    (`_DELIVERY_NARROWED_RUN`), make it optional or permissive (`_delivery_makes_run_optional`), negate it in any form,
    or say "skip", "omit" or "avoid".
    """
    run = _delivery_mutation_run(sentence)
    if run is None:
        return False
    return bool(
        _DELIVERY_LOCALLY.search(sentence, run.end())
        and _DELIVERY_ALL_CHANGED_CODE.search(sentence, run.end())
        and _DELIVERY_BEFORE_OPENING.search(sentence, run.end())
        and not _delivery_ties_run_to_part(sentence, run)
        and not _DELIVERY_NARROWED_RUN.search(sentence)
        and not _delivery_makes_run_optional(sentence, run)
        and not _DELIVERY_NEGATION.search(sentence)
        and not _DELIVERY_SKIPS.search(sentence)
    )


def _delivery_narrows_mutation_run(sentence: str) -> bool:
    """Return whether a sentence about mutation testing scopes it to part of the changed code, unnegated.

    It names mutation testing and either ties its run to part of the changed code (`_delivery_ties_run_to_part`) or
    holds a narrowed run (`_DELIVERY_NARROWED_RUN`) whose own clause does not negate it, so "rather than the `Mutation:`
    commands of the high-risk tasks" is not a narrowing.
    """
    if not _DELIVERY_MUTATION.search(sentence):
        return False
    run = _delivery_mutation_run(sentence)
    return (run is not None and _delivery_ties_run_to_part(sentence, run)) or any(
        not _DELIVERY_NEGATION.search(_delivery_clause_before(sentence, narrowed.start()))
        for narrowed in _DELIVERY_NARROWED_RUN.finditer(sentence)
    )


def _delivery_says_what_happens_without_the_tool(sentence: str) -> bool:
    """Return whether a sentence says what happens when the mutation tool cannot run on this machine."""
    return bool(
        _DELIVERY_TOOL.search(sentence)
        and _DELIVERY_CANNOT_RUN.search(sentence)
        and _DELIVERY_FALLBACK.search(sentence)
    )


def _delivery_single_risk_gaps(opening_blocks: list[str], finish_blocks: list[str]) -> list[str]:
    """Return what the two skills lack to warn about and pre-check a single pull request with high-risk tasks (R2.4)."""
    opening = [
        sentence for block in _delivery_single_high_risk_blocks(opening_blocks) for sentence in _sentences(block)
    ]
    finish = [sentence for block in _delivery_single_high_risk_blocks(finish_blocks) for sentence in _sentences(block)]
    gaps = []
    if not any(_delivery_warns_whole_feature(s) and _DELIVERY_BEFORE_OPENING.search(s) for s in opening):
        gaps.append(
            "opening-pull-requests/SKILL.md: no sentence about a single pull request with a high-risk task warns the"
            " user, before opening it, that `risk:high` will cover the whole feature"
        )
    if not any(_delivery_runs_local_mutation_first(s) for s in opening):
        gaps.append(
            "opening-pull-requests/SKILL.md: no sentence about a single pull request with a high-risk task runs"
            " mutation testing locally on all the changed code before opening it"
        )
    gaps.extend(
        f"opening-pull-requests/SKILL.md: scopes the local mutation run to part of the changed code: {s.strip()!r}"
        for s in opening
        if _delivery_narrows_mutation_run(s)
    )
    if not any(_delivery_says_what_happens_without_the_tool(s) for s in opening):
        gaps.append(
            "opening-pull-requests/SKILL.md: no sentence about a single pull request with a high-risk task says what"
            " happens when the mutation tool cannot run on this machine"
        )
    if not any(_delivery_warns_whole_feature(s) for s in finish):
        gaps.append(
            "develop-feature/SKILL.md (Phase 4: Finish): no sentence offering the single pull request warns that, with"
            " a high-risk task, `risk:high` will cover the whole feature"
        )
    return gaps


class SingleDeliveryRiskWarningTest(unittest.TestCase):
    maxDiff = None

    def test_single_delivery_warns_about_risk_high(self) -> None:
        """R2.4: a single pull request with a high-risk task is warned about and mutation-tested locally first.

        In opening-pull-requests/SKILL.md, the blocks that name the single pull request and a high-risk task hold:
        one sentence that warns the user, before opening (or pushing) it, that `risk:high` will cover the whole
        feature (or every slice or task, unqualified: not "each high-risk task"); one that requires running mutation
        testing locally on all the changed code (unqualified: not "all the high-risk changed code") before opening it,
        with nothing after its run verb naming a high-risk mention, a task or a slice ("of the high-risk tasks", "in
        the high-risk tasks' files") and nothing making it optional ("optionally", "may", "consider", "if you like",
        or "can" in the run's clause); no sentence about mutation testing that ties its run that way, unnegated, or
        scopes it to the tasks' own `Mutation:` commands or to the high-risk code; and one that says what happens (CI,
        evidence, a record or telling the user) when the tool cannot run on this machine. A high-risk task named before
        the run verb, as its condition, is fine, and so is the `risk:high` label after it. In develop-feature's
        `## Phase 4: Finish`, where the single delivery is offered, one sentence warns that with a high-risk task
        `risk:high` will cover the whole feature. Warning and local-run sentences carry no negation in any form and no
        "skip", "omit" or "avoid", and each warning names the single pull request, so R2.3's check ignores it.
        """
        gaps = _delivery_single_risk_gaps(
            _blocks(_DELIVERY_OPENING_PULL_REQUESTS), _section_blocks(_DELIVERY_DEVELOP_FEATURE, "Phase 4: Finish")
        )

        self.assertEqual(gaps, [], "\n".join(gaps))


# R9.4: rewriting the history of a pull request that is already pushed (a rebase onto the updated default branch, the
# stacked `git rebase --onto` after a squash merge) needs the user's yes for that rewrite and goes up with
# `--force-with-lease`, never a plain `--force`.
_DELIVERY_REWRITES_HISTORY = re.compile(r"\brewrit\w*|\brebas\w*")
_DELIVERY_ALREADY_PUSHED = re.compile(
    r"\balready (?:pushed|up|open|on (?:the )?(?:remote|origin))\b"
    r"|\bpushed\b|\bon the remote\b|\bremote (?:branch|history)\b"
)
_DELIVERY_LEASE_PUSH = re.compile(r"(?<![\w-])--force-with-lease\b")
_DELIVERY_PLAIN_FORCE = re.compile(r"(?<![\w-])(?:--force|-f)(?![\w-])|\bplain force\b")
# A force-push said in words ("force-push it", "force push", "push it by force").
_DELIVERY_FORCE_PUSH = re.compile(r"\bforce[- ]?push\w*|\bforced push\w*|\bpush\w*(?: \S+){0,2}? by force\b")
# What makes a force-push in words a lease push when it sits in the same clause.
_DELIVERY_WITH_LEASE = re.compile(r"--force-with-lease\b|\bwith\b(?: \S+){0,2}? lease\b")
# A prohibition that keeps a rule ("never --force", "don't force-push", "rather than --force"). Narrower than
# _DELIVERY_NEGATION: "no" and "without" also sit in conditions ("a rebase with no conflicts is pre-approved").
_DELIVERY_PROHIBITS = re.compile(r"\b(?:never|not|no longer|cannot|neither|nor|instead of|rather than)\b|n['\u2019]t\b")
# A condition attached to the lease push ("if you can", "when possible", "unless it fails", "ideally").
_DELIVERY_HEDGE = re.compile(
    r"\b(?:if|when|whenever|where|wherever)\b(?: \S+){0,3}? (?:possible|feasible|practical|convenient|available"
    r"|supported|appropriate|needed|necessary|works?|succeeds?|able|can|could|allowed|prefer\w*|likes?|wants?|wish\w*)\b"
    r"|\b(?:unless|ideally|preferabl[ey]|optionally|try\w* to|attempt\w* to)\b"
)
# Asking for the yes, or making the push wait on it ("with its own yes", "after the user's approval").
_DELIVERY_ASKS_YES = re.compile(
    r"\b(?P<trigger>ask\w*|wait\w* for|get\w*|needs?|requir\w*|seek\w*|with|after|once)\b(?: \S+){0,4}? "
    r"(?:yes|approval|approves?|go-ahead|consent|confirmation)\b"
)
# Triggers that bind the yes to the push however the sentence orders them ("push with lease only after the yes").
_DELIVERY_GATING_TRIGGERS = ("with", "after", "once")
_DELIVERY_HISTORY_CONTEXT = re.compile(
    rf"\brewrit\w*|\brebas\w*|--force|\blease\b|\bhistory\b|{_DELIVERY_FORCE_PUSH.pattern}"
)
# Waiving the yes in words that carry their own negation: "no need to ask", "don't ask", "skip the yes", "needs no yes".
_DELIVERY_WAIVES_YES = re.compile(
    r"\b(?:no need to|needn't|need not|never|don't|do not|doesn't|does not|(?:does|do)(?: not|n't) need to)"
    r"(?: \w+ly)? (?:ask|wait|seek|get|confirm|request)\b"
    r"|\b(?:skip|omit|forg[oe]|bypass|drop|ignor|dispens)\w*(?: \S+){0,2} "
    r"(?:yes|ask\w*|approval|confirmation|consent|go-ahead)\b"
    r"|\bno (?:yes|approval|confirmation|consent|go-ahead|need|requirement)\b"
)
# A need for the yes, negated: "does not need a yes", "doesn't require approval", "the yes is not needed", "this rule
# does not apply to stacked rebases".
_DELIVERY_NEGATED_NEED = re.compile(
    r"(?:\b(?:not|never|no longer)|n['\u2019]t)(?: (?:\w+ly|be|been))? "
    r"(?:need\w*|requir\w*|necessary|mandatory|compulsory|obligatory|appl(?:y|ies))\b"
    r"|\b(?:unnecessary|unneeded|needless)\b"
)
# Ways to weaken the yes that count only when no prohibition comes before them in their clause, so "never force-push
# without an explicit yes" and "the yes is never optional" keep the rule.
_DELIVERY_WEAKENS_YES = (
    # Made optional, given in advance or by default, exempt or waived.
    re.compile(
        r"\b(?:optional\w*|pre-?approv\w*|pre-?authori[sz]\w*|exempt\w*|waiv\w*|implicit\w*|implied|assumed"
        r"|automatic\w*|unprompted|silently|on (?:your|its|their) own|at (?:your|its|their) discretion)\b"
    ),
    # Taken as already given ("treat a stacked rebase as approved", "the user already approved").
    re.compile(
        r"\b(?:counts? as|treat\w*|consider\w*|deem\w*|already)(?: \S+){0,4}? (?:approv\w*|confirm\w*|consented)\b"
    ),
    # Carried over from another yes ("the push's yes also covers the rebase", "reuse the earlier approval").
    re.compile(
        r"\b(?:same|earlier|previous|prior|original|first|initial|existing|one|single|general|push|push's)\b"
        r"(?: \S+){0,2}? (?:yes|approval|go-ahead|consent)\b(?: \S+){0,3}? "
        r"(?:covers?|includes?|extends? to|suffices?|is enough|counts? for|carries over)\b"
        r"|\bre-?us\w*(?: \S+){0,3}? (?:yes|approval|go-ahead|consent)\b"
    ),
    # An ask made optional or permissive ("you may ask", "can ask", "consider asking").
    re.compile(
        r"\b(?:may|might|can|could|free to|welcome to|choose to|consider)(?: \S+){0,2}? (?:ask|request|seek|confirm)\w*"
    ),
    # An ask made conditional ("ask the yes if needed", "confirm when in doubt").
    re.compile(
        r"\b(?:ask\w*|yes|approval|confirm\w*|consent|go-ahead)\b(?: \S+){0,6}? (?:if|when|whenever|where|as)\b"
        r"(?: \S+){0,2}? (?:needed|necessary|in doubt|unsure|uncertain|appropriate|relevant|warranted|risky"
        r"|you (?:like|want|wish|prefer|think)\w*)\b"
    ),
    # Going up without the yes ("without asking", "without approval").
    re.compile(r"\bwithout\b(?: \S+){0,3}? (?:ask\w*|yes|approval|confirm\w*|consent|go-ahead)\b"),
)
# Permission to push or rewrite ("you may force-push it", "can rebase and push"), a waiver in a sentence that asks no
# yes.
_DELIVERY_PERMITS_PUSH = re.compile(
    r"\b(?:may|might|can|could|free to|allowed to|ok(?:ay)? to|fine to)(?: \S+){0,3}? "
    r"(?:force[- ]?push|push|rewrit|rebas)"
)
# Narrowing the rule to one kind of rewrite, or exempting some from it.
_DELIVERY_NARROWS_REWRITE = re.compile(
    r"\b(?:unless|except)\b|\b(?:only|solely|just)\b(?: \S+){0,4}? (?:stack|squash)\w*"
)
_DELIVERY_YES_AFTER_PUSH = re.compile(
    r"\b(?:after|once)(?: (?:the|it|its|it's|is|has|have|been|having|you|we|they))* (?:push\w*|force-push\w*)\b"
    r"|\bafterwards?\b|\bafter the fact\b|\bretroactiv\w*"
)


def _delivery_asks_yes_before_lease_push(sentence: str) -> bool:
    """Return whether a sentence asks the user's yes for a history rewrite and pushes it with `--force-with-lease`.

    The sentence names the rewrite (`_DELIVERY_REWRITES_HISTORY`); neither the lease push's clause nor the ask's clause
    is negated; and the yes comes first in the sentence or binds the push ("with its own yes", "only after the yes").
    """
    if not _DELIVERY_REWRITES_HISTORY.search(sentence):
        return False
    leases = [
        lease
        for lease in _DELIVERY_LEASE_PUSH.finditer(sentence)
        if not _DELIVERY_NEGATION.search(_delivery_clause_before(sentence, lease.start()))
    ]
    asks = [
        ask
        for ask in _DELIVERY_ASKS_YES.finditer(sentence)
        if not _DELIVERY_NEGATION.search(_delivery_clause_before(sentence, ask.start()) + ask.group(0))
    ]
    return any(
        ask.start() < lease.start() or ask.group("trigger") in _DELIVERY_GATING_TRIGGERS
        for lease in leases
        for ask in asks
    )


def _delivery_unprohibited(sentence: str, match: re.Match[str]) -> bool:
    """Return whether no prohibition (`_DELIVERY_PROHIBITS`) comes before a match in its clause."""
    return not _DELIVERY_PROHIBITS.search(_delivery_clause_before(sentence, match.start()))


def _delivery_clause_with_neighbours(sentence: str, index: int) -> str:
    """Return the clause of a sentence holding `index`, together with the clause before it and the clause after it."""
    bounds = [0, *(match.start() for match in _DELIVERY_CLAUSE_BREAK.finditer(sentence)), len(sentence)]
    clause = max(position for position in range(len(bounds) - 1) if bounds[position] <= index)
    return sentence[bounds[max(clause - 1, 0)] : bounds[min(clause + 2, len(bounds) - 1)]]


def _delivery_force_pushes_without_lease(sentence: str, force: re.Match[str]) -> bool:
    """Return whether a force-push in words is neither prohibited nor made a lease push in its clause."""
    clause = _delivery_clause_before(sentence, force.start()) + _delivery_clause_after(sentence, force.start())
    return _delivery_unprohibited(sentence, force) and not _DELIVERY_WITH_LEASE.search(clause)


def _delivery_force_gaps(sentences: list[str]) -> list[str]:
    """Return the sentences that push with a plain force or make the lease push conditional.

    A `--force`, `-f` or "plain force" (`_DELIVERY_PLAIN_FORCE`) counts unless a prohibition comes before it in its
    clause; a force-push in words (`_DELIVERY_FORCE_PUSH`) also unless its clause holds `--force-with-lease` or "with a
    lease"; a `--force-with-lease` is conditional when a condition (`_DELIVERY_HEDGE`) sits in its clause or in the
    clause before or after it.
    """
    gaps = [
        f"pushes with a plain --force: {sentence!r}"
        for sentence in sentences
        if any(_delivery_unprohibited(sentence, force) for force in _DELIVERY_PLAIN_FORCE.finditer(sentence))
    ]
    gaps.extend(
        f"force-pushes without a lease: {sentence!r}"
        for sentence in sentences
        if any(
            _delivery_force_pushes_without_lease(sentence, force) for force in _DELIVERY_FORCE_PUSH.finditer(sentence)
        )
    )
    gaps.extend(
        f"makes the lease push conditional: {sentence!r}"
        for sentence in sentences
        if any(
            _DELIVERY_HEDGE.search(_delivery_clause_with_neighbours(sentence, lease.start()))
            for lease in _DELIVERY_LEASE_PUSH.finditer(sentence)
        )
    )
    return gaps


def _delivery_weakens_yes(sentence: str) -> bool:
    """Return whether a sentence lets a history rewrite or force-push go up without a firm yes from the user.

    It waives the yes in words that carry their own negation (`_DELIVERY_WAIVES_YES`), negates the need for it
    (`_DELIVERY_NEGATED_NEED`), weakens it in any of `_DELIVERY_WEAKENS_YES` with no prohibition before it in its
    clause, or permits the push or rewrite (`_DELIVERY_PERMITS_PUSH`, not prohibited) in a sentence that asks no yes.
    """
    if _DELIVERY_WAIVES_YES.search(sentence) or _DELIVERY_NEGATED_NEED.search(sentence):
        return True
    if any(
        _delivery_unprohibited(sentence, weakening)
        for pattern in _DELIVERY_WEAKENS_YES
        for weakening in pattern.finditer(sentence)
    ):
        return True
    return not _DELIVERY_ASKS_YES.search(sentence) and any(
        _delivery_unprohibited(sentence, permit) for permit in _DELIVERY_PERMITS_PUSH.finditer(sentence)
    )


def _delivery_history_rewrite_gaps(blocks: list[str]) -> list[str]:
    """Return what opening-pull-requests' blocks lack to rewrite pushed history only with a yes and a lease (R9.4)."""
    gaps = []
    if not any(
        _DELIVERY_ALREADY_PUSHED.search(block)
        and any(_delivery_asks_yes_before_lease_push(sentence) for sentence in _sentences(block))
        for block in blocks
    ):
        gaps.append(
            "no paragraph or list item about an already pushed pull request says, in one sentence, to ask the user's"
            " yes for rewriting its history and push it with `--force-with-lease`"
        )
    sentences = [sentence.strip() for block in blocks for sentence in _sentences(block)]
    gaps.extend(_delivery_force_gaps(sentences))
    context = [sentence for sentence in sentences if _DELIVERY_HISTORY_CONTEXT.search(sentence)]
    gaps.extend(
        f"rewrites history without a firm yes: {sentence!r}" for sentence in context if _delivery_weakens_yes(sentence)
    )
    gaps.extend(
        f"narrows or exempts the rewrites that need a yes: {sentence!r}"
        for sentence in context
        if _DELIVERY_NARROWS_REWRITE.search(sentence)
    )
    gaps.extend(
        f"asks the yes after pushing: {sentence!r}"
        for sentence in context
        if _DELIVERY_ASKS_YES.search(sentence) and _DELIVERY_YES_AFTER_PUSH.search(sentence)
    )
    return gaps


class PushedHistoryRewriteTest(unittest.TestCase):
    maxDiff = None

    def test_rewriting_pushed_history_needs_a_yes(self) -> None:
        """R9.4: rewriting an already pushed pull request's history needs the user's yes and `--force-with-lease`.

        opening-pull-requests/SKILL.md has a paragraph or list item about an already pushed pull request (pushed, on
        the remote) where one sentence names the rewrite (rewrite, rebase), asks the user's yes for it and pushes it
        with `--force-with-lease`, with neither clause negated and the yes coming first or binding the push ("with its
        own yes", "only after the yes"). No sentence anywhere pushes with a plain `--force`, `-f` or "plain force"
        outside a prohibiting clause ("never --force"), force-pushes in words ("force-push it") outside a prohibiting
        clause and without a lease in that clause, or attaches a condition to the lease push ("if you can", "when
        possible", "unless", "ideally"). No sentence about rewriting history, force-pushing or the lease weakens the
        yes: waives it ("no need to ask", "skip the yes", "needs no yes"), negates the need for it ("does not need a
        yes", "is not required"), makes it optional, pre-approved, exempt, implied or carried over from another yes,
        makes the ask optional, permissive or conditional ("optionally ask", "you may ask", "ask if needed"), goes up
        without it ("without asking"), or permits the push in a sentence that asks no yes ("you may force-push it");
        all but the waivers and negated needs count only outside a prohibiting clause, so "never force-push without
        an explicit yes" and "the yes is never optional" keep the rule. Nor does any such sentence narrow or exempt
        the rewrites it covers ("only for stacked rebases", "except a stacked rebase", "unless"), or ask the yes after
        pushing.
        """
        gaps = [
            f"opening-pull-requests/SKILL.md: {gap}"
            for gap in _delivery_history_rewrite_gaps(_blocks(_DELIVERY_OPENING_PULL_REQUESTS))
        ]

        self.assertEqual(gaps, [], "\n".join(gaps))


_MEASURE_IMPACT = SKILLS_DIR / "measure-impact" / "SKILL.md"
_RUN_SH = re.compile(r"\brun\.sh\b")
_SESSION_COSTS = re.compile(r"\bsession_costs\.py\b")
_METRICS_REPORT = re.compile(r"\bmetrics_report\.py\b")
_TRANSCRIPT = re.compile(r"\btranscripts?\b")
_COST = re.compile(r"\bcosts?\b")
_NOT_IN_REPORT = re.compile(r"\bnot\b[^.:;]*\bin (?:this|the) report\b")


class MeasureImpactCostsTest(unittest.TestCase):
    maxDiff = None  # a failure lists every gap, not the first one

    def test_measure_impact_adds_session_costs_when_given_transcripts(self) -> None:
        """R6.6: 002 measure-impact's argument hint names the transcript folders; its `## Workflow` has a block that
        runs session_costs.py through run.sh with the transcript folders it is given, and still runs metrics_report.py
        through run.sh, so the costs report sits next to the delivery report instead of replacing it; and no sentence
        of `## Limits to state when relevant` says the cost is not in the report unless it is about transcripts (the
        case where none were given).
        """
        hint = read_frontmatter(_MEASURE_IMPACT).get("argument-hint", "").lower()
        workflow = _section_blocks(_MEASURE_IMPACT, "Workflow")
        limits = _section_blocks(_MEASURE_IMPACT, "Limits to state when relevant")

        gaps = [] if _TRANSCRIPT.search(hint) else [f"argument-hint does not mention the transcript folders: {hint!r}"]
        if not any(all(p.search(block) for p in (_RUN_SH, _SESSION_COSTS, _TRANSCRIPT)) for block in workflow):
            gaps.append("Workflow has no block running session_costs.py through run.sh with the transcript folders")
        if not any(_RUN_SH.search(block) and _METRICS_REPORT.search(block) for block in workflow):
            gaps.append("Workflow no longer runs the delivery report (metrics_report.py) through run.sh")
        gaps += [
            f"Limits still says the cost is not in the report: {sentence!r}"
            for block in limits
            for sentence in _sentences(block)
            if _COST.search(sentence) and _NOT_IN_REPORT.search(sentence) and not _TRANSCRIPT.search(sentence)
        ]

        self.assertEqual(gaps, [], "\n".join(gaps))


_REPOSITORY_ROOT = PLUGIN_ROOT.parents[1]
_TASKS_TEMPLATE = SKILLS_DIR / "writing-plans" / "templates" / "tasks.md"
_SLICE_SUMMARY_TEMPLATE = SKILLS_DIR / "develop-feature" / "templates" / "slice-summary.md"
_DEVELOP_FEATURE = SKILLS_DIR / "develop-feature" / "SKILL.md"
# R7.4: every file that states the default budget of a slice or a pull request, with the `## ` section holding it
# (None: the whole file).
_BUDGET_FILES: dict[str, tuple[Path, str | None]] = {
    "writing-plans/SKILL.md": (_WRITING_PLANS, None),
    "engineering-standards/SKILL.md": (SKILLS_DIR / "engineering-standards" / "SKILL.md", "6. Git and pull requests"),
    "opening-pull-requests/SKILL.md": (SKILLS_DIR / "opening-pull-requests" / "SKILL.md", "Workflow"),
    "measure-impact/SKILL.md": (_MEASURE_IMPACT, "Limits to state when relevant"),
    "README.md": (_REPOSITORY_ROOT / "README.md", None),
}
_BUDGET = re.compile(r"\bbudget\b|\bpresupuesto\b|\btope\b")
_LINES_400 = re.compile(r"(?<![\d,.])400(?![\d,])")
_LINES_500 = re.compile(r"(?<![\d,.])500(?![\d,])")
_AIM_300_TO_500 = re.compile(r"(?<![\d,.])300\s*(?:\u2013|-|to|and)\s*500(?![\d,])")
_CODE_AND_TESTS = re.compile(r"\bcode\b.*\btests?\b|\btests?\b.*\bcode\b")
_DOCUMENTS = re.compile(r"\bdocuments?\b")
_NOT_COUNTED = re.compile(r"\b(?:not|never|no)\b(?: \S+){0,3} count|\bexclud\w*|\bwithout\b|\bapart\b|\bseparate\w*")
_SMALLER = re.compile(r"\bsmaller\b")
_HIGH_RISK = re.compile(r"\bhigh[- ]risk\b")
_ADDED_REMOVED = re.compile(r"\badded\b.*\bremoved\b")
_OVER = re.compile(r"\b(?:over|exceed\w*|above|past)\b")
_HOW_MUCH = re.compile(r"\bhow (?:much|many)\b|\bover by\b|\bby \S+ lines\b|\bexcess\b")
_WARNS = re.compile(r"\bwarn\w*|\bflag\w*|\balert\w*")
_PRE_APPROVED = re.compile(r"\bpre-approved\b")
_SUMMARY = re.compile(r"\bsummary\b")
_MESSAGE = re.compile(r"\bmessage\b")


def _slice_size_gaps() -> list[str]:
    """Return what writing-plans, its tasks.md template, the slice summary and develop-feature miss of R7.1-R7.3."""
    plans = _blocks(_WRITING_PLANS)
    template_budget = [line for line in _blocks(_TASKS_TEMPLATE) if "pull request budget" in line]
    size = " ".join(read_section(_SLICE_SUMMARY_TEMPLATE, "Size").lower().split())
    checkpoint = _section_blocks(_DEVELOP_FEATURE, "Slice checkpoint")
    checks = {
        "writing-plans: no block aims a slice at 300-500 changed lines of code and tests, documents not counted": any(
            all(p.search(b) for p in (_AIM_300_TO_500, _CODE_AND_TESTS, _DOCUMENTS, _NOT_COUNTED)) for b in plans
        ),
        "writing-plans: no block allows a smaller slice only for a smaller feature or to split high-risk work": any(
            _SMALLER.search(b) and "feature" in b and _HIGH_RISK.search(b) for b in plans
        ),
        "templates/tasks.md: the Pull request budget line does not default to 500": any(
            _LINES_500.search(line) and not _LINES_400.search(line) for line in template_budget
        ),
        "slice-summary.md: ## Size does not count code and tests (added, removed) apart from the documents": all(
            p.search(size) for p in (_CODE_AND_TESTS, _ADDED_REMOVED, _DOCUMENTS)
        ),
        "develop-feature: Slice checkpoint does not warn when a slice goes over the budget, and by how much": any(
            all(p.search(b) for p in (_OVER, _BUDGET, _WARNS, _HOW_MUCH)) for b in checkpoint
        ),
        "develop-feature: with pre-approved pauses the warning is not kept in the summary and session message": any(
            all(p.search(b) for p in (_PRE_APPROVED, _WARNS, _SUMMARY, _MESSAGE)) for b in checkpoint
        ),
    }
    return [gap for gap, holds in checks.items() if not holds]


def _default_budget_gaps() -> list[str]:
    """Return each file of `_BUDGET_FILES` that still gives 400 lines as a budget, or none at all as 500 (R7.4)."""
    gaps = []
    for name, (path, heading) in _BUDGET_FILES.items():
        blocks = _blocks(path) if heading is None else _section_blocks(path, heading)
        budget_blocks = [block for block in blocks if _BUDGET.search(block)]
        gaps += [f"{name}: still a 400-line budget: {block!r}" for block in budget_blocks if _LINES_400.search(block)]
        if not any(_LINES_500.search(block) for block in budget_blocks):
            gaps.append(f"{name}: no block gives 500 changed lines as the default budget")
    return gaps


class SliceSizeTest(unittest.TestCase):
    maxDiff = None  # a failure lists every gap, not the first one

    def test_slices_aim_at_300_to_500_changed_lines(self) -> None:
        """R7.1, R7.2, R7.3, R7.4, R9.1: 003 slices aim at 300-500 changed lines and the pause reports their size.

        writing-plans has a block that aims each slice at 300-500 changed lines of code and tests without counting the
        feature's documents, and one that allows a smaller slice only for a smaller feature or to split high-risk
        work; its tasks.md template defaults the Pull request budget to 500. The slice summary's `## Size` counts the
        changed lines of code and tests (added, removed) apart from the documents'. develop-feature's `## Slice
        checkpoint` warns when a slice goes over the budget, with by how much, and with pre-approved pauses keeps that
        warning in the summary and the session's message. No file in `_BUDGET_FILES` still gives 400 lines as a
        budget, and each gives 500.
        """
        gaps = _slice_size_gaps() + _default_budget_gaps()

        self.assertEqual(gaps, [], "\n".join(gaps))


# Pull request text (003 R5.1-R5.4, R9.1, R9.2): opening-pull-requests follows the repository's pull request template
# word for word, else four fixed sections, in English and plain words, with none of the flow's data; setup-project's
# template has those four sections; the release is 0.8.0. Keywords of each rule inside its section, on text that is
# lowercased, without backticks and single-spaced, as _split_blocks leaves it.
_TEXT_OPENING = SKILLS_DIR / "opening-pull-requests" / "SKILL.md"
_TEXT_TEMPLATE = SKILLS_DIR / "setup-project" / "templates" / "pull_request_template.md"
_TEXT_MANIFEST = PLUGIN_ROOT / ".claude-plugin" / "plugin.json"
_TEXT_CHANGELOG = PLUGIN_ROOT / "CHANGELOG.md"
_TEXT_README = PLUGIN_ROOT.parents[1] / "README.md"
_TEXT_RELEASE = "0.8.0"
_TEXT_SECTIONS = ["What and why", "Where to look first", "How it was verified", "Not in this pull request"]
_TEXT_FENCE = re.compile(r"\s*(?:```|~~~)")
_TEXT_LEAVES_OUT = re.compile(
    r"\bleav\w*\b(?: \S+){0,8}? out\b|\bleft out\b|\bkeep\w*\b(?: \S+){0,8}? out of\b|\bomit\w*|\bexclud\w*"
    r"|\bnever\b|\bwithout\b|\bno\b|\bnothing\b"
)
_TEXT_PLAIN = re.compile(r"\bplain\b|\bsimple\b|\beveryday\b")
_TEXT_TITLE = re.compile(r"\btitles?\b")
_TEXT_DESCRIPTION = re.compile(r"\bdescriptions?\b")
# What the pull request text must never hold, outside backticks and link targets (R5.4).
_TEXT_FLOW_DATA = re.compile(
    r"\b[rtsb]\d+(?:\.\d+)?\b|\b[rtsb]<[nk]>|\bslices?\b|\bpartitions?\b|\btask ids?\b|\breview rounds?\b"
    r"|\b(?:task|covers|rounds|escaped-gate|adjusts|asked):"  # `reviews:` is ordinary prose in a description
)
_TEXT_ROLE_NAMES = re.compile("|".join(rf"\b{re.escape(agent.stem)}\b" for agent in sorted(AGENTS_DIR.glob("*.md"))))
# The sections the four fixed ones replace, named anywhere in step 4's prose.
_TEXT_OLD_SECTIONS = re.compile(
    r"\brequirements → tests\b|\brisk and where to look first\b|\bcommits, one per task\b|\bhow it was built\b"
)
# R5.1, R5.2, R5.3, R5.4 and the merge-order line T9 put first: each rule must sit in one sentence of step 4's prose.
_TEXT_STEP_4_RULES: dict[str, tuple[re.Pattern[str], ...]] = {
    "(R5.1) looking for pull_request_template.md in .github/, then the root, then docs/": (
        re.compile(r"\bpull_request_template\.md\b"),
        re.compile(r"\.github/"),
        re.compile(r"\broot\b"),
        re.compile(r"\bdocs/"),
        re.compile(r"\bin (?:that|this) order\b|\bthen\b|\bfollowed by\b"),
    ),
    "(R5.1) matching the template's name in any letter case": (
        re.compile(r"\bpull_request_template\.md\b"),
        re.compile(r"\bcase\b|\bcapitali[sz]\w*|\b(?:upper|lower)case\b"),
    ),
    "(R5.1) keeping the template's sections in order, with their headings and fixed text as they are": (
        re.compile(r"\bsections?\b"),
        re.compile(r"\border\b"),
        re.compile(r"\bheadings?\b|\btitles?\b"),
        re.compile(r"\btext\b"),
        re.compile(r"\bverbatim\b|\bword for word\b|\bas (?:is|they are|written)\b|\bunchanged\b|\bexactly\b"),
    ),
    "(R5.1) filling each section in place of its help comments": (
        re.compile(r"\bcomments?\b"),
        re.compile(r"\binstead of\b|\bin place of\b|\breplac\w*"),
    ),
    "(R5.1) None in a section with nothing to say": (
        re.compile(r"\bnone\b"),
        re.compile(r"\bempty\b|\bnothing\b|\bno content\b|\bwithout content\b"),
    ),
    "(R5.1) checking a box only when what it says was verified": (
        re.compile(r"\bcheck ?box\w*|\bboxes\b|\btick\w*"),
        re.compile(r"\bonly\b"),
        re.compile(r"\bverif\w*|\bconfirm\w*"),
    ),
    "(R5.2) the fixed sections when there is no such template, even with a folder of several": (
        re.compile(r"\bfolder\b|\bdirector(?:y|ies)\b"),
        re.compile(r"\bseveral\b|\bmultiple\b|\bmany\b|\bmore than one\b"),
        re.compile(r"\bsections?\b"),
    ),
    "(R5.3) the title and the description in English and plain words": (
        _TEXT_TITLE,
        _TEXT_DESCRIPTION,
        re.compile(r"\benglish\b"),
        _TEXT_PLAIN,
    ),
    "(R5.4) the title and the description leave out the flow's data": (
        _TEXT_LEAVES_OUT,
        _TEXT_TITLE,
        _TEXT_DESCRIPTION,
        re.compile(r"\bflow\b"),
    ),
    "(R5.4) no IDs of requirements, bug criteria, tasks, slices or partitions": (
        _TEXT_LEAVES_OUT,
        re.compile(r"\bids?\b"),
        re.compile(r"\brequirements?\b"),
        re.compile(r"\bcriteri(?:on|a)\b"),
        re.compile(r"\btasks?\b"),
        re.compile(r"\bslices?\b"),
        re.compile(r"\bpartitions?\b"),
    ),
    '(R5.4) not the word "slice"': (_TEXT_LEAVES_OUT, re.compile(r"\bword\b\W{1,3}slice\b")),
    "(R5.4) no Task:, Covers:, Rounds: or Escaped-gate: lines": (
        _TEXT_LEAVES_OUT,
        re.compile(r"\btask:"),
        re.compile(r"\bcovers:"),
        re.compile(r"\brounds:"),
        re.compile(r"\bescaped-gate:"),
    ),
    "(R5.4) no review rounds and no names of the plugin's roles": (
        _TEXT_LEAVES_OUT,
        re.compile(r"\breview rounds?\b|\brounds? of reviews?\b"),
        re.compile(r"\broles?(?:'s?)? names?\b|\bnames? of (?:the )?(?:plugin'?s? )?(?:roles|subagents|agents)\b"),
    ),
    "(R5.4) code and paths in backticks, code blocks and link targets are exempt": (
        re.compile(r"\bbackticks?\b"),
        re.compile(r"\bcode blocks?\b"),
        re.compile(
            r"\blink (?:targets?|destinations?|urls?)\b|\b(?:targets?|destinations?|urls?) of (?:the )?links?\b"
        ),
    ),
    "(T9) a stacked description still starts with its Merge order: line": (
        re.compile(r"\bmerge order:"),
        re.compile(r"\bfirst line\b|\bbefore any section\b|\bstart\w*"),
    ),
}
# R5.2: what each fixed section asks for, in the skill's fallback block and in setup-project's template.
_TEXT_SECTION_CONTENT: dict[str, tuple[tuple[str, re.Pattern[str]], ...]] = {
    "Where to look first": (
        ("each change's risk", re.compile(r"\brisk\b")),
        ("in plain words", _TEXT_PLAIN),
        ("for high-risk changes", re.compile(r"\bhigh[- ]risk\b")),
        ("the files", re.compile(r"\bfiles?\b")),
        ("and lines to read first", re.compile(r"\blines?\b")),
        ("and what they guard", re.compile(r"\bguard\w*|\bprotect\w*")),
    ),
    "How it was verified": (
        ("the check's result", re.compile(r"\bcheck\b")),
        ("each behavior", re.compile(r"\bbehaviou?rs?\b")),
        ("with its test", re.compile(r"\btests?\b")),
        ("the end-to-end evidence", re.compile(r"\bend[- ]to[- ]end\b")),
    ),
}
_TEXT_EXPLICIT_YES = re.compile(r"\b(?:wait\w*|ask\w*) for (?:an |the |their |its )?(?:explicit )?yes\b")
_TEXT_NEVER_MERGES_OR_APPROVES = (re.compile(r"\bnever\b"), re.compile(r"\bmerge\b"), re.compile(r"\bapprove\b"))
_TEXT_CHANGELOG_ITEMS = (
    ("live publishing", re.compile(r"\blive\b")),
    ("the flow's data in refs/notes/konundrm", re.compile(r"\brefs/notes/konundrm\b")),
    ("the pull request text", re.compile(r"\bpull request (?:template|text|descriptions?)\b")),
)
_TEXT_README_ITEMS = (
    ("live publishing (en vivo)", re.compile(r"\ben vivo\b")),
    ("where the flow's data stays (refs/notes/konundrm)", re.compile(r"\brefs/notes/konundrm\b")),
)


def _text_subsection(path: Path, prefix: str) -> tuple[list[str], list[str]]:
    """Return the prose lines and the fenced lines of the `### ` subsection whose heading starts with `prefix`.

    The subsection runs to the next `## ` or `### ` heading outside a code fence; both lists are empty without it.
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    start = next((index for index, line in enumerate(lines) if line.startswith(prefix)), None)
    if start is None:
        return [], []
    prose: list[str] = []
    fenced: list[str] = []
    in_fence = False
    for line in lines[start + 1 :]:
        if _TEXT_FENCE.match(line):
            in_fence = not in_fence
            continue
        if not in_fence and line.startswith(("## ", "### ")):
            break
        (fenced if in_fence else prose).append(line)
    return prose, fenced


def _text_normalized(lines: list[str]) -> str:
    """Return pull request text lowercased and single-spaced, without backtick spans and link targets (R5.4)."""
    text = re.sub(r"`[^`]*`", " ", "\n".join(lines))
    text = re.sub(r"\]\([^)]*\)", "]", text)
    return " ".join(text.lower().split())


def _text_body_gaps(name: str, lines: list[str]) -> list[str]:
    """Return what a pull request body's sections lack: the four fixed headings in order, what two of them ask for,
    and no flow data or role name anywhere in the body (R5.2, R5.4)."""
    headings = [line[3:].strip() for line in lines if line.startswith("## ")]
    gaps = [] if headings == _TEXT_SECTIONS else [f"{name}: its sections are {headings}, not {_TEXT_SECTIONS}"]
    bodies: dict[str, list[str]] = {}
    for line in lines:
        if line.startswith("## "):
            bodies[line[3:].strip()] = []
        elif bodies:
            bodies[list(bodies)[-1]].append(line)
    for heading, items in _TEXT_SECTION_CONTENT.items():
        body = _text_normalized(bodies.get(heading, []))
        gaps += [
            f"{name}: '{heading}' does not ask for {label}" for label, pattern in items if not pattern.search(body)
        ]
    text = _text_normalized(lines)
    found = sorted({match.group(0) for match in _TEXT_FLOW_DATA.finditer(text)})
    found += sorted({match.group(0) for match in _TEXT_ROLE_NAMES.finditer(text)})
    if found:
        gaps.append(f"{name}: holds the flow's data or role names: {found}")
    return gaps


def _text_skill_gaps() -> list[str]:
    """Return what opening-pull-requests' step 4 lacks to write the pull request text R5.1-R5.4 ask for."""
    prose, fenced = _text_subsection(_TEXT_OPENING, "### 4.")
    blocks = _split_blocks(prose)
    gaps = [
        f"opening-pull-requests step 4 lacks {label}"
        for label, patterns in _TEXT_STEP_4_RULES.items()
        if not any(_in_one_sentence(block, *patterns) for block in blocks)
    ]
    gaps += _text_body_gaps("opening-pull-requests step 4's fixed sections", fenced)
    gaps += [
        f"opening-pull-requests step 4 still names a replaced section: {block!r}"
        for block in blocks
        if _TEXT_OLD_SECTIONS.search(block)
    ]
    return gaps


def _text_invariant_gaps() -> list[str]:
    """Return the invariant's gaps: opening-pull-requests still waits for a yes before pushing and never merges or
    approves."""
    gaps = []
    ask_prose, _ = _text_subsection(_TEXT_OPENING, "### 5.")
    if not any(_TEXT_EXPLICIT_YES.search(block) for block in _split_blocks(ask_prose)):
        gaps.append("opening-pull-requests step 5 lacks (invariant): waiting for an explicit yes before pushing")
    if not any(
        _in_one_sentence(block, *_TEXT_NEVER_MERGES_OR_APPROVES) for block in _section_blocks(_TEXT_OPENING, "Rules")
    ):
        gaps.append("opening-pull-requests Rules lack (invariant): never merging or approving")
    return gaps


def _text_release_gaps() -> list[str]:
    """Return what plugin.json, the CHANGELOG and the README lack for this feature, released as 0.8.0 (R9.2).

    Later releases put newer entries above its entry, so plugin.json's version only has to be 0.8.0 or later and the
    [0.8.0] entry is looked up by its version, never by its position.
    """
    gaps = []
    version = json.loads(_TEXT_MANIFEST.read_text(encoding="utf-8"))["version"]
    numbers = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", version)
    released = tuple(int(part) for part in _TEXT_RELEASE.split("."))
    if numbers is None or tuple(int(part) for part in numbers.groups()) < released:
        gaps.append(f"plugin.json: version is {version}, older than {_TEXT_RELEASE}")
    heading = next(
        (
            line[3:]
            for line in _TEXT_CHANGELOG.read_text(encoding="utf-8").splitlines()
            if line.startswith(f"## [{_TEXT_RELEASE}]")
        ),
        None,
    )
    if heading is None:
        gaps.append(f"CHANGELOG.md: there is no [{_TEXT_RELEASE}] entry")
    else:
        entry = " ".join(read_section(_TEXT_CHANGELOG, heading).lower().replace("`", "").split())
        gaps += [
            f"CHANGELOG.md [{_TEXT_RELEASE}]: does not name {label}"
            for label, pattern in _TEXT_CHANGELOG_ITEMS
            if not pattern.search(entry)
        ]
    readme, _ = _text_subsection(_TEXT_README, "### Cómo avanza una feature")
    flow = " ".join(" ".join(readme).lower().replace("`", "").split())
    gaps += [
        f"README.md '### Cómo avanza una feature': does not describe {label}"
        for label, pattern in _TEXT_README_ITEMS
        if not pattern.search(flow)
    ]
    return gaps


class PullRequestTextTest(unittest.TestCase):
    maxDiff = None  # a failure lists every gap, not the first one

    def test_pull_request_text_follows_the_template_without_flow_data(self) -> None:
        """R5.1, R5.2, R5.3, R5.4, R9.1, R9.2: 003 the pull request text follows the repository's template word for
        word, else four fixed sections, in English and plain words, with none of the flow's data.

        opening-pull-requests' step 4 says, each in one sentence: look for `pull_request_template.md` in `.github/`,
        then the root, then `docs/`, in any letter case; keep its sections in order with their headings and fixed text
        as they are; fill each in place of its help comments, "None" when it has nothing; check a box only when what it
        says was verified; without that template, even with a folder of several, use the fixed sections; write the
        title and the description in English and plain words; leave out of them the flow's data (IDs of requirements,
        bug criteria, tasks, slices and partitions, the word "slice", the Task:, Covers:, Rounds: and Escaped-gate:
        lines, review rounds and role names), except code and paths in backticks, code blocks and link targets; and a
        stacked description still starts with its Merge order: line. Its fixed sections, and setup-project's
        pull_request_template.md, are exactly What and why, Where to look first (risk in plain words; for high risk
        the files and lines and what they guard), How it was verified (check, each behavior with its test, end-to-end
        evidence) and Not in this pull request, with no flow data or role name. Invariant: step 5 still waits for an
        explicit yes before pushing and Rules still never merge or approve. plugin.json is 0.8.0 or later, the
        CHANGELOG's [0.8.0] entry, looked up by its version, names live publishing, refs/notes/konundrm and the pull
        request text, and the README's `### Cómo avanza una feature` describes publishing "en vivo" and
        refs/notes/konundrm.
        """
        template_lines = _TEXT_TEMPLATE.read_text(encoding="utf-8").splitlines()

        gaps = (
            _text_skill_gaps()
            + _text_body_gaps("setup-project/templates/pull_request_template.md", template_lines)
            + _text_invariant_gaps()
            + _text_release_gaps()
        )

        self.assertEqual(gaps, [], "\n".join(gaps))


# Consolidation (004 R1.1-R1.7): writing-plans lists one behavior per task, then merges related low-risk tasks into one
# consolidated task that keeps one test per behavior. Keywords of each rule inside one sentence of a block of its
# SKILL.md (lowercased, without backticks, single-spaced): outside its Self-review and Approval steps, inside its
# Self-review step, or inside its Approval step. The template shows such a task, and still parses.
_MERGE = re.compile(r"\bmerg\w*|\bconsolidat\w*")
_MERGE_CONSOLIDATED_TASK = re.compile(r"\bconsolidated tasks?\b")
_MERGE_FIRST = re.compile(r"\bfirst\b")
_MERGE_BEHAVIOR = re.compile(r"\bbehaviou?rs?\b")
_MERGE_OWN_LINE = re.compile(r"\b(?:its|their) own lines?\b")
_MERGE_SINGLE_CYCLE = re.compile(r"\b(?:a single|one) cycle\b")
_MERGE_NEXT_TO_EACH_OTHER = re.compile(r"\bnext to each other\b")
_MERGE_DEPENDENCY_FORBIDS = re.compile(r"\bdependenc(?:y|ies)\b")
_MERGE_LOW_RISK = re.compile(r"\blow[- ]risk\b")
_MERGE_ALL = re.compile(r"\b(?:all|every|each)\b")
_MERGE_MEDIUM = re.compile(r"\bmedium\b")
_MERGE_HIGH = re.compile(r"\bhigh\b")
_MERGE_NEVER = re.compile(r"\bnever\b")
_MERGE_OWNERSHIP_ROW = re.compile(r"\brow\b(?: \S+){0,4} ownership table\b")
_MERGE_SAME_RULE = re.compile(r"\bsame rule\b")
_MERGE_VERIFY_COMMAND = re.compile(r"\bverify command\b")
_MERGE_ONE_LOGICAL_CHANGE = re.compile(r"\bone logical change\b")
_MERGE_TITLE = re.compile(r"\btitle\b")
_MERGE_FIVE = re.compile(r"\b(?:at most|no more than|up to) (?:five|5)\b")
_MERGE_LINES_300 = re.compile(r"(?<![\d,.])300(?![\d,])(?: \S+){0,2} lines\b")
_MERGE_PULL_REQUEST_BUDGET = re.compile(r"\bpull request budget\b")
_MERGE_PROPERTY = re.compile(r"\bproperty\b")
_MERGE_DECISION_FIELD = re.compile(r"\bdecision:")
_MERGE_DEPENDENCY = re.compile(r"\bdependency\b")
_MERGE_CHORE = re.compile(r"\bchore\b")
_MERGE_ONE_TITLE = re.compile(r"\bone title\b")
_MERGE_AGAIN = re.compile(r"\bmerge again\b")
_MERGE_SHOWN_AGAIN = re.compile(r"\bshow\w*(?: \S+){0,3} again\b")
_MERGE_LOW_RISK_TASK = re.compile(r"\blow[- ]risk task\b")
_MERGE_DOUBT = re.compile(r"\bdoubt\b|\bunsure\b")
_MERGE_APART = re.compile(r"\bapart\b|\bseparate\b")
_MERGE_ONE_ID = re.compile(r"\bone id\b")
_MERGE_COVERS = re.compile(r"\bcovers\b")
_MERGE_HEADER_LINE = re.compile(r"\bconsolidation:")
_MERGE_USER = re.compile(r"\buser\b")
_MERGE_LOW = re.compile(r"\blow\b")
_MERGE_LOW_AND_MEDIUM = re.compile(r"\blow and medium\b")
_MERGE_ONE_RULE = re.compile(r"\bone rule\b")
_MERGE_THREE = re.compile(r"\b(?:at most|no more than|up to) (?:three|3)\b")
_MERGE_NONE = re.compile(r"\bnone\b")
_MERGE_ONE_TASK_PER_LINE = re.compile(r"\bone task per line\b")
_MERGE_BEHAVIORS_IN_TASKS = re.compile(r"\bbehaviou?rs in <m> tasks\b")
_MERGE_STAYED_APART = re.compile(r"\bstay(?:ed|s)? apart\b")
_MERGE_PLAN_CHANGE = re.compile(r"\bplan change\b")
_MERGE_WITHOUT_THAT_LINE = re.compile(r"\bwithout that line\b")
_MERGE_READS_AS_LOW = re.compile(r"\breads as low\b")
_MERGE_ONLY_WITH_MEDIUM = re.compile(r"\bonly with other medium lines\b")
_MERGE_FILES_LINE = re.compile(r"\bfiles: line\b")
_MERGE_INVARIANTS = re.compile(r"\binvariants\b")
_MERGE_COVERING_PROPERTY_TASK = re.compile(r"\bproperty task that covers it\b")
_MERGE_MEDIUM_LINES = re.compile(r"\bmedium lines\b")
_MERGE_SAME_WAY = re.compile(r"\bsame way\b")
_MERGE_RENUMBERED = re.compile(r"\brenumber\w*")
_MERGE_WHY = re.compile(r"\bwhy\b")
_MERGE_CHANGE = re.compile(r"\bchange\b")
_MERGE_TEMPLATE_HEADER = re.compile(r"(?m)^- \*\*Consolidation:\*\* low\b")
_MERGE_TESTS_LIST = re.compile(r"\btests: list\b")
_MERGE_TESTS_FIELD = re.compile(r"\btests:")
_MERGE_ONE_TEST_PER_BEHAVIOR = re.compile(r"\bone test per behaviou?r\b")
_MERGE_CRITERION = re.compile(r"\bcriteri(?:on|a)\b")
_MERGE_CONDITIONS = re.compile(r"\bconditions?\b")
_MERGE_OWN_TEST = re.compile(r"\b(?:its|their) own tests?\b")
_MERGE_NUMBER_OF_BEHAVIORS = re.compile(r"\b(?:number of|how many) behaviou?rs\b")
_MERGE_TOTALS = re.compile(r"\btotals?\b")
_MERGE_TASKS = re.compile(r"\btasks\b")
_MERGE_OLD_RULE = re.compile(r"\bone behaviou?r, one test, one commit\b")
# What writing-plans/SKILL.md must say outside its Self-review and Approval steps, each in one sentence.
_MERGE_RULES: dict[str, tuple[re.Pattern[str], ...]] = {
    "R1.1 every behavior is first listed on its own line": (_MERGE_FIRST, _MERGE_BEHAVIOR, _MERGE_OWN_LINE),
    "R1.1 the lines that belong together merge into one consolidated task, built in a single cycle": (
        _MERGE,
        _MERGE_CONSOLIDATED_TASK,
        _MERGE_SINGLE_CYCLE,
    ),
    "R1.1 lines merge even when they are not next to each other, unless a dependency forbids it": (
        _MERGE_NEXT_TO_EACH_OTHER,
        _MERGE_DEPENDENCY_FORBIDS,
    ),
    "R1.2, R1.3 every merged line is low risk, and a medium or high line is never merged": (
        _MERGE_LOW_RISK,
        _MERGE_ALL,
        _MERGE_MEDIUM,
        _MERGE_HIGH,
        _MERGE_NEVER,
        _MERGE,
    ),
    "R1.2 one owner: one row of the design's ownership table or one rule applied to several owners, with one verify"
    " command": (_MERGE_OWNERSHIP_ROW, _MERGE_SAME_RULE, _MERGE_VERIFY_COMMAND),
    "R1.2 they form one logical change that one title states": (_MERGE_ONE_LOGICAL_CHANGE, _MERGE_TITLE),
    "R1.2 at most five behaviors and about 300 changed lines, never more than the pull request budget": (
        _MERGE_FIVE,
        _MERGE_BEHAVIOR,
        _MERGE_LINES_300,
        _MERGE_PULL_REQUEST_BUDGET,
    ),
    "R1.3 a property line, one that needs a Decision: field and one that adds a dependency are never merged": (
        _MERGE_NEVER,
        _MERGE,
        _MERGE_PROPERTY,
        _MERGE_DECISION_FIELD,
        _MERGE_DEPENDENCY,
    ),
    "R1.5 chore lines merge with each other when one title states them, or into the low-risk task they prepare": (
        _MERGE_CHORE,
        _MERGE,
        _MERGE_ONE_TITLE,
        _MERGE_LOW_RISK_TASK,
    ),
    "R1.3 when a condition is in doubt the lines stay apart": (_MERGE_DOUBT, _MERGE_APART),
    "R1.4 a consolidated task is one task: one ID, every criterion in Covers and a Tests: list with one test per"
    " behavior and its criterion": (
        _MERGE_CONSOLIDATED_TASK,
        _MERGE_ONE_ID,
        _MERGE_COVERS,
        _MERGE_TESTS_LIST,
        _MERGE_ONE_TEST_PER_BEHAVIOR,
        _MERGE_CRITERION,
    ),
    "R1.8 the header's Consolidation: line holds the user's choice, low unless the user says otherwise": (
        _MERGE_HEADER_LINE,
        _MERGE_USER,
        _MERGE_LOW,
    ),
    "R1.8 with low and medium, medium lines that are cases of one rule merge too, at most three per task": (
        _MERGE_LOW_AND_MEDIUM,
        _MERGE_MEDIUM,
        _MERGE_ONE_RULE,
        _MERGE_THREE,
    ),
    "R1.8 with none, one task per line": (_MERGE_NONE, _MERGE_ONE_TASK_PER_LINE),
    "R1.7 the totals go on the header's Consolidation: line": (_MERGE_HEADER_LINE, _MERGE_BEHAVIORS_IN_TASKS),
    "R1.9 tasks a plan change adds to a plan that is being built are consolidated the same way, and no task is"
    " renumbered": (_MERGE_PLAN_CHANGE, _MERGE, _MERGE_SAME_WAY, _MERGE_RENUMBERED),
    "R1.9 a plan without the Consolidation: line reads as low for the tasks a plan change adds": (
        _MERGE_WITHOUT_THAT_LINE,
        _MERGE_READS_AS_LOW,
    ),
    "R1.8 a medium line merges only with other medium lines, when the header says low and medium": (
        _MERGE_ONLY_WITH_MEDIUM,
        _MERGE_LOW_AND_MEDIUM,
    ),
    "R1.5 a chore merged into a behavior task has its step on the Files: line": (_MERGE_CHORE, _MERGE_FILES_LINE),
    "R3.9 a medium or high task's invariants name the property task that covers them": (
        _MERGE_INVARIANTS,
        _MERGE_COVERING_PROPERTY_TASK,
    ),
}
_MERGE_SELF_REVIEW_RULES: dict[str, tuple[re.Pattern[str], ...]] = {
    "R1.6 every consolidated task meets the conditions of the consolidation step": (
        _MERGE_CONSOLIDATED_TASK,
        _MERGE_CONDITIONS,
    ),
    "R1.6 every behavior of a consolidated task has its own test": (
        _MERGE_BEHAVIOR,
        _MERGE_CONSOLIDATED_TASK,
        _MERGE_OWN_TEST,
    ),
    "R1.8 with low and medium in the header, a task of medium lines meets that paragraph's conditions": (
        _MERGE_LOW_AND_MEDIUM,
        _MERGE_MEDIUM_LINES,
        _MERGE_CONDITIONS,
    ),
}
_MERGE_APPROVAL_RULES: dict[str, tuple[re.Pattern[str], ...]] = {
    "R1.7 the number of behaviors of each consolidated task": (_MERGE_NUMBER_OF_BEHAVIORS, _MERGE_CONSOLIDATED_TASK),
    "R1.7 the plan's totals of behaviors and tasks": (_MERGE_TOTALS, _MERGE_BEHAVIOR, _MERGE_TASKS),
    "R1.7 why the other tasks stayed apart": (_MERGE_WHY, _MERGE_STAYED_APART),
    "R1.8 the user may change the Consolidation: line": (_MERGE_USER, _MERGE_CHANGE, _MERGE_HEADER_LINE),
    "R1.8 when the user changes it, the plan is merged again and shown again": (_MERGE_AGAIN, _MERGE_SHOWN_AGAIN),
}


def _merge_rule_gaps(where: str, blocks: list[str], rules: dict[str, tuple[re.Pattern[str], ...]]) -> list[str]:
    """Return one message per rule whose patterns share no sentence of the blocks."""
    return [
        f"{where} does not say: {rule}"
        for rule, patterns in rules.items()
        if not any(_in_one_sentence(block, *patterns) for block in blocks)
    ]


def _merge_skill_gaps(skill_text: str) -> list[str]:
    """Return the consolidation rules (R1.1-R1.7) a writing-plans SKILL.md text lacks, one message per rule."""
    lines = skill_text.splitlines()
    review_lines, without_review = _split_self_review(lines)
    approval_lines, body_lines = _split_approval(without_review)
    body = _split_blocks(body_lines)
    gaps = _merge_rule_gaps("writing-plans", body, _MERGE_RULES)
    gaps += _merge_rule_gaps("writing-plans Self-review", _split_blocks(review_lines), _MERGE_SELF_REVIEW_RULES)
    gaps += _merge_rule_gaps("writing-plans Approval", _split_blocks(approval_lines), _MERGE_APPROVAL_RULES)
    gaps += [
        f"writing-plans still makes every task one behavior, one test, one commit: {block!r}"
        for block in _split_blocks(lines)
        if _MERGE_OLD_RULE.search(block)
    ]
    return gaps


def _template_tests_lists(template_text: str) -> dict[str, int]:
    """Return, by task ID, how many tests each template task lists under a `- Tests:` line.

    The tests are the `- ` items indented deeper than that line. HTML comments are dropped first, as `read_tasks`
    drops them, so only a real task's list counts.
    """
    counts: dict[str, int] = {}
    task_id = None
    list_indent = None
    for line in _HTML_COMMENT.sub("", template_text).splitlines():
        indent = len(line) - len(line.lstrip())
        if list_indent is not None and line.strip() and indent > list_indent and task_id is not None:
            counts[task_id] += 1 if line.lstrip().startswith("- ") else 0
            continue
        list_indent = None
        match = _TEMPLATE_TASK_LINE.match(line)
        if match or line.startswith("#"):
            task_id = match.group("id") if match else None
        elif task_id is not None and indent and line.strip() == "- Tests:":
            counts[task_id] = 0
            list_indent = indent
    return counts


def _merge_template_gaps(template_text: str, parsed_tasks: dict[str, Any]) -> list[str]:
    """Return what the tasks.md template lacks for R1.4 and R1.8: a consolidated task that still parses, its
    comment, and the header's `- **Consolidation:** low` line.

    Args:
        template_text: The template's text.
        parsed_tasks: The template's tasks as `read_tasks` returns them, by task ID.
    """
    consolidated = [task for task, tests in _template_tests_lists(template_text).items() if tests >= 2]
    if not consolidated:
        return ["no task lists two or more tests under a `- Tests:` line"]
    gaps = [] if _MERGE_TEMPLATE_HEADER.search(template_text) else ["no `- **Consolidation:** low` header line"]
    gaps += [
        f"{task}, which lists several tests, does not parse as a `Risk: low` task with two or more Covers IDs, a"
        " slice and a partition"
        for task in consolidated
        if task not in parsed_tasks
        or parsed_tasks[task].risk != "low"
        or len(parsed_tasks[task].covers) < 2
        or None in (parsed_tasks[task].slice, parsed_tasks[task].partition)
    ]
    comments = " ".join(" ".join(_HTML_COMMENT.findall(template_text)).replace("`", "").lower().split())
    if not all(p.search(comments) for p in (_MERGE_FIVE, _MERGE_LOW_RISK, _MERGE_BEHAVIOR, _MERGE_TESTS_FIELD)):
        gaps.append(
            "no comment says a task holds one behavior, or up to five related low-risk behaviors with their tests"
            " under `Tests:`"
        )
    return gaps


class WritingPlansConsolidationTest(unittest.TestCase):
    maxDiff = None  # a failure lists every gap, not the first one

    def test_writing_plans_consolidates_related_low_risk_tasks(self) -> None:
        """R1.1, R1.2, R1.3, R1.4, R1.5, R1.6, R1.7, R1.8, R1.9: 004 writing-plans merges related low-risk behaviors.

        Outside its Self-review and Approval steps, writing-plans says, each part in one sentence: every behavior is
        first listed on its own line; the lines that belong together merge into one consolidated task, built in a
        single cycle, even when they are not next to each other and unless a dependency forbids it; every merged line
        is low risk and a medium or high line is never merged; they have one owner (one row of the design's ownership
        table, or the same rule applied to several owners) with one verify command, form one logical change under one
        title, and stay within five behaviors and about 300 changed lines, never more than the pull request budget; a
        property line, one that needs a `- Decision:` field and one that adds a dependency are never merged; chore
        lines merge with each other when one title states them, or into the low-risk task they prepare; a doubt keeps
        the
        lines apart; a consolidated task is one task (one ID, every criterion in `Covers`) whose `Tests:` list holds
        one test per behavior with its criterion; the header's `Consolidation:` line holds the user's choice (`low`
        unless the user says otherwise; `low and medium` also merges medium lines that are cases of one rule, at most
        three per task; `none` writes one task per line) and the totals; and the tasks a plan change adds to a plan
        that is already being built are consolidated the same way, with no task renumbered. Its Self-review checks
        that every consolidated task meets those conditions and that each behavior has its own test; its Approval
        shows the number of behaviors of each consolidated task, the plan's totals, why the other tasks stayed apart,
        and that the user may change the `Consolidation:` line, after which the plan is merged again and shown again.
        No block still makes every task "one behavior, one test, one commit".
        The tasks.md template has a `- **Consolidation:** low` header line, a task that lists two or more tests under
        `- Tests:` and parses as a `Risk: low` task with two or more Covers IDs, a slice and a partition, and a
        comment saying a task holds one behavior or up to five related low-risk behaviors.
        """
        template_text = _WRITING_PLANS_TEMPLATE.read_text(encoding="utf-8")
        parsed_tasks = _read_template_tasks(_WRITING_PLANS_TEMPLATE)

        gaps = _merge_skill_gaps(_WRITING_PLANS.read_text(encoding="utf-8"))
        gaps += [f"templates/tasks.md: {gap}" for gap in _merge_template_gaps(template_text, parsed_tasks)]

        self.assertEqual(gaps, [], "\n".join(gaps))


# Feature 004 (right-sized flow) outside the orchestrating skills: the principle every role reads in the Standards and
# the note where the impact report is read (004 R1.2, R1.3, R1.8, R2.2, R3.1, R3.2, R4.3, R5.4). Keywords of each rule
# inside one sentence of its section, on blocks from _section_blocks (lowercased, without backticks, single-spaced).
_SIZED_STANDARDS = SKILLS_DIR / "engineering-standards" / "SKILL.md"
_SIZED_REVIEW = re.compile(r"\breviews?\b")
_SIZED_AGAIN = re.compile(r"\bagain\b")
_SIZED_ONLY = re.compile(r"\bonly\b")
_SIZED_CONCERNS = re.compile(r"\bconcerns?\b")
_SIZED_SECTION_NAME = re.compile(r"\breviews after a change\b")
_SIZED_NAMES_A_REVIEW_AGAIN = re.compile(
    r"\b(?:spec|code) review\b.*\b(?:again|repeat\w*)\b|\b(?:again|repeat\w*)\b.*\b(?:spec|code) review\b"
)
_SIZED_BEHAVIOR = re.compile(r"\bbehaviou?rs?\b")
_SIZED_CHARACTERIZATION = re.compile(r"\bcharacterization\b")
_SIZED_NO_BEHAVIOR = re.compile(r"\bno behaviou?r\b")
_SIZED_NO_NEW_TEST = re.compile(r"\bno new tests?\b")
_SIZED_HIGH = re.compile(r"\bhigh\b")
_SIZED_EVERY_REVIEW = re.compile(r"\b(?:every|all|each)\b(?: \S+){0,2} reviews?\b")
_SIZED_LOW_RISK = re.compile(r"\blow[- ]risk\b")
_SIZED_ONE_TASK = re.compile(r"\b(?:one|the same|a single) task\b")
_SIZED_MEDIUM = re.compile(r"\bmedium\b")
_SIZED_LOW_AND_MEDIUM = re.compile(r"\blow and medium\b")
_SIZED_ALWAYS = re.compile(r"\balways\b")
_SIZED_ONE_BEHAVIOR = re.compile(r"\b(?:one|a single) behaviou?r\b")
_SIZED_VERSION = re.compile(r"(?<![\d.])0\.9\.0(?![\d.])")
_SIZED_ROUNDS = re.compile(r"\brounds?\b")
_SIZED_COMPARE = re.compile(r"\bcompar\w*|\blower\b|\bfewer\b")
_SIZED_ADJUSTMENT = re.compile(r"\badjustments?\b")
_SIZED_FIXES_PER_FEATURE = re.compile(r"\bfixes per feature\b")
# (section of engineering-standards/SKILL.md, the rule, the patterns one of its sentences must all match).
_SIZED_STANDARDS_RULES: tuple[tuple[str, str, tuple[re.Pattern[str], ...]], ...] = (
    (
        "2. Definition of Done",
        "R2.2 a behavior that already existed has its characterization test",
        (_SIZED_BEHAVIOR, _SIZED_CHARACTERIZATION),
    ),
    (
        "2. Definition of Done",
        "R4.3 a change that adds or changes no behavior needs no new test",
        (_SIZED_NO_BEHAVIOR, _SIZED_NO_NEW_TEST),
    ),
    (
        "7. Review severity",
        "R3.1 a change made after a review passed goes again only through the reviews it concerns, as"
        " develop-feature's Reviews after a change says",
        (_SIZED_AGAIN, _SIZED_ONLY, _SIZED_REVIEW, _SIZED_CONCERNS, _SIZED_SECTION_NAME),
    ),
    (
        "7. Review severity",
        "R3.2 high-risk work repeats every review after any change",
        (_SIZED_HIGH, _SIZED_EVERY_REVIEW),
    ),
    (
        "10. Verification by risk",
        "R1.2 related low-risk behaviors may share one task",
        (_SIZED_LOW_RISK, _SIZED_BEHAVIOR, _SIZED_ONE_TASK),
    ),
    (
        "10. Verification by risk",
        "R1.8 a medium task holds one behavior unless the plan says low and medium",
        (_SIZED_MEDIUM, _SIZED_ONE_BEHAVIOR, _SIZED_LOW_AND_MEDIUM),
    ),
    (
        "10. Verification by risk",
        "R1.3 a high task always holds one behavior",
        (_SIZED_HIGH, _SIZED_ALWAYS, _SIZED_ONE_BEHAVIOR),
    ),
)
# What one block of measure-impact's limits must say about features built from 0.9.0 on.
_SIZED_IMPACT_LIMIT = (
    _SIZED_VERSION,
    _SIZED_BEHAVIOR,
    _SIZED_ROUNDS,
    _SIZED_COMPARE,
    _SIZED_ADJUSTMENT,
    _SIZED_FIXES_PER_FEATURE,
)


class RightSizedFlowPrincipleTest(unittest.TestCase):
    maxDiff = None  # a failure lists every gap, not the first one

    def test_standards_state_what_is_merged_and_which_reviews_run_again(self) -> None:
        """R1.2, R1.3, R1.8, R2.2, R3.1, R3.2, R4.3: 004 the Standards state the principle every role reads.

        `## 2. Definition of Done` says a behavior that already existed has its characterization test and a change
        that adds or changes no behavior needs no new test. `## 7. Review severity` says, in one sentence each, that
        a change made after a review passed goes again only through the reviews it concerns, as develop-feature's
        Reviews after a change says, and that high-risk work repeats every review; it does not restate which review
        each kind of change goes to, so the table has one owner. `## 10. Verification by risk` says that related
        low-risk behaviors may share one task, that a medium task holds one behavior unless the plan says
        `low and medium`, and that a high task always holds one behavior.
        """
        gaps = [
            f"engineering-standards ## {section} does not say: {rule}"
            for section, rule, patterns in _SIZED_STANDARDS_RULES
            if not any(_in_one_sentence(block, *patterns) for block in _section_blocks(_SIZED_STANDARDS, section))
        ]
        gaps += [
            f"engineering-standards ## 7. Review severity restates the table of Reviews after a change: {sentence}"
            for block in _section_blocks(_SIZED_STANDARDS, "7. Review severity")
            for sentence in _sentences(block)
            if _SIZED_NAMES_A_REVIEW_AGAIN.search(sentence)
        ]

        self.assertEqual(gaps, [], "\n".join(gaps))

    def test_measure_impact_says_task_counts_changed_meaning(self) -> None:
        """R5.4: 004 measure-impact says its per-task numbers are not comparable across the 0.9.0 change.

        A block of `## Limits to state when relevant` names 0.9.0, says a task may hold several behaviors, says tasks
        done or review rounds per task run lower than, or are not to be compared with, earlier features, and says an
        adjustment is a commit of its own, so fixes per feature read differently.
        """
        limits = _section_blocks(_MEASURE_IMPACT, "Limits to state when relevant")

        stated = any(all(pattern.search(block) for pattern in _SIZED_IMPACT_LIMIT) for block in limits)

        self.assertTrue(
            stated,
            "measure-impact ## Limits to state when relevant: no block says that from 0.9.0 a task may hold several"
            " behaviors and an adjustment is a commit of its own, so tasks done, review rounds per task and fixes per"
            " feature are not comparable with earlier features",
        )


if __name__ == "__main__":
    unittest.main()
