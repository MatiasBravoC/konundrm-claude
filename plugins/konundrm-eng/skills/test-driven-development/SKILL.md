---
name: test-driven-development
description: Writes the next failing test, one behavior at a time, and stops at red. Never writes or edits the implementation, not even a stub; making the test pass is handed to the user, the implementer subagent or designing-modules, and the next test is written only after the previous one is verified green. Use when the user says "hagamos esto con TDD", "test-driven", "test-first", "escribe el test primero" or "red-green-refactor", or when a task from tasks.md needs its failing test. For code that already exists without tests, use adding-test-coverage instead.
argument-hint: "[behavior or task ID]"
---

# Test-Driven Development

**Iron law: no production code without a failing test first.** This skill owns the red step and
only the red step. A test written next to the code it tests gets shaped by that code; the hard
stop between red and green is what keeps the test honest.

## Contract

- **Receives:** one behavior to specify, either a task from `tasks.md` (with its test path, test
  name and requirement IDs) or a request from the user. Only for the test-writer subagent, a task
  may list several behaviors under `Tests:`.
- **Produces:** exactly one new failing test (for the test-writer subagent on a task with a
  `Tests:` list, one per listed behavior), evidence that each fails for the right reason, and a
  handoff report per test (format below). Never production code.

## Workflow

### 0. Decompose (only when there is no tasks.md)

List the behaviors as small testable steps, ordered simple to complex: happy path, boundaries
(empty, zero, exactly at the threshold, first and last), invalid input and errors, interactions
and side effects. Then list the **invariants** the behavior must keep for every input (see
"Properties" below); each one becomes a property test after the example tests that pin down the
basic cases. Show the list to the user before the first test; it is the cheapest moment to
catch a missing case.

### 1. RED: write one test

Write a single test for the next uncovered behavior, following Standards → Tests for location,
naming and structure. Then run only that test and read the failure. It must fail **because the
behavior is missing**:

- Good: the assertion fails, or the symbol under construction does not exist yet.
- Bad: a typo, a broken import of something that should exist, a fixture error, a syntax error.
  Fix the test and rerun.
- A test that passes immediately specifies nothing new for this cycle. Working with the user,
  delete it or pick a different behavior. As the test-writer subagent, keep it if it asserts the
  task's criterion (an earlier task may already have built the behavior) and return a
  CHARACTERIZATION report (format below) instead of a RED one; the orchestrator decides.

Without a test runner, trace the test by hand and state exactly why it cannot pass yet.

#### Properties

When the task asks for a property, or the logic has an invariant (Standards → Tests), the one
test you write is a property test (Hypothesis, fast-check). It checks a rule over generated
inputs instead of one example, which catches the edge cases nobody thought to write down:

| Pattern | Example |
| --- | --- |
| Round-trip | `parse(format(rut)) == rut` |
| Invariant | the result is sorted and has the same elements as the input |
| Reference model | the fast implementation agrees with an obviously correct slow one |
| Idempotence | `normalize(normalize(x)) == normalize(x)` |
| Metamorphic | doubling every line price doubles the order total |

Constrain the generators to the valid domain the spec defines; invalid inputs belong to their own
example tests. A property is red for the right reason when the function is missing, or when the
runner reports a counterexample that violates the rule. Put the shrunk counterexample in the
handoff report.

#### A task with several tests

A task from `tasks.md` may list several tests under `Tests:`: writing-plans merges related
low-risk behaviors into one task. Running as the **test-writer subagent** on such a task, write
every test of that list before you stop, still one behavior per test. The implementer has not
run yet, so each test is seen failing first, and the implementer then makes them pass one at a
time, seeing each one red before its code. Run them with the task's verify command and return one
RED report per test, in the task's order, or a CHARACTERIZATION report for a test that already
passes. The property tests a dispatch adds for the task's invariants are part of that list.
Working with the user, or on a task with a single `Test:` line, the rule does not change: one
test, then stop.

### 2. Stop and hand off

Report in this format, then stop:

```
RED: <behavior>
Test: <path>::<name>   Covers: <requirement IDs or "—">
Command: <exact command run>
Failure: <the decisive failure line>
Right reason: <why this failure means the behavior is missing>
To make it pass: <what the minimal change must do, described in words, not code>
```

- Running as the **test-writer subagent:** return the report; the orchestrator dispatches the implementer.
- Running **with the user:** ask them to implement it, or offer to hand it to `designing-modules`.
  Do not continue to the next test in the same turn.

A test that passes on the current code (behavior already present, a characterization test before
a change, or a test written to kill a surviving mutant) gets this report instead:

```
CHARACTERIZATION: <behavior or invariant>
Test: <path>::<name>   Covers: <requirement IDs or "—">
Command: <exact command run> → pass
Why it passes: <the code that already implements it, file:line>
Guards against: <the regression or mutated line it would catch>
```

### 3. Verify green before the next test

When resumed, run the test from step 1 five times in a row, then the suite so far (Standards →
Tests: five runs before it lands). Write the next test only when every run is green and nothing
earlier broke. If it is still red, say so precisely and stay on it. If it passes only some of the
time, it is flaky: fix the test's source of nondeterminism before anything else, and never
retry, skip or mark it as an expected failure to get past it.

### 4. Repeat, then audit

Continue until the behavior list is exhausted. Then read the finished implementation cold: every
branch, raised error and condition should trace back to a test. Each gap goes through the same
red → stop → verify cycle.

## Boundaries

- You may refactor the **test file** (fixtures, parametrization, grouping). You may not rename,
  restructure or touch the code under test, even when you can see the improvement.
- When a new project lacks the test-runner setup the test needs to import its target (pytest's
  `pythonpath`, a `conftest.py`, a vitest config), you may add that minimal configuration and
  must list it in the handoff. It never contains the behavior under test.
- Characterization tests for existing, working code already pass by definition; they get the
  CHARACTERIZATION report instead of the RED handoff. Everything else does not.
- A regression test for a bug is an ordinary RED test: it reproduces the bug as reported and
  fails for that reason. "Right reason" quotes the symptom from the report.
- Never commit a focused or skipped test (`.only`, `xit`, an unexplained skip): Standards → Gate
  integrity, and the plugin's hooks reject them.

## Red flags: stop if you think…

| Thought | Reality |
| --- | --- |
| "I'll add a quick stub so it compiles." | The stub is implementation. Report the missing symbol instead. |
| "This is too simple to fail, skip running it." | Run it. A test never seen failing proves nothing. |
| "I'll write the next two tests to save a round trip." | Batching tests breaks the cycle. One test, one stop. Only the test-writer subagent, on a task that lists several tests, writes them in one dispatch. |
| "The test is hard to write; I'll test the internals." | Hard to test means the design needs a seam. Say so in the handoff. |
| "Three examples are enough for this parser." | Examples cover the cases you thought of. Add the round-trip property. |

## Example

Behavior: "reject passwords shorter than 8 characters" (`R1.1`).

```
RED: rejects passwords shorter than 8 characters
Test: tests/auth/test_password_policy.py::test_rejects_password_shorter_than_8_chars   Covers: R1.1
Command: pytest tests/auth/test_password_policy.py::test_rejects_password_shorter_than_8_chars
Failure: ModuleNotFoundError: No module named 'auth.password_policy'
Right reason: the module under construction does not exist yet; the test itself imports and runs.
To make it pass: create auth/password_policy.py with validate_password(pw) returning a list of
violations that includes "too_short" when len(pw) < 8.
```
