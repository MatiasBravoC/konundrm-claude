"""Unit tests for hooks/scripts/audit_subagent_changes.py."""

from __future__ import annotations

import contextlib
import io
import json
import os
import random
import shlex
import subprocess
import sys
import tempfile
import unittest
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from audit_subagent_changes import Violation, find_violations, on_start, on_stop, restore_instructions
from hook_state import SubagentRecord
from working_tree import snapshot_tree

IMPLEMENTER = "konundrm-eng:implementer"
SPEC_REVIEWER = "konundrm-eng:spec-reviewer"
CODE_REVIEWER = "konundrm-eng:code-reviewer"
SECURITY_REVIEWER = "konundrm-eng:security-reviewer"
REVIEWER_TYPES = (SPEC_REVIEWER, CODE_REVIEWER, SECURITY_REVIEWER)
SEED_FILES = {
    "README.md": b"seed\n",
    "src/app.py": b"VALUE = 1\n",
    "src/util.py": b"def helper():\n    return 1\n",
    "tests/test_app.py": b"def test_app():\n    pass\n",
}
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


class ConcurrentReviewersTest(unittest.TestCase):
    def test_restores_a_reviewers_change_whatever_order_concurrent_reviewers_stop(self) -> None:
        # R3.6: two reviewers start before one of them changes a file. Whichever stops first sees
        # the change and is blocked; once it stops again the hook restores the file, so the tree
        # ends as it was before both started, in either order of stopping.
        with _reviewer_repository() as (root, _):
            for number, (change, changer_stops_first) in enumerate(
                [("modify", True), ("modify", False), ("create", True), ("create", False)]
            ):
                with self.subTest(change=change, changer_stops_first=changer_stops_first):
                    changer = (f"agent-spec-{number}", SPEC_REVIEWER)
                    other = (f"agent-code-{number}", CODE_REVIEWER)
                    before = _file_contents(root)
                    for agent_id, agent_type in (changer, other):
                        _run_hook(on_start, _reviewer_event("SubagentStart", agent_id, agent_type, root))
                    _make_reviewer_change(root, change, number)

                    stop_order = [changer, other] if changer_stops_first else [other, changer]
                    first_stops = [
                        _stop_until_allowed(agent_id, agent_type, root) for agent_id, agent_type in stop_order
                    ]

                    self.assertTrue(first_stops[0])  # the first stop saw the change and was blocked
                    self.assertEqual(_file_contents(root), before)
                    for agent_id, _ in (changer, other):
                        self.assertIsNone(SubagentRecord("session-t70", agent_id).role)

    def test_concurrent_reviewers_leave_the_tree_as_it_started_in_any_stop_order(self) -> None:
        # R3.6, T23 invariant: whatever reviewers run together, whichever of them makes the changes
        # (modify, create or delete, anywhere in the tree) and whatever order they stop in, every
        # file ends as it was before they started and no reviewer's record is left behind. The
        # generator makes every change before the first stop and retries a blocked stop at once;
        # the explicit tests below cover the shapes it leaves out.
        with _reviewer_repository() as (root, git_env):
            for seed in range(6):  # about 0.6 s per seed; this suite runs in every check
                scenario = _generate_reviewer_scenario(seed)
                with self.subTest(seed=seed, scenario=scenario):
                    if _file_contents(root) != SEED_FILES:  # an earlier failed seed left changes behind
                        _git(["checkout", "--", "."], root, git_env)
                        _git(["clean", "-fdq"], root, git_env)
                    before = _file_contents(root)
                    for agent_id, agent_type in scenario.reviewers:
                        _run_hook(on_start, _reviewer_event("SubagentStart", agent_id, agent_type, root))
                    for _, kind, path in scenario.changes:
                        _apply_change(root, kind, path)

                    first_stops = [_stop_until_allowed(*scenario.reviewers[index], root) for index in scenario.stops]

                    self.assertTrue(first_stops[0])  # every scenario makes at least one change
                    self.assertEqual(_file_contents(root), before)
                    for agent_id, _ in scenario.reviewers:
                        self.assertIsNone(SubagentRecord("session-t70", agent_id).role)

    def test_a_blocked_reviewer_that_follows_the_restore_instructions_is_not_blocked_again(self) -> None:
        # R3.6, shape the T23 generator leaves out: the blocked reviewer runs the commands the
        # block message lists instead of leaving the restore to the hook, while another reviewer
        # is still running. Its next stop and the other reviewer's stop pass without a block.
        with _reviewer_repository() as (root, git_env):
            changer, other = ("agent-follows", SPEC_REVIEWER), ("agent-other", SECURITY_REVIEWER)
            before = _file_contents(root)
            for agent_id, agent_type in (changer, other):
                _run_hook(on_start, _reviewer_event("SubagentStart", agent_id, agent_type, root))
            _apply_change(root, "modify", "src/app.py")
            _apply_change(root, "create", "tests/test_note.py")
            _apply_change(root, "delete", "README.md")

            blocked = _run_hook(on_stop, _reviewer_event("SubagentStop", *changer, root))
            _follow_restore_instructions(root, git_env, blocked["reason"])
            retry = _run_hook(on_stop, _reviewer_event("SubagentStop", *changer, root))
            other_stop = _run_hook(on_stop, _reviewer_event("SubagentStop", *other, root))

            self.assertEqual(blocked["decision"], "block")
            self.assertEqual((retry, other_stop), ({}, {}))
            self.assertEqual(_file_contents(root), before)
            for agent_id, _ in (changer, other):
                self.assertIsNone(SubagentRecord("session-t70", agent_id).role)

    def test_restores_a_change_made_after_another_concurrent_reviewer_already_stopped(self) -> None:
        # R3.6, shape the T23 generator leaves out: one of three reviewers stops cleanly, then a
        # second one changes files while the third still runs. The next stop is blocked and the
        # tree ends as it started.
        with _reviewer_repository() as (root, _):
            early, changer, late = (
                ("agent-early", CODE_REVIEWER),
                ("agent-changer", SPEC_REVIEWER),
                ("agent-late", SECURITY_REVIEWER),
            )
            before = _file_contents(root)
            for agent_id, agent_type in (early, changer, late):
                _run_hook(on_start, _reviewer_event("SubagentStart", agent_id, agent_type, root))
            early_blocked = _stop_until_allowed(*early, root)
            _apply_change(root, "modify", "tests/test_app.py")
            _apply_change(root, "create", "notes.md")

            first_stops = [_stop_until_allowed(*late, root), _stop_until_allowed(*changer, root)]

            self.assertFalse(early_blocked)
            self.assertEqual(first_stops, [True, False])
            self.assertEqual(_file_contents(root), before)
            for agent_id, _ in (early, changer, late):
                self.assertIsNone(SubagentRecord("session-t70", agent_id).role)

    def test_restores_when_another_reviewer_stops_between_a_blocked_stop_and_its_retry(self) -> None:
        # R3.6, shape the T23 generator leaves out: the blocked reviewer does not stop again at
        # once; the other reviewer stops first and is blocked by the same change. Both retries
        # pass and the tree ends as it started.
        with _reviewer_repository() as (root, _):
            changer, other = ("agent-changer", CODE_REVIEWER), ("agent-other", SPEC_REVIEWER)
            before = _file_contents(root)
            for agent_id, agent_type in (changer, other):
                _run_hook(on_start, _reviewer_event("SubagentStart", agent_id, agent_type, root))
            _apply_change(root, "delete", "src/util.py")

            first = [_run_hook(on_stop, _reviewer_event("SubagentStop", *agent, root)) for agent in (changer, other)]
            _run_hook(on_stop, _reviewer_event("SubagentStop", *changer, root))
            _run_hook(on_stop, _reviewer_event("SubagentStop", *other, root))

            self.assertEqual([output.get("decision") for output in first], ["block", "block"])
            self.assertEqual(_file_contents(root), before)
            for agent_id, _ in (changer, other):
                self.assertIsNone(SubagentRecord("session-t70", agent_id).role)


@dataclass(frozen=True)
class ReviewerScenario:
    """One generated T23 case: the reviewers, the changes (reviewer index, kind, path) and the stop order."""

    reviewers: list[tuple[str, str]]
    changes: list[tuple[int, str, str]]
    stops: list[int]


def _generate_reviewer_scenario(seed: int) -> ReviewerScenario:
    """Draws 2-3 reviewers that all start before 1-3 changes, then a random order for their stops."""
    rng = random.Random(seed)  # noqa: S311 - seeded for reproducible test data, not cryptography
    count = rng.randint(2, 3)
    reviewers = [(f"agent-s{seed}-r{index}", rng.choice(REVIEWER_TYPES)) for index in range(count)]
    present = sorted(SEED_FILES)
    changes = []
    for number in range(rng.randint(1, 3)):
        kind, directory = rng.choice(("modify", "create", "delete")), rng.choice(("src", "tests", ""))
        tracked = [path for path in present if path.rpartition("/")[0] == directory]
        if kind == "create" or not tracked:
            kind, path = "create", f"{directory}/created_{seed}_{number}.py".lstrip("/")
        else:
            path = rng.choice(tracked)
            if kind == "delete":
                present.remove(path)
        changes.append((rng.randrange(count), kind, path))
    return ReviewerScenario(reviewers, changes, rng.sample(range(count), count))


def _apply_change(root: Path, kind: str, path: str) -> None:
    """Makes one reviewer change: appends to a tracked file, creates a new one or deletes a tracked one."""
    target = root / path
    if kind == "modify":
        with target.open("ab") as changed:
            changed.write(b"# edited by a reviewer\n")
    elif kind == "create":
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"CREATED = True\n")
    else:
        target.unlink()


def _follow_restore_instructions(root: Path, git_env: dict[str, str], reason: str) -> None:
    """Runs each `git restore` and `rm` command a block message lists, as an obedient subagent would."""
    for line in reason.splitlines():
        command = shlex.split(line)
        if command[:2] == ["git", "restore"]:
            _git(command[1:], root, git_env)
        elif command[:1] == ["rm"]:
            (root / command[-1]).unlink()


@contextlib.contextmanager
def _reviewer_repository() -> Iterator[tuple[Path, dict[str, str]]]:
    """Yields a committed repository and its Git environment, with hook state isolated in a temporary directory."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp).resolve() / "repo"
        git_env = {"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": str(root.parent / "no-global-gitconfig")}
        _make_repository(root, git_env)
        hook_env = {**git_env, "CLAUDE_PLUGIN_DATA": str(root.parent / "plugin-data")}
        with mock.patch.dict(os.environ, hook_env):
            os.environ.pop("CLAUDE_PROJECT_DIR", None)  # each event's cwd resolves the repository
            yield root, git_env


def _reviewer_event(name: str, agent_id: str, agent_type: str, cwd: Path) -> dict[str, Any]:
    """Builds a SubagentStart or SubagentStop event for one reviewer subagent."""
    return {
        "hook_event_name": name,
        "session_id": "session-t70",
        "agent_id": agent_id,
        "agent_type": agent_type,
        "cwd": str(cwd),
    }


def _stop_until_allowed(agent_id: str, agent_type: str, root: Path) -> bool:
    """Stops a reviewer, and stops it again when the first stop is blocked; returns whether it was blocked."""
    first = _run_hook(on_stop, _reviewer_event("SubagentStop", agent_id, agent_type, root))
    was_blocked = first.get("decision") == "block"
    if was_blocked:
        _run_hook(on_stop, _reviewer_event("SubagentStop", agent_id, agent_type, root))
    return was_blocked


def _make_reviewer_change(root: Path, change: str, number: int) -> None:
    """Changes the checkout as a misbehaving reviewer would: edits a tracked file or creates a new one."""
    if change == "modify":
        with (root / "src" / "app.py").open("ab") as app:
            app.write(f"# edited by reviewer {number}\n".encode())
    else:
        (root / "src" / f"reviewer_note_{number}.py").write_bytes(f"NOTE = {number}\n".encode())


def _make_repository(root: Path, env: dict[str, str]) -> None:
    """Creates a repository at root with one commit of SEED_FILES: root, production and test files."""
    root.mkdir()
    _git(["init", "-q", "-b", "main"], root, env)
    for relative, content in SEED_FILES.items():
        (root / relative).parent.mkdir(parents=True, exist_ok=True)
        (root / relative).write_bytes(content)
    _git(["add", "--all"], root, env)
    _git(["commit", "-q", "-m", "seed"], root, env)


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
