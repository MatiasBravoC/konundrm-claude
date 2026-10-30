"""Unit tests for hooks/scripts/tasks_document.py."""

from __future__ import annotations

import json
import random
import subprocess
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

RANGE_SEPARATORS = ("\u2013", "\u2014", "-", "..", "to")
TASK_COUNT = 60

# A Tasks-cell item: (first, last, is_single). A single ID uses only `first`.
Item = tuple[int, int, bool]


def _generate_rows(rng: random.Random) -> list[list[Item]]:
    """Up to five rows of up to four items over T1-T60; about half of the ranges run backwards."""
    return [
        [(rng.randint(1, TASK_COUNT), rng.randint(1, TASK_COUNT), rng.random() < 0.4) for _ in range(rng.randint(0, 4))]
        for _ in range(rng.randint(1, 5))
    ]


def _render_item(rng: random.Random, item: Item) -> str:
    """One Tasks-cell item as Markdown: an ID or a range with a random separator, spacing and bold."""
    first, last, is_single = item
    if is_single:
        text = f"T{first}"
    else:
        space = rng.choice(("", " "))
        text = f"T{first}{space}{rng.choice(RANGE_SEPARATORS)}{space}T{last}"
    return f"**{text}**" if rng.random() < 0.3 else text


def _render_partitions(rng: random.Random, rows: list[list[Item]]) -> str:
    """A Partitions table whose row i holds partition P<i>, with whole cells bold at random."""
    lines = ["| Wave | Partition | Tasks | Depends on |", "| --- | --- | --- | --- |"]
    for index, items in enumerate(rows, start=1):
        cell = ", ".join(_render_item(rng, item) for item in items) or "\u2014"
        if items and rng.random() < 0.3:
            cell = f"**{cell}**"
        partition = f"**P{index}**" if rng.random() < 0.3 else f"P{index}"
        lines.append(f"| {index} | {partition} | {cell} | \u2014 |")
    return "\n".join(lines) + "\n"


def _expected_partitions(rows: list[list[Item]]) -> dict[str, str | None]:
    """Reference model: the first row listing a task wins; a range a..b lists a to b, nothing if a > b."""
    expected: dict[str, str | None] = {f"T{number}": None for number in range(1, TASK_COUNT + 1)}
    for index, items in enumerate(rows, start=1):
        for first, last, is_single in items:
            listed = [first] if is_single else range(first, last + 1)
            for number in listed:
                if expected[f"T{number}"] is None:
                    expected[f"T{number}"] = f"P{index}"
    return expected


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
        # R2.1, R3.1, R4.5: the template groups every task into a slice and a partition, ships
        # serial (Parallel reads as no) and carries the Parallel and Checkpoints header lines.
        document = read_tasks(TEMPLATE)
        with TEMPLATE.open(encoding="utf-8") as template:  # universal newlines
            header_lines = [line.strip() for line in template]
        self.assertEqual(document.status, "Draft")
        self.assertTrue(document.tasks)
        self.assertTrue(all(task.risk in ("low", "medium", "high") for task in document.tasks))
        self.assertEqual([task.id for task in document.tasks if task.slice is None], [])
        self.assertEqual([task.id for task in document.tasks if task.partition is None], [])
        self.assertIs(document.parallel, False)
        self.assertTrue(any(line.startswith("- **Parallel:**") for line in header_lines))
        self.assertTrue(any(line.startswith("- **Checkpoints:**") for line in header_lines))

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

    def test_a_huge_task_range_does_not_hang_the_reader(self) -> None:
        # R3.8: a range as wide as T1-T10000000000 assigns only the document's tasks inside its bounds,
        # and is read in under 2 seconds. The read runs in a child process so a reader that enumerates
        # every number in the range is killed at the deadline instead of hanging the suite.
        self.path.write_text(
            "- **Status:** Approved\n\n"
            "## Slice S1: apply\n\n"
            "- [ ] **T1** First\n"
            "- [ ] **T2** Second\n"
            "- [ ] **T7** Seventh\n"
            "- [ ] **T10000000001** Past the range\n\n"
            "### Partitions\n\n"
            "| Wave | Partition | Tasks | Depends on |\n"
            "| --- | --- | --- | --- |\n"
            "| 1 | P1 | T1\u2013T10000000000 | — |\n"
            "| 2 | P2 | T10000000001 | P1 |\n",
            encoding="utf-8",
        )
        reader = (
            "import json, sys\n"
            "from pathlib import Path\n"
            "sys.path.insert(0, sys.argv[1])\n"
            "from tasks_document import read_tasks\n"
            "print(json.dumps({task.id: task.partition for task in read_tasks(Path(sys.argv[2])).tasks}))\n"
        )
        scripts = str(Path(__file__).resolve().parents[1] / "scripts")
        try:
            # subprocess.run kills the child when the timeout expires.
            completed = subprocess.run(
                [sys.executable, "-c", reader, scripts, str(self.path)],
                capture_output=True,
                text=True,
                timeout=2,
                check=True,
            )
        except subprocess.TimeoutExpired:
            self.fail("reading a partition row with T1\u2013T10000000000 took more than 2 seconds")
        self.assertEqual(
            json.loads(completed.stdout),
            {"T1": "P1", "T2": "P1", "T7": "P1", "T10000000001": "P2"},
        )

    def test_partitions_follow_the_first_row_and_ranges_cover_their_bounds(self) -> None:
        # R3.1, R3.8: over 300 seeded tables, the first row that lists a task wins, and a range
        # Ta<sep>Tb covers exactly a to b (nothing when a > b), whatever the separator or bolding.
        rng = random.Random(11)  # noqa: S311 - seeded for reproducible test data, not cryptography
        task_lines = "".join(f"- [ ] **T{number}** Task {number}\n" for number in range(1, TASK_COUNT + 1))
        for case in range(300):
            rows = _generate_rows(rng)
            table = _render_partitions(rng, rows)
            with self.subTest(case=case, table=table):
                _, tasks = self.read(
                    f"- **Status:** Approved\n\n## Slice S1: apply\n\n{task_lines}\n### Partitions\n\n{table}"
                )
                self.assertEqual({task.id: task.partition for task in tasks}, _expected_partitions(rows))

    def test_reads_whether_partitions_run_in_parallel(self) -> None:
        # R3.6: the parallel answer is read back from the header; a plan without the line is serial.
        headers = {
            "- **Parallel:** yes\n": True,
            "- **Parallel:** Yes\n": True,
            "- **Parallel:** no\n": False,
            "": False,
        }
        for header, expected in headers.items():
            with self.subTest(header=header):
                self.path.write_text(f"- **Status:** Approved\n{header}\n- [ ] **T1** First\n", encoding="utf-8")
                self.assertIs(read_tasks(self.path).parallel, expected)


if __name__ == "__main__":
    unittest.main()
