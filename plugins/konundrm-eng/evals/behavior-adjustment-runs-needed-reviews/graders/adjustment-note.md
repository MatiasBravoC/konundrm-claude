---
type: tool_used
tool: Bash
input_match: 'git\s+notes\s+--ref[= ]refs/notes/konundrm\s+add[\s\S]*Adjusts:[\s\S]*Reviews:[\s\S]*Asked:'
---
Each adjustment's commit gets a note under `refs/notes/konundrm` that names the task it adjusts (`Adjusts:`), the reviews that ran (`Reviews:`) and what the user asked (`Asked:`), written in the same command as the commit.
