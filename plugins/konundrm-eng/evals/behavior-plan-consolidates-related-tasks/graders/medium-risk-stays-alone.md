---
type: llm
focus: { source: file, path: specs/001-tarjeta/tasks.md }
---
PASS if every task that covers R2.1 (the count of contacts per e-mail domain, whose counts add up to the total) is `Risk: medium` or `Risk: high`, covers no contact-card criterion (R1.1 to R1.4) and holds one behavior or one property: a single `Test:` line, not a `Tests:` list. FAIL if R2.1 shares a task with a contact-card criterion, if a task that lists several tests covers R2.1, or if a task covering R2.1 is `Risk: low`.
