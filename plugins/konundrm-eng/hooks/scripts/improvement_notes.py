"""Keeps a slice's or feature's improvement notes, free of project content, in the central notes file.

The file lives at a fixed path inside Claude's configuration folder and is shared by every
project, so the project and feature names only ever go into its content, each on one line, and
never into the path, and the notes are scrubbed of code, credentials and e-mail addresses first.

Sections:
    NOTES_FILE          — where the notes file lives, relative to Claude's configuration folder.
    FALLBACK_NOTES_FILE — the notes file's name in the feature's folder when the central one fails.
    scrub()             — drops code blocks and redacts credentials and e-mail addresses.
    append_notes()      — adds one dated entry tagged with project, feature and scope.
    main()              — command line: notes on stdin, --project, --feature and --scope.
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

from secret_patterns import SECRET_PATTERNS
from session_doctor import claude_config_directory

NOTES_FILE = Path("konundrm-eng") / "improvements.md"
FALLBACK_NOTES_FILE = "improvement-notes.md"

_CODE_MARKER = "[code removed]"
_SECRET_MARKER = "[secret removed]"  # noqa: S105 - the text left in place of a credential, not one
_EMAIL_MARKER = "[email removed]"

# The start of a line (matched without its ending, so it cannot reach the next line) that may open
# a fenced block: three or more backticks at any indentation, as wide as _CLOSING_FENCE accepts
# (list items indent theirs, and a no-break space is still indentation).
_FENCE_START = re.compile(r"\s*(`{3,})")
# A line that is only a fence; it closes the block when at least as long as the opening one.
_CLOSING_FENCE = re.compile(r"\s*(`{3,})\s*")
# Any run of backticks; a later run exactly as long as the line's first one closes an inline span.
_ANY_BACKTICK_RUN = re.compile(r"`+")
# Three or more backticks outside a block (an inline span); reduced to one so no fence remains.
_BACKTICK_RUN = re.compile(r"`{3,}")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
# A whole private key: secret_patterns' BEGIN header through its END line, or through the end of
# the text when END is missing (like an unclosed fence), since the header alone leaves the key body.
_PRIVATE_KEY_BEGIN = next(secret.pattern.pattern for secret in SECRET_PATTERNS if secret.kind == "private key")
_PRIVATE_KEY_BLOCK = re.compile(
    _PRIVATE_KEY_BEGIN + r".*?(?:-----END [A-Z ]*PRIVATE KEY[A-Z ]*-----|\Z)",
    re.DOTALL,
)


def scrub(notes: str) -> str:
    """Removes a project's code, credentials and e-mail addresses from notes.

    Every fenced code block is dropped with its contents and replaced by a "[code removed]" line.
    A block opens at a line starting with three or more backticks, at any indentation, unless a
    run of exactly as many backticks follows later on that line, which makes the start an inline
    span (as in "```npm run check``` failed"); a shorter or longer run, such as a lone backtick
    in the info string, still opens a block. The block closes at a line holding only a fence at
    least as long as the opening one, and a block never closed runs to the end of the text. An
    inline span split across lines is therefore dropped as a block, erring on the safe side.
    Any other run of three or more backticks, such as an inline span, is reduced to one.
    Then every private key outside a block, from its "-----BEGIN … PRIVATE KEY-----" header
    through its "-----END … PRIVATE KEY-----" line (or through the end of the text when that line
    is missing), every other match of a ``secret_patterns.SECRET_PATTERNS`` pattern, placeholder
    or not, becomes "[secret removed]" and every e-mail address "[email removed]", repeated until
    nothing matches, since removing one value can expose another that it was glued to.

    Args:
        notes: Text of the notes, in Markdown.

    Returns:
        The notes with every other character, line break included, kept as given. The result has
        no triple backticks, nothing ``secret_patterns.find_secrets`` reports and no e-mail address.
    """
    return _redact_until_clean(_drop_code_blocks(notes))


def _drop_code_blocks(text: str) -> str:
    kept = []
    closing_fence_length = 0  # 0 while outside a block
    for line in text.splitlines(keepends=True):
        if closing_fence_length:
            closing = _CLOSING_FENCE.fullmatch(line)
            if closing and len(closing.group(1)) >= closing_fence_length:
                closing_fence_length = 0
            continue
        content = line.splitlines()[0]
        opening = _opening_fence(content)
        if opening:
            closing_fence_length = len(opening.group(1))
            kept.append(line[: opening.start(1)] + _CODE_MARKER + line[len(content) :])
        else:
            kept.append(_BACKTICK_RUN.sub("`", line))
    return "".join(kept)


def _opening_fence(content: str) -> re.Match[str] | None:
    # The fence's run is greedy, so the rest starts after its last backtick.
    start = _FENCE_START.match(content)
    if start is None:
        return None
    fence_length = len(start.group(1))
    rest = content[start.end() :]
    is_inline_span = any(len(run.group()) == fence_length for run in _ANY_BACKTICK_RUN.finditer(rest))
    return None if is_inline_span else start


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
