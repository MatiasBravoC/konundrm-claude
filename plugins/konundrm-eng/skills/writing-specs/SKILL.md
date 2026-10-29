---
name: writing-specs
description: Turns a feature idea into an approved requirements document before any design or code exists. Interviews the user, then writes specs/<NNN-slug>/requirements.md with user stories, acceptance criteria in EARS notation with traceable IDs, explicit non-goals, and a final end-to-end verification. Use when the user wants to start a new feature, says "quiero agregar…", "especifiquemos esto", "escribe los requisitos", "write a spec" or "what should this do", or when a request is too vague to plan. Does not design or plan; hand off to writing-plans once approved.
argument-hint: "[feature idea]"
---

# Writing Specs

Specify **what** and **why**, never **how**. A spec is done when someone who never talked to the
user could write a failing test for every acceptance criterion.

## Contract

- **Receives:** a feature idea (`$ARGUMENTS` or the conversation).
- **Produces:** `specs/<NNN-slug>/requirements.md` with status `Approved`, where `NNN` is the next
  free three-digit number under `specs/` and `slug` is 2–4 kebab-case words.

## Workflow

Copy this checklist and keep it updated:

```
- [ ] 1. Gather context
- [ ] 2. Interview the user
- [ ] 3. Write requirements.md from the template
- [ ] 4. Self-review against the quality bar
- [ ] 5. Get explicit approval
```

### 1. Gather context

Read `CLAUDE.md`, existing specs under `specs/`, and the code areas the idea touches. Never ask the
user something the repository already answers.

### 2. Interview the user

Ask one question at a time; offer options with `AskUserQuestion` when the answer is a choice.
Stop once you can fill the template, usually 3–7 questions. Cover:

- The problem and who has it. What happens today without the feature?
- The observable behaviors that would make it a success.
- Edge cases, errors and limits (empty, duplicate, unauthorized, too large, offline).
- Who may do it and with which data: roles and permissions, personal or payment data involved,
  and what must never leak or be logged.
- What is explicitly **out of scope** for this iteration.
- Constraints: performance, security, compatibility, deadlines, systems that must not change.

A report of something broken is a bug, not a feature: suggest `/konundrm-eng:fix-bug` instead.

### 3. Write the document

Use [templates/requirements.md](templates/requirements.md). Write each acceptance criterion in
EARS notation with an ID (`R<story>.<n>`) so tasks and tests can trace to it:

| Pattern | Template |
| --- | --- |
| Event | `WHEN <trigger>, THE SYSTEM SHALL <response>.` |
| State | `WHILE <state>, THE SYSTEM SHALL <response>.` |
| Unwanted | `IF <condition>, THEN THE SYSTEM SHALL <response>.` |
| Optional | `WHERE <feature is enabled>, THE SYSTEM SHALL <response>.` |
| Always | `THE SYSTEM SHALL <response>.` |

Mark any unresolved point as `[NEEDS CLARIFICATION: question]` instead of guessing.

### 4. Self-review

Fix the document until every answer is yes:

- Every criterion is observable and testable, with a concrete value instead of "fast" or "secure".
- No criterion names a class, table, framework or file. Those belong in the design.
- Error and edge cases have criteria, not just the happy path.
- Non-goals are listed, so scope cannot silently grow.
- The final verification describes a real end-to-end check a human could run.
- No `[NEEDS CLARIFICATION]` remains. If one does, ask the user before continuing.

### 5. Approval

Show the user the document path and a five-line summary (stories, criteria count, non-goals). Set
`Status: Approved` only after an explicit yes. When called from `develop-feature`, return control
to it; otherwise suggest `writing-plans` as the next step.

## Example criterion

Weak: "Login should be secure and handle bad passwords."

Strong:

- `R1.3` IF a user submits a wrong password 5 times within 15 minutes, THEN THE SYSTEM SHALL
  lock the account for 15 minutes and show "Account temporarily locked".
