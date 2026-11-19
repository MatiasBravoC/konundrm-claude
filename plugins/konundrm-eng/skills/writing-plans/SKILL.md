---
name: writing-plans
description: Turns an approved requirements.md into a technical design and a list of small test-first tasks grouped into pull-request-sized slices. Explores the codebase to decide which module owns each responsibility, writes specs/<NNN-slug>/design.md (ownership, interfaces, threats for high-risk work, how the slices reach users) and tasks.md, where every task is one behavior of 2–5 minutes, or up to five related low-risk behaviors consolidated into one, with exact files, the tests to write, its risk level and the command that verifies it. Use after writing-specs, or when the user says "planifiquemos", "cómo lo implementamos", "divide esto en tareas", "write a plan" or "break this down". Does not write production code or tests.
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
- [ ] 4. List the behaviors, one per line
- [ ] 5. Consolidate the related low-risk ones and write tasks.md
- [ ] 6. Group the tasks into slices
- [ ] 7. Partition each slice into waves
- [ ] 8. Self-review traceability, consolidation and partitions
- [ ] 9. Get explicit approval
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

### 4. Behaviors

List every behavior the spec asks for on its own line first, in your notes, not in `tasks.md`:
what the system does, its type, its risk, the criteria it covers, its owner (the row of the
design's ownership table) and its test. Step 5 merges the lines that belong together and only then
writes the tasks, so each task is written once and each ID is given once. Rules for each line:

- **One behavior, one test.** If the line needs "and", split it.
- **2–5 minutes of work:** one failing test plus the minimal code to pass it.
- **Order** from the walking skeleton outward: happy path first, then edges, then errors.
- **Properties:** each invariant the spec implies (round-trip, totals preserved, idempotence,
  ordering) goes on the `Invariants` of the `medium` or `high` line whose code makes it hold,
  with the generator's valid domain stated: its property test is written with that line's test.
  It gets its own `property` line, after the lines it needs, only when it takes several lines,
  or a `low` one, to make it hold over that whole domain.
- **Risk:** every line gets `low`, `medium` or `high` following Standards → Verification by risk.
  When unsure between two levels, pick the higher one.
- Work with nothing to test (config, scaffolding, docs) is a `chore` line.

### 5. tasks.md

Use [templates/tasks.md](templates/tasks.md). One task per behavior makes a small feature pay for
dozens of cycles of test-writer, implementer and two reviews, and a cycle costs the same whatever
its size. So first merge the lines that belong together into one **consolidated task**, built and
reviewed in a single cycle. They need not be next to each other in the list: bring related lines
together when no dependency forbids it. Merge them when every one of these holds:

- **Low risk, all of them.** A `high` line is never merged, with anything, and a `medium` line
  only with other `medium` lines, when the header says `low and medium` (below).
- **One owner.** They have the same owner in the first list, one row of the design's ownership
  table (one responsibility, in one file or several), or they apply one and the same rule to
  several owners (the same setting, wording or check repeated in each), and one verify command
  runs exactly their tests.
- **One logical change.** One title says what the merged task delivers, without an "and" joining
  things a reviewer would read apart: the cases of one function (happy path, edges, errors), the
  fields of one form, the options of one command, the steps of one piece of wiring or setup.
- **Within the limit.** At most five behaviors and about 300 changed lines of code and tests, and
  never more than the pull request budget. Count the tests, which often weigh more than the code
  they pin: size them from the neighbouring tests or from the task commits the repository
  already has.

Never merge a `property` line, a line that needs a `- Decision:` field or one that adds a
dependency. `chore` lines merge with each other when one title states them (the steps of one
setup, or small edits of one kind such as wording or tidy-ups), within the same limit, or into the
low-risk task they prepare or document: when they change one of its files, or write the README
or changelog lines about what that task builds. When one condition is in doubt, keep the lines
apart: a wrong merge costs a failed review of a bigger change.

The header line `- **Consolidation:**` holds the user's choice: `low` unless the user says
otherwise in the request or when approving the plan. With `low and medium`, also merge `medium`
lines that are cases of one rule: the same function or class and the same test file, at most three
behaviors per task, each of their invariants kept on the merged task. With `none`, write one task
per line. A `tasks.md` without that line (a plan written before 0.9.0) reads as `low` for the
tasks a plan change adds: add the line then, and count each task the plan already had as one
behavior in its totals.

Then write the tasks, numbered in their final order. Rules for each task:

- **Exact paths** for the test file, each test name, and every source file created or modified.
- **A verify command** that runs just the task's test, or just the tests of a consolidated task
  (`pytest path::name`, `npx vitest run path -t "name"`).
- **Covers:** the requirement IDs it advances.
- **Dependencies** point to earlier tasks only: a task never depends on a later one.
- **Risk:** every task carries `Risk: low | medium | high`, the risk of its lines.
  Medium and high tasks list their `Invariants`, each one naming the `property` task that covers
  it when there is one (`property in T7`): develop-feature writes the property test of the
  others together with the task's own test. High-risk tasks also name the mutation command
  scoped to the changed code, what the security review must look at (`Security:`, from the
  threats table) and the end-to-end evidence to collect.
- A `chore` task carries a verify command instead of a test.
- **Decisions:** when a task has two or more reasonable approaches, record them in its
  `- Decision:` field, each option with its advantages and disadvantages, plus your recommendation.
  A task with only one reasonable approach has no `- Decision:` field. Once chosen, rewrite the
  field's first line as `- Decision: <option> (user | recommended)` and keep the options below
  it, which records who chose. Summaries cite these decisions and their options as recorded.
- **A consolidated task** is one task: one ID, the risk of its lines, the criteria of all its
  behaviors in `Covers`, and a `Tests:` list in place of the `Test:` line, with one test per
  behavior and the criterion it asserts. Each behavior keeps its own test, so the trace from the
  spec to a test does not change. A `chore` line merged into a behavior task has no test: write
  its step on the `Files:` line, after the file it changes (`<path>` (modify: <the step>)), so
  the implementer and the reviewers read it as part of the task.

After the last task, add the totals to the header's `Consolidation:` line, after the user's
choice: `low · <n> behaviors in <m> tasks`. They count the lines of the first list.

When a plan change adds tasks to a plan that is already being built, list and consolidate the new
lines the same way, among themselves only: a task that has its commit keeps its ID, its `Covers`
and its tests, each new task takes the next unused ID, and no task is renumbered, because a built
task's note names its ID. An ID is `T` and a number, never `T2a`: the plan's readers know no
other form. Give each new task its place in its slice's `### Partitions` table, then update the
totals.

### 6. Slices

Group consecutive tasks under `## Slice S<n>: <what this pull request delivers>` headings
(Standards → Git and pull requests). A slice:

- aims at 300–500 changed lines of code and tests, the feature's documents (`requirements.md`,
  `design.md`, `tasks.md`, summaries, evidence) not counted, and never goes over the pull request
  budget in the header (default 500); estimate from the files each task touches, and split the
  slice when in doubt;
- is smaller than 300 lines only when the whole feature is smaller, or to split off high-risk work
  from the rest;
- merges on its own: after its last task the check is green and nothing user-visible is half-built
  and reachable;
- keeps high-risk tasks together with the tests that guard them, and apart from unrelated
  low-risk work, so the `risk:high` review and mutation run stay focused.

A feature small enough for one pull request has one slice. Tasks keep their order and IDs across
slices.

### 7. Partitions

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

### 8. Self-review

- Every acceptance criterion maps to at least one task; no behavior task lacks a criterion.
- Checked against the first list: every consolidated task meets the four conditions of step 5
  (with `low and medium` in the header, a task of `medium` lines meets that paragraph's
  conditions in place of the first, and a `chore` line merged into the task it prepares or
  documents meets step 5's rule for `chore` lines in place of the second) and merges no `high`
  or `property` line, no `medium` line unless the header says `low and medium`, none that needs
  a `- Decision:` field and none that adds a dependency.
- Every behavior of a consolidated task has its own test in `Tests:`, with its criterion.
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

### 9. Approval

Show the ownership table, the threats (if any) and the task list grouped by slice (IDs, titles
and risk only, plus the number of behaviors of each consolidated task) with each slice's
partitions. Then give the plan's totals in one line (`<n> behaviors in <m> tasks`) and, in one
more, why the other tasks stayed apart (`9 stay apart: 5 medium, 3 with another owner, 1 over the
limit`), and say that the user may change the `Consolidation:` line to `none` or to
`low and medium`, naming the tasks that choice would merge (`low and medium` would merge T4–T6).
When the user changes it, merge again with that choice (steps 5 to 8) and show the plan again.
Ask for an explicit yes before setting `Status: Approved`. When called from `develop-feature`,
return control to it.

Present each open decision with its options, advantages, disadvantages and recommendation. The
user picks an option or accepts the recommendation; rewrite the first line of each
`- Decision:` field with the choice, keeping its options below, before approving.
