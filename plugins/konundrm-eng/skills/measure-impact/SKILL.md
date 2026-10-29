---
name: measure-impact
description: Reports whether the konundrm-eng workflow is improving delivery in this repository. Combines Git history (commit mix, fixes per feature, reverts, fixes that land soon after a task touched the same files, and the gate each fix-bug commit says the bug escaped), the review rounds and escalations recorded in specs/*/tasks.md, what the plugin's gates blocked, asked for or restored, and merged pull requests from GitHub (size against the budget, time to merge), then interprets the trends and proposes one or two concrete adjustments. Invoke with /konundrm-eng:measure-impact [days].
disable-model-invocation: true
argument-hint: "[days, default 30]"
---

# Measuring Impact

Developers reliably overestimate how much AI speeds them up. Measure instead: are fewer defects
escaping, is rework falling, and do the gates catch real problems or only add friction?

## Workflow

1. Run the report for the window in `$ARGUMENTS` (30 days when empty):
   `sh "${CLAUDE_PLUGIN_ROOT}/hooks/run.sh" metrics_report.py --days <days>`
2. Show the report as it is.
3. Interpret it in at most six bullets, citing the numbers:
   - **Escaped defects and fixes per feature:** falling means problems are caught before they
     ship. Open the listed possible escapes; for each real one, name the gate that should have
     caught it (spec criterion, property, review, end-to-end check). Fixes made with
     `/konundrm-eng:fix-bug` already name it in their `Escaped-gate:` trailer: the gate that
     appears most is the one to sharpen first.
   - **Pull requests:** many over the budget mean the plans need smaller slices; a growing time
     to merge means reviewers are the bottleneck, so slices should get smaller, not fewer.
   - **Review rounds per task:** more than two on average points at vague specs or plans; the
     cheapest fix is a sharper approval, not more review.
   - **Escalations:** frequent `BLOCKED` on the same kind of task means the plan template or the
     standards miss a rule.
   - **Gate events:** many stop blocks, role violations or flagged dependencies show where Claude
     struggles; improve that skill, standard or eval.
4. Propose at most two adjustments, each tied to a number in the report (a standard to sharpen,
   a property or eval to add, a risk level to raise). Do not change anything without a yes.

## Limits to state when relevant

- "Possible escaped defects" is a proxy: a `fix` commit touching files a task changed in the 30
  days before. Confirm before counting it.
- Gate events are logged on this machine only, and review rounds only exist for features built
  with `develop-feature`.
- The pull request section needs the `gh` CLI signed in to the repository's GitHub; without it
  the report says so. `KONUNDRM_PR_BUDGET` changes the budget it compares against (default 400).
- Token cost per feature is not in this report: Claude Code exports it through OpenTelemetry
  (`claude_code.cost.usage`, tagged by plugin, skill and agent) when the organization enables
  telemetry.
- Compare trends over time for the same repository, never people or teams.
