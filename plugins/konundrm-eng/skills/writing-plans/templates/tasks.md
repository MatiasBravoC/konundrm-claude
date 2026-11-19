# Tasks: <Feature name>

- **Spec:** [requirements.md](requirements.md) · **Design:** [design.md](design.md)
- **Status:** Draft <!-- Draft → Approved → Done -->
- **Check command:** `<npm run check | poe check | make check>`
- **Base commit:** `<SHA the feature branch started from>`
- **Pull request budget:** <500> changed lines of code and tests per slice
- **Consolidation:** low <!-- low | low and medium | none: which related behaviors writing-plans
merges into one task (up to 5 behaviors and about 300 changed lines; "low and medium" also merges
the cases of one medium rule, up to 3). The user may change it when approving the plan. Once the
tasks are written it also holds the totals: low · <n> behaviors in <m> tasks -->
- **Parallel:** no <!-- yes | no: whether the partitions of one wave may be built at the same time -->
- **Checkpoints:** ask <!-- ask | pre-approved: pre-approved when the user approved the pauses
between slices in advance (in the request or when approving the plan) -->
- **Decisions:** ask <!-- ask | pre-approved: pre-approved when the user approved the open decisions
in advance (in the request or when approving the plan), apart from the pauses -->
- **Sessions:** per-slice <!-- per-slice | single: single when the user asked to build the whole
feature in one session (in the request, when approving the plan or at a pause) -->
- **Publish:** local <!-- local | live: live only when the user said yes, or asked for it, to
publishing the feature on GitHub while it is built (develop-feature asks at plan approval) -->

<!-- One task = one red-green-refactor cycle = one commit. A task holds one behavior, or up to five
related low-risk behaviors that writing-plans merged (a consolidated task), each with its own test
under "Tests:". develop-feature checks the box and adds
a "Rounds" line (review rounds and escalations, read by the impact report) at the slice's pause
(`task_ledger.py close-slice`, in the slice's summary commit), from the task's "Task: T<n>" commit.
Types: behavior (needs a failing test first), property (a property test for an invariant) or
chore (no test; verify only). Risk: low | medium | high (Standards → Verification by risk)
decides the extra verification each task gets.
A slice is one pull request: it merges on its own, leaves the main branch green and fits the
budget. Until its last slice lands, a user-visible feature stays unreachable (not wired to an
entry point, or behind a flag).
Each slice ends with its Partitions table. A partition is a group of tasks one session builds, in
order; partition IDs are unique across the whole feature. Waves run in order; within a wave no
partition depends on another or shares files with another (except tasks.md and the evidence),
and a wave holds at most three partitions. "Depends on" lists the partitions it waits for. -->

## Slice S1: <what this pull request delivers, in one line>

- [ ] **T1** <Behavior, stated as what the system does> · `behavior` · Risk: low · Covers: R1.1
  - Test: `tests/<path>/test_<module>.py::test_<behavior>`
  - Files: `src/<path>/<module>.py` (new)
  - Verify: `<command that runs only this test>`
  - Depends on: —
  - Decision: <what to choose; only when the task has two or more reasonable approaches>
    - Option A: <approach> · pros: <…> · cons: <…>
    - Option B: <approach> · pros: <…> · cons: <…>
    - Recommendation: <option, and why>

- [ ] **T2** <What the related behaviors deliver together, in one statement> · `behavior` · Risk: low · Covers: R1.2, R1.3
  - Tests:
    - `tests/<path>/test_<module>.py::test_<behavior>`: <behavior> (R1.2)
    - `tests/<path>/test_<module>.py::test_<other_behavior>`: <other behavior> (R1.3)
  - Files: `src/<path>/<module>.py` (modify)
  - Verify: `<command that runs only these tests>`
  - Depends on: T1

- [ ] **T3** <Invariant, stated as a rule for every valid input> · `property` · Risk: medium · Covers: R1.4
  - Test: `tests/<path>/test_<module>.py::test_<invariant>_for_any_<input>`
  - Generator domain: <the valid inputs the spec allows>
  - Invariants: <the rule this property checks>
  - Files: `src/<path>/<module>.py` (modify)
  - Verify: `<command>`
  - Depends on: T2

### Partitions

| Wave | Partition | Tasks | Depends on |
| --- | --- | --- | --- |
| 1 | P1 | T1–T3 | — |

## Slice S2: <what this pull request delivers, in one line>

- [ ] **T4** <Behavior touching money, auth, personal data, data deletion or an external contract> · `behavior` · Risk: high · Covers: R2.1
  - Test: `tests/<path>/test_<module>.py::test_<behavior>`
  - Files: `src/<path>/<module>.py` (modify)
  - Verify: `<command>`
  - Invariants: <every rule that must hold for all valid inputs, each with a property test>
  - Mutation: `<mutation tool scoped to the changed code>`
  - Security: <what the security review must look at: the trust boundary and the threat from design.md>
  - Evidence: `<end-to-end check of the real application; saved under evidence/>`
  - Depends on: T3

- [ ] **T5** <Configuration or scaffolding step> · `chore` · Risk: low · Covers: —
  - Files: `<path>`
  - Verify: `<command whose success proves the step>`
  - Depends on: —

### Partitions

<!-- P2 and P3 share a wave: neither depends on the other and they touch different files. -->

| Wave | Partition | Tasks | Depends on |
| --- | --- | --- | --- |
| 1 | P2 | T4 | — |
| 1 | P3 | T5 | — |

<!-- Example of a finished task, as develop-feature leaves it:
- [x] **T1** … · `behavior` · Risk: low · Covers: R1.1
  - Decision: Option A (user)
    - Option A: <approach> · pros: <…> · cons: <…>
    - Option B: <approach> · pros: <…> · cons: <…>
    - Recommendation: <option, and why>
  - Change: <a change the user asked for while the task was being built, verbatim> (user)
  - Rounds: spec 1 · code 1 · escalations 0
-->
