# Rethink: T77 — pre-approved decisions recorded apart from the pauses

Date: 2026-10-30 · Branch: `claude/p-decisions-t77` (base `4bd69e6`) · Trigger: the code review
failed a third time (spec 3 passed · code 3 failed). Report of `konundrm-eng:rethinker`, verbatim
except that the session scratchpad's absolute path is shortened to `<session scratchpad>`.

RETHINK: T77
Verdict: NEW APPROACH
Why it keeps failing:
- **The prose is not the problem.** All three code reviews approved the prose in SKILL.md, the template and the CHANGELOG, and all three spec reviews passed. Only one Critical was outside the guards: CR1-C1, the CHANGELOG check reading the newest entry, which was fixed and stayed fixed. Every other Critical is in one of the test's two "no sentence anywhere means X" guards:
  - `_decisions_ties_to_checkpoints` (test_flows.py:1615-1623, with its excuse `_DECISIONS_CHECKPOINTS_NEGATED` at :1516):
    - CR1-C2: flagged correct prose.
    - CR2-C: missed "An open decision never pauses under `Checkpoints: pre-approved` either."
    - Still open: CR3-S1 flags the correct sentence that names both lines, and CR3-S2 misses "does not wait and takes the recommended option".
  - `_decisions_ties_to_pauses` (:1626-1638, with `_DECISIONS_CLAUSE_TEXT` at :1502):
    - It did not exist before fix round 1, which built it from CR1's Suggestion S2.
    - CR2-S(a) flagged correct prose; the fix that followed is what CR3-C now flags.
    - Reproduced with t77-code3-mine/repro.py: the three correct prohibitions ("Never record `- **Decisions:** pre-approved` just because the user approved the pauses." and the two like it) return True, and adding the first one to Phase 2 fails the whole test.
- **Why these guards can't converge:**
  - Each guard claims what an arbitrary sentence *means* ("keys an open decision to Checkpoints", "sets Decisions because the pauses were approved"). It decides that with negation windows and clause splits, but whether a negation or a condition covers a phrase is not something a regex can decide.
  - So every boundary has natural sentences on both sides. Make it wider, and correct prose fails with a message that says the opposite of the sentence (CR1-C2, CR3-C). Make it narrower, and the bug itself passes (CR2-C).
  - code-reviewer.md:57-58 makes both cases Critical ("a test that does not test what it claims").
  - The code reviewer gets only the diff (dispatch-prompts.md:105-115), so each round probes the boundary from scratch.
  - The fixes kept moving the boundary instead of removing it. The block grew from about 190 to about 250 lines (spec reviews 1 and 3).
- **The task does not ask for either guard.** The Test field (tasks.md:617) writes "solo con `Decisions: pre-approved`" as a positive statement ("con `Checkpoints: pre-approved` sola sigue pausando la tarea y preguntando"), and the positive rules already pin that. The Test field does not mention the CHANGELOG at all.

Alternatives:
1. **Positive rules only.**
   - Change: delete both guards and the CHANGELOG guard loop. The docstring then claims only "a sentence of section X says Y", like `_PREAPPROVED_RULES` and `_OPEN_DECISION_RULES` do.
   - Criteria and findings: it meets the Test field, and CR3-C, CR3-S1 and CR3-S2 disappear.
   - Risk: it reopens CR2's Critical. A contradicting sentence added next to the correct one passes: none of the 7 wrong probes is caught when added. A fresh reviewer, or the spec reviewer reading "solo con", would likely raise it again.
2. **Positive rules plus one structural guard that never judges meaning.**
   - The rule: every sentence of develop-feature's SKILL.md, and of the CHANGELOG's 0.6.0 entry, that names `Checkpoints: pre-approved` together with a decision (outside a header) or the recommended option must also name a `Decisions:` value. It must not join the two `pre-approved` values with "or".
   - It has no negation, clause or verb logic, so there is nothing to get wrong about scope. Its message states the rule, so it can never claim the opposite of what a sentence says.
   - The positive R5.2 rule adopts the same convention.
   - Prototype results (proto.py, read-only, temp copies):
     - On the current SKILL.md, CHANGELOG and template it reports nothing.
     - On the HEAD versions it reports 12 gaps, the same shape as the original RED, including the old Phase 3 sentence and the old CHANGELOG sentence.
     - All 8 correct sentences from CR1–CR3 pass, including CR3-C's three prohibitions and CR3-S1's sentence naming both lines.
     - All 7 wrong ones are flagged: CR2-C, CR1's "Decisions: pre-approved or Checkpoints: pre-approved", CR3-S2's coordinated negations and the original bug sentences. Each was tried in three places: the Slice checkpoint, the Phase 3 paragraph that states the rule, and the CHANGELOG decisions bullet.
   - Risk: two narrow known limits (probe2.py).
     - A correct sentence that relates `Checkpoints: pre-approved` to a decision without naming the `Decisions:` line fails loudly, with an honest message. CR3 rated loud failures like that as Suggestions.
     - A wrong sentence that names both lines without "or" ("…and under `Checkpoints: pre-approved` too…") is left to the positive rules.

Recommended: 2. It keeps the protection CR2 demanded (the bug must not come back anywhere) and removes what produced every later Critical: claims about meaning decided by regex. The block gets shorter and the approved prose stays as it is.

Current attempt: KEEP (adjust it)

Instructions:
- test-writer (fix round, opus/high). Edit only test_flows.py, and only inside the `_DECISIONS_` block and the T77 test method; T78 edits the rest of that file in parallel.
  1. Delete `_decisions_ties_to_checkpoints`, `_decisions_ties_to_pauses` and the names only they use: `_DECISIONS_CHECKPOINTS_NEGATED`, `_DECISIONS_BEFORE_HEADER`, `_DECISIONS_CLAUSE_TEXT`, `_DECISIONS_PAUSES_APPROVED` and `_DECISIONS_APPROVAL`. Grep each one before deleting it. Then drop the `prefix` parameter of `_decisions_not_after_header`, since no caller will pass it.
  2. Add `_DECISIONS_EITHER_LINE`: the two `pre-approved` header values joined by "or", in either order, with at most 2 words between.
  3. Add one predicate (for example `_decisions_leaves_out_the_line(sentence)`). It is true when the sentence matches `_PREAPPROVED_LINE` and also `_DECISIONS_DECISION` or `_DECISIONS_RECOMMENDED`, and then either does not match `_DECISIONS_HEADER` or does match `_DECISIONS_EITHER_LINE`. Put no negation, clause, verb or polarity logic in it.
  4. In `_decisions_skill_gaps` (every SKILL.md sentence) and `_decisions_changelog_gaps` (every sentence of the 0.6.0 entry), replace the guard loops with this predicate. The message states the rule and never what the sentence means: "…names Checkpoints: pre-approved with an open decision or the recommended option but not the Decisions: line that decides it, or offers either line with 'or' (R5.3): '<sentence>'".
  5. In the Phase 3 R5.2 rule, add `_DECISIONS_HEADER` to its patterns. Label it "R5.2 with Checkpoints: pre-approved and Decisions: ask an open decision still pauses the task and asks the user".
  6. For CR3-S3, replace `_DECISIONS_APART` with a pattern of its own. It accepts only "separately", "apart", "independently", "on its own", or a negation at most 2 words before "approv…". The adjective "separate" and other negation words no longer count. The current sentence must pass, and "Approving the pauses also approves the decisions, with no separate question." must fail the rule.
  7. Keep these as they are:
     - `_decisions_says`, `_DECISIONS_TAKE`, `_DECISIONS_TAKES_RECOMMENDED`, `_DECISIONS_NEGATED_TAKE` and `_DECISIONS_NEGATED_PAUSE`.
     - `_DECISIONS_CLAUSE_NEGATION`: do not narrow its window for CR3-S2. It now feeds only positive rules, and leaving out "or" would reject "never stops or pauses".
     - `_DECISIONS_CITED`, `_decisions_template_gaps`, the `[0.6.0]` pinning and the CHANGELOG positive check, and `test_pre_approved_checkpoints_do_not_stop`.
  8. Rewrite the block comment and the docstrings of the predicate, `_decisions_skill_gaps`, `_decisions_changelog_gaps` and the T77 test method:
     - Claim exactly the positive rules plus the structural rule.
     - Say why the rule is polarity-free.
     - List its two known limits: a sentence without the `Decisions:` line fails even when correct (add the line), and a sentence naming both lines is judged by the positive rules.
     - Remove the claim "no sentence … takes the recommended option under `Checkpoints: pre-approved`".
  9. Put this evidence in the report, and return a CHARACTERIZATION report (the current prose passes):
     - The verify command passes five times in a row.
     - These pass: `-k test_pre_approved`, `-k test_develop_feature_asks_the_user_for_open_decisions`, `-k test_contract_tests_define_each_module_name_once`, `-k test_every_contract_test_names_its_requirements`.
     - ruff format and ruff check are clean.
     - The new functions, run on `git show HEAD:` copies of SKILL.md, CHANGELOG.md and templates/tasks.md in a temp directory, return the 12 RED gaps.
     - The probe lists in the two prototypes give the results described above.
- implementer: no dispatch. The skill, the template and the CHANGELOG pass the new rules unchanged (the prototype reports nothing on the current tree), so do not edit them. If the new test reports a gap on the current prose, send it back to the test-writer.
- Orchestrator: if the next review calls one of the documented limits a Critical, send it to a `finding-verifier` before starting another fix round.

Plan change: none. The Test field at tasks.md:617 is met as written, and requirements and design stay as they are.

Prototype files (scratch only; the repo is untouched and `git status` still shows the same 4 files):
- `<session scratchpad>\t77-rethink\proto\proto.py` — the guard, the RED run on the base documents, and the CR1–CR3 probes.
- `<session scratchpad>\t77-rethink\proto\probe2.py` — the guard's known limits and the tighter "apart" pattern.

Run each with `python -I <script> <worktree>`.
