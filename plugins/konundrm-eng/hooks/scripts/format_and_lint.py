"""PostToolUse hook on Edit, Write and MultiEdit: formats and lints the file just edited.

Runs only the tools the project already opted into (ruff; biome; prettier and eslint from
node_modules), never downloads anything, and reports lint errors that auto-fix could not resolve
back to Claude with exit code 2. Unused imports and variables are left alone: they are normal
between two edits (an import added before its first use), and the stop gate's full check reports
any that remain. It also marks the session dirty, the stop gate's signal outside Git repositories.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from file_kinds import is_documentation_path
from hook_io import read_hook_input
from hook_state import SessionState
from project_paths import project_root, relative_path

PYTHON_SUFFIXES = frozenset({".py", ".pyi"})
ESLINT_SUFFIXES = frozenset({".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts", ".vue", ".svelte"})
PRETTIER_SUFFIXES = ESLINT_SUFFIXES | {".css", ".scss", ".less", ".html", ".json", ".jsonc", ".yaml", ".yml"}
# Unused import (F401) and unused variable (F841): ruff --fix would delete an import added one
# edit before the code that uses it.
RUFF_RULES_IGNORED_MID_EDIT = "F401,F841"
STEP_TIMEOUT_SECONDS = 60
OUTPUT_TAIL_LINES = 40


@dataclass(frozen=True)
class Step:
    """One tool invocation; only ``lint`` steps report remaining problems to Claude."""

    kind: str  # "format" or "lint"
    argv: tuple[str, ...]


def _exists(root: Path, *names: str) -> bool:
    return any((root / name).exists() for name in names)


def _uses_ruff(root: Path) -> bool:
    if _exists(root, "ruff.toml", ".ruff.toml"):
        return True
    pyproject = root / "pyproject.toml"
    return pyproject.is_file() and "[tool.ruff" in pyproject.read_text(encoding="utf-8", errors="replace")


def _package_mentions(root: Path, name: str) -> bool:
    try:
        package = json.loads((root / "package.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    sections = (package.get("dependencies") or {}, package.get("devDependencies") or {})
    return name in package or any(name in section for section in sections)


def _uses_prettier(root: Path) -> bool:
    configs = [p.name for p in root.glob(".prettierrc*")] + [p.name for p in root.glob("prettier.config.*")]
    return bool(configs) or _package_mentions(root, "prettier")


def _uses_eslint(root: Path) -> bool:
    return bool(list(root.glob("eslint.config.*")) or list(root.glob(".eslintrc*")))


def _uses_biome(root: Path) -> bool:
    return _exists(root, "biome.json", "biome.jsonc")


def _node_bin(root: Path, name: str) -> str | None:
    folder = root / "node_modules" / ".bin"
    for candidate in (folder / f"{name}.cmd", folder / name) if os.name == "nt" else (folder / name,):
        if candidate.is_file():
            return str(candidate)
    return None


def _python_bin(root: Path, name: str) -> str | None:
    for candidate in (root / ".venv" / "Scripts" / f"{name}.exe", root / ".venv" / "bin" / name):
        if candidate.is_file():
            return str(candidate)
    return shutil.which(name)


def plan_steps(path: Path, root: Path) -> list[Step]:
    """Chooses the formatter and linter invocations for one edited file.

    Args:
        path: Absolute path of the edited file.
        root: Project root, used to detect which tools the project uses.

    Returns:
        Steps in execution order; empty when the project configures no tool for this file type.
    """
    suffix = path.suffix.lower()
    target = str(path)
    if suffix in PYTHON_SUFFIXES and _uses_ruff(root):
        ruff = _python_bin(root, "ruff")
        if ruff:
            return [
                Step("format", (ruff, "format", target)),
                Step("lint", (ruff, "check", "--fix", "--ignore", RUFF_RULES_IGNORED_MID_EDIT, target)),
            ]
        return []
    if suffix in PRETTIER_SUFFIXES and _uses_biome(root):
        biome = _node_bin(root, "biome")
        return [Step("lint", (biome, "check", "--write", target))] if biome else []
    steps: list[Step] = []
    if suffix in PRETTIER_SUFFIXES and _uses_prettier(root):
        prettier = _node_bin(root, "prettier")
        if prettier:
            steps.append(Step("format", (prettier, "--write", target)))
    if suffix in ESLINT_SUFFIXES and _uses_eslint(root):
        eslint = _node_bin(root, "eslint")
        if eslint:
            steps.append(Step("lint", (eslint, "--fix", target)))
    return steps


def _run(step: Step, root: Path) -> tuple[int, str]:
    try:
        completed = subprocess.run(
            step.argv,
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=STEP_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError) as error:
        return 0, f"skipped {step.argv[0]}: {error}"  # A broken local tool must not block editing.
    output = f"{completed.stdout or ''}\n{completed.stderr or ''}".strip()
    return completed.returncode, "\n".join(output.splitlines()[-OUTPUT_TAIL_LINES:])


def main() -> int:
    """Runs the hook for a PostToolUse event read from stdin."""
    event = read_hook_input()
    tool_input = event.get("tool_input") or {}
    raw_path = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not raw_path:
        return 0
    root = project_root(event)
    path = Path(raw_path) if Path(raw_path).is_absolute() else root / raw_path
    if relative_path(str(path), root) is None or not path.is_file():
        return 0

    if not is_documentation_path(path.name):
        state = SessionState(event.get("session_id"))
        if not state.dirty:
            state.dirty = True
            state.save()

    problems = []
    for step in plan_steps(path, root):
        exit_code, output = _run(step, root)
        if step.kind == "lint" and exit_code != 0:
            tool = Path(step.argv[0]).stem
            problems.append(f"$ {tool} {' '.join(step.argv[1:-1])} <file>\n{output}")
    if problems:
        shown = relative_path(str(path), root)
        sys.stderr.write(
            f"Lint problems remain in {shown} after auto-fix. Fix them before moving on:\n\n"
            + "\n\n".join(problems)
            + "\n"
        )
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
