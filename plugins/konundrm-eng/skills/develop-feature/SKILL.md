---
name: develop-feature
description: Runs a feature from idea to reviewed pull requests with a fixed, gated workflow. Writes and approves the spec, writes and approves the plan (tasks grouped into pull-request-sized slices), then for each task dispatches fresh subagents (test-writer for red, implementer for green and refactor, spec-reviewer, code-reviewer, a security-reviewer on high-risk tasks, and a finding-verifier that tries to refute Critical findings), rejects flaky tests, scales verification to each task's risk (property tests, mutation testing, end-to-end evidence), verifies every claim by running commands, lands one atomic commit per task and, with the user's yes, opens one pull request per slice. Invoke explicitly with /konundrm-eng:develop-feature <idea>, or pass an existing specs/<NNN-slug> folder to resume.
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
| Risk verification | you | properties, mutation and evidence as the task's risk requires |
| Gate and commit | you, with the `committing-changes` skill | the check command passes; one atomic commit |
| Pull requests | you, with the `opening-pull-requests` skill | the user approves the push; one pull request per slice |

Dispatch prompts for every subagent: [reference/dispatch-prompts.md](reference/dispatch-prompts.md).

## Phase 0: Prepare

1. If `$ARGUMENTS` points to an existing `specs/<NNN-slug>/`, **resume**: read its files, skip
   stages whose documents are `Approved`, take the base commit from the `tasks.md` header, and
   continue at the first task without a commit. A checked box only counts when
   `git log --grep "Task: T<n>"` finds its commit; uncheck any box that has none.
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
the gates and the audit work per working tree.

Keep a tally per task: spec review rounds, code review rounds and escalations. It goes into
`tasks.md` at the gate.

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

## Phase 4: Finish

1. Run the check command on the whole project.
2. Dispatch `spec-reviewer` once more over the full feature diff (`git diff <base>..HEAD`) against
   every acceptance criterion, to catch gaps between tasks. On FAIL, propose one new task per gap
   (a plan change, so ask the user), then run the approved tasks through Phase 3.
3. Perform the final verification from `requirements.md` against the real application. Run it
   when it can be automated and save the evidence in `specs/<NNN-slug>/evidence/final.md`;
   otherwise give the user the exact steps.
4. If the feature changed a fact the project's `AGENTS.md` or `CLAUDE.md` states (a command, a
   layer, an ownership rule), update that line in the same final commit, so the next session does
   not read stale instructions.
5. Set the three documents to `Status: Done` in a final `docs(<scope>)` commit.
6. Report: commits made, a table mapping each requirement ID to its test(s) and evidence, the
   risk level of each task, Suggestions not applied, refuted findings, and anything escalated.
   When any task was `high`, tell the user to read that diff before pushing. **Ask before
   pushing** or opening pull requests. On a yes, run the `opening-pull-requests` skill: one
   pull request per slice, stacked in order, each with its traceability table, and `risk:high` on
   the slices that hold a high-risk task so CI repeats mutation testing on them.

To see whether the workflow is paying off across features, run `/konundrm-eng:measure-impact`.

## Escalation: stop and ask the user when

- a task fails the same review three times;
- the plan turns out to be wrong (a task cannot be done as written, or the design must change):
  propose the edit to `design.md`/`tasks.md` and wait;
- a subagent returns `BLOCKED` for a reason no other role can resolve. A `BLOCKED` that only
  says a test is wrong is not an escalation: route it to a new `test-writer` and continue;
- the baseline or the final check is red for reasons outside the feature.

Start that message with a line `BLOCKED: <one-line reason>`. The plugin's stop gate lets the turn
end on a red tree only when the message carries a `BLOCKED:` or `RED:` line.
