# Changelog

All notable changes to `konundrm-eng` are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the plugin uses
[Semantic Versioning](https://semver.org/). Bump `version` in `.claude-plugin/plugin.json` with
every release; installed copies only update when it changes.

## [0.9.0] - 2026-11-18

Fewer review cycles for the same work. A plan no longer pays one full cycle of test-writer,
implementer and two reviews for every behavior: related low-risk behaviors are merged into
consolidated tasks, built and reviewed once. After a change, only the reviews that change concerns
run again. And a small change you ask for on work already built is made right away, as an
adjustment, with no new task and no second approval. One that changes what the code does still
gets its failing test first, the implementer and its reviews.

### Added

- Consolidated tasks. writing-plans first lists one behavior per line, then merges the low-risk
  lines that have one owner in the design, make one logical change and fit in five behaviors and
  about 300 changed lines of code and tests. A consolidated task is one task of the plan (one ID,
  one commit, one note) with a `Tests:` list that keeps one test per behavior and its criterion.
  Medium- and high-risk lines, `property` lines, open decisions and new dependencies stay in
  tasks of their own. An invariant that the code of one medium- or high-risk line keeps is
  tested with that line, not in a task of its own, and a documentation chore joins the low-risk
  task it documents. The plan's approval shows how many behaviors each task holds, why the
  others stayed apart and which tasks the other choice would merge, and the new header line
  `- **Consolidation:**` holds the choice: `low` (the default), `low and medium` (also merges
  the cases of one medium-risk rule, up to three per task) or `none`.
- One cycle per consolidated task. One test-writer dispatch writes every test of the task and
  reports on each one; a test that does not hold goes back alone. One implementer makes them pass
  one at a time, seeing each one fail before its code, and the spec review checks every listed
  behavior against its own test. The property tests of a task's invariants are written in that
  same red step, so verifying by risk no longer forces a second round of reviews.
- Reviews after a change. A new section of develop-feature decides, from the change's own diff,
  which reviews run again after a fix round, a change from verifying by risk or the fix of a red
  check: the review whose finding was fixed; the spec review alone when the change only added
  tests; both reviews when it changed an existing test or what the code does (the spec review
  alone when it only reworded a message, in the code and in the tests that assert it); the code
  review alone when it changed how the code is built or what configures a gate; none when it
  changed only text that nothing reads. A rename counts as how the code is built, also when the
  tests that use the name change with it. High-risk tasks repeat every review, a doubt runs
  both, and each review that was not repeated is appended to the task's Git note and listed in
  the slice summary. fix-bug follows the same rule.
- Adjustments. A change the user asks for on built work is classified first. A plan change (it
  adds or removes a criterion, changes the design, touches high-risk work, changes code in a file
  no task of the feature lists or is expected to take more than about 50 changed lines) still
  becomes tasks the user approves. Anything else is an adjustment, a rename included while
  nothing outside the feature's files uses the old name, and it is made at once: the criterion
  and the plan's lines that state the old detail are updated first, a change in what the code
  does gets its failing test first, then come the implementer, the verification, only the
  reviews its diff needs, the check and a commit of its own. Its Git note records the tasks it
  adjusts, the reviews that ran and what was asked, and the next summary lists it. A change asked
  on the task in progress joins that task. A finished feature is recognised by its documents.
  An adjustment to one that is already merged goes on a new branch cut from the remote's default
  branch, and a plan change reopens a finished feature only while it is not merged, no later
  feature follows it and its notes are there. `reference/adjustments.md` holds the procedure.
- Evals `behavior-plan-consolidates-related-tasks` and `behavior-adjustment-runs-needed-reviews`.

### Changed

- After a fix round, develop-feature and fix-bug no longer repeat every review: they run only
  the reviews the round concerns. A task's first reviews, and every review of a high-risk task,
  run as they did.
- A change asked at a slice's pause is no longer always a new task: an adjustment is made right
  away, and only a plan change waits for approval.
- measure-impact warns that tasks done, review rounds per task and fixes per feature are not
  comparable with features planned before this version.
- fix-bug marks the tree before its fix round and stages the fix in the same command as its
  commit (`git add -A && git commit …`).
- Plans written with earlier versions need no change and are built as before, one cycle per
  task: no task already in an approved plan is merged, and the tasks a plan change adds are
  consolidated among themselves. Two things do change for them: on a medium- or high-risk task
  the red step also writes the property tests of its invariants, and after a change only the
  reviews it concerns run again.

### Fixed

- The plan reader and `close-slice` take a task's rounds only from its own `- Rounds:` field. A
  Rounds text quoted in another field of the task (a `Test:` description, a change the user
  asked for), or wrapped onto a line of its own, was read as the task's rounds and miscounted
  the impact report, and `close-slice` could write the rounds over that line.
- `find_duplicates.py` refuses `--all` together with `--base` whatever value `--base` has. On
  Python 3.10 a `--base` equal to its default was taken for not given.

## [0.8.0] - 2026-11-01

Features you can follow on GitHub while they are built, and commits and pull requests any
developer can read without knowing the flow. Opt in when you approve the plan: each slice gets its
branch on GitHub as it starts, each task's commit is pushed as soon as it passes its reviews and
the check, and each finished slice opens a pull request stacked on the previous one. The flow's
data moves out of commit messages into Git notes, and the plugin points at its real repository.

### Added

- Live publishing. After the plan is approved, develop-feature asks, as a separate question,
  whether to publish the feature live, and records `- **Publish:** live` or `local` in the
  `tasks.md` header; it only offers it when the repository has a remote and `gh`, signed in, can
  see it. Live, each slice starts on its own branch, `feat/<NNN-slug>-s<k>`, pushed before its
  first task; every commit is pushed as soon as it is made (never forced, a rejected push stops
  with `BLOCKED:`); a finished slice opens its pull request, ready for review, stacked on the
  previous slice's; and the end of the feature lists every pull request in merge order instead of
  asking to push. A resumed session pushes what is missing and opens the pull request a finished
  slice lacks. Subagents and partition sessions never push. Plans without the `Publish:` line stay
  local and ask before any push, as before.
- `task_ledger.py record` attaches the pending note that `message` leaves to the commit just
  made; a resumed session runs it first, so a session cut between a commit and its note never
  builds that task twice.

### Changed

- The flow's data lives in Git notes under `refs/notes/konundrm`, not in commit messages. Every
  commit the plugin makes says only what changed: no task, requirement, slice or partition IDs and
  no `Task:`, `Covers:`, `Rounds:` or `Escaped-gate:` lines. A task's note holds its
  `Task: T<n> · Covers: …` and `Rounds: …` lines, a fix-bug's its `Covers: B1` and
  `Escaped-gate:` lines, and integrating a partition copies each note to its integrated commit.
  The skills, `task_ledger.py` and the impact report read the notes and still read the old
  message lines of features started before this version, also when a feature mixes both.
- Stacked pull requests state their merge order: each title ends with `(k/N)`, and each
  description starts with `Merge order: <k> of <N>. Merge #<n> first.` A pull request goes against
  the default branch only once the previous one is merged and its branch is gone; `risk:high` is
  added only when the repository has the label, never created; a branch with an open pull request
  never gets a second one.
- The pull request text follows the repository's pull request template word for word
  (`pull_request_template.md` in `.github/`, the root or `docs/`, in any letter case), else four
  fixed sections: What and why, Where to look first, How it was verified and Not in this pull
  request. Title and description are in plain English and leave the flow's data out: no IDs, no
  word "slice", no flow lines, no review rounds and no role names. setup-project's pull request
  template has those four sections.
- Slices aim at 300–500 changed lines of code and tests, not counting the feature's documents,
  and the default pull request budget is 500 changed lines instead of 400. Each slice summary
  counts its changed lines apart from the documents', and the pause warns when a slice goes over
  the budget, and by how much.

### Fixed

- The plugin's manifest, the README's install commands and setup-project's marketplace and review
  workflow templates point at `MatiasBravoC/konundrm-claude`, the plugin's real repository, which
  is private: whoever installs the plugin, and the CI of each project that uses it, needs access to
  it.

## [0.7.0] - 2026-11-01

A cheaper feature flow. The run that built 0.6.0 (80 tasks, 5 sessions, 380 subagents) spent
about 57% of its price-weighted tokens in the orchestrators, whose every turn rereads the whole
conversation; it ran the full check 290 times (about 5.7 h), ran its 221 reviews one after
another and paid about 0.65 s of hooks on every shell command. This release continues the feature
in a new session per slice, runs the full check once per task unless something changed after it
passed, runs a task's reviews at the same time, moves the flow's bookkeeping into commands that
answer in one call, keeps Python out of the hook for commands that are not the check, and measures
a run from its transcripts. Its savings are not measured yet: the next feature built with this
flow is the comparison. Requires Claude Code 2.1.295 or later, as 0.6.0 did.

### Added

- `task_ledger.py` does the flow's bookkeeping, one call each. `status <tasks.md>` prints the
  plan's base commit, the tasks with a `Task:` commit in `<base>..HEAD`, the next task (or each
  partition's next task in the wave in progress), whether the working tree is clean and whether a
  passing check is recorded for this exact tree. `message <tasks.md> T<n> --subject … --rounds …
  [--body …]` writes a task's commit message, with its `Task: T<n> · Covers: …` and `Rounds: …`
  trailers, under the Git directory and prints its path; it refuses, with exit 1 and nothing
  written, a task the plan lacks or one already committed. `close-slice <tasks.md> S<k>` checks
  the boxes of the slice's committed tasks and writes their Rounds lines from their commits. A
  plan that cannot be read, or whose base commit is missing or unknown, ends with exit 2 and
  `<file>:<line>` on stderr, changing nothing.
- `run_slices.py specs/<NNN-slug> [--claude PATH] [--max-sessions N] [-- ARGS...]` builds a
  feature with pre-approved pauses from a terminal: it runs
  `claude -p "/konundrm-eng:develop-feature specs/<NNN-slug>"` once per slice, in order, and its
  last line says how the run ended: `DONE`, `BLOCKED: <reason>`, `RED: <reason>` (a session waits
  for a person's decision), `FAILED: exit <n>`, `STALLED: session <k> added no commit` or
  `STALLED: reached the cap of <n> sessions`. It opens no session unless the plan is readable,
  `Approved`, `Checkpoints: pre-approved` and names a base commit in the repository, and never
  more than the pending slices plus one.
- `session_costs.py <folder>... [--check-pattern REGEX]` measures a run from Claude Code transcript
  folders: per role (the orchestrator and each subagent type) its dispatches, turns, tokens by kind
  and weighted (1, 1.25, 0.1 and 5) with its share, active minutes, full check runs with their
  minutes, test runs and messages that dispatched subagents at once; then the busiest orchestrator
  session's context per turn (first, median, 90th percentile, maximum). It prints counts, times
  and token totals, never content (an unreadable transcript gives one line with its path and the
  error type, and exit 1), skips and counts invalid lines, and reads Windows paths past 260
  characters. `/konundrm-eng:measure-impact [days] [transcript folders...]` adds this report to
  the delivery report when it gets transcript folders.
- Tests, run by the check, for this release's agreements that can be checked without a model:
  each role's instructions, each new step of the flow, the new commands and the hook. The rules go
  into the contract tests under `hooks/tests/contract/`; the commands get `test_task_ledger.py`,
  `test_task_commits.py`, `test_run_slices.py`, `test_deliberate_stops.py` and
  `test_session_costs.py`; the fast path of `run.sh` is tested in
  `integration/test_hook_scripts.py`; and hook tests such as `test_record_check_result.py` and
  `test_audit_subagent_changes.py` grow with what they cover.

### Changed

- Sessions: once a slice's pause is over and another slice or the finish phase is left, the
  session's part of the feature ends, and the feature goes on in a new session per slice that
  resumes from the plan and the repository, so the cost of a turn no longer grows with the
  feature. In the desktop app the session tools open it in the same folder with
  `/konundrm-eng:develop-feature specs/<NNN-slug>`; elsewhere the session ends with the exact
  `claude "…"` command. Uncommitted files stop the hand-off with a `BLOCKED:` line naming them.
  `- **Sessions:** single` in the `tasks.md` header, set from the request, the plan approval or a
  pause, keeps the next slice in the current session; `- **Sessions:** per-slice` is the default.
- One full check per task: the test-writer runs only the tests it wrote or changed; the spec,
  code and security reviewers get the orchestrator's verification output and run only the test or
  minimal reproduction a finding needs; the finding verifier runs only what its finding needs; the
  implementer runs the task's test and the tests of the code it changed, then the project's check
  once at the end of each dispatch. None runs the full suite outside the check.
- The gate starts with `task_ledger.py status` and runs the check only when no passing check is
  recorded for the current tree, so a file changed after the last green check (a test fix,
  evidence, a rethink report) still gets one. A passing check, Claude's or a gate's, also writes
  its tree to `.git/konundrm-eng-green` (one per worktree).
- The implementer, develop-feature's baseline and its gate run the check command as given, alone
  in its shell call, with no pipe, redirection or other command around it, so its pass is
  recorded and the commit reuses it instead of running the check again.
- A task's commit is one command: `task_ledger.py message`, then `git commit -F` on the file it
  wrote, through the commit gate like any other commit. The message carries the task, its
  requirements and its review rounds; the pause's `close-slice` writes the boxes and Rounds lines
  into `tasks.md`, committed with the slice summary.
- Parallel reviews: once a task is verified, develop-feature launches the spec and code reviews in
  one message, with the security review on a high-risk task, and runs no test-writer or
  implementer meanwhile. All their findings go to one fix round, and each re-review gets its
  previous findings, the fix round's reports and the new verification output. A change made while
  verifying by risk or after a red check goes back through the reviews before the commit.
- Resuming and the session start count a task as built by its `Task:` commit in `<base>..HEAD`,
  whatever its box says; the session start falls back to the boxes for a plan without a usable
  base commit.
- The fast path of `hooks/run.sh`: for the hook that records checks, a command that cannot be the
  project's check (`KONUNDRM_CHECK_CMD` included) exits without starting Python. What it cannot
  decide goes to Python byte for byte, and every other hook, the commit gate and the dependency
  guard included, gets its input untouched.

### Fixed

- Resuming looked task commits up with `git log -E --grep '^Task: T<n>( |$)'` over the whole
  history, so `Task:` commits an earlier feature left on the default branch counted as built;
  `task_ledger.py status` searches only `<base>..HEAD`.

### Known limitations

- A check run piped, redirected or chained (`npm run check | tail`) is not recorded, on purpose,
  so the gate runs it again; run it alone, or after `cd <root> &&`.
- Parallel partitions still look a partition's tasks up with an unranged `git log --grep`.
- `run_slices.py` checks the plan only before the first session, counts a session as progress when
  HEAD's SHA changed, and sees no stop line when `--output-format json` or `stream-json` follows
  `--`.
- `session_costs.py`: a folder that does not exist gives an empty table without a warning;
  subagents that workflows start (`subagents/workflows/`) are not read; a `--check-pattern` is
  searched anywhere in a command, so start it with `^`; test runs count only `python -m unittest`,
  `python -m pytest`, `pytest`, `npm test` and `npm run test`; two kinds of line Claude Code does
  not write, one whose `type` is not text and JSON nested past Python's recursion limit, still stop
  the report (one fixed line, exit 1, no content).

### Upgrading

Plans written with 0.6.0, with boxes and Rounds lines per task, keep working: resuming, the
session start and the impact report read both. A `tasks.md` without a `Sessions:` line reads as
`per-slice`, so the feature continues in a new session after each slice's pause; add
`- **Sessions:** single` to its header to stay in one session. `task_ledger.py` and
`run_slices.py` need the plan's `- **Base commit:**` line with a SHA. No setup-project template
changed, so projects prepared with 0.6.0 need nothing copied.

## [0.6.0] - 2026-10-30

Guided slice delivery. A 61-task feature ran for about three days in one session, with the session
and every subagent on Opus 5.5 at effort max (about US$1,300 at API prices), and ended with
thousands of lines its developer had not followed. This release spends model effort where it
pays, builds the independent parts of each slice in parallel, pauses after each slice so the
developer understands it before the next one, keeps reviews small with one stacked pull request
per slice, and records what could make the plugin better. Requires Claude Code 2.1.295 or later,
as 0.5.0 did; that already covers the per-dispatch `effort` parameter.

### Added

- `rethinker` agent (`opus`/`max`, read-only): when a task fails its fifth review, or the same
  review a third time, develop-feature and fix-bug stop the fix rounds and ask it why the attempts
  keep failing. It answers `NEW APPROACH`, `ADJUST` or `PLAN CHANGE`, says whether to keep or set
  aside the current attempt, and gives instructions for the test-writer and the implementer. A
  plan change waits for the user. An attempt set aside is stashed with a message naming the task
  and recovered by its SHA, never discarded; the report is saved as
  `specs/<NNN-slug>/evidence/T<n>-rethink.md`. A task that still fails two reviews after its
  rethink goes to the user. `roles.py` lists it as read-only, so the hooks hold it to that.
- Parallel partitions inside each slice: writing-plans ends every slice with a `### Partitions`
  table (`| Wave | Partition | Tasks | Depends on |`) that groups its tasks into partitions (sets
  of tasks one session builds in order) and waves (partitions built at the same time: no
  dependency between them, no shared file but `tasks.md` and `evidence/`, at most three). Task
  ranges such as `T1–T3` are accepted, and task IDs match by number, so `T01` is `T1`. After plan
  approval, develop-feature asks separately whether to build in parallel, offering it only when
  the partitions' checks and end-to-end tests can run at once on the machine, and records the
  answer as `- **Parallel:** yes | no` in the `tasks.md` header. With a yes it builds a wave's
  first partition itself and each other one in a partition session
  (`/konundrm-eng:develop-feature specs/<NNN-slug> --partition P<k>`) with its own Git worktree
  outside the checkout, on a `wave/<NNN-slug>-p<k>` branch. It cherry-picks the partitions onto
  the feature branch one at a time, running the check after each, stops on a conflict outside the
  plan's boxes, and ends the wave with one code review across it. A resumed session finishes an
  unfinished wave first, judging by each task's commit, and the session start names the next task
  of each partition in the wave in progress.
- Slice checkpoint: once a slice's last task is committed (or its last wave integrated),
  develop-feature writes the slice summary `specs/<NNN-slug>/summaries/S<k>.md` from
  `templates/slice-summary.md` (what changed and why, requirements covered, size, risks and
  high-risk tasks, decisions, review rounds and rethinks, and a reading order with files and line
  ranges) and commits it as `docs(<scope>): summarize slice S<k>`. It then pauses after each
  slice: shows the summary, asks two or three short questions about the slice's code, explains
  the right answer with file and lines when one is wrong, and waits for the go-ahead, which never
  depends on the answers. Changes asked at the pause become new tasks or a plan change approved
  before the next slice. With `- **Checkpoints:** pre-approved` in the `tasks.md` header (set when
  the user approves the pauses in the request or with the plan) it writes and commits the summary
  and goes on without stopping.
- Design decisions with the user: writing-plans records a `- Decision:` field, with each option's
  pros and cons and a recommendation, when a task has two or more reasonable approaches, and the
  user picks one at plan approval. A test-writer or implementer that meets an approach the plan
  left open returns `Status: DECISION`; develop-feature pauses that task, shows the options and
  records `- Decision: <option> (user)`. With `- **Decisions:** pre-approved` in the `tasks.md`
  header (set when the user approves the decisions in advance, apart from the pauses) it takes the
  recommended option and records `(recommended)`; `Checkpoints: pre-approved` alone still pauses
  the task. The slice summaries cite every decision.
- Feature summary: in its finish phase develop-feature writes `specs/<NNN-slug>/summary.md` from
  `templates/feature-summary.md` (spec, module ownership, slice summaries, decisions,
  requirements with tests and evidence, rethinks, refuted findings, suggestions not applied and
  how to test the feature) and commits it with the final `docs(<scope>)` commit. Every pull
  request of the feature links it.
- `process-reviewer` agent (`sonnet`/`high`, read-only, listed in `roles.py`): at each slice
  checkpoint, after the summary commit, and at the end of the feature, after the feature summary,
  develop-feature asks it to read the flow's record (review rounds, escalations, rethinks, blocked
  subagents, gate events, user corrections) and propose improvement notes for the plugin, each
  with its evidence and the skill or agent it affects, never with project code, secrets or
  personal data.
- `improvement_notes.py` (`--project`, `--feature`, `--scope`, notes on stdin) appends the
  improvement notes with date, project and feature to one central file shared by all your
  projects, `<Claude config dir>/konundrm-eng/improvements.md` (`CLAUDE_CONFIG_DIR`, else
  `~/.claude`). It keeps the notes only up to the first line that may start code and removes
  secrets and e-mail addresses. When the central file cannot be written, the notes go to
  `specs/<NNN-slug>/improvement-notes.md` and the user is warned.
- Tests, run by the check, for every agreement that can be checked without a model: model and
  effort per role, which skills set either, each role's permissions, the plan template and how it
  is read, the task-commit search, the CI review's settings, every new step of the flow, the
  version and this changelog. The new contract tests live under `hooks/tests/contract/`, and
  each names the requirements it covers; the others are added to the hook test files they
  extend, such as `test_roles.py` and `test_tasks_document.py`.
- Evals: `behavior-slice-checkpoint`, `behavior-design-decision`, `behavior-slice-summary`,
  `behavior-feature-summary` and `behavior-improvement-notes`.

### Changed

- Model and effort per role: agent frontmatter sets them instead of inheriting the session's.
  test-writer and implementer `opus`/`medium` (before `inherit`), spec-reviewer `sonnet`/`high`,
  code-reviewer `opus`/`high`, security-reviewer `opus`/`xhigh`, finding-verifier `opus`/`high`.
- develop-feature has a `## Model and effort` section: every fix round runs the test-writer or
  implementer on `opus`/`high`, and so does every writer dispatch after a rethink; a high-risk
  task runs its test-writer, implementer and spec review on `opus`/`high`; the whole-feature spec
  review in the finish phase runs on `opus`/`high`. Every other dispatch omits both parameters,
  so the frontmatter applies. fix-bug follows the same rule keyed to the bug's risk;
  reviewing-pull-requests and migrate-code run their whole-pull-request or whole-batch spec
  review, and migrate-code its retries, on `opus`/`high`.
- writing-plans raises its own effort to `xhigh` while active, and gains a partition step and the
  decision rule. No other skill sets `model` or `effort`, so a long session never switches either
  midway.
- Delivery: after the feature's final verification and with a yes to push, develop-feature
  offers one stacked pull request per slice (the default) or a single pull request with every
  slice. Stacked, `risk:high` goes only on the slices that hold a high-risk task. Single, with a
  high-risk task, it warns first that `risk:high` will cover the whole feature and runs mutation
  testing locally on all the changed code when the tool works on the machine.
- opening-pull-requests builds each slice's description from its slice summary, links the feature
  summary as a URL pinned to the final commit, and lists the pull request's commits in order under
  `## Commits, one per task`, each with its task ID.
- The `claude-review.yml` template runs the CI review on `claude-opus-5-5` at `--effort medium`.
- migrate-code puts each batch on its own branch (`migrate/<slug>-b<k>`) and tidy-codebase each
  task (`tidy/<slug>`), each with its own pull request.
- Rewriting a pushed pull request (a rebase onto the updated default branch) needs the user's yes
  for that rewrite and pushes with `--force-with-lease`.

### Fixed

- Task commits are found with `git log -E --grep '^Task: T<n>( |$)'` in develop-feature and
  opening-pull-requests. The plain `--grep "Task: T1"` also matched T10 to T19, so in a plan of ten
  or more tasks a resumed session could miscount, and a pull request could be cut at the wrong
  commit.
- Parallel sessions work in worktrees outside the project folder, never under
  `.claude/worktrees/`. The gates check the linked worktree a session runs in instead of the main
  checkout, and the subagent audit compares and restores only in the root it snapshotted when the
  subagent started.
- A private-key header of any type (DH, X25519, ED448 and others) is detected as a secret.

### Known limitations

- CI mutation testing on a `risk:high` pull request covers everything it changed, not only the
  files of its high-risk tasks.
- measure-impact does not merge the gate events of parallel sessions: each worktree logs its own.
- The behavior evals run a model, so they stay outside the check and CI; run them with
  `claude plugin eval`.
- Nothing applies the improvement notes to the plugin by itself: read
  `<Claude config dir>/konundrm-eng/improvements.md` and decide what to change.

### Upgrading

Copy the changed setup-project templates into repositories prepared before 0.6.0, or run
`/konundrm-eng:setup-project` again: the `claude_args` of `.github/workflows/claude-review.yml`
(`--model claude-opus-5-5` and `--effort medium`) and the `## Commits, one per task` section of
`.github/pull_request_template.md`. Run sessions at `high`: each agent now sets its own effort, so
the session's level, `max` included, no longer reaches them. `CLAUDE_CODE_EFFORT_LEVEL`, when
set, still overrides every agent's effort and the per-dispatch levels the orchestrators pass, so
leave it unset. Every agent now names its own model, so neither `CLAUDE_CODE_SUBAGENT_MODEL` nor
a `/model` switch reaches any of them (in 0.5.0 the variable reached the reviewers, and a switch
reached the test-writer and the implementer). `CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1` would put
every role, and the orchestrators' per-dispatch `opus`/`high` overrides, on one model, so leave
it unset too. To run a role on another model or effort, edit the agent's frontmatter. Plans
written with 0.5.0 still run, slice by slice, with no partitions and no parallel question. A
plan without a `Checkpoints:` line reads as `ask` and pauses after each slice, and one without a
`Decisions:` line reads as `ask` and pauses on each open decision; add
`- **Checkpoints:** pre-approved` and `- **Decisions:** pre-approved` to its header to keep an
unattended run going.

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
