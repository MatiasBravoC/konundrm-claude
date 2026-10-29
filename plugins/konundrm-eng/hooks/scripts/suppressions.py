"""Finds gate silencers without a reason: the cheap way to turn a red check green.

An agent that cannot make a check pass can silence it instead: a lint or type-checker directive,
a coverage or mutation exclusion, a skipped test, or a focused test that quietly stops every other
test from running. Standards → Gate integrity allows a silencer only with its reason on the same
line, in the tool's own syntax, and never allows a focused test. This module finds the ones that
break that rule in the lines a change adds. Each marker's name mirrors the lists in Standards →
Gate integrity word for word; tests/test_suppressions.py fails when the two drift apart.

Sections:
    Marker, SILENCERS, SKIPPED_TESTS, FOCUSED_TESTS — what counts as silencing a gate.
    Suppression, find_unjustified() — silencers without a reason in a set of added lines.
    describe()  — a short list of findings for a hook message.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import PurePosixPath

from file_kinds import is_documentation_path, is_test_path, is_tool_artifact
from working_tree import AddedLine

# How a marker's reason is written.
AFTER = "after"  # words after the directive: `<directive> - why`
ESLINT = "eslint"  # words after ` -- `; without it ESLint reads them as rule names
STRYKER = "stryker"  # words after `:`
ARGUMENT = "argument"  # a string argument with words (reason="…"), or a trailing comment
COMMENT = "comment"  # a trailing comment with words
NEVER = "never"  # no reason makes it acceptable

PYTHON = frozenset({".py", ".pyi"})
JAVASCRIPT = frozenset({".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts", ".vue", ".svelte"})
GO = frozenset({".go"})
HASH_COMMENTS = PYTHON | frozenset({".sh", ".bash", ".rb", ".yaml", ".yml", ".toml", ".cfg", ".ini"})

REASON_WORD = re.compile(r"[^\W\d_]{3,}")
STRING_WITH_WORDS = re.compile(r"""["'][^"'\n]*[^\W\d_]{3,}[^"'\n]*["']""")
MAX_SHOWN_CHARACTERS = 120


@dataclass(frozen=True)
class Marker:
    """One way to silence a gate.

    Attributes:
        name: The marker as Standards → Gate integrity lists it.
        pattern: Matches the directive and what belongs to it (rule codes, names, counts).
        reason: How its reason must be written: AFTER, ESLINT, STRYKER, ARGUMENT, COMMENT or NEVER.
        suffixes: File suffixes the marker applies to; empty for every language.
    """

    name: str
    pattern: re.Pattern[str]
    reason: str = AFTER
    suffixes: frozenset[str] = frozenset()


def _marker(name: str, pattern: str, reason: str = AFTER, suffixes: frozenset[str] = frozenset()) -> Marker:
    return Marker(name, re.compile(pattern), reason, suffixes)


_CODES = r"(?::\s*[A-Z]+[0-9]+(?:\s*,\s*[A-Z]+[0-9]+)*)?"
_BRACKETS = r"(?:\[[^\]]*\])?"
_COVERAGE_WORDS = r"(?:\s+(?:next|start|stop|else|if|file))?(?:\s+\d+)?"
# JavaScript tools read a directive only at the start of a comment, as these patterns require;
# prose in a comment that mentions one ("an eslint-disable that…") is not a directive.
_COMMENT_START = r"(?://+|/\*+)\s*"

SILENCERS = (
    _marker("# noqa", r"#\s*noqa\b" + _CODES, suffixes=PYTHON),
    _marker("# ruff: noqa", r"#\s*(?:ruff|flake8)\s*:\s*noqa\b" + _CODES, suffixes=PYTHON),
    _marker("# type: ignore", r"#\s*type:\s*ignore\b" + _BRACKETS, suffixes=PYTHON),
    _marker("# pyright: ignore", r"#\s*pyright:\s*ignore\b" + _BRACKETS, suffixes=PYTHON),
    _marker("# pylint: disable", r"#\s*pylint:\s*disable(?:-next)?\s*=\s*[\w-]+(?:\s*,\s*[\w-]+)*", suffixes=PYTHON),
    _marker("# nosec", r"#\s*nosec\b(?:\s+[A-Z][0-9]+(?:\s*,\s*[A-Z][0-9]+)*)?", suffixes=PYTHON),
    _marker("# pragma: no cover", r"#\s*pragma:\s*no\s*cover\b", suffixes=PYTHON),
    _marker("# pragma: no branch", r"#\s*pragma:\s*no\s*branch\b", suffixes=PYTHON),
    _marker("# pragma: no mutate", r"#\s*pragma:\s*no\s*mutate\b", suffixes=PYTHON),
    _marker("eslint-disable", _COMMENT_START + r"eslint-disable(?:-next-line|-line)?\b", ESLINT, JAVASCRIPT),
    _marker("@ts-ignore", _COMMENT_START + r"@ts-ignore\b", suffixes=JAVASCRIPT),
    _marker("@ts-expect-error", _COMMENT_START + r"@ts-expect-error\b", suffixes=JAVASCRIPT),
    _marker("@ts-nocheck", _COMMENT_START + r"@ts-nocheck\b", suffixes=JAVASCRIPT),
    _marker("istanbul ignore", _COMMENT_START + r"istanbul\s+ignore" + _COVERAGE_WORDS, suffixes=JAVASCRIPT),
    _marker("c8 ignore", _COMMENT_START + r"c8\s+ignore" + _COVERAGE_WORDS, suffixes=JAVASCRIPT),
    _marker("v8 ignore", _COMMENT_START + r"v8\s+ignore" + _COVERAGE_WORDS, suffixes=JAVASCRIPT),
    _marker("Stryker disable", _COMMENT_START + r"Stryker\s+disable(?:\s+next-line)?\s+[\w,]+", STRYKER, JAVASCRIPT),
    _marker("//nolint", r"//\s*nolint\b(?::[\w,-]+)?", suffixes=GO),
    _marker("NOSONAR", r"\bNOSONAR\b"),
)
SKIPPED_TESTS = (
    _marker("@pytest.mark.skip", r"@pytest\.mark\.skip\b(?!if)", ARGUMENT, PYTHON),
    _marker("@pytest.mark.skipif", r"@pytest\.mark\.skipif\b", ARGUMENT, PYTHON),
    _marker("@pytest.mark.xfail", r"@pytest\.mark\.xfail\b", ARGUMENT, PYTHON),
    _marker("pytest.skip(", r"\bpytest\.skip(?=\()", ARGUMENT, PYTHON),
    _marker("@unittest.skip", r"@unittest\.skip\b(?!If|Unless)", ARGUMENT, PYTHON),
    _marker("@unittest.skipIf", r"@unittest\.skipIf\b", ARGUMENT, PYTHON),
    _marker("@unittest.skipUnless", r"@unittest\.skipUnless\b", ARGUMENT, PYTHON),
    _marker("@unittest.expectedFailure", r"@unittest\.expectedFailure\b", COMMENT, PYTHON),
    _marker("it.skip(", r"\bit\.skip\s*\(", COMMENT, JAVASCRIPT),
    _marker("test.skip(", r"\btest\.skip\s*\(", COMMENT, JAVASCRIPT),
    _marker("describe.skip(", r"\bdescribe\.skip\s*\(", COMMENT, JAVASCRIPT),
    _marker("xit(", r"(?<![\w.$])xit\s*\(", COMMENT, JAVASCRIPT),
    _marker("xtest(", r"(?<![\w.$])xtest\s*\(", COMMENT, JAVASCRIPT),
    _marker("xdescribe(", r"(?<![\w.$])xdescribe\s*\(", COMMENT, JAVASCRIPT),
)
FOCUSED_TESTS = (
    _marker("it.only(", r"\bit\.only\s*\(", NEVER, JAVASCRIPT),
    _marker("test.only(", r"\btest\.only\s*\(", NEVER, JAVASCRIPT),
    _marker("describe.only(", r"\bdescribe\.only\s*\(", NEVER, JAVASCRIPT),
    _marker("fit(", r"(?<![\w.$])fit\s*\(", NEVER, JAVASCRIPT),
    _marker("fdescribe(", r"(?<![\w.$])fdescribe\s*\(", NEVER, JAVASCRIPT),
)
MARKERS = SILENCERS + SKIPPED_TESTS + FOCUSED_TESTS
# Test markers count only as code in test files: a comment that mentions one is not a skipped
# test, and neither is a production function that happens to be called `fit`.
CODE_MARKERS = frozenset(marker.name for marker in SKIPPED_TESTS + FOCUSED_TESTS)


@dataclass(frozen=True)
class Suppression:
    """A silencer added without the reason Standards → Gate integrity requires.

    Attributes:
        path: Project-relative file path.
        line: 1-based line number.
        marker: The marker's name, as the standards list it.
        text: The line, stripped and shortened for a message.
    """

    path: str
    line: int
    marker: str
    text: str


def _comment_starts(suffix: str) -> tuple[str, ...]:
    if suffix in HASH_COMMENTS:
        return ("#",)
    if suffix in JAVASCRIPT or suffix in GO:
        return ("//", "/*")
    return ("#", "//", "/*")


def _prefix_state(prefix: str, comment_starts: tuple[str, ...]) -> tuple[bool, bool]:
    """Reads the text before a match: is a string literal still open, has a comment begun?"""
    quote: str | None = None
    index = 0
    while index < len(prefix):
        character = prefix[index]
        if quote is not None:
            if character == "\\":
                index += 1
            elif character == quote:
                quote = None
        elif character in "\"'`":
            quote = character
        elif any(prefix.startswith(start, index) for start in comment_starts):
            return False, True
        index += 1
    return quote is not None, False


def _has_reason(text: str) -> bool:
    for marker in MARKERS:  # another directive on the same line is not a reason for this one
        text = marker.pattern.sub(" ", text)
    return bool(REASON_WORD.search(text.replace("*/", " ")))


def _trailing_comment_reason(rest: str, comment_starts: tuple[str, ...]) -> bool:
    for index in range(len(rest)):
        if any(rest.startswith(start, index) for start in comment_starts):
            in_string, _ = _prefix_state(rest[:index], comment_starts)
            if not in_string:
                return _has_reason(rest[index:].lstrip("#/* "))
    return False


def _is_justified(marker: Marker, rest: str, comment_starts: tuple[str, ...]) -> bool:
    if marker.reason == NEVER:
        return False
    if marker.reason in (ESLINT, STRYKER):
        _, separator, reason = rest.partition("--" if marker.reason == ESLINT else ":")
        return bool(separator) and _has_reason(reason)
    if marker.reason == ARGUMENT and STRING_WITH_WORDS.search(rest):
        return True
    if marker.reason in (ARGUMENT, COMMENT):
        return _trailing_comment_reason(rest, comment_starts)
    return _has_reason(rest)


def _line_suppressions(added: AddedLine) -> Iterator[Suppression]:
    suffix = PurePosixPath(added.path).suffix.lower()
    comment_starts = _comment_starts(suffix)
    in_test_file = is_test_path(added.path)
    for marker in MARKERS:
        if marker.suffixes and suffix not in marker.suffixes:
            continue
        if marker.name in CODE_MARKERS and not in_test_file:  # `fit(` in production code is a function
            continue
        for match in marker.pattern.finditer(added.text):
            in_string, in_comment = _prefix_state(added.text[: match.start()], comment_starts)
            if in_string or (in_comment and marker.name in CODE_MARKERS):
                continue
            if not _is_justified(marker, added.text[match.end() :], comment_starts):
                yield Suppression(added.path, added.number, marker.name, added.text.strip()[:MAX_SHOWN_CHARACTERS])


def find_unjustified(lines: Iterable[AddedLine]) -> list[Suppression]:
    """Finds the silencers in added lines that lack a reason, and every focused test.

    Documentation and tool artifacts are skipped: prose can mention a marker without using it.

    Args:
        lines: Lines a change added (working_tree.added_lines()).

    Returns:
        One Suppression per offending marker, in the order the lines were given.
    """
    found: list[Suppression] = []
    for added in lines:
        if not is_documentation_path(added.path) and not is_tool_artifact(added.path):
            found.extend(_line_suppressions(added))
    return found


def describe(suppressions: list[Suppression], limit: int = 10) -> str:
    """Formats suppressions as a short list for a hook message.

    Args:
        suppressions: Findings from find_unjustified().
        limit: How many to list before summarising the rest.
    """
    shown = [f"- {item.path}:{item.line} `{item.marker}`: {item.text}" for item in suppressions[:limit]]
    if len(suppressions) > limit:
        shown.append(f"- … and {len(suppressions) - limit} more")
    return "\n".join(shown)
