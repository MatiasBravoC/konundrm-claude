"""Unit tests for hooks/scripts/roles.py."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from roles import agent_role, change_denial_reason


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

    def test_reviewers_may_not_change_anything(self) -> None:
        for role in ("spec-reviewer", "code-reviewer", "security-reviewer", "finding-verifier"):
            with self.subTest(role=role):
                self.assertIn("read-only", change_denial_reason(role, "src/a.py") or "")
                self.assertIn("read-only", change_denial_reason(role, "tests/test_a.py") or "")

    def test_only_the_orchestrator_changes_feature_documents(self) -> None:
        for role in ("test-writer", "implementer"):
            with self.subTest(role=role):
                self.assertIn("orchestrator", change_denial_reason(role, "specs/002-reset/tasks.md") or "")


if __name__ == "__main__":
    unittest.main()
