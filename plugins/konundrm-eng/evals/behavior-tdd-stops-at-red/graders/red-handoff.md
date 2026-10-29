---
type: llm
focus: last_message
---
PASS if the final message is a red-step handoff: a line starting with 'RED:' that names the behavior, plus the test's path and name, the failure (or why it cannot pass yet), and what the minimal implementation must do described in words rather than code; and it stops instead of implementing. FAIL if it implements the function, writes the next test, or has no 'RED:' line.
