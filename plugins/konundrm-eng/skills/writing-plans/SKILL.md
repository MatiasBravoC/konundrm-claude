---
name: writing-plans
description: Turns an approved requirements.md into a technical design and a list of small test-first tasks grouped into pull-request-sized slices. Explores the codebase to decide which module owns each responsibility, writes specs/<NNN-slug>/design.md (ownership, interfaces, threats for high-risk work, how the slices reach users) and tasks.md, where every task is one red-green-refactor cycle of 2–5 minutes with exact files, the test to write, its risk level and the command that verifies it. Use after writing-specs, or when the user says "planifiquemos", "cómo lo implementamos", "divide esto en tareas", "write a plan" or "break this down". Does not write production code or tests.
argument-hint: "[path to requirements.md]"
---

# Writing Plans

A plan is good when an engineer with no context, and doubts about their own taste, could execute
each task without asking a question. Precision over prose.

## Contract

- **Receives:** an approved `specs/<NNN-slug>/requirements.md` (`$ARGUMENTS`, or the most recent spec).
- **Produces:** `design.md` and `tasks.md` in the same folder, both with status `Approved`.

Refuse to plan from a spec whose status is not `Approved`; send the user back to `writing-specs`.

## Workflow

```
- [ ] 1. Read the spec and the code it touches
- [ ] 2. Decide module ownership (designing-modules)
- [ ] 3. Write design.md
- [ ] 4. Write tasks.md
- [ ] 5. Group the tasks into slices
- [ ] 6. Self-review traceability
- [ ] 7. Get explicit approval
```

### 1–2. Explore and decide ownership

Apply the `designing-modules` skill to the feature as a whole: for each responsibility the spec
implies, search for the module that already owns it, find duplicates, and decide extend vs. new.
Read the project's `AGENTS.md`/`CLAUDE.md` and its architecture rules (import-linter contracts,
dependency-cruiser config) so the design respects them.

### 3. design.md

Use [templates/design.md](templates/design.md). Keep it under ~150 lines. It records decisions,
not tutorials: the ownership table, public interfaces with signatures, data flow, the alternatives
rejected and why, threats, delivery and risks. Every section ties back to requirement IDs.

- **Threats** (Standards → Security): required when any task will be high risk. One row per trust
  boundary the feature crosses, with what could go wrong and the control that prevents it. Each
  control becomes a task or part of one, so it gets a test.
- **Delivery:** how the slices reach users, what keeps the feature unreachable until its last
  slice lands (an entry point not wired yet, or a flag the spec's `WHERE` criteria already name),
  and how each slice is rolled back.

### 4. tasks.md

Use [templates/tasks.md](templates/tasks.md). Rules for each task:

- **One behavior, one test, one commit.** If the task needs "and", split it.
- **2–5 minutes of work:** one failing test plus the minimal code to pass it.
- **Exact paths** for the test file, the test name, and every source file created or modified.
- **A verify command** that runs just that test (`pytest path::name`, `npx vitest run path -t "name"`).
- **Covers:** the requirement IDs it advances.
- **Order** from the walking skeleton outward: happy path first, then edges, then errors; a task
  never depends on a later one.
- **Properties:** each invariant the spec implies (round-trip, totals preserved, idempotence,
  ordering) gets its own `property` task after the example tasks that pin the basic cases, with
  the generator's valid domain stated.
- **Risk:** every task gets `Risk: low | medium | high` following Standards → Verification by risk.
  Medium and high tasks list their `Invariants`; high-risk tasks also name the mutation command
  scoped to the changed code, what the security review must look at (`Security:`, from the
  threats table) and the end-to-end evidence to collect. When unsure between two levels, pick the
  higher one.
- Tasks with nothing to test (config, scaffolding, docs) are typed `chore` and carry a verify
  command instead of a test.

### 5. Slices

Group consecutive tasks under `## Slice S<n>: <what this pull request delivers>` headings
(Standards → Git and pull requests). A slice:

- fits the pull request budget in the header (default 400 changed lines, tests included); estimate
  from the files each task touches, and split the slice when in doubt;
- merges on its own: after its last task the check is green and nothing user-visible is half-built
  and reachable;
- keeps high-risk tasks together with the tests that guard them, and apart from unrelated
  low-risk work, so the `risk:high` review and mutation run stay focused.

A feature small enough for one pull request has one slice. Tasks keep their order and IDs across
slices.

### 6. Self-review

- Every acceptance criterion maps to at least one task; no behavior task lacks a criterion.
- Every task has a risk level, and every money, auth, personal-data, data-deletion or
  external-contract task is high.
- Every high-risk task has a threats row and a `Security:` line; every threat has its control in
  some task.
- No task touches a module the design does not mention.
- Dependencies point to earlier tasks only, so slices merge in order.
- Every slice fits the budget and leaves the main branch working.
- The last task, or the feature's final verification, exercises the end-to-end flow.

### 7. Approval

Show the ownership table, the threats (if any) and the task list grouped by slice (IDs and titles
only), and ask for an explicit yes before setting `Status: Approved`. When called from
`develop-feature`, return control to it.
