"""Finds, runs and caches the project's single quality-gate command.

Every hook and every skill gets the check command from find_check_command(), so they cannot
disagree about what "the check" is. Skills call it through the CLI at the bottom of this file:
``sh "${CLAUDE_PLUGIN_ROOT}/hooks/run.sh" quality_check.py``.

Sections:
    gates_disabled()       — honours the KONUNDRM_GATE=off escape hatch.
    find_check_command()   — discovers the command.
    is_check_invocation()  — tells whether a shell command line runs exactly that command.
    run_command()          — runs a shell command and keeps the end of its output.
    remember_green_tree(), green_tree() — keep the last green tree beside the repository.
    CheckResult, run_check() — runs the check unless the same tree content already passed.
    main()                 — CLI: prints the check command.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from hook_state import SessionState
from project_paths import project_root
from working_tree import run_git

if sys.version_info >= (3, 11):
    import tomllib

CHECK_TIMEOUT_SECONDS = 600
OUTPUT_TAIL_LINES = 60
CD_PREFIX = re.compile(r"""^cd\s+(?:"([^"]+)"|'([^']+)'|(\S+))\s*(?:&&|;)\s*(.+)$""")
MSYS_DRIVE_PATH = re.compile(r"^/([A-Za-z])(/.*)?$")
GREEN_TREE_FILE = "konundrm-eng-green"


def gates_disabled() -> bool:
    """Returns True when the user switched the quality gates off with KONUNDRM_GATE=off."""
    return os.environ.get("KONUNDRM_GATE", "").strip().lower() in {"off", "0", "false"}


def _node_runner(root: Path) -> str:
    if (root / "pnpm-lock.yaml").is_file():
        return "pnpm"
    if (root / "yarn.lock").is_file():
        return "yarn"
    if (root / "bun.lock").is_file() or (root / "bun.lockb").is_file():
        return "bun"
    return "npm"


def _has_poe_check(pyproject: Path) -> bool:
    text = pyproject.read_text(encoding="utf-8", errors="replace")
    if sys.version_info >= (3, 11):
        try:
            tasks = tomllib.loads(text).get("tool", {}).get("poe", {}).get("tasks", {})
        except tomllib.TOMLDecodeError:
            return False
        return "check" in tasks
    else:  # Python 3.10 has no TOML parser.
        return bool(re.search(r"(?ms)^\[tool\.poe\.tasks\].*?^check\s*=", text))


def find_check_command(root: Path, env: dict[str, str] | None = None) -> str | None:
    """Discovers the single command that runs every quality gate for the project.

    Resolution order: the KONUNDRM_CHECK_CMD variable, a ``check`` script in package.json, a
    ``check`` poethepoet task in pyproject.toml, then a ``check`` target in a Makefile or justfile.

    Args:
        root: Project root directory.
        env: Environment to read the override from; defaults to os.environ.

    Returns:
        The shell command, or None when the project exposes none.
    """
    env = dict(os.environ) if env is None else env
    override = env.get("KONUNDRM_CHECK_CMD", "").strip()
    if override:
        return override

    package_json = root / "package.json"
    if package_json.is_file():
        try:
            scripts = json.loads(package_json.read_text(encoding="utf-8")).get("scripts") or {}
        except (OSError, ValueError, AttributeError):
            scripts = {}
        if "check" in scripts:
            return f"{_node_runner(root)} run check"

    pyproject = root / "pyproject.toml"
    if pyproject.is_file() and _has_poe_check(pyproject):
        return "uv run poe check" if (root / "uv.lock").is_file() else "poe check"

    for filename, runner in (("Makefile", "make"), ("justfile", "just")):
        recipe_file = root / filename
        if (
            recipe_file.is_file()
            and shutil.which(runner)
            and re.search(r"(?m)^check\s*:", recipe_file.read_text(encoding="utf-8", errors="replace"))
        ):
            return f"{runner} check"
    return None


def _normalize(command: str) -> str:
    text = " ".join(command.split())
    text = re.sub(r"\s*2>&1$", "", text)
    return text.rstrip(";").strip()


def _equivalent_forms(check: str) -> set[str]:
    canonical = _normalize(check)
    forms = {canonical}
    if canonical.startswith("uv run "):
        forms.add(canonical[len("uv run ") :])
    elif canonical.startswith("poe "):
        forms.add(f"uv run {canonical}")
    return forms


def _as_local_path(path: str) -> Path:
    match = MSYS_DRIVE_PATH.match(path)
    if os.name == "nt" and match:  # Git Bash spells C:\x as /c/x.
        return Path(f"{match.group(1)}:{match.group(2) or '/'}")
    return Path(path)


def _same_directory(first: Path, second: Path) -> bool:
    try:
        return first.resolve() == second.resolve()
    except OSError:
        return False


def is_check_invocation(command: str, check: str, root: Path, cwd: Path) -> bool:
    """Tells whether a shell command line runs exactly the project's check from its root.

    Accepts the check alone or preceded by ``cd <root> &&``. Rejects pipelines and anything else
    whose exit status could hide a failing check.

    Args:
        command: The command line Claude ran.
        check: The project's check command.
        root: Project root.
        cwd: Directory the command line started in.
    """
    text = _normalize(command)
    directory = cwd
    match = CD_PREFIX.match(text)
    if match:
        target = _as_local_path(next(group for group in match.groups()[:3] if group))
        directory = target if target.is_absolute() else cwd / target
        text = match.group(4)
    return _same_directory(directory, root) and text in _equivalent_forms(check)


def run_command(command: str, cwd: Path, timeout: int = CHECK_TIMEOUT_SECONDS) -> tuple[int, str]:
    """Runs a shell command and keeps the end of its combined output.

    Args:
        command: Command line, run through the platform shell.
        cwd: Working directory.
        timeout: Seconds before the command is abandoned (reported as exit code 124).

    Returns:
        The exit code and the last OUTPUT_TAIL_LINES lines of stdout followed by stderr.
    """
    try:
        # The project's own check command is a shell line by definition (npm run …, make …).
        completed = subprocess.run(  # noqa: S602 - the check command is a shell line by definition
            command,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return 124, f"Timed out after {timeout}s: {command}"
    except OSError as error:
        return 127, f"Could not run `{command}`: {error}"
    output = f"{completed.stdout or ''}\n{completed.stderr or ''}".strip()
    return completed.returncode, "\n".join(output.splitlines()[-OUTPUT_TAIL_LINES:])


def _green_tree_path(root: Path) -> Path | None:
    output = run_git(["rev-parse", "--git-path", GREEN_TREE_FILE], root)
    if output is None:
        return None
    # Git answers relative to the directory it ran in, or absolute (linked worktrees).
    return root / output.decode("utf-8", errors="replace").strip()


def remember_green_tree(root: Path, tree: str | None) -> None:
    """Records, under the repository's Git directory, the tree whose check just passed.

    The file lives beside the repository rather than in CLAUDE_PLUGIN_DATA so that any shell,
    including a Git hook, can read it back with green_tree().

    Args:
        root: Project root inside a Git repository; nothing happens outside one.
        tree: Tree object that passed (working_tree.snapshot_tree), or None when the snapshot is
            unknown. None deletes the record, so an older tree is never mistaken for this one.

    Side effects:
        Writes or deletes ``<git-path konundrm-eng-green>``. A filesystem error is ignored: a
        missing record only costs one more run of the check.
    """
    path = _green_tree_path(root)
    if path is None:
        return
    try:
        if tree is None:
            path.unlink(missing_ok=True)
        else:
            path.write_text(f"{tree}\n", encoding="utf-8")
    except OSError:
        return  # The record is an optimisation; losing it only means the check runs again.


def green_tree(root: Path) -> str | None:
    """Reads the tree whose check last passed in this repository, without CLAUDE_PLUGIN_DATA.

    Args:
        root: Project root.

    Returns:
        The tree object's SHA, or None when no check has passed yet, the record is unreadable
        or ``root`` is not inside a Git repository.
    """
    path = _green_tree_path(root)
    if path is None:
        return None
    try:
        tree = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return tree or None


@dataclass(frozen=True)
class CheckResult:
    """Outcome of one quality-gate run, or of reusing an earlier green run."""

    passed: bool
    exit_code: int
    output_tail: str
    cached: bool


def run_check(root: Path, check: str, state: SessionState, fingerprint: str | None) -> CheckResult:
    """Runs the check unless the same tree content already passed, and records a pass.

    Args:
        root: Project root.
        check: The project's check command.
        state: Session record holding the last green fingerprint; saved on a pass.
        fingerprint: Current tree snapshot (working_tree.snapshot_tree), or None when unknown.

    Returns:
        The result; ``cached`` is True when an earlier green run was reused.

    Side effects:
        A fresh pass also records ``fingerprint`` beside the repository (remember_green_tree).
    """
    if fingerprint is not None and fingerprint == state.green_fingerprint:
        state.mark_green(fingerprint)
        state.save()
        return CheckResult(passed=True, exit_code=0, output_tail="", cached=True)
    exit_code, output_tail = run_command(check, root)
    if exit_code == 0:
        state.mark_green(fingerprint)
        state.save()
        remember_green_tree(root, fingerprint)
    return CheckResult(passed=exit_code == 0, exit_code=exit_code, output_tail=output_tail, cached=False)


def main() -> int:
    """Prints the project's check command; exits 1 with an explanation when there is none."""
    root = project_root({"cwd": os.getcwd()})
    check = find_check_command(root)
    if check is None:
        sys.stderr.write(f"No check command found in {root}. Run /konundrm-eng:setup-project to create one.\n")
        return 1
    print(check)
    return 0


if __name__ == "__main__":
    sys.exit(main())
