# Adjustments

How develop-feature makes an adjustment: a small change the user asks for on work the feature
already committed. [SKILL.md](../SKILL.md#adjustments) says what counts as one, who makes it and
when; this file is the procedure. Its prompts are in [dispatch-prompts.md](dispatch-prompts.md).

## Contents

- Steps
- When the diff is not what the request sounded like
- Where it is recorded

## Steps

1. **Clean tree.** Start between tasks, from a clean tree: finish and commit the task in progress
   first.
2. **Criterion first.** When the request changes a detail an acceptance criterion states (a text,
   a value, a limit), edit that line of `requirements.md` yourself, before any dispatch, so the
   writers and the reviewers read the new criterion. Only you can: the plugin denies the feature's
   documents to subagents.
3. **Tests first.** Search the tests for what the request changes
   (`git grep -n -F '<old text or value>' -- <test folders>`). When a test asserts it, or the
   request changes what the code does for some input, dispatch `test-writer` (adjustment prompt)
   and run its tests yourself: each must fail because the code still does what it did. When it
   added, renamed or removed a test, update that task's `Test:` or `Tests:` line and its `Verify:`
   line in `tasks.md` now, before the implementer runs, so the tree its check passes on is the one
   you commit.
4. **The change.** Dispatch `implementer` (adjustment prompt). You write no code and no test
   yourself. The only files you edit directly are the feature's own documents and prose that
   nothing loads, runs or tests (a README, a changelog); a prompt, a skill, a template or any
   other file the product, a tool or a test reads goes to the writers.
5. **Verify.** Run five times in a row the tests the adjustment changed or added, and once the
   verify command of each task it adjusts: the tasks whose tests or criteria describe what the
   request changes, normally one. A command that selects no test proves nothing. The check at the
   gate runs every other test.
6. **Reviews.** Read the adjustment's diff (`git status --porcelain`, `git diff --stat HEAD` and
   its hunks, with its size from `git diff --shortstat HEAD -- . ":(exclude)specs/<NNN-slug>"`
   plus the untracked files) and dispatch, at the same time and with the adjustment-review
   prompt, the reviews that [Reviews after a change](../SKILL.md#reviews-after-a-change) names for
   it: often one, sometimes none. Their findings go to one fix round (mark the tree before it, as
   inside a task), then to the reviews that table names for that round.
7. **Gate and commit.** Gate as step 6 of the task loop does, then commit the adjustment alone
   with the `committing-changes` skill in its develop-feature mode, which writes its note in the
   same command: the tasks it adjusts, the reviews that ran and why not the others, and what the
   user asked. Change no file between the gate and the commit: the commit gate reuses a green
   check only for the exact tree it ran on. With `Publish: live`, push it; in a local build whose
   pull requests are already open, ask before pushing.
8. **Tell the user**, in two or three lines: what changed, which reviews ran, which ones the
   change did not need and why and, when you edited a criterion, its ID with the old and the new
   wording.

## When the diff is not what the request sounded like

- It shows a plan change: it adds or removes a criterion or a behavior no criterion covers,
  changes the design, or touches a file a `high` task lists or changed (for each code or test
  file the diff changed, `git log --notes=refs/notes/konundrm --format=%N <base>..HEAD -- <file>`
  prints the `Task:` line of every task whose commit changed it, also when the plan did not list
  that file). Do not commit it: set it aside with
  `git stash push --include-untracked -m "<NNN-slug> adjustment set aside: <the request in a few words>"`,
  tell the user that message and propose the plan change. To recover it, the user runs
  `git stash list --grep="<that message>" --format=%H`, which prints its commit SHA, and then
  `git stash apply <sha>` with that SHA.
- It only grew past about 50 changed lines of code and tests: keep it, run both reviews on it and
  tell the user it grew.
- A review still fails after the fix round: it was not an adjustment. Set it aside the same way
  and propose a plan change. An adjustment never goes to Rethink.

## Where it is recorded

The note of its commit is the record the flow reads, and the next summary that is written lists
the adjustment from that note. So do not edit a summary in the adjustment's own commit: the tree
you commit stays the one the implementer's check passed, and the gate reuses that result.

- During a slice: the Slice checkpoint lists it in that slice's summary.
- At a slice's pause, after its summary commit: it belongs to the next slice, whose summary lists
  it and whose pull request holds it. With `Publish: live`, cut and push the next slice's branch
  first, as Live publishing says, and commit it there.
- After the last slice's summary: Phase 4 lists it in the feature's `summary.md`.
- Once the feature is done: when the user has no more changes, add the entries of that sitting's
  adjustments to `summary.md` in one `docs` commit. If code changed after the final verification,
  repeat the steps of it that exercise what changed, or say in the entry that it was not repeated.
