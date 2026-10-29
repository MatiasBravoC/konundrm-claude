"""Unit tests for the setup-project template scripts/check_commit_msg.py."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "skills" / "setup-project" / "templates" / "python"))

from check_commit_msg import header_problem


class HeaderProblemTest(unittest.TestCase):
    def test_accepts_conventional_commits_headers(self) -> None:
        for message in (
            "feat(auth): add Google sign-in",
            "fix: handle empty input\n\nBody.\n\nEscaped-gate: spec",
            "feat(api)!: drop the v1 endpoints",
            "build(deps): bump ruff",
            "Merge branch 'main' into feat/003-coupons",
            'Revert "feat(x): y"',
            "fixup! feat(x): y",
        ):
            with self.subTest(message=message):
                self.assertIsNone(header_problem(message))

    def test_rejects_emoji_prefixes_unknown_types_and_long_headers(self) -> None:
        for message in (
            "✨ feat(auth): add login",
            ":sparkles: feat(auth): add login",
            "Feat: capitalised type",
            "update stuff",
            "feature(x): unknown type",
            "feat(auth): " + "x" * 70,
            "",
        ):
            with self.subTest(message=message):
                self.assertIsNotNone(header_problem(message))


if __name__ == "__main__":
    unittest.main()
