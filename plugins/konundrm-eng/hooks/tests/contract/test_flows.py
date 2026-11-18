"""Contract tests for the flows the orchestrating skills describe (skills/*/SKILL.md and their references)."""

from __future__ import annotations

import ast
import re
import unittest
from collections.abc import Callable
from pathlib import Path

from .plugin_files import PLUGIN_ROOT, SKILLS_DIR, read_frontmatter, read_section

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


# Recovering a set-aside attempt (R8.2). These run on blocks from _blocks: lowercased, without backticks.
_STASH_PUSH_MESSAGE = re.compile(r'\bgit stash push\b[^"]*?(?<!\S)-m "([^"]+)"')
_STASH_GREP_VALUE = re.compile(r"""--grep(?:=|\s+)(?:"([^"]*)"|'([^']*)'|(\S+))""")
_STASH_APPLY = re.compile(r"\bgit stash apply\b(?:\s+(?:--index|-q|--quiet))*\s*")
# What may follow `git stash apply` and its options in PowerShell too: a quoted placeholder naming the entry, a quoted
# stash@{<...>} or a quoted command substitution. Unquoted, PowerShell reads the braces of stash@{3} as a script block.
_STASH_NAMED_ENTRY = re.compile(r"""(["'])(?:<[^<>"']*entry[^<>"']*>|stash@\{<[^<>"']+>\})\1|"\$\(""")
# A SHA has no braces, so it may go unquoted, but only after a lookup that prints SHAs (--format=%H, lowercased).
_STASH_SHA_ENTRY = re.compile(r"""(["']?)<sha>\1""")
_STASH_SHA_LOOKUP = re.compile(r"""--format[= ]["']?%h\b""")
_STASH_UNQUOTED_BRACES = re.compile(r"<[^<>]*entry[^<>]*>|stash@\{<[^<>]+>\}")
_STASH_TASK = "<nnn-slug> t<n>"  # develop-feature's part of the message that fix-bug replaces
_STASH_BUG = "<yyyy-mm-dd>-<slug> b1"


def _stash_push_message(blocks: list[str]) -> str | None:
    """Return the `-m` message of the first `git stash push` in blocks, lowercased as `_blocks` leaves it."""
    for block in blocks:
        match = _STASH_PUSH_MESSAGE.search(block)
        if match:
            return match.group(1)
    return None


def _stash_finds_and_applies(block: str, message: str) -> bool:
    """Return whether a block looks a stash entry up with `git stash list --grep` on a value that contains message,
    and applies the entry with `git stash apply`."""
    if "git stash list" not in block or "git stash apply" not in block:
        return False
    return any(message in "".join(value) for value in _STASH_GREP_VALUE.findall(block))


def _stash_apply_problem(block: str, rest: str) -> str | None:
    """Return why the argument at the start of rest, which follows a `git stash apply` in block, does not name its
    stash entry in a form PowerShell also runs, or None when it does."""
    if _STASH_NAMED_ENTRY.match(rest):
        return None
    if _STASH_SHA_ENTRY.match(rest):
        if _STASH_SHA_LOOKUP.search(block):
            return None
        return "applies <sha> but no git stash list in its block prints SHAs with --format=%H"
    if _STASH_UNQUOTED_BRACES.match(rest):
        return "leaves its entry unquoted, and PowerShell reads the braces of stash@{n} as a script block"
    return "does not name its stash entry; a position such as stash@{0} or <n> shifts with every push"


def _stash_unnamed_applies(skill: str, path: Path) -> list[str]:
    """Return one message per `git stash apply` in a SKILL.md that does not name its entry in a form PowerShell also
    runs, quoting the command and saying why."""
    gaps = []
    for block in _blocks(path):
        for match in _STASH_APPLY.finditer(block):
            rest = block[match.end() :]
            problem = _stash_apply_problem(block, rest)
            if problem is not None:
                quoted = match.group() + rest.split(" ", 1)[0]
                gaps.append(f"{skill}: {quoted.strip()!r} {problem} (R8.2)")
    return gaps


def _stash_recovery_gaps() -> list[str]:
    """Return what develop-feature's Rethink section and fix-bug lack to recover a set-aside attempt by its stash
    message (R8.2): a block that finds the entry with `git stash list --grep=<message>` and applies it, and no
    `git stash apply` without its entry anywhere in either SKILL.md."""
    develop_feature = DEVELOP_FEATURE_DIR / "SKILL.md"
    fix_bug = SKILLS_DIR / "fix-bug" / "SKILL.md"
    message = _stash_push_message(_section_blocks(develop_feature, "Rethink"))
    if message is None or _STASH_TASK not in message:
        return [f"develop-feature Rethink: no git stash push -m with a message naming {_STASH_TASK!r} (R8.2)"]
    gaps = []
    lookups = {
        "develop-feature Rethink": (_section_blocks(develop_feature, "Rethink"), message),
        "fix-bug": (_blocks(fix_bug), message.replace(_STASH_TASK, _STASH_BUG)),
    }
    for where, (blocks, expected) in lookups.items():
        if not any(_stash_finds_and_applies(block, expected) for block in blocks):
            gaps.append(
                f"{where}: no paragraph or list item finds the attempt with git stash list --grep containing "
                f"{expected!r} and applies that entry with git stash apply (R8.2)"
            )
    gaps += _stash_unnamed_applies("develop-feature", develop_feature)
    return gaps + _stash_unnamed_applies("fix-bug", fix_bug)


# fix-bug's dispatches after a rethink (R1.2): the attempt rebuilt from the red step is not a fix round, so fix-bug
# says itself that every test-writer and implementer dispatch after a rethink runs on opus at high.
_FIX_BUG_RETHINK_AFTER = re.compile(r"\bafter\b(?: \S+){0,3} rethink\b")
_FIX_BUG_RETHINK_EVERY_DISPATCH = re.compile(r"\b(?:every|each|all|any)\b(?: \S+){0,4} dispatch(?:es)?\b")


def _fix_bug_after_rethink_states_dispatches(statement: str) -> bool:
    """Return whether a statement covers every test-writer and implementer dispatch after a rethink."""
    return (
        _FIX_BUG_RETHINK_AFTER.search(statement) is not None
        and "test-writer" in statement
        and "implementer" in statement
        and _FIX_BUG_RETHINK_EVERY_DISPATCH.search(statement) is not None
    )


def _fix_bug_after_rethink_gaps(skill: Path) -> list[str]:
    """Return what fix-bug lacks to run every test-writer and implementer dispatch after a rethink on opus at high
    (R1.2): a statement naming those dispatches after a rethink, in a block that sets `model: opus` and
    `effort: high`."""
    matching = [
        block
        for block in _blocks(skill)
        if any(_fix_bug_after_rethink_states_dispatches(statement) for statement in _STATEMENT_END.split(block))
    ]
    if not matching:
        return [
            "fix-bug: no statement says every test-writer and implementer dispatch after a rethink runs on "
            "opus at high; the rebuilt first attempts would run at their frontmatter's effort (R1.2)"
        ]
    if not any(_sets_opus_high(block) for block in matching):
        return [
            "fix-bug: the paragraph about test-writer and implementer dispatches after a rethink does not set "
            "model: opus and effort: high (R1.2)"
        ]
    return []


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
    # 003 R6.1: the fix's commit carries no Task: line, so only its review and its type are checked here.
    "R3.3 reviewing an integration fix and committing it typed feat or refactor": lambda b: (
        _REVIEWED.search(b) is not None and _FEAT.search(b) is not None and _REFACTOR.search(b) is not None
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


# The pause at the end of a slice (R4.1, R6.1). These run on the blocks of develop-feature's `## Slice checkpoint`
# section, each rule within one sentence (_in_one_sentence) so an unrelated sentence cannot satisfy it.
_CHECKPOINT_WHEN = re.compile(r"\b(?:when|once|after)\b")
_CHECKPOINT_LAST_TASK = re.compile(r"\blast task\b")
_CHECKPOINT_LANDED = re.compile(r"\b(?:committed|integrated|lands|landed)\b")
_CHECKPOINT_WRITES = re.compile(r"\b(?:writ|fill|sav)\w*")
_CHECKPOINT_TEMPLATE = re.compile(r"\btemplates/slice-summary\.md\b")
_CHECKPOINT_SUMMARY_FILE = re.compile(r"\bspecs/<[^>\s]+>/summaries/s<k>\.md\b")
# Committing the slice's summary (003 R6.1: a plain subject that names no slice, and no Task: line).
_CHECKPOINT_SUMMARY_COMMIT = re.compile(r"\bcommit\w*(?: \S+){0,3} summary\b|\bsummary(?:'s)? commit\b")
_CHECKPOINT_STOPS = re.compile(r"\b(?:stop|paus|halt)\w*")
_CHECKPOINT_READING_ORDER = re.compile(r"\breading order\b|\bwhat to read first\b")
_CHECKPOINT_GO_AHEAD = re.compile(r"\bgo[- ]ahead\b|\bapprov\w*")
_CHECKPOINT_NEXT_SLICE = re.compile(r"\bnext slice\b")
_CHECKPOINT_BEFORE = re.compile(r"\b(?:before|until)\b")
_CHECKPOINT_LINK = "(#slice-checkpoint)"
# A partition session also runs Phase 3, and a parallel slice reaches the checkpoint from the last step of Parallel
# partitions, so the Phase 3 sentence that sends a slice there names a slice built without a parallel wave.
_CHECKPOINT_NO_PARALLEL_WAVE = re.compile(r"\b(?:without|not|no)\b(?: \S+){0,3} parallel\b|\bparallel:(?:\*\*)? ?no\b")
_CHECKPOINT_NAME = re.compile(r"\bcheckpoint\b")

# What develop-feature's `## Slice checkpoint` section must say, each in one sentence of one of its blocks.
_CHECKPOINT_RULES: dict[str, tuple[re.Pattern[str], ...]] = {
    "R4.1 it runs when the slice's last task is committed (and integrated)": (
        _CHECKPOINT_WHEN,
        _CHECKPOINT_LAST_TASK,
        _CHECKPOINT_LANDED,
    ),
    "R6.1 it writes the summary from templates/slice-summary.md": (_CHECKPOINT_WRITES, _CHECKPOINT_TEMPLATE),
    "R6.1 it writes the summary to specs/<slug>/summaries/S<k>.md": (_CHECKPOINT_WRITES, _CHECKPOINT_SUMMARY_FILE),
    "R6.1 it commits the summary": (_CHECKPOINT_SUMMARY_COMMIT,),
    "R4.1 it stops and shows the user the summary": (_CHECKPOINT_STOPS, _SHOWS, _USER, _SUMMARIES),
    "R4.1 it shows the summary's reading order (what to read first)": (_SHOWS, _CHECKPOINT_READING_ORDER),
    "R4.1 it waits for the user's go-ahead": (_WAITS, _CHECKPOINT_GO_AHEAD),
    "R4.1 it starts the next slice only after that go-ahead": (
        _CHECKPOINT_GO_AHEAD,
        _CHECKPOINT_BEFORE,
        _CHECKPOINT_NEXT_SLICE,
    ),
}


def _checkpoint_gaps(skill: Path) -> list[str]:
    """Return one message per part of R4.1 and R6.1 that develop-feature's `## Slice checkpoint` section lacks, and
    one when no block outside that section links to it, so the task loop never reaches it."""
    blocks = _section_blocks(skill, "Slice checkpoint")
    if not blocks:
        return ["develop-feature: SKILL.md has no '## Slice checkpoint' section"]
    gaps = [
        f"develop-feature Slice checkpoint: no sentence says {label}"
        for label, patterns in _CHECKPOINT_RULES.items()
        if not any(_in_one_sentence(block, *patterns) for block in blocks)
    ]
    outside = [block for block in _blocks(skill) if block not in blocks]
    if not any(_CHECKPOINT_LINK in block for block in outside):
        gaps.append(f"develop-feature: no block outside the section links to [Slice checkpoint]{_CHECKPOINT_LINK}")
    return gaps + _checkpoint_reach_gaps(skill)


def _checkpoint_reach_gaps(skill: Path) -> list[str]:
    """Return one message when the Phase 3 task loop never links to the `## Slice checkpoint` section, one per Phase 3
    sentence that links to it without limiting it to a slice built without a parallel wave, and one when no sentence
    of develop-feature's SKILL.md says a partition session never runs the checkpoint."""
    linking = [
        sentence
        for block in _section_blocks(skill, "Phase 3: Task loop")
        for sentence in _sentences(block)
        if _CHECKPOINT_LINK in sentence
    ]
    gaps = [] if linking else [f"develop-feature Phase 3: no sentence links to [Slice checkpoint]{_CHECKPOINT_LINK}"]
    gaps += [
        f"develop-feature Phase 3: this link to the Slice checkpoint is not limited to a slice built without a "
        f"parallel wave: {sentence!r}"
        for sentence in linking
        if not _CHECKPOINT_NO_PARALLEL_WAVE.search(sentence)
    ]
    if not any(_in_one_sentence(block, _NEGATION, _PARTITION_SESSIONS, _CHECKPOINT_NAME) for block in _blocks(skill)):
        gaps.append("develop-feature: no sentence says a partition session never runs the Slice checkpoint")
    return gaps


# The comprehension questions at the slice pause (R4.2, R4.3). These run on the blocks of develop-feature's
# `## Slice checkpoint` section, each rule within one sentence (_in_one_sentence) so an unrelated sentence cannot
# satisfy it.
_QUESTIONS_TWO_OR_THREE = re.compile(r"\b(?:two or three|two to three|2 (?:or|to) 3|2-3)\b(?: \S+){0,2} questions\b")
_QUESTIONS_QUESTIONS = re.compile(r"\bquestions?\b")
_QUESTIONS_SHORT = re.compile(r"\bshort\b")
_QUESTIONS_ABOUT_THE_CODE = re.compile(r"\b(?:about|on|over)\b(?: \S+){0,3} code\b")
_QUESTIONS_SLICE = re.compile(r"\bslice")
_QUESTIONS_EACH = re.compile(r"\b(?:each|every)\b")
_QUESTIONS_ANSWERABLE = re.compile(r"\banswerable\b|\b(?:can|could) be answered\b|\banswer\w* (?:it|them|each) from\b")
_QUESTIONS_WRONG_ANSWER = re.compile(r"\b(?:wrong\w*|incorrect\w*|mistaken)\b")
_QUESTIONS_DONT_KNOW = re.compile(r"\b(?:don(?:'|\u2019)t|do not|does not|doesn(?:'|\u2019)t) know\b")
_QUESTIONS_EXPLAINS = re.compile(r"\bexplain\w*")
_QUESTIONS_RIGHT_ANSWER = re.compile(r"\b(?:right|correct) answers?\b")
_QUESTIONS_LINES = re.compile(r"\blines?\b|\bline ranges?\b")
_QUESTIONS_ANSWERS = re.compile(r"\banswers?\b")
_QUESTIONS_DEPENDS = re.compile(r"\b(?:depend|condition|requir|gat|wait|block|hing)\w*")

# What develop-feature's `## Slice checkpoint` section must say about its questions, each in one sentence.
_QUESTIONS_RULES: dict[str, tuple[re.Pattern[str], ...]] = {
    "R4.2 it asks two or three questions": (_ASKS, _QUESTIONS_TWO_OR_THREE),
    "R4.2 the questions are short": (_QUESTIONS_SHORT, _QUESTIONS_QUESTIONS),
    "R4.2 the questions are about the slice's code": (
        _QUESTIONS_QUESTIONS,
        _QUESTIONS_ABOUT_THE_CODE,
        _QUESTIONS_SLICE,
    ),
    "R4.2 each question is answerable from the summary and the files it points to": (
        _QUESTIONS_EACH,
        _QUESTIONS_ANSWERABLE,
        _SUMMARIES,
        _FILES,
    ),
    "R4.3 on a wrong answer it explains the right answer": (
        _QUESTIONS_WRONG_ANSWER,
        _QUESTIONS_EXPLAINS,
        _QUESTIONS_RIGHT_ANSWER,
    ),
    "R4.3 on an 'I don't know' it explains the right answer": (
        _QUESTIONS_DONT_KNOW,
        _QUESTIONS_EXPLAINS,
        _QUESTIONS_RIGHT_ANSWER,
    ),
    "R4.3 the explanation cites the file and the lines that show it": (_QUESTIONS_EXPLAINS, _FILES, _QUESTIONS_LINES),
}
_QUESTIONS_FREE_GO_AHEAD_RULE = "R4.3 the go-ahead never depends on the answers"
_QUESTIONS_FREE_GO_AHEAD = (_NEGATION, _CHECKPOINT_GO_AHEAD, _QUESTIONS_DEPENDS, _QUESTIONS_ANSWERS)
# A sentence that holds the go-ahead back on a condition ("do not give the go-ahead until the answers are right") makes
# it depend on the answers, whatever negation it holds.
_QUESTIONS_HOLDS_BACK = re.compile(r"\b(?:until|unless)\b|\bonly (?:if|when)\b|\bonce\b.*\b(?:right|correct)\b")


def _questions_frees_the_go_ahead(block: str) -> bool:
    """Return whether one sentence of a block says the go-ahead never depends on the answers, without holding the
    go-ahead back on a condition."""
    return any(
        all(pattern.search(sentence) for pattern in _QUESTIONS_FREE_GO_AHEAD)
        and _QUESTIONS_HOLDS_BACK.search(sentence) is None
        for sentence in _sentences(block)
    )


def _questions_gaps(skill: Path) -> list[str]:
    """Return one message per part of R4.2 and R4.3 that develop-feature's `## Slice checkpoint` section lacks."""
    blocks = _section_blocks(skill, "Slice checkpoint")
    if not blocks:
        return ["develop-feature: SKILL.md has no '## Slice checkpoint' section"]
    gaps = [
        f"develop-feature Slice checkpoint: no sentence says {label}"
        for label, patterns in _QUESTIONS_RULES.items()
        if not any(_in_one_sentence(block, *patterns) for block in blocks)
    ]
    if not any(_questions_frees_the_go_ahead(block) for block in blocks):
        gaps.append(f"develop-feature Slice checkpoint: no sentence says {_QUESTIONS_FREE_GO_AHEAD_RULE}")
    return gaps


# Changes the user asks for at the slice pause (R4.4, amended by 004 R4.1 and R4.3: each change is classified, an
# adjustment is made right away and only the other changes become new tasks or a plan change). These run on the
# blocks of develop-feature's `## Slice checkpoint` section, each rule within one sentence (_in_one_sentence) so an
# unrelated sentence cannot satisfy it. The approval rule asks for an approval of the changes themselves, so the
# go-ahead sentence alone ("wait for the user's go-ahead before starting the next slice") cannot satisfy it.
_CHANGES_WHEN = re.compile(r"\b(?:when|whenever|if)\b")
_CHANGES_ASKED = re.compile(
    r"\b(?:ask|request)\w*(?: \S+){0,3} changes\b|\bchanges\b(?: \S+){0,3} (?:asked|requested)\b"
)
_CHANGES_AT_THE_PAUSE = re.compile(r"\b(?:at|during|in) (?:the|this|that|each) (?:pause|checkpoint|stop)\b")
_CHANGES_CHANGES = re.compile(r"\bchanges\b")  # plural, so "plan change" alone does not name the asked changes
_CHANGES_TURNS = re.compile(r"\b(?:turn|convert|becom|record|add)\w*")
_CHANGES_NEW_TASKS = re.compile(r"\bnew tasks?\b")
_CHANGES_DESIGN_MD = re.compile(r"\bdesign\.md\b")
_CHANGES_APPROVES = re.compile(r"\bapprov\w*")  # not _CHECKPOINT_GO_AHEAD: the go-ahead is not an approval of changes
_CHANGES_APPROVED_ITEM = re.compile(r"\b(?:them|changes|new tasks?|plan change)\b")
# The negation governs the verb ("never make those changes"), so a stray "no" elsewhere in the sentence does not count.
_CHANGES_NEVER_MAKES = re.compile(r"\b(?:never|not|don't)\b(?: \S+){0,2} (?:mak|edit|chang|appl|implement|cod)\w*")
_CHANGES_CLASSIFIES = re.compile(r"\bclassif\w*")
_CHANGES_ADJUSTMENTS_LINK = re.compile(r"\(#adjustments\)")
_CHANGES_ADJUSTMENT = re.compile(r"\badjustments?\b")
_CHANGES_RIGHT_AWAY = re.compile(r"\bright away\b|\bat once\b|\bimmediately\b|\bnow\b")
_CHANGES_OTHER = re.compile(r"\b(?:the|any|every) other changes?\b")
_CHANGES_YOURSELF = re.compile(r"\byourself\b")

# What develop-feature's `## Slice checkpoint` section must say about changes asked at the pause, each in one sentence.
_CHANGES_RULES: dict[str, tuple[re.Pattern[str], ...]] = {
    "R4.4 when the user asks for changes at the pause": (_CHANGES_WHEN, _USER, _CHANGES_ASKED, _CHANGES_AT_THE_PAUSE),
    "004 R4.1 each change is classified as the Adjustments section says": (
        _CHANGES_CLASSIFIES,
        _CHANGES_ADJUSTMENTS_LINK,
    ),
    "004 R4.3 an adjustment is made right away": (_CHANGES_ADJUSTMENT, _CHANGES_RIGHT_AWAY),
    "R4.4 the other changes become new tasks in tasks.md": (
        _CHANGES_OTHER,
        _CHANGES_CHANGES,
        _CHANGES_TURNS,
        _CHANGES_NEW_TASKS,
        _TASKS_MD,
    ),
    "R4.4 or a plan change to design.md/tasks.md": (_CHANGES_CHANGES, _CHANGES_TURNS, _PLAN_EDIT, _CHANGES_DESIGN_MD),
    "R4.4 the user approves them before the next slice starts": (
        _CHANGES_APPROVES,
        _USER,
        _CHANGES_APPROVED_ITEM,
        _CHECKPOINT_BEFORE,
        _CHECKPOINT_NEXT_SLICE,
    ),
    "004 R4.3 the orchestrator never makes a change itself": (_CHANGES_NEVER_MAKES, _CHANGES_YOURSELF),
}


def _changes_gaps(skill: Path) -> list[str]:
    """Return one message per part of R4.4 that develop-feature's `## Slice checkpoint` section lacks."""
    blocks = _section_blocks(skill, "Slice checkpoint")
    if not blocks:
        return ["develop-feature: SKILL.md has no '## Slice checkpoint' section"]
    return [
        f"develop-feature Slice checkpoint: no sentence says {label}"
        for label, patterns in _CHANGES_RULES.items()
        if not any(_in_one_sentence(block, *patterns) for block in blocks)
    ]


# Checkpoints the user approved in advance (R4.5). Each rule runs within one sentence (_in_one_sentence) of the
# section that owns it, and names the `Checkpoints:` header value, so the sentences about the ordinary pause ("wait
# for the user's go-ahead") cannot satisfy it alone.
_PREAPPROVED_LINE = re.compile(r"\bcheckpoints:(?:\*\*)? ?pre-approved\b")
_PREAPPROVED_ASK_LINE = re.compile(r"\bcheckpoints:(?:\*\*)? ?ask\b")
_PREAPPROVED_IN_ADVANCE = re.compile(r"\bin advance\b|\bbeforehand\b|\bahead of time\b")
_PREAPPROVED_REQUEST = re.compile(r"\brequest\b")
_PREAPPROVED_PLAN_APPROVAL = re.compile(r"\bapprov\w*(?: \S+){0,2} plan\b|\bplan\b(?: \S+){0,2} approv\w*")
_PREAPPROVED_OTHERWISE = re.compile(r"\b(?:otherwise|unless|else)\b")
# The negation governs the verb, allowing a short list ("without stopping, asking questions or waiting").
_PREAPPROVED_NEGATED = r"\b(?:never|not|no|without)\b(?: \S+){0,4} "
_PREAPPROVED_NEVER_STOPS = re.compile(_PREAPPROVED_NEGATED + r"(?:stop|halt)\w*")
_PREAPPROVED_NEVER_ASKS = re.compile(_PREAPPROVED_NEGATED + r"ask\w*")
_PREAPPROVED_NEVER_WAITS = re.compile(_PREAPPROVED_NEGATED + r"wait\w*")

# Section of develop-feature's SKILL.md -> what it must say about pre-approved checkpoints, each in one sentence.
_PREAPPROVED_RULES: dict[str, dict[str, tuple[re.Pattern[str], ...]]] = {
    "Phase 2: Plan": {
        "R4.5 it records Checkpoints: pre-approved when the user approved the pauses in advance": (
            _RECORDS,
            _PREAPPROVED_LINE,
            _APPROVES,
            _PAUSES,
            _PREAPPROVED_IN_ADVANCE,
        ),
        "R4.5 that approval comes in the request or when approving the plan": (
            _PREAPPROVED_LINE,
            _PREAPPROVED_REQUEST,
            _PREAPPROVED_PLAN_APPROVAL,
        ),
        "R4.5 it records Checkpoints: ask otherwise": (_PREAPPROVED_ASK_LINE, _PREAPPROVED_OTHERWISE),
    },
    "Slice checkpoint": {
        "R4.5 with Checkpoints: pre-approved it still writes and commits the summary": (
            _PREAPPROVED_LINE,
            _CHECKPOINT_WRITES,
            _COMMIT,
            _SUMMARIES,
        ),
        "R4.5 with Checkpoints: pre-approved it goes on to the next slice without stopping": (
            _PREAPPROVED_LINE,
            _CHECKPOINT_NEXT_SLICE,
            _PREAPPROVED_NEVER_STOPS,
        ),
        "R4.5 with Checkpoints: pre-approved it asks no questions": (_PREAPPROVED_LINE, _PREAPPROVED_NEVER_ASKS),
        "R4.5 with Checkpoints: pre-approved it does not wait": (_PREAPPROVED_LINE, _PREAPPROVED_NEVER_WAITS),
    },
}


def _preapproved_gaps(skill: Path) -> list[str]:
    """Return one message per part of R4.5 that its section of develop-feature's SKILL.md lacks."""
    gaps: list[str] = []
    for heading, rules in _PREAPPROVED_RULES.items():
        blocks = _section_blocks(skill, heading)
        gaps += [
            f"develop-feature {heading}: no sentence says {label}"
            for label, patterns in rules.items()
            if not any(_in_one_sentence(block, *patterns) for block in blocks)
        ]
    return gaps


# Decisions the user approved in advance (R5.2, R5.3), recorded apart from the pauses: the `Decisions:` header line,
# not `Checkpoints:`, lets an open decision take the recommended option. The header line itself contains
# "decisions:", so the words that prove what the user approved, or what an open decision does, must name a decision
# outside that line (_DECISIONS_DECISION never matches "decision:" or "decisions:").
#
# Two kinds of check. The positive rules (_DECISIONS_RULES, _DECISIONS_CITED, the CHANGELOG's take rule) each ask that
# one sentence of the owning section say something. One structural rule (_decisions_leaves_out_the_line) runs on every
# sentence of develop-feature's SKILL.md and of the CHANGELOG's 0.6.0 entry: a sentence that names
# `Checkpoints: pre-approved` together with a decision or the recommended option also names the `Decisions:` line that
# decides it, and never offers the two `pre-approved` lines with "or". It is polarity-free on purpose: it reads only
# which header lines and words a sentence names, never a negation, a clause or a verb, because whether a negation or a
# condition covers a phrase is not something a regex can decide, and every guard that tried had correct sentences on
# both sides of its boundary. Its message states the rule, so it never claims what a sentence means. Two known
# limits: a correct sentence that relates `Checkpoints: pre-approved` to a decision without naming the `Decisions:`
# line fails (add the line), and a sentence that names both lines without "or" is judged by the positive rules alone.

# Header tokens: the `Decisions:` line's two values, any `Decisions:` header, a decision named outside the header, and
# the two `pre-approved` lines offered as alternatives ("`Decisions: pre-approved` or `Checkpoints: pre-approved`").
_DECISIONS_LINE = re.compile(r"\bdecisions:(?:\*\*)? ?pre-approved\b")
_DECISIONS_ASK_LINE = re.compile(r"\bdecisions:(?:\*\*)? ?ask\b")
_DECISIONS_HEADER = re.compile(r"\bdecisions:")
_DECISIONS_DECISION = re.compile(r"\bdecisions?\b(?!:)")
_DECISIONS_EITHER_LINE = re.compile(
    rf"{_PREAPPROVED_LINE.pattern},? or (?:\S+ ){{0,2}}\W*{_DECISIONS_LINE.pattern}"
    rf"|{_DECISIONS_LINE.pattern},? or (?:\S+ ){{0,2}}\W*{_PREAPPROVED_LINE.pattern}"
)


def _decisions_not_after_header() -> str:
    """Return lookbehinds that fail right after a header name, with or without `**` and the space.

    So a header value ("decisions: ask", "**checkpoints:** ask") never counts as the user being asked. Python's
    lookbehinds have a fixed width, hence one per spelling.
    """
    return "".join(
        f"(?<!{name}:{bold}{space})"
        for name in ("decisions", "checkpoints")
        for bold in ("", r"\*\*")
        for space in ("", " ")
    )


# Approval. Approving the decisions: "approved the open decisions in advance". Keeping the two approvals apart:
# "separately", "apart", "independently", "on its own", or a negation at most 2 words before the approval ("approving
# the pauses does not approve the decisions"); the adjective "separate" ("with no separate question") does not count.
_DECISIONS_APPROVED = re.compile(r"\bapprov\w*(?: [^\s,;:.()]+){0,3} decisions?\b(?!:)")
_DECISIONS_APART = re.compile(
    r"\b(?:separately|apart|independently|on its own)\b|\b(?:not|never|nor|\w+n't)\b(?: [^\s,;:.()]+){0,2} approv\w*"
)
_DECISIONS_WITHOUT = re.compile(r"\b(?:without|lacking|lacks|missing|ha(?:s|ve) no)\b")
# "reads as ask", "defaults to ask", "read it as ask", "counts the line as ask".
_DECISIONS_READS_AS_ASK = re.compile(r"\b(?:reads?|counts?|means?|defaults?)(?: [^\s,;:.()]+){0,2}? (?:as |to )?ask\b")

# Negation, for the positive rules only. _DECISIONS_CLAUSE_NEGATION governs a verb of its own clause: "does not take",
# "never pauses", "never stops or pauses"; "no RED: line is needed: take" does not.
_DECISIONS_CLAUSE_NEGATION = r"\b(?:never|not|no|nor|without)\b(?: [^\s,;:.()]+){0,3} "

# Phase 3 verbs. One verb set says what happens to the recommended option, for the positive rules: active ("takes",
# "use", "goes with the recommended option") or passive ("the recommended option is taken"); negated ("does not use",
# "is not taken") in _DECISIONS_NEGATED_TAKE.
_DECISIONS_TAKE = (
    r"(?:take[sn]?|taking|took|choos(?:e|es|ing)|chose|chosen|pick(?:s|ed|ing)?|us(?:e|es|ed|ing)"
    r"|appl(?:y|ies|ied|ying)|follow(?:s|ed|ing)?|accept(?:s|ed|ing)?|(?:go|goes|going|went|gone) with)\b"
)
_DECISIONS_TAKES_RECOMMENDED = re.compile(
    rf"\b{_DECISIONS_TAKE}(?: \S+){{0,2}} recommended\b"
    rf"|\brecommended\b(?: [^\s,;:.()]+){{0,2}} (?:is|are|gets?|be|been)\b(?: [^\s,;:.()]+){{0,2}}? {_DECISIONS_TAKE}"
)
_DECISIONS_NEGATED_TAKE = re.compile(_DECISIONS_CLAUSE_NEGATION + _DECISIONS_TAKE)
_DECISIONS_NEGATED_PAUSE = re.compile(_DECISIONS_CLAUSE_NEGATION + r"paus\w*")
_DECISIONS_ASKS_OR_WAITS = re.compile(r"\bwait\w*|" + _decisions_not_after_header() + r"\bask\w*")
_DECISIONS_RECOMMENDED_FORMAT = re.compile(r"\bdecision: ?<[^>]+> ?\(recommended\)")
_DECISIONS_RECOMMENDED = re.compile(r"\brecommended\b")
_DECISIONS_SLICE_SUMMARY = re.compile(
    r"\bslice(?:'s)? summar(?:y|ies)\b|\bsummar(?:y|ies) of (?:the|its|each|that) slice\b"
)

# Template and CHANGELOG. The template patterns run on its header's list items from _split_blocks (lowercased, a
# multi-line comment joined). The CHANGELOG entry is the one that ships R5.2 and R5.3; a newer entry above it
# ([Unreleased], [0.7.0]) is not this check's concern.
_DECISIONS_TEMPLATE = SKILLS_DIR / "writing-plans" / "templates" / "tasks.md"
_DECISIONS_TEMPLATE_LINE = re.compile(r"^- \*\*decisions:\*\* ask\b")
_DECISIONS_TEMPLATE_CHECKPOINTS = re.compile(r"^- \*\*checkpoints:\*\*")
_DECISIONS_CHANGELOG = SKILLS_DIR.parent / "CHANGELOG.md"
_DECISIONS_CHANGELOG_HEADING = re.compile(r"^## (\[0\.6\.0\].*)$")


def _decisions_says(
    *patterns: re.Pattern[str], unless: re.Pattern[str] | None = None, in_block: re.Pattern[str] | None = None
) -> Callable[[str], bool]:
    """Return a predicate on a block from `_blocks`: whether one of its sentences matches every pattern.

    Args:
        patterns: what that one sentence must all match.
        unless: what that sentence must not match (a negated verb), or None.
        in_block: what the whole block must also match (the header line the sentence refers to), or None.
    """

    def says(block: str) -> bool:
        if in_block is not None and not in_block.search(block):
            return False
        return any(
            all(pattern.search(sentence) for pattern in patterns) and not (unless and unless.search(sentence))
            for sentence in _sentences(block)
        )

    return says


# Section of develop-feature's SKILL.md -> what it must say about pre-approved decisions, each in one sentence.
_DECISIONS_RULES: dict[str, dict[str, Callable[[str], bool]]] = {
    "Phase 2: Plan": {
        "R5.3 it records Decisions: pre-approved when the user approved the decisions in advance": _decisions_says(
            _RECORDS, _DECISIONS_LINE, _DECISIONS_APPROVED, _PREAPPROVED_IN_ADVANCE
        ),
        "R5.3 that approval comes in the request or when approving the plan": _decisions_says(
            _DECISIONS_LINE, _PREAPPROVED_REQUEST, _PREAPPROVED_PLAN_APPROVAL
        ),
        "R5.2 it records Decisions: ask otherwise": _decisions_says(_DECISIONS_ASK_LINE, _PREAPPROVED_OTHERWISE),
        "R5.2 a tasks.md without the Decisions: line reads as ask": _decisions_says(
            _TASKS_MD, _DECISIONS_WITHOUT, _DECISIONS_READS_AS_ASK, in_block=_DECISIONS_HEADER
        ),
        "R5.2 approving the pauses does not approve the decisions, nor the other way round": _decisions_says(
            _APPROVES, _PAUSES, _DECISIONS_DECISION, _DECISIONS_APART
        ),
    },
    "Phase 3: Task loop": {
        "R5.3 with Decisions: pre-approved an open decision never pauses the task": _decisions_says(
            _DECISIONS_LINE, _DECISIONS_DECISION, _DECISIONS_NEGATED_PAUSE
        ),
        "R5.3 with Decisions: pre-approved it takes the recommended option": _decisions_says(
            _DECISIONS_LINE, _DECISIONS_TAKES_RECOMMENDED, unless=_DECISIONS_NEGATED_TAKE
        ),
        "R5.3 it records - Decision: <option> (recommended) with the options below it": _decisions_says(
            _DECISIONS_RECOMMENDED_FORMAT, _OPTIONS, _BELOW
        ),
        (
            "R5.2 with Checkpoints: pre-approved and Decisions: ask an open decision still pauses the task and asks "
            "the user"
        ): (
            _decisions_says(
                _PREAPPROVED_LINE,
                _DECISIONS_HEADER,
                _DECISIONS_DECISION,
                _PAUSES,
                _DECISIONS_ASKS_OR_WAITS,
                _USER,
                unless=_DECISIONS_NEGATED_PAUSE,
            )
        ),
    },
}
_DECISIONS_CITED_RULE = "R5.3 the slice summary cites the recommended decision"
_DECISIONS_CITED = (_DECISIONS_RECOMMENDED, _DECISIONS_SLICE_SUMMARY, _CITE)


_DECISIONS_LINE_RULE = (
    "names Checkpoints: pre-approved with an open decision or the recommended option but not the Decisions: line that "
    "decides it, or offers either line with 'or' (R5.3)"
)


def _decisions_leaves_out_the_line(sentence: str) -> bool:
    """Return whether a sentence breaks the structural rule: it names `Checkpoints: pre-approved` together with a
    decision (outside a header) or the recommended option, and either names no `Decisions:` line or offers the two
    `pre-approved` lines with "or".

    Polarity-free: it reads only which header lines and words the sentence names, with no negation, clause or verb
    logic, since whether a negation covers a phrase is not something a regex can decide. Known limits: a correct
    sentence without the `Decisions:` line is reported too (add the line), and a sentence that names both lines
    without "or" passes here and is judged by the positive rules alone.

    Args:
        sentence: one lowercased sentence from `_sentences`.
    """
    if not _PREAPPROVED_LINE.search(sentence):
        return False
    if not (_DECISIONS_DECISION.search(sentence) or _DECISIONS_RECOMMENDED.search(sentence)):
        return False
    return not _DECISIONS_HEADER.search(sentence) or bool(_DECISIONS_EITHER_LINE.search(sentence))


def _decisions_skill_gaps(skill: Path) -> list[str]:
    """Return one message per positive rule of R5.2 and R5.3 that its section of develop-feature's SKILL.md lacks
    (_DECISIONS_RULES, and _DECISIONS_CITED in Phase 3 or the Slice checkpoint), and one per sentence anywhere in the
    skill that breaks the structural rule of `_decisions_leaves_out_the_line`.

    The messages state the rule a sentence breaks, never what the sentence means. The structural rule's two known
    limits are those of `_decisions_leaves_out_the_line`.
    """
    gaps: list[str] = []
    for heading, rules in _DECISIONS_RULES.items():
        blocks = _section_blocks(skill, heading)
        gaps += [
            f"develop-feature {heading}: no sentence says {label}"
            for label, says in rules.items()
            if not any(says(block) for block in blocks)
        ]
    cited_in = _section_blocks(skill, "Phase 3: Task loop") + _section_blocks(skill, "Slice checkpoint")
    if not any(_in_one_sentence(block, *_DECISIONS_CITED) for block in cited_in):
        gaps.append(f"develop-feature Phase 3 or Slice checkpoint: no sentence says {_DECISIONS_CITED_RULE}")
    sentences = [sentence.strip() for block in _blocks(skill) for sentence in _sentences(block)]
    gaps += [
        f"develop-feature: this sentence {_DECISIONS_LINE_RULE}: {sentence!r}"
        for sentence in sentences
        if _decisions_leaves_out_the_line(sentence)
    ]
    return gaps


def _decisions_template_gaps(template: Path) -> list[str]:
    """Return a message when, in the header of writing-plans' tasks.md template (before its first `## ` heading), the
    `- **Decisions:** ask` list item is not the one right after or right before the `- **Checkpoints:**` item."""
    header = template.read_text(encoding="utf-8").split("\n## ", 1)[0]
    items = _split_blocks(header.splitlines())
    found = next((index for index, item in enumerate(items) if _DECISIONS_TEMPLATE_CHECKPOINTS.match(item)), None)
    if found is not None and any(_DECISIONS_TEMPLATE_LINE.match(item) for item in items[max(found - 1, 0) : found + 2]):
        return []
    return ["writing-plans templates/tasks.md header: no - **Decisions:** ask line next to - **Checkpoints:**"]


def _decisions_changelog_gaps(changelog: Path) -> list[str]:
    """Return the R5.3 gaps of the CHANGELOG's 0.6.0 entry: one per sentence of the entry that breaks the structural
    rule of `_decisions_leaves_out_the_line` (with that rule's two known limits), and one when no sentence takes the
    recommended option under `Decisions: pre-approved`; or a single message when there is no 0.6.0 entry.

    The messages state the rule a sentence breaks, never what the sentence means.
    """
    lines = changelog.read_text(encoding="utf-8").splitlines()
    heading = next((match.group(1) for match in map(_DECISIONS_CHANGELOG_HEADING.match, lines) if match), None)
    if heading is None:
        return ["CHANGELOG.md: there is no [0.6.0] entry"]
    blocks = _split_blocks(read_section(changelog, heading).splitlines())
    sentences = [sentence.strip() for block in blocks for sentence in _sentences(block)]
    gaps = [
        f"CHANGELOG.md 0.6.0 entry: this sentence {_DECISIONS_LINE_RULE}: {sentence!r}"
        for sentence in sentences
        if _decisions_leaves_out_the_line(sentence)
    ]
    if not any(
        _DECISIONS_LINE.search(sentence) and _DECISIONS_TAKES_RECOMMENDED.search(sentence) for sentence in sentences
    ):
        gaps.append("CHANGELOG.md 0.6.0 entry: no sentence takes the recommended option under Decisions: pre-approved")
    return gaps


# The improvement notes (R7.1, R7.5; R7.4's warning). These run on blocks from _section_blocks of develop-feature's
# `## Slice checkpoint` and `## Phase 4: Finish`, and on its dispatch-prompts.md `## process-reviewer` section.
_NOTES_DISPATCHES = re.compile(r"\bdispatch\w*(?: \S+){0,3} (?:konundrm-eng:)?process-reviewer\b")
_NOTES_SCRIPT = re.compile(r"\bimprovement_notes\.py\b")
_NOTES_RUN_SH = re.compile(r"\bhooks/run\.sh\b")
_NOTES_PROJECT_FLAG = re.compile(r"--project\b")
_NOTES_FEATURE_FLAG = re.compile(r"--feature\b")
_NOTES_SLICE_SCOPE = re.compile(r"--scope \"?'?slice\b")
_NOTES_FEATURE_SCOPE = re.compile(r"--scope \"?'?feature\b")
_NOTES_REPORT = re.compile(r"\breport\b|\bimprovement notes\b")
_NOTES_WHOLE_FEATURE = re.compile(r"\b(?:whole|full|entire) feature\b")
_NOTES_MENTION = re.compile(r"\bprocess-reviewer\b|\bimprovement notes\b|\bnotes\b")
_NOTES_STEP_REFERENCE = re.compile(r"\bsteps? (\d+(?:(?:, | and | to |-)\d+)*)")
_NOTES_FALLBACK = re.compile(
    r"\bf(?:a|e)ll\w*(?: \S+){0,2} back\b|\bfallback\b|\bfeature(?:'s)? folder\b|\bimprovement-notes\.md\b"
)
_NOTES_TELLS = re.compile(r"\b(?:tell|warn|inform|relay|show|pass\w* on)\w*|\blet\w*(?: \S+){0,3} know\b")
_NOTES_CHANGES = re.compile(r"\b(?:chang|edit|modif|alter|appl|implement|patch|rewrit|updat)\w*")
_NOTES_PLUGIN = re.compile(r"\bplugin\b|\bskills?\b|\bagents?\b|\bhooks?\b")
_NOTES_NAMES = re.compile(r"\bnotes\b")
# The six parts of the flow record R7.1 names, each as the process-reviewer prompt must name it.
_NOTES_RECORD_PARTS: dict[str, re.Pattern[str]] = {
    "review rounds": re.compile(r"\brounds?\b"),
    "escalations": re.compile(r"\bescalat\w*"),
    "rethinks": re.compile(r"\brethinks?\b"),
    "blocked subagents": re.compile(r"\bblocked\b"),
    "gate events": re.compile(r"\bgates?\b"),
    "the user's corrections": re.compile(r"\bcorrect(?:ion|ed|s)\w*"),
}
_NOTES_SCOPE = re.compile(r"\bscope\b|\bslice\b(?: \S+){0,3} or (?:the )?(?:whole )?feature\b")


def _notes_step_numbers(sentence: str) -> set[int]:
    """Return the step numbers a sentence cites ("steps 1 to 4", "steps 1, 2 and 3", "step 2")."""
    numbers: set[int] = set()
    for match in _NOTES_STEP_REFERENCE.finditer(sentence):
        cited = match.group(1)
        for low, high in re.findall(r"(\d+)(?: to |-)(\d+)", cited):
            numbers.update(range(int(low), int(high) + 1))
        numbers.update(int(number) for number in re.findall(r"\d+", cited))
    return numbers


def _notes_saves(block: str, scope: re.Pattern[str]) -> bool:
    """Return whether a block passes the process-reviewer's report to improvement_notes.py through the plugin's
    run.sh, with --project, --feature and the --scope the pattern names."""
    patterns = (_NOTES_SCRIPT, _NOTES_RUN_SH, _NOTES_PROJECT_FLAG, _NOTES_FEATURE_FLAG, scope, _NOTES_REPORT)
    return all(pattern.search(block) for pattern in patterns)


def _notes_order_gaps(
    where: str, blocks: list[str], scope: re.Pattern[str], before: list[int], after: list[int]
) -> tuple[list[str], int | None]:
    """Return one message per ordering rule a section breaks about dispatching the process-reviewer and saving its
    notes, and the index of the dispatching block (None when there is none).

    Args:
        where: the section's name, used to start each message.
        blocks: the section's blocks, from `_section_blocks`.
        scope: the `--scope` the saving block must pass.
        before: indices of the blocks the dispatch must come after (one of them at least).
        after: indices of the blocks the dispatch and the save must come before (all of them, and at least one).
    """
    dispatching = [index for index, block in enumerate(blocks) if _NOTES_DISPATCHES.search(block)]
    if not dispatching:
        return [f"develop-feature {where}: no step dispatches konundrm-eng:process-reviewer"], None
    at = dispatching[0]
    gaps = []
    saving = [index for index, block in enumerate(blocks) if index >= at and _notes_saves(block, scope)]
    if not saving:
        gaps.append(
            f"develop-feature {where}: no step from the dispatch on passes the process-reviewer's report to"
            f" sh ${{CLAUDE_PLUGIN_ROOT}}/hooks/run.sh improvement_notes.py with --project, --feature and"
            f" --scope {'feature' if scope is _NOTES_FEATURE_SCOPE else 'slice S<k>'}"
        )
    if not any(index < at for index in before):
        gaps.append(f"develop-feature {where}: the process-reviewer is not dispatched after the step before it")
    last = max([at, *saving[:1]])
    if not after or any(index <= last for index in after):
        gaps.append(f"develop-feature {where}: the process-reviewer and the notes do not come before the step after")
    return gaps, at


def _notes_checkpoint_gaps(blocks: list[str]) -> list[str]:
    """Return one message per R7.1 rule develop-feature's `## Slice checkpoint` breaks: after the summary commit and
    before the stop that shows the user the summary, it dispatches the process-reviewer and saves its notes with a
    slice scope; and with `Checkpoints: pre-approved` it still does so."""
    commits = [index for index, block in enumerate(blocks) if _CHECKPOINT_SUMMARY_COMMIT.search(block)]
    shows = [
        index
        for index, block in enumerate(blocks)
        if any(
            all(pattern.search(sentence) for pattern in (_CHECKPOINT_STOPS, _SHOWS, _USER, _SUMMARIES))
            and not _NEGATION.search(sentence)
            for sentence in _sentences(block)
        )
    ]
    gaps, at = _notes_order_gaps("Slice checkpoint", blocks, _NOTES_SLICE_SCOPE, commits, shows)
    number = _DELIVERY_LIST_NUMBER.match(blocks[at]) if at is not None else None

    def keeps_the_notes(sentence: str) -> bool:
        if not (_PREAPPROVED_LINE.search(sentence) and _COMMIT.search(sentence) and _SUMMARIES.search(sentence)):
            return False
        if number is not None and int(number.group(1)) in _notes_step_numbers(sentence):
            return True
        clauses = _CLAUSE_BREAK.split(sentence)
        return any(_NOTES_MENTION.search(clause) and not _NEGATION.search(clause) for clause in clauses)

    if not any(keeps_the_notes(sentence) for block in blocks for sentence in _sentences(block)):
        gaps.append(
            "develop-feature Slice checkpoint: the Checkpoints: pre-approved sentence does not keep the"
            " process-reviewer step along with writing and committing the summary"
        )
    return gaps


def _notes_finish_gaps(blocks: list[str]) -> list[str]:
    """Return one message per R7.1 rule develop-feature's `## Phase 4: Finish` breaks: after the step that writes the
    feature summary and before the one that sets `Status: Done`, it dispatches the process-reviewer over the whole
    feature and saves its notes with the feature scope."""
    summaries = [
        index
        for index, block in enumerate(blocks)
        if any(_delivery_writes_the_summary(sentence) for sentence in _sentences(block))
    ]
    done = [index for index, block in enumerate(blocks) if _DELIVERY_STATUS_DONE.search(block)]
    gaps, at = _notes_order_gaps("Phase 4", blocks, _NOTES_FEATURE_SCOPE, summaries, done)
    if at is not None and not _NOTES_WHOLE_FEATURE.search(blocks[at]):
        gaps.append("develop-feature Phase 4: the process-reviewer is not dispatched over the whole feature")
    return gaps


def _notes_prompt_gaps(prompts: Path) -> list[str]:
    """Return what a dispatch-prompts file lacks for the process-reviewer: a fenced `## process-reviewer` prompt that
    names the six parts of the flow record and the scope, and an entry for it in the `## Contents` list."""
    section = read_section(prompts, "process-reviewer")
    prompt = " ".join(section.replace("`", "").lower().split())
    gaps = [] if "```" in section else ["dispatch-prompts.md: no '## process-reviewer' section with a fenced prompt"]
    gaps += [
        f"dispatch-prompts.md: the process-reviewer prompt does not name {part}"
        for part, pattern in _NOTES_RECORD_PARTS.items()
        if not pattern.search(prompt)
    ]
    if not _NOTES_SCOPE.search(prompt):
        gaps.append("dispatch-prompts.md: the process-reviewer prompt does not name the scope (slice or feature)")
    contents = read_section(prompts, "Contents").lower().splitlines()
    if not any(line.lstrip().startswith(("-", "*")) and "process-reviewer" in line for line in contents):
        gaps.append("dispatch-prompts.md: the Contents list does not name the process-reviewer prompt")
    return gaps


def _notes_gaps(skill: Path, prompts: Path) -> list[str]:
    """Return one message per part of R7.1 and R7.5 (and R7.4's warning to the user) that develop-feature lacks."""
    checkpoint = _section_blocks(skill, "Slice checkpoint")
    finish = _section_blocks(skill, "Phase 4: Finish")
    gaps = _notes_checkpoint_gaps(checkpoint) + _notes_finish_gaps(finish)
    if not any(_in_one_sentence(block, _NOTES_FALLBACK, _NOTES_TELLS, _USER) for block in checkpoint + finish):
        gaps.append(
            "develop-feature: no sentence of the Slice checkpoint or Phase 4 tells the user when the notes fell back"
            " to the feature folder"
        )
    if not any(
        _in_one_sentence(block, _NEGATION, _NOTES_CHANGES, _NOTES_PLUGIN, _NOTES_NAMES) for block in _blocks(skill)
    ):
        gaps.append("develop-feature: no sentence forbids changing the plugin on the strength of the notes (R7.5)")
    return gaps + _notes_prompt_gaps(prompts)


# A session that stops between a slice's last task commit and its summary commit resumes through Phase 0 (R4.1, R6.1):
# a Phase 0 block that names the summary commit must say a slice with every task committed but no summary commit runs
# the Slice checkpoint before the next slice's first task, so resuming never skips the summary and the pause.
_RESUME_CHECKPOINT_MISSING = re.compile(r"\b(?:missing|lacks|lacking|without|has no|no commit)\b")
# 003 R6.1: a slice's summary commit is found by the file it adds, `summaries/S<k>.md`, not by its subject.
_RESUME_SUMMARY = re.compile(r"\bsummaries/s<k>\.md\b")
_RESUME_CHECKPOINT_RULES: dict[str, Callable[[str], bool]] = {
    "R4.1, R6.1 a slice whose every task has its commit but whose summary commit is missing": lambda block: (
        _in_one_sentence(block, _EVERY_TASK_COMMIT, _COMMIT, _RESUME_SUMMARY, _RESUME_CHECKPOINT_MISSING)
    ),
    "R4.1 running the Slice checkpoint before the next slice's first task": lambda block: any(
        _CHECKPOINT_LINK in sentence and _CHECKPOINT_BEFORE.search(sentence) and _CHECKPOINT_NEXT_SLICE.search(sentence)
        for sentence in _sentences(block)
    ),
}


def _resume_checkpoint_gaps(skill: Path) -> list[str]:
    """Return one message when no block of develop-feature's `## Phase 0: Prepare` section names the summary file
    `summaries/S<k>.md`, else one per rule of _RESUME_CHECKPOINT_RULES that no such block states."""
    blocks = [block for block in _section_blocks(skill, "Phase 0: Prepare") if _RESUME_SUMMARY.search(block)]
    if not blocks:
        return ["develop-feature Phase 0: no block names the slice's summary file summaries/S<k>.md"]
    return [
        f"develop-feature Phase 0: no sentence says {label}"
        for label, rule in _RESUME_CHECKPOINT_RULES.items()
        if not any(rule(block) for block in blocks)
    ]


# Every worktree of a parallel session lives outside the project folder (R9.2): `claude --worktree` and the desktop
# app's worktree sessions put it under `.claude/worktrees/`, inside the checkout, where it shows up in the tree and
# breaks its gates. So develop-feature never recommends either, and its sentence about building several features at
# once says where each feature's worktree goes instead.
_WORKTREE_CLAUDE_FLAG = r"(?<![\w.-])claude --worktree\b"
_WORKTREE_CLAUDE_FOLDER = r"(?<![\w.])\.claude/worktrees\b"
_WORKTREE_BREAKS = re.compile(r"\bbreak(?:s|ing)?\b")
_WORKTREE_NEGATED = r"\b(?:never|not|no|don't|avoid)\b(?: \S+){0,4} "
# Where a clause ends inside a sentence from `_sentences`: a colon or semicolon that ends a word, not the one of
# `konundrm-eng:rethinker`. Parentheses and commas stay inside the clause, as in "(such as .claude/worktrees/)".
_WORKTREE_CLAUSE_END = re.compile(r"(?<!\s)[:;](?=\s|$)")
# What develop-feature never recommends, each label naming it and why (R9.2), mapped to the regex that finds it.
_WORKTREE_INSIDE_RULES: dict[str, str] = {
    "claude --worktree (R9.2: it creates the worktree inside the checkout)": _WORKTREE_CLAUDE_FLAG,
    ".claude/worktrees/ as a place to build (R9.2: it is inside the checkout)": _WORKTREE_CLAUDE_FOLDER,
}
_WORKTREE_SEVERAL_FEATURES = re.compile(
    r"\b(?:several|multiple|many|two or more|more than one) features\b"
    r"|\bfeatures (?:at once|in parallel|at the same time|concurrently|simultaneously)\b"
)
_WORKTREE_OUTSIDE_RULE = "R9.2 building several features at once puts each feature's worktree outside the project"


def _worktree_recommends(sentence: str, name: str) -> bool:
    """Return whether a sentence from `_sentences` names `name` (a regex source) other than as a warning.

    The sentence is split into clauses at `_WORKTREE_CLAUSE_END`. A clause that names it is a warning, and allowed,
    when that same clause says something breaks (`_WORKTREE_BREAKS`, as in "a worktree inside the checkout (such as
    .claude/worktrees/) shows up in this tree and breaks its gates") or puts a negation at most four words before the
    name ("never use claude --worktree"). A break cue or negation in another clause of the sentence does not count,
    so "start it with claude --worktree: a worktree inside the checkout breaks its gates" recommends it. The sentence
    recommends it when any clause that names it is not a warning.
    """
    return any(
        re.search(name, clause) is not None
        and _WORKTREE_BREAKS.search(clause) is None
        and re.search(_WORKTREE_NEGATED + name, clause) is None
        for clause in _WORKTREE_CLAUSE_END.split(sentence)
    )


def _worktree_outside_gaps(skill: Path) -> list[str]:
    """Return one message per entry of _WORKTREE_INSIDE_RULES that a sentence of develop-feature recommends
    (`_worktree_recommends`), quoting the first such sentence, plus one when no sentence about building several
    features at once (`_WORKTREE_SEVERAL_FEATURES`) names a worktree outside the project (`_OUTSIDE_THE_PROJECT`),
    including when no such sentence exists, so the rule never passes vacuously."""
    sentences = [sentence for block in _blocks(skill) for sentence in _sentences(block)]
    gaps = []
    for label, name in _WORKTREE_INSIDE_RULES.items():
        offending = [sentence for sentence in sentences if _worktree_recommends(sentence, name)]
        if offending:
            gaps.append(f"develop-feature recommends {label}: {offending[0].strip()!r}")
    several = [sentence for sentence in sentences if _WORKTREE_SEVERAL_FEATURES.search(sentence)]
    if not any(_WORKTREES.search(sentence) and _OUTSIDE_THE_PROJECT.search(sentence) for sentence in several):
        gaps.append(f"develop-feature: no sentence says {_WORKTREE_OUTSIDE_RULE} ({len(several)} such sentences)")
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
        and commits it typed feat or refactor; runs a cross code review over the wave at
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

    def test_develop_feature_pauses_after_each_slice(self) -> None:
        """R4.1, R6.1: develop-feature's `## Slice checkpoint` section runs once a slice's last task is committed (and,
        with partitions, integrated): it writes the slice's summary from `templates/slice-summary.md` to
        `specs/<slug>/summaries/S<k>.md` and commits it (003 R6.1: with a plain subject and no `Task:` line, the
        summary being found by its file); then it stops, shows the user the summary
        with its reading order, and waits for the user's go-ahead before starting the next slice. Another part of
        SKILL.md links to the section, so the task loop reaches it; every Phase 3 sentence that links to it limits it
        to a slice built without a parallel wave, and a sentence says a partition session never runs it."""
        gaps = _checkpoint_gaps(DEVELOP_FEATURE_DIR / "SKILL.md")

        self.assertEqual(gaps, [])

    def test_slice_checkpoint_asks_comprehension_questions(self) -> None:
        """R4.2, R4.3: when develop-feature pauses after a slice, its `## Slice checkpoint` section asks two or three
        short questions about the slice's code, each answerable from the summary and the files it points to; when the
        user answers wrong or says they don't know, it explains the right answer citing the file and the lines that
        show it; and the go-ahead never depends on the answers."""
        gaps = _questions_gaps(DEVELOP_FEATURE_DIR / "SKILL.md")

        self.assertEqual(gaps, [])

    def test_changes_asked_at_a_checkpoint_are_adjustments_or_new_tasks(self) -> None:
        """R4.4: when the user asks for changes at the slice pause, develop-feature's `## Slice checkpoint` section
        classifies each one as its `## Adjustments` section says (004 R4.1) and makes an adjustment right away (004
        R4.3); it turns the other changes into new tasks in tasks.md or a plan change to design.md/tasks.md, which the
        user approves before the next slice starts (an approval of the changes, not the go-ahead alone); and the
        orchestrator never makes a change itself."""
        gaps = _changes_gaps(DEVELOP_FEATURE_DIR / "SKILL.md")

        self.assertEqual(gaps, [])

    def test_pre_approved_checkpoints_do_not_stop(self) -> None:
        """R4.5: develop-feature records `- **Checkpoints:** pre-approved` in the tasks.md header when the user
        approved the pauses in advance (in the request or when approving the plan), `ask` otherwise; and with
        `Checkpoints: pre-approved` the Slice checkpoint still writes and commits the summary, then goes on to the next
        slice without stopping, asking questions or waiting."""
        gaps = _preapproved_gaps(DEVELOP_FEATURE_DIR / "SKILL.md")

        self.assertEqual(gaps, [])

    def test_pre_approved_decisions_are_recorded_apart_from_pauses(self) -> None:
        """R5.2, R5.3: a sentence of develop-feature's Phase 2 says it records `- **Decisions:** pre-approved` in the
        tasks.md header when the user approved the decisions in advance (in the request or when approving the plan),
        one that it records `ask` otherwise, one that a missing line reads as ask, and one that approving the pauses
        does not approve the decisions; sentences of Phase 3 say that with `Decisions: pre-approved` an open decision
        never pauses and takes the recommended option, recorded as `- Decision: <option> (recommended)` with the
        options below it, and that with `Checkpoints: pre-approved` and `Decisions: ask` it still pauses the task and
        asks the user; Phase 3 or the Slice checkpoint has the slice summary cite it; a sentence of the CHANGELOG's
        0.6.0 entry takes the recommended option under `Decisions: pre-approved`; and writing-plans' tasks.md template
        has a `- **Decisions:** ask` header line next to `- **Checkpoints:**`. Structural rule, polarity-free because a
        regex cannot tell what a negation covers: every sentence of the skill and of that entry that names
        `Checkpoints: pre-approved` with a decision or the recommended option also names the `Decisions:` line, and
        none offers the two `pre-approved` lines with "or". Its limits: a correct sentence without the `Decisions:`
        line fails (add the line), and one naming both lines is judged by the positive rules alone."""
        gaps = (
            _decisions_skill_gaps(DEVELOP_FEATURE_DIR / "SKILL.md")
            + _decisions_template_gaps(_DECISIONS_TEMPLATE)
            + _decisions_changelog_gaps(_DECISIONS_CHANGELOG)
        )

        self.assertEqual(gaps, [])

    def test_develop_feature_records_improvement_notes(self) -> None:
        """R7.1, R7.5: develop-feature's Slice checkpoint dispatches konundrm-eng:process-reviewer after committing the
        slice summary and before stopping to show it, and passes its report to improvement_notes.py through the
        plugin's run.sh with --project, --feature and a slice --scope, also under `Checkpoints: pre-approved`; Phase 4
        does the same over the whole feature, with the feature scope, after writing the feature summary and before
        `Status: Done`; the user is told when the notes fell back to the feature folder (R7.4); a sentence forbids
        changing the plugin on the strength of the notes; and dispatch-prompts.md has a `## process-reviewer` prompt,
        named in its Contents, that names the six parts of the flow record and the scope."""
        gaps = _notes_gaps(DEVELOP_FEATURE_DIR / "SKILL.md", DEVELOP_FEATURE_DIR / "reference" / "dispatch-prompts.md")

        self.assertEqual(gaps, [])

    def test_resume_runs_a_missing_slice_checkpoint_first(self) -> None:
        """R4.1, R6.1: when develop-feature resumes a slice whose every task has its commit but no commit adds its
        summary `summaries/S<k>.md` (the session stopped between the two; 003 R6.1), its `## Phase 0:
        Prepare` section runs the Slice checkpoint before the next slice's first task, so the slice's summary and pause
        are never skipped."""
        gaps = _resume_checkpoint_gaps(DEVELOP_FEATURE_DIR / "SKILL.md")

        self.assertEqual(gaps, [])

    def test_parallel_features_use_worktrees_outside_the_project(self) -> None:
        """R9.2: develop-feature tells the user to build each of several features at once in a worktree outside the
        project folder, and never recommends `claude --worktree` or `.claude/worktrees/`, which put it inside the
        checkout; a sentence warning that such a worktree breaks the gates stays allowed."""
        gaps = _worktree_outside_gaps(DEVELOP_FEATURE_DIR / "SKILL.md")

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

    def test_a_set_aside_attempt_is_recovered_by_its_stash_message(self) -> None:
        """R8.2: develop-feature's Rethink section and fix-bug recover a set-aside attempt by looking its stash entry up
        by the message it was stashed with (`git stash list --grep=<message>`) right before `git stash apply`, and no
        `git stash apply` in either SKILL.md goes without its entry. Git worktrees share one stash list that other
        sessions push to, so a bare apply restores the newest entry, maybe another session's work, and a position
        such as `stash@{0}` or a number such as `<n>` shifts with every push. The entry is quoted (`"<entry>"`,
        `"stash@{<n>}"`, `"$(...)"`) or is a `<sha>` from a lookup with `--format=%H`, because the user may run these
        commands in PowerShell, which reads the braces of an unquoted `stash@{3}` as a script block and git fails."""
        gaps = _stash_recovery_gaps()

        self.assertEqual(gaps, [])

    def test_fix_bug_runs_dispatches_after_a_rethink_on_opus_high(self) -> None:
        """R1.2: fix-bug says itself that every test-writer and implementer dispatch after a rethink runs with the
        Agent tool's `model: opus` and `effort: high`. After a rethink fix-bug rebuilds the bug from its red step, and
        those rebuilt first attempts are not fix rounds, so without this rule they fall under "otherwise omit both
        parameters" and run at their frontmatter's medium effort."""
        skill = SKILLS_DIR / "fix-bug" / "SKILL.md"

        gaps = _fix_bug_after_rethink_gaps(skill)

        self.assertEqual(gaps, [])

    def test_fix_bug_rethinks_a_stuck_fix(self) -> None:
        """R8.1, R8.4: fix-bug, at the fifth failed review or the third failure of the same review, stops the fix
        rounds and rethinks, dispatching the rethinker or saying to follow develop-feature's Rethink section through a
        link to it; it asks the user only when the fix still fails two more reviews after its rethink, so no sentence
        and no Escalation item asks the user at either trigger without the rethink; and its Escalation list still asks
        the user when the baseline check is red."""
        skill = SKILLS_DIR / "fix-bug" / "SKILL.md"

        gaps = _fix_bug_rethink_gaps(skill) + _fix_bug_escalation_gaps(skill)

        self.assertEqual(gaps, [])


# R2.2: the two deliveries develop-feature offers when the user approves pushing, and opening-pull-requests supports.
_DELIVERY_STACKED = re.compile(r"\bstack\w*")
_DELIVERY_PER_SLICE = re.compile(r"\b(?:per|each|every|one) slice\b|\bslice by slice\b|\bslices? each\b")
_DELIVERY_SINGLE = re.compile(
    r"\b(?:single|one) pull request\b(?: \S+){0,6} (?:all|every|each)\b(?: \S+){0,3} slices?\b"
    r"|\b(?:single|one) pull request\b(?: \S+){0,4} (?:whole|entire) feature\b"
    r"|\b(?:all|every)\b(?: \S+){0,3} slices?\b(?: \S+){0,4} (?:single|one) pull request\b"
)
_DELIVERY_DEFAULT = re.compile(r"\bdefault\b(?!\s*branch|>)")
_DELIVERY_PUSH = re.compile(r"\bpush\w*")


def _delivery_offers_both(sentence: str) -> bool:
    """Return whether a sentence names both deliveries: stacked pull requests per slice and a single pull request."""
    return all(pattern.search(sentence) for pattern in (_DELIVERY_STACKED, _DELIVERY_PER_SLICE, _DELIVERY_SINGLE))


def _delivery_names_stacked_the_default(sentence: str) -> bool:
    """Return whether a sentence calls the stacked pull requests, not the single one, the default.

    "Default" belongs to the delivery named last before it ("stacked per slice (the default)"), or to the first one
    named after it when none comes before ("by default, stacked per slice").
    """
    default = _DELIVERY_DEFAULT.search(sentence)
    if default is None:
        return False
    named = sorted(
        [(match.start(), "stacked") for match in _DELIVERY_STACKED.finditer(sentence)]
        + [(match.start(), "single") for match in _DELIVERY_SINGLE.finditer(sentence)]
    )
    before = [delivery for start, delivery in named if start < default.start()]
    after = [delivery for start, delivery in named if start >= default.start()]
    owner = before[-1] if before else next(iter(after), None)
    return owner == "stacked"


def _delivery_asks_before_pushing(sentence: str) -> bool:
    """Return whether a sentence asks the user, or waits for their approval, before pushing."""
    return _DELIVERY_PUSH.search(sentence) is not None and bool(_ASKS.search(sentence) or _APPROVES.search(sentence))


def _delivery_gaps(skill: str, blocks: list[str], *, at_push_approval: bool) -> list[str]:
    """Return one message per R2.2 delivery rule that no block of a skill states.

    Args:
        skill: The skill's name, for the messages.
        blocks: The skill's blocks, from `_blocks` or `_section_blocks`.
        at_push_approval: Whether the offer must also sit in the block that asks before pushing.
    """
    sentences = [sentence for block in blocks for sentence in _sentences(block)]
    gaps = []
    if not any(_DELIVERY_SINGLE.search(sentence) for sentence in sentences):
        gaps.append(f"{skill}: no sentence names a single pull request with every slice")
    if not any(_delivery_offers_both(sentence) for sentence in sentences):
        gaps.append(f"{skill}: no sentence offers stacked pull requests per slice or a single pull request")
    if not any(_delivery_names_stacked_the_default(sentence) for sentence in sentences):
        gaps.append(f"{skill}: no sentence makes the stacked pull requests per slice the default")
    if at_push_approval and not any(
        any(_delivery_asks_before_pushing(sentence) for sentence in _sentences(block))
        and any(_delivery_offers_both(sentence) for sentence in _sentences(block))
        for block in blocks
    ):
        gaps.append(f"{skill}: the block that asks before pushing does not offer both deliveries")
    return gaps


# R6.3: the feature summary develop-feature writes when the feature ends, and every pull request links.
_DELIVERY_SUMMARY_FILE = re.compile(r"\bspecs/<nnn-slug>/summary\.md\b")
_DELIVERY_SUMMARY_MENTION = re.compile(r"(?<![\w/-])(?:specs/<nnn-slug>/)?summary\.md\b|\bfeature summary\b")
_DELIVERY_SUMMARY_TEMPLATE = re.compile(r"\btemplates/feature-summary\.md\b")
_DELIVERY_FINAL_VERIFICATION = re.compile(r"\bfinal verification\b")
_DELIVERY_STATUS_DONE = re.compile(r"\bstatus: ?done\b")
_DELIVERY_LINKS = re.compile(r"\blink\w*")
_DELIVERY_DESCRIPTION = re.compile(r"\bdescriptions?\b|\bbod(?:y|ies)\b")
# "every pull request", "all of the feature's pull requests": nothing between the quantifier and "pull request" but
# determiners, so a word that picks some of them ("each stacked pull request", "every slice pull request") fails.
_DELIVERY_EVERY_PULL_REQUEST = re.compile(
    r"\b(?:every|each|all)\b(?: of)?(?: (?:the|its|their|these|those|feature's)){0,2} pull requests?\b"
)
# Both deliveries named as alternatives of one rule ("stacked or single", "single or a stacked one"), so a rule that
# names one delivery ("of a stacked delivery") or a look-alike ("single-slice") fails.
_DELIVERY_BOTH_DELIVERIES = re.compile(
    r"\bstack\w*(?: \S+){0,2} (?:or|and)(?: an?| the)? single\b(?!-)"
    r"|\bsingle\b(?!-)(?: \S+){0,2} (?:or|and)(?: an?| the)? stack\w*"
)
# Words that make a rule conditional, optional or narrowed to some pull requests ("only the last one", "when asked").
# A scope that is no condition ("With a feature folder, ...") holds none of them.
_DELIVERY_NARROWING = re.compile(
    r"\b(?:only|if|when|whenever|unless|once|until|provided|otherwise|except\w*|excluding|but|besides|beyond|none"
    r"|neither|some|optional\w*|may|might|could|can(?:not|'t)?|last|first|ask\w*|wants?|chooses?|prefer\w*)\b"
    r"|\b(?:as long as|in case|other than|apart from|save for)\b"
)
# Words that take a step back ("leave it out", "omit it", "drop it", "remove it").
_DELIVERY_RETRACTS = re.compile(
    r"\bomit\w*|\bleav\w*(?: \S+){0,4} out\b|\bdrop\w*|\bignor\w*|\bdiscard\w*|\bbypass\w*|\bremov\w*|\bexclud\w*"
)
_DELIVERY_LIST_NUMBER = re.compile(r"(\d+)\. ")


def _delivery_is_unconditional(sentence: str) -> bool:
    """Return whether a sentence is neither negated, skipped, made conditional, narrowed nor retracted."""
    return not any(pattern.search(sentence) for pattern in (_NEGATION, _SKIP, _DELIVERY_NARROWING, _DELIVERY_RETRACTS))


def _delivery_writes_the_summary(sentence: str) -> bool:
    """Return whether a sentence writes the feature summary to specs/<NNN-slug>/summary.md."""
    return bool(_WRITES.search(sentence) and _DELIVERY_SUMMARY_FILE.search(sentence))


def _delivery_summary_retractions(blocks: list[str], step: str) -> list[str]:
    """Return one message per Phase 4 sentence that negates, skips, conditions, narrows or retracts writing the summary.

    Checked are every sentence of the step that writes the summary, and every other Phase 4 sentence that names the
    summary or that step ("Skip step 4 for a feature with one slice"), so no sentence anywhere takes the rule back.

    Args:
        blocks: develop-feature's Phase 4 blocks, from `_section_blocks`.
        step: The block (list item) that writes the summary.
    """
    number = _DELIVERY_LIST_NUMBER.match(step)
    step_reference = re.compile(rf"\bstep {number.group(1)}\b" if number else r"(?!)")
    about_the_summary = [
        sentence
        for block in blocks
        for sentence in _sentences(block)
        if _DELIVERY_SUMMARY_MENTION.search(sentence) or step_reference.search(sentence)
    ]
    return [
        f"develop-feature Phase 4: a sentence takes back writing the summary: {sentence.strip()!r}"
        for sentence in dict.fromkeys(_sentences(step) + about_the_summary)
        if not _delivery_is_unconditional(sentence)
    ]


def _delivery_summary_order_gaps(blocks: list[str]) -> list[str]:
    """Return one message per R6.3 rule develop-feature's Phase 4 breaks about writing the feature summary.

    The summary is written from templates/feature-summary.md to specs/<NNN-slug>/summary.md after the final
    verification and before `Status: Done` and the delivery choice, so it lands in the feature's commits. It is
    written unconditionally: see `_delivery_summary_retractions`.
    """
    numbered = [(index, sentence) for index, block in enumerate(blocks) for sentence in _sentences(block)]
    writing = [position for position, (_, sentence) in enumerate(numbered) if _delivery_writes_the_summary(sentence)]
    if not writing:
        return ["develop-feature Phase 4: no sentence writes the feature summary to specs/<NNN-slug>/summary.md"]
    at = writing[0]
    block = blocks[numbered[at][0]]
    gaps = _delivery_summary_retractions(blocks, block)
    if not _DELIVERY_SUMMARY_TEMPLATE.search(block):
        gaps.append(
            "develop-feature Phase 4: the step that writes the summary does not use templates/feature-summary.md"
        )

    def positions(matches: Callable[[str], bool]) -> list[int]:
        return [position for position, (_, sentence) in enumerate(numbered) if position != at and matches(sentence)]

    verification = positions(lambda sentence: _DELIVERY_FINAL_VERIFICATION.search(sentence) is not None)
    status_done = positions(lambda sentence: _DELIVERY_STATUS_DONE.search(sentence) is not None)
    delivery = positions(_delivery_offers_both)
    if not any(position < at for position in verification):
        gaps.append("develop-feature Phase 4: the summary is not written after the final verification")
    if not status_done or any(position < at for position in status_done):
        gaps.append("develop-feature Phase 4: the summary is not written before Status: Done")
    if not delivery or any(position < at for position in delivery):
        gaps.append("develop-feature Phase 4: the summary is not written before the delivery choice")
    return gaps


def _delivery_links_the_summary(sentence: str) -> bool:
    """Return whether a sentence links the feature summary from the description of every pull request, naming both
    deliveries ("stacked or single") as the pull requests it covers."""
    return all(
        pattern.search(sentence)
        for pattern in (
            _DELIVERY_LINKS,
            _DELIVERY_SUMMARY_MENTION,
            _DELIVERY_DESCRIPTION,
            _DELIVERY_EVERY_PULL_REQUEST,
            _DELIVERY_BOTH_DELIVERIES,
        )
    )


# A sentence about the feature summary's link: it names summary.md, the feature summary or the summary link, or it
# points at a link ("that link", "no link") while talking about descriptions. The slice summaries
# (`summaries/S<k>.md`), "the summary's links" and "evidence links" are none of these.
_DELIVERY_SUMMARY_LINK = re.compile(r"\bsummary links?\b|\blinks? to (?:the |its |their )?(?:feature )?summary\b")
_DELIVERY_A_LINK = re.compile(r"\b(?:that|this|the|its|their|same|such|said|a|an|any|no) links?\b")
# The one sentence allowed outside the linking paragraph to leave the link out: "<cases> have no summary.md, so their
# descriptions carry no summary link", where every case is a branch that has no summary.md.
_DELIVERY_NO_SUMMARY = re.compile(r"(?P<cases>.+?) (?:has|have) no (?:specs/<nnn-slug>/)?summary\.md\b(?P<rest>.*)")
_DELIVERY_NO_SUMMARY_REST = re.compile(
    r"(?:,? so (?:their|its|the) (?:pull request )?descriptions? (?:carr(?:y|ies)|ha(?:ve|s)|gets?) no"
    r" (?:feature )?summary link)?"
)
_DELIVERY_CASE_SEPARATOR = re.compile(r",(?: (?:and|or))? | (?:and|or) ")
_DELIVERY_CASE_WITHOUT_SUMMARY = re.compile(
    r"(?:(?:a|an|any|every|each) )?(?:fix-bug branch(?:es)?|small changes? without slices"
    r"|features? built before the (?:feature )?summary existed)"
)


def _delivery_mentions_the_link(sentence: str) -> bool:
    """Return whether a sentence names the feature summary or its link (see `_DELIVERY_SUMMARY_LINK`)."""
    return bool(
        _DELIVERY_SUMMARY_MENTION.search(sentence)
        or _DELIVERY_SUMMARY_LINK.search(sentence)
        or (_DELIVERY_A_LINK.search(sentence) and _DELIVERY_DESCRIPTION.search(sentence))
    )


def _delivery_leaves_out_only_branches_without_a_summary(sentence: str) -> bool:
    """Return whether a sentence is the allowed one: "<cases> have no summary.md, so their descriptions carry no
    summary link", where each case is a fix-bug branch, a small change without slices or a feature built before the
    summary existed, and nothing after it adds another pull request, slice or delivery."""
    shape = _DELIVERY_NO_SUMMARY.fullmatch(sentence.strip())
    if shape is None or not _DELIVERY_NO_SUMMARY_REST.fullmatch(shape.group("rest").strip()):
        return False
    cases = _DELIVERY_CASE_SEPARATOR.split(shape.group("cases"))
    return all(_DELIVERY_CASE_WITHOUT_SUMMARY.fullmatch(case.strip()) for case in cases)


def _delivery_link_gaps(blocks: list[str]) -> list[str]:
    """Return one message per R6.3 rule opening-pull-requests breaks about linking the feature summary.

    Some block links summary.md from the description of every pull request, stacked or single, and no sentence of the
    skill takes the link back. Every sentence of a block that links it must be unconditional: no negation, skip,
    condition ("when", "if"), narrowing ("only the last") or retraction ("leave it out"); a leading scope that is no
    condition ("With a feature folder, link ...") passes. Every other sentence that names the summary or its link
    (`_delivery_mentions_the_link`) must be unconditional too, or be the one sentence that leaves the link out of the
    branches that have no summary.md (`_delivery_leaves_out_only_branches_without_a_summary`).

    Args:
        blocks: opening-pull-requests' blocks, from `_blocks`.
    """
    linking = [block for block in blocks if any(_delivery_links_the_summary(s) for s in _sentences(block))]
    if not linking:
        return [
            "opening-pull-requests: no sentence links the feature summary from the description of every pull request,"
            " stacked or single"
        ]
    in_linking = [sentence for block in linking for sentence in _sentences(block)]
    elsewhere = [
        sentence
        for block in blocks
        if block not in linking
        for sentence in _sentences(block)
        if _delivery_mentions_the_link(sentence) and not _delivery_leaves_out_only_branches_without_a_summary(sentence)
    ]
    return [
        f"opening-pull-requests: a sentence takes back linking the summary: {sentence.strip()!r}"
        for sentence in in_linking + elsewhere
        if not _delivery_is_unconditional(sentence)
    ]


def _delivery_normalized(text: str) -> str:
    """Return text normalized as `_split_blocks` normalizes a block: lowercased, no backticks, single-spaced."""
    return " ".join(_split_blocks(text.splitlines()))


def _delivery_pull_requests_row(blocks: list[str]) -> str | None:
    """Return the table row whose first cell is `Pull requests` (develop-feature's Roles row), or None without one.

    Args:
        blocks: develop-feature's blocks, from `_blocks`.
    """
    rows = (block for block in blocks if block.startswith("|"))
    return next((row for row in rows if row.strip("|").split("|")[0].strip() == "pull requests"), None)


def _delivery_naming_gaps(develop_feature: Path, opening_pull_requests: Path) -> list[str]:
    """Return one message per place that does not name both deliveries (R2.2).

    The places are develop-feature's description, its Roles row for pull requests and opening-pull-requests'
    description. Each one must name the stacked pull requests, one per slice, and a single pull request with every
    slice (`_delivery_offers_both` on the place's whole text); this checks only that both are named, not what the
    text says about them. A missing Roles row is a gap.

    Args:
        develop_feature: develop-feature's SKILL.md.
        opening_pull_requests: opening-pull-requests' SKILL.md.
    """
    both = "both deliveries (stacked pull requests, one per slice, and a single pull request)"
    gaps = []
    if not _delivery_offers_both(_delivery_normalized(read_frontmatter(develop_feature).get("description", ""))):
        gaps.append(f"develop-feature description does not name {both}")
    row = _delivery_pull_requests_row(_blocks(develop_feature))
    if row is None:
        gaps.append("develop-feature has no Roles row for Pull requests")
    elif not _delivery_offers_both(row):
        gaps.append(f"develop-feature Roles row for Pull requests does not name {both}")
    if not _delivery_offers_both(_delivery_normalized(read_frontmatter(opening_pull_requests).get("description", ""))):
        gaps.append(f"opening-pull-requests description does not name {both}")
    return gaps


class FeatureDeliveryFlowTest(unittest.TestCase):
    maxDiff = None  # a failure lists every gap, not the first one

    def test_develop_feature_offers_stacked_or_single_delivery(self) -> None:
        """R2.2: when the feature is done and the user approves pushing, develop-feature's Phase 4 offers one stacked
        pull request per slice, the default, or a single pull request with every slice, and opening-pull-requests
        supports both deliveries with the stacked one as its default."""
        develop_feature = _section_blocks(DEVELOP_FEATURE_DIR / "SKILL.md", "Phase 4: Finish")
        opening_pull_requests = _blocks(SKILLS_DIR / "opening-pull-requests" / "SKILL.md")

        gaps = _delivery_gaps("develop-feature Phase 4", develop_feature, at_push_approval=True) + _delivery_gaps(
            "opening-pull-requests", opening_pull_requests, at_push_approval=False
        )

        self.assertEqual(gaps, [])

    def test_develop_feature_writes_the_feature_summary(self) -> None:
        """R6.3: when the feature ends, develop-feature's Phase 4 writes the feature summary from
        templates/feature-summary.md to specs/<NNN-slug>/summary.md, after the final verification and before
        Status: Done and the delivery choice, with no Phase 4 sentence taking that step back; and opening-pull-requests
        links it from the description of every pull request, stacked or single, with no sentence anywhere in
        opening-pull-requests making the link conditional, narrowing or retracting it, except the one that leaves it
        out of the branches that have no summary.md (a fix-bug branch, a small change without slices, a feature built
        before the summary existed)."""
        develop_feature = _section_blocks(DEVELOP_FEATURE_DIR / "SKILL.md", "Phase 4: Finish")
        opening_pull_requests = _blocks(SKILLS_DIR / "opening-pull-requests" / "SKILL.md")

        gaps = _delivery_summary_order_gaps(develop_feature) + _delivery_link_gaps(opening_pull_requests)

        self.assertEqual(gaps, [])

    def test_skill_descriptions_name_both_deliveries(self) -> None:
        """R2.2: develop-feature's description and its Roles row for pull requests, and opening-pull-requests'
        description, each name both deliveries: the stacked pull requests, one per slice, and a single pull request
        with every slice. It checks only that each place names both, not what its sentences say about them."""
        develop_feature = DEVELOP_FEATURE_DIR / "SKILL.md"
        opening_pull_requests = SKILLS_DIR / "opening-pull-requests" / "SKILL.md"

        gaps = _delivery_naming_gaps(develop_feature, opening_pull_requests)

        self.assertEqual(gaps, [])


# R3.1, R3.5: after verification the reviews launch at once, and only the writers run one at a time.
_REVIEWS_AUDIT_SCRIPT = PLUGIN_ROOT / "hooks" / "scripts" / "audit_subagent_changes.py"
_REVIEWS_DISPATCH = re.compile(r"\b(?:dispatch|launch|start|run)\w*")
_REVIEWS_SPEC = re.compile(r"\bspec[- ]review|\bspec(?:,| and) code\b")
_REVIEWS_CODE = re.compile(r"\bcode(?: and security)?[- ]review")  # also "code-reviewer"
_REVIEWS_SECURITY = re.compile(r"\bsecurity[- ]review")
_REVIEWS_HIGH = re.compile(r"\bhigh\b")
_REVIEWS_TOGETHER = re.compile(_AT_THE_SAME_TIME.pattern + r"|\bin parallel\b|\bin (?:one|the same|a single) message\b")
_REVIEWS_WRITER = re.compile(r"\b(?:test-writers?|implementers?|writers?)\b")
_REVIEWS_WHILE = re.compile(r"\b(?:while|during|until)\b")
_REVIEWS_ONE_AT_A_TIME = re.compile(r"\bone\b(?: \S+){0,6} at a time\b|\bone after (?:another|the other)\b")
_REVIEWS_SUBAGENTS = re.compile(r"\bsubagents?\b")
_REVIEWS_WAITS_FOR_CODE = re.compile(r"\b(?:once|after|wait\w*)\b(?: \S+){0,2} code[- ]review")
_REVIEWS_PHASE_3_RULES = {
    "R3.1 dispatches the spec and code reviews at the same time": (
        _REVIEWS_DISPATCH,
        _REVIEWS_SPEC,
        _REVIEWS_CODE,
        _REVIEWS_TOGETHER,
    ),
    "R3.1 launches the security review with them on high tasks": (_REVIEWS_SECURITY, _REVIEWS_HIGH, _REVIEWS_TOGETHER),
    "R3.5 runs no test-writer or implementer while a reviewer runs": (
        _NEGATION,
        _REVIEWS_WRITER,
        _REVIEWED,
        _REVIEWS_WHILE,
    ),
    "R3.5 runs the writers one at a time": (_REVIEWS_WRITER, _REVIEWS_ONE_AT_A_TIME),
}


def _reviews_contradictions(where: str, blocks: list[str]) -> list[str]:
    """Return the sentences that run every subagent one at a time or make the security review wait for code review."""
    gaps = []
    for sentence in (sentence.strip() for block in blocks for sentence in _sentences(block)):
        sequential = _REVIEWS_SUBAGENTS.search(sentence) and _REVIEWS_ONE_AT_A_TIME.search(sentence)
        if sequential and not _REVIEWS_WRITER.search(sentence):
            gaps.append(f"{where} runs every subagent one at a time, not only the writers: {sentence}")
        if _REVIEWS_SECURITY.search(sentence) and _REVIEWS_WAITS_FOR_CODE.search(sentence):
            gaps.append(f"{where} makes the security review wait for the code review: {sentence}")
    return gaps


# R3.2, R3.3: every finding goes to one fix round, and a review that runs again gets its findings and what changed.
_ONE_FIX_ROUND = re.compile(r"\b(?:one|a single|the same)\b(?: \S+){0,3} fix[- ]rounds?\b")
_FIX_ROUND_ROUTES = re.compile(r"\bfindings?\b.*\brout\w*|\brout\w*.*\bfindings?\b")  # also "routed the same way"
_FIX_ROUND_AGAIN = re.compile(r"\breview\w* again\b|\brepeat\w*(?: from)? steps? 3\b")
_PLACEHOLDER = re.compile(r"<[^<>]+>")
_PREVIOUS_FINDINGS = re.compile(r"\b(?:previous|earlier|prior|last|own)\b(?: \S+){0,2} findings?\b")
_CHANGED = re.compile(r"\bchang\w*")
_FIX_ROUND_PHASE_3_RULES = {
    "R3.2 sends every finding of the reviews to one fix round": (
        re.compile(r"\b(?:all|every)\b"),
        re.compile(r"\bfindings?\b"),
        _ONE_FIX_ROUND,
    ),
    "R3.3 gives a review that runs again its previous findings and what changed": (_PREVIOUS_FINDINGS, _CHANGED),
}
_RE_REVIEW_PROMPT_RULES = {
    "the review's previous findings": (_PLACEHOLDER, _PREVIOUS_FINDINGS),
    "the fix round's report of each file changed and what changed in it": (
        _PLACEHOLDER,
        re.compile(r"\bfix[- ]round\b"),
        re.compile(r"\bfiles?\b"),
        _CHANGED,
    ),
    "the orchestrator's verification output after the fix round": (_PLACEHOLDER, re.compile(r"\bverif\w*")),
    "rereading those files": (re.compile(r"\bre-?read\w*"), re.compile(r"\bfiles?\b")),
    "reviewing what changed instead of the whole task": (_CHANGED, _NEGATION, re.compile(r"\bwhole task\b")),
}


# R3.4: a task is committed only once its reviews passed, so a later change is reviewed again. Amended by 004 R3.1
# and R3.4: the later change goes again through the reviews it concerns, not through all of them, and the task is
# committed when no change made after a review's pass is one that review must see again.
_COMMIT_ANY = re.compile(r"\b(?:any|every)\b")
_COMMIT_REVIEWED_AGAIN = (re.compile(r"\breview\w*|\bsteps? 3\W{1,3}4\b"), re.compile(r"\bagain\b|\bonce more\b"))
_COMMIT_AFTER_ITS_PASS = re.compile(r"\bafter\b(?: \S+){0,4} pass\b")
_COMMIT_CONCERNS = re.compile(r"\bconcerns?\b")
_COMMIT_PHASE_3_RULES = {
    "R3.4 commits a task only when its spec, code and (on high tasks) security reviews passed, and no change made"
    " after a review's pass is one that review must see again (004 R3.4)": (
        re.compile(r"\bcommit\w*"),
        re.compile(r"\bonly\b"),
        _REVIEWS_SPEC,
        _REVIEWS_CODE,
        _REVIEWS_SECURITY,
        _REVIEWS_HIGH,
        re.compile(r"\bpass\w*"),
        _COMMIT_AFTER_ITS_PASS,
        re.compile(r"\bagain\b"),
    ),
    "R3.4 sends any change made after the reviews again through the reviews it concerns (004 R3.1)": (
        _COMMIT_ANY,
        re.compile(r"\bchang\w*|\bfix\w*"),
        *_COMMIT_REVIEWED_AGAIN,
        _COMMIT_CONCERNS,
    ),
}
_COMMIT_ANY_TEST = re.compile(r"\b(?:any|every)\b(?: \S+)? tests?\b")
_COMMIT_NOT_ONLY_TESTS = re.compile(r"\bchang\w*|\bfix\w*|\bcode\b")


class ReviewFlowTest(unittest.TestCase):
    maxDiff = None  # a failure lists every gap, not the first one

    def test_reviews_launch_at_once_with_no_writer_running(self) -> None:
        """R3.1, R3.5: 002 develop-feature's Phase 3 dispatches the spec and code reviews (and, on high tasks, the
        security review) at the same time, runs no writer while a reviewer runs, and runs only the writers one at a
        time, as the audit hook's docstring also says; neither makes every subagent sequential."""
        phase_3 = _section_blocks(DEVELOP_FEATURE_DIR / "SKILL.md", "Phase 3: Task loop")
        docstring = ast.get_docstring(ast.parse(_REVIEWS_AUDIT_SCRIPT.read_text(encoding="utf-8"))) or ""
        audit = _split_blocks(docstring.splitlines())

        gaps = [
            f"develop-feature Phase 3 lacks: {rule}"
            for rule, patterns in _REVIEWS_PHASE_3_RULES.items()
            if not any(_in_one_sentence(block, *patterns) for block in phase_3)
        ]
        if not any(_in_one_sentence(block, _REVIEWS_WRITER, _REVIEWS_ONE_AT_A_TIME) for block in audit):
            gaps.append("audit_subagent_changes docstring lacks: R3.5 runs the writers one at a time")
        gaps += _reviews_contradictions("develop-feature Phase 3", phase_3)
        gaps += _reviews_contradictions("audit_subagent_changes docstring", audit)

        self.assertEqual(gaps, [])

    def test_findings_share_one_fix_round_and_re_reviews_get_what_changed(self) -> None:
        """R3.2, R3.3: 002 develop-feature's Phase 3 sends every finding of the reviews to one fix round, routes no
        review's findings to a fix round of its own before reviewing again, and gives a review that runs again its
        previous findings and what changed; the `## re-review` prompt passes those findings, the fix round's report
        of each changed file and the verification output, and asks to reread those files instead of the whole task."""
        phase_3 = _section_blocks(DEVELOP_FEATURE_DIR / "SKILL.md", "Phase 3: Task loop")
        prompts = DEVELOP_FEATURE_DIR / "reference" / "dispatch-prompts.md"
        section = read_section(prompts, "re-review")
        prompt = _split_blocks("\n".join(re.findall(r"```\w*\n(.*?)```", section, re.DOTALL)).splitlines())

        gaps = [
            f"develop-feature Phase 3 lacks: {rule}"
            for rule, patterns in _FIX_ROUND_PHASE_3_RULES.items()
            if not any(_in_one_sentence(block, *patterns) for block in phase_3)
        ]
        gaps += [
            f"develop-feature Phase 3 routes one review's findings and reviews again, not one fix round: {block}"
            for block in phase_3
            if _FIX_ROUND_ROUTES.search(block) and _FIX_ROUND_AGAIN.search(block) and not _ONE_FIX_ROUND.search(block)
        ]
        gaps += [
            f"dispatch-prompts.md re-review prompt lacks: {rule}"
            for rule, patterns in _RE_REVIEW_PROMPT_RULES.items()
            if not any(all(pattern.search(block) for pattern in patterns) for block in prompt)
        ]
        contents = read_section(prompts, "Contents").lower().splitlines()
        if not any(line.lstrip().startswith(("-", "*")) and "re-review" in line for line in contents):
            gaps.append("dispatch-prompts.md: the Contents list does not name the re-review prompt")

        self.assertEqual(gaps, [])

    def test_task_commits_only_after_the_reviews_its_final_code_needs(self) -> None:
        """R3.4: 002 develop-feature's Phase 3 commits a task only when its spec and code reviews (and, on high tasks,
        its security review) passed and no change made after a review's pass is one that review must see again (004
        R3.4), sends any change made after the reviews again through the reviews it concerns (004 R3.1), and has no
        sentence that limits that second review to the tests added after the reviews."""
        phase_3 = _section_blocks(DEVELOP_FEATURE_DIR / "SKILL.md", "Phase 3: Task loop")

        gaps = [
            f"develop-feature Phase 3 lacks: {rule}"
            for rule, patterns in _COMMIT_PHASE_3_RULES.items()
            if not any(_in_one_sentence(block, *patterns) for block in phase_3)
        ]
        gaps += [
            f"develop-feature Phase 3 reviews again only the tests added after the reviews: {sentence.strip()}"
            for block in phase_3
            for sentence in _sentences(block)
            if all(pattern.search(sentence) for pattern in (_COMMIT_ANY_TEST, *_COMMIT_REVIEWED_AGAIN))
            and not _COMMIT_NOT_ONLY_TESTS.search(sentence)
        ]

        self.assertEqual(gaps, [])


# R2.5, R2.6, R4.7: the gate asks `task_ledger.py status` and runs the check only when it is not green for this tree.
_GATE_STATUS = re.compile(r"\btask_ledger\.py status\b")
_GATE_GREEN = re.compile(r"\bgreen\b")
_GATE_STATUS_OR_GREEN = re.compile(r"\bstatus\b|\bgreen\b|\botherwise\b")
_GATE_TO_COMMIT = re.compile(r"\bcommit\w*|\bstep 7\b")
_GATE_SKIPS = re.compile(_NEGATION.pattern + r"|\bskip\w*")
_GATE_NOT_GREEN = re.compile(r"\botherwise\b|\b(?:not|no|never|isn't|doesn't)\b(?: \S+){0,3} (?:green|show\w*)\b")
_GATE_RUNS_CHECK_COMMAND = (re.compile(r"\brun\w*"), re.compile(r"\bcheck command\b"))
_GATE_RED = re.compile(r"\bred\b|\bfail\w*|\bdoes not pass\b")
_GATE_STEP_5 = re.compile(r"\bsteps?\b[^.;]{0,15}\b5\b|\bverify by risk\b")
_GATE_RULES = {
    "R4.7 runs task_ledger.py status to learn whether the check is green for this tree": (
        _GATE_STATUS,
        _CHECK,
        _GATE_GREEN,
    ),
    "R2.5 goes to the commit without running the check when status shows it green": (
        re.compile(r"\bstatus\b"),
        _GATE_GREEN,
        _GATE_TO_COMMIT,
        _GATE_SKIPS,
        _CHECK,
    ),
    "R2.6 otherwise runs the check command before committing": (_GATE_NOT_GREEN, *_GATE_RUNS_CHECK_COMMAND),
    "a red check's fix goes through step 5 (verify by risk) again": (_GATE_RED, _CHECK, _GATE_STEP_5),
}
# Running the check with no condition: "then run the check command", "run the check again", "the full check runs".
_GATE_RUNS_CHECK = re.compile(r"\b(?:re)?run\w*(?: (?:the|full))* check\b|\bcheck (?:command )?runs?\b")

# R2.7, R4.2, R4.3: a task commits as `git commit -F` of what `task_ledger.py message` writes, never editing tasks.md.
_TASK_COMMIT_LINE = re.compile(r"\bmsg=\$\(.*\btask_ledger\.py message\b.*--rounds\b.*&& git commit -f \"?\$msg\b")
_TASK_COMMIT_NAMES = {
    "task_ledger.py message": re.compile(r"\btask_ledger\.py message\b"),
    "--rounds": re.compile(r"--rounds\b"),
    "git commit -F": re.compile(r"\bgit commit -f\b"),
}
_TASK_COMMIT_WORD = re.compile(r"\bcommit\w*")
_TASK_COMMIT_ROUNDS_FLAG = re.compile(r"--rounds\b")
_TASK_COMMIT_BOX = re.compile(r"\bbox(?:es)?\b")
_TASK_COMMIT_ROUNDS = re.compile(r"(?<!-)\brounds\b")
_TASK_COMMIT_GATE = re.compile(r"\bcommit (?:gate|hook)\b")
_TASK_COMMIT_LIKE_ANY = re.compile(r"\b(?:any|every) other commit\b|\bscript\b")
_TASK_COMMIT_AS_STEP_7 = re.compile(r"\btask_ledger\.py message\b|\bstep 7\b")
_TASK_COMMIT_CO_AUTHOR = re.compile(r"\bco-author\w*|\battribution\b")
_TASK_COMMIT_TRAILER = re.compile(r"--trailer\b")
_TASK_COMMIT_BODY = re.compile(r"--body\b")
# Checking a box, writing a Rounds line, or committing (or sending the tally to) a tasks.md update.
_TASK_COMMIT_LEDGER_EDIT = re.compile(
    r"\b(?:check|tick|mark)(?:s|ed|ing)?\b(?: \S+){0,4} box(?:es)?\b"
    r"|\b(?:add|writ|record|put|append)\w*(?: \S+){0,4} rounds(?: lines?\b|:)"
    r"|\btasks\.md update\b|\bupdat\w*(?: \S+){0,3} tasks\.md\b|\b(?:go|goes|lands?|written) (?:in|into|to) tasks\.md\b"
)
_TASK_COMMIT_CLAUSE_BREAK = re.compile(r"[,;:()]")
# Single quotes keep the shell from expanding the subject and body only when they hold no apostrophe, which would close
# the quote and leave a backtick span after it to run inside `msg=$(…)`; a quoted heredoc expands nothing either.
_TASK_COMMIT_SINGLE_QUOTES = re.compile(r"\bsingle[- ]quot")
_TASK_COMMIT_NO_APOSTROPHE = re.compile(r"\b(?:no|without|never)\b(?: \S+){0,3} (?:'|apostrophes?\b)")
_TASK_COMMIT_QUOTED_HEREDOC = re.compile(r"<<-? ?'\w+'")
_TASK_COMMIT_FIX_BUG_INHERITS = re.compile(r"\btask_ledger\b|\bsame as (?:(?:inside|in) )?develop-feature\b")
# (where, the rule, the patterns one of its sentences must all match). Where: develop-feature's step 7, Phase 3 tally
# paragraph or Phase 0 partition session paragraph, or committing-changes' `### Inside develop-feature`.
_TASK_COMMIT_RULES = [
    ("step 7", 'R4.2 msg=$(task_ledger.py message … --rounds …) && git commit -F "$msg"', (_TASK_COMMIT_LINE,)),
    # 003 R6.2: the rounds reach the task's note through `message --rounds`, not its commit message.
    ("tally", "R2.7 the tally goes to the task's commit step as --rounds", (_TASK_COMMIT_ROUNDS_FLAG,)),
    ("step 7", "R2.7 checks no box, writes no Rounds line", (_NEGATION, _TASK_COMMIT_BOX, _TASK_COMMIT_ROUNDS)),
    ("step 7", "R4.3 goes through the commit gate like any other commit", (_TASK_COMMIT_GATE, _TASK_COMMIT_LIKE_ANY)),
    ("partition", "commits its tasks as step 7 or task_ledger.py message", (_TASK_COMMIT_WORD, _TASK_COMMIT_AS_STEP_7)),
    ("committing-changes", "co-author trailers go on with --trailer", (_TASK_COMMIT_CO_AUTHOR, _TASK_COMMIT_TRAILER)),
]


def _unnegated(sentence: str, pattern: re.Pattern[str]) -> bool:
    """Return whether a sentence matches a pattern with no negation in the match or earlier in its clause."""
    return any(
        not _NEGATION.search(_TASK_COMMIT_CLAUSE_BREAK.split(sentence[: match.start()])[-1] + match.group())
        for match in pattern.finditer(sentence)
    )


def _subsection_blocks(blocks: list[str], heading: str) -> list[str]:
    """Return the blocks after a `### ` heading block up to the next `### ` heading, or [] when there is none."""
    start = blocks.index(heading) + 1 if heading in blocks else len(blocks)
    end = next((index for index in range(start, len(blocks)) if blocks[index].startswith("### ")), len(blocks))
    return blocks[start:end]


# R1.8, R4.7: a resumed session asks `task_ledger.py status`, which counts only `Task:` commits in `<base>..HEAD`.
_RESUME_RUNS = re.compile(r"\b(?:run|use|ask|call)\w*")
_RESUME_BASE_RANGE = re.compile(r"<base>\.\.head\b|\b(?:after|since)\b(?: \S+){0,4} base\b")
_RESUME_EARLIER_FEATURE = re.compile(r"\b(?:earlier|previous|other|another) feature")
_RESUME_COMMIT = re.compile(r"\bcommit\w*")
_RESUME_BOX = re.compile(r"\bbox(?:es)?\b")
_RESUME_WHATEVER_BOX = re.compile(r"\bwhatever\b|\bregardless\b|\b(?:not|never|no)\b(?: \S+){0,4} box")
_RESUME_BUILT = re.compile(r"\b(?:built|pending|done)\b")  # not the wave bullet's "never by boxes" about integration
_RESUME_CONTINUES = re.compile(r"\b(?:continue|resume|go on|start)\w*")
_RESUME_NEXT = re.compile(r"\bnext\b")
_RESUME_STATUS_NAMES = re.compile(r"\bstatus\b")
_RESUME_UNRANGED_LOOKUP = re.compile(r"\bgit log\b.*--grep '\^task:")
_RESUME_RANGE = re.compile(r"\.\.head\b|<base>\.\.")
_RESUME_RULES = {
    "R4.7 runs task_ledger.py status": (_GATE_STATUS, _RESUME_RUNS),
    "R1.8 counts only commits after the plan's base (<base>..HEAD)": (_RESUME_BASE_RANGE, _RESUME_COMMIT),
    "R1.8 an earlier feature's Task: commits never count": (_RESUME_EARLIER_FEATURE, _NEGATION, _RESUME_COMMIT),
    "R1.8 a task with its commit is built whatever its box says": (
        _RESUME_BOX,
        _RESUME_COMMIT,
        _RESUME_WHATEVER_BOX,
        _RESUME_BUILT,
    ),
    "R1.8 continues at the task status names as next": (_RESUME_CONTINUES, _RESUME_NEXT, _RESUME_STATUS_NAMES),
}

# The check run as given (R2.4, R2.5): the recorder keeps a passing check only when the shell call is the check command
# alone, so a trimmed, redirected or chained run leaves `check: not recorded` and the gate and the commit run it again.
IMPLEMENTER = PLUGIN_ROOT / "agents" / "implementer.md"
_ALONE_CHECK = re.compile(r"\bcheck\b")
_ALONE_AS_GIVEN = re.compile(r"\bas (?:given|is|written|printed|named)\b|\bexactly as\b|\bverbatim\b|\bunchanged\b")
_ALONE_OWN_CALL = re.compile(
    r"\balone\b|\bby itself\b|\bon its own\b"
    r"|\b(?:its own|a separate|a single|one) (?:shell |bash )?(?:call|invocation)\b"
)
_ALONE_PIPE = re.compile(r"\bpip(?:e|es|ed|ing)\b|\|")
_ALONE_REDIRECT = re.compile(r"\bredirect\w*")
_ALONE_REASON = re.compile(r"\brecord\w*|\bregister\w*|\breus\w*")
_ALONE_RULES = {
    "the check command run as given, alone in its own shell call": (_ALONE_CHECK, _ALONE_AS_GIVEN, _ALONE_OWN_CALL),
    "no pipe or redirection on the check": (_ALONE_CHECK, _NEGATION, _ALONE_PIPE, _ALONE_REDIRECT),
    "why: only such a run is recorded and reused": (_ALONE_CHECK, _ALONE_REASON),
}


class GateFlowTest(unittest.TestCase):
    maxDiff = None  # a failure lists every gap, not the first one

    def test_gate_runs_the_check_only_when_status_is_not_green(self) -> None:
        """R2.5, R2.6, R4.7: 002 develop-feature's Phase 3 gate runs `task_ledger.py status`, goes to the commit
        without running the check when status shows it green for this tree, runs the check command otherwise, and
        sends a red check's fix through step 5 again; no Phase 3 sentence runs the check with no such condition."""
        phase_3 = _section_blocks(DEVELOP_FEATURE_DIR / "SKILL.md", "Phase 3: Task loop")
        gate = [block for block in phase_3 if block.startswith("6. **gate.**")]

        gaps = [] if gate else ["develop-feature Phase 3 has no step 6 starting '6. **Gate.**'"]
        gaps += [
            f"develop-feature Phase 3 step 6 lacks: {rule}"
            for rule, patterns in _GATE_RULES.items()
            if not any(_in_one_sentence(block, *patterns) for block in gate)
        ]
        gaps += [
            f"develop-feature Phase 3 runs the check whatever status shows: {sentence.strip()}"
            for block in phase_3
            for sentence in _sentences(block)
            if not _GATE_STATUS_OR_GREEN.search(sentence)
            and any(
                _GATE_RUNS_CHECK.search(clause) and not _NEGATION.search(clause)
                for clause in _CLAUSE_BREAK.split(sentence)
            )
        ]

        self.assertEqual(gaps, [])

    def test_task_commit_goes_through_the_gate_with_its_message(self) -> None:
        """R2.7, R4.2, R4.3: 002 develop-feature's step 7 and partition session commit a task with `task_ledger.py
        message` and a plain `git commit -F`, through the commit gate, its rounds as `--rounds` and no box or Rounds
        line in tasks.md; committing-changes' develop-feature mode says so too, attribution in `--trailer`, single
        quotes only with no apostrophe in them (or a quoted heredoc), and its fix-bug mode does not inherit
        `message`."""
        skill = DEVELOP_FEATURE_DIR / "SKILL.md"
        phase_3 = _section_blocks(skill, "Phase 3: Task loop")
        step_7 = [block for block in phase_3 if block.startswith("7. **commit.**")]
        tally = [block for block in phase_3 if block.startswith("keep a tally per task")]
        partition = [b for b in _section_blocks(skill, "Phase 0: Prepare") if b.startswith("**partition session.**")]
        workflow = _section_blocks(SKILLS_DIR / "committing-changes" / "SKILL.md", "Workflow")
        inside = _subsection_blocks(workflow, "### inside develop-feature")
        fix_bug = _subsection_blocks(workflow, "### inside fix-bug")
        where = {"step 7": step_7, "tally": tally, "partition": partition, "committing-changes": inside}

        gaps = [
            f"{name} lacks: {rule}"
            for name, rule, patterns in _TASK_COMMIT_RULES
            if not any(_in_one_sentence(block, *patterns) for block in where[name])
        ]
        missing = [name for name, pattern in _TASK_COMMIT_NAMES.items() if not pattern.search(" ".join(inside))]
        if missing:
            gaps.append(f"committing-changes does not name (R4.2, R4.3): {missing}")
        gaps += [
            f"{name} edits tasks.md with the task's commit (R2.7): {sentence.strip()}"
            for name, blocks in (("Phase 3", phase_3), ("partition", partition), ("committing-changes", inside))
            for block in blocks
            for sentence in _sentences(block)
            if _unnegated(sentence, _TASK_COMMIT_LEDGER_EDIT)
        ]
        gaps += [
            f"committing-changes puts attribution in --body: {sentence.strip()}"
            for block in inside
            for sentence in _sentences(block)
            if _TASK_COMMIT_CO_AUTHOR.search(sentence) and _unnegated(sentence, _TASK_COMMIT_BODY)
        ]
        gaps += [
            f"committing-changes offers single quotes without excluding ' from them: {sentence.strip()}"
            for block in inside
            for sentence in _sentences(block)
            if _TASK_COMMIT_SINGLE_QUOTES.search(sentence) and not _TASK_COMMIT_NO_APOSTROPHE.search(sentence)
            if not any(_TASK_COMMIT_QUOTED_HEREDOC.search(other) for other in inside)
        ]
        gaps += [
            f"committing-changes ### Inside fix-bug inherits task_ledger.py message: {sentence.strip()}"
            for block in fix_bug
            for sentence in _sentences(block)
            if _TASK_COMMIT_FIX_BUG_INHERITS.search(sentence)
        ]

        self.assertEqual(gaps, [])

    def test_resume_uses_status_and_the_base_range(self) -> None:
        """R1.8, R4.7: 002 develop-feature's Phase 0 resume runs `task_ledger.py status`, counts only commits in
        `<base>..HEAD` (never an earlier feature's), treats a task with its commit as built whatever its box says and
        continues at the task status names as next; no Phase 0 sentence looks a task's commit up with an unranged
        `git log --grep '^Task: …'`."""
        prepare = [
            block
            for block in _section_blocks(DEVELOP_FEATURE_DIR / "SKILL.md", "Phase 0: Prepare")
            if not block.startswith("**partition session")
        ]
        start = next((index for index, block in enumerate(prepare) if block.startswith("1. ")), len(prepare))
        end = next((index for index in range(start + 1, len(prepare)) if prepare[index].startswith("2. ")), start)
        resume = prepare[start + 1 : end]

        gaps = [] if resume else ["develop-feature Phase 0 step 1 has no resume bullets"]
        gaps += [
            f"develop-feature Phase 0 resume lacks: {rule}"
            for rule, patterns in _RESUME_RULES.items()
            if not any(_in_one_sentence(block, *patterns) for block in resume)
        ]
        gaps += [
            f"develop-feature Phase 0 looks a task's commit up outside <base>..HEAD: {sentence.strip()}"
            for block in prepare
            for sentence in _sentences(block)
            if _RESUME_UNRANGED_LOOKUP.search(sentence) and not _RESUME_RANGE.search(sentence)
        ]

        self.assertEqual(gaps, [])

    def test_the_check_runs_alone_so_its_pass_is_recorded(self) -> None:
        """R2.4, R2.5: 002 the implementer's check step (agents/implementer.md `## Process`), develop-feature's Phase 0
        baseline (step 3) and its Phase 3 gate (step 6) each say, in one sentence of that step, to run the check
        command as given, alone in its own shell call, with no pipe or redirection, and why: the hook records only
        such a run, so the commit can reuse it instead of the gate running the check again.

        The "why" rule shares its sentence with the word "check" only, so wording like "so its pass is recorded" fits.
        """
        skill = DEVELOP_FEATURE_DIR / "SKILL.md"
        places = {
            "implementer.md ## Process check step": [
                block for block in _section_blocks(IMPLEMENTER, "Process") if block.startswith("6.")
            ],
            "develop-feature Phase 0 step 3 (baseline)": [
                block for block in _section_blocks(skill, "Phase 0: Prepare") if block.startswith("3.")
            ],
            "develop-feature Phase 3 step 6 (gate)": [
                block for block in _section_blocks(skill, "Phase 3: Task loop") if block.startswith("6. **gate.**")
            ],
        }

        gaps = [f"{place} is missing" for place, blocks in places.items() if not blocks]
        gaps += [
            f"{place} lacks: {rule}"
            for place, blocks in places.items()
            for rule, patterns in _ALONE_RULES.items()
            if not any(_in_one_sentence(block, *patterns) for block in blocks)
        ]

        self.assertEqual(gaps, [])


# The slice's pause and its ledger (R2.8, R4.5): close-slice checks the boxes and writes the rounds of the slice's
# committed tasks, and its result lands in the summary commit.
_CLOSE_RUN_SH = re.compile(r"\bhooks/run\.sh\b")
_CLOSE_COMMAND = re.compile(r"\btask_ledger\.py close-slice\b")
_CLOSE_PLAN = re.compile(r"\bspecs/<[^>\s]+>/tasks\.md\b")
_CLOSE_SLICE_ID = re.compile(r"\bs<k>")
_CLOSE_RUNS = (_CLOSE_RUN_SH, _CLOSE_COMMAND, _CLOSE_PLAN, _CLOSE_SLICE_ID)
_CLOSE_NAMED = re.compile(r"\bclose-slice\b")
_CLOSE_LEDGER = re.compile(r"\bclose-slice\b|\btasks\.md\b")
_CLOSE_IN_TASK_COMMIT = re.compile(r"\b(?:box|rounds)\b.*\b(?:in|with) (?:the|its) task's (?:own )?commit\b")
_CLOSE_CHECKS_BOX = re.compile(r"\b(?:check|mark|tick)\w*(?: \S+){0,3} box(?:es)?\b")
_CLOSE_AT_PAUSE = re.compile(r"\bclose-slice\b|\bpause\b|\bsummarize slice\b|\bsummary commit\b|\bcheckpoint\b")

# The hand-off after each pause (R1.1-R1.3): the feature goes on in a new session in the same folder, opened by the
# app's session tools or left as the exact command; Phase 0 sends a session with nothing left to build to Phase 4.
_HANDOFF_NEW_SESSION = re.compile(r"\bnew session\b")
_HANDOFF_SLICE_LEFT = re.compile(r"\b(?:another|next|more|remaining) slice\b|\bslices? (?:is |are )?left\b")
_HANDOFF_PHASE_4 = re.compile(r"\bphase 4\b")
_HANDOFF_PAUSE_DONE = re.compile(r"\bsummary\b|\bnotes\b")
_HANDOFF_FOLDER = re.compile(r"\b(?:same|this) (?:folder|directory)\b")
_HANDOFF_PROMPT = re.compile(r"/konundrm-eng:develop-feature specs/<nnn-slug>(?!\s*--partition)")
_HANDOFF_TOOLS = re.compile(r"\btools?\b")
_HANDOFF_ENDS = re.compile(r"\b(?:stop|end|leave)\w*")
_HANDOFF_NO_TOOLS = re.compile(r"\b(?:without|otherwise|no such)\b")
_HANDOFF_COMMAND = re.compile(r'\bclaude "/konundrm-eng:develop-feature specs/<nnn-slug>"')
_HANDOFF_NOTHING_NEXT = re.compile(r"\bnext: none\b|\bno next task\b|\bnames no (?:next )?task\b")
_HANDOFF_CONTINUES = (_HANDOFF_NEW_SESSION, _HANDOFF_SLICE_LEFT, _HANDOFF_PHASE_4)
_HANDOFF_RULES: dict[str, tuple[re.Pattern[str], ...]] = {
    "(R1.1) a new session goes on while a slice or Phase 4 is left": _HANDOFF_CONTINUES,
    "(R1.2) the app's session tools open it in the same folder with /konundrm-eng:develop-feature specs/<nnn-slug>,"
    " and this session stops": (_HANDOFF_NEW_SESSION, _HANDOFF_TOOLS, _HANDOFF_FOLDER, _HANDOFF_PROMPT, _HANDOFF_ENDS),
    '(R1.3) without the tools, the session ends with claude "/konundrm-eng:develop-feature specs/<nnn-slug>"': (
        _HANDOFF_NO_TOOLS,
        _HANDOFF_ENDS,
        _HANDOFF_COMMAND,
    ),
}

# A dirty tree at the hand-off (R1.6): the new session resumes from the plan and the repository, so uncommitted files
# stop the pause with a BLOCKED: line naming them instead of opening it. The second rule needs the dirty tree or the
# BLOCKED: line too, since step 8 already says "without such tools ... open ... new session".
_DIRTY_TREE = re.compile(r"\buncommitted\b|\bnot (?:yet )?committed\b|\bdirty (?:working )?tree\b|\bpending changes\b")
_DIRTY_NAMES = re.compile(r"\b(?:nam|list)\w*")
_DIRTY_OPEN = re.compile(r"\bopen\w*")
_DIRTY_STOP = re.compile(_DIRTY_TREE.pattern + "|" + _BLOCKED_LINE.pattern)
_DIRTY_RULES: dict[str, tuple[re.Pattern[str], ...]] = {
    "(R1.6) uncommitted changes stop it with a BLOCKED: line naming the files": (
        _DIRTY_TREE,
        _BLOCKED_LINE,
        _DIRTY_NAMES,
        _FILES,
    ),
    "(R1.6) that stop opens no new session": (_DIRTY_STOP, _NEGATION, _DIRTY_OPEN, _HANDOFF_NEW_SESSION),
}

# One session for the whole feature (R1.7): the plan's `- **Sessions:**` line, `per-slice` by default, keeps the next
# slice in the current session when it says `single`, whether the user asked in the request, the approval or a pause.
_SESSIONS_SINGLE = re.compile(r"\bsessions:(?:\*\*)? ?single\b")
_SESSIONS_PER_SLICE = re.compile(r"\bsessions:(?:\*\*)? ?per-slice\b")
_SESSIONS_HERE = re.compile(r"\b(?:this|the same|the current) session\b")
_SESSIONS_ONE = re.compile(r"\b(?:one|a single|the same) session\b")
# Building the next slice, not any mention of a slice: "the slice's last task" in the pause's commit does not count.
_SESSIONS_BUILDS_NEXT = re.compile(r"\b(?:build|continu|go(?:es)? on|proceed|mov)\w*(?: \S+){0,3} next slice\b")
_SESSIONS_ASKED = re.compile(r"\b(?:request|approv)\w*")
_SESSIONS_PAUSE = re.compile(r"\bpaus\w*")
_SESSIONS_CHANGES = re.compile(r"\b(?:record|writ|set|chang|switch|updat|becom)\w*")
_SESSIONS_READS_AS = re.compile(r"\b(?:reads?|counts?|means?|defaults?)(?: [^\s,;:.()]+){0,2}? (?:as |to )?per-slice\b")
_SESSIONS_TEMPLATE_LINE = re.compile(r"^- \*\*sessions:\*\* per-slice\b")
_SESSIONS_TEMPLATE_DECISIONS = re.compile(r"^- \*\*decisions:\*\*")
_SESSIONS_RULES: dict[str, tuple[str, tuple[re.Pattern[str], ...]]] = {
    "Slice checkpoint lacks (R1.7): with sessions: single, the next slice is built in this session": (
        "checkpoint",
        (_SESSIONS_SINGLE, _SESSIONS_HERE, _SESSIONS_BUILDS_NEXT),
    ),
    "Phase 2 lacks (R1.7): record sessions: single when the request or approval asked for one session": (
        "plan",
        (_RECORDS, _SESSIONS_SINGLE, _SESSIONS_ONE, _SESSIONS_ASKED),
    ),
    "Phase 2 lacks (R1.7): sessions: per-slice otherwise": ("plan", (_SESSIONS_PER_SLICE, _PREAPPROVED_OTHERWISE)),
    "Phase 2 lacks (R1.7): a tasks.md without the line reads as per-slice": (
        "plan",
        (_DECISIONS_WITHOUT, _SESSIONS_READS_AS),
    ),
    "Slice checkpoint or Phase 2 lacks (R1.7): asked at a pause, the line becomes sessions: single": (
        "both",
        (_SESSIONS_PAUSE, _SESSIONS_CHANGES, _SESSIONS_SINGLE),
    ),
}


class SliceHandoffFlowTest(unittest.TestCase):
    maxDiff = None  # a failure lists every gap, not the first one

    def test_slice_checkpoint_closes_the_slice_in_the_summary_commit(self) -> None:
        """R2.8, R4.5: 002 develop-feature's Slice checkpoint runs `task_ledger.py close-slice` through run.sh before
        committing the summary, so the plan's boxes and rounds land in the summary commit, also
        with pre-approved pauses; the tasks.md template says the box is checked at the pause, not in the task's own
        commit."""
        checkpoint = _section_blocks(DEVELOP_FEATURE_DIR / "SKILL.md", "Slice checkpoint")
        template = _blocks(SKILLS_DIR / "writing-plans" / "templates" / "tasks.md")
        text = " ".join(checkpoint)
        runs = [block for block in checkpoint if _CLOSE_COMMAND.search(block)]
        number = _DELIVERY_LIST_NUMBER.match(runs[0]) if runs else None
        close_at, commit_at = _CLOSE_COMMAND.search(text), _CHECKPOINT_SUMMARY_COMMIT.search(text)

        gaps = []
        if not any(_in_one_sentence(b, *_CLOSE_RUNS) for b in checkpoint):
            gaps.append("Slice checkpoint lacks (R4.5): sh run.sh task_ledger.py close-slice specs/<...>/tasks.md S<k>")
        if not any(_in_one_sentence(b, _CLOSE_LEDGER, _CHECKPOINT_SUMMARY_COMMIT) for b in checkpoint):
            gaps.append("Slice checkpoint lacks (R2.8): close-slice's tasks.md in the summary commit")
        if not (close_at and commit_at and close_at.start() < commit_at.start()):
            gaps.append("Slice checkpoint does not run close-slice before committing the summary (R2.8)")
        if not any(
            _PREAPPROVED_LINE.search(sentence)
            and (_CLOSE_NAMED.search(sentence) or (number and int(number.group(1)) in _notes_step_numbers(sentence)))
            for block in checkpoint
            for sentence in _sentences(block)
        ):
            gaps.append("Slice checkpoint's Checkpoints: pre-approved sentence skips close-slice (R2.8)")
        gaps += [
            f"tasks.md template checks the box in the task's own commit (R2.8): {sentence.strip()}"
            for block in template
            for sentence in _sentences(block)
            if (match := _CLOSE_IN_TASK_COMMIT.search(sentence)) and not _NEGATION.search(sentence[: match.start()])
        ]
        if not any(_in_one_sentence(block, _CLOSE_CHECKS_BOX, _CLOSE_AT_PAUSE) for block in template):
            gaps.append("tasks.md template does not say develop-feature checks the box at the slice's pause (R2.8)")

        self.assertEqual(gaps, [])

    def test_feature_continues_in_a_new_session_after_each_slice(self) -> None:
        """R1.1, R1.2, R1.3: 002 develop-feature's Slice checkpoint hands the feature, once the pause ends and a slice
        or Phase 4 is left, to a new session in the same folder: the app's session tools open it with the prompt that
        resumes the feature, otherwise the session ends with the exact `claude` command; pre-approved pauses hand off
        too, and Phase 0 sends a session whose `status` names no next task to Phase 4."""
        checkpoint = _section_blocks(DEVELOP_FEATURE_DIR / "SKILL.md", "Slice checkpoint")
        prepare = _section_blocks(DEVELOP_FEATURE_DIR / "SKILL.md", "Phase 0: Prepare")
        handoff = [block for block in checkpoint if _in_one_sentence(block, *_HANDOFF_CONTINUES)]
        number = _DELIVERY_LIST_NUMBER.match(handoff[0]) if handoff else None
        go_aheads = [block for block in checkpoint if _CHECKPOINT_GO_AHEAD.search(block)]
        go_ahead = _DELIVERY_LIST_NUMBER.match(go_aheads[0]) if go_aheads else None

        gaps = [
            f"Slice checkpoint lacks {rule}"
            for rule, patterns in _HANDOFF_RULES.items()
            if not any(_in_one_sentence(block, *patterns) for block in checkpoint)
        ]
        if not any(
            _HANDOFF_NEW_SESSION.search(sentence)
            and (
                (_HANDOFF_PAUSE_DONE.search(sentence) and _CHECKPOINT_GO_AHEAD.search(sentence))
                or (go_ahead and int(go_ahead.group(1)) in _notes_step_numbers(sentence))
            )
            for block in checkpoint
            for sentence in _sentences(block)
        ):
            gaps.append("Slice checkpoint does not hand off once the summary, notes and go-ahead are done (R1.1)")
        if not any(
            _PREAPPROVED_LINE.search(sentence)
            and (
                _HANDOFF_NEW_SESSION.search(sentence)
                or (number and int(number.group(1)) in _notes_step_numbers(sentence))
            )
            for block in checkpoint
            for sentence in _sentences(block)
        ):
            gaps.append("Slice checkpoint's Checkpoints: pre-approved sentence skips the new session (R1.1)")
        if not any(_in_one_sentence(block, _HANDOFF_NOTHING_NEXT, _HANDOFF_PHASE_4) for block in prepare):
            gaps.append("develop-feature Phase 0 does not send a session with next: none to Phase 4 (R1.1)")

        self.assertEqual(gaps, [])

    def test_handoff_stops_on_uncommitted_changes(self) -> None:
        """R1.6: 002 develop-feature's Slice checkpoint, when uncommitted changes remain at the hand-off, stops with a
        `BLOCKED:` line naming those files and opens no new session, which would resume without them."""
        checkpoint = _section_blocks(DEVELOP_FEATURE_DIR / "SKILL.md", "Slice checkpoint")

        gaps = [
            f"Slice checkpoint lacks {rule}"
            for rule, patterns in _DIRTY_RULES.items()
            if not any(_in_one_sentence(block, *patterns) for block in checkpoint)
        ]

        self.assertEqual(gaps, [])

    def test_sessions_single_keeps_the_feature_in_one_session(self) -> None:
        """R1.7: 002 develop-feature builds the next slice in the current session when the plan says
        `- **Sessions:** single`, recorded in Phase 2 when the user asked for one session in the request or the plan's
        approval, or at a pause; otherwise `per-slice`, which a plan without the line reads as; the tasks.md template's
        header carries `- **Sessions:** per-slice` after its `- **Decisions:**` line."""
        checkpoint = _section_blocks(DEVELOP_FEATURE_DIR / "SKILL.md", "Slice checkpoint")
        plan = _section_blocks(DEVELOP_FEATURE_DIR / "SKILL.md", "Phase 2: Plan")
        sections = {"checkpoint": checkpoint, "plan": plan, "both": checkpoint + plan}
        header = (SKILLS_DIR / "writing-plans" / "templates" / "tasks.md").read_text(encoding="utf-8").split("\n## ")[0]
        items = _split_blocks(header.splitlines())
        decisions = next((i for i, item in enumerate(items) if _SESSIONS_TEMPLATE_DECISIONS.match(item)), len(items))

        gaps = [
            rule
            for rule, (where, patterns) in _SESSIONS_RULES.items()
            if not any(_in_one_sentence(block, *patterns) for block in sections[where])
        ]
        if not any(_SESSIONS_TEMPLATE_LINE.match(item) for item in items[decisions + 1 :]):
            gaps.append("writing-plans tasks.md template lacks (R1.7): - **Sessions:** per-slice after Decisions")

        self.assertEqual(gaps, [])


# The flow's data lives in a Git note under refs/notes/konundrm, never in a commit message (003 R6.1-R6.4, R9.1).
# These check keywords of each rule, on blocks from _blocks (lowercased, no backticks) or on the raw Markdown.
_FLOW_NOTES_SKILLS = (
    "develop-feature",
    "committing-changes",
    "fix-bug",
    "opening-pull-requests",
    "reviewing-pull-requests",
    "engineering-standards",
)
_FLOW_NOTES_SEARCHING_SKILLS = ("develop-feature", "opening-pull-requests", "reviewing-pull-requests")
_FLOW_NOTES_REF = "--notes=refs/notes/konundrm"
# The last four are the lines 004 adds to notes: an adjustment's (R4.6) and a task's reviews not repeated (R3.8).
_FLOW_LINE = re.compile(r"\b(?:task|covers|rounds|escaped-gate|adjusts|reviews|asked|not repeated):")
_FLOW_SEARCH_LINE = re.compile(r"\b(?:task|covers|adjusts):")
# Where a flow line would go if it went into the commit: its body, trailers or message, or a commit that carries it.
_FLOW_IN_THE_MESSAGE = re.compile(
    r"\bbody\b|\btrailers?\b|\bmessage\b|\bcarr(?:y|ies|ying)\b|\bcommit (?:records?|holds?|has)\b"
    r"|\bwith (?:the|its|that|this|a)\b(?: \S+){0,4} (?:task|covers|rounds|escaped-gate|adjusts|reviews|asked):"
    r" line\b"
)
_FLOW_IDS_IN_THE_BODY = re.compile(r"\btask(?: and requirement)? ids?\b(?: \S+){0,2} (?:body|message)\b")
_FLOW_IN_A_NOTE = re.compile(r"\bnotes?\b")
# A fenced commit message: a Conventional Commits subject line, and a flow line of its own.
_FLOW_FENCE = re.compile(r"^```[^\n]*\n(.*?)^```", re.MULTILINE | re.DOTALL)
_FLOW_FENCE_SUBJECT = re.compile(r"^[a-z]+(?:\([^)\n]*\))?!?: \S", re.MULTILINE)
_FLOW_FENCE_LINE = re.compile(r"^(?:Task|Covers|Rounds|Escaped-gate|Adjusts|Reviews|Asked|Not repeated):", re.MULTILINE)
# A commit subject template in inline code, and what R6.1 keeps out of it: slices, partitions, rounds and flow IDs.
_FLOW_SUBJECT_SPAN = re.compile(r"^\w+\([^)]*\)!?: ")
_FLOW_SUBJECT_NAMES_THE_FLOW = re.compile(r"\b(?:slice|partition|rounds?)\b|\b[SPTRB]<[kn]>|\b[TRB]\d", re.IGNORECASE)
_FLOW_INLINE_CODE = re.compile(r"`([^`\n]+)`")
# The task's commit in one command (R6.2): `message`, then `git commit -F`, then `record`.
_FLOW_MESSAGE_COMMIT_RECORD = re.compile(
    r"\btask_ledger\.py message\b.*?&& git commit -f\b[^&]*&&[^&]*\btask_ledger\.py record\b"
)
_FLOW_ROUNDS = re.compile(r"\brounds\b")
_FLOW_ROUNDS_IN_THE_MESSAGE = re.compile(
    r"\brounds\b(?: \S+){0,6} commit message\b|\bcommit message\b(?: \S+){0,4} --rounds\b"
)
_FLOW_RECORD = "task_ledger.py record"
_FLOW_STATUS = "task_ledger.py status"
_FLOW_FIRST = re.compile(r"\b(?:first|before)\b")
_FLOW_GIT_LOG = re.compile(r"\bgit log\b")
_FLOW_SUMMARY_FILE = re.compile(r"\bsummaries/s<k>\.md\b")
_FLOW_NOTES_COPY = re.compile(r"\bgit notes --ref[= ]refs/notes/konundrm copy\b")
_FLOW_NOTES_ADD = re.compile(r"\bgit notes --ref[= ]refs/notes/konundrm add\b")
_FLOW_COVERS = re.compile(r"\bcovers:")
_FLOW_ESCAPED_GATE = re.compile(r"\bescaped-gate:")
_FLOW_SLICE_ENDS = re.compile(r"\bslice\b.*\bends?\b|\bends?\b.*\bslice\b")
_FLOW_LAST_TASK_COMMIT = re.compile(r"\blast\b(?: \S+){0,4} commit")
_FLOW_FALLBACK = re.compile(r"\b(?:otherwise|fall\w* back|without|lacks?|no|when there is none)\b")


def _flow_lines_in_messages(skill: str) -> list[str]:
    """Return each instruction of a skill that puts a Task:, Covers:, Rounds: or Escaped-gate: line, or an
    adjustment's Adjusts:, Reviews: or Asked: line (004 R4.6), in a commit: a sentence that names such a line and
    its body, trailers or message (unnegated, and with no note in it), a sentence that puts task or requirement IDs
    in the body, and a fenced commit message with such a line."""
    path = SKILLS_DIR / skill / "SKILL.md"
    gaps = [
        f"{skill}: puts a flow line in a commit message (R6.1): {sentence.strip()}"
        for block in _blocks(path)
        for sentence in _sentences(block)
        if (
            _FLOW_LINE.search(sentence)
            and _unnegated(sentence, _FLOW_IN_THE_MESSAGE)
            and not _FLOW_IN_A_NOTE.search(sentence)
        )
        or _unnegated(sentence, _FLOW_IDS_IN_THE_BODY)
    ]
    gaps += [
        f"{skill}: a fenced commit message carries a flow line (R6.1): {fence.splitlines()[0]!r}"
        for fence in _FLOW_FENCE.findall(path.read_text(encoding="utf-8"))
        if _FLOW_FENCE_SUBJECT.search(fence) and _FLOW_FENCE_LINE.search(fence)
    ]
    gaps += [
        f"{skill}: a commit subject names the flow (R6.1): `{span}`"
        for span in _FLOW_INLINE_CODE.findall(path.read_text(encoding="utf-8"))
        if _FLOW_SUBJECT_SPAN.match(span) and _FLOW_SUBJECT_NAMES_THE_FLOW.search(span)
    ]
    return gaps


def _flow_searches_without_notes(skill: str) -> list[str]:
    """Return each search for a Task:, Covers: or Adjusts: line in a skill that does not read the konundrm notes:
    inline code with `--grep` on such a line, or a sentence that names `git log` and such a line, without
    `--notes=refs/notes/konundrm` (R6.2, 004 R4.8), plus any `--grep` on a summary subject (R6.1: the summary is
    found by its file)."""
    path = SKILLS_DIR / skill / "SKILL.md"
    spans = _FLOW_INLINE_CODE.findall(path.read_text(encoding="utf-8"))
    gaps = [
        f"{skill}: searches a flow line without {_FLOW_NOTES_REF} (R6.2): `{span}`"
        for span in spans
        if "--grep" in span and re.search(r"\b(?:Task|Covers|Adjusts):", span) and _FLOW_NOTES_REF not in span
    ]
    gaps += [
        f"{skill}: git log reads a flow line without {_FLOW_NOTES_REF} (R6.2): {sentence.strip()}"
        for block in _blocks(path)
        for sentence in _sentences(block)
        if _FLOW_GIT_LOG.search(sentence) and _FLOW_SEARCH_LINE.search(sentence) and _FLOW_NOTES_REF not in sentence
    ]
    gaps += [
        f"{skill}: finds a summary by its subject, not its file (R6.1): `{span}`"
        for span in spans
        if "--grep" in span and "summar" in span
    ]
    return gaps


def _flow_task_commit_gaps(skill: Path) -> list[str]:
    """Return what develop-feature's step 7 and Phase 0 lack: the task committed as message → git commit → record in
    one command, its rounds in its note, and the resume running `record` before anything else (R6.2, R6.4)."""
    phase_3 = _section_blocks(skill, "Phase 3: Task loop")
    step_7 = [block for block in phase_3 if block.startswith("7. **commit.**")]
    prepare = _section_blocks(skill, "Phase 0: Prepare")
    prepare_text = " ".join(prepare)
    gaps = []
    if not any(_FLOW_MESSAGE_COMMIT_RECORD.search(block) for block in step_7):
        gaps.append(
            "develop-feature step 7 lacks (R6.2): task_ledger.py message && … git commit -F … && task_ledger.py record"
            " in one command"
        )
    if not any(_in_one_sentence(block, _FLOW_ROUNDS, _FLOW_IN_A_NOTE) for block in step_7):
        gaps.append("develop-feature step 7 lacks (R6.2): the task's rounds live in its note")
    gaps += [
        f"develop-feature Phase 3 keeps the rounds in the commit message (R6.1): {sentence.strip()}"
        for block in phase_3
        for sentence in _sentences(block)
        if _unnegated(sentence, _FLOW_ROUNDS_IN_THE_MESSAGE)
    ]
    record_at, status_at = prepare_text.find(_FLOW_RECORD), prepare_text.find(_FLOW_STATUS)
    if record_at < 0 or (status_at >= 0 and record_at > status_at):
        gaps.append("develop-feature Phase 0 resume does not run task_ledger.py record before status (R6.4)")
    if not any(
        _FLOW_RECORD in sentence and _FLOW_FIRST.search(sentence) for block in prepare for sentence in _sentences(block)
    ):
        gaps.append("develop-feature Phase 0 lacks (R6.4): a sentence that runs task_ledger.py record first")
    if not any(_in_one_sentence(block, _FLOW_GIT_LOG, _FLOW_SUMMARY_FILE) for block in prepare):
        gaps.append("develop-feature Phase 0 lacks (R6.1): finding a slice's summary with git log … summaries/S<k>.md")
    return gaps


def _flow_fix_bug_note_gaps() -> list[str]:
    """Return one message per fix-bug commit step (fix-bug's step 8, committing-changes' fix-bug mode) that does not
    write `Covers:` and `Escaped-gate:` with `git notes --ref=refs/notes/konundrm add` (R6.2)."""
    fix_bug = _subsection_blocks(
        _section_blocks(SKILLS_DIR / "fix-bug" / "SKILL.md", "Workflow"), "### 8. gate and commit"
    )
    committing = _subsection_blocks(
        _section_blocks(SKILLS_DIR / "committing-changes" / "SKILL.md", "Workflow"), "### inside fix-bug"
    )
    return [
        f"{where} lacks (R6.2): git notes --ref=refs/notes/konundrm add with Covers: and Escaped-gate:"
        for where, blocks in (("fix-bug step 8", fix_bug), ("committing-changes ### Inside fix-bug", committing))
        if not any(
            _FLOW_NOTES_ADD.search(block) and _FLOW_COVERS.search(block) and _FLOW_ESCAPED_GATE.search(block)
            for block in blocks
        )
    ]


def _flow_slice_end_gaps() -> list[str]:
    """Return a message when opening-pull-requests does not end a slice at the commit that adds its summaries/S<k>.md,
    falling back to the slice's last task commit (R6.1: no summary subject or Task: line to find it by)."""
    blocks = _blocks(SKILLS_DIR / "opening-pull-requests" / "SKILL.md")
    if any(
        _FLOW_SUMMARY_FILE.search(block)
        and _FLOW_SLICE_ENDS.search(block)
        and _FLOW_LAST_TASK_COMMIT.search(block)
        and _FLOW_FALLBACK.search(block)
        for block in blocks
    ):
        return []
    return [
        "opening-pull-requests lacks (R6.1): a slice ends at the commit that adds summaries/S<k>.md, else at its last"
        " task commit"
    ]


class FlowDataInNotesTest(unittest.TestCase):
    maxDiff = None  # a failure lists every gap, not the first one

    def test_commits_carry_no_flow_lines_and_keep_their_data_in_notes(self) -> None:
        """R6.1, R6.2, R6.3, R6.4: 003 every commit the plugin's flows make carries only what changes, and the flow's
        data lives in a Git note under refs/notes/konundrm (R9.1: checked here, without a model).

        No sentence of develop-feature, committing-changes, fix-bug, opening-pull-requests, reviewing-pull-requests or
        engineering-standards puts a `Task:`, `Covers:`, `Rounds:` or `Escaped-gate:` line in a commit's body,
        trailers or message, or the task and requirement IDs in its body; no fenced commit message carries one; and
        no commit subject template names a slice, partition or round. develop-feature commits a task as
        `task_ledger.py message` → `git commit -F` → `task_ledger.py record` in one command, its rounds in its note;
        resumes by running `record` before `status`; finds a slice's summary by `summaries/S<k>.md`; and copies each
        integrated commit's note with `git notes --ref=refs/notes/konundrm copy`. Every `Task:` / `Covers:` search
        in develop-feature, opening-pull-requests and reviewing-pull-requests reads `--notes=refs/notes/konundrm`;
        opening-pull-requests ends a slice at the commit that adds its summary, else at its last task commit; and
        fix-bug (and committing-changes' fix-bug mode) writes `Covers:` and `Escaped-gate:` with
        `git notes --ref=refs/notes/konundrm add`."""
        develop_feature = DEVELOP_FEATURE_DIR / "SKILL.md"

        gaps = [gap for skill in _FLOW_NOTES_SKILLS for gap in _flow_lines_in_messages(skill)]
        gaps += [gap for skill in _FLOW_NOTES_SEARCHING_SKILLS for gap in _flow_searches_without_notes(skill)]
        gaps += _flow_task_commit_gaps(develop_feature)
        if not any(_FLOW_NOTES_COPY.search(block) for block in _section_blocks(develop_feature, "Parallel partitions")):
            gaps.append("develop-feature Parallel partitions lacks (R6.3): git notes --ref=refs/notes/konundrm copy")
        gaps += _flow_slice_end_gaps()
        gaps += _flow_fix_bug_note_gaps()

        self.assertEqual(gaps, [])


# Live publishing (003 R1.1-R1.4, R2.1-R2.3, R3.1-R3.6, R9.1): develop-feature asks at plan approval whether to publish
# while it builds, records `- **Publish:** live|local`, and in live mode pushes each slice branch and each flow commit.
# These check keywords of each rule inside its section, on blocks from _blocks (lowercased, no backticks).
_LIVE = re.compile(r"\bpublish:(?:\*\*)? ?live\b|\blive\b")
_LIVE_LINE = re.compile(r"\bpublish:(?:\*\*)? ?live\b")
_LIVE_LOCAL = re.compile(r"\bpublish:(?:\*\*)? ?local\b|\blocal\b")
_LIVE_PUSH = re.compile(r"\bpush\w*")
_LIVE_PUBLISH = re.compile(r"\bpublish\w*")
_LIVE_ASK = re.compile(r"\bask\w*|\bquestion\b")
_LIVE_SEPARATE = re.compile(r"\b(?:separate|apart|own)\b")
_LIVE_REMOTE_CHECK = re.compile(r"\bgit remote get-url origin\b")
_LIVE_GH_CHECK = re.compile(r"\bgh repo view\b")
_LIVE_MISSING = re.compile(r"\bmissing\b|\blacks?\b|\bwithout\b|\bfails?\b")
_LIVE_SAYS = re.compile(r"\bone line\b|\bone-line\b|\bsay\w*|\btell\w*|\bnam(?:e|es|ing)\b")
_LIVE_EXPLICIT_YES = re.compile(r"\byes\b|\brequest\b|\basked for\b")
_LIVE_WITHOUT_THE_LINE = re.compile(r"\b(?:without|lacks?|no)\b(?: \S+){0,4} line\b")
_LIVE_RESUMES = re.compile(r"\bresum\w*")
_LIVE_NEVER_ASKS = re.compile(r"\b(?:never|not|without|no)\b(?: \S+){0,4} ask\w*")
_LIVE_SWITCH_C = re.compile(r"\bgit switch -c feat/<nnn-slug>-s<k>")
_LIVE_PUSH_U = re.compile(r"\bgit push (?:-u|--set-upstream) origin feat/<nnn-slug>-s<k>")
_LIVE_FIRST_SLICE = re.compile(r"\bs1\b|\bfirst slice\b")
_LIVE_PLAN_COMMIT = re.compile(r"\bplan\b")
_LIVE_PREVIOUS_SLICE = re.compile(r"\b(?:previous|earlier|prior) slice\b|\bslice before\b")
_LIVE_TIP = re.compile(r"\btip\b|\bhead\b|\bbranch\b")
_LIVE_ALREADY_EXISTS = re.compile(r"\balready exists?\b|\bexists already\b")
_LIVE_SWITCH = re.compile(r"\bswitch\w*")
_LIVE_NOT_AGAIN = re.compile(r"\b(?:never|not|without|no)\b(?: \S+){0,4} (?:creat\w*|again|anew)")
_LIVE_GIT_PUSH = re.compile(r"\bgit push\b")
_LIVE_NEXT_TASK = re.compile(r"\b(?:next|following) task\b")
_LIVE_FLOW_COMMITS = {
    "the slice summary": re.compile(r"\bsummar\w*"),
    "plan changes": re.compile(r"\bplan (?:change|edit)\w*"),
    "partition integration": re.compile(r"\bintegrat\w*"),
    "the feature's closing commit": re.compile(r"\bfinal\b|\bclos\w*|\bfinish\w*"),
}
_LIVE_AFTER = re.compile(r"\b(?:after|once|when)\b")
_LIVE_CHECK_PASSES = re.compile(r"\bcheck\b(?: \S+){0,4} (?:pass\w*|green)\b")
_LIVE_PARTITION_BRANCH = re.compile(r"\bwave/|\bpartition(?:'s|s'|s)? branch")
_LIVE_UNPUSHED = re.compile(r"\bremote\b|\bupstream\b|\bunpushed\b|\bnot (?:yet )?pushed\b")
_LIVE_FIRST = re.compile(r"\bfirst\b|\bbefore\b")
_LIVE_FAILS = re.compile(r"\bfail\w*|\breject\w*")
_LIVE_ERROR = re.compile(r"\berror\b")
_LIVE_NEVER_FORCES = re.compile(r"\b(?:never|not|no|nor|without)\b(?: \S+){0,4} (?:--force\b|forc\w*)")
_LIVE_NEVER_PULLS = re.compile(r"\b(?:never|not|no|nor|without)\b(?: \S+){0,6} (?:pull(?!\w* requests?\b)|fetch)\w*")
_LIVE_ONLY_MAIN = re.compile(r"\bonly\b(?: \S+){0,6} main session\b")
_LIVE_TEMPLATE_LINE = re.compile(r"- \*\*publish:\*\* local\b")
_LIVE_NOT_LIVE = re.compile(r"\b(?:without|unless|no)\b(?: \S+){0,2} publish:(?:\*\*)? ?live\b")
_LIVE_NOTHING_PUSHED = re.compile(r"\b(?:nothing|never|not|no)\b(?: \S+){0,4} push\w*")
_LIVE_BEFORE = re.compile(r"\bbefore\b")
_LIVE_PHASE_4 = re.compile(r"\bphase 4\b")
_LiveRules = dict[str, tuple[list[str], tuple[re.Pattern[str], ...]]]


def _live_rule_gaps(rules: _LiveRules) -> list[str]:
    """Return the name of each rule no sentence of its blocks matches with every one of its patterns."""
    return [
        rule for rule, (blocks, patterns) in rules.items() if not any(_in_one_sentence(b, *patterns) for b in blocks)
    ]


def _live_develop_feature_rules(skill: Path) -> _LiveRules:
    """Return each live-publishing rule of develop-feature's SKILL.md, with the blocks that must hold it."""
    prepare = _section_blocks(skill, "Phase 0: Prepare")
    plan = _section_blocks(skill, "Phase 2: Plan")
    loop = _section_blocks(skill, "Phase 3: Task loop")
    partitions = _section_blocks(skill, "Parallel partitions")
    finish = _section_blocks(skill, "Phase 4: Finish")
    everything = _blocks(skill)
    rules: _LiveRules = {
        "Phase 2 lacks (R1.1): a separate question whether to publish while building": (
            plan,
            (_LIVE_ASK, _LIVE_SEPARATE, _LIVE_PUBLISH),
        ),
        "Phase 2 lacks (R1.1): Publish: live recorded only on an explicit yes or the request": (
            plan,
            (_LIVE_LINE, _LIVE_EXPLICIT_YES),
        ),
        "Phase 2 lacks (R1.2): saying in one line what is missing and recording local": (
            plan,
            (_LIVE_MISSING, _LIVE_SAYS, _LIVE_LOCAL),
        ),
        "Phase 2 lacks (R1.3): a tasks.md without the Publish line reads as local": (
            plan,
            (_LIVE_PUBLISH, _LIVE_WITHOUT_THE_LINE, _LIVE_LOCAL),
        ),
        "Phase 0 or 2 lacks (R1.4): a resumed session follows the Publish choice without asking again": (
            prepare + plan,
            (_LIVE_RESUMES, _LIVE_PUBLISH, _LIVE_NEVER_ASKS),
        ),
        # The invariant of R1.3: a plan that does not say live (or predates the line) publishes nothing early.
        "Phase 3 lacks (R1.3): without Publish: live, nothing is pushed before Phase 4's question": (
            loop,
            (_LIVE_NOT_LIVE, _LIVE_NOTHING_PUSHED, _LIVE_BEFORE, _LIVE_PHASE_4),
        ),
        "Phase 4 lacks (R1.3): asking before pushing": (finish, (_LIVE_ASK, _LIVE_BEFORE, _LIVE_PUSH)),
        "Phase 3 lacks (R2.1): S1's branch cut from the commit that adds the spec and plan": (
            loop,
            (_LIVE_FIRST_SLICE, _LIVE_PLAN_COMMIT),
        ),
        "Phase 3 lacks (R2.2): slice k's branch cut from the tip of the previous slice's branch": (
            loop,
            (_LIVE_PREVIOUS_SLICE, _LIVE_TIP),
        ),
        # The branch may exist without an upstream (its first push failed), and a bare `git push` fails there.
        "Phase 3 lacks (R2.3): switching to a slice branch that already exists instead of creating it, then"
        " git push -u origin feat/<NNN-slug>-s<k>": (
            loop,
            (_LIVE_ALREADY_EXISTS, _LIVE_SWITCH, _LIVE_NOT_AGAIN, _LIVE_PUSH_U),
        ),
        "Phase 3 lacks (R3.1): git push of each task commit before the next task": (
            loop,
            (_LIVE_GIT_PUSH, _LIVE_NEXT_TASK),
        ),
        "Parallel partitions lacks (R3.3): pushing integrated commits after the check passes": (
            partitions,
            (_LIVE_PUSH, _LIVE_AFTER, _LIVE_CHECK_PASSES),
        ),
        "Parallel partitions lacks (R3.3): never pushing a partition's branch": (
            partitions,
            (_NEVER_PUSHES, _LIVE_PARTITION_BRANCH),
        ),
        "Phase 0 lacks (R3.4): a resumed live feature first pushes what the remote lacks with"
        " git push -u origin feat/<NNN-slug>-s<k>": (
            prepare,
            (_LIVE_PUSH, _LIVE_UNPUSHED, _LIVE_FIRST, _LIVE_PUSH_U),
        ),
        "develop-feature lacks (R3.5): a failed push stops with BLOCKED: quoting Git's error": (
            everything,
            (_BLOCKED, _LIVE_PUSH, _LIVE_FAILS, _LIVE_ERROR),
        ),
        "develop-feature lacks (R3.5): a push is never forced": (everything, (_LIVE_PUSH, _LIVE_NEVER_FORCES)),
        "develop-feature lacks (R3.5): a failed push pulls nothing from the remote": (
            everything,
            (_LIVE_PUSH, _LIVE_NEVER_PULLS),
        ),
        "develop-feature lacks (R3.6): publishing only from the main session": (
            everything,
            (_LIVE_PUSH, _LIVE_ONLY_MAIN),
        ),
    }
    for kind, pattern in _LIVE_FLOW_COMMITS.items():
        rules[f"develop-feature lacks (R3.2): pushing {kind} as soon as it is made in live mode"] = (
            everything,
            (_LIVE, _LIVE_PUSH, pattern),
        )
    return rules


def _live_develop_feature_gaps() -> list[str]:
    """Return one message per live-publishing rule develop-feature's SKILL.md lacks in the section that owns it."""
    skill = DEVELOP_FEATURE_DIR / "SKILL.md"
    plan = _section_blocks(skill, "Phase 2: Plan")
    loop = _section_blocks(skill, "Phase 3: Task loop")
    gaps = _live_rule_gaps(_live_develop_feature_rules(skill))
    if not any(_LIVE_REMOTE_CHECK.search(block) and _LIVE_GH_CHECK.search(block) for block in plan):
        gaps.append("Phase 2 lacks (R1.1, R1.2): git remote get-url origin and gh repo view before the question")
    if not any(_LIVE_SWITCH_C.search(block) and _LIVE_PUSH_U.search(block) and _LIVE.search(block) for block in loop):
        gaps.append(
            "Phase 3 lacks (R2.1, R2.2): in live mode, git switch -c feat/<NNN-slug>-s<k> and"
            " git push -u origin feat/<NNN-slug>-s<k>"
        )
    return gaps


# Stacked pull requests per slice (003 R4.1-R4.9, R9.1): in live mode each slice ends in its pull request, stacked on
# the previous slice's, and opening-pull-requests writes the merge order into every stacked pull request, live or at the
# end of a local feature. Keywords of each rule inside its section, on blocks from _blocks (lowercased, no backticks).
_STACK_GH_PR_CREATE = re.compile(r"\bgh pr create --base (?:<[^>]*>|\S+) --head feat/<nnn-slug>-s<k>")
_STACK_OPENS_PR = re.compile(r"\bgh pr create\b|\bopen\w*\b(?: \S+){0,4} (?:pull requests?|prs?)\b")
_STACK_PR = re.compile(r"\bpull requests?\b|\bprs?\b|\bgh pr create\b")
_STACK_AFTER_PUSH = re.compile(r"\bpush\w*|\bafter\b|\bonce\b|\bthen\b")
_STACK_DEFAULT_BRANCH = re.compile(r"\bdefault branch\b")
_STACK_BASE = re.compile(r"\bbase\b|\bagainst\b|--base\b")
_STACK_BRANCH = re.compile(r"\bbranch\b")
_STACK_NOT_DRAFT = re.compile(r"\bready for review\b|\b(?:never|not|no|without)\b(?: \S+){0,4} (?:--)?drafts?\b")
_STACK_GONE = re.compile(r"\bno longer\b|\bgone\b|\bdeleted\b|\bmissing\b|\bnot (?:on|in) the remote\b")
# R4.2: a branch never pushed (a local delivery's slices before step 5) is absent too, so its absence alone must not
# send the pull request to the default branch: the fallback requires the previous pull request to be merged.
_STACK_MERGED_PR = re.compile(
    r"--state merged\b|\b(?:pull requests?|prs?)\b(?: \S+){0,4} merged\b|\bmerged (?:pull requests?|prs?)\b"
)
_STACK_REQUIRES = re.compile(r"\bonly\b|\brequir\w*|--state merged\b")
_STACK_POSITION = re.compile(r"\((?:<?k>?|\d+)/(?:<?n>?|\d+)\)")
_STACK_TITLE = re.compile(r"\btitles?\b")
_STACK_SLICES = re.compile(r"\bslices?\b")
_STACK_PLAN = re.compile(r"\bplan\b|\btasks\.md\b")
_STACK_TOTAL = re.compile(r"\btotal\b|\bnumber of\b|\bhow many\b|\bcount\b")
_STACK_MERGE_ORDER = re.compile(r"merge order: (?:<[^>]+>|\w+) of (?:<[^>]+>|\w+)\. merge #(?:<[^>]+>|\d+) first\.")
_STACK_MERGE_FIRST = re.compile(r"merge order: 1 of (?:<[^>]+>|\w+)\. merge this one first\.")
_STACK_STARTS = re.compile(r"\bstart\w*|\bbegin\w*|\bfirst line\b|\bbefore any section\b")
_STACK_OLD_STACKED_ON = re.compile(r"\bstacked on #")
_STACK_RISK_HIGH = re.compile(r"\brisk:high\b")
_STACK_ONLY = re.compile(r"\bonly\b")
_STACK_LABEL_EXISTS = re.compile(r"\bexist\w*|\bgh label list\b|\bhas (?:the |that |this )?(?:label|it)\b")
_STACK_LABEL = re.compile(r"\blabel\b")
_STACK_NEVER_CREATES = re.compile(r"\b(?:never|without|nor|not)\b (?:\S+ ){0,2}?creat\w*")
_STACK_ASKS_TO_CREATE = re.compile(r"\bask\w* before creat\w*")
_STACK_SAYS = re.compile(r"\bsay\w*|\btell\w*|\bmention\w*|\bwarn\w*|\breport\w*")
_STACK_PAUSE = re.compile(r"\bpaus\w*|\bcheckpoint\b")
_STACK_ALREADY_OPEN = re.compile(
    r"\balready\b(?: \S+){0,4} open\b|\bopen (?:pull request|pr)\b(?: \S+){0,4} already\b"
    r"|\bexisting (?:open )?(?:pull request|pr)\b"
)
_STACK_NO_DUPLICATE = re.compile(
    r"\b(?:never|not|no|without)\b(?: \S+){0,4} (?:another|second|again|duplicat\w*|new one)\b"
)
_STACK_GH = re.compile(r"\bgh\b")
_STACK_FAILS = re.compile(r"\bfail\w*|\bcannot\b|\bcan't\b|\breject\w*")
_STACK_URLS = re.compile(r"\burls?\b")
_STACK_IN_ORDER = re.compile(r"\border\b")
_STACK_SHOWS = re.compile(r"\bpaus\w*|\bshow\w*|\bstop\w*")
_STACK_SESSION_MESSAGE = re.compile(r"\b(?:closing|session'?s?|final) message\b|\bmessage of the session\b")
_STACK_NO_PR = re.compile(r"\b(?:without|lacks?|no|missing|has no)\b(?: \S+){0,4} (?:pull requests?|prs?)\b")
_STACK_FIRST = re.compile(r"\bbefore\b|\bfirst\b")
_STACK_LAST_SLICE = re.compile(r"\blast slice\b")
_STACK_INSTEAD_OF_ASKING = re.compile(
    r"\b(?:instead of|rather than) ask\w*|\b(?:never|not|no|without)\b(?: \S+){0,4} ask\w*"
    r"|\bskip\w*(?: \S+){0,3} question\b"
)
_STACK_NOT_LIVE = re.compile(
    r"\blocal\b|\botherwise\b|\b(?:without|unless|no)\b(?: \S+){0,2} publish:(?:\*\*)? ?live\b"
)


def _stacked_pull_request_rules(develop_feature: Path, opening: Path) -> _LiveRules:
    """Return each stacked-pull-request rule of develop-feature and opening-pull-requests, with the blocks that hold it.

    The pull request mechanics may sit in develop-feature's Slice checkpoint or in opening-pull-requests, which it runs;
    the title and the merge-order line must sit in opening-pull-requests, so a local feature's delivery stacks the same.
    """
    prepare = _section_blocks(develop_feature, "Phase 0: Prepare")
    checkpoint = _section_blocks(develop_feature, "Slice checkpoint")
    finish = _section_blocks(develop_feature, "Phase 4: Finish")
    opening_blocks = _blocks(opening)
    mechanics = checkpoint + opening_blocks
    live_prepare = [block for block in prepare if _LIVE.search(block)]
    return {
        "Slice checkpoint lacks (R4.1): in live mode, opening the slice's pull request once its summary is pushed": (
            checkpoint,
            (_LIVE, _STACK_OPENS_PR, _STACK_AFTER_PUSH),
        ),
        "Slice checkpoint or opening-pull-requests lacks (R4.1): the first slice's pull request against the default"
        " branch": (mechanics, (_LIVE_FIRST_SLICE, _STACK_DEFAULT_BRANCH, _STACK_BASE)),
        "Slice checkpoint or opening-pull-requests lacks (R4.1): each later pull request against the previous slice's"
        " branch": (mechanics, (_LIVE_PREVIOUS_SLICE, _STACK_BRANCH, _STACK_BASE)),
        "Slice checkpoint or opening-pull-requests lacks (R4.1): the pull request opened ready for review, not as a"
        " draft": (mechanics, (_STACK_PR, _STACK_NOT_DRAFT)),
        "opening-pull-requests lacks (R4.2): against the default branch only when the previous slice's pull request"
        " is merged and its branch is gone from the remote": (
            opening_blocks,
            (_LIVE_PREVIOUS_SLICE, _STACK_GONE, _STACK_MERGED_PR, _STACK_REQUIRES, _STACK_DEFAULT_BRANCH),
        ),
        "opening-pull-requests lacks (R4.3): each title ends with its position and the total, (k/N)": (
            opening_blocks,
            (_STACK_TITLE, _STACK_POSITION),
        ),
        "opening-pull-requests lacks (R4.3): N is the number of slices the plan has": (
            opening_blocks,
            (_STACK_SLICES, _STACK_PLAN, _STACK_TOTAL),
        ),
        "Slice checkpoint or opening-pull-requests lacks (R4.4): risk:high only if the repository has the label": (
            mechanics,
            (_STACK_RISK_HIGH, _STACK_ONLY, _STACK_LABEL_EXISTS),
        ),
        "Slice checkpoint or opening-pull-requests lacks (R4.4): never creating the label": (
            mechanics,
            (_STACK_LABEL, _STACK_NEVER_CREATES),
        ),
        "Slice checkpoint or opening-pull-requests lacks (R4.4): saying at the slice's pause that the label is"
        " missing": (mechanics, (_STACK_LABEL, _STACK_SAYS, _STACK_PAUSE)),
        "Slice checkpoint or opening-pull-requests lacks (R4.5): no second pull request for a branch that already has"
        " an open one": (mechanics, (_STACK_ALREADY_OPEN, _STACK_NO_DUPLICATE)),
        "Slice checkpoint or opening-pull-requests lacks (R4.7): BLOCKED: quoting the error when gh cannot open the"
        " pull request": (mechanics, (_BLOCKED, _STACK_GH, _STACK_PR, _STACK_FAILS, _LIVE_ERROR)),
        "Slice checkpoint lacks (R4.8): the pause shows the feature's pull request URLs in merge order": (
            checkpoint,
            (_STACK_URLS, _STACK_PR, _STACK_IN_ORDER, _STACK_SHOWS),
        ),
        "Slice checkpoint lacks (R4.8): with pre-approved pauses, the session's message lists the URLs": (
            checkpoint,
            (_STACK_URLS, _STACK_SESSION_MESSAGE),
        ),
        "Phase 0 lacks (R4.6): a resumed live feature first opens the pull request a finished slice lacks": (
            live_prepare,
            (_STACK_SLICES, _STACK_NO_PR, _STACK_OPENS_PR, _STACK_FIRST),
        ),
        "Phase 4 lacks (R4.9): in live mode, pushing the final commit to the last slice's branch": (
            finish,
            (_LIVE, _LIVE_PUSH, _STACK_LAST_SLICE),
        ),
        "Phase 4 lacks (R4.9): in live mode, listing every pull request URL in merge order": (
            finish,
            (_LIVE, _STACK_URLS, _STACK_IN_ORDER),
        ),
        "Phase 4 lacks (R4.9): in live mode, not asking whether to push": (finish, (_LIVE, _STACK_INSTEAD_OF_ASKING)),
        # The invariant: a local feature still asks before anything goes up.
        "Phase 4 lacks (invariant): in local mode, asking before pushing": (
            finish,
            (_STACK_NOT_LIVE, _LIVE_ASK, _LIVE_BEFORE, _LIVE_PUSH),
        ),
    }


def _stacked_pull_request_gaps() -> list[str]:
    """Return one message per stacked-pull-request rule the two skills lack, and per old rule they still state."""
    develop_feature = DEVELOP_FEATURE_DIR / "SKILL.md"
    opening = SKILLS_DIR / "opening-pull-requests" / "SKILL.md"
    opening_blocks = _blocks(opening)
    mechanics = _section_blocks(develop_feature, "Slice checkpoint") + opening_blocks
    gaps = _live_rule_gaps(_stacked_pull_request_rules(develop_feature, opening))
    if not any(_STACK_GH_PR_CREATE.search(block) for block in mechanics):
        gaps.append(
            "Slice checkpoint or opening-pull-requests lacks (R4.1): gh pr create --base <base> --head"
            " feat/<NNN-slug>-s<k>"
        )
    if not any(_STACK_MERGE_ORDER.search(block) and _STACK_STARTS.search(block) for block in opening_blocks):
        gaps.append(
            "opening-pull-requests lacks (R4.3): the description starts with Merge order: k of N. Merge #<n> first."
        )
    if not any(_STACK_MERGE_FIRST.search(block) for block in opening_blocks):
        gaps.append("opening-pull-requests lacks (R4.3): the first one's Merge order: 1 of N. Merge this one first.")
    gaps += [
        f"opening-pull-requests still says (R4.3): {block!r}"
        for block in opening_blocks
        if _STACK_OLD_STACKED_ON.search(block)
    ]
    gaps += [
        f"still asks to create the label (R4.4): {sentence.strip()!r}"
        for block in mechanics
        for sentence in _sentences(block)
        if _STACK_ASKS_TO_CREATE.search(sentence) and _STACK_LABEL.search(sentence)
    ]
    return gaps


class LivePublishingFlowTest(unittest.TestCase):
    maxDiff = None  # a failure lists every gap, not the first one

    def test_live_publishing_pushes_each_slice_branch_and_commit(self) -> None:
        """R1.1, R1.2, R1.3, R1.4, R2.1, R2.2, R2.3, R3.1, R3.2, R3.3, R3.4, R3.5, R3.6: 003 develop-feature publishes
        a feature while it builds it only when the plan says so (R9.1: checked here, without a model).

        Phase 2 checks the remote (`git remote get-url origin`) and `gh repo view`, asks a separate question, records
        `- **Publish:** live` only on an explicit yes or the request, otherwise says in one line what is missing and
        records local; a plan without the line reads as local and a resumed session never asks again. Phase 3 cuts
        `feat/<NNN-slug>-s<k>` with `git switch -c` (S1 from the plan's commit, slice k from the previous slice's
        tip), switches to an existing one instead of creating it, pushes it with `git push -u origin` and runs
        `git push` after each task commit, before the next task. Every other flow commit (summary, plan change,
        integration, final commit) is pushed too in live mode; integrated partitions go up after the check passes and
        their branches never; a resume, and a switch to an existing slice branch, first push what the remote lacks
        with `git push -u origin feat/<NNN-slug>-s<k>`, which also sets the upstream; a failed push stops with
        `BLOCKED:` quoting Git's error, never forced nor pulled; only the main session publishes, and the implementer
        and test-writer never push. The tasks.md template carries `- **Publish:** local`."""
        template = (SKILLS_DIR / "writing-plans" / "templates" / "tasks.md").read_text(encoding="utf-8")
        header = _split_blocks(template.split("\n## ")[0].splitlines())

        gaps = _live_develop_feature_gaps()
        gaps += [
            f"agents/{agent}.md lacks (R3.6): never pushing"
            for agent in ("implementer", "test-writer")
            if not any(_never_pushes(block) for block in _blocks(PLUGIN_ROOT / "agents" / f"{agent}.md"))
        ]
        if not any(_LIVE_TEMPLATE_LINE.match(item) for item in header):
            gaps.append("writing-plans tasks.md template lacks (R1.1): - **Publish:** local in its header")

        self.assertEqual(gaps, [])

    def test_slices_end_in_stacked_pull_requests_in_merge_order(self) -> None:
        """R4.1, R4.2, R4.3, R4.4, R4.5, R4.6, R4.7, R4.8, R4.9: 003 each live slice ends in its own pull request,
        stacked on the previous slice's, with its merge order written down (R9.1: checked here, without a model).

        Once a live slice's summary is pushed, `gh pr create --base <base> --head feat/<NNN-slug>-s<k>` opens it ready
        for review: S1 against the default branch, each later one against the previous slice's branch, or against the
        default branch only when that slice's pull request is merged and its branch gone from the remote (a branch
        never pushed is absent too). opening-pull-requests, which also delivers a local
        feature, ends each title with `(k/N)` (N the plan's slices) and starts each description with
        `Merge order: k of N. Merge #<n> first.` (the first: `Merge this one first.`) instead of `Stacked on #`.
        `risk:high` goes on only if the label exists, never created, and its absence is said at the pause; a branch
        with an open pull request gets no second one; a gh failure stops with `BLOCKED:` quoting its error. The pause,
        or the session's message when pauses are pre-approved, lists the URLs in merge order; a resumed live feature
        first opens the pull request a finished slice lacks; Phase 4 in live mode pushes the final commit to the last
        slice's branch and lists every URL in merge order instead of asking, while a local feature still asks before
        pushing."""
        gaps = _stacked_pull_request_gaps()

        self.assertEqual(gaps, [])


# The right-sized flow (004): a task that lists several tests is built in one cycle (R2.1-R2.3, R3.9), a change made
# after a review passed goes again only through the reviews it concerns (R3.1-R3.8), and a small change the user asks
# for is made right away as an adjustment (R4.1-R4.11). Keywords of each rule inside one sentence of its section of
# develop-feature's SKILL.md or of reference/adjustments.md, or inside one block of the fenced prompts of a section
# of reference/dispatch-prompts.md, on blocks from _split_blocks (lowercased, without backticks, single-spaced; a
# table row is one block).
_SIZED_SKILL = DEVELOP_FEATURE_DIR / "SKILL.md"
_SIZED_PROMPTS = DEVELOP_FEATURE_DIR / "reference" / "dispatch-prompts.md"
_SIZED_ONE_DISPATCH = re.compile(r"\b(?:one|a single|the same) dispatch writes (?:every|each|all) tests?\b")
_SIZED_SAME_DISPATCH = re.compile(r"\bsame dispatch\b")
_SIZED_EVERY_TEST = re.compile(r"\b(?:every|each|all)\b(?: \S+){0,2} tests?\b")
_SIZED_TESTS_LIST = re.compile(r"\btests: list\b")
_SIZED_REPORT_PER_TEST = re.compile(r"\breports?\b(?: \S+){0,2} (?:per|for each|for every) test\b")
_SIZED_AGAINST_ITS_REPORT = re.compile(r"\bagainst its report\b")
_SIZED_FAILS = re.compile(r"\bfails?\b")
_SIZED_REASON = re.compile(r"\breason\b")
_SIZED_RED_REPORT = re.compile(r"\bred reports?\b")
_SIZED_RED_REPORTS = re.compile(r"\bred reports\b")
_SIZED_PASSES = re.compile(r"\bpass(?:es)?\b")
_SIZED_SKIPS_STEP_2 = re.compile(r"\bskip\w*(?: \S+){0,2} step 2\b")
_SIZED_THAT_TEST = re.compile(r"\bthat test\b")
_SIZED_NEW_TEST_WRITER = re.compile(r"\bnew test-writer\b")
_SIZED_LEAVE_AS_THEY_ARE = re.compile(r"\bleave\b(?: \S+){0,2} as they are\b")
_SIZED_IMPLEMENTER = re.compile(r"\bimplementer\b")
_SIZED_ONE_AT_A_TIME = re.compile(r"\bone(?: test)? at a time\b")
_SIZED_TASKS_ORDER = re.compile(r"\btask's order\b|\border the task lists\b")
_SIZED_RED_BEFORE_ITS_CODE = re.compile(r"\bred before its code\b")
_SIZED_STILL_FAIL = re.compile(r"\bstill fail\b")
_SIZED_MEDIUM_OR_HIGH = re.compile(r"\bmedium or high\b")
_SIZED_PROPERTY_TEST = re.compile(r"\bproperty tests?\b")
_SIZED_INVARIANT = re.compile(r"\binvariants?\b")
_SIZED_ONE_TEST_PER_BEHAVIOR = re.compile(r"\bone test per behaviou?r\b")
_SIZED_FOR_EACH_TEST = re.compile(r"\b(?:for each|for every|per) test\b")
_SIZED_CHARACTERIZATION_REPORT = re.compile(r"\bcharacterization report\b")
_SIZED_EVERY_FAILING_TEST = re.compile(r"\b(?:every|each|all)\b(?: \S+){0,1} failing tests?\b")
_SIZED_WRITE_OR_FIX_ONLY = re.compile(r"\bwrite or fix only\b")
_SIZED_TASK_TESTS_FIELD = re.compile(r"\btask tests:")
_SIZED_PLACEHOLDER = re.compile(r"<[^<>]+>")
# What Phase 3 must say about a task that lists several tests, each in one sentence.
_SIZED_PHASE_3_RULES: dict[str, tuple[re.Pattern[str], ...]] = {
    "R2.1 one test-writer dispatch writes every test the task lists, on its Test: line or in its Tests: list": (
        _SIZED_ONE_DISPATCH,
        _SIZED_EVERY_TEST,
        _SIZED_TESTS_LIST,
    ),
    "R2.1 the test-writer returns a report per test": (_SIZED_REPORT_PER_TEST,),
    "R2.2 each test is checked against its report": (_SIZED_EVERY_TEST, _SIZED_AGAINST_ITS_REPORT),
    "R2.2 every test fails for the reason its RED report gives": (
        _SIZED_EVERY_TEST,
        _SIZED_FAILS,
        _SIZED_REASON,
        _SIZED_RED_REPORT,
    ),
    "R2.2 a test that does not hold goes back alone to a new test-writer, naming the tests to leave as they are": (
        _SIZED_THAT_TEST,
        _SIZED_NEW_TEST_WRITER,
        _SIZED_LEAVE_AS_THEY_ARE,
    ),
    "R2.2 when every test of the task already passes, step 2 is skipped": (
        _SIZED_EVERY_TEST,
        _SIZED_PASSES,
        _SIZED_SKIPS_STEP_2,
    ),
    "R2.3 the implementer gets the RED reports and makes the tests pass one at a time, in the task's order, each"
    " one red before its code": (
        _SIZED_IMPLEMENTER,
        _SIZED_RED_REPORTS,
        _SIZED_ONE_AT_A_TIME,
        _SIZED_TASKS_ORDER,
        _SIZED_RED_BEFORE_ITS_CODE,
    ),
    "R3.9 on a medium or high task the same dispatch also writes the property test of each listed invariant": (
        _SIZED_MEDIUM_OR_HIGH,
        _SIZED_SAME_DISPATCH,
        _SIZED_PROPERTY_TEST,
        _SIZED_INVARIANT,
    ),
}
# (section of dispatch-prompts.md, the rule, the patterns one sentence of its fenced prompts must all match).
_SIZED_PROMPT_RULES: tuple[tuple[str, str, tuple[re.Pattern[str], ...]], ...] = (
    (
        "test-writer",
        "R2.1 every test of the task's Tests: list, one test per behavior",
        (_SIZED_EVERY_TEST, _SIZED_TESTS_LIST, _SIZED_ONE_TEST_PER_BEHAVIOR),
    ),
    (
        "test-writer",
        "R2.2 a RED report or a CHARACTERIZATION report for each test",
        (_SIZED_FOR_EACH_TEST, _SIZED_RED_REPORT, _SIZED_CHARACTERIZATION_REPORT),
    ),
    (
        "test-writer",
        "R3.9 the property tests to write for the task's invariants",
        (_SIZED_PROPERTY_TEST, _SIZED_INVARIANT, _SIZED_PLACEHOLDER),
    ),
    (
        "test-writer",
        "R2.2 the tests already written, to leave as they are",
        (_SIZED_LEAVE_AS_THEY_ARE, _SIZED_PLACEHOLDER),
    ),
    ("test-writer", "R2.2 the one test to write or fix", (_SIZED_WRITE_OR_FIX_ONLY, _SIZED_PLACEHOLDER)),
    (
        "implementer",
        "R2.3 every failing test made to pass, one at a time and in the task's order, seen still failing before its"
        " code",
        (_SIZED_EVERY_FAILING_TEST, _SIZED_PASSES, _SIZED_ONE_AT_A_TIME, _SIZED_TASKS_ORDER, _SIZED_STILL_FAIL),
    ),
    ("implementer (fix round)", "R2.3 the task's tests, one per test", (_SIZED_TASK_TESTS_FIELD, _SIZED_PLACEHOLDER)),
)

# Reviews after a change (R3.1-R3.8).
_AFTER_SECTION = "Reviews after a change"
_AFTER_LINK = re.compile(r"\(#reviews-after-a-change\)")
_AFTER_FIX_BUG_LINK = re.compile(r"\(\.\./develop-feature/skill\.md#reviews-after-a-change\)")
_AFTER_FINDING = re.compile(r"\bfindings?\b")
_AFTER_FIXED = re.compile(r"\bfix(?:es|ed)?\b")
_AFTER_THAT_REVIEW = re.compile(r"\bthat review\b")
_AFTER_ADDED_TESTS = re.compile(r"\badded tests\b")
_AFTER_NOTHING_ELSE = re.compile(r"\bnothing else\b")
_AFTER_TEST_THAT_WAS_THERE = re.compile(r"\btest that was there\b|\bexisting test\b")
_AFTER_WHAT_THE_CODE_DOES = re.compile(r"\bwhat the code does\b")
_AFTER_HOW_BUILT = re.compile(r"\bhow the code is built\b")
_AFTER_SILENCER = re.compile(r"\bsilencer\b")
_AFTER_SPEC_REVIEWER = re.compile(r"\bspec[- ]review(?:er)?\b")
_AFTER_CODE_REVIEWER = re.compile(r"\bcode[- ]review(?:er)?\b")
_AFTER_REVIEWER = re.compile(r"\breview\w*")
_AFTER_GATE = re.compile(r"\bgates?\b")
_AFTER_ONLY_TEXT = re.compile(r"\bonly text\b|\btext (?:only|alone)\b")
_AFTER_NOTHING_READS = re.compile(r"\bnothing reads\b")
_AFTER_NONE = re.compile(r"\bnone\b")
_AFTER_HIGH = re.compile(r"\bhigh\b")
_AFTER_EVERY_REVIEW = re.compile(r"\b(?:every|all|each)\b(?: \S+){0,2} reviews?\b")
_AFTER_SECURITY = re.compile(r"\bsecurity[- ]review(?:er)?\b")
_AFTER_CANNOT_TELL = re.compile(r"\bcannot tell\b|\bdoubt\b|\bunsure\b|\bnot sure\b|\bunclear\b")
_AFTER_BOTH_REVIEWS = re.compile(r"\bboth reviews\b")
_AFTER_ASKS = re.compile(r"\basks?\b")
_AFTER_WOULD_SKIP = re.compile(r"\bwould skip\b")
_AFTER_DIFF = re.compile(r"\bdiff\b")
_AFTER_NEVER = re.compile(r"\bnever\b|\bnot\b")
_AFTER_WRITERS_REPORT = re.compile(r"\bwriter's report\b")
_AFTER_GIT_ADD = re.compile(r"\bgit add -a && git write-tree\b")
_AFTER_SHA = re.compile(r"\bsha\b")
_AFTER_BEFORE = re.compile(r"\bbefore\b")
_AFTER_WRITER = re.compile(r"\bwriter\b")
_AFTER_DIFF_STAT = re.compile(r"\bgit diff --stat <sha>")
_AFTER_THE_INDEX = re.compile(r"\bthe index\b")
_AFTER_WITHOUT_THE_SHA = re.compile(r"\bwithout the sha\b")
_AFTER_RED_CHECK = re.compile(r"\bred check\b")
_AFTER_GIT_GREP = re.compile(r"\bgit grep\b")
_AFTER_LEAVES_OUT = re.compile(r"\b(?:leaves out|skips|does not repeat) a review\b")
_AFTER_SLICE_SUMMARY = re.compile(r"\bslice summary\b")
_AFTER_CODE_REVIEW_ALWAYS = re.compile(r"\bcode review always\b")
_AFTER_STATUS_PORCELAIN = re.compile(r"\bgit status --porcelain\b")
_AFTER_PRODUCT = re.compile(r"\bproduct\b")
_AFTER_TOOL = re.compile(r"\btool\b")
_AFTER_READS = re.compile(r"\breads\b")
_AFTER_IS_CODE = re.compile(r"\bis code\b")
_AFTER_NO_REVIEW = re.compile(r"\bno reviews?\b")
_AFTER_EVERY_CHANGED_LINE = re.compile(r"\bevery changed line\b")
_AFTER_VERIFY = re.compile(r"\bverify command\b")
_AFTER_RERUN = re.compile(r"\brerun\b|\brun\b(?: \S+){0,3} again\b")
_AFTER_FIRST = re.compile(r"\bfirst\b|\bbefore\b")
_AFTER_CODE_OR_TESTS = re.compile(r"\bcode\b.*\btests?\b|\btests?\b.*\bcode\b")
_AFTER_GREEN = re.compile(r"\bgreen\b")
_AFTER_COMMIT = re.compile(r"\bcommit\b")
_AFTER_FIRST_REVIEWS = re.compile(r"\bfirst reviews\b")
_AFTER_STEP_3 = re.compile(r"\bstep 3\b")
_AFTER_ALWAYS = re.compile(r"\balways\b")
_AFTER_ONLY = re.compile(r"\bonly\b")
_AFTER_REVIEWS = re.compile(r"\breviews\b")
_AFTER_AGAIN = re.compile(r"\bagain\b")
_AFTER_FIX_ROUND = re.compile(r"\bfix[- ]round\b")
_AFTER_NOTE = re.compile(r"\bnote\b")
_AFTER_DID_NOT_REPEAT = re.compile(r"\b(?:did not|didn't) repeat\b|\bnot repeated\b")
_AFTER_BEFORE_THE_FIRST_CHANGE = re.compile(r"\bbefore the first change\b")
_AFTER_ONE_RE_REVIEW = re.compile(r"\bone re-review\b")
_AFTER_CHECK_FAILS = re.compile(r"\bcheck fails\b")
_AFTER_SINCE_LAST_RAN = re.compile(r"\bsince this review last ran\b")
_AFTER_USER_ASKED = re.compile(r"\buser asked\b")
_AFTER_CRITERION = re.compile(r"\bcriteri(?:on|a)\b")
_AFTER_OLD_RULE = re.compile(r"\breviews of step 3 again\b")
# The rows of the section's table: (the rule, what the first cell must say, what the second cell must name, what
# the second cell must not name).
_AFTER_TABLE_RULES: tuple[
    tuple[str, tuple[re.Pattern[str], ...], tuple[re.Pattern[str], ...], tuple[re.Pattern[str], ...]], ...
] = (
    (
        "R3.1 a change that fixed a review's finding goes back to that review",
        (_AFTER_FIXED, _AFTER_FINDING),
        (_AFTER_THAT_REVIEW,),
        (),
    ),
    (
        "R3.1 a change that only added tests goes to the spec review alone",
        (_AFTER_ADDED_TESTS, _AFTER_NOTHING_ELSE),
        (_AFTER_SPEC_REVIEWER,),
        (_AFTER_CODE_REVIEWER,),
    ),
    (
        "R3.1 a change to a test that was there, or to what the code does, goes to the spec review and the code review",
        (_AFTER_TEST_THAT_WAS_THERE, _AFTER_WHAT_THE_CODE_DOES),
        (_AFTER_SPEC_REVIEWER, _AFTER_CODE_REVIEWER),
        (),
    ),
    (
        "R3.1 a change to how the code is built, or to what configures a gate, goes to the code review alone",
        (_AFTER_HOW_BUILT, _AFTER_SILENCER, _AFTER_GATE),
        (_AFTER_CODE_REVIEWER,),
        (_AFTER_SPEC_REVIEWER,),
    ),
    (
        "R3.1 a change to text that nothing reads repeats no review",
        (_AFTER_ONLY_TEXT, _AFTER_NOTHING_READS),
        (_AFTER_NONE,),
        (_AFTER_REVIEWER,),
    ),
    (
        "R3.2 anything on a high task repeats every review, the security review included",
        (_AFTER_HIGH,),
        (_AFTER_EVERY_REVIEW, _AFTER_SECURITY),
        (),
    ),
)
# What the `## Reviews after a change` section must say around its table, each in one sentence.
_AFTER_SECTION_RULES: dict[str, tuple[re.Pattern[str], ...]] = {
    "R3.7 the reviews are decided from the change's own diff, never from the writer's report": (
        _AFTER_DIFF,
        _AFTER_NEVER,
        _AFTER_WRITERS_REPORT,
    ),
    "R3.7 inside a task the tree is marked with git add -A && git write-tree right before the change's first"
    " writer runs, and its SHA kept": (_AFTER_GIT_ADD, _AFTER_BEFORE, _AFTER_WRITER, _AFTER_SHA),
    "R3.7 the change alone is git diff --stat <sha> plus the untracked files git status --porcelain lists": (
        _AFTER_DIFF_STAT,
        _AFTER_STATUS_PORCELAIN,
    ),
    "R3.7 the diff is compared with that tree, never with the index": (_AFTER_NEVER, _AFTER_THE_INDEX),
    "R3.7 without the SHA both reviews run": (_AFTER_WITHOUT_THE_SHA, _AFTER_BOTH_REVIEWS),
    "R3.1 a message's old wording is searched for before it counts as text that nothing reads": (
        _AFTER_GIT_GREP,
        _AFTER_NOTHING_READS,
    ),
    "R3.1 the fix of a red check always gets the code review again": (
        _AFTER_RED_CHECK,
        _AFTER_ALWAYS,
        _AFTER_CODE_REVIEWER,
        _AFTER_AGAIN,
    ),
    "R3.1 a file the product, a tool or a test reads is code, whatever its extension": (
        _AFTER_PRODUCT,
        _AFTER_TOOL,
        _AFTER_READS,
        _AFTER_IS_CODE,
    ),
    "R3.1 the row with no review holds only when every changed line is that kind of text": (
        _AFTER_NO_REVIEW,
        _AFTER_ONLY,
        _AFTER_EVERY_CHANGED_LINE,
    ),
    "R3.3 when the row is not clear, both reviews run": (_AFTER_CANNOT_TELL, _AFTER_BOTH_REVIEWS),
    "R3.3 a review the user asks for runs even when the table would skip it": (_USER, _AFTER_ASKS, _AFTER_WOULD_SKIP),
    "R3.5 the verify command reruns first when code or tests changed": (
        _AFTER_VERIFY,
        _AFTER_RERUN,
        _AFTER_FIRST,
        _AFTER_CODE_OR_TESTS,
    ),
    "R3.5 the gate still needs the check green before the commit": (_CHECK, _AFTER_GREEN, _AFTER_COMMIT),
    "R3.1 a task's first reviews always run, all of them, in step 3": (
        _AFTER_FIRST_REVIEWS,
        _AFTER_STEP_3,
        _AFTER_ALWAYS,
    ),
}
# What Phase 3 must say to send its later changes through that section, each in one sentence.
_AFTER_PHASE_3_RULES: dict[str, tuple[re.Pattern[str], ...]] = {
    "R3.7 the task is marked with git add -A && git write-tree, keeping its SHA, before its one fix round": (
        _AFTER_GIT_ADD,
        _AFTER_SHA,
        _ONE_FIX_ROUND,
    ),
    "R3.1 after a fix round only the reviews the section names run again": (
        _AFTER_FIX_ROUND,
        _AFTER_ONLY,
        _AFTER_REVIEWS,
        _AFTER_AGAIN,
        _AFTER_LINK,
    ),
    "R3.7 the task is marked the same way before the first change of the verification by risk": (
        _AFTER_GIT_ADD,
        _AFTER_BEFORE_THE_FIRST_CHANGE,
    ),
    "R3.9 the changes of the verification by risk go again, in one re-review, through the reviews the section names": (
        _COMMIT_ANY,
        _CHANGED,
        _AFTER_ONE_RE_REVIEW,
        _AFTER_REVIEWS,
        _COMMIT_CONCERNS,
        _AFTER_AGAIN,
        _AFTER_LINK,
    ),
    "R3.1 the fix of a red check is marked the same way and goes through the reviews the section names, the code"
    " review always among them": (
        _AFTER_GIT_ADD,
        _AFTER_CHECK_FAILS,
        _AFTER_REVIEWS,
        _AFTER_LINK,
        _AFTER_CODE_REVIEW_ALWAYS,
    ),
}
# What the `## re-review` prompt and the process-reviewer prompt must carry, each in one block of the fenced prompt.
_AFTER_PROMPT_RULES: tuple[tuple[str, str, tuple[re.Pattern[str], ...]], ...] = (
    (
        "re-review",
        "R3.7 the reports of every fix round since this review last ran",
        (_AFTER_FIX_ROUND, _AFTER_SINCE_LAST_RAN, _SIZED_PLACEHOLDER),
    ),
    ("re-review", "R3.7 what the last round changed, from git diff --stat", (_AFTER_DIFF_STAT, _SIZED_PLACEHOLDER)),
    (
        "re-review",
        "R4.10 a change the user asked for during the task, as a criterion for the review",
        (_AFTER_USER_ASKED, _AFTER_CRITERION, _SIZED_PLACEHOLDER),
    ),
    (
        "process-reviewer",
        "R3.8 the adjustments and the reviews not repeated after a change",
        (_AFTER_DID_NOT_REPEAT, _SIZED_PLACEHOLDER),
    ),
)

# Adjustments (R4.1-R4.11): what counts as one and who makes it is in SKILL.md's `## Adjustments`; the procedure is
# in reference/adjustments.md.
_ADJUST_SECTION = "Adjustments"
_ADJUST_REFERENCE = DEVELOP_FEATURE_DIR / "reference" / "adjustments.md"
_ADJUST_PROMPTS = ("test-writer (adjustment)", "implementer (adjustment)", "adjustment review")
_ADJUST_LINK = re.compile(r"\(#adjustments\)")
_ADJUST_REFERENCE_LINK = re.compile(r"\(reference/adjustments\.md\)")
_ADJUST_REVIEWS_LINK = re.compile(r"\(\.\./skill\.md#reviews-after-a-change\)")
_ADJUST_CLASSIFIES = re.compile(r"\bclassif\w*")
_ADJUST_BEFORE = re.compile(r"\bbefore\b")
_ADJUST_TOUCHING = re.compile(r"\btouch\w*|\bchang\w*|\bedit\w*")
_ADJUST_PAUSE = re.compile(r"\bpause\b")
_ADJUST_DONE = re.compile(r"\bdone\b")
_ADJUST_PLAN_CHANGE = re.compile(r"\bplan change\b")
_ADJUST_CRITERION = re.compile(r"\bacceptance criteri(?:on|a)\b")
_ADJUST_A_CRITERION = re.compile(r"\bcriteri(?:on|a)\b")
_ADJUST_ADDS_OR_REMOVES = re.compile(r"\badds?\b.*\bremoves?\b|\bremoves?\b.*\badds?\b")
_ADJUST_NO_CRITERION_COVERS = re.compile(r"\bbehaviou?r no criterion covers\b")
_ADJUST_DESIGN = re.compile(r"\bdesign\b")
_ADJUST_INTERFACE = re.compile(r"\binterface\b")
_ADJUST_DEPENDENCY = re.compile(r"\bdependency\b")
_ADJUST_FILE_A_HIGH_TASK_LISTS = re.compile(r"\bfile a high task lists\b")
_ADJUST_HIGH_ROW = re.compile(r"\bhigh row\b")
_ADJUST_FILE_NO_TASK_LISTS = re.compile(r"\bfile no task\b(?: \S+){0,3} lists\b")
_ADJUST_FIFTY_LINES = re.compile(r"(?<![\d,.])50(?![\d,])(?: \S+){0,2} lines\b")
_ADJUST_NEW_TASKS = re.compile(r"\bnew tasks?\b")
_ADJUST_WRITING_PLANS = re.compile(r"\bwriting-plans\b")
_ADJUST_CONSOLIDATION = re.compile(r"\bconsolidat\w*")
_ADJUST_APPROVES = re.compile(r"\bapprov\w*")
_ADJUST_CANNOT_TELL = re.compile(r"\bcannot tell\b|\bdoubt\b|\bunsure\b|\bnot sure\b|\bunclear\b")
_ADJUST_ADJUSTMENT = re.compile(r"\badjustments?\b")
_ADJUST_REQUEST = re.compile(r"\brequest\b")
_ADJUST_APPROVAL = re.compile(r"\bapproval\b")
_ADJUST_DEFECT = re.compile(r"\bdefect\b")
_ADJUST_TYPED_FIX = re.compile(r"\btype (?:its commit|it) fix\b")
_ADJUST_ESCAPED_GATE = re.compile(r"\bescaped-gate:")
_ADJUST_NOTE = re.compile(r"\bnote\b")
_ADJUST_TASK_IN_PROGRESS = re.compile(r"\btask in progress\b")
_ADJUST_BEFORE_ITS_COMMIT = re.compile(r"\bbefore its commit\b")
_ADJUST_JOINS_THAT_TASK = re.compile(r"\bjoins that task\b|\b(?:becomes|is) part of that task\b")
_ADJUST_CHANGE_LINE = re.compile(r"- change: <")
_ADJUST_ADJUSTMENT_PROMPTS = re.compile(r"\badjustment prompts\b")
_ADJUST_MARKS_THE_TREE = re.compile(r"\bmark the tree\b")
_ADJUST_RE_REVIEW_PROMPT = re.compile(r"\bre-review prompt\b")
_ADJUST_HANDED_OVER = re.compile(r"\bhanded the feature over\b")
_ADJUST_BEFORE_THE_HAND_OVER = re.compile(r"\bbefore it hands the feature over\b")
_ADJUST_MAKES_NONE = re.compile(r"\bmakes none\b|\b(?:makes no|does not make) adjustments?\b")
_ADJUST_REOPENS = re.compile(r"\breopens\b")
_ADJUST_APPROVED = re.compile(r"\bapproved\b")
_ADJUST_TASK_LINE = re.compile(r"\btask: line\b")
_ADJUST_LOG_PER_FILE = re.compile(r"\bgit log --notes=refs/notes/konundrm\b.* -- <file>")
_ADJUST_FIX_ROUND = re.compile(r"\bfix[- ]round\b")
_ADJUST_ONE_MORE_CRITERION = re.compile(r"\bone more criterion\b")
_ADJUST_REQUIREMENTS_MD = re.compile(r"\brequirements\.md\b")
_ADJUST_NOT_A_FAILED_REVIEW = re.compile(r"\bnot a failed review\b")
_ADJUST_ONLY = re.compile(r"\bonly\b")
_ADJUST_MAIN_SESSION = re.compile(r"\bmain session\b")
_ADJUST_CLEAN_POINT = re.compile(r"\bclean point\b")
_ADJUST_PARTITION_SESSION = re.compile(r"\bpartition session\b")
_ADJUST_BLOCKED = re.compile(r"\bblocked:")
_ADJUST_WAVE = re.compile(r"\bwave\b")
_ADJUST_HOLD = re.compile(r"\bhold\b|\bwait\b")
_ADJUST_STATUS_DONE = re.compile(r"\bstatus: done\b")
_ADJUST_PHASE_4 = re.compile(r"\bphase 4\b")
_ADJUST_NOT_AGAIN = re.compile(r"\bnot\b(?: \S+){0,2} again\b")
_ADJUST_USER_ASKS = re.compile(r"\buser asks\b")
_ADJUST_NEVER_STARTS_OVER = re.compile(r"\bnever start\b(?: \S+){0,3} over\b")
_ADJUST_SUMMARY_SECTION = re.compile(r"## adjustments\b")
_ADJUST_FINAL_SLICE = re.compile(r"\b(?:final|last) slice\b")
_ADJUST_AFTER_THIS_REPORT = re.compile(r"\bafter this report\b")
_ADJUST_TEST_WRITER = re.compile(r"\btest-writer\b")
_ADJUST_WHAT_THE_CODE_DOES = re.compile(r"\bwhat the code does\b")
_ADJUST_MUST_FAIL = re.compile(r"\bmust fail\b")
_ADJUST_BEFORE_ANY_DISPATCH = re.compile(r"\bbefore any dispatch\b")
_ADJUST_ADDED_RENAMED_REMOVED = re.compile(r"\badded, renamed or removed\b")
_ADJUST_NO_CODE = re.compile(r"\bno code\b")
_ADJUST_NO_TEST = re.compile(r"\bno tests?\b")
_ADJUST_YOURSELF = re.compile(r"\byourself\b")
_ADJUST_DOCUMENTS = re.compile(r"\bdocuments\b")
_ADJUST_PROSE = re.compile(r"\bprose\b")
_ADJUST_NOTHING_LOADS = re.compile(r"\bnothing loads\b")
_ADJUST_FIVE_TIMES = re.compile(r"\bfive times\b")
_ADJUST_CHANGED_OR_ADDED = re.compile(r"\bchanged or added\b")
_ADJUST_ONCE = re.compile(r"\bonce\b")
_ADJUST_VERIFY = re.compile(r"\bverify command\b")
_ADJUST_DIFF = re.compile(r"\bdiff\b")
_ADJUST_REVIEWS = re.compile(r"\breviews\b")
_ADJUST_GATE = re.compile(r"\bgate\b")
_ADJUST_STEP_6 = re.compile(r"\bstep 6\b")
_ADJUST_COMMIT = re.compile(r"\bcommit\b")
_ADJUST_COMMITTING_CHANGES = re.compile(r"\bcommitting-changes\b")
_ADJUST_LIVE = re.compile(r"\bpublish: live\b")
_ADJUST_PUSH = re.compile(r"\bpush it\b")
_ADJUST_PULL_REQUESTS_OPEN = re.compile(r"\bpull requests\b(?: \S+){0,2} open\b")
_ADJUST_ASK_BEFORE_PUSHING = re.compile(r"\bask before pushing\b")
_ADJUST_TELLS = re.compile(r"\btell\b|\breport\b|\bsay\b")
_ADJUST_RAN = re.compile(r"\bran\b")
_ADJUST_NOT_NEEDED = re.compile(r"\b(?:did not|didn't|does not|not) need\w*")
_ADJUST_OLD = re.compile(r"\bold\b")
_ADJUST_NEW = re.compile(r"\bnew\b")
_ADJUST_NOT_COMMITTED = re.compile(r"\b(?:do not|don't|never|not) commit\b|\bwithout committing\b")
_ADJUST_STASH_PUSH = re.compile(r"\bgit stash push (?:--include-untracked|-u)\b")
_ADJUST_STASH_LIST = re.compile(r"\bgit stash list --grep=")
_ADJUST_STASH_FORMAT = re.compile(r"--format=%h\b")
_ADJUST_STASH_APPLY = re.compile(r"\bgit stash apply <sha>")
_ADJUST_KEEP = re.compile(r"\bkeep\b")
_ADJUST_BOTH_REVIEWS = re.compile(r"\bboth reviews\b")
_ADJUST_STILL_FAILS = re.compile(r"\bstill fails\b")
_ADJUST_NOT_AN_ADJUSTMENT = re.compile(r"\bnot an adjustment\b")
_ADJUST_NEVER = re.compile(r"\bnever\b")
_ADJUST_RETHINK = re.compile(r"\brethink\b")
_ADJUST_NEXT_SUMMARY = re.compile(r"\bnext summary\b")
_ADJUST_DO_NOT_EDIT = re.compile(r"\b(?:do not|don't|never) edit\b")
_ADJUST_SUMMARY = re.compile(r"\bsummary\b")
_ADJUST_NEXT_SLICE = re.compile(r"\bbelongs to the next slice\b")
_ADJUST_NEXT_SLICES_BRANCH = re.compile(r"\bnext slice's branch\b")
_ADJUST_SUMMARY_MD = re.compile(r"\bsummary\.md\b")
_ADJUST_DOCS_COMMIT = re.compile(r"\bdocs commit\b")
_ADJUST_GIT_LOG = re.compile(r"\bgit log\b")
_ADJUST_NOTES_REF = re.compile(r"--notes=refs/notes/konundrm\b")
_ADJUST_GREP = re.compile(r"--grep '\^adjusts:'")
_ADJUST_COMMIT_AND_NOTE = re.compile(
    r'\bgit add -a && git commit -m "[^"]*" --trailer "[^"]*" && git notes --ref[= ]refs/notes/konundrm add'
    r' -m "adjusts:[^"]*" -m "reviews:[^"]*" -m "asked:[^"]*" head\b'
)
_ADJUST_FIX_TYPE = re.compile(r"\bfix\b")
_ADJUST_NEVER_AMEND = re.compile(r"\bnever amend\b")
_ADJUST_ONCE_PER_ADJUSTMENT = re.compile(r"\bonce per adjustment\b")
_ADJUST_REQUEST_PLACEHOLDER = re.compile(r"<request>")
_ADJUST_OUTPUT_FIELD = (re.compile(r"\borchestrator'?s?\b"), re.compile(r"\bverif\w*"), re.compile(r"<[^<>]+>"))
_ADJUST_EVERY_TEST_THAT_ASSERTS = re.compile(r"\bevery test that asserts\b")
_ADJUST_EACH_MUST_FAIL = re.compile(r"\beach must fail\b")
_ADJUST_STATUS_BLOCKED = re.compile(r"\bstatus: blocked\b")
_ADJUST_MUST_MEET = re.compile(r"\bmust meet\b")
# What the `## Adjustments` section of SKILL.md must say, each in one sentence.
_ADJUST_SECTION_RULES: dict[str, tuple[re.Pattern[str], ...]] = {
    "R4.1 a change asked during the build, at a pause or once the feature is done is classified before anything is"
    " touched": (_ADJUST_CLASSIFIES, _ADJUST_BEFORE, _ADJUST_TOUCHING, _ADJUST_PAUSE, _ADJUST_DONE),
    "R4.2 a plan change when it adds or removes an acceptance criterion, or a behavior no criterion covers": (
        _ADJUST_PLAN_CHANGE,
        _ADJUST_ADDS_OR_REMOVES,
        _ADJUST_CRITERION,
        _ADJUST_NO_CRITERION_COVERS,
    ),
    "R4.2 a plan change when it changes the design, a public interface or a dependency": (
        _ADJUST_DESIGN,
        _ADJUST_INTERFACE,
        _ADJUST_DEPENDENCY,
    ),
    "R4.2 a plan change when it touches a file a high task lists, or anything the High row of the Standards names": (
        _ADJUST_FILE_A_HIGH_TASK_LISTS,
        _ADJUST_HIGH_ROW,
    ),
    "R4.2 a plan change when it changes code in a file no task of the feature lists": (_ADJUST_FILE_NO_TASK_LISTS,),
    "R4.2 a plan change when it is expected to take more than about 50 changed lines": (_ADJUST_FIFTY_LINES,),
    "R4.2, R1.9 a plan change becomes new tasks, written as writing-plans writes them with its consolidation, that"
    " the user approves and the task loop builds": (
        _ADJUST_NEW_TASKS,
        _TASKS_MD,
        _ADJUST_WRITING_PLANS,
        _ADJUST_CONSOLIDATION,
        _USER,
        _ADJUST_APPROVES,
        _TASK_LOOP,
    ),
    "R4.2 when it is not clear which of the two a request is, it is a plan change": (
        _ADJUST_CANNOT_TELL,
        _ADJUST_PLAN_CHANGE,
    ),
    "R4.3 the request is the adjustment's approval, and reference/adjustments.md says how it is made": (
        _ADJUST_REQUEST,
        _ADJUST_APPROVAL,
        _ADJUST_REFERENCE_LINK,
    ),
    "R4.6 a request that reports a defect is typed fix, with the Escaped-gate: line in its note": (
        _ADJUST_DEFECT,
        _ADJUST_TYPED_FIX,
        _ADJUST_ESCAPED_GATE,
        _ADJUST_NOTE,
    ),
    "R4.10 a change asked on the task in progress, before its commit, is classified the same way": (
        _ADJUST_TASK_IN_PROGRESS,
        _ADJUST_BEFORE_ITS_COMMIT,
        _ADJUST_CLASSIFIES,
    ),
    "R4.10 anything else joins that task": (_ADJUST_JOINS_THAT_TASK,),
    "R4.10 the criterion is edited in requirements.md first, and the request is recorded under the task in tasks.md"
    " as a Change: line, one more criterion for every later dispatch and review": (
        _ADJUST_REQUIREMENTS_MD,
        _TASKS_MD,
        _ADJUST_CHANGE_LINE,
        _ADJUST_ONE_MORE_CRITERION,
    ),
    "R3.7, R4.10 the tree is marked, the request goes to the task's writers with the adjustment prompts, and the"
    " test-writer's test must fail first": (
        _ADJUST_MARKS_THE_TREE,
        _ADJUST_ADJUSTMENT_PROMPTS,
        _ADJUST_TEST_WRITER,
        _ADJUST_MUST_FAIL,
    ),
    "R4.10 once step 3 has run, the reviews that Reviews after a change names run again with the re-review prompt": (
        _AFTER_LINK,
        _ADJUST_RE_REVIEW_PROMPT,
    ),
    "R4.10 it is not a failed review": (_ADJUST_NOT_A_FAILED_REVIEW,),
    "R4.11 only the feature's main session makes adjustments, before it hands the feature over, at the next clean"
    " point": (
        _ADJUST_ONLY,
        _ADJUST_MAIN_SESSION,
        _ADJUST_BEFORE_THE_HAND_OVER,
        _ADJUST_CLEAN_POINT,
    ),
    "R4.11 a session that has already handed the feature over makes none": (
        _ADJUST_HANDED_OVER,
        _ADJUST_MAKES_NONE,
    ),
    "R4.11 a partition session makes none and stops with a BLOCKED: line": (
        _ADJUST_PARTITION_SESSION,
        _ADJUST_BLOCKED,
    ),
    "R4.11 during a parallel wave the adjustment is held": (_ADJUST_WAVE, _ADJUST_HOLD, _ADJUST_ADJUSTMENT),
}
# What the other sections of SKILL.md must say to send a change the user asks for to `## Adjustments`:
# (section, the rule, the patterns one of its sentences must all match).
_ADJUST_POINTER_RULES: tuple[tuple[str, str, tuple[re.Pattern[str], ...]], ...] = (
    (
        "Phase 0: Prepare",
        "R4.11 a resumed feature that is already Done does not run Phase 4 again: the change goes through Adjustments",
        (_ADJUST_STATUS_DONE, _ADJUST_PHASE_4, _ADJUST_NOT_AGAIN, _ADJUST_LINK),
    ),
    (
        "Phase 0: Prepare",
        "R4.2 a plan change on a finished feature reopens it: its documents go back to Approved",
        (_ADJUST_PLAN_CHANGE, _ADJUST_REOPENS, _ADJUST_APPROVED),
    ),
    (
        "Phase 0: Prepare",
        "R4.11 a partition session stops with a BLOCKED: line that quotes the request",
        (_ADJUST_USER_ASKS, _ADJUST_LINK, _ADJUST_BLOCKED, _ADJUST_REQUEST),
    ),
    (
        "Phase 3: Task loop",
        "R4.1 a change the user asks for during the build goes through Adjustments, never by starting a task over",
        (_ADJUST_USER_ASKS, _ADJUST_LINK, _ADJUST_NEVER_STARTS_OVER),
    ),
    (
        "Slice checkpoint",
        "R3.8 the summary lists the reviews that were not repeated after a change",
        (_ADJUST_REVIEWS, _AFTER_DID_NOT_REPEAT),
    ),
    (
        "Phase 4: Finish",
        "R1.9 the new tasks for the gaps are written as writing-plans writes them, with its consolidation",
        (_ADJUST_NEW_TASKS, _ADJUST_WRITING_PLANS, _ADJUST_CONSOLIDATION),
    ),
    (
        "Phase 4: Finish",
        "R4.8 the feature summary lists the adjustments made after the final slice's summary, from their notes",
        (_ADJUST_SUMMARY_SECTION, _ADJUST_FINAL_SLICE, _ADJUST_NOTE),
    ),
    (
        "Phase 4: Finish",
        "R4.1 a change asked after the final report goes through Adjustments",
        (_ADJUST_AFTER_THIS_REPORT, _ADJUST_LINK),
    ),
)
# What reference/adjustments.md must say, each in one sentence.
_ADJUST_REFERENCE_RULES: dict[str, tuple[re.Pattern[str], ...]] = {
    "R4.7 a criterion the request changes is edited in requirements.md before any dispatch": (
        _ADJUST_A_CRITERION,
        _ADJUST_REQUIREMENTS_MD,
        _ADJUST_BEFORE_ANY_DISPATCH,
    ),
    "R4.3 the test-writer goes first when the request changes what the code does, and its tests, which the"
    " orchestrator runs itself, must fail": (
        _ADJUST_TEST_WRITER,
        _ADJUST_WHAT_THE_CODE_DOES,
        _ADJUST_YOURSELF,
        _ADJUST_MUST_FAIL,
    ),
    "R4.7 a test added, renamed or removed updates the task's lines in tasks.md": (
        _ADJUST_ADDED_RENAMED_REMOVED,
        _TASKS_MD,
    ),
    "R4.3 the orchestrator writes no code and no test itself": (_ADJUST_NO_CODE, _ADJUST_NO_TEST, _ADJUST_YOURSELF),
    "R4.3 it edits directly only the feature's documents and prose that nothing loads, runs or tests": (
        _ADJUST_ONLY,
        _ADJUST_DOCUMENTS,
        _ADJUST_PROSE,
        _ADJUST_NOTHING_LOADS,
    ),
    "R4.4 the tests it changed or added run five times, and the verify command of each task it adjusts once": (
        _ADJUST_FIVE_TIMES,
        _ADJUST_CHANGED_OR_ADDED,
        _ADJUST_ONCE,
        _ADJUST_VERIFY,
    ),
    "R4.4 the reviews come from its diff, as Reviews after a change names them": (
        _ADJUST_DIFF,
        _ADJUST_REVIEWS,
        _ADJUST_REVIEWS_LINK,
    ),
    "R4.4, R4.6 the gate comes before its own commit, which committing-changes makes with its note": (
        _ADJUST_GATE,
        _ADJUST_STEP_6,
        _ADJUST_COMMIT,
        _ADJUST_COMMITTING_CHANGES,
        _ADJUST_NOTE,
    ),
    "R4.9 with Publish: live the commit is pushed": (_ADJUST_LIVE, _ADJUST_PUSH),
    "R4.9 in a local build whose pull requests are already open, it asks before pushing": (
        _ADJUST_PULL_REQUESTS_OPEN,
        _ADJUST_ASK_BEFORE_PUSHING,
    ),
    "R4.7, R4.8 the user is told which reviews ran, which ones the change did not need, and an edited criterion"
    " with its old and new wording": (
        _ADJUST_TELLS,
        _USER,
        _ADJUST_REVIEWS,
        _ADJUST_RAN,
        _ADJUST_NOT_NEEDED,
        _ADJUST_A_CRITERION,
        _ADJUST_OLD,
        _ADJUST_NEW,
    ),
    "R4.5 a diff that shows a plan change is not committed": (_ADJUST_PLAN_CHANGE, _ADJUST_NOT_COMMITTED),
    "R4.5 git log with the notes, per changed file, prints the Task: line of every task whose commit changed it": (
        _ADJUST_LOG_PER_FILE,
        _ADJUST_TASK_LINE,
    ),
    "R4.5 it is set aside with git stash push and the plan change is proposed": (
        _ADJUST_STASH_PUSH,
        _ADJUST_PLAN_CHANGE,
    ),
    "R4.5 the user recovers it by its message, with a SHA": (
        _ADJUST_STASH_LIST,
        _ADJUST_STASH_FORMAT,
        _ADJUST_STASH_APPLY,
    ),
    "R4.5 an adjustment that only grew past about 50 lines is kept, gets both reviews and the user is told": (
        _ADJUST_FIFTY_LINES,
        _ADJUST_KEEP,
        _ADJUST_BOTH_REVIEWS,
        _ADJUST_TELLS,
        _USER,
    ),
    "R4.5 when a review still fails after the fix round, it was not an adjustment": (
        _ADJUST_STILL_FAILS,
        _ADJUST_FIX_ROUND,
        _ADJUST_NOT_AN_ADJUSTMENT,
    ),
    "R4.5 an adjustment never goes to Rethink": (_ADJUST_ADJUSTMENT, _ADJUST_NEVER, _ADJUST_RETHINK),
    "R4.8 the next summary that is written lists the adjustment from its note": (_ADJUST_NOTE, _ADJUST_NEXT_SUMMARY),
    "R4.8 no summary is edited in the adjustment's own commit": (
        _ADJUST_DO_NOT_EDIT,
        _ADJUST_SUMMARY,
        _ADJUST_COMMIT,
    ),
    "R4.9 an adjustment made at a slice's pause belongs to the next slice": (_ADJUST_PAUSE, _ADJUST_NEXT_SLICE),
    "R4.9 with Publish: live the next slice's branch is cut and pushed first": (
        _ADJUST_LIVE,
        _ADJUST_NEXT_SLICES_BRANCH,
    ),
    "R4.8 once the feature is done its entries go to summary.md in one docs commit": (
        _ADJUST_SUMMARY_MD,
        _ADJUST_DOCS_COMMIT,
    ),
}
# (section of dispatch-prompts.md, the rule, the patterns one block of its fenced prompt must all match).
_ADJUST_PROMPT_RULES: tuple[tuple[str, str, tuple[re.Pattern[str], ...]], ...] = (
    (
        "test-writer (adjustment)",
        "R4.3 every test that asserts what the request changes is changed, and each must fail",
        (_ADJUST_EVERY_TEST_THAT_ASSERTS, _ADJUST_EACH_MUST_FAIL),
    ),
    (
        "implementer (adjustment)",
        "R4.3 without a test change, a request that changes what the code does comes back Status: BLOCKED",
        (_ADJUST_WHAT_THE_CODE_DOES, _ADJUST_STATUS_BLOCKED),
    ),
    (
        "adjustment review",
        "R4.4 the request and the criteria as they read after the change are what it must meet",
        (_ADJUST_REQUEST, _ADJUST_A_CRITERION, _ADJUST_MUST_MEET),
    ),
)
# What committing-changes' `### Inside develop-feature` must say about an adjustment's commit, each in one sentence.
_ADJUST_COMMITTING_RULES: dict[str, tuple[re.Pattern[str], ...]] = {
    "R4.6 the skill is called once per task and once per adjustment": (_ADJUST_ONCE_PER_ADJUSTMENT,),
    "R4.6 the commit is typed fix only for a defect, with the Escaped-gate: line in its note": (
        _ADJUST_FIX_TYPE,
        _ADJUST_ONLY,
        _ADJUST_DEFECT,
        _ADJUST_ESCAPED_GATE,
        _ADJUST_NOTE,
    ),
    "R4.6 the commit is never amended, because its note would stay on the old one": (
        _ADJUST_NEVER_AMEND,
        _ADJUST_NOTE,
    ),
}


def _sized_prompt_blocks(heading: str) -> list[str]:
    """Return the blocks of the fenced prompts of a `## <heading>` section of dispatch-prompts.md, or [] without it."""
    section = read_section(_SIZED_PROMPTS, heading)
    return _split_blocks("\n".join(re.findall(r"```\w*\n(.*?)```", section, re.DOTALL)).splitlines())


def _sized_rule_gaps(where: str, blocks: list[str], rules: dict[str, tuple[re.Pattern[str], ...]]) -> list[str]:
    """Return `<where> lacks: <rule>` for each rule whose patterns share no sentence of the blocks."""
    return [
        f"{where} lacks: {rule}"
        for rule, patterns in rules.items()
        if not any(_in_one_sentence(block, *patterns) for block in blocks)
    ]


def _sized_prompt_gaps(rules: tuple[tuple[str, str, tuple[re.Pattern[str], ...]], ...]) -> list[str]:
    """Return one message per rule whose patterns share no block of the fenced prompts of its section."""
    return [
        f"dispatch-prompts.md ## {heading} prompt lacks: {rule}"
        for heading, rule, patterns in rules
        if not any(all(pattern.search(block) for pattern in patterns) for block in _sized_prompt_blocks(heading))
    ]


def _after_table_rows() -> list[tuple[str, str]]:
    """Return the two cells of each row of the table of `## Reviews after a change`, without its header row."""
    rows = []
    for block in _section_blocks(_SIZED_SKILL, _AFTER_SECTION):
        cells = [cell.strip() for cell in block.strip("|").split("|")]
        if block.startswith("|") and len(cells) == 2 and not set(cells[0]) <= set("-: "):
            rows.append((cells[0], cells[1]))
    return rows[1:]


def _after_table_gaps() -> list[str]:
    """Return one message per rule no row of the table states: what the change did, in its first cell, with the
    reviews that run again, in its second cell, and none of the reviews that rule keeps out."""
    rows = _after_table_rows()
    return [
        f"develop-feature ## {_AFTER_SECTION} table lacks: {rule}"
        for rule, what, reviews, kept_out in _AFTER_TABLE_RULES
        if not any(
            all(pattern.search(first) for pattern in what)
            and all(pattern.search(second) for pattern in reviews)
            and not any(pattern.search(second) for pattern in kept_out)
            for first, second in rows
        )
    ]


def _after_fix_bug_gaps() -> list[str]:
    """Return what fix-bug's step 6 lacks of R3.6: only the reviews its fix round concerns run again, through a link
    to develop-feature's section, and a high-risk fix repeats them all."""
    fix_bug = _subsection_blocks(_section_blocks(SKILLS_DIR / "fix-bug" / "SKILL.md", "Workflow"), "### 6. reviews")
    gaps = []
    if not any(
        _in_one_sentence(block, _AFTER_ONLY, _AFTER_REVIEWS, _AFTER_AGAIN, _AFTER_FIX_BUG_LINK) for block in fix_bug
    ):
        gaps.append("fix-bug step 6 lacks (R3.6): only the reviews the fix round concerns run again, with a link")
    if not any(_in_one_sentence(block, _AFTER_HIGH, re.compile(r"\ball\b|\bevery\b")) for block in fix_bug):
        gaps.append("fix-bug step 6 lacks (R3.6): a high-risk fix repeats every review")
    return gaps


def _adjustment_prompt_gaps() -> list[str]:
    """Return what dispatch-prompts.md lacks of the three adjustment prompts: its Contents entry, the section with a
    fenced prompt that carries the user's request and, for the review, the orchestrator's verification output."""
    contents = read_section(_SIZED_PROMPTS, "Contents").lower().splitlines()
    gaps = []
    for heading in _ADJUST_PROMPTS:
        if not any(line.lstrip().startswith(("-", "*")) and heading in line for line in contents):
            gaps.append(f"dispatch-prompts.md: the Contents list does not name the {heading} prompt")
        prompt = _sized_prompt_blocks(heading)
        if not prompt:
            gaps.append(f"dispatch-prompts.md: no `## {heading}` section with a fenced prompt")
        elif not any(_ADJUST_REQUEST_PLACEHOLDER.search(block) for block in prompt):
            gaps.append(f"dispatch-prompts.md: the {heading} prompt does not carry the user's request (<request>)")
    review = _sized_prompt_blocks(_ADJUST_PROMPTS[-1])
    if review and not any(all(p.search(block) for p in _ADJUST_OUTPUT_FIELD) for block in review):
        gaps.append("dispatch-prompts.md: the adjustment review prompt has no field for the orchestrator's output")
    return gaps + _sized_prompt_gaps(_ADJUST_PROMPT_RULES)


def _adjustment_commit_gaps() -> list[str]:
    """Return what committing-changes' `### Inside develop-feature` lacks for an adjustment's commit (R4.6): the
    command that stages, commits and writes its note with the `Adjusts:`, `Reviews:` and `Asked:` lines, and the
    rules about its type and about amending it."""
    committing = _subsection_blocks(
        _section_blocks(SKILLS_DIR / "committing-changes" / "SKILL.md", "Workflow"), "### inside develop-feature"
    )
    gaps = []
    if not any(_ADJUST_COMMIT_AND_NOTE.search(block) for block in committing):
        gaps.append(
            "committing-changes ### Inside develop-feature lacks (R4.6): the adjustment's commit and note in one"
            " command, git add -A && git commit ... && git notes --ref=refs/notes/konundrm add, with its Adjusts:,"
            " Reviews: and Asked: lines"
        )
    where = "committing-changes ### Inside develop-feature"
    return gaps + _sized_rule_gaps(where, committing, _ADJUST_COMMITTING_RULES)


class RightSizedFlowTest(unittest.TestCase):
    maxDiff = None  # a failure lists every gap, not the first one

    def test_a_task_that_lists_several_tests_is_built_in_one_cycle(self) -> None:
        """R2.1, R2.2, R2.3, R3.9: 004 develop-feature builds a task that lists several tests in a single cycle.

        Phase 3 says, each part in one sentence: one test-writer dispatch writes every test the task lists (the one
        on its `Test:` line or each one of its `Tests:` list) and returns a report per test; each test is checked
        against its report; every test fails for the reason its RED report gives; a test that does not hold goes
        back alone to a new test-writer, naming the tests to leave as they are; when every test of the task already
        passes, step 2 is skipped; the implementer gets the RED reports and makes the tests pass one at a time, in
        the task's order, each one red before its code; and on a medium or high task the same dispatch also writes
        the property test of each listed invariant. The `## test-writer` prompts ask for every test of the `Tests:`
        list, one test per behavior, with a RED or a CHARACTERIZATION report for each test, the property tests of
        the task's invariants and, for a test sent back, the tests to leave as they are and the one to write or fix.
        The `## implementer` prompt makes every failing test pass one at a time, in the task's order, seeing each
        still fail before its code, and the fix-round prompt names the task's tests.
        """
        phase_3 = _section_blocks(_SIZED_SKILL, "Phase 3: Task loop")

        gaps = _sized_rule_gaps("develop-feature Phase 3", phase_3, _SIZED_PHASE_3_RULES)
        gaps += [
            f"dispatch-prompts.md ## {heading} prompt lacks: {rule}"
            for heading, rule, patterns in _SIZED_PROMPT_RULES
            if not any(_in_one_sentence(block, *patterns) for block in _sized_prompt_blocks(heading))
        ]

        self.assertEqual(gaps, [])

    def test_only_the_reviews_a_change_concerns_run_again(self) -> None:
        """R3.1, R3.2, R3.3, R3.5, R3.6, R3.7, R3.8, R3.9, R4.10: 004 after a change, only the reviews it concerns run.

        The table of develop-feature's `## Reviews after a change` has a row for each case: a change that fixed a
        review's finding goes back to that review; one that only added tests goes to the spec review alone; a change
        to a test that was there or to what the code does goes to the spec review and the code review; a change to
        how the code is built, or to what configures a gate, goes to the
        code review alone; a change to text that nothing reads repeats no review; and anything on a high task
        repeats every review, the security review included. Around it the section says, each part in one sentence:
        the reviews are decided from the change's own diff, never from the writer's report; inside a task the tree
        is marked with `git add -A && git write-tree` right before the change's first writer runs and its SHA kept,
        so the change alone is `git diff --stat <sha>` plus the untracked files of `git status --porcelain`,
        compared with that tree and never with the index, and without the SHA both reviews run; a file the product,
        a tool or a test reads is code, and a message's old wording is searched for before it counts as text that
        nothing reads; the row with no review holds only when every changed line is that kind of text; both reviews
        run when the row is not clear, and so does a review the user asks for; the fix of a red check always gets
        the code review again; the verify command reruns first when code or tests changed and the check stays green
        before the commit; and a task's first reviews always run in step 3 (the record of each review the rule
        leaves out is pinned by RightSizedFlowEdgesTest). Phase 3 marks the task before a fix round, before the
        first change of the verification by risk and before the fix of a red check, and sends each of those changes
        through that section (the verification by risk in one re-review, the fix of a red check always with the
        code review); no Phase 3 sentence still runs "the reviews of step 3 again". The re-review prompt carries the
        reports of every fix round since that review last ran, what the last round changed and a change the user
        asked for; the process-reviewer prompt carries the reviews not repeated. fix-bug's step 6 follows the same
        section and repeats every review on a high-risk fix.
        """
        phase_3 = _section_blocks(_SIZED_SKILL, "Phase 3: Task loop")
        section = _section_blocks(_SIZED_SKILL, _AFTER_SECTION)

        gaps = [] if section else [f"develop-feature: SKILL.md has no '## {_AFTER_SECTION}' section"]
        gaps += _after_table_gaps()
        gaps += _sized_rule_gaps(f"develop-feature ## {_AFTER_SECTION}", section, _AFTER_SECTION_RULES)
        gaps += _sized_rule_gaps("develop-feature Phase 3", phase_3, _AFTER_PHASE_3_RULES)
        gaps += [
            f"develop-feature Phase 3 still runs every review again after a change: {sentence.strip()}"
            for block in phase_3
            for sentence in _sentences(block)
            if _AFTER_OLD_RULE.search(sentence)
        ]
        gaps += _sized_prompt_gaps(_AFTER_PROMPT_RULES)
        gaps += _after_fix_bug_gaps()

        self.assertEqual(gaps, [])

    def test_a_change_the_user_asks_for_is_classified_first(self) -> None:
        """R1.9, R3.8, R4.1, R4.2, R4.3, R4.6, R4.8, R4.10, R4.11: 004 a requested change is classified first.

        develop-feature's `## Adjustments` section says, each part in one sentence: a change asked during the build,
        at a pause or once the feature is done is classified before anything is touched; it is a plan change when it
        adds or removes an acceptance criterion or a behavior no criterion covers, changes the design, a public
        interface or a dependency, touches a
        file a high task lists or anything the High row of the Standards names, changes code in a file no task of
        the feature lists, or is expected to take more than about 50 changed lines, and then becomes new tasks,
        written as writing-plans writes them with its consolidation, that the user approves and the task loop builds;
        a request that is not clearly one of the two is a plan change; for an adjustment the request is the approval
        and reference/adjustments.md says how it is made; a request that reports a defect is typed `fix`, with the
        `Escaped-gate:` line in its note; a change asked on the task in progress, before its commit, is classified
        the same way and joins that task: its criterion is edited in requirements.md first, the request is recorded
        under the task in tasks.md as a `- Change:` line, one more criterion for every later dispatch and review, it
        goes to the task's writers with the adjustment prompts (the test-writer's test must fail first), the
        reviews `## Reviews after a change` names run again with the re-review prompt, and it is not a failed
        review; only the feature's main session makes adjustments, at the next clean point, a session that has
        handed the feature over makes none, a partition session stops with a `BLOCKED:` line and a parallel wave
        holds the adjustment. Phase 0 sends a change on a feature that is already Done to that section without
        running Phase 4 again, reopens the feature for a plan change (its documents go back to Approved) and makes
        a partition session stop with `BLOCKED:`; Phase 3 sends a change asked during the build there instead of
        starting a task over; the Slice
        checkpoint lists the reviews not repeated; and Phase 4 writes the new tasks of its gaps as writing-plans
        does, lists in the feature summary the adjustments made after the final slice's summary and sends a change
        asked after its report to that section.
        """
        section = _section_blocks(_SIZED_SKILL, _ADJUST_SECTION)

        gaps = [] if section else [f"develop-feature: SKILL.md has no '## {_ADJUST_SECTION}' section"]
        gaps += _sized_rule_gaps(f"develop-feature ## {_ADJUST_SECTION}", section, _ADJUST_SECTION_RULES)
        gaps += [
            f"develop-feature ## {heading} lacks: {rule}"
            for heading, rule, patterns in _ADJUST_POINTER_RULES
            if not any(_in_one_sentence(block, *patterns) for block in _section_blocks(_SIZED_SKILL, heading))
        ]

        self.assertEqual(gaps, [])

    def test_an_adjustment_follows_its_procedure(self) -> None:
        """R4.3, R4.4, R4.5, R4.6, R4.7, R4.8, R4.9: 004 reference/adjustments.md is how an adjustment is made.

        It says, each part in one sentence: a criterion the request changes is edited in requirements.md before any
        dispatch; the test-writer goes first when the request changes what the code does, and its tests must fail; a
        test added, renamed or removed updates the task's lines in tasks.md; the orchestrator writes no code and no
        test itself and edits directly only the feature's documents and prose that nothing loads, runs or tests; the
        tests the adjustment changed or added run five times and the verify command of each task it adjusts once;
        the reviews come from its diff, as `## Reviews after a change` names them; the gate comes before its own
        commit, which committing-changes makes with its note; with `Publish: live` the commit is pushed, and a local
        build whose pull requests are open asks first; the user is told which reviews ran, which ones the change did
        not need, and an edited criterion with its old and new wording; a diff that shows a plan change is not
        committed but set aside with `git stash push`, recoverable by its message, and `git log` with the notes
        prints, per changed file, the `Task:` line of every task whose commit changed it; one that only grew past
        about 50
        lines is kept and gets both reviews; a review that still fails after the fix round means it was not an
        adjustment, which never goes to Rethink; the next summary that is written lists it from its note, so no
        summary is edited in its own commit; one made at a slice's pause belongs to the next slice, whose branch is
        cut and pushed first with `Publish: live`; and once the feature is done its entries go to summary.md in one
        docs commit.
        """
        gaps = [] if _ADJUST_REFERENCE.is_file() else ["develop-feature: reference/adjustments.md does not exist"]
        blocks = _blocks(_ADJUST_REFERENCE) if _ADJUST_REFERENCE.is_file() else []
        gaps += _sized_rule_gaps("develop-feature reference/adjustments.md", blocks, _ADJUST_REFERENCE_RULES)

        self.assertEqual(gaps, [])

    def test_an_adjustment_has_its_prompts_its_commit_and_its_note(self) -> None:
        """R4.3, R4.4, R4.6, R4.8, R4.10: 004 an adjustment has its own prompts, commit and note.

        dispatch-prompts.md has the three adjustment prompts, each named in its Contents and carrying the user's
        request: the test-writer's changes every test that asserts what the request changes, and each must fail; the
        implementer's, without a test change, returns `Status: BLOCKED` when the request changes what the code does;
        the review's says the request and the criteria as they read after the change are what it must meet, and has
        a field for the orchestrator's output. committing-changes' develop-feature mode is called once per task and
        once per adjustment, stages, commits and writes the adjustment's note in one command
        (`git add -A && git commit ... && git notes
        --ref=refs/notes/konundrm add` with its `Adjusts:`, `Reviews:` and `Asked:` lines), types the commit `fix`
        only for a defect, with the `Escaped-gate:` line in its note, and never amends it. The Slice checkpoint
        lists the adjustments with `git log --notes=refs/notes/konundrm --grep '^Adjusts:'`.
        """
        checkpoint = _section_blocks(_SIZED_SKILL, "Slice checkpoint")

        listing = (_ADJUST_GIT_LOG, _ADJUST_NOTES_REF, _ADJUST_GREP)

        gaps = _adjustment_prompt_gaps() + _adjustment_commit_gaps()
        if not any(all(pattern.search(block) for pattern in listing) for block in checkpoint):
            gaps.append(
                "develop-feature Slice checkpoint lacks (R4.8): listing the slice's adjustments with"
                " git log --notes=refs/notes/konundrm --grep '^Adjusts:'"
            )

        self.assertEqual(gaps, [])


# The right-sized flow (004), the edges its final review found: what happens to the property tests step 1 writes, to
# the record of a review that was not repeated, to a finished feature that is resumed, to a change asked on the task
# in progress, to an adjustment on a merged feature, to fix-bug's fix round and to a split task's attempt. Each rule
# is keywords that one sentence of its source must all match, on blocks from _split_blocks (lowercased, without
# backticks, single-spaced).
_EDGE_FIX_BUG = SKILLS_DIR / "fix-bug" / "SKILL.md"
_EDGE_COMMITTING = SKILLS_DIR / "committing-changes" / "SKILL.md"
_EDGE_OPENING = SKILLS_DIR / "opening-pull-requests" / "SKILL.md"
# Where a rule must be said: the name a failure shows, and the blocks to search.
_EDGE_SOURCES: dict[str, Callable[[], list[str]]] = {
    "develop-feature Phase 0": lambda: _section_blocks(_SIZED_SKILL, "Phase 0: Prepare"),
    "develop-feature Phase 3": lambda: _section_blocks(_SIZED_SKILL, "Phase 3: Task loop"),
    "develop-feature Reviews after a change": lambda: _section_blocks(_SIZED_SKILL, _AFTER_SECTION),
    "develop-feature Rethink": lambda: _section_blocks(_SIZED_SKILL, "Rethink"),
    "develop-feature Parallel partitions": lambda: _section_blocks(_SIZED_SKILL, "Parallel partitions"),
    "develop-feature Slice checkpoint": lambda: _section_blocks(_SIZED_SKILL, "Slice checkpoint"),
    "develop-feature Adjustments": lambda: _section_blocks(_SIZED_SKILL, _ADJUST_SECTION),
    "reference/adjustments.md": lambda: _blocks(_ADJUST_REFERENCE) if _ADJUST_REFERENCE.is_file() else [],
    "fix-bug step 6": lambda: _subsection_blocks(_section_blocks(_EDGE_FIX_BUG, "Workflow"), "### 6. reviews"),
    "fix-bug step 9": lambda: _subsection_blocks(_section_blocks(_EDGE_FIX_BUG, "Workflow"), "### 9. report"),
    "committing-changes Inside fix-bug": lambda: _subsection_blocks(
        _section_blocks(_EDGE_COMMITTING, "Workflow"), "### inside fix-bug"
    ),
    "opening-pull-requests": lambda: _blocks(_EDGE_OPENING),
    "the test-writer prompt": lambda: _sized_prompt_blocks("test-writer"),
    "the implementer prompt": lambda: _sized_prompt_blocks("implementer"),
    "the test-writer (adjustment) prompt": lambda: _sized_prompt_blocks("test-writer (adjustment)"),
}
_EDGE_TODO_ITEM = re.compile(r"\btodo item\b")
_EDGE_NOTES_APPEND = re.compile(r"\bgit notes --ref[= ]refs/notes/konundrm append\b")
_EDGE_NOT_REPEATED_LINE = re.compile(r"\bnot repeated:")
_EDGE_NOTES = re.compile(r"\bnotes\b")
_EDGE_APPEND = re.compile(r"\bappend\b")
_EDGE_NOTES_LOG = re.compile(r"\bgit log --notes=refs/notes/konundrm\b")
_EDGE_GREP_NOT_REPEATED = re.compile(r"--grep '\^not repeated:'")
_EDGE_DOES_NOT_COVER = re.compile(r"\bdoes not cover\b")
_EDGE_EVERY_TIME = re.compile(r"\bevery time\b")
_EDGE_FIVE_RUNS = re.compile(r"\bfive runs\b")
_EDGE_COVERING_PROPERTY_TASK = re.compile(r"\bproperty task that covers it\b")
_EDGE_FIVE_VERIFICATIONS = re.compile(r"\bfive verifications\b")
_EDGE_NEW_IMPLEMENTER = re.compile(r"\bnew implementer\b")
_EDGE_ALREADY_PASS = re.compile(r"\balready pass\b")
_EDGE_TEST_FILE = re.compile(r"\btest file\b")
_EDGE_EVIDENCE_FILE = re.compile(r"\bevidence file\b")
_EDGE_RUNS_ONLY_IT = re.compile(r"\bruns only it\b")
_EDGE_REPORT = re.compile(r"\breport\b")
_EDGE_FINISHED = re.compile(r"\bfinished\b")
_EDGE_WHATEVER = re.compile(r"\bwhatever\b|\bregardless\b|\bno matter\b")
_EDGE_NOT_MERGED = re.compile(r"\bnot merged\b")
_EDGE_MERGED = re.compile(r"\bmerged\b")
_EDGE_NEW_FEATURE = re.compile(r"\bnew feature\b")
_EDGE_HIGH_TASK = re.compile(r"\bhigh task\b")
_EDGE_ITSELF_BUILDS = re.compile(r"\bitself builds\b")
_EDGE_STOPS_THE_TASK = re.compile(r"\bstop the task\b")
_EDGE_ONE_ROUND = re.compile(r"\bone round\b")
_EDGE_STEP_2_NOT_RUN = re.compile(r"\bstep 2 has not run\b")
_EDGE_TASK_BLOCK = re.compile(r"\btask block\b")
_EDGE_ALREADY_SATISFIES = re.compile(r"\balready satisfies\b")
_EDGE_VERIFY_LINE = re.compile(r"\bverify: line\b")
_EDGE_HIGH_TASKS_FILE = re.compile(r"\bfile a high task lists or changed\b")
_EDGE_STOP_BEFORE = re.compile(r"\bstop before\b")
_EDGE_ASK_THE_USER = re.compile(r"\bask the user\b")
_EDGE_LEFT_FOR_LATER = re.compile(r"\bleaves for later\b")
_EDGE_STILL_BUILDING = re.compile(r"\bstill the one building\b")
_EDGE_TELL_THE_USER = re.compile(r"\btell the user\b")
_EDGE_NOW = re.compile(r"\bnow\b")
_EDGE_DEFAULT_BRANCH = re.compile(r"\bdefault branch\b")
_EDGE_SWITCH = re.compile(r"\bgit switch -c\b")
_EDGE_NEVER_COMMIT = re.compile(r"\bnever commit\b")
_EDGE_MERGED_BRANCH = re.compile(r"\bmerged branch\b")
_EDGE_OLD_DETAIL = re.compile(r"\bold detail\b")
_EDGE_GIT_GREP = re.compile(r"\bgit grep\b")
_EDGE_USES_A_NAME = re.compile(r"\buses a name it changes\b")
_EDGE_CHARACTERIZATION = re.compile(r"\bcharacterization\b")
_EDGE_NONE_FAILS = re.compile(r"\bnone of its tests fails\b")
_EDGE_STOP = re.compile(r"\bstop\b")
_EDGE_FINDING_VERIFIER = re.compile(r"\bfinding-verifier\b")
_EDGE_ONE_FIX_ROUND = re.compile(r"\bone fix[- ]round\b")
_EDGE_CLASSIFICATION_LINK = re.compile(r"\(\.\./skill\.md#adjustments\)")
_EDGE_FILE_NO_TASK = re.compile(r"\bfile no task\b")
_EDGE_BODY_AND_NOTE = re.compile(r"--format='%b%n'")
_EDGE_FOLLOW = re.compile(r"--follow\b")
_EDGE_PLAIN_MESSAGE = re.compile(r"\bletters, digits and spaces only\b")
_EDGE_ASIDE_THE_SAME_WAY = re.compile(r"\bset it aside the same way\b")
_EDGE_BEFORE_THE_TURN_ENDS = re.compile(r"\bbefore you end the turn\b|\bbefore the turn\b(?: \S+){0,4} ends\b")
_EDGE_NEVER_BEND = re.compile(r"\bnever bend\b")
_EDGE_STAGE = re.compile(r"\bstage\b")
_EDGE_MARK = re.compile(r"\bmark\b")
_EDGE_PLAIN_ADD = re.compile(r"\bgit add -a\b")
_EDGE_FIX_COMMIT = re.compile(r"\bgit add -a && git commit -f\b")
_EDGE_SPLIT = re.compile(r"\bsplit\b")
_EDGE_WHOLE_ATTEMPT_ASIDE = re.compile(r"\bwhole attempt aside\b")
_EDGE_EVERY_PART = re.compile(r"\bevery part\b")
_EDGE_STEP_1 = re.compile(r"\bstep 1\b")
_EDGE_USERS_YES = re.compile(r"\buser's yes\b")
_EDGE_DISPATCH_IMPLEMENTER = re.compile(r"\bdispatch implementer\b")
_EDGE_ADJUSTMENT_PROMPT = re.compile(r"\badjustment prompt\b")
_EDGE_AFTER_WHICH_CHANGE = re.compile(r"<review> after <the fix round \| verifying by risk \|")
_EDGE_WHAT_IT_TOUCHED = re.compile(r"<what the change touched>")
_EDGE_KEEPS_THE_TASKS_ID = re.compile(r"\bkeeps the task's id for its first part\b")
_EDGE_NEXT_UNUSED_ID = re.compile(r"\bnext unused id\b")
_EDGE_NEVER_RENUMBER = re.compile(r"\bnever renumber\b")
_EDGE_KEEPS_THE_PLAN_FILES = re.compile(re.escape(":(exclude)specs/<nnn-slug>/tasks.md"))
_EDGE_STAGED_STASH = re.compile(r"\bgit add -a && git stash push\b")
_EDGE_EVERY_REVIEW_OF_STEP_3 = re.compile(r"\bevery review of step 3\b")
_EDGE_FILE_A_HIGH_TASK_LISTS = re.compile(r"\bfile a high task lists\b")
_EDGE_CRITERION_FROM_COMMIT = re.compile(re.escape("git show <sha> -- specs/<nnn-slug>/requirements.md"))
_EDGE_NEWEST_SUMMARY_COMMIT = re.compile(re.escape("git log -1 --format=%h -- specs/<nnn-slug>/summary.md"))
_EdgeRules = tuple[tuple[str, str, tuple[re.Pattern[str], ...]], ...]
# (source, the rule, the patterns one of its sentences must all match).
_EDGE_RECORD_RULES: _EdgeRules = (
    (
        "develop-feature Reviews after a change",
        "R3.8 each review the rule leaves out is noted in the task's todo item",
        (_AFTER_LEAVES_OUT, _AFTER_NOTE, _EDGE_TODO_ITEM),
    ),
    (
        "develop-feature Reviews after a change",
        "R3.8 after the task's commit each one is appended to the task's note as a Not repeated: line",
        (_EDGE_NOTES_APPEND, _EDGE_NOT_REPEATED_LINE, _EDGE_AFTER_WHICH_CHANGE, _EDGE_WHAT_IT_TOUCHED),
    ),
    (
        "develop-feature Reviews after a change",
        "R3.8 the slice summary lists them from those notes",
        (_AFTER_SLICE_SUMMARY, _EDGE_NOTES),
    ),
    (
        "develop-feature Phase 3",
        "R3.8 the commit step appends to the task's note each review it did not repeat",
        (_EDGE_APPEND, _AFTER_NOTE, _AFTER_DID_NOT_REPEAT, _AFTER_LINK),
    ),
    (
        "develop-feature Slice checkpoint",
        "R3.8 the summary lists them with git log on the notes, by their Not repeated: line",
        (_EDGE_NOTES_LOG, _EDGE_GREP_NOT_REPEATED),
    ),
    (
        "develop-feature Slice checkpoint",
        "R4.8 the criterion an adjustment updated is read from its commit",
        (_EDGE_CRITERION_FROM_COMMIT,),
    ),
    (
        "fix-bug step 9",
        "R3.8 the report names each review not repeated after a fix round",
        (_AFTER_DID_NOT_REPEAT, _AFTER_FIX_ROUND),
    ),
    (
        "opening-pull-requests",
        "R4.8 the summary link uses the newest commit that changed summary.md",
        (_EDGE_NEWEST_SUMMARY_COMMIT,),
    ),
)
_EDGE_BUILD_RULES: _EdgeRules = (
    (
        "develop-feature Phase 3",
        "R3.9 the command of a test the verify command does not cover runs every time: the five runs, each rerun"
        " and the output the reviews get",
        (_EDGE_DOES_NOT_COVER, _EDGE_EVERY_TIME, _EDGE_FIVE_RUNS),
    ),
    (
        "develop-feature Phase 3",
        "R3.9 an invariant is not missing when a property task of the plan covers it",
        (_SIZED_INVARIANT, _EDGE_COVERING_PROPERTY_TASK),
    ),
    (
        "develop-feature Phase 3",
        "R2.2 tests that already pass skip the implementer and still get their five verifications",
        (_SIZED_SKIPS_STEP_2, _EDGE_FIVE_VERIFICATIONS),
    ),
    (
        "develop-feature Phase 3",
        "R2.3 a test that went back to the test-writer is built by a new implementer, told which tests already pass",
        (_EDGE_NEW_IMPLEMENTER, _EDGE_ALREADY_PASS),
    ),
    (
        "develop-feature Phase 3",
        "R3.1 a red check in a test file goes to a new test-writer",
        (_AFTER_CHECK_FAILS, _SIZED_NEW_TEST_WRITER, _EDGE_TEST_FILE),
    ),
    (
        "develop-feature Phase 3",
        "R3.9 the evidence file the orchestrator saves is not a change that brings reviews back",
        (_EDGE_EVIDENCE_FILE, _AFTER_ONE_RE_REVIEW),
    ),
    (
        "develop-feature Parallel partitions",
        "R3.2 an integration fix that touches a file a high task lists gets every review of step 3",
        (_EDGE_EVERY_REVIEW_OF_STEP_3, _EDGE_FILE_A_HIGH_TASK_LISTS),
    ),
    (
        "the test-writer prompt",
        "R3.9 a property test the verify command does not cover runs with a command of its own, given in its report",
        (_SIZED_PROPERTY_TEST, _EDGE_RUNS_ONLY_IT, _EDGE_REPORT),
    ),
    (
        "the implementer prompt",
        "R2.3 another implementer of the same task is told which tests already pass",
        (_EDGE_ALREADY_PASS, _SIZED_PLACEHOLDER),
    ),
    (
        "develop-feature Rethink",
        "R2.5 a split always sets the whole attempt aside",
        (_EDGE_SPLIT, _AFTER_ALWAYS, _EDGE_WHOLE_ATTEMPT_ASIDE),
    ),
    ("develop-feature Rethink", "R2.5 every part is then built from step 1", (_EDGE_EVERY_PART, _EDGE_STEP_1)),
    (
        "develop-feature Rethink",
        "R2.5 a split keeps the task's ID for its first part and gives each other part the next unused ID",
        (_EDGE_SPLIT, _EDGE_KEEPS_THE_TASKS_ID, _EDGE_NEXT_UNUSED_ID),
    ),
    ("develop-feature Rethink", "R2.5 a split never renumbers a task", (_EDGE_NEVER_RENUMBER,)),
    (
        "develop-feature Rethink",
        "R4.10 the set-aside keeps tasks.md and requirements.md out of the stash when a decision or a change was"
        " recorded for the task",
        (_EDGE_KEEPS_THE_PLAN_FILES, re.compile(re.escape(":(exclude)specs/<nnn-slug>/requirements.md"))),
    ),
    (
        "develop-feature Rethink",
        "R3.7 the attempt is staged before it is stashed, so a deleted file stays deleted",
        (_EDGE_STAGED_STASH,),
    ),
    (
        "fix-bug step 6",
        "R3.7 the tree is marked before the fix round's first writer runs, and its SHA kept",
        (_AFTER_GIT_ADD, _AFTER_SHA, _AFTER_BEFORE),
    ),
    (
        "committing-changes Inside fix-bug",
        "R3.7 the fix is staged in the same command as its commit, because a fix round's mark leaves an older"
        " tree staged",
        (_EDGE_STAGE, _EDGE_PLAIN_ADD, _EDGE_MARK),
    ),
)
_EDGE_REQUEST_RULES: _EdgeRules = (
    (
        "develop-feature Phase 0",
        "R4.11 a feature whose documents read Status: Done is finished whatever status would print",
        (_ADJUST_STATUS_DONE, _EDGE_FINISHED, _EDGE_WHATEVER),
    ),
    (
        "develop-feature Phase 0",
        "R4.2 a plan change reopens a finished feature only while its pull requests are not merged",
        (_ADJUST_REOPENS, _EDGE_NOT_MERGED, _EDGE_USERS_YES),
    ),
    (
        "develop-feature Phase 0",
        "R4.2 once it is merged, the change is proposed as a new feature",
        (_EDGE_MERGED, _EDGE_NEW_FEATURE),
    ),
    (
        "develop-feature Adjustments",
        "R4.10 on a high task a change asked on the task in progress is always a plan change",
        (_ADJUST_TASK_IN_PROGRESS, _EDGE_HIGH_TASK, _ADJUST_PLAN_CHANGE),
    ),
    (
        "develop-feature Adjustments",
        "R4.10 a plan change to what the task itself builds stops the task",
        (_EDGE_ITSELF_BUILDS, _EDGE_STOPS_THE_TASK),
    ),
    (
        "develop-feature Adjustments",
        "R4.10 a change on the task in progress first waits for the subagents that are running",
        (re.compile(r"(?<!not )(?<!never )\bwait for the subagents that are running\b"),),
    ),
    (
        "develop-feature Adjustments",
        "R4.10 changes asked together join the task in one round",
        (_ADJUST_JOINS_THAT_TASK, _EDGE_ONE_ROUND),
    ),
    (
        "develop-feature Adjustments",
        "R4.10 before step 2 has run, steps 1 and 2 go on with the task block as it now reads",
        (_EDGE_STEP_2_NOT_RUN, _EDGE_TASK_BLOCK),
    ),
    (
        "develop-feature Adjustments",
        "R4.10 a test the code already satisfies need not fail first",
        (_ADJUST_MUST_FAIL, _EDGE_ALREADY_SATISFIES),
    ),
    (
        "develop-feature Adjustments",
        "R4.10 a test added, renamed or removed updates the task's Test: and Verify: lines",
        (_ADJUST_ADDED_RENAMED_REMOVED, _EDGE_VERIFY_LINE),
    ),
    (
        "develop-feature Adjustments",
        "R4.10 a diff that reaches a file a high task lists or changed stops before the commit and asks the user",
        (_EDGE_HIGH_TASKS_FILE, _EDGE_STOP_BEFORE, _EDGE_ASK_THE_USER),
    ),
    (
        "develop-feature Adjustments",
        "R4.11 a request left for later is made then, as long as this session still builds the feature",
        (_EDGE_LEFT_FOR_LATER, _EDGE_STILL_BUILDING),
    ),
    (
        "develop-feature Adjustments",
        "R4.11 the user is told when an adjustment is held for a wave",
        (_ADJUST_WAVE, _ADJUST_HOLD, _EDGE_TELL_THE_USER),
    ),
)
_EDGE_PROCEDURE_RULES: _EdgeRules = (
    (
        "reference/adjustments.md",
        "R4.9 at a live pause the next slice's branch is cut and pushed now, before the adjustment",
        (_ADJUST_LIVE, _ADJUST_NEXT_SLICES_BRANCH, _EDGE_NOW),
    ),
    (
        "reference/adjustments.md",
        "R4.9 on a finished feature whose branch is merged, the adjustment gets a new branch from the default branch",
        (_EDGE_DEFAULT_BRANCH, _EDGE_SWITCH),
    ),
    (
        "reference/adjustments.md",
        "R4.9 an adjustment is never committed on the default branch nor pushed to a merged branch",
        (_EDGE_NEVER_COMMIT, _EDGE_DEFAULT_BRANCH, _EDGE_MERGED_BRANCH),
    ),
    (
        "reference/adjustments.md",
        "R4.7 the plan is searched for the old detail and each line that still states it is updated",
        (_EDGE_OLD_DETAIL, _EDGE_GIT_GREP, _TASKS_MD),
    ),
    (
        "reference/adjustments.md",
        "R4.3 a rename the tests call sends the test-writer first",
        (_EDGE_USES_A_NAME, _ADJUST_TEST_WRITER),
    ),
    (
        "reference/adjustments.md",
        "R4.3 a test the code already satisfies is kept as a CHARACTERIZATION instead of failing",
        (_ADJUST_MUST_FAIL, _EDGE_CHARACTERIZATION, _EDGE_ALREADY_SATISFIES),
    ),
    (
        "reference/adjustments.md",
        "R4.3 when none of its tests fails, the code already does what was asked: stop and tell the user",
        (_EDGE_NONE_FAILS, _EDGE_STOP, _EDGE_TELL_THE_USER),
    ),
    (
        "reference/adjustments.md",
        "R3.7, R4.4 a doubtful Critical finding goes to a finding-verifier before the one fix round, and the tree is"
        " marked before that round",
        (_EDGE_FINDING_VERIFIER, _EDGE_ONE_FIX_ROUND, _ADJUST_MARKS_THE_TREE),
    ),
    (
        "reference/adjustments.md",
        "R4.3 the implementer makes the change, with the adjustment prompt",
        (_EDGE_DISPATCH_IMPLEMENTER, _EDGE_ADJUSTMENT_PROMPT),
    ),
    (
        "reference/adjustments.md",
        "R4.5 the diff is checked against every condition of the classification, a file no task lists included",
        (_EDGE_CLASSIFICATION_LINK, _EDGE_FILE_NO_TASK),
    ),
    (
        "reference/adjustments.md",
        "R4.5 the lookup of the tasks that changed a file reads the note or the message and follows renames",
        (_EDGE_BODY_AND_NOTE, _EDGE_FOLLOW),
    ),
    (
        "reference/adjustments.md",
        "R4.5 the set-aside message is written with letters, digits and spaces only",
        (_EDGE_PLAIN_MESSAGE,),
    ),
    (
        "reference/adjustments.md",
        "R4.5 a change whose review still fails is set aside the same way and proposed as a plan change",
        (_EDGE_ASIDE_THE_SAME_WAY, _ADJUST_PLAN_CHANGE),
    ),
    (
        "reference/adjustments.md",
        "R4.8 on a finished feature the entries go to summary.md before the turn ends",
        (_EDGE_BEFORE_THE_TURN_ENDS, _ADJUST_SUMMARY_MD),
    ),
    (
        "the test-writer (adjustment) prompt",
        "R4.3 tests that use a name the request changes are changed too",
        (_EDGE_USES_A_NAME,),
    ),
    (
        "the test-writer (adjustment) prompt",
        "R4.3 a test the code already satisfies gets a CHARACTERIZATION report and is never bent to fail",
        (_EDGE_ALREADY_SATISFIES, _EDGE_NEVER_BEND, _SIZED_CHARACTERIZATION_REPORT),
    ),
)


def _edge_gaps(rules: _EdgeRules) -> list[str]:
    """Return `<source> lacks: <rule>` for each rule whose patterns share no sentence of its source."""
    return [
        f"{source} lacks: {rule}"
        for source, rule, patterns in rules
        if not any(_in_one_sentence(block, *patterns) for block in _EDGE_SOURCES[source]())
    ]


class RightSizedFlowEdgesTest(unittest.TestCase):
    maxDiff = None  # a failure lists every gap, not the first one

    def test_reviews_not_repeated_and_adjustments_leave_a_record_that_travels(self) -> None:
        """R3.8, R4.8: 004 what was not reviewed again, and what an adjustment changed, is read from Git.

        develop-feature's `## Reviews after a change` notes each review the rule leaves out in the task's todo item,
        appends it to the task's note right after its commit (`git notes --ref=refs/notes/konundrm append` with a
        `Not repeated:` line) and has the slice summary list them from those notes; step 7 of Phase 3 appends them;
        the Slice checkpoint lists them with `git log --notes=refs/notes/konundrm --grep '^Not repeated:'` and reads
        the criterion an adjustment updated from its commit; fix-bug's report names each review not repeated after a
        fix round; and opening-pull-requests links the summary at the newest commit that changed `summary.md`.
        """
        gaps = _edge_gaps(_EDGE_RECORD_RULES)

        self.assertEqual(gaps, [])

    def test_the_one_cycle_build_covers_its_property_tests_and_its_second_dispatches(self) -> None:
        """R2.2, R2.3, R2.5, R3.1, R3.2, R3.7, R3.9, R4.10: 004 the edges of building a task in one cycle.

        Phase 3 runs the command of a test the verify command does not cover every time the task runs it (the five
        runs, each rerun, the output the reviews get); does not count as missing an invariant a `property` task
        covers; gives tests that already pass their five verifications; has a new implementer build a test that
        went back to the test-writer, told which tests already pass; sends a red check in a test file to a new
        test-writer; and does not treat the evidence file as a change. An integration fix on a file a `high` task
        lists gets every review of step 3. The test-writer prompt runs such a property test with a command of its
        own and the implementer prompt names the tests that already pass. A rethink's split keeps the task's ID for
        its first part, gives each other part the next unused ID, never renumbers a task, always sets the whole
        attempt aside and builds every part from step 1; its stash is staged first and keeps tasks.md and
        requirements.md out when a decision or a change was recorded. fix-bug marks the tree before its fix round,
        and committing-changes stages the fix in the same command as its commit.
        """
        gaps = _edge_gaps(_EDGE_BUILD_RULES)
        committing = _EDGE_SOURCES["committing-changes Inside fix-bug"]()
        if not any(_EDGE_FIX_COMMIT.search(block) for block in committing):
            gaps.append("committing-changes ### Inside fix-bug lacks (R3.7): git add -A && git commit -F ...")

        self.assertEqual(gaps, [])

    def test_a_finished_feature_and_a_task_in_progress_take_a_change_safely(self) -> None:
        """R4.2, R4.10, R4.11: 004 a change on a finished feature or on the task in progress is handled safely.

        Phase 0 knows a finished feature by its documents (`Status: Done`), whatever `status` would print, reopens it
        for a plan change only while its pull requests are not merged, and otherwise proposes a new feature.
        `## Adjustments` says, each part in one sentence: on a `high` task a change on the task in progress is always
        a plan change; a plan change to what the task itself builds stops the task; changes asked together join the
        task in one round; before step 2 has run, steps 1 and 2 go on with the task block as it now reads; a test
        the code already satisfies need not fail first; a test added, renamed or removed updates the task's lines;
        a diff that reaches a file a `high` task lists or changed stops before the commit and asks the user; a
        request left for later is made then while this session still builds the feature; and the user is told when
        an adjustment is held for a wave.
        """
        gaps = _edge_gaps(_EDGE_REQUEST_RULES)

        self.assertEqual(gaps, [])

    def test_an_adjustment_has_a_branch_a_red_step_that_can_be_met_and_a_safe_set_aside(self) -> None:
        """R4.3, R4.4, R4.5, R4.7, R4.8, R4.9: 004 the edges of making an adjustment.

        reference/adjustments.md says, each part in one sentence: at a live pause the next slice's branch is cut and
        pushed now; on a finished feature whose branch is merged the adjustment gets a new branch from the default
        branch, and is never committed on the default branch nor pushed to a merged branch; the plan is searched
        for the old detail; a rename the tests call sends the test-writer first; a test the code already satisfies
        is kept as a CHARACTERIZATION; when none of its tests fails it stops and tells the user; a doubtful Critical
        finding goes to a finding-verifier before the one fix round; the diff is checked against every condition of
        the classification; the lookup of the tasks that changed a file reads the note or the message and follows
        renames; the set-aside message uses letters, digits and spaces only; a change whose review still fails is set
        aside the same way and proposed as a plan change; and on a finished feature the entries
        go to summary.md before the turn ends. The test-writer (adjustment) prompt changes the tests that use a
        name the request changes and returns a CHARACTERIZATION report, never a bent test, for one the code
        already satisfies.
        """
        gaps = _edge_gaps(_EDGE_PROCEDURE_RULES)

        self.assertEqual(gaps, [])


if __name__ == "__main__":
    unittest.main()
