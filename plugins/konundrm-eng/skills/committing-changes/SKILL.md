---
name: committing-changes
description: Turns the working tree's pending changes into small, atomic Git commits, one logical change each, with messages in Conventional Commits format (no emoji) written in English. Runs the project's check command first and refuses to commit on red, never bypasses hooks, and stops before pushing to ask for explicit approval. Use when the user says "sube los cambios", "commitea esto", "guarda mi trabajo en git" or "haz commit de todo", when develop-feature finishes a task, or whenever there are uncommitted changes worth saving.
---

# Committing Changes

Leave a history a stranger can read, bisect and revert: one reason per commit, every commit green,
nothing pushed without a yes.

## Contract

- **Receives:** uncommitted changes in the working tree.
- **Produces:** one or more local commits on a clean tree and a list of their messages. Never a push.

## Workflow

```
- [ ] 0. Confirm the repository
- [ ] 1. Run the quality gate
- [ ] 2. Read everything pending
- [ ] 3. Split into atomic groups
- [ ] 4. Write each message
- [ ] 5. Commit, then stop
```

### 0. Confirm the repository

Check `git rev-parse --show-toplevel` and the current branch. Nested folders, monorepos, worktrees
and background runs make it easy to be somewhere else. Committing to the wrong repository is an
unauthorized change to someone's project, not a fixable slip.

### 1. Run the quality gate

Run the project's check command once: the session context names it, or
`sh "${CLAUDE_PLUGIN_ROOT}/hooks/run.sh" quality_check.py` prints it (the same discovery the
hooks use). If it fails, stop and report; do not commit red. The plugin's commit hook enforces
the same rule and reuses this green result while the files stay the same, so do not run it again
between commits of the same pass. If the project has no check command, say so and continue:
nothing gates the commit, and `/konundrm-eng:setup-project` can add one.

### 2. Read everything pending

`git status`, `git diff`, `git diff --staged`. Decide from the actual diff, not from memory of the
conversation.

### 3. Split into atomic groups

Atomic means one reason to exist, not one file:

- Two unrelated changes in the same file are two commits: stage hunks separately
  (`git add -p`, or `git apply --cached` with a partial patch when interactive mode is unavailable).
- Files that only make sense together (a function and its test, a component and its type) are
  one commit. Every commit must build and pass on its own. The plugin's hook checks the whole
  working tree, not each partial commit (only Python's pre-commit framework checks what each
  commit stages), so keep each group self-contained.
- Test: could you revert one change without the other and still have something coherent? Then
  they are separate commits.

Order the commits as a story: refactor before the feature that needs it.

### 4. Write each message

`<type>(<scope>): <imperative summary>` ([Conventional Commits](https://www.conventionalcommits.org/)),
at most 72 characters, **always in English**, whatever the conversation language: changelogs,
release notes and future contributors read it. The header starts with the type: no emoji or
other prefix.
Add a body (blank line, 1–3 sentences) when the summary does not explain *why*. Inside
`develop-feature` and `fix-bug`, the task and requirement IDs go in a Git note, never in the
message ([Inside develop-feature](#inside-develop-feature), [Inside fix-bug](#inside-fix-bug)).

| Type | Use for |
| --- | --- |
| `feat` | new capability |
| `fix` | bug fix, including security fixes |
| `refactor` | restructuring with no behavior change, including removing code or files |
| `test` | adding or fixing tests only |
| `docs` | documentation only |
| `style` | formatting, no logic change |
| `perf` | performance |
| `chore` | tooling, config, scripts |
| `build` | dependency upgrades |
| `ci` | CI pipelines |

`<scope>` is the module or area touched (`auth`, `billing`, `UserCard`); omit it only for
project-wide changes. If `git log` shows established scopes, reuse them.

Example: `feat(discounts): add percentage-based discount helper`

### 5. Commit, then stop

Commit each group, confirm `git status` is clean, list the commit messages, and **ask before
`git push`**. Pushing is a separate, explicitly approved step every time. When the user wants a
pull request, hand over to the `opening-pull-requests` skill.

### Inside develop-feature

The orchestrator calls this skill once per task and once per adjustment, with the change
already one logical change and the check green for these exact files. In that mode: skip step 1
(the commit hook reuses that green result), make exactly **one** commit, and do not ask about
pushing; the orchestrator asks once, when the whole feature is done.

Build a task's message with `task_ledger.py message`, commit it with a plain `git commit -F` and
attach its note with `task_ledger.py record`, in one call:
`msg=$(sh "${CLAUDE_PLUGIN_ROOT}/hooks/run.sh" task_ledger.py message specs/<NNN-slug>/tasks.md T<n> --subject "<type>(<scope>): <summary>" --rounds "spec <n> · code <n> · escalations <n>") && git add -A && git commit -F "$msg" --trailer "Co-Authored-By: …" && sh "${CLAUDE_PLUGIN_ROOT}/hooks/run.sh" task_ledger.py record`.
`message` writes only the subject and the optional `--body "<why>"` to a file under the Git
directory and prints only its path. It leaves the flow's lines, `Task: T<n> · Covers: R…` and
`Rounds: …`, in a pending note that `record` attaches to the new commit under
`refs/notes/konundrm`. It never commits nor changes the working tree, and it refuses a task the
plan lacks or one already committed. The `git commit` goes through the commit
gate like any other commit. Write the subject and the body inside double quotes with no backtick,
`$`, `"` or `\` in them, or inside single quotes with no `'` in them, so the shell expands nothing:
a backtick would run a command before the commit. Add the session's co-author and attribution trailers to the
`git commit` with `--trailer`, never in `--body`. Do not check the task's box nor write its Rounds
line in `tasks.md` in this commit.

The other commits develop-feature makes in this mode (a slice summary, a partition report, an
integration fix) are not a task's own commit, and `message` refuses a task that already has one:
write their message by hand, with a plain subject that says what changed, and attach no note.

An adjustment (a small change the user asked for on work already committed; develop-feature →
Adjustments) is not a task's own commit either, so its message is written by hand too, but it gets
a note, written in the same command as the commit, so it is written once:
`git add -A && git commit -m "<type>(<scope>): <summary>" --trailer "Co-Authored-By: …" && git notes --ref=refs/notes/konundrm add -m "Adjusts: T<n>" -m "Reviews: <spec, code | spec | code | none> (<why the others were not needed>)" -m "Asked: <the request, in one line>" HEAD`.
In the note, `Adjusts:` names the task or tasks the request is about (`—` when it is about none),
`Reviews:` the reviews that ran for it and why not the others, and `Asked:` what the user asked.
Quote each `-m` text as the subject is quoted, rewording a request that holds a backtick, `$`,
`"` or `\`. Never amend that commit: Git would leave its note on the old one. Type the commit by
what it changes (`feat`, `refactor`, `docs`, `style`, `test`). Type it `fix` only when the request
reported a defect (built work that does not do what an approved criterion says), and then add
`-m "Escaped-gate: <spec | property | review | e2e | none>"` to its note, as fix-bug does: the
impact report counts a `fix` on a task's files as an escaped defect, so a preference is never
typed `fix`.

### Inside fix-bug

The `fix-bug` skill calls this skill once, with the fix already one logical change and the check
green for these exact files. In that mode: skip step 1 (the commit hook reuses that green
result), make exactly **one** `fix` commit whose body gives the root cause and ends with
`Fixes: <issue>` only (left out when there is no issue), and do not ask about pushing; fix-bug
asks once it has reported. This mode owns the commit's note, the only place for its flow data:
write it in the same command as the commit, so it is written once,
`git commit -F <message file> --trailer "Co-Authored-By: …" && git notes --ref=refs/notes/konundrm add -m "Covers: B1" -m "Escaped-gate: <spec | property | review | e2e | none>" HEAD`,
with the requirement ID in `Covers:` when the bug broke an approved one (Standards → Git and pull
requests).

## Ground rules

- Never `--no-verify`, never skip or disable hooks. If a hook fails, fix the cause and commit again.
- The commit gate denies changes that add a gate silencer without its reason and asks the person
  about anything that looks like a credential (Standards → Gate integrity, Security). Fix the
  change; never work around the gate.
- Amend only a commit you made in this same pass and have not pushed.
- Keep attribution and co-author trailers exactly as configured for the session.
