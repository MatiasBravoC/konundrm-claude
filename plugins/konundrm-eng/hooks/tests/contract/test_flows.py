"""Contract tests for the flows the orchestrating skills describe (skills/*/SKILL.md and their references)."""

from __future__ import annotations

import re
import unittest

from .plugin_files import SKILLS_DIR, read_section

DEVELOP_FEATURE_DIR = SKILLS_DIR / "develop-feature"


def _says_opus_high(row: str) -> bool:
    """Return whether a table row has a cell that is exactly `opus` and another that is exactly `high`."""
    cells = {cell.strip().strip("`").strip() for cell in row.strip("|").split("|")}
    return {"opus", "high"} <= cells


class DevelopFeatureFlowTest(unittest.TestCase):
    def test_develop_feature_overrides_model_and_effort_where_agreed(self) -> None:
        """R1.2, R1.3, R1.4: develop-feature runs fix rounds, high-risk tasks and the whole-feature spec review
        in opus/high, and every other dispatch omits the Agent tool's model and effort."""
        section = read_section(DEVELOP_FEATURE_DIR / "SKILL.md", "Model and effort")
        rows = [line.strip().lower() for line in section.splitlines() if line.strip().startswith("|")]
        rows = [row for row in rows if not re.fullmatch(r"[|\s:-]+", row)]
        expected_rows = {
            "R1.2 fix round of the test-writer or implementer": lambda row: (
                "fix round" in row and "test-writer" in row and "implementer" in row
            ),
            "R1.3 test-writer, implementer and spec-reviewer of a high task": lambda row: (
                "fix round" not in row
                and "whole feature" not in row
                and re.search(r"`?high`?[- ]risk|risk[^|]*`?high`?|`high` task|high task", row) is not None
                and all(agent in row for agent in ("test-writer", "implementer", "spec-reviewer"))
            ),
            "R1.4 spec-reviewer over the whole feature": lambda row: "whole feature" in row and "spec-reviewer" in row,
        }

        missing = []
        if not section:
            missing.append("SKILL.md has no '## Model and effort' section")
        for label, matches in expected_rows.items():
            matching = [row for row in rows if matches(row)]
            if not matching:
                missing.append(f"no table row for {label}")
            elif not any(_says_opus_high(row) for row in matching):
                missing.append(f"the row for {label} does not say opus and high")
        lowered = section.lower()
        if not ("omit" in lowered and "model" in lowered and "effort" in lowered and "frontmatter" in lowered):
            missing.append("the section does not say every other dispatch omits model and effort (frontmatter applies)")
        dispatch_prompts = (DEVELOP_FEATURE_DIR / "reference" / "dispatch-prompts.md").read_text(encoding="utf-8")
        if "Model and effort" not in dispatch_prompts:
            missing.append("reference/dispatch-prompts.md does not refer to 'Model and effort'")

        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
