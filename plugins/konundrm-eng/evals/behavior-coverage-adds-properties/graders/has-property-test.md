---
type: llm
focus: trace
---
Judge from the content of the Write and Edit calls in the trace. PASS if the test files include at least one property-based test (Hypothesis `@given`, or an equivalent generator-driven test) that checks a rule the docstring promises for every input, such as: the slug is lowercase ASCII, contains no double hyphens, has no leading or trailing hyphen, or slugify is idempotent. Example-only tests FAIL.
