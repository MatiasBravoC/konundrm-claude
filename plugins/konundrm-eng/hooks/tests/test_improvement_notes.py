"""Unit tests for hooks/scripts/improvement_notes.py."""

from __future__ import annotations

import os
import random
import re
import string
import subprocess
import sys
import tempfile
import unittest
from dataclasses import dataclass, field
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

    def test_falls_back_to_the_feature_folder_when_the_central_file_cannot_be_written(self) -> None:
        # R7.4: when the central file cannot be written, the notes stay with the feature's documents
        # and the caller learns the fallback was used (the CLI tells the user, T49).
        # A regular file where the central folder should be makes mkdir/open fail on Windows and POSIX alike.
        blocker = self.config_dir / "konundrm-eng"
        blocker.write_bytes(b"not a folder")
        notes = "Los checkpoints de slice fueron demasiado largos."

        path, used_fallback = improvement_notes.append_notes(
            notes,
            project="konundrm-claude",
            feature="001-guided-slice-delivery",
            scope="slice 7",
            today=date(2026, 10, 29),
            config_dir=self.config_dir,
            fallback_dir=self.fallback_dir,
        )

        expected = self.fallback_dir / "improvement-notes.md"
        self.assertEqual((path, used_fallback), (expected, True))
        content = expected.read_text(encoding="utf-8")
        for text in ("2026-10-29", "konundrm-claude", "001-guided-slice-delivery", "slice 7", notes):
            self.assertIn(text, content)
        self.assertEqual(sorted(self.config_dir.rglob("*")), [blocker])
        self.assertEqual(blocker.read_bytes(), b"not a folder")


# Generated notes for the scrub property (T47). Fake credentials are assembled from split literals and
# seeded noise, so this file never holds a value a secret scanner would flag.
_ALNUM = string.ascii_letters + string.digits
_UPPER_DIGITS = string.ascii_uppercase + string.digits
_TOKEN_ALPHABET = _ALNUM + "_-"
_BASE64 = _ALNUM + "+/"
_PROSE_WORDS = (
    "la", "revisión", "del", "módulo", "falló", "después", "de", "corrección", "y", "el", "índice",
    "quedó", "pequeño", "señal", "acción", "también", "conviene", "dividir", "tareas", "más", "cortas",
)  # fmt: skip
# Backticks and "@" in prose that are neither a fence nor an e-mail address.
_PROSE_EXTRAS = ("`npm run check`", "`scrub()`", "``doble ` tick``", "@equipo", "@revisora", "a @ b", "```en línea```")
# Inline triple-backtick spans that open a prose line. CommonMark never reads them as a fence (a
# backtick fence's info string has no backticks), so a later bare fence still opens a real block.
_INLINE_SPAN_LEADS = ("```en línea``` ", "```npm run check``` ", "  ```scrub()``` ")
# Fence indents include Unicode spaces (no-break, ideographic): a fence they indent still hides code.
_FENCE_INDENTS = ("", "", " ", "  ", "   ", "    ", "\t", "\u00a0", "\u3000")
# Some info strings hold a lone backtick; with no equal run after it, the line still opens a block.
_INFO_STRINGS = ("python", "sh", "ts", "json", " python", "python `x`", "sh `npm`", "ts title=`a.ts`")
_WRAPPERS = (("", ""), ("`", "`"), ("(", ")"), ('"', '"'), ("<", ">"), ("token=", ""), ("[", "]"))
_EMAIL_NAMES = ("ana", "perez", "soto", "maria", "jose", "soporte", "devops")
_EMAIL_SEPARATORS = ("", ".", "_", "+", "-")
_EMAIL_DOMAINS = ("cliente-ejemplo.cl", "mail.empresa.com", "uc.cl", "proveedor.io")
_KEY_LABELS = ("", "RSA ", "EC ", "DSA ", "OPENSSH ", "PGP ", "ENCRYPTED ")


def _noise(rng: random.Random, length: int, alphabet: str = _ALNUM) -> str:
    return "".join(rng.choice(alphabet) for _ in range(length))


# One shape per entry of secret_patterns.SECRET_PATTERNS but the private key, which is built as a whole block.
_SECRET_SHAPES = {
    "aws": lambda rng: (
        rng.choice(("AK" + "IA", "AS" + "IA", "AB" + "IA", "AC" + "CA")) + _noise(rng, 16, _UPPER_DIGITS)
    ),
    "github": lambda rng: "gh" + rng.choice("pousr") + "_" + _noise(rng, rng.randint(36, 60)),
    "github_pat": lambda rng: "github" + "_pat_" + _noise(rng, rng.randint(50, 90), _ALNUM + "_"),
    "gitlab": lambda rng: "glp" + "at-" + _noise(rng, rng.randint(20, 40), _TOKEN_ALPHABET),
    "slack": lambda rng: "xo" + "x" + rng.choice("abposr") + "-" + _noise(rng, rng.randint(10, 40), _ALNUM + "-"),
    "slack_webhook": lambda rng: (
        "https://hooks."
        + "slack.com/services/T"
        + _noise(rng, 9, _UPPER_DIGITS)
        + "/B"
        + _noise(rng, 9, _UPPER_DIGITS)
        + "/"
        + _noise(rng, 24)
    ),
    "stripe": lambda rng: rng.choice(("sk", "rk")) + "_live_" + _noise(rng, rng.randint(20, 40)),
    "google": lambda rng: "AI" + "za" + _noise(rng, 35, _TOKEN_ALPHABET),
    "anthropic": lambda rng: (
        "sk-"
        + "ant-"
        + rng.choice(("api", "admin"))
        + _noise(rng, 2, string.digits)
        + "-"
        + _noise(rng, rng.randint(80, 100), _TOKEN_ALPHABET)
    ),
    "openai_project": lambda rng: (
        "sk-" + rng.choice(("proj", "svcacct", "admin")) + "-" + _noise(rng, rng.randint(40, 60), _TOKEN_ALPHABET)
    ),
    "openai_legacy": lambda rng: "sk-" + _noise(rng, 20) + "T3Blbk" + "FJ" + _noise(rng, 20),
    "npm": lambda rng: "np" + "m_" + _noise(rng, 36),
    "pypi": lambda rng: "pypi-" + "AgEIcHlwaS5vcmc" + _noise(rng, rng.randint(50, 80), _TOKEN_ALPHABET),
    "sendgrid": lambda rng: "SG." + _noise(rng, 22, _TOKEN_ALPHABET) + "." + _noise(rng, 43, _TOKEN_ALPHABET),
    "azure": lambda rng: "AccountKey=" + _noise(rng, 86, _BASE64) + "==",
}


@dataclass
class _GeneratedNotes:
    """A generated note plus every piece of project content it carries, so its absence can be checked."""

    newline: str
    blocks: list[str] = field(default_factory=list)
    secrets: list[str] = field(default_factory=list)  # one whole credential each, private-key headers included
    key_lines: list[str] = field(default_factory=list)  # body and END lines of private keys
    emails: list[str] = field(default_factory=list)
    code_tokens: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return self.newline.join(self.blocks)


class _NotesGenerator:
    """Builds notes mixing Spanish prose, credentials, e-mail addresses, fenced code and private keys."""

    def __init__(self, rng: random.Random) -> None:
        self.rng = rng

    def notes(self) -> _GeneratedNotes:
        notes = _GeneratedNotes(newline=self.rng.choice(("\n", "\r\n")))
        for _ in range(self.rng.randint(1, 8)):
            roll = self.rng.random()
            if roll < 0.55:
                notes.blocks.append(self._paragraph(notes))
            elif roll < 0.8:
                notes.blocks.append(self._code_block(notes, is_closed=True))
            else:
                notes.blocks.append(self._private_key(notes))
        # A fence never closed runs to the end of the text, so only the last block may leave it open.
        if self.rng.random() < 0.2:
            notes.blocks.append(self._code_block(notes, is_closed=False))
        notes.blocks.append(self.rng.choice(("", "Fin de las notas.")))
        return notes

    def _secret(self, notes: _GeneratedNotes) -> str:
        shape = self.rng.choice(list(_SECRET_SHAPES.values()))
        value = shape(self.rng)
        # A placeholder-looking value is not a credential to find_secrets; draw another one.
        while any(word in value.upper() for word in secret_patterns.PLACEHOLDER_WORDS):
            value = shape(self.rng)
        notes.secrets.append(value)
        return value

    def _email(self, notes: _GeneratedNotes) -> str:
        # Every piece of the local part carries digits, so a fragment left behind can be told from prose.
        pieces = [self.rng.choice(_EMAIL_NAMES) + _noise(self.rng, 3, string.digits) for _ in range(2)]
        address = self.rng.choice(_EMAIL_SEPARATORS).join(pieces) + "@" + self.rng.choice(_EMAIL_DOMAINS)
        notes.emails.append(address)
        return address

    def _sensitive_item(self, notes: _GeneratedNotes) -> str:
        value = self._secret(notes) if self.rng.random() < 0.6 else self._email(notes)
        opening, closing = self.rng.choice(_WRAPPERS)
        return opening + value + closing

    def _paragraph(self, notes: _GeneratedNotes) -> str:
        bullet = self.rng.choice(("", "- ", "> ", "1. ", *_INLINE_SPAN_LEADS))
        words = []
        for _ in range(self.rng.randint(3, 12)):
            roll = self.rng.random()
            if roll < 0.25:
                words.append(self._sensitive_item(notes))
            elif roll < 0.4:
                words.append(self.rng.choice(_PROSE_EXTRAS))
            else:
                words.append(self.rng.choice(_PROSE_WORDS))
        return bullet + " ".join(words) + self.rng.choice((".", ":", ""))

    def _code_block(self, notes: _GeneratedNotes, *, is_closed: bool) -> str:
        indent = self.rng.choice(_FENCE_INDENTS)
        fence = "`" * self.rng.randint(3, 5)
        # Bare fences are drawn as often as all info strings together: they are the ones a prose line
        # mistaken for an opening fence would take for its closing fence.
        info = "" if self.rng.random() < 0.5 else self.rng.choice(_INFO_STRINGS)
        lines = [indent + fence + info]
        for _ in range(self.rng.randint(0, 4)):
            token = "fuente_" + _noise(self.rng, 10, string.ascii_lowercase)
            notes.code_tokens.append(token)
            line = indent + self.rng.choice(("def ", "x = ", "", "    return ")) + token
            if self.rng.random() < 0.3:
                line += " " + self._sensitive_item(notes)
            lines.append(line)
        if len(fence) > 3 and self.rng.random() < 0.5:
            # A shorter fence inside a longer one is content, not the end of the block.
            lines.insert(self.rng.randint(1, len(lines)), indent + "```" + self.rng.choice(("", "sh")))
        if is_closed:
            closing_fence = fence + "`" * self.rng.randint(0, 2)
            lines.append(self.rng.choice((indent, "")) + closing_fence + self.rng.choice(("", " ")))
        return notes.newline.join(lines)

    def _private_key(self, notes: _GeneratedNotes) -> str:
        label = self.rng.choice(_KEY_LABELS) + "PRIVATE" + " KEY" + self.rng.choice(("", " BLOCK"))
        header = "-----BEGIN " + label + "-----"
        notes.secrets.append(header)
        lines = [_noise(self.rng, 64, _BASE64) for _ in range(self.rng.randint(1, 4))]
        if self.rng.random() < 0.8:
            lines.append("-----END " + label + "-----")
        notes.key_lines.extend(lines)
        return notes.newline.join([header, *lines])


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

    def test_scrub_does_not_treat_an_inline_triple_backtick_span_as_a_fence(self) -> None:
        # R7.3 (Threats, row 1): a prose line that starts with an inline ``` span is not a fence, so the
        # bare fence after it still opens a block and its code never reaches the notes.
        # Counterexample found by the T47 property and confirmed by the security review.
        notes = (
            "```npm run check``` falló con este código:\n"
            "```\n"
            "def filtrar_cliente(rut):\n"
            '    return "codigo-propietario"\n'
            "```\n"
            "Fin de las notas.\n"
        )

        scrubbed = improvement_notes.scrub(notes)

        for leaked in ("filtrar_cliente", "codigo-propietario", "```"):
            self.assertNotIn(leaked, scrubbed)
        self.assertIn("Fin de las notas.", scrubbed)

    def test_scrub_drops_a_fence_indented_with_non_ascii_spaces(self) -> None:
        # R7.3 (Threats, row 1): a fence indented with a no-break or ideographic space still opens a
        # block, so its code never reaches the notes and the prose after the block survives.
        # Found by code review round 2: narrowing the indent to spaces and tabs leaked the block.
        for space in ("\u00a0", "\u3000"):
            notes = f"Nota:\n{space}```\ndef filtrar_cliente(): pass\n```\nFin.\n"

            scrubbed = improvement_notes.scrub(notes)

            for leaked in ("filtrar_cliente", "```"):
                self.assertNotIn(leaked, scrubbed, f"indent {space!r}: {scrubbed!r}")
            self.assertIn("Fin.", scrubbed, f"indent {space!r}: {scrubbed!r}")

    def test_scrub_drops_a_fence_whose_info_string_has_a_backtick(self) -> None:
        # R7.3 (Threats, row 1): a fence whose info string holds a single backtick still opens a block;
        # only a line whose opening run is closed by an equal run later on is an inline span.
        # Found by code review round 2: rejecting any backtick after the run leaked the block.
        notes = "```python `x`\ndef filtrar_cliente(): pass\n```\nFin.\n"

        scrubbed = improvement_notes.scrub(notes)

        for leaked in ("filtrar_cliente", "```"):
            self.assertNotIn(leaked, scrubbed, scrubbed)
        self.assertIn("Fin.", scrubbed, scrubbed)

    def test_scrub_drops_a_fence_whose_info_string_has_a_longer_backtick_run(self) -> None:
        # R7.3 (Threats, row 1): a run longer than the opening fence later on the line does not close an
        # inline span, so the fence still opens a block and a closing fence at least as long ends it.
        # Kills the `==` → `>=` mutant of _opening_fence found by T47's mutation review.
        notes = "```py ````\ndef filtrar_cliente(): pass\n````\nFin.\n"

        scrubbed = improvement_notes.scrub(notes)

        for leaked in ("filtrar_cliente", "```"):
            self.assertNotIn(leaked, scrubbed, scrubbed)
        self.assertIn("Fin.", scrubbed, scrubbed)

    def test_scrub_redacts_a_secret_exposed_by_removing_another(self) -> None:
        # R7.3 (Threats, row 1): an AWS key glued to an Azure key has no word boundary after it, so it
        # only matches once the Azure key is gone; scrub repeats until nothing matches, and leaks neither.
        # Kills the single-pass mutant of _redact_until_clean found by T47's mutation review.
        aws_key = "AK" + "IA" + "Q7RZ3M9TB2KX4WNP"
        azure_key = "Account" + "Key=" + ("Q29ycG9EZUxhQ2xhdmVGYWxzYVBhcmFUZXN0" * 3)[:86] + "=="
        notes = f"El log mostró {aws_key}{azure_key} completo.\n"
        self.assertEqual([match.kind for match in secret_patterns.find_secrets(notes)], ["Azure storage account key"])

        scrubbed = improvement_notes.scrub(notes)

        for leaked in (aws_key, azure_key):
            self.assertNotIn(leaked, scrubbed, scrubbed)
        self.assertEqual(secret_patterns.find_secrets(scrubbed), [], scrubbed)
        self.assertTrue(scrubbed.startswith("El log mostró "), scrubbed)
        self.assertTrue(scrubbed.endswith(" completo.\n"), scrubbed)

    def test_scrubbed_notes_never_keep_secrets_code_or_emails(self) -> None:
        # R7.3 (Threats, row 1): over 300 generated notes, the scrubbed text keeps no fence, nothing
        # find_secrets reports, no e-mail address and none of the generated code, credentials or addresses.
        rng = random.Random(17)  # noqa: S311 - repeatable generated notes for tests, not cryptography
        generator = _NotesGenerator(rng)
        covered_patterns: set[secret_patterns.SecretPattern] = set()
        for index in range(300):
            case = generator.notes()
            text = case.text
            context = f"case {index}: {text!r}"
            for value in case.secrets:
                self.assertTrue(secret_patterns.find_secrets(value), f"{context}\nnot a detected secret: {value!r}")
                covered_patterns.update(s for s in secret_patterns.SECRET_PATTERNS if s.pattern.search(value))
            self.assertGreaterEqual(len(secret_patterns.find_secrets(text)), len(case.secrets), context)

            scrubbed = improvement_notes.scrub(text)

            failure = f"{context}\nscrubbed: {scrubbed!r}"
            self.assertNotIn("```", scrubbed, failure)
            self.assertEqual(secret_patterns.find_secrets(scrubbed), [], failure)
            # An oracle independent of scrub's own e-mail regex: anything shaped like name@host.tld.
            self.assertIsNone(re.search(r"\S+@\S+\.\S+", scrubbed), failure)
            # A fragment of an address, such as the name before a dot, is personal data too.
            name_pieces = [piece for address in case.emails for piece in re.split(r"[._+-]", address.split("@")[0])]
            for leaked in (*case.secrets, *case.key_lines, *case.emails, *name_pieces, *case.code_tokens):
                self.assertNotIn(leaked, scrubbed, failure)
        self.assertEqual(
            covered_patterns, set(secret_patterns.SECRET_PATTERNS), "a credential format was not generated"
        )


_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "improvement_notes.py"


def _mentions(output: str, path: Path, project_root: Path) -> bool:
    """Whether the output names the path, absolute or relative to the project root."""
    relative = path.relative_to(project_root) if path.is_relative_to(project_root) else path
    return any(form in output for form in (str(path), path.as_posix(), str(relative), relative.as_posix()))


class CommandLineTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        # Resolved so the paths the script prints match these (Windows temp paths may be 8.3 short names).
        self.root = Path(self._tmp.name).resolve()
        self.home = self.root / "home"
        self.project = self.root / "project"
        self.feature_dir = self.project / "specs" / "001-x"
        self.home.mkdir()
        self.feature_dir.mkdir(parents=True)

    def _run(self, notes: str, *, config_dir: Path, feature: str) -> subprocess.CompletedProcess[str]:
        # HOME and USERPROFILE point at the temporary folder too, so the real ~/.claude is never touched.
        # The notes arrive as UTF-8 bytes, as run.sh pipes them, while the child's locale encoding is
        # left non-UTF-8 (cp1252 on Windows, ASCII under an uncoerced C locale elsewhere): the script
        # itself must read stdin as UTF-8 instead of relying on the caller's environment.
        env = {
            key: value
            for key, value in os.environ.items()
            if key.upper() not in {"PYTHONIOENCODING", "PYTHONUTF8", "PYTHONCOERCECLOCALE", "LC_ALL", "LANG"}
        }
        env |= {
            "CLAUDE_CONFIG_DIR": str(config_dir),
            "HOME": str(self.home),
            "USERPROFILE": str(self.home),
            "PYTHONUTF8": "0",
            "PYTHONCOERCECLOCALE": "0",
            "LC_ALL": "C",
        }
        completed = subprocess.run(
            [sys.executable, str(_SCRIPT), "--project", "konundrm-claude", "--feature", feature, "--scope", "slice 7"],
            input=notes.encode("utf-8"),
            cwd=self.project,
            env=env,
            capture_output=True,
            timeout=60,
            check=False,
        )
        return subprocess.CompletedProcess(
            completed.args,
            completed.returncode,
            completed.stdout.decode("utf-8", errors="replace"),
            completed.stderr.decode("utf-8", errors="replace"),
        )

    def test_cli_reads_notes_from_stdin_and_prints_where_they_went(self) -> None:
        # R7.2: the CLI reads the notes from stdin, scrubs them and appends them, dated and tagged with
        # --project, --feature and --scope, to <CLAUDE_CONFIG_DIR>/konundrm-eng/improvements.md.
        # R7.4: when that file cannot be written, the notes go to specs/<--feature>/improvement-notes.md
        # under the working directory (the project root) and the output warns and names both files.
        # R7.2, R7.4: the notes are stored exactly as written, accents included, whatever the caller's
        # locale encoding (run.sh sets no PYTHONIOENCODING).
        # Threats row 2: a hostile --feature never lets the fallback leave specs/ or touch the config folder.
        # Fake credentials are split literals, so this file never holds one a scanner would flag.
        aws_key = "AK" + "IA" + "Q7RZ3M9TB2KX4WNP"
        email = "ana.perez@cliente-ejemplo.cl"
        # Accented text the cp1252 code page would corrupt (ó) or cannot decode at all (Í, Á).
        prose = "Los checkpoints de slice fueron demasiado largos. La revisión mostró el Índice del ÁREA."
        notes = (
            f"{prose}\n"
            "```python\n"
            "def filtrar_cliente(rut):\n"
            "    return 'codigo-propietario'\n"
            "```\n"
            f"El log del hook mostró la clave {aws_key} completa.\n"
            f"La spec citaba a {email} como responsable.\n"
        )
        leaks = ("```", "filtrar_cliente", "codigo-propietario", aws_key, email)

        # Central file writable.
        config_dir = self.root / "config"
        config_dir.mkdir()
        days = {date.today().isoformat()}
        result = self._run(notes, config_dir=config_dir, feature="001-x")
        days.add(date.today().isoformat())

        central = config_dir / "konundrm-eng" / "improvements.md"
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(central.is_file(), f"stdout: {result.stdout!r}\nstderr: {result.stderr!r}")
        content = central.read_text(encoding="utf-8")
        for text in ("konundrm-claude", "001-x", "slice 7", prose):
            self.assertIn(text, content)
        self.assertTrue(any(day in content for day in days), content)
        for leaked in leaks:
            self.assertNotIn(leaked, content)
        self.assertEqual(secret_patterns.find_secrets(content), [], content)
        self.assertTrue(_mentions(result.stdout, central, self.project), result.stdout)
        self.assertFalse((self.feature_dir / "improvement-notes.md").exists())

        # Central file not writable: a regular file stands where its folder should be.
        blocked_config = self.root / "blocked-config"
        blocked_config.mkdir()
        blocker = blocked_config / "konundrm-eng"
        blocker.write_bytes(b"not a folder")
        blocked_central = blocked_config / "konundrm-eng" / "improvements.md"
        days = {date.today().isoformat()}
        result = self._run(notes, config_dir=blocked_config, feature="001-x")
        days.add(date.today().isoformat())

        fallback = self.feature_dir / "improvement-notes.md"
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(fallback.is_file(), output)
        fallback_content = fallback.read_text(encoding="utf-8")
        for text in ("konundrm-claude", "001-x", "slice 7", prose):
            self.assertIn(text, fallback_content)
        self.assertTrue(any(day in fallback_content for day in days), fallback_content)
        for leaked in leaks:
            self.assertNotIn(leaked, fallback_content)
        self.assertTrue(_mentions(output, fallback, self.project), f"fallback path not named: {output!r}")
        self.assertTrue(
            _mentions(output, blocked_central, self.project), f"no warning about the central file: {output!r}"
        )
        self.assertEqual(blocker.read_bytes(), b"not a folder")

        # Hostile --feature with the central file blocked: nothing is written outside specs/ nor in the
        # config folder. Both targets exist, so a naive specs/<feature> join would write into them.
        escape = self.root / "escape"
        escape.mkdir()
        before = sorted(p for p in self.root.rglob("*") if p.is_file())
        for hostile in ("../../escape", str(escape), str(blocked_config)):
            self._run(notes, config_dir=blocked_config, feature=hostile)

            after = sorted(p for p in self.root.rglob("*") if p.is_file())
            new_files = [p for p in after if p not in before]
            outside = [p for p in new_files if not p.is_relative_to(self.project / "specs")]
            self.assertEqual(outside, [], f"--feature {hostile!r} wrote outside specs/")
            self.assertEqual(sorted(blocked_config.rglob("*")), [blocker], f"--feature {hostile!r}")
            self.assertEqual(blocker.read_bytes(), b"not a folder")


if __name__ == "__main__":
    unittest.main()
