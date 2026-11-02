---
name: opening-pull-requests
description: Pushes committed work and opens pull requests a reviewer can approve quickly. Checks the branch is green and within the pull request budget, turns a feature's slices from tasks.md into stacked pull requests, one per slice (the default), or a single pull request with every slice, writes a Conventional Commits title and a description with what and why, a requirement → test → evidence table, each task's risk and where to look first, labels risk:high when a slice holds a high-risk task, and asks before every push. Never approves, merges or force-pushes on its own. Use when the user says "abre un PR", "crea el pull request", "sube esto y abre un PR", "open a pull request" or "push and open a PR", or when develop-feature or fix-bug finishes and the user approves pushing.
argument-hint: "[branch | specs/NNN-slug]"
---

# Opening Pull Requests

A pull request is a request for a person's judgment. Make it small enough to review well and
clear enough that the reviewer knows what to check first (Standards → Git and pull requests).

## Contract

- **Receives:** local commits on a branch that is not the default branch, and the user's yes to
  push. A feature built with `- **Publish:** live` has its slice branches pushed already, and
  develop-feature opens each slice's pull request with steps 3 to 5 as its slice ends.
- **Produces:** pushed branches and open pull requests, one per slice or one for the whole
  feature, with their URLs. Never a merge or an approval.

## Workflow

```
- [ ] 1. Confirm the branch and its base
- [ ] 2. Check green and size
- [ ] 3. Map the slices
- [ ] 4. Write each title and description
- [ ] 5. Ask, then push and open
- [ ] 6. Report
```

### 1. Branch and base

`git rev-parse --show-toplevel`, the current branch, and `git status` (must be clean: commit
first with `committing-changes`). The base is the default branch
(`gh repo view --json defaultBranchRef -q .defaultBranchRef.name`, or `origin/HEAD`). Never open a
pull request from the default branch. List what would go out: `git log --oneline <base>..HEAD`.
Check `gh auth status`; without `gh`, give the user the push command and the description to paste.

### 2. Green and size

Run the check command once (or rely on the commit gate's green result for this tree). Measure:
`git diff --shortstat <base>...HEAD`. The budget is the `Pull request budget` in the feature's
`tasks.md`, else `KONUNDRM_PR_BUDGET`, else 500 changed lines. Over the budget without slices,
propose a split along commit boundaries (refactors first, then each behavior) and ask before
going on: big pull requests get worse reviews.

### 3. Slices

With a feature folder (`specs/<NNN-slug>/tasks.md` with `## Slice S<n>` headings), the user
chooses the delivery: stacked pull requests, one per slice (the default), or a single pull request
with every slice.

**Single:** the feature branch is one pull request against the default branch, and its
description covers every slice.

When any task is high risk, warn the user before opening the single pull request that `risk:high`
will cover the whole feature, so CI repeats mutation testing on all of it. With a single pull
request and a high-risk task, also run mutation testing locally on all the changed code before
opening it, with the project's changed-code mutation command, the same one CI's `risk:high` job
runs (with setup-project's templates, `uv run --with "mutmut>=3.8,<4" python
scripts/check_mutation.py --base <base>` in Python, `npx stryker run --mutate <changed line
ranges>` in TypeScript), and kill or justify every surviving mutant. If the tool cannot run on this machine (mutmut does not run on
native Windows), record that in the evidence and tell the user: the `risk:high` CI run is then the
first mutation check.

**Stacked:** each slice is one pull request:

1. Find each task's commit, by its note:
   `git log --notes=refs/notes/konundrm --format=%H -E --grep '^Task: T<n>( |$)' <base>..HEAD`.
2. Slice `S<k>` ends at the commit that adds `specs/<NNN-slug>/summaries/S<k>.md`
   (`git log --diff-filter=A --format=%H -- specs/<NNN-slug>/summaries/S<k>.md`), falling back to the last commit
   of its tasks when there is none. The spec-and-plan commit belongs to the first slice; the final
   `Status: Done` commit to the last.
3. Create a branch at each slice end: `git branch <branch>-s<k> <sha>` (the last slice keeps the
   feature branch). Base of S1: the default branch. Base of S<k>: the branch of S<k-1>.
   The base of S<k> is the default branch instead only when the previous slice's pull request is
   merged (`gh pr list --head <previous slice branch> --state merged` lists it) and that branch is
   gone from the remote (`git ls-remote --exit-code --heads origin <previous slice branch>` finds
   nothing). A branch that was never pushed, as in a local delivery before step 5, has no merged
   pull request, so it stays the base of S<k>.

Without slices (a fix, a small change) the branch is one pull request.

### 4. Title and description

Title: the Conventional Commits header of the slice's main change (`feat(coupons): apply
percentage coupons`), ≤ 72 characters. A stacked pull request's title ends with its position and
the total, `(k/N)` (`feat(coupons): apply percentage coupons (2/5)`), within those 72 characters.
`N` is the number of slices the plan in `tasks.md` has when the pull request opens. Description: the project's
`.github/pull_request_template.md` when it exists, else these sections, filled from the spec,
`tasks.md`, the commits and `specs/<NNN-slug>/evidence/`:

```
## What and why
<two or three sentences: the problem from requirements.md and what this slice delivers>

## Requirements → tests → evidence
| Requirement | Test | Evidence |
| --- | --- | --- |
| R1.1 | tests/…::test_… | evidence/T1.md or "unit test" |

## Risk and where to look first
<each task's risk; for high-risk tasks the file and lines a reviewer must read, and the threat
they guard>

## Verification
<check command result, mutation score for high-risk code, end-to-end evidence>

## Commits, one per task
<every commit of this pull request in order, oldest first, each as its task ID (T<n>), short SHA
and subject>

## Not in this pull request
<later slices, Suggestions not applied, known follow-ups>

## How it was built
Spec and plan approved by <person>. Tests, code and reviews by Claude Code subagents
(konundrm-eng); every claim above was checked by running it. Needs a person's approval.
```

Start each stacked pull request's description, on its first line before any section, with its
merge order, `Merge order: <k> of <N>. Merge #<n> first.`, where `#<n>` is the previous slice's
pull request (they open in order, so its number is known); the first slice's says
`Merge order: 1 of <N>. Merge this one first.`

For a fix-bug branch, the table has the `B1` criterion and the regression test, and "What and
why" states the root cause and the escaped gate. Keep the attribution lines configured for the
session.

List Commits, one per task with
`git log --reverse --notes=refs/notes/konundrm --format='%h %s%n%b%N' <range>`, where the range
of a stacked slice is `<previous slice branch>..<slice branch>` (S1 starts at `<base>`) and the
range of the single pull request is `<base>..HEAD`. Take each commit's task ID from the
`Task: T<n> · Covers: R…` line of its note (`%N`) or, in a commit made before notes, from that
line in its body (`%b`), so a feature that mixes both formats lists every task, as step 1 finds
them; a commit with neither (spec and plan, summary, `Status: Done`) shows `—` in its place.

When `specs/<NNN-slug>/summaries/S<k>.md` exists, build that slice's description from it: its
"What changed and why" feeds What and why, "Requirements covered" the table, "Risks and high-risk
tasks" and "Reading order" Risk and where to look first, "Decisions" and the review rounds How it
was built. Add what the summary lacks (evidence links, the check result, the merge-order line, the
attribution). The summary's links are relative to `summaries/` (`../requirements.md`), and GitHub
resolves links in a pull request body against the pull request page, so rewrite them to
repository paths.

With a feature folder, link `specs/<NNN-slug>/summary.md` from the description of every pull
request, stacked or single, as a full URL: `https://github.com/<owner>/<repo>/blob/<commit>/specs/<NNN-slug>/summary.md`.
`<commit>` is the SHA of the feature's final `docs(<scope>)` commit, which holds the summary, so
the link keeps working after the slice branches are merged and deleted.

A fix-bug branch, a small change without slices and a feature built before the summary existed
have no `summary.md`, so their descriptions carry no summary link.

### 5. Ask, then push and open

Show the user every branch, its base, title, labels and draft state, and wait for an explicit
yes. Then, per slice in order:

- `git push -u origin <branch>` (never `--force`; after a rebase, `--force-with-lease` only with
  its own yes);
- `gh pr create --base <base> --head <branch> --title "<title>" --body-file <file>`, with
  `--draft` when the user wants CI first. When the branch already has an open pull request
  (`gh pr list --head <branch> --state open`), never open another one: keep the existing one;
- `gh pr edit <number> --add-label risk:high` only when that slice holds a high-risk task and the
  repository has the label (`gh label list --search risk:high`), so CI repeats mutation testing
  on it and reviewers of the other slices are not asked to treat them as high risk. Never create
  the label, which would change the repository: open the pull request without it and say so at
  the slice's pause, or in the report (step 6).

### 6. Report

List each pull request's URL, base and size. Remind the user that a person approves each one,
preferably someone other than the requester of agent-written work, and that stacked pull
requests merge in order. When the repository squash-merges, the next slice needs
`git rebase --onto <default> <previous-slice-branch> <next-branch>` and a lease push after each
merge; offer to do it then.

## Rules

- Never push to or open from the default branch; never merge, approve or request changes.
- Never force-push without an explicit yes for that push.
- When a pull request that is already pushed needs its history rewritten (a rebase onto the
  updated default branch, or the stacked `git rebase --onto` after a squash merge), ask the
  user's explicit yes for that rewrite, then push it with `--force-with-lease`, never a plain
  `--force`.
- Pull request text quotes evidence; it does not claim anything you did not run.
