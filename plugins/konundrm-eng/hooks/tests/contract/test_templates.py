"""Contract tests for the plugin's templates: what setup-project copies and what develop-feature fills in."""

from __future__ import annotations

import re
import shlex
import unittest
from pathlib import Path

from .plugin_files import SKILLS_DIR, read_section

CLAUDE_REVIEW_TEMPLATE = SKILLS_DIR / "setup-project" / "templates" / "claude-review.yml"
SLICE_SUMMARY_TEMPLATE = SKILLS_DIR / "develop-feature" / "templates" / "slice-summary.md"
FEATURE_SUMMARY_TEMPLATE = SKILLS_DIR / "develop-feature" / "templates" / "feature-summary.md"

# The header of a YAML literal block scalar under the `claude_args` key: `claude_args: |`, `|-` or `|+`.
_CLAUDE_ARGS_HEADER = re.compile(r"(?P<indent> *)claude_args: *\|[-+]? *(?:#.*)?")


def _claude_args_blocks(path: Path) -> list[list[str]]:
    """Return the command-line arguments in each `claude_args: |` block of a workflow file.

    A block is the lines after its header that are blank or indented deeper than the `claude_args` key. Its text is
    split into arguments as a shell does, dropping `#` comments, so a flag in a YAML comment, under another key or in
    another step does not count. Lines are read with universal newlines.
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    blocks = []
    for index, line in enumerate(lines):
        header = _CLAUDE_ARGS_HEADER.fullmatch(line)
        if header is None:
            continue
        body = []
        for body_line in lines[index + 1 :]:
            if body_line.strip() and len(body_line) - len(body_line.lstrip(" ")) <= len(header["indent"]):
                break
            body.append(body_line)
        blocks.append(shlex.split("\n".join(body), comments=True))
    return blocks


def _flag_values(args: list[str], flag: str) -> list[str | None]:
    """Return the value of each occurrence of a flag in a list of command-line arguments.

    The value is the next argument (`--flag value`) or the text after the equals sign (`--flag=value`). A flag that
    is the last argument has the value None.
    """
    values: list[str | None] = []
    for position, arg in enumerate(args):
        if arg == flag:
            values.append(args[position + 1] if position + 1 < len(args) else None)
        elif arg.startswith(f"{flag}="):
            values.append(arg[len(flag) + 1 :])
    return values


class ClaudeReviewTemplateTest(unittest.TestCase):
    def test_ci_review_runs_on_opus_at_medium_effort(self) -> None:
        """R1.7: the pull request review in CI runs on Opus 5.5 (claude-opus-5-5) at medium effort.

        The review template's only `claude_args: |` block, which claude-code-action passes to the Claude Code CLI,
        holds exactly one `--model claude-opus-5-5` and exactly one `--effort medium`.
        """
        blocks = _claude_args_blocks(CLAUDE_REVIEW_TEMPLATE)
        args = [arg for block in blocks for arg in block]

        actual = {
            "claude_args blocks": len(blocks),
            "--model": _flag_values(args, "--model"),
            "--effort": _flag_values(args, "--effort"),
        }

        self.assertEqual(actual, {"claude_args blocks": 1, "--model": ["claude-opus-5-5"], "--effort": ["medium"]})


# What R6.1 asks a slice summary to hold, each with the pattern a `## ` heading of the template must match.
_SLICE_SUMMARY_SECTIONS = {
    "what changed and why": re.compile(r"changed.*\bwhy\b|\bwhy\b.*changed", re.IGNORECASE),
    "requirements covered": re.compile(r"\brequirements?\b", re.IGNORECASE),
    "size (lines changed)": re.compile(r"\bsize\b|\blines\b", re.IGNORECASE),
    "risks": re.compile(r"\brisks?\b", re.IGNORECASE),
    "decisions": re.compile(r"\bdecisions?\b", re.IGNORECASE),
    "review rounds": re.compile(r"\breview\b.*\brounds?\b|\brounds?\b.*\breview", re.IGNORECASE),
    "rethinks": re.compile(r"\brethinks?\b", re.IGNORECASE),
    "reading order": re.compile(r"\breading order\b", re.IGNORECASE),
}

# A file path and a line range inside backticks, such as `src/a.py:12-40` or `<path>:<first>\u2013<last>`.
_RANGE_END = r"(?:\d+|<[^<>`]+>)"
_FILE_WITH_LINE_RANGE = re.compile(rf"`[^`\s]+:{_RANGE_END}\s*[-\u2013]\s*{_RANGE_END}`")


def _headings(text: str) -> list[str]:
    """Return the text of every `## ` heading of a Markdown document, in order."""
    return [line[3:].strip() for line in text.splitlines() if line.startswith("## ")]


def _missing_sections(headings: list[str], sections: dict[str, re.Pattern[str]]) -> list[str]:
    """Return one gap per section whose pattern matches none of `headings`, or [] when every section has one."""
    return [
        f"no '## ' heading for {label} (headings: {headings})"
        for label, pattern in sections.items()
        if not any(pattern.search(heading) for heading in headings)
    ]


def _slice_summary_gaps(path: Path) -> list[str]:
    """Return what R6.1 asks of a slice summary that the template at `path` lacks, or [] when it has it all."""
    if not path.is_file():
        return [f"{path}: the slice summary template does not exist"]
    text = path.read_text(encoding="utf-8")
    headings = _headings(text)
    gaps = _missing_sections(headings, _SLICE_SUMMARY_SECTIONS)
    if not re.search(r"high[- ]risk", text, re.IGNORECASE):
        gaps.append("nothing about the slice's high-risk tasks")
    reading_order_pattern = _SLICE_SUMMARY_SECTIONS["reading order"]
    reading_order = next((heading for heading in headings if reading_order_pattern.search(heading)), None)
    if reading_order is not None and not _FILE_WITH_LINE_RANGE.search(read_section(path, reading_order)):
        gaps.append(f"'## {reading_order}' shows no file path with a line range such as `<path>:<first>-<last>`")
    return gaps


class SliceSummaryTemplateTest(unittest.TestCase):
    maxDiff = None

    def test_slice_summary_template_has_every_section(self) -> None:
        """R6.1: the slice summary template has a section for everything a finished slice must report.

        Its `## ` headings name what changed and why, the requirements covered, the size in changed lines, the risks,
        the decisions, the review rounds, the rethinks and the reading order; it mentions the high-risk tasks; and the
        reading order shows a file path with a line range.
        """
        gaps = _slice_summary_gaps(SLICE_SUMMARY_TEMPLATE)

        self.assertEqual(gaps, [])


# What R6.3 asks the final feature summary to gather, each with the pattern its own `## ` heading of the template must
# match. Each pattern names only its own section, so a heading meant for another one (`Requirements, tests and
# evidence` for the spec, `Slices` for the slice summaries) cannot stand in for it.
_FEATURE_SUMMARY_SECTIONS = {
    "the spec": re.compile(r"\bspec\b", re.IGNORECASE),
    "the design": re.compile(r"\bdesign\b", re.IGNORECASE),
    "the slice summaries": re.compile(r"\bslice summar(?:y|ies)\b", re.IGNORECASE),
    "the decisions": re.compile(r"\bdecisions?\b", re.IGNORECASE),
    "the evidence": re.compile(r"\bevidence\b", re.IGNORECASE),
    "the rethinks": re.compile(r"\brethinks?\b", re.IGNORECASE),
    "the refuted findings": re.compile(r"\brefuted\b", re.IGNORECASE),
    "the suggestions not applied": re.compile(
        r"\bsuggestions?\b.*\bnot applied\b|\bunapplied suggestions?\b", re.IGNORECASE
    ),
    "how to test the feature": re.compile(r"\bhow to (?:test|try|verify)\b", re.IGNORECASE),
}


def _sections_without_own_heading(headings: list[str], sections: dict[str, re.Pattern[str]]) -> list[str]:
    """Return one gap per section left without a `## ` heading of its own, or [] when each section has a distinct one.

    Sections and headings are paired one to one (a maximum bipartite matching by augmenting paths), so a heading that
    matches two sections, such as `Design decisions`, counts for only one of them.
    """
    owners: dict[int, str] = {}  # heading index -> the section that heading is paired with

    def pair(label: str, visited: set[int]) -> bool:
        for index, heading in enumerate(headings):
            if index in visited or not sections[label].search(heading):
                continue
            visited.add(index)
            if index not in owners or pair(owners[index], visited):
                owners[index] = label
                return True
        return False

    return [
        f"no '## ' heading of its own for {label} (headings: {headings})"
        for label in sections
        if not pair(label, set())
    ]


def _feature_summary_gaps(path: Path) -> list[str]:
    """Return what R6.3 asks of the feature summary that the template at `path` lacks, or [] when it has it all."""
    if not path.is_file():
        return [f"{path}: the feature summary template does not exist"]
    text = path.read_text(encoding="utf-8")
    gaps = _sections_without_own_heading(_headings(text), _FEATURE_SUMMARY_SECTIONS)
    # The summary sits in specs/<NNN-slug>/ next to summaries/S<k>.md, so it gathers each slice's summary by linking it.
    if "summaries/S" not in text:
        gaps.append("no link to the slice summaries in summaries/S<k>.md")
    return gaps


class FeatureSummaryTemplateTest(unittest.TestCase):
    maxDiff = None

    def test_feature_summary_template_has_every_section(self) -> None:
        """R6.3: the feature summary template has a section for everything the finished feature must gather.

        Each of the spec, the design, the slice summaries, the decisions, the evidence, the rethinks, the refuted
        findings, the suggestions not applied and how to test the feature has a `## ` heading of its own, never one
        shared with another of them; and it links the slice summaries in `summaries/S<k>.md`.
        """
        gaps = _feature_summary_gaps(FEATURE_SUMMARY_TEMPLATE)

        self.assertEqual(gaps, [])


if __name__ == "__main__":
    unittest.main()
