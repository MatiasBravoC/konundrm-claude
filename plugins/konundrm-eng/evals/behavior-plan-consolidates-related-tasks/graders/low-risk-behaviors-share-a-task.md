---
type: llm
focus: { source: file, path: specs/001-tarjeta/tasks.md }
---
PASS only if all of these hold: at least one task is a consolidated task, with a `Tests:` list of two or more tests, `Risk: low` and a `Covers:` field that names the criterion of each of those tests; the four contact-card criteria (R1.1 to R1.4) are covered by fewer than four tasks; and each test of a `Tests:` list says which behavior or criterion it asserts. FAIL if every task has a single test, if a task with a `Tests:` list is `Risk: medium` or `Risk: high`, or if one of R1.1 to R1.4 has no test of its own.
