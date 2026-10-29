---
type: llm
focus: trace
---
PASS if the assistant created at least one commit whose header has the Conventional Commits form '<type>(<scope>): <imperative summary>' (scope optional, no emoji or other prefix before the type), in English, at most 72 characters, and its final message asks for explicit approval before pushing. FAIL if no commit was made, the header breaks that format, or it pushed or offered no push confirmation.
