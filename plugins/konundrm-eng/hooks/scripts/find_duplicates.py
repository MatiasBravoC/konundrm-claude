"""Finds copy-pasted code: runs of lines that appear, normalized, in more than one place.

Published data (GitClear) shows AI-assisted code adds copy-pasted blocks while refactoring drops.
designing-modules and the code-reviewer agent run this script for deterministic evidence instead of
looking for duplicates by reading. From the project directory:

    sh "${CLAUDE_PLUGIN_ROOT}/hooks/run.sh" find_duplicates.py [--all | --base REV] [--min-lines N]
        [--include-tests] [paths...]

Lines are compared after normalize(), so formatting, comments and imports never count. A window of
--min-lines consecutive kept lines that also occurs elsewhere (in another file, or in a part of the
same file it does not overlap) grows into the longest run of equal lines: a block. Each copy is
reported once, against the first other copy in path order, so a block pasted into ten files gives
nine report lines, not forty-five. By default only blocks that include a line added since --base
count, whether staged, unstaged or untracked; --all reports every block in the project.

Sections:
    SOURCE_SUFFIXES, is_candidate(), list_candidates() — which files are compared.
    normalize()                — the lines that count, with their original line numbers.
    SourceFile, read_sources() — reads and normalizes every candidate once.
    Block, find_blocks()       — the duplicated blocks in the files reported on.
    format_report(), main()    — CLI: exit 0 when clean, 1 with duplicates, 2 on usage errors.
"""

from __future__ import annotations

import argparse
import os
import re
import stat
import sys
from collections import Counter, defaultdict
from collections.abc import Container, Iterable, Iterator, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path, PurePosixPath

from file_kinds import is_test_path, is_tool_artifact
from project_paths import project_root, relative_path
from working_tree import AddedLine, added_lines, head_tree, run_git, snapshot_tree

DEFAULT_MIN_LINES = 6
MAX_FILE_BYTES = 512 * 1024
READ_THREADS = 8

SOURCE_SUFFIXES = frozenset(
    {".py", ".pyi", ".rb", ".php", ".sh", ".sql"}
    | {".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".vue", ".svelte"}
    | {".go", ".rs", ".java", ".kt", ".kts", ".scala", ".swift", ".cs", ".c", ".h", ".cc", ".cpp", ".hpp"}
)
# Lockfiles are generated. Most have no source suffix (package-lock.json, poetry.lock, go.sum) and
# never get this far; Yarn's Plug'n'Play map is JavaScript.
LOCK_FILE_NAMES = frozenset({".pnp.cjs", ".pnp.js", ".pnp.loader.mjs"})
MINIFIED_FILE = "*.min.*"

COMMENT_MARKERS = ("#", "//", "/*", "*", "--", "<!--")
BLOCK_COMMENTS = (("/*", "*/"), ("<!--", "-->"))
LETTER_OR_DIGIT = re.compile(r"[^\W_]")
# Keywords that say nothing alone on a line, written without spaces ("} else {" is "}else{").
TRIVIAL_LINES = frozenset(
    {"pass", "return", "return;", "break", "break;", "continue", "continue;"}
    | {"else", "else:", "else{", "}else{", "try:", "try{", "finally:", "finally{", "}finally{"}
    | {"end", "then", "do", "done", "fi", "esac"}  # Ruby and shell
)
TRIVIAL_LINE_MAX_LENGTH = max(map(len, TRIVIAL_LINES)) + 2  # with its spaces back: "} else {"
# Duplicated import blocks are noise. Matched at the start of a whitespace-collapsed line.
IMPORT_LINE = re.compile(
    r"""
    import\b                                                         # Python, JavaScript, Go, Java, Swift
    | from\s+\S+\s+import\b                                          # Python
    | export\s+(?:type\s+)?[*{]                                      # JavaScript re-exports
    | \}\s*from\s                                                    # end of a multi-line import or export
    | (?:(?:const|let|var)\s+[^=]+=\s*)?require(?:_relative|_once)?\b  # CommonJS, Ruby, PHP
    | include(?:_once)?\b                                            # PHP, Ruby
    | (?:pub(?:\([^)]*\))?\s+)?use\s+[\w\\:{]                        # Rust, PHP
    | extern\s+crate\s                                               # Rust
    | (?:global\s+)?using\s+(?:static\s+|namespace\s+)?[\w.:]+\s*[;=]  # C#, C++
    """,
    re.VERBOSE,
)

Location = tuple[int, int]  # (position in the list of sources, index of a kept line in that file)


def is_candidate(path: str, include_tests: bool = False) -> bool:
    """Tells whether a project file is source code worth comparing.

    Args:
        path: Path relative to the project root, with forward slashes.
        include_tests: Whether test code (file_kinds.is_test_path()) counts too.

    Returns:
        True for a file with a source suffix that is not a lockfile, a minified file or a tool
        artifact, nor test code unless include_tests is set.
    """
    name = PurePosixPath(path).name.lower()
    if PurePosixPath(name).suffix not in SOURCE_SUFFIXES or name in LOCK_FILE_NAMES:
        return False
    if fnmatchcase(name, MINIFIED_FILE) or is_tool_artifact(path):
        return False
    return include_tests or not is_test_path(path)


def _bracket_balance(line: str) -> int:
    return sum(map(line.count, "([{")) - sum(map(line.count, ")]}"))


def _comment_closer(line: str) -> str:
    """Returns what ends the block comment a comment line opens; empty when nothing stays open."""
    for opener, closer in BLOCK_COMMENTS:
        if line.startswith(opener):
            return "" if closer in line[len(opener) :] else closer
    return ""


def _is_filler(line: str) -> bool:
    """Tells whether a line carries no logic of its own: no letter or digit, or a lone keyword."""
    if not line[0].isalnum() and not LETTER_OR_DIGIT.search(line):  # most lines pass the first, fast test
        return True
    return len(line) <= TRIVIAL_LINE_MAX_LENGTH and line.replace(" ", "") in TRIVIAL_LINES


def normalize(text: str) -> list[tuple[int, str]]:
    """Picks the lines of a file that count toward duplication.

    Leaves out blank lines, comments (a block comment up to its end), lines without a letter or
    digit (closing brackets and the like), lone trivial keywords (``pass``, ``return``,
    ``} else {``) and imports, including the rest of a multi-line import list. Only newlines split
    lines, as in Git, so the numbers match its diffs even when a form feed sits inside a line.

    Args:
        text: File content.

    Returns:
        ``(line number, text)`` for each kept line: the 1-based number in the file, and the line
        stripped, with each inner run of whitespace collapsed to one space.
    """
    kept: list[tuple[int, str]] = []
    comment_closer = ""  # end marker of the block comment being skipped
    open_brackets = 0  # brackets still open in a multi-line import
    for number, raw in enumerate(text.split("\n"), start=1):
        line = " ".join(raw.split())
        if not line:
            continue
        if comment_closer:
            comment_closer = "" if comment_closer in line else comment_closer
        elif open_brackets:
            open_brackets = max(0, open_brackets + _bracket_balance(line))
        elif line.startswith(COMMENT_MARKERS):
            comment_closer = _comment_closer(line)
        elif IMPORT_LINE.match(line):
            open_brackets = max(0, _bracket_balance(line))
        elif not _is_filler(line):
            kept.append((number, line))
    return kept


@dataclass(frozen=True)
class SourceFile:
    """A candidate file reduced to the lines that count toward duplication.

    Attributes:
        path: Path relative to the project root, with forward slashes.
        numbers: The original 1-based line number of each kept line.
        texts: The normalized text of each kept line.
    """

    path: str
    numbers: list[int]
    texts: list[str]

    @classmethod
    def from_text(cls, path: str, text: str) -> SourceFile:
        """Builds the SourceFile of a file's content (see normalize())."""
        kept = normalize(text)
        return cls(path, [number for number, _ in kept], [line for _, line in kept])


def _comparable_content(location: Path) -> bytes | None:
    try:
        status = location.lstat()
        # A symbolic link would repeat its target; a folder here is a submodule.
        if not stat.S_ISREG(status.st_mode) or status.st_size > MAX_FILE_BYTES:
            return None
        data = location.read_bytes()
    except OSError:  # deleted since Git listed it, or unreadable
        return None
    return None if b"\0" in data else data  # a NUL byte means binary


def read_sources(root: Path, paths: Iterable[str]) -> list[SourceFile]:
    """Reads and normalizes each file once, skipping the ones that cannot be compared.

    Skipped: files that are gone or unreadable, anything but a regular file, files over
    MAX_FILE_BYTES and binary files (with a NUL byte).

    Args:
        root: Project root.
        paths: Candidate paths relative to the root (list_candidates()).

    Returns:
        A SourceFile per readable candidate, in the order given.
    """
    paths = list(paths)
    sources: list[SourceFile] = []
    # Opening a file costs a tenth of a millisecond on Windows: threads overlap the waits while
    # this one normalizes the files already read, in order.
    with ThreadPoolExecutor(max_workers=READ_THREADS) as pool:
        for path, data in zip(paths, pool.map(_comparable_content, [root / path for path in paths]), strict=True):
            if data is not None:
                sources.append(SourceFile.from_text(path, data.decode("utf-8", errors="replace")))
    return sources


@dataclass(frozen=True, order=True)
class Block:
    """A run of lines that also appears, normalized, somewhere else; ordered by path and line.

    Attributes:
        path: File the block is reported in, relative to the project root.
        start: The block's first line in that file, 1-based.
        end: The block's last line.
        other_path: File that holds the other copy.
        other_start: First line of the other copy.
        other_end: Last line of the other copy.
        lines: How many lines match, both copies alike, not counting the blank, comment and other
            ignored lines between them.
    """

    path: str
    start: int
    end: int
    other_path: str
    other_start: int
    other_end: int
    lines: int

    def __str__(self) -> str:
        return (
            f"{self.path}:{self.start}-{self.end} duplicates "
            f"{self.other_path}:{self.other_start}-{self.other_end} ({self.lines} lines)"
        )


class _WindowIndex:
    """Where each window of ``size`` consecutive kept lines occurs across the sources."""

    def __init__(self, sources: Sequence[SourceFile], size: int) -> None:
        self.sources = sources
        self.size = size
        counts: Counter[str] = Counter()
        for source in sources:
            counts.update(source.texts)
        self.keys = [self._window_keys(source.texts, counts) for source in sources]
        self.locations: defaultdict[int, list[Location]] = defaultdict(list)
        for file_index, keys in enumerate(self.keys):
            for start, key in enumerate(keys):
                if key is not None:
                    self.locations[key].append((file_index, start))

    def _window_keys(self, texts: list[str], counts: Counter[str]) -> list[int | None]:
        """Hashes each window of a file, by start.

        A window gets None when no copy can match it, because one of its lines occurs nowhere else
        in the project, or when it only repeats one line (a table of identical rows is not a copy).
        """
        keys: list[int | None] = []
        shared = 0  # lines in a row, up to this one, that occur more than once in the project
        same = 0  # lines in a row, up to this one, equal to it
        previous: str | None = None
        for end, text in enumerate(texts, start=1):
            shared = shared + 1 if counts[text] > 1 else 0
            same = same + 1 if text == previous else 1
            previous = text
            if end >= self.size:
                keys.append(hash(tuple(texts[end - self.size : end])) if shared >= self.size > same else None)
        return keys

    def includes_added(self, file_index: int, start: int, length: int, added: Container[int] | None) -> bool:
        """Tells whether kept lines ``start`` to ``start + length`` include an added line."""
        numbers = self.sources[file_index].numbers
        return added is None or any(numbers[line] in added for line in range(start, start + length))

    def first_other_copy(self, key: int, here: Location) -> Location | None:
        """Finds the first other place, in source order, that holds the window at ``here``."""
        file_index, start = here
        window = self.sources[file_index].texts[start : start + self.size]
        for other_file, other_start in self.locations[key]:
            if other_file == file_index and abs(other_start - start) < self.size:
                continue  # the window itself, or one that overlaps it
            if self.sources[other_file].texts[other_start : other_start + self.size] == window:  # not a collision
                return other_file, other_start
        return None

    def grow(self, here: Location, other: Location) -> tuple[int, int, int]:
        """Extends two matching windows into the longest run of equal lines around them.

        Returns:
            The run's start at ``here``, its start at ``other`` and its length, in kept lines.
        """
        first, second = self.sources[here[0]].texts, self.sources[other[0]].texts
        start, other_start = here[1], other[1]
        length = self.size
        while min(start, other_start) > 0 and first[start - 1] == second[other_start - 1]:
            start, other_start, length = start - 1, other_start - 1, length + 1
        while (
            start + length < len(first)
            and other_start + length < len(second)
            and first[start + length] == second[other_start + length]
        ):
            length += 1
        return start, other_start, length

    def copies_in(self, file_index: int, added: Container[int] | None) -> Iterator[tuple[int, Location, int]]:
        """Yields one file's duplicated blocks as ``(start, other copy's location, length)``.

        Args:
            file_index: Position of the file in the sources.
            added: Line numbers of which a block must include one (the lines a change added), or
                None to yield every block.
        """
        grown: dict[tuple[int, int], int] = {}  # (other file, offset) -> end of the run grown there
        resume = 0  # end of the last block yielded: the windows inside it are reported already
        for start, key in enumerate(self.keys[file_index]):
            # A block with an added line holds a window with that line, so only those need growing.
            if key is None or start < resume or not self.includes_added(file_index, start, self.size, added):
                continue
            other = self.first_other_copy(key, (file_index, start))
            if other is None or start < grown.get((other[0], other[1] - start), 0):
                continue
            first, other_start, length = self.grow((file_index, start), other)
            grown[(other[0], other[1] - start)] = first + length
            end = first + length
            if other[0] == file_index and length > abs(other_start - first):
                # The copies run into each other: a stretch repeated back to back. Report its first
                # repeat and, once reported, skip the rest of the stretch.
                end, length = max(first, other_start) + length, abs(other_start - first)
            if self.includes_added(file_index, first, length, added):
                resume = end
                yield first, (other[0], other_start), length


def _block(source: SourceFile, start: int, other: SourceFile, other_start: int, length: int) -> Block:
    return Block(
        source.path,
        source.numbers[start],
        source.numbers[start + length - 1],
        other.path,
        other.numbers[other_start],
        other.numbers[other_start + length - 1],
        length,
    )


def find_blocks(
    sources: Sequence[SourceFile], min_lines: int, report_on: Mapping[str, Container[int] | None]
) -> list[Block]:
    """Finds the duplicated blocks in the files to report on.

    Copies anywhere in the sources count, but only blocks in a file of ``report_on`` are reported.
    Each is reported once, against the first other copy in source order, and a pair of copies that
    both qualify appears once.

    Args:
        sources: Every candidate file, normalized, in path order (read_sources()).
        min_lines: The fewest kept lines a block may have.
        report_on: For each file to report on, the line numbers of which a block must include one
            (the lines a change added), or None to report every block in it.

    Returns:
        The blocks, ordered by path and line.
    """
    index = _WindowIndex(sources, min_lines)
    found: dict[tuple[Location, Location, int], Block] = {}
    for file_index, source in enumerate(sources):
        if source.path not in report_on:
            continue
        for start, other, length in index.copies_in(file_index, report_on[source.path]):
            here = (file_index, start)
            pair = (min(here, other), max(here, other), length)
            if pair not in found:
                found[pair] = _block(source, start, sources[other[0]], other[1], length)
    return sorted(found.values())


def list_candidates(root: Path, include_tests: bool = False) -> list[str] | None:
    """Lists the project's tracked and untracked, non-ignored files that is_candidate() accepts.

    Args:
        root: Project root inside a Git repository.
        include_tests: Whether test files count too.

    Returns:
        Paths relative to the root, sorted; None outside a Git repository.
    """
    output = run_git(["ls-files", "--cached", "--others", "--exclude-standard", "-z"], root)
    if output is None:
        return None
    paths = set(output.decode("utf-8", errors="replace").split("\0"))  # a conflicted file is listed per stage
    return sorted(path for path in paths if path and is_candidate(path, include_tests))


class _UsageError(Exception):
    """A command-line or repository problem, reported on stderr with exit code 2."""


def _base_tree(root: Path, base: str) -> str | None:
    if base == "HEAD":
        return head_tree(root)  # the empty tree before the first commit
    output = run_git(["rev-parse", "--verify", "--quiet", f"{base}^{{tree}}"], root)
    if output is None:
        return None
    return output.decode("ascii", errors="replace").strip() or None


def _lines_by_path(lines: Iterable[AddedLine]) -> dict[str, set[int]]:
    numbers: dict[str, set[int]] = {}
    for line in lines:
        numbers.setdefault(line.path, set()).add(line.number)
    return numbers


def _changed_lines(root: Path, base: str) -> dict[str, set[int]]:
    """Maps each file with lines added since ``base`` (staged, unstaged or untracked) to them."""
    before = _base_tree(root, base)
    if before is None:
        raise _UsageError(f"{base!r} is not a revision of this repository.")
    after = snapshot_tree(root)
    if after is None:
        raise _UsageError("Git could not snapshot the working tree.")
    return _lines_by_path(added_lines(root, before, after))


def _project_path(path: str, root: Path) -> str:
    """Turns a command-line path, relative to the current directory, into a project-relative one."""
    absolute = Path.cwd() / path
    relative = relative_path(str(absolute), root)
    if relative is None:
        raise _UsageError(f"{path} is outside the project ({root}).")
    if not absolute.exists():
        raise _UsageError(f"{path} does not exist.")
    return relative


def _is_selected(path: str, selected: list[str]) -> bool:
    return not selected or any(choice in (".", path) or path.startswith(f"{choice}/") for choice in selected)


def _find(root: Path, arguments: argparse.Namespace) -> list[Block]:
    selected = [_project_path(path, root) for path in arguments.paths]
    candidates = list_candidates(root, arguments.include_tests)
    if candidates is None:
        raise _UsageError(f"{root} is not inside a Git repository.")
    report_on: Mapping[str, Container[int] | None]
    if arguments.all:
        report_on = dict.fromkeys(candidates)
    else:
        changed = _changed_lines(root, arguments.base)
        report_on = {path: changed[path] for path in candidates if path in changed}
    report_on = {path: lines for path, lines in report_on.items() if _is_selected(path, selected)}
    if not report_on:
        return []  # nothing to report on, so no need to read the project
    return find_blocks(read_sources(root, candidates), arguments.min_lines, report_on)


def format_report(blocks: Sequence[Block], min_lines: int, scope: str) -> str:
    """Formats the report: one line per block, then a summary line.

    Args:
        blocks: The blocks, in report order (find_blocks()).
        min_lines: The smallest block searched for.
        scope: What was searched, as the summary names it: "the changed code" or "the project".
    """
    if not blocks:
        return f"No duplicated blocks of {min_lines}+ lines in {scope}.\n"
    noun = "block" if len(blocks) == 1 else "blocks"
    summary = f"Found {len(blocks)} duplicated {noun} of {min_lines}+ lines in {scope}."
    return "\n".join([*map(str, blocks), summary]) + "\n"


def _parse_arguments(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="find_duplicates.py",
        description="Reports blocks of code that also appear elsewhere in the project; by default only "
        "blocks that include a line added since --base. Exits 0 when there are none, 1 when there "
        "are, 2 on a usage error.",
    )
    parser.add_argument("paths", nargs="*", help="report only on these files or folders")
    parser.add_argument(
        "--min-lines",
        type=int,
        default=DEFAULT_MIN_LINES,
        metavar="N",
        help=f"smallest block to report, in lines that count (default {DEFAULT_MIN_LINES})",
    )
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument("--base", default="HEAD", metavar="REV", help="revision to compare with (default HEAD)")
    scope.add_argument("--all", action="store_true", help="report every duplicated block in the project")
    parser.add_argument("--include-tests", action="store_true", help="compare test files too")
    arguments = parser.parse_args(argv)
    if arguments.min_lines < 2:
        parser.error("--min-lines must be at least 2")
    if arguments.base.startswith("-"):
        parser.error(f"--base must name a revision, not {arguments.base!r}")
    return arguments


def main(argv: list[str] | None = None) -> int:
    """Prints the duplicated blocks of the changed code, or of the whole project with --all.

    Args:
        argv: Command-line arguments; defaults to sys.argv[1:].

    Returns:
        0 when there are none, 1 when there are, 2 on a usage error or outside a Git repository.
    """
    for stream in (sys.stdout, sys.stderr):  # Claude Code reads UTF-8; Windows pipes default to a code page
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    arguments = _parse_arguments(argv)
    root = project_root({"cwd": os.getcwd()})
    try:
        blocks = _find(root, arguments)
    except _UsageError as error:
        sys.stderr.write(f"find_duplicates.py: {error}\n")
        return 2
    sys.stdout.write(format_report(blocks, arguments.min_lines, "the project" if arguments.all else "the changed code"))
    return 1 if blocks else 0


if __name__ == "__main__":
    sys.exit(main())
