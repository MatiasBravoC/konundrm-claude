"""Contract tests for the flows the orchestrating skills describe (skills/*/SKILL.md and their references)."""

from __future__ import annotations

import re
import unittest
from collections.abc import Callable
from pathlib import Path

from .plugin_files import SKILLS_DIR, read_section

DEVELOP_FEATURE_DIR = SKILLS_DIR / "develop-feature"
MODEL_AND_EFFORT_LINK_TARGET = "../develop-feature/SKILL.md#model-and-effort"
RETHINK_LINK_TARGET = "../develop-feature/SKILL.md#rethink"

# A line that opens a new Markdown block: a list item, a heading or a table row.
_BLOCK_START = re.compile(r"\s*(?:[-*+]\s|\d+\.\s|#|\|)")
# The patterns below run on blocks from _blocks: lowercased, without backticks, single-spaced.
_ANY_FIX_ROUND = re.compile(r"\b(?:every|each|any|all) fix[- ]rounds?\b|\bfix[- ]rounds (?:always )?run\b")
_FIX_ROUND = re.compile(r"\bfix[- ]rounds?\b")
_HIGH_RISK = re.compile(r"\bhigh[- ]risk\b|\brisk is high\b")
_RETRY = re.compile(r"\bretr(?:y|ies)\b")
_WHOLE_PULL_REQUEST = re.compile(r"\bwhole[- ](?:feature|pull request)\b")
_MODEL_OPUS = re.compile(r"\bmodel: ?opus\b")
_EFFORT_HIGH = re.compile(r"\beffort: ?high\b")
_OPUS_HIGH_SHORTHAND = re.compile(r"\bopus ?(?:/|at) ?high\b")

# The rethink (R8). These also run on blocks from _blocks, some on one clause of a block (_in_one_clause).
_CLAUSE_BREAK = re.compile(r"[,;:.()]")
_SENTENCE_END = re.compile(r"(?<!\s)[.;:!?](?=\s|$)")  # not the lone "." of `git checkout -- .`
_FIFTH = re.compile(r"\b(?:fifth|5th|five)\b")
_THIRD = re.compile(r"\b(?:third|3rd|three)\b")
_TWO = re.compile(r"\btwo\b")
_REVIEW = re.compile(r"\breviews?\b")
_SAME_REVIEW = re.compile(r"\bsame review(?:er)?\b")
_FAILURE = re.compile(r"\bfail")
_STOP = re.compile(r"\b(?:stop(?:s|ping)?|halt(?:s|ing)?|no more|no further|instead of|rather than)\b")
_FIXING = re.compile(r"\bfix(?:es|ing|[- ]rounds?)?\b")
_ASKS_THE_USER = re.compile(r"\b(?:ask|wait)(?:s|ing)?\b(?: \S+){0,4} user\b|\bescalat")
_PROPOSES = re.compile(r"\b(?:propos|suggest|present)")
_BUILDS_AGAIN = re.compile(r"\b(?:re-?build|redo|restart)|\b(?:build|start)\b(?: \S+){0,3} (?:again|anew|over)\b")
_KEEPS_UNTRACKED = re.compile(r"--include-untracked|--all\b|(?<!\S)-[ua]\b")
# Throwing the attempt away: the word "discard", or a command that does it. A negation earlier in the same sentence
# ("never discard it", "do not run git clean") makes it a prohibition instead.
_DISCARDS = re.compile(
    r"\bdiscard\w*|\bgit (?:reset --hard|restore|clean|stash (?:drop|clear))\b|\bgit checkout (?:--|\.)(?!\S)"
)
_NEGATION = re.compile(r"\b(?:never|not|no|nothing|nor|without|don't|instead of|rather than)\b")
# The approved PLAN CHANGE edit (R8.3), and the two ways it survives a stash of the attempt (R8.2): written after the
# stash, or kept out of it by an `:(exclude)` pathspec for every plan document (or the feature's specs folder).
_PLAN_EDIT = re.compile(
    r"\bplan (?:change|edit)\b|\bapproved (?:plan )?edit\b|\bedit (?:to|of) (?:tasks|design|requirements)\.md\b"
)
_WRITES = re.compile(r"\b(?:writ|commit|appl|sav|mak)\w*")
_AFTER_THE_STASH = re.compile(r"\bafter\b(?: \S+){0,5} (?:stash\w*|aside)\b")
_STASH_BEFORE_WRITING = re.compile(r"\bstash\w*\b.*\bbefore (?:writ|commit|appl|sav|mak)\w*")
_EXCLUDED = re.compile(r":\(exclude\)(\S+)")
_PLAN_DOCUMENTS = ("tasks.md", "design.md", "requirements.md")
# fix-bug's rethink (R8.1, R8.4), which may follow develop-feature's Rethink section through a link instead of
# restating it.
_STATEMENT_END = re.compile(r"(?<!\s)[.;!?](?=\s|$)")  # unlike _SENTENCE_END, keeps "<condition>: escalate." whole
_DISPATCHES_THE_RETHINKER = re.compile(r"\bdispatch\w*(?: \S+){0,3} (?:konundrm-eng:)?rethinker\b")
# Saying to follow a linked section, not only pointing at it: "follow ...", "rethink as ... says", "per ...".
_FOLLOWS = re.compile(
    r"\b(?:follow\w*|appl(?:y|ies)|runs?|use|using|per|like|as in)\b"
    r"|\b(?:as|what)\b(?: \S+){0,4} (?:says|describes|does)\b"
)
_RED = re.compile(r"\bred\b")


def _says_opus_high(row: str) -> bool:
    """Return whether a table row has a cell that is exactly `opus` and another that is exactly `high`."""
    cells = {cell.strip().strip("`").strip() for cell in row.strip("|").split("|")}
    return {"opus", "high"} <= cells


def _blocks(path: Path) -> list[str]:
    """Return the paragraphs, list items, headings and table rows of a Markdown file, after its frontmatter.

    Each block is normalized as `_split_blocks` describes. Lines are read with universal newlines.
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    if lines[:1] == ["---"] and "---" in lines[1:]:
        lines = lines[lines.index("---", 1) + 1 :]
    return _split_blocks(lines)


def _section_blocks(path: Path, heading: str) -> list[str]:
    """Return the blocks of a Markdown file's `## <heading>` section, as `_blocks` does, or [] when it lacks one."""
    return _split_blocks(read_section(path, heading).splitlines())


def _split_blocks(lines: list[str]) -> list[str]:
    """Return Markdown lines grouped into paragraphs, list items, headings and table rows.

    Each block is lowercased, without backticks and with its whitespace collapsed to single spaces, so a phrase
    wrapped across lines still matches.
    """
    blocks: list[list[str]] = []
    for line in lines:
        if not blocks or not line.strip() or _BLOCK_START.match(line):
            blocks.append([])
        if line.strip():
            blocks[-1].append(line)
    return [" ".join(" ".join(block).replace("`", "").lower().split()) for block in blocks if block]


def _sets_opus_high(block: str) -> bool:
    """Return whether a block from `_blocks` passes the Agent tool `model: opus` and `effort: high`.

    Accepts the two parameters spelled out, the `opus`/`high` or "opus at high" shorthand, and a table row with the
    cells `opus` and `high`. A "high" that names a risk level does not count.
    """
    if _MODEL_OPUS.search(block) and _EFFORT_HIGH.search(block):
        return True
    return _OPUS_HIGH_SHORTHAND.search(block) is not None or _says_opus_high(block)


def _is_about_first_attempts_on_a_high_risk_bug(block: str) -> bool:
    """Return whether a block is about the test-writer's and implementer's first attempts on a high-risk bug.

    A block that also states the fix-round rule counts only when it says "first attempt", so the fix-round rule
    alone cannot stand in for this one.
    """
    if _HIGH_RISK.search(block) is None or "test-writer" not in block or "implementer" not in block:
        return False
    return "first attempt" in block or _FIX_ROUND.search(block) is None


def _says_other_dispatches_omit_both(block: str) -> bool:
    """Return whether a block says to omit `model` and `effort` so each agent's frontmatter applies."""
    return all(word in block for word in ("omit", "model", "effort", "frontmatter"))


def _override_gaps(skill: str, blocks: list[str], overrides: dict[str, Callable[[str], bool]]) -> list[str]:
    """Return one message per override of a skill that no block about its dispatch sets to opus and high.

    Args:
        skill: the skill's folder name, used to start each message.
        blocks: the skill's SKILL.md blocks, from `_blocks`.
        overrides: a label per agreed override, mapped to whether a block is about that dispatch.
    """
    gaps = []
    for label, is_about in overrides.items():
        about = [block for block in blocks if is_about(block)]
        if not about:
            gaps.append(f"{skill}: no paragraph or list item about {label}")
        elif not any(_sets_opus_high(block) for block in about):
            gaps.append(f"{skill}: the paragraph or list item about {label} does not set model opus and effort high")
    return gaps


def _in_one_clause(block: str, *patterns: re.Pattern[str]) -> bool:
    """Return whether one clause of a block (text between commas, semicolons, colons, periods or parentheses)
    matches every pattern, so the words can come in any order but must belong together."""
    return any(all(pattern.search(clause) for pattern in patterns) for clause in _CLAUSE_BREAK.split(block))


def _is_fifth_failed_review(block: str) -> bool:
    """Return whether a block names a task's fifth failed review ("its fifth failed review", "fails five reviews")."""
    return _in_one_clause(block, _FIFTH, _REVIEW) and _FAILURE.search(block) is not None


def _is_third_failure_of_the_same_review(block: str) -> bool:
    """Return whether a block names a third failure of one review ("the same review fails a third time")."""
    return _in_one_clause(block, _THIRD, _SAME_REVIEW)


def _is_two_failed_reviews(block: str) -> bool:
    """Return whether a block names two (more) failed reviews ("if the task still fails two more reviews")."""
    return _in_one_clause(block, _TWO, _REVIEW) and _FAILURE.search(block) is not None


def _names_a_rethink_trigger(text: str) -> bool:
    """Return whether text names a trigger of the rethink: a fifth failed review, or a third failure of one review."""
    return _is_fifth_failed_review(text) or _is_third_failure_of_the_same_review(text)


# What develop-feature's `## Rethink` section must say, each in one paragraph or list item of it.
_RETHINK_STEPS: dict[str, Callable[[str], bool]] = {
    "R8.1 rethinking at a task's fifth failed review": _is_fifth_failed_review,
    "R8.1 rethinking at the third failure of the same review": _is_third_failure_of_the_same_review,
    "R8.1 stopping the fix rounds": lambda block: _in_one_clause(block, _STOP, _FIXING),
    "R8.1 dispatching the rethinker": lambda block: "dispatch" in block and "rethinker" in block,
    "R8.2 an attempt the rethinker sets aside": lambda block: "aside" in block,
    "R8.2 a git stash that keeps that attempt, untracked files included": lambda block: (
        "git stash" in block and _KEEPS_UNTRACKED.search(block) is not None
    ),
    "R8.2 building the task again": lambda block: _BUILDS_AGAIN.search(block) is not None,
    "R8.2 the rethinker's instructions going to the test-writer and implementer": lambda block: (
        "instructions" in block and any(word in block for word in ("test-writer", "implementer", "dispatch"))
    ),
    "R8.3 proposing a PLAN CHANGE and waiting for the user": lambda block: (
        "plan change" in block and _PROPOSES.search(block) is not None and _ASKS_THE_USER.search(block) is not None
    ),
    "R8.4 asking the user when the task still fails two more reviews": lambda block: (
        _is_two_failed_reviews(block) and _ASKS_THE_USER.search(block) is not None
    ),
}


def _discard_instructions(blocks: list[str]) -> list[str]:
    """Return each discard word or command in blocks that no negation earlier in its sentence turns into a ban."""
    found = []
    for block in blocks:
        for sentence in _SENTENCE_END.split(block):
            found += [
                match.group()
                for match in _DISCARDS.finditer(sentence)
                if _NEGATION.search(sentence[: match.start()]) is None
            ]
    return found


def _rethink_gaps(skill: Path) -> list[str]:
    """Return one message per step of R8.1 to R8.4 that the skill's `## Rethink` section lacks, and one when that
    section says to throw the attempt away."""
    blocks = _section_blocks(skill, "Rethink")
    gaps = [] if blocks else ["develop-feature: SKILL.md has no '## Rethink' section"]
    gaps += [
        f"develop-feature Rethink: no paragraph or list item about {label}"
        for label, is_about in _RETHINK_STEPS.items()
        if not any(is_about(block) for block in blocks)
    ]
    discards = _discard_instructions(blocks)
    if discards:
        gaps.append(f"develop-feature Rethink: says to throw the attempt away ({', '.join(discards)}); R8.2 keeps it")
    return gaps


def _writes_the_plan_edit_after_the_stash(block: str) -> bool:
    """Return whether a block about the approved plan edit writes it only once the attempt is stashed.

    One sentence of the block must pair a write verb with "after ... stash" or "after ... aside" (no negation before
    the "after"), or say to stash "before writing".
    """
    if _PLAN_EDIT.search(block) is None:
        return False
    for sentence in _SENTENCE_END.split(block):
        after = _AFTER_THE_STASH.search(sentence)
        if after and _WRITES.search(sentence) and _NEGATION.search(sentence[: after.start()]) is None:
            return True
        if _STASH_BEFORE_WRITING.search(sentence):
            return True
    return False


def _keeps_the_plan_out_of_the_stash(block: str) -> bool:
    """Return whether a block's git stash excludes every plan document, by name or through a `specs/` path."""
    if "git stash" not in block:
        return False
    excluded = _EXCLUDED.findall(block)
    if any("specs/" in path for path in excluded):
        return True
    return all(any(document in path for path in excluded) for document in _PLAN_DOCUMENTS)


def _after_rethink_gaps(skill: Path) -> list[str]:
    """Return what develop-feature lacks for the work after a rethink: the approved plan edit surviving the stash
    of a set-aside attempt (R8.2, R8.3), and every later test-writer and implementer dispatch on opus at high, said
    in the Rethink block that passes on the rethinker's instructions or in a Model and effort row (R1.2)."""
    blocks = _section_blocks(skill, "Rethink")
    gaps = []
    if not any(_writes_the_plan_edit_after_the_stash(b) or _keeps_the_plan_out_of_the_stash(b) for b in blocks):
        gaps.append(
            "develop-feature Rethink: does not write the approved plan edit after stashing the attempt, nor keep "
            "tasks.md, design.md and requirements.md out of the stash (the stash would take the approved edit)"
        )
    carries_instructions = [
        block for block in blocks if "instructions" in block and "test-writer" in block and "implementer" in block
    ]
    rows = _section_blocks(skill, "Model and effort")
    rethink_rows = [
        row
        for row in rows
        if row.startswith("|") and "rethink" in row and "test-writer" in row and "implementer" in row
    ]
    if not any(_sets_opus_high(block) for block in carries_instructions) and not any(
        _says_opus_high(row) for row in rethink_rows
    ):
        gaps.append(
            "develop-feature: no Rethink block with the rethinker's instructions, nor Model and effort row naming the "
            "rethink, runs every later test-writer and implementer dispatch on opus at high (R1.2)"
        )
    return gaps


def _escalation_blocks(skill: Path) -> list[str]:
    """Return the blocks of a skill's `## Escalation` section, as `_section_blocks` does, whatever follows that word
    in its heading ("Escalation: stop and ask the user when")."""
    lines = skill.read_text(encoding="utf-8").splitlines()
    heading = next((line[3:] for line in lines if line.startswith("## Escalation")), "Escalation")
    return _section_blocks(skill, heading)


def _escalation_gaps(skill: Path) -> list[str]:
    """Return one message per item of the skill's `## Escalation` list that still asks the user at a rethink
    trigger without pointing to the rethink, and one when no item asks after the rethink's two extra failures."""
    blocks = _escalation_blocks(skill)
    gaps = [
        f"develop-feature Escalation: asks the user at a rethink trigger instead of rethinking: {block!r}"
        for block in blocks
        if "rethink" not in block and _names_a_rethink_trigger(block)
    ]
    if not any(_is_two_failed_reviews(block) and "rethink" in block for block in blocks):
        gaps.append(
            "develop-feature Escalation: no item asks the user when a task still fails two reviews after its rethink"
        )
    return gaps


def _rethinker_prompt_gaps(prompts: Path) -> list[str]:
    """Return what a dispatch-prompts file lacks for the rethinker: a fenced `## rethinker` prompt that passes the
    review findings and asks for the RETHINK report, and an entry for it in the `## Contents` list."""
    section = read_section(prompts, "rethinker")
    prompt = " ".join(section.replace("`", "").lower().split())
    gaps = []
    if "```" not in section:
        gaps.append("dispatch-prompts.md: no '## rethinker' section with a fenced prompt")
    if "finding" not in prompt:
        gaps.append("dispatch-prompts.md: the rethinker prompt does not pass the review findings")
    if re.search(r"\brethink\b", prompt) is None:
        gaps.append("dispatch-prompts.md: the rethinker prompt does not ask for the RETHINK report")
    contents = read_section(prompts, "Contents").lower().splitlines()
    if not any(line.lstrip().startswith(("-", "*")) and "rethinker" in line for line in contents):
        gaps.append("dispatch-prompts.md: the Contents list does not name the rethinker prompt")
    return gaps


# The two triggers of the rethink (R8.1); fix-bug must stop its fix rounds and rethink at each.
_RETHINK_TRIGGERS: dict[str, Callable[[str], bool]] = {
    "the fifth failed review": _is_fifth_failed_review,
    "the third failure of the same review": _is_third_failure_of_the_same_review,
}


def _follows_the_rethink_link(block: str) -> bool:
    """Return whether one sentence of a block links to develop-feature's Rethink section and says to follow it."""
    link = f"]({RETHINK_LINK_TARGET.lower()})"  # blocks are lowercased
    return any(link in sentence and _FOLLOWS.search(sentence) for sentence in _SENTENCE_END.split(block))


def _fix_bug_rethink_gaps(skill: Path) -> list[str]:
    """Return what fix-bug lacks to rethink a stuck fix: at each trigger, a paragraph or list item that stops the fix
    rounds and rethinks (R8.1); one that dispatches the rethinker or says to follow develop-feature's Rethink section
    (R8.1); and one that stops to ask the user when the fix still fails two more reviews after its rethink (R8.4)."""
    blocks = _blocks(skill)
    gaps = []
    for trigger, names_it in _RETHINK_TRIGGERS.items():
        rethinking = [block for block in blocks if names_it(block) and "rethink" in block]
        if not rethinking:
            gaps.append(f"fix-bug: no paragraph or list item rethinks at {trigger} (R8.1)")
        elif not any(_in_one_clause(block, _STOP, _FIXING) for block in rethinking):
            gaps.append(
                f"fix-bug: the paragraph or list item that rethinks at {trigger} does not stop the fix rounds (R8.1)"
            )
    if not any(_DISPATCHES_THE_RETHINKER.search(block) or _follows_the_rethink_link(block) for block in blocks):
        gaps.append(f"fix-bug: nothing dispatches the rethinker or says to follow {RETHINK_LINK_TARGET} (R8.1)")
    asking = [block for block in blocks if _ASKS_THE_USER.search(block)]
    asking += _escalation_blocks(skill)  # its heading already says "stop and ask the user when"
    if not any(_is_two_failed_reviews(block) and "rethink" in block for block in asking):
        gaps.append("fix-bug: nothing asks the user when the fix still fails two more reviews after its rethink (R8.4)")
    return gaps


def _fix_bug_escalation_gaps(skill: Path) -> list[str]:
    """Return each fix-bug instruction that still asks the user at a rethink trigger instead of rethinking (a sentence
    that escalates there, or one condition of the Escalation list), and a gap when the Escalation list no longer asks
    the user when the baseline check is red."""
    statements = [statement.strip() for block in _blocks(skill) for statement in _STATEMENT_END.split(block)]
    gaps = [
        f"fix-bug: escalates at a rethink trigger instead of rethinking: {statement!r} (R8.1)"
        for statement in statements
        if _names_a_rethink_trigger(statement) and _ASKS_THE_USER.search(statement) and "rethink" not in statement
    ]
    escalation = _escalation_blocks(skill)
    conditions = [condition.strip() for item in escalation for condition in _CLAUSE_BREAK.split(item)]
    gaps += [
        f"fix-bug Escalation: asks the user at a rethink trigger instead of rethinking: {condition!r} (R8.1)"
        for condition in conditions
        if _names_a_rethink_trigger(condition) and "rethink" not in condition
    ]
    if not any("baseline" in item and _RED.search(item) for item in escalation):
        gaps.append("fix-bug Escalation: no longer asks the user when the baseline check is red for unrelated reasons")
    return gaps


# The parallel question (R3.2, R3.6). These run on blocks from _blocks, in Phase 2 (and Phase 0 for the resume).
_PARALLEL = re.compile(r"\bparallel\b")
_ASKS = re.compile(r"\bask(?:s|ed|ing)?\b")
_APPROVES = re.compile(r"\bapprov\w*")
_SEPARATELY = re.compile(r"\bseparate(?:ly)?\b|\bof its own\b|\bown question\b|\bapart\b|\bon its own\b")
_TWO_OR_MORE_PARTITIONS = re.compile(
    r"\b(?:two|2) or more partitions\b|\bmore than one partition\b|\b(?:several|multiple) partitions\b"
)
_CONDITION = re.compile(r"\b(?:when|whenever|if|only)\b")
_AT_THE_SAME_TIME = re.compile(r"\bat the same time\b|\bconcurrent\w*|\bsimultaneous\w*|\bat once\b")
_END_TO_END = re.compile(r"\bend[- ]to[- ]end\b|\be2e\b")
_SAYS_WHY = re.compile(r"\b(?:say|says|saying|explain\w*|tell\w*|state\w*|give\w*)\b(?: \S+){0,4} (?:why|the reason)\b")
_RECORDS = re.compile(r"\b(?:record|writ|sav|stor|set|keep|put)\w*")
_PARALLEL_HEADER_LINE = "**parallel:**"
_RESUMED = re.compile(r"\bresum\w*")
_REUSES_THE_ANSWER = re.compile(
    r"\b(?:keep|read|use|reuse|follow|honou?r|take|respect)s?\b|\bwithout asking\b|\b(?:not|never) ask\w*\b"
)

# What develop-feature must say about the parallel question, each in one paragraph or list item of Phase 2 that
# asks about building in parallel.
_PARALLEL_QUESTION_STEPS: dict[str, Callable[[str], bool]] = {
    "R3.2 asking it as a question of its own, apart from the plan approval": lambda block: (
        _SEPARATELY.search(block) is not None
    ),
    "R3.2 asking only when a slice has a wave of two or more partitions": lambda block: (
        "wave" in block and _TWO_OR_MORE_PARTITIONS.search(block) is not None and _CONDITION.search(block) is not None
    ),
    "R3.2 offering parallel only when the partitions' checks and end-to-end tests can run at the same time": (
        lambda block: (
            "only" in block
            and "check" in block
            and _END_TO_END.search(block) is not None
            and _AT_THE_SAME_TIME.search(block) is not None
        )
    ),
    "R3.2 saying why when it does not offer parallel": lambda block: _SAYS_WHY.search(block) is not None,
    "R3.6 recording the answer in the tasks.md header line '- **Parallel:**'": lambda block: (
        _PARALLEL_HEADER_LINE in block and "tasks.md" in block and _RECORDS.search(block) is not None
    ),
}


def _is_the_parallel_question(block: str) -> bool:
    """Return whether a block asks the user whether to build partitions in parallel."""
    return _PARALLEL.search(block) is not None and _ASKS.search(block) is not None


def _keeps_the_answer_on_resume(block: str) -> bool:
    """Return whether a block says a resumed session keeps (reads) the recorded parallel answer, not asking again."""
    return (
        _RESUMED.search(block) is not None
        and _PARALLEL.search(block) is not None
        and _REUSES_THE_ANSWER.search(block) is not None
    )


def _parallel_question_gaps(skill: Path) -> list[str]:
    """Return one message per part of R3.2 and R3.6 that develop-feature's Phase 2 (or Phase 0, for the resume)
    lacks."""
    plan = _section_blocks(skill, "Phase 2: Plan")
    if not plan:
        return ["develop-feature: SKILL.md has no '## Phase 2: Plan' section"]
    first_approval = next((index for index, block in enumerate(plan) if _APPROVES.search(block)), len(plan))
    questions = [block for block in plan[first_approval:] if _is_the_parallel_question(block)]
    gaps = (
        []
        if questions
        else ["develop-feature Phase 2: no paragraph or list item, after the plan approval, asks about parallel"]
    )
    gaps += [
        f"develop-feature Phase 2: the parallel question does not cover {label}"
        for label, says_it in _PARALLEL_QUESTION_STEPS.items()
        if not any(says_it(block) for block in questions)
    ]
    resume_blocks = plan + _section_blocks(skill, "Phase 0: Prepare")
    if not any(_keeps_the_answer_on_resume(block) for block in resume_blocks):
        gaps.append("develop-feature: no paragraph or list item says a resumed session keeps the parallel answer")
    return gaps


class DevelopFeatureFlowTest(unittest.TestCase):
    maxDiff = None  # a failure lists every gap, not the first one

    def test_develop_feature_overrides_model_and_effort_where_agreed(self) -> None:
        """R1.2, R1.3, R1.4: develop-feature runs fix rounds, high-risk tasks and the whole-feature spec review
        in opus/high, and every other dispatch omits the Agent tool's model and effort."""
        section = read_section(DEVELOP_FEATURE_DIR / "SKILL.md", "Model and effort")
        rows = [line.strip().lower() for line in section.splitlines() if line.strip().startswith("|")]
        rows = [row for row in rows if not re.fullmatch(r"[|\s:-]+", row)]
        expected_rows = {
            "R1.2 fix round of the test-writer or implementer": lambda row: (
                "fix round" in row and "test-writer" in row and "implementer" in row
            ),
            "R1.3 test-writer, implementer and spec-reviewer of a high task": lambda row: (
                "fix round" not in row
                and "whole feature" not in row
                and re.search(r"`?high`?[- ]risk|risk[^|]*`?high`?|`high` task|high task", row) is not None
                and all(agent in row for agent in ("test-writer", "implementer", "spec-reviewer"))
            ),
            "R1.4 spec-reviewer over the whole feature": lambda row: "whole feature" in row and "spec-reviewer" in row,
        }

        missing = []
        if not section:
            missing.append("SKILL.md has no '## Model and effort' section")
        for label, matches in expected_rows.items():
            matching = [row for row in rows if matches(row)]
            if not matching:
                missing.append(f"no table row for {label}")
            elif not any(_says_opus_high(row) for row in matching):
                missing.append(f"the row for {label} does not say opus and high")
        lowered = section.lower()
        if not ("omit" in lowered and "model" in lowered and "effort" in lowered and "frontmatter" in lowered):
            missing.append("the section does not say every other dispatch omits model and effort (frontmatter applies)")
        dispatch_prompts = (DEVELOP_FEATURE_DIR / "reference" / "dispatch-prompts.md").read_text(encoding="utf-8")
        if "Model and effort" not in dispatch_prompts:
            missing.append("reference/dispatch-prompts.md does not refer to 'Model and effort'")

        self.assertEqual(missing, [])

    def test_develop_feature_rethinks_a_stuck_task(self) -> None:
        """R1.2, R8.1, R8.2, R8.3, R8.4: develop-feature's `## Rethink` section stops the fix rounds at a task's
        fifth failed review or the third failure of the same review and dispatches the rethinker; keeps an attempt
        the rethinker sets aside in a git stash, untracked files included, never discarding it, and builds the task
        again from the rethinker's instructions, every later test-writer and implementer dispatch running on opus at
        high (in that block or a Model and effort row naming the rethink); on a PLAN CHANGE proposes it and waits for
        the user, and writes the approved edit only after stashing the attempt or keeps the plan documents out of the
        stash; and asks the user when the task still fails two more reviews. The Escalation list no longer asks the
        user at either trigger (the same review failing three times included), but still asks after the rethink's
        two extra failures, and reference/dispatch-prompts.md has a fenced `## rethinker` prompt, named in its
        Contents, that passes the review findings and asks for the RETHINK report."""
        skill = DEVELOP_FEATURE_DIR / "SKILL.md"
        prompts = DEVELOP_FEATURE_DIR / "reference" / "dispatch-prompts.md"

        gaps = _rethink_gaps(skill) + _after_rethink_gaps(skill)
        gaps += _escalation_gaps(skill) + _rethinker_prompt_gaps(prompts)

        self.assertEqual(gaps, [])

    def test_develop_feature_asks_about_parallel_partitions_once(self) -> None:
        """R3.2, R3.6: after the plan is approved, develop-feature's Phase 2 asks, as a question of its own and only
        when some slice has a wave of two or more partitions, whether to build them in parallel; it offers parallel
        only when those partitions' checks and end-to-end tests can run at the same time on the machine and otherwise
        says why; it records the answer in tasks.md's `- **Parallel:**` header line, and a resumed session keeps that
        answer instead of asking again."""
        gaps = _parallel_question_gaps(DEVELOP_FEATURE_DIR / "SKILL.md")

        self.assertEqual(gaps, [])


class OtherFlowsTest(unittest.TestCase):
    maxDiff = None  # a failure lists every gap, not the first one

    def test_other_flows_override_model_and_effort_where_agreed(self) -> None:
        """R1.2, R1.3, R1.4: fix-bug, reviewing-pull-requests and migrate-code pass `model: opus` and `effort: high`
        in the paragraph or list item of each dispatch develop-feature's Model and effort agrees on (every fix round
        or retry, a high-risk bug's first attempts and spec review, a spec review over a whole pull request); fix-bug
        and reviewing-pull-requests omit both parameters everywhere else, and fix-bug links to that section."""
        expected = {
            "fix-bug": {
                "R1.2 every fix round of the test-writer or implementer": lambda block: (
                    _ANY_FIX_ROUND.search(block) is not None and "test-writer" in block and "implementer" in block
                ),
                "R1.3 the first attempts of the test-writer and implementer on a high-risk bug": (
                    _is_about_first_attempts_on_a_high_risk_bug
                ),
                "R1.3 the spec-reviewer on a high-risk bug": lambda block: (
                    _HIGH_RISK.search(block) is not None and "spec-reviewer" in block
                ),
            },
            "reviewing-pull-requests": {
                "R1.4 the spec-reviewer over the whole pull request": lambda block: (
                    "spec-reviewer" in block and _WHOLE_PULL_REQUEST.search(block) is not None
                ),
            },
            "migrate-code": {
                "R1.2 the implementer's retries after a failed per-file verify": lambda block: (
                    _RETRY.search(block) is not None
                ),
                "R1.4 the per-batch spec-reviewer": lambda block: "spec-reviewer" in block and "batch" in block,
            },
        }
        omit_elsewhere = ("fix-bug", "reviewing-pull-requests")

        missing = []
        for skill, overrides in expected.items():
            blocks = _blocks(SKILLS_DIR / skill / "SKILL.md")
            missing += _override_gaps(skill, blocks, overrides)
            if skill in omit_elsewhere and not any(_says_other_dispatches_omit_both(block) for block in blocks):
                missing.append(f"{skill}: no paragraph or list item says to omit model and effort (frontmatter wins)")
        fix_bug = (SKILLS_DIR / "fix-bug" / "SKILL.md").read_text(encoding="utf-8")
        if f"]({MODEL_AND_EFFORT_LINK_TARGET})" not in fix_bug:
            missing.append(f"fix-bug: no Markdown link to {MODEL_AND_EFFORT_LINK_TARGET}")

        self.assertEqual(missing, [])

    def test_fix_bug_rethinks_a_stuck_fix(self) -> None:
        """R8.1, R8.4: fix-bug, at the fifth failed review or the third failure of the same review, stops the fix
        rounds and rethinks, dispatching the rethinker or saying to follow develop-feature's Rethink section through a
        link to it; it asks the user only when the fix still fails two more reviews after its rethink, so no sentence
        and no Escalation item asks the user at either trigger without the rethink; and its Escalation list still asks
        the user when the baseline check is red."""
        skill = SKILLS_DIR / "fix-bug" / "SKILL.md"

        gaps = _fix_bug_rethink_gaps(skill) + _fix_bug_escalation_gaps(skill)

        self.assertEqual(gaps, [])


if __name__ == "__main__":
    unittest.main()
