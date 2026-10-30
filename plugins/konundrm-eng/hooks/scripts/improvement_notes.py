"""Keeps a slice's or feature's improvement notes, free of project content, in the central notes file.

The file lives at a fixed path inside Claude's configuration folder and is shared by every
project, so the project and feature names only ever go into its content, each on one line, and
never into the path, and the notes are scrubbed of code, credentials and e-mail addresses first.

Sections:
    NOTES_FILE     — where the notes file lives, relative to Claude's configuration folder.
    scrub()        — drops code blocks and redacts credentials and e-mail addresses.
    append_notes() — adds one dated entry tagged with project, feature and scope.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from secret_patterns import SECRET_PATTERNS

NOTES_FILE = Path("konundrm-eng") / "improvements.md"

_CODE_MARKER = "[code removed]"
_SECRET_MARKER = "[secret removed]"  # noqa: S105 - the text left in place of a credential, not one
_EMAIL_MARKER = "[email removed]"

# A line that opens a fenced block, at any indentation (list items indent theirs).
_OPENING_FENCE = re.compile(r"\s*(`{3,})")
# A line that is only a fence; it closes the block when at least as long as the opening one.
_CLOSING_FENCE = re.compile(r"\s*(`{3,})\s*")
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

    Every fenced code block (opened by a line starting with three or more backticks, at any
    indentation) is dropped with its contents and replaced by a "[code removed]" line; a block
    never closed runs to the end of the text. Any other run of three or more backticks is reduced
    to one. Then every private key outside a block, from its "-----BEGIN … PRIVATE KEY-----"
    header through its "-----END … PRIVATE KEY-----" line (or through the end of the text when
    that line is missing), every other match of a ``secret_patterns.SECRET_PATTERNS`` pattern,
    placeholder or not, becomes "[secret removed]" and every e-mail address "[email removed]",
    repeated until nothing matches, since removing one value can expose another that it was
    glued to.

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
        opening = _OPENING_FENCE.match(line)
        if opening:
            closing_fence_length = len(opening.group(1))
            content = line.splitlines()[0]
            kept.append(line[: opening.start(1)] + _CODE_MARKER + line[len(content) :])
        else:
            kept.append(_BACKTICK_RUN.sub("`", line))
    return "".join(kept)


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
    """Adds one dated entry with the notes to the end of the central notes file.

    Earlier content is never erased or changed. Project, feature and scope are written on a
    single line each (any line break or run of whitespace becomes one space), so a hostile name
    can neither change the path nor forge a new line in the file.

    Args:
        notes: Text of the notes, written as given.
        project: Name of the project the notes come from.
        feature: Name of the feature the notes are about.
        scope: What the notes cover, such as "slice 2" or "feature".
        today: Date stamped on the entry.
        config_dir: Claude's configuration folder; the file is ``config_dir / NOTES_FILE``.
        fallback_dir: Folder for the notes when the central file cannot be written (not used yet).

    Returns:
        The path written to and whether it was the fallback.

    Raises:
        OSError: If the folder or the file cannot be created or written.

    Side effects:
        Creates ``config_dir / NOTES_FILE`` and its folder when missing, then appends to it.
    """
    del fallback_dir  # the fallback arrives with T48
    path = config_dir / NOTES_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = (
        f"\n## {today.isoformat()} · {_single_line(scope)}\n\n"
        f"- Project: {_single_line(project)}\n"
        f"- Feature: {_single_line(feature)}\n\n"
        f"{notes.rstrip()}\n"
    )
    with path.open("a", encoding="utf-8", newline="\n") as notes_file:
        notes_file.write(entry)
    return path, False


def _single_line(value: str) -> str:
    return " ".join(value.split())
