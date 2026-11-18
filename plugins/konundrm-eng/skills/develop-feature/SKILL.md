---
name: develop-feature
description: Runs a feature from idea to reviewed pull requests with a fixed, gated workflow. Writes and approves the spec, writes and approves the plan (tasks grouped into pull-request-sized slices), then for each task dispatches fresh subagents (test-writer for red, implementer for green and refactor, spec-reviewer, code-reviewer, a security-reviewer on high-risk tasks, and a finding-verifier that tries to refute Critical findings), rejects flaky tests, sends a task stuck in review to a rethinker that finds what to do differently, scales verification to each task's risk (property tests, mutation testing, end-to-end evidence), verifies every claim by running commands, lands one atomic commit per task and, with the user's yes, opens stacked pull requests, one per slice (the default), or a single pull request with every slice. Invoke explicitly with /konundrm-eng:develop-feature <idea>, or pass an existing specs/<NNN-slug> folder to resume.
disable-model-invocation: true
argument-hint: "<feature idea | specs/NNN-slug [--partition P<n>]>"
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
| Red | `konundrm-eng:test-writer` subagent | you see each new test fail for the right reason (or pass on arrival, see step 1) |
| Green and refactor | `konundrm-eng:implementer` subagent | you see the task's tests pass five runs in a row |
| Spec review | `konundrm-eng:spec-reviewer` subagent | verdict PASS |
| Code review | `konundrm-eng:code-reviewer` subagent | no Critical finding |
| Security review (high risk) | `konundrm-eng:security-reviewer` subagent | no Critical finding |
| Finding check | `konundrm-eng:finding-verifier` subagent | each Critical finding confirmed or refuted |
| Rethink (stuck task) | `konundrm-eng:rethinker` subagent | a RETHINK report saying what to do differently, or a plan change the user approves |
| Process review (each slice, then the feature) | `konundrm-eng:process-reviewer` subagent | its improvement notes saved with `improvement_notes.py` |
| Risk verification | you | properties, mutation and evidence as the task's risk requires |
| Gate and commit | you, with the `committing-changes` skill | the check command passes; one atomic commit |
| Adjustment (a small change the user asks for on built work) | the writers, then only the reviews the change concerns | its verify command, those reviews and the check pass; one commit. Read [Adjustments](#adjustments) again before making one |
| Pull requests | you, with the `opening-pull-requests` skill | the user approves the push; stacked pull requests, one per slice (the default), or a single pull request with every slice |

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

First attempts on low- and medium-risk tasks run at `medium` and only failures go up to `high`,
so the extra effort goes only to work that has shown it needs it. An
[adjustment](#adjustments) is a first attempt too: its writers and reviews use their defaults,
and its fix round is a fix round.

## Phase 0: Prepare

1. If `$ARGUMENTS` points to an existing `specs/<NNN-slug>/`, **resume**, in this order:
   - First run `sh "${CLAUDE_PLUGIN_ROOT}/hooks/run.sh" task_ledger.py record`, before anything
     else: when the last session stopped between a task's commit and its `record`, it attaches that
     task's pending note to the commit. With nothing pending it exits 1 and changes nothing, so a
     refusal here is harmless.
   - Read the feature folder's files, skip stages whose documents are `Approved` and take the base commit from the
     `tasks.md` header.
   - When the three documents already read `Status: Done`, the feature is finished whatever
     `status` would print, and the rest of this step does not apply: no task is left to build,
     Phase 4 does not run again, and a change the user asks for goes through
     [Adjustments](#adjustments). `status` finds a built task by its commit's note, and notes do
     not travel in a clone nor survive a squash merge or a rebase, so after any of them it names
     as next a task that is built. A plan change there reopens the feature only while its pull
     requests are not merged (`gh pr list --head <branch> --state merged` lists none), no later
     feature has commits after it
     (`git log --oneline <base>..HEAD -- specs ':(exclude)specs/<NNN-slug>'` lists none of
     another feature) and `status` still lists every one of its tasks as committed: with the
     user's yes, set the three documents back to
     `Approved`, put its new tasks in a new slice after the last one, so the finished slices keep
     their summaries and pull requests, build them through Phase 3 and run Phase 4 again. Once
     it is merged, a later feature has commits after it or its notes are gone, propose the change
     as a new feature instead: `status` counts every task commit after this plan's base, so a
     later feature's `T13` would count as this feature's new `T13`, and without its notes the
     next session would build its built tasks again.
   - When the plan is `Approved`, some slice has a wave of two or more partitions and `tasks.md`
     has no `- **Parallel:**` line yet (the session stopped between the approval and recording the
     answer), ask the parallel question now, before Phase 3, and record the answer as
     [Phase 2](#phase-2-plan) describes, instead of assuming `no`.
   - A plan whose slices have no `### Partitions` table (written by an earlier plugin version) is
     built as before: its slices one after another, each slice's tasks in list order, in this
     session through the Phase 3 task loop. It gets no parallel question, no partition sessions and
     no worktrees. In a mixed plan, a slice without a `### Partitions` table counts as a single
     partition.
   - Run `sh "${CLAUDE_PLUGIN_ROOT}/hooks/run.sh" task_ledger.py status specs/<NNN-slug>/tasks.md`
     to learn which tasks have a commit and which is next. `status` counts only commits after the
     plan's base (`<base>..HEAD`), so an earlier feature's task commits never count. A task with
     its commit counts as built whatever its box says: an unchecked box does not make it pending,
     and a checked box with no commit does not make it built.
   - In the main session, look for an unfinished wave before going on: run `git worktree list` and
     `git branch --list 'wave/*'`. A worktree or branch named `wave/<NNN-slug>-p<k>` means its wave
     is unfinished, so finish that wave first, before any other task. Finish or abort a cherry-pick
     in progress, and copy the note of each task commit picked here without one, as
     [Parallel partitions](#parallel-partitions) step 5 says, then judge what is integrated by each task's `Task:` commit (`status` for
     commits here), never by boxes, SHAs or branch names: a task committed here is
     integrated; one committed only on its partition's branch is still to integrate; one with no
     commit is still being built. When the wave's first partition is built and every other
     partition is integrated (each of its tasks has its commit here and its `evidence/P<k>.md` is
     here), nothing is left to build or pick, but nothing committed shows whether the check and
     the wave-wide review ran: at [Parallel partitions](#parallel-partitions), run the check
     command (routing a red check as step 6 does), then step 7 again, then step 8.
     Otherwise resume at step 3, and for each partition whose branch still lacks its report commit
     (the one that adds `evidence/P<k>.md`) and whose folder has no session open, start that
     session again there with the same `--partition P<k>` prompt (it resumes from its own
     commits). Never build another partition's tasks here.
   - When every task of a slice has its commit here but no commit adds its summary
     `specs/<NNN-slug>/summaries/S<k>.md` (the session stopped between the two), run the
     [Slice checkpoint](#slice-checkpoint) for that slice before the next slice's first task.
     Look for that commit with `git log --diff-filter=A --format=%h -- specs/<NNN-slug>/summaries/S<k>.md`: no
     output means it is missing.
   - With `- **Publish:** live` in the `tasks.md` header, in the main session, stay on the slice
     branch as [Live publishing](#phase-3-task-loop) says, then first push the commits the remote
     does not have yet with `git push -u origin feat/<NNN-slug>-s<k>`, before the next task.
     A finished slice (its summary commit exists) that has no pull request yet
     (`gh pr list --head feat/<NNN-slug>-s<k> --state all` lists none) gets it first, before the
     next task: once its branch is pushed with `git push -u origin feat/<NNN-slug>-s<k>`, so the
     remote holds its summary, open its pull request as the [Slice checkpoint](#slice-checkpoint)
     says.
   - Continue at the task `status` names as next (in a parallel wave, the main session still builds
     only the wave's first partition). When it prints `next: none` (every task is built and every
     slice has its summary commit), go on to [Phase 4](#phase-4-finish).
2. Confirm the repository root and that the tree is clean. If unrelated changes are pending, ask
   the user to commit or stash them first; never mix them into feature commits.
3. Get the check command from the plugin, the same one its hooks run: the session context names
   it, or `sh "${CLAUDE_PLUGIN_ROOT}/hooks/run.sh" quality_check.py` prints it. Run it once as a
   baseline, exactly as given, alone in its own shell call, with no pipe, redirection or other
   command around it, because the hook records only such a check run. If it is red before you start, stop and report: never build on red. If none exists,
   suggest `/konundrm-eng:setup-project` and ask whether to continue without gates.

**Partition session.** When `$ARGUMENTS` also says `--partition P<k>`, the feature's main session
started you in a Git worktree of your own to build one partition of a parallel wave
([Parallel partitions](#parallel-partitions)). Resume as in
step 1, then run Phase 3 for only that partition's tasks, in the order the `### Partitions`
table of the slice that holds `P<k>` lists them, and skip Phases 1, 2 and 4. Never edit `design.md`, `requirements.md` or another
partition's tasks, and check no box nor write any Rounds line in `tasks.md`: commit each of your
tasks as step 7 does, with `task_ledger.py message`. After the last task's commit, write a short
report as `specs/<NNN-slug>/evidence/P<k>.md` with what the main session needs to integrate you:
your branch, each task's commit SHA and subject, each task's rounds (from its note) and the
Suggestions not applied. Commit it as `docs(<scope>): report <what its tasks built>`, then stop
with that report. Never push nor open pull requests: the main session integrates your branch. A partition
session never runs the [Slice checkpoint](#slice-checkpoint): the main session runs it once the
slice's last wave is integrated. A PLAN CHANGE from a rethink is not yours to propose or write:
stop with a `BLOCKED:` line for the main session that quotes its `Plan change:`. A change the
user asks for is not yours to make either ([Adjustments](#adjustments)): stop with a `BLOCKED:`
line that quotes the request. A fresh worktree may lack installed dependencies or local
configuration the check needs; set them up as the project's `AGENTS.md` or README says before the
baseline in step 3, and if the check still cannot run, stop with `BLOCKED:`.

## Phase 1: Spec

Run the `konundrm-eng:writing-specs` skill with the request. Do not continue until the user
explicitly approves `requirements.md`. Then, unless already on a feature branch, create
`feat/<NNN-slug>` from the current commit, and note that commit's SHA as the base.

## Phase 2: Plan

Run the `konundrm-eng:writing-plans` skill on the approved spec, with the base SHA in the
`tasks.md` header. Do not continue until the user explicitly approves `design.md` and `tasks.md`.

Then, only when some slice has a wave of two or more partitions, ask a separate question: whether
to build those partitions in parallel, one session per partition
([Parallel partitions](#parallel-partitions)). Offer parallel only when the
partitions' checks and end-to-end tests can run at the same time on this machine; they cannot when
they need a fixed port, a shared local database, a container name or another single resource.
When they cannot, say why and build in order; when unsure, say so and recommend building in order. Record
the answer in the `tasks.md` header line `- **Parallel:** yes` or `no` (`no` unless the user says
yes). A resumed session keeps that parallel answer and never asks again.

Record the `tasks.md` header line `- **Checkpoints:** pre-approved` when the user approved the
pauses between slices in advance, in the request or when approving the plan, and
`- **Checkpoints:** ask` otherwise; a `tasks.md` without that line reads as `ask`.

Record the `tasks.md` header line `- **Decisions:** pre-approved` when the user approved the open
decisions in advance, in the request or when approving the plan, and `- **Decisions:** ask`
otherwise; a `tasks.md` without that line reads as `ask`. The user approves the pauses and the
decisions separately: approving the pauses does not approve the decisions, nor the other way round.
Here, open decisions are the ones a `test-writer` or `implementer` returns as `Status: DECISION`
during the build ([Phase 3](#phase-3-task-loop)); choosing among the plan's own `- Decision:`
options at plan approval does not approve the build's open decisions in advance.

Record the `tasks.md` header line `- **Sessions:** single` when the user asked to build the whole
feature in one session, in the request or when approving the plan, and `- **Sessions:** per-slice`
otherwise; a `tasks.md` without that line reads as `per-slice`. When the user asks at a pause to
finish the feature in this session, set that line to `- **Sessions:** single` there
([Slice checkpoint](#slice-checkpoint), step 8).

Then find out whether the feature can be published on GitHub while it is built: run
`git remote get-url origin` and `gh repo view`. When both succeed, ask a separate question, apart
from the others: whether to publish the feature on GitHub while it is built, each slice's branch
and each commit pushed as soon as it exists. Record the `tasks.md` header line
`- **Publish:** live` only on an explicit yes or when the user asked for it in the request, and
`- **Publish:** local` otherwise. When either command fails, say in one line what is missing (an
`origin` remote, `gh` itself, a `gh auth login` session or access to the repository), do not offer
live publishing and record `- **Publish:** local`. A `tasks.md` without that `Publish:` line reads
as `local`: the feature is built locally and Phase 4 asks before any push. A resumed session keeps
the publish choice and never asks again.

Then commit the three documents as `docs(<scope>): add spec and plan for <slug>`, so every
later commit contains only its task. From here on, work autonomously until the feature is done or
an escalation rule fires.

## Phase 3: Task loop

Track the tasks in your todo list. For each task in order, start **fresh subagents**; never reuse
one across tasks. Run the writers (`test-writer`, `implementer`) **one at a time**, and never while
a reviewer runs: the plugin attributes file changes to the subagents that were running. Read-only
reviewers may run together. To build several features at once, create each one's
Git worktree outside the project folder, on a branch cut from the default branch, and start that
feature's session in it:
`git worktree add ../<repo>-worktrees/<NNN-slug> -b feat/<NNN-slug> <default-branch>`. Without
that start point Git cuts the branch from this checkout's HEAD, and the unfinished feature checked
out here would end up in the new feature's pull request. The gates and the audit work per working
tree, and a worktree inside the checkout shows up in this tree and breaks its gates. Pass `model`
and `effort` only as [Model and effort](#model-and-effort) lists; fix rounds always run on `opus`
at `high`.

When the `tasks.md` header says `**Parallel:** yes`, build each wave of two or more partitions as
[Parallel partitions](#parallel-partitions) says. Otherwise build each slice's tasks here, in list
order.

**Live publishing.** When the `tasks.md` header says `- **Publish:** live`, each slice gets its own
branch on the remote from its start. Before the slice's first task, cut the branch, switch to it
and push it: `git switch -c feat/<NNN-slug>-s<k> <start>`, then
`git push -u origin feat/<NNN-slug>-s<k>`. S1 starts from the commit that adds the spec and plan
(Phase 2's last commit). Slice k starts from the tip of the previous slice's branch, the commit
that adds its summary. When the slice branch already exists (a resumed session), switch to it with
`git switch feat/<NNN-slug>-s<k>` and stay there, without creating it again, then push it with
`git push -u origin feat/<NNN-slug>-s<k>`, which also sets its upstream. After each task's
commit (step 7), run `git push` before the next task. In live mode, push every other commit of the
flow the same way, as soon as it is made: the slice summary, each plan change, each adjustment,
each integration of a partition and the feature's final commit. Only the main session pushes: subagents and partition
sessions never push nor open pull requests. When a push is rejected or fails, or the remote is
gone, stop with a `BLOCKED:` line that quotes Git's error; the commit stays safe locally. Never
force a push, and never pull or fetch from the remote to make one go through. Without
`Publish: live`, nothing is pushed before Phase 4's question.

A change the user asks for during the build goes through [Adjustments](#adjustments), whether it
is about the task in progress or about work already committed: never start a task over for it.

Keep a tally per task: spec review rounds, code review rounds and escalations. It goes to the
task's commit step as `--rounds` at step 7, which keeps it in the task's note, never into
`tasks.md`. Also count the task's failed
reviews in its todo item (a spec review FAIL, or a code or security review with a Critical finding
no `finding-verifier` refuted), for example `T12 · failed: spec 1, code 2`: the fifth, or a third
failure of the same review, sends the task to [Rethink](#rethink) instead of another fix round.

1. **Red** (`behavior` and `property` tasks). Dispatch `test-writer`: one dispatch writes every
   test the task lists, the one on its `Test:` line or each one of its `Tests:` list, and returns
   a report per test. On a `medium` or `high` task the same dispatch also writes the property test
   of each invariant the task lists that no `property` task covers, so step 5 finds it written and
   no review repeats for it. Then run the task's verify command yourself, and the command its
   report gives for a test that command does not cover, and check each test against its report
   (from here on that command runs with the verify command every time this task runs it: the
   five runs of step 2, each rerun after a change and the output the reviews get):
   - It fails for the reason its RED report gives: that test is ready.
   - It passes and its report is a CHARACTERIZATION (the behavior or invariant already holds,
     often because an earlier task built it): read the test. If it asserts what its criterion
     requires, keep it: that test is ready.
   - Anything else (it errors for another reason, it passes with a RED report, or it does not
     assert its criterion): send that test's report back to a new `test-writer`, naming the tests
     to leave as they are, at most twice, then escalate.

   When every test fails for the reason its RED report gives, or is a kept CHARACTERIZATION,
   continue to step 2 with the reports; when every test of the task already passes this way, skip
   step 2's `implementer`, run its five verifications and continue at step 3. A `DECISION` or
   `BLOCKED` report is for the whole task: the test-writer wrote no test.
2. **Green and refactor.** Dispatch `implementer` with the RED reports: it makes the tests pass
   one at a time, in the task's order, and reports each one red before its code. Read a test it
   reports green before its code as step 1 reads a CHARACTERIZATION: keep it if it asserts its
   criterion, otherwise send it to a new `test-writer` as step 1 does. When it returns `BLOCKED`
   on one test, send that test back the same way. In both cases, once that test is red for the
   reason its report gives, dispatch a new `implementer` for it and tell it which tests already
   pass. Then run the verify command yourself **five times in a row**: every run must pass (Standards →
   Tests). A run that fails while others pass means a flaky test: send the failing output to a
   new `test-writer` (flaky-test prompt), then run the five verifications again. For `chore`
   tasks, dispatch `implementer` directly and run the task's verify command once. The implementer
   runs the check at the end of its dispatch, and the gate runs it only when `status` does not
   show it green.
3. **Reviews.** Dispatch `spec-reviewer` and `code-reviewer` at the same time, in one message,
   each with the output of your verification runs. On `high` tasks, dispatch `security-reviewer`
   in the same message too, with the task's `Security:` line and the `Threats` table. Dispatch no
   `test-writer` or `implementer` until every review of the batch is back. Whatever the outcome,
   record the reviews' Suggestions for the final summary; do not loop on them. When every review
   passes with no Critical finding left, continue to step 5; otherwise go to step 4.
4. **One fix round for the batch.**
   - On `high` tasks, and for any Critical finding that looks doubtful, first dispatch one
     `finding-verifier` per finding, one after another. Drop REFUTED findings, keeping the
     verifier's evidence for the summary. If no finding is left, skip the fix round and the
     re-review and continue to step 5.
   - Mark the task as it stands (`git add -A && git write-tree`, keeping the SHA it prints), so
     the round's own diff can be read afterwards, then send every finding left (the spec review's
     FAIL findings and the CONFIRMED or UNCERTAIN Critical findings of the code and security
     reviews) to one fix round, one writer at a time: a missing or wrong test, or a test that
     does not test what it claims → `test-writer` (test-writer prompt, naming the tests to leave
     as they are); everything else → `implementer` (fix-round prompt).
   - After the fix round, rerun the verify command yourself (five times in a row as in step 2, once
     for a `chore` task) and run again, at once and with the re-review prompt, only the reviews
     the round concerns, as [Reviews after a change](#reviews-after-a-change) names them from the
     round's diff: often one, and every review of step 3 on a `high` task. Each review gets its
     previous findings (or "none"), the reports of every fix round since it last ran (each file
     changed and what changed in it), what the round's diff shows and the new verification
     output, and rereads those files instead of reviewing the whole task.
5. **Verify by risk** (Standards → Verification by risk), using the task's `Invariants`,
   `Mutation` and `Evidence` fields from `tasks.md`:
   - `medium` and `high`: every listed invariant has a property test, in this task or in the
     `property` task that covers it. Step 1 wrote this task's; for one still missing, dispatch
     `test-writer`. A property that fails has found a bug: send its counterexample to the
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
   - Mark the task (`git add -A && git write-tree`) before the first change this step makes.
     When the step is done, any change it made (a test added, a fix or an exclusion mark, not
     the evidence file you save yourself) goes again, in one re-review, through the reviews it
     concerns ([Reviews after a change](#reviews-after-a-change)), as after step 4's fix round,
     so nothing lands without the reviews it needs.
6. **Gate.** Run
   `sh "${CLAUDE_PLUGIN_ROOT}/hooks/run.sh" task_ledger.py status specs/<NNN-slug>/tasks.md` to
   learn whether the check is green for the current tree (a passing check recorded on exactly
   these files, whoever ran it). When `status` shows `check: green for this tree`, go to step 7
   without running the check again. Otherwise run the check command exactly as given, alone in its own
   shell call, with no pipe, redirection or other command around it: it must pass, and running
   it on the exact files you will commit lets the commit hook reuse its green result. If the
   check fails, mark the task (`git add -A && git write-tree`), send the failure to the
   `implementer` (fix-round prompt) or, when the fix belongs in a test file, which the
   implementer cannot edit, to a new `test-writer` as in step 4 (test-writer prompt, naming the
   tests to leave as they are), rerun the verify command and the reviews that fix needs
   ([Reviews after a change](#reviews-after-a-change)), the code review always among them, as
   after step 4's fix round, take the task through step 5 (verify by risk) again, then repeat
   this step.
7. **Commit.** Run the `committing-changes` skill in its develop-feature mode: the task's code,
   tests and evidence land as **one** commit, without rerunning the check and without asking
   about pushing yet. A task is committed only when its spec review and code review, and on
   `high` tasks its security review, passed, and no change made after a review's pass is one
   that review must see again ([Reviews after a change](#reviews-after-a-change)). Commit it in
   one call, with the task's tally as `--rounds` and the session's co-author trailer as
   `--trailer`, quoted as `committing-changes` says:
   `msg=$(sh "${CLAUDE_PLUGIN_ROOT}/hooks/run.sh" task_ledger.py message specs/<NNN-slug>/tasks.md T<n> --subject "<type>(<scope>): <summary>" --rounds "spec <n> · code <n> · escalations <n>") && git add -A && git commit -F "$msg" --trailer "Co-Authored-By: …" && sh "${CLAUDE_PLUGIN_ROOT}/hooks/run.sh" task_ledger.py record`.
   `message` writes the subject and the optional `--body` to a file under the Git directory and
   prints its path, and leaves the task's `Task: T<n> · Covers: R…` and `Rounds: …` lines in a
   pending note; it commits nothing. `record` then attaches that note to the new commit under
   `refs/notes/konundrm`. The commit is a plain `git commit`, so it goes through the commit
   gate like any other commit: the hook reuses the green result step 6 left for this tree and
   denies the commit on red. This commit checks no box and writes no Rounds line in `tasks.md`:
   the task's rounds live in its note. Then append to that note each review the task did not
   repeat after a change, as [Reviews after a change](#reviews-after-a-change) says. With
   `Publish: live`, push it next, as [Live publishing](#phase-3-task-loop) says.

When the task was the slice's last task and the slice is built here without a parallel wave, run
the [Slice checkpoint](#slice-checkpoint) before the next slice's first task; a parallel slice runs
it from step 9 of [Parallel partitions](#parallel-partitions).

**Open decisions.** When a `test-writer` or `implementer` returns `Status: DECISION` (the task
admits two or more reasonable approaches the plan left open), pause that task: dispatch no other
subagent for it and run no fix round for it. Show the user the subagent's `Decision:` report, the
options with their advantages, disadvantages and the recommendation, and wait for the user's
choice. Start that message with a line `RED: T<n> waits for a decision`, since the task's test may
already be red and the stop gate ends a turn on a red tree only with a `RED:` or `BLOCKED:` line.

Record the choice in `tasks.md` by adding a `- Decision:` field to the task as
`- Decision: <option> (user)` (rewrite a field the task already has only when it asks the same
question: a task that lists several tests may leave more than one choice open, and each keeps its
own field), and keep the options from the subagent's `Decision:` report below it, so summaries
cite the decision as recorded; that record lands in the task's commit. Then send the task to a new subagent of the same role with the same
prompt, whose task block now carries the decision. A `Status: DECISION` is not an escalation nor a
`BLOCKED`: the design is not wrong, it left the choice open.

With `Decisions: pre-approved` in the `tasks.md` header, an open decision never pauses the
task, so no `RED:` line is needed: take the recommended option and record it as
`- Decision: <option> (recommended)`, with the options from the subagent's `Decision:` report
below it, so the slice summary cites the recommended choice. Then send the task to a new subagent
of the same role with the same prompt. `Checkpoints: pre-approved` alone does not take the
recommended option: with `Checkpoints: pre-approved` and `Decisions: ask`, an open decision still
pauses the task and waits for the user's choice, as above.

Never accept "it passes" from a subagent without running the command yourself. The plugin also
audits each subagent when it finishes: files changed outside its role are sent back to it, then
restored automatically.

## Reviews after a change

A review runs again only when the change could have invalidated what it checked. This rule
decides which reviews run again after a change made once a task's first reviews came back: a fix
round (step 4), a change from verifying by risk (step 5), the fix of a red check (step 6), a
change the user asks for on the task in progress and an [adjustment](#adjustments). A task's
first reviews are not under it: step 3 always dispatches them all.

Decide from the change's own diff, never from how small it sounded nor from the writer's report.
Inside a task the tree already holds the task's uncommitted work, so `git diff HEAD` shows the
whole task: right before the change's first writer runs, mark the tree with
`git add -A && git write-tree` and keep the SHA it prints in the task's todo item. Afterwards the
change alone is `git diff --stat <sha>`, its hunks, and the files `git status --porcelain` lists
as `??`. Compare with that tree, never with the index, which a writer that stages moves; without
the SHA, treat the whole task as changed and run both reviews. An adjustment starts from a clean
tree, so there `git diff HEAD` and those `??` files are the change.

| What the change did | Reviews that run again |
| --- | --- |
| It fixed a finding of a review | that review, whatever else applies |
| It added tests and changed nothing else: no line of a test that was there, no fixture, mock or snapshot, no production code | `spec-reviewer` |
| It changed a test that was there (edited what it sets up or asserts, removed it, added or changed a fixture, a mock or a snapshot) or what the code does for some input: a result, an error, a side effect, or a value the code decides with (a limit, a default, a pattern, a flag), whether or not a test asserts it yet | `spec-reviewer` and `code-reviewer`; the `spec-reviewer` alone when all it changed is the wording of a message shown to a person, in the code and in the tests that assert it, and its old text is left nowhere in code |
| It changed how the code is built without changing what it does (its structure, a name, a move, an extraction, an import), with at most that name or path replaced in the tests that use it, added a silencer or a skip, or touched what configures a gate: the check, the test runner, a linter, the type checker, coverage, mutation testing, the Git hooks or CI | `code-reviewer` |
| It changed only text that nothing reads: comments that are not tool directives, prose that nothing loads, runs or tests (a README, a changelog, the wording of a doc-comment), formatting made by the project's formatter, or the wording of a message shown to a person that no test asserts, no criterion states and no code matches | none |
| Anything, on a `high` task | every review of step 3, `security-reviewer` included |

A file the product, a tool or a test reads is code whatever its extension: a prompt, a skill, an
agent or a template in Markdown, a `requirements.txt`, a fixture. Before calling a message's
wording text that nothing reads, search for its old text (`git grep -n -F -e '<old text>'`, with
`MSYS_NO_PATHCONV=1` before `git` when the text holds a `/`, which Git Bash on Windows would
rewrite as a path): a hit in code or tests makes it code. A change can match several rows: run
every review they name, at the same time. The row with no review holds only when every changed line is plainly that kind of
text; when you cannot tell which row a change falls in, run both reviews, and when the user asks
for a review the table would skip, run it. The fix of a red check (step 6) always gets the code
review again, whatever it changed: that fix is where a gate gets bent. Whatever the rows say,
rerun the verify command first when code or tests changed, with the command of a test the
change added that it does not cover (step 1), and the gate still needs the check green before
the commit (step 6).

Each time this rule leaves out a review that step 3 ran, note it in the task's todo item with
what the change touched (`T12 · not repeated: code review, the round only added a test`). A todo
item ends with its session, so right after the task's commit and its `record` (step 7) append
each one to the task's note, which a partition's integration copies and a resumed session reads:
`git notes --ref=refs/notes/konundrm append -m "Not repeated: <review> after <the fix round | verifying by risk | the fix of a red check | a change the user asked for> (<what the change touched>)" HEAD`.
The slice summary lists them from those notes and the process-reviewer's flow record carries
them.

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
     stash cannot take it. A split of a consolidated task keeps the task's ID for its first part
     and gives each other part the next unused ID, one more than the plan's highest. List the new
     parts right after the first part, in its slice, add their IDs to its partition's row of the
     `### Partitions` table and to the `Depends on:` line of each later task that needs them, and
     update the header's totals. Never renumber a task: a built task's note names its ID. A split
     always sets the whole attempt aside, its tests included, whatever `Current attempt:` says:
     one attempt cannot be committed as two tasks, and each part's check would run the other
     parts' tests. Then build every part from step 1, the first part first, each with the
     report's `Instructions:` and on `opus` at `high`. A new part counts its own failed reviews
     and may have its own rethink.
   - `Current attempt: SET ASIDE`: stash the attempt, never discard it. The tree was clean when the
     task began, so the stash holds only this attempt:
     `git add -A && git stash push --include-untracked -m "<NNN-slug> T<n> attempt set aside by rethink"`
     (staging first, so a file a later round deleted stays deleted in the stash). When the
     `test-writer` line keeps the current test, end that command with
     `-- . ':(exclude)<test file>'` so the test stays. When you recorded a decision or a change
     the user asked for during this task (its `- Decision:` or `- Change:` line in `tasks.md`, a
     criterion edited in `requirements.md`, a line of `design.md` that stated the old detail or
     name), keep those files out of the stash the same way, with
     `':(exclude)specs/<NNN-slug>/tasks.md' ':(exclude)specs/<NNN-slug>/requirements.md' ':(exclude)specs/<NNN-slug>/design.md'`
     after `-- .`, so the task built again still carries them. Check with `git status` that
     nothing else is left, then build the task again from step 1 of the task loop, or from step 2
     when the test stays (rerun its verify command and pass that output as the RED report).
   - `Current attempt: KEEP`: when the `test-writer` line changes the test, send it to a new
     `test-writer` (test-writer prompt, naming the tests to leave as they are) first; then send
     the `implementer` line to the `implementer` (fix-round prompt) and review again from step 3,
     with every review: a rethink is not under [Reviews after a change](#reviews-after-a-change).
3. Save the RETHINK report as `specs/<NNN-slug>/evidence/T<n>-rethink.md`, after any stash so the
   stash does not take it, adding the stash message when you set the attempt aside. To recover the
   attempt, the user runs
   `git stash list --grep="<NNN-slug> T<n> attempt set aside by rethink" --format=%H`, which
   prints its commit SHA, and then `git stash apply <sha>` with that SHA. Look the attempt up by its
   message each time, never reuse a position such as `stash@{0}`: positions shift with every new
   stash, and Git worktrees share one stash list. A SHA does not shift if another session stashes
   between the two commands, and it has no braces, which PowerShell would read as a script block in
   an unquoted `stash@{<n>}`. The file lands in the task's commit.
4. One rethink per task. If the task still fails two more reviews, stop and ask the user (an
   escalation), with the RETHINK report and, when you set the attempt aside, its stash message.

## Parallel partitions

Partitions in the same wave of a slice depend on no other partition of the wave and share no file
with it (writing-plans checks both), so each can be built in its own session and Git worktree,
behind its own gates. When the `tasks.md` header says `Parallel: yes`, build each wave of a
slice's `### Partitions` table this way:

1. Start from a clean tree on the feature branch, with every earlier wave of this slice
   integrated. Its head is the wave base: note its SHA as `<wave-base>` in your todo list and in
   the message that starts the wave, so step 7 has it after HEAD moves. A resumed session
   recovers it as `git merge-base HEAD wave/<NNN-slug>-p<k>` while a branch of the wave exists.
2. For every partition of the wave except the first, create a worktree **outside this checkout**,
   on a new branch from the wave base:
   `git worktree add ../<repo>-worktrees/<NNN-slug>-p<k> -b wave/<NNN-slug>-p<k>`. A worktree
   inside the checkout (such as `.claude/worktrees/`) shows up in this tree and breaks its gates.
   Then start a partition session in each folder with the prompt
   `/konundrm-eng:develop-feature specs/<NNN-slug> --partition P<k>`: with the desktop app's
   session tools when they can open a session in an existing folder, otherwise by giving the user
   each folder and the command to run there,
   `claude "/konundrm-eng:develop-feature specs/<NNN-slug> --partition P<k>"`.
3. Build the wave's first partition here, on the feature branch, task by task (Phase 3).
4. Wait for the other partitions. A partition is done when its session says so (the desktop app
   tells you; otherwise the user does) and its branch has a commit for every one of its tasks
   (`git log --notes=refs/notes/konundrm -E --grep '^Task: T<n>( |$)' <branch>`) plus its report
   commit. A partition session
   that stops with `BLOCKED:` holds the wave: relay it to the user and send the answer to that
   session. When its line only quotes a change the user asked that session for, it needs no
   answer: note the change for after the wave ([Adjustments](#adjustments)) and tell that session
   to go on with its tasks.
5. Integrate one partition at a time, in table order, and only between tasks: no subagent running
   in this checkout and the tree clean. The plugin's subagent audit attributes any file that
   changes during a subagent's run to that subagent. If this session has uncommitted work of its
   own (a task in progress), finish it first; never integrate on a dirty tree.
   - Pick the partition's commits: `git cherry-pick <fork-point>..<branch>`, where the fork point
     is `git merge-base HEAD <branch>`. The range ends at the branch's tip, so it includes the
     partition's report commit and its `evidence/P<k>.md`. In `tasks.md`, a conflict keeps both
     sides' boxes and Rounds lines.
   - Cherry-picking leaves notes behind, so copy each picked task commit's note to its copy here:
     `git notes --ref=refs/notes/konundrm copy <old> <new>`. Pair `<old>` and `<new>` in order,
     never by subject (two commits may share one): the picked range's commits, oldest first
     (`git log --reverse --format=%H <fork-point>..<branch>`), against the commits the pick just
     made, in the same order (`git log --reverse --format=%H <start>..HEAD`, where `<start>` is
     `git rev-parse HEAD` taken before the pick), skipping a pick that came out empty. The report
     commit has no note to copy.
   - On a resumed wave, pick only what is not here yet. A partition whose tasks and
     `evidence/P<k>.md` are all here is integrated: skip it. Otherwise, since integration runs in
     table order, the partition's integrated commits are the start of its branch, so begin the
     range after them, `git cherry-pick <last>..<branch>`, where `<last>` is the branch's last task
     commit whose task already has its commit here (the fork point when none has). A session that
     stopped mid-pick may have left a picked commit without its note: copy it as above before
     judging what is here. A new session no longer has `<start>`, so pair such a commit with the
     branch commit that has the same author time and subject (`git log --format='%H %at %s'`; a
     pick keeps both, and two task commits never share both). The report commit counts as integrated only when `evidence/P<k>.md` is
     here. When a pick still stops on a commit that comes out empty because
     its task already has its commit here, `git cherry-pick --skip` it.
   - Any other conflict means the partitions were not as independent as planned. Run
     `git cherry-pick --abort`, report which partition and which files conflicted, and stop with a
     `BLOCKED:` line. Only after the user's go-ahead, redo the cherry-pick and hand each conflicted
     file, with both sides, to the `implementer` (the `test-writer` for a test), have
     `code-reviewer` review the resolution (every review of step 3 when the file is one a `high`
     task lists), stage the resolved files (`git add <files>`), then run
     `git cherry-pick --continue`. The resolution belongs to the commit being picked, not to a
     separate fix commit, and the rest of the partition's range is then picked as usual.
   - After a partition that changed dependencies or generated files, set the checkout up as
     `AGENTS.md` or the README says.
   - Run the check command after each partition. The history stays linear, one commit per task,
     so the pull request reads commit by commit.
   - With `Publish: live`, push the integrated commits with `git push` once the check passes on
     them (after step 6's fix when it was red). Never push a partition's branch: `wave/` branches
     stay local.
6. If the check is red after a partition, route the failure as in Phase 3 step 4 (a test problem
   to the `test-writer`, everything else to the `implementer`'s fix round, with that partition's
   last task), have `code-reviewer` review the fix (every review of step 3 when it touches a file
   a `high` task lists), run the check again, and commit the fix with
   `committing-changes`, typed `feat` or `refactor`, never `fix` (measure-impact counts `fix` commits on task files as escaped defects).
   Then integrate the next partition.
7. After the last partition, dispatch `code-reviewer` once over `git diff <wave-base>..HEAD` for
   duplication or inconsistency between partitions built apart, and route its Critical findings
   as in step 6.
8. Close any session still open in a partition's folder, then remove its worktree with
   `git worktree remove <folder>`, never `--force`: if it refuses, show the user what is left and
   keep its branch, which Git does not delete while a worktree has it checked out. Delete its
   branch (`git branch -D wave/<NNN-slug>-p<k>`) only once every one of its tasks has its commit
   here and its report commit is integrated (`evidence/P<k>.md` is here): the report commit has
   no note, so searching task notes alone cannot tell. A session
   that resumes with every partition of the wave integrated never goes back to step 3: it runs
   the check command (step 6 when red) and step 7 again, then picks up here
   ([Phase 0](#phase-0-prepare)).
9. Go on to the slice's next wave. After its last wave, continue with the end of the slice: the
   [Slice checkpoint](#slice-checkpoint).

## Slice checkpoint

Each slice ends in a pull request a person reads, so pause after each slice to show the user what
it holds. Run this once the slice's last task is committed, or, with partitions, once its last
wave is integrated:

1. Write the slice's summary from `templates/slice-summary.md` to
   `specs/<NNN-slug>/summaries/S<k>.md`, filling each of its sections from `tasks.md`, the
   evidence and the slice's commits. For `## Size`, measure from the commit that ended the
   previous slice (the `Base commit` for S1) to `HEAD`: the code and tests with
   `git diff --shortstat <from>...HEAD -- . ":(exclude)specs/<NNN-slug>"`, and the feature's
   documents apart with `git diff --shortstat <from>...HEAD -- specs/<NNN-slug>`. For
   `## Adjustments`, list the [adjustments](#adjustments) made since that commit with
   `git log --notes=refs/notes/konundrm --format='%h %s%n%N' --grep '^Adjusts:' <from>..HEAD`,
   each one from its note, with the criterion it updated read from its commit
   (`git show <sha> -- specs/<NNN-slug>/requirements.md`; `—` when that prints nothing), and add
   the changes the user asked for on a task in progress (the `- Change:` lines of the slice's
   tasks). Under the rounds table, list the reviews not repeated after a change, from the tasks'
   notes:
   `git log --notes=refs/notes/konundrm --format='%h %s%n%N' --grep '^Not repeated:' <from>..HEAD`.
2. Run `sh "${CLAUDE_PLUGIN_ROOT}/hooks/run.sh" task_ledger.py close-slice specs/<NNN-slug>/tasks.md S<k>`,
   which checks the box of each of the slice's tasks that has its commit and writes the rounds from
   that commit's note; it should print `not committed: none`, and a task it names is not built yet, so
   build it first. Commit the summary and that `tasks.md` change together with the
   `committing-changes` skill in its develop-feature mode, as
   `docs(<scope>): summarize <what it delivers>`. The commit that adds `summaries/S<k>.md` ends
   the slice's pull request, so the summary stays inside it. With `Publish: live`, push it with
   `git push` as soon as it is made, then open the slice's pull request as
   [Live pull request](#slice-checkpoint) below says.
3. Dispatch `konundrm-eng:process-reviewer` over the slice's flow record (its prompt is in
   [reference/dispatch-prompts.md](reference/dispatch-prompts.md)), then pass its report, the
   `IMPROVEMENT NOTES` block, on stdin to
   `sh "${CLAUDE_PLUGIN_ROOT}/hooks/run.sh" improvement_notes.py --project <project>
   --feature <NNN-slug> --scope "slice S<k>"`, where `<project>` is the repository's folder name.
   The script prints where the notes went. When it warns that the notes fell back to the feature
   folder (`specs/<NNN-slug>/improvement-notes.md`), tell the user, and commit that file as
   `docs(<scope>): keep the process improvement notes`. Like the one-session commit of step 8,
   it comes after the summary commit that ends the slice, so it lands in the next slice's pull
   request (in the last slice's, after the final slice). Never change the plugin's skills, agents
   or hooks on the strength of these notes: they are proposals for the plugin's author.
4. Stop and show the user the summary, with its reading order first: the files and line ranges to
   read, in order. When the slice's changed lines of code and tests go over the `Pull request
   budget` in `tasks.md`, warn the user first, with the number of lines and how much it went over
   (`612 changed lines, over the 500-line budget by 112 lines`). With `Publish: live`, also show
   the URLs of the feature's pull requests opened so far, in merge order (S1 first).
5. Ask two or three short questions about the slice's code, each answerable from the summary and
   the files it points to. When the user answers wrong or says they don't know, explain the right
   answer, citing the file and the lines that show it.
6. Wait for the user's go-ahead before starting the next slice. Never make the go-ahead depend on
   the answers.
7. When the user asks for changes at the pause, classify each one as [Adjustments](#adjustments)
   says. Make an adjustment right away, before the next slice starts. Turn the other changes into
   new tasks in `tasks.md`, written as `writing-plans` writes them, or into a plan change to
   `design.md`/`tasks.md`, and wait for the user to approve them before starting the next slice.
   Never write code or tests yourself, and make no change outside those two paths.
8. Once the pause is over (the summary committed and the improvement notes saved, and, with
   `Checkpoints: ask`, the user's go-ahead) and another slice or Phase 4 is left, continue the
   feature in a new session that resumes from the plan and the repository, not in this one. With
   `- **Sessions:** single` in the `tasks.md` header, build the next slice, or Phase 4, in this
   session instead. When the user asks at the pause to finish the feature in this session, set that
   header line to `- **Sessions:** single` and commit it alone as
   `docs(<scope>): build <NNN-slug> in one session`, before going on (it lands in the next
   slice's pull request, as step 3 says). First run `git status --porcelain`: if it lists uncommitted changes, stop
   with a `BLOCKED:` line that names those files, without opening the new session or giving its
   command. When the desktop app's session tools can open a session in an existing folder, open
   the new session in this folder with the prompt `/konundrm-eng:develop-feature specs/<NNN-slug>` and stop working
   on the feature in this session; without such tools, or when the app refuses to open it, end
   with the exact command that resumes it in a new session:
   `claude "/konundrm-eng:develop-feature specs/<NNN-slug>"`.

**Live pull request.** With `Publish: live`, once the summary commit is pushed (step 2), the main
session opens the slice's pull request without asking, since the plan's `Publish: live` is the
yes: `gh pr create --base <base> --head feat/<NNN-slug>-s<k> --title "<title> (k/N)" --body-file <file>`,
ready for review, never as a draft. Its base, title, description and label follow
`opening-pull-requests` (steps 3 to 5), so S1 goes against the default branch and each later slice
against the previous slice's branch. When `gh` cannot open the pull request, or fails, stop with a
`BLOCKED:` line that quotes its error; the branch stays pushed. `gh` runs here and on resume,
never per task.

With `Checkpoints: pre-approved` in the `tasks.md` header, still write the summary, run `close-slice`,
commit both and save the improvement notes (steps 1 to 3), then go on to the next slice as step 8
says (in a new session, or here with `Sessions: single`) without stopping, asking questions or
waiting. A slice over the budget still gets its warning: it stays in the summary's `## Size`
and in the session's closing message. With `Publish: live`, that closing message also lists the
URLs of the feature's pull requests opened so far, in merge order. From a terminal, `run_slices.py` chains those sessions for a `Checkpoints: pre-approved`
plan, headless and one per slice, and its last line says how it ended:
`sh "${CLAUDE_PLUGIN_ROOT}/hooks/run.sh" run_slices.py specs/<NNN-slug>`.

## Adjustments

A change the user asks for on work the feature already built is not always a new task. Whenever
the user asks for one (during the build, at a slice's pause, once the feature is done, or when a
session resumes a feature whose documents say `Status: Done`), classify it before touching
anything and tell the user which it is in one line:

- **A plan change** when it adds or removes an acceptance criterion, or a behavior no criterion
  covers; changes the design (the owner of a responsibility, a public interface, a dependency);
  touches a file a `high` task lists, or anything the High row of Standards → Verification by
  risk names; changes code in a file no task of the feature lists; or is expected to take more
  than about 50 changed lines of code and tests. Turn it into new tasks in `tasks.md`, written as
  `writing-plans` writes them (its consolidation included), or into a plan change to
  `design.md`/`tasks.md`, wait for the user to approve them and build them through the task loop.
  On a finished feature, first reopen it as [Phase 0](#phase-0-prepare) says, or propose a new
  feature when Phase 0 does not let it reopen. When you cannot tell which of the two a request
  is, it is a plan change.
- **An adjustment** otherwise: a small change inside the criteria the spec already has, to how a
  behavior is built, worded or presented, or to a detail one criterion states (a text, a value, a
  limit). A rename changes no design while nothing outside the files the feature's tasks list
  uses the old name, also when `design.md` gives that name. The request is its approval: make it
  now, as [reference/adjustments.md](reference/adjustments.md) says. In short: the criterion
  first, then the writers (its test first and red when it changes what the code does), the
  reviews that [Reviews after a change](#reviews-after-a-change) names for its diff, the gate,
  and a commit of its own with its note. A diff that turns out to be a plan change (it reached a
  file a `high` task lists or changed, or code in a file no task lists or changed) is never
  committed: the reference says how to set it aside.

When the request reports that built work does not do what an approved criterion says, it is a
defect, not a preference: make it as an adjustment is made, its test first and red for the
reported reason, but type its commit `fix` and add the `Escaped-gate:` line to its note, as
`fix-bug` does, so the impact report counts it.

A change the user asks for on the task in progress, before its commit, is classified the same
way, and on a `high` task it is always a plan change, because it touches a file a `high` task
lists. A plan change waits for the user while the task goes on, unless it changes what that task
itself builds: then stop the task and wait, as when the plan turns out to be wrong
([Escalation](#escalation-stop-and-ask-the-user-when)). Anything else joins that task, and
changes asked together join it in one round (a step these items name by number is a step of the
task loop):

1. Wait for the subagents that are running.
2. Edit the criterion in `requirements.md` first when the request changes a detail it states,
   and the plan's lines that still state the old detail or name
   ([reference/adjustments.md](reference/adjustments.md), step 2), then record the request under
   the task in `tasks.md` as `- Change: <the request, verbatim> (user)`, as an open decision is
   recorded, so every later dispatch and review reads it in the task block as one more
   criterion.
3. While the task's code is not written yet (step 2 has not run), nothing else is needed: steps
   1 and 2 go on with the task block as it now reads, and a test already written that the
   request changes goes back to a new `test-writer` first. Otherwise mark the tree and send the
   request to the task's writers with the adjustment prompts, the `test-writer` first when a
   test asserts or names what changes or the request changes what the code does: its test must
   fail before the `implementer` runs, unless the code already satisfies it
   ([reference/adjustments.md](reference/adjustments.md), step 3). When it added, renamed or
   removed a test, update the task's `Test:` or `Tests:` line and its `Verify:` line then.
4. Rerun the verify command. Step 3 then reviews the task with the request or, once step 3 has
   run, the reviews that [Reviews after a change](#reviews-after-a-change) names run again with
   the re-review prompt.
5. When the change's own diff touches a file a `high` task lists or changed
   ([reference/adjustments.md](reference/adjustments.md) has the command), stop before the
   task's commit and ask the user (an escalation): it reached high-risk work, which this path
   does not review as such.

It is not a failed review, and the slice summary lists it under its Adjustments as part of that
task.

Only the feature's main session makes adjustments, in the session that received the request and
before it hands the feature over (Slice checkpoint, step 8), at the next clean point between
tasks. A request the user leaves for later is made when the user said, as long as this session
is still the one building the feature then; when it would hand the feature over first, make it
at the next clean point instead, because a new session resumes from the plan and the
repository, not from this conversation. A session that has already handed the feature over
makes none either: it tells the user to ask in the session that is building it. A partition
session makes none: it stops with a `BLOCKED:` line that quotes the request for the main
session. While a parallel wave is being built or integrated, hold the adjustment until the
wave's worktrees are removed, and tell the user it is held: a session that resumes the wave
does not know it, so they ask again if this one ends first. Changes asked together are one
adjustment when they make one logical change within the limit; otherwise make them one after
another.

## Phase 4: Finish

1. Run the check command on the whole project.
2. Dispatch `spec-reviewer`, with `model: opus` and `effort: high`, once more over the full
   feature diff (`git diff <base>..HEAD`) against every acceptance criterion, to catch gaps
   between tasks. On FAIL, propose new tasks for the gaps, written as `writing-plans` writes them,
   its consolidation included (a plan change, so ask the user), then run the approved tasks
   through Phase 3.
3. Perform the final verification from `requirements.md` against the real application. Run it
   when it can be automated and save the evidence in `specs/<NNN-slug>/evidence/final.md`;
   otherwise give the user the exact steps.
4. Write the feature summary from `templates/feature-summary.md` to `specs/<NNN-slug>/summary.md`,
   filling every section from the three documents, `summaries/`, `evidence/` and the feature's
   commits. Its `## Adjustments` section lists the adjustments made after the final slice's
   summary, each one read from its note as the [Slice checkpoint](#slice-checkpoint) reads them.
   It goes into the final commit of step 7, the feature's closing commit. A stacked slice whose branch ends at an earlier commit reaches the summary through
   its pull request's link, pinned to the SHA of that final commit (`opening-pull-requests`).
5. Dispatch `konundrm-eng:process-reviewer` over the whole feature's flow record, then pass its
   report on stdin to `sh "${CLAUDE_PLUGIN_ROOT}/hooks/run.sh" improvement_notes.py --project
   <project> --feature <NNN-slug> --scope feature`, as in the [Slice checkpoint](#slice-checkpoint).
   When the script warns that the notes fell back to the feature folder, tell the user; that file
   goes into the final commit of step 7.
6. If the feature changed a fact the project's `AGENTS.md` or `CLAUDE.md` states (a command, a
   layer, an ownership rule), update that line in the same final commit, so the next session does
   not read stale instructions.
7. Set the three documents to `Status: Done` and commit them with `summary.md` in a final
   `docs(<scope>)` commit. With `Publish: live`, push it to the last slice's branch with
   `git push` as soon as it is made.
8. Report: commits made, a table mapping each requirement ID to its test(s) and evidence, the
   risk level of each task, Suggestions not applied, refuted findings, each rethink (its evidence
   file and the message of any stash it left), and anything escalated. A change the user asks
   for after this report goes through [Adjustments](#adjustments).
   With `Publish: live`, every slice already has its pull request, so list every pull request
   URL of the feature in merge order instead of asking whether to push. In local mode (without
   `Publish: live`), when any task was `high`, tell the user to read that diff before pushing,
   and **ask before pushing** or opening pull requests. On a yes, offer two deliveries: one stacked pull request
   per slice (the default) or a single pull request with every slice. When any task is high risk,
   warn that with a single pull request `risk:high` will cover the whole feature. Then run the
   `opening-pull-requests` skill with the choice: each pull request carries a plain-English
   description that says what to read first and how it was verified, and `risk:high` on the slices that hold a high-risk task so CI repeats mutation testing
   on them.

To see whether the workflow is paying off across features, run `/konundrm-eng:measure-impact`.

## Escalation: stop and ask the user when

- a task still fails two reviews after its rethink ([Rethink](#rethink));
- the plan turns out to be wrong (a task cannot be done as written, or the design must change):
  propose the edit to `design.md`/`tasks.md` and wait;
- a subagent returns `BLOCKED` for a reason no other role can resolve. A `BLOCKED` that only
  says a test is wrong is not an escalation: route it to a new `test-writer` and continue;
- integrating a partition conflicts outside the plan's boxes in `tasks.md`
  ([Parallel partitions](#parallel-partitions), step 5);
- the baseline or the final check is red for reasons outside the feature.

A partition session never waits for the user on a plan change, whether from a rethink or because
the plan turns out to be wrong: it stops with a `BLOCKED:` line for the main session, which relays
it to the user ([Phase 0](#phase-0-prepare)).

Start the escalation message with a line `BLOCKED: <one-line reason>`. The plugin's stop gate lets
the turn end on a red tree only when the message carries a `BLOCKED:` or `RED:` line.
