"""Unit tests for hooks/scripts/audit_subagent_changes.py."""

from __future__ import annotations

import contextlib
import io
import json
import os
import random
import subprocess
import sys
import tempfile
import unittest
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from audit_subagent_changes import Violation, find_violations, on_start, on_stop, restore_instructions
from hook_state import SubagentRecord
from working_tree import snapshot_tree

IMPLEMENTER = "konundrm-eng:implementer"
CHANGE_KINDS = ("none", "violation", "allowed")
OTHER_CHECKOUT = {"main": "worktree", "worktree": "main"}


class FindViolationsTest(unittest.TestCase):
    def test_flags_test_changes_made_by_the_implementer(self) -> None:
        violations = find_violations("implementer", [("M", "src/a.py"), ("M", "tests/test_a.py")])
        self.assertEqual([(v.status, v.path) for v in violations], [("M", "tests/test_a.py")])

    def test_flags_production_changes_made_by_the_test_writer(self) -> None:
        violations = find_violations("test-writer", [("A", "tests/test_b.py"), ("A", "src/b.py")])
        self.assertEqual([v.path for v in violations], ["src/b.py"])

    def test_flags_any_change_made_by_a_reviewer(self) -> None:
        self.assertEqual(len(find_violations("code-reviewer", [("D", "src/a.py"), ("M", "tests/t.py")])), 2)

    def test_ignores_tool_artifacts_such_as_coverage_files(self) -> None:
        changes = [("A", ".coverage"), ("M", "src/pkg/__pycache__/a.pyc"), ("A", "coverage/lcov.info")]
        self.assertEqual(find_violations("spec-reviewer", changes), [])


class RestoreInstructionsTest(unittest.TestCase):
    def test_lists_each_file_with_the_command_that_restores_it(self) -> None:
        message = restore_instructions(
            "implementer",
            "abc123",
            [Violation("M", "tests/test_a.py", "not yours"), Violation("A", "tests/test_new.py", "not yours")],
        )
        self.assertIn("tests/test_a.py (modified): not yours", message)
        self.assertIn('git restore --source=abc123 --worktree -- "tests/test_a.py"', message)
        self.assertIn('rm -- "tests/test_new.py"', message)


class AuditRootTest(unittest.TestCase):
    def test_audit_restores_only_in_the_tree_it_snapshotted(self) -> None:
        # R3.3 (threat "Sesión en un worktree → gates del plugin"): when a subagent's SubagentStart
        # and SubagentStop resolve different checkouts of one repository, the audit compares and
        # restores only in the checkout it snapshotted at start. The two checkouts already differ
        # in test and production files, so comparing one with the other's snapshot would block an
        # implementer that changed nothing and then restore or delete files in the wrong tree.
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp).resolve()
            trees = {"main": base / "main", "worktree": base / "worktree"}
            git_env = {"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": str(base / "no-global-gitconfig")}
            _make_diverging_checkouts(trees["main"], trees["worktree"], git_env)
            # (start checkout, stop checkout, what the subagent changes in the start checkout)
            explicit = [
                ("main", "worktree", "none"),
                ("worktree", "main", "none"),
                ("main", "main", "violation"),
                ("worktree", "worktree", "violation"),
                ("main", "main", "allowed"),
                ("worktree", "main", "violation"),
            ]
            rng = random.Random(23)  # noqa: S311 - seeded for reproducible test data, not cryptography
            generated = [
                (rng.choice(sorted(trees)), rng.choice(sorted(trees)), rng.choice(CHANGE_KINDS)) for _ in range(10)
            ]
            hook_env = {**git_env, "CLAUDE_PLUGIN_DATA": str(base / "plugin-data")}
            with mock.patch.dict(os.environ, hook_env):
                os.environ.pop("CLAUDE_PROJECT_DIR", None)  # each event's cwd resolves to its own checkout
                for number, (start, stop, change) in enumerate(explicit + generated):
                    with self.subTest(case=number, start=start, stop=stop, change=change):
                        start_root, other_root = trees[start], trees[OTHER_CHECKOUT[start]]
                        before_start, before_other = _file_contents(start_root), _file_contents(other_root)

                        _run_hook(on_start, _event("SubagentStart", number, start_root))
                        _make_subagent_change(start_root, change, number)
                        after_change = _file_contents(start_root)
                        first_stop = _run_hook(on_stop, _event("SubagentStop", number, trees[stop]))
                        _run_hook(on_stop, _event("SubagentStop", number, trees[stop]))

                        self.assertEqual(first_stop.get("decision") == "block", change == "violation")
                        self.assertEqual(_file_contents(other_root), before_other)
                        expected_start = after_change if change == "allowed" else before_start
                        self.assertEqual(_file_contents(start_root), expected_start)

    def test_a_record_without_its_root_is_dropped_unaudited(self) -> None:
        # R3.3 (threat "Sesión en un worktree → gates del plugin"): a record an older plugin version
        # saved has a role and a snapshot but no root. Guessing the root from the stop event could
        # compare and restore in another checkout, so the audit drops the record and checks nothing,
        # even when the event's checkout holds a change that would block an audit of that root.
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp).resolve()
            main, worktree = base / "main", base / "worktree"
            git_env = {"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": str(base / "no-global-gitconfig")}
            _make_diverging_checkouts(main, worktree, git_env)
            hook_env = {**git_env, "CLAUDE_PLUGIN_DATA": str(base / "plugin-data")}
            with mock.patch.dict(os.environ, hook_env):
                os.environ.pop("CLAUDE_PROJECT_DIR", None)
                legacy = SubagentRecord("session-t70", "agent-0")
                legacy.role, legacy.before_tree, legacy.blocks = "implementer", snapshot_tree(main), 0
                legacy.save()
                saved = SubagentRecord("session-t70", "agent-0")
                # Saved with a valid snapshot, so only the missing root keeps the audit from running.
                self.assertEqual((saved.role, saved.root, saved.before_tree), ("implementer", None, legacy.before_tree))
                self.assertIsNotNone(saved.before_tree)
                _make_subagent_change(main, "violation", 0)
                before_main, before_worktree = _file_contents(main), _file_contents(worktree)

                output = _run_hook(on_stop, _event("SubagentStop", 0, main))

                self.assertEqual(output, {})
                self.assertEqual(_file_contents(main), before_main)
                self.assertEqual(_file_contents(worktree), before_worktree)
                self.assertIsNone(SubagentRecord("session-t70", "agent-0").role)


def _event(name: str, number: int, cwd: Path) -> dict[str, Any]:
    """Builds a SubagentStart or SubagentStop event for one implementer subagent."""
    return {
        "hook_event_name": name,
        "session_id": "session-t70",
        "agent_id": f"agent-{number}",
        "agent_type": IMPLEMENTER,
        "cwd": str(cwd),
    }


def _run_hook(handler: Callable[[dict[str, Any]], int], event: dict[str, Any]) -> dict[str, Any]:
    """Runs a hook handler and returns the JSON it printed, or an empty dict when it printed nothing."""
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        handler(event)
    text = output.getvalue()
    return json.loads(text) if text else {}


def _make_subagent_change(root: Path, change: str, number: int) -> None:
    """Changes the checkout as an implementer would: a test file (violation) or a production file (allowed)."""
    if change == "violation" and number % 2:
        (root / "tests" / f"test_added_{number}.py").write_bytes(b"def test_added():\n    assert True\n")
    elif change == "violation":
        with (root / "tests" / "test_shared.py").open("ab") as shared:
            shared.write(f"# edited by agent {number}\n".encode())
    elif change == "allowed":
        (root / "src" / f"feature_{number}.py").write_bytes(f"FEATURE = {number}\n".encode())


def _file_contents(root: Path) -> dict[str, bytes]:
    """Maps every file in a checkout, outside its Git metadata, to its bytes."""
    contents = {}
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if relative.parts[0] != ".git" and path.is_file():
            contents[relative.as_posix()] = path.read_bytes()
    return contents


def _git(args: list[str], cwd: Path, env: dict[str, str]) -> None:
    """Runs git isolated from the machine's system and global configuration."""
    subprocess.run(
        ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", *args],
        cwd=cwd,
        env={**os.environ, **env},
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )


def _make_diverging_checkouts(main: Path, worktree: Path, env: dict[str, str]) -> None:
    """Creates a repository at main and a linked worktree, then makes their test and production files differ."""
    main.mkdir()
    _git(["init", "-q", "-b", "main"], main, env)
    seed = {
        "README.md": b"seed\n",
        "src/app.py": b"VALUE = 1\n",
        "tests/test_shared.py": b"def test_shared():\n    assert True\n",
    }
    for relative, content in seed.items():
        (main / relative).parent.mkdir(parents=True, exist_ok=True)
        (main / relative).write_bytes(content)
    _git(["add", "--all"], main, env)
    _git(["commit", "-q", "-m", "seed"], main, env)
    _git(["worktree", "add", "-q", "-b", "partition", str(worktree)], main, env)
    # Two partitions mid-wave: each checkout holds work the other does not.
    (main / "src" / "app.py").write_bytes(b"VALUE = 2\n")
    (main / "tests" / "test_main_only.py").write_bytes(b"def test_main_only():\n    assert True\n")
    (worktree / "tests" / "test_shared.py").write_bytes(b"def test_shared():\n    assert 1 == 1\n")
    (worktree / "tests" / "test_worktree_only.py").write_bytes(b"def test_worktree_only():\n    assert True\n")


if __name__ == "__main__":
    unittest.main()
