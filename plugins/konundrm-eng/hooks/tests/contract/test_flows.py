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


# The pause at the end of a slice (R4.1, R6.1). These run on the blocks of develop-feature's `## Slice checkpoint`
# section, each rule within one sentence (_in_one_sentence) so an unrelated sentence cannot satisfy it.
_CHECKPOINT_WHEN = re.compile(r"\b(?:when|once|after)\b")
_CHECKPOINT_LAST_TASK = re.compile(r"\blast task\b")
_CHECKPOINT_LANDED = re.compile(r"\b(?:committed|integrated|lands|landed)\b")
_CHECKPOINT_WRITES = re.compile(r"\b(?:writ|fill|sav)\w*")
_CHECKPOINT_TEMPLATE = re.compile(r"\btemplates/slice-summary\.md\b")
_CHECKPOINT_SUMMARY_FILE = re.compile(r"\bspecs/<[^>\s]+>/summaries/s<k>\.md\b")
_CHECKPOINT_SUMMARY_COMMIT = re.compile(r"\bdocs\([^)\s]+\): summarize slice s<k>")
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
    "R6.1 it commits the summary as docs(<scope>): summarize slice S<k>": (_CHECKPOINT_SUMMARY_COMMIT,),
    "R6.1 the summary commit carries the Task: line of the slice's last task": (_TASK_LINE, _CHECKPOINT_LAST_TASK),
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


# Changes the user asks for at the slice pause (R4.4). These run on the blocks of develop-feature's
# `## Slice checkpoint` section, each rule within one sentence (_in_one_sentence) so an unrelated sentence cannot
# satisfy it. The approval rule asks for an approval of the changes themselves, so the go-ahead sentence alone ("wait
# for the user's go-ahead before starting the next slice") cannot satisfy it.
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
_CHANGES_OUTSIDE = re.compile(r"\boutside\b")

# What develop-feature's `## Slice checkpoint` section must say about changes asked at the pause, each in one sentence.
_CHANGES_RULES: dict[str, tuple[re.Pattern[str], ...]] = {
    "R4.4 when the user asks for changes at the pause": (_CHANGES_WHEN, _USER, _CHANGES_ASKED, _CHANGES_AT_THE_PAUSE),
    "R4.4 the changes become new tasks in tasks.md": (_CHANGES_CHANGES, _CHANGES_TURNS, _CHANGES_NEW_TASKS, _TASKS_MD),
    "R4.4 or a plan change to design.md/tasks.md": (_CHANGES_CHANGES, _CHANGES_TURNS, _PLAN_EDIT, _CHANGES_DESIGN_MD),
    "R4.4 the user approves them before the next slice starts": (
        _CHANGES_APPROVES,
        _USER,
        _CHANGES_APPROVED_ITEM,
        _CHECKPOINT_BEFORE,
        _CHECKPOINT_NEXT_SLICE,
    ),
    "R4.4 the changes are never made on the spot, outside the task loop": (
        _CHANGES_NEVER_MAKES,
        _CHANGES_OUTSIDE,
        _TASK_LOOP,
    ),
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
_RESUME_CHECKPOINT_MISSING = re.compile(r"\b(?:missing|lacks|lacking|without|has no)\b")
_RESUME_CHECKPOINT_RULES: dict[str, Callable[[str], bool]] = {
    "R4.1, R6.1 a slice whose every task has its commit but whose summary commit is missing": lambda block: (
        _in_one_sentence(block, _EVERY_TASK_COMMIT, _COMMIT, _CHECKPOINT_SUMMARY_COMMIT, _RESUME_CHECKPOINT_MISSING)
    ),
    "R4.1 running the Slice checkpoint before the next slice's first task": lambda block: any(
        _CHECKPOINT_LINK in sentence and _CHECKPOINT_BEFORE.search(sentence) and _CHECKPOINT_NEXT_SLICE.search(sentence)
        for sentence in _sentences(block)
    ),
}


def _resume_checkpoint_gaps(skill: Path) -> list[str]:
    """Return one message when no block of develop-feature's `## Phase 0: Prepare` section names the summary commit,
    else one per rule of _RESUME_CHECKPOINT_RULES that no such block states."""
    blocks = [block for block in _section_blocks(skill, "Phase 0: Prepare") if _CHECKPOINT_SUMMARY_COMMIT.search(block)]
    if not blocks:
        return ["develop-feature Phase 0: no block names the summary commit docs(<scope>): summarize slice S<k>"]
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

    def test_develop_feature_pauses_after_each_slice(self) -> None:
        """R4.1, R6.1: develop-feature's `## Slice checkpoint` section runs once a slice's last task is committed (and,
        with partitions, integrated): it writes the slice's summary from `templates/slice-summary.md` to
        `specs/<slug>/summaries/S<k>.md` and commits it as `docs(<scope>): summarize slice S<k>` with the `Task:` line
        of the slice's last task, so it stays in that slice's pull request; then it stops, shows the user the summary
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

    def test_changes_asked_at_a_checkpoint_become_tasks(self) -> None:
        """R4.4: when the user asks for changes at the slice pause, develop-feature's `## Slice checkpoint` section
        turns them into new tasks in tasks.md or a plan change to design.md/tasks.md, which the user approves before
        the next slice starts (an approval of the changes, not the go-ahead alone), and never makes them on the spot,
        outside the task loop."""
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
        """R4.1, R6.1: when develop-feature resumes a slice whose every task has its commit but whose summary commit
        `docs(<scope>): summarize slice S<k>` is missing (the session stopped between the two), its `## Phase 0:
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


if __name__ == "__main__":
    unittest.main()
