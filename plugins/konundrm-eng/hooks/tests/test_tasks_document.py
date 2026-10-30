"""Unit tests for hooks/scripts/tasks_document.py."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from tasks_document import Task, read_tasks

TEMPLATE = Path(__file__).resolve().parents[2] / "skills" / "writing-plans" / "templates" / "tasks.md"

TASKS = """# Tasks: Coupons

- **Spec:** [requirements.md](requirements.md) · **Design:** [design.md](design.md)
- **Status:** Approved
- **Base commit:** `abc123`

## Slice S1: apply a coupon · Budget: ~400 changed lines

- [x] **T1** Applies a 10 % coupon · `behavior` · Risk: low · Covers: R1.1
  - Test: `tests/test_coupons.py::test_applies_percentage`
  - Rounds: spec 2 · code 1 · escalations 0

- [ ] **T2** Total is never negative for any coupon · `property` · Risk: high · Covers: R1.2

## Slice S2: expiry

- [ ] **T3** Rejects expired coupons · `behavior` · Risk: Medium · Covers: R2.1

<!-- Example:
- [x] **T9** done · Risk: low
  - Rounds: spec 9 · code 9 · escalations 9
-->
"""


class ReadTasksTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = Path(self._tmp.name) / "tasks.md"

    def read(self, text: str) -> tuple[str, tuple[Task, ...]]:
        self.path.write_text(text, encoding="utf-8")
        document = read_tasks(self.path)
        return document.status, document.tasks

    def test_reads_status_tasks_risks_slices_and_rounds(self) -> None:
        status, tasks = self.read(TASKS)
        self.assertEqual(status, "Approved")
        self.assertEqual(
            tasks,
            (
                Task("T1", "Applies a 10 % coupon", True, "low", "S1", (2, 1, 0)),
                Task("T2", "Total is never negative for any coupon", False, "high", "S1", None),
                Task("T3", "Rejects expired coupons", False, "medium", "S2", None),
            ),
        )

    def test_ignores_the_commented_example(self) -> None:
        _, tasks = self.read(TASKS)
        self.assertNotIn("T9", [task.id for task in tasks])

    def test_tasks_without_slices_or_risk_still_parse(self) -> None:
        status, tasks = self.read("- **Status:** Draft\n\n- [ ] **T1** Something\n")
        self.assertEqual(status, "Draft")
        self.assertEqual(tasks, (Task("T1", "Something", False, None, None, None),))

    def test_a_missing_file_is_an_empty_document(self) -> None:
        document = read_tasks(Path(self._tmp.name) / "missing.md")
        self.assertEqual((document.status, document.tasks), ("", ()))

    def test_the_writing_plans_template_parses(self) -> None:
        document = read_tasks(TEMPLATE)
        self.assertEqual(document.status, "Draft")
        self.assertTrue(document.tasks)
        self.assertTrue(all(task.risk in ("low", "medium", "high") for task in document.tasks))
        self.assertTrue(all(task.slice is not None for task in document.tasks))

    def test_reads_the_partition_of_each_task(self) -> None:
        # R3.1: each task takes the partition of the first row that lists it; unlisted is None.
        _, tasks = self.read(
            "- **Status:** Approved\n\n"
            "## Slice S1: apply\n\n"
            "- [ ] **T1** First\n"
            "- [ ] **T2** Second\n"
            "- [ ] **T3** Third\n\n"
            "### Partitions\n\n"
            "| Wave | Partition | Tasks | Depends on |\n"
            "| --- | --- | --- | --- |\n"
            "| 1 | P1 | T1, T2 | — |\n"
            "| 2 | P2 | T3, T1 | P1 |\n\n"
            "## Slice S2: expiry\n\n"
            "- [ ] **T4** Fourth\n"
            "- [ ] **T5** Fifth\n\n"
            "### Partitions\n\n"
            "| Wave | Partition | Tasks | Depends on |\n"
            "| --- | --- | --- | --- |\n"
            "| 1 | P3 | T4 | — |\n"
        )
        self.assertEqual(
            {task.id: task.partition for task in tasks},
            {"T1": "P1", "T2": "P1", "T3": "P2", "T4": "P3", "T5": None},
        )

    def test_expands_task_ranges_and_reads_bold_cells(self) -> None:
        # R3.8: an en-dash range Ta-Tb assigns every task from a to b; bold cells read like plain ones.
        task_lines = "".join(f"- [ ] **T{number}** Task {number}\n" for number in range(1, 10))
        _, tasks = self.read(
            "- **Status:** Approved\n\n"
            "## Slice S1: apply\n\n"
            f"{task_lines}\n"
            "### Partitions\n\n"
            "| Wave | Partition | Tasks | Depends on |\n"
            "| --- | --- | --- | --- |\n"
            "| 1 | P1 | T1\u2013T3, T6 | — |\n"
            "| 2 | **P2** | **T4\u2013T5** | P1 |\n"
            "| 3 | P3 | T7..T8 | P1 |\n"
        )
        self.assertEqual(
            {task.id: task.partition for task in tasks},
            {
                "T1": "P1",
                "T2": "P1",
                "T3": "P1",
                "T4": "P2",
                "T5": "P2",
                "T6": "P1",
                "T7": "P3",
                "T8": "P3",
                "T9": None,
            },
        )


if __name__ == "__main__":
    unittest.main()
