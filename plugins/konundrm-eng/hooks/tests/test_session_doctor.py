"""Unit tests for hooks/scripts/session_doctor.py."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from session_doctor import (
    check_command_context,
    environment_warnings,
    feature_progress_context,
    installed_legacy_skills,
)


class InstalledLegacySkillsTest(unittest.TestCase):
    def test_lists_only_replaced_skills_that_still_have_a_skill_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp)
            for name in ("tdd", "deployer", "my-own-skill"):
                (config / "skills" / name).mkdir(parents=True)
                (config / "skills" / name / "SKILL.md").write_text("---\nname: x\n---\n")
            (config / "skills" / "mapper").mkdir()  # emptied folder: not installed
            self.assertEqual(installed_legacy_skills(config), ["deployer", "tdd"])

    def test_warns_about_them_with_the_folder_to_clean(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp)
            (config / "skills" / "engineer").mkdir(parents=True)
            (config / "skills" / "engineer" / "SKILL.md").write_text("")
            warnings = environment_warnings(config)
            self.assertTrue(any("engineer" in warning and "Move those folders" in warning for warning in warnings))

    def test_has_no_warnings_on_a_clean_setup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(environment_warnings(Path(tmp)), [])


class CheckCommandContextTest(unittest.TestCase):
    def test_names_the_check_command_or_how_to_create_one(self) -> None:
        with mock.patch.dict(os.environ, {"KONUNDRM_GATE": ""}):
            self.assertIn("`npm run check`", check_command_context("npm run check"))
            self.assertIn("setup-project", check_command_context(None))

    def test_says_when_the_gates_are_off(self) -> None:
        with mock.patch.dict(os.environ, {"KONUNDRM_GATE": "off"}):
            self.assertIn("off", check_command_context("npm run check"))


class FeatureProgressContextTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def write_tasks(self, feature: str, status: str, *boxes: bool) -> None:
        folder = self.root / "specs" / feature
        folder.mkdir(parents=True)
        tasks = "".join(
            f"- [{'x' if done else ' '}] **T{n}** Step {n} · `behavior`\n" for n, done in enumerate(boxes, 1)
        )
        (folder / "tasks.md").write_text(f"- **Status:** {status}\n\n{tasks}", encoding="utf-8")

    def test_names_each_approved_feature_and_its_next_task(self) -> None:
        self.write_tasks("003-coupons", "Approved", True, False, False)
        context = feature_progress_context(self.root) or ""
        self.assertIn("specs/003-coupons: 1 of 3 tasks checked, next T2: Step 2", context)
        self.assertIn("/konundrm-eng:develop-feature", context)

    def test_says_when_only_the_finish_phase_is_left(self) -> None:
        self.write_tasks("004-export", "Approved", True, True)
        self.assertIn("finish phase", feature_progress_context(self.root) or "")

    def test_ignores_drafts_done_features_and_projects_without_specs(self) -> None:
        self.assertIsNone(feature_progress_context(self.root))
        self.write_tasks("001-login", "Done", True)
        self.write_tasks("002-search", "Draft", False)
        self.assertIsNone(feature_progress_context(self.root))


if __name__ == "__main__":
    unittest.main()
