---
name: setup-project
description: Prepares a repository for the konundrm-eng workflow. Detects the stack, merges quality tooling into the existing config (Python — ruff, mypy, pytest-cov, pytest-randomly, import-linter, poethepoet; TypeScript — eslint, tsc, prettier, dependency-cruiser, vitest), exposes one check command, wires pre-commit (with secret scanning) and CI to that same command, adds static analysis, a mutation-testing gate for high-risk pull requests and an AI review of every pull request, enforces the commit message format, writes AGENTS.md, CLAUDE.md and a pull request template, enables the plugin for the whole team in .claude/settings.json with Claude kept out of secret files, and proposes branch protection. Gates start green on legacy code and strict on new code. Run once per repository with /konundrm-eng:setup-project.
disable-model-invocation: true
argument-hint: "[python | typescript]"
---

# Setup Project

The plugin's hooks call one command, `check`, in every repository. This skill makes that command
exist and mean the same thing everywhere: format, lint, types, architecture rules, tests with
coverage. It then puts the same standard around the agent (team settings, instructions) and
after the commit (pre-commit, CI, pull requests). Templates live in `${CLAUDE_SKILL_DIR}/templates/`.

## Workflow

```
- [ ] 1. Inspect the repository
- [ ] 2. Propose the change list and get approval
- [ ] 3. Install dev dependencies
- [ ] 4. Merge configuration
- [ ] 5. Write architecture rules from the real structure
- [ ] 6. Wire pre-commit: secrets, check, commit message
- [ ] 7. Add CI
- [ ] 8. Write AGENTS.md, CLAUDE.md, team settings and the pull request template
- [ ] 9. Propose branch protection
- [ ] 10. Run the baseline and make it green
- [ ] 11. Report
```

### 1. Inspect

Detect the stack from `$ARGUMENTS` or the files (`pyproject.toml`, `package.json`, lockfiles, `uv.lock`),
the package manager, the source and test layout, the layers that actually exist, every quality
tool already configured (black, flake8, isort, jest, biome, an existing Makefile or CI), whether
`AGENTS.md`, `CLAUDE.md` or `.claude/settings.json` exist, and the GitHub remote (`gh repo view`).

### 2. Propose and approve

Show a table `file → create | merge | keep` and the dependencies to install. Wait for an explicit
yes. Rules:

- **Merge, never overwrite.** Keep the project's existing values where they differ from the template.
- **Keep equivalent tools.** If the project uses jest instead of vitest or black instead of ruff
  format, wire `check` to the existing tool; offer migration only as an optional extra.

### 3. Install dev dependencies

- Python (uv): `uv add --dev ruff mypy pytest pytest-cov pytest-randomly hypothesis import-linter
  poethepoet diff-cover pre-commit pip-audit` (with pip: add them to the dev extra instead).
  Hypothesis runs the property tests; pytest-randomly runs the suite in random order and prints
  the seed, so tests that depend on each other show up (Standards → Tests). Mutation testing uses
  mutmut 3.8+, which CI installs on demand; it needs `fork()`, so it does not run on native
  Windows, where high-risk work relies on the `risk:high` CI gate or WSL.
- TypeScript (npm, or the project's manager): `npm install -D eslint @eslint/js typescript-eslint
  eslint-plugin-jsdoc prettier dependency-cruiser vitest @vitest/coverage-v8 fast-check husky
  lint-staged secretlint @secretlint/secretlint-rule-preset-recommend @commitlint/cli
  @commitlint/config-conventional @stryker-mutator/core @stryker-mutator/vitest-runner`. fast-check
  runs the property tests, Stryker the mutation tests, and secretlint scans staged files for
  secrets. secretlint and Stryker 10 need Node 22 or later.

### 4. Merge configuration

| Stack | Template | Destination |
| --- | --- | --- |
| Python | `templates/python/pyproject.toml` | merge into `pyproject.toml` |
| Python | `templates/python/check_commit_msg.py` | `scripts/check_commit_msg.py` |
| Python | `templates/python/check_mutation.py` | `scripts/check_mutation.py` |
| TypeScript | `templates/typescript/package.json` | merge `scripts` and `lint-staged` into `package.json` |
| TypeScript | `templates/typescript/eslint.config.mjs`, `vitest.config.ts`, `commitlint.config.mjs`, `stryker.config.mjs` | repository root |
| TypeScript | `templates/typescript/secretlintrc.json` | `.secretlintrc.json` |

Replace every `your_package`/`src` placeholder with the real names. In Python, the mutation gate's
`--source` and `[tool.mutmut] source_paths` must name the same folder.

### 5. Architecture rules

Write the import-linter contracts (`[tool.importlinter]`) or `.dependency-cruiser.cjs`
(`templates/typescript/dependency-cruiser.cjs`) from the layers that **exist today**. Never invent
layers. A flat project starts with the no-cycles rule only; layer rules come when the layers do.
Every rule says how to fix a violation (the contract `name`, or the rule's `comment`, printed by
`--output-type err-long`): an error that names the remedy is one an agent can act on.

### 6. Pre-commit

- Python: `templates/python/pre-commit-config.yaml` → `.pre-commit-config.yaml`, then
  `uv run pre-commit install`. gitleaks scans what is staged before each commit; pre-commit
  downloads Go to build it the first time.
- TypeScript: `npx husky init`, then copy `templates/typescript/husky/pre-commit` (lint-staged
  runs secretlint on the staged files, then the check) and `templates/typescript/husky/commit-msg`
  into `.husky/`.

### 7. CI

Copy `templates/<stack>/ci.yml` to `.github/workflows/ci.yml`, adjusting versions and paths, and
`templates/<stack>/dependabot.yml` to `.github/dependabot.yml`. CI runs `check` on every push and
pull request, enforces 80 % coverage on changed lines with diff-cover, validates commit messages,
scans for secrets (TruffleHog), runs static analysis that blocks only new findings (Semgrep),
audits dependencies (also nightly), and runs mutation testing: on pull requests labelled
`risk:high` as a gate on the changed code (every mutant killed or marked equivalent with its
reason), nightly as a report. It runs with read-only permissions and pins every action to a
commit SHA, which Dependabot keeps current along with the dependencies. Create the `risk:high`
label (`gh label create risk:high`, after the user's yes).

AI review of every pull request: copy `templates/claude-review.yml` to
`.github/workflows/claude-review.yml` when the user wants it. It runs `reviewing-pull-requests`
with the plugin's reviewers and posts only verified findings; it needs the `ANTHROPIC_API_KEY`
repository secret (the user adds it: `gh secret set ANTHROPIC_API_KEY`) and access to the
plugin's marketplace repository. Tell the user it costs API usage on every push to a pull request.

### 8. Agent instructions, team settings, pull request template

- `AGENTS.md`, from `templates/AGENTS.md`: the instructions every AI tool reads (Claude Code,
  Codex, Cursor, Copilot). A short map with the commands, the layers, where deeper docs live and
  the few rules the code does not show; under ~60 lines. If it exists, add only what is missing.
- `CLAUDE.md`, from `templates/CLAUDE.md`: it imports `AGENTS.md` (`@AGENTS.md`) and adds only
  what is specific to Claude Code. If a `CLAUDE.md` exists, move its project facts into
  `AGENTS.md` and keep the import.
- `.claude/settings.json`, merged from `templates/claude-settings.json`: registers the `konundrm`
  marketplace and enables `konundrm-eng`, so every teammate who trusts the folder gets the
  plugin, and denies Claude reads of `.env` files, `secrets/` and key files (`.env.example`
  stays readable). A plugin cannot ship these settings itself; the repository does. Keep any
  rule the file already has.
- `.github/pull_request_template.md`, from `templates/pull_request_template.md`: the same
  sections `opening-pull-requests` fills, for pull requests people open by hand.

### 9. Branch protection

Propose protecting the default branch, and run it only after an explicit yes (it changes the
repository's settings and needs admin rights):

```
gh api -X PUT repos/<owner>/<repo>/branches/<default>/protection --input - <<'EOF'
{"required_status_checks": {"strict": true, "contexts": ["check", "secrets", "sast", "audit"]},
 "enforce_admins": true,
 "required_pull_request_reviews": {"required_approving_review_count": 1, "dismiss_stale_reviews": true,
   "require_last_push_approval": true},
 "restrictions": null, "required_conversation_resolution": true}
EOF
```

A person approves every pull request, after its last push (Standards → Git and pull requests).
When the plan does not include protected branches (GitHub Free private repositories), say so and
give the user the steps for the settings page instead.

### 10. Baseline

Run the check command. Legacy code must not block day one, but new code must meet the standards:

- mypy: `[[tool.mypy.overrides]]` with relaxed settings for legacy modules, listed explicitly.
- ruff: `per-file-ignores` for legacy files in `pyproject.toml`, as recorded debt. Do not use
  `ruff check --add-noqa`: it writes silencers without reasons, which the commit gate rejects.
- pytest-randomly: if the suite fails only in random order, it has order-dependent tests; record
  `-p no:randomly` in `addopts` as debt with a comment, and list the tests to fix.
- Coverage: set `fail_under` to the current total (rounded down) and rely on diff-cover for new code.
- TypeScript: per-directory `rules` overrides in `eslint.config.mjs` for legacy folders.

Do not mass-fix legacy code in this pass. Repeat until the check passes.

### 11. Report

List files created and merged, the check command, the baseline numbers (coverage, ignored
files), the debt recorded, and what the user still has to do by hand: add `ANTHROPIC_API_KEY` if
they want the AI review, approve or apply branch protection, and on Windows use WSL for local
mutation runs and Claude Code's sandbox (it runs on macOS, Linux and WSL2, not native Windows).
Next step: commit the setup with `committing-changes` (`chore(tooling): add konundrm quality gates`).
