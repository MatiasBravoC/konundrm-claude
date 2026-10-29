"""Contract tests for the plugin's agent definitions in agents/*.md."""

from __future__ import annotations

import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[3]
AGENTS_DIR = PLUGIN_ROOT / "agents"


def read_frontmatter(path: Path) -> dict[str, str]:
    """Return the top-level `name: value` keys of an agent file's frontmatter.

    The frontmatter is the block between the first two lines that are exactly `---`. Indented lines
    (items of list values such as `skills:`) are ignored.
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    fences = [index for index, line in enumerate(lines) if line == "---"][:2]
    fields: dict[str, str] = {}
    for line in lines[fences[0] + 1 : fences[1]]:
        if line[:1].isspace() or ":" not in line:
            continue
        key, value = line.split(":", 1)
        fields[key.strip()] = value.strip()
    return fields


class AgentModelsTest(unittest.TestCase):
    def test_each_role_has_its_agreed_model_and_effort(self) -> None:
        """R1.1, R10.1: each role runs on its agreed model and effort."""
        expected = {
            "test-writer": ("opus", "medium"),
            "implementer": ("opus", "medium"),
            "spec-reviewer": ("sonnet", "high"),
            "code-reviewer": ("opus", "high"),
            "security-reviewer": ("opus", "xhigh"),
            "finding-verifier": ("opus", "high"),
        }

        actual = {}
        for role in expected:
            fields = read_frontmatter(AGENTS_DIR / f"{role}.md")
            actual[role] = (fields.get("model"), fields.get("effort"))

        self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
