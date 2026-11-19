---
type: llm
focus: trace
---
Judge the part of the trace where the second change the user left for later is made: an empty or blank name now returns `Hola, desconocido.`. PASS only if all of these hold: the orchestrator edited the acceptance criterion in `specs/001-saludo/requirements.md` before dispatching a writer for this change; a `test-writer` subagent changed or added the test first, and that test was run and seen failing before an `implementer` subagent changed `saludo.py`; the orchestrator ran the changed test itself after the implementer; a `spec-reviewer` subagent was dispatched for this change, alone or with a `code-reviewer`; and it landed in a commit of its own. FAIL if the code changed before a failing test existed, if the spec review was skipped, if the orchestrator wrote the test or the code itself, or if the change became a new task in the plan.
