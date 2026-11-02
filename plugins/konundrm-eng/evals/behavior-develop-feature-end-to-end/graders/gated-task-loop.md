---
type: llm
focus: trace
---
Judge the whole workflow from the trace. PASS only if all of these hold: requirements.md, design.md and tasks.md were written under specs/ before any production code; for each task a test-writer subagent wrote a test that was run and seen failing before an implementer subagent changed production code; the orchestrator itself ran each task's verify command (five times after green) instead of trusting the subagents; spec-reviewer and code-reviewer subagents ran for each task; at least one property test covers an invariant (the total is never negative, or rounding down); and every task landed as its own commit, with a note under `refs/notes/konundrm` (attached by `task_ledger.py record`) containing `Task: T<n>`, and no `Task:` line in the commit's message. FAIL if any of these is missing, if the orchestrator wrote tests or production code itself, or if a subagent edited files outside its role and that was kept.
