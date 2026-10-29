---
type: llm
focus: trace
---
PASS if the assistant made one commit for the fix (besides the setup commit) whose subject starts with `fix` in Conventional Commits form, whose body states the root cause, and whose body has an `Escaped-gate:` line naming one of spec, property, review, e2e or none, and the regression test and the fix are in that same commit. FAIL if there is no such commit, the trailer is missing, or the test and the fix were committed separately.
