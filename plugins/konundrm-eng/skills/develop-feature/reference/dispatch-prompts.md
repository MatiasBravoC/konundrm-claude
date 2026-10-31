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
- finding-verifier
- test-writer (surviving mutant)
- test-writer (flaky test)
- rethinker
- process-reviewer

## test-writer

```
Feature folder: specs/<NNN-slug>/ (requirements.md, design.md, tasks.md)
Check command: <command>

Task:
<task block from tasks.md>

Acceptance criteria covered:
<EARS lines for the IDs in "Covers">

Write exactly one test for this task at the path and name the task gives (a property test when
the task type is `property`, over the domain it states). Run it. If it fails because the behavior
is missing, return your RED report. If it already passes because the behavior exists, return a
CHARACTERIZATION report. Do not create or edit any non-test file.
```

## implementer

```
Feature folder: specs/<NNN-slug>/ — follow design.md
Check command: <command>

Task:
<task block from tasks.md>

Failing test: <path>::<name>
RED report:
<RED report from test-writer>

Make the failing test pass with the minimal change that fits the design, then refactor with every
test green. Do not edit test files. Return your GREEN report.
```

For a `chore` task, replace the failing-test lines with: `No test for this task. Done when the
verify command succeeds: <command>`.

## implementer (fix round)

```
Fix round. Feature folder: specs/<NNN-slug>/ — follow design.md
Check command: <command>
Task: <task block from tasks.md>
Task test: <path>::<name> — verify command: <command>

Problems to resolve (findings, a failing property's counterexample, or the check failure),
verbatim, with file:line:
<items>

The task's test is already green: skip your red check. Fix the problems without editing test
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

Orchestrator's verification output (verify command, 5 runs): <output>

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
Orchestrator's verification output (verify command, 5 runs): <output>

Review the uncommitted changes (`git diff HEAD`, plus untracked files from
`git status --porcelain`). Return your CODE REVIEW.
```

## security-reviewer

```
Feature folder: specs/<NNN-slug>/ (design.md holds the Threats table)
Task: <task ID and title> · Risk: high
Security focus (the task's Security line, verbatim):
<Security: …>
Orchestrator's verification output (verify command, 5 runs): <output>

Review the uncommitted changes (`git diff HEAD`, plus untracked files from
`git status --porcelain`) as an attacker would. Check every Threats row this task covers. Return
your SECURITY REVIEW.
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

Propose improvements to the plugin's workflow from this record, in general terms, without the
project's code, names or data. Do not change any file. Return your IMPROVEMENT NOTES report.
```
