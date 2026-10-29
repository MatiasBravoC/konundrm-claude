"""Classifies project files: test code, documentation, feature documents and tool artifacts.

The test-file lists mirror Standards → Tests ("What counts as a test file") word for word;
tests/test_file_kinds.py fails when the two drift apart.

Sections:
    TEST_DIRECTORIES, TEST_FILE_GLOBS — what counts as test code.
    is_test_path()           — test code, by directory or file name.
    is_documentation_path()  — prose files whose edits never need the quality check.
    is_feature_document()    — requirements.md, design.md and tasks.md of a specs/ feature.
    is_tool_artifact()       — caches, coverage and build output that tools write as a side effect.
"""

from __future__ import annotations

import re
from fnmatch import fnmatchcase
from pathlib import PurePosixPath

TEST_DIRECTORIES = frozenset({"tests", "test", "__tests__", "spec", "e2e", "__mocks__", "__snapshots__"})
TEST_FILE_GLOBS = ("test_*.py", "*_test.py", "conftest.py", "*.test.*", "*.spec.*", "*_test.go")

DOCUMENTATION_SUFFIXES = frozenset({".md", ".mdx", ".txt", ".rst", ".adoc"})
FEATURE_DOCUMENT = re.compile(r"^specs/\d{3}-[^/]+/(requirements|design|tasks)\.md$")

ARTIFACT_DIRECTORIES = frozenset(
    {
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".tox",
        ".venv",
        "htmlcov",
        ".nyc_output",
        "node_modules",
        ".stryker-tmp",
        ".hypothesis",  # Hypothesis example database, written whenever property tests run
    }
)
# Output folders only at the project root: deeper down, a folder named "build" can be source code.
ROOT_ARTIFACT_DIRECTORIES = frozenset({"coverage", "mutants", "reports", "dist", "build"})
ARTIFACT_FILE_GLOBS = (".coverage", ".coverage.*", "coverage.xml", "junit*.xml", "*.pyc", "*.tsbuildinfo")


def _parts(path: str) -> tuple[str, ...]:
    return PurePosixPath(path.replace("\\", "/")).parts


def is_test_path(path: str) -> bool:
    """Tells whether a project-relative path is test code.

    Args:
        path: Path relative to the project root; either slash style.

    Returns:
        True for files inside a test directory or named like a test file.
    """
    parts = _parts(path)
    if not parts:
        return False
    if any(part.lower() in TEST_DIRECTORIES for part in parts[:-1]):
        return True
    return any(fnmatchcase(parts[-1], pattern) for pattern in TEST_FILE_GLOBS)


def is_documentation_path(path: str) -> bool:
    """Tells whether a path is prose (Markdown, text) rather than code or configuration."""
    return PurePosixPath(path.replace("\\", "/")).suffix.lower() in DOCUMENTATION_SUFFIXES


def is_feature_document(path: str) -> bool:
    """Tells whether a project-relative path is one of a feature's spec, design or task files."""
    return bool(FEATURE_DOCUMENT.match(path.replace("\\", "/")))


def is_tool_artifact(path: str) -> bool:
    """Tells whether a path is output that tools write as a side effect of running.

    Running tests or the check creates caches and coverage files when the project's .gitignore
    misses them; such files are not authored changes.
    """
    parts = _parts(path)
    if not parts:
        return False
    if len(parts) > 1 and parts[0] in ROOT_ARTIFACT_DIRECTORIES:
        return True
    if any(part in ARTIFACT_DIRECTORIES for part in parts[:-1]):
        return True
    return any(fnmatchcase(parts[-1], pattern) for pattern in ARTIFACT_FILE_GLOBS)
