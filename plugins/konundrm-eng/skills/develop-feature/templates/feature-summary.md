# Feature summary: <Feature name>

- **Spec:** [requirements.md](requirements.md) · **Design:** [design.md](design.md) · **Tasks:** [tasks.md](tasks.md)
- **Slices:** S1–S<last> · **Tasks:** T1–T<last>

<!-- Written in Phase 4, after the final verification and before the delivery choice, so no
branch has been pushed and no pull request exists yet. Saved as summary.md next to
requirements.md, so every link is relative to the feature folder. Every fact comes from
requirements.md, design.md, tasks.md, summaries/, evidence/ and the feature's commits: write
"none" for an empty section instead of dropping it. -->

## Spec: problem and goals

<The problem the feature solves and its goals, in two to four sentences, from requirements.md.>

## Design: module ownership

| Module | Owns |
| --- | --- |
| `<path>` | <the responsibility design.md gives it> |

## Slice summaries

| Slice | Delivers | Tasks | Summary |
| --- | --- | --- | --- |
| S<k> | <what the slice delivers, in one line> | T<first>–T<last> | [summaries/S<k>.md](summaries/S<k>.md) |

## Decisions

<!-- One entry per decision taken across the feature: the options, the choice and who chose it. -->

- <question>: <option A> | <option B> → **<chosen option>** (user | recommended)

## Requirements, tests and evidence

| Requirement | Task | Test | Evidence |
| --- | --- | --- | --- |
| R<x.y> | T<n> | `<path>::<test name>` | <`evidence/T<n>.md` for a high-risk task, or "test output"> |

- **Final verification:** <[evidence/final.md](evidence/final.md), or "not automated: the steps under How to test the feature">

## Rethinks

- T<n>: <what the rethink found and the new approach>; report in [evidence/T<n>-rethink.md](evidence/T<n>-rethink.md)<, set-aside attempt in stash "<message>">

## Refuted findings

- T<n> <reviewer>: <the finding>. Refuted: <the finding-verifier's evidence>

## Suggestions not applied

- T<n> <reviewer>: <the code-review suggestion and why it was left out>

## How to test the feature

<!-- The final verification of requirements.md, as commands or steps a person can repeat. -->

1. `<command>` or <step>: <what the person should see>
