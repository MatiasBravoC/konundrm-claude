---
name: adding-test-coverage
description: Backfills tests for code that already exists. Measures current coverage, writes unit tests for every real branch and error path of the selected modules, adds integration tests only for critical cross-module flows, and checks test strength with mutation testing when available. Tests mirror the source tree and are named after the behavior they verify. Use when the user says "testea este módulo", "genera tests", "revisa el coverage", "quiero tests unitarios" or "cubre esto con tests", or for legacy code with no tests. For new behavior that does not exist yet, use test-driven-development instead.
argument-hint: "[module or path]"
---

# Adding Test Coverage

Coverage proves code ran, not that it was checked. The goal is tests that would fail if the
behavior broke, organized so the test tree reads as a mirror of the source tree.

## Contract

- **Receives:** one or more existing modules (`$ARGUMENTS` or the conversation).
- **Produces:** passing tests that cover every real branch, the before/after coverage numbers, the
  mutation score when a tool is configured, and a list of deliberate exclusions with reasons.

## Workflow

```
- [ ] 1. Measure what exists
- [ ] 2. Enumerate behaviors per public symbol
- [ ] 3. Write the tests
- [ ] 4. Check strength
- [ ] 5. Verify organization
- [ ] 6. Report
```

### 1. Measure

Find existing tests in the project's conventional locations. Run coverage with branch measurement
(`pytest --cov=<pkg> --cov-branch --cov-report=term-missing`, `vitest run --coverage`,
`jest --coverage`). Without tooling, enumerate branches by reading the code.

### 2. Enumerate behaviors

For each public function, method or component in scope, list: the normal cases (one per input
shape or range the logic branches on), every validation and error path, boundaries implied by the
logic (zero, empty, exactly at a threshold), and promised side effects.

Then infer its **properties** from the signature, the doc-comment and the callers: round-trips,
invariants, idempotence, agreement with a simpler reference, metamorphic relations (patterns in
the `test-driven-development` skill). The doc-comment's promises are the contract; each promise
that holds for all inputs becomes a property test (Standards → Tests).

Skip code without logic of its own (re-exports, trivial getters). For truly unreachable code, add
an exclusion with a one-line reason (`# pragma: no cover  # defensive: guarded by caller`) instead
of a hollow test.

### 3. Write the tests

Follow Standards → Tests: mirrored location, behavior names, Arrange → Act → Assert, one behavior
per test, specific error assertions, mocks only at boundaries. Write integration tests in
`tests/integration/` only for flows whose correctness depends on real collaboration between modules.

Run the new tests after each file, five times in a row (Standards → Tests): a test that passes
only some of the time is flaky and gets fixed before you move on. A new test on existing code
should pass; if it fails, you have found a bug or misread the behavior. Report it to the user
rather than changing the code.

A test only earns its place when it adds something: a branch or scenario no other test covers,
or a mutant it kills. Uber's AutoCover rejects "change-detector" tests that only restate the
implementation (asserting the exact calls a function makes); write behavior assertions instead.

A failing property needs one more step before you call it a bug: reread the documentation and the
callers, and decide whether the code or the property is wrong. A property that is too strong
("never raises" for input the function rejects on purpose) is fixed by narrowing its generator.
Report a bug only with the shrunk counterexample and the line of documentation it contradicts.

### 4. Check strength

When a mutation tool is configured (`mutmut run`, `npx stryker run`), run it on the modules in
scope. Each surviving mutant is a missing assertion: add or sharpen a test, rerun. A mutant no
test could tell apart from the original is equivalent: exclude its line with the tool's comment
and the reason (`# pragma: no mutate  # equivalent: …`, `// Stryker disable next-line all: …`).
Target: 60 % mutation score, rising. mutmut does not run on native Windows; there, use WSL or
leave mutation to CI and say so in the report. Without the tool, re-read each test and ask
"which bug would make this fail?".

### 5. Verify organization

The test tree must mirror the source tree plus one separate integration area. Reorganize before
reporting if it does not.

### 6. Report

State what was already covered, which gaps you filled, the properties you added, branch coverage
before → after (target ≥ 80 % on the modules in scope), the mutation score if measured, bugs
found with their counterexamples, and deliberate exclusions with their reasons.
