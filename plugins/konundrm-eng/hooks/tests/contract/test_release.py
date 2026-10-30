"""Contract tests for what a release of the plugin ships beyond its skills and agents: evals, version and changelog."""

from __future__ import annotations

import unittest
from pathlib import Path

from .plugin_files import PLUGIN_ROOT, read_frontmatter

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


if __name__ == "__main__":
    unittest.main()
