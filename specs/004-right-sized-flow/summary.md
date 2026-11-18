# Feature summary: Tareas del tamaño justo y revisiones proporcionales al cambio

- **Spec:** [requirements.md](requirements.md) · **Design:** [design.md](design.md)
- **Slices:** one · **Plugin version:** 0.9.0

<!-- This feature has no tasks.md and no slice summaries. The user delegated the criteria ("ese
criterio defínelo tú que sabes mejor") and handed over the project while away, so it was built in
one line of work, outside the plugin's own task loop. What was kept: the spec and the design
before any text, a contract test for each rule, the full check green before each commit, and
adversarial reviews of the design and of the finished change. Every fact below comes from
requirements.md, design.md, evidence/final.md and the commits. -->

## Spec: problem and goals

`writing-plans` split every feature, however small, into tasks of one behavior, and
`develop-feature` gave each one its own cycle of test-writer, implementer, spec review, code
review, five runs, check and commit. That cost is per cycle, not per line: in feature 002's
measurement a task of 30 lines and one of 110 both took 12.4 minutes, and the three features of
this repository hold 79, 44 and 12 tasks. A small change the user asked for on built work became a
new task with its own approval and full cycle, and inside a task every fix round repeated every
review. The goals: fewer cycles without losing the trace from each criterion to its test; a small
requested change made at once and reviewed in proportion to what it touches; after a change, only
the reviews it concerns; an explicit, conservative criterion that leaves high risk out; a visible
record of what was merged and of the reviews that were not repeated; and a criterion the user can
move when approving a plan.

## Design: module ownership

| Module | Owns |
| --- | --- |
| `writing-plans` (and its `tasks.md` template) | listing one behavior per line, consolidating the related low-risk ones into one task with a `Tests:` list, the header line `Consolidation:` and the totals shown at approval |
| `develop-feature` Phase 3 (steps 1 and 2), `reference/dispatch-prompts.md`, agents `test-writer`, `implementer`, `spec-reviewer` and `rethinker`, skill `test-driven-development` | building a task that lists several tests in one cycle: one test-writer dispatch, one implementer that sees each test red before its code, every listed behavior checked against its own test |
| `develop-feature`, section `## Reviews after a change` (`fix-bug` step 6 links to it) | which reviews run again after a change, decided from the change's own diff against a `git write-tree` mark |
| `develop-feature`, section `## Adjustments`, and `reference/adjustments.md` with three prompts | classifying a change the user asks for (adjustment or plan change), the task in progress, a finished feature, who makes it and when, and the procedure |
| `committing-changes` (`### Inside develop-feature`, `### Inside fix-bug`) | an adjustment's own commit and its Git note (`Adjusts:`, `Reviews:`, `Asked:`); fix-bug's commit staging the reviewed fix |
| `develop-feature/templates/slice-summary.md` and `feature-summary.md` | where adjustments and the reviews that were not repeated are listed |
| `engineering-standards` (sections 2, 7 and 10) | the principle every role reads, linking to the table instead of repeating it |
| `measure-impact` | the warning that per-task numbers are not comparable across this version |
| `hooks/scripts/tasks_document.py` and `task_ledger.py` | reading a task's rounds, and choosing the line `close-slice` rewrites, only from the task's own `- Rounds:` field (the one script change, a fix) |
| `hooks/tests/contract/`, `evals/`, `README.md`, `CHANGELOG.md`, `plugin.json` | 315 contract rules, two behavior evals, the documentation and version 0.9.0 |

A consolidated task is one task for `task_ledger.py`, `session_doctor.py`, `run_slices.py` and
`metrics_report.py`: one ID, one commit, one note. No hook changed.

## How it was built

| Step | What | Result |
| --- | --- | --- |
| 1 | Map of the plugin: 15 readers over its parts, 2 critics that cross-checked their claims | where the "one test" wording lives, what the ledger and the hooks need, the sizes of the real tasks |
| 2 | Spec and first design, with contract tests written first | the first draft of the three rules |
| 3 | Design review: 6 reviewers with different lenses, 6 skeptics | 69 findings; the second design (lines merge in any order, 300 lines, the `Consolidation:` line, the tree mark, the narrowed "only text" row, the criterion edited first, the note and the next summary as the record) |
| 4 | The text of the skills, agents, prompts and templates, with its tests | commits `ce97a8c` and `d6c5ba6` |
| 5 | Final review of the finished change, round 1: 5 reviewers | 66 findings, none a blocker; applied in `87ee951`, `e38e5ed`, `e28d1d1` and `6458767` |
| 6 | Final review, round 2: 7 reviewers that checked the fixes of round 1, the tests and what the user asked for, and 5 skeptics | 58 findings, none a blocker; 13 major, of which 9 confirmed and 4 partly; applied in `64ece65`, `1b36602`, `a2e6017` and `6049730` |
| 7 | Mutation check of the contract tests: one rule removed or inverted at a time, 462 edits in four sets | 453 fail a test; the nine left are explanations or repeated sentences ([evidence/final.md](evidence/final.md), section 2) |
| 8 | Regression review of the fixes of round 2: 3 reviewers that followed the changed paths, ran their commands and compared every copy of a changed rule, and 5 skeptics | 15 findings that were 10 distinct residues, none a blocker; 3 major, all confirmed; applied in `71f21a5` |

## Decisions

The user delegated them; each one can be changed without touching a script.

- Which behaviors merge: every risk level | low and medium | low only → **low only by default;
  medium is a choice per plan (`low and medium`, cases of one rule, at most three); high never**
  (replaying plans 001 and 002, medium would have merged 2 tasks of 79 and none of 44)
- The limit of a consolidated task: consecutive lines of one file up to 200 lines | lines in any
  order with one owner up to 300 lines → **five behaviors and about 300 changed lines, never more
  than the pull request budget** (the first draft left 75 of 79 and 42 of 44 tasks; this one, 62
  and 36 in the same replay; a reviewer's mechanical replay with the real commit sizes, 57 and 38)
- An invariant that the code of one task keeps: a `property` task of its own | tested with that
  task → **with that task**, when one medium- or high-risk line makes it hold; a `property` line
  of its own only when it takes several lines, or a low one
- A documentation chore: a task of its own | inside the task it documents → **inside the
  low-risk task it documents**
- The shape of the unit: review batches over atomic tasks | merging at build time | one ordinary
  task with a `Tests:` list → **one ordinary task**, so the ledger, the hooks and the impact
  report need no change
- Who decides which reviews repeat: a script that classifies the diff | a table the orchestrator
  applies to the diff → **the table**, because knowing whether behavior changed needs reading the
  diff, and the plugin's only classifier treats every Markdown file as documentation
- How a change is told apart inside a task: the index | a tree SHA → **`git add -A && git
  write-tree`**, because a writer that stages moves the index and the change would look empty
- A fix round that only adds tests: both reviews | the spec review alone → **the spec review
  alone**; a rename: both reviews | the code review alone → **the code review alone**; a message
  that was only reworded, in the code and in the tests that assert it: both reviews | the spec
  review alone → **the spec review alone**. A value the code decides with (a limit, a default)
  still gets both
- A rename of a name `design.md` gives: a plan change | an adjustment → **an adjustment**, while
  nothing outside the files the feature's tasks list uses the old name
- A change that reports a defect: never typed `fix` | typed `fix` with `Escaped-gate:` → **`fix`
  with `Escaped-gate:`**, so the impact report counts it
- Where an adjustment is recorded: the summary, in the adjustment's own commit | a Git note, and
  the next summary that is written → **the note and the next summary**, so the tree that passed
  the check is the tree that is committed
- Where a review that was not repeated is recorded: the session's todo list | the task's note →
  **the task's note** (`Not repeated:`), which a resumed session and a partition's integration
  keep
- A change asked on the task in progress: start the task over | join the task → **joins the
  task**, recorded as `- Change:` in its block; on a `high` task it is always a plan change
- A plan change on a finished feature: reopen it always | only while its pull requests are open →
  **only while they are open, no later feature has commits after it and the ledger still lists
  every task**; otherwise it is a new feature, because the ledger counts later features'
  commits and, without its notes, would send the next session to build tasks that are built
- The branch of an adjustment to a merged feature: from the local default branch | from the
  remote's → **from the remote's, after a fetch**, because a merge made on GitHub is not in the
  local default branch; its pull request is listed and measured against the remote's too
- Which tasks changed a file, on a finished feature: every commit up to `HEAD` | up to the
  feature's final commit → **up to its final commit**, so a later feature's tasks do not count
- A change on the task in progress that the code already makes: commit or stash its tests, as
  an adjustment does | keep them in the task → **keep them in the task**
- Enforcement: hooks | instructions held by contract tests → **instructions** (a non-goal); what
  is written down (notes, summaries) lets a person audit them
- Plans already written: consolidate them again | build them as they are → **as they are**
- The plan reader's misread of a quoted Rounds line: leave it | fix it → **fixed**, also for a
  wrapped line and for `close-slice`, because the new `- Change:` line holds the user's words
  verbatim

## Requirements, tests and evidence

Contract tests are in `plugins/konundrm-eng/hooks/tests/contract/`.

| Requirement | Test | Evidence |
| --- | --- | --- |
| R1.1–R1.9 | `test_skills.py::WritingPlansConsolidationTest::test_writing_plans_consolidates_related_low_risk_tasks` | test output; eval not run |
| R1.2, R1.3, R1.8, R3.1, R3.2 (the principle) | `test_skills.py::RightSizedFlowPrincipleTest::test_standards_state_what_is_merged_and_which_reviews_run_again` | test output |
| R2.1–R2.3, R3.9 | `test_flows.py::RightSizedFlowTest::test_a_task_that_lists_several_tests_is_built_in_one_cycle` | test output |
| R2.1–R2.6, R3.8, R3.9, R4.3 (the roles) | `test_agents.py::TaskWithSeveralTestsTest::test_writers_handle_a_task_that_lists_several_tests` | test output |
| R2.2, R2.3, R2.5, R3.1, R3.2, R3.7, R3.9, R4.10 (the edges of one cycle) | `test_flows.py::RightSizedFlowEdgesTest::test_the_one_cycle_build_covers_its_property_tests_and_its_second_dispatches` | [evidence/final.md](evidence/final.md), section 3 |
| R3.1–R3.3, R3.5–R3.9 | `test_flows.py::RightSizedFlowTest::test_only_the_reviews_a_change_concerns_run_again` | evidence, section 3 (the mark) |
| R3.4 | `test_flows.py::ReviewFlowTest::test_task_commits_only_after_the_reviews_its_final_code_needs` | test output |
| R3.8, R4.8 (the record) | `test_flows.py::RightSizedFlowEdgesTest::test_reviews_not_repeated_and_adjustments_leave_a_record_that_travels`, `test_templates.py::AdjustmentsSummaryTemplateTest::test_summaries_list_the_adjustments_and_their_reviews` | evidence, section 3 |
| R4.1, R4.2, R4.3, R4.6, R4.10, R4.11 | `test_flows.py::RightSizedFlowTest::test_a_change_the_user_asks_for_is_classified_first`, `test_flows.py::DevelopFeatureFlowTest::test_changes_asked_at_a_checkpoint_are_adjustments_or_new_tasks` | test output |
| R4.2, R4.10, R4.11 (a finished feature, the task in progress) | `test_flows.py::RightSizedFlowEdgesTest::test_a_finished_feature_and_a_task_in_progress_take_a_change_safely` | test output |
| R4.3–R4.5, R4.7–R4.9 | `test_flows.py::RightSizedFlowTest::test_an_adjustment_follows_its_procedure`, `test_flows.py::RightSizedFlowEdgesTest::test_an_adjustment_has_a_branch_a_red_step_that_can_be_met_and_a_safe_set_aside` | evidence, section 3 |
| R4.3, R4.4, R4.6, R4.8, R4.10 | `test_flows.py::RightSizedFlowTest::test_an_adjustment_has_its_prompts_its_commit_and_its_note`, `test_flows.py::FlowDataInNotesTest::test_commits_carry_no_flow_lines_and_keep_their_data_in_notes` | evidence, section 3 |
| R1.1–R1.9, R2.1–R2.5, R3.1–R3.9, R4.1–R4.11, R5.4 (the edges a single edit could remove) | the five tests of `test_right_sized_pins.py::RightSizedFlowPinsTest` | evidence, section 2 (the mutations) |
| R5.1 | the contract tests above, inside `npm run check` | evidence, sections 1 and 2 |
| R5.2 | `test_release.py::BehaviorEvalsTest::test_each_right_sized_flow_mechanism_has_a_behavior_eval` | the evals exist; not run (evidence, section 5) |
| R5.3 | `test_release.py::VersionAndChangelogTest::test_0_9_0_changelog_names_each_mechanism`, `test_release.py::ReadmeTest::test_readme_describes_consolidated_tasks_and_adjustments` | test output |
| R5.4 | `test_skills.py::RightSizedFlowPrincipleTest::test_measure_impact_says_task_counts_changed_meaning` | test output |
| the plan reader fix | `hooks/tests/test_tasks_document.py::ReadTasksTest::test_a_rounds_text_quoted_in_another_field_is_not_the_tasks_rounds`, `hooks/tests/test_task_ledger.py::CloseSliceTest::test_close_slice_leaves_a_rounds_text_wrapped_inside_another_field` | evidence, section 4 |

- **Final verification:** [evidence/final.md](evidence/final.md). Item 1 (the check and the plugin
  validation) passes. Items 2 and 3 (the two evals, and a feature built with 0.9.0 and measured)
  are not done.

## Rethinks

None.

## Refuted findings

None of the 39 blocker and major findings of the design review was refuted; 9 were confirmed only
in part, and the part that did not hold was left out (for example: the red step proves more than
a missing symbol once the implementer sees each test fail, so no second implementer dispatch was
added; a numeric limit in the plan's header was dropped, because the planner cannot apply a line
count exactly).

None of the 13 major findings of the second round was refuted either; 4 were confirmed only in
part. Three were about the tests: the rules did have the gaps, but losing most of them would
have cost extra reviews, not work, so they were rated minor and pinned all the same. The fourth
said that the property tests of the red step would rarely be written, because planning sent
every invariant to a task of its own: 23 of the 33 tasks with invariants in plans 001 to 003
already named no `property` task, so the path was the common one; the planning rule was fixed
because it did not say which invariants get a `property` line.

The regression review's 5 major findings were 3 problems, each found by two reviewers, and all
were confirmed. The skeptics' shorter replacement texts were the ones applied.

## Suggestions not applied

- A helper script that prints the changed paths by kind between two tree snapshots, to feed the
  table: left for later, if the process-reviewer's notes show misclassifications.
- A `Kind: change | defect` line in the adjustment's note: the commit type (`fix`) and the
  `Escaped-gate:` line already say it.
- Starting an approved plan change from the stash of the adjustment that was set aside: the stash
  stays recoverable by its message, and the task loop builds the task from its tests.
- A numeric limit in the `Consolidation:` header line: the limits are in `writing-plans`, one
  sentence to change.
- Listing the reviews not repeated in a partition's report: the task's note carries them, and the
  integration copies it.
- The spec review alone for a changed value (a limit, a default), as for a reworded message: a
  value cannot be searched for as a text can, so both reviews still run. It is the commonest
  small request that still pays four dispatches.
- A documentation chore that documents several tasks still is a task of its own, with both
  reviews.
- On a finished feature, the `docs` commit that adds an adjustment's entry to `summary.md` runs
  the check again, because the commit gate snapshots the whole tree: no small text fix was
  found.
- Pins for nine sentences that explain or repeat a rule (evidence, section 2), and dropping the
  two reasons Phase 0 gives for not trusting `status` on a finished feature.
- Listing the commits made after a finished feature's final commit, in place of ending the
  lookup there: ending the range is one command. Its known limit is a file renamed after the
  final commit, which prints no task and so reads as a plan change, the safe side.
- Outside this feature, already in 0.8.0: `task_ledger.py status` ends in a traceback, not in
  exit code 2, on a `tasks.md` with no task line in the template's format.

## Adjustments

None.

## How to test the feature

1. `npm run check`: it passes, with the contract tests of the feature inside it.
2. `claude plugin validate ./plugins/konundrm-eng`: `Validation passed`.
3. With the `claude` command line signed in:
   `claude plugin eval plugins/konundrm-eng --case behavior-plan-consolidates-related-tasks --allow-tools Write Edit --ablation none --runs 1`.
   The plan it writes merges the four contact-card behaviors, leaves the medium rule alone and
   lists one test per behavior.
4. On Linux or macOS:
   `claude plugin eval plugins/konundrm-eng --case behavior-adjustment-runs-needed-reviews --allow-tools Bash Write Edit --ablation none --runs 1`.
5. Build the next small feature with 0.9.0 and compare, with `/konundrm-eng:measure-impact` and its
   transcripts, the dispatches per behavior with the 4.7 dispatches per task of features 001 to
   003.
