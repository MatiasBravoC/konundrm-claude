"""Validates commit messages against Konundrm's Conventional Commits format.

Header: ``<type>(<scope>): <imperative summary>``, at most 72 characters, starting with the type
(no emoji or other prefix). Merge, revert, fixup! and squash! commits pass.

Usage:
    python scripts/check_commit_msg.py .git/COMMIT_EDITMSG   # pre-commit commit-msg stage
    python scripts/check_commit_msg.py --range origin/main..HEAD   # CI
"""

from __future__ import annotations

import re
import subprocess
import sys

TYPES = (
    "feat",
    "fix",
    "refactor",
    "test",
    "docs",
    "style",
    "perf",
    "chore",
    "build",
    "ci",
    "revert",
)
HEADER = re.compile(rf"^(?P<type>{'|'.join(TYPES)})(?:\([\w$.,/ -]+\))?!?: \S.*$")
EXEMPT = re.compile(r"^(Merge |Revert |fixup! |squash! |amend! )")
MAX_HEADER_LENGTH = 72


def header_problem(message: str) -> str | None:
    """Returns why a commit message's header is invalid, or None when it is valid."""
    header = message.strip().splitlines()[0] if message.strip() else ""
    if EXEMPT.match(header):
        return None
    if len(header) > MAX_HEADER_LENGTH:
        return f"header is {len(header)} characters; the limit is {MAX_HEADER_LENGTH}"
    if not HEADER.match(header):
        return "expected '<type>(<scope>): <summary>' with type in " + ", ".join(TYPES)
    return None


def _messages_in_range(revision_range: str) -> list[tuple[str, str]]:
    log = subprocess.run(  # noqa: S603 - fixed git argv; the range comes from CI
        ["git", "log", "--format=%H%x00%B%x1e", revision_range],  # noqa: S607 - git from PATH
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    ).stdout
    entries = [entry.strip("\n") for entry in log.split("\x1e") if entry.strip()]
    return [(sha, text) for sha, text in (entry.split("\x00", 1) for entry in entries)]


def main(argv: list[str]) -> int:
    """Validates the message file or the revision range given on the command line."""
    if len(argv) == 3 and argv[1] == "--range":
        messages = _messages_in_range(argv[2])
    elif len(argv) == 2:
        with open(argv[1], encoding="utf-8") as message_file:
            text = "\n".join(
                line for line in message_file.read().splitlines() if not line.startswith("#")
            )
        messages = [("this commit", text)]
    else:
        print(__doc__, file=sys.stderr)
        return 2
    failures = [(sha, problem) for sha, text in messages if (problem := header_problem(text))]
    for sha, problem in failures:
        print(f"{sha[:12]}: {problem}", file=sys.stderr)
    if failures:
        print("Example: feat(auth): add Google sign-in", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main(sys.argv))
