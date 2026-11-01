# Feature summary: Flujo más eficiente (002)

- **Spec:** [requirements.md](requirements.md) · **Design:** [design.md](design.md) · **Tasks:** [tasks.md](tasks.md)
- **Slices:** S1–S13 · **Tasks:** T1–T44 (T42 joined S1; T43–T44 came from Phase 4)

## Spec: problem and goals

The run that built the 0.6.0 (80 tasks, 5 sessions) spent 57% of its price-weighted tokens in the
orchestrators, whose every turn rereads the whole conversation (the main session reread a median of
382k tokens in each of its 1,087 turns), ran the full check about 290 times (5.7 h), mostly because
the implementer and the gate repeated it on every task, ran its 221 reviews one after another, paid
about 0.65 s of hooks per shell command and could not be measured without hand-made scripts. The
feature keeps every task guarantee (a red test, five green runs, spec and code reviews on the final
code, a green check and one commit) while giving each slice a fresh orchestrator session, running
the full check once per task unless something changed, launching a task's reviews at once, moving
the flow's bookkeeping into one-call plugin commands, making the hooks cheaper per command, and
measuring a run from its transcripts.

## Design: module ownership

| Module | Owns |
| --- | --- |
| `P/hooks/scripts/tasks_document.py` | reading `tasks.md`: base commit, each task's `Covers:`, the `Checkpoints:` line |
| `P/hooks/scripts/task_commits.py` | the task commits in `<base>..HEAD` and their `Rounds:` trailer (new) |
| `P/hooks/scripts/quality_check.py` (+ `record_check_result.py`) | remembering the tree of the last passing check beside the repository |
| `P/hooks/scripts/task_ledger.py` | `status`, `message` and `close-slice`: the feature's state, a task's commit message and the slice pause's bookkeeping, one call each (new) |
| `P/hooks/scripts/session_doctor.py` | naming the next task at session start, by commits |
| `P/hooks/scripts/working_tree.py` | the shared Git runner |
| `P/hooks/scripts/metrics_report.py` | per-task review rounds in the impact report, from either plan format |
| `P/hooks/scripts/audit_subagent_changes.py` | the audit when several reviewers run at once |
| `P/hooks/scripts/run_slices.py` | chaining headless sessions, one per slice (new) |
| `P/hooks/scripts/deliberate_stops.py` | reading the `RED:` and `BLOCKED:` stop lines the same way for the stop gate and `run_slices.py` (new, out of `quality_gate.py`) |
| `P/hooks/run.sh` | the fast path that skips Python for the check recorder on commands that are not the check |
| `P/hooks/scripts/session_costs.py` | measuring a run from its transcripts (new) |
| `P/agents/*.md` | what each role runs |
| `P/skills/develop-feature/SKILL.md`, `reference/dispatch-prompts.md` | the flow: parallel reviews, gate, commit, slice pause, new session |
| `P/skills/writing-plans/templates/tasks.md` | the plan's `Sessions:` line |
| `P/skills/committing-changes/SKILL.md` | the task commit with the built message |
| `P/skills/measure-impact/SKILL.md` | the cost report inside the impact report |
| `P/.claude-plugin/plugin.json`, `P/CHANGELOG.md`, `README.md` | version 0.7.0 and its documentation |

`P` is `plugins/konundrm-eng`.

## Slice summaries

| Slice | Delivers | Tasks | Summary |
| --- | --- | --- | --- |
| S1 | the check recorder no longer starts Python for commands that are not the check | T1–T4, T42 | [summaries/S1.md](summaries/S1.md) |
| S2 | task commits found by range, and the passing check's tree kept beside the repository | T5–T7 | [summaries/S2.md](summaries/S2.md) |
| S3 | `task_ledger.py status`: the feature's state in one call | T8–T10 | [summaries/S3.md](summaries/S3.md) |
| S4 | the task commit's message, the slice pause's bookkeeping and the session start, by commits | T11–T15 | [summaries/S4.md](summaries/S4.md) |
| S5 | each role runs only what it needs | T16–T19 | [summaries/S5.md](summaries/S5.md) |
| S6 | a task's reviews at once | T20–T23 | [summaries/S6.md](summaries/S6.md) |
| S7 | gate and commit without a repeated check; resume by range | T24–T26 | [summaries/S7.md](summaries/S7.md) |
| S8 | the pause closes the slice and the feature goes on in a new session | T27–T30 | [summaries/S8.md](summaries/S8.md) |
| S9 | `run_slices.py`: sessions chained from a terminal | T31–T32 | [summaries/S9.md](summaries/S9.md) |
| S10 | `session_costs.py`: tokens and time per role | T33–T35 | [summaries/S10.md](summaries/S10.md) |
| S11 | the measurement leaks no content and is offered from the impact report | T36–T39 | [summaries/S11.md](summaries/S11.md) |
| S12 | version 0.7.0, its changelog and README | T40–T41 | [summaries/S12.md](summaries/S12.md) |
| S13 | the measurement skips malformed tool blocks and times without a zone, and the check runs as given so the commit reuses it (Phase 4's gaps) | T43–T44 | [summaries/S13.md](summaries/S13.md) |

## Decisions

- How `run.sh` reads the event before deciding (T1): a `read` loop of builtins over all of stdin |
  `head -c 8192` for the start, decide with `case`, drain the rest with `cat >/dev/null` →
  **`head -c 8192`** (user)
- A command with a JSON escape (T42, added to S1 when measurements showed the fast path reached
  1.7% of the 0.6.0's commands): every escape goes to Python | decide on the escaped text when the
  check word has no `"`, `\` or `/` → **decide on the escaped text** (user approved adding T42:
  "Sí, agrégala")
- What a re-review gets as "what changed" (T21): its previous findings and the fix round's report
  (files and what changed in each) | its previous findings and a `git diff` against a tree snapshot
  taken before the fix → **the fix round's report** (user)
- A fourth ending for `run_slices.py` (R1.4, during T31): stop only on done, `BLOCKED:` or a failure
  | also stop on `RED:`, a session waiting for a person's decision → **also `RED:`** (user, plan
  change of 2026-11-01: "Detener ante RED: (Recomendado)")
- What counts as an orchestrator dispatch (T33): each orchestrator session transcript | each Agent
  call of the orchestrator → **each session transcript** (recommended)
- The check when no `--check-pattern` is given (T34): the project's check command as
  `quality_check.find_check_command` finds it from the current folder | a fixed pattern of the usual
  forms → **the project's check command** (recommended)
- How a Bash or PowerShell command line is read (T34): each simple command the gate's separator
  finds | the pattern over the whole line → **each simple command** (recommended)
- The 90th percentile of context per turn (T35): nearest rank | linear interpolation → **nearest
  rank** (recommended)
- What `session_costs.py` does when reading a transcript raises (T36): `main()` writes one fixed
  line with the error's type and the transcript's path, exit 1 | each error raised without the text
  it read, traceback kept → **one fixed line** (recommended)
- What a line missing fields is (T37): skip and count a line that is not UTF-8, not JSON, not an
  object or has a non-ISO timestamp, and a user or assistant line missing what the report reads |
  skip only lines that are not JSON or not objects → **the full field check** (recommended)
- A subagent transcript whose `meta.json` is missing, not JSON or without an `agentType` name
  (T37): count its lines under the fixed role `unknown` | skip the transcript and count its lines as
  skipped | leave it an error → **role `unknown`** (recommended)
- Where the `\\?\` prefix goes (T38): on Windows, once on each folder from the command line, made
  absolute, and off every printed path | only on paths of 260 characters or more → **once per
  folder** (recommended)
- The version the test requires in `plugin.json` (T40): 0.7.0 or later, compared as numbers, plus
  a [0.7.0] changelog entry looked up by version | exactly "0.7.0" → **0.7.0 or later** (recommended)
- Where the README test looks for each part (T41): the session per entrega and `Sessions: single`
  in `### Cómo avanza una feature`, chaining sessions and measuring a run in `## Uso` | the whole
  README → **per section** (recommended)
- What counts as measuring a run (T41): "transcripci" next to `session_costs.py` or
  `measure-impact` | `session_costs.py` by name → **either name** (recommended)
- The R6.4 gap found by the whole-feature spec review (Phase 4): a new task T43 in a slice S13 |
  narrow R6.4 to the documented limit → **T43** (user, 2026-11-01: "Tarea nueva T43
  (Recomendado)")
- Where the feature finishes after S13 (Phase 4): this session (`Sessions: single`) | a new session
  per slice → **this session** (user, 2026-11-01: "En esta sesión (Recomendado)")
- How many runs the same-task comparison makes (Phase 4): 8 (2 tasks × 2 versions × 2
  repetitions) | 4 (one repetition) → **8** (user, 2026-11-01: "Mantener 8")
- How the remaining runs go (Phase 4): in pairs, the same task on both versions at once | all at
  once | one after another → **in pairs** (user, 2026-11-01: "De a 2, en pares (Recomendado)")
- What to do about the trimmed checks the comparison found (Phase 4): T44 and measure again | T44
  without measuring again | leave it for the next version → **T44 without measuring again**
  (user, 2026-11-01: "T44 sin medir de nuevo")
- The two lines the whole-feature re-review still found after T43 (a `type` that is not text, JSON
  nested past Python's recursion limit; Claude Code writes neither): a task that closes the whole
  class with a property test | a task for these two | narrow R6.4 → **narrow R6.4**, now written
  in requirements.md and the [0.7.0] Known limitations (user, 2026-11-01: "Acotar R6.4")
- When to compare 0.6.0 and 0.7.0 on the same task (asked during S5): in Phase 4 | not at all →
  **in Phase 4** (user, 2026-10-31: "En la Fase 4"); measured in
  [evidence/diagnosis.md](evidence/diagnosis.md)

## Requirements, tests and evidence

| Requirement | Task | Test | Evidence |
| --- | --- | --- | --- |
| R1.1, R1.2, R1.3 | T28 | `P/hooks/tests/contract/test_flows.py::test_feature_continues_in_a_new_session_after_each_slice` | test output |
| R1.4 | T31 | `P/hooks/tests/test_run_slices.py::test_runs_one_session_per_slice_until_done_blocked_or_failed` | [evidence/T31.md](evidence/T31.md) |
| R1.5 | T32 | `P/hooks/tests/test_run_slices.py::test_stops_when_a_session_adds_no_commit` | test output |
| R1.6 | T29 | `P/hooks/tests/contract/test_flows.py::test_handoff_stops_on_uncommitted_changes` | test output |
| R1.7 | T30 | `P/hooks/tests/contract/test_flows.py::test_sessions_single_keeps_the_feature_in_one_session` | test output |
| R1.8 | T5, T6, T8, T26 | `P/hooks/tests/test_tasks_document.py::test_reads_the_base_commit_and_each_tasks_covers`, `P/hooks/tests/test_task_commits.py::test_finds_task_commits_only_after_the_base_with_their_rounds`, `P/hooks/tests/test_task_ledger.py::test_status_shows_next_task_built_tasks_tree_and_check`, `P/hooks/tests/contract/test_flows.py::test_resume_uses_status_and_the_base_range` | test output |
| R1.9 | T6, T14 | `P/hooks/tests/test_task_commits.py::test_finds_task_commits_only_after_the_base_with_their_rounds`, `P/hooks/tests/test_session_doctor.py::test_counts_committed_tasks_as_done_and_names_the_first_without_a_commit` | test output |
| R2.1 | T16 | `P/hooks/tests/contract/test_agents.py::test_test_writer_runs_only_its_own_tests` | test output |
| R2.2 | T17 | `P/hooks/tests/contract/test_agents.py::test_reviewers_rely_on_the_orchestrators_verification_output` | test output |
| R2.3 | T18 | `P/hooks/tests/contract/test_agents.py::test_finding_verifier_runs_only_what_its_finding_needs` | test output |
| R2.4 | T19, T44 | `P/hooks/tests/contract/test_agents.py::test_implementer_runs_the_full_suite_only_in_the_final_check`, `P/hooks/tests/contract/test_flows.py::test_the_check_runs_alone_so_its_pass_is_recorded` | test output |
| R2.5 | T24, T44 | `P/hooks/tests/contract/test_flows.py::test_gate_runs_the_check_only_when_status_is_not_green`, `…::test_the_check_runs_alone_so_its_pass_is_recorded` | [evidence/diagnosis.md](evidence/diagnosis.md) |
| R2.6 | T24 | `P/hooks/tests/contract/test_flows.py::test_gate_runs_the_check_only_when_status_is_not_green` | test output |
| R2.7 | T11, T25 | `P/hooks/tests/test_task_ledger.py::test_message_builds_the_task_commit_message_from_the_plan`, `P/hooks/tests/contract/test_flows.py::test_task_commit_goes_through_the_gate_with_its_message` | [evidence/T25.md](evidence/T25.md) |
| R2.8 | T13, T27 | `P/hooks/tests/test_task_ledger.py::test_close_slice_checks_boxes_and_writes_rounds_from_the_commits`, `P/hooks/tests/contract/test_flows.py::test_slice_checkpoint_closes_the_slice_in_the_summary_commit` | test output |
| R2.9 | T15 | `P/hooks/tests/test_metrics_report.py::test_reads_rounds_written_by_close_slice_and_per_task_alike` | test output |
| R3.1, R3.5 | T20 | `P/hooks/tests/contract/test_flows.py::test_reviews_launch_at_once_with_no_writer_running` | test output |
| R3.2, R3.3 | T21 | `P/hooks/tests/contract/test_flows.py::test_findings_share_one_fix_round_and_re_reviews_get_what_changed` | test output |
| R3.4 | T22 | `P/hooks/tests/contract/test_flows.py::test_task_commits_only_after_its_reviews_pass_on_its_final_code` | test output |
| R3.6 | T23 | `P/hooks/tests/test_audit_subagent_changes.py::test_restores_a_reviewers_change_whatever_order_concurrent_reviewers_stop` | test output |
| R4.1 | T7, T8, T9 | `P/hooks/tests/test_record_check_result.py::test_a_passing_check_remembers_its_tree_beside_the_repository`, `P/hooks/tests/test_task_ledger.py::test_status_shows_next_task_built_tasks_tree_and_check`, `P/hooks/tests/test_task_ledger.py::test_status_names_the_next_task_of_each_partition_in_the_current_wave` | test output |
| R4.2 | T5, T11, T25 | `P/hooks/tests/test_task_ledger.py::test_message_builds_the_task_commit_message_from_the_plan`, `P/hooks/tests/contract/test_flows.py::test_task_commit_goes_through_the_gate_with_its_message` | [evidence/T25.md](evidence/T25.md) |
| R4.3 | T25 | `P/hooks/tests/contract/test_flows.py::test_task_commit_goes_through_the_gate_with_its_message` | [evidence/T25.md](evidence/T25.md) |
| R4.4 | T12 | `P/hooks/tests/test_task_ledger.py::test_message_refuses_an_unknown_or_already_committed_task` | test output |
| R4.5 | T13, T27 | `P/hooks/tests/test_task_ledger.py::test_close_slice_checks_boxes_and_writes_rounds_from_the_commits` | test output |
| R4.6 | T10 | `P/hooks/tests/test_task_ledger.py::test_status_names_the_file_and_line_when_the_plan_cannot_be_read` | test output |
| R4.7 | T24, T26 | `P/hooks/tests/contract/test_flows.py::test_gate_runs_the_check_only_when_status_is_not_green`, `P/hooks/tests/contract/test_flows.py::test_resume_uses_status_and_the_base_range` | test output |
| R5.1 | T1, T42 | `P/hooks/tests/integration/test_hook_scripts.py::test_run_sh_skips_python_for_a_command_that_is_not_the_check`, `…::test_run_sh_skips_python_for_a_quoted_command_that_is_not_the_check` | [evidence/final.md](evidence/final.md), step 3 |
| R5.2 | T2 | `P/hooks/tests/integration/test_hook_scripts.py::test_run_sh_runs_python_for_the_check_and_a_custom_check` | [evidence/final.md](evidence/final.md), step 3 |
| R5.3 | T3, T42 | `P/hooks/tests/integration/test_hook_scripts.py::test_run_sh_runs_python_when_it_cannot_tell_the_command` | test output |
| R5.4 | T4 | `P/hooks/tests/integration/test_hook_scripts.py::test_run_sh_passes_the_event_intact_to_the_gate_and_the_guard` | [evidence/T4.md](evidence/T4.md) |
| R6.1 | T33, T34 | `P/hooks/tests/test_session_costs.py::test_reports_tokens_weights_shares_and_active_time_per_role`, `…::test_counts_check_runs_test_runs_and_parallel_dispatches` | [evidence/final.md](evidence/final.md), step 4 |
| R6.2 | T35 | `P/hooks/tests/test_session_costs.py::test_reports_the_busiest_orchestrators_context_per_turn` | [evidence/final.md](evidence/final.md), step 4 |
| R6.3 | T36 | `P/hooks/tests/test_session_costs.py::test_never_prints_message_command_or_result_content` | [evidence/T36.md](evidence/T36.md) |
| R6.4 (narrowed in Phase 4) | T37, T43 | `P/hooks/tests/test_session_costs.py::test_skips_and_counts_invalid_lines`, `…::test_skips_and_counts_lines_with_a_malformed_tool_block_or_a_time_without_a_zone` | test output |
| R6.5 | T38 | `P/hooks/tests/test_session_costs.py::test_reads_transcripts_past_the_windows_path_limit` | [evidence/final.md](evidence/final.md), step 4 |
| R6.6 | T39 | `P/hooks/tests/contract/test_skills.py::test_measure_impact_adds_session_costs_when_given_transcripts` | test output |
| R7.1 | T40 | `P/hooks/tests/contract/test_release.py::test_0_7_0_changelog_names_each_mechanism` | test output |
| R7.2 | T40, T41 | `…::test_0_7_0_changelog_names_each_mechanism`, `P/hooks/tests/contract/test_release.py::test_readme_describes_sessions_per_slice_and_measuring_a_run` | test output |

- **Final verification:** [evidence/final.md](evidence/final.md) (steps 1–5) and
  [evidence/diagnosis.md](evidence/diagnosis.md) (step 5, with the measured A/B comparison); step 6
  belongs to the next feature.

## Rethinks

- none

## Refuted findings

- none (the four Critical findings sent to a finding-verifier, one in T25 and three in T31, were all
  CONFIRMED and fixed)

## Suggestions not applied

Each slice summary lists its own in full (`summaries/S<k>.md`, under "Review rounds and rethinks"
or "Open risks"). The ones a user of the plugin would notice first:

- T41 code review: README `## Uso` step 4 does not say to run `run_slices.py` from the project's
  root, that the headless sessions need permission to edit and run commands (Claude flags after
  `--`, or settings that allow them) or the run ends in `STALLED:` or `FAILED:`, nor that the plan
  must be `Approved` with a base commit; step 8's plugin folder is not quoted although the real
  install path can hold a space. Left out because it is wording beyond T41's criteria; it is the
  first follow-up.
- T41 spec and code reviews: the README's "sus revisiones de spec, de código y de seguridad corren
  al mismo tiempo" reads as a security review on every task (it runs on high-risk tasks only); the
  `hooks/run.sh` line of its tree overstates the fast path; "seis herramientas" counts
  `run_slices.py`, which no skill runs.
- T44 code review: the new rule says "with no pipe, redirection or other command around it" but
  does not say that a leading `cd <root> &&` is still fine (the recorder accepts it and needs the
  call to start in the project's root); the test's "why" rule for the gate also matches an older
  sentence; two lines of `develop-feature/SKILL.md` pass the 100-column wrap. Left out: the
  reviews passed, and Suggestions do not start another round.
- T20 code review, still open: `agents/security-reviewer.md` lines 3 and 12 say it runs after the
  code review, although the three reviews now run at once (the flow in `develop-feature` is right;
  the agent's own description is stale).
- T40 code review: the [0.7.0] changelog entry says an unreadable plan prints `<file>:<line>`, but a
  plan that cannot be read at all prints `<path>: cannot read the plan`, with no line.
- T31 and T32 reviews: `run_slices.py` checks the plan only before the first session, counts a
  session as progress when HEAD's SHA changed (`git rev-list --count` would match R1.5's wording),
  sees no stop line when `--output-format json` or `stream-json` follows `--`, and on Windows
  `shutil.which("claude")` looks in the current folder first.
- T34 code review: a user-given `--check-pattern` is searched anywhere in a command (start it with
  `^`); a chained check keeps only its first simple command; the test-runner list is fixed.
- T37 and T38 reviews: a folder that does not exist gives an empty table with no warning; subagents
  that workflows start are not read.
- T42: raising the fast path's value-cut budget from 64 to 256 steps would put 2% more commands
  back on the fast path.
- Test tidy-ups across slices (shared helpers repeated in several test files, split tests, unit
  tests for helpers covered only through their callers), as each slice summary lists.

## How to test the feature

1. `npm run check` and `claude plugin validate ./plugins/konundrm-eng`: both pass.
2. In a fresh repository with a two-slice plan (Approved, a base commit), commit a task with
   `msg=$(sh plugins/konundrm-eng/hooks/run.sh task_ledger.py message specs/<slug>/tasks.md T1 --subject "feat(x): build T1" --rounds "spec 1 · code 1 · escalations 0") && git add -A && git commit -F "$msg"`:
   `task_ledger.py status specs/<slug>/tasks.md` names T2 as next while T1's box is still empty;
   `message` for an unknown or committed task exits 1 and writes nothing; `close-slice` checks the
   boxes and writes the rounds from the commits; `run_slices.py specs/<slug> --claude <fake>` ends
   with `DONE`, `BLOCKED: …`, `RED: …`, `FAILED: exit <n>` or `STALLED: session <k> added no
   commit` as the fake sessions do (`evidence/final.md`, step 2).
3. Send the check recorder, through `run.sh`, the PostToolUse event of `ls -la` 20 times: the mean
   is under half of the 0.6.0 launcher's; after an event for a passing `npm run check`, `status`
   says `check: green for this tree` (`evidence/final.md`, step 3).
4. `sh plugins/konundrm-eng/hooks/run.sh session_costs.py <transcript folder>…` from the project's
   root: a table per role, the busiest orchestrator's context per turn and `skipped lines: <n>`,
   with no message, command or result text (`evidence/final.md`, step 4).
5. Read `evidence/diagnosis.md`: the 0.6.0 and the 0.7.0 building the same two tasks, measured.
6. In the next feature, with pauses pre-approved and two slices: the second slice runs in a new
   session, each task commit carries its rounds, the summary commit checks the boxes, and
   `/konundrm-eng:measure-impact` with the transcript folders shows the reviews in parallel and one
   full check per task.
