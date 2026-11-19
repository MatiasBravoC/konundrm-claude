# Adjustments

How develop-feature makes an adjustment: a small change the user asks for on work the feature
already committed. [SKILL.md](../SKILL.md#adjustments) says what counts as one, who makes it and
when; this file is the procedure. Its prompts are in [dispatch-prompts.md](dispatch-prompts.md).

## Contents

- Steps
- When the diff is not what the request sounded like
- Where it is recorded

## Steps

1. **Clean tree, right branch.** Start between tasks, from a clean tree: finish and commit the
   task in progress first. At a slice's pause with `Publish: live`, when another slice is left,
   cut and push the next slice's branch now, as [Where it is recorded](#where-it-is-recorded)
   says, so the commit of step 7 lands there and not in the pull request that is already open;
   after the last slice, stay on its branch, as the feature's final commit does. On a finished
   feature, check where you are: when the pull request of the feature's branch is merged
   (`gh pr list --head <branch> --state merged` lists it) or you are on the default branch, cut
   a new branch from the default branch that holds the feature, the remote's after a fetch
   (`git fetch origin <default-branch>`, then
   `git switch -c feat/<NNN-slug>-<short-slug> --no-track origin/<default-branch>`), because a
   merge made on GitHub is not in your local default branch, or the local one when there is no
   remote or the merge was made locally. Make the adjustment there and tell the user it needs a
   pull request of its own; with `Publish: live`, its first push is
   `git push -u origin feat/<NNN-slug>-<short-slug>`. When it is not merged and you are on
   another feature's branch, switch to the feature's own branch first: the default branch does
   not hold its code yet. With `Publish: live` the feature's branch is its last slice's,
   `feat/<NNN-slug>-s<N>`: a branch named `feat/<NNN-slug>` holds only the spec and plan. Never
   commit an adjustment on the default branch nor push it to a merged branch.
2. **Criterion first.** When the request changes a detail an acceptance criterion states (a text,
   a value, a limit), edit that line of `requirements.md` yourself, before any dispatch, so the
   writers and the reviewers read the new criterion. Only you can: the plugin denies the feature's
   documents to subagents. Then, and for a rename too, search the plan for the old detail
   (`git grep -n -F -e '<old text, value or name>' -- specs/<NNN-slug>/tasks.md specs/<NNN-slug>/design.md`,
   with `MSYS_NO_PATHCONV=1` before `git` as in step 3) and update each line that still states
   it, above all in tasks that are not built yet: their dispatches paste the task block as it is
   written.
3. **Tests first.** Search the tests for what the request changes
   (`git grep -n -F -e '<old text, value or name>' -- <test folders>`, with `MSYS_NO_PATHCONV=1`
   before `git` when the text holds a `/`, which Git Bash on Windows would rewrite as a path, so
   the search would find nothing). When a test asserts it or uses a name it changes (a rename the
   tests call), or the request changes what the code does for some input, dispatch `test-writer`
   (adjustment prompt) and run its tests yourself: each must fail because the code still does
   what it did, except one whose report is a CHARACTERIZATION because the code as it stands
   already satisfies it (when a limit moves, one of its two boundary tests passes before and
   after). Read that one as step 1 of the task loop reads a CHARACTERIZATION and keep it when it
   asserts what the request asks for. When none of its tests fails, the code already does what
   was asked: stop and tell the user, and for a reported defect say that the test could not
   reproduce it. Except on a task in progress, where its tests stay in that task and the task
   goes on, do not leave its changes in the tree: when the user wants the tests kept, go on
   from step 5 and commit them as the adjustment, otherwise set them aside with the stash
   command below. When the test-writer added, renamed or removed a test, update that task's
   `Test:` or `Tests:` line and its `Verify:` line in `tasks.md` now, before the implementer
   runs, so the tree its check passes on is the one you commit.
4. **The change.** Dispatch `implementer` (adjustment prompt). You write no code and no test
   yourself. The only files you edit directly are the feature's own documents and prose that
   nothing loads, runs or tests (a README, a changelog); a prompt, a skill, a template or any
   other file the product, a tool or a test reads goes to the writers.
5. **Verify.** Run five times in a row the tests the adjustment changed or added, and once the
   verify command of each task it adjusts: the tasks whose commits built what the request
   changes, normally one, the same ones its note names. A command that selects no test proves
   nothing. The check at the gate runs every other test.
6. **Reviews.** Read the adjustment's diff (`git status --porcelain`, `git diff --stat HEAD` and
   its hunks, with its size from `git diff --shortstat HEAD -- . ":(exclude)specs/<NNN-slug>"`
   plus the untracked files) and dispatch, at the same time and with the adjustment-review
   prompt, the reviews that [Reviews after a change](../SKILL.md#reviews-after-a-change) names for
   it: often one, sometimes none. Handle their findings as step 4 of the task loop does, once: a
   doubtful Critical finding goes to a `finding-verifier` first, the findings left go to one fix
   round (mark the tree before it, as inside a task), and the reviews that table names for that
   round run again with the re-review prompt.
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

- It shows a plan change by any condition of [SKILL.md](../SKILL.md#adjustments): it adds or
  removes a criterion or a behavior no criterion covers, changes the design, touches a file a
  `high` task lists or changed or anything the standards call high risk, or changes code in a
  file no task of the feature lists or changed (for each code or test file the diff changed,
  `git log --notes=refs/notes/konundrm --format='%b%N' --follow <base>..HEAD -- <file>` prints
  the `Task:` line of every task whose commit changed it, from its note or, in a feature started
  before 0.8.0, from its message, also when the plan did not list that file or a later task
  renamed it; a `Task:` line of a commit made after the feature's final commit names a later
  feature's task, so on a finished feature end the range not at `HEAD` but at its final commit
  (`git log -1 --format=%h -S'**Status:** Done' -- specs/<NNN-slug>/tasks.md`); where the notes
  are missing, as in a clone or after a squash merge, go by the plan's `Files:` lines and count a
  file a `high` task could have changed as changed by it). Do not commit it: set it aside with
  `git add -A && git stash push --include-untracked -m "<NNN-slug> adjustment set aside: <the request in a few words>"`,
  tell the user that message and propose the plan change. Write those few words with letters,
  digits and spaces only: inside the double quotes the shell would run a backtick or expand a
  `$`, and `--grep` reads `[`, `*` or `\` as a pattern. To recover it, the user runs
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
- Once the feature is done: before you end the turn that made them, add the entries of that
  turn's adjustments to `summary.md` in one `docs` commit. If code changed after the final verification,
  repeat the steps of it that exercise what changed, or say in the entry that it was not repeated.
