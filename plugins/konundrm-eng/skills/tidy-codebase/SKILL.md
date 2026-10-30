---
name: tidy-codebase
description: Periodic clean-up pass ("garbage collection") that finds the drift day-to-day gates miss and turns it into small, behavior-preserving changes. Scans for duplicated blocks, silencers without a reason or no longer needed, unused code and dependencies, AGENTS.md, CLAUDE.md and docs that no longer match the code, and old TODOs; ranks the findings, proposes at most five tasks, and with the user's yes implements each as its own commit and small pull request. Invoke with /konundrm-eng:tidy-codebase [path or area], or schedule it to run weekly.
disable-model-invocation: true
argument-hint: "[path or area]"
---

# Tidy Codebase

AI-assisted teams copy more and refactor less (GitClear), and instructions drift away from the
code they describe. OpenAI's harness team replaced a weekly cleanup day with recurring agents
that open small refactoring pull requests against that drift. This skill is that pass: read-only
until the user picks what to fix, then one small change at a time.

Scope: $ARGUMENTS (the whole project when empty)

## Workflow

```
- [ ] 1. Scan (read-only)
- [ ] 2. Rank and propose
- [ ] 3. Fix what the user approves
- [ ] 4. Report
```

### 1. Scan

Collect findings with evidence, without changing anything:

- **Duplication:** `sh "${CLAUDE_PLUGIN_ROOT}/hooks/run.sh" find_duplicates.py --all`.
- **Silencers:** `git grep -n -E "noqa|type: ignore|pyright: ignore|nosec|pragma: no cover|eslint-disable|@ts-ignore|@ts-expect-error|@ts-nocheck|NOSONAR"`.
  For each one, decide whether its reason is missing or no longer true (the code it excused
  changed), and whether the tool still reports anything without it (ruff `RUF100`, ESLint
  `reportUnusedDisableDirectives`).
- **Unused code and dependencies:** the project's own tools when configured (ruff, `knip`,
  `deptry`, `ts-prune`, `vulture`); never install one without the user's yes.
- **Instructions and docs:** every command, path and rule in `AGENTS.md`, `CLAUDE.md` and the
  README still exists and works (run each command with its help flag, check each path).
- **Old TODOs:** `git grep -n -E "TODO|FIXME|XXX"` with `git blame` dates; older than 90 days.
- **Complexity near the limit:** functions at or over the limits in Standards → Design.

### 2. Rank and propose

Rank by value (how much confusion or risk it removes) over cost. Propose at most five tasks, each
behavior-preserving, small enough for one pull request, with how it will be verified: the
existing tests stay green, plus characterization tests first where coverage is thin. Show the
list and wait for the user to pick.

### 3. Fix

For each approved task, in order, on its own branch from the default branch (`tidy/<slug>`): the
`implementer` makes the change (refactor prompt from develop-feature's fix round, with the finding
as the problem), you run the check, the `code-reviewer` reviews it, and `committing-changes`
commits it as `refactor(…)`, `chore(…)` or `docs(…)`. With the user's yes, `opening-pull-requests`
opens one pull request per task, from that task's branch.

### 4. Report

List what was fixed, what was left and why, and the numbers that show the trend (duplicated
blocks, silencers, TODOs) so the next pass can compare. To run this every week, suggest a
scheduled task in the Claude desktop app or a `/schedule` routine with the prompt
`/konundrm-eng:tidy-codebase`.

## Rules

- Never change behavior in this pass; a behavior change becomes a feature or a fix-bug.
- Never remove a silencer whose reason still holds; fix the cause or keep it with its reason.
- One finding per commit and per pull request.
