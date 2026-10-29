"""What the project already depends on, so the dependency guard only questions new packages.

Reads package.json and node_modules for npm, and pyproject.toml, uv.lock, poetry.lock, pdm.lock and
requirements*.txt for PyPI. Also finds npm scopes served by a private registry (``.npmrc``), whose
packages the public registry cannot vouch for.

Sections:
    declared_packages()   — (ecosystem, name) pairs the project already uses.
    local_binaries()      — commands installed in node_modules/.bin.
    private_npm_scopes()  — npm scopes configured with their own registry.
"""

from __future__ import annotations

import contextlib
import json
import re
import sys
from pathlib import Path
from typing import Any

from package_installs import normalize_name

if sys.version_info >= (3, 11):
    import tomllib

NPM_DEPENDENCY_SECTIONS = ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies")
LOCK_FILE_NAME = re.compile(r'(?m)^name = "([^"]+)"')
REQUIREMENT_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")
PRIVATE_SCOPE = re.compile(r"(?m)^\s*(@[a-z0-9][a-z0-9._~-]*):registry\s*=", re.IGNORECASE)


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _npm_names(root: Path) -> set[str]:
    try:
        package = json.loads(_read(root / "package.json") or "{}")
    except ValueError:
        return set()
    names: set[str] = set()
    for section in NPM_DEPENDENCY_SECTIONS:
        dependencies = package.get(section) if isinstance(package, dict) else None
        if isinstance(dependencies, dict):
            names.update(name.lower() for name in dependencies)
    return names


def _requirement_names(requirements: Any) -> set[str]:
    """Names from a list of PEP 508 strings (dict entries such as include-group are skipped)."""
    names = set()
    for requirement in requirements if isinstance(requirements, list) else []:
        match = REQUIREMENT_NAME.match(requirement) if isinstance(requirement, str) else None
        if match:
            names.add(normalize_name("pypi", match.group(1)))
    return names


def _pyproject_names(text: str) -> set[str]:
    if not text:
        return set()
    if sys.version_info >= (3, 11):
        try:
            return _declared_in_pyproject(tomllib.loads(text))
        except tomllib.TOMLDecodeError:
            return set()
    else:  # Python 3.10 has no TOML parser; the lock files still cover locked projects.
        return set()


def _declared_in_pyproject(data: dict[str, Any]) -> set[str]:
    """Dependency names from PEP 621, PEP 735 dependency groups, uv and Poetry tables."""
    project, tool = data.get("project", {}), data.get("tool", {})
    names = _requirement_names(project.get("dependencies"))
    for group in [*project.get("optional-dependencies", {}).values(), *data.get("dependency-groups", {}).values()]:
        names |= _requirement_names(group)
    names |= _requirement_names(tool.get("uv", {}).get("dev-dependencies"))
    poetry = tool.get("poetry", {})
    poetry_sections = [poetry.get("dependencies", {})]
    poetry_sections += [group.get("dependencies", {}) for group in poetry.get("group", {}).values()]
    for section in poetry_sections:
        names |= {normalize_name("pypi", name) for name in section if name.lower() != "python"}
    return names


def _pypi_names(root: Path) -> set[str]:
    names = _pyproject_names(_read(root / "pyproject.toml"))
    for lock_file in ("uv.lock", "poetry.lock", "pdm.lock"):
        names |= {normalize_name("pypi", name) for name in LOCK_FILE_NAME.findall(_read(root / lock_file))}
    for requirements in root.glob("requirements*.txt"):
        for line in _read(requirements).splitlines():
            match = REQUIREMENT_NAME.match(line)
            if match and not line.lstrip().startswith(("-", "#")):
                names.add(normalize_name("pypi", match.group(1)))
    return names


def declared_packages(root: Path) -> set[tuple[str, str]]:
    """Lists the packages the project already declares or has locked.

    Args:
        root: Project root.

    Returns:
        ``(ecosystem, normalised name)`` pairs, ecosystem being ``npm`` or ``pypi``.
    """
    return {("npm", name) for name in _npm_names(root)} | {("pypi", name) for name in _pypi_names(root)}


def local_binaries(root: Path) -> set[str]:
    """Lists the commands the project's node_modules/.bin provides (what npx runs first)."""
    names: set[str] = set()
    with contextlib.suppress(OSError):
        for entry in (root / "node_modules" / ".bin").iterdir():
            names.add(entry.name.split(".")[0].lower() if entry.suffix in (".cmd", ".ps1") else entry.name.lower())
    return names


def private_npm_scopes(root: Path) -> set[str]:
    """Lists the npm scopes the project's .npmrc sends to their own registry (``@acme:registry=…``)."""
    return {scope.lower() for scope in PRIVATE_SCOPE.findall(_read(root / ".npmrc"))}
