"""Unit tests for hooks/scripts/audit_subagent_changes.py."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from audit_subagent_changes import Violation, find_violations, restore_instructions


class FindViolationsTest(unittest.TestCase):
    def test_flags_test_changes_made_by_the_implementer(self) -> None:
        violations = find_violations("implementer", [("M", "src/a.py"), ("M", "tests/test_a.py")])
        self.assertEqual([(v.status, v.path) for v in violations], [("M", "tests/test_a.py")])

    def test_flags_production_changes_made_by_the_test_writer(self) -> None:
        violations = find_violations("test-writer", [("A", "tests/test_b.py"), ("A", "src/b.py")])
        self.assertEqual([v.path for v in violations], ["src/b.py"])

    def test_flags_any_change_made_by_a_reviewer(self) -> None:
        self.assertEqual(len(find_violations("code-reviewer", [("D", "src/a.py"), ("M", "tests/t.py")])), 2)

    def test_ignores_tool_artifacts_such_as_coverage_files(self) -> None:
        changes = [("A", ".coverage"), ("M", "src/pkg/__pycache__/a.pyc"), ("A", "coverage/lcov.info")]
        self.assertEqual(find_violations("spec-reviewer", changes), [])


class RestoreInstructionsTest(unittest.TestCase):
    def test_lists_each_file_with_the_command_that_restores_it(self) -> None:
        message = restore_instructions(
            "implementer",
            "abc123",
            [Violation("M", "tests/test_a.py", "not yours"), Violation("A", "tests/test_new.py", "not yours")],
        )
        self.assertIn("tests/test_a.py (modified): not yours", message)
        self.assertIn('git restore --source=abc123 --worktree -- "tests/test_a.py"', message)
        self.assertIn('rm -- "tests/test_new.py"', message)


if __name__ == "__main__":
    unittest.main()
