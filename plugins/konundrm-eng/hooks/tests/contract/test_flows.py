"""Contract tests for the flows the orchestrating skills describe (skills/*/SKILL.md and their references)."""

from __future__ import annotations

import re
import unittest
from collections.abc import Callable
from pathlib import Path

from .plugin_files import SKILLS_DIR, read_frontmatter, read_section

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


# The partition session (R3.3). These run on blocks from _blocks that are about a session started for one partition.
_PARTITION_ARGUMENT = re.compile(r"--partition\s+p<\w+>", re.IGNORECASE)
_PARTITION_SESSION = re.compile(r"--partition\b|\bpartition sessions?\b")
_TASK_LOOP = re.compile(r"\bphase 3\b|\btask loop\b")
_ONLY = re.compile(r"\bonly\b")
_OTHER_PARTITION = re.compile(r"\b(?:an)?other partitions?\b|\bother partitions'")
_PARTITION_REPORT = re.compile(r"\bevidence/p<\w+>\.md\b")
_NEVER_PUSHES = re.compile(r"\b(?:never|not|no|nor)\b(?: \S+){0,4} push")
_PLAN_CHANGE = re.compile(r"\bplan change\b")
_BLOCKED = re.compile(r"\bblocked:")
# The task order comes from the level-3 `### Partitions` table, one per slice, so the session must name the slice that
# holds its partition. A level-2 `## Partitions` heading exists in no plan document.
_PARTITIONS_TABLE = re.compile(r"(?<!#)###\s*partitions\b")
_LEVEL_2_PARTITIONS = re.compile(r"(?<!#)##\s*partitions\b")
_SLICE_OF_THE_PARTITION = re.compile(
    r"\bslice\b(?: \S+){0,6} (?:p<\w+>|(?:its|your|this|that|the) partition\b)|\b(?:p<\w+>|partition)'s slice\b"
)


def _never_edits_the_plan(block: str) -> bool:
    """Return whether one sentence of a block forbids editing design.md, requirements.md and other partitions' tasks."""
    return any(
        _NEGATION.search(sentence) is not None
        and "design.md" in sentence
        and "requirements.md" in sentence
        and _OTHER_PARTITION.search(sentence) is not None
        for sentence in _SENTENCE_END.split(block)
    )


def _follows_its_slice_partitions_table(block: str) -> bool:
    """Return whether a block builds only the partition's tasks through Phase 3, and one of its sentences takes them
    from the `### Partitions` table of the slice that holds the partition."""
    return (
        _ONLY.search(block) is not None
        and _TASK_LOOP.search(block) is not None
        and any(
            _PARTITIONS_TABLE.search(sentence) is not None and _SLICE_OF_THE_PARTITION.search(sentence) is not None
            for sentence in _SENTENCE_END.split(block)
        )
    )


def _never_pushes(block: str) -> bool:
    """Return whether one sentence of a block forbids pushing."""
    return any(_NEVER_PUSHES.search(sentence) is not None for sentence in _SENTENCE_END.split(block))


# What develop-feature must say about a partition session, each in one paragraph or list item about that session.
_PARTITION_SESSION_RULES: dict[str, Callable[[str], bool]] = {
    "building only its partition's tasks through the Phase 3 task loop": lambda block: (
        _ONLY.search(block) is not None and _TASK_LOOP.search(block) is not None
    ),
    "taking those tasks from the ### Partitions table of the slice that holds P<k>": (
        _follows_its_slice_partitions_table
    ),
    "never editing design.md, requirements.md or another partition's tasks": _never_edits_the_plan,
    "leaving its report in specs/<NNN-slug>/evidence/P<k>.md": lambda block: (
        _PARTITION_REPORT.search(block) is not None
    ),
    "never pushing (the main session integrates its branch)": _never_pushes,
    "stopping with a BLOCKED: line on a PLAN CHANGE instead of editing the plan": lambda block: (
        _PLAN_CHANGE.search(block) is not None and _BLOCKED.search(block) is not None
    ),
}


def _partition_session_gaps(skill: Path) -> list[str]:
    """Return one message per part of R3.3's partition session that develop-feature's SKILL.md lacks."""
    gaps = []
    if not _PARTITION_ARGUMENT.search(read_frontmatter(skill).get("argument-hint", "")):
        gaps.append("develop-feature: the frontmatter argument-hint does not mention --partition P<n>")
    blocks = _blocks(skill)
    sessions = [block for block in blocks if _PARTITION_SESSION.search(block)]
    if any(_LEVEL_2_PARTITIONS.search(block) for block in blocks):
        gaps.append("develop-feature: refers to a ## Partitions heading; the plan's table is ### Partitions")
    gaps += [
        f"develop-feature: no paragraph or list item about a partition session says {label}"
        for label, says_it in _PARTITION_SESSION_RULES.items()
        if not any(says_it(block) for block in sessions)
    ]
    return gaps


# The main session's side of a parallel wave (R3.3, R9.2). These run on blocks of the `## Parallel partitions` section.
_WORKTREE_ADD_OUTSIDE = re.compile(r"\bgit worktree add \.\./\S*worktrees/")
_WORKTREE_ADD_ELSEWHERE = re.compile(r"\bgit worktree add (?!\.\./)")
_OUTSIDE_THE_PROJECT = re.compile(r"\boutside\b(?: \S+){0,3} (?:checkout|project|repo\w*)\b")
_WAVE_BRANCH = re.compile(r"(?<![\w/])wave/\S+")
_FIRST_PARTITION = re.compile(r"\bfirst partition\b")
_IN_THE_MAIN_SESSION = re.compile(r"\b(?:here|main session|this session|feature branch)\b")
_THE_OTHER_PARTITIONS = re.compile(
    r"\bexcept the first\b|\bother partitions?\b|\bthe others\b|\bthe rest\b|\beach of the others\b"
)
_SESSION = re.compile(r"\bsessions?\b")
_ONE_AT_A_TIME = re.compile(r"\bone (?:partition )?at a time\b|\bone by one\b|\bone after (?:the )?other\b")
_CHERRY_PICK = re.compile(r"\bcherry-pick\b")
_MERGE_BASE = re.compile(r"\bmerge-base\b")
# Picking up to the branch's tip, or naming the report, keeps the partition's report commit in the range.
_UP_TO_THE_BRANCH_OR_REPORT = re.compile(r"\.\.(?:<[\w -]*branch>|wave/)|\breport\b")
_CHECK = re.compile(r"\bcheck\b")
_AFTER_A_PARTITION = re.compile(r"\b(?:after|each|every)\b(?: \S+){0,3} partition\b")
_REVIEWED = re.compile(r"\breview\w*")
_TASK_LINE = re.compile(r"\btask:")
_FEAT = re.compile(r"\bfeat\b")
_REFACTOR = re.compile(r"\brefactor\b")
_AT_THE_END = re.compile(
    r"\bafter the last\b|\bat the end\b|\blast partition\b|\bfinally\b|\bonce (?:all|every)\b|\bwhole wave\b"
)
_ACROSS_PARTITIONS = re.compile(r"\bbetween partitions\b|\bacross\b|\bwave\b|<wave-base>")
_WORKTREE_REMOVE = re.compile(r"\bgit worktree remove\b")
_NEVER_FORCE = re.compile(r"\b(?:never|not|no|without)\b(?: \S+){0,3} --force\b")
_FORCED_REMOVE = re.compile(r"\bgit worktree remove (?:\S+ )?(?:--force|-f)\b")
_DELETES_THE_BRANCH = re.compile(r"\bgit branch (?:-d|--delete)\b|\bdelete\w* (?:its|the|each|that) (?:\S+ )?branch\b")
_ONLY_ONCE = re.compile(r"\b(?:once|only|after|when|until)\b")
_EVERY_TASK_COMMIT = re.compile(r"\b(?:every|all|each)\b(?: \S+){0,4} (?:tasks?|task commits?)\b")
_FINDS_COMMITS_BY_TASK_LINE = re.compile(r"--grep\b|\bgit log\b")

# What develop-feature's `## Parallel partitions` section must say, each in one of its paragraphs or list items.
_PARALLEL_PARTITIONS_RULES: dict[str, Callable[[str], bool]] = {
    "R9.2 creating each worktree outside the project with `git worktree add ../<repo>-worktrees/...`": lambda b: (
        _WORKTREE_ADD_OUTSIDE.search(b) is not None and _OUTSIDE_THE_PROJECT.search(b) is not None
    ),
    "R3.3 giving each partition worktree a branch under wave/": lambda b: _WAVE_BRANCH.search(b) is not None,
    "R3.3 building the wave's first partition in the main session": lambda b: (
        _FIRST_PARTITION.search(b) is not None and _IN_THE_MAIN_SESSION.search(b) is not None
    ),
    "R3.3 building each other partition in its own session and worktree": lambda b: (
        _THE_OTHER_PARTITIONS.search(b) is not None and _SESSION.search(b) is not None and "worktree" in b
    ),
    "R3.3 integrating one partition at a time": lambda b: _ONE_AT_A_TIME.search(b) is not None,
    "R3.3 cherry-picking a partition's commits, its report included, from the merge-base": lambda b: (
        _CHERRY_PICK.search(b) is not None
        and _MERGE_BASE.search(b) is not None
        and _UP_TO_THE_BRANCH_OR_REPORT.search(b) is not None
    ),
    "R3.3 running the full check after each partition": lambda b: (
        _CHECK.search(b) is not None
        and (_ONE_AT_A_TIME.search(b) is not None or _AFTER_A_PARTITION.search(b) is not None)
    ),
    "R3.3 reviewing an integration fix and committing it with its task's Task: line, typed feat or refactor": (
        lambda b: (
            _REVIEWED.search(b) is not None
            and _TASK_LINE.search(b) is not None
            and _FEAT.search(b) is not None
            and _REFACTOR.search(b) is not None
        )
    ),
    "R3.3 a cross code review of the whole wave at the end": lambda b: (
        "code-review" in b and _AT_THE_END.search(b) is not None and _ACROSS_PARTITIONS.search(b) is not None
    ),
    "R3.3 removing worktrees with `git worktree remove`, never --force": lambda b: (
        _WORKTREE_REMOVE.search(b) is not None and _NEVER_FORCE.search(b) is not None
    ),
    "R3.3 deleting a partition branch only once every one of its task commits is integrated": lambda b: (
        _DELETES_THE_BRANCH.search(b) is not None
        and _ONLY_ONCE.search(b) is not None
        and _EVERY_TASK_COMMIT.search(b) is not None
    ),
    "R3.3 finding a task's commits by its Task: line": lambda b: (
        _TASK_LINE.search(b) is not None and _FINDS_COMMITS_BY_TASK_LINE.search(b) is not None
    ),
}


def _parallel_partitions_gaps(skill: Path) -> list[str]:
    """Return one message per part of R3.3 and R9.2 that develop-feature's `## Parallel partitions` section lacks,
    plus one per instruction that adds a worktree inside the project or forces its removal."""
    blocks = _section_blocks(skill, "Parallel partitions")
    if not blocks:
        return ["develop-feature: SKILL.md has no '## Parallel partitions' section"]
    gaps = [
        f"develop-feature Parallel partitions: no paragraph or list item covers {label}"
        for label, says_it in _PARALLEL_PARTITIONS_RULES.items()
        if not any(says_it(block) for block in blocks)
    ]
    gaps += [
        f"develop-feature Parallel partitions: adds a worktree that is not under ../: {block[:80]!r}"
        for block in blocks
        if _WORKTREE_ADD_ELSEWHERE.search(block)
    ]
    gaps += [
        f"develop-feature Parallel partitions: forces a worktree removal: {block[:80]!r}"
        for block in blocks
        if _FORCED_REMOVE.search(block)
    ]
    return gaps


# An integration conflict outside the plan's boxes (R3.4). These run on blocks of `## Parallel partitions` and of
# `## Escalation`.
_CONFLICT = re.compile(r"\bconflict")
_BOTH_SIDES = re.compile(r"\bboth sides\b")
_OTHER_CONFLICT = re.compile(
    r"\bother conflicts?\b|\bconflicts?\b(?: \S+){0,4} (?:outside|beyond|elsewhere)\b"
    r"|\bconflict\w*(?: \S+){0,3} other files?\b"
)
_NOT_INDEPENDENT = re.compile(r"\bindependen")
_CHERRY_PICK_ABORT = re.compile(r"\bgit cherry-pick --abort\b")
# Reporting what conflicted: a report verb, then "which", "the" or "each" and the partition or the files.
_REPORTS_WHAT_CONFLICTED = re.compile(
    r"\b(?:report|tell|show|nam|list|say|relay)\w*\b(?: \S+){0,6} (?:which|what|the|its|each)\b(?: \S+){0,2} "
    r"(?:partitions?|files?)\b"
)
_FILES = re.compile(r"\bfiles?\b")
_BLOCKED_LINE = re.compile(r"\bblocked:")
_STOPS = re.compile(r"\b(?:stop|halt|wait)\w*")
_USER_GO_AHEAD = re.compile(
    r"\bgo-ahead\b|\bapprov\w*|\buser's (?:yes|answer|ok)\b|\buser (?:agrees|approves|says)\b"
    r"|\b(?:wait|ask)\w*(?: \S+){0,4} user\b"
)
_REDOES_THE_CHERRY_PICK = re.compile(r"\b(?:redo|re-?run|repeat|again)\b")
_CONFLICTED_FILE = re.compile(r"\bconflicted files?\b|\beach file\b|\bconflicting files?\b")
_INTEGRATION = re.compile(r"\bintegrat|\bcherry-pick\b|\bpartition")
_OUTSIDE_THE_PLAN = re.compile(r"\boutside\b|\bbeyond\b|\bother than\b|\bnot (?:in|on|about)\b|\bother\b")


def _reports_the_partition_and_files(sentence: str) -> bool:
    """Return whether one sentence reports which partition and which files conflicted."""
    return (
        _REPORTS_WHAT_CONFLICTED.search(sentence) is not None
        and "partition" in sentence
        and _FILES.search(sentence) is not None
    )


def _hands_off_after_the_go_ahead(block: str) -> bool:
    """Return whether a block hands the conflict to the implementer only after naming the user's go-ahead."""
    go_ahead = _USER_GO_AHEAD.search(block)
    return _CONFLICT.search(block) is not None and go_ahead is not None and "implementer" in block[go_ahead.end() :]


# What develop-feature's `## Parallel partitions` section must say about integration conflicts, each in one of its
# paragraphs or list items.
_INTEGRATION_CONFLICT_RULES: dict[str, Callable[[str], bool]] = {
    "a conflict in tasks.md keeps both sides' boxes and Rounds lines": lambda b: (
        _CONFLICT.search(b) is not None and "tasks.md" in b and _BOTH_SIDES.search(b) is not None
    ),
    "any other conflict means the partitions were not as independent as planned": lambda b: (
        _OTHER_CONFLICT.search(b) is not None and _NOT_INDEPENDENT.search(b) is not None
    ),
    "any other conflict aborts the cherry-pick with `git cherry-pick --abort`": lambda b: (
        _OTHER_CONFLICT.search(b) is not None and _CHERRY_PICK_ABORT.search(b) is not None
    ),
    "any other conflict is reported, naming the partition and the files": lambda b: (
        _OTHER_CONFLICT.search(b) is not None
        and any(_reports_the_partition_and_files(s) for s in _SENTENCE_END.split(b))
    ),
    "any other conflict stops with a `BLOCKED:` line": lambda b: (
        _OTHER_CONFLICT.search(b) is not None and _BLOCKED_LINE.search(b) is not None and _STOPS.search(b) is not None
    ),
    "the conflict reaches the implementer only after the user's go-ahead": _hands_off_after_the_go_ahead,
    "after the go-ahead, redoing the cherry-pick and handing each conflicted file, with both sides, to the "
    "implementer or the test-writer for a test": lambda b: (
        _CONFLICT.search(b) is not None
        and _USER_GO_AHEAD.search(b) is not None
        and _CHERRY_PICK.search(b) is not None
        and _REDOES_THE_CHERRY_PICK.search(b) is not None
        and _CONFLICTED_FILE.search(b) is not None
        and _BOTH_SIDES.search(b) is not None
        and "implementer" in b
        and "test-writer" in b
    ),
    "reviewing the conflict's resolution like any integration fix": lambda b: (
        _CONFLICT.search(b) is not None
        and _USER_GO_AHEAD.search(b) is not None
        and "implementer" in b
        and _REVIEWED.search(b) is not None
    ),
}


def _integration_conflict_gaps(skill: Path) -> list[str]:
    """Return one message per part of R3.4 that develop-feature's `## Parallel partitions` section lacks, and one
    when its `## Escalation` list does not name an integration conflict outside the plan's boxes."""
    blocks = _section_blocks(skill, "Parallel partitions")
    if not blocks:
        return ["develop-feature: SKILL.md has no '## Parallel partitions' section"]
    gaps = [
        f"develop-feature Parallel partitions: no paragraph or list item covers {label} (R3.4)"
        for label, says_it in _INTEGRATION_CONFLICT_RULES.items()
        if not any(says_it(block) for block in blocks)
    ]
    if not any(
        _CONFLICT.search(block) and _INTEGRATION.search(block) and _OUTSIDE_THE_PLAN.search(block)
        for block in _escalation_blocks(skill)
    ):
        gaps.append("develop-feature Escalation: no item names an integration conflict outside the plan's boxes (R3.4)")
    return gaps


# Resuming an unfinished parallel wave (R3.5). These run on blocks of `## Phase 0: Prepare` (the partition session's
# own paragraph left out), `## Phase 2: Plan` and `## Parallel partitions`.
_WAVE = re.compile(r"\bwaves?\b")
_FINDS_A_WAVE = re.compile(r"\bgit worktree list\b|\bgit branch --list\b|(?<![\w/])wave/")
_UNFINISHED = re.compile(
    r"\bunfinished\b|\bnot (?:yet )?(?:finished|done|integrated)\b|\bincomplete\b|\bin progress\b|\bopen wave\b"
)
_FINISH = re.compile(r"\bfinish\w*")
_FIRST_OR_BEFORE = re.compile(r"\bfirst\b|\bbefore\b")
_INTEGRATED = re.compile(r"\bintegrat\w*")
_NOT_BY_SHAS_OR_BOXES = re.compile(
    r"\b(?:never|not|rather than|instead of)\b(?: \S+){0,4} (?:shas?|boxes|checkbox\w*|checked|branch names?)\b"
)
_SKIP = re.compile(r"\bskip\w*")
_ALREADY_HERE = re.compile(r"\balready\b|\bits commit here\b")
_RESTARTS = re.compile(r"\bre-?start\w*|\brelaunch\w*|\breopen\w*|\bstart\w*\b(?: \S+){0,4} again\b")
_NOT_RUNNING = re.compile(
    r"\bno longer\b|\bnot (?:running|open)\b|\bno (?:\S+ )?session\b|\bstopped\b|\bclosed\b|\bdied\b|\bgone\b"
)
_ITS_WORKTREE = re.compile(r"\bworktree\b|\bfolder\b|\bthere\b")
_SAME_PARTITION_PROMPT = re.compile(r"--partition\b|\b(?:same|step 2|its) (?:prompt|command)\b")
# "never build", "do not build", "don't ever build": the prohibition itself, not any negation word in the sentence.
_FORBIDS_BUILDING = re.compile(r"\b(?:never|do not|don't)(?: \S+){0,2} build\b")
_ANOTHER_PARTITIONS_TASKS = re.compile(r"\banother partition's tasks\b|\btasks of another partition\b")
_NO_PARALLEL_LINE = re.compile(r"\b(?:no|without|lacks?|missing)\b(?: \S+){0,4} (?:\*\*parallel:\*\*|parallel\b)")


def _never_builds_another_partition_here(block: str) -> bool:
    """Return whether one sentence of a block forbids the main session to build another partition's tasks.

    The prohibition ("never build", "do not build") and "another partition's tasks" must share one sentence, so a
    sentence that only happens to hold a negation, "build" and "other partition" (Phase 0's "nothing is left to
    build") does not satisfy it.
    """
    return any(
        _FORBIDS_BUILDING.search(sentence) is not None
        and _ANOTHER_PARTITIONS_TASKS.search(sentence) is not None
        and _IN_THE_MAIN_SESSION.search(sentence) is not None
        for sentence in _SENTENCE_END.split(block)
    )


def _finishes_the_found_wave_first(block: str) -> bool:
    """Return whether a block, about resuming, finds an unfinished wave and, in one sentence, finishes it first."""
    return (
        _RESUMED.search(block) is not None
        and _FINDS_A_WAVE.search(block) is not None
        and _UNFINISHED.search(block) is not None
        and any(
            _WAVE.search(sentence) is not None
            and _FINISH.search(sentence) is not None
            and _FIRST_OR_BEFORE.search(sentence) is not None
            for sentence in _SENTENCE_END.split(block)
        )
    )


def _judges_integration_by_task_commits(block: str) -> bool:
    """Return whether one statement of a block judges what is integrated by the `Task:` commit, not by boxes or SHAs.

    Splits on _STATEMENT_END, not _SENTENCE_END, because the colon of `Task:` would cut the statement in two.
    """
    return any(
        _INTEGRATED.search(statement) is not None
        and _TASK_LINE.search(statement) is not None
        and _NOT_BY_SHAS_OR_BOXES.search(statement) is not None
        for statement in _STATEMENT_END.split(block)
    )


def _skips_commits_already_integrated(block: str) -> bool:
    """Return whether one sentence of a block skips the cherry-pick of a commit whose task already has its commit."""
    return any(
        _CHERRY_PICK.search(sentence) is not None
        and _SKIP.search(sentence) is not None
        and "task" in sentence
        and _ALREADY_HERE.search(sentence) is not None
        for sentence in _SENTENCE_END.split(block)
    )


def _asks_when_the_parallel_line_is_missing(block: str) -> bool:
    """Return whether a block, about an approved plan, asks the parallel question when tasks.md lacks its line."""
    return _APPROVES.search(block) is not None and any(
        _NO_PARALLEL_LINE.search(sentence) is not None and _ASKS.search(sentence) is not None
        for sentence in _STATEMENT_END.split(block)
    )


# What develop-feature must say about resuming an unfinished wave, each in one paragraph or list item. The first three
# rules check their key words within one sentence, so unrelated words elsewhere in Phase 0 step 1 do not satisfy them.
_RESUMED_WAVE_RULES: dict[str, Callable[[str], bool]] = {
    "on resume, finding an unfinished wave (a wave/ worktree or branch) and finishing it first": (
        _finishes_the_found_wave_first
    ),
    "deciding what is integrated by each task's Task: commit, never by boxes, SHAs or branch names": (
        _judges_integration_by_task_commits
    ),
    "skipping, when integrating again, the commits whose task already has its commit here": (
        _skips_commits_already_integrated
    ),
    "restarting a partition session that no longer runs in its worktree with its --partition P<k> prompt": (
        lambda b: (
            _RESTARTS.search(b) is not None
            and _NOT_RUNNING.search(b) is not None
            and _ITS_WORKTREE.search(b) is not None
            and _SAME_PARTITION_PROMPT.search(b) is not None
        )
    ),
    "the main session never building another partition's tasks": _never_builds_another_partition_here,
}

# What Phase 0 must say, in one paragraph or list item, so that a resumed session that skips the approved plan's Phase 2
# still asks the parallel question it finds no answer to (R3.6).
_RESUMED_PARALLEL_ANSWER_RULE = (
    "asking the parallel question when the plan is Approved but tasks.md has no Parallel: line"
)


def _resumed_wave_gaps(skill: Path) -> list[str]:
    """Return one message per part of R3.5 that develop-feature's Phase 0, Phase 2 and Parallel partitions lack, and
    one when no block of Phase 0 (where a resumed session goes, skipping the approved Phase 2) asks the parallel
    question tasks.md has no answer to (R3.6)."""
    prepare = [
        block for block in _section_blocks(skill, "Phase 0: Prepare") if not block.startswith("**partition session")
    ]
    blocks = prepare + _section_blocks(skill, "Phase 2: Plan") + _section_blocks(skill, "Parallel partitions")
    gaps = [
        f"develop-feature: no paragraph or list item of Phase 0, Phase 2 or Parallel partitions covers {label} (R3.5)"
        for label, says_it in _RESUMED_WAVE_RULES.items()
        if not any(says_it(block) for block in blocks)
    ]
    if not any(_asks_when_the_parallel_line_is_missing(block) for block in prepare):
        gaps.append(
            f"develop-feature: no paragraph or list item of Phase 0 covers {_RESUMED_PARALLEL_ANSWER_RULE} (R3.6)"
        )
    return gaps


# A plan without partitions (R2.6). These run on sentences (split by _STATEMENT_END, which keeps "Parallel: yes" whole)
# of blocks from _blocks, so an unrelated sentence of the same paragraph cannot satisfy a rule.
# "Partitions" in the plural, so "depend on no other partition of the wave" is not about a plan without partitions.
_WITHOUT_PARTITIONS = re.compile(r"\b(?:no|without|lacks?|lacking)\b(?: \S+){0,3} (?:###\s*)?partitions\b")
_IN_ORDER = re.compile(
    r"\bone after (?:another|the other)\b|\bin (?:\w+ )?order\b|\bsequentially\b|\bin sequence\b|\bin turn\b"
)
# Each order is tied to its own noun within a few words, so "slices ... tasks in list order" cannot stand in for the
# slices' order, nor "slices one after another, each slice's tasks" for the tasks' order.
_SLICES_IN_SEQUENCE = re.compile(
    r"\bslices\b\S*(?: \S+){0,3} (?:one after (?:another|the other)|in sequence|sequentially|in turn)\b"
)
_TASKS_IN_ORDER = re.compile(r"\btasks\b\S*(?: \S+){0,3} in (?:\w+ )?order\b")
_IN_THIS_SESSION = re.compile(r"\b(?:this|the main|the same) session\b|\bhere\b")
_PARALLEL_QUESTION = re.compile(r"\bparallel question\b|\bask\w*(?: \S+){0,6} parallel\b")
_PARTITION_SESSIONS = re.compile(r"\bpartition sessions?\b")
_WORKTREES = re.compile(r"\bworktrees?\b")
_PARALLEL_YES = re.compile(r"\bparallel:(?:\*\*)? ?yes\b")
_PARALLEL_PARTITIONS_LINK = "(#parallel-partitions)"
_OTHERWISE = re.compile(r"\botherwise\b|\belse\b|\bparallel:(?:\*\*)? ?no\b")
_SINGLE_PARTITION = re.compile(r"\b(?:single|one|lone) partition\b")


def _sentences(block: str) -> list[str]:
    """Return the sentences of a block from `_blocks`, split where a statement ends (not at a colon)."""
    return _STATEMENT_END.split(block)


def _in_one_sentence(block: str, *patterns: re.Pattern[str]) -> bool:
    """Return whether one sentence of a block matches every pattern."""
    return any(all(pattern.search(sentence) for pattern in patterns) for sentence in _sentences(block))


# What develop-feature must say, each in one paragraph or list item about a plan whose slices have no `### Partitions`
# table, so a plan written by an earlier plugin version is built as before.
_PLAN_WITHOUT_PARTITIONS_RULES: dict[str, Callable[[str], bool]] = {
    "building its slices one after another": lambda block: _in_one_sentence(block, _SLICES_IN_SEQUENCE),
    "building each slice's tasks in list order": lambda block: _in_one_sentence(block, _TASKS_IN_ORDER),
    "building them in this session, through the Phase 3 task loop": lambda block: _in_one_sentence(
        block, _IN_THIS_SESSION, _TASK_LOOP
    ),
    "asking no parallel question": lambda block: _in_one_sentence(block, _NEGATION, _PARALLEL_QUESTION),
    "starting no partition sessions and no worktrees": lambda block: _in_one_sentence(
        block, _NEGATION, _PARTITION_SESSIONS, _WORKTREES
    ),
}


def _is_about_a_plan_without_partitions(block: str) -> bool:
    """Return whether one sentence of a block is about a plan (or its slices) that has no `### Partitions` table."""
    return any(
        _WITHOUT_PARTITIONS.search(sentence) is not None and ("plan" in sentence or "slice" in sentence)
        for sentence in _sentences(block)
    )


def _treats_a_slice_without_partitions_as_one(block: str) -> bool:
    """Return whether one sentence of a block treats a slice without a `### Partitions` table as a single partition."""
    return any(
        _WITHOUT_PARTITIONS.search(sentence) is not None
        and "slice" in sentence
        and _SINGLE_PARTITION.search(sentence) is not None
        for sentence in _sentences(block)
    )


def _task_loop_points_to_parallel_partitions(block: str) -> bool:
    """Return whether a block sends the `Parallel: yes` case to the `## Parallel partitions` section in one sentence,
    and in another (or the same) builds otherwise in list order."""
    return any(
        _PARALLEL_YES.search(sentence) is not None and _PARALLEL_PARTITIONS_LINK in sentence
        for sentence in _sentences(block)
    ) and _in_one_sentence(block, _OTHERWISE, _IN_ORDER)


def _plan_without_partitions_gaps(skill: Path) -> list[str]:
    """Return one message per part of R2.6 that develop-feature's SKILL.md lacks."""
    blocks = _blocks(skill)
    about = [block for block in blocks if _is_about_a_plan_without_partitions(block)]
    gaps = (
        []
        if about
        else ["develop-feature: no paragraph or list item is about a plan whose slices have no ### Partitions table"]
    )
    gaps += [
        f"develop-feature: no paragraph or list item about a plan without ### Partitions tables says {label}"
        for label, says_it in _PLAN_WITHOUT_PARTITIONS_RULES.items()
        if not any(says_it(block) for block in about)
    ]
    if not any(_treats_a_slice_without_partitions_as_one(block) for block in blocks):
        gaps.append("develop-feature: no sentence treats a slice without a ### Partitions table as a single partition")
    task_loop = _section_blocks(skill, "Phase 3: Task loop")
    if not any(_task_loop_points_to_parallel_partitions(block) for block in task_loop):
        gaps.append(
            "develop-feature Phase 3: no paragraph or list item sends Parallel: yes to "
            f"[Parallel partitions]{_PARALLEL_PARTITIONS_LINK} and otherwise builds in list order"
        )
    return gaps


# An open decision a subagent returns during the build (R5.2, R5.4). These run on blocks from _blocks that mention a
# decision, each rule within one sentence (_in_one_sentence) so an unrelated sentence cannot satisfy it.
_DECISION = re.compile(r"\bdecision")
_STATUS_DECISION = re.compile(r"\bstatus: ?decision\b")
_PAUSES = re.compile(r"\b(?:paus|hold)\w*")
_SUBAGENT = re.compile(r"\b(?:subagents?|dispatch\w*)\b")
_SHOWS = re.compile(r"\b(?:show|present|relay)\w*")
_USER = re.compile(r"\buser\b")
_OPTIONS = re.compile(r"\boptions?\b")
_ADVANTAGES = re.compile(r"\badvantages?\b")
_DISADVANTAGES = re.compile(r"\bdisadvantages?\b")
_RECOMMENDATION = re.compile(r"\brecommend\w*")
_WAITS = re.compile(r"\bwait\w*")
_CHOICE = re.compile(r"\b(?:choice|choos\w*|chos\w*|pick\w*)\b")
_RECORDS_CHOICE = re.compile(r"\b(?:record|writ)\w*")
_DECISION_FIELD = re.compile(r"\bdecision:")
_TASKS_MD = re.compile(r"\btasks\.md\b")
# The template's `(user | recommended)` or the decided `(user)` the orchestrator writes; either names who chose.
_CHOSEN_FORMAT = re.compile(r"\bdecision: ?<[^>]+> ?\(user(?: ?\| ?recommended)?\)")
_BELOW = re.compile(r"\bbelow\b")
_KEEPS = re.compile(r"\b(?:keep|stay|retain)\w*")
_SUMMARIES = re.compile(r"\bsummar(?:y|ies)\b")
_CITE = re.compile(r"\b(?:cit|quot)\w*")
_COMMIT = re.compile(r"\bcommit\b")
_THE_RECORD = re.compile(r"\b(?:decision|record|choice)")
_SAME_ROLE = re.compile(r"\bsame role\b")
_NEW = re.compile(r"\bnew\b")
_CHOICE_OR_DECISION = re.compile(r"\b(?:choice|decision|chosen)\b")
_ESCALATION_OR_BLOCKED = re.compile(r"\bescalat\w*|\bblocked\b")
_WRONG = re.compile(r"\bwrong\b")
_DESIGN_OR_PLAN = re.compile(r"\b(?:design|plan)\b")

# What develop-feature must say about a subagent's `Status: DECISION`, each in one sentence of a block about it.
_OPEN_DECISION_RULES: dict[str, tuple[re.Pattern[str], ...]] = {
    "R5.2 it pauses the task when a subagent returns Status: DECISION": (_STATUS_DECISION, _PAUSES),
    "R5.2 it dispatches no other subagent for the paused task": (_NEGATION, _SUBAGENT),
    "R5.2 it runs no fix round for it": (_NEGATION, _FIX_ROUND),
    "R5.2 it shows the user the options with their advantages, disadvantages and the recommendation": (
        _SHOWS,
        _USER,
        _OPTIONS,
        _ADVANTAGES,
        _DISADVANTAGES,
        _RECOMMENDATION,
    ),
    "R5.2 it waits for the user's choice": (_WAITS, _USER, _CHOICE),
    "R5.4 it records the choice in the task's - Decision: field in tasks.md": (
        _RECORDS_CHOICE,
        _DECISION_FIELD,
        _TASKS_MD,
    ),
    "R5.4 the record reads - Decision: <option> (user)": (_CHOSEN_FORMAT,),
    "R5.4 the options stay below the chosen line": (_KEEPS, _OPTIONS, _BELOW),
    "R5.4 summaries cite the recorded decision": (_SUMMARIES, _CITE),
    "R5.4 the record lands in the task's commit": (_THE_RECORD, _COMMIT),
    "R5.2 it sends the task back to a new subagent of the same role with the choice": (
        _SAME_ROLE,
        _NEW,
        _CHOICE_OR_DECISION,
    ),
    "R5.2 a Status: DECISION is not an escalation or BLOCKED": (_DECISION, _NEGATION, _ESCALATION_OR_BLOCKED),
    "R5.2 the design is not wrong, it left the choice open": (_NEGATION, _WRONG, _DESIGN_OR_PLAN),
}


def _open_decision_gaps(blocks: list[str]) -> list[str]:
    """Return one message per rule of `_OPEN_DECISION_RULES` that no block mentioning a decision states in one
    sentence."""
    about = [block for block in blocks if _DECISION.search(block)]
    return [
        f"develop-feature: no sentence about a subagent's open decision says {label}"
        for label, patterns in _OPEN_DECISION_RULES.items()
        if not any(_in_one_sentence(block, *patterns) for block in about)
    ]


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

    def test_a_partition_session_builds_only_its_partition(self) -> None:
        """R3.3: develop-feature's argument-hint offers `--partition P<n>`, and a session started with it builds only
        that partition's tasks through the Phase 3 task loop, never edits design.md, requirements.md or another
        partition's tasks, leaves its report in `specs/<NNN-slug>/evidence/P<k>.md`, never pushes (the main session
        integrates its branch), and stops with a `BLOCKED:` line for the main session on a PLAN CHANGE."""
        gaps = _partition_session_gaps(DEVELOP_FEATURE_DIR / "SKILL.md")

        self.assertEqual(gaps, [])

    def test_parallel_partitions_integrate_one_at_a_time(self) -> None:
        """R3.3, R9.2: develop-feature's `## Parallel partitions` section builds the wave's first partition in the main
        session and each other one in its own session, in a worktree on a `wave/` branch created outside the project
        with `git worktree add ../<repo>-worktrees/...`; integrates them one at a time by cherry-picking each branch's
        commits (its report included) from the merge-base, running the check after each; reviews an integration fix
        and commits it with its task's `Task:` line typed feat or refactor; runs a cross code review over the wave at
        the end; removes worktrees with `git worktree remove`, never `--force`; and deletes a partition branch only
        once every one of its task commits, found by `Task:` line, is integrated."""
        gaps = _parallel_partitions_gaps(DEVELOP_FEATURE_DIR / "SKILL.md")

        self.assertEqual(gaps, [])

    def test_an_integration_conflict_waits_for_the_user(self) -> None:
        """R3.4: in develop-feature's `## Parallel partitions` section, a conflict in tasks.md's boxes and Rounds lines
        keeps both sides, but any other conflict while integrating a partition means the partitions were not as
        independent as planned: the main session runs `git cherry-pick --abort`, reports which partition and which
        files, and stops with a `BLOCKED:` line; only after the user's go-ahead does it redo the cherry-pick and hand
        each conflicted file, with both sides, to the implementer (the test-writer for a test), reviewed like any
        integration fix. The `## Escalation` list also names an integration conflict outside the plan's boxes."""
        gaps = _integration_conflict_gaps(DEVELOP_FEATURE_DIR / "SKILL.md")

        self.assertEqual(gaps, [])

    def test_resume_finishes_an_unfinished_wave_first(self) -> None:
        """R3.5, R3.6: on resume with an unfinished parallel wave (a `wave/` worktree or branch of the feature),
        develop-feature finishes that wave before anything else; decides what is integrated by each task's `Task:`
        commit, not by boxes, SHAs or branch names, skipping on re-integration the commits whose task already has its
        commit here; restarts a partition session that no longer runs in its existing worktree with its
        `--partition P<k>` prompt; and never builds another partition's tasks in the main session (R3.5). A resumed
        session skips the approved plan's Phase 2, so Phase 0 itself asks the parallel question when the plan is
        Approved but tasks.md has no `- **Parallel:**` line yet (R3.6)."""
        gaps = _resumed_wave_gaps(DEVELOP_FEATURE_DIR / "SKILL.md")

        self.assertEqual(gaps, [])

    def test_plans_without_partitions_run_in_list_order(self) -> None:
        """R2.6: a plan written by an earlier plugin version, whose slices have no `### Partitions` table, is built as
        before: its slices one after another, each slice's tasks in list order, in this session through the Phase 3
        task loop, with no parallel question, no partition sessions and no worktrees; a slice without a Partitions
        table counts as a single partition, so a mixed plan still works; and the Phase 3 task loop sends the
        `Parallel: yes` case to `## Parallel partitions`, otherwise building in list order."""
        gaps = _plan_without_partitions_gaps(DEVELOP_FEATURE_DIR / "SKILL.md")

        self.assertEqual(gaps, [])

    def test_develop_feature_asks_the_user_for_open_decisions(self) -> None:
        """R5.2, R5.4: when a test-writer or implementer returns `Status: DECISION`, develop-feature pauses that task
        (no other subagent for it, no fix round), shows the user the options with their advantages, disadvantages and
        the recommendation, and waits for the user's choice; it records the choice in the task's `- Decision:` field
        in tasks.md as `- Decision: <option> (user | recommended)` with the options kept below, so summaries cite it,
        and that record lands in the task's commit; then it sends the task back to a new subagent of the same role
        carrying the choice. A `Status: DECISION` is not an escalation or a BLOCKED: the design is not wrong."""
        gaps = _open_decision_gaps(_blocks(DEVELOP_FEATURE_DIR / "SKILL.md"))

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
