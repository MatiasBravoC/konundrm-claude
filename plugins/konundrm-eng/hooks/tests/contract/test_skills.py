"""Contract tests for the plugin's skill definitions in skills/*/SKILL.md."""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
import unittest
from collections.abc import Callable
from pathlib import Path

from .plugin_files import SKILLS_DIR, read_frontmatter
from .test_flows import _split_blocks

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


if __name__ == "__main__":
    unittest.main()
