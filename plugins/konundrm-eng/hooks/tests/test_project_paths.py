"""Unit tests for hooks/scripts/project_paths.py."""

from __future__ import annotations

import os
import random
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from project_paths import project_root, relative_path


class RelativePathTest(unittest.TestCase):
    def test_expresses_inside_paths_relative_to_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(relative_path(str(root / "src" / "a.py"), root), "src/a.py")

    def test_keeps_relative_paths_with_forward_slashes(self) -> None:
        self.assertEqual(relative_path("src\\pkg\\a.py", Path(".")), "src/pkg/a.py")

    def test_returns_none_for_paths_outside_the_project(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as other:
            self.assertIsNone(relative_path(str(Path(other) / "a.py"), Path(tmp)))


class ProjectRootTest(unittest.TestCase):
    def test_prefers_the_project_directory_claude_code_exports(self) -> None:
        with mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": "/work/app"}):
            self.assertEqual(project_root({"cwd": "/elsewhere"}), Path("/work/app"))

    def test_falls_back_to_the_event_cwd_outside_git(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CLAUDE_PROJECT_DIR", None)
            self.assertEqual(project_root({"cwd": tmp}).resolve(), Path(tmp).resolve())

    def test_project_root_is_the_worktree_the_session_works_in(self) -> None:
        # R3.3: a parallel partition's session works in its own worktree outside the project
        # folder, so its gates must check that worktree rather than the main checkout. The
        # project folder may be the repository root or a package inside it (a monorepo), and it
        # may itself sit in a linked worktree.
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp).resolve()
            main, worktree, worktree2 = base / "main", base / "worktree", base / "worktree2"
            outside = base / "outside"
            _make_repository_with_linked_worktrees(main, worktree, worktree2)
            outside.mkdir()
            zones = {"worktree": worktree, "main": main, "outside": outside}
            explicit = [
                ("worktree", worktree),
                ("worktree", worktree / "app"),
                ("main", main),
                ("main", main / "app"),
                ("outside", outside),
                ("worktree2", worktree2),
                ("worktree2", worktree2 / "app"),
            ]
            rng = random.Random(17)  # noqa: S311 - seeded for reproducible test data, not cryptography
            generated = []
            for index in range(40):
                name = rng.choice(sorted(zones))
                folder = zones[name]
                for level in range(rng.randint(0, 3)):
                    folder = folder / f"d{index}_{level}_{rng.randint(0, 99)}"
                folder.mkdir(parents=True, exist_ok=True)
                generated.append((name, folder))
            # (checkout holding CLAUDE_PROJECT_DIR, zone of the cwd) -> expected root. None keeps
            # CLAUDE_PROJECT_DIR: the cwd is in the main checkout, outside the repository, or in
            # the same checkout as the project folder. A linked worktree that is another checkout
            # moves the root to its top level.
            expected_roots = {
                ("main", "main"): None,
                ("main", "worktree"): worktree,
                ("main", "worktree2"): worktree2,
                ("main", "outside"): None,
                ("worktree", "main"): None,
                ("worktree", "worktree"): None,
                ("worktree", "worktree2"): worktree2,
                ("worktree", "outside"): None,
            }
            project_dirs = [
                ("main", "main", main),
                ("main", "main/app", main / "app"),
                ("worktree", "worktree", worktree),
                ("worktree", "worktree/app", worktree / "app"),
            ]
            for checkout, project_dir_choice, project_dir in project_dirs:
                with mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(project_dir)}):
                    for name, cwd in explicit + generated:
                        with self.subTest(project_dir=project_dir_choice, zone=name, cwd=str(cwd)):
                            expected = expected_roots[(checkout, name)] or project_dir
                            root = project_root({"cwd": str(cwd)})
                            self.assertEqual(root.resolve(), expected.resolve())


def _run_git(args: list[str], cwd: Path) -> None:
    """Runs git isolated from the machine's system and global configuration."""
    env = dict(os.environ, GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=str(cwd / ".no-global-gitconfig"))
    subprocess.run(
        ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", *args],
        cwd=cwd,
        env=env,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )


def _make_repository_with_linked_worktrees(main: Path, *worktrees: Path) -> None:
    """Creates a repository with one commit at main, holding an app/ package, and a linked worktree at each path."""
    main.mkdir()
    _run_git(["init", "-q", "-b", "main"], main)
    (main / "README.md").write_text("seed", encoding="utf-8")
    (main / "app").mkdir()
    (main / "app" / "README.md").write_text("package", encoding="utf-8")
    _run_git(["add", "README.md", "app/README.md"], main)
    _run_git(["commit", "-q", "-m", "seed"], main)
    for number, worktree in enumerate(worktrees, start=1):
        _run_git(["worktree", "add", "-q", "-b", f"partition{number}", str(worktree)], main)


if __name__ == "__main__":
    unittest.main()
