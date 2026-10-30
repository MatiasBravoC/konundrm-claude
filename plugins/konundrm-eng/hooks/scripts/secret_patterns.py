"""Recognises credentials in text before they reach a file or a commit.

Only high-confidence shapes are listed: provider key formats with a fixed prefix and private key
blocks. A match is almost always a real secret, so the hooks can stop and ask instead of guessing
from entropy. Values that are obviously placeholders (documentation examples such as AWS's
``…EXAMPLE`` keys, or the same character repeated) are ignored. Secret scanning in CI (TruffleHog)
remains the broad net; this is the early one, in front of the agent.

Sections:
    PRIVATE_KEY_LABEL              — the label of a PEM private key of any type.
    SecretPattern, SECRET_PATTERNS — the credential formats recognised.
    SecretMatch, find_secrets()    — credentials in a text, with line numbers and masked values.
    find_secrets_in_lines()        — credentials in lines a change added.
    describe()                     — a short list of findings for a hook message.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from file_kinds import is_tool_artifact

if TYPE_CHECKING:  # the edit hook imports this module on every write; keep Git's module out of it
    from working_tree import AddedLine

MAX_DISTINCT_PLACEHOLDER_CHARACTERS = 3
PLACEHOLDER_WORDS = ("EXAMPLE", "XXXXXXXX", "PLACEHOLDER", "REDACTED", "YOUR_", "DUMMY", "FAKE")
# The label of a PEM private key, between "-----BEGIN " or "-----END " and "-----": up to three
# type words of any kind (RSA, EC, DH, X25519, ED448, OPENSSH, ENCRYPTED, PGP…) or none, then
# "PRIVATE KEY", then PGP's " BLOCK". The words are bounded so matching stays linear, and the
# label must end in "PRIVATE KEY", so public keys and certificates never match.
PRIVATE_KEY_LABEL = r"(?:[A-Z0-9]{1,16} ){0,3}PRIVATE KEY(?: BLOCK)?"


@dataclass(frozen=True)
class SecretPattern:
    """One credential format.

    Attributes:
        kind: Human name for messages ("GitHub token").
        pattern: Regex whose ``body`` group, when present, is the random part of the value.
    """

    kind: str
    pattern: re.Pattern[str]


def _pattern(kind: str, regex: str) -> SecretPattern:
    return SecretPattern(kind, re.compile(regex))


SECRET_PATTERNS = (
    _pattern("AWS access key ID", r"\b(?:AKIA|ASIA|ABIA|ACCA)(?P<body>[0-9A-Z]{16})\b"),
    _pattern("GitHub token", r"\bgh[pousr]_(?P<body>[A-Za-z0-9]{36,255})\b"),
    _pattern("GitHub fine-grained token", r"\bgithub_pat_(?P<body>[A-Za-z0-9_]{50,255})\b"),
    _pattern("GitLab token", r"\bglpat-(?P<body>[A-Za-z0-9_-]{20,})"),
    _pattern("Slack token", r"\bxox[abposr]-(?P<body>[A-Za-z0-9-]{10,})"),
    _pattern(
        "Slack webhook URL", r"https://hooks\.slack\.com/services/T[A-Z0-9]+/B[A-Z0-9]+/(?P<body>[A-Za-z0-9]{20,})"
    ),
    _pattern("Stripe live key", r"\b(?:sk|rk)_live_(?P<body>[A-Za-z0-9]{20,})"),
    _pattern("Google API key", r"\bAIza(?P<body>[0-9A-Za-z_-]{35})(?![0-9A-Za-z_-])"),
    _pattern("Anthropic API key", r"\bsk-ant-(?:api|admin)\d{2}-(?P<body>[A-Za-z0-9_-]{80,})"),
    _pattern("OpenAI API key", r"\bsk-(?:proj|svcacct|admin)-(?P<body>[A-Za-z0-9_-]{40,})"),
    _pattern("OpenAI API key", r"\bsk-(?P<body>[A-Za-z0-9]{20}T3BlbkFJ[A-Za-z0-9]{20})\b"),
    _pattern("npm token", r"\bnpm_(?P<body>[A-Za-z0-9]{36})\b"),
    _pattern("PyPI token", r"\bpypi-AgEIcHlwaS5vcmc(?P<body>[A-Za-z0-9_-]{50,})"),
    _pattern("SendGrid key", r"\bSG\.(?P<body>[A-Za-z0-9_-]{22}\.[A-Za-z0-9_-]{43})(?![A-Za-z0-9_-])"),
    _pattern("Azure storage account key", r"AccountKey=(?P<body>[A-Za-z0-9+/]{86}==)"),
    _pattern("private key", rf"-----BEGIN {PRIVATE_KEY_LABEL}-----"),
)


@dataclass(frozen=True)
class SecretMatch:
    """A credential found in text.

    Attributes:
        path: Project-relative file path, or an empty string for text not yet in a file.
        line: 1-based line number.
        kind: The credential format.
        masked: The value with everything but its first characters hidden, safe to show.
    """

    path: str
    line: int
    kind: str
    masked: str


def _is_placeholder(value: str, body: str) -> bool:
    if any(word in value.upper() for word in PLACEHOLDER_WORDS):
        return True
    return bool(body) and len(set(body)) <= MAX_DISTINCT_PLACEHOLDER_CHARACTERS


def _mask(value: str) -> str:
    return value[: min(8, len(value) // 3)] + "…"


def _line_matches(path: str, number: int, line: str) -> list[SecretMatch]:
    found = []
    for secret in SECRET_PATTERNS:
        for match in secret.pattern.finditer(line):
            value = match.group(0)
            body = match.groupdict().get("body") or ""
            if not _is_placeholder(value, body):
                found.append(SecretMatch(path, number, secret.kind, _mask(value)))
    return found


def find_secrets(text: str, path: str = "") -> list[SecretMatch]:
    """Finds credentials in a block of text, such as the content a tool is about to write.

    Args:
        text: The text to scan.
        path: Project-relative path the text belongs to, for messages; empty when unknown.

    Returns:
        One SecretMatch per credential, in order of appearance.
    """
    found: list[SecretMatch] = []
    for number, line in enumerate(text.splitlines(), start=1):
        found.extend(_line_matches(path, number, line))
    return found


def find_secrets_in_lines(lines: Iterable[AddedLine]) -> list[SecretMatch]:
    """Finds credentials in lines a change added (working_tree.added_lines()), skipping tool artifacts."""
    found: list[SecretMatch] = []
    for added in lines:
        if not is_tool_artifact(added.path):
            found.extend(_line_matches(added.path, added.number, added.text))
    return found


def describe(matches: list[SecretMatch], limit: int = 10) -> str:
    """Formats findings as a short list for a hook message, with masked values only.

    Args:
        matches: Findings from find_secrets() or find_secrets_in_lines().
        limit: How many to list before summarising the rest.
    """
    shown = [
        f"- {match.path + ':' if match.path else 'line '}{match.line}: {match.kind} ({match.masked})"
        for match in matches[:limit]
    ]
    if len(matches) > limit:
        shown.append(f"- … and {len(matches) - limit} more")
    return "\n".join(shown)
