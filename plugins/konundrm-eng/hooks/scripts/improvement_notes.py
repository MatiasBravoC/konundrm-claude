"""Keeps a slice's or feature's improvement notes, free of project content, in the central notes file.

The file lives at a fixed path inside Claude's configuration folder and is shared by every
project, so the project and feature names only ever go into its content, each on one line, and
never into the path, and the notes are scrubbed of code, credentials and e-mail addresses first.

Sections:
    NOTES_FILE          — where the notes file lives, relative to Claude's configuration folder.
    FALLBACK_NOTES_FILE — the notes file's name in the feature's folder when the central one fails.
    scrub()             — drops everything from the first line that may start code and redacts
                          credentials and e-mail addresses.
    append_notes()      — adds one dated entry tagged with project, feature and scope.
    main()              — command line: notes on stdin, --project, --feature and --scope.
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

from secret_patterns import PRIVATE_KEY_LABEL, SECRET_PATTERNS
from session_doctor import claude_config_directory

NOTES_FILE = Path("konundrm-eng") / "improvements.md"
FALLBACK_NOTES_FILE = "improvement-notes.md"

_CODE_MARKER = "[rest omitted: it may contain code]"
_SECRET_MARKER = "[secret removed]"  # noqa: S105 - the text left in place of a credential, not one
_EMAIL_MARKER = "[email removed]"

# scrub has no Markdown parser, and every attempt to find where CommonMark ends a code block met
# another construct that turned that "end" into the start of a new block. So scrub never looks for
# an end: it keeps the notes only up to the first line that may start code and drops the rest.
#
# One line with its ending. As in CommonMark, only "\n", "\r\n" and "\r" end a line: str.splitlines
# also breaks at U+2028, U+2029, "\x0b", "\x0c", "\x1c" to "\x1e" and U+0085, and what follows one of
# those is mid-line content that starts nothing.
_LINE = re.compile(r"[^\r\n]*(?:\r\n|\r|\n)|[^\r\n]+")
# The characters str.splitlines ends a line at and CommonMark does not, as a regex class body.
_SPLITLINES_ONLY_SEPARATORS = r"\x0b\x0c\x1c-\x1e\x85\u2028\u2029"
# commonmark.js reads a fence where one of them sits in a leading ``` span (a JavaScript "." stops at
# U+2028 and U+2029), so a line holding any of them gets no inline-span exception, erring on the safe side.
_SPLITLINES_ONLY_SEPARATOR = re.compile(rf"[{_SPLITLINES_ONLY_SEPARATORS}]")
# Whitespace within a line: Python's \s without the characters str.splitlines ends a line at. Any of
# it counts as indentation, a no-break or ideographic space included, which errs on the safe side.
# Only spaces and tabs make a line blank, though: a line holding other whitespace has content.
_SPACE = rf"[^\S\r\n{_SPLITLINES_ONLY_SEPARATORS}]"
_INDENTATION_CHARACTER = re.compile(_SPACE)
# A quote marker, with or without a space after it, or a list item's marker ("-", "*", "+", "1.",
# "1)", any number) followed by whitespace or the line's end. Read generously: taking prose for a
# container only moves the line's content column, never hides a fence or an HTML tag behind it.
_CONTAINER_MARKER = re.compile(rf">|(?:[-*+]|\d+[.)])(?={_SPACE}|\Z)")
# The only characters a blank line may hold.
_BLANK_CHARACTERS = " \t"
# How far past where its container's content starts a line is indented code.
_INDENTED_CODE_COLUMNS = 4
_FENCE_RUN = re.compile(r"`{3,}|~{3,}")
# Any run of backticks; a later run exactly as long as the line's first one closes an inline span.
_ANY_BACKTICK_RUN = re.compile(r"`+")
# Every opener of a CommonMark HTML block (types 1 to 7: "<" and a tag name, "</", "<!--", "<?",
# "<!" and a letter, "<![CDATA["), and a few more lines, which errs on the safe side.
_HTML_BLOCK_OPENER = re.compile(r"<[A-Za-z/?!]")
# Three or more backticks or tildes in a kept line (an inline span, a strikethrough, a fence after a
# separator only str.splitlines ends lines at); reduced to one character so no fence remains.
_FENCE_CHARACTER_RUN = re.compile(r"([`~])\1{2,}")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
# A whole private key: the BEGIN header secret_patterns detects through the first END line of any
# private key type, or through the end of the text when END is missing, since the header alone
# leaves the key body.
_PRIVATE_KEY_BLOCK = re.compile(
    rf"-----BEGIN {PRIVATE_KEY_LABEL}-----.*?(?:-----END {PRIVATE_KEY_LABEL}-----|\Z)",
    re.DOTALL,
)


def scrub(notes: str) -> str:
    """Removes a project's code, credentials and e-mail addresses from notes.

    The notes are kept only up to the first line that may start code; that line and everything
    after it, prose included, are replaced by one "[rest omitted: it may contain code]" line.
    Dropping prose errs on the safe side: without a Markdown parser, scrub cannot tell for sure
    where a code block ends. A line may start code when, after any indentation (a no-break or
    ideographic space counts as indentation) and any quote markers (">") and list markers ("-",
    "*", "+", "1.", "1)"), it holds:

    - a fence: three or more backticks or tildes. A backtick line is instead an inline span (as in
      "```npm run check``` failed") when a run of exactly as many backticks follows later on it
      and the line holds none of the separators below; a shorter or longer run, such as a lone
      backtick in the info string, still starts code. Tildes have no inline span, so "~~~text~~~"
      starts code.
    - an HTML block's opener: "<" followed by a letter, "/", "?" or "!", which covers every
      CommonMark HTML block (types 1 to 7: a tag, a closing tag, "<!--", "<?", "<!DOCTYPE",
      "<![CDATA[").
    - a tab anywhere in the indentation or among the markers: CommonMark readers disagree on how
      many columns a tab behind markers reaches, so any such tab starts code.
    - indented code: 4 columns or more of indentation past where the content of the line's last
      container starts (or the line's start), the one space after a marker belonging to the
      marker. Every indentation character counts one column.

    A line holding nothing but spaces and tabs is blank and starts nothing, and so is one holding
    nothing but spaces after its markers; one whose indentation holds other whitespace, such as
    four spaces and a no-break space, is indented code.

    As in CommonMark, a line ends only at a line feed, a carriage return or the two together. Any
    other separator (U+2028, U+2029, a vertical tab, a form feed, U+001C to U+001E, U+0085) is a
    character within its line, so what follows it starts no code; a line holding one gets no
    inline-span exception, since a CommonMark reader may end a fence's info string at it. Any run
    of three or more backticks or tildes left in the kept lines, such as an inline span, is
    reduced to one character.
    Then every private key of any type (RSA, EC, DH, X25519, ED448, OPENSSH…, or none), from its
    "-----BEGIN … PRIVATE KEY-----" header through the next "-----END … PRIVATE KEY-----" line
    (or through the end of the text when that line is missing), every other match of a
    ``secret_patterns.SECRET_PATTERNS`` pattern, placeholder or not, becomes "[secret removed]"
    and every e-mail address "[email removed]", repeated until nothing matches, since removing
    one value can expose another that it was glued to.

    Args:
        notes: Text of the notes, in Markdown.

    Returns:
        The notes before the first line that may start code, with every other character, line
        break included, kept as given; then, when such a line exists, the marker line in its place,
        ending as that line ended. The result has no three backticks or three tildes in a row,
        nothing ``secret_patterns.find_secrets`` reports and no e-mail address.
    """
    return _redact_until_clean(_drop_code(notes))


def _drop_code(text: str) -> str:
    kept = []
    for line_match in _LINE.finditer(text):
        line = line_match.group()
        content = line.rstrip("\r\n")
        if _may_start_code(content):
            kept.append(_CODE_MARKER + line[len(content) :])
            break
        kept.append(_FENCE_CHARACTER_RUN.sub(r"\1", line))
    return "".join(kept)


def _may_start_code(content: str) -> bool:
    """Whether a line, without its ending, may start code under any container it may be in."""
    if not content.strip(_BLANK_CHARACTERS):
        return False
    # Any tab in the prefix starts code, so every character read counts one column: column == position.
    content_start = position = 0
    while True:
        # Tracked while the indentation is read, so each line is still scanned once (linear time).
        is_blank = True
        while position < len(content) and _INDENTATION_CHARACTER.match(content, position):
            if content[position] == "\t":
                # CommonMark readers disagree on the columns a tab behind markers reaches, so any tab
                # before the content starts code, erring on the safe side.
                return True
            is_blank = is_blank and content[position] == " "
            position += 1
        if position == len(content) and is_blank:
            # A blank line inside its containers starts nothing; one with other whitespace goes on to
            # the column check.
            return False
        if position - content_start >= _INDENTED_CODE_COLUMNS:
            return True
        marker = _CONTAINER_MARKER.match(content, position)
        if marker is None:
            return _starts_fence(content, position) or _HTML_BLOCK_OPENER.match(content, position) is not None
        position = marker.end()
        # As in CommonMark, the space after a marker belongs to the marker (a tab starts code above).
        content_start = position + (content[position : position + 1] == " ")


def _starts_fence(content: str, position: int) -> bool:
    run = _FENCE_RUN.match(content, position)
    if run is None:
        return False
    if run.group()[0] == "~" or _SPLITLINES_ONLY_SEPARATOR.search(content):
        # Tildes have no inline span, so "~~~tachado~~~" starts code too, and neither does a line
        # holding a separator commonmark.js may end an info string at, erring on the safe side.
        return True
    # The run is greedy, so the rest of the line starts after its last backtick.
    later_runs = _ANY_BACKTICK_RUN.finditer(content, run.end())
    return not any(len(later.group()) == len(run.group()) for later in later_runs)


def _redact_until_clean(text: str) -> str:
    # Each pass replaces only original characters (no pattern matches a marker), so it ends.
    while True:
        redacted = _PRIVATE_KEY_BLOCK.sub(_SECRET_MARKER, text)
        for secret in SECRET_PATTERNS:
            redacted = secret.pattern.sub(_SECRET_MARKER, redacted)
        redacted = _EMAIL.sub(_EMAIL_MARKER, redacted)
        if redacted == text:
            return text
        text = redacted


def append_notes(
    notes: str,
    *,
    project: str,
    feature: str,
    scope: str,
    today: date,
    config_dir: Path,
    fallback_dir: Path,
) -> tuple[Path, bool]:
    """Adds one dated entry with the notes to the end of the central notes file, or of the fallback.

    Earlier content is never erased or changed. Project, feature and scope are written on a
    single line each (any line break or run of whitespace becomes one space), so a hostile name
    can neither change the path nor forge a new line in the file. When the central folder or file
    cannot be created or written, the same entry goes to ``fallback_dir / FALLBACK_NOTES_FILE``
    instead, so the notes stay with the feature's documents.

    Args:
        notes: Text of the notes, written as given.
        project: Name of the project the notes come from.
        feature: Name of the feature the notes are about.
        scope: What the notes cover, such as "slice 2" or "feature".
        today: Date stamped on the entry.
        config_dir: Claude's configuration folder; the file is ``config_dir / NOTES_FILE``.
        fallback_dir: The feature's folder, which must already exist; used only when the central
            file cannot be written.

    Returns:
        The path written to and whether it was the fallback.

    Raises:
        OSError: If the central file cannot be written and the fallback file cannot either.

    Side effects:
        Creates ``config_dir / NOTES_FILE`` and its folder when missing, then appends to it; on
        failure, creates or appends to ``fallback_dir / FALLBACK_NOTES_FILE`` instead.
    """
    entry = (
        f"\n## {today.isoformat()} · {_single_line(scope)}\n\n"
        f"- Project: {_single_line(project)}\n"
        f"- Feature: {_single_line(feature)}\n\n"
        f"{notes.rstrip()}\n"
    )
    central_path = config_dir / NOTES_FILE
    try:
        central_path.parent.mkdir(parents=True, exist_ok=True)
        _append_entry(central_path, entry)
    except OSError:
        fallback_path = fallback_dir / FALLBACK_NOTES_FILE
        _append_entry(fallback_path, entry)
        return fallback_path, True
    return central_path, False


def _append_entry(path: Path, entry: str) -> None:
    with path.open("a", encoding="utf-8", newline="\n") as notes_file:
        notes_file.write(entry)


def _single_line(value: str) -> str:
    return " ".join(value.split())


def main(argv: list[str] | None = None) -> int:
    """Scrubs the notes read from stdin and appends them to the central notes file, or the fallback.

    The central file is ``NOTES_FILE`` inside Claude's configuration folder
    (``session_doctor.claude_config_directory``); the fallback is
    ``specs/<--feature>/improvement-notes.md`` under the working directory, the project root.

    Args:
        argv: Command-line arguments without the program name; ``sys.argv[1:]`` when None.
            ``--project``, ``--feature`` and ``--scope`` are required, and ``--feature`` must be a
            single folder name under ``specs/`` (no separator, drive, "." or "..").

    Returns:
        0 when the notes were written, naming the file on stdout (and, when it was the fallback,
        warning on stderr which central file failed); 1 when neither file could be written. A
        usage error, including an unsafe ``--feature``, exits with 2 before anything is written.

    Side effects:
        Reads stdin to its end as UTF-8 whatever the locale, replacing undecodable bytes with
        U+FFFD; creates or appends to one of the two notes files.
    """
    arguments = _parse_arguments(argv)
    # Decoded explicitly: the locale's code page (cp1252 on Windows) would garble or crash on UTF-8.
    notes = scrub(sys.stdin.buffer.read().decode("utf-8", errors="replace"))
    config_dir = claude_config_directory()
    central_path = config_dir / NOTES_FILE
    fallback_dir = Path.cwd() / "specs" / arguments.feature
    try:
        written_path, used_fallback = append_notes(
            notes,
            project=arguments.project,
            feature=arguments.feature,
            scope=arguments.scope,
            today=date.today(),
            config_dir=config_dir,
            fallback_dir=fallback_dir,
        )
    except OSError as error:
        print(
            f"improvement notes not saved: neither {central_path} nor "
            f"{fallback_dir / FALLBACK_NOTES_FILE} could be written ({error.strerror or error}).",
            file=sys.stderr,
        )
        return 1
    if used_fallback:
        print(f"warning: could not write {central_path}; the notes stay with the feature.", file=sys.stderr)
    print(f"Improvement notes saved to {written_path}")
    return 0


def _parse_arguments(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="improvement_notes.py",
        description="Appends the improvement notes read from stdin, scrubbed of code, credentials and "
        "e-mail addresses, to the central notes file, or to the feature's folder when that fails.",
    )
    parser.add_argument("--project", required=True, help="name of the project the notes come from")
    parser.add_argument("--feature", required=True, help="the feature's folder name under specs/")
    parser.add_argument("--scope", required=True, help='what the notes cover, such as "slice 2" or "feature"')
    arguments = parser.parse_args(argv)
    if not _is_folder_name(arguments.feature):
        parser.error(f"--feature must be one folder name under specs/, not {arguments.feature!r}")
    return arguments


def _is_folder_name(name: str) -> bool:
    # Path(name).name drops any drive, root or parent part, so it equals name only for one segment;
    # both separators are refused on every platform so the check does not depend on the OS.
    return name not in ("", ".", "..") and "/" not in name and "\\" not in name and Path(name).name == name


if __name__ == "__main__":
    sys.exit(main())
