"""Unit tests for hooks/scripts/task_commits.py (they run Git in temporary repositories)."""

from __future__ import annotations

import random
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from task_commits import GitError, TaskCommit, task_commits

# Task numbers whose digits prefix one another, so matching a prefix ("T1" in "T10") shows up.
TASK_NUMBERS = (1, 2, 10, 11, 20, 100, 101)
TASK_LINE_ENDINGS = (" · Covers: R1.1", "", " ")
SEED_COUNT = 40


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
    """Commit an empty change with `message` (written to a UTF-8 file, so `·` survives) and return its sha."""
    message_file = root.parent / "message.txt"
    message_file.write_text(message, encoding="utf-8", newline="\n")
    git(root, "commit", "-q", "--allow-empty", "-F", str(message_file))
    return git(root, "rev-parse", "HEAD")


def _random_message(rng: random.Random, index: int) -> tuple[str, int | None, tuple[int, int, int] | None]:
    """Return a commit message, the number its real `Task:` line names (None without one) and its rounds."""
    decoy = rng.choice(TASK_NUMBERS)
    candidates = (
        ("why this change", rng.random() < 0.5),
        (f"see Task: T{decoy} for why", rng.random() < 0.4),
        (f"Task: X{decoy}", rng.random() < 0.3),
    )
    paragraphs = [paragraph for paragraph, is_wanted in candidates if is_wanted]
    rng.shuffle(paragraphs)
    number = rng.choice(TASK_NUMBERS) if rng.random() < 0.7 else None
    rounds = None
    if number is not None:
        task_paragraph = f"Task: T{'0' * rng.randint(0, 2)}{number}{rng.choice(TASK_LINE_ENDINGS)}"
        if rng.random() < 0.5:
            rounds = (rng.randint(0, 3), rng.randint(0, 3), rng.randint(0, 3))
            task_paragraph += f"\nRounds: spec {rounds[0]} · code {rounds[1]} · escalations {rounds[2]}"
        paragraphs.insert(rng.randint(0, len(paragraphs)), task_paragraph)
    message = f"feat: change {index}\n" + "".join(f"\n{paragraph}\n" for paragraph in paragraphs)
    return message, number, rounds


def _import_histories(root: Path, histories: dict[str, list[str]]) -> dict[tuple[str, int], str]:
    """Build one linear branch per history with a single `git fast-import`; map (branch, position) to sha.

    fast-import keeps each message byte for byte (no trailing-space cleanup) and costs one process
    for every history, where `git commit` would cost one per commit.
    """
    stream = bytearray()
    marks: dict[int, tuple[str, int]] = {}
    for branch, messages in histories.items():
        for position, message in enumerate(messages):
            mark = len(marks) + 1
            marks[mark] = (branch, position)
            data = message.encode("utf-8")
            stream += f"commit refs/heads/{branch}\nmark :{mark}\n".encode()
            stream += f"committer t <t@example.com> {1_700_000_000 + mark} +0000\n".encode()
            stream += f"data {len(data)}\n".encode() + data + b"\n"
    marks_file = root.parent / "marks.txt"
    subprocess.run(
        ["git", "fast-import", "--quiet", f"--export-marks={marks_file}"],
        cwd=root,
        input=bytes(stream),
        capture_output=True,
        check=True,
    )
    shas = {}
    for line in marks_file.read_text(encoding="utf-8").splitlines():
        mark_text, sha = line.split()
        shas[marks[int(mark_text.lstrip(":"))]] = sha
    return shas


@unittest.skipIf(shutil.which("git") is None, "Git is not installed")
class TaskCommitsTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name) / "repo"
        self.root.mkdir()
        git(self.root, "init", "-q")

    # R1.8, R1.9: only commits after the plan's base count, keyed by task number, with their rounds.
    def test_finds_task_commits_only_after_the_base_with_their_rounds(self) -> None:
        commit(self.root, "feat: an earlier feature's task\n\nTask: T1 · Covers: R9.9\n")
        base = commit(self.root, "docs(specs): plan the feature\n")
        t1 = commit(
            self.root,
            "feat: first task\n\nwhy\n\nTask: T01 · Covers: R1.8\nRounds: spec 1 · code 2 · escalations 0\n",
        )
        t10 = commit(self.root, "feat: tenth task\n\nTask: T10 · Covers: R1.9\n")
        t2 = commit(self.root, "feat: second task\n\nTask: T2 · Covers: R1.9\n")
        commit(self.root, "docs(specs): summarize slice S1\n\nTask: T1 · Covers: R1.8\n")

        found = task_commits(self.root, base)

        self.assertEqual(
            found,
            {
                "T1": TaskCommit(task_id="T1", sha=t1, rounds=(1, 2, 0)),
                "T2": TaskCommit(task_id="T2", sha=t2, rounds=None),
                "T10": TaskCommit(task_id="T10", sha=t10, rounds=None),
            },
        )
        with self.assertRaises(GitError):
            task_commits(self.root, "no-such-base")

    # R1.8, R1.9: over seeded linear histories, a commit counts for a task only when a real
    # `Task: T<n>` line of its body names that number and it comes after the base; the oldest wins.
    def test_a_commit_counts_for_a_task_only_when_its_task_line_names_it_in_the_range(self) -> None:
        histories: dict[str, list[str]] = {}
        facts: dict[str, list[tuple[int | None, tuple[int, int, int] | None]]] = {}
        base_positions: dict[str, int] = {}
        for seed in range(SEED_COUNT):
            rng = random.Random(seed)  # noqa: S311 - seeded for reproducible test data, not cryptography
            generated = [_random_message(rng, index) for index in range(rng.randint(1, 9))]
            base_position = rng.randint(0, len(generated))
            generated.insert(base_position, ("docs(specs): plan the feature\n", None, None))
            histories[f"seed{seed}"] = [message for message, _, _ in generated]
            facts[f"seed{seed}"] = [(number, rounds) for _, number, rounds in generated]
            base_positions[f"seed{seed}"] = base_position
        shas = _import_histories(self.root, histories)

        for branch, history in histories.items():
            (self.root / ".git" / "HEAD").write_text(f"ref: refs/heads/{branch}\n", encoding="utf-8")
            expected: dict[str, TaskCommit] = {}
            for position in range(base_positions[branch] + 1, len(history)):
                number, rounds = facts[branch][position]
                if number is not None and f"T{number}" not in expected:
                    sha = shas[(branch, position)]
                    expected[f"T{number}"] = TaskCommit(task_id=f"T{number}", sha=sha, rounds=rounds)

            found = task_commits(self.root, shas[(branch, base_positions[branch])])

            self.assertEqual(found, expected, f"{branch} (base at {base_positions[branch]}): {history!r}")


if __name__ == "__main__":
    unittest.main()
