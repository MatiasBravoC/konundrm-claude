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


# Generated notes for the scrub property (T47, T57). Fake credentials are assembled from split literals and
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
# Inline triple-backtick spans that open a prose line. CommonMark never reads them as a fence (a backtick
# fence's info string has no backticks), so they start no code and the prose on their line survives.
_INLINE_SPAN_LEADS = ("```en línea``` ", "```npm run check``` ", "  ```scrub()``` ")
_WRAPPERS = (("", ""), ("`", "`"), ("(", ")"), ('"', '"'), ("<", ">"), ("token=", ""), ("[", "]"))
_EMAIL_NAMES = ("ana", "perez", "soto", "maria", "jose", "soporte", "devops")
_EMAIL_SEPARATORS = ("", ".", "_", "+", "-")
_EMAIL_DOMAINS = ("cliente-ejemplo.cl", "mail.empresa.com", "uc.cl", "proveedor.io")
# PEM private key types before "PRIVATE KEY" (T58: any type, one word or several, or none).
_KEY_LABELS = (
    "", "RSA ", "EC ", "DSA ", "OPENSSH ", "PGP ", "ENCRYPTED ", "DH ", "X25519 ", "ED25519 ", "ED448 ", "SM2 ",
    "SSH2 ENCRYPTED ", "ENCRYPTED X448 ",
)  # fmt: skip
# The line endings CommonMark knows; scrub keeps the prose before the code with any of them.
_NEWLINES = ("\n", "\r\n", "\r")
# What a line that may start code can sit behind (T57): up to 3 spaces, then any mix of quote markers, bullets
# and numbered items.
_CONTAINERS = ("> ", "> > ", "- ", "* ", "+ ", "1. ", "2) ", "100. ", "- - ", "1. > ", "> - ", "* 1. ", "  - ", "   > ")
# Indentation before a fence that still starts code: up to 3 spaces, or a no-break or ideographic space.
_FENCE_INDENTS = ("", "", " ", "  ", "   ", "\u00a0", "\u3000")
# A lone backtick in a backtick fence's info string closes no inline span, so the line still starts code.
_INFO_STRINGS = ("", "", "python", "sh", " python", "python `x`", "sh `npm`", "ts title=`a.ts`", "texto~~~")
# Lines that may open a CommonMark HTML block, with the block's type (1 to 7) (T57 spec review round 3).
_HTML_OPENERS = (
    (1, "<pre>"), (1, "<script>"), (1, '<style type="text/css">'), (1, "<textarea"),
    (2, "<!--"), (2, "<!-- nota"),
    (3, "<?php"), (3, '<?xml version="1.0"?>'),
    (4, "<!DOCTYPE html>"), (4, "<!ELEMENT nota ANY>"),
    (5, "<![CDATA["),
    (6, "<div>"), (6, "</div>"), (6, '<table class="x">'), (6, "<p"),
    (7, "<mi-componente>"), (7, "</span>"), (7, '<a href="x">'),
)  # fmt: skip
# Indentation of 4 columns or more, a tab counting to the next multiple of 4: an indented code line.
_CODE_INDENTS = ("    ", "      ", "\t", "\t\t", " \t", "   \t")
# Spaces CommonMark does not count as blank (only spaces and tabs are): a line indented 4 columns or more that
# holds nothing else is an indented code line (T57 spec review round 4).
_NON_BLANK_SPACES = ("\u00a0", "\u3000", "\u2007", "\u202f")
# Nested quote and list markers whose tab markdown-it (VS Code's preview) reads as reaching 4 columns past the
# innermost container, so what follows is indented code there, though not in commonmark.js (spec review round 4).
_TABS_AFTER_MARKERS = (
    "> >>  \t", "> >>   \t", ">> > \t", ">> >   \t", "> > > \t", ">>>>   \t", " >>>  \t", ">  >> \t",
    ">> - \t", ">> -   \t", ">>> -  \t", ">  >- \t", ">>1. \t", ">>1.   \t", "> >1.  \t",
)  # fmt: skip
# Markers a tab may sit among before a line's content; any such tab starts code by decision (spec review round 5).
_PREFIX_MARKERS = (">", "-", "*", "+", "1.", "2)")
# Characters str.splitlines breaks a line at but CommonMark does not (it ends lines only at "\n", "\r\n"
# and "\r"), so what follows one is mid-line and starts no code, whatever it looks like. Spec review round 5:
# commonmark.js reads a fence where U+2028 or U+2029 sits in an inline ``` span, so by decision a line holding
# any of them that leads with such a span starts code.
_SPLITLINES_ONLY_SEPARATORS = ("\u2028", "\u2029", "\x0b", "\x0c", "\x1c", "\x1d", "\x1e", "\x85")
_MID_LINE_STARTS = ("```", "~~~", "    ```", "<div>", "<!--")
# The code names the example notes hold, all of which must be gone after scrub.
_CODE_NAMES = re.compile(r"codigo_\w+|propietario|LEAK\w*|w3x")


def _noise(rng: random.Random, length: int, alphabet: str = _ALNUM) -> str:
    return "".join(rng.choice(alphabet) for _ in range(length))


def _continuation(containers: str) -> str:
    """What a line inside the containers repeats: every quote marker and tab, with spaces for the rest."""
    return re.sub(r"[^>\t]", " ", containers)


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
    """A generated note, the prose scrub must keep and every piece of project content it must drop.

    The prose tokens on lines before the first line that may start code must survive; every token from that
    line on, prose or code, must be gone. After a private key with no END line, which scrub redacts through
    the end of the text, no prose token has to survive.
    """

    newline: str
    lines: list[str] = field(default_factory=list)
    has_code_started: bool = False
    is_redacted_to_end: bool = False
    kept_prose: list[str] = field(default_factory=list)
    dropped_prose: list[str] = field(default_factory=list)
    code_tokens: list[str] = field(default_factory=list)
    secrets: list[str] = field(default_factory=list)  # one whole credential each, private-key headers included
    key_lines: list[str] = field(default_factory=list)  # body and END lines of private keys
    emails: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return self.newline.join(self.lines)


class _NotesGenerator:
    """Builds notes mixing Spanish prose, credentials, e-mail addresses, private keys and lines that may start code."""

    def __init__(self, rng: random.Random) -> None:
        self.rng = rng
        # Every form generated so far, so the property fails if one stops being generated.
        self.forms: set[str] = set()

    def notes(self) -> _GeneratedNotes:
        notes = _GeneratedNotes(newline=self.rng.choice(_NEWLINES))
        self.forms.add(f"line ending {notes.newline!r}")
        for _ in range(self.rng.randint(1, 8)):
            roll = self.rng.random()
            if roll < 0.5:
                self._paragraph(notes)
            elif roll < 0.85:
                self._code(notes)
            else:
                self._private_key(notes)
        if self.rng.random() < 0.5:
            notes.lines.append("")  # the text ends with a line ending
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

    def _prose_token(self, notes: _GeneratedNotes) -> str:
        """Returns a word no other line holds, filed by whether scrub must keep it or drop it."""
        token = "prosa_" + _noise(self.rng, 10, string.ascii_lowercase)
        if notes.has_code_started:
            notes.dropped_prose.append(token)
        elif not notes.is_redacted_to_end:
            notes.kept_prose.append(token)
        return token

    def _paragraph(self, notes: _GeneratedNotes) -> None:
        bullet = self.rng.choice(("", "", "- ", "> ", "1. ", "> - "))
        has_span_lead = self.rng.random() < 0.2
        if has_span_lead:
            bullet += self._inline_span_lead(notes)
        # A plain word first, so a wrapped item never puts "<" at the start of the line (an HTML block opener).
        words = [self.rng.choice(_PROSE_WORDS)]
        for _ in range(self.rng.randint(2, 11)):
            roll = self.rng.random()
            if roll < 0.25:
                words.append(self._sensitive_item(notes))
            elif roll < 0.4:
                words.append(self.rng.choice(_PROSE_EXTRAS))
            else:
                words.append(self.rng.choice(_PROSE_WORDS))
        words.insert(self.rng.randint(1, len(words)), self._prose_token(notes))
        line = bullet + " ".join(words) + self.rng.choice((".", ":", ""))
        if not has_span_lead and self.rng.random() < 0.2:
            # Only "\n", "\r\n" and "\r" end a line, so a fence, an HTML tag or indentation after the separator is
            # mid-line: it starts no code, and the prose after it survives. Not after an inline span lead, which a
            # separator anywhere on its line turns into code (spec review round 5).
            separator = self.rng.choice(_SPLITLINES_ONLY_SEPARATORS)
            self.forms.add(f"code start after {separator!r}")
            start = self.rng.choice(_MID_LINE_STARTS) + self.rng.choice(_INFO_STRINGS)
            line += separator + start + " " + self._prose_token(notes)
        notes.lines.append(line)

    def _inline_span_lead(self, notes: _GeneratedNotes) -> str:
        """Returns an inline ``` span to open a prose line, which starts code when it holds a separator."""
        lead = self.rng.choice(_INLINE_SPAN_LEADS)
        if self.rng.random() < 0.6:
            self.forms.add("inline span lead")
            return lead
        # Spec review round 5: commonmark.js ends the info string of "```npm\u2028run```" at the separator, so the
        # line opens a fence; by decision any separator only str.splitlines ends lines at does the same.
        separator = self.rng.choice(_SPLITLINES_ONLY_SEPARATORS)
        self.forms.add(f"inline span holding {separator!r}")
        notes.has_code_started = True
        return lead.replace("```", "```" + separator, 1)

    def _code(self, notes: _GeneratedNotes) -> None:
        """Adds lines from one that may start code on; scrub drops them and everything after them."""
        notes.has_code_started = True
        roll = self.rng.random()
        # Their own markers hold the tab, so no other container goes around them.
        if roll < 0.15:
            notes.lines.extend(self._tab_after_markers_lines(notes))
            return
        if roll < 0.3:
            notes.lines.extend(self._tab_in_prefix_lines(notes))
            return
        containers = self.rng.choice(("", "", "", *_CONTAINERS))
        if containers:
            self.forms.add(f"container {containers!r}")
        build = self.rng.choice((self._fence_lines, self._html_lines, self._indented_lines, self._space_only_lines))
        notes.lines.extend(build(notes, containers))

    def _fence_lines(self, notes: _GeneratedNotes, containers: str) -> list[str]:
        character = self.rng.choice("`~")
        self.forms.add(f"{character} fence")
        if containers:
            self.forms.add("fence in a container")
        indent = self.rng.choice(_FENCE_INDENTS)
        if not indent.isascii():
            self.forms.add("fence indented with a non-ASCII space")
        fence = character * self.rng.randint(3, 5)
        info = self.rng.choice(_INFO_STRINGS)
        if self.rng.random() < 0.1:
            # A longer run closes no inline span either (kills the == to >= mutant of the inline-span check).
            info = "py " + character * (len(fence) + 1)
            if character == "`":
                self.forms.add("longer backtick run in the info string")
        if character == "`" and "`" in info:
            self.forms.add("backtick in a backtick fence's info string")
        body_prefix = _continuation(containers)
        lines = [containers + indent + fence + info]
        lines.extend(self._code_line(notes, body_prefix) for _ in range(self.rng.randint(1, 3)))
        if self.rng.random() < 0.6:
            # scrub no longer looks for the close: what follows it is dropped all the same.
            lines.append(body_prefix + fence)
        return lines

    def _html_lines(self, notes: _GeneratedNotes, containers: str) -> list[str]:
        html_type, opener = self.rng.choice(_HTML_OPENERS)
        self.forms.add(f"HTML block type {html_type}")
        if containers:
            self.forms.add("HTML block in a container")
        body_prefix = _continuation(containers)
        # A blank line first, since an HTML block of type 7 cannot interrupt a paragraph.
        lines = ["", containers + opener]
        lines.extend(self._code_line(notes, body_prefix) for _ in range(self.rng.randint(1, 3)))
        if self.rng.random() < 0.5:
            # A fence inside an HTML block is HTML, so the next fence opens a code block (spec review round 3).
            self.forms.add("fence inside an HTML block")
            fence = self.rng.choice(("```", "~~~"))
            lines.insert(2, body_prefix + fence)
            lines.extend((body_prefix + fence, self._code_line(notes, body_prefix), body_prefix + fence))
        return lines

    def _indented_lines(self, notes: _GeneratedNotes, containers: str) -> list[str]:
        if containers:
            # Spaces only: a tab right after a marker may fill fewer than 4 columns of the item's content.
            indentation = " " * self.rng.randint(4, 6)
            self.forms.add("indented code in a container")
        else:
            indentation = self.rng.choice(_CODE_INDENTS)
            self.forms.add("indented code with a tab" if "\t" in indentation else "indented code with spaces")
        body_prefix = _continuation(containers) + indentation
        # A blank line first, since indented code cannot interrupt a paragraph. A fence or a marker behind the
        # indentation is code too.
        first = self._code_line(notes, containers + indentation + self.rng.choice(("", "- ", "> ", "``` ")))
        return ["", first, *(self._code_line(notes, body_prefix) for _ in range(self.rng.randint(0, 2)))]

    def _space_only_lines(self, notes: _GeneratedNotes, containers: str) -> list[str]:
        space = self.rng.choice(_NON_BLANK_SPACES)
        self.forms.add(f"indented line of only {space!r}")
        if containers:
            indentation = " " * self.rng.randint(4, 6)
            self.forms.add("indented line of only non-blank spaces in a container")
        else:
            indentation = self.rng.choice(_CODE_INDENTS)
        # Only spaces and tabs make a line blank, so the line is indented code. The line after it is not code to
        # any reader, so only the rule "drop everything from the first code line on" drops it.
        first = containers + indentation + space * self.rng.randint(1, 2)
        return ["", first, self._code_line(notes, _continuation(containers))]

    def _tab_after_markers_lines(self, notes: _GeneratedNotes) -> list[str]:
        markers = self.rng.choice(_TABS_AFTER_MARKERS)
        self.forms.add(f"tab after markers {markers!r}")
        # A blank line first, since indented code cannot interrupt a paragraph.
        return ["", self._code_line(notes, markers)]

    def _tab_in_prefix_lines(self, notes: _GeneratedNotes) -> list[str]:
        """A line with a tab anywhere before its content, behind any markers: code by decision (spec review round 5)."""
        if self.rng.random() < 0.3:
            # What markdown-it reads as indented code and commonmark.js does not: spaced nested quotes, a list
            # marker, a tab.
            self.forms.add("tab after spaced nested quotes and a list marker")
            quotes = "".join(">" + " " * self.rng.randint(1, 3) for _ in range(2))
            marker = self.rng.choice(_PREFIX_MARKERS[1:])
            prefix = " " * self.rng.randint(0, 1) + quotes + marker + "\t" + " " * self.rng.randint(0, 2)
        else:
            markers = [self.rng.choice(_PREFIX_MARKERS) for _ in range(self.rng.randint(1, 3))]
            # Spaces before the first marker, then after each one; a list marker needs whitespace after it.
            gaps = [" " * self.rng.randint(0, 3)]
            gaps.extend(" " * self.rng.randint(0 if marker == ">" else 1, 3) for marker in markers)
            tab_gap = self.rng.randrange(len(gaps))
            self.forms.add(f"tab after {markers[tab_gap - 1]!r}" if tab_gap else "tab before any marker")
            position = self.rng.randint(0, len(gaps[tab_gap]))
            gaps[tab_gap] = gaps[tab_gap][:position] + "\t" + gaps[tab_gap][position:]
            prefix = gaps[0] + "".join(marker + gap for marker, gap in zip(markers, gaps[1:], strict=True))
        # A blank line first, since indented code cannot interrupt a paragraph.
        return ["", self._code_line(notes, prefix)]

    def _code_line(self, notes: _GeneratedNotes, prefix: str) -> str:
        token = "fuente_" + _noise(self.rng, 10, string.ascii_lowercase)
        notes.code_tokens.append(token)
        line = prefix + self.rng.choice(("def ", "x = ", "", "    return ")) + token
        if self.rng.random() < 0.3:
            line += " " + self._sensitive_item(notes)
        return line

    def _private_key(self, notes: _GeneratedNotes) -> None:
        key_type = self.rng.choice(_KEY_LABELS)
        self.forms.add(f"private key type {key_type!r}")
        label = key_type + "PRIVATE" + " KEY" + self.rng.choice(("", " BLOCK"))
        header = "-----BEGIN " + label + "-----"
        notes.secrets.append(header)
        lines = [_noise(self.rng, 64, _BASE64) for _ in range(self.rng.randint(1, 4))]
        is_closed = self.rng.random() < 0.8
        self.forms.add("closed private key" if is_closed else "unclosed private key")
        if is_closed:
            lines.append("-----END " + label + "-----")
        elif not notes.has_code_started:
            # scrub redacts a key with no END line through the end of the text, prose included.
            notes.is_redacted_to_end = True
        notes.key_lines.extend(lines)
        notes.lines.extend((header, *lines))


class ScrubTest(unittest.TestCase):
    def _assert_one_marker_line_after(self, scrubbed: str, kept_end: str) -> None:
        """Asserts that, after kept_end, the last prose kept, scrub left one line: the marker for what it dropped."""
        self.assertIn(kept_end, scrubbed, f"the prose before the code is missing: {scrubbed!r}")
        rest = scrubbed.split(kept_end, 1)[1]
        marker_lines = [line for line in rest.splitlines() if line.strip()]
        self.assertEqual(len(marker_lines), 1, f"not one marker line after {kept_end!r}: {scrubbed!r}")

    def test_scrub_drops_code_and_redacts_secrets_and_emails(self) -> None:
        # R7.3 (Threats, row 1): the shared notes file never receives a project's code, credentials
        # or e-mail addresses; each removal leaves a short marker so the note still reads in general terms.
        # T57 fix round 4: everything from the first line that may start code is dropped, so the prose
        # after the first block goes too, by decision.
        # Fake credentials are split literals, so this file never holds one a scanner would flag.
        aws_key = "AK" + "IA" + "Q7RZ3M9TB2KX4WNP"
        github_token = "gh" + "p_" + "a8Kd2LmQ9xZr4TbW7nYc3VfHs6PjE1uGo5Ri"
        email = "ana.perez@cliente-ejemplo.cl"
        notes = (
            f"El log del hook mostró la clave {aws_key} completa.\n"
            f"El reviewer copió el token {github_token} en su resumen.\n"
            f"La spec citaba a {email} como responsable.\n"
            "Antes del bloque.\n"
            "```python\n"
            "def filtrar_cliente(rut):\n"
            "    return 'codigo-propietario'\n"
            "```\n"
            "Después del bloque.\n"
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
            "Después del bloque.",
            "Un paso de la lista",
            "sangria_filtrada",
            "Al final quedó una valla sin cerrar:",
            "cola_sin_cerrar",
            "texto tras la valla abierta",
            aws_key,
            github_token,
            email,
        ):
            self.assertNotIn(leaked, scrubbed)
        self.assertEqual(secret_patterns.find_secrets(scrubbed), [])
        self.assertIsNone(re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", scrubbed), scrubbed)
        # Each redaction leaves a marker in place, between the prose that surrounded it.
        for before, after in (
            ("El log del hook mostró la clave ", " completa."),
            ("El reviewer copió el token ", " en su resumen."),
            ("La spec citaba a ", " como responsable."),
        ):
            found = re.search(re.escape(before) + r"(.*?)" + re.escape(after), scrubbed, re.DOTALL)
            self.assertIsNotNone(found, f"prose around the removed part is missing: {scrubbed!r}")
            self.assertTrue(found.group(1).strip(), f"no marker between {before!r} and {after!r}: {scrubbed!r}")
        self._assert_one_marker_line_after(scrubbed, "Antes del bloque.\n")
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
        # R7.3 (Threats, row 1): a prose line that starts with an inline ``` span is not a fence, so it
        # survives and the bare fence after it is where the code starts.
        # Counterexample found by the T47 property and confirmed by the security review. T57 fix round 4:
        # the prose after the block is dropped with it.
        notes = (
            "```npm run check``` falló con este código:\n"
            "```\n"
            "def filtrar_cliente(rut):\n"
            '    return "codigo-propietario"\n'
            "```\n"
            "Fin de las notas.\n"
        )

        scrubbed = improvement_notes.scrub(notes)

        for leaked in ("filtrar_cliente", "codigo-propietario", "```", "Fin de las notas."):
            self.assertNotIn(leaked, scrubbed)
        self.assertIn("npm run check", scrubbed)
        self._assert_one_marker_line_after(scrubbed, "falló con este código:\n")

    def test_scrub_drops_a_fence_indented_with_non_ascii_spaces(self) -> None:
        # R7.3 (Threats, row 1): a fence indented with a no-break or ideographic space may open a block,
        # so its code never reaches the notes. Found by code review round 2: narrowing the indent to
        # spaces and tabs leaked the block. T57 fix round 4: the prose after it is dropped too, whatever
        # closes the block.
        for space in ("\u00a0", "\u3000"):
            plain_close = f"Nota:\n{space}```\ndef filtrar_cliente(): pass\n```\ndef codigo_tras_valla(): pass\n```\n"
            same_space_close = f"Nota:\n{space}```\ndef filtrar_cliente(): pass\n{space}```\nFin.\n"

            scrubbed_plain_close = improvement_notes.scrub(plain_close)
            scrubbed_same_space_close = improvement_notes.scrub(same_space_close)

            for leaked in ("filtrar_cliente", "codigo_tras_valla", "```"):
                self.assertNotIn(leaked, scrubbed_plain_close, f"indent {space!r}: {scrubbed_plain_close!r}")
            for leaked in ("filtrar_cliente", "```", "Fin."):
                self.assertNotIn(leaked, scrubbed_same_space_close, f"indent {space!r}: {scrubbed_same_space_close!r}")
            self._assert_one_marker_line_after(scrubbed_plain_close, "Nota:\n")
            self._assert_one_marker_line_after(scrubbed_same_space_close, "Nota:\n")

    def test_scrub_drops_a_fence_whose_info_string_has_a_backtick(self) -> None:
        # R7.3 (Threats, row 1): a fence whose info string holds a single backtick may still open a block;
        # only a line whose opening run is closed by an equal run later on is an inline span.
        # Found by code review round 2: rejecting any backtick after the run leaked the block.
        notes = "Nota:\n```python `x`\ndef filtrar_cliente(): pass\n```\ndef codigo_tras_valla(): pass\n```\nFin.\n"

        scrubbed = improvement_notes.scrub(notes)

        for leaked in ("filtrar_cliente", "codigo_tras_valla", "```", "Fin."):
            self.assertNotIn(leaked, scrubbed, scrubbed)
        self._assert_one_marker_line_after(scrubbed, "Nota:\n")

    def test_scrub_drops_a_fence_whose_info_string_has_a_longer_backtick_run(self) -> None:
        # R7.3 (Threats, row 1): a run longer than the opening fence later on the line does not close an
        # inline span, so the line may still open a block and "filtrar_cliente" never reaches the notes.
        # Kills the `==` → `>=` mutant of _opening_fence found by T47's mutation review.
        notes = "Nota:\n```py ````\ndef filtrar_cliente(): pass\n````\ndef codigo_tras_valla(): pass\n````\nFin.\n"

        scrubbed = improvement_notes.scrub(notes)

        for leaked in ("filtrar_cliente", "codigo_tras_valla", "```", "Fin."):
            self.assertNotIn(leaked, scrubbed, scrubbed)
        self._assert_one_marker_line_after(scrubbed, "Nota:\n")

    def test_scrub_drops_tilde_and_nested_code_blocks(self) -> None:
        # R7.3 (Threats, row 1): scrub keeps the notes, as given, only up to the first line that may start
        # code, and leaves one marker line in place of everything from that line on. A line may start code,
        # behind any indentation and any list or quote markers, with a fence of backticks or tildes, an
        # HTML block's opener (types 1 to 7) or 4 columns of indentation or more. T57 fix round 4: three
        # spec reviews each found a CommonMark construct that turned a close scrub matched into an opening
        # fence, so scrub matches no close and the prose after the code goes with it, by decision. Spec review
        # round 5: when in doubt, the line is code, so any tab before a line's content starts code, and an inline
        # ``` span starts none only on a line with no separator that only str.splitlines ends lines at.
        before = "Antes del bloque.\n"
        lead = "Antes del bloque.\n\n"
        # Spec review round 4: after nested quote markers, markdown-it (VS Code's preview) reads a tab as reaching 4
        # columns past the innermost container where commonmark.js does not; either reading counts. The last three
        # are code to both parsers.
        tabbed_markers = (
            "> >>  \t", "> >>   \t", ">> > \t", ">> >  \t", ">> >   \t", "> > > \t", ">  >> \t",
            ">> - \t", ">> -  \t", ">> -   \t", ">>1. \t", ">>1.  \t", ">>1.   \t", ">>> - \t",
            ">   \t", "-   \t", "1.  \t",
        )  # fmt: skip
        # Spec review round 5: a tab anywhere before a line's content, whatever columns it reaches.
        tab_prefixes = (
            "\t- ", "\t> ", "\t1. ", " \t ", "> \t", ">\t", "-\t", "*\t", "+\t", "1.\t", "2)\t", "- \t", "> - \t",
            "  -\t", "> >\t", "1. >\t", ">\t  - ",
        )  # fmt: skip
        cases = {
            # T57: "~~~" blocks, blocks opened inside a list item or a quote, closes indented 4 spaces.
            "tilde": (before, "~~~python\ndef codigo_tilde():\n    return 'propietario'\n~~~\n"),
            "longer tilde, shorter tilde and backticks inside": (
                before,
                "~~~~\ncodigo_tilde_largo_a\n```\ncodigo_tilde_largo_b\n~~~\ncodigo_tilde_largo_c\n~~~~\n",
            ),
            "backticks with tildes inside": (before, "```\ncodigo_backtick_a\n~~~\ncodigo_backtick_b\n```\n"),
            "bullet": (before, "- ```python\n  codigo_vineta()\n  ```\n"),
            "bullet with tildes": (before, "- ~~~\n  codigo_vineta_tilde()\n  ~~~\n"),
            "numbered item": (before, "1. ```\n   codigo_numerado()\n   ```\n"),
            "quote": (before, "> ```\n> codigo_cita()\n> ```\n"),
            "backtick close indented 4 spaces": (before, "```\ncodigo_sangria_a\n    ```\ncodigo_sangria_b\n```\n"),
            "tilde close indented 4 spaces": (
                before,
                "~~~\ncodigo_sangria_tilde_a\n    ~~~\ncodigo_sangria_tilde_b\n~~~\n",
            ),
            # Spec review round 1: the line a close-matching reader takes for the end of the block opens a new
            # block in CommonMark, so the "codigo_reabierto" line after it is code too.
            "list marker on an earlier line": (
                before + "- paso\n\n",
                "  ```\n  codigo_lista_a\n```\ncodigo_reabierto_lista\n```\n",
            ),
            "opener indented with a tab": (before, "\t```\nprosa\n```\ncodigo_reabierto_tab\n```\n"),
            "opener indented 4 spaces": (before, "    ```\nprosa\n```\ncodigo_reabierto_sangria\n```\n"),
            "dedented line after a fence on the marker line": (
                before,
                "- ```\n  codigo_lista_b\nprosa\n  ```\ncodigo_reabierto_vineta\n  ```\n",
            ),
            "dedented line after a marker on an earlier line": (
                before + "- paso\n\n",
                "  ```\n  codigo_lista_c\nprosa\n  ```\ncodigo_reabierto_paso\n  ```\n",
            ),
            "item numbered 2 after a paragraph": (
                before + "Texto.\n",
                "2. ```\ncodigo_a\n```\ncodigo_reabierto_a\n```\n",
            ),
            "item numbered 2 after a paragraph, fence at its content column": (
                before + "Texto.\n",
                "2. ```\n   codigo_b\n   ```\ncodigo_reabierto_b\n```\n",
            ),
            # Spec review round 2 and a markdown-it fuzz: list or quote markers indented 4 columns or more past
            # the item they sit in open nothing, so the line is a lazy continuation of the item's paragraph and
            # a later fence in the item opens a block.
            "review: bullet indented 4 spaces under '100. '": (
                lead + "100. Paso\n",
                "    - ```py\n      ```\n      codigo_filtrado()\n      ```\n",
            ),
            "review: bullet indented 4 spaces under '1.   '": (
                lead + "1.   a\n",
                "    - ```\n      ```\n      LEAK1\n",
            ),
            "review: tildes": (lead + "1.   a\n", "    * ~~~\n      ~~~\n      LEAK5\n"),
            "review: fuzzer, quote in an item numbered 2": (
                lead + "  2) > w0x\n",
                "    - ```py\n      ```\n\t  >w3x\n",
            ),
            "tab before the marker": (lead + "1.   a\n", "\t- ```\n\t  ```\n\t  codigo_tab\n"),
            "space and tab before the marker": (lead + "1.   a\n", " \t+ ```\n\t  ```\n\t  codigo_espacio_tab\n"),
            "numbered marker": (lead + "1.   a\n", "    1. ```\n       ```\n       codigo_numerado\n"),
            "numbered marker with a parenthesis": (
                lead + "1.   a\n",
                "    1) ~~~\n       ~~~\n       codigo_parentesis\n",
            ),
            "nested markers '- - '": (lead + "1.   a\n", "    - - ```\n        ```\n        codigo_anidado\n"),
            "nested markers '1. - ' under a 9-digit item": (
                lead + "123456789. a\n",
                "      1. - ```\n           ```\n           codigo_anidado_numerado\n",
            ),
            "quote marker after the list marker": (
                lead + "1.   a\n",
                "    - > ```\n      > ```\n      > codigo_cita\n",
            ),
            "'1. > '": (lead + "1.   a\n", "    1. > ```\n       > ```\n       > codigo_cita_numerada\n"),
            "deeper item opened on an earlier line": (
                lead + "1. a\n   1.   b\n",
                "       - ```\n         ```\n         codigo_profundo\n",
            ),
            "item inside a quote": (lead + "> 100. a\n", ">     - ```\n>       ```\n>       codigo_en_cita\n"),
            "lazy line before the opener": (
                lead + "100. a\nperezosa\n",
                "    - ```\n      ```\n      codigo_tras_perezosa\n",
            ),
            "4-digit item, 5 spaces": (lead + "1000. a\n", "     - ```\n       ```\n       codigo_ancho\n"),
            "9-digit item, 9 spaces": (
                lead + "123456789. a\n",
                "         - ```\n           ```\n           codigo_muy_ancho\n",
            ),
            "quote inside the item": (lead + "100. > a\n", "\t- > ```\n\t  > ```\n\t  > codigo_cita_en_item\n"),
            "item inside a quote, opener without the quote marker": (
                lead + "> 100. a\n",
                "\t- > ```\n\t  > ```\n\t  > codigo_cita_perezosa\n",
            ),
            # Spec review round 3: an HTML block holds what looks like a fence, so the next fence opens code.
            "review: comment holding tildes": (lead, "<!--\n~~~\n-->\n~~~\nLEAK_A()\n~~~\n"),
            "review: <pre> holding backticks": (lead, "<pre>\n```\n</pre>\n```\nLEAK_B()\n```\n"),
            "review: <div> holding backticks": (lead, "<div>\n```\n\n```\nLEAK_C()\n```\n"),
            "review: comment in a list item": (lead, "- <!--\n  ~~~\n  -->\n  ~~~\n  LEAK_D()\n  ~~~\n"),
            # HTML blocks and indented code hold code with no fence at all.
            "HTML block of type 1": ("Texto.\n\n", "<pre>\ncodigo_html()\n</pre>\n"),
            "HTML block of type 3": (lead, "<?php\ncodigo_php();\n?>\n"),
            "HTML block of type 4": (lead, "<!DOCTYPE html>\ncodigo_doctype()\n"),
            "HTML block of type 5": (lead, "<![CDATA[\ncodigo_cdata()\n]]>\n"),
            "HTML block of type 6, closing tag": (lead, "</div>\ncodigo_cierre_div()\n"),
            "HTML block of type 7": (lead, "<mi-componente>\ncodigo_tipo_siete()\n"),
            "HTML block in a quote": (lead, "> <div>\n> codigo_html_en_cita()\n"),
            "indented code": ("Texto.\n\n", "    codigo_indentado()\n"),
            "tab-indented code": ("Texto.\n\n", "\tcodigo_tabulado()\n"),
            "indented code in a list item": ("Texto.\n\n", "-     codigo_en_item()\n"),
            # Spec review round 4: only spaces and tabs make a line blank (commonmark.js and markdown-it agree), so a
            # line indented 4 columns or more that holds only a no-break or other Unicode space is indented code.
            # The line after it is prose, dropped because it follows the code.
            "review: no-break space indented 4 spaces": ("Nota:\n\n", "    \u00a0\ndef codigo_secreto(): pass\n"),
            "review: no-break space 6 spaces past '1.'": ("", "1.      \u00a0\ndef codigo_secreto(): pass\n"),
            "review: no-break space after a tab": ("", "\t\u00a0\ndef codigo_secreto(): pass\n"),
            "ideographic space indented 4 spaces": ("Nota:\n\n", "    \u3000\ndef codigo_secreto(): pass\n"),
            "ideographic space 6 spaces past '1.'": ("Nota:\n\n", "1.      \u3000\ndef codigo_secreto(): pass\n"),
            "figure space after a tab": ("Nota:\n\n", "\t\u2007\ndef codigo_secreto(): pass\n"),
            "narrow no-break space 5 spaces past '-'": ("", "-     \u202f\ndef codigo_secreto(): pass\n"),
            "two no-break spaces 5 spaces past '>'": ("Nota:\n\n", ">     \u00a0\u00a0\ndef codigo_secreto(): pass\n"),
            "figure spaces indented 6 spaces": ("Nota:\n\n", "      \u2007\u2007\ndef codigo_secreto(): pass\n"),
            **{
                f"tab after {markers!r}": ("Nota:\n\n", markers + "def codigo_secreto(): pass\n")
                for markers in tabbed_markers
            },
            "tab after '>>>>  ' at the start of the notes": ("", ">>>>  \tdef codigo_secreto(): pass\n"),
            # Spec review round 5: markdown-it reads indented code behind spaced nested quotes, a list marker and a
            # tab, and commonmark.js reads a fence where U+2028 or U+2029 sits in an inline span (a JavaScript "."
            # stops at them). By decision, a tab anywhere before a line's content, behind any markers, starts code,
            # and so does a leading ``` on a line holding any separator only str.splitlines ends lines at.
            "review: tab after '> >   -'": ("Nota:\n\n", "> >   -\t  def codigo_secreto(): pass\n"),
            "review: tab after ' >   >   1.' at the start of the notes": (
                "",
                " >   >   1.\t def codigo_secreto(): pass\n",
            ),
            "review: U+2028 in an inline span": (
                "Nota:\n\n",
                "```npm\u2028run``` fallo:\ndef codigo_secreto(): pass\n```\nFin.\n",
            ),
            "review: U+2029 in an inline span at the start of the notes": (
                "",
                "```\u2029```\ndef codigo_secreto(): pass\n```\n",
            ),
            **{
                f"tab in the prefix {prefix!r}": ("Nota:\n\n", prefix + "def codigo_secreto(): pass\n")
                for prefix in tab_prefixes
            },
            "tab after '-' right after a paragraph": ("Nota:\n", "-\tdef codigo_secreto(): pass\n"),
            **{
                f"{separator!r} in an inline span": (
                    "Nota:\n\n",
                    f"```npm{separator}run``` fallo:\ndef codigo_secreto(): pass\n",
                )
                for separator in _SPLITLINES_ONLY_SEPARATORS
            },
            "U+2028 after an inline span on its line": (
                "Nota:\n\n",
                "```npm run``` fallo\u2028sigue:\ndef codigo_secreto(): pass\n",
            ),
        }
        for form, (kept, from_code) in cases.items():
            code_names = _CODE_NAMES.findall(from_code)
            for newline in _NEWLINES:
                with self.subTest(form=form, newline=newline):
                    kept_text = kept.replace("\n", newline)
                    notes = kept_text + (from_code + "Después del bloque.\n").replace("\n", newline)
                    self.assertTrue(code_names, f"no code name to look for in {from_code!r}")
                    # The line a bare fence leaves: the marker alone, ending as the fence's line ended.
                    marker_line = improvement_notes.scrub("```" + newline)

                    scrubbed = improvement_notes.scrub(notes)

                    for leaked in (*code_names, "Después del bloque.", "```", "~~~"):
                        self.assertNotIn(leaked, scrubbed, scrubbed)
                    self.assertTrue(scrubbed.startswith(kept_text), f"the prose before the code changed: {scrubbed!r}")
                    # Exactly the marker line follows: no line of Unicode spaces stays behind (str.strip drops them).
                    self.assertEqual(
                        scrubbed[len(kept_text) :],
                        marker_line,
                        f"not one marker line in place of the code: {scrubbed!r}",
                    )

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

    def test_scrub_removes_every_pem_private_key_block(self) -> None:
        # R7.3 (Threats, row 1), T58: a PEM private key of any type (BEGIN DH PRIVATE KEY between dashes,
        # X25519, ED25519…) is dropped whole, from its BEGIN line through its END line, or through the end
        # of the text when END is missing, and the prose around it stays.
        # Fake key material is split literals, so this file never holds one a scanner would flag.
        secret_marker = improvement_notes.scrub("-----BEGIN " + "RSA PRIVATE" + " KEY-----").strip()
        body_lines = ("MIIBIjANBgkq" + "FirmaFalsaDeTipo", "Q29ycG9EZUxh" + "Q2xhdmVGYWxzYQ==")
        body = "".join(line + "\n" for line in body_lines)
        for key_type in ("DH", "X25519", "ED25519", "ED448", "SM2", "ANY"):
            header = "-----BEGIN " + key_type + " PRIVATE" + " KEY-----"
            end = "-----END " + key_type + " PRIVATE" + " KEY-----"
            closed = f"Clave filtrada:\n{header}\n{body}{end}\nTexto tras la clave cerrada.\n"
            unclosed = f"Otra clave sin cierre:\n{header}\n{body}"
            for notes, kept_before, kept_after in (
                (closed, "Clave filtrada:\n", "Texto tras la clave cerrada.\n"),
                (unclosed, "Otra clave sin cierre:\n", ""),
            ):
                with self.subTest(key_type=key_type, is_closed=bool(kept_after)):
                    scrubbed = improvement_notes.scrub(notes)

                    self.assertTrue(scrubbed.startswith(kept_before), f"the prose before the key changed: {scrubbed!r}")
                    self.assertTrue(scrubbed.endswith(kept_after), f"the prose after the key is missing: {scrubbed!r}")
                    self.assertIn(secret_marker, scrubbed)
                    for leaked in ("-----BEGIN", "-----END", "PRIVATE KEY", *body_lines):
                        self.assertNotIn(leaked, scrubbed, scrubbed)

    def test_scrubbed_notes_never_keep_secrets_code_or_emails(self) -> None:
        # R7.3 (Threats, row 1): over 400 generated notes, scrub keeps the prose before the first line that
        # may start code and drops everything from that line on, prose included; the result keeps no fence,
        # nothing find_secrets reports, no e-mail address and none of the generated code, credentials or
        # addresses. T57 fix round 4: a line may start code, behind up to 3 spaces and any list or quote
        # markers, with a fence of backticks or tildes (also behind a no-break or ideographic space), an HTML
        # block's opener (types 1 to 7) or 4 columns of indentation or more. An inline ``` span starts no code,
        # nor does anything after a separator only str.splitlines ends lines at. Spec review round 4: a line
        # indented 4 columns or more that holds only a no-break or other Unicode space starts code (only spaces
        # and tabs make a line blank), and so does a tab after nested markers that markdown-it reads as indented
        # code even where commonmark.js does not. Spec review round 5, by decision: a tab anywhere before a line's
        # content, behind any markers, starts code, and an inline ``` span leading a line that holds a separator
        # only str.splitlines ends lines at starts code too. T58: a private key of any PEM type (DH, X25519, ED448,
        # SM2, several words or none), closed or not, keeps none of its header, body or END lines.
        rng = random.Random(17)  # noqa: S311 - repeatable generated notes for tests, not cryptography
        generator = _NotesGenerator(rng)
        covered_patterns: set[secret_patterns.SecretPattern] = set()
        kept_count = dropped_count = 0
        for index in range(400):
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
            self.assertNotIn("~~~", scrubbed, failure)
            self.assertEqual(secret_patterns.find_secrets(scrubbed), [], failure)
            # An oracle independent of scrub's own e-mail regex: anything shaped like name@host.tld.
            self.assertIsNone(re.search(r"\S+@\S+\.\S+", scrubbed), failure)
            # A fragment of an address, such as the name before a dot, is personal data too.
            name_pieces = [piece for address in case.emails for piece in re.split(r"[._+-]", address.split("@")[0])]
            for leaked in (
                *case.secrets,
                *case.key_lines,
                *case.emails,
                *name_pieces,
                *case.code_tokens,
                *case.dropped_prose,
            ):
                self.assertNotIn(leaked, scrubbed, failure)
            for kept in case.kept_prose:
                self.assertIn(kept, scrubbed, f"{failure}\nprose before the code was dropped: {kept!r}")
            kept_count += len(case.kept_prose)
            dropped_count += len(case.dropped_prose)
        self.assertEqual(
            covered_patterns, set(secret_patterns.SECRET_PATTERNS), "a credential format was not generated"
        )
        self.assertGreater(kept_count, 0, "no prose was generated before code")
        self.assertGreater(dropped_count, 0, "no prose was generated after code")
        expected_forms = {
            *(f"line ending {newline!r}" for newline in _NEWLINES),
            "inline span lead",
            *(f"code start after {separator!r}" for separator in _SPLITLINES_ONLY_SEPARATORS),
            *(f"container {containers!r}" for containers in _CONTAINERS),
            "` fence",
            "~ fence",
            "fence in a container",
            "fence indented with a non-ASCII space",
            "backtick in a backtick fence's info string",
            "longer backtick run in the info string",
            *(f"HTML block type {html_type}" for html_type in range(1, 8)),
            "HTML block in a container",
            "fence inside an HTML block",
            "indented code with spaces",
            "indented code with a tab",
            "indented code in a container",
            *(f"indented line of only {space!r}" for space in _NON_BLANK_SPACES),
            "indented line of only non-blank spaces in a container",
            *(f"tab after markers {markers!r}" for markers in _TABS_AFTER_MARKERS),
            *(f"inline span holding {separator!r}" for separator in _SPLITLINES_ONLY_SEPARATORS),
            "tab before any marker",
            *(f"tab after {marker!r}" for marker in _PREFIX_MARKERS),
            "tab after spaced nested quotes and a list marker",
            *(f"private key type {key_type!r}" for key_type in _KEY_LABELS),
            "closed private key",
            "unclosed private key",
        }
        self.assertEqual(generator.forms, expected_forms, "a form of code or prose was not generated")


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
