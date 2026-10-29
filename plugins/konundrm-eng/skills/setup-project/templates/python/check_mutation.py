"""Mutation testing of the code a pull request changed, as a gate (Standards → Verification).

CI runs it on pull requests labelled ``risk:high``:

    uv run --with "mutmut>=3.8,<4" python scripts/check_mutation.py --base origin/main

1. Finds the functions and methods the branch changed: ``git diff`` against the merge base,
   located with ``ast``.
2. Runs mutmut on their mutants only. mutmut names a mutant ``<module>.x_<function>__mutmut_<n>``,
   or ``<module>.x<sep><Class><sep><method>__mutmut_<n>`` where the separator is U+01C1, and its
   module path drops a leading ``src.`` and a trailing ``.__init__``.
3. Reads ``mutmut results --all true``, shows each surviving mutant, and fails when the changed
   code's mutation score is below ``--min-score``. The default, 100, means every mutant is killed
   or its line carries mutmut's no-mutate pragma with the reason (an equivalent mutant).

mutmut needs ``fork``, so it does not run on native Windows: run this in CI or WSL.

Usage:
    python scripts/check_mutation.py --base <revision> [--source src] [--min-score 100]
"""

from __future__ import annotations

import argparse
import ast
import re
import subprocess
import sys
from fnmatch import fnmatchcase
from pathlib import Path, PurePosixPath

DESCRIPTION = "Mutation testing of the code a pull request changed, as a gate."
METHOD_SEPARATOR = "ǁ"  # mutmut joins class and method names with this letter
HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
RESULT_LINE = re.compile(r"^\s*(?P<name>\S+): (?P<status>[a-z][a-z ]*)$")
DETECTED = frozenset({"killed", "timeout", "caught by type check", "segfault"})
UNDETECTED = frozenset({"survived", "no tests"})
MAX_SHOWN_MUTANTS = 20
Function = ast.FunctionDef | ast.AsyncFunctionDef


def _git(*args: str) -> str:
    return subprocess.run(  # noqa: S603 - fixed git argv
        ["git", *args],  # noqa: S607 - git from PATH
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    ).stdout


def changed_lines(diff: str) -> dict[str, set[int]]:
    """Reads a zero-context diff into the added line numbers of each file.

    Args:
        diff: Output of ``git diff -U0``.

    Returns:
        Lines of the new version that the diff adds or changes, by file path.
    """
    lines: dict[str, set[int]] = {}
    path: str | None = None
    in_header = False  # "+++ b/<path>" appears only between "diff --git" and the first hunk
    for line in diff.splitlines():
        if line.startswith("diff --git "):
            in_header, path = True, None
        elif in_header and line.startswith("+++ "):
            name = line[4:].rstrip("\t")
            path = None if name == "/dev/null" else name.removeprefix("b/")
        elif line.startswith("@@"):
            in_header = False
            hunk = HUNK.match(line)
            if hunk and path is not None:
                start, count = int(hunk.group(1)), int(hunk.group(2) or "1")
                lines.setdefault(path, set()).update(range(start, start + count))
    return lines


def module_name(path: str, source: str) -> str | None:
    """Turns a file path into the module name mutmut uses, or None outside the source folder."""
    if PurePosixPath(path).suffix != ".py" or not path.startswith(source.rstrip("/") + "/"):
        return None
    names = list(PurePosixPath(path).with_suffix("").parts)
    if names and names[0] == "src":
        names = names[1:]
    if names and names[-1] == "__init__":
        names = names[:-1]
    return ".".join(names) or None


def _touches(node: Function, lines: set[int]) -> bool:
    first = min([node.lineno, *(decorator.lineno for decorator in node.decorator_list)])
    return bool(lines.intersection(range(first, (node.end_lineno or node.lineno) + 1)))


def changed_functions(source_text: str, lines: set[int]) -> list[str]:
    """Names, in mutmut's form, the functions and methods that contain a changed line.

    Args:
        source_text: The file's current content.
        lines: Changed line numbers in that file.

    Returns:
        ``x_<function>`` for top-level functions, ``x<sep><Class><sep><method>`` for methods.
    """
    found: list[str] = []
    for node in ast.parse(source_text).body:
        if isinstance(node, Function) and _touches(node, lines):
            found.append(f"x_{node.name}")
        elif isinstance(node, ast.ClassDef):
            methods = [member for member in node.body if isinstance(member, Function)]
            found.extend(
                f"x{METHOD_SEPARATOR}{node.name}{METHOD_SEPARATOR}{method.name}"
                for method in methods
                if _touches(method, lines)
            )
    return found


def mutant_globs(lines_by_file: dict[str, set[int]], source: str, root: Path) -> list[str]:
    """Builds the mutant name patterns that cover the changed functions and methods."""
    globs: list[str] = []
    for path, lines in sorted(lines_by_file.items()):
        module = module_name(path, source)
        if module is None or not (root / path).is_file():
            continue
        text = (root / path).read_text(encoding="utf-8")
        globs.extend(f"{module}.{name}__mutmut_*" for name in changed_functions(text, lines))
    return globs


def parse_results(output: str, globs: list[str]) -> dict[str, str]:
    """Reads ``mutmut results --all true`` and keeps the mutants that match the patterns."""
    statuses: dict[str, str] = {}
    for line in output.splitlines():
        match = RESULT_LINE.match(line)
        if match and any(fnmatchcase(match["name"], pattern) for pattern in globs):
            statuses[match["name"]] = match["status"].strip()
    return statuses


def mutation_score(statuses: dict[str, str]) -> tuple[float | None, list[str]]:
    """Scores the mutants: detected over detected plus undetected, as Stryker does.

    Returns:
        The score from 0 to 100 (None when no mutant counts) and the undetected mutants' names.
    """
    detected = [name for name, status in statuses.items() if status in DETECTED]
    undetected = sorted(name for name, status in statuses.items() if status in UNDETECTED)
    counted = len(detected) + len(undetected)
    return (100 * len(detected) / counted if counted else None), undetected


def _mutmut(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - this interpreter runs mutmut with fixed arguments
        [sys.executable, "-m", "mutmut", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def _report(score: float, minimum: float, undetected: list[str]) -> None:
    print(f"Mutation score of the changed code: {score:.1f} % (minimum {minimum:.0f} %).")
    for name in undetected[:MAX_SHOWN_MUTANTS]:
        print(_mutmut("show", name).stdout)
    if len(undetected) > MAX_SHOWN_MUTANTS:
        print(f"… and {len(undetected) - MAX_SHOWN_MUTANTS} more surviving mutants.")


def main(argv: list[str]) -> int:
    """Runs the gate: 0 on pass, 1 when the score is too low, 2 when mutmut cannot run."""
    parser = argparse.ArgumentParser(description=DESCRIPTION)
    parser.add_argument("--base", required=True, help="revision the pull request merges into")
    parser.add_argument("--source", default="src", help="folder mutmut mutates (default: src)")
    parser.add_argument("--min-score", type=float, default=100.0, help="lowest passing score")
    arguments = parser.parse_args(argv)

    merge_base = _git("merge-base", arguments.base, "HEAD").strip()
    diff = _git("diff", "-U0", "--no-color", "--diff-filter=AM", merge_base, "--", "*.py")
    globs = mutant_globs(changed_lines(diff), arguments.source, Path.cwd())
    if not globs:
        print("No changed functions under the source folder: nothing to mutate.")
        return 0
    run = _mutmut("run", *globs)
    if run.returncode != 0:
        print(run.stdout[-4000:], run.stderr[-4000:], sep="\n", file=sys.stderr)
        return 2
    results = _mutmut("results", "--all", "true").stdout
    score, undetected = mutation_score(parse_results(results, globs))
    if score is None:
        print("mutmut produced no mutants for the changed functions.")
        return 0
    _report(score, arguments.min_score, undetected)
    return 0 if score >= arguments.min_score else 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main(sys.argv[1:]))
