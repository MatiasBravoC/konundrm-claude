"""Unit tests for hooks/scripts/project_paths.py."""

from __future__ import annotations

import os
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


if __name__ == "__main__":
    unittest.main()
