# Final verification: Publicar en GitHub mientras se construye una feature (003)

Steps 1–6 of `requirements.md` → Final verification, run on 2026-11-01 on Windows 11 (Git Bash,
Python 3.13 from the Microsoft Store, `claude` 2.1.310) on `feat/003-live-github-publishing` at
`8bb71f3`, with every task and both slice summaries committed. Step 4 is the delivery itself and runs
only after the user's yes; step 5 belongs to the next feature built with `Publish: live`, as
`requirements.md` says. The scripts that built test repositories ran outside this repository, in the
session's scratch folder; their paths are shown as `<test repo>`, and `plugins/konundrm-eng` is this
repository's plugin. Nothing here copies transcript content: the measurements print counts, times
and tokens only.

## Step 1: the check and the plugin validation

`npm run check`, on the whole project (the hook tests' interpreter path elided):

```
> check
> python scripts/check.py

--- Format: uvx --from ruff==0.17.0 ruff format --check .
81 files already formatted
--- Lint: uvx --from ruff==0.17.0 ruff check .
All checks passed!
--- Types (Python 3.10): uvx --from mypy==2.4.0 mypy
Success: no issues found in 32 source files
--- Types (Python 3.13): uvx --from mypy==2.4.0 mypy --python-version 3.13
Success: no issues found in 32 source files
--- Hook tests: <python> -m unittest discover -s plugins/konundrm-eng/hooks/tests -t plugins/konundrm-eng/hooks
Ran 493 tests in 149.372s

OK (skipped=1)
All checks passed.
```

The skipped test is `test_run_slices.py`'s session killed by a signal, which only POSIX can report;
CI runs the hook tests on ubuntu-latest, windows-latest and macos-latest.

`claude plugin validate ./plugins/konundrm-eng`:

```
✘ Found 1 problem the plugin directory refuses a submission for:
  ❯ LICENSE: License missing (LICENSE_MISSING). …
⚠ Found 1 plugin directory warning:
  ❯ .claude-plugin/plugin.json icon: No icon (ICON_MISSING). …
These plugin directory checks do not change the result below. …
✔ Validation passed
```

Exit 0. The two findings are listing checks for a submission to the plugin directory and do not
change the result. Neither comes from this feature: the plugin has never had a LICENSE file, a
`license` field or an icon, and the feature changed only the version and the repository in
`plugin.json`.

## Step 2: `message`, `git commit` and `record` in a test repository

`notes_e2e.py` builds a fresh repository with a base commit and a two-slice plan, and commits tasks
the way develop-feature does in 0.8.0: `task_ledger.py message`, then
`git add -A && git commit -F <file> --trailer "Co-Authored-By: …"`, then `task_ledger.py record`. It
also makes `record` refuse twice, and commits a third task the 0.7.0 way (its lines in the message)
in the same feature. Output, verbatim except the paths:

Test repository: a fresh `git init`, a base commit, then a plan with two slices (S1: T1, T2; S2: T3), every box unchecked.

### 1. T1: `message`, then `git commit`, then `record`

```
$ sh <plugin>/hooks/run.sh task_ledger.py message specs/001-demo/tasks.md T1 --subject "feat(demo): build the first part" --rounds "spec 2 · code 1 · escalations 0"
<test repo>/.git/KONUNDRM_TASK_MSG
[exit 0]
```

The message file `message` wrote (what the commit will say):

```
feat(demo): build the first part
```

The pending note it left beside it (`<git dir>/KONUNDRM_TASK_NOTE`):

```
Task: T1 · Covers: R1.1
Rounds: spec 2 · code 1 · escalations 0
```

`git add -A && git commit -F <that file> --trailer "Co-Authored-By: …"` → commit `18ce8c4 feat(demo): build the first part`

```
$ sh <plugin>/hooks/run.sh task_ledger.py record
recorded: 18ce8c4 Task: T1 · Covers: R1.1
[exit 0]
```

The commit's whole message (`git log -1 --format=%B`):

```
feat(demo): build the first part

Co-Authored-By: Example Assistant <assistant@example.com>
```

Its note (`git notes --ref=refs/notes/konundrm show HEAD`):

```
Task: T1 · Covers: R1.1
Rounds: spec 2 · code 1 · escalations 0
```

Pending files after `record`: note missing, message missing

### 2. `status` counts T1 by its note and names T2

```
$ sh <plugin>/hooks/run.sh task_ledger.py status specs/001-demo/tasks.md
feature: 001-demo
plan: specs/001-demo/tasks.md
base: 0846cd0c7f90a3ca8256c832e6d040f336b7bb37
committed: T1
next: T2 construye la segunda parte
tree: clean
check: not recorded
[exit 0]
```

### 3. `record` with nothing pending: exit 1, nothing changes

```
$ sh <plugin>/hooks/run.sh task_ledger.py record
[stderr] task_ledger.py: no pending note: <test repo>/.git/KONUNDRM_TASK_NOTE or <test repo>/.git/KONUNDRM_TASK_MSG is missing
[exit 1]
```

HEAD unchanged: True; notes ref unchanged: True

### 4. T2's message is pending, but another commit lands first: `record` refuses it, then attaches it to T2's commit

```
$ sh <plugin>/hooks/run.sh task_ledger.py message specs/001-demo/tasks.md T2 --subject "feat(demo): build the second part" --rounds "spec 1 · code 3 · escalations 1"
<test repo>/.git/KONUNDRM_TASK_MSG
[exit 0]
```

```
$ sh <plugin>/hooks/run.sh task_ledger.py record
[stderr] task_ledger.py: HEAD a092134 was not committed from <test repo>/.git/KONUNDRM_TASK_MSG
[exit 1]
```

HEAD `a092134 chore: an unrelated commit` has a note: False; pending note, pending message and notes ref unchanged: True

`git add -A && git commit -F <that file> --trailer "Co-Authored-By: …"` → commit `2355bad feat(demo): build the second part`

```
$ sh <plugin>/hooks/run.sh task_ledger.py record
recorded: 2355bad Task: T2 · Covers: R1.2, R2.1
[exit 0]
```

Its note:

```
Task: T2 · Covers: R1.2, R2.1
Rounds: spec 1 · code 3 · escalations 1
```

### 5. `status` names T3; `close-slice S1` checks the boxes with the rounds from the notes

```
$ sh <plugin>/hooks/run.sh task_ledger.py status specs/001-demo/tasks.md
feature: 001-demo
plan: specs/001-demo/tasks.md
base: 0846cd0c7f90a3ca8256c832e6d040f336b7bb37
committed: T1, T2
next: T3 construye la tercera parte
tree: clean
check: not recorded
[exit 0]
```

```
$ sh <plugin>/hooks/run.sh task_ledger.py close-slice specs/001-demo/tasks.md S1
not committed: none
[exit 0]
```

```diff
diff --git a/specs/001-demo/tasks.md b/specs/001-demo/tasks.md
index c033771..e24ee9d 100644
--- a/specs/001-demo/tasks.md
+++ b/specs/001-demo/tasks.md
@@ -8,11 +8,13 @@
 
 ## Slice S1: la primera mitad
 
-- [ ] **T1** construye la primera parte · `behavior` · Risk: low · Covers: R1.1
+- [x] **T1** construye la primera parte · `behavior` · Risk: low · Covers: R1.1
   - Verify: `python -c "print(1)"`
+  - Rounds: spec 2 · code 1 · escalations 0
 
-- [ ] **T2** construye la segunda parte · `behavior` · Risk: low · Covers: R1.2, R2.1
+- [x] **T2** construye la segunda parte · `behavior` · Risk: low · Covers: R1.2, R2.1
   - Verify: `python -c "print(2)"`
+  - Rounds: spec 1 · code 3 · escalations 1
 
 ## Slice S2: la segunda mitad
```

### 6. T3 committed the 0.7.0 way (its lines in the message) in the same feature

```
$ sh <plugin>/hooks/run.sh task_ledger.py status specs/001-demo/tasks.md
feature: 001-demo
plan: specs/001-demo/tasks.md
base: 0846cd0c7f90a3ca8256c832e6d040f336b7bb37
committed: T1, T2, T3
next: none
tree: clean
check: not recorded
[exit 0]
```

```
$ sh <plugin>/hooks/run.sh task_ledger.py close-slice specs/001-demo/tasks.md S2
not committed: none
[exit 0]
```

```diff
diff --git a/specs/001-demo/tasks.md b/specs/001-demo/tasks.md
index e24ee9d..7420a19 100644
--- a/specs/001-demo/tasks.md
+++ b/specs/001-demo/tasks.md
@@ -18,5 +18,6 @@
 
 ## Slice S2: la segunda mitad
 
-- [ ] **T3** construye la tercera parte · `behavior` · Risk: low · Covers: R2.2
+- [x] **T3** construye la tercera parte · `behavior` · Risk: low · Covers: R2.2
   - Verify: `python -c "print(3)"`
+  - Rounds: spec 1 · code 1 · escalations 0
```

Test repository log, each commit's whole message (`git log --format='%h %s%n%b'`):

```
ff71cef feat(demo): build the third part
Task: T3 · Covers: R2.2
Rounds: spec 1 · code 1 · escalations 0
a42f5b7 docs(demo): summarize the first half
Co-Authored-By: Example Assistant <assistant@example.com>
2355bad feat(demo): build the second part
Co-Authored-By: Example Assistant <assistant@example.com>
a092134 chore: an unrelated commit
18ce8c4 feat(demo): build the first part
Co-Authored-By: Example Assistant <assistant@example.com>
ae82ec8 docs(demo): add spec and plan for demo
0846cd0 chore: start
```

The same commits with their notes (`git log --notes=refs/notes/konundrm --format='%h %s%n%N'`):

```
ff71cef feat(demo): build the third part
a42f5b7 docs(demo): summarize the first half
2355bad feat(demo): build the second part
Task: T2 · Covers: R1.2, R2.1
Rounds: spec 1 · code 3 · escalations 1
a092134 chore: an unrelated commit
18ce8c4 feat(demo): build the first part
Task: T1 · Covers: R1.1
Rounds: spec 2 · code 1 · escalations 0
ae82ec8 docs(demo): add spec and plan for demo
0846cd0 chore: start
```

Each task commit's message holds only its subject and the co-author trailer; its note holds the
`Task:` (with `Covers:`) and `Rounds:` lines (R6.1, R6.2). `status` counts T1 and T2 by their notes
and `close-slice` writes their rounds from the notes; T3, with its lines in the message, counts the
same way in the same feature (R6.5). `record` exits with 1 and changes nothing when nothing is
pending or when HEAD was not committed from the pending message (R6.4).

## Step 3: features 001 and 002, 0.7.0 against 0.8.0

`compare_070.py` extracts the plugin as of `c8229a2` (0.7.0, the end of feature 002) and `8bb71f3`
(0.8.0) with `git archive`, clones this repository with its `refs/notes/konundrm`, and runs both
versions at two points of the history: `c8229a2`, when it held only features 001 and 002, and
`8bb71f3`, with this feature's commits and notes. At each point it runs `task_ledger.py status` on
both plans, `task_ledger.py close-slice` on each of their 23 slices (10 in 001, 13 in 002; the plan
is restored after each run) and `metrics_report.py --days 60`, and compares the two versions' stdout,
stderr, exit code and, for `close-slice`, the plan it leaves:

| At | `status` (2 plans) | `close-slice` (23 slices) | Impact report |
| --- | --- | --- | --- |
| `c8229a2` (001 and 002 only) | same, exit 0 | same: exit 0, `not committed: none` | same |
| `8bb71f3` (with this feature) | same, exit 0 | same: exit 0, `not committed: none` | one number differs |

No `close-slice` run changed either plan: both features' boxes and Rounds lines already match their
commits. The one difference, at `8bb71f3`, is the impact report's task commit count:

```diff
--- 0.7.0
+++ 0.8.0
 | Commits | feat | fix | refactor | test | other types | reverts | task commits |
 | --- | --- | --- | --- | --- | --- | --- | --- |
-| 172 | 94 | 15 | 0 | 14 | 48 | 1 | 147 |
+| 172 | 94 | 15 | 0 | 14 | 48 | 1 | 154 |
```

The seven more are this feature's T4–T10, whose `Task:` line lives only in their note, which 0.7.0
does not read; T1–T3 carry it in the message and both versions count them. Every other line of the
report is the same. Neither run could reach GitHub from the clone, so the pull request section,
whose default budget moved from 400 to 500 lines (R7.4), is covered by
`test_metrics_report.py::test_reads_flow_notes_and_defaults_to_a_500_line_budget`.

## Step 4: the delivery (with the user's yes)

The user approved two stacked pull requests:
[#3](https://github.com/MatiasBravoC/konundrm-claude/pull/3), `feat/003-live-github-publishing-s1`
into `main`, and [#4](https://github.com/MatiasBravoC/konundrm-claude/pull/4),
`feat/003-live-github-publishing` into `feat/003-live-github-publishing-s1`. This repository has no
pull request template, so each got the four fixed sections. Checked with
`gh pr view <number> --json title,body,baseRefName,isDraft,labels` right after opening:

| Pull request | Title | First line of the description | Sections | Flow data |
| --- | --- | --- | --- | --- |
| #3 | `feat(hooks): keep workflow bookkeeping out of commit messages (1/2)`, 67 characters | `Merge order: 1 of 2. Merge this one first.` | What and why · Where to look first · How it was verified · Not in this pull request | none |
| #4 | `feat(skills): publish features live with stacked pull requests (2/2)`, 68 characters | `Merge order: 2 of 2. Merge #3 first.` | the same four, in the same order | none |

"None" means a scan of each title and description, outside code spans and link targets, found no
requirement, task, slice, partition or bug-criterion ID, no word "slice", no `Task:`, `Covers:`,
`Rounds:` or `Escaped-gate:` line, no review rounds and no role name. Both descriptions end with the
session's attribution line; neither pull request is a draft or has a label, since no task was high
risk. Their CI is in [GitHub CI](#github-ci) below.

## Step 5: live publishing (the next feature)

Out of this run, as `requirements.md` says: this feature was built locally (`Publish: local`; a
non-goal was to publish it live). In the next feature built with `Publish: live`, look for each
slice's branch on GitHub when the slice starts, each task's commit as soon as the task ends, the
slice summary followed by the slice's pull request, and the final commit pushed to the last slice's
branch with every pull request's URL listed in merge order.

## Step 6: measuring this build

Section 5 of [002's diagnosis](../../002-efficient-feature-flow/evidence/diagnosis.md) lists what
the next feature had to confirm. This feature is that next feature: pauses pre-approved, two slices,
one session per slice, built with the 0.7.0 flow and, from T4's commit on, with its own
`message` → `git commit` → `record`. From the repository root (so a check run is `npm run check`),
`sh plugins/konundrm-eng/hooks/run.sh session_costs.py <folder>` over a copy of each slice session's
transcripts (the session file and its `subagents/` folder) took 0.6 s and 0.5 s.

The S1 session, which also wrote the spec and the plan:

```
role                           dispatches  turns  input  cache_write  cache_read  output  weighted  share  active_min_median  active_min_total  check_runs  check_min_total  test_runs  parallel_dispatch_msgs
orchestrator                   1           183    456    1158999      77261828    327197  10811373  70.0%  133.3              133.3             10          26.0             14         10
konundrm-eng:implementer       8           110    220    368470       5109012     71846   1330939   8.6%   4.8                40.9              10          26.8             22         0
konundrm-eng:code-reviewer     10          67     134    402810       2452426     49193   994854    6.4%   0.8                9.1               0           0.0              0          0
konundrm-eng:spec-reviewer     10          39     78     325879       939802      19405   598432    3.9%   0.3                3.5               0           0.0              0          0
konundrm-eng:process-reviewer  1           2      4      24944        24084       4473    55957     0.4%   0.7                0.7               0           0.0              0          0
konundrm-eng:test-writer       9           104    208    470980       5652477     101887  1663616   10.8%  2.1                18.9              0           0.0              22         0

busiest orchestrator session
turns  context_first  context_median  context_p90  context_max
183    81436          458419          596005       630675

skipped lines: 0
```

The S2 session, a new session started when S1's pause ended:

```
role                           dispatches  turns  input  cache_write  cache_read  output  weighted  share  active_min_median  active_min_total  check_runs  check_min_total  test_runs  parallel_dispatch_msgs
orchestrator                   1           103    214    325396       24403298    147344  3584009   46.1%  74.6               74.6              3           7.9              6          6
konundrm-eng:test-writer       8           102    204    496949       4901301     118935  1706195   21.9%  1.5                18.6              0           0.0              15         0
konundrm-eng:code-reviewer     6           48     96     302118       1832458     38353   752754    9.7%   1.1                6.6               0           0.0              0          0
konundrm-eng:implementer       6           93     186    354893       4867505     60505   1233078   15.9%  4.4                28.4              6           15.6             13         0
konundrm-eng:process-reviewer  1           3      8      28231        49088       5687    68641     0.9%   0.7                0.7               0           0.0              0          0
konundrm-eng:spec-reviewer     6           22     46     232553       493967      18034   430304    5.5%   0.5                2.7               0           0.0              0          0

busiest orchestrator session
turns  context_first  context_median  context_p90  context_max
103    79915          235694          351164       374075

skipped lines: 0
```

### 1. The second slice runs in a new session, with a context near a slice's size: confirmed

S2's orchestrator reread a median of 235,694 tokens per turn over 103 turns (first 79,915, 90th
percentile 351,164, maximum 374,075). The S1 session, which also held the spec interview and two
plans over 183 turns, reread a median of 458,419 (maximum 630,675). For reference, 002's slice
sessions had medians of 200k–334k and the 0.6.0 run's single session 382k. The orchestrator's share
of the weighted tokens fell from 70.0% in S1 to 46.1% in S2.

### 2. Each task's commit carries its rounds and the summary commit checks the boxes: confirmed

From T4 on, a task's rounds travel in its commit's note: T4–T10 each have `Task:` and `Rounds:` there
(`git log --notes=refs/notes/konundrm`) and neither in the message. T1–T3, built before `message`
changed, carry them in the message, as `tasks.md` planned. The summary commits `1e06b21` (S1) and
`8bb71f3` (S2) check every box of their slice and write each task's Rounds line from its commit,
through `close-slice`.

### 3. One full check per task, run as given, with a commit that takes seconds: the commit and the gate confirmed; one check per task only without a fix round

Every full check in both sessions ran as given (`npm run check` alone, never piped or redirected),
so the recorder kept each passing run. Full checks per task in S2:

| Task | Implementer | Orchestrator at the gate | Task commit | Full checks |
| --- | --- | --- | --- | --- |
| T7 | 1, red: lint findings in the new test, which only the test-writer may edit | 1: the test changed after that check | 2.6 s | 2 |
| T8 | 2: first dispatch and fix round | 1: the invariant test was added after the fix round's check | 2.3 s | 3 |
| T9 | 2: first dispatch and fix round | 0: `status` said `check: green for this tree` | 2.7 s | 2 |
| T10 | 1 | 0: `status` said `check: green for this tree` | 3.4 s | 1 |
| **S2** | **6** | **2** | **2.3–3.4 s** | **8, 2.0 per task** |

S2 also ran the baseline check and one inside its summary commit's gate (152.8 s), since the summary
and `close-slice` changed the tree after T10's check. In S1, under the same rules, six tasks took 17
full checks (2.8 per task): 10 by implementers (T3 and T4 ran two, the first one red; T5 ran three
over three dispatches) and 7 by the orchestrator at the gates (T3's twice, the first one red), where
it ran the check without asking `status` first except at T1's gate; its task commits took 1.7–3.5 s. In both sessions only two commits took a
check's time (152.5 s and 152.8 s), and neither was a task's: the spec-and-plan commit and S2's
summary commit, where the gate ran the check because only documents had changed since the last
passing check (S1's summary commit took 1.6 s because the orchestrator ran the check just before).

So the task's `git commit` now takes seconds and `status` lets the gate reuse the implementer's
check, as the 0.7.0 meant (the 0.6.0 run averaged 4.0 full checks per task and ran the check inside
46 of its `git commit` calls). One check per task held where a task had no fix round and nothing
changed after the implementer's check (T10); every fix round adds its implementer's check, and a
test-writer round after it makes the gate run one more.

### 4. The spec and code reviews of each task leave in one message: confirmed

S2 had 6 review batches (T7 1, T8 2, T9 2, T10 1) and 6 orchestrator messages that dispatched two or
more subagents at once; S1 had 10 batches and 10 such messages.

## Constraints

| Constraint (`requirements.md`) | Measured | Result |
| --- | --- | --- |
| The changed commands use only Python's standard library 3.10+ and run on Windows, macOS and Linux | `task_commits.py`, `task_ledger.py`, `metrics_report.py` and `working_tree.py` import only the standard library and the plugin's own modules, and mypy passes here for 3.10 and 3.13 (step 1). On GitHub, `metrics_report.py` failed on Python 3.10 on an older line until T12 fixed it; after S3, the CI run 41386172101 passes these scripts' tests on all three systems with Python 3.10 and 3.13, and its remaining failures are in code this feature did not change (see GitHub CI below) | pass, after S3 |
| `status` answers in under 2 s with a 100-task plan, now reading the flow data from notes | `status_timing_notes.py`: a plan of 100 tasks in 10 slices and 260 commits, none with a flow line in its message and each with a note (200 before the base naming T1–T100, then 60 task commits T1–T60); 10 runs: median 0.41 s, max 0.42 s | pass |
| Live: one push per task and no `gh` call per task; `gh` at plan approval, at each slice's end and on resume | develop-feature pushes after each task's commit and runs `gh` "here and on resume, never per task", pinned by `contract/test_flows.py::test_live_publishing_pushes_each_slice_branch_and_commit` and `::test_slices_end_in_stacked_pull_requests_in_merge_order` | pass (rules; measured live in the next feature) |
| Nothing on the remote is rewritten; subagents and partition sessions push nothing | develop-feature never forces a push nor pulls or fetches to make one go through, and only the main session pushes; `agents/implementer.md` and `agents/test-writer.md` never push nor open pull requests; same contract test | pass (rules) |
| Nothing else changes on GitHub: no settings, no labels | opening-pull-requests adds `risk:high` only when the label exists and never creates it; same contract tests | pass (rules) |
| The flow data stays in the local repository | no skill or agent pushes `refs/notes/konundrm` (`git grep` finds no push of notes); live publishing pushes only the slice branches | pass |
| Commits keep their `Co-Authored-By` line and pull requests their attribution line | each of this feature's commits carries one `Co-Authored-By` trailer (19 before the closing commit, which adds its own), and step 2's task commits keep theirs; opening-pull-requests keeps "the attribution lines configured for the session", and both pull requests end with it (step 4) | pass |

## GitHub CI

The check above runs here, on Windows with Python 3.13. The repository's CI
(`.github/workflows/ci.yml`) also runs the hook tests on ubuntu-latest, windows-latest and
macos-latest with Python 3.10 and 3.13, and its last run on `main`, on `c8229a2` (the commit this
feature started from, run 41355334852), failed in five of its eight jobs; macOS and Windows with
Python 3.13, and the plugin validation, passed:

| Job | Failure | Origin |
| --- | --- | --- |
| lint, mypy on Linux | `session_costs.py:502: error: Statement is unreachable` | the code after a Windows-only early return, which mypy on Linux treats as unreachable (feature 002) |
| test, Python 3.10, all three systems | 4 errors in `test_metrics_report.py`: `ValueError: Invalid isoformat string: '…Z'` | `metrics_report.py:110` reads commit dates with `datetime.fromisoformat`, which accepts a trailing `Z` only from Python 3.11 (the plugin's first commit) |
| test, Python 3.10, all three systems | `test_find_duplicates.py`, `test_usage_errors_exit_2_with_a_message` with `--all --base HEAD`: exit 0 instead of 2 | `find_duplicates.py` accepts that pair of options on Python 3.10 |
| test, ubuntu-latest, Python 3.10 and 3.13 | `test_session_costs.py`, `test_reads_transcripts_past_the_windows_path_limit`: "238 not greater than 260" | the test's long folder comes out shorter than 260 characters on that runner (feature 002) |

None of these lines was written by this feature, but `metrics_report.py` is one of the scripts it
changed.

The CI of the two pull requests as first opened (run 41381551936 for #3, run 41381573656 for #4)
failed those jobs and Windows with Python 3.13 too, with failures of this feature's own beside the
older ones:

| Jobs | New failure | Cause |
| --- | --- | --- |
| test, ubuntu-latest and windows-latest, Python 3.10 and 3.13 | `test_task_ledger.py`: `test_message_builds_the_task_commit_message_from_the_plan`, `test_record_attaches_the_pending_note_to_the_commit_made_from_it` and `test_record_changes_nothing_whenever_it_refuses_for_any_pending_state`, each with `git notes add failed for HEAD …; does it already have a note?` | `record`'s `git notes add` needs a Git identity; those runners have none and this machine has a global one, while the tests gave Git an identity only on their own commands (reproduced here with `HOME` at an empty folder and `GIT_CONFIG_NOSYSTEM=1`) |
| test, Python 3.10, all three systems | `test_metrics_report.py::test_reads_flow_notes_and_defaults_to_a_500_line_budget` | the older `Z` date line, which this new test also reaches |

The merge was held, the user chose to fix first, and slice S3 did: T11 gives each test repository
its own identity and has `record` report Git's own error, and T12 reads `Z` dates through one
helper. The CI run on the fixes (run 41386172101, on `dfc0ee2`, pull request #4) failed only on
older problems:

| Job | Result |
| --- | --- |
| lint | failed: `session_costs.py:502` unreachable (older) |
| test, ubuntu-latest, Python 3.10 | failed: the `find_duplicates` option check and the long-path test (both older) |
| test, ubuntu-latest, Python 3.13 | failed: the long-path test (older) |
| test, macos-latest, Python 3.10 | failed: the `find_duplicates` option check (older) |
| test, windows-latest, Python 3.10 | failed: the `find_duplicates` option check (older) |
| test, macos-latest and windows-latest, Python 3.13 | passed |
| validate | passed |

So this feature adds no CI failure, and T12 also removed the four older `test_metrics_report.py`
errors on Python 3.10. Three older problems are left on `main`, outside this feature: the mypy
warning on Linux, the `find_duplicates` option check on Python 3.10 and the long-path test on
ubuntu.

## Scripts

The scripts that produced this evidence ran outside the repository, in the session's scratch
folder: `notes_e2e.py` (step 2), `compare_070.py` (step 3), `status_timing_notes.py` (from 002's
`status_timing.py`), and for step 6 `check_timeline.py`, `status_lines.py`, `commit_durations.py` and
`commit_gate_scan.py` (the last two from 002). They print counts, times, roles and the `next:` and
`check:` lines of `status`, never transcript content.
