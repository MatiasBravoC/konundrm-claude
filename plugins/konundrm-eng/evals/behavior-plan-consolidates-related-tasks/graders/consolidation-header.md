---
type: llm
focus: { source: file, path: specs/001-tarjeta/tasks.md }
---
PASS only if the plan's header has a line `- **Consolidation:**` whose value starts with `low` and holds the plan's totals as `<n> behaviors in <m> tasks`, with more behaviors than tasks. FAIL if the line is missing, if its value is `none` or `low and medium`, or if it has no totals.
