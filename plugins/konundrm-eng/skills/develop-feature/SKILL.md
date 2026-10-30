---
name: develop-feature
description: Runs a feature from idea to reviewed pull requests with a fixed, gated workflow. Writes and approves the spec, writes and approves the plan (tasks grouped into pull-request-sized slices), then for each task dispatches fresh subagents (test-writer for red, implementer for green and refactor, spec-reviewer, code-reviewer, a security-reviewer on high-risk tasks, and a finding-verifier that tries to refute Critical findings), rejects flaky tests, sends a task stuck in review to a rethinker that finds what to do differently, scales verification to each task's risk (property tests, mutation testing, end-to-end evidence), verifies every claim by running commands, lands one atomic commit per task and, with the user's yes, opens one pull request per slice. Invoke explicitly with /konundrm-eng:develop-feature <idea>, or pass an existing specs/<NNN-slug> folder to resume.
disable-model-invocation: true
argument-hint: "<feature idea | specs/NNN-slug>"
---

# Develop Feature

You are the **orchestrator**. You never write tests or production code in this workflow: you
dispatch subagents with clean context, verify what they claim by running commands yourself, and
advance only when each gate passes. Pass paths and task text to subagents, not file dumps, to keep
your own context lean.

Request: $ARGUMENTS

## Roles

| Stage | Who | Gate to advance |
| --- | --- | --- |
| Spec | you, with the `writing-specs` skill | `requirements.md` approved by the user |
| Plan | you, with the `writing-plans` skill | `design.md` and `tasks.md` approved by the user |
| Red | `konundrm-eng:test-writer` subagent | you see the new test fail for the right reason (or pass on arrival, see step 1) |
| Green and refactor | `konundrm-eng:implementer` subagent | you see the task's test pass five runs in a row |
| Spec review | `konundrm-eng:spec-reviewer` subagent | verdict PASS |
| Code review | `konundrm-eng:code-reviewer` subagent | no Critical finding |
| Security review (high risk) | `konundrm-eng:security-reviewer` subagent | no Critical finding |
| Finding check | `konundrm-eng:finding-verifier` subagent | each Critical finding confirmed or refuted |
| Rethink (stuck task) | `konundrm-eng:rethinker` subagent | a RETHINK report saying what to do differently, or a plan change the user approves |
| Risk verification | you | properties, mutation and evidence as the task's risk requires |
| Gate and commit | you, with the `committing-changes` skill | the check command passes; one atomic commit |
| Pull requests | you, with the `opening-pull-requests` skill | the user approves the push; one pull request per slice |

Dispatch prompts for every subagent: [reference/dispatch-prompts.md](reference/dispatch-prompts.md).
Model and effort for each dispatch: [Model and effort](#model-and-effort).

## Model and effort

Each subagent's frontmatter sets its default: Opus at `medium` for the test-writer and the
implementer, Sonnet at `high` for the per-task spec review, Opus at `high` for the code review and
the finding check, and Opus at `xhigh` for the security review. Omit the Agent tool's `model` and
`effort` parameters so those defaults apply, except in these cases, where you pass the values
listed (Claude Code sets `effort` only when told a level):

| Dispatch | `model` | `effort` |
| --- | --- | --- |
| Any fix round: `test-writer` or `implementer` sent back after a FAIL, a Critical finding, a red for the wrong reason, a flaky run or a red check | `opus` | `high` |
| Every `test-writer` and `implementer` dispatch for a task after its [rethink](#rethink) | `opus` | `high` |
| `test-writer`, `implementer` and `spec-reviewer` on a `high` task | `opus` | `high` |
| `spec-reviewer` over the whole feature (Phase 4) | `opus` | `high` |

First attempts run at `medium` and only failures go up to `high`: in Anthropic's Opus 5.5 coding
runs this solved slightly more tasks than running everything at `high`, for less.

## Phase 0: Prepare

1. If `$ARGUMENTS` points to an existing `specs/<NNN-slug>/`, **resume**: read its files, skip
   stages whose documents are `Approved`, take the base commit from the `tasks.md` header, and
   continue at the first task without a commit. A checked box only counts when
   `git log -E --grep '^Task: T<n>( |$)'` finds its commit (anchored, so T1 never matches T10);
   uncheck any box that has none.
2. Confirm the repository root and that the tree is clean. If unrelated changes are pending, ask
   the user to commit or stash them first; never mix them into feature commits.
3. Get the check command from the plugin, the same one its hooks run: the session context names
   it, or `sh "${CLAUDE_PLUGIN_ROOT}/hooks/run.sh" quality_check.py` prints it. Run it once as a
   baseline. If it is red before you start, stop and report: never build on red. If none exists,
   suggest `/konundrm-eng:setup-project` and ask whether to continue without gates.

## Phase 1: Spec

Run the `konundrm-eng:writing-specs` skill with the request. Do not continue until the user
explicitly approves `requirements.md`. Then, unless already on a feature branch, create
`feat/<NNN-slug>` from the current commit, and note that commit's SHA as the base.

## Phase 2: Plan

Run the `konundrm-eng:writing-plans` skill on the approved spec, with the base SHA in the
`tasks.md` header. Do not continue until the user explicitly approves `design.md` and `tasks.md`.
Then commit the three documents as `docs(<scope>): add spec and plan for <slug>`, so every
later commit contains only its task. From here on, work autonomously until the feature is done or
an escalation rule fires.

## Phase 3: Task loop

Track the tasks in your todo list. For each task in order, start **fresh subagents**; never reuse
one across tasks, and run konundrm-eng subagents **one at a time**: the plugin attributes file
changes to the subagent that was running. To build several features at once, run each in its own
Git worktree and session (`claude --worktree`, or a new worktree session in the desktop app):
the gates and the audit work per working tree. Pass `model` and `effort` only as
[Model and effort](#model-and-effort) lists; fix rounds always run on `opus` at `high`.

Keep a tally per task: spec review rounds, code review rounds and escalations. It goes into
`tasks.md` at the gate. Also count the task's failed reviews in its todo item (a spec review FAIL,
or a code or security review with a Critical finding no `finding-verifier` refuted), for example
`T12 · failed: spec 1, code 2`: the fifth, or a third failure of the same review, sends the task to
[Rethink](#rethink) instead of another fix round.

1. **Red** (`behavior` and `property` tasks). Dispatch `test-writer`. Then run the task's verify
   command yourself.
   - It fails for the reason in the RED report: continue to step 2.
   - It errors for another reason: send the report back to a new `test-writer`, at most twice,
     then escalate.
   - It passes and the test-writer returned a CHARACTERIZATION report (the behavior or invariant
     already holds, often because an earlier task built it): read the test. If it asserts what the
     task's criterion requires, keep it, skip step 2 and continue at step 3. If it does not, send
     it back as in the previous case.
2. **Green and refactor.** Dispatch `implementer` with the RED report. Then run the verify command
   yourself **five times in a row**: every run must pass (Standards → Tests). A run that fails
   while others pass means a flaky test: send the failing output to a new `test-writer`
   (flaky-test prompt), then run the five verifications again. For `chore` tasks, dispatch
   `implementer` directly and run the task's verify command once. The full check runs once, at
   the gate.
3. **Spec review.** Dispatch `spec-reviewer`. On FAIL, route each finding: missing or wrong test →
   `test-writer`; missing or wrong behavior → `implementer` (fix-round prompt). Then review again.
4. **Code review.** Dispatch `code-reviewer`. Record Suggestions for the final summary; do not
   loop on them. Critical findings:
   - On `high` tasks, and for any finding that looks doubtful, first dispatch one
     `finding-verifier` per finding, one after another. Drop REFUTED findings, keeping the
     verifier's evidence for the summary.
   - Route CONFIRMED and UNCERTAIN findings like spec-review findings: a test that does not test
     what it claims → `test-writer`; everything else → `implementer` (fix-round prompt). Then
     repeat steps 3–4.
   - On `high` tasks, once the code review has no Critical finding, dispatch `security-reviewer`
     with the task's `Security:` line and the `Threats` table. Its Critical findings go through a
     `finding-verifier` each and are routed the same way; then repeat from step 3.
5. **Verify by risk** (Standards → Verification by risk), using the task's `Invariants`,
   `Mutation` and `Evidence` fields from `tasks.md`:
   - `medium` and `high`: every listed invariant has a property test. For each missing one,
     dispatch `test-writer`. A property that fails has found a bug: send its counterexample to the
     `implementer` (fix-round prompt).
   - `high`: run the task's mutation command. Each surviving mutant goes to a new `test-writer`
     (surviving-mutant prompt), unless it is equivalent: then the `implementer` marks its line
     with the tool's exclusion and the reason (Standards → Gate integrity). Rerun the command to
     confirm. If the tool cannot run on this machine (mutmut does not run on native Windows),
     record that in the evidence: the `risk:high` CI run fails the pull request while any mutant
     in the changed code survives, so it is checked before merging either way. Then
     run the task's end-to-end check against the real application (HTTP calls, CLI runs, or the
     browser for UI) and save the commands and their output, or screenshots, in
     `specs/<NNN-slug>/evidence/T<n>.md`.
   - Any test added in this step goes through step 4 once more, so no test lands unreviewed.
6. **Gate.** In `tasks.md`, check the task's box and add `  - Rounds: spec <n> · code <n> ·
   escalations <n>` under it. Then run the check command. It must pass; if it does not, send the
   failure to the `implementer` (fix-round prompt) and repeat from step 3. Running the check
   last, on the exact files you will commit, lets the commit hook reuse this green result.
7. **Commit.** Run the `committing-changes` skill in its develop-feature mode: the task's code,
   tests, evidence and `tasks.md` update land as **one** commit with `Task: T<n> · Covers: R…` in
   the body, without rerunning the check and without asking about pushing yet.

Never accept "it passes" from a subagent without running the command yourself. The plugin also
audits each subagent when it finishes: files changed outside its role are sent back to it, then
restored automatically.

## Rethink

A task that keeps failing review needs a different approach, not one more fix. At its fifth failed
review, or when the same review fails a third time, stop the fix rounds and:

1. Dispatch `konundrm-eng:rethinker` (rethinker prompt) with the task, its criteria, every review
   finding so far, verbatim and in order, and the latest RED and GREEN reports. Its frontmatter
   runs it on Opus at `max`, so pass no `model` or `effort`.
2. Act on its RETHINK report. From then on, every `test-writer` and `implementer` dispatch for the
   task carries that role's line from the report's `Instructions:` and runs on `opus` at `high`,
   like any fix round ([Model and effort](#model-and-effort)).
   - `Verdict: PLAN CHANGE`: first propose its `Plan change:` edit to `tasks.md`, `design.md` or
     `requirements.md` and wait for the user (an escalation). Once the user approves it, handle the
     attempt as below and write the approved edit only after the attempt is stashed or kept, so the
     stash cannot take it.
   - `Current attempt: SET ASIDE`: stash the attempt, never discard it. The tree was clean when the
     task began, so the stash holds only this attempt:
     `git stash push --include-untracked -m "<NNN-slug> T<n> attempt set aside by rethink"`. When
     the `test-writer` line keeps the current test, end that command with
     `-- . ':(exclude)<test file>'` so the test stays. Check with `git status` that nothing else is
     left, then build the task again from step 1 of the task loop, or from step 2 when the test
     stays (rerun its verify command and pass that output as the RED report).
   - `Current attempt: KEEP`: when the `test-writer` line changes the test, send it to a new
     `test-writer` (test-writer prompt) first; then send the `implementer` line to the
     `implementer` (fix-round prompt) and review again from step 3.
3. Save the RETHINK report as `specs/<NNN-slug>/evidence/T<n>-rethink.md`, after any stash so the
   stash does not take it, adding the stash message when you set the attempt aside: the user finds
   the attempt by that message in `git stash list` and recovers it with `git stash apply`. Name a
   stash by its message, never by a position such as `stash@{0}`: positions shift with every new
   stash, and Git worktrees share one stash list. The file lands in the task's commit.
4. One rethink per task. If the task still fails two more reviews, stop and ask the user (an
   escalation), with the RETHINK report and, when you set the attempt aside, its stash message.

## Phase 4: Finish

1. Run the check command on the whole project.
2. Dispatch `spec-reviewer`, with `model: opus` and `effort: high`, once more over the full
   feature diff (`git diff <base>..HEAD`) against every acceptance criterion, to catch gaps
   between tasks. On FAIL, propose one new task per gap (a plan change, so ask the user), then
   run the approved tasks through Phase 3.
3. Perform the final verification from `requirements.md` against the real application. Run it
   when it can be automated and save the evidence in `specs/<NNN-slug>/evidence/final.md`;
   otherwise give the user the exact steps.
4. If the feature changed a fact the project's `AGENTS.md` or `CLAUDE.md` states (a command, a
   layer, an ownership rule), update that line in the same final commit, so the next session does
   not read stale instructions.
5. Set the three documents to `Status: Done` in a final `docs(<scope>)` commit.
6. Report: commits made, a table mapping each requirement ID to its test(s) and evidence, the
   risk level of each task, Suggestions not applied, refuted findings, each rethink (its evidence
   file and the message of any stash it left), and anything escalated.
   When any task was `high`, tell the user to read that diff before pushing. **Ask before
   pushing** or opening pull requests. On a yes, run the `opening-pull-requests` skill: one
   pull request per slice, stacked in order, each with its traceability table, and `risk:high` on
   the slices that hold a high-risk task so CI repeats mutation testing on them.

To see whether the workflow is paying off across features, run `/konundrm-eng:measure-impact`.

## Escalation: stop and ask the user when

- a task still fails two reviews after its rethink ([Rethink](#rethink));
- the plan turns out to be wrong (a task cannot be done as written, or the design must change):
  propose the edit to `design.md`/`tasks.md` and wait;
- a subagent returns `BLOCKED` for a reason no other role can resolve. A `BLOCKED` that only
  says a test is wrong is not an escalation: route it to a new `test-writer` and continue;
- the baseline or the final check is red for reasons outside the feature.

Start that message with a line `BLOCKED: <one-line reason>`. The plugin's stop gate lets the turn
end on a red tree only when the message carries a `BLOCKED:` or `RED:` line.
