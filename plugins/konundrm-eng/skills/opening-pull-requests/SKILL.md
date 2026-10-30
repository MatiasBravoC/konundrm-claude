---
name: opening-pull-requests
description: Pushes committed work and opens pull requests a reviewer can approve quickly. Checks the branch is green and within the pull request budget, turns a feature's slices from tasks.md into one stacked pull request each, writes a Conventional Commits title and a description with what and why, a requirement → test → evidence table, each task's risk and where to look first, labels risk:high when a slice holds a high-risk task, and asks before every push. Never approves, merges or force-pushes on its own. Use when the user says "abre un PR", "crea el pull request", "sube esto y abre un PR", "open a pull request" or "push and open a PR", or when develop-feature or fix-bug finishes and the user approves pushing.
argument-hint: "[branch | specs/NNN-slug]"
---

# Opening Pull Requests

A pull request is a request for a person's judgment. Make it small enough to review well and
clear enough that the reviewer knows what to check first (Standards → Git and pull requests).

## Contract

- **Receives:** local commits on a branch that is not the default branch, and the user's yes to
  push.
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
`tasks.md`, else `KONUNDRM_PR_BUDGET`, else 400 changed lines. Over the budget without slices,
propose a split along commit boundaries (refactors first, then each behavior) and ask before
going on: big pull requests get worse reviews.

### 3. Slices

With a feature folder (`specs/<NNN-slug>/tasks.md` with `## Slice S<n>` headings), the user
chooses the delivery: stacked pull requests, one per slice (the default), or a single pull request
with every slice.

**Single:** the feature branch is one pull request against the default branch, and its
description covers every slice.

**Stacked:** each slice is one pull request:

1. Find each task's commit: `git log --format=%H -E --grep '^Task: T<n>( |$)' <base>..HEAD`.
2. Slice `S<k>` ends at the last commit of its tasks. The spec-and-plan commit belongs to the
   first slice; the final `Status: Done` commit to the last.
3. Create a branch at each slice end: `git branch <branch>-s<k> <sha>` (the last slice keeps the
   feature branch). Base of S1: the default branch. Base of S<k>: the branch of S<k-1>.

Without slices (a fix, a small change) the branch is one pull request.

### 4. Title and description

Title: the Conventional Commits header of the slice's main change (`feat(coupons): apply
percentage coupons`), ≤ 72 characters. Description: the project's
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

## Not in this pull request
<later slices, Suggestions not applied, known follow-ups>

## How it was built
Spec and plan approved by <person>. Tests, code and reviews by Claude Code subagents
(konundrm-eng); every claim above was checked by running it. Needs a person's approval.
```

For a stacked slice, start the description with `Stacked on #<number>: merge that one first.`
For a fix-bug branch, the table has the `B1` criterion and the regression test, and "What and
why" states the root cause and the escaped gate. Keep the attribution lines configured for the
session.

When `specs/<NNN-slug>/summaries/S<k>.md` exists, build that slice's description from it: its
"What changed and why" feeds What and why, "Requirements covered" the table, "Risks and high-risk
tasks" and "Reading order" Risk and where to look first, "Decisions" and the review rounds How it
was built. Add what the summary lacks (evidence links, the check result, the stacked-on line, the
attribution). The summary's links are relative to `summaries/` (`../requirements.md`), and GitHub
resolves links in a pull request body against the pull request page, so rewrite them to
repository paths.

### 5. Ask, then push and open

Show the user every branch, its base, title, labels and draft state, and wait for an explicit
yes. Then, per slice in order:

- `git push -u origin <branch>` (never `--force`; after a rebase, `--force-with-lease` only with
  its own yes);
- `gh pr create --base <base> --head <branch> --title "<title>" --body-file <file>`, with
  `--draft` when the user wants CI first;
- `gh pr edit <number> --add-label risk:high` when the slice holds a high-risk task, so CI
  repeats mutation testing on it. If the label does not exist, ask before creating it
  (`gh label create risk:high`): it changes the repository.

### 6. Report

List each pull request's URL, base and size. Remind the user that a person approves each one,
preferably someone other than the requester of agent-written work, and that stacked pull
requests merge in order. When the repository squash-merges, the next slice needs
`git rebase --onto <default> <previous-slice-branch> <next-branch>` and a lease push after each
merge; offer to do it then.

## Rules

- Never push to or open from the default branch; never merge, approve or request changes.
- Never force-push without an explicit yes for that push.
- Never edit history that is already on the remote except a stacked rebase the user approved.
- Pull request text quotes evidence; it does not claim anything you did not run.
