---
name: migrate-code
description: Runs a large, behavior-preserving mechanical change (a framework or library upgrade, an API replacement, a test-framework switch, a language-version bump) the way Google, Airbnb and Amazon run LLM-assisted migrations. Builds an inventory of every site by deterministic search, writes a recipe with before/after examples the user approves, adds characterization tests where coverage is thin, applies deterministic codemods first and the implementer only to the long tail, moves each file through gated steps (types, lint, its tests) with bounded retries, ships review-sized batches as separate pull requests, and keeps a progress file so the work can stop and resume. Invoke with /konundrm-eng:migrate-code <what to migrate>, or a migrations/<slug> folder to resume.
disable-model-invocation: true
argument-hint: "<migration goal | migrations/slug>"
---

# Migrate Code

Google's LLM-assisted migrations, Airbnb's move of 3,500 test files from Enzyme to React Testing
Library and Amazon's Java upgrades share one shape: deterministic tools find and change what
they can, the model handles the long tail, every file passes a gate before it moves on, and the
volume is capped so reviewers keep up. A migration never changes behavior; a behavior change is
a feature (`/konundrm-eng:develop-feature`).

Goal: $ARGUMENTS

## Workflow

```
- [ ] 1. Inventory
- [ ] 2. Recipe and pilot
- [ ] 3. Safety net
- [ ] 4. Codemod first
- [ ] 5. File by file, gated
- [ ] 6. Batches
- [ ] 7. Finish
```

All state lives in `migrations/<slug>/`: `inventory.md` (one row per file: status, attempts,
last error), `recipe.md` and `report.md`. To resume, read them and continue at the first file
that is not `committed`.

### 1. Inventory

Find every site with deterministic search, never by reading files at random: `git grep`,
ast-grep or the language's AST tools, the old API's import graph, or the compiler and type
checker errors after bumping the version. Write `inventory.md` with each file, the number of
sites and status `pending`. Report the totals.

### 2. Recipe and pilot

Write `recipe.md`: what changes and what must not, three to five before/after pairs taken from
the real code, the per-file verify command (type check, lint and that file's tests), and the
edge cases found so far. Have the `implementer` migrate two or three representative files with
the recipe, check them yourself, and refine the recipe. Get the user's explicit yes on the recipe
and the pilot before going on.

### 3. Safety net

For each file whose behavior has thin coverage (`adding-test-coverage` measures it), have the
`test-writer` add characterization tests first (CHARACTERIZATION reports), committed before the
migration touches the file. A migration without tests that would notice a change in behavior is
a guess.

### 4. Codemod first

When a deterministic transformation exists (the framework's official codemod, OpenRewrite,
jscodeshift or ts-morph, libcst, ast-grep, pyupgrade), run it on the inventory first and mark what
it fully converted. Deterministic edits are cheaper to review and never hallucinate. The
`implementer` only takes what the tool could not do.

### 5. File by file, gated

Each file moves `pending → migrated → verified → committed`, or to `needs-human`:

1. **Migrate:** dispatch `implementer` with the recipe, the file and its last error, if any.
2. **Verify:** run the per-file verify command yourself. On failure, send the error back with the
   recipe (Airbnb's retry loop), at most three attempts per file; then mark `needs-human` with the
   last error and move on.
3. **Check the diff:** the change touches only what the recipe covers. Unrelated edits, deleted
   tests, weakened assertions and new silencers (Standards → Gate integrity) send the file back.

Update `inventory.md` after every file.

### 6. Batches

Group verified files into batches within the pull request budget (Standards → Git and pull
requests). For each batch: run the full check, dispatch `code-reviewer` on the batch (and
`spec-reviewer` with the recipe as the criterion: the batch applies the recipe and nothing
else), commit it as `refactor(<scope>): migrate <n> files from <old> to <new>`, and, with the
user's yes, open its pull request with `opening-pull-requests`. Ask the user how many batches the
reviewers can take per week, and do not open more than that.

### 7. Finish

The migration is done when the inventory has no `pending` file, the deterministic search for the
old usage returns nothing (or only listed exceptions), every `needs-human` file is listed for a
person, and compatibility shims are removed. Write `report.md`: files migrated by the codemod and
by the implementer, attempts, files left for people, and the time it took. Ask before pushing.

## Rules

- Behavior stays the same: the existing and characterization tests pass unchanged.
- Never delete, skip or weaken a test to make a migrated file pass.
- No new dependency without the user's yes (the dependency guard checks it too).
- One migration per branch; unrelated fixes found on the way become notes in `report.md`.
