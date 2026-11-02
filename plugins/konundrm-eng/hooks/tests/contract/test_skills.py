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

from .plugin_files import PLUGIN_ROOT, SKILLS_DIR, read_frontmatter, read_section
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


# R2.5: every pull request description lists its commits in order, each with the task ID from its `Task:` line.
_DELIVERY_PULL_REQUEST_TEMPLATE = SKILLS_DIR / "setup-project" / "templates" / "pull_request_template.md"
_DELIVERY_COMMITS_HEADING = "Commits, one per task"
_DELIVERY_FENCE = re.compile(r"\s*(?:```|~~~)")
_DELIVERY_COMMIT = re.compile(r"\bcommits?\b")
_DELIVERY_IN_ORDER = re.compile(
    r"\boldest first\b|--reverse\b|\bchronologic\w*\b|\bin (?:commit |their |the same |the )?order\b"
    r"|\bin the order (?:they were|of) \w+"
)
_DELIVERY_INVERTED_ORDER = re.compile(
    r"\b(?:newest|latest|most recent|last) (?:commit )?first\b|\breverse(?:d)? (?:chronological )?order\b"
    r"|\bany order\b|\bunordered\b"
)
_DELIVERY_TASK_ID = re.compile(r"\btask ids?\b|\bt<n>|\bt\d+\b")
_DELIVERY_PARTIAL = re.compile(r"\b(?:only|solely|some|high[- ]risk)\b")
_DELIVERY_TASK_LINE = re.compile(r"\btask:(?: \S+){0,6}? (?:lines?|trailers?)\b")
_DELIVERY_READ_FROM = re.compile(r"\b(?:from|reads?|reading|tak\w*|comes?|pull\w*|extract\w*|parse\w*)\b")
# A sentence about the commit listing: its heading, "commits section", "commit list", "list of commits", or a listing
# verb a few words before "commit(s)" ("do not list the commits", "include every commit").
_DELIVERY_COMMIT_LISTING = re.compile(
    rf"\b{re.escape(_DELIVERY_COMMITS_HEADING.lower())}\b"
    r"|\bcommits?(?:['\u2019]s?)? (?:section|list|listing|table|entries)\b"
    r"|\blists? of(?: \S+){0,2}? commits?\b"
    r"|\b(?:list|show|includ|enumerat|add|print|writ|giv|mention|keep)\w*\b(?: \S+){0,3}? commits?\b"
)
# Ways to leave the listing out that _DELIVERY_NEGATION does not read as negations.
_DELIVERY_SKIPS_SECTION = re.compile(
    r"\b(?:skip\w*|omit\w*|drop\w*|remov\w*|delet\w*|exclud\w*|strip\w*|forgo\w*|hid(?:e|es|ing|den)|cut)\b"
    r"|\b(?:leav\w*|left)\b(?: \S+){0,6}? out\b"
)
_DELIVERY_GIT_LOG = re.compile(r"\bgit log\b")
# git log's only oldest-first option.
_DELIVERY_OLDEST_FIRST_OPTION = re.compile(r"(?<!\S)--reverse\b")


def _delivery_commits_section(path: Path) -> list[str]:
    """Return the blocks of the `## Commits, one per task` section of a file, stopping at a code fence (R2.5)."""
    lines = read_section(path, _DELIVERY_COMMITS_HEADING).splitlines()
    end = next((index for index, line in enumerate(lines) if _DELIVERY_FENCE.match(line)), len(lines))
    return _split_blocks(lines[:end])


def _delivery_commit_list_gaps(name: str, path: Path) -> list[str]:
    """Return what one description template's commits section lacks to list its commits in order with task IDs."""
    blocks = _delivery_commits_section(path)
    if not blocks:
        return [f"{name}: has no `## {_DELIVERY_COMMITS_HEADING}` section"]
    sentences = [sentence for block in blocks for sentence in _sentences(block)]
    gaps = []
    if not any(
        _DELIVERY_IN_ORDER.search(s) and not _DELIVERY_NEGATION.search(s) and not _DELIVERY_INVERTED_ORDER.search(s)
        for s in sentences
    ):
        gaps.append(f"{name}: the commits section never says the commits are listed in order, oldest first")
    gaps.extend(
        f"{name}: the commits section orders them otherwise: {s.strip()!r}"
        for s in sentences
        if _DELIVERY_INVERTED_ORDER.search(s)
    )
    if not any(
        _DELIVERY_COMMIT.search(s)
        and _DELIVERY_TASK_ID.search(s)
        and not _DELIVERY_NEGATION.search(s)
        and not _DELIVERY_PARTIAL.search(s)
        for s in sentences
    ):
        gaps.append(f"{name}: the commits section never lists every commit with its task ID")
    return gaps


def _delivery_task_line_gaps(blocks: list[str]) -> list[str]:
    """Return what opening-pull-requests lacks to take each commit's task ID from its `Task:` line (R2.5).

    Also returns every sentence that refers to the commit listing (`_DELIVERY_COMMIT_LISTING`) and negates it
    (`_DELIVERY_NEGATION`) or leaves it out (`_DELIVERY_SKIPS_SECTION`), whatever delivery it names, and the gaps of
    `_delivery_git_log_gaps`.
    """
    sentences = [sentence for block in blocks for sentence in _sentences(block)]
    gaps = []
    if not any(
        _DELIVERY_TASK_LINE.search(s)
        and _DELIVERY_COMMIT.search(s)
        and _DELIVERY_TASK_ID.search(s)
        and _DELIVERY_READ_FROM.search(s)
        and not _DELIVERY_NEGATION.search(s)
        for s in sentences
    ):
        gaps.append(
            "opening-pull-requests/SKILL.md: no sentence says each commit's task ID comes from its `Task:` line"
        )
    gaps.extend(
        f"opening-pull-requests/SKILL.md: drops or negates the commits section: {s.strip()!r}"
        for s in sentences
        if _DELIVERY_COMMIT_LISTING.search(s) and (_DELIVERY_NEGATION.search(s) or _DELIVERY_SKIPS_SECTION.search(s))
    )
    return gaps + _delivery_git_log_gaps(sentences)


def _delivery_git_log_gaps(sentences: list[str]) -> list[str]:
    """Return what the skill's `git log` command for the commit listing lacks to list them oldest first (R2.5).

    The command is a sentence naming both `git log` and the commit listing (`_DELIVERY_COMMIT_LISTING`); at least one
    must exist, and every one must pass `--reverse`, since git log lists newest first by default.
    """
    commands = [s for s in sentences if _DELIVERY_GIT_LOG.search(s) and _DELIVERY_COMMIT_LISTING.search(s)]
    if not commands:
        return ["opening-pull-requests/SKILL.md: no sentence gives the `git log` command that lists the commits"]
    return [
        f"opening-pull-requests/SKILL.md: lists the commits with `git log` without `--reverse`: {s.strip()!r}"
        for s in commands
        if not _DELIVERY_OLDEST_FIRST_OPTION.search(s)
    ]


class PullRequestTaskCommitsTest(unittest.TestCase):
    maxDiff = None

    def test_pull_requests_list_their_task_commits(self) -> None:
        """R2.5: each pull request description lists its commits in order, each with its task ID.

        Both opening-pull-requests/SKILL.md (the description sections in its step 4 fenced block) and setup-project's
        pull_request_template.md have a `## Commits, one per task` section. In each, one sentence, not negated and not
        inverted ("newest first", "reverse order", "any order"), lists the commits in order (oldest first, `git log
        --reverse`, chronological, "in order"); one sentence, not negated and not narrowed ("only", "some",
        "high-risk"), lists the commits with their task ID (`T<n>` or "task ID"). The skill also says, in one
        unnegated sentence, that each commit's task ID is read from its `Task:` line; gives the `git log` command for
        the listing with `--reverse`, so it comes out oldest first; and has no sentence that refers to the listing (its
        heading, "commits section", "commit list", "list of commits", "list the commits") while negating it or leaving
        it out ("skip", "omit", "drop", "leave … out", "not", "without"), for either delivery (stacked or single).
        """
        gaps = [
            *_delivery_commit_list_gaps("opening-pull-requests/SKILL.md", _DELIVERY_OPENING_PULL_REQUESTS),
            *_delivery_commit_list_gaps(
                "setup-project/templates/pull_request_template.md", _DELIVERY_PULL_REQUEST_TEMPLATE
            ),
            *_delivery_task_line_gaps(_blocks(_DELIVERY_OPENING_PULL_REQUESTS)),
        ]

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


if __name__ == "__main__":
    unittest.main()
