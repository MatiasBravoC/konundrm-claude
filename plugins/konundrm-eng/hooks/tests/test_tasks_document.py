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

from tasks_document import Task, TasksDocument, read_tasks

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


# CPython refuses int() on strings longer than this many digits (sys.get_int_max_str_digits()).
INT_DIGIT_LIMIT = 4300
STRAY_TOKENS = (",", "**", "\u2014", "x", "T", "Tx", "abc", "P1", "T-", "..", "to")
# Maps every byte to an ASCII digit, so thousands of random digits cost one translate call.
BYTE_TO_DIGIT = bytes(ord("0") + value % 10 for value in range(256))


def _random_task_id(rng: random.Random) -> str:
    """A task ID of 1 to 4 digits, or now and then one well past CPython's int digit limit, sometimes zero-padded."""
    length = rng.randint(INT_DIGIT_LIMIT - 100, INT_DIGIT_LIMIT + 1700) if rng.random() < 0.1 else rng.randint(1, 4)
    digits = str(rng.randint(1, 9)) + rng.randbytes(length - 1).translate(BYTE_TO_DIGIT).decode("ascii")
    padding = "0" * rng.randint(1, 3) if rng.random() < 0.2 else ""
    return f"T{padding}{digits}"


def _random_cell(rng: random.Random) -> str:
    """A Tasks cell mixing IDs, ranges with any accepted separator, commas, bold, placeholders and stray text."""
    tokens: list[str] = []
    for _ in range(rng.randint(0, 5)):
        kind = rng.random()
        if kind < 0.35:
            tokens.append(_random_task_id(rng))
        elif kind < 0.7:
            space = rng.choice(("", " "))
            separator = rng.choice(RANGE_SEPARATORS)
            tokens.append(f"{_random_task_id(rng)}{space}{separator}{space}{_random_task_id(rng)}")
        else:
            tokens.append(rng.choice(STRAY_TOKENS))
    return "".join(f"{token}{rng.choice(('', ' ', ', '))}" for token in tokens)


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
                Task("T1", "Applies a 10 % coupon", True, "low", "S1", (2, 1, 0), covers=("R1.1",)),
                Task("T2", "Total is never negative for any coupon", False, "high", "S1", None, covers=("R1.2",)),
                Task("T3", "Rejects expired coupons", False, "medium", "S2", None, covers=("R2.1",)),
            ),
        )

    def test_ignores_the_commented_example(self) -> None:
        _, tasks = self.read(TASKS)
        self.assertNotIn("T9", [task.id for task in tasks])

    def test_a_rounds_text_quoted_in_another_field_is_not_the_tasks_rounds(self) -> None:
        # 004 R4.10: a `- Change:` line holds the user's words verbatim, and a `Test:` line may
        # describe the ledger, so either can quote a Rounds line. Only the task's own line counts.
        quoted = "  - Change: show the tally as Rounds: spec 9 · code 9 · escalations 9 (user)\n"
        _, without_its_line = self.read("- [ ] **T1** Something · Risk: low\n" + quoted)
        _, with_its_line = self.read(
            "- [x] **T1** Something · Risk: low\n" + quoted + "  - Rounds: spec 2 · code 1 · escalations 0\n"
        )
        self.assertEqual([task.rounds for task in without_its_line], [None])
        self.assertEqual([task.rounds for task in with_its_line], [(2, 1, 0)])

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
        # and is read in under 2 seconds. The child process times only read_tasks, so starting the
        # interpreter does not count against the budget; the looser outer timeout is a kill switch
        # so a reader that enumerates every number in the range cannot hang the suite.
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
            "import json, sys, time\n"
            "from pathlib import Path\n"
            "sys.path.insert(0, sys.argv[1])\n"
            "from tasks_document import read_tasks\n"
            "path = Path(sys.argv[2])\n"
            "start = time.perf_counter()\n"
            "document = read_tasks(path)\n"
            "elapsed_seconds = time.perf_counter() - start\n"
            "partitions = {task.id: task.partition for task in document.tasks}\n"
            "print(json.dumps({'partitions': partitions, 'elapsed_seconds': elapsed_seconds}))\n"
        )
        scripts = str(Path(__file__).resolve().parents[1] / "scripts")
        try:
            # subprocess.run kills the child when the timeout expires. An enumerating reader would run
            # out of memory over 10^10 IDs long before finishing, so waiting past 10 seconds adds nothing.
            completed = subprocess.run(
                [sys.executable, "-c", reader, scripts, str(self.path)],
                capture_output=True,
                text=True,
                timeout=10,
                check=True,
            )
        except subprocess.TimeoutExpired:
            self.fail("reading a partition row with T1\u2013T10000000000 did not finish within 10 seconds")
        result = json.loads(completed.stdout)
        self.assertEqual(
            result["partitions"],
            {"T1": "P1", "T2": "P1", "T7": "P1", "T10000000001": "P2"},
        )
        self.assertLess(
            result["elapsed_seconds"],
            2,
            f"read_tasks took {result['elapsed_seconds']:.2f} s on a T1\u2013T10000000000 row; the budget is 2 s",
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

    def test_zero_padded_ids_match_their_number(self) -> None:
        # R3.8: a zero-padded ID matches its number in an explicit cell (both ways) and in a range's
        # bounds, under the first-row rule; each task keeps its ID exactly as written.
        _, tasks = self.read(
            "- **Status:** Approved\n\n"
            "## Slice S1: apply\n\n"
            "- [ ] **T1** First\n"
            "- [ ] **T02** Second\n"
            "- [ ] **T4** Fourth\n"
            "- [ ] **T6** Sixth\n\n"
            "### Partitions\n\n"
            "| Wave | Partition | Tasks | Depends on |\n"
            "| --- | --- | --- | --- |\n"
            "| 1 | P1 | T01 | \u2014 |\n"
            "| 2 | P2 | T2, T1 | P1 |\n"
            "| 3 | P3 | T03\u2013T05, T02 | P2 |\n"
        )
        self.assertEqual(
            {task.id: task.partition for task in tasks},
            {"T1": "P1", "T02": "P2", "T4": "P3", "T6": None},
        )

    def test_a_task_id_with_thousands_of_digits_does_not_crash_the_reader(self) -> None:
        # R3.8: an explicit ID or a range bound longer than CPython's 4300-digit int limit does not
        # make read_tasks raise, and such a cell matches no task. A range with one over-long bound
        # lists nothing, even when its other bound is small, so T1 and T2 fall through to P4.
        huge = "1" * 5000
        _, tasks = self.read(
            "- **Status:** Approved\n\n"
            "## Slice S1: apply\n\n"
            "- [ ] **T1** First\n"
            "- [ ] **T2** Second\n\n"
            "### Partitions\n\n"
            "| Wave | Partition | Tasks | Depends on |\n"
            "| --- | --- | --- | --- |\n"
            f"| 1 | P1 | T{huge} | \u2014 |\n"
            f"| 2 | P2 | T1\u2013T{huge} | P1 |\n"
            f"| 3 | P3 | T{huge}\u2013T2 | P2 |\n"
            "| 4 | P4 | T1, T2 | P3 |\n"
        )
        self.assertEqual({task.id: task.partition for task in tasks}, {"T1": "P4", "T2": "P4"})

    def test_the_reader_never_raises_on_any_partition_cell(self) -> None:
        # R3.8: over 200 seeded documents, read_tasks returns a TasksDocument whatever the Tasks cells
        # hold: IDs of any length (some past CPython's int digit limit, some zero-padded), ranges with
        # every accepted separator, commas, bold, placeholders and stray letters. Some task lines carry
        # an over-long ID of their own.
        seed = 73
        rng = random.Random(seed)  # noqa: S311 - seeded for reproducible test data, not cryptography
        # 200 cases, because each one writes the file read_tasks takes, and file I/O dominates the run.
        for case in range(200):
            task_ids = ["T1", "T2", "T03", *(_random_task_id(rng) for _ in range(rng.randint(0, 2)))]
            task_lines = "".join(f"- [ ] **{task_id}** Task\n" for task_id in task_ids)
            cells = [_random_cell(rng) for _ in range(rng.randint(1, 4))]
            rows = "".join(
                f"| {index} | {'**' if bold else ''}P{index}{'**' if bold else ''} | {cell} | \u2014 |\n"
                for index, (cell, bold) in enumerate(((cell, rng.random() < 0.3) for cell in cells), start=1)
            )
            with self.subTest(seed=seed, case=case, task_ids=task_ids, cells=cells):
                self.path.write_text(
                    "- **Status:** Approved\n\n## Slice S1: apply\n\n"
                    f"{task_lines}\n### Partitions\n\n"
                    "| Wave | Partition | Tasks | Depends on |\n| --- | --- | --- | --- |\n"
                    f"{rows}",
                    encoding="utf-8",
                )
                self.assertIsInstance(read_tasks(self.path), TasksDocument)

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

    def test_an_unfilled_parallel_line_reads_as_no(self) -> None:
        # R3.6: only a line whose whole value is yes reads as parallel; the template placeholder, the
        # choices left inside a comment, an empty value, or a word on the next line all read as no.
        headers = {
            "- **Parallel:** yes | no\n": False,
            "- **Parallel:** <!-- yes | no -->\n": False,
            "- **Parallel:**\n": False,
            "- **Parallel:** <!-- yes | no -->\nyes, the next line is not the answer\n": False,
            "- **Parallel:**\nyes\n": False,
            "- **Parallel:** yes <!-- yes | no -->\n": True,
            "- **Parallel:** Yes   \n": True,
        }
        for header, expected in headers.items():
            with self.subTest(header=header):
                self.path.write_text(f"- **Status:** Approved\n{header}\n- [ ] **T1** First\n", encoding="utf-8")
                self.assertIs(read_tasks(self.path).parallel, expected)

    def test_reads_the_base_commit_and_each_tasks_covers(self) -> None:
        # R1.8, R4.2: the base commit is a hex SHA, full or short; the template's placeholder or a
        # missing line gives None, since the value is later handed to git as a revision. Each task's
        # covers are the IDs of its trailing Covers field, even when its title mentions "Covers: …".
        headers = {
            "- **Base commit:** `79dbbaedcab693f354418995a117fb422ae95f50`\n": (
                "79dbbaedcab693f354418995a117fb422ae95f50"
            ),
            "- **Base commit:** `b8c3142`\n": "b8c3142",
            "- **Base commit:** `<SHA the feature branch started from>`\n": None,
            "": None,
        }
        for header, expected in headers.items():
            with self.subTest(header=header):
                self.path.write_text(f"- **Status:** Approved\n{header}\n- [ ] **T1** First\n", encoding="utf-8")
                self.assertEqual(read_tasks(self.path).base_commit, expected)
        _, tasks = self.read(
            "- **Status:** Approved\n\n"
            "## Slice S1: resume\n\n"
            "- [ ] **T5** El lector del plan entrega el Base commit · `behavior` · Risk: low · Covers: R1.8, R4.2\n"
            "- [ ] **T6** Una sola cobertura · `behavior` · Risk: low · Covers: R5.1\n"
            "- [ ] **T7** Sin cobertura · `refactor` · Risk: low · Covers: —\n"
            "- [ ] **T11** `message` arma el mensaje con el asunto, `Task: T<n> · Covers: …` del plan y"
            " `Rounds:`, lo escribe bajo el directorio de Git e imprime su ruta · `behavior` · Risk: low"
            " · Covers: R4.2, R2.7\n"
        )
        self.assertEqual(
            {task.id: task.covers for task in tasks},
            {"T5": ("R1.8", "R4.2"), "T6": ("R5.1",), "T7": (), "T11": ("R4.2", "R2.7")},
        )


if __name__ == "__main__":
    unittest.main()
