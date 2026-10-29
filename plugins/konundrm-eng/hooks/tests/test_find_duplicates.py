"""Unit tests for hooks/scripts/find_duplicates.py (the command tests run Git in temporary repositories)."""

from __future__ import annotations

import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import find_duplicates
from find_duplicates import SourceFile, find_blocks, is_candidate, normalize

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "find_duplicates.py"

COPIED = (  # nine lines, all of which count
    "def invoice_total(order, customer):\n"
    "    subtotal = sum(item.price * item.quantity for item in order.items)\n"
    "    if customer.is_member:\n"
    "        subtotal = subtotal * 0.9\n"
    "    shipping = 0 if subtotal > 50 else 4.99\n"
    "    tax = round(subtotal * 0.21, 2)\n"
    "    total = round(subtotal + shipping + tax, 2)\n"
    "    order.total = total\n"
    "    return total\n"
)
OTHER = (  # nine more, sharing no line with COPIED
    "def parse_header(line):\n"
    '    name, _, value = line.partition(":")\n'
    "    name = name.strip().lower()\n"
    "    value = value.strip()\n"
    "    if not name:\n"
    '        raise ValueError(f"no header name in {line!r}")\n'
    '    if name in ("content-length", "max-forwards"):\n'
    "        value = int(value)\n"
    "    return name, value\n"
)


def filler(tag: str, count: int) -> str:
    """Lines that occur nowhere else."""
    return "".join(f"{tag}_{number} = {number}\n" for number in range(count))


def git(root: Path, *args: str) -> None:
    command = ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args]
    subprocess.run(command, cwd=root, capture_output=True, check=True)


def run_main(root: Path, *args: str, cwd: Path | None = None) -> tuple[int, str, str]:
    """Runs the CLI in-process on the project at ``root``; returns its exit code, stdout and stderr."""
    stdout, stderr = io.StringIO(), io.StringIO()
    previous = os.getcwd()
    os.chdir(cwd or root)
    try:
        with (
            mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(root)}),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            code = find_duplicates.main(list(args))
    except SystemExit as exit_request:  # argparse rejects the command line
        code = int(exit_request.code or 0)
    finally:
        os.chdir(previous)
    return code, stdout.getvalue(), stderr.getvalue()


class NormalizeTest(unittest.TestCase):
    def test_collapses_whitespace_and_keeps_the_original_line_numbers(self) -> None:
        text = "\n  total  =\tprice *  2  \r\n\nreport(total)\n"
        self.assertEqual(normalize(text), [(2, "total = price * 2"), (4, "report(total)")])

    def test_drops_blank_comment_and_punctuation_only_lines(self) -> None:
        lines = [
            "x = 1",
            "",
            "# a comment",
            "// a comment",
            "/* a block comment",
            "   that goes on without stars",
            "*/",
            "/** a doc comment */",
            " * a starred line",
            "-- an SQL comment",
            "<!-- an HTML comment -->",
            "});",
            "]",
            "y = 2",
        ]
        self.assertEqual(normalize("\n".join(lines)), [(1, "x = 1"), (14, "y = 2")])

    def test_drops_lone_trivial_keywords_but_not_lines_that_carry_a_value(self) -> None:
        lines = ["pass", "return", "return;", "break", "continue", "else:", "try:", "finally:", "else {"]
        lines += ["} else {", "}else{", "end", "return total", "break_point = 1"]
        self.assertEqual([text for _, text in normalize("\n".join(lines))], ["return total", "break_point = 1"])

    def test_drops_imports_in_each_language_with_the_rest_of_multi_line_lists(self) -> None:
        lines = [
            "import os",
            "from package.module import (",
            "    first,",
            "    second,",
            ")",
            "import {",
            "  alpha,",
            "} from './letters';",
            "export { beta } from './beta';",
            "const fs = require('fs');",
            "import (",
            '    "fmt"',
            ")",
            "use std::collections::HashMap;",
            "using System.Linq;",
            "require_relative 'helper'",
            "important = imports_done",
        ]
        self.assertEqual(normalize("\n".join(lines)), [(17, "important = imports_done")])

    def test_counts_lines_as_git_does(self) -> None:
        # A form feed or a Unicode line separator inside a line is not a line break for Git.
        numbers = [number for number, _ in normalize("a = 1\x0c\nb = '\N{LINE SEPARATOR}'\nc = 3\n")]
        self.assertEqual(numbers, [1, 2, 3])


class IsCandidateTest(unittest.TestCase):
    def test_accepts_source_files(self) -> None:
        for path in ("src/app.py", "web/App.TSX", "cmd/main.go", "db/schema.sql", "scripts/run.sh"):
            with self.subTest(path=path):
                self.assertTrue(is_candidate(path))

    def test_rejects_other_files_lockfiles_minified_files_and_tool_artifacts(self) -> None:
        for path in ("README.md", "package-lock.json", ".pnp.cjs", "static/vendor.min.js", "node_modules/x/a.js"):
            with self.subTest(path=path):
                self.assertFalse(is_candidate(path))
        self.assertFalse(is_candidate("build/lib.py"))

    def test_counts_test_files_only_when_asked(self) -> None:
        self.assertFalse(is_candidate("tests/test_app.py"))
        self.assertTrue(is_candidate("tests/test_app.py", include_tests=True))


def blocks(*files: tuple[str, str], min_lines: int = 6, added: dict[str, set[int]] | None = None) -> list[str]:
    """Reports on in-memory files: every block, or with ``added`` only the blocks with added lines."""
    sources = [SourceFile.from_text(path, text) for path, text in sorted(files)]
    report_on = dict.fromkeys(path for path, _ in files) if added is None else added
    return [str(block) for block in find_blocks(sources, min_lines, report_on)]


class FindBlocksTest(unittest.TestCase):
    def test_finds_a_function_copied_into_another_file(self) -> None:
        found = blocks(("a.py", filler("a", 3) + COPIED), ("b.py", COPIED + filler("b", 2)))
        self.assertEqual(found, ["a.py:4-12 duplicates b.py:1-9 (9 lines)"])

    def test_ignores_a_copy_shorter_than_the_minimum(self) -> None:
        five = "".join(COPIED.splitlines(keepends=True)[:5])
        self.assertEqual(blocks(("a.py", five + filler("a", 2)), ("b.py", filler("b", 2) + five)), [])
        self.assertEqual(blocks(("a.py", COPIED), ("b.py", COPIED), min_lines=10), [])

    def test_merges_consecutive_windows_into_one_block(self) -> None:
        found = blocks(("a.py", COPIED + OTHER), ("b.py", filler("b", 1) + COPIED + OTHER))
        self.assertEqual(found, ["a.py:1-18 duplicates b.py:2-19 (18 lines)"])

    def test_line_ranges_span_the_ignored_lines_inside_a_copy(self) -> None:
        lines = COPIED.splitlines(keepends=True)
        commented = "".join([*lines[:3], "    # members get a discount\n", "\n", *lines[3:]])
        self.assertEqual(blocks(("a.py", COPIED), ("b.py", commented)), ["a.py:1-9 duplicates b.py:1-11 (9 lines)"])

    def test_overlapping_windows_in_one_file_are_not_duplicates(self) -> None:
        self.assertEqual(blocks(("a.py", "left = 1\nright = 2\n" * 5)), [])
        self.assertEqual(blocks(("a.py", "row = 0\n" * 20)), [])  # one line repeated is not a copy

    def test_finds_a_copy_elsewhere_in_the_same_file(self) -> None:
        found = blocks(("a.py", COPIED + filler("a", 3) + COPIED))
        self.assertEqual(found, ["a.py:1-9 duplicates a.py:13-21 (9 lines)"])

    def test_reports_a_stretch_of_back_to_back_copies_once(self) -> None:
        stanza = "".join(COPIED.splitlines(keepends=True)[:6])
        self.assertEqual(blocks(("a.py", stanza * 3)), ["a.py:1-6 duplicates a.py:7-12 (6 lines)"])

    def test_a_copy_appended_to_back_to_back_copies_is_reported_on_its_own(self) -> None:
        stanza = "".join(COPIED.splitlines(keepends=True)[:6])
        found = blocks(("a.py", stanza * 3), added={"a.py": set(range(13, 19))})
        self.assertEqual(found, ["a.py:13-18 duplicates a.py:1-6 (6 lines)"])

    def test_reports_each_copy_once_against_the_first_other_copy(self) -> None:
        found = blocks(("a.py", COPIED), ("b.py", COPIED), ("c.py", COPIED))
        self.assertEqual(found, ["a.py:1-9 duplicates b.py:1-9 (9 lines)", "c.py:1-9 duplicates a.py:1-9 (9 lines)"])

    def test_with_added_lines_reports_only_blocks_that_include_one(self) -> None:
        files = (("a.py", COPIED + filler("a", 2)), ("b.py", COPIED), ("c.py", filler("c", 1) + COPIED))
        self.assertEqual(blocks(*files, added={"c.py": set(range(1, 11))}), ["c.py:2-10 duplicates a.py:1-9 (9 lines)"])
        self.assertEqual(blocks(*files, added={"a.py": {10, 11}}), [])

    def test_two_new_copies_of_each_other_are_reported_once(self) -> None:
        found = blocks(("a.py", COPIED), ("b.py", COPIED), added={"a.py": set(range(1, 10)), "b.py": set(range(1, 10))})
        self.assertEqual(found, ["a.py:1-9 duplicates b.py:1-9 (9 lines)"])


@unittest.skipIf(shutil.which("git") is None, "Git is not installed")
class FindDuplicatesCommandTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        git(self.root, "init", "-q")

    def write(self, path: str, text: str) -> None:
        (self.root / path).parent.mkdir(parents=True, exist_ok=True)
        (self.root / path).write_text(text, encoding="utf-8")

    def commit(self) -> None:
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "change")

    def test_changed_code_ignores_earlier_duplication_and_reports_a_new_copy(self) -> None:
        self.write("a.py", filler("a", 3) + COPIED)
        self.write("b.py", COPIED + filler("b", 3))
        self.write("c.py", OTHER)
        self.commit()
        self.write("a.py", filler("a", 3) + COPIED + filler("new", 3))  # edited, but away from its copy
        self.write("d.py", filler("d", 2) + OTHER)
        code, out, _ = run_main(self.root)
        self.assertEqual(code, 1)
        self.assertEqual(
            out.splitlines(),
            ["d.py:3-11 duplicates c.py:1-9 (9 lines)", "Found 1 duplicated block of 6+ lines in the changed code."],
        )

    def test_all_reports_duplication_that_existed_before_the_change(self) -> None:
        self.write("a.py", filler("a", 3) + COPIED)
        self.write("b.py", COPIED + filler("b", 3))
        self.commit()
        self.assertEqual(run_main(self.root), (0, "No duplicated blocks of 6+ lines in the changed code.\n", ""))
        code, out, _ = run_main(self.root, "--all")
        self.assertEqual(code, 1)
        self.assertEqual(
            out.splitlines(),
            ["a.py:4-12 duplicates b.py:1-9 (9 lines)", "Found 1 duplicated block of 6+ lines in the project."],
        )

    def test_reports_staged_unstaged_and_untracked_copies(self) -> None:
        self.write("source.py", COPIED + filler("s", 2) + OTHER)
        self.write("tracked.py", filler("t", 2))
        self.commit()
        self.write("staged.py", COPIED)
        git(self.root, "add", "staged.py")
        self.write("tracked.py", filler("t", 2) + OTHER)
        self.write("untracked.py", filler("u", 1) + COPIED)
        code, out, _ = run_main(self.root)
        self.assertEqual(code, 1)
        self.assertEqual(
            out.splitlines()[:-1],
            [
                "staged.py:1-9 duplicates source.py:1-9 (9 lines)",
                "tracked.py:3-11 duplicates source.py:12-20 (9 lines)",
                "untracked.py:2-10 duplicates source.py:1-9 (9 lines)",
            ],
        )

    def test_base_compares_with_an_earlier_revision(self) -> None:
        self.write("a.py", COPIED)
        self.commit()
        self.write("b.py", filler("b", 1) + COPIED)
        self.commit()
        self.assertEqual(run_main(self.root)[0], 0)
        code, out, _ = run_main(self.root, "--base", "HEAD~1")
        self.assertEqual((code, out.splitlines()[0]), (1, "b.py:2-10 duplicates a.py:1-9 (9 lines)"))

    def test_before_the_first_commit_every_line_is_new(self) -> None:
        self.write("a.py", COPIED)
        self.write("b.py", COPIED)
        code, out, _ = run_main(self.root)
        self.assertEqual((code, out.splitlines()[0]), (1, "a.py:1-9 duplicates b.py:1-9 (9 lines)"))

    def test_skips_test_files_unless_asked(self) -> None:
        self.write("app.py", COPIED)
        self.write("tests/test_app.py", filler("t", 1) + COPIED)
        self.assertEqual(run_main(self.root, "--all"), (0, "No duplicated blocks of 6+ lines in the project.\n", ""))
        code, out, _ = run_main(self.root, "--all", "--include-tests")
        self.assertEqual((code, out.splitlines()[0]), (1, "app.py:1-9 duplicates tests/test_app.py:2-10 (9 lines)"))

    def test_skips_artifacts_lockfiles_minified_binary_and_large_files(self) -> None:
        self.write("app.py", COPIED)
        self.write("kept.py", COPIED)
        for skipped in ("node_modules/lib/copy.py", "build/copy.py", ".pnp.cjs", "vendor.min.js", "notes.md"):
            self.write(skipped, COPIED)
        (self.root / "binary.py").write_bytes(COPIED.encode() + b"\0")
        self.write("large.py", COPIED + filler("x", 40_000))  # over 512 KB
        code, out, _ = run_main(self.root, "--all")
        self.assertEqual(code, 1)
        self.assertEqual(
            out.splitlines(),
            ["app.py:1-9 duplicates kept.py:1-9 (9 lines)", "Found 1 duplicated block of 6+ lines in the project."],
        )

    def test_paths_restrict_the_report_to_those_files_or_folders(self) -> None:
        self.write("a.py", COPIED)
        self.write("src/b.py", COPIED)
        self.write("c.py", OTHER)
        self.write("src/d.py", OTHER)
        self.commit()
        code, out, _ = run_main(self.root, "--all", "src")
        self.assertEqual(code, 1)
        self.assertEqual(
            out.splitlines(),
            [
                "src/b.py:1-9 duplicates a.py:1-9 (9 lines)",
                "src/d.py:1-9 duplicates c.py:1-9 (9 lines)",
                "Found 2 duplicated blocks of 6+ lines in the project.",
            ],
        )
        code, out, _ = run_main(self.root, "--all", "c.py")
        self.assertEqual(out.splitlines()[:-1], ["c.py:1-9 duplicates src/d.py:1-9 (9 lines)"])
        code, out, _ = run_main(self.root, "--all", "d.py", cwd=self.root / "src")  # relative to where it runs
        self.assertEqual(out.splitlines()[:-1], ["src/d.py:1-9 duplicates c.py:1-9 (9 lines)"])

    def test_ignores_a_file_deleted_from_the_working_tree(self) -> None:
        self.write("a.py", COPIED)
        self.write("b.py", COPIED)
        self.commit()
        (self.root / "b.py").unlink()  # still in the index
        self.assertEqual(run_main(self.root, "--all"), (0, "No duplicated blocks of 6+ lines in the project.\n", ""))

    def test_usage_errors_exit_2_with_a_message(self) -> None:
        self.write("a.py", COPIED)
        self.commit()
        for args in (
            ["--base", "no-such-revision"],
            ["--min-lines", "1"],
            ["--min-lines", "six"],
            ["--all", "--base", "HEAD"],
            ["../outside.py"],
            ["missing.py"],
        ):
            with self.subTest(args=args):
                code, out, err = run_main(self.root, *args)
                self.assertEqual((code, out), (2, ""))
                self.assertTrue(err.strip())

    def test_outside_a_git_repository_exits_2(self) -> None:
        with tempfile.TemporaryDirectory() as plain:
            code, out, err = run_main(Path(plain), "--all")
        self.assertEqual((code, out), (2, ""))
        self.assertIn("not inside a Git repository", err)

    def test_runs_end_to_end_as_a_script(self) -> None:
        self.write("módulo.py", COPIED)
        self.write("b.py", COPIED)
        self.commit()
        env = {name: value for name, value in os.environ.items() if name != "CLAUDE_PROJECT_DIR"}

        def run(*args: str) -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                [sys.executable, str(SCRIPT), *args],
                cwd=self.root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                env=env,
                timeout=60,
            )

        found = run("--all")
        self.assertEqual(found.returncode, 1)
        self.assertEqual(
            found.stdout.splitlines(),
            ["b.py:1-9 duplicates módulo.py:1-9 (9 lines)", "Found 1 duplicated block of 6+ lines in the project."],
        )
        clean = run()
        self.assertEqual(clean.returncode, 0)
        self.assertEqual(clean.stdout, "No duplicated blocks of 6+ lines in the changed code.\n")


if __name__ == "__main__":
    unittest.main()
