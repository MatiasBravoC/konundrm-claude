"""Runs the repository's checks, the same steps as CI, so the plugin's gates can run them locally.

Ruff and mypy come from the active environment when they are installed; otherwise the versions
pinned in requirements-dev.txt run through uvx, so nothing has to be installed globally.
"""

from __future__ import annotations

import importlib.util
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOOKS = ROOT / "plugins" / "konundrm-eng" / "hooks"


def pinned_version(package: str) -> str:
    """Returns the version of a package pinned in requirements-dev.txt."""
    text = (ROOT / "requirements-dev.txt").read_text(encoding="utf-8")
    match = re.search(rf"(?m)^{re.escape(package)}==(\S+)", text)
    if match is None:
        raise SystemExit(f"{package} is not pinned in requirements-dev.txt")
    return match.group(1)


def tool(package: str) -> list[str]:
    """Returns the command that runs a development tool, preferring an installed copy."""
    if importlib.util.find_spec(package) is not None:
        return [sys.executable, "-m", package]
    if shutil.which("uvx") is None:
        raise SystemExit(f"{package} is not installed and uvx is missing: pip install -r requirements-dev.txt")
    return ["uvx", "--from", f"{package}=={pinned_version(package)}", package]


def steps() -> list[tuple[str, list[str]]]:
    """Lists the checks, in the order CI runs them."""
    ruff, mypy = tool("ruff"), tool("mypy")
    tests = [sys.executable, "-m", "unittest", "discover", "-s", str(HOOKS / "tests"), "-t", str(HOOKS)]
    return [
        ("Format", [*ruff, "format", "--check", "."]),
        ("Lint", [*ruff, "check", "."]),
        ("Types (Python 3.10)", mypy),
        ("Types (Python 3.13)", [*mypy, "--python-version", "3.13"]),
        ("Hook tests", tests),
    ]


def main() -> int:
    """Runs every step and reports the ones that failed."""
    failed = []
    for name, command in steps():
        print(f"--- {name}: {' '.join(command)}", flush=True)
        if subprocess.run(command, cwd=ROOT, check=False).returncode != 0:
            failed.append(name)
    if failed:
        print(f"FAILED: {', '.join(failed)}")
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
