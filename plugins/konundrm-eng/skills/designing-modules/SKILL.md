---
name: designing-modules
description: Decides where new behavior lives before any code is written, so each responsibility has exactly one owning module. Searches the codebase for an existing owner, hunts and consolidates duplicates, chooses extend vs. new module, applies SOLID and dependency-direction rules, and records the decision in a short design note. Use whenever adding a feature, function, endpoint, service, component or module to an existing codebase, when refactoring, when implementing a task from tasks.md, or when the user asks "dónde va esto", "buena arquitectura", "organizar el código" or "clean architecture", even if they never mention cohesion or coupling.
---

# Designing Modules

Most unmaintainable codebases rot one convenient addition at a time: the nearest open file gets
one more function. This skill stops that by making placement a deliberate decision.

## Contract

- **Receives:** a responsibility to add or change (a task, a failing test, or a request).
- **Produces:** a design note (below) and code placed according to it. Inside `develop-feature`
  the note already exists as `design.md`; follow it and flag any deviation instead of re-deciding.

## Before writing code

1. **Name the responsibility** in one sentence. If it needs "and", it is two responsibilities.
2. **Search before creating.** Grep and glob for modules that own this or something adjacent: by
   name, folder, exports, imports and callers. Identify the layer it belongs to (domain,
   application, infrastructure, entry point) and what already lives there.
3. **Hunt duplicates.** Check whether this behavior already exists anywhere, even partially, under
   a bad name, or as dead code. If it does, **consolidate**: move it to the one owner, update the
   callers, delete the copy. If that is unsafe in this change, or (as the implementer subagent)
   it would require editing tests, say so explicitly with locations instead.
4. **Decide extend vs. new.** Extend a module only when its current single responsibility already
   includes this behavior. "Related but distinct" means a new module, not a convenient neighbour.
5. **Refuse god-modules.** If the candidate is already a grab-bag (`utils.py`, a component that
   fetches and renders five views), do not add to it; propose the split.

Write the design note before editing:

```
Responsibility: <one sentence>
Owner: <path> (extended | new) — <why there>
Duplicates: <locations consolidated, or "none found">
Depends on: <public interfaces used>; direction respected: <yes / which rule>
```

## While writing code

- Apply SOLID as defined in Standards → Design: one reason to change per function, new variants
  by addition, honest subtypes, narrow interfaces, policy depending on abstractions it owns.
- Respect dependency direction; no cycles (extract a third module instead of reordering imports).
- Import public surfaces only. Reaching into another module's private helper is coupling that
  breaks on its next change; add a proper entry point instead.
- Keep the exported surface minimal.
- No speculative abstractions: an interface needs a second implementation or a real boundary.

## Verify

Run the project's architecture check if configured (import-linter `lint-imports`,
dependency-cruiser `depcruise`). A new layer or module boundary means adding a contract to that
config in the same change. If no tool is configured, state which rule you checked by hand.

Then run the plugin's duplicate finder on the change:
`sh "${CLAUDE_PLUGIN_ROOT}/hooks/run.sh" find_duplicates.py`. It lists every block of six or more
lines you added that also exists elsewhere in the project (copy-paste grows fastest in
AI-written code). Consolidate each one into its owner, or say in the design note why the two
copies must stay apart.

## Self-check before finishing

- Which single module owns what I added, and why there?
- Did I search for an existing owner and for duplicates, and consolidate what I found?
- Does every function I touched still have one reason to change?
- Did I import anything private to another module?

"I put it where it was convenient" is a failing answer. Reconsider before moving on.
