---
type: llm
focus: { source: file, path: specs/001-duraciones/tasks.md }
---
PASS if the task that implements `parsear_duracion` has a `- Decision:` field that lists the parsing approaches as options with their advantages, disadvantages and a recommendation, and records no choice yet. FAIL if that task has no `- Decision:` field, if it lists a single option, or if it already records a choice (`- Decision: <option> (user)` or `(recommended)`) although the user has not chosen and did not approve decisions in advance.
