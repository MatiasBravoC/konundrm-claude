"""Unit tests for hooks/scripts/format_and_lint.py."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from format_and_lint import plan_steps


class PlanStepsTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _fake_node_bin(self, name: str) -> None:
        folder = self.root / "node_modules" / ".bin"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / (f"{name}.cmd" if os.name == "nt" else name)).write_text("")

    def _fake_venv_bin(self, name: str) -> None:
        folder = self.root / ".venv" / ("Scripts" if os.name == "nt" else "bin")
        folder.mkdir(parents=True, exist_ok=True)
        (folder / (f"{name}.exe" if os.name == "nt" else name)).write_text("")

    def test_runs_nothing_when_the_project_configures_no_tool(self) -> None:
        self.assertEqual(plan_steps(self.root / "a.py", self.root), [])
        self.assertEqual(plan_steps(self.root / "a.ts", self.root), [])

    def test_formats_then_lints_python_with_ruff_when_configured(self) -> None:
        (self.root / "pyproject.toml").write_text("[tool.ruff]\nline-length = 100\n")
        self._fake_venv_bin("ruff")
        steps = plan_steps(self.root / "a.py", self.root)
        self.assertEqual([step.kind for step in steps], ["format", "lint"])
        self.assertEqual(steps[1].argv[1:3], ("check", "--fix"))
        self.assertIn("F401,F841", steps[1].argv, "unused imports are expected between two edits")

    def test_uses_prettier_and_eslint_from_node_modules(self) -> None:
        (self.root / "package.json").write_text(json.dumps({"devDependencies": {"prettier": "3"}}))
        (self.root / "eslint.config.mjs").write_text("export default [];")
        self._fake_node_bin("prettier")
        self._fake_node_bin("eslint")
        self.assertEqual([s.kind for s in plan_steps(self.root / "a.ts", self.root)], ["format", "lint"])
        self.assertEqual([s.kind for s in plan_steps(self.root / "a.css", self.root)], ["format"])

    def test_biome_replaces_prettier_and_eslint(self) -> None:
        (self.root / "biome.json").write_text("{}")
        self._fake_node_bin("biome")
        steps = plan_steps(self.root / "a.tsx", self.root)
        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0].argv[1:3], ("check", "--write"))


if __name__ == "__main__":
    unittest.main()
