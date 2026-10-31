"""Tests for hooks/scripts/task_ledger.py, run as the CLI the orchestrator calls, in temporary repositories."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import quality_check
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


if __name__ == "__main__":
    unittest.main()
