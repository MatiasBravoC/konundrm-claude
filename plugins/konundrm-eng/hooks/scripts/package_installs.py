"""Finds the registry packages a shell command line would install or run.

Covers npm, pnpm, yarn and bun (add/install, npx/dlx/exec) and pip, uv, uvx, poetry, pdm and pipx.
Versions, extras and aliases are stripped to the registry name. Local paths, URLs, Git sources and
requirement files are not registry names and are skipped, and so is a whole command that points at
a custom index or registry, because the public registry cannot vouch for it.

Sections:
    PackageRequest          — one package a command would fetch.
    find_package_requests() — every such package in a command line.
    normalize_name()        — the comparable form of a package name.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass

from shell_commands import ShellCommand, iter_commands

# (program, subcommand) → (ecosystem, mode). Mode "all": every positional is a package.
# Mode "first": only the first positional is a package; the rest are arguments for it.
# Mode "options": positionals are a command to run; only package options (--with) add packages.
NPM_INSTALL_ALIASES = (
    "install",
    "i",
    "in",
    "ins",
    "inst",
    "insta",
    "instal",
    "isnt",
    "isnta",
    "isntal",
    "isntall",
    "add",
)
INSTALLERS: dict[tuple[str, str], tuple[str, str]] = {
    **{("npm", alias): ("npm", "all") for alias in NPM_INSTALL_ALIASES},
    ("npm", "exec"): ("npm", "first"),
    ("npm", "x"): ("npm", "first"),
    ("pnpm", "add"): ("npm", "all"),
    ("pnpm", "dlx"): ("npm", "first"),
    ("yarn", "add"): ("npm", "all"),
    ("yarn global", "add"): ("npm", "all"),
    ("yarn", "dlx"): ("npm", "first"),
    ("bun", "add"): ("npm", "all"),
    ("bun", "install"): ("npm", "all"),
    ("bun", "x"): ("npm", "first"),
    ("pip", "install"): ("pypi", "all"),
    ("uv pip", "install"): ("pypi", "all"),
    ("uv", "add"): ("pypi", "all"),
    ("uv", "run"): ("pypi", "options"),
    ("uv tool", "install"): ("pypi", "all"),
    ("uv tool", "run"): ("pypi", "first"),
    ("poetry", "add"): ("pypi", "all"),
    ("pdm", "add"): ("pypi", "all"),
    ("pipx", "install"): ("pypi", "all"),
    ("pipx", "run"): ("pypi", "first"),
}
DIRECT_RUNNERS = {"npx": "npm", "pnpx": "npm", "bunx": "npm", "uvx": "pypi"}
PIP_PROGRAM = re.compile(r"^pip(\d+(\.\d+)*)?$")  # pip, pip3, pip3.12
PYTHON_PROGRAM = re.compile(r"^(py|python(\d+(\.\d+)*)?)$")  # py, python, python3, python3.12

# Options per ecosystem: values that are packages (and whether they replace the first positional),
# options that take a non-package value, and options that point at another package source.
EXTRA_PACKAGE_OPTIONS = {"npm": frozenset(), "pypi": frozenset({"--with"})}
REPLACING_PACKAGE_OPTIONS = {"npm": frozenset({"-p", "--package"}), "pypi": frozenset({"--from", "--spec"})}
VALUE_OPTIONS = {
    "npm": frozenset({"--prefix", "-C", "--dir", "--cwd", "-w", "--workspace", "--filter", "--tag", "--save-prefix"}),
    "pypi": frozenset(
        {
            "-r",
            "--requirement",
            "-e",
            "--editable",
            "-c",
            "--constraint",
            "-t",
            "--target",
            "--prefix",
            "--root",
            "-p",
            "--python",
            "--group",
            "-G",
            "--optional",
            "--extra",
            "--directory",
            "--project",
            "--platform",
            "--python-version",
            "--cache-dir",
            "--log",
            "--only-binary",
            "--no-binary",
            "--config-settings",
        }
    ),
}
CUSTOM_SOURCE_OPTIONS = {
    "npm": frozenset({"--registry"}),
    "pypi": frozenset(
        {"-i", "--index-url", "--extra-index-url", "--index", "--default-index", "-f", "--find-links", "--source"}
    ),
}

NPM_NAME = re.compile(r"^(?:@[a-z0-9][a-z0-9._~-]*/)?[a-z0-9][a-z0-9._~-]*$")
PYPI_NAME = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?")
NOT_A_NPM_NAME_PREFIXES = (
    ".",
    "/",
    "~",
    "file:",
    "link:",
    "git+",
    "git:",
    "git@",
    "http:",
    "https:",
    "github:",
    "workspace:",
    "portal:",
    "patch:",
)


@dataclass(frozen=True)
class PackageRequest:
    """One registry package a command would download.

    Attributes:
        ecosystem: ``npm`` or ``pypi``.
        name: Registry name, normalised (normalize_name).
        runs_binary: True when the package was named as a command to run (npx, uvx), which may
            also be a binary the project already has installed.
    """

    ecosystem: str
    name: str
    runs_binary: bool = False


def normalize_name(ecosystem: str, name: str) -> str:
    """Returns the form registries compare names in (PEP 503 for PyPI, lower case for npm)."""
    if ecosystem == "pypi":
        return re.sub(r"[-_.]+", "-", name).lower()
    return name.lower()


def _npm_name(spec: str) -> str | None:
    if spec.startswith(NOT_A_NPM_NAME_PREFIXES) or "\\" in spec or spec[1:2] == ":":
        return None
    if "@npm:" in spec:
        spec = spec.split("@npm:", 1)[1]
    if spec.startswith("@"):
        scope_end = spec.find("/")
        if scope_end < 0:
            return None
        version_at = spec.find("@", scope_end)
    elif "/" in spec:  # user/repo is a GitHub shorthand
        return None
    else:
        version_at = spec.find("@")
    name = (spec[:version_at] if version_at > 0 else spec).lower()
    return name if NPM_NAME.match(name) else None


def _pypi_name(spec: str) -> str | None:
    if "/" in spec or "\\" in spec or spec.startswith((".", "~")) or spec.endswith((".whl", ".tar.gz", ".zip")):
        return None
    match = PYPI_NAME.match(spec)
    return normalize_name("pypi", match.group(0)) if match else None


def _installer(shell_command: ShellCommand) -> tuple[str, str, list[str]] | None:
    """Recognises an installing command and returns (ecosystem, mode, arguments after the subcommand)."""
    program, arguments = shell_command.program, list(shell_command.arguments)
    if program in DIRECT_RUNNERS:
        return DIRECT_RUNNERS[program], "first", arguments
    if PYTHON_PROGRAM.match(program) and "-m" in arguments:  # python3.12 -m pip install …
        module_at = arguments.index("-m")
        module = arguments[module_at + 1] if module_at + 1 < len(arguments) else ""
        program, arguments = module, arguments[module_at + 2 :]
    if PIP_PROGRAM.match(program):
        program = "pip"
    if (program, arguments[:1]) in (("uv", ["pip"]), ("uv", ["tool"]), ("yarn", ["global"])):
        program, arguments = f"{program} {arguments[0]}", arguments[1:]
    subcommand = next((argument for argument in arguments if not argument.startswith("-")), None)
    if subcommand is None or (program, subcommand) not in INSTALLERS:
        return None
    ecosystem, mode = INSTALLERS[(program, subcommand)]
    return ecosystem, mode, arguments[arguments.index(subcommand) + 1 :]


def _package_specs(ecosystem: str, mode: str, arguments: list[str]) -> list[tuple[str, bool]] | None:
    """Reads (spec, runs_binary) pairs from an installer's arguments; None for a custom package source."""
    positionals: list[str] = []
    named: list[str] = []
    replaced_first = False
    index = 0
    while index < len(arguments):
        argument = arguments[index]
        if argument == "--":
            positionals.extend(arguments[index + 1 :])
            break
        if argument.startswith("-") and len(argument) > 1:
            option, has_value, value = argument.partition("=")
            if option in CUSTOM_SOURCE_OPTIONS[ecosystem]:
                return None
            names_package = option in EXTRA_PACKAGE_OPTIONS[ecosystem] | REPLACING_PACKAGE_OPTIONS[ecosystem]
            if (names_package or option in VALUE_OPTIONS[ecosystem]) and not has_value:
                value = arguments[index + 1] if index + 1 < len(arguments) else ""
                index += 1
            if names_package and value:
                named.append(value)
                replaced_first = replaced_first or option in REPLACING_PACKAGE_OPTIONS[ecosystem]
        else:
            positionals.append(argument)
        index += 1
    if mode == "all":
        return [(spec, False) for spec in named + positionals]
    if mode == "options":
        return [(spec, False) for spec in named]
    first = [] if replaced_first or not positionals else [(positionals[0], True)]
    return [(spec, False) for spec in named] + first


def _requests_in(shell_command: ShellCommand) -> Iterator[PackageRequest]:
    installer = _installer(shell_command)
    if installer is None:
        return
    ecosystem, mode, arguments = installer
    specs = _package_specs(ecosystem, mode, arguments)
    for spec, runs_binary in specs or []:
        name = _npm_name(spec) if ecosystem == "npm" else _pypi_name(spec)
        if name:
            yield PackageRequest(ecosystem=ecosystem, name=name, runs_binary=runs_binary)


def find_package_requests(command_line: str) -> Iterator[PackageRequest]:
    """Finds every registry package a command line would install or run.

    Args:
        command_line: The command Claude is about to run in Bash or PowerShell.

    Yields:
        One PackageRequest per package, in order, without duplicates.
    """
    seen: set[PackageRequest] = set()
    for shell_command in iter_commands(command_line):
        for request in _requests_in(shell_command):
            if request not in seen:
                seen.add(request)
                yield request
