# Slice S<k> summary: <what this pull request delivers, in one line>

- **Spec:** [requirements.md](../requirements.md) · **Design:** [design.md](../design.md) · **Tasks:** [tasks.md](../tasks.md)
- **Tasks:** T<first>–T<last>

<!-- Written when the slice's last task is done, as summaries/S<k>.md. Every fact comes from
tasks.md, design.md, evidence/ and the slice's commits: write "none" for an empty section instead
of dropping it. -->

## What changed and why

<What the slice adds or changes, in two to four sentences, and the problem or requirement it answers.>

## Requirements covered

| Requirement | Task | Test |
| --- | --- | --- |
| R<x.y> | T<n> | `<path>::<test name>` |

## Size

<changed lines> changed lines (<added> added, <removed> removed) against a budget of <Pull request budget> per slice.

## Risks and high-risk tasks

- **Risk per task:** T<n> <low | medium | high>, …
- **High-risk tasks:** T<n>: mutation run `<command>` → <killed>/<total> mutants killed, <survivors justified or "none">; evidence in `specs/<NNN-slug>/evidence/T<n>.md`
- **Open risks:** <what could still go wrong and where, or "none">

## Decisions

<!-- One entry per decision taken while delivering the slice: the options, the choice and who chose it. -->

- <question>: <option A> | <option B> → **<chosen option>** (user | recommended)

## Review rounds and rethinks

| Task | Spec rounds | Code rounds | Escalations |
| --- | --- | --- | --- |
| T<n> | <n> | <n> | <n> |

- **Rethinks:** T<n>: <what the rethink found and the new approach>; report in `specs/<NNN-slug>/evidence/T<n>-rethink.md`<, set-aside attempt in stash "<message>">

## Reading order

<!-- Files in the order a reviewer should read them, each with the line range that matters. -->

1. `<path>:<first>-<last>`: <what to look at there and why first>
2. `<path>:<first>-<last>`: <…>
