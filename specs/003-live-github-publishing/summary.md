# Feature summary: Publicar en GitHub mientras se construye una feature

- **Spec:** [requirements.md](requirements.md) · **Design:** [design.md](design.md) · **Tasks:** [tasks.md](tasks.md)
- **Slices:** S1–S3 · **Tasks:** T1–T12

## Spec: problem and goals

develop-feature built a whole feature locally and pushed it, with stacked pull requests, only at the
end, so the user could not follow the work on GitHub while it moved. Each task commit ended with the
flow's lines (`Task: T3 · Covers: R1.2`, `Rounds: …`) and each pull request description carried
requirement and task IDs and the word slice, which a developer outside the flow cannot read; and the
plugin's manifest, README and two setup-project templates pointed to a GitHub organization that does
not exist. The goals: follow each feature on GitHub as it is built when the user chooses to (a branch
per slice from its start, each task as one commit as soon as it passes, each finished slice as a
stacked pull request), commits and pull requests any developer understands, pull requests of about
300 to 500 changed lines, publishing that never rewrites history and runs only from the main
session, and a plugin that points to its real repository.

## Design: module ownership

| Module | Owns |
| --- | --- |
| `plugins/konundrm-eng/hooks/scripts/task_commits.py` | finding each task's commit and rounds, from the commit message or from its note under `refs/notes/konundrm`, with one `git log` |
| `plugins/konundrm-eng/hooks/scripts/task_ledger.py` | `message`, which writes a message without flow lines and leaves them in a pending note, and `record`, which attaches that note to the commit made from it |
| `plugins/konundrm-eng/hooks/scripts/metrics_report.py` | the impact report, reading task commits and escaped gates from notes too, with 500 lines as the default pull request budget |
| skills `develop-feature`, `committing-changes`, `fix-bug`, `reviewing-pull-requests` | commits without flow lines, `record` first on resume, notes copied when a partition is integrated |
| `writing-plans` (and its `tasks.md` template), `engineering-standards`, `develop-feature` (and the slice summary template), `opening-pull-requests` | slices of 300 to 500 changed lines of code and tests, and the pause's count and warning |
| `develop-feature` (and the `tasks.md` template), agents `implementer` and `test-writer` | live publishing: the question at plan approval, a branch per slice, a push per commit, only from the main session |
| `develop-feature`, `opening-pull-requests`, setup-project's pull request template | each slice's stacked pull request in merge order, and its plain-English text |
| `plugin.json`, `README.md`, setup-project's `claude-settings.json` and `claude-review.yml`, `CHANGELOG.md` | the repository's address, the private-repository note and version 0.8.0 |
| `plugins/konundrm-eng/hooks/scripts/working_tree.py` | running Git; `run_git_checked` hands Git's own error to the callers that report it (added in S3, with `run_git` unchanged) |

## Slice summaries

| Slice | Delivers | Tasks | Summary |
| --- | --- | --- | --- |
| S1 | Commits say only what changed, with the flow's data in Git notes, and the plugin points to its repository | T1–T6 | [summaries/S1.md](summaries/S1.md) |
| S2 | Live publishing on GitHub, one stacked pull request per slice in merge order, pull request text anyone can read, 300–500-line slices and release 0.8.0 | T7–T10 | [summaries/S2.md](summaries/S2.md) |
| S3 | The ledger and the impact report pass GitHub CI without a global Git identity and on Python 3.10 (added at delivery) | T11–T12 | [summaries/S3.md](summaries/S3.md) |

## Decisions

- Scope: 47 tasks in 12 slices | 15 tasks | the 10 tasks that address the request → **10 tasks** (user)
- Where the flow's data lives: the commit message | a JSON file of the plugin's own | a Git note → **a Git note under `refs/notes/konundrm`** (user: a commit speaks only of its change; the design chose notes over a JSON file)
- How the publishing and pull request text rules are enforced: a script and hooks that block | instructions in the skills → **instructions in the skills** (user, a non-goal)
- Pull request text when the repository has no template: the plugin's fixed sections, in English, with no development meta comments → **four fixed sections in English** (user)
- Order of the stacked pull requests: implicit | explicit → **explicit, `(k/N)` in the title and a `Merge order:` first line** (user, added during the spec)
- Publishing this feature: live | local → **local, pushed only with the user's yes** (user, a non-goal)
- Pauses between slices: ask | pre-approved → **pre-approved** (user); open decisions: ask | pre-approved → **ask** (user)
- This feature's own commits: T1–T3 with the flow lines in the message (built before `message` changed) | T4 on with `message` → `git commit` → `record` → **both, in that order** (plan: `record` lands before `message` stops writing the lines)
- T5's files: the five planned skills | also engineering-standards §6, measure-impact and the eval graders that pinned the old lines → **also those files** (orchestrator)
- T7's files: also measure-impact and the README, which still said 400 lines (orchestrator, from T2's code review)
- T7's red check (lint findings in the new test): the implementer works around it | a test-writer fix round → **test-writer fix round** (orchestrator, routing rule)
- T8's invariant had no check: a separate round after the re-review | add it in the verify-by-risk step before the re-review → **before the re-review** (orchestrator)
- R4.2's fallback to the default branch: decide just before the pull request opens | only when the previous pull request is merged and its branch is gone → **merged and gone** (orchestrator, R4.2's wording)
- T10's files: also develop-feature's Phase 4 phrase "traceability table" (orchestrator)
- The live summary link: change the older test now | leave it open → **leave it open**, since it needs a plan change (orchestrator)
- Delivery: two stacked pull requests | a single pull request | not yet → **two stacked pull requests, then merge both so `main` holds the new version** (user)
- T1–T3's commits, which carry the flow lines in their message: leave them | rewrite them before pushing → **leave them** (user)
- The README's stale line about the bug-fix commit: fix it before pushing | leave it → **leave it** (user)
- The pull requests' CI showed four of this feature's tests failing: fix first, then merge | merge now, fix after | do not merge yet → **fix first, then merge**, as slice S3 built in the Phase 4 session (user)
- T11's test file failed format and lint after the red step: the implementer works around it | a test-writer fix round → **test-writer fix round** (orchestrator, routing rule)
- T12's red step: a new test, which cannot fail on Python 3.13 | the CI's Python 3.10 failures → **the CI's failures** (plan)
- Where Git's own error is captured: `task_ledger.py` | `working_tree.py`, next to `run_git` → **`working_tree.py`** (implementer; the spec review accepted the file outside the task's list)

## Requirements, tests and evidence

Tests are under `plugins/konundrm-eng/hooks/tests/`. No task was high risk, so no task has its own
evidence file; the final verification covers the feature end to end.

| Requirement | Task | Test | Evidence |
| --- | --- | --- | --- |
| R1.1, R1.2, R1.3, R1.4 | T8 | `contract/test_flows.py::test_live_publishing_pushes_each_slice_branch_and_commit` | test output |
| R2.1, R2.2, R2.3 | T8 | `contract/test_flows.py::test_live_publishing_pushes_each_slice_branch_and_commit` | test output |
| R3.1, R3.2, R3.3, R3.4, R3.5, R3.6 | T8 | `contract/test_flows.py::test_live_publishing_pushes_each_slice_branch_and_commit` | test output; [final.md](evidence/final.md), constraints |
| R4.1, R4.2, R4.4, R4.5, R4.6, R4.7, R4.8, R4.9 | T9 | `contract/test_flows.py::test_slices_end_in_stacked_pull_requests_in_merge_order` | test output |
| R4.3 | T9 | `contract/test_flows.py::test_slices_end_in_stacked_pull_requests_in_merge_order` | test output; [final.md](evidence/final.md), step 4 at delivery |
| R5.1, R5.2, R5.3, R5.4 | T10 | `contract/test_skills.py::test_pull_request_text_follows_the_template_without_flow_data` | test output; [final.md](evidence/final.md), step 4 at delivery |
| R6.1 | T4, T5 | `test_task_ledger.py::test_message_keeps_flow_data_in_the_pending_note`, `contract/test_flows.py::test_commits_carry_no_flow_lines_and_keep_their_data_in_notes` | [final.md](evidence/final.md), step 2 |
| R6.2 | T1, T2, T3, T4, T5, T11, T12 | `test_task_commits.py::test_a_task_and_its_rounds_come_from_the_flow_note_too`, `test_metrics_report.py::test_reads_flow_notes_and_defaults_to_a_500_line_budget`, `test_task_ledger.py::test_record_attaches_the_pending_note_to_the_commit_made_from_it`, `test_task_ledger.py::test_message_keeps_flow_data_in_the_pending_note`, `test_task_ledger.py::test_record_reports_gits_own_error_when_the_note_cannot_be_written`, `contract/test_flows.py::test_commits_carry_no_flow_lines_and_keep_their_data_in_notes`; on Python 3.10, the `test_metrics_report.py` tests in GitHub CI | [final.md](evidence/final.md), step 2 and GitHub CI |
| R6.3 | T5 | `contract/test_flows.py::test_commits_carry_no_flow_lines_and_keep_their_data_in_notes` | test output |
| R6.4 | T3, T5, T11 | `test_task_ledger.py::test_record_changes_nothing_whenever_it_refuses_for_any_pending_state`, `test_task_ledger.py::test_record_reports_gits_own_error_when_the_note_cannot_be_written`, `contract/test_flows.py::test_commits_carry_no_flow_lines_and_keep_their_data_in_notes` | [final.md](evidence/final.md), step 2 |
| R6.5 | T1, T2 | `test_task_commits.py::test_each_task_keeps_its_commit_wherever_its_flow_lines_are_for_any_history`, `test_metrics_report.py::test_reads_flow_notes_and_defaults_to_a_500_line_budget` | [final.md](evidence/final.md), steps 2 and 3 |
| R7.1, R7.2, R7.3 | T7 | `contract/test_skills.py::test_slices_aim_at_300_to_500_changed_lines` | test output |
| R7.4 | T2, T7 | `test_metrics_report.py::test_reads_flow_notes_and_defaults_to_a_500_line_budget`, `contract/test_skills.py::test_slices_aim_at_300_to_500_changed_lines` | test output |
| R8.1, R8.2 | T6 | `contract/test_meta.py::test_plugin_addresses_point_to_its_repository` | test output |
| R9.1 | T5, T7, T8, T9, T10 | the contract tests above | test output |
| R9.2 | T10 | `contract/test_skills.py::test_pull_request_text_follows_the_template_without_flow_data` | test output |

- **Final verification:** [evidence/final.md](evidence/final.md): steps 1–3 and 6 run and passed;
  step 4 is checked on the pull requests once the user approves the delivery; step 5 belongs to the
  next feature built with `Publish: live`. GitHub CI on the first pull requests showed four of this
  feature's tests failing (no global Git identity on the runners, and Python 3.10 rejecting a `Z`
  date); slice S3 fixed them, and the CI run on the fixes fails only on three problems `main` had
  before this feature (the evidence's GitHub CI section).

## Rethinks

none

## Refuted findings

none

## Suggestions not applied

All non-blocking; the flow records Suggestions instead of looping on them.

- S1 code reviews: `record` would accept a blank pending note and report success
  (`task_ledger.py:369-374`), and an `OSError` while deleting the second pending file would show a
  traceback (`:372-373`).
- S1 code reviews: `message` writes the message before the note, so a failed second write could
  leave a stale note (`task_ledger.py:193-194`).
- S1 code reviews: on a resumed parallel wave, develop-feature pairs notes against
  `<fork-point>..<branch>` while the pick is `<last>..<branch>`
  (`develop-feature/SKILL.md:376-377`); the whole-feature spec review found the governing rule
  ("the picked range's commits") clear.
- S1 code reviews: the README says a project's CI needs a token for the private repository, but not
  how to give it.
- S2 reviews: a pull request opened live is told to link `summary.md` at the final commit's SHA,
  which does not exist when the earlier slices' pull requests open; an older contract test forbids
  making that link conditional, so changing it needs a plan change
  (`opening-pull-requests/SKILL.md:143-147`).
- S2 reviews: `engineering-standards/SKILL.md:140` still says a pull request description traces each
  requirement to its test and states each task's risk.
- S2 reviews: opening-pull-requests step 2 measures the budget with the whole diff, counting the
  feature's documents (`opening-pull-requests/SKILL.md:39-45`).
- S2 reviews: in live mode, the commits a slice checkpoint makes after the summary (improvement notes
  that fell back to the feature folder, the switch to one session) join the pull request just opened,
  and the Live publishing paragraph calls the previous slice branch's tip "the commit that adds its
  summary" (`develop-feature/SKILL.md:208-222`).
- S2 reviews: the Live pull request paragraph defers to opening-pull-requests steps 3–5, which wait
  for a yes and may open a draft; the live text overrides both without saying so
  (`develop-feature/SKILL.md:522-529`).
- S2 reviews: after a fallback to the default branch, `Merge #<n> first.` names a pull request that
  is already merged (`opening-pull-requests/SKILL.md:126-129`).
- S2 reviews: the fix-bug and summary mappings name the four fixed sections, not a repository
  template's matching ones, and setup-project's template lacks the fixed sections' mutation-score
  hint.
- S2 reviews: some contract-test rules accept loose keywords (R2.1, R3.2 and R5.4's leave-out
  patterns), so weaker wording would still pass.
- Whole-feature spec review: the README's skills table still says fix-bug ends in a `fix` commit
  "con `Escaped-gate:`" (`README.md:60`); the escaped gate now lives in the commit's note. The user
  chose to leave it.
- T11 code review: `run_git`'s docstring repeats the Args block of `run_git_checked`
  (`working_tree.py:73-80`).
- T11 code review: the new test clears the identity variables but not `GIT_CONFIG_PARAMETERS` or
  `GIT_CONFIG_COUNT`, so under a Git process started with `-c user.name=…` it would fail falsely,
  never pass falsely (`test_task_ledger.py:1013-1024`).
- T11 code review: `run_git_checked` has no direct test of its spawn-failure and empty-stderr
  branches (`working_tree.py:62-66`).
- T12 code review: the same trailing-`Z` workaround also lives in `package_registry.py:136` and
  `session_costs.py:141-142`; worth one shared helper if a fourth copy appears.

## How to test the feature

1. `npm run check`: format, lint, types and 494 hook tests pass (1 skipped on Windows); then
   `claude plugin validate ./plugins/konundrm-eng`: "Validation passed". To see what GitHub CI
   sees, run `HOME=<empty folder> GIT_CONFIG_NOSYSTEM=1 python -m unittest discover -s plugins/konundrm-eng/hooks/tests -t plugins/konundrm-eng/hooks -k test_task_ledger`:
   it passes without a global Git identity.
2. In a scratch repository with a plan in `specs/<NNN-slug>/tasks.md`, commit a task with
   `msg=$(sh <plugin>/hooks/run.sh task_ledger.py message <plan> T1 --subject "feat(demo): build it" --rounds "spec 1 · code 1 · escalations 0") && git add -A && git commit -F "$msg" && sh <plugin>/hooks/run.sh task_ledger.py record`:
   the message holds only the subject, `git notes --ref=refs/notes/konundrm show HEAD` shows the
   `Task:` and `Rounds:` lines, `task_ledger.py status <plan>` counts T1, and `task_ledger.py
   close-slice <plan> S1` checks its box with those rounds.
3. In this repository, `task_ledger.py status` and `close-slice` on the plans of features 001 and 002,
   and `metrics_report.py --days 60`, print the same with the 0.7.0 plugin
   (`git archive c8229a2 plugins/konundrm-eng`) as with this one; at this branch's tip the report
   counts 7 more task commits, this feature's T4–T10, recorded in notes.
4. After the delivery, `gh pr view <number> --json title,body` on each pull request: the title ends
   in `(1/2)` or `(2/2)`, the body starts with `Merge order:`, has the four fixed sections in English
   and no requirement, task or slice IDs, flow lines or role names.
5. In the next feature, answer yes to live publishing at plan approval and watch GitHub: the slice's
   branch when it starts, one commit per task as it ends, and the slice's pull request at its pause.
6. `sh plugins/konundrm-eng/hooks/run.sh session_costs.py <folder>` over one slice session's
   transcripts: tokens per role, full checks, and the messages that sent the reviews together
   ([evidence/final.md](evidence/final.md), step 6).
