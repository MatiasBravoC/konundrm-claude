# Dispatch prompts

Fill the `<…>` placeholders and paste the task block and requirement lines **verbatim** from
`tasks.md` and `requirements.md`. Subagents start with a clean context: everything they need must
be in the prompt or in a file the prompt names. Pass the Agent tool's `model` and `effort` only
where [Model and effort](../SKILL.md#model-and-effort) lists them.

## Contents

- test-writer
- implementer
- implementer (fix round)
- spec-reviewer (task)
- spec-reviewer (whole feature)
- code-reviewer
- security-reviewer
- re-review
- finding-verifier
- test-writer (surviving mutant)
- test-writer (flaky test)
- rethinker
- process-reviewer
- test-writer (adjustment)
- implementer (adjustment)
- adjustment review

## test-writer

```
Feature folder: specs/<NNN-slug>/ (requirements.md, design.md, tasks.md)
Check command: <command>

Task:
<task block from tasks.md>

Acceptance criteria covered:
<EARS lines for the IDs in "Covers">

Property tests to write too (leave this paragraph out on a `low` task, or when there is none):
<each of the task's `Invariants` that no `property` task covers>

Write the task's tests at the paths and names the task gives: the one on its `Test:` line, or
every test of its `Tests:` list, one test per behavior (a property test when the task type is
`property`, over the domain it states). Run them with the task's verify command. For each test,
return a RED report if it fails because its behavior is missing, or a CHARACTERIZATION report if
it already passes because the behavior exists. Do not create or edit any non-test file.
```

When step 1 sends one test back (it errored for another reason, passed with a RED report or does
not assert its criterion), add this paragraph above the last one, so the tests that are ready stay
untouched:

```
Tests already written, to leave exactly as they are: <path>::<name>, one per test
Write or fix only: <path>::<name> — <what was wrong: the output, or the criterion it misses>
```

## implementer

```
Feature folder: specs/<NNN-slug>/ — follow design.md
Check command: <command>

Task:
<task block from tasks.md>

Failing tests: <path>::<name>, one per test of the task
RED reports:
<RED and CHARACTERIZATION reports from test-writer, one per test>

Make every failing test pass with the minimal change that fits the design, one test at a time and
in the task's order: before you write a test's code, run that test and see it still fail. Then
refactor with every test green. Do not edit test files. Return your GREEN report.
```

For a `chore` task, replace the failing-test lines with: `No test for this task. Done when the
verify command succeeds: <command>`.

## implementer (fix round)

```
Fix round. Feature folder: specs/<NNN-slug>/ — follow design.md
Check command: <command>
Task: <task block from tasks.md>
Task tests: <path>::<name>, one per test of the task — verify command: <command>

Problems to resolve (findings, a failing property's counterexample, or the check failure),
verbatim, with file:line:
<items>

The task's tests are already green: skip your red check. Fix the problems without editing test
files. If one can only be fixed by changing a test, say so in your report instead of working
around it. Rerun the verify and check commands and return your GREEN report.
```

## spec-reviewer (task)

```
Feature folder: specs/<NNN-slug>/
Task:
<task block>

Acceptance criteria covered:
<EARS lines>

Implementer's GREEN report (claims to verify, not facts):
<GREEN report>

Orchestrator's verification output (verify command: 5 runs, or 1 for a `chore` task): <output>

Review the uncommitted changes (`git diff HEAD`, plus untracked files from
`git status --porcelain`). Return your SPEC REVIEW.
```

## spec-reviewer (whole feature)

```
Feature folder: specs/<NNN-slug>/ — review against every criterion in requirements.md.
Changes: `git diff <base-sha>..HEAD`.
Orchestrator's check output (Phase 4): <output>

Check that every acceptance criterion is implemented and asserted by at least one test, and that
nothing outside the spec was built. Return your SPEC REVIEW with the task field set to "feature".
```

## code-reviewer

```
Feature folder: specs/<NNN-slug>/ (design.md is the intended design)
Task: <task ID and title>
Check command: <command> — implementer's GREEN report says: <its Check line>
(the orchestrator runs the full check at the gate)
Orchestrator's verification output (verify command: 5 runs, or 1 for a `chore` task): <output>

Review the uncommitted changes (`git diff HEAD`, plus untracked files from
`git status --porcelain`). Return your CODE REVIEW.
```

## security-reviewer

```
Feature folder: specs/<NNN-slug>/ (design.md holds the Threats table)
Task: <task ID and title> · Risk: high
Security focus (the task's Security line, verbatim):
<Security: …>
Orchestrator's verification output (verify command: 5 runs, or 1 for a `chore` task): <output>

Review the uncommitted changes (`git diff HEAD`, plus untracked files from
`git status --porcelain`) as an attacker would. Check every Threats row this task covers. Return
your SECURITY REVIEW.
```

## re-review

For the spec, code or security reviewer after a fix round, or after any other change that
[Reviews after a change](../SKILL.md#reviews-after-a-change) sends back to it. Start from that
reviewer's prompt above and keep its lines up to the task's criteria or Security line; replace the
rest with:

```
Re-review after a fix round. Your previous findings on this task, verbatim (or "none"):
<previous findings of this review>

Reports of every fix round since this review last ran (each file changed and what changed in it):
<files changed and their changes, from those rounds' GREEN and RED reports>

What the last round changed (`git diff --stat <sha>`, against the tree marked before the round):
<output>

Change the user asked for during this task, verbatim (a criterion for this review, also on the
task's `- Change:` line; leave this paragraph out when there is none):
<request>

Orchestrator's verification output after the fix round (verify command: 5 runs, or 1 for a
`chore` task): <output>

Reread the files those rounds changed. Check that each previous finding is resolved and that the
changes broke nothing. Review what changed, not the whole task. Return the same review report as
before.
```

## finding-verifier

```
Feature folder: specs/<NNN-slug>/
Task: <task ID and title> · Risk: <level>

Finding to verify (from the code review, verbatim):
<one Critical finding with file:line>

Try to prove this finding wrong. Reproduce it only in a temporary directory outside the
repository, never by editing project files. Return your FINDING CHECK.
```

## test-writer (surviving mutant)

```
Feature folder: specs/<NNN-slug>/
Task: <task ID and title>
Check command: <command>
Task test file: <path> — verify command for the new test: <command with the new test's name>

Mutation testing left this mutant alive (the tests still pass with it):
<mutant: file:line, original → mutated>

Write one test in the task's test file that fails with the mutant and passes with the current
code. It passes on the current code by design: return a CHARACTERIZATION report naming the
mutated line it guards.
```

## test-writer (flaky test)

```
Feature folder: specs/<NNN-slug>/
Task: <task ID and title>
Test: <path>::<name> — verify command: <command>

Run five times in a row, this test passed <n> times and failed <m> times. A failing run's output:
<decisive lines>

Find why the test is nondeterministic (shared state between tests, test order, real time or
timezone, unseeded randomness, concurrency, network) and fix the test so it passes every run.
Do not add retries, sleeps that hide a race, or a skip. If the nondeterminism is in the
production code, describe it instead of changing that code. Run the verify command five times
and return your report with the five results.
```

## rethinker

```
Feature folder: specs/<NNN-slug>/ (requirements.md, design.md, tasks.md)
Check command: <command>

Task:
<task block from tasks.md>

Acceptance criteria covered:
<EARS lines for the IDs in "Covers">

This task has failed <n> reviews. Every finding so far, verbatim and in order, each with the
review and round it came from:
<findings>

Latest RED and GREEN reports:
<reports>

Find why the attempts keep failing and what to do differently. The attempt is uncommitted: read
it with `git diff HEAD`, plus untracked files from `git status --porcelain`, and the code around
it. Do not change any file. Return your RETHINK report.
```

## process-reviewer

```
Feature folder: specs/<NNN-slug>/ (requirements.md, design.md, tasks.md)
Scope: <slice S<k> or feature>
Commits in scope: <base>..HEAD

Flow record for this scope:
- Review rounds: the `Rounds:` lines of the scope's tasks in tasks.md, and the findings of each
  round: <findings, in order, each with its task and round>
- Escalations: <each time a task went to the user, and why, or "none">
- Rethinks: the specs/<NNN-slug>/evidence/T<n>-rethink.md files of the scope's tasks
- Blocked subagents: <each report that came back Status: BLOCKED, with its reason, or "none">
- Gate events: the gates section of
  `sh "${CLAUDE_PLUGIN_ROOT}/hooks/run.sh" metrics_report.py --days <days since the scope began>`
- User corrections: <what the user corrected or overrode, or "none">, and the slice summaries in
  specs/<NNN-slug>/summaries/
- Adjustments, and reviews not repeated after a change: <each one, with the reviews that ran and
  why the others did not, or "none">

Propose improvements to the plugin's workflow from this record, in general terms, without the
project's code, names or data. Do not change any file. Return your IMPROVEMENT NOTES report.
```

## test-writer (adjustment)

For an [adjustment](adjustments.md), or a change the user asks for on the task in progress, whose
request changes what the code does for some input or something a test asserts.

```
Adjustment to work already built. Feature folder: specs/<NNN-slug>/
Check command: <command>

Task it adjusts:
<task block from tasks.md>

Acceptance criteria covered, as they read now (a criterion the request changes is already edited):
<EARS lines for the IDs in "Covers">

Change the user asked for, verbatim:
<request>

Find every test that asserts what the request changes (search the test folders for the old text
or value) and change each one to assert what the request asks for; add a test in the task's test
file when none asserts it. Leave every other test as it is. Run the tests you changed or added:
each must fail because the code still does what it did. Return a RED report for each one. Do not
create or edit any non-test file.
```

## implementer (adjustment)

```
Adjustment to work already built. Feature folder: specs/<NNN-slug>/ — follow design.md
Check command: <command>

Task it adjusts:
<task block from tasks.md>
Verify command: <command>

Change the user asked for, verbatim:
<request>

<RED reports from the test-writer | No test changes for this adjustment: the task's tests are
green, so skip your red check and keep them green. If the request cannot be met without changing
what the code does for some input, or without changing a test, change nothing and return
`Status: BLOCKED` naming that behavior: its test comes first.>

Make the change with the smallest edit that fits the design, and nothing the request does not ask
for. Do not edit test files. Rerun the verify and check commands and return your GREEN report.
```

## adjustment review

For the spec or code reviewer after an adjustment (the security reviewer too when the user asks
for it). Start from that reviewer's prompt above and keep its lines up to the task's criteria;
replace the rest with:

```
The task was reviewed and committed before. The user then asked for this change, verbatim:
<request>
The criteria above read as they do after this change: the request and those criteria are what the
change must meet.

Files the adjustment changed and what changed in each:
<files changed and their changes, from the writers' reports>

Orchestrator's verification output after the adjustment (the tests it changed or added: 5 runs;
the task's verify command: 1 run): <output>

Review the uncommitted changes (`git diff HEAD`, plus untracked files from
`git status --porcelain`): they are the adjustment alone, not the whole task. Return the same
review report as for a task.
```
