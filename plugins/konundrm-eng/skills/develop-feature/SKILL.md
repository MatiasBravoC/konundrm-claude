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
| Red | `konundrm-eng:test-writer` subagent | you see the new test fail for the right reason (or pass on arrival, see step 1) |
| Green and refactor | `konundrm-eng:implementer` subagent | you see the task's test pass five runs in a row |
| Spec review | `konundrm-eng:spec-reviewer` subagent | verdict PASS |
| Code review | `konundrm-eng:code-reviewer` subagent | no Critical finding |
| Security review (high risk) | `konundrm-eng:security-reviewer` subagent | no Critical finding |
| Finding check | `konundrm-eng:finding-verifier` subagent | each Critical finding confirmed or refuted |
| Rethink (stuck task) | `konundrm-eng:rethinker` subagent | a RETHINK report saying what to do differently, or a plan change the user approves |
| Process review (each slice, then the feature) | `konundrm-eng:process-reviewer` subagent | its improvement notes saved with `improvement_notes.py` |
| Risk verification | you | properties, mutation and evidence as the task's risk requires |
| Gate and commit | you, with the `committing-changes` skill | the check command passes; one atomic commit |
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
so the extra effort goes only to work that has shown it needs it.

## Phase 0: Prepare

1. If `$ARGUMENTS` points to an existing `specs/<NNN-slug>/`, **resume**, in this order:
   - Read its files, skip stages whose documents are `Approved` and take the base commit from the
     `tasks.md` header.
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
     plan's base (`<base>..HEAD`), so an earlier feature's `Task:` commits never count. A task with
     its commit counts as built whatever its box says: an unchecked box does not make it pending,
     and a checked box with no commit does not make it built.
   - In the main session, look for an unfinished wave before going on: run `git worktree list` and
     `git branch --list 'wave/*'`. A worktree or branch named `wave/<NNN-slug>-p<k>` means its wave
     is unfinished, so finish that wave first, before any other task. Finish or abort a cherry-pick
     in progress, then judge what is integrated by each task's `Task:` commit (`status` for
     commits here), never by boxes, SHAs or branch names: a task committed here is
     integrated; one committed only on its partition's branch is still to integrate; one with no
     commit is still being built. When the wave's first partition is built and every other
     partition is integrated (each of its tasks has its commit here and its `evidence/P<k>.md` is
     here), nothing is left to build or pick, but nothing committed shows whether the check and
     the wave-wide review ran: at [Parallel partitions](#parallel-partitions), run the check
     command (routing a red check as step 6 does), then step 7 again, then step 8.
     Otherwise resume at step 3, and for each partition whose branch still lacks its report commit
     (`docs(<scope>): report partition P<k>`) and whose folder has no session open, start that
     session again there with the same `--partition P<k>` prompt (it resumes from its own
     commits). Never build another partition's tasks here.
   - When every task of a slice has its commit here but the slice's commit
     `docs(<scope>): summarize slice S<k>` is missing (the session stopped between the two), run
     the [Slice checkpoint](#slice-checkpoint) for that slice before the next slice's first task.
     Look for that commit with `git log -E --grep '^docs\(.+\): summarize slice S<k>$'` (anchored,
     so S1 never matches S10).
   - Continue at the task `status` names as next (in a parallel wave, the main session still builds
     only the wave's first partition). When it prints `next: none` (every task is built and every
     slice has its summary commit), go on to [Phase 4](#phase-4-finish).
2. Confirm the repository root and that the tree is clean. If unrelated changes are pending, ask
   the user to commit or stash them first; never mix them into feature commits.
3. Get the check command from the plugin, the same one its hooks run: the session context names
   it, or `sh "${CLAUDE_PLUGIN_ROOT}/hooks/run.sh" quality_check.py` prints it. Run it once as a
   baseline. If it is red before you start, stop and report: never build on red. If none exists,
   suggest `/konundrm-eng:setup-project` and ask whether to continue without gates.

**Partition session.** When `$ARGUMENTS` also says `--partition P<k>`, the feature's main session
started you in a Git worktree of your own to build one partition of a parallel wave
([Parallel partitions](#parallel-partitions)). Resume as in
step 1, then run Phase 3 for only that partition's tasks, in the order the `### Partitions`
table of the slice that holds `P<k>` lists them, and skip Phases 1, 2 and 4. Never edit `design.md`, `requirements.md` or another
partition's tasks, and check no box nor write any Rounds line in `tasks.md`: commit each of your
tasks as step 7 does, with `task_ledger.py message`. After the last task's commit, write a short
report as `specs/<NNN-slug>/evidence/P<k>.md` with what the main session needs to integrate you:
your branch, each task's commit SHA and subject, each task's rounds (from its commit) and the
Suggestions not applied. Commit it as
`docs(<scope>): report partition P<k>` with the last task's `Task:` line, then stop with that
report. Never push nor open pull requests: the main session integrates your branch. A partition
session never runs the [Slice checkpoint](#slice-checkpoint): the main session runs it once the
slice's last wave is integrated. A PLAN CHANGE from a rethink is not yours to propose or write:
stop with a `BLOCKED:` line for the main session that quotes its `Plan change:`. A fresh worktree may lack installed dependencies or local
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

Keep a tally per task: spec review rounds, code review rounds and escalations. It goes into the
task's commit message as `--rounds` at step 7, never into `tasks.md`. Also count the task's failed
reviews in its todo item (a spec review FAIL, or a code or security review with a Critical finding
no `finding-verifier` refuted), for example `T12 · failed: spec 1, code 2`: the fifth, or a third
failure of the same review, sends the task to [Rethink](#rethink) instead of another fix round.

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
   `implementer` directly and run the task's verify command once. The implementer runs the check
   at the end of its dispatch, and the gate runs it only when `status` does not show it green.
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
   - Send every finding left (the spec review's FAIL findings and the CONFIRMED or UNCERTAIN
     Critical findings of the code and security reviews) to one fix round, one writer at a time:
     a missing or wrong test, or a test that does not test what it claims → `test-writer`;
     everything else → `implementer` (fix-round prompt).
   - After the fix round, rerun the verify command yourself (five times in a row as in step 2, once
     for a `chore` task) and run the reviews of step 3 again, at once, with the re-review prompt:
     each review gets its previous findings (or "none"), the fix round's reports (each file changed
     and what changed in it) and the new verification output, and rereads those files instead of
     reviewing the whole task.
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
   - Any change made in this step (a test added, a fix or an exclusion mark) goes through the
     reviews again as after step 4's fix round (re-review prompt), so nothing lands unreviewed.
6. **Gate.** Run
   `sh "${CLAUDE_PLUGIN_ROOT}/hooks/run.sh" task_ledger.py status specs/<NNN-slug>/tasks.md` to
   learn whether the check is green for the current tree (a passing check recorded on exactly
   these files, whoever ran it). When `status` shows `check: green for this tree`, go to step 7
   without running the check again. Otherwise run the check command: it must pass, and running
   it on the exact files you will commit lets the commit hook reuse its green result. If the
   check fails, send the failure to the `implementer` (fix-round prompt), rerun the verify command
   and the reviews as after step 4's fix round, take the task through step 5 (verify by risk)
   again, then repeat this step.
7. **Commit.** Run the `committing-changes` skill in its develop-feature mode: the task's code,
   tests and evidence land as **one** commit, without rerunning the check and without asking
   about pushing yet. A task is committed only when its spec review and code review, and on
   `high` tasks its security review, passed on its final code. Commit it in one call, with the
   task's tally as `--rounds` and the session's co-author trailer as `--trailer`, quoted as
   `committing-changes` says:
   `msg=$(sh "${CLAUDE_PLUGIN_ROOT}/hooks/run.sh" task_ledger.py message specs/<NNN-slug>/tasks.md T<n> --subject "<type>(<scope>): <summary>" --rounds "spec <n> · code <n> · escalations <n>") && git add -A && git commit -F "$msg" --trailer "Co-Authored-By: …"`.
   `message` writes the subject, the optional `--body` and the trailers
   `Task: T<n> · Covers: R…` and `Rounds: …` to a file under the Git directory and prints its
   path; it commits nothing. The commit is a plain `git commit`, so it goes through the commit
   gate like any other commit: the hook reuses the green result step 6 left for this tree and
   denies the commit on red. This commit checks no box and writes no Rounds line in `tasks.md`:
   the task's rounds live in its commit message.

When the task was the slice's last task and the slice is built here without a parallel wave, run
the [Slice checkpoint](#slice-checkpoint) before the next slice's first task; a parallel slice runs
it from step 9 of [Parallel partitions](#parallel-partitions).

**Open decisions.** When a `test-writer` or `implementer` returns `Status: DECISION` (the task
admits two or more reasonable approaches the plan left open), pause that task: dispatch no other
subagent for it and run no fix round for it. Show the user the subagent's `Decision:` report, the
options with their advantages, disadvantages and the recommendation, and wait for the user's
choice. Start that message with a line `RED: T<n> waits for a decision`, since the task's test may
already be red and the stop gate ends a turn on a red tree only with a `RED:` or `BLOCKED:` line.

Record the choice in `tasks.md` by adding the task's `- Decision:` field (or rewriting it, when
the task already has one) as `- Decision: <option> (user)`, and keep the options from the
subagent's `Decision:` report below it, so summaries cite the decision as recorded; that record
lands in the task's commit. Then send the task to a new subagent of the same role with the same
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
   (`git log -E --grep '^Task: T<n>( |$)' <branch>`) plus its report commit. A partition session
   that stops with `BLOCKED:` holds the wave: relay it to the user and send the answer to that
   session.
5. Integrate one partition at a time, in table order, and only between tasks: no subagent running
   in this checkout and the tree clean. The plugin's subagent audit attributes any file that
   changes during a subagent's run to that subagent. If this session has uncommitted work of its
   own (a task in progress), finish it first; never integrate on a dirty tree.
   - Pick the partition's commits: `git cherry-pick <fork-point>..<branch>`, where the fork point
     is `git merge-base HEAD <branch>`. The range ends at the branch's tip, so it includes the
     partition's report commit (`docs(<scope>): report partition P<k>`) and its
     `evidence/P<k>.md`. In `tasks.md`, a conflict keeps both sides' boxes and Rounds lines.
   - On a resumed wave, pick only what is not here yet. A partition whose tasks and
     `evidence/P<k>.md` are all here is integrated: skip it. Otherwise, since integration runs in
     table order, the partition's integrated commits are the start of its branch, so begin the
     range after them, `git cherry-pick <last>..<branch>`, where `<last>` is the branch's last task
     commit whose task already has its commit here (the fork point when none has). The report
     commit carries the last task's `Task:` line, so it counts as integrated only when
     `evidence/P<k>.md` is here. When a pick still stops on a commit that comes out empty because
     its task already has its commit here, `git cherry-pick --skip` it.
   - Any other conflict means the partitions were not as independent as planned. Run
     `git cherry-pick --abort`, report which partition and which files conflicted, and stop with a
     `BLOCKED:` line. Only after the user's go-ahead, redo the cherry-pick and hand each conflicted
     file, with both sides, to the `implementer` (the `test-writer` for a test), have
     `code-reviewer` review the resolution, stage the resolved files (`git add <files>`), then run
     `git cherry-pick --continue`. The resolution belongs to the commit being picked, not to a
     separate fix commit, and the rest of the partition's range is then picked as usual.
   - After a partition that changed dependencies or generated files, set the checkout up as
     `AGENTS.md` or the README says.
   - Run the check command after each partition. The history stays linear, one commit per task,
     so the pull request reads commit by commit.
6. If the check is red after a partition, route the failure as in Phase 3 step 4 (a test problem
   to the `test-writer`, everything else to the `implementer`'s fix round, with that partition's
   last task), have `code-reviewer` review the fix, run the check again, and commit the fix with
   `committing-changes`, carrying that task's `Task: T<n> · Covers: …` line and typed `feat` or
   `refactor`, never `fix` (measure-impact counts `fix` commits on task files as escaped defects).
   Then integrate the next partition.
7. After the last partition, dispatch `code-reviewer` once over `git diff <wave-base>..HEAD` for
   duplication or inconsistency between partitions built apart, and route its Critical findings
   as in step 6. A finding carries the `Task:` line of the task whose code it names; when it names
   several, the wave's last integrated task.
8. Close any session still open in a partition's folder, then remove its worktree with
   `git worktree remove <folder>`, never `--force`: if it refuses, show the user what is left and
   keep its branch, which Git does not delete while a worktree has it checked out. Delete its
   branch (`git branch -D wave/<NNN-slug>-p<k>`) only once every one of its tasks has its commit
   here and its report commit is integrated (`evidence/P<k>.md` is here): the report commit
   carries the last task's `Task:` line, so searching task lines alone cannot tell. A session
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
   evidence and the slice's commits.
2. Run `sh "${CLAUDE_PLUGIN_ROOT}/hooks/run.sh" task_ledger.py close-slice specs/<NNN-slug>/tasks.md S<k>`,
   which checks the box of each of the slice's tasks that has its commit and writes the rounds from
   that commit; it should print `not committed: none`, and a task it names is not built yet, so
   build it first. Commit the summary and that `tasks.md` change together with the
   `committing-changes` skill in its develop-feature mode, as
   `docs(<scope>): summarize slice S<k>` carrying the `Task:` line of the slice's last task, so the
   summary stays inside that slice's pull request.
3. Dispatch `konundrm-eng:process-reviewer` over the slice's flow record (its prompt is in
   [reference/dispatch-prompts.md](reference/dispatch-prompts.md)), then pass its report, the
   `IMPROVEMENT NOTES` block, on stdin to
   `sh "${CLAUDE_PLUGIN_ROOT}/hooks/run.sh" improvement_notes.py --project <project>
   --feature <NNN-slug> --scope "slice S<k>"`, where `<project>` is the repository's folder name.
   The script prints where the notes went. When it warns that the notes fell back to the feature
   folder (`specs/<NNN-slug>/improvement-notes.md`), tell the user, and commit that file as
   `docs(<scope>): keep slice S<k> improvement notes` carrying the `Task:` line of the slice's
   last task, so it stays in that slice's pull request. Never change the plugin's skills, agents
   or hooks on the strength of these notes: they are proposals for the plugin's author.
4. Stop and show the user the summary, with its reading order first: the files and line ranges to
   read, in order.
5. Ask two or three short questions about the slice's code, each answerable from the summary and
   the files it points to. When the user answers wrong or says they don't know, explain the right
   answer, citing the file and the lines that show it.
6. Wait for the user's go-ahead before starting the next slice. Never make the go-ahead depend on
   the answers.
7. When the user asks for changes at the pause, turn the changes into new tasks in `tasks.md` or
   into a plan change to `design.md`/`tasks.md`, and wait for the user to approve them before
   starting the next slice. Never make those changes on the spot, outside the task loop.
8. Once the pause is over (the summary committed and the improvement notes saved, and, with
   `Checkpoints: ask`, the user's go-ahead) and another slice or Phase 4 is left, continue the
   feature in a new session that resumes from the plan and the repository, not in this one. With
   `- **Sessions:** single` in the `tasks.md` header, build the next slice, or Phase 4, in this
   session instead. When the user asks at the pause to finish the feature in this session, set that
   header line to `- **Sessions:** single` and commit it alone as
   `docs(<scope>): build <NNN-slug> in one session` carrying the `Task:` line of the slice's last
   task, before going on. First run `git status --porcelain`: if it lists uncommitted changes, stop
   with a `BLOCKED:` line that names those files, without opening the new session or giving its
   command. When the desktop app's session tools can open a session in an existing folder, open
   the new session in this folder with the prompt `/konundrm-eng:develop-feature specs/<NNN-slug>` and stop working
   on the feature in this session; without such tools, or when the app refuses to open it, end
   with the exact command that resumes it in a new session:
   `claude "/konundrm-eng:develop-feature specs/<NNN-slug>"`.

With `Checkpoints: pre-approved` in the `tasks.md` header, still write the summary, run `close-slice`,
commit both and save the improvement notes (steps 1 to 3), then go on to the next slice as step 8
says (in a new session, or here with `Sessions: single`) without stopping, asking questions or
waiting. From a terminal, `run_slices.py` chains those sessions for a `Checkpoints: pre-approved`
plan, headless and one per slice, and its last line says how it ended:
`sh "${CLAUDE_PLUGIN_ROOT}/hooks/run.sh" run_slices.py specs/<NNN-slug>`.

## Phase 4: Finish

1. Run the check command on the whole project.
2. Dispatch `spec-reviewer`, with `model: opus` and `effort: high`, once more over the full
   feature diff (`git diff <base>..HEAD`) against every acceptance criterion, to catch gaps
   between tasks. On FAIL, propose one new task per gap (a plan change, so ask the user), then
   run the approved tasks through Phase 3.
3. Perform the final verification from `requirements.md` against the real application. Run it
   when it can be automated and save the evidence in `specs/<NNN-slug>/evidence/final.md`;
   otherwise give the user the exact steps.
4. Write the feature summary from `templates/feature-summary.md` to `specs/<NNN-slug>/summary.md`,
   filling every section from the three documents, `summaries/`, `evidence/` and the feature's
   commits. It goes into the final commit of step 7, which lands before any slice branch is cut
   or pushed. A stacked slice whose branch ends at an earlier commit reaches the summary through
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
   `docs(<scope>)` commit.
8. Report: commits made, a table mapping each requirement ID to its test(s) and evidence, the
   risk level of each task, Suggestions not applied, refuted findings, each rethink (its evidence
   file and the message of any stash it left), and anything escalated.
   When any task was `high`, tell the user to read that diff before pushing. **Ask before
   pushing** or opening pull requests. On a yes, offer two deliveries: one stacked pull request
   per slice (the default) or a single pull request with every slice. When any task is high risk,
   warn that with a single pull request `risk:high` will cover the whole feature. Then run the
   `opening-pull-requests` skill with the choice: each pull request carries its traceability
   table, and `risk:high` on the slices that hold a high-risk task so CI repeats mutation testing
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
