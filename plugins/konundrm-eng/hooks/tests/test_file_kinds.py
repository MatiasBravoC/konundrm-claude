"""Unit tests for hooks/scripts/file_kinds.py."""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import file_kinds

STANDARDS = Path(__file__).resolve().parents[2] / "skills" / "engineering-standards" / "SKILL.md"


def _backticked_items(line_prefix: str) -> list[str]:
    for line in STANDARDS.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith(line_prefix):
            return re.findall(r"`([^`]+)`", line)
    raise AssertionError(f"No line starting with {line_prefix!r} in {STANDARDS}")


class StandardsSyncTest(unittest.TestCase):
    def test_test_directories_match_the_engineering_standards(self) -> None:
        documented = {item.rstrip("/") for item in _backticked_items("- Directories:")}
        self.assertEqual(documented, set(file_kinds.TEST_DIRECTORIES))

    def test_test_file_globs_match_the_engineering_standards(self) -> None:
        self.assertEqual(_backticked_items("- File names:"), list(file_kinds.TEST_FILE_GLOBS))


class IsTestPathTest(unittest.TestCase):
    def test_accepts_files_inside_test_directories(self) -> None:
        for path in (
            "tests/billing/test_x.py",
            "src/__tests__/Card.tsx",
            "e2e/login.ts",
            "tests/__init__.py",
            "src/__snapshots__/Card.test.tsx.snap",
            "src/__mocks__/api.ts",
        ):
            with self.subTest(path=path):
                self.assertTrue(file_kinds.is_test_path(path))

    def test_accepts_test_file_name_patterns(self) -> None:
        for path in ("test_api.py", "api_test.py", "conftest.py", "src/a.test.tsx", "src/a.spec.ts", "pkg/a_test.go"):
            with self.subTest(path=path):
                self.assertTrue(file_kinds.is_test_path(path))

    def test_accepts_windows_separators(self) -> None:
        self.assertTrue(file_kinds.is_test_path("src\\tests\\test_a.py"))

    def test_rejects_production_and_spec_documents(self) -> None:
        for path in (
            "src/billing.py",
            "src/testing_utils.py",
            "specs/001-login/tasks.md",
            "latest.py",
            "Test_a.py",
            "",
        ):
            with self.subTest(path=path):
                self.assertFalse(file_kinds.is_test_path(path))


class IsDocumentationPathTest(unittest.TestCase):
    def test_classifies_prose_by_extension(self) -> None:
        self.assertTrue(file_kinds.is_documentation_path("docs/Guide.MD"))
        self.assertTrue(file_kinds.is_documentation_path("notes.txt"))
        self.assertFalse(file_kinds.is_documentation_path("src/a.py"))
        self.assertFalse(file_kinds.is_documentation_path("package.json"))


class IsFeatureDocumentTest(unittest.TestCase):
    def test_accepts_the_three_documents_of_a_numbered_feature(self) -> None:
        for name in ("requirements", "design", "tasks"):
            with self.subTest(name=name):
                self.assertTrue(file_kinds.is_feature_document(f"specs/003-google-login/{name}.md"))

    def test_rejects_other_files_and_folders(self) -> None:
        for path in ("specs/003-google-login/notes.md", "specs/tasks.md", "docs/003-x/design.md", "spec/design.md"):
            with self.subTest(path=path):
                self.assertFalse(file_kinds.is_feature_document(path))


class IsToolArtifactTest(unittest.TestCase):
    def test_accepts_caches_and_coverage_output(self) -> None:
        for path in (
            ".coverage",
            "coverage.xml",
            "src/pkg/__pycache__/a.cpython-313.pyc",
            ".pytest_cache/v/cache/lastfailed",
            ".hypothesis/examples/1a2b/3c4d",
            "coverage/cobertura-coverage.xml",
            "node_modules/x/index.js",
        ):
            with self.subTest(path=path):
                self.assertTrue(file_kinds.is_tool_artifact(path))

    def test_root_only_output_folders_do_not_hide_nested_source(self) -> None:
        self.assertTrue(file_kinds.is_tool_artifact("build/lib/a.py"))
        self.assertFalse(file_kinds.is_tool_artifact("src/build/compiler.py"))
        self.assertFalse(file_kinds.is_tool_artifact("src/coverage/report.ts"))

    def test_rejects_source_and_tests(self) -> None:
        for path in ("src/a.py", "tests/test_a.py", "build", ""):
            with self.subTest(path=path):
                self.assertFalse(file_kinds.is_tool_artifact(path))


if __name__ == "__main__":
    unittest.main()
