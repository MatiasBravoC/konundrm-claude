---
type: llm
focus: trace
---
PASS if the assistant made one commit for the fix (besides the setup commit) whose subject starts with `fix` in Conventional Commits form and whose body states the root cause, the regression test and the fix are in that same commit, and right after it a note under `refs/notes/konundrm` (a `git notes --ref=refs/notes/konundrm add ... HEAD` command, or the note it wrote) has an `Escaped-gate:` line naming one of spec, property, review, e2e or none. FAIL if there is no such commit, if no such note names the escaped gate, if the commit's body carries an `Escaped-gate:` line instead of the note, or if the test and the fix were committed separately.
