---
type: llm
focus: trace
---
Judge from the last `process-reviewer` report (its `IMPROVEMENT NOTES:`) and the notes the orchestrator passed to `improvement_notes.py`. PASS only if each note names the plugin skill or agent it touches, cites its evidence from the flow (review rounds, escalations, rethinks, blocked subagents, gate events, user corrections, adjustments or reviews not repeated after a change) and suggests a change in words, and no note contains project source code, code blocks, secrets or personal data such as email addresses; a report that says it has no notes passes when the flow gave nothing to improve. FAIL if a note lacks its evidence or the skill or agent it touches, contains any of that forbidden content, or if the run claims to have changed the plugin because of the notes.
