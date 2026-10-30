"""Contract tests for what a release of the plugin ships beyond its skills and agents: evals, version and changelog."""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from .plugin_files import PLUGIN_ROOT, read_frontmatter, read_section

EVALS_DIR = PLUGIN_ROOT / "evals"

# One behavior eval per new mechanism the user meets (R10.3): the slice checkpoint with its questions, the design
# decision, the slice summary, the feature summary and the improvement notes.
_NEW_MECHANISM_EVALS = (
    "behavior-slice-checkpoint",
    "behavior-design-decision",
    "behavior-slice-summary",
    "behavior-feature-summary",
    "behavior-improvement-notes",
)

# The grader types `claude plugin eval` documents (https://code.claude.com/docs/en/plugin-evals.md).
_GRADER_TYPES = frozenset({"llm", "tool_used", "file_exists", "regex", "tool_order", "baseline"})


def _prompt_gaps(path: Path) -> list[str]:
    """Return what the eval case's `prompt.md` at `path` lacks (the file, its frontmatter, a prompt), or []."""
    if not path.is_file():
        return [f"{path}: the case has no prompt.md"]
    try:
        read_frontmatter(path)
    except ValueError as error:
        return [str(error)]
    lines = path.read_text(encoding="utf-8").splitlines()
    closing_fence = [index for index, line in enumerate(lines) if line == "---"][1]
    if not "\n".join(lines[closing_fence + 1 :]).strip():
        return [f"{path}: no prompt text after the frontmatter"]
    return []


def _grader_gaps(graders_dir: Path) -> list[str]:
    """Return what the eval case's graders in `graders_dir` lack, or [] when each sets a known `type:`.

    The case needs at least one `graders/*.md`, and each one needs a frontmatter whose `type:` is a documented grader
    type.
    """
    graders = sorted(graders_dir.glob("*.md")) if graders_dir.is_dir() else []
    if not graders:
        return [f"{graders_dir}: the case has no graders/*.md"]
    gaps = []
    for grader in graders:
        try:
            grader_type = read_frontmatter(grader).get("type", "")
        except ValueError as error:
            gaps.append(str(error))
            continue
        if grader_type not in _GRADER_TYPES:
            gaps.append(f"{grader}: frontmatter 'type: {grader_type}' is not one of {sorted(_GRADER_TYPES)}")
    return gaps


def _eval_case_gaps(case_dir: Path) -> list[str]:
    """Return what the behavior eval case at `case_dir` lacks, or [] when it has a prompt and typed graders."""
    if not case_dir.is_dir():
        return [f"{case_dir}: the eval case does not exist"]
    return _prompt_gaps(case_dir / "prompt.md") + _grader_gaps(case_dir / "graders")


class BehaviorEvalsTest(unittest.TestCase):
    maxDiff = None

    def test_each_new_mechanism_has_a_behavior_eval(self) -> None:
        """R10.3: every new mechanism the user meets has a behavior eval that `claude plugin eval` can run.

        Each of `behavior-slice-checkpoint`, `behavior-design-decision`, `behavior-slice-summary`,
        `behavior-feature-summary` and `behavior-improvement-notes` under `evals/` has a `prompt.md` with a frontmatter
        and a prompt after it, and at least one `graders/*.md` whose frontmatter sets a documented `type:`. The evals
        run a model, so the check only verifies their structure.
        """
        gaps = [gap for name in _NEW_MECHANISM_EVALS for gap in _eval_case_gaps(EVALS_DIR / name)]

        self.assertEqual(gaps, [])


_CHANGELOG_PATH = PLUGIN_ROOT / "CHANGELOG.md"
_CHANGELOG_MANIFEST_PATH = PLUGIN_ROOT / ".claude-plugin" / "plugin.json"
# This feature (guided slice delivery) ships as 0.6.0 (requirements.md, Constraints).
_CHANGELOG_FEATURE_VERSION = (0, 6, 0)
# Released entries only: `## [Unreleased]` has no digits, so it never matches.
_CHANGELOG_RELEASE_HEADING = re.compile(r"^## (\[(\d+)\.(\d+)\.(\d+)\].*)$")
_CHANGELOG_MECHANISMS = (
    ("model and effort per role", re.compile(r"\bmodel and effort (?:per|for each|for every) role\b")),
    ("the rethinker", re.compile(r"\brethinker\b")),
    ("parallel partitions", re.compile(r"\bpartitions?\b")),
    ("slice pauses", re.compile(r"\bslice checkpoints?\b|\bpauses? (?:after|at the end of) (?:each|every) slice\b")),
    ("slice summaries", re.compile(r"\bslice summar(?:y|ies)\b")),
    ("the feature summary", re.compile(r"\bfeature summar(?:y|ies)\b")),
    ("improvement notes", re.compile(r"\bimprovement notes?\b")),
)


def _changelog_released_entries() -> list[tuple[tuple[int, int, int], str]]:
    """Return `(version, heading)` for each released CHANGELOG entry, newest first.

    `heading` is the heading line without its leading `## `, ready for `read_section`.
    """
    entries = []
    for line in _CHANGELOG_PATH.read_text(encoding="utf-8").splitlines():
        match = _CHANGELOG_RELEASE_HEADING.match(line)
        if match:
            version = (int(match.group(2)), int(match.group(3)), int(match.group(4)))
            entries.append((version, match.group(1)))
    return entries


def _changelog_mechanism_gaps(entries: list[tuple[tuple[int, int, int], str]]) -> list[str]:
    """Return one gap per new mechanism the 0.6.0 entry does not name, or one gap when that entry is missing."""
    heading = next((heading for version, heading in entries if version == _CHANGELOG_FEATURE_VERSION), None)
    if heading is None:
        return ["CHANGELOG.md: there is no [0.6.0] entry"]
    text = read_section(_CHANGELOG_PATH, heading).lower().replace("`", "")
    text = re.sub(r"\s+", " ", text)
    return [
        f"CHANGELOG.md [0.6.0]: the entry does not name {label}"
        for label, pattern in _CHANGELOG_MECHANISMS
        if not pattern.search(text)
    ]


class VersionAndChangelogTest(unittest.TestCase):
    maxDiff = None

    def test_version_and_changelog_agree(self) -> None:
        """R10.1: plugin.json's version is the first CHANGELOG release, 0.6.0 or later; 0.6.0 names each mechanism.

        The first released entry is the first `## [<x.y.z>]` heading, so a `## [Unreleased]` heading is skipped. The
        0.6.0 entry is looked up by its version, not by position, so the check stays true after later releases put
        newer entries above it. It must name model and effort per role, the rethinker, parallel partitions, slice
        pauses, slice summaries, the feature summary and improvement notes.
        """
        manifest_version = json.loads(_CHANGELOG_MANIFEST_PATH.read_text(encoding="utf-8"))["version"]
        entries = _changelog_released_entries()

        gaps = []
        if not entries:
            gaps.append("CHANGELOG.md: there is no released `## [<x.y.z>]` entry")
        else:
            first_version, first_heading = entries[0]
            first_text = ".".join(str(part) for part in first_version)
            if manifest_version != first_text:
                gaps.append(f"plugin.json version {manifest_version} is not the first CHANGELOG entry {first_heading}")
            if first_version < _CHANGELOG_FEATURE_VERSION:
                gaps.append(f"CHANGELOG.md: the first released entry {first_heading} is older than 0.6.0")
        gaps += _changelog_mechanism_gaps(entries)

        self.assertEqual(gaps, [])


if __name__ == "__main__":
    unittest.main()
