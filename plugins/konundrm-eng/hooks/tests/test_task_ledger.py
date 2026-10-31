"""Tests for hooks/scripts/task_ledger.py, run as the CLI the orchestrator calls, in temporary repositories."""

from __future__ import annotations

import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import quality_check
import task_ledger
from task_commits import task_commits
from working_tree import snapshot_tree

TASK_LEDGER = Path(__file__).resolve().parents[1] / "scripts" / "task_ledger.py"
PLAN_PATH = "specs/002-efficient-feature-flow/tasks.md"
# Accented, as this plan's real titles are: status must print it as UTF-8 whatever the locale.
NEXT_TITLE = "status nombra la próxima tarea del árbol"


def git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return completed.stdout.strip()


def commit(root: Path, message: str) -> str:
    """Commit everything with `message` (written to a UTF-8 file, so `·` survives) and return its sha."""
    message_file = root.parent / "message.txt"
    message_file.write_text(message, encoding="utf-8", newline="\n")
    git(root, "add", "-A")
    git(root, "commit", "-q", "--allow-empty", "-F", str(message_file))
    return git(root, "rev-parse", "HEAD")


def plan_text(base: str) -> str:
    return (
        "# Tasks: efficient feature flow\n"
        "\n"
        "- **Status:** Approved\n"
        f"- **Base commit:** `{base}`\n"
        "\n"
        "## Slice S1: the ledger\n"
        "\n"
        "- [ ] **T1** status reads the plan · `behavior` · Risk: low · Covers: R4.1\n"
        f"- [x] **T2** {NEXT_TITLE} · `behavior` · Risk: low · Covers: R1.8\n"
        "- [ ] **T3** status reads the check · `behavior` · Risk: low · Covers: R4.1\n"
    )


def line_value(output: str, key: str) -> str:
    """Return the value of the single `key: value` line of `output`."""
    values = [line[len(key) + 1 :].strip() for line in output.splitlines() if line.startswith(f"{key}:")]
    if len(values) != 1:
        raise AssertionError(f"expected one {key!r} line in:\n{output}")
    return values[0]


@unittest.skipIf(shutil.which("git") is None, "Git is not installed")
class LedgerRepositoryTest(unittest.TestCase):
    """A temporary repository and the environment every task_ledger.py call runs under."""

    def setUp(self) -> None:
        repository = tempfile.TemporaryDirectory()
        self.addCleanup(repository.cleanup)
        self.root = (Path(repository.name).resolve()) / "repo"
        self.root.mkdir()
        git(self.root, "init", "-q")
        # A non-UTF-8 locale (cp1252 on Windows, ASCII under an uncoerced C locale elsewhere), so the
        # script itself must write UTF-8; no session variables, so no result depends on the session.
        dropped = {
            "CLAUDE_PLUGIN_DATA",
            "CLAUDE_PROJECT_DIR",
            "PYTHONIOENCODING",
            "PYTHONUTF8",
            "PYTHONCOERCECLOCALE",
            "LC_ALL",
            "LANG",
        }
        self.environment = {key: value for key, value in os.environ.items() if key.upper() not in dropped}
        self.environment |= {"PYTHONUTF8": "0", "PYTHONCOERCECLOCALE": "0", "LC_ALL": "C"}


class StatusTest(LedgerRepositoryTest):
    def run_status(self) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(
            [sys.executable, str(TASK_LEDGER), "status", PLAN_PATH],
            cwd=self.root,
            env=self.environment,
            capture_output=True,
            check=False,
        )

    def status(self) -> str:
        completed = self.run_status()
        stdout = completed.stdout.decode("utf-8")
        self.assertEqual(completed.returncode, 0, f"{stdout}\n{completed.stderr.decode('utf-8', 'replace')}")
        return stdout

    # R4.1, R1.8: one call shows the base, the tasks with a commit after the base (box checked or
    # not), the first task without one, whether the tree is clean and whether its check passed.
    def test_status_shows_next_task_built_tasks_tree_and_check(self) -> None:
        (self.root / "README.md").write_text("previous feature\n", encoding="utf-8")
        commit(self.root, "feat: an earlier feature's task\n\nTask: T2 · Covers: R9.9\n")
        base = commit(self.root, "chore: start the feature branch\n")
        plan = self.root / PLAN_PATH
        plan.parent.mkdir(parents=True)
        plan.write_text(plan_text(base), encoding="utf-8", newline="\n")
        commit(self.root, "docs(specs): add spec and plan\n")
        (self.root / "ledger.txt").write_text("T1\n", encoding="utf-8")
        commit(self.root, "feat: status reads the plan\n\nTask: T1 · Covers: R4.1\n")

        clean_unrecorded = self.status()
        quality_check.remember_green_tree(self.root, snapshot_tree(self.root))
        clean_green = self.status()
        (self.root / "test_new_task.py").write_text("# a task's new test\n", encoding="utf-8")
        dirty_unrecorded = self.status()
        quality_check.remember_green_tree(self.root, snapshot_tree(self.root))
        dirty_green = self.status()

        self.assertEqual(line_value(clean_unrecorded, "base"), base)
        self.assertEqual(line_value(clean_unrecorded, "committed").replace(",", " ").split(), ["T1"])
        next_task = line_value(clean_unrecorded, "next")
        self.assertEqual(next_task.split()[0], "T2")
        self.assertIn(NEXT_TITLE, next_task)
        observed = [
            (line_value(output, "tree"), line_value(output, "check"))
            for output in (clean_unrecorded, clean_green, dirty_unrecorded, dirty_green)
        ]
        self.assertEqual(
            observed,
            [
                ("clean", "not recorded"),
                ("clean", "green for this tree"),
                ("dirty", "not recorded"),
                ("dirty", "green for this tree"),
            ],
        )

    # R4.1, R1.9: with partitions in parallel, status names the first task without a commit of each
    # partition of the wave in progress. Built means committed after the base (every box stays
    # unchecked), and a later partition's task may land before an earlier one of another partition.
    def test_status_names_the_next_task_of_each_partition_in_the_current_wave(self) -> None:
        base = commit(self.root, "chore: start the feature branch\n")
        plan = self.root / PLAN_PATH
        plan.parent.mkdir(parents=True)

        def write_plan(parallel: str) -> None:
            tasks = "".join(f"- [ ] **T{n}** step {n} · `behavior` · Risk: low · Covers: R4.1\n" for n in range(1, 7))
            plan.write_text(
                "# Tasks: efficient feature flow\n"
                "\n"
                "- **Status:** Approved\n"
                f"- **Base commit:** `{base}`\n"
                f"- **Parallel:** {parallel}\n"
                "\n"
                "## Slice S1: the ledger\n"
                "\n"
                f"{tasks}"
                "\n"
                "### Partitions\n"
                "\n"
                "| Wave | Partition | Tasks | Depends on |\n"
                "| --- | --- | --- | --- |\n"
                "| 1 | P1 | T1, T2 | — |\n"
                "| 1 | P2 | T3, T4 | — |\n"
                "| 2 | P3 | T5 | P1 |\n"
                "| 2 | P4 | T6 | P2 |\n",
                encoding="utf-8",
                newline="\n",
            )

        write_plan("yes")
        commit(self.root, "docs(specs): add spec and plan\n")

        def build(task_id: str) -> None:
            (self.root / f"{task_id}.txt").write_text(f"{task_id}\n", encoding="utf-8")
            commit(self.root, f"feat: build {task_id}\n\nTask: {task_id} · Covers: R4.1\n")

        build("T3")
        first_wave = self.status()
        for task_id in ("T1", "T2", "T4"):
            build(task_id)
        second_wave = self.status()
        write_plan("no")
        serial = self.status()

        self.assertEqual(line_value(first_wave, "next per partition"), "P1 T1, P2 T4")
        self.assertNotIn("next:", [line[:5] for line in first_wave.splitlines()])
        self.assertEqual(line_value(second_wave, "next per partition"), "P3 T5, P4 T6")
        self.assertNotIn("next:", [line[:5] for line in second_wave.splitlines()])
        self.assertEqual(line_value(serial, "next"), "T5 step 5")
        self.assertNotIn("next per partition", serial)

    # R4.6: a plan that cannot be read (missing, without a usable Base commit, or naming a commit
    # this repository lacks) ends with exit 2 (1 means "refused") and names the file and the line,
    # as given on the command line, with no status lines on stdout and nothing changed.
    def test_status_names_the_file_and_line_when_the_plan_cannot_be_read(self) -> None:
        commit(self.root, "chore: start the feature branch\n")
        plan = self.root / PLAN_PATH
        plan.parent.mkdir(parents=True)
        placeholder = plan_text("x").replace("`x`", "`<SHA the feature branch started from>`")
        without_base = "".join(line for line in plan_text("x").splitlines(keepends=True) if "Base commit" not in line)
        cases = {
            "missing plan": (None, PLAN_PATH),
            "no Base commit line": (without_base, f"{PLAN_PATH}:1"),
            "template placeholder": (placeholder, f"{PLAN_PATH}:4"),
            "unknown commit": (plan_text("deadbeef" * 5), f"{PLAN_PATH}:4"),
        }
        for case, (text, location) in cases.items():
            with self.subTest(case):
                if text is None:
                    plan.unlink(missing_ok=True)
                else:
                    plan.write_text(text, encoding="utf-8", newline="\n")
                plan_bytes = plan.read_bytes() if text is not None else None
                porcelain = git(self.root, "status", "--porcelain")

                completed = self.run_status()

                stderr = completed.stderr.decode("utf-8", "replace")
                self.assertEqual(completed.returncode, 2, stderr)
                self.assertIn(location, stderr)
                self.assertNotIn("Traceback", stderr)
                self.assertEqual(completed.stdout.decode("utf-8", "replace"), "")
                self.assertEqual(plan.exists(), text is not None)
                self.assertEqual(plan.read_bytes() if text is not None else None, plan_bytes)
                self.assertEqual(git(self.root, "status", "--porcelain"), porcelain)


class MessageTest(LedgerRepositoryTest):
    def message(self, *args: str) -> str:
        """Run `message` from the repository root and return the path it prints, as `msg=$(…)` takes it."""
        completed = subprocess.run(
            [sys.executable, str(TASK_LEDGER), "message", PLAN_PATH, *args],
            cwd=self.root,
            env=self.environment,
            capture_output=True,
            check=False,
        )
        stdout = completed.stdout.decode("utf-8", "replace")
        self.assertEqual(completed.returncode, 0, f"{stdout}\n{completed.stderr.decode('utf-8', 'replace')}")
        printed = stdout.removesuffix("\n")
        self.assertTrue(printed, "message printed no path")
        self.assertNotIn("\n", printed, f"stdout must be exactly one line: {stdout!r}")
        self.assertNotIn("\r", printed, f"stdout must be exactly one line: {stdout!r}")
        return printed

    def message_leaving_the_tree_alone(self, *args: str) -> str:
        """Run `message` and check it changed nothing in the working tree (R2.7: not even the plan)."""
        plan = self.root / PLAN_PATH
        before = (plan.read_bytes(), git(self.root, "status", "--porcelain"), snapshot_tree(self.root))
        printed = self.message(*args)
        after = (plan.read_bytes(), git(self.root, "status", "--porcelain"), snapshot_tree(self.root))
        self.assertEqual(after, before)
        return printed

    def commit_with(self, printed: str) -> str:
        """Commit as the orchestrator does (add everything, then commit -F the printed path) from the root."""
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-F", printed)
        return git(self.root, "rev-parse", "HEAD")

    # R4.2, R2.7: one call builds the task's commit message (subject, optional body, then a final
    # paragraph that is Git's trailer block: the Task line with the covers that end the plan's line,
    # and the Rounds line), writes it under the Git directory as UTF-8 and prints only its path.
    # A second call overwrites the file, and neither call touches the working tree.
    def test_message_builds_the_task_commit_message_from_the_plan(self) -> None:
        base = commit(self.root, "chore: start the feature branch\n")
        plan = self.root / PLAN_PATH
        plan.parent.mkdir(parents=True)
        plan.write_text(
            "# Tasks: efficient feature flow\n"
            "\n"
            "- **Status:** Approved\n"
            f"- **Base commit:** `{base}`\n"
            "\n"
            "## Slice S4: the commit message\n"
            "\n"
            "- [ ] **T1** status reads the plan · `behavior` · Risk: low · Covers: R4.1\n"
            # The title quotes a Task line itself, as this feature's real T11 does: the covers must
            # come from the field that ends the line.
            "- [ ] **T2** `message` arma el mensaje con el asunto, `Task: T<n> · Covers: …` del plan y "
            "`Rounds:`, lo escribe bajo el directorio de Git e imprime su ruta · `behavior` · Risk: low · "
            "Covers: R4.2, R2.7\n"
            "- [ ] **T3** status reads the check · `behavior` · Risk: low · Covers: R4.1\n",
            encoding="utf-8",
            newline="\n",
        )
        commit(self.root, "docs(specs): add spec and plan\n")
        rounds = "spec 1 · code 2 · escalations 0"
        expected_with_body = (
            "feat(hooks): build the task commit message\n"
            "\n"
            "Reads the covers from the plan.\n"
            "Writes the message under the Git directory.\n"
            "\n"
            "Task: T2 · Covers: R4.2, R2.7\n"
            "Rounds: spec 1 · code 2 · escalations 0"
        )
        expected_without_body = (
            "feat(hooks): read the check in status\n\nTask: T3 · Covers: R4.1\nRounds: spec 1 · code 2 · escalations 0"
        )
        message_file = (self.root / git(self.root, "rev-parse", "--git-path", "KONUNDRM_TASK_MSG")).resolve()

        (self.root / "T2.txt").write_text("T2\n", encoding="utf-8")
        first_path = self.message_leaving_the_tree_alone(
            "T2",
            "--subject",
            "feat(hooks): build the task commit message",
            "--rounds",
            rounds,
            "--body",
            "Reads the covers from the plan.\nWrites the message under the Git directory.",
        )
        first_text = Path(self.root, first_path).read_bytes().decode("utf-8")
        first_sha = self.commit_with(first_path)
        (self.root / "T3.txt").write_text("T3\n", encoding="utf-8")
        second_path = self.message_leaving_the_tree_alone(
            "T3", "--subject", "feat(hooks): read the check in status", "--rounds", rounds
        )
        second_text = Path(self.root, second_path).read_bytes().decode("utf-8")
        second_sha = self.commit_with(second_path)

        self.assertEqual(Path(self.root, first_path).resolve(), message_file)
        self.assertEqual(Path(self.root, second_path).resolve(), message_file)
        self.assertEqual(first_text.removesuffix("\n"), expected_with_body)
        self.assertEqual(second_text.removesuffix("\n"), expected_without_body)
        self.assertEqual(git(self.root, "log", "-1", "--format=%B", first_sha), expected_with_body)
        self.assertEqual(git(self.root, "log", "-1", "--format=%B", second_sha), expected_without_body)
        found = task_commits(self.root, base)
        self.assertEqual(
            {task_id: (found[task_id].sha, found[task_id].rounds) for task_id in found},
            {"T2": (first_sha, (1, 2, 0)), "T3": (second_sha, (1, 2, 0))},
        )

    def run_message(self, *args: str) -> subprocess.CompletedProcess[bytes]:
        """Run `message` from the repository root without asserting how it ended."""
        return subprocess.run(
            [sys.executable, str(TASK_LEDGER), "message", PLAN_PATH, *args],
            cwd=self.root,
            env=self.environment,
            capture_output=True,
            check=False,
        )

    # R4.4: a task the plan lacks, or one a commit after the base already names (matched by number,
    # so `**T02**` is the `Task: T2` commit, as status counts it), is refused with exit 1, nothing on
    # stdout for `msg=$(…)`, a reason naming the task and the plan or the commit, and nothing
    # changed: no message file created or rewritten, the working tree as it was. A `Task:` commit
    # before the base is an earlier feature's and does not count.
    def test_message_refuses_an_unknown_or_already_committed_task(self) -> None:
        (self.root / "README.md").write_text("previous feature\n", encoding="utf-8")
        commit(self.root, "feat: an earlier feature's task\n\nTask: T1 · Covers: R9.9\n")
        base = commit(self.root, "chore: start the feature branch\n")
        plan = self.root / PLAN_PATH
        plan.parent.mkdir(parents=True)
        plan.write_text(
            "# Tasks: efficient feature flow\n"
            "\n"
            "- **Status:** Approved\n"
            f"- **Base commit:** `{base}`\n"
            "\n"
            "## Slice S4: the commit message\n"
            "\n"
            "- [ ] **T1** status reads the plan · `behavior` · Risk: low · Covers: R4.1\n"
            "- [ ] **T02** message refuses a committed task · `behavior` · Risk: low · Covers: R4.4\n"
            "- [ ] **T3** status reads the check · `behavior` · Risk: low · Covers: R4.1\n",
            encoding="utf-8",
            newline="\n",
        )
        commit(self.root, "docs(specs): add spec and plan\n")
        (self.root / "T2.txt").write_text("T2\n", encoding="utf-8")
        committed_sha = commit(self.root, "feat: build T2\n\nTask: T2 · Covers: R4.4\n")
        (self.root / "work_in_progress.py").write_text("# the next task's change\n", encoding="utf-8")
        message_file = (self.root / git(self.root, "rev-parse", "--git-path", "KONUNDRM_TASK_MSG")).resolve()
        rounds = ("--subject", "feat(hooks): a task", "--rounds", "spec 1 · code 1 · escalations 0")
        refusals = {
            "unknown task": ("T9", PLAN_PATH),
            "committed after the base, written T02": ("T02", committed_sha[:7]),
        }

        def assert_refused(task_id: str, named: str) -> None:
            before = (plan.read_bytes(), git(self.root, "status", "--porcelain"), snapshot_tree(self.root))
            file_before = message_file.read_bytes() if message_file.exists() else None

            completed = self.run_message(task_id, *rounds)

            stderr = completed.stderr.decode("utf-8", "replace")
            self.assertEqual(completed.returncode, 1, stderr)
            self.assertNotIn("Traceback", stderr)
            self.assertEqual(completed.stdout.decode("utf-8", "replace"), "")
            self.assertIn(task_id, stderr)
            self.assertIn(named, stderr)
            self.assertEqual(message_file.read_bytes() if message_file.exists() else None, file_before)
            after = (plan.read_bytes(), git(self.root, "status", "--porcelain"), snapshot_tree(self.root))
            self.assertEqual(after, before)

        for case, (task_id, named) in refusals.items():
            with self.subTest(f"{case}, no message file yet"):
                assert_refused(task_id, named)
                self.assertFalse(message_file.exists())
        with self.subTest("committed before the base only: accepted"):
            accepted = self.message_leaving_the_tree_alone("T1", *rounds)
            self.assertEqual(Path(self.root, accepted).resolve(), message_file)
        for case, (task_id, named) in refusals.items():
            with self.subTest(f"{case}, after an accepted call wrote the file"):
                assert_refused(task_id, named)
        with self.subTest("status counts T02 as committed too"):
            status = subprocess.run(
                [sys.executable, str(TASK_LEDGER), "status", PLAN_PATH],
                cwd=self.root,
                env=self.environment,
                capture_output=True,
                check=False,
            )
            stdout = status.stdout.decode("utf-8", "replace")
            self.assertEqual(status.returncode, 0, status.stderr.decode("utf-8", "replace"))
            self.assertEqual(line_value(stdout, "committed").replace(",", " ").split(), ["T02"])


def two_slice_plan(base: str, s2_tasks: str) -> str:
    """A plan laid out as this feature's tasks.md, with slice S2's task blocks given."""
    return (
        "# Tasks: efficient feature flow\n"
        "\n"
        "- **Status:** Approved\n"
        f"- **Base commit:** `{base}`\n"
        "\n"
        "## Slice S1: the ledger\n"
        "\n"
        "- [ ] **T1** status reads the plan · `behavior` · Risk: low · Covers: R4.1\n"
        "  - Verify: `... -k test_one`\n"
        "  - Depends on: —\n"
        "\n"
        "- [ ] **T2** status reads the check · `behavior` · Risk: low · Covers: R4.1\n"
        "  - Verify: `... -k test_two`\n"
        "  - Depends on: T1\n"
        "\n"
        "### Partitions\n"
        "\n"
        "| Wave | Partition | Tasks | Depends on |\n"
        "| --- | --- | --- | --- |\n"
        "| 1 | P1 | T1, T2 | — |\n"
        "\n"
        "## Slice S2: the slice pause\n"
        "\n"
        f"{s2_tasks}"
        "\n"
        "### Partitions\n"
        "\n"
        "| Wave | Partition | Tasks | Depends on |\n"
        "| --- | --- | --- | --- |\n"
        "| 1 | P1 | T3, T04, T5, T6 | — |\n"
        # writing-plans' template ends with this example; its T1 is no task, though T1 is committed.
        "\n"
        "<!-- Example of a finished task, as develop-feature leaves it:\n"
        "- [x] **T1** … · `behavior` · Risk: low · Covers: R1.1\n"
        "  - Decision: Option A (user)\n"
        "    - Option A: <approach> · pros: <…> · cons: <…>\n"
        "    - Option B: <approach> · pros: <…> · cons: <…>\n"
        "    - Recommendation: <option, and why>\n"
        "  - Rounds: spec 1 · code 1 · escalations 0\n"
        "-->\n"
    )


S2_OPEN = (
    "- [ ] **T3** close-slice checks the boxes · `behavior` · Risk: medium · Covers: R2.8, R4.5\n"
    "  - Verify: `... -k test_three`\n"
    "  - Depends on: T2\n"
    "  - Decision: Option A (user) — where the rounds come from\n"
    "    - Option A: the task's commit · pros: one source · cons: none\n"
    "    - Recommendation: A.\n"
    "\n"
    "- [ ] **T04** close-slice replaces a Rounds line · `behavior` · Risk: low · Covers: R2.8\n"
    "  - Verify: `... -k test_four`\n"
    "  - Rounds: spec 9 · code 9 · escalations 9\n"
    "  - Depends on: T3\n"
    "\n"
    "- [ ] **T5** close-slice keeps the plan's rounds · `behavior` · Risk: low · Covers: R2.8\n"
    "  - Verify: `... -k test_five`\n"
    "  - Rounds: spec 2 · code 2 · escalations 2\n"
    "\n"
    "- [ ] **T6** close-slice reports a task without a commit · `behavior` · Risk: low · Covers: R2.8\n"
    "  - Verify: `... -k test_six`\n"
    "  - Depends on: T5\n"
)

S2_CLOSED = (
    "- [x] **T3** close-slice checks the boxes · `behavior` · Risk: medium · Covers: R2.8, R4.5\n"
    "  - Verify: `... -k test_three`\n"
    "  - Depends on: T2\n"
    "  - Decision: Option A (user) — where the rounds come from\n"
    "    - Option A: the task's commit · pros: one source · cons: none\n"
    "    - Recommendation: A.\n"
    "  - Rounds: spec 2 · code 3 · escalations 1\n"
    "\n"
    "- [x] **T04** close-slice replaces a Rounds line · `behavior` · Risk: low · Covers: R2.8\n"
    "  - Verify: `... -k test_four`\n"
    "  - Rounds: spec 1 · code 4 · escalations 0\n"
    "  - Depends on: T3\n"
    "\n"
    "- [x] **T5** close-slice keeps the plan's rounds · `behavior` · Risk: low · Covers: R2.8\n"
    "  - Verify: `... -k test_five`\n"
    "  - Rounds: spec 2 · code 2 · escalations 2\n"
    "\n"
    "- [ ] **T6** close-slice reports a task without a commit · `behavior` · Risk: low · Covers: R2.8\n"
    "  - Verify: `... -k test_six`\n"
    "  - Depends on: T5\n"
)


SEED_COUNT = 30
PLAN_TASK_NUMBERS = range(1, 13)
"""Numbers a generated plan draws its tasks from, wider than the committed ones."""
COMMITTED_NUMBERS = frozenset(range(1, 7))
"""Numbers the fixed history commits after the base (T1 to T6)."""
TASK_LINE = re.compile(rb"^- \[[ xX]\] \*\*T0*(?P<number>\d+)\*\*")
ROUNDS_LINE = re.compile(rb"^\s+- Rounds:")


def _random_rounds(rng: random.Random) -> str:
    return f"Rounds: spec {rng.randint(0, 5)} · code {rng.randint(0, 5)} · escalations {rng.randint(0, 2)}"


def _plain_rounds(number: int) -> str:
    """A commit's Rounds line whose numbers derive from `number`, ending in a line feed."""
    return f"Rounds: spec {number} · code {number + 1} · escalations 0\n"


def _random_task_block(rng: random.Random, number: int) -> list[str]:
    """One task's lines without endings: the task line, then fields, a Decision and a Rounds line."""
    task_id = f"T{number:02d}" if rng.random() < 0.3 else f"T{number}"
    box = rng.choice([" ", " ", "x", "X"])
    fields = [
        [f"  - Verify: `... -k test_{number}`"],
        ["  - Depends on: —"],
        [f"  - Files: `module_{number}.py`"],
    ]
    units = rng.sample(fields, rng.randint(0, 3))
    if rng.random() < 0.3:
        units.append(
            [
                "  - Decision: Option A (user) — a choice",
                "    - Option A: one · pros: simple · cons: none",
                "    - Recommendation: A.",
            ]
        )
    rng.shuffle(units)
    if rng.random() < 0.5:
        units.insert(rng.randint(0, len(units)), [f"  - {_random_rounds(rng)}"])
    task_line = f"- [{box}] **{task_id}** step {number} · `behavior` · Risk: low · Covers: R2.8"
    return [task_line, *(line for unit in units for line in unit)]


def _random_plan(rng: random.Random, base: str) -> tuple[bytes, str]:
    """A plan with the real layout and random line endings, and the ID of one of its slices."""
    numbers = rng.sample(list(PLAN_TASK_NUMBERS), rng.randint(1, 8))
    slice_count = rng.randint(1, min(3, len(numbers)))
    cuts = sorted(rng.sample(range(1, len(numbers)), slice_count - 1))
    groups = [numbers[start:end] for start, end in zip([0, *cuts], [*cuts, len(numbers)], strict=True)]
    lines = ["# Tasks: efficient feature flow", "", "- **Status:** Approved", f"- **Base commit:** `{base}`", ""]
    for index, group in enumerate(groups, start=1):
        if index > 1:
            lines.append("")
        lines += [f"## Slice S{index}: slice {index}", ""]
        for position, number in enumerate(group):
            if position > 0:
                lines += ["", "<!-- a note between blocks -->", ""] if rng.random() < 0.2 else [""]
            lines += _random_task_block(rng, number)
        lines += [
            "",
            "### Partitions",
            "",
            "| Wave | Partition | Tasks | Depends on |",
            "| --- | --- | --- | --- |",
            f"| 1 | P1 | {', '.join(f'T{number}' for number in group)} | — |",
        ]
    mode = rng.choice(["lf", "crlf", "mixed"])
    endings = [{"lf": "\n", "crlf": "\r\n"}.get(mode) or rng.choice(["\n", "\r\n"]) for _ in lines]
    if rng.random() < 0.3:
        endings[-1] = ""  # only ever after the last Partitions row
    text = "".join(line + ending for line, ending in zip(lines, endings, strict=True))
    return text.encode("utf-8"), f"S{rng.randint(1, len(groups))}"


def _split_at_slice(content: bytes, slice_id: str) -> tuple[list[bytes], list[bytes], list[bytes]]:
    """The lines (endings kept) before the slice's heading, from it to the next slice, and after."""
    lines = content.splitlines(keepends=True)
    heading = f"## Slice {slice_id}:".encode()
    start = next(index for index, line in enumerate(lines) if line.startswith(heading))
    end = next(
        (index for index in range(start + 1, len(lines)) if lines[index].startswith(b"## Slice ")),
        len(lines),
    )
    return lines[:start], lines[start:end], lines[end:]


class CloseSliceTest(LedgerRepositoryTest):
    def run_close_slice(self, slice_id: str) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(
            [sys.executable, str(TASK_LEDGER), "close-slice", PLAN_PATH, slice_id],
            cwd=self.root,
            env=self.environment,
            capture_output=True,
            check=False,
        )

    # R2.8, R4.5: one call checks the box of every task of the named slice that has a commit after
    # the base and writes the rounds from that commit (the task's oldest one in the range) as the
    # block's last line, or in place of its Rounds line; a commit without Rounds leaves the plan's
    # line alone, a task without a commit stays unchecked and is reported, other slices and an
    # earlier feature's commits do not count, the file keeps its line endings, a second run changes
    # nothing, an unknown slice is refused, and nothing but the plan changes (no commit).
    def test_close_slice_checks_boxes_and_writes_rounds_from_the_commits(self) -> None:
        git(self.root, "config", "core.autocrlf", "false")
        (self.root / "README.md").write_text("previous feature\n", encoding="utf-8")
        commit(
            self.root,
            "feat: an earlier feature's task\n\nTask: T6 · Covers: R9.9\nRounds: spec 8 · code 8 · escalations 8\n",
        )
        base = commit(self.root, "chore: start the feature branch\n")
        commit(self.root, "feat: build T1\n\nTask: T1 · Covers: R4.1\nRounds: spec 7 · code 7 · escalations 7\n")
        commit(self.root, "feat: build T3\n\nTask: T3 · Covers: R2.8, R4.5\nRounds: spec 2 · code 3 · escalations 1\n")
        commit(self.root, "feat: build T4\n\nTask: T4 · Covers: R2.8\nRounds: spec 1 · code 4 · escalations 0\n")
        commit(self.root, "feat: build T5\n\nTask: T5 · Covers: R2.8\n")
        commit(self.root, "docs(specs): summarize slice S2\n\nTask: T3 · Covers: R2.8, R4.5\n")
        plan = self.root / PLAN_PATH
        plan.parent.mkdir(parents=True)

        for newline in ("\n", "\r\n"):
            with self.subTest(newline=repr(newline)):
                plan.write_text(two_slice_plan(base, S2_OPEN), encoding="utf-8", newline=newline)
                head = commit(self.root, "docs(specs): add the plan\n")
                expected = two_slice_plan(base, S2_CLOSED).replace("\n", newline).encode("utf-8")

                first = self.run_close_slice("S2")
                first_bytes = plan.read_bytes()
                second = self.run_close_slice("S2")
                second_bytes = plan.read_bytes()
                unknown = self.run_close_slice("S9")

                first_stdout = first.stdout.decode("utf-8", "replace")
                self.assertEqual(first.returncode, 0, f"{first_stdout}\n{first.stderr.decode('utf-8', 'replace')}")
                self.assertEqual(first_bytes, expected)
                self.assertEqual(line_value(first_stdout, "not committed"), "T6")
                self.assertEqual(second.returncode, 0, second.stderr.decode("utf-8", "replace"))
                self.assertEqual(second_bytes, expected)
                unknown_stderr = unknown.stderr.decode("utf-8", "replace")
                self.assertEqual(unknown.returncode, 1, unknown_stderr)
                self.assertIn("S9", unknown_stderr)
                self.assertNotIn("Traceback", unknown_stderr)
                self.assertEqual(unknown.stdout.decode("utf-8", "replace"), "")
                self.assertEqual(plan.read_bytes(), expected)
                self.assertEqual(git(self.root, "rev-parse", "HEAD"), head)
                self.assertEqual(git(self.root, "status", "--porcelain", "--untracked-files=all"), f"M {PLAN_PATH}")
                self.assertEqual(git(self.root, "diff", "--name-only"), PLAN_PATH)

        # A plan from before Partitions tables can end on its last task block, with no final line
        # break: the added Rounds line takes the file's CRLF and the file keeps its missing break.
        with self.subTest(newline="'\\r\\n', the slice's last task block ends the file without a break"):
            plan_lines = [
                "# Tasks: efficient feature flow",
                "",
                f"- **Base commit:** `{base}`",
                "",
                "## Slice S1: the ledger",
                "",
                "- [ ] **T1** status reads the plan · `behavior` · Risk: low · Covers: R4.1",
                "  - Verify: `... -k test_one`",
                "",
                "## Slice S2: the slice pause",
                "",
                "- [ ] **T3** close-slice checks the boxes · `behavior` · Risk: medium · Covers: R2.8, R4.5",
                "  - Verify: `... -k test_three`",
            ]
            plan.write_bytes("\r\n".join(plan_lines).encode("utf-8"))
            closed_lines = [
                *plan_lines[:11],
                "- [x] **T3** close-slice checks the boxes · `behavior` · Risk: medium · Covers: R2.8, R4.5",
                "  - Verify: `... -k test_three`",
                "  - Rounds: spec 2 · code 3 · escalations 1",
            ]
            expected = "\r\n".join(closed_lines).encode("utf-8")

            first = self.run_close_slice("S2")
            first_bytes = plan.read_bytes()
            second = self.run_close_slice("S2")
            second_bytes = plan.read_bytes()

            self.assertEqual(first.returncode, 0, first.stderr.decode("utf-8", "replace"))
            self.assertEqual(first_bytes, expected)
            self.assertEqual(second.returncode, 0, second.stderr.decode("utf-8", "replace"))
            self.assertEqual(second_bytes, expected)

    # R2.8, R4.5 (T13 invariants): over seeded plans with the real layout and LF, CRLF or mixed
    # line endings, a second close-slice leaves the file byte-identical, and the first changes
    # nothing but the named slice's task boxes ([ ] → [x], only for a task committed after the base)
    # and its indented Rounds lines; every other line, ending included, stays in place.
    def test_close_slice_is_idempotent_and_changes_only_the_slices_boxes_and_rounds(self) -> None:
        commit(self.root, "feat: an earlier feature's task\n\nTask: T9 · Covers: R9.9\n" + _plain_rounds(8))
        base = commit(self.root, "chore: start the feature branch\n")
        for number in sorted(COMMITTED_NUMBERS):
            rounds = _plain_rounds(number) if number % 2 else ""
            commit(self.root, f"feat: build T{number}\n\nTask: T{number} · Covers: R2.8\n{rounds}")
        commit(self.root, "docs(specs): summarize slice S1\n\nTask: T3 · Covers: R2.8\n")
        plan = self.root / PLAN_PATH
        plan.parent.mkdir(parents=True)

        for seed in range(SEED_COUNT):
            rng = random.Random(seed)  # noqa: S311 - seeded for reproducible test data, not cryptography
            original, slice_id = _random_plan(rng, base)
            context = f"seed {seed}, closing {slice_id}, plan:\n{original.decode('utf-8')!r}"
            with self.subTest(seed=seed):
                plan.write_bytes(original)

                task_ledger.close_slice(self.root, plan, slice_id)
                closed = plan.read_bytes()
                task_ledger.close_slice(self.root, plan, slice_id)
                closed_twice = plan.read_bytes()

                self.assertEqual(closed_twice, closed, context)
                before, original_slice, after = _split_at_slice(original, slice_id)
                closed_before, closed_slice, closed_after = _split_at_slice(closed, slice_id)

                def kept(lines: list[bytes]) -> list[bytes]:
                    return [line for line in lines if not TASK_LINE.match(line) and not ROUNDS_LINE.match(line)]

                self.assertEqual(
                    closed_before + kept(closed_slice) + closed_after, before + kept(original_slice) + after, context
                )
                original_tasks = [line for line in original_slice if TASK_LINE.match(line)]
                closed_tasks = [line for line in closed_slice if TASK_LINE.match(line)]
                self.assertEqual(len(closed_tasks), len(original_tasks), context)
                for original_line, closed_line in zip(original_tasks, closed_tasks, strict=True):
                    if closed_line == original_line:
                        continue
                    number = int(TASK_LINE.match(original_line)["number"])
                    self.assertTrue(original_line.startswith(b"- [ ] "), f"{context}\n{closed_line!r}")
                    self.assertEqual(closed_line, b"- [x] " + original_line[len(b"- [ ] ") :], context)
                    self.assertIn(number, COMMITTED_NUMBERS, f"{context}\n{closed_line!r}")


if __name__ == "__main__":
    unittest.main()
