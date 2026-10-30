"""Contract tests about the contract tests themselves: each one names the agreement it protects."""

from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path

CONTRACT_DIR = Path(__file__).resolve().parent

# The first line of a contract test's docstring, which unittest prints after `FAIL:`, starts with the requirement IDs
# it protects and a colon: `R1.7: ...` or `R1.2, R1.3, R1.4: ...` (tasks.md's convention).
_NAMES_REQUIREMENTS = re.compile(r"R\d+\.\d+(?:, R\d+\.\d+)*: \S")

# What `unittest discover` loads by default: modules named `test*.py` and, in their TestCase classes, `test*` methods.
_DISCOVERED_MODULE = re.compile(r"test.*\.py")
_TEST_PREFIX = "test"


def _first_docstring_line(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """Return the first line of a function's docstring as `TestCase.shortDescription` does, or "" without one."""
    doc = ast.get_docstring(node, clean=False)
    return doc.strip().split("\n")[0].strip() if doc else ""


def _is_test_case(node: ast.ClassDef, test_case_names: set[str]) -> bool:
    """Return whether a class derives from `unittest.TestCase`, directly or through a TestCase of the same module."""
    for base in node.bases:
        name = base.attr if isinstance(base, ast.Attribute) else base.id if isinstance(base, ast.Name) else ""
        if name in test_case_names:
            return True
    return False


def _requirement_gaps(path: Path) -> list[str]:
    """Return one gap per test in a contract module that the check would not run or that names no requirement.

    A test is any function whose name starts with `test`. It is a gap when unittest discovery would not run it (the
    module is not named `test*.py`, or the function is not a method of a module-level TestCase class) or when the first
    line of its docstring does not start with the requirement IDs it protects. Each gap names the file and the test.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    is_discovered_module = _DISCOVERED_MODULE.fullmatch(path.name) is not None
    test_case_names = {"TestCase"}
    run_tests: set[ast.AST] = set()
    gaps = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and _is_test_case(node, test_case_names):
            test_case_names.add(node.name)
            if is_discovered_module:
                run_tests.update(item for item in node.body if isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef))
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) or not node.name.startswith(_TEST_PREFIX):
            continue
        if node not in run_tests:
            gaps.append(f"{path.name}::{node.name}: unittest discovery does not run it, so the check ignores it")
        elif not _NAMES_REQUIREMENTS.match(_first_docstring_line(node)):
            gaps.append(
                f"{path.name}::{node.name}: the first line of its docstring does not start with the requirement IDs"
                " it protects (`R1.2: ...` or `R1.2, R1.3: ...`)"
            )
    return gaps


class ContractTestsNameTheirRequirementsTest(unittest.TestCase):
    maxDiff = None

    def test_every_contract_test_names_its_requirements(self) -> None:
        """R10.2: every contract test runs in the check and names the requirements it protects when it fails.

        unittest prints a failing test's name and the first line of its docstring, so that line must start with the
        requirement IDs (`R1.7: ...`). Every Python module of the contract package is read, this one included, so a
        test added later is held to the same rule.
        """
        modules = sorted(CONTRACT_DIR.glob("*.py"))

        gaps = [gap for module in modules for gap in _requirement_gaps(module)]

        self.assertIn(Path(__file__).resolve(), modules)
        self.assertEqual(gaps, [])
