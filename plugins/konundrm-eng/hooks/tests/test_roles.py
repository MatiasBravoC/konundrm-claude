"""Unit tests for hooks/scripts/roles.py."""

from __future__ import annotations

import random
import string
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from file_kinds import TEST_DIRECTORIES, TEST_FILE_GLOBS
from roles import READ_ONLY_ROLES, agent_role, change_denial_reason

PATH_CHARACTERS = string.ascii_lowercase + string.digits + "_.-"
FEATURE_DOCUMENTS = ("requirements.md", "design.md", "tasks.md")


def generate_paths(seed: int, count: int) -> list[str]:
    """Builds repeatable relative paths of 1 to 6 segments over [a-z0-9_.-].

    The shapes take turns, so files in test folders, test file names, hidden files and
    specs/<NNN-slug>/ documents are always among the paths instead of appearing by chance.
    """
    rng = random.Random(seed)  # noqa: S311 - repeatable test inputs, not cryptography
    test_folders = sorted(TEST_DIRECTORIES)  # sorted: a frozenset's order changes between runs

    def segment() -> str:
        return "".join(rng.choice(PATH_CHARACTERS) for _ in range(rng.randint(1, 12)))

    def under_folders(*last: str) -> str:
        return "/".join([*(segment() for _ in range(rng.randint(0, 6 - len(last)))), *last])

    def test_file_name() -> str:
        return "".join(segment() if character == "*" else character for character in rng.choice(TEST_FILE_GLOBS))

    shapes = (
        lambda: under_folders(segment()),
        lambda: under_folders(rng.choice(test_folders), segment()),
        lambda: under_folders(test_file_name()),
        lambda: under_folders("." + segment()),
        lambda: f"specs/{rng.randrange(1000):03d}-{segment()}/{rng.choice(FEATURE_DOCUMENTS)}",
    )
    return [shapes[index % len(shapes)]() for index in range(count)]


class AgentRoleTest(unittest.TestCase):
    def test_maps_plugin_scoped_agent_type_to_role(self) -> None:
        self.assertEqual(agent_role({"agent_type": "konundrm-eng:implementer"}), "implementer")

    def test_maps_bare_agent_type_to_role(self) -> None:
        self.assertEqual(agent_role({"agent_type": "test-writer"}), "test-writer")

    def test_every_plugin_agent_has_a_role(self) -> None:
        agents = Path(__file__).resolve().parents[2] / "agents"
        for definition in sorted(agents.glob("*.md")):
            with self.subTest(agent=definition.stem):
                self.assertEqual(agent_role({"agent_type": f"konundrm-eng:{definition.stem}"}), definition.stem)

    def test_ignores_main_conversation_and_foreign_agents(self) -> None:
        for event in ({}, {"agent_type": "other-plugin:implementer"}, {"agent_type": "konundrm-eng:planner"}):
            with self.subTest(event=event):
                self.assertIsNone(agent_role(event))


class ChangeDenialReasonTest(unittest.TestCase):
    def test_main_conversation_may_change_anything(self) -> None:
        for path in ("tests/test_a.py", "src/a.py", "specs/001-login/tasks.md"):
            with self.subTest(path=path):
                self.assertIsNone(change_denial_reason(None, path))

    def test_test_writer_may_change_tests_only(self) -> None:
        self.assertIsNone(change_denial_reason("test-writer", "tests/auth/test_login.py"))
        self.assertIn("only create or edit test files", change_denial_reason("test-writer", "src/auth/login.py") or "")

    def test_implementer_may_change_production_code_but_not_tests(self) -> None:
        self.assertIsNone(change_denial_reason("implementer", "src/auth/login.py"))
        self.assertIn(
            "may not edit test files", change_denial_reason("implementer", "src/__tests__/Login.test.tsx") or ""
        )

    def test_read_only_roles_may_not_change_anything(self) -> None:
        # R8.5: the rethinker is read-only, like the reviewers. R7.1: so is the process-reviewer. The
        # role is built from the agent_type the hooks receive, because the hooks never restrict an agent
        # that agent_role does not map.
        read_only_names = (
            "spec-reviewer",
            "code-reviewer",
            "security-reviewer",
            "finding-verifier",
            "rethinker",
            "process-reviewer",
        )
        for name in read_only_names:
            with self.subTest(role=name):
                role = agent_role({"agent_type": f"konundrm-eng:{name}"})
                self.assertIn("read-only", change_denial_reason(role, "src/a.py") or "")
                self.assertIn("read-only", change_denial_reason(role, "tests/test_a.py") or "")

    def test_read_only_roles_are_denied_for_any_path(self) -> None:
        # R8.5: property over 500 seeded paths and every role in READ_ONLY_ROLES, so a read-only role
        # added later is covered too. Test code and feature documents are among the paths because
        # the other roles' rules treat them differently; the read-only denial must win for them too.
        paths = generate_paths(seed=7, count=500)
        for role in sorted(READ_ONLY_ROLES):
            with self.subTest(role=role):
                for path in paths:
                    reason = change_denial_reason(role, path) or ""
                    self.assertIn("read-only", reason, f"the {role} may change {path}")

    def test_only_the_orchestrator_changes_feature_documents(self) -> None:
        for role in ("test-writer", "implementer"):
            with self.subTest(role=role):
                self.assertIn("orchestrator", change_denial_reason(role, "specs/002-reset/tasks.md") or "")


if __name__ == "__main__":
    unittest.main()
