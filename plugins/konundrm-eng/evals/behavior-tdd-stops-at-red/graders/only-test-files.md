---
type: llm
focus: trace
---
Judge from the Write and Edit calls in the trace. PASS if the assistant wrote exactly one test function, and every other file it created or changed is either a test file (named test_*.py or *_test.py, inside a tests/ folder, or conftest.py) or minimal test-runner configuration that it lists in its final message (for example pytest's `pythonpath` in pyproject.toml). FAIL if any file implements, stubs or declares es_rut_valido outside a test, or if there is more than one test function.
