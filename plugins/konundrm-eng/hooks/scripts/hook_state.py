"""Records the hooks keep between events: one per session and one per running subagent.

State is an optimisation and an audit aid. A missing, unreadable or unwritable record never fails
a hook; it only makes the next hook do more work.

Sections:
    SessionState    — quality-gate flags of one Claude Code session.
    SubagentRecord  — the working tree a konundrm-eng subagent started from.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any

from hook_io import plugin_data_directory

STATE_RETENTION_SECONDS = 7 * 24 * 3600


def _state_directory() -> Path:
    return plugin_data_directory() / "sessions"


def _file_safe(name: str | None, fallback: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", name or fallback)


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _load(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _save(path: Path, data: dict[str, Any]) -> None:
    """Writes a record atomically and prunes sibling records older than the retention period."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(f".{os.getpid()}.tmp")
        temporary.write_text(json.dumps(data), encoding="utf-8")
        os.replace(temporary, path)
        cutoff = time.time() - STATE_RETENTION_SECONDS
        for record in path.parent.glob("*.json"):
            if record.stat().st_mtime < cutoff:
                record.unlink(missing_ok=True)
    except OSError:
        pass


class SessionState:
    """What the quality gates know about one Claude Code session.

    Attributes:
        dirty: True once Edit/Write changed a non-documentation file this turn; the stop gate's
            fallback outside Git repositories.
        green_fingerprint: Tree snapshot of the last passing check.
        stop_blocks: Consecutive times the stop gate has blocked the turn from ending.
        turn_start_tree: Tree snapshot taken when the current turn began.
    """

    def __init__(self, session_id: str | None) -> None:
        self._path = _state_directory() / f"{_file_safe(session_id, 'no-session')}.json"
        data = _load(self._path)
        self.dirty = bool(data.get("dirty", False))
        self.green_fingerprint: str | None = data.get("green_fingerprint")
        self.stop_blocks = _as_int(data.get("stop_blocks"))
        self.turn_start_tree: str | None = data.get("turn_start_tree")

    def start_turn(self, tree: str | None) -> None:
        """Begins a turn: remembers the tree it starts from and forgets the last turn's flags."""
        self.turn_start_tree = tree
        self.dirty = False
        self.stop_blocks = 0

    def mark_green(self, fingerprint: str | None) -> None:
        """Records a passing check: clears the dirty flag and the block counter."""
        self.dirty = False
        self.green_fingerprint = fingerprint
        self.stop_blocks = 0

    def save(self) -> None:
        """Persists the record; failures are ignored."""
        _save(
            self._path,
            {
                "dirty": self.dirty,
                "green_fingerprint": self.green_fingerprint,
                "stop_blocks": self.stop_blocks,
                "turn_start_tree": self.turn_start_tree,
            },
        )


class SubagentRecord:
    """The working tree one konundrm-eng subagent started from, kept until it stops.

    Attributes:
        role: The subagent's konundrm-eng role.
        before_tree: Tree snapshot taken when the subagent started.
        blocks: Times its stop was blocked because of changes outside its role.
    """

    def __init__(self, session_id: str | None, agent_id: str) -> None:
        name = f"{_file_safe(session_id, 'no-session')}--{_file_safe(agent_id, 'no-agent')}.json"
        self._path = _state_directory() / "agents" / name
        data = _load(self._path)
        self.role: str | None = data.get("role")
        self.before_tree: str | None = data.get("before_tree")
        self.blocks = _as_int(data.get("blocks"))

    def save(self) -> None:
        """Persists the record; failures are ignored."""
        _save(self._path, {"role": self.role, "before_tree": self.before_tree, "blocks": self.blocks})

    def delete(self) -> None:
        """Removes the record once the subagent has stopped."""
        with contextlib.suppress(OSError):
            self._path.unlink(missing_ok=True)
