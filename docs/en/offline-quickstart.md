---
layout: default
title: Offline Quick Start
parent: English
nav_order: 2
lang_peer: /ja/offline-quickstart/
permalink: /en/offline-quickstart/
---

# Your first offline report

Start with the [output previews]({{ '/en/getting-started/' | relative_url }}#preview-the-outputs),
then make your own **fictional** market-regime report here. No Claude account,
broker account or market-data API key is needed for these repository commands.
They reuse the bundled fictional component fixtures and native scoring functions,
not live downloads. You will pause at a human decision gate, read the proposal,
and record a practice decision in a new directory under `reports/`.

Allow about **15 minutes after setup**, including reading and choosing a practice
posture. The automated test times the command path against a 900-second ceiling;
that is not a measurement of human reading, downloads, installation or a fresh OS.

## 1. Prepare the repository environment

Clone or download this repository and enter its root. Install Python matching
`config/python-support.json` (root environment: `>=3.11.5,<3.14`) and `uv`, then:

```bash
uv sync --locked --extra dev
```

This initial dependency installation needs network access or a populated local
package cache. **The following command path is offline after installation.**
Activate the environment so `python` means this checkout's interpreter:

```bash
# macOS / Linux
source .venv/bin/activate
```

On Windows PowerShell, use `.venv\Scripts\Activate.ps1`. If activation is restricted,
substitute `.venv\Scripts\python.exe` for `python` in the commands below. On
macOS/Linux the equivalent explicit interpreter is `.venv/bin/python`.
Run every command from the repository root; nothing installs a skill into your
personal agent configuration.

<!-- quickstart: doctor -->
```bash
python scripts/doctor.py
```

Expected: `Offline environment doctor` and per-item checks with fix hints. Missing
FMP, FINVIZ or Alpaca credentials are **expected warnings**, with exit code 0;
do not create accounts or add keys for this demo. Doctor does not test provider
connectivity, credential validity or whether every skillset is runnable. Resolve
Python/package warnings using the setup command before continuing.

## 2. Generate and pause

Choose a **new** run directory. The following example refuses an existing one,
even if empty. If you already used the name, choose another name and use it
consistently in every later command. Do not erase an earlier run to restart.

<!-- quickstart: start -->
```bash
python scripts/run_market_regime_daily.py --run-dir reports/quickstart-demo
```

In a terminal it displays the fictional proposal and asks for a posture. For this
walkthrough, **press Enter with no answer** to pause and inspect the result first.
With redirected input/CI it pauses automatically. `AWAITING_DECISION` and exit
code **3** mean waiting for your choice, not a completed or failed run. Run each
command separately; a shell configured to stop on nonzero exits may stop at this
intentional pause.

<!-- quickstart: paused-status -->
```bash
python scripts/run_market_regime_daily.py --run-dir reports/quickstart-demo --status
```

This also returns 3 while paused. Open the JSON files in your editor:

| Output under `reports/quickstart-demo/` | What to inspect |
| --- | --- |
| `01_market_breadth_report.json` | Breadth result and fixture provenance |
| `02_uptrend_report.json` | Uptrend participation result |
| `04_exposure_proposal.json` | Proposed exposure posture for human review |
| `manifest.json` | Run identifier, step statuses, inputs and artifact hashes |

The evaluation time is fixed at **2026-01-15T13:08:00+00:00**. These are fictional
learning inputs, not today's market. Optional top-risk analysis is `SKIPPED` in
this basic path; that is not a successful risk assessment. The missing optional
input is reflected in the proposal. No `journal.json` exists before your choice.

## 3. Record an explicit practice choice

Read the proposal first. For this **fictional exercise**, choose `restrict` to
practice a restrictive posture. The example does not authorize a live trade or
recommend a current exposure level. If you chose a posture at the initial prompt
instead of pausing, the run is already complete: skip the resume command and
inspect status. Completed runs refuse a second decision.

<!-- quickstart: resume -->
```bash
python scripts/run_market_regime_daily.py --run-dir reports/quickstart-demo --resume --decision restrict
```

<!-- quickstart: status -->
```bash
python scripts/run_market_regime_daily.py --run-dir reports/quickstart-demo --status
```

Expected: `COMPLETED`, exit code 0, and a new `journal.json` recording your practice
choice, `destination: trader-memory-core`, and `delivery: handoff_only`. This is a
**local handoff**, not delivery to your real journal or a change to `state/`.
Status is read-only. The existing reports remain attached to this run.

If a command reports `BLOCKED`, keep its directory intact and consult the
[detailed runner guide](https://github.com/tradermonty/claude-trading-skills/blob/main/docs/dev/guided-market-regime-daily.md).
Do not edit manifests to bypass a gate. Do not treat fixture outputs as an
investment signal or attach personal account data to a public support request.

## 4. Choose your next path with three questions

1. **What do I need to do?** A morning risk check, a portfolio review, or a review
   of a completed trade? Name the goal rather than a ticker tip.
2. **Which inputs can I safely use?** Start with fictional inputs. Distinguish
   public market data from private account files; do not paste credentials or
   personal holdings into a query. A no-paid-API route is not a promise that every
   subsequent skill runs offline.
3. **How much time do I have?** Choose 15, 30, 60 or 90 minutes. Time is a routing
   hint, not a guarantee that an unfamiliar task will finish within it.

Here is a tested 15-minute, beginner morning-check example. It recommends a path;
it does not run that path or send the query to a model:

<!-- quickstart: navigator -->
```bash
python skills/trading-skills-navigator/scripts/recommend.py --query "I have 15 minutes before the market open to check market breadth, uptrend participation and exposure posture" --no-api --time-budget 15m --experience beginner --format json
```

Expected: `goal_match.workflow.id` is `market-regime-daily` and `no_api_path` is
`true`. Change the query to your own non-sensitive goal; different goals can
produce a different workflow or an honest gap. See the
[Navigator guide]({{ '/en/skills/trading-skills-navigator/' | relative_url }}) for
using the selected skills. This demo runs directly from the repository; a
one-command skillset installer and doctor's live readiness checks remain future
work under #301.

## What is tested

`scripts/tests/test_offline_quickstart.py` extracts the marked commands from both
language pages and executes them in the locked test environment, with no provider
keys and isolated user homes. It checks the pause, explicit decision, real report
files, fixed fixture evaluation, local handoff, unchanged source fixtures, and
read-only final status. Python socket/DNS guards record and reject attempted
connections; tests prove the guard loaded and detect swallowed attempts. This is
not an OS network sandbox. Existing CI's root-script test row runs the same test.
It verifies executable instructions, not human completion time or live-market
correctness.
