"""Unit tests for hooks/scripts/metrics_report.py (they build a small Git history)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import metrics_log
from metrics_report import (
    build_report,
    delivery_section,
    gates_section,
    possible_escapes,
    pull_requests_section,
    read_commits,
    read_merged_pull_requests,
    rework_section,
)


def commit(root: Path, path: str, content: str, message: str) -> None:
    (root / path).parent.mkdir(parents=True, exist_ok=True)
    (root / path).write_text(content)
    for args in (["add", "-A"], ["commit", "-q", "-m", message]):
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@e", *args], cwd=root, check=True)


@unittest.skipIf(shutil.which("git") is None, "Git is not installed")
class MetricsReportTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name) / "repo"
        self.root.mkdir()
        patcher = mock.patch.dict(os.environ, {"CLAUDE_PLUGIN_DATA": str(Path(self._tmp.name) / "data")})
        patcher.start()
        self.addCleanup(patcher.stop)
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        commit(self.root, "src/a.py", "1", "feat(a): add a\n\nTask: T1 · Covers: R1.1")
        commit(self.root, "src/b.py", "1", "♻️ refactor(b): tidy b")  # history from the old Gitmoji format
        commit(self.root, "src/a.py", "2", "fix(a): handle empty input")
        self.since = datetime.now(timezone.utc) - timedelta(days=1)

    def test_reads_commit_types_task_trailers_and_files(self) -> None:
        commits = read_commits(self.root, self.since)
        self.assertEqual([c.kind for c in commits], ["feat", "refactor", "fix"])
        self.assertEqual([c.is_task for c in commits], [True, False, False])
        self.assertEqual(commits[0].files, ("src/a.py",))

    def test_a_fix_to_files_a_task_just_changed_is_a_possible_escape(self) -> None:
        escapes = possible_escapes(read_commits(self.root, self.since))
        self.assertEqual([escape.subject for escape in escapes], ["fix(a): handle empty input"])

    def test_sums_review_rounds_per_feature(self) -> None:
        tasks = self.root / "specs" / "001-login" / "tasks.md"
        tasks.parent.mkdir(parents=True)
        tasks.write_text(
            "- [x] **T1** a · `behavior`\n  - Rounds: spec 2 · code 1 · escalations 0\n"
            "- [x] **T2** b · `behavior`\n  - Rounds: spec 1 · code 3 · escalations 1\n- [ ] **T3** c\n"
            "<!-- Example:\n- [x] **T9** done\n  - Rounds: spec 9 · code 9 · escalations 9\n-->\n"
        )
        self.assertIn("| 001-login | 2 | 3 | 4 | 1 |", rework_section(self.root))

    def test_counts_gate_events_by_kind_and_reason(self) -> None:
        events = [{"kind": "commit_denied", "reason": "bypass"}, {"kind": "commit_denied", "reason": "bypass"}]
        self.assertIn("| commit_denied (bypass) | 2 |", gates_section(events))

    def test_counts_the_gates_bugs_escaped_from(self) -> None:
        commit(self.root, "src/b.py", "2", "fix(b): reject empty input\n\nRoot cause.\n\nEscaped-gate: property")
        commit(self.root, "src/b.py", "3", "fix(b): keep order\n\nEscaped-gate: Property")
        commit(self.root, "src/b.py", "4", "fix(b): log less\n\nEscaped-gate: review")
        lines = delivery_section(read_commits(self.root, self.since))
        self.assertIn("**property 2, review 1**", "\n".join(lines))

    def test_builds_a_report_with_every_section(self) -> None:
        metrics_log.record_event(self.root, "stop_blocked", "s1")
        report = build_report(self.root, 30, pull_requests=[])
        for heading in (
            "## Delivery (Git)",
            "## Rework",
            "## Gates (hook log)",
            "| stop_blocked | 1 |",
            "## Pull requests (GitHub)",
        ):
            with self.subTest(heading=heading):
                self.assertIn(heading, report)


class PullRequestsSectionTest(unittest.TestCase):
    def test_reports_size_against_the_budget_and_time_to_merge(self) -> None:
        pull_requests = [
            {
                "additions": 100,
                "deletions": 20,
                "createdAt": "2026-10-01T10:00:00Z",
                "mergedAt": "2026-10-01T14:00:00Z",
            },
            {
                "additions": 500,
                "deletions": 100,
                "createdAt": "2026-10-02T10:00:00Z",
                "mergedAt": "2026-10-03T10:00:00Z",
            },
            {"additions": 30, "deletions": 0, "createdAt": "2026-10-04T10:00:00Z", "mergedAt": "2026-10-04T12:00:00Z"},
        ]
        table = "\n".join(pull_requests_section(pull_requests, budget=400))
        self.assertIn("| 3 | 120 | 1 of 3 (budget 400) | 4.0 h |", table)

    def test_says_when_github_is_not_reachable_or_nothing_merged(self) -> None:
        self.assertIn("Not available", "\n".join(pull_requests_section(None, 400)))
        self.assertIn("No pull requests merged", "\n".join(pull_requests_section([], 400)))

    def test_reads_merged_pull_requests_through_gh(self) -> None:
        completed = subprocess.CompletedProcess([], 0, stdout='[{"number": 1, "additions": 3}]', stderr="")
        with (
            mock.patch("metrics_report.shutil.which", return_value="gh"),
            mock.patch("metrics_report.subprocess.run", return_value=completed) as run,
        ):
            found = read_merged_pull_requests(Path("."), datetime(2026, 10, 1, tzinfo=timezone.utc))
        self.assertEqual(found, [{"number": 1, "additions": 3}])
        self.assertIn("merged:>=2026-10-01", run.call_args.args[0])

    def test_gives_none_without_gh_or_when_it_fails(self) -> None:
        with mock.patch("metrics_report.shutil.which", return_value=None):
            self.assertIsNone(read_merged_pull_requests(Path("."), datetime.now(timezone.utc)))
        failed = subprocess.CompletedProcess([], 1, stdout="", stderr="not a GitHub repository")
        with (
            mock.patch("metrics_report.shutil.which", return_value="gh"),
            mock.patch("metrics_report.subprocess.run", return_value=failed),
        ):
            self.assertIsNone(read_merged_pull_requests(Path("."), datetime.now(timezone.utc)))


if __name__ == "__main__":
    unittest.main()
