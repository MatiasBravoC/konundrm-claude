---
name: measure-impact
description: Reports whether the konundrm-eng workflow is improving delivery in this repository. Combines Git history (commit mix, fixes per feature, reverts, fixes that land soon after a task touched the same files, and the gate each fix-bug commit says the bug escaped), the review rounds and escalations recorded in specs/*/tasks.md, what the plugin's gates blocked, asked for or restored, and merged pull requests from GitHub (size against the budget, time to merge), then interprets the trends and proposes one or two concrete adjustments. Given the folders of the project's Claude Code transcripts, it adds what each role cost in tokens and time. Invoke with /konundrm-eng:measure-impact [days] [transcript folders...].
disable-model-invocation: true
argument-hint: "[days, default 30] [transcript folders...]"
---

# Measuring Impact

Developers reliably overestimate how much AI speeds them up. Measure instead: are fewer defects
escaping, is rework falling, and do the gates catch real problems or only add friction?

## Workflow

1. Run the delivery report for the window in the first argument of `$ARGUMENTS` (30 days when
   empty):
   `sh "${CLAUDE_PLUGIN_ROOT}/hooks/run.sh" metrics_report.py --days <days>`
2. When `$ARGUMENTS` also names transcript folders, run the costs report on all of them as one
   run: `sh "${CLAUDE_PLUGIN_ROOT}/hooks/run.sh" session_costs.py <folder>...`. Each folder is a
   project's `~/.claude/projects/<project>/`, where `<project>` is the project's path with every
   character other than a letter or digit turned into `-`. Without transcript folders, skip this
   step.
3. Show each report as it is, the costs report after the delivery report.
4. Interpret them in at most six bullets, citing the numbers:
   - **Escaped defects and fixes per feature:** falling means problems are caught before they
     ship. Open the listed possible escapes; for each real one, name the gate that should have
     caught it (spec criterion, property, review, end-to-end check). Fixes made with
     `/konundrm-eng:fix-bug` already name it in their note's `Escaped-gate:` line
     (`refs/notes/konundrm`): the gate that appears most is the one to sharpen first.
   - **Pull requests:** many over the budget mean the plans need smaller slices; a growing time
     to merge means reviewers are the bottleneck, so slices should get smaller, not fewer.
   - **Review rounds per task:** more than two on average points at vague specs or plans; the
     cheapest fix is a sharper approval, not more review.
   - **Escalations:** frequent `BLOCKED` on the same kind of task means the plan template or the
     standards miss a rule.
   - **Gate events:** many stop blocks, role violations or flagged dependencies show where Claude
     struggles; improve that skill, standard or eval.
   - **Costs per role and context (only when the costs report ran):** the role with the largest
     share of weighted tokens is where saving pays most; a busiest orchestrator session whose
     context keeps growing toward its maximum should hand more work to subagents. Nonzero
     `skipped lines` means every count is short by those lines.
5. Propose at most two adjustments, each tied to a number in the report (a standard to sharpen,
   a property or eval to add, a risk level to raise). Do not change anything without a yes.

## Limits to state when relevant

- "Possible escaped defects" is a proxy: a `fix` commit touching files a task changed in the 30
  days before. Confirm before counting it.
- Gate events are logged on this machine only, and review rounds only exist for features built
  with `develop-feature`.
- The pull request section needs the `gh` CLI signed in to the repository's GitHub; without it
  the report says so. `KONUNDRM_PR_BUDGET` changes the budget it compares against (default 500).
- Token cost comes only from the transcript folders given, so without them the report has none.
  It is per role over those transcripts, not per feature, and transcripts exist only on the
  machine that ran the sessions. Claude Code also exports cost through OpenTelemetry
  (`claude_code.cost.usage`, tagged by plugin, skill and agent) when the organization enables
  telemetry.
- Compare trends over time for the same repository, never people or teams.
