"""Unit tests for hooks/scripts/working_tree.py (they run Git in temporary repositories)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from working_tree import AddedLine, added_lines, changed_paths, head_tree, restore_paths, snapshot_tree


def git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout


@unittest.skipIf(shutil.which("git") is None, "Git is not installed")
class WorkingTreeTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        git(self.root, "init", "-q")
        (self.root / ".gitignore").write_text("ignored/\n")
        (self.root / "a.txt").write_text("one\n")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "init")

    def test_returns_none_outside_a_git_repository(self) -> None:
        with tempfile.TemporaryDirectory() as plain:
            self.assertIsNone(snapshot_tree(Path(plain)))

    def test_same_content_gives_the_same_snapshot_even_after_committing(self) -> None:
        (self.root / "b.txt").write_text("new\n")
        before = snapshot_tree(self.root)
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "add b")
        self.assertEqual(snapshot_tree(self.root), before)

    def test_sees_a_same_size_edit_made_in_the_same_clock_tick_as_the_index(self) -> None:
        source = self.root / "a.txt"
        tick = (source.stat().st_mtime_ns // 10**9 - 10) * 10**9  # a whole second, 10 s ago
        os.utime(source, ns=(tick, tick))
        git(self.root, "add", "a.txt")  # records the entry while it is not "racy", so Git keeps its stat
        os.utime(self.root / ".git" / "index", ns=(tick, tick))  # as if the index was written in that tick
        before = snapshot_tree(self.root)
        source.write_text("two\n")  # same size as "one\n"
        os.utime(source, ns=(tick, tick))  # and the same tick: only the content tells them apart
        self.assertNotEqual(snapshot_tree(self.root), before)

    def test_a_project_inside_a_larger_repository_sees_and_restores_its_own_paths(self) -> None:
        package = self.root / "packages" / "app"
        (package / "tests").mkdir(parents=True)
        (package / "tests" / "test_x.py").write_text("original\n")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "add package")
        before = snapshot_tree(package) or ""
        (package / "tests" / "test_x.py").write_text("changed\n")
        (package / "new.py").write_text("created\n")
        (self.root / "a.txt").write_text("outside the project\n")
        changes = changed_paths(package, before, snapshot_tree(package) or "")
        self.assertEqual(sorted(changes), [("A", "new.py"), ("M", "tests/test_x.py")])
        self.assertEqual(restore_paths(package, before, changes), [])
        self.assertEqual((package / "tests" / "test_x.py").read_text(), "original\n")
        self.assertFalse((package / "new.py").exists())

    def test_does_not_touch_the_real_index(self) -> None:
        (self.root / "b.txt").write_text("new\n")
        snapshot_tree(self.root)
        self.assertEqual(git(self.root, "diff", "--cached", "--name-only"), "")

    def test_lists_added_modified_and_deleted_files_but_not_ignored_ones(self) -> None:
        before = snapshot_tree(self.root)
        (self.root / "a.txt").write_text("two\n")
        (self.root / "b.txt").write_text("new\n")
        (self.root / "ignored").mkdir()
        (self.root / "ignored" / "x.txt").write_text("x\n")
        after = snapshot_tree(self.root)
        self.assertEqual(sorted(changed_paths(self.root, before or "", after or "")), [("A", "b.txt"), ("M", "a.txt")])
        (self.root / "a.txt").unlink()
        self.assertIn(("D", "a.txt"), changed_paths(self.root, before or "", snapshot_tree(self.root) or ""))

    def test_restores_files_to_an_earlier_snapshot(self) -> None:
        (self.root / "draft.txt").write_text("uncommitted\n")
        before = snapshot_tree(self.root) or ""
        (self.root / "a.txt").write_text("two\n")
        (self.root / "draft.txt").unlink()
        (self.root / "b.txt").write_text("new\n")
        changes = changed_paths(self.root, before, snapshot_tree(self.root) or "")
        self.assertEqual(restore_paths(self.root, before, changes), [])
        self.assertEqual((self.root / "a.txt").read_text(), "one\n")
        self.assertEqual((self.root / "draft.txt").read_text(), "uncommitted\n")
        self.assertFalse((self.root / "b.txt").exists())
        self.assertEqual(snapshot_tree(self.root), before)

    def test_head_tree_matches_a_snapshot_of_the_committed_files(self) -> None:
        self.assertEqual(head_tree(self.root), snapshot_tree(self.root))

    def test_head_tree_is_the_empty_tree_before_the_first_commit(self) -> None:
        with tempfile.TemporaryDirectory() as fresh:
            git(Path(fresh), "init", "-q")
            (Path(fresh) / "a.py").write_text("x = 1\n")
            empty = head_tree(Path(fresh)) or ""
            self.assertEqual(changed_paths(Path(fresh), empty, snapshot_tree(Path(fresh)) or ""), [("A", "a.py")])

    def test_head_tree_is_none_outside_a_git_repository(self) -> None:
        with tempfile.TemporaryDirectory() as plain:
            self.assertIsNone(head_tree(Path(plain)))

    def test_added_lines_lists_new_and_modified_lines_with_their_numbers(self) -> None:
        (self.root / "a.txt").write_text("one\ntwo\nthree\n")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "three lines")
        before = snapshot_tree(self.root) or ""
        (self.root / "a.txt").write_text("one\nTWO\nthree\nfour\n")
        (self.root / "b.py").write_text("x = 1\n")
        added = added_lines(self.root, before, snapshot_tree(self.root) or "")
        self.assertEqual(
            added,
            [AddedLine("a.txt", 2, "TWO"), AddedLine("a.txt", 4, "four"), AddedLine("b.py", 1, "x = 1")],
        )

    def test_added_lines_reads_content_that_looks_like_a_diff_header(self) -> None:
        before = snapshot_tree(self.root) or ""
        (self.root / "a.txt").write_text("one\n++ not a header\n--- nor this\n")
        added = added_lines(self.root, before, snapshot_tree(self.root) or "")
        self.assertEqual(added, [AddedLine("a.txt", 2, "++ not a header"), AddedLine("a.txt", 3, "--- nor this")])

    def test_added_lines_keeps_unusual_file_names(self) -> None:
        before = snapshot_tree(self.root) or ""
        (self.root / "naïve file.py").write_text("y = 2\n")
        added = added_lines(self.root, before, snapshot_tree(self.root) or "")
        self.assertEqual(added, [AddedLine("naïve file.py", 1, "y = 2")])

    def test_added_lines_ignores_deletions_and_identical_snapshots(self) -> None:
        before = snapshot_tree(self.root) or ""
        self.assertEqual(added_lines(self.root, before, before), [])
        (self.root / "a.txt").unlink()
        self.assertEqual(added_lines(self.root, before, snapshot_tree(self.root) or ""), [])


if __name__ == "__main__":
    unittest.main()
