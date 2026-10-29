"""Splits a shell command line into the simple commands it would run, for hooks that inspect them.

Understands POSIX shells, PowerShell and cmd well enough for guardrails: quotes, comments, line
continuations, ``;``/``&&``/``||``/``|``/``&`` separators, wrappers that run another command (env,
command, sudo, PowerShell's ``&``), command strings run by a nested shell (``bash -c``,
``pwsh -Command`` including ``-EncodedCommand``, ``cmd /c``), and environment assignments that apply
to a command (``NAME=value cmd``, or ``export``/``$env:``/``set`` earlier in the same line).

It is a guardrail parser, not a shell: a script can still run commands no parser sees.

Sections:
    ShellCommand     — one simple command with the environment assignments that apply to it.
    iter_commands()  — every simple command in a command line, wrappers and nested shells unwrapped.
"""

from __future__ import annotations

import base64
import binascii
import re
import shlex
from collections.abc import Iterator
from dataclasses import dataclass

SEPARATOR_CHARACTERS = frozenset(";&|()\n")
FALLBACK_SEPARATOR = re.compile(r"&&|\|\||[;|&\n]")
ENV_ASSIGNMENT = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$", re.DOTALL)
POWERSHELL_ENV = re.compile(r"^\$env:([A-Za-z_][A-Za-z0-9_]*)(?:=(.*))?$", re.IGNORECASE | re.DOTALL)
LINE_CONTINUATION = re.compile(r"(\\|`)\r?\n")
MAX_SHELL_NESTING = 4

# Wrappers that run their arguments as a command, with the options that consume a value.
WRAPPER_OPTIONS_WITH_VALUE: dict[str, frozenset[str]] = {
    "command": frozenset(),
    "builtin": frozenset(),
    "exec": frozenset(),
    "nohup": frozenset(),
    "env": frozenset({"-u", "--unset", "-C", "--chdir", "-S", "--split-string"}),
    "sudo": frozenset({"-u", "-g", "-C", "-D", "-h", "-p", "-r", "-t", "-U"}),
    "doas": frozenset({"-u", "-C"}),
    "nice": frozenset({"-n", "--adjustment"}),
    "time": frozenset({"-f", "--format", "-o", "--output"}),
    "stdbuf": frozenset({"-i", "-o", "-e", "--input", "--output", "--error"}),
    "xargs": frozenset(
        {
            "-I",
            "-L",
            "-n",
            "-P",
            "-s",
            "-d",
            "-E",
            "-a",
            "--replace",
            "--max-lines",
            "--max-args",
            "--max-procs",
            "--max-chars",
            "--delimiter",
            "--eof",
            "--arg-file",
        }
    ),
    # timeout also takes a positional duration before the command (see _unwrap).
    "timeout": frozenset({"-s", "-k", "--signal", "--kill-after"}),
}
# Builtins that run their joined arguments as a new command line.
EVALUATORS = frozenset({"eval", "iex", "invoke-expression"})
POSIX_SHELLS = frozenset({"sh", "bash", "zsh", "dash", "ksh"})
POWERSHELLS = frozenset({"pwsh", "powershell"})


@dataclass(frozen=True)
class ShellCommand:
    """One simple command, after wrappers and nested shells were unwrapped.

    Attributes:
        program: Executable name, lower-cased, without directory or ``.exe`` (``git``, ``npm``).
        arguments: Everything after the program.
        env: ``NAME=value`` assignments in effect for this command.
    """

    program: str
    arguments: tuple[str, ...]
    env: tuple[str, ...]


def _strip_comments(command: str) -> str:
    """Removes ``#`` comments outside quotes, keeping the newline that ends each one."""
    kept: list[str] = []
    quote = ""
    index = 0
    while index < len(command):
        char = command[index]
        if quote:
            kept.append(char)
            if char == "\\" and quote == '"' and index + 1 < len(command):
                kept.append(command[index + 1])
                index += 1
            elif char == quote:
                quote = ""
        elif char in "'\"":
            quote = char
            kept.append(char)
        elif char == "\\" and index + 1 < len(command):
            kept.append(command[index : index + 2])
            index += 1
        elif char == "#" and (not kept or kept[-1][-1:].isspace() or kept[-1][-1:] in SEPARATOR_CHARACTERS):
            newline = command.find("\n", index)
            index = len(command) if newline == -1 else newline
            continue
        else:
            kept.append(char)
        index += 1
    return "".join(kept)


def _simple_commands(command: str) -> list[list[str]]:
    """Splits a command line into the token lists of its simple commands."""
    text = LINE_CONTINUATION.sub(" ", command)
    try:
        lexer = shlex.shlex(_strip_comments(text), posix=True, punctuation_chars=";&|()<>\n")
        lexer.whitespace = " \t\r"
        lexer.whitespace_split = True
        lexer.commenters = ""
        tokens = list(lexer)
    except ValueError:  # Unbalanced quotes: fall back to a plain split.
        return [segment.split() for segment in FALLBACK_SEPARATOR.split(text) if segment.split()]

    commands: list[list[str]] = [[]]
    for token in tokens:
        if token and set(token) <= SEPARATOR_CHARACTERS:
            commands.append([])
        else:
            commands[-1].append(token)
    return [tokens for tokens in commands if tokens]


def _program(token: str) -> str:
    name = re.split(r"[\\/]", token)[-1].lower()
    return name[:-4] if name.endswith(".exe") else name


def _skip_options(arguments: list[str], options_with_value: frozenset[str]) -> list[str]:
    index = 0
    while index < len(arguments) and arguments[index].startswith("-"):
        if arguments[index] == "--":
            return arguments[index + 1 :]
        index += 2 if arguments[index] in options_with_value else 1
    return arguments[index:]


def _posix_shell_script(arguments: list[str]) -> str | None:
    for index, argument in enumerate(arguments):
        if argument.startswith("--"):
            continue
        if not argument.startswith("-"):
            return None
        if "c" in argument[1:]:
            return arguments[index + 1] if index + 1 < len(arguments) else None
    return None


def _powershell_script(arguments: list[str]) -> str | None:
    for index, argument in enumerate(arguments):
        flag = argument.lower()
        if flag == "-c" or (len(flag) >= 4 and "-command".startswith(flag)):
            return " ".join(arguments[index + 1 :])
        if flag in ("-e", "-ec") or (len(flag) >= 3 and "-encodedcommand".startswith(flag)):
            try:
                return base64.b64decode(arguments[index + 1]).decode("utf-16-le")
            except (IndexError, ValueError, binascii.Error):
                return None
    return None


def _cmd_script(arguments: list[str]) -> str | None:
    for index, argument in enumerate(arguments):
        if argument.lower() in ("/c", "/k", "/r"):
            return " ".join(arguments[index + 1 :])
    return None


def _nested_script(program: str, arguments: list[str]) -> str | None:
    """Returns the command string a shell runs (``bash -c``, ``pwsh -Command``, ``cmd /c``), if any."""
    if program in POSIX_SHELLS:
        return _posix_shell_script(arguments)
    if program in POWERSHELLS:
        return _powershell_script(arguments)
    if program == "cmd":
        return _cmd_script(arguments)
    if program in EVALUATORS:
        return " ".join(arguments)
    return None


def _environment_changes(tokens: list[str]) -> list[str] | None:
    """Returns the assignments a command makes for the rest of the line, or None if it makes none."""
    if tokens[0] == "export":
        return [token for token in tokens[1:] if ENV_ASSIGNMENT.match(token)]
    if tokens[0].lower() == "set" and len(tokens) == 2 and ENV_ASSIGNMENT.match(tokens[1]):
        return [tokens[1]]
    match = POWERSHELL_ENV.match(tokens[0])
    if match and match.group(2) is not None:
        return [f"{match.group(1)}={match.group(2)}"]
    if match and len(tokens) >= 3 and tokens[1] == "=":
        return [f"{match.group(1)}={tokens[2]}"]
    return None


def _unwrap(tokens: list[str], env: list[str], depth: int) -> Iterator[ShellCommand]:
    tokens = list(tokens)
    env = list(env)
    while tokens:
        while tokens and ENV_ASSIGNMENT.match(tokens[0]):
            env.append(tokens.pop(0))
        if not tokens:
            return
        program, arguments = _program(tokens[0]), tokens[1:]
        if program in WRAPPER_OPTIONS_WITH_VALUE:
            tokens = _skip_options(arguments, WRAPPER_OPTIONS_WITH_VALUE[program])
            if program == "timeout":
                tokens = tokens[1:]  # the duration
            continue
        script = _nested_script(program, arguments)
        if script is not None:
            if depth < MAX_SHELL_NESTING:
                yield from _find(script, env, depth + 1)
        else:
            yield ShellCommand(program=program, arguments=tuple(arguments), env=tuple(env))
        return


def _find(command: str, env: list[str], depth: int) -> Iterator[ShellCommand]:
    line_env = list(env)
    for tokens in _simple_commands(command):
        changes = _environment_changes(tokens)
        if changes is not None:
            line_env.extend(changes)
            continue
        yield from _unwrap(tokens, line_env, depth)


def iter_commands(command_line: str) -> Iterator[ShellCommand]:
    """Yields every simple command a command line would run.

    Args:
        command_line: The command string Claude is about to run in Bash or PowerShell.

    Yields:
        One ShellCommand per simple command, with wrappers removed and nested shell strings expanded.
    """
    yield from _find(command_line, [], 0)
