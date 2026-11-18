# Final verification: right-sized tasks and proportional reviews

Run on 2026-11-18 on Windows 11 (Git Bash, Git 2.53, Python 3.14), on the branch
`feat/004-right-sized-flow`. Each section says what was checked, how and the result.

## 1. The check and the plugin validation

`npm run check`, run alone on the tree of the last commit that changes code or tests:

```text
--- Format: uvx --from ruff==0.17.0 ruff format --check .
81 files already formatted
--- Lint: uvx --from ruff==0.17.0 ruff check .
All checks passed!
--- Types (Python 3.10): uvx --from mypy==2.4.0 mypy
Success: no issues found in 32 source files
--- Types (Python 3.13): uvx --from mypy==2.4.0 mypy --python-version 3.13
Success: no issues found in 32 source files
--- Hook tests: ... -m unittest discover -s ...\hooks\tests -t ...\hooks
Ran 512 tests in 282.608s
OK (skipped=1)
All checks passed.
```

Before this feature the same command ran 494 tests. `claude plugin validate ./plugins/konundrm-eng`
prints `✔ Validation passed`; its two directory notes (no icon, no license file) predate this
feature.

## 2. The contract tests fail without the feature

The new contract tests were copied over an export of the 0.8.0 tree (`git archive 4dc55e3`) and
run there: 19 of 85 fail, every one of them a test this feature added or amended.

```text
FAIL: TaskWithSeveralTestsTest.test_writers_handle_a_task_that_lists_several_tests
FAIL: DevelopFeatureFlowTest.test_changes_asked_at_a_checkpoint_are_adjustments_or_new_tasks
FAIL: ReviewFlowTest.test_task_commits_only_after_the_reviews_its_final_code_needs
FAIL: RightSizedFlowTest.test_a_task_that_lists_several_tests_is_built_in_one_cycle
FAIL: RightSizedFlowTest.test_only_the_reviews_a_change_concerns_run_again
FAIL: RightSizedFlowTest.test_a_change_the_user_asks_for_is_classified_first
FAIL: RightSizedFlowTest.test_an_adjustment_follows_its_procedure
FAIL: RightSizedFlowTest.test_an_adjustment_has_its_prompts_its_commit_and_its_note
FAIL: RightSizedFlowEdgesTest.test_reviews_not_repeated_and_adjustments_leave_a_record_that_travels
FAIL: RightSizedFlowEdgesTest.test_the_one_cycle_build_covers_its_property_tests_and_its_second_dispatches
FAIL: RightSizedFlowEdgesTest.test_a_finished_feature_and_a_task_in_progress_take_a_change_safely
FAIL: RightSizedFlowEdgesTest.test_an_adjustment_has_a_branch_a_red_step_that_can_be_met_and_a_safe_set_aside
FAIL: BehaviorEvalsTest.test_each_right_sized_flow_mechanism_has_a_behavior_eval
FAIL: ReadmeTest.test_readme_describes_consolidated_tasks_and_adjustments
FAIL: VersionAndChangelogTest.test_0_9_0_changelog_names_each_mechanism
FAIL: RightSizedFlowPrincipleTest.test_measure_impact_says_task_counts_changed_meaning
FAIL: RightSizedFlowPrincipleTest.test_standards_state_what_is_merged_and_which_reviews_run_again
FAIL: WritingPlansConsolidationTest.test_writing_plans_consolidates_related_low_risk_tasks
FAIL: AdjustmentsSummaryTemplateTest.test_summaries_list_the_adjustments_and_their_reviews
Ran 85 tests
```

The feature is pinned by 203 rules across those tests. A script listed, for each rule, the
sentences of the current text that satisfy it: every rule is met by the sentence it was written
for, none by an unrelated one.

## 3. The commands the new text prescribes

Run in throwaway repositories with the plugin's own scripts, by the author and again by the
reviewers of section 6.

- The mark. After `git add -A && git write-tree`, a writer edited a tracked file, created a new
  one, staged another and deleted one. `git diff --stat <sha>` listed the deleted file, the
  staged one and the edited one, and `git status --porcelain` listed the new file as `??`. The
  plain `git diff --stat` against the index missed the staged file, which is why the text
  compares with the tree and never with the index. The mark prints the same tree SHA as the
  hooks' own snapshot, so the recorded check result does not change.
- A consolidated plan (a `- **Consolidation:**` header, a nested `Tests:` list, a `- Change:`
  line): `task_ledger.py status`, `message`, `record` and `close-slice`, `session_doctor.py` and
  `run_slices.py` read it as before; the task's note is `Task: T2 · Covers: R1.2, R1.3, R1.4`.
- An adjustment's commit and note in one command, then
  `git log --notes=refs/notes/konundrm --format='%h %s%n%N' --grep '^Adjusts:'`: the listing
  prints the adjustment commits and no task commit; `status` and `close-slice` do not take an
  adjustment for a task; a `fix` adjustment with `Escaped-gate:` is counted by `metrics_report.py`.
- fix-bug's commit after a marked fix round: without `git add -A` the commit held the tree from
  before the round (reproduced by two reviewers); with it, the commit holds the reviewed fix.
- The set-aside stash and its recovery by message and SHA work with a message of letters, digits
  and spaces; a message with `[` is not found, which the text now rules out.

## 4. The plan reader fix

`tasks_document.py` read as a task's rounds the first Rounds-shaped text anywhere in its block.
The new unit test failed first (`[(9, 9, 9)] != [None]`) and passes with the fix. On this
repository's own plans the only change is task T1 of feature 003, whose `Test:` line quotes a
Rounds example: it was read as spec 1 · code 2 and its own line says spec 2 · code 2. Totals of
spec, code and escalation rounds, before and after:

| Plan | Tasks | Before | After |
| --- | --- | --- | --- |
| 001-guided-slice-delivery | 79 | 117 · 103 · 1 | 117 · 103 · 1 |
| 002-efficient-feature-flow | 44 | 54 · 56 · 1 | 54 · 56 · 1 |
| 003-live-github-publishing | 12 | 17 · 18 · 0 | 18 · 18 · 0 |

## 5. The evals: not run

- `behavior-plan-consolidates-related-tasks` needs no Git and can run on this machine, but the run
  stopped before the model answered: `exit 1: Not logged in · Please run /login` (the `claude`
  command line had no session). Its only stored result, under
  `plugins/konundrm-eng/evals/results/2026-11-18T03-53-45-020Z` (ignored by Git), is that failed
  attempt. To run it:
  `claude plugin eval plugins/konundrm-eng --case behavior-plan-consolidates-related-tasks --allow-tools Write Edit --ablation none --runs 1`
- `behavior-adjustment-runs-needed-reviews` needs Git, and on Windows the eval runner refuses any
  case that is granted Bash. It has to run on Linux or macOS.

So items 2 and 3 of the final verification in requirements.md are still open. What the contract
tests check is the text of the instructions, not what a model does with them.

## 6. The reviews

Every review ran as independent agents that could only read the repository and experiment on
copies; a second agent then tried to refute each finding.

| Round | On | Agents | Findings | Outcome |
| --- | --- | --- | --- | --- |
| Design | the first draft of the rules | 6 reviewers, 6 skeptics | 69 (3 blockers, 36 major, 30 minor) | of the 39 blockers and majors, 30 confirmed and 9 partly; all taken into the second design |
| Final, round 1 | the finished change | 5 of 7 reviewers; no skeptic | 66 (11 major, 55 minor) | the usage limit cut the other 2 reviewers and the 7 skeptics; the author checked each finding and applied them |
| Final, round 2 | the corrected change, at `6458767` | 4 reviewers, 4 skeptics | pending | running when this file was written: the two lenses the limit cut (the contract tests, what the user asked for) and two reviewers that verify the fixes of round 1 |

## 7. What is not verified

- What a model does with the new instructions: neither eval ran (section 5), and no feature has
  been built with 0.9.0 yet. The saving is an estimate from replaying plans 001 and 002.
- The second round of the final review (section 6) had not finished when this file was written.
- GitHub CI on Linux and macOS: nothing was pushed.
