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


# What binds a name at module level for T72: assignments (plain, annotated with a value, augmented), `def`, `async def`,
# `class` and imports. Branches of a top-level `if`, `try` or `match` are alternatives, so a later branch's first
# binding of a name an earlier branch bound stands in for it and replaces nothing; a name bound twice inside one branch,
# or both inside and outside the statement, is a replacement. A binding is `(name, line, is_alternative)`.
_ONCE_DEFINITIONS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


def _once_assigned_names(node: ast.stmt) -> list[str]:
    """Return the names a simple module-level statement binds, in order, or [] when it binds none."""
    if isinstance(node, _ONCE_DEFINITIONS):
        return [node.name]
    if isinstance(node, ast.Import | ast.ImportFrom):
        return [alias.asname or alias.name for alias in node.names if alias.name != "*"]
    if isinstance(node, ast.Assign | ast.AugAssign) or (isinstance(node, ast.AnnAssign) and node.value is not None):
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        return [
            name.id
            for target in targets
            for name in ast.walk(target)
            if isinstance(name, ast.Name) and isinstance(name.ctx, ast.Store)
        ]
    return []


def _once_alternatives(branches: list[list[ast.stmt]]) -> list[tuple[str, int, bool]]:
    """Return the bindings of alternative branches in source order, marking the ones that only stand in for another.

    A later branch's first binding of a name an earlier branch bound is marked as an alternative: only one of the two
    runs. Its further bindings of that name keep their mark, so a repeat inside the later branch is still a replacement.
    """
    bound_by_earlier: set[str] = set()
    bindings = []
    for branch in branches:
        bound_in_branch: set[str] = set()
        for name, line, is_alternative in _once_bindings(branch):
            stands_in = name in bound_by_earlier and name not in bound_in_branch
            bindings.append((name, line, is_alternative or stands_in))
            bound_in_branch.add(name)
        bound_by_earlier |= bound_in_branch
    return bindings


def _once_statement_bindings(node: ast.stmt) -> list[tuple[str, int, bool]]:
    """Return `(name, line, is_alternative)` for each module-level name one top-level statement binds."""
    if isinstance(node, ast.If):
        return _once_alternatives([node.body, node.orelse])
    if isinstance(node, ast.Try):
        handlers = [handler.body for handler in node.handlers]
        return _once_alternatives([node.body + node.orelse, *handlers]) + _once_bindings(node.finalbody)
    if isinstance(node, ast.Match):
        return _once_alternatives([case.body for case in node.cases])
    return [(name, node.lineno, False) for name in _once_assigned_names(node)]


def _once_bindings(statements: list[ast.stmt]) -> list[tuple[str, int, bool]]:
    """Return `(name, line, is_alternative)` for each module-level binding of a block of statements, in source order."""
    return [binding for node in statements for binding in _once_statement_bindings(node)]


def _once_duplicates(path: Path) -> list[str]:
    """Return one message per module-level binding of a contract module that replaces an earlier one of its name.

    Each message names the file, the name, the line of the binding replaced and the line replacing it, since the second
    silently replaces the first and the test that used it can no longer fail.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    last_lines: dict[str, int] = {}
    duplicates = []
    for name, line, is_alternative in _once_bindings(tree.body):
        if name in last_lines and not is_alternative:
            duplicates.append(
                f"{path.name}: `{name}` is defined on line {last_lines[name]} and again on line {line},"
                " which replaces the first"
            )
        last_lines[name] = line
    return duplicates


class ContractTestsDefineEachNameOnceTest(unittest.TestCase):
    maxDiff = None

    def test_contract_tests_define_each_module_name_once(self) -> None:
        """R10.2: no contract module defines a module-level name twice, so no test loses the helper it checks with.

        A second assignment, `def`, `class` or import of a name replaces the first in silence (T27's second `_RECORDS`
        left T19's test unable to fail). Every Python module of the contract package is read, this one included.
        """
        modules = sorted(CONTRACT_DIR.glob("*.py"))

        duplicates = [duplicate for module in modules for duplicate in _once_duplicates(module)]

        self.assertIn(Path(__file__).resolve(), modules)
        self.assertEqual(duplicates, [])
