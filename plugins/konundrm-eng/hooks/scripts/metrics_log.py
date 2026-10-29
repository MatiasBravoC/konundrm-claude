"""Append-only log of what the konundrm-eng gates did in a project, read by the impact report.

Each hook that blocks, asks or restores something records one event, so the team can see whether
the gates catch real problems or only add friction. The log lives in the plugin's data directory,
one JSON-lines file per project, never in the repository. Recording never fails a hook.

Event kinds:
    stop_blocked        — the stop gate kept Claude working (``reason``: red_check, suppression or both).
    stop_gave_up        — the turn ended with those problems after the maximum number of attempts.
    commit_denied       — the commit gate denied a commit (``reason``: bypass, subagent, suppression,
                          red_check).
    secret_flagged      — an edit or a commit carried what looks like a credential and the person
                          was asked (``where``: edit, commit).
    role_violation      — a subagent changed files outside its role (``role``, ``paths``).
    role_restored       — the audit restored those files itself.
    dependency_flagged  — the dependency guard asked the person to confirm a package.
    dependency_denied   — the dependency guard denied a package OSV lists as malicious.

Sections:
    record_event()  — appends one event for a project.
    read_events()   — reads a project's events, oldest first.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hook_io import plugin_data_directory


def _log_path(root: Path) -> Path:
    try:
        key = os.path.normcase(str(root.resolve()))
    except OSError:
        key = os.path.normcase(str(root))
    return plugin_data_directory() / "metrics" / f"{hashlib.sha256(key.encode()).hexdigest()[:16]}.jsonl"


def record_event(root: Path, kind: str, session_id: str | None = None, **details: Any) -> None:
    """Appends one event to the project's log; failures are ignored.

    Args:
        root: Project root the event belongs to.
        kind: One of the event kinds in the module docstring.
        session_id: Claude Code session that triggered it, when known.
        **details: Small JSON-serialisable fields that explain the event.
    """
    event = {
        "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "kind": kind,
        "project": str(root),
        "session": session_id,
        **details,
    }
    with contextlib.suppress(OSError, TypeError, ValueError):
        path = _log_path(root)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as log:
            log.write(json.dumps(event, ensure_ascii=False) + "\n")


def read_events(root: Path) -> list[dict[str, Any]]:
    """Reads every event recorded for a project, skipping unreadable lines.

    Returns:
        The events in the order they were recorded; empty when there is no log.
    """
    try:
        lines = _log_path(root).read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    events = []
    for line in lines:
        with contextlib.suppress(ValueError):
            event = json.loads(line)
            if isinstance(event, dict):
                events.append(event)
    return events
