# <Project name>

<One sentence: what this system does and for whom.>

<!-- Instructions for every AI coding tool (Claude Code, Codex, Cursor, Copilot). Keep it a map:
under ~60 lines, pointing to where details live instead of repeating them. -->

## Commands

- Check (everything CI runs): `<npm run check | uv run poe check>`
- One test: `<pytest tests/path/test_x.py::test_name | npx vitest run path -t "name">`
- Run locally: `<command>`

## Map

- `<src/…>`: <what lives there>. Layers: `<entrypoints>` → `<application>` → `<domain>`;
  `<infrastructure>` implements interfaces the inner layers own. Enforced by
  `<import-linter | dependency-cruiser>`, whose errors say how to fix them.
- `specs/`: approved requirements, designs and task lists, one folder per feature.
- `<docs/…>`: <deeper documentation, if any>. Read the file for an area before changing it.

## Rules

- <Up to 5 ownership facts the code does not make obvious, e.g. "All money math lives in `billing/money.py`".>
- Tests first: a failing test before the code, and a regression test before every bug fix.
- The check is green before every commit; never silence a lint, type or test failure without its
  reason on the same line.
- Commits use Conventional Commits; pull requests stay small and a person approves each one.
- Secrets come from the environment, never from code, tests or logs.
