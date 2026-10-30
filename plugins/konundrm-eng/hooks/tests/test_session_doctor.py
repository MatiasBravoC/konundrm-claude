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

    def test_names_each_partitions_next_task_when_they_run_in_parallel(self) -> None:
        # R3.7: during a parallel wave the session start names the next task of each partition of
        # the slice being built (S1); S2's partition P3 waits for its own stacked pull request.
        folder = self.root / "specs" / "005-coupons"
        folder.mkdir(parents=True)
        plan = (
            "- **Status:** Approved\n"
            "- **Parallel:** {parallel}\n\n"
            "## Slice S1: apply\n\n"
            "- [x] **T1** Step 1 · `behavior`\n"
            "- [ ] **T2** Step 2 · `behavior`\n"
            "- [ ] **T3** Step 3 · `behavior`\n\n"
            "### Partitions\n\n"
            "| Wave | Partition | Tasks | Depends on |\n"
            "| --- | --- | --- | --- |\n"
            "| 1 | P1 | T1, T3 | — |\n"
            "| 1 | P2 | T2 | — |\n\n"
            "## Slice S2: expiry\n\n"
            "- [ ] **T4** Step 4 · `behavior`\n\n"
            "### Partitions\n\n"
            "| Wave | Partition | Tasks | Depends on |\n"
            "| --- | --- | --- | --- |\n"
            "| 1 | P3 | T4 | — |\n"
        )
        (folder / "tasks.md").write_text(plan.format(parallel="yes"), encoding="utf-8")
        parallel_lines = (feature_progress_context(self.root) or "").splitlines()
        (folder / "tasks.md").write_text(plan.format(parallel="no"), encoding="utf-8")
        serial_context = feature_progress_context(self.root) or ""

        self.assertIn("- specs/005-coupons: 1 of 4 tasks checked, next per partition: P1 T3, P2 T2", parallel_lines)
        self.assertIn("- specs/005-coupons: 1 of 4 tasks checked, next T2: Step 2", serial_context)
        self.assertNotIn("per partition", serial_context)

    def test_lists_partitions_by_number_and_falls_back_to_one_task(self) -> None:
        # R3.7: with Parallel on, partitions are listed by number (P2 before P10), and the session
        # start falls back to a single next task when only one partition of the slice is pending or
        # a pending task of the slice belongs to no partition.
        folder = self.root / "specs" / "006-coupons"
        folder.mkdir(parents=True)
        header = "- **Status:** Approved\n- **Parallel:** yes\n\n## Slice S1: apply\n\n"
        table = "### Partitions\n\n| Wave | Partition | Tasks | Depends on |\n| --- | --- | --- | --- |\n"
        tasks = (
            "- [x] **T1** Step 1 · `behavior`\n- [ ] **T2** Step 2 · `behavior`\n- [ ] **T3** Step 3 · `behavior`\n\n"
        )
        cases = {
            "P10 listed before P2": (
                tasks + table + "| 1 | P10 | T2 | — |\n| 1 | P2 | T1, T3 | — |\n",
                "- specs/006-coupons: 1 of 3 tasks checked, next per partition: P2 T3, P10 T2",
            ),
            "only one partition pending": (
                tasks + table + "| 1 | P1 | T2, T3 | — |\n| 1 | P2 | T1 | — |\n",
                "- specs/006-coupons: 1 of 3 tasks checked, next T2: Step 2",
            ),
            "a pending task in no partition": (
                tasks + table + "| 1 | P1 | T1, T2 | — |\n| 1 | P2 | T1 | — |\n",
                "- specs/006-coupons: 1 of 3 tasks checked, next T2: Step 2",
            ),
        }
        for case, (body, expected_line) in cases.items():
            with self.subTest(case):
                (folder / "tasks.md").write_text(header + body, encoding="utf-8")
                context = feature_progress_context(self.root) or ""

                self.assertIn(expected_line, context.splitlines())
                if "per partition" not in expected_line:
                    self.assertNotIn("per partition", context)


if __name__ == "__main__":
    unittest.main()
