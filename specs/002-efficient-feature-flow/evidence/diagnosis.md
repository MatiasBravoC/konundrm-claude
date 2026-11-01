# Diagnosis: the 0.6.0 flow against the 0.7.0 flow

Step 5 of the final verification in `requirements.md`. It puts side by side what was measured (the
hooks, and the same two tasks built by both versions), what each version prescribes per task, and an
estimate of the 0.6.0 run under the new rules, and says what the next feature's measurement has to
confirm. The measurements of the 0.6.0 run and of the hooks are in [final.md](final.md), steps 3
and 4. Measured on 2026-11-01, Windows 11, 6 cores.

## In short

- **Same task, both versions (measured, 8 headless runs):** the 0.7.0 reached the task's commit
  25% sooner on a script task (T12: 16.5 → 12.4 min) and in the same time on an agent-text task
  (T18: 12.5 → 12.4 min), with about the same tokens (0.5–0.6 M weighted per task), and it sent the
  spec and code reviews together where the 0.6.0 sent them one after the other.
- **It did not yet run one full check per task:** 4.0–4.5 full checks per task against 4.5–5.5.
  The agents ran the check with its output trimmed (`npm run check 2>&1 | tail`, or redirected to a
  file), which the recorder ignores on purpose because a pipe can hide a failing exit code, so
  `task_ledger.py status` said `check: not recorded` and the commit gate ran the check again in 3
  of the 4 runs. The one run that ran it as given committed in 1 s instead of about 100 s. T44
  (slice S13, added in Phase 4) has the implementer and the orchestrator run the check as given;
  its effect is estimated below, not measured (the user chose not to measure again).
- **Hooks (measured):** the check recorder takes 70 ms per command that is not the check, against
  181 ms with the 0.6.0 (0.39×).
- **The 0.6.0 run under the new rules (estimated):** about 180 fewer full checks (283 → about 135,
  −3.6 h) once checks run as given, about 1.7 h less waiting on reviews, 7 min less of hooks: about
  −17% to −21% of its 32.4 h of active time; tokens about −10% to −20%, mostly from rereading a
  slice's context instead of a whole feature's.

## 1. The hooks (measured)

The check recorder's launcher (`run.sh`) no longer starts Python for a command that is not the
check: 70–73 ms against 180–182 ms per command (mean of 20 runs, [final.md](final.md), step 3), and
it still records a passing check, also a custom one. The check itself costs 365 ms instead of 284 ms,
once per check run, because the passing tree is now written beside the repository. Over the 5,016
shell commands of the 0.6.0 run, the fast path covers 74.4% (T42's measurement), about 7 minutes
of hook time in that run. The commit gate and the dependency guard still read every command whole
(T4) and still fail closed.

## 2. The same tasks with both versions (measured)

### How it ran

- **Tasks:** two the feature had already built, of different kinds. T12 (`task_ledger.py message`
  refuses an unknown or committed task: about 110 changed lines, code and tests) and T18 (the
  finding verifier runs only what its finding needs: about 30 lines, agent text and a contract
  test).
- **Each run:** a local clone, outside this repository and without a remote, at the commit before
  the task's, with `tasks.md` trimmed to that one task (renumbered T90 and T91, because the history
  already holds `Task: T12` and `Task: T18` commits of feature 001, and the 0.6.0 resume searches
  the whole history), pauses and decisions pre-approved, `Sessions: single`. Then
  `claude -p "/konundrm-eng:develop-feature specs/002-efficient-feature-flow"` with only one plugin
  version loaded (`--plugin-dir`, the marketplace copy turned off), model `claude-opus-5-5`, effort
  `high`, permission mode `auto`, no MCP servers. Each run was stopped 3 s after its task's commit,
  so the slice pause and Phase 4 of the clone never ran.
- **Runs:** 2 tasks × 2 versions × 2 repetitions. The first ran alone; the rest, at the user's
  request, in pairs that ran the same task with both versions at once (both under the same load),
  and the last alone, to match the first. An earlier start inside a deeper folder stopped at its
  baseline check: a cache path there passed Windows' 260-character limit, the check went red, and
  the 0.7.0 session stopped with `BLOCKED:` as it should; it is not counted.
- **Measured with:** `session_costs.py` over each run's transcript folder (tokens, turns,
  dispatches and full checks per role, messages that dispatched two or more subagents), the
  commit's time minus the start, and how long each `git commit` call took (60 s or more: the commit
  gate ran the check inside it). The scripts are listed in [final.md](final.md).
- **Cost:** the eight runs took 76 minutes of wall clock and about 4.1 M weighted tokens in all, a
  quarter of the 15–20 M the plan estimated, because each run stopped at its task's commit.

### Results

| Run | How it ran | Minutes to the commit | Weighted tokens, M (orchestrator) | Orchestrator turns | Full checks: commands + inside the commit | Reviews sent together |
| --- | --- | --- | --- | --- | --- | --- |
| T18, 0.7.0, 1 | alone | 13.8 | 0.54 (0.22) | 20 | 4 + 1 | yes |
| T18, 0.7.0, 2 | pair | 11.0 | 0.41 (0.16) | 14 | 3 + 1 | yes |
| T18, 0.6.0, 1 | pair | 14.0 | 0.52 (0.23) | 23 | 4 + 1 | no |
| T18, 0.6.0, 2 | alone | 10.9 | 0.43 (0.17) | 18 | 3 + 1 | no |
| T12, 0.7.0, 1 | pair | 12.5 | 0.51 (0.16) | 15 | 3 + 1 | yes |
| T12, 0.7.0, 2 | pair | 12.3 | 0.55 (0.22) | 19 | 4 + 0 | yes |
| T12, 0.6.0, 1 | pair | 14.2 | 0.53 (0.18) | 17 | 3 + 1 | no |
| T12, 0.6.0, 2 | pair | 18.7 | 0.63 (0.23) | 16 | 6 + 1 | no |

| Task | Version | Minutes to the commit | Weighted tokens, M | Full checks | Minutes of check | Orchestrator turns |
| --- | --- | --- | --- | --- | --- | --- |
| T12 | 0.6.0 | 16.5 (14.2–18.7) | 0.58 | 5.5 (4–7) | 9.4 | 16.5 |
| T12 | 0.7.0 | 12.4 (12.3–12.5) | 0.53 | 4.0 (4–4) | 7.0 | 17.0 |
| T18 | 0.6.0 | 12.5 (10.9–14.0) | 0.48 | 4.5 (4–5) | 8.4 | 20.5 |
| T18 | 0.7.0 | 12.4 (11.0–13.8) | 0.48 | 4.5 (4–5) | 8.6 | 17.0 |

Every run committed its task with the same files changed by both versions (the 0.6.0 also checked
the plan's box and wrote its Rounds line in the commit; the 0.7.0 wrote the rounds in the commit's
trailer). Every task had one spec and one code review; no run needed a review fix round.

### What explains the numbers

- **Reviews:** each 0.7.0 run sent the spec and code reviews in one message (R3.1); the 0.6.0 sent
  them one after the other. On a task this size that saves about a minute, the shorter review.
- **The implementer's check:** the 0.7.0 implementer ran the full check once, at the end, in all four
  runs (R2.4); the 0.6.0 implementer ran it one to four times (four in the slowest run).
- **The check run again:** a full check here is the baseline, the implementer's, the
  orchestrator's at the gate when `status` does not show it green, and the commit gate's when the
  tree was not recorded green. In the 0.7.0 runs the gate step and the commit should reuse the
  implementer's passing check (R2.5), but 29 of the 30 check runs written as commands across the
  eight runs were trimmed, redirected or chained (`npm run check 2>&1 | tail -25`,
  `npm run check > /tmp/check.log 2>&1; echo "exit $?"`), which the recorder never records (a known
  limitation, listed in the [0.7.0] changelog). So `status` said `check: not recorded`, the orchestrator ran the check again,
  trimmed again, and the commit gate ran it once more: about 100 s each time. The only run whose
  orchestrator ran `npm run check` as given got `check: green for this tree` and a commit of 1 s.
- **Tokens:** a single task is too small for the per-slice sessions to show; both versions'
  orchestrators reread about 55k tokens per turn here, against the 382k median of the 0.6.0's main
  session over a whole feature.
- **Variance:** two runs of the same task and version differ by up to 4.5 minutes (T12 with the
  0.6.0: 14.2 and 18.7); one extra check loop weighs as much as the version.

### With T44 (estimated)

T44 tells the implementer and the orchestrator to run the check command as given, alone in its
call. In these runs that removes the orchestrator's check at the gate and the commit gate's rerun:
2 to 2.5 full checks per task, about 3.5 to 4.5 minutes of the 12.4, so about 8 to 9 minutes per
task, 35% to 50% less than the 0.6.0. In a session that builds a whole slice, the baseline check
also runs once per session instead of once per task.

## 3. What each version prescribes per task

| | 0.6.0 | 0.7.0 |
| --- | --- | --- |
| Orchestrator session | one for the whole feature (the 0.6.0 run: 1,087 turns, median context 382k) | one per slice, then a new one (this feature's slice sessions: median context 200k–334k) |
| Full check | the implementer at will, the orchestrator at the gate, the commit gate again after the plan's box changed; the test-writer and reviewers when they chose (4.0 per task in the 0.6.0 run, 4.2 with the suites) | the implementer once at the end of each dispatch; the orchestrator only when `status` does not show it green for the tree; the commit reuses it (about 1.3 per task when the check runs as given) |
| Test-writer and reviewers | could run the check or the suite | only their own tests, or the one test a finding needs; the reviewers get the orchestrator's verification output |
| Reviews | one after the other | spec and code (and security on high-risk tasks) in one message; one fix round for all findings; re-reviews get their findings and what changed |
| Bookkeeping | Git queries and plan edits by hand (about 300 Git calls in the 0.6.0 main session) | `task_ledger.py status` (1 call), `message` plus the commit (1 call), `close-slice` (1 call per slice) |
| The plan in a task's commit | box and Rounds line written, which changed the tree after the check | untouched; the rounds travel in the commit's trailer and `close-slice` writes them at the pause |
| Hooks per shell command | the recorder started Python every time | the recorder starts Python only for a command that may be the check |

## 4. The 0.6.0 run under the new rules (estimate)

From the 0.6.0 run's measurement ([final.md](final.md), step 4) and the rules above, with checks run
as given (T44):

- **Full checks:** 283 by the orchestrators, the implementers and the commit gate, plus 33 by the
  test-writers and reviewers, become about one per implementer dispatch (101), one baseline per
  slice session and one per slice summary commit (about 16 each): about 135, about 180 fewer, about
  3.6 h less at 72 s each (5.65 h measured).
- **Reviews:** about 105 review batches, each saving its shorter review (median 1.0 min for spec,
  1.4 for code): about 1.7 h.
- **Hooks:** about 7 minutes.
- **Total:** about 5.4 h to 6.7 h of its 32.4 h of active time, −17% to −21% (the S5 estimate, from
  the same frequencies, gave about −21%).
- **Tokens:** the orchestrators held 57% of the weighted tokens, and 78% of theirs were cache reads,
  which grow with the context reread each turn. Slice sessions rereading a median of 200k–334k
  instead of 382k, and one `status` call instead of several Git queries, put the run at about −10%
  to −20% of its 206 M weighted tokens. The A/B cannot show this part: it needs a feature with
  several slices.

This feature itself was built with the new flow as it landed, slice by slice (for example S12: 2
tasks, about 3.4 M weighted tokens, the orchestrator 57%, median context 200k; S9: 9.5 M for its two
tasks, one of them high-risk). Its tasks differ from the 0.6.0's, so those numbers are not a
comparison.

## 5. What the next feature has to confirm

Step 6 of the final verification, with `/konundrm-eng:measure-impact` and the run's transcript
folders (or `session_costs.py` over them):

- With pauses pre-approved and two slices, the second slice runs in a new session, and its
  orchestrator's context per turn stays near a slice's size.
- Each task's commit carries its rounds; the summary commit checks the boxes.
- One full check per task: the implementer's, run as given; `status` prints `check: green for this
  tree` at the gate, and the task's `git commit` call takes seconds, not a check's minute and a
  half.
- The spec and code reviews of each task leave in one message.
