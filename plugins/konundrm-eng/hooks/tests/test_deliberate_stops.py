"""Unit tests for hooks/scripts/deliberate_stops.py."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from deliberate_stops import find_deliberate_stop


class FindDeliberateStopTest(unittest.TestCase):
    # R1.4: the first stop line in a multi-line text, undecorated, and nothing past its end.
    def test_returns_only_the_rest_of_the_first_stop_line(self) -> None:
        text = "Slice S1 built.\n**BLOCKED:** T2 needs a plan change\nThe plan says one thing.\nRED: T3 later\n"

        self.assertEqual(find_deliberate_stop(text), "BLOCKED: T2 needs a plan change")


if __name__ == "__main__":
    unittest.main()
