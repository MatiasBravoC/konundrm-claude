---
name: naming-identifiers
description: Audits and fixes the names of files, modules, classes, functions, variables and booleans so each one says what it does or holds, then renames safely across the whole project in a single pass. Flags names that hide a cohesion problem (validateAndSave, utils.py) and leaves public contracts untouched unless asked. Use when the user says "mejora los nombres", "hazlo más legible", "esto es difícil de entender", "rename this" or "naming review", or after generating code whose names were chosen in a hurry.
argument-hint: "[file or folder]"
---

# Naming Identifiers

A name works when a reader can predict what it holds or does before reading the implementation.
Linters enforce the mechanical part (casing, length); this skill handles meaning.

## Contract

- **Receives:** files or a folder to audit, or the code changed in the current task.
- **Produces:** a list of renames applied (old → new, with the reason) and a list of suggested
  renames not applied because they touch public contracts or are too wide to verify now.

## Audit checklist

Apply Standards → Naming to every name in scope:

- **Files and modules** describe their responsibility. A grown `utils`/`helpers` gets split and
  each piece named after its job; this is also a cohesion finding.
- **Functions** are verb + object (`apply_discount`, not `process2`). If the only honest name
  contains "and", report the cohesion problem even if you do not split it now.
- **Variables** say what they hold, with units where they matter (`timeout_seconds`). Loop
  indices and short-lived obvious locals are fine; the bar is "would a reader look elsewhere?".
- **Booleans** read as yes/no questions (`is_valid`, `has_pending_changes`).
- **Consistency:** one concept, one name across the codebase. Pick the dominant term and align.

## Renaming safely

1. **Search first.** Grep the whole project for every reference: imports, calls, re-exports,
   string-based lookups (DI containers, `getattr`, routes, templates, mocks patched by path).
2. **Rename everywhere in one pass.** A half-done rename lies about what is current. As the
   implementer subagent you may not edit tests: when a rename would reach them, leave it as a
   suggestion for the orchestrator instead of renaming half. Prefer the
   language server or IDE rename when available. If the change spans more than you can verify,
   apply the safe subset and list the rest.
3. **Leave public contracts alone unless asked:** published APIs, URL routes, database columns,
   environment variables, event names, CLI flags. List them as suggestions.
4. **Verify** by running the project's check command. Types and tests catch missed references.

## Example output

```
Applied:
  billing/utils.py → billing/tax_rates.py   (it only resolves tax rates)
  calc() → order_total()                    (verb + object)
  flag → is_overdue                         (boolean as a question)
Suggested (public contract, not applied):
  GET /api/getUserData → GET /api/users/{id}
```
