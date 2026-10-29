"""Unit tests for hooks/scripts/secret_patterns.py.

The fake credentials are assembled at run time from a seeded generator, so this file never holds
a string that secret scanners (or this plugin) would flag.
"""

from __future__ import annotations

import random
import string
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import secret_patterns
from working_tree import AddedLine

RANDOM = random.Random(20261020)  # noqa: S311 - repeatable fake values for tests, not cryptography


def noise(length: int, alphabet: str = string.ascii_letters + string.digits) -> str:
    return "".join(RANDOM.choice(alphabet) for _ in range(length))


def fake(kind: str) -> str:
    """Builds a value with the shape of a real credential of the given kind."""
    shapes = {
        "aws": lambda: "AK" + "IA" + noise(16, string.ascii_uppercase + string.digits),
        "github": lambda: "gh" + "p_" + noise(36),
        "github_pat": lambda: "github" + "_pat_" + noise(82, string.ascii_letters + string.digits + "_"),
        "gitlab": lambda: "glp" + "at-" + noise(20),
        "slack": lambda: "xo" + "xb-" + noise(24, string.ascii_letters + string.digits + "-"),
        "stripe": lambda: "sk" + "_live_" + noise(24),
        "google": lambda: "AI" + "za" + noise(35, string.ascii_letters + string.digits + "_-"),
        "anthropic": lambda: "sk-" + "ant-api03-" + noise(93, string.ascii_letters + string.digits + "_-"),
        "openai": lambda: "sk-" + "proj-" + noise(48, string.ascii_letters + string.digits + "_-"),
        "npm": lambda: "np" + "m_" + noise(36),
        "private_key": lambda: "-----BEGIN " + "RSA PRIVATE" + " KEY-----",
    }
    return shapes[kind]()


class FindSecretsTest(unittest.TestCase):
    def test_recognises_each_provider_format(self) -> None:
        expected = {
            "aws": "AWS access key ID",
            "github": "GitHub token",
            "github_pat": "GitHub fine-grained token",
            "gitlab": "GitLab token",
            "slack": "Slack token",
            "stripe": "Stripe live key",
            "google": "Google API key",
            "anthropic": "Anthropic API key",
            "openai": "OpenAI API key",
            "npm": "npm token",
            "private_key": "private key",
        }
        for shape, kind in expected.items():
            with self.subTest(shape=shape):
                found = secret_patterns.find_secrets(f'TOKEN = "{fake(shape)}"\n')
                self.assertEqual([match.kind for match in found], [kind])

    def test_reports_line_numbers_and_masks_the_value(self) -> None:
        value = fake("github")
        found = secret_patterns.find_secrets(f"a = 1\nb = '{value}'\n", "src/config.py")
        self.assertEqual((found[0].path, found[0].line), ("src/config.py", 2))
        self.assertNotIn(value, found[0].masked)
        self.assertTrue(found[0].masked.endswith("…"))

    def test_ignores_documentation_examples_and_repeated_placeholders(self) -> None:
        for text in (
            "AK" + "IAIOSFODNN7EXAMPLE",
            "gh" + "p_" + "x" * 36,
            "sk" + "_live_" + "0" * 24,
            "AI" + "za" + "YOUR_KEY_HERE" + "a" * 22,
        ):
            with self.subTest(text=text):
                self.assertEqual(secret_patterns.find_secrets(text), [])

    def test_plain_code_has_no_findings(self) -> None:
        text = 'api_key = os.environ["STRIPE_API_KEY"]\nheaders = {"Authorization": f"Bearer {token}"}\n'
        self.assertEqual(secret_patterns.find_secrets(text), [])


class FindSecretsInLinesTest(unittest.TestCase):
    def test_scans_added_lines_and_skips_tool_artifacts(self) -> None:
        value = fake("stripe")
        lines = [AddedLine("src/pay.py", 3, f"KEY = '{value}'"), AddedLine("coverage/x.json", 1, value)]
        found = secret_patterns.find_secrets_in_lines(lines)
        self.assertEqual([(match.path, match.line) for match in found], [("src/pay.py", 3)])

    def test_describe_shows_masked_values_only(self) -> None:
        value = fake("npm")
        text = secret_patterns.describe(secret_patterns.find_secrets(value, "src/a.ts"))
        self.assertIn("src/a.ts:1: npm token", text)
        self.assertNotIn(value, text)


if __name__ == "__main__":
    unittest.main()
