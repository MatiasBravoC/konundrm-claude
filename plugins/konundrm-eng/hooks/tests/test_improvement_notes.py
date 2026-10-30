"""Unit tests for hooks/scripts/improvement_notes.py."""

from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import improvement_notes


class AppendNotesTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        # Nested so a "../.." escape would still land inside the temporary directory, where we can see it.
        self.root = Path(self._tmp.name)
        self.config_dir = self.root / "home" / "user" / "claude-config"
        self.fallback_dir = self.root / "home" / "user" / "project" / "specs" / "001-x"
        self.config_dir.mkdir(parents=True)
        self.fallback_dir.mkdir(parents=True)

    def test_appends_dated_notes_tagged_with_project_feature_and_scope(self) -> None:
        # R7.2: dated notes, tagged with project and feature, go to one fixed central file.
        # Threat "Ruta del archivo de notas": hostile names never change the path and stay on one line.
        project = "../../evil-project/sub\nINJECTED-PROJECT"
        feature = "nested/feature/..\r\nINJECTED-FEATURE"
        notes = "Los checkpoints de slice fueron demasiado largos."

        path, used_fallback = improvement_notes.append_notes(
            notes,
            project=project,
            feature=feature,
            scope="slice 2",
            today=date(2026, 10, 29),
            config_dir=self.config_dir,
            fallback_dir=self.fallback_dir,
        )

        expected = self.config_dir / "konundrm-eng" / "improvements.md"
        self.assertEqual(improvement_notes.NOTES_FILE, Path("konundrm-eng") / "improvements.md")
        self.assertEqual((path, used_fallback), (expected, False))
        written = sorted(p for p in self.root.rglob("*") if p.is_file())
        self.assertEqual(written, [expected])
        content = expected.read_text(encoding="utf-8")
        for text in ("2026-10-29", "slice 2", notes):
            self.assertIn(text, content)
        lines = content.splitlines()
        for first_part, injected in (("evil-project", "INJECTED-PROJECT"), ("nested/feature", "INJECTED-FEATURE")):
            carrying = [line for line in lines if injected in line]
            self.assertEqual(len(carrying), 1, f"{injected} must appear on exactly one line: {lines!r}")
            self.assertIn(first_part, carrying[0], f"{injected} was split onto its own line: {lines!r}")


if __name__ == "__main__":
    unittest.main()
