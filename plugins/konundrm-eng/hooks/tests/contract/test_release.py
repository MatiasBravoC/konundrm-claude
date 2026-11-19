"""Contract tests for what a release of the plugin ships beyond its skills and agents.

That is its evals, its version and changelog, and the repository README that describes the release.
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from .plugin_files import PLUGIN_ROOT, read_frontmatter, read_section

EVALS_DIR = PLUGIN_ROOT / "evals"

# One behavior eval per new mechanism the user meets (R10.3): the slice checkpoint with its questions, the design
# decision, the slice summary, the feature summary and the improvement notes.
_NEW_MECHANISM_EVALS = (
    "behavior-slice-checkpoint",
    "behavior-design-decision",
    "behavior-slice-summary",
    "behavior-feature-summary",
    "behavior-improvement-notes",
)
# One behavior eval per mechanism of feature 004 the user meets (004 R5.2): the plan with consolidated tasks and the
# adjustment that runs only the reviews its change needs.
_NEW_MECHANISM_EVALS_004 = (
    "behavior-plan-consolidates-related-tasks",
    "behavior-adjustment-runs-needed-reviews",
)

# The grader types `claude plugin eval` documents (https://code.claude.com/docs/en/plugin-evals.md).
_GRADER_TYPES = frozenset({"llm", "tool_used", "file_exists", "regex", "tool_order", "baseline"})


def _prompt_gaps(path: Path) -> list[str]:
    """Return what the eval case's `prompt.md` at `path` lacks (the file, its frontmatter, a prompt), or []."""
    if not path.is_file():
        return [f"{path}: the case has no prompt.md"]
    try:
        read_frontmatter(path)
    except ValueError as error:
        return [str(error)]
    lines = path.read_text(encoding="utf-8").splitlines()
    closing_fence = [index for index, line in enumerate(lines) if line == "---"][1]
    if not "\n".join(lines[closing_fence + 1 :]).strip():
        return [f"{path}: no prompt text after the frontmatter"]
    return []


def _grader_gaps(graders_dir: Path) -> list[str]:
    """Return what the eval case's graders in `graders_dir` lack, or [] when each sets a known `type:`.

    The case needs at least one `graders/*.md`, and each one needs a frontmatter whose `type:` is a documented grader
    type.
    """
    graders = sorted(graders_dir.glob("*.md")) if graders_dir.is_dir() else []
    if not graders:
        return [f"{graders_dir}: the case has no graders/*.md"]
    gaps = []
    for grader in graders:
        try:
            grader_type = read_frontmatter(grader).get("type", "")
        except ValueError as error:
            gaps.append(str(error))
            continue
        if grader_type not in _GRADER_TYPES:
            gaps.append(f"{grader}: frontmatter 'type: {grader_type}' is not one of {sorted(_GRADER_TYPES)}")
    return gaps


def _eval_case_gaps(case_dir: Path) -> list[str]:
    """Return what the behavior eval case at `case_dir` lacks, or [] when it has a prompt and typed graders."""
    if not case_dir.is_dir():
        return [f"{case_dir}: the eval case does not exist"]
    return _prompt_gaps(case_dir / "prompt.md") + _grader_gaps(case_dir / "graders")


class BehaviorEvalsTest(unittest.TestCase):
    maxDiff = None

    def test_each_new_mechanism_has_a_behavior_eval(self) -> None:
        """R10.3: every new mechanism the user meets has a behavior eval that `claude plugin eval` can run.

        Each of `behavior-slice-checkpoint`, `behavior-design-decision`, `behavior-slice-summary`,
        `behavior-feature-summary` and `behavior-improvement-notes` under `evals/` has a `prompt.md` with a frontmatter
        and a prompt after it, and at least one `graders/*.md` whose frontmatter sets a documented `type:`. The evals
        run a model, so the check only verifies their structure.
        """
        gaps = [gap for name in _NEW_MECHANISM_EVALS for gap in _eval_case_gaps(EVALS_DIR / name)]

        self.assertEqual(gaps, [])

    def test_each_right_sized_flow_mechanism_has_a_behavior_eval(self) -> None:
        """R5.2: 004 each mechanism of the right-sized flow the user meets has a behavior eval the runner can run.

        `behavior-plan-consolidates-related-tasks` (the plan merges related low-risk behaviors into one task and
        leaves the medium-risk one alone) and `behavior-adjustment-runs-needed-reviews` (a small change asked on work
        already built is made as an adjustment, with only the reviews it needs) each have a `prompt.md` with a
        frontmatter and a prompt after it, and at least one `graders/*.md` whose frontmatter sets a documented
        `type:`. The evals run a model, so the check only verifies their structure.
        """
        gaps = [gap for name in _NEW_MECHANISM_EVALS_004 for gap in _eval_case_gaps(EVALS_DIR / name)]

        self.assertEqual(gaps, [])


_CHANGELOG_PATH = PLUGIN_ROOT / "CHANGELOG.md"
_CHANGELOG_MANIFEST_PATH = PLUGIN_ROOT / ".claude-plugin" / "plugin.json"
# This feature (guided slice delivery) ships as 0.6.0 (requirements.md, Constraints).
_CHANGELOG_FEATURE_VERSION = (0, 6, 0)
# Released entries only: `## [Unreleased]` has no digits, so it never matches.
_CHANGELOG_RELEASE_HEADING = re.compile(r"^## (\[(\d+)\.(\d+)\.(\d+)\].*)$")
_CHANGELOG_MECHANISMS = (
    ("model and effort per role", re.compile(r"\bmodel and effort (?:per|for each|for every) role\b")),
    ("the rethinker", re.compile(r"\brethinker\b")),
    ("parallel partitions", re.compile(r"\bpartitions?\b")),
    ("slice pauses", re.compile(r"\bslice checkpoints?\b|\bpauses? (?:after|at the end of) (?:each|every) slice\b")),
    ("slice summaries", re.compile(r"\bslice summar(?:y|ies)\b")),
    ("the feature summary", re.compile(r"\bfeature summar(?:y|ies)\b")),
    ("improvement notes", re.compile(r"\bimprovement notes?\b")),
)


def _changelog_released_entries() -> list[tuple[tuple[int, int, int], str]]:
    """Return `(version, heading)` for each released CHANGELOG entry, newest first.

    `heading` is the heading line without its leading `## `, ready for `read_section`.
    """
    entries = []
    for line in _CHANGELOG_PATH.read_text(encoding="utf-8").splitlines():
        match = _CHANGELOG_RELEASE_HEADING.match(line)
        if match:
            version = (int(match.group(2)), int(match.group(3)), int(match.group(4)))
            entries.append((version, match.group(1)))
    return entries


# Feature 002 (efficient feature flow) ships as 0.7.0 (R7.2). Keyword patterns, not sentence grammars: each ties its
# keyword to the mechanism so a quoted command or "one commit per task" in the entry does not match by accident.
_CHANGELOG_002_VERSION = (0, 7, 0)
_CHANGELOG_002_MECHANISMS = (
    (
        "a new session per slice",
        re.compile(
            r"\b(?:new|one|a|fresh|own) sessions? (?:per|for each|for every) slice\b"
            r"|\bper-slice sessions?\b|\bsessions?\W{1,6}per-slice\b"
            r"|\beach slice (?:runs |gets |starts )?(?:in )?(?:its own|a new|a fresh) session\b"
        ),
    ),
    ("one check per task", re.compile(r"\bchecks?\b(?: \w+){0,2} (?:per|for each|for every) task\b")),
    (
        "parallel reviews",
        re.compile(
            r"\bparallel (?:spec and code )?reviews?\b"
            r"|\breviews?\b(?: \w+){0,2} (?:in parallel|at once|concurrently)\b"
        ),
    ),
    ("task_ledger.py", re.compile(r"\btask_ledger\.py\b")),
    ("the fast path of run.sh", re.compile(r"\bfast[ -]path\b.{0,60}\brun\.sh\b|\brun\.sh\b.{0,60}\bfast[ -]path\b")),
    ("run_slices.py", re.compile(r"\brun_slices\.py\b")),
    ("session_costs.py", re.compile(r"\bsession_costs\.py\b")),
)

# Feature 004 (right-sized flow) ships as 0.9.0 (004 R5.3). Keyword patterns, as for 002: each ties its keyword to the
# mechanism, so a passing mention of a task or a review in the entry does not match by accident.
_CHANGELOG_004_VERSION = (0, 9, 0)
_CHANGELOG_004_MECHANISMS = (
    ("consolidated tasks", re.compile(r"\bconsolidated tasks?\b")),
    ("one test per behavior in a consolidated task", re.compile(r"\bone test per behaviou?r\b")),
    (
        "that only low-risk tasks are merged",
        re.compile(r"\blow[- ]risk\b.{0,200}?\bmerg\w*|\bmerg\w*.{0,200}?\blow[- ]risk\b"),
    ),
    (
        "that only the reviews a change concerns run again",
        re.compile(r"\bonly the reviews\b(?: \S+){0,8} (?:concerns?|needs?)\b"),
    ),
    ("adjustments", re.compile(r"\badjustments?\b")),
    (
        "that plans written with earlier versions are built as before",
        re.compile(r"\bearlier versions?\b.{0,120}?\bas before\b"),
    ),
)


def _changelog_mechanism_gaps(
    entries: list[tuple[tuple[int, int, int], str]],
    version: tuple[int, int, int],
    mechanisms: tuple[tuple[str, re.Pattern[str]], ...],
) -> list[str]:
    """Return one gap per mechanism the `version` entry does not name, or one gap when that entry is missing.

    The entry is looked up by its version, never by position. Its text is matched lowercased, without backticks and
    with whitespace collapsed, since entries wrap their lines.
    """
    version_text = ".".join(str(part) for part in version)
    heading = next((heading for entry_version, heading in entries if entry_version == version), None)
    if heading is None:
        return [f"CHANGELOG.md: there is no [{version_text}] entry"]
    text = read_section(_CHANGELOG_PATH, heading).lower().replace("`", "")
    text = re.sub(r"\s+", " ", text)
    return [
        f"CHANGELOG.md [{version_text}]: the entry does not name {label}"
        for label, pattern in mechanisms
        if not pattern.search(text)
    ]


def _manifest_version() -> tuple[int, ...] | None:
    """Return plugin.json's version as a tuple of numbers, or None when it is not `<x.y.z>`."""
    version = json.loads(_CHANGELOG_MANIFEST_PATH.read_text(encoding="utf-8"))["version"]
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", version)
    return tuple(int(part) for part in match.groups()) if match else None


class VersionAndChangelogTest(unittest.TestCase):
    maxDiff = None

    def test_version_and_changelog_agree(self) -> None:
        """R10.1: plugin.json's version is the first CHANGELOG release, 0.6.0 or later; 0.6.0 names each mechanism.

        The first released entry is the first `## [<x.y.z>]` heading, so a `## [Unreleased]` heading is skipped. The
        0.6.0 entry is looked up by its version, not by position, so the check stays true after later releases put
        newer entries above it. It must name model and effort per role, the rethinker, parallel partitions, slice
        pauses, slice summaries, the feature summary and improvement notes.
        """
        manifest_version = json.loads(_CHANGELOG_MANIFEST_PATH.read_text(encoding="utf-8"))["version"]
        entries = _changelog_released_entries()

        gaps = []
        if not entries:
            gaps.append("CHANGELOG.md: there is no released `## [<x.y.z>]` entry")
        else:
            first_version, first_heading = entries[0]
            first_text = ".".join(str(part) for part in first_version)
            if manifest_version != first_text:
                gaps.append(f"plugin.json version {manifest_version} is not the first CHANGELOG entry {first_heading}")
            if first_version < _CHANGELOG_FEATURE_VERSION:
                gaps.append(f"CHANGELOG.md: the first released entry {first_heading} is older than 0.6.0")
        gaps += _changelog_mechanism_gaps(entries, _CHANGELOG_FEATURE_VERSION, _CHANGELOG_MECHANISMS)

        self.assertEqual(gaps, [])

    def test_0_7_0_changelog_names_each_mechanism(self) -> None:
        """R7.1, R7.2: 002 ships as 0.7.0 or later, and the [0.7.0] CHANGELOG entry names each new mechanism.

        plugin.json's version, compared as numbers, is 0.7.0 or later (test_version_and_changelog_agree already ties
        it to the first released entry). The [0.7.0] entry is looked up by its version, and must name a new session per
        slice, one check per task, parallel reviews, task_ledger.py, the fast path of run.sh, run_slices.py and
        session_costs.py.
        """
        manifest_version = _manifest_version()
        entries = _changelog_released_entries()

        gaps = []
        if manifest_version is None or manifest_version < _CHANGELOG_002_VERSION:
            shown = "not <x.y.z>" if manifest_version is None else ".".join(str(part) for part in manifest_version)
            gaps.append(f"plugin.json version {shown} is older than 0.7.0")
        gaps += _changelog_mechanism_gaps(entries, _CHANGELOG_002_VERSION, _CHANGELOG_002_MECHANISMS)

        self.assertEqual(gaps, [])

    def test_0_9_0_changelog_names_each_mechanism(self) -> None:
        """R5.3: 004 ships as 0.9.0 or later, and the [0.9.0] CHANGELOG entry names each new mechanism.

        plugin.json's version, compared as numbers, is 0.9.0 or later (test_version_and_changelog_agree already ties
        it to the first released entry). The [0.9.0] entry is looked up by its version, and must name consolidated
        tasks with one test per behavior, that only low-risk tasks are merged, that only the reviews a change concerns
        run again, adjustments, and that plans written with earlier versions are built as before.
        """
        manifest_version = _manifest_version()
        entries = _changelog_released_entries()

        gaps = []
        if manifest_version is None or manifest_version < _CHANGELOG_004_VERSION:
            shown = "not <x.y.z>" if manifest_version is None else ".".join(str(part) for part in manifest_version)
            gaps.append(f"plugin.json version {shown} is older than 0.9.0")
        gaps += _changelog_mechanism_gaps(entries, _CHANGELOG_004_VERSION, _CHANGELOG_004_MECHANISMS)

        self.assertEqual(gaps, [])


# The repository README (two levels above the plugin), in Spanish, where a slice is an "entrega".
_README_PATH = PLUGIN_ROOT.parents[1] / "README.md"
# What 0.7.0 adds to the README (R7.2), each looked for in the section a reader goes to for it, so the practices table
# or the known limits cannot match by accident. Keyword patterns, not sentence grammars: "sesión" and "entrega" each
# appear many times already, so the session pattern ties them together, and measuring needs the transcripts.
_README_002_ITEMS = (
    (
        "### Cómo avanza una feature",
        "a new session per slice",
        re.compile(
            r"\bsesi[oó]n(?:es)? (?:nuevas? |propias? )?(?:por|para cada|de cada) entrega\b"
            r"|\bcada entrega\b(?: \w+){0,3} en (?:una|su) "
            r"(?:sesi[oó]n nueva|nueva sesi[oó]n|sesi[oó]n propia|propia sesi[oó]n)\b"
        ),
    ),
    (
        "### Cómo avanza una feature",
        "the tasks.md header line Sessions: single",
        re.compile(r"\bsessions:\W{0,4}single\b"),
    ),
    ("## Uso", "run_slices.py given a specs/ folder", re.compile(r"\brun_slices\.py\s+specs/")),
    (
        "## Uso",
        "measuring a run from its transcripts with session_costs.py or measure-impact",
        re.compile(
            r"transcripci.{0,160}?(?:\bsession_costs\.py\b|\bmeasure-impact\b)"
            r"|(?:\bsession_costs\.py\b|\bmeasure-impact\b).{0,160}?transcripci"
        ),
    ),
)
# What 0.9.0 adds to the README (004 R5.3), each in the section a reader goes to for it. A consolidated task is a
# "tarea consolidada" and an adjustment an "ajuste"; the review rule ties "revisiones" to what the change concerns.
_README_004_ITEMS = (
    (
        "### Cómo avanza una feature",
        "consolidated tasks (tareas consolidadas) of low risk",
        re.compile(
            r"\btareas? consolidadas?\b.{0,400}?\briesgo bajo\b"
            r"|\briesgo bajo\b.{0,400}?\btareas? consolidadas?\b"
        ),
    ),
    (
        "### Cómo avanza una feature",
        "one test per behavior in a consolidated task",
        re.compile(r"\bun test por comportamiento\b"),
    ),
    (
        "### Cómo avanza una feature",
        "that after a change only the reviews it concerns run again",
        re.compile(r"\bsolo\b(?: \S+){0,4} revisiones\b.{0,160}?\b(?:conciern\w*|necesit\w*)"),
    ),
    (
        "### Cómo avanza una feature",
        "adjustments (ajustes) made right away for a small change the user asks for",
        re.compile(r"\bajustes?\b.{0,300}?\ben el momento\b|\ben el momento\b.{0,300}?\bajustes?\b"),
    ),
)


def _read_markdown_section(path: Path, heading_line: str) -> str | None:
    """Return the body of the section whose heading line is exactly `heading_line`, or None when there is none.

    The body runs up to the next heading of the same or a higher level (`## ` ends a `### ` section, but not the other
    way round). Lines are read with universal newlines.
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    try:
        start = lines.index(heading_line) + 1
    except ValueError:
        return None
    level = len(heading_line) - len(heading_line.lstrip("#"))
    ends_section = re.compile(rf"^#{{1,{level}}} ")
    end = next((index for index in range(start, len(lines)) if ends_section.match(lines[index])), len(lines))
    return "\n".join(lines[start:end])


def _readme_item_gaps(items: tuple[tuple[str, str, re.Pattern[str]], ...]) -> list[str]:
    """Return one gap per item the README section it belongs to does not describe, or one per missing section.

    Each item is `(heading line, label, pattern)`. The section is matched lowercased, without backticks and with
    whitespace collapsed, since the README wraps its lines.
    """
    gaps: list[str] = []
    for heading_line, label, pattern in items:
        body = _read_markdown_section(_README_PATH, heading_line)
        if body is None:
            gap = f"README.md: there is no '{heading_line}' section"
            if gap not in gaps:
                gaps.append(gap)
            continue
        text = re.sub(r"\s+", " ", body.lower().replace("`", ""))
        if not pattern.search(text):
            gaps.append(f"README.md '{heading_line}': does not describe {label}")
    return gaps


class ReadmeTest(unittest.TestCase):
    maxDiff = None

    def test_readme_describes_sessions_per_slice_and_measuring_a_run(self) -> None:
        """R7.2: 002 the README describes the new flow, how to chain sessions and how to measure a run.

        `### Cómo avanza una feature` says each slice ("entrega") continues in a new session and names the tasks.md
        header line `Sessions: single` that keeps it in one; `## Uso` runs `run_slices.py` on a `specs/` folder and
        measures a run from its transcripts ("transcripción") with `session_costs.py` or `measure-impact`. Each section
        is matched lowercased, without backticks and with whitespace collapsed, since the README wraps its lines.
        """
        gaps = _readme_item_gaps(_README_002_ITEMS)

        self.assertEqual(gaps, [])

    def test_readme_describes_consolidated_tasks_and_adjustments(self) -> None:
        """R5.3: 004 the README describes consolidated tasks, the reviews that run again and adjustments.

        `### Cómo avanza una feature` says the plan merges related tasks of low risk ("riesgo bajo") into a
        consolidated task ("tarea consolidada") that keeps one test per behavior ("un test por comportamiento"), that
        after a change only the reviews it concerns run again, and that a small change the user asks for is made
        right away ("en el momento") as an adjustment ("ajuste"). The section is matched lowercased, without
        backticks and with whitespace collapsed.
        """
        gaps = _readme_item_gaps(_README_004_ITEMS)

        self.assertEqual(gaps, [])


if __name__ == "__main__":
    unittest.main()
