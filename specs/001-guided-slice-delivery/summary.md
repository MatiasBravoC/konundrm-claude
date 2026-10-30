# Feature summary: Guided slice delivery with parallel partitions

- **Spec:** [requirements.md](requirements.md) · **Design:** [design.md](design.md) · **Tasks:** [tasks.md](tasks.md)
- **Slices:** S1–S10 · **Tasks:** T1–T79
- **Plugin version:** 0.6.0 (`plugins/konundrm-eng`, written `P` below). Base commit `b8c3142`.

## Spec: problem and goals

On IAdrivers, a 61-task feature ran for about three days in one session. The session and every subagent ran on Opus 5.5 at max effort, about US$1,300 at API prices. At the end the developer had thousands of lines they had not followed. The earlier 0.6.0 draft cut some cost but delivered one pull request per feature, so `risk:high` covered all of it. Plugin improvements noticed during a run were noted by hand or lost.

The feature has six goals:
- each role runs on an agreed model and effort, with more effort only for fix rounds, high-risk tasks and stuck tasks;
- independent parts of a slice are built in parallel;
- the developer pauses after each slice with a summary, comprehension questions and their own design decisions;
- delivery is one stacked pull request per slice, with a single pull request as an option;
- a read-only agent records plugin improvement notes;
- a contract test suite keeps every agreement.

## Design: module ownership

| Module | Owns |
| --- | --- |
| `P/agents/*.md` (frontmatter) | Model and effort of each role (R1.1) |
| `P/skills/develop-feature/SKILL.md` | Per-dispatch overrides, Rethink, parallel question and Parallel partitions, open decisions, Slice checkpoint, feature summary, improvement notes in the flow, exact task-commit lookup (R1.2–R1.4, R2.6, R3.2–R3.5, R4.1–R4.5, R5.2–R5.4, R6.1, R6.3, R7.1, R7.5, R8.1–R8.4, R9.1, R9.2) |
| `P/skills/fix-bug`, `reviewing-pull-requests`, `migrate-code` | The same overrides and, for fix-bug, the same Rethink (R1.2–R1.4, R8.1, R8.4) |
| `P/skills/writing-plans/SKILL.md` and `templates/tasks.md` | xhigh planning effort; slices, partitions and waves; `- Decision:` fields (R1.5, R1.6, R2.1, R3.1, R5.1) |
| `P/skills/setup-project/templates/claude-review.yml` | CI pull request review on Opus 5.5 at medium (R1.7) |
| `P/agents/rethinker.md` | Read-only replanning of a stuck task, Opus max (R8.1) |
| `P/agents/process-reviewer.md` | Read-only review of the flow record that returns improvement notes, Sonnet high (R7.1) |
| `P/agents/test-writer.md`, `implementer.md` | Return `Status: DECISION` instead of choosing an undecided approach (R5.2) |
| `P/hooks/scripts/roles.py` | The read-only role registry (R7.1, R8.5) |
| `P/hooks/scripts/tasks_document.py` | The only `tasks.md` reader: partitions, ranges, waves, the `Parallel:` line (R3.1, R3.6, R3.8) |
| `P/hooks/scripts/session_doctor.py` | The next task of each partition of the current wave at session start (R3.7) |
| `P/hooks/scripts/project_paths.py` | Gates rooted in the linked worktree the session works in (R3.3) |
| `P/hooks/scripts/audit_subagent_changes.py` | One root per subagent: compare and restore only in the tree snapshotted at start (R3.3) |
| `P/hooks/scripts/improvement_notes.py` (new) | Scrub notes and append them to the central file, with a fallback (R7.2–R7.4) |
| `P/hooks/scripts/secret_patterns.py` | One secret detector, now with PEM private keys of any type (R7.3) |
| `P/skills/develop-feature/templates/slice-summary.md`, `feature-summary.md` (new) | The sections of both summaries (R6.1, R6.3) |
| `P/skills/opening-pull-requests/SKILL.md`, `setup-project/templates/pull_request_template.md` | Stacked or single delivery, `risk:high` placement, commits per task, summary in the description, history rewrites (R2.2–R2.5, R6.2, R9.4) |
| `P/skills/migrate-code`, `tidy-codebase` | One branch and one pull request per batch or cleanup task (R9.3) |
| `P/hooks/tests/contract/` (new) | The contract suite, run by `npm run check` (R10.1, R10.2) |
| `P/evals/behavior-*` (five new) | Behavior evals, outside the check (R10.3) |
| `P/.claude-plugin/plugin.json`, `P/CHANGELOG.md`, `README.md` | Version 0.6.0, changelog, user documentation (R10.1) |

## Slice summaries

| Slice | Delivers | Tasks | Summary |
| --- | --- | --- | --- |
| S1 | Each role runs on its agreed model and effort; the base of the contract suite | T1–T5 | [summaries/S1.md](summaries/S1.md) |
| S2 | A stuck task is rethought by a read-only rethinker instead of fixed again | T6–T10 | [summaries/S2.md](summaries/S2.md) |
| S3 | Plans split slices into partitions and waves; the reader parses them; exact task-commit lookup | T11–T18, T55 | [summaries/S3.md](summaries/S3.md) |
| S4 | Partitions built in parallel sessions and integrated one at a time; worktree-safe gates and audit | T19–T24, T56, T70 | [summaries/S4.md](summaries/S4.md) |
| S5 | Slice checkpoint with summary and questions; design decisions go to the user | T25–T33 | [summaries/S5.md](summaries/S5.md) |
| S6 | Stacked or single delivery, `risk:high` per slice, the feature summary | T34–T41 | [summaries/S6.md](summaries/S6.md) |
| S7 | Process-reviewer and scrubbed improvement notes in one central file | T42–T50, T57–T59 | [summaries/S7.md](summaries/S7.md) |
| S8 | Contract tests name their requirements; five behavior evals | T51–T52 | [summaries/S8.md](summaries/S8.md) |
| S9 | Polish from the reviews: sturdier reader, wave-aware session start, PowerShell-safe stash recovery | T60–T69, T71–T76 | [summaries/S9.md](summaries/S9.md) |
| S10 | Version 0.6.0 and changelog, README, and the gaps found at the end: decisions approved apart from the pauses, feature worktrees outside the project, both deliveries named everywhere | T53, T54, T77, T78, T79 | [summaries/S10.md](summaries/S10.md) |

**Size.** Every slice except S8 is over the 400-line budget: S1 441 (1214 with the spec-and-plan commit), S2 655, S3 676, S4 1433, S5 1057, S6 1385, S7 2254, S8 399, S9 800, S10 966. The prose contract tests cause most of it: one regex rule set per requirement clause. Each summary's reading order says where to start.

### How the feature was built

- **Integration.** The main session built part of the work. Side sessions built the rest in parallel, in app worktrees under `.claude/worktrees/`: "S3", "S7", "agents", "templates" (later "delivery"). The main session cherry-picked their commits into `feat/001-guided-slice-delivery` in slice order, and in task order unless a ready task depended on nothing still pending (T78 went before T77 in S10), and ran the full check before each commit. It checked each task's box and added its Rounds line at integration, and shortened two subjects over 72 characters (T48, T63). A `git merge-tree` dry run predicted the one conflict, T71 in `test_flows.py`; both sides were kept. This feature's own `tasks.md` has no Partitions tables and no `Parallel:` line, so the run coordinated the parallel work by hand. The new partition mechanism is checked by its tests and by the final verification's interactive run.
- **Model and effort incident.** The main session loaded the agent definitions when it started, before T1 changed them. So every dispatch without explicit parameters ran on Opus 5.5 at max, reviewers included; the subagent transcripts confirm it. From T10's reviews on, every dispatch passes `model` and `effort` from the agreed table. The user later asked whether the table was followed. The main session checked 85 subagent transcripts from 06:00 on: all matched, except one general-purpose helper at Sonnet/max (it inherited its effort) and the S3 session's orchestrator, which ran at high instead of max.
- **Gate gap.** The main session's `CLAUDE_PROJECT_DIR` was the scratch folder it started in, which has no check command. So the commit gate ran no check for the main session's commits. Every commit was re-verified by hand. In a temporary worktree, the 23 commits `d5981a1..b6eb7eb` were checked after the fact: all green. From T51 on, the check ran explicitly before each commit.
- **Checkpoints.** The user told the main session to carry on without pausing, so `tasks.md` records `Checkpoints: pre-approved`, and, since T77 separated the two, `Decisions: pre-approved` for the decisions the user also delegated. S6–S10's summaries are committed at the end of their slices. S1–S5's were drafted afterwards and land in the final docs commit, because putting them inside earlier slice ranges would rewrite history.

## Decisions

"user" means the user chose. "recommended" means the main session or a side session chose the recommended option under the user's permission to decide during the run ("sigue nomás… te doy permiso, sé maximalista"). Pushing, opening pull requests and the stacked-or-single delivery choice stay with the user. Where the sources record only the choice, the options are reconstructed. Each slice summary has the details.

**Planning and run setup**
- Spec and plan: approve | change → **approved, 223ba1c** (user)
- Where improvement notes live: the plugin repository | GitHub issues | one central file in the Claude config folder → **the central file** (user)
- Integrating partitions: merge commits | cherry-pick → **cherry-pick, for linear history and one commit set per slice** (recommended)
- Who writes the summaries: a separate agent | the orchestrator → **the orchestrator, which already has the records** (recommended)
- Property tests: `hypothesis` | `random` with a fixed seed → **`random`; the hooks use only the standard library** (recommended)
- After the model incident: keep omitting the parameters | pass them on every dispatch → **pass them, from T10's reviews on** (recommended); subagents on the table, orchestrators stay at max (user)
- Side-session commits: rebuild them in the main line | cherry-pick in slice order with the check first → **cherry-pick** (user: "Intégralos", "Sí, intégralos")
- More parallel work: keep the main line | open more side sessions → **agents and templates sessions, later the delivery session, with separate SKILL.md regions, test anchors and helper-name prefixes** (user asked; the split was recommended)
- Pauses between slices: stop at each | continue → **`Checkpoints: pre-approved`** (user: "sigue nomás", "Sí, sigue")
- Slice summaries S1–S5: write them inside their ranges (rewriting history) | draft them afterwards → **draft them, committed in the final docs commit** (recommended)

**Plan changes**
- Scrub gaps, an uncapped range and the worktree gate: record them | add tasks → **T55–T59, a0db71d** (user)
- T56 made the audit restore files in the S7 worktree: patch forward | revert, fix the audit, land T56 again → **revert 61cad85, add T70 (high risk), T56 again as a3ea3c1** (recommended)
- Review suggestions worth keeping: record them | add a polish slice → **S9 with T60–T69, 99ddad8; T71–T72, 9acda84; T73–T76, d5981a1** (recommended)
- T53 and T54: keep them in S8 | move them to a last slice → **S10, 80f61db, so the changelog covers S9** (recommended)
- Whole-feature spec review FAIL: ask the user | add tasks → **T77 and T78 in 4bd69e6; the skill says to ask about plan changes, but the user had delegated decisions** (recommended)
- Coverage changes: **T4 also covers R1.3; T9 also covers R1.2; T23 covers R3.5 and R3.6** (recommended)

**Building and reviewing**
- Tasks that passed on arrival (T7, T13, T51, T63, T72): rewrite until red | keep as characterization → **keep them, after proving each can fail** (recommended)
- Critical findings: a finding-verifier | reproduce directly → **reproduce directly**: the delivery session for T35–T37, T39 and T41, the templates session for T52, the main session for T29 (recommended)
- A gate refused a commit because another tree was red (T51, T56, T65): skip the hook | wait and retry → **wait and retry; no hook was skipped** (recommended)
- Suggestions after a passing review: another round | commit and record them → **commit and record** (recommended)
- A blocked side session held T25: wait | build it in the main line → **main line** (recommended). T38 and T40 kept a main-line fallback; it was not needed.
- A stray `uv.lock` left by a subagent's `uv run` (T29; T39's read-only code-reviewer did it again): keep | delete → **delete; prompts forbid `uv run` and `uv lock` in the repository root** (recommended)
- S3 template `Parallel:` line: literal `yes | no` (reads as yes) | `no <!-- yes | no -->` → **the latter** (recommended)
- T55 and T56 placement: **T55 at the end of S3, T56 at the start of S4** (recommended)
- T23: drop "ask when the `Parallel:` line is missing" | move it to Phase 0 → **Phase 0, under R3.6** (recommended). A resumed wave with every partition integrated reruns the check and the wave review first (recommended)
- Partition sessions: only a rethink's PLAN CHANGE stops them | any plan change → **any plan change ends in `BLOCKED:`, in T22** (recommended); T19's and T21's suggestions folded into T21–T24 (recommended)
- T25 `- Decision:` record: replace the options | keep them below the choice → **keep them; design.md updated** (recommended)
- T27's duplicate `_RECORDS` weakened T19's test: rename only | rename and guard the suite → **`_RECORDS_CHOICE` plus T72** (recommended)
- T29 Critical (the checkpoint would fire in partition sessions): verifier | fix → **fix: only slices without a parallel wave reach it from Phase 3** (recommended)
- T30's test-writer found its own rule passable: leave it to review | tighten before green → **tighten** (recommended)
- T36: read a task or slice named after the run verb as a restriction | parse further → **restriction, stated in the test** (recommended)
- T38: keep a `Pull request` column | drop it → **drop it; the summary predates pull requests** (recommended)
- Feature summary link: relative | URL pinned to the final docs commit's SHA → **pinned URL; no link where no summary exists** (recommended)
- T39 kept a Critical after two fix rounds: continue | stop → **attempt kept as WIP 1c3b255 without a `Task:` line; one last round in the delivery session; the two remaining test gaps recorded as residual risk** (recommended). The ready S6 commits were integrated first and T39 landed last (recommended)
- T40: widen the test | reword the skill → **reword** (recommended)
- T57 failed three spec reviews: accept the known forms | one more fix round | change the design → **change it without a parser: keep the notes only up to the first line that may start code** (recommended; see Rethinks). Its three older tests changed to the new rule; round 4 got one more fix round; round 5 got one last blunt round, any later finding being a residual risk; design.md's Threats row was updated in T57's commit (all recommended)
- Mutation testing could not run: stop the high-risk tasks | hand-injected mutants, mutmut left to CI's `risk:high` job → **the latter** (recommended)
- T52's five `skill-fired` graders can never pass: verifier | delete them → **delete them**; `tool: Agent` accepted (recommended)
- T60, a test-only chore: implementer | test-writer → **test-writer** (recommended)
- T64: derive the writing tools | list MultiEdit → **list it** (recommended)
- T73: catch `ValueError` | cap digits in one place → **cap at 18 significant digits** (recommended)
- T74, a wave cell that is not a number: guess | do not filter → **do not filter** (recommended)
- T75 stash recovery: quote the entry | apply by SHA → **by SHA, safe in PowerShell** (recommended); T66's tasks.md line updated in T75's commit (recommended)
- T71 conflict: one side | both → **both, restoring the shared `assertEqual`** (recommended)
- The process-reviewer could not be dispatched (the session's agent list predates it): skip the notes | a general-purpose agent following `agents/process-reviewer.md` read-only → **the latter, Sonnet high** (recommended)
- S10: T53 and T54 moved from S8 to a last slice, so S9 could be integrated meanwhile and the changelog would cover it; the whole-feature review's two gaps became T77 and T78, and the stale delivery wording a handover note found became T79 (plan changes 4bd69e6 and a65babd); T78 was integrated before T77, because only dependent tasks need task order; T77 was rethought after three failed code reviews (new approach, attempt kept, plan unchanged); feature worktrees go to `../<repo>-worktrees/<NNN-slug>` on a branch cut from the default branch (T78); the README was fixed at T77's integration, and this feature's `tasks.md` records `Decisions: pre-approved` because the user approved the decisions in advance (all recommended; details in [summaries/S10.md](summaries/S10.md))

## Requirements, tests and evidence

Tests are `P/hooks/tests/…::name`. In a cell, `::name` repeats the file before it.

| Requirement | Task | Test | Evidence |
| --- | --- | --- | --- |
| R1.1 | T1, T43 (T8) | `contract/test_agents.py::test_each_role_has_its_agreed_model_and_effort`, `::test_the_process_reviewer_is_a_read_only_sonnet_agent`, `::test_the_rethinker_is_a_read_only_opus_max_agent` | test output |
| R1.2 | T3, T4, T9, T67 | `contract/test_flows.py::test_develop_feature_overrides_model_and_effort_where_agreed`, `::test_other_flows_override_model_and_effort_where_agreed`, `::test_develop_feature_rethinks_a_stuck_task`, `::test_fix_bug_runs_dispatches_after_a_rethink_on_opus_high` | test output |
| R1.3 | T3, T4 | `contract/test_flows.py::test_develop_feature_overrides_model_and_effort_where_agreed`, `::test_other_flows_override_model_and_effort_where_agreed` | test output |
| R1.4 | T3, T4 | same as R1.3 | test output |
| R1.5 | T2 | `contract/test_skills.py::test_only_the_planning_skill_declares_effort` | test output |
| R1.6 | T2 | same as R1.5 | test output |
| R1.7 | T5, T69 | `contract/test_templates.py::test_ci_review_runs_on_opus_at_medium_effort` | test output |
| R2.1 | T15 | `test_tasks_document.py::test_the_writing_plans_template_parses` | test output |
| R2.2 | T34, T79 | `contract/test_flows.py::test_develop_feature_offers_stacked_or_single_delivery`, `::test_skill_descriptions_name_both_deliveries` (T79 in `43473e5`; passes in the full check, 404 tests at that commit) | test output |
| R2.3 | T35 | `contract/test_skills.py::test_stacked_delivery_labels_only_high_risk_slices` | test output |
| R2.4 | T36 | `contract/test_skills.py::test_single_delivery_warns_about_risk_high` | test output |
| R2.5 | T37 | `contract/test_skills.py::test_pull_requests_list_their_task_commits` | test output |
| R2.6 | T24 | `contract/test_flows.py::test_plans_without_partitions_run_in_list_order` | test output |
| R3.1 | T11, T13, T15, T16 | `test_tasks_document.py::test_reads_the_partition_of_each_task`, `::test_partitions_follow_the_first_row_and_ranges_cover_their_bounds`, `::test_the_writing_plans_template_parses`; `contract/test_skills.py::test_writing_plans_partitions_each_slice` | test output |
| R3.2 | T19 | `contract/test_flows.py::test_develop_feature_asks_about_parallel_partitions_once` | test output |
| R3.3 | T70, T56, T20, T21 | `test_audit_subagent_changes.py::test_audit_restores_only_in_the_tree_it_snapshotted`; `test_project_paths.py::test_project_root_is_the_worktree_the_session_works_in`; `contract/test_flows.py::test_a_partition_session_builds_only_its_partition`, `::test_parallel_partitions_integrate_one_at_a_time` | [evidence/T70.md](evidence/T70.md) |
| R3.4 | T22 | `contract/test_flows.py::test_an_integration_conflict_waits_for_the_user` | test output |
| R3.5 | T23 | `contract/test_flows.py::test_resume_finishes_an_unfinished_wave_first` | test output |
| R3.6 | T14, T19, T23, T62 | `test_tasks_document.py::test_reads_whether_partitions_run_in_parallel`, `::test_an_unfilled_parallel_line_reads_as_no`; `contract/test_flows.py::test_develop_feature_asks_about_parallel_partitions_once`, `::test_resume_finishes_an_unfinished_wave_first` | test output |
| R3.7 | T17, T63, T74 | `test_session_doctor.py::test_names_each_partitions_next_task_when_they_run_in_parallel`, `::test_lists_partitions_by_number_and_falls_back_to_one_task`, `::test_lists_only_the_current_wave_partitions` | test output |
| R3.8 | T12, T13, T55, T60, T61, T73 | `test_tasks_document.py::test_expands_task_ranges_and_reads_bold_cells`, `::test_partitions_follow_the_first_row_and_ranges_cover_their_bounds`, `::test_a_huge_task_range_does_not_hang_the_reader`, `::test_zero_padded_ids_match_their_number`, `::test_a_task_id_with_thousands_of_digits_does_not_crash_the_reader`, `::test_the_reader_never_raises_on_any_partition_cell` | test output |
| R4.1 | T29, T71 | `contract/test_flows.py::test_develop_feature_pauses_after_each_slice`, `::test_resume_runs_a_missing_slice_checkpoint_first` | test output |
| R4.2 | T30 | `contract/test_flows.py::test_slice_checkpoint_asks_comprehension_questions` | test output |
| R4.3 | T30 | same as R4.2 | test output |
| R4.4 | T31 | `contract/test_flows.py::test_changes_asked_at_a_checkpoint_become_tasks` | test output |
| R4.5 | T15, T32 | `test_tasks_document.py::test_the_writing_plans_template_parses`; `contract/test_flows.py::test_pre_approved_checkpoints_do_not_stop` | test output |
| R5.1 | T25 | `contract/test_skills.py::test_writing_plans_lists_design_decisions` | test output |
| R5.2 | T26, T27, T77 | `contract/test_agents.py::test_writers_return_a_decision_instead_of_choosing`; `contract/test_flows.py::test_develop_feature_asks_the_user_for_open_decisions`, `::test_pre_approved_decisions_are_recorded_apart_from_pauses` (T77 in `74fccbc`; passes in the full check, 403 tests at that commit) | test output |
| R5.3 | T32, T77 | `contract/test_flows.py::test_pre_approved_checkpoints_do_not_stop`, `::test_pre_approved_decisions_are_recorded_apart_from_pauses` (T77 in `74fccbc`; passes in the full check, 403 tests at that commit) | test output |
| R5.4 | T25, T27 | `contract/test_skills.py::test_writing_plans_lists_design_decisions`; `contract/test_flows.py::test_develop_feature_asks_the_user_for_open_decisions` | test output |
| R6.1 | T28, T29, T71 | `contract/test_templates.py::test_slice_summary_template_has_every_section`; `contract/test_flows.py::test_develop_feature_pauses_after_each_slice`, `::test_resume_runs_a_missing_slice_checkpoint_first` | test output |
| R6.2 | T33 | `contract/test_skills.py::test_slice_pull_requests_use_the_slice_summary` | test output |
| R6.3 | T38, T39 | `contract/test_templates.py::test_feature_summary_template_has_every_section`; `contract/test_flows.py::test_develop_feature_writes_the_feature_summary` | test output |
| R7.1 | T42, T43, T50 | `test_roles.py::test_read_only_roles_may_not_change_anything`, `::test_read_only_roles_are_denied_for_any_path`; `contract/test_agents.py::test_the_process_reviewer_is_a_read_only_sonnet_agent`; `contract/test_flows.py::test_develop_feature_records_improvement_notes` | test output |
| R7.2 | T44, T45, T49 | `test_improvement_notes.py::test_appends_dated_notes_tagged_with_project_feature_and_scope`, `::test_appending_keeps_every_earlier_note`, `::test_cli_reads_notes_from_stdin_and_prints_where_they_went` | CLI run in [evidence/T46.md](evidence/T46.md) (section T49) |
| R7.3 | T43, T46, T47, T57, T58, T59 | `contract/test_agents.py::test_the_process_reviewer_is_a_read_only_sonnet_agent`; `test_improvement_notes.py::test_scrub_drops_code_and_redacts_secrets_and_emails`, `::test_scrubbed_notes_never_keep_secrets_code_or_emails`, `::test_scrub_drops_tilde_and_nested_code_blocks`, `::test_scrub_removes_every_pem_private_key_block`, `::test_scrub_handles_long_word_runs_quickly`; `test_secret_patterns.py::test_reports_a_pem_private_key_header_of_any_type` | [evidence/T46.md](evidence/T46.md) |
| R7.4 | T48, T49, T50 | `test_improvement_notes.py::test_falls_back_to_the_feature_folder_when_the_central_file_cannot_be_written`, `::test_cli_reads_notes_from_stdin_and_prints_where_they_went`; `contract/test_flows.py::test_develop_feature_records_improvement_notes` | test output |
| R7.5 | T50 | `contract/test_flows.py::test_develop_feature_records_improvement_notes` | test output |
| R8.1 | T8, T9, T10, T64 | `contract/test_agents.py::test_the_rethinker_is_a_read_only_opus_max_agent`; `contract/test_flows.py::test_develop_feature_rethinks_a_stuck_task`, `::test_fix_bug_rethinks_a_stuck_fix` | test output |
| R8.2 | T9, T66, T75 | `contract/test_flows.py::test_develop_feature_rethinks_a_stuck_task`, `::test_a_set_aside_attempt_is_recovered_by_its_stash_message` | test output |
| R8.3 | T9 | `contract/test_flows.py::test_develop_feature_rethinks_a_stuck_task` | test output |
| R8.4 | T9, T10 | `contract/test_flows.py::test_develop_feature_rethinks_a_stuck_task`, `::test_fix_bug_rethinks_a_stuck_fix` | test output |
| R8.5 | T6, T7, T65 | `test_roles.py::test_read_only_roles_may_not_change_anything`, `::test_read_only_roles_are_denied_for_any_path` | test output |
| R9.1 | T18 | `contract/test_skills.py::test_task_commits_are_found_by_exact_id` | test output |
| R9.2 | T21, T78 | `contract/test_flows.py::test_parallel_partitions_integrate_one_at_a_time`, `::test_parallel_features_use_worktrees_outside_the_project` (T78 in `d0edf4a`; passes in the full check, 402 tests at that commit) | test output |
| R9.3 | T40 | `contract/test_skills.py::test_migrations_and_cleanups_use_one_branch_per_pull_request` | test output |
| R9.4 | T41 | `contract/test_skills.py::test_rewriting_pushed_history_needs_a_yes` | test output |
| R10.1 | T1, T53 (the whole contract suite) | `contract/test_agents.py::test_each_role_has_its_agreed_model_and_effort`; `contract/test_release.py::test_version_and_changelog_agree` | test output |
| R10.2 | T51, T72 | `contract/test_meta.py::test_every_contract_test_names_its_requirements`, `::test_contract_tests_define_each_module_name_once` | test output |
| R10.3 | T52 | `contract/test_release.py::test_each_new_mechanism_has_a_behavior_eval` | test output; the evals themselves have never been run |

T54 (README), T68 and T76 (wording in Model and effort) cover no requirement.

- **High-risk tasks:** T70 (S4) and T46, T47, T57, T58 (S7). Mutation testing never ran: mutmut refuses native Windows, and this machine's WSL has no uv or pip. Each evidence file records the attempt. Reviewers used hand-injected mutants and differential checks against markdown-it-py and commonmark.js instead. CI's `risk:high` job must run mutmut on S4's and S7's pull requests.
- **Whole-feature spec review** (Opus high, on a frozen worktree at `bd72d9f`, Phase 4): FAIL with two gaps. First, one `Checkpoints: pre-approved` line governed both the pauses (R4.5) and the decisions (R5.3), but the spec separates them; T77 adds a `Decisions:` header line. Second, develop-feature still recommended `claude --worktree`, which creates the worktree inside the checkout (R9.2); T78 fixes that. Everything else was implemented and asserted (400 tests at the time). The review was not repeated after T77 and T78: each passed its own spec review against those criteria (R5.2, R5.3, R9.2), and the full check passes. A side session's handover note later found stale delivery wording the review had missed (two skill descriptions and a Roles row naming only one pull request per slice), which became T79 (R2.2).
- **Final verification:** at `7daed5f`, the tip before the closing commit, `npm run check` passed with 404 tests and `claude plugin validate ./plugins/konundrm-eng` passed with one directory warning (no icon), which is outside this feature. The improvement-notes script also ran end to end against a temporary configuration folder: neither a code block nor an e-mail reached the notes file. The interactive run in a test project (the final verification's step 2) was not done: it needs a person to approve the spec and plan, pick a decision, answer a pause's questions and choose the delivery. [evidence/final.md](evidence/final.md) records the results and the steps.

## Rethinks

- **No rethink ran with the rethinker agent.** This session loaded its agent list when it started, before T8 created the rethinker, so it could not dispatch it. The side sessions could not dispatch it either.
- **T57** (S7, high risk): the main session acted as rethinker after three failed spec reviews. Each review found another CommonMark construct that turned the scrub's "close a code block" into an "open": a list marker on an earlier line, paragraph-text openers, lazy continuation, HTML blocks. New approach: keep the notes only up to the first line that may start code, replace the rest with `[rest omitted: it may contain code]`, and add no parser dependency. The attempt was kept and built on, not set aside, so there is no stash. Rounds 4 and 5 found narrow leaks that were fixed by decision, and round 6 passed. This counts as T57's one escalation. There is no `evidence/T57-rethink.md`: the reasoning is in 0514375's body, in [evidence/T46.md](evidence/T46.md) (section T57) and in [summaries/S7.md](summaries/S7.md).
- **T39** (S6) is not a rethink: its fix loop was stopped and the attempt kept as WIP commit 1c3b255 on `claude/p-delivery-t39-attempt`. One more round on the same approach tightened only the test.

## Refuted findings

None. No finding-verifier was dispatched: Critical findings were reproduced directly instead, and every one was confirmed. The confirmed Criticals were in these tasks:
- T23: three of five test rules were vacuous.
- T27: a duplicate module-level name weakened T19's test.
- T29: the checkpoint would also fire in a partition session.
- T35, T36, T37, T39, T41: gaps in the wording tests.
- T46: a PEM key's body and END line survived.
- T47: an inline backtick span read as a fence, then a regression of its first fix.
- T49: stdin was read in the Windows code page.
- T52: graders that could never pass.

## Suggestions not applied

Grouped by theme. Each slice summary lists its own per task: [S1](summaries/S1.md), [S2](summaries/S2.md), [S3](summaries/S3.md), [S4](summaries/S4.md), [S5](summaries/S5.md), [S6](summaries/S6.md), [S7](summaries/S7.md), [S8](summaries/S8.md), [S9](summaries/S9.md), [S10](summaries/S10.md). Suggestions worth applying became S9's tasks T60–T76.

- **Prose contract tests that are too loose or too strict.** Most tasks that pin skill wording with regexes got these suggestions: a negated or narrowed sentence still passes, or a correct rewording fails. Examples: T16, T19, T20, T22, T24, T29–T31, T33, T35–T37, T40, T41, T50, T75, T78 and T79; T77's structural rule keeps documented limits (a reference across two sentences, an "or" inside parentheses). T39 keeps two such gaps as accepted residual risk. The delivery session's advice: pin canonical phrases in the skills and test that they are present, instead of interpreting free wording.
- **Test hygiene.**
  - Helpers duplicated across test files (T3/T4, T16, T25, T26, T40).
  - One test checking several behaviors (T18, T46/T47, T49).
  - Expected markers derived from the code under test (T57, T58).
  - Branches with no test: `read_frontmatter`'s error, T74's wave fallbacks, T72's alternative-branch logic, T48's double failure, T49's exit codes.
  - Naming and wrapping nits.
- **Skill and agent prose.**
  - opening-pull-requests still says the user chooses the delivery and assumes a slice in steps 4–5 (T34).
  - Stacked-only wording outside T79's three places: develop-feature's Slice checkpoint says each slice ends in a pull request, and engineering-standards' Definition of Done asks that each slice's pull request be approved, which reads as unmet with a single pull request (T79's spec review).
  - The changelog's Upgrading still advises running sessions at `high`, which no spec text backs (T53).
  - `process-reviewer.md` points to escalation lines that do not exist; the dispatch prompt works around it (T43).
  - migrate-code's groundwork pull request is never opened (T40).
  - A DECISION report still reads as GREEN (T26).
  - General rules read as unconditional before the pre-approved exception (T32).
  - Ambiguous link rewriting (T33) and several over-long lines.
- **Scrub limits (R7.3), relying on the process-reviewer's own ban.** The scrub does not catch inline code spans, JWTs, `password=` values or bearer tokens. It also misses e-mails at dotless domains, private key labels with a hyphen or dot, and PGP, SSH2 four-dash or OpenVPN keys. Residual risks accepted after T57: a byte order mark before a first-line fence, and code joined by U+2028. T58 regression: one contrived line where a made-up private-key header runs into a real one is no longer flagged by the secret-write hooks.
- **Reader and resume edge cases.**
  - The `Rounds:` field still converts an unbounded number with `int()`, so a huge value raises. This sibling of T73 was found by the S9 process review.
  - T74's single-task fallback follows file order, not wave order.
  - Resume edges in T23: red baseline, missing worktrees, and `cherry-pick --continue` bypassing the gate's silencer check.
  - A session stopped at a pause resumes without asking for the go-ahead (T71).
  - Two features created at the same time could take the same `NNN`, and so the same worktree folder and branch (T78).
  - Two fallback-file edges: an empty stdin appends a header-only entry, and a partial write duplicates an entry (T48, T49).
- **Behavior evals (T52).** The evals were never run. Some graders can fail a correct run or accept an unfilled placeholder: `input_match` scans whole tool inputs, the `**/*.py` glob, and `ask | pre-approved`. Others check too little: only `S2.md`, and no `-F` commits. The structure test skips the eval limits. Review them before the first run.

### Plugin problems found and improvement notes

Problems the run found in the plugin, besides the incidents above:
- A read-only reviewer can still create files through Bash (`uv run` left a `uv.lock`), and the audit did not report it.
- App worktrees under `.claude/worktrees/` disturb the gates unless they are excluded.
- The role hook stops test-writers and implementers from writing scratch scripts outside the project.
- The commit gate blocks a subagent's `git commit` even in a throwaway repository.
- An orchestrator cannot dispatch agents added during its own run.
- `core.autocrlf` without a `.gitattributes` gives mixed line endings.

The process-reviewer saved notes for S7, S8, S9 and S10, and for the whole feature, in the central file `~/.claude/konundrm-eng/improvements.md`: 36 notes, scrubbed by `improvement_notes.py`. The process-reviewer and the script arrived in S7, so S1–S6 have none. Their main themes:
- prove that the gates guard the tree being worked on, and fail loudly when they do not (raised in all three slices);
- what to do when a role agent is missing from the session;
- count repeated gaps of one kind as a rethink trigger, and prefer fail-closed filters;
- check the slice budget during the slice, and define what counts toward it;
- apply cheap or test-validity suggestions in the same round, instead of growing a backlog;
- give each parallel lane its own insertion anchor and one handover format;
- record the model and effort each subagent really ran with;
- write shell-portable commands in prose;
- ask for the go-ahead again when resuming at a pause;
- say what a contract test over prose may assert, and never judge polarity or meaning with regular expressions (S10);
- rethink earlier when every Critical finding sits in the test, and keep fix rounds from adding new checks (S10);
- integrate each side task as soon as it commits, and give handover notes one place and one format (S10);
- enforce the 72-character commit subject in the commit gate (S10);
- make the whole-feature review sweep every place that restates changed behavior (S10);
- show the run's time, dispatches and added tasks at each checkpoint, and ask before the plan grows past about a quarter (feature);
- run the full check once per task and once per wave, not twice per task (feature);
- re-calibrate the line budget, test hook changes from a linked worktree, and give two requirements that separate two things two mechanisms in the design (feature).

None changed the plugin (R7.5).

## How to test the feature

From the repository root, on `feat/001-guided-slice-delivery` (Python 3.10–3.13, Node, and Claude Code 2.1.292 or later):

1. `npm run check`: lint, types and every hook and contract test pass, ending with `All checks passed.`. The last recorded run had 404 tests. A failing contract test prints `FAIL:` followed by a line that starts with the requirement IDs it protects, for example `R1.7: …`.
2. `claude plugin validate ./plugins/konundrm-eng`: no errors. One warning about the missing icon is expected and is outside this feature.
3. Optional: run the five behavior evals with the plugin's eval command (`claude plugin eval`, cases `P/evals/behavior-*`). They run a model and are not part of the check. Read the eval limits under Suggestions not applied first.

The interactive run, in an empty test project:

1. Create an empty folder, `git init` it, and add a minimal project with a check command. Start Claude Code there with the plugin loaded from this branch (`claude --plugin-dir <repo>/plugins/konundrm-eng`).
2. Run `/konundrm-eng:develop-feature` and describe a small feature that has two slices. The second slice should have two independent parts and one task with two reasonable approaches. Do not pre-approve pauses or decisions. Expect the spec interview and then `specs/001-<slug>/requirements.md`.
3. Approve the spec. Expect `design.md` and `tasks.md`, with each slice ending in a `### Partitions` table: S2 should have one wave with two partitions. The plan approval shows the task's `- Decision:` with the options, pros and cons, and a recommendation for you to choose.
4. Choose an option. Expect the plan to record `- Decision: <option> (user)` with the options kept below it, and the `Checkpoints:` and `Decisions:` header lines to say `ask`. Then expect a separate question: build S2's partitions in parallel? If the checks cannot run at the same time on the machine, the session says why instead.
5. Answer yes, and let S1 build. Expect red → green → spec and code review per task, and one commit per task with a `Task: T<n>` line.
6. At the end of S1, expect a stop. A commit `docs(<scope>): summarize slice S1` adds `specs/<slug>/summaries/S1.md`. The session shows the reading order, with files and line ranges, and asks two or three short questions. Answer one wrong: the session explains the answer with file and lines, and still waits for your go-ahead. It does not hold the go-ahead until you answer right.
7. Give the go-ahead. Expect the first S2 partition to be built in this session. The second is built in its own `--partition P<k>` session, in a Git worktree outside the project folder (`../<repo>-worktrees/`). Opening a new session meanwhile shows the next task of each partition. Each partition then gets cherry-picked onto the feature branch one at a time, with the full check after each, and the worktrees are removed without `--force`.
8. After S2's checkpoint, expect Phase 4: the whole-feature spec review, the final verification, `specs/<slug>/summary.md` and the `Status: Done` commit. Then the delivery choice: one stacked pull request per slice (the default) or a single one. If a task is high risk, choosing single warns that `risk:high` will cover the whole feature. Decline the push.
9. Open `~/.claude/konundrm-eng/improvements.md`. Expect new dated entries tagged with the project, the feature and the scope (`slice S1`, `slice S2`, `feature`). They should contain no code blocks, secrets or e-mail addresses from the test project. If that file cannot be written, the notes land in `specs/<slug>/improvement-notes.md` and the session says so.
