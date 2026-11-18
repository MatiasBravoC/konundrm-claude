---
type: llm
focus: last_message
---
PASS only if the final message asks the user to approve the plan, lists its tasks, says how many behaviors the consolidated task holds, and gives the plan's totals of behaviors and tasks (for example "5 behaviors in 3 tasks"). FAIL if it reports the plan as approved without asking, leaves out how many behaviors the consolidated task holds or the totals, or reports tests or code already written.
