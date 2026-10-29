# Tasks: <Feature name>

- **Spec:** [requirements.md](requirements.md) · **Design:** [design.md](design.md)
- **Status:** Draft <!-- Draft → Approved → Done -->
- **Check command:** `<npm run check | poe check | make check>`
- **Base commit:** `<SHA the feature branch started from>`
- **Pull request budget:** <400> changed lines per slice

<!-- One task = one red-green-refactor cycle = one commit. develop-feature checks the box and adds
a "Rounds" line (review rounds and escalations, read by the impact report) in the task's own
commit, so a checked box without a "Task: T<n>" commit means that commit failed.
Types: behavior (needs a failing test first), property (a property test for an invariant) or
chore (no test; verify only). Risk: low | medium | high (Standards → Verification by risk)
decides the extra verification each task gets.
A slice is one pull request: it merges on its own, leaves the main branch green and fits the
budget. Until its last slice lands, a user-visible feature stays unreachable (not wired to an
entry point, or behind a flag). -->

## Slice S1: <what this pull request delivers, in one line>

- [ ] **T1** <Behavior, stated as what the system does> · `behavior` · Risk: low · Covers: R1.1
  - Test: `tests/<path>/test_<module>.py::test_<behavior>`
  - Files: `src/<path>/<module>.py` (new)
  - Verify: `<command that runs only this test>`
  - Depends on: —

- [ ] **T2** <Invariant, stated as a rule for every valid input> · `property` · Risk: medium · Covers: R1.2
  - Test: `tests/<path>/test_<module>.py::test_<invariant>_for_any_<input>`
  - Generator domain: <the valid inputs the spec allows>
  - Invariants: <the rule this property checks>
  - Files: `src/<path>/<module>.py` (modify)
  - Verify: `<command>`
  - Depends on: T1

## Slice S2: <what this pull request delivers, in one line>

- [ ] **T3** <Behavior touching money, auth, personal data, data deletion or an external contract> · `behavior` · Risk: high · Covers: R2.1
  - Test: `tests/<path>/test_<module>.py::test_<behavior>`
  - Files: `src/<path>/<module>.py` (modify)
  - Verify: `<command>`
  - Invariants: <every rule that must hold for all valid inputs, each with a property test>
  - Mutation: `<mutation tool scoped to the changed code>`
  - Security: <what the security review must look at: the trust boundary and the threat from design.md>
  - Evidence: `<end-to-end check of the real application; saved under evidence/>`
  - Depends on: T2

- [ ] **T4** <Configuration or scaffolding step> · `chore` · Risk: low · Covers: —
  - Files: `<path>`
  - Verify: `<command whose success proves the step>`
  - Depends on: —

<!-- Example of a finished task, as develop-feature leaves it:
- [x] **T1** … · `behavior` · Risk: low · Covers: R1.1
  - Rounds: spec 1 · code 1 · escalations 0
-->
