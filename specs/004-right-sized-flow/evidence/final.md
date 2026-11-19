# Final verification: right-sized tasks and proportional reviews

Run on 2026-11-18 on Windows 11 (Git Bash, Git 2.53, Python 3.14), on the branch
`feat/004-right-sized-flow`. Each section says what was checked, how and the result.

## 1. The check and the plugin validation

`npm run check`, run alone right before commit `71f21a5`, the last one that changes the skills:

```text
--- Format: uvx --from ruff==0.17.0 ruff format --check .
82 files already formatted
--- Lint: uvx --from ruff==0.17.0 ruff check .
All checks passed!
--- Types (Python 3.10): uvx --from mypy==2.4.0 mypy
Success: no issues found in 32 source files
--- Types (Python 3.13): uvx --from mypy==2.4.0 mypy --python-version 3.13
Success: no issues found in 32 source files
--- Hook tests: ... -m unittest discover -s ...\hooks\tests -t ...\hooks
Ran 518 tests in 300.596s
OK (skipped=1)
All checks passed.
```

Before this feature the same command ran 494 tests. It passed again, with the same 518 tests, on
the tree of each later commit of this branch: the commit gate takes no other result.
`claude plugin validate ./plugins/konundrm-eng` prints `✔ Validation passed`; its two directory
notes (no icon, no license file) predate this feature.

## 2. The contract tests fail without the feature, and without each of its rules

The contract tests were copied over an export of the 0.8.0 tree (`git archive 4dc55e3`) and run
there: 24 of 90 fail, every one of them a test this feature added or amended.

```text
FAIL: TaskWithSeveralTestsTest.test_writers_handle_a_task_that_lists_several_tests
FAIL: DevelopFeatureFlowTest.test_changes_asked_at_a_checkpoint_are_adjustments_or_new_tasks
FAIL: ReviewFlowTest.test_task_commits_only_after_the_reviews_its_final_code_needs
FAIL: RightSizedFlowEdgesTest.test_a_finished_feature_and_a_task_in_progress_take_a_change_safely
FAIL: RightSizedFlowEdgesTest.test_an_adjustment_has_a_branch_a_red_step_that_can_be_met_and_a_safe_set_aside
FAIL: RightSizedFlowEdgesTest.test_reviews_not_repeated_and_adjustments_leave_a_record_that_travels
FAIL: RightSizedFlowEdgesTest.test_the_one_cycle_build_covers_its_property_tests_and_its_second_dispatches
FAIL: RightSizedFlowTest.test_a_change_the_user_asks_for_is_classified_first
FAIL: RightSizedFlowTest.test_a_task_that_lists_several_tests_is_built_in_one_cycle
FAIL: RightSizedFlowTest.test_an_adjustment_follows_its_procedure
FAIL: RightSizedFlowTest.test_an_adjustment_has_its_prompts_its_commit_and_its_note
FAIL: RightSizedFlowTest.test_only_the_reviews_a_change_concerns_run_again
FAIL: BehaviorEvalsTest.test_each_right_sized_flow_mechanism_has_a_behavior_eval
FAIL: ReadmeTest.test_readme_describes_consolidated_tasks_and_adjustments
FAIL: VersionAndChangelogTest.test_0_9_0_changelog_names_each_mechanism
FAIL: RightSizedFlowPinsTest.test_a_requested_change_keeps_the_edges_of_its_path
FAIL: RightSizedFlowPinsTest.test_a_task_with_several_tests_keeps_the_edges_of_its_one_cycle
FAIL: RightSizedFlowPinsTest.test_planning_keeps_the_edges_of_what_it_merges
FAIL: RightSizedFlowPinsTest.test_reviews_after_a_change_keep_what_surrounds_their_table
FAIL: RightSizedFlowPinsTest.test_the_adjustment_review_gets_the_orchestrators_verification_runs
FAIL: RightSizedFlowPrincipleTest.test_measure_impact_says_task_counts_changed_meaning
FAIL: RightSizedFlowPrincipleTest.test_standards_state_what_is_merged_and_which_reviews_run_again
FAIL: WritingPlansConsolidationTest.test_writing_plans_consolidates_related_low_risk_tasks
FAIL: AdjustmentsSummaryTemplateTest.test_summaries_list_the_adjustments_and_their_reviews
Ran 90 tests
FAILED (failures=24)
```

The feature is pinned by 315 rules across those tests (155 in `test_flows.py`, 37 in
`test_skills.py`, 18 in `test_agents.py` and 105 in `test_right_sized_pins.py`).

Each rule was also checked the other way round. One rule at a time was removed or inverted in the
text of the skills, agents, prompts and templates, on copies of the tree, and the contract tests
were run after each edit:

| Set of mutations | Applies to the final text | Fails a test | Passes every test |
| --- | --- | --- | --- |
| One per rule of the feature, by the reviewer of the tests' strength | 178 of 191 | 174 | 4 |
| One per part of an acceptance criterion, by the reviewer of the tests' coverage | 212 of 231 | 207 | 5 |
| One per sentence the second review changed or added | 54 of 61 | 54 | 0 |
| One per sentence the regression review changed or added | 18 of 18 | 18 | 0 |
| Total | 462 | 453 | 9 |

The 39 mutations that no longer apply edit a sentence a later review reworded. Each has its
equivalent in a later set, except one whose sentence was removed. When the second review began,
134 of the first two sets passed every test (76 and 58). The nine that still pass were left on
purpose, because the sentence explains or repeats a rule that is pinned where it is stated:

- the verify rerun and the test already written, in the list for a change on the task in
  progress (the section and step 2 of the task loop state both);
- "often one, sometimes none" in the procedure's reviews step, and the prose that says the
  adjustment's note is written in the same command (the command itself is pinned);
- the todo item's wording for a review that was not repeated, and the reason why the note is
  where a partition's integration finds it (the append command is pinned);
- "when the step is done" in verifying by risk (the single re-review is pinned);
- the opening sentence of `## Adjustments`;
- the second statement of the next slice's branch in "Where it is recorded" (step 1 states it).

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
  and spaces; a message with `[` is not found, which the text now rules out. Without `git add -A`
  before it, a file that a marked fix round deleted came back on recovery; with it, the file
  stays deleted.
- The branch for an adjustment to a merged feature. With the feature merged on the remote and the
  local default branch never pulled, a branch cut from the local default branch held no feature
  folder. `git fetch origin <default-branch>` and
  `git switch -c feat/<NNN-slug>-<short-slug> --no-track origin/<default-branch>` give a branch
  with the feature and no upstream, and `git push -u origin …` creates it on the remote. Without
  `--no-track` the new branch tracks the default branch and a plain `git push` is refused.
- The searches. In Git Bash, `git grep -n -F` finds nothing for a text that starts with `/`
  unless `MSYS_NO_PATHCONV=1` is set, and reads a text that starts with a dash as an option
  unless it follows `-e`.
- The ledger after a rebase or in a clone: `status` prints `committed: none` and names the first
  task as next for a plan whose documents say `Done`, which is why a finished feature is
  recognised by its documents and reopens only while `status` still lists every task.
- The pull request of that new branch. With the local default branch still behind,
  `git log --oneline <base>..HEAD` listed the whole merged feature (9 commits, 624 lines) for a
  branch that holds two commits and 6 lines, with a merge commit, a squash and a rebase merge
  alike. Against `origin/<base>` the list and the measure are the branch's own. With a local
  default branch that is ahead of the remote the count the text asks for is 0 and nothing
  changes.
- The lookup of the tasks that changed a file, on a finished feature. Up to `HEAD` it printed a
  later feature's `Task:` lines with nothing to tell them apart, on a throwaway repository and on
  this one (for feature 001, `hooks/run.sh` printed two tasks of feature 002). Ended at the
  feature's final commit, which
  `git log -1 --format=%h -S'**Status:** Done' -- specs/<NNN-slug>/tasks.md` prints, it gives
  only that feature's lines, also through a merge commit and for two features built at once.
- A change on the task in progress that the code already makes. The adjustment's set-aside, run
  there, stashed the whole uncommitted task and left `status` naming it as next, which is why
  the procedure now leaves those tests in the task.
- Rethink's set-aside after a rename on the task in progress: with the two excludes the stash
  took the edited line of `design.md`; with the third one the three documents stay.

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

The second review found the same misread for a Rounds text that a field wraps onto a line of its
own, and that `close-slice` used the same expression to choose the line it rewrites. Two tests
failed first: the reader returned `[(9, 9, 9)]` where the task's own field says `(2, 1, 0)` (on
the reviewer's copy), and `close-slice` wrote the commit's rounds over the wrapped line of a
`- Change:` request (here). Both now go through one function, `rounds_field`, which takes only
a line that is the `- Rounds:` field itself. The 135 tasks of the three plans read the same
rounds as before this second change.

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
copies; a second agent then tried to refute each blocker or major finding. Their reports were
working files outside the repository and are not kept: the counts below are the author's record
of them.

| Round | On | Agents | Findings | Outcome |
| --- | --- | --- | --- | --- |
| Design | the first draft of the rules | 6 reviewers, 6 skeptics | 69 (3 blockers, 36 major, 30 minor) | of the 39 blockers and majors, 30 confirmed and 9 partly; all taken into the second design |
| Final, round 1 | the finished change | 5 of 7 reviewers; no skeptic | 66 (11 major, 55 minor) | the usage limit cut the other 2 reviewers and the 7 skeptics; the author checked each finding and applied them in `87ee951`, `e38e5ed`, `e28d1d1` and `6458767` |
| Final, round 2 | the corrected change, at `1afa828` | 7 reviewers, 5 skeptics | 58 (13 major, 45 minor) | every finding of round 1 was found applied; of the 13 majors, 9 confirmed and 4 partly, none refuted; applied in `64ece65`, `1b36602`, `a2e6017` and `6049730` |
| Regression | the fixes of round 2, at `6049730` | 3 reviewers, 5 skeptics | 15 (5 major, 10 minor), which were 10 distinct residues | the 5 majors were 3 problems, all confirmed; the 10 residues were applied in `71f21a5` |

Round 2 ran twice before it finished: a usage limit and then a network outage cut it, so it was
split into seven smaller reviews. The regression review was cut once, when the computer went to
sleep, and ran again from the start.

## 7. What is not verified

- What a model does with the new instructions: neither eval ran (section 5), and no feature has
  been built with 0.9.0 yet. The saving is an estimate. Replaying plans 001 and 002 leaves 62 of
  79 and 36 of 44 tasks; a reviewer's mechanical replay with the real commit sizes leaves 57 and
  38, about one task in five fewer. On two small features a reviewer wrote for the purpose, the
  plan went from 14 tasks and 55 dispatches to 5 and 19, and from 13 and 52 to 8 and 32.
- Nine sentences that a single edit can still remove with every test green (section 2).
- The GitHub CI run of this branch's last commit: its result is on the pull request (section 8).

## 8. GitHub CI

The branch was pushed and its pull request opened after this file was first closed. The first
run, on `e22fc0d`, ran the 518 tests on Windows, macOS and Linux with Python 3.10 and 3.13. Five
of its eight jobs failed: the same five that fail on `main` at `4dc55e3`, for the same three
reasons, none of them in this feature.

- `lint`, on Linux: mypy reported `session_costs.py:502: error: Statement is unreachable`, in a
  function that only does something on Windows. Reproduced here with `mypy --platform linux`. The
  function now keeps its Windows part inside the platform check, and mypy passes for `linux`,
  `darwin` and `win32`, for Python 3.10 and 3.13.
- The tests on Python 3.10: `test_usage_errors_exit_2_with_a_message` got exit 0 for
  `--all --base HEAD`. Before Python 3.13, argparse takes a value that is its default for "not
  given", so the two options did not conflict. `--base` has no argparse default now and the
  script fills it in afterwards.
- The tests on Linux: `test_reads_transcripts_past_the_windows_path_limit` failed its own fixture
  check (`238 not greater than 260`), because its long folder passed the limit only under a
  temporary folder whose own path is long. With a check that leaves the temporary folder out,
  the test failed here first (`221 not greater than 260`) and passes with longer folder names.

They are fixed in the commit
`fix(hooks): pass the three checks GitHub CI was failing on main`. That commit's own CI run is on
the pull request, not in this file: the Python 3.10 case cannot be run on this machine, which has
Python 3.13 and 3.14.
