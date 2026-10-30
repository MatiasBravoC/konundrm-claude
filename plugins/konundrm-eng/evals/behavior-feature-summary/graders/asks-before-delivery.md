---
type: llm
focus: last_message
---
PASS if the final message points to the feature summary (`specs/001-calendario/summary.md`) and asks for explicit approval before pushing any branch or opening any pull request, without reporting that it already pushed or opened one. FAIL if it does not mention the feature summary, if it pushed or opened a pull request, or if it ends without asking.
