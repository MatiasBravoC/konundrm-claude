# Changelog

All notable changes to `konundrm-eng` are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the plugin uses
[Semantic Versioning](https://semver.org/). Bump `version` in `.claude-plugin/plugin.json` with
every release; installed copies only update when it changes.

## [0.5.0] - 2026-10-20

A gap analysis against what large software companies publish about programming with AI (Google,
Meta, Microsoft, Amazon, Uber, Airbnb, Stripe, Spotify, OpenAI, Anthropic, GitHub, DORA): the gates
can no longer be silenced or slip open, bugs and migrations get their own flows, and the work goes
on past the local commit to small, reviewed pull requests. Requires Claude Code 2.1.295 or later.

### Added

- `fix-bug` skill (`/konundrm-eng:fix-bug`): reproduce, expected behavior as an EARS criterion
  `B1`, a regression test that fails for the reported reason, root cause with evidence, the
  minimal fix, reviews and one `fix` commit with `Fixes:`, `Covers:` and `Escaped-gate:` trailers.
- `opening-pull-requests` skill: pushes only with a yes, one stacked pull request per slice, a
  description with requirement → test → evidence, risk and where to look first, `risk:high`
  labels.
- `reviewing-pull-requests` skill, local or in CI: spec, code and security reviewers, every
  Critical finding verified before posting, inline comments plus one summary; never approves.
- `migrate-code` skill: inventory by deterministic search, an approved recipe, characterization
  tests, codemods first, a gated state machine per file with bounded retries, review-sized
  batches and a resumable progress file.
- `tidy-codebase` skill: a periodic pass over duplication, stale silencers, unused code and drifted
  instructions, fixed as small behavior-preserving pull requests.
- `security-reviewer` subagent (read-only), dispatched on high-risk tasks against the feature's
  threat notes; Critical findings go through the finding-verifier.
- `suppressions.py`: finds gate silencers added without their reason (`# noqa`, `# type: ignore`,
  `eslint-disable`, `@ts-ignore`, coverage and mutation exclusions, skipped tests) and every
  focused test. The stop gate blocks the turn and the commit gate denies the commit. The marker
  lists mirror the new Standards → Gate integrity, and a test keeps them in sync.
- `secret_patterns.py` and `block_secret_writes.py` (PreToolUse on edits): content shaped like a
  real credential (AWS, GitHub, GitLab, Slack, Stripe, Google, Anthropic, OpenAI, npm, PyPI,
  SendGrid, Azure, private keys) makes the edit and the commit ask the person first.
- `find_duplicates.py`: blocks of six or more lines the change copied from elsewhere in the
  project (`--all` for the whole project); designing-modules, the code-reviewer and
  tidy-codebase use it.
- `tasks_document.py`: one parser for `tasks.md` (status, tasks, risk, slice, rounds), shared by
  the impact report and the session doctor.
- The session doctor names the features in progress and their next task at every session start,
  including after a compaction, so a long develop-feature run finds its place again.
- `working_tree.head_tree()` and `added_lines()`: the lines a change adds, with line numbers.
- The dependency guard asks OSV.dev about each new package's latest version: a malware report
  (OpenSSF `MAL-` id or a GitHub CWE-506 advisory) denies the command, and known vulnerabilities
  ask the person. It also asks when the license is undeclared, `UNLICENSED`, `SEE LICENSE IN …`,
  strong or network copyleft, or not open source, reading SPDX expressions and PyPI classifiers.
  `KONUNDRM_ACCEPTED_LICENSES` accepts licenses per project and `KONUNDRM_OSV_URL` points to a
  mirror; denials are logged as `dependency_denied`.
- Impact report: the gates bugs escaped from (`Escaped-gate:` trailers), and merged pull requests
  from GitHub through `gh` (median size against `KONUNDRM_PR_BUDGET`, time to merge).
- setup-project templates: `AGENTS.md` (imported by `CLAUDE.md`), `.claude/settings.json` that
  enables the plugin for the whole team and denies Claude reads of `.env` files, `secrets/` and
  keys, `.github/pull_request_template.md`, `claude-review.yml` (AI review of every same-repository
  pull request with `anthropics/claude-code-action`, pinned by SHA), `scripts/check_mutation.py`,
  `stryker.config.mjs`, `.secretlintrc.json`, gitleaks in pre-commit, lint-staged with
  secretlint in husky, Semgrep in CI blocking only new findings, pytest-randomly, ruff `PGH`,
  ESLint `reportUnusedDisableDirectives`, and a branch-protection step run only after a yes.
- Evals: `triggers-opening-pull-requests`, `triggers-reviewing-pull-requests`,
  `behavior-fix-bug-regression-test-first`, `behavior-commit-gate-rejects-silencer` and the long
  `behavior-develop-feature-end-to-end`; the no-trigger graders list the new skills.
- Tests for the setup-project template scripts (`check_commit_msg.py`, `check_mutation.py`).

### Changed

- Mutation testing in CI is a gate on pull requests labelled `risk:high`: in Python,
  `check_mutation.py` runs mutmut on the functions the pull request changed; in TypeScript,
  Stryker mutates the changed lines with `STRYKER_BREAK=100`. A surviving mutant fails the job
  unless its line is marked equivalent with its reason. Before, the job ended with `|| true` (and
  Stryker's `break: null`), so it could never fail, and on Windows, where mutmut does not run,
  high-risk Python code had no mutation check anywhere. The nightly run stays a report. The
  mutmut template keys follow 3.8 (`source_paths`, `pytest_add_cli_args_test_selection`).
- The commit gate fails closed: a crash or parser failure while handling a commit denies it,
  `onFailure: "block"` covers timeouts and a hook that cannot start, and without Python `run.sh`
  denies commands that mention a commit.
- writing-plans groups tasks into pull-request-sized slices under a budget (default 400 changed
  lines) and writes threat notes and a delivery plan in `design.md` when the work is high risk.
- develop-feature runs each task's verify command five times after green (a flaky test goes back
  to the test-writer), adds the security review on high-risk tasks, updates `AGENTS.md` when the
  feature changes a fact it states, and ends with `opening-pull-requests`.
- Engineering standards: five green runs before a test lands, regression tests for bugs, no test
  bent to the code; Git and pull requests (small batches, a person approves, the `Escaped-gate:`
  trailer); untrusted input for agents (Rule of Two), static analysis, licenses and malicious
  packages, threat notes; security review for high risk; new §11 Gate integrity.
- code-reviewer checks gate integrity, change-detector tests and duplication with the new tool;
  implementer and test-writer may not silence gates, focus or skip tests, or retry flaky ones.
- Architecture rules carry their remedy: dependency-cruiser comments printed with
  `--output-type err-long`, an instructive import-linter contract name.
- The stop gate's events carry a `reason` (`red_check`, `suppression`) like the commit gate's.

### Upgrading

Run `/konundrm-eng:setup-project` again in repositories prepared before 0.5.0 to merge the new
templates, or copy them by hand: `check_mutation.py`, the mutation and `sast` jobs of `ci.yml`,
`stryker.config.mjs` (it replaces `stryker.config.json`), the pre-commit, husky and lint-staged
changes, `AGENTS.md`, `.claude/settings.json` and the pull request template.

## [0.4.0] - 2026-10-20

### Changed

- Commit messages use plain Conventional Commits, `<type>(<scope>): <summary>`, without the
  leading Gitmoji. committing-changes, the engineering standards, develop-feature and
  setup-project write that format; the `check_commit_msg.py` and `commitlint.config.mjs`
  templates reject a header that starts with an emoji; the Dependabot templates use `build` and
  `ci` as prefixes.
- measure-impact still counts commits in the old Gitmoji format, so earlier history keeps its
  types.

### Upgrading

Repositories prepared with setup-project before 0.4.0 keep their own copy of the old validator,
which rejects the new messages. Copy the new `scripts/check_commit_msg.py` (Python) or
`commitlint.config.mjs` (TypeScript), and the `commit-message` prefixes of
`.github/dependabot.yml`, into each of them.

## [0.3.1] - 2026-10-12

Fixes from an end-to-end audit: the official validator, the plugin loaded in Claude Code 2.1.295
on Windows, a malformed-event robustness run over every hook, latency measurements in a
5,000-file repository, reviews of spec compliance and workflow coherence, real headless sessions,
and the eval suite (16 of 17 cases pass on Windows; the git case needs a shell sandbox, which
the Windows eval runner does not offer).

### Verified in real sessions

- Plugin subagents report `agent_type` as `konundrm-eng:<role>`, which the role rules expect.
- A failing Bash command arrives as `PostToolUseFailure`, never `PostToolUse`.
- The commit gate (red check and `HUSKY=0` bypass), the dependency guard (its "ask" becomes a
  denial with the reason in headless mode) and the stop gate (three blocks, then the warning)
  behave as documented, and Claude receives each reason verbatim.

### Changed

- The stop gate blocks with a `decision: block` JSON output, like the subagent audit, instead of
  exit code 2. Claude receives it as "Stop hook feedback".
- test-driven-development allows the minimal test-runner setup a new project lacks (reported in
  the handoff), never the behavior under test.

### Fixed

- Hooks no longer crash on events whose fields have unexpected types; `read_hook_input()`
  normalises them (the robustness run found 16 crashes across 7 hooks).
- Projects inside a larger repository (monorepo packages): the subagent audit and the stop gate
  now see and restore paths relative to the project folder. Restoring used to fail there.
- The commit gate and the dependency guard see commands behind `timeout`, `xargs`, `stdbuf`,
  `eval` and `iex`/`Invoke-Expression`, and installs through `python3.X -m pip`, `pip3.X` and
  `yarn global add`.
- Hook overhead per Bash command drops from about 0.77 s to 0.54 s on Windows: the per-command
  hooks import their heavy modules only when needed and `run.sh` starts no external processes.
- `run.sh` accepts Windows paths written with backslashes.
- `.hypothesis/` counts as a tool artifact, so running property tests is not a role violation.
- The impact report ignores HTML comments; the tasks template's commented example inflated it.
- develop-feature: a test that passes on arrival returns a CHARACTERIZATION report (format now
  defined in test-driven-development) and skips the implementer; the fix-round prompt carries
  every input it needs; BLOCKED about a wrong test goes to the test-writer instead of the user;
  the branch is created after the spec and the spec and plan get their own commit; finding
  verifiers run one at a time; tests added during risk verification are reviewed and failures
  routed; a failed final review becomes new tasks; resuming trusts `Task:` commits and the
  `Base commit` header; every template has `Status: Done`.
- committing-changes has a develop-feature mode: one commit, no second check, no push question.
- Reviewers fall back to loading the standards with the Skill tool and may run tests; the
  implementer no longer half-renames across test files.
- Evals: graders that look for test content judge the trace instead of the file list; the
  README documents `--allow-tools` for behavior cases.
- setup-project installs Stryker for TypeScript and documents mutmut's Windows limit; the README
  states the Git Bash requirement on Windows.

## [0.3.0] - 2026-10-12

Verification practices from current research on AI-written code: generation is cheap, so the
work moves to proving the code does what was meant.

### Added

- `guard_new_dependencies.py` (PreToolUse on Bash/PowerShell): against slopsquatting. Before a
  command installs or runs a package the project does not use yet (npm, pnpm, yarn, bun, npx,
  pip, uv, uvx, poetry, pdm, pipx), it asks npm or PyPI about it and asks the person to confirm
  when the package does not exist, is younger than 30 days, has under 100 weekly downloads or
  cannot be verified. Declared and locked packages, local npx binaries, private npm scopes and
  `KONUNDRM_TRUSTED_PACKAGES` globs are skipped; answers are cached for a day.
- `finding-verifier` subagent: tries to refute each Critical review finding with a reproduction
  before anyone fixes it. `develop-feature` uses it on high-risk tasks and doubtful findings.
- Reviewers no longer pin `model: inherit`, so `CLAUDE_CODE_SUBAGENT_MODEL` can put them on a
  different model from the one that wrote the code.
- Standards §10 Verification by risk: every task is low, medium or high risk. Medium adds property
  tests; high adds mutation testing on the changed modules, end-to-end evidence saved in
  `specs/NNN-slug/evidence/`, adversarial finding checks and a human read of the diff. Symbolic
  execution (CrossHair) and formal verification are documented as options for critical kernels.
- Property-based testing in Standards → Tests, `test-driven-development`, `adding-test-coverage`
  and the test-writer; doc-comment postconditions become property tests ("executable contracts").
  `property` task type and `Risk:` field in the tasks template.
- `measure-impact` skill and `metrics_report.py`: fixes per feature, possible escaped defects,
  review rounds and escalations per feature, and gate events. Hooks record what they block, ask
  or restore in a per-project log (`metrics_log.py`); `develop-feature` writes a `Rounds:` line
  per task.
- setup-project: Hypothesis and fast-check as dev dependencies; CI runs mutation testing on pull
  requests labelled `risk:high`.
- Evals: coverage work adds properties; a false finding is refuted with evidence.

### Changed

- The shell parser moved out of `gate_git_commit.py` into `shell_commands.py`, shared with the
  dependency guard.
- Plugin data location has one owner (`hook_io.plugin_data_directory()`).

## [0.2.0] - 2026-10-11

### Added

- `audit_subagent_changes.py` (SubagentStart/SubagentStop): snapshots the working tree when a
  subagent starts and checks every file it changed, by any tool, against its role. The first
  violation is sent back to the subagent; a second one is restored automatically with a warning.
  Role rules also keep subagents out of `specs/NNN-*/{requirements,design,tasks}.md`.
- `record_check_result.py` (PostToolUse on Bash/PowerShell): a check Claude ran and passed is
  reused by the commit and stop gates for the same file contents.
- `session_doctor.py` (SessionStart): tells Claude the project's check command and warns when Git
  is missing or the replaced account-level skills are still installed.
- `hooks/run.sh`: one launcher finds a working Python 3.10+ (`python3`, `python`, `py`), skips the
  Microsoft Store stub and reports when there is none.
- `quality_check.py` CLI, so skills get the check command from the same code the hooks use.
- Evals: `engineering-standards` trigger, negative graders for sibling skills, two no-trigger
  cases, and four LLM-judged behavior cases (TDD stops at red, specs interview first, commits
  never push unasked, clean changes are approved without invented findings).
- Engineering standards §8 Errors and logging and §9 Security; code-reviewer cites them.
- setup-project templates: secret scanning (TruffleHog), dependency audit (pip-audit, npm audit),
  Dependabot, ruff `S` and eslint `no-eval`/`no-new-func`, read-only CI permissions, actions
  pinned by commit SHA, job timeouts.
- Repository: CI (ruff, mypy on Python 3.10 and 3.13, hook tests on Linux, Windows and macOS,
  `claude plugin validate`), Dependabot, `pyproject.toml` and `requirements-dev.txt`.

### Changed

- Commit gate parser respects quotes and comments and finds commits behind `env`, `command`,
  `sudo`, PowerShell's `&`, inside `bash -c`/`pwsh -Command`/`cmd /c` (including
  `-EncodedCommand`), after `export`/`$env:` earlier in the line, and with abbreviated
  `--no-verify`. Also blocks `LEFTHOOK=0`, `HUSKY_SKIP_HOOKS` and `GIT_CONFIG_*` overrides.
- Check results are keyed by a content snapshot of the working tree instead of HEAD plus diff, so
  splitting work into several commits no longer reruns the whole check for each one.
- Stop gate compares the tree at the start and end of the turn: changes made through Bash or
  generators now count, and changes that were already there no longer block the turn.
- `format_and_lint.py` no longer lets `ruff --fix` delete an import added one edit before its
  first use (F401/F841 are left to the stop gate).
- `_common.py` split into one module per responsibility (`hook_io`, `project_paths`,
  `file_kinds`, `roles`, `working_tree`, `quality_check`, `hook_state`), with one test file each.
- The test-file list in Standards → Tests now matches the code (`__mocks__/`, `__snapshots__/`),
  and a test fails if they drift apart again.
- `develop-feature` runs the full check once per task, after checking the task's box, so the
  commit hook reuses it; `committing-changes` runs it once per pass.
- CI templates cancel superseded pull request runs only, never pushes to main or nightly jobs.

### Fixed

- Template `check_commit_msg.py` passes its own template's lint rules.
- Template `pyproject.toml` keeps Markdown out of ruff: recent ruff versions also format code
  blocks in `.md` files, which would turn a project's `check` red because of a README sample.
- Tree snapshots copy the index with its timestamp, so Git still detects files edited in the same
  clock tick without a size change ("racy Git"); a fresh timestamp hid them intermittently.

## [0.1.0] - 2026-10-11

### Added

- `engineering-standards`: single source of truth for design (SOLID with violation examples),
  Definition of Done, tests, naming, documentation, Git and review severity.
- `writing-specs` and `writing-plans`: requirements in EARS notation with traceable IDs, design
  notes with module ownership, and 2–5 minute test-first tasks.
- `develop-feature`: orchestrator that runs spec → plan → per-task subagent loop → commit.
- `setup-project`: prepares a repository with one `check` command, pre-commit, CI and CLAUDE.md,
  with templates for Python and TypeScript.
- Subagents `test-writer`, `implementer`, `spec-reviewer` and `code-reviewer`.
- Hooks: role boundaries per subagent, format and lint after edits, commit gate, stop gate.
- Skill-trigger evals for every model-invoked skill.

### Changed

- Skills renamed to the Agent Skills naming convention and given a shared structure (contract,
  checklist workflow, rules, example): `tdd` → `test-driven-development`, `engineer` →
  `designing-modules`, `tester` → `adding-test-coverage`, `documentator` → `documenting-code`,
  `mapper` → `naming-identifiers`, `deployer` → `committing-changes`.
- `designing-modules` covers all five SOLID principles and writes a design note.
- `documenting-code` now owns the module header, including the section index formerly in `mapper`.
- `adding-test-coverage` adds mutation testing; `committing-changes` requires a green check.
