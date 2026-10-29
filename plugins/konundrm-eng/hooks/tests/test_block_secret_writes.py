"""Unit tests for hooks/scripts/block_secret_writes.py."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from block_secret_writes import written_text


class WrittenTextTest(unittest.TestCase):
    def test_reads_every_tool_that_writes_text(self) -> None:
        self.assertEqual(written_text({"file_path": "a.py", "content": "x = 1"}), "x = 1")
        self.assertEqual(written_text({"old_string": "a", "new_string": "b"}), "b")
        self.assertEqual(written_text({"new_source": "print(1)"}), "print(1)")
        self.assertEqual(
            written_text({"edits": [{"old_string": "a", "new_string": "b"}, {"new_string": "c"}, "junk"]}), "b\nc"
        )

    def test_ignores_non_text_values(self) -> None:
        self.assertEqual(written_text({"content": 3, "edits": "not a list"}), "")


if __name__ == "__main__":
    unittest.main()
