"""Unit tests for hooks/scripts/improvement_notes.py."""

from __future__ import annotations

import random
import re
import string
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import improvement_notes
import secret_patterns


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

    def test_appending_keeps_every_earlier_note(self) -> None:
        # R7.2: the central file only grows; each append keeps every earlier byte exactly as it was.
        rng = random.Random(13)  # noqa: S311 - repeatable generated notes for tests, not cryptography
        for sequence in range(100):
            config_dir = self.root / "sequences" / str(sequence)
            path = config_dir / improvement_notes.NOTES_FILE
            note_count = rng.randint(1, 8)
            for _ in range(note_count):
                notes = "".join(rng.choice(string.printable) for _ in range(rng.randint(0, 80)))
                before = path.read_bytes() if path.exists() else b""

                improvement_notes.append_notes(
                    notes,
                    project="konundrm-claude",
                    feature="001-guided-slice-delivery",
                    scope="slice 7",
                    today=date(2026, 10, 29),
                    config_dir=config_dir,
                    fallback_dir=self.fallback_dir,
                )

                after = path.read_bytes()
                self.assertGreater(len(after), len(before), f"sequence {sequence}: nothing was appended")
                self.assertEqual(after[: len(before)], before, f"sequence {sequence}: earlier notes changed")


class ScrubTest(unittest.TestCase):
    def test_scrub_drops_code_and_redacts_secrets_and_emails(self) -> None:
        # R7.3 (Threats, row 1): the shared notes file never receives a project's code, credentials
        # or e-mail addresses; each removal leaves a short marker so the note still reads in general terms.
        # Fake credentials are split literals, so this file never holds one a scanner would flag.
        aws_key = "AK" + "IA" + "Q7RZ3M9TB2KX4WNP"
        github_token = "gh" + "p_" + "a8Kd2LmQ9xZr4TbW7nYc3VfHs6PjE1uGo5Ri"
        email = "ana.perez@cliente-ejemplo.cl"
        notes = (
            "Antes del bloque.\n"
            "```python\n"
            "def filtrar_cliente(rut):\n"
            "    return 'codigo-propietario'\n"
            "```\n"
            "Después del bloque.\n"
            f"El log del hook mostró la clave {aws_key} completa.\n"
            f"El reviewer copió el token {github_token} en su resumen.\n"
            f"La spec citaba a {email} como responsable.\n"
            "- Un paso de la lista traía código indentado:\n"
            "  ```\n"
            "  sangria_filtrada = True\n"
            "  ```\n"
            "Al final quedó una valla sin cerrar:\n"
            "```sh\n"
            "cola_sin_cerrar --token interno\n"
            "texto tras la valla abierta\n"
        )
        prose = "Los checkpoints de slice fueron largos.\nConviene correr `npm run check` antes de cada commit.\n"
        self.assertEqual(
            [match.kind for match in secret_patterns.find_secrets(notes)],
            ["AWS access key ID", "GitHub token"],
        )

        scrubbed = improvement_notes.scrub(notes)

        for leaked in (
            "```",
            "filtrar_cliente",
            "codigo-propietario",
            "sangria_filtrada",
            "cola_sin_cerrar",
            "texto tras la valla abierta",
            aws_key,
            github_token,
            email,
        ):
            self.assertNotIn(leaked, scrubbed)
        self.assertEqual(secret_patterns.find_secrets(scrubbed), [])
        self.assertIsNone(re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", scrubbed), scrubbed)
        # Each removal leaves a marker in place, between the prose that surrounded it.
        for before, after in (
            ("Antes del bloque.", "Después del bloque."),
            ("El log del hook mostró la clave ", " completa."),
            ("El reviewer copió el token ", " en su resumen."),
            ("La spec citaba a ", " como responsable."),
            ("- Un paso de la lista traía código indentado:", "Al final quedó una valla sin cerrar:"),
        ):
            found = re.search(re.escape(before) + r"(.*?)" + re.escape(after), scrubbed, re.DOTALL)
            self.assertIsNotNone(found, f"prose around the removed part is missing: {scrubbed!r}")
            self.assertTrue(found.group(1).strip(), f"no marker between {before!r} and {after!r}: {scrubbed!r}")
        tail = scrubbed.split("Al final quedó una valla sin cerrar:", 1)[1]
        self.assertTrue(tail.strip(), f"the unclosed block left no marker: {scrubbed!r}")
        self.assertEqual(improvement_notes.scrub(prose), prose)

        # A private key pasted as prose (no fence) is dropped whole, from its BEGIN line through its
        # END line, or through the end of the text when END is missing, like an unclosed fence.
        key_begin = "-----BEGIN " + "RSA PRIVATE" + " KEY-----"
        key_end = "-----END " + "RSA PRIVATE" + " KEY-----"
        key_body = "MIIEowIBAAKCAQEAu1SUcuerpoFirmaFalsa\nQ29ycG9EZUxhQ2xhdmVGYWxzYVBhcmFUZXN0\n"
        pem_notes = (
            "Clave filtrada:\n"
            f"{key_begin}\n{key_body}{key_end}\n"
            "Texto tras la clave cerrada.\n"
            "Otra clave sin cierre:\n"
            f"{key_begin}\n{key_body}"
        )
        self.assertEqual([match.kind for match in secret_patterns.find_secrets(pem_notes)], ["private key"] * 2)

        pem_scrubbed = improvement_notes.scrub(pem_notes)

        for leaked in ("-----BEGIN", "-----END", "MIIEowIBAAKCAQEAu1SU", "Q29ycG9EZUxhQ2xhdmVGYWxzYVBhcmFUZXN0"):
            self.assertNotIn(leaked, pem_scrubbed)
        self.assertEqual(secret_patterns.find_secrets(pem_scrubbed), [])
        found = re.search(r"Clave filtrada:(.*?)Texto tras la clave cerrada\.", pem_scrubbed, re.DOTALL)
        self.assertIsNotNone(found, f"prose around the closed key is missing: {pem_scrubbed!r}")
        self.assertTrue(found.group(1).strip(), f"no marker where the closed key was: {pem_scrubbed!r}")
        pem_tail = pem_scrubbed.split("Otra clave sin cierre:", 1)[1]
        self.assertTrue(pem_tail.strip(), f"the key without END left no marker: {pem_scrubbed!r}")


if __name__ == "__main__":
    unittest.main()
