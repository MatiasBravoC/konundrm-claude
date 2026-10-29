"""Prints a Markdown report of whether the konundrm-eng workflow improves delivery in a project.

Combines four sources over a time window: Git history (commit types, reverts, fixes that land
soon after a task touched the same files, a proxy for escaped defects, and the gate each
``fix-bug`` commit says should have caught its bug), the review rounds and escalations
develop-feature records in specs/*/tasks.md, the gate events the hooks log (metrics_log.py), and
merged pull requests from GitHub when the ``gh`` CLI can reach them (size and time to merge).
Run it with ``sh "${CLAUDE_PLUGIN_ROOT}/hooks/run.sh" metrics_report.py --days 30``.

Sections:
    CommitInfo, read_commits()   — the window's commits from Git.
    delivery_section()           — commit mix, possible escaped defects and the gates they escaped.
    rework_section()             — review rounds and escalations per feature.
    gates_section()              — what the hooks blocked, asked or restored.
    pull_requests_section()      — merged pull requests: size against the budget, time to merge.
    build_report(), main()       — the whole report.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from metrics_log import read_events
from project_paths import project_root
from tasks_document import read_tasks

# The optional leading token still counts commits written in the Gitmoji format used before 0.4.0.
COMMIT_TYPE = re.compile(r"^(?:\S+\s+)?(feat|fix|refactor|test|docs|style|perf|chore|build|ci|revert)(?:\([^)]*\))?!?:")
TASK_TRAILER = re.compile(r"(?m)^Task:\s*T\d+")
ESCAPED_GATE_TRAILER = re.compile(r"(?mi)^Escaped-gate:\s*(?P<gate>[a-z0-9-]+)")
ESCAPE_WINDOW = timedelta(days=30)
FIELD, RECORD = "\x1f", "\x1e"
DEFAULT_PR_BUDGET_LINES = 400
GH_TIMEOUT_SECONDS = 30


@dataclass(frozen=True)
class CommitInfo:
    """One commit, as the report needs it.

    Attributes:
        when: Commit time.
        kind: Conventional Commits type, ``revert`` or ``other``.
        subject: First line of the message.
        is_task: Whether the body carries a ``Task: T<n>`` trailer (a develop-feature task).
        files: Paths the commit touched.
        escaped_gate: For fix-bug commits, the gate its ``Escaped-gate:`` trailer names.
    """

    when: datetime
    kind: str
    subject: str
    is_task: bool
    files: tuple[str, ...]
    escaped_gate: str | None = None


def read_commits(root: Path, since: datetime) -> list[CommitInfo]:
    """Reads the commits made since a date, oldest first; empty outside a Git repository."""
    try:
        output = subprocess.run(
            [
                "git",
                "log",
                "--reverse",  # history order, oldest first; timestamps tie within a second
                f"--since={since.isoformat()}",
                f"--format={RECORD}%cI{FIELD}%s{FIELD}%b{FIELD}",
                "--name-only",
            ],
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    commits = []
    for record in filter(None, output.split(RECORD)):
        parts = record.split(FIELD)
        if len(parts) < 4:
            continue
        when, subject, body, files = parts[0], parts[1], parts[2], parts[3]
        match = COMMIT_TYPE.match(subject)
        kind = "revert" if subject.startswith("Revert") else (match.group(1) if match else "other")
        gate = ESCAPED_GATE_TRAILER.search(body)
        commits.append(
            CommitInfo(
                when=datetime.fromisoformat(when),
                kind=kind,
                subject=subject,
                is_task=bool(TASK_TRAILER.search(body)),
                files=tuple(line for line in files.splitlines() if line.strip()),
                escaped_gate=gate.group("gate").lower() if gate else None,
            )
        )
    return commits


def possible_escapes(commits: list[CommitInfo]) -> list[CommitInfo]:
    """Fix commits that touch files a task commit changed in the 30 days before them."""
    escapes = []
    for index, commit in enumerate(commits):
        if commit.kind != "fix":
            continue
        recent_tasks = [
            earlier for earlier in commits[:index] if earlier.is_task and commit.when - earlier.when <= ESCAPE_WINDOW
        ]
        if any(set(commit.files) & set(task.files) for task in recent_tasks):
            escapes.append(commit)
    return escapes


def delivery_section(commits: list[CommitInfo]) -> list[str]:
    """Commit mix, fix-to-feature ratio and possible escaped defects."""
    kinds = Counter(commit.kind for commit in commits)
    escapes = possible_escapes(commits)
    feats = kinds.get("feat", 0)
    ratio = f"{kinds.get('fix', 0) / feats:.2f}" if feats else "n/a"
    lines = [
        "## Delivery (Git)",
        "",
        "| Commits | feat | fix | refactor | test | other types | reverts | task commits |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
        f"| {len(commits)} | {feats} | {kinds.get('fix', 0)} | {kinds.get('refactor', 0)} | {kinds.get('test', 0)} | "
        f"{len(commits) - sum(kinds.get(k, 0) for k in ('feat', 'fix', 'refactor', 'test', 'revert'))} | "
        f"{kinds.get('revert', 0)} | {sum(commit.is_task for commit in commits)} |",
        "",
        f"Fixes per feature: **{ratio}**. Possible escaped defects (a fix touching files a task changed in the "
        f"30 days before): **{len(escapes)}**.",
    ]
    lines += [f"- {escape.when.date()} {escape.subject}" for escape in escapes[:10]]
    gates = Counter(commit.escaped_gate for commit in commits if commit.kind == "fix" and commit.escaped_gate)
    if gates:
        listed = ", ".join(f"{gate} {count}" for gate, count in gates.most_common())
        lines += ["", f"Gates that should have caught the bugs fixed (`Escaped-gate:` trailers): **{listed}**."]
    return lines


def _feature_rework(tasks_file: Path) -> tuple[int, int, int, int]:
    tasks = read_tasks(tasks_file).tasks
    rounds = [task.rounds for task in tasks if task.rounds is not None]
    return (
        sum(task.done for task in tasks),
        sum(r[0] for r in rounds),
        sum(r[1] for r in rounds),
        sum(r[2] for r in rounds),
    )


def rework_section(root: Path) -> list[str]:
    """Review rounds and escalations per feature, from the Rounds lines in specs/*/tasks.md."""
    rows = []
    for tasks_file in sorted(root.glob("specs/*/tasks.md")):
        done, spec, code, escalations = _feature_rework(tasks_file)
        rows.append(f"| {tasks_file.parent.name} | {done} | {spec} | {code} | {escalations} |")
    if not rows:
        return ["## Rework (specs/*/tasks.md)", "", "No features under specs/ yet."]
    return [
        "## Rework (specs/*/tasks.md)",
        "",
        "| Feature | Tasks done | Spec review rounds | Code review rounds | Escalations |",
        "| --- | --- | --- | --- | --- |",
        *rows,
    ]


def gates_section(events: list[dict[str, Any]]) -> list[str]:
    """What the hooks blocked, asked for or restored."""
    counts = Counter(
        f"{event.get('kind')} ({event['reason']})" if event.get("reason") else str(event.get("kind"))
        for event in events
    )
    if not counts:
        return ["## Gates (hook log)", "", "No gate events recorded on this machine in the window."]
    return [
        "## Gates (hook log)",
        "",
        "| Event | Count |",
        "| --- | --- |",
        *[f"| {kind} | {count} |" for kind, count in counts.most_common()],
    ]


def _pr_budget() -> int:
    try:
        return max(1, int(os.environ.get("KONUNDRM_PR_BUDGET", DEFAULT_PR_BUDGET_LINES)))
    except ValueError:
        return DEFAULT_PR_BUDGET_LINES


def read_merged_pull_requests(root: Path, since: datetime) -> list[dict[str, Any]] | None:
    """Asks GitHub, through the ``gh`` CLI, for the pull requests merged since a date.

    Returns:
        The pull requests (number, additions, deletions, createdAt, mergedAt), or None when gh
        is missing, not signed in, or the repository is not on GitHub.
    """
    if shutil.which("gh") is None:
        return None
    command = [
        *("gh", "pr", "list", "--state", "merged", "--limit", "200"),
        *("--search", f"merged:>={since.date()}", "--json", "number,additions,deletions,createdAt,mergedAt"),
    ]
    try:
        completed = subprocess.run(
            command,
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=GH_TIMEOUT_SECONDS,
        )
        data = json.loads(completed.stdout) if completed.returncode == 0 else None
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else None


def _hours_to_merge(pull_request: dict[str, Any]) -> float | None:
    try:
        opened = datetime.fromisoformat(str(pull_request["createdAt"]).replace("Z", "+00:00"))
        merged = datetime.fromisoformat(str(pull_request["mergedAt"]).replace("Z", "+00:00"))
    except (KeyError, ValueError):
        return None
    return (merged - opened).total_seconds() / 3600


def pull_requests_section(pull_requests: list[dict[str, Any]] | None, budget: int) -> list[str]:
    """Merged pull requests: how many, how big against the budget, how long they took to merge."""
    heading = ["## Pull requests (GitHub)", ""]
    if pull_requests is None:
        return [*heading, "Not available: the `gh` CLI is missing, not signed in, or this repository is not on GitHub."]
    if not pull_requests:
        return [*heading, "No pull requests merged in the window."]
    sizes = [int(pr.get("additions") or 0) + int(pr.get("deletions") or 0) for pr in pull_requests]
    hours = [value for value in map(_hours_to_merge, pull_requests) if value is not None]
    over = f"{sum(size > budget for size in sizes)} of {len(sizes)} (budget {budget})"
    median_hours = f"{statistics.median(hours):.1f} h" if hours else "n/a"
    return [
        *heading,
        "| Merged | Median changed lines | Over the budget | Median time to merge |",
        "| --- | --- | --- | --- |",
        f"| {len(sizes)} | {statistics.median(sizes):.0f} | {over} | {median_hours} |",
    ]


def build_report(
    root: Path,
    days: int,
    now: datetime | None = None,
    pull_requests: list[dict[str, Any]] | None = None,
) -> str:
    """Builds the full Markdown report for a project and a window of days.

    Args:
        root: Project root.
        days: Length of the window.
        now: End of the window; defaults to the current time.
        pull_requests: Merged pull requests to report; read from GitHub when omitted.
    """
    now = now or datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    events = [event for event in read_events(root) if str(event.get("time", "")) >= since.isoformat(timespec="seconds")]
    if pull_requests is None:
        pull_requests = read_merged_pull_requests(root, since)
    sections = [
        [f"# konundrm-eng impact report: {root.name}, last {days} days", ""],
        delivery_section(read_commits(root, since)),
        rework_section(root),
        gates_section(events),
        pull_requests_section(pull_requests, _pr_budget()),
        [
            "## Reading it",
            "",
            "- Falling fixes per feature and escaped defects mean the gates catch problems before they ship.",
            "- The gate a bug escaped from names the control to sharpen: a spec criterion, a property, a review rule.",
            "- Many review rounds per task point at vague specs or plans: invest more in those approvals.",
            "- Frequent stop blocks or role violations show where Claude struggles; improve that skill or standard.",
            "- Pull requests over the budget are reviewed worse; split them in writing-plans, not after the fact.",
            "- Gate events are logged per machine; compare trends over time, not people.",
        ],
    ]
    return "\n".join(line for section in sections for line in [*section, ""]).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    """Prints the impact report for the project containing the current directory."""
    parser = argparse.ArgumentParser(description="konundrm-eng impact report")
    parser.add_argument("--days", type=int, default=30, help="window to report on (default 30)")
    arguments = parser.parse_args(argv)
    sys.stdout.write(build_report(project_root({"cwd": str(Path.cwd())}), arguments.days))
    return 0


if __name__ == "__main__":
    sys.exit(main())
