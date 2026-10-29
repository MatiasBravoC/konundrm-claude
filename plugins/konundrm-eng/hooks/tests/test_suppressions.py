"""Unit tests for hooks/scripts/suppressions.py."""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import suppressions
from working_tree import AddedLine

STANDARDS = Path(__file__).resolve().parents[2] / "skills" / "engineering-standards" / "SKILL.md"


def _documented(line_prefix: str) -> list[str]:
    for line in STANDARDS.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith(line_prefix):
            return re.findall(r"`([^`]+)`", line)
    raise AssertionError(f"No line starting with {line_prefix!r} in {STANDARDS}")


def markers(path: str, *texts: str) -> list[str]:
    lines = [AddedLine(path, number, text) for number, text in enumerate(texts, start=1)]
    return [found.marker for found in suppressions.find_unjustified(lines)]


class StandardsSyncTest(unittest.TestCase):
    def test_silencers_match_the_engineering_standards(self) -> None:
        self.assertEqual(_documented("- Silencers:"), [marker.name for marker in suppressions.SILENCERS])

    def test_skipped_tests_match_the_engineering_standards(self) -> None:
        self.assertEqual(_documented("- Skipped tests:"), [marker.name for marker in suppressions.SKIPPED_TESTS])

    def test_focused_tests_match_the_engineering_standards(self) -> None:
        self.assertEqual(_documented("- Focused tests"), [marker.name for marker in suppressions.FOCUSED_TESTS])


class PythonSilencersTest(unittest.TestCase):
    def test_flags_directives_without_a_reason(self) -> None:
        for line, marker in (
            ("x = f()  # noqa", "# noqa"),
            ("x = f()  # noqa: E501", "# noqa"),
            ("x = f()  # noqa:E501,W291", "# noqa"),
            ("# ruff: noqa: F401", "# ruff: noqa"),
            ("y = g()  # type: ignore", "# type: ignore"),
            ("y = g()  # type: ignore[arg-type]", "# type: ignore"),
            ("y = g()  # pyright: ignore[reportGeneralTypeIssues]", "# pyright: ignore"),
            ("z = h()  # pylint: disable=broad-except", "# pylint: disable"),
            ("run(cmd)  # nosec B603", "# nosec"),
            ("if debug:  # pragma: no cover", "# pragma: no cover"),
            ("if x:  # pragma: no branch", "# pragma: no branch"),
            ("total = a + b  # pragma: no mutate", "# pragma: no mutate"),
        ):
            with self.subTest(line=line):
                self.assertEqual(markers("src/a.py", line), [marker])

    def test_accepts_directives_with_a_reason_on_the_same_line(self) -> None:
        for line in (
            "run(argv)  # noqa: S603 - fixed argv, no user input",
            "x = f()  # noqa: E501 -- the URL cannot be split",
            "y = g()  # type: ignore[attr-defined]  # stub lacks this attribute",
            "if debug:  # pragma: no cover  # defensive: guarded by the caller",
            "total = a + b  # pragma: no mutate  # equivalent: both orders give the same sum",
            "z = h()  # pylint: disable=broad-except  # last-resort handler logs and re-raises",
        ):
            with self.subTest(line=line):
                self.assertEqual(markers("src/a.py", line), [])

    def test_a_second_directive_is_not_the_reason_for_the_first(self) -> None:
        self.assertEqual(
            markers("src/a.py", "y = g()  # type: ignore[misc]  # noqa: E501"), ["# noqa", "# type: ignore"]
        )

    def test_ignores_markers_inside_string_literals(self) -> None:
        for line in ('PATTERN = "# noqa"', "text = 'skip with # type: ignore'", 'msg = f"use # noqa: {code}"'):
            with self.subTest(line=line):
                self.assertEqual(markers("src/a.py", line), [])

    def test_python_markers_do_not_apply_to_other_languages(self) -> None:
        self.assertEqual(markers("src/a.ts", "const x = 1;  # noqa"), [])


class JavaScriptSilencersTest(unittest.TestCase):
    def test_eslint_needs_its_description_after_two_dashes(self) -> None:
        self.assertEqual(markers("src/a.ts", "// eslint-disable-next-line no-console"), ["eslint-disable"])
        self.assertEqual(markers("src/a.ts", "/* eslint-disable */"), ["eslint-disable"])
        self.assertEqual(markers("src/a.ts", "// eslint-disable-next-line no-console because"), ["eslint-disable"])
        self.assertEqual(markers("src/a.ts", "// eslint-disable-next-line no-console -- CLI output by design"), [])

    def test_typescript_and_coverage_directives_need_words(self) -> None:
        for line, marker in (
            ("// @ts-ignore", "@ts-ignore"),
            ("// @ts-expect-error", "@ts-expect-error"),
            ("// @ts-nocheck", "@ts-nocheck"),
            ("/* istanbul ignore next */", "istanbul ignore"),
            ("/* c8 ignore next 3 */", "c8 ignore"),
            ("/* v8 ignore start */", "v8 ignore"),
            ("// Stryker disable next-line all", "Stryker disable"),
        ):
            with self.subTest(line=line):
                self.assertEqual(markers("src/a.ts", line), [marker])
        for line in (
            "// @ts-expect-error the library ships no types",
            "/* istanbul ignore next -- platform specific branch */",
            "// Stryker disable next-line EqualityOperator: equivalent mutant",
        ):
            with self.subTest(line=line):
                self.assertEqual(markers("src/a.ts", line), [])

    def test_prose_that_mentions_a_directive_is_not_one(self) -> None:
        for line in (
            "// Standards: an eslint-disable that no longer silences anything is an error.",
            "/* Never use @ts-ignore here: fix the types. */",
            "// Coverage tools such as istanbul ignore nothing on this line.",
        ):
            with self.subTest(line=line):
                self.assertEqual(markers("src/a.ts", line), [])

    def test_nolint_and_nosonar(self) -> None:
        self.assertEqual(markers("cmd/a.go", "x := f() //nolint:errcheck"), ["//nolint"])
        self.assertEqual(markers("cmd/a.go", "x := f() //nolint:errcheck // close error is irrelevant here"), [])
        self.assertEqual(markers("src/A.java", "int x = y; // NOSONAR"), ["NOSONAR"])


class TestMarkersTest(unittest.TestCase):
    def test_flags_skips_without_a_reason_in_test_files(self) -> None:
        for path, line, marker in (
            ("tests/test_a.py", "@pytest.mark.skip", "@pytest.mark.skip"),
            ("tests/test_a.py", "@pytest.mark.skip()", "@pytest.mark.skip"),
            ("tests/test_a.py", "@pytest.mark.xfail", "@pytest.mark.xfail"),
            ("tests/test_a.py", "    pytest.skip()", "pytest.skip("),
            ("tests/test_a.py", "@unittest.expectedFailure", "@unittest.expectedFailure"),
            ("src/a.test.ts", 'it.skip("adds", () => {', "it.skip("),
            ("src/a.test.ts", 'xdescribe("cart", () => {', "xdescribe("),
        ):
            with self.subTest(line=line):
                self.assertEqual(markers(path, line), [marker])

    def test_accepts_skips_that_say_why(self) -> None:
        for path, line in (
            ("tests/test_a.py", '@pytest.mark.skip(reason="needs the payments sandbox")'),
            ("tests/test_a.py", '@pytest.mark.skipif(sys.version_info < (3, 11), reason="tomllib is new in 3.11")'),
            ("tests/test_a.py", '    pytest.skip("needs a network connection")'),
            ("tests/test_a.py", '@unittest.skipIf(os.name == "nt", "symlinks need admin rights on Windows")'),
            ("tests/test_a.py", "@unittest.expectedFailure  # upstream bug, see issue 42"),
            ("src/a.test.ts", 'it.skip("adds", () => { // flaky upstream API, see issue 42'),
        ):
            with self.subTest(line=line):
                self.assertEqual(markers(path, line), [])

    def test_focused_tests_are_never_justified(self) -> None:
        for line, marker in (
            ('it.only("adds", () => { // just this one', "it.only("),
            ('test.only("adds", () => {', "test.only("),
            ('describe.only("cart", () => {', "describe.only("),
            ('fit("adds", () => {', "fit("),
            ('fdescribe("cart", () => {', "fdescribe("),
        ):
            with self.subTest(line=line):
                self.assertEqual(markers("src/__tests__/cart.ts", line), [marker])

    def test_test_markers_count_only_as_code_in_test_files(self) -> None:
        self.assertEqual(markers("src/model.ts", "export function fit(width: number) {"), [])
        self.assertEqual(markers("src/a.test.ts", "// remember: it.only( focuses a test"), [])
        self.assertEqual(markers("src/a.test.ts", "model.fit(data);"), [])


class FindUnjustifiedTest(unittest.TestCase):
    def test_skips_documentation_and_tool_artifacts(self) -> None:
        self.assertEqual(markers("README.md", "Use `# noqa` sparingly"), [])
        self.assertEqual(markers("node_modules/x/index.ts", "// @ts-ignore"), [])

    def test_reports_path_line_and_a_shortened_line(self) -> None:
        found = suppressions.find_unjustified([AddedLine("src/a.py", 7, "    x = f()  # noqa" + " " * 200)])
        self.assertEqual((found[0].path, found[0].line, found[0].marker), ("src/a.py", 7, "# noqa"))
        self.assertLessEqual(len(found[0].text), suppressions.MAX_SHOWN_CHARACTERS)

    def test_describe_lists_and_summarises(self) -> None:
        found = [suppressions.Suppression("src/a.py", n, "# noqa", "x  # noqa") for n in range(1, 13)]
        text = suppressions.describe(found, limit=10)
        self.assertIn("src/a.py:1 `# noqa`", text)
        self.assertIn("… and 2 more", text)


if __name__ == "__main__":
    unittest.main()
