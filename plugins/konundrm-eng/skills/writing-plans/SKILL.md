---
name: writing-plans
description: Turns an approved requirements.md into a technical design and a list of small test-first tasks grouped into pull-request-sized slices. Explores the codebase to decide which module owns each responsibility, writes specs/<NNN-slug>/design.md (ownership, interfaces, threats for high-risk work, how the slices reach users) and tasks.md, where every task is one red-green-refactor cycle of 2–5 minutes with exact files, the test to write, its risk level and the command that verifies it. Use after writing-specs, or when the user says "planifiquemos", "cómo lo implementamos", "divide esto en tareas", "write a plan" or "break this down". Does not write production code or tests.
argument-hint: "[path to requirements.md]"
effort: xhigh
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
- [ ] 6. Partition each slice into waves
- [ ] 7. Self-review traceability and partitions
- [ ] 8. Get explicit approval
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
- **Decisions:** when a task has two or more reasonable approaches, record them in its
  `- Decision:` field, each option with its advantages and disadvantages, plus your recommendation.
  A task with only one reasonable approach has no `- Decision:` field. Once chosen, rewrite the
  field's first line as `- Decision: <option> (user | recommended)` and keep the options below
  it, which records who chose. Summaries cite these decisions and their options as recorded.

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

### 6. Partitions

Close each slice with a `### Partitions` table, `| Wave | Partition | Tasks | Depends on |`, laid
out as in [templates/tasks.md](templates/tasks.md). The task list keeps its order; the table only
groups it.

- A **partition** is a set of tasks one session builds, in list order. Every task belongs to
  exactly one partition. Keep each dependency chain inside one partition where you can, and follow
  module boundaries, so partitions stay independent.
- A partition depends on another when one of its tasks depends on one of that partition's tasks.
- A **wave** is a set of partitions of one slice that do not depend on each other. A partition
  goes in a later wave than every partition it depends on, and the partitions of one wave share no
  file (`tasks.md` and `evidence/` excepted). A task that adds a dependency touches the manifest
  and the lockfile, so two such tasks never sit in different partitions of one wave.
- At most three partitions per wave; prefer fewer, balanced ones over many small ones.
- Partition IDs (`P1`, `P2`…) are unique across the feature: they do not restart in each slice.
- When no work in a slice is independent, use a single partition with every task of the slice.

develop-feature can build the partitions of one wave at the same time when the user accepts it
(the `Parallel:` line in the header of `tasks.md`).

### 7. Self-review

- Every acceptance criterion maps to at least one task; no behavior task lacks a criterion.
- Every task has a risk level, and every money, auth, personal-data, data-deletion or
  external-contract task is high.
- Every high-risk task has a threats row and a `Security:` line; every threat has its control in
  some task.
- No task touches a module the design does not mention.
- Dependencies point to earlier tasks only, so slices merge in order.
- Every slice fits the budget and leaves the main branch working.
- Every task is in exactly one partition; each partition's `Depends on` matches its tasks'
  dependencies and names only partitions of earlier waves; the partitions of a wave share no file
  except `tasks.md` and `evidence/`.
- The last task, or the feature's final verification, exercises the end-to-end flow.

### 8. Approval

Show the ownership table, the threats (if any) and the task list grouped by slice (IDs and titles
only) with each slice's partitions, and ask for an explicit yes before setting `Status: Approved`. When called from
`develop-feature`, return control to it.

Present each open decision with its options, advantages, disadvantages and recommendation. The
user picks an option or accepts the recommendation; rewrite the first line of each
`- Decision:` field with the choice, keeping its options below, before approving.
