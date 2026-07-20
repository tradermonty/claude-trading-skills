---
layout: default
title: "Contrarian Setup Gate"
grand_parent: English
parent: Skill Guides
nav_order: 13
lang_peer: /ja/skills/contrarian-setup-gate/
permalink: /en/skills/contrarian-setup-gate/
generated: true
---

# Contrarian Setup Gate
{: .no_toc }

Synthesize the three Jason Shapiro contrarian-pipeline verdicts (COT crowding, news-reaction failure, weekly price-action confirmation) into one actionable setup_status via a fail-closed precedence state machine. Pure, offline synthesis -- no network, no API keys, no computation beyond validation and precedence.
{: .fs-6 .fw-300 }

<span class="badge badge-free">No API</span>

[Download Skill Package (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/contrarian-setup-gate.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/contrarian-setup-gate){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

Synthesize the outputs of Jason Shapiro's 3-step contrarian process into one actionable state. cot-contrarian-detector (step 1) flags crowded positioning, news-reaction-failure-analyzer (step 2) tests whether the market failed to react to news favorable to the crowd, and technical-analyst's contrarian-confirmation mode (step 3) confirms weekly price-action evidence of a reversal. This gate reads those three report JSONs and applies an explicit, exhaustively-tested precedence rule set to produce one `setup_status`, with a fail-closed reason attached to every input that could not be confirmed.

The gate does no fetching, no API calls, and no computation beyond validating and combining the three inputs it is given. It is the pipeline's synthesis center, not a data source.

---

## 2. When to Use

- After running cot-contrarian-detector (always required -- this is the pipeline's entry point)
- Mid-pipeline, with only the detector report, to see the CROWDED state and what steps remain
- After running news-reaction-failure-analyzer, to see whether the setup advances to WATCHING_PRICE or is REJECTED
- After running technical-analyst's contrarian-confirmation mode, to see whether the setup reaches READY_FOR_PLAN
- Before handing a symbol's direction and stop level to a position-sizing skill

---

## 3. Prerequisites

- Python 3.9+
- No API keys -- this skill is fully offline
- A cot-contrarian-detector JSON report for the symbol under evaluation (required)
- Optionally, a news-reaction-failure-analyzer JSON report for the same symbol (step 2)
- Optionally, a technical-analyst contrarian-confirmation JSON report for the same symbol (step 3)

---

## 4. Quick Start

```bash
python3 skills/contrarian-setup-gate/scripts/run_contrarian_setup_gate.py \
  --symbol B6 \
  --detector-json reports/cot_crowding_2026-07-12.json \
  --news-json reports/nrf_B6_2026-07-12.json \
  --price-action-json reports/ta_confirmation_B6_2026-07-12.json \
  --as-of 2026-07-15 \
  --output-dir reports/
```

---

## 5. Workflow

### Step 1: Run the Gate

```bash
python3 skills/contrarian-setup-gate/scripts/run_contrarian_setup_gate.py \
  --symbol B6 \
  --detector-json reports/cot_crowding_2026-07-12.json \
  --news-json reports/nrf_B6_2026-07-12.json \
  --price-action-json reports/ta_confirmation_B6_2026-07-12.json \
  --as-of 2026-07-15 \
  --output-dir reports/
```

`--symbol` and `--detector-json` are required; `--news-json` and `--price-action-json` are optional -- omit either to see the state at that pipeline stage. `--as-of` is required (no implicit "today"): staleness is always evaluated against an explicit reference date so reruns are deterministic.

Exit behavior is intentionally asymmetric: a missing or malformed `--as-of` (or any other CLI usage error) is an operator config mistake, so the CLI exits `2` with usage text and writes no report. A problem with one of the three untrusted report files -- unreadable, malformed, stale, inconsistent -- is always handled fail-closed instead: the CLI exits `0` and writes a report naming the reason, exactly like every other skill in this pipeline.

### Step 2: Read the Setup Status

| Status | Meaning | Next Step |
|---|---|---|
| `READY_FOR_PLAN` | All three steps confirmed; direction, entry_trigger, and invalidation_level are populated | Hand `direction` and `invalidation_level` to a position-sizing skill |
| `WATCHING_PRICE` | Crowding + news confirmed; price action still pending | Run technical-analyst's contrarian-confirmation mode |
| `CROWDED` | Crowding confirmed; news and/or price still pending | Run news-reaction-failure-analyzer |
| `REJECTED` | Crowding is NOT_CONFIRMED (classification NEUTRAL), or news/price came back NOT_CONFIRMED | Stop -- do not run further steps for this symbol/direction |
| `INSUFFICIENT_EVIDENCE` | A required input is missing, unreadable, stale, inconsistent, or could not itself reach a verdict | Stop -- fix or regenerate the named input before rerunning |

`missing_confirmations` lists every step still blocking, with its `state` and `reason`. `warnings` never change the status -- they flag audit-worthy conditions such as a MEDIUM-confidence confirming signal or a near-stale input.

### Step 3: Act on READY_FOR_PLAN Only

At `READY_FOR_PLAN`, `direction` (SHORT/LONG, the fade side of the crowd), `entry_trigger` (a factual echo of the confirming weekly signal), and `invalidation_level` (the stop reference from the price-action report) are populated. `gate_confidence` is the weaker of the news and price-action confidences (HIGH/MEDIUM/LOW -- `LOW` is a token both upstream skills document as reserved but never actually emit; the gate accepts it and ranks it weakest rather than rejecting it as unknown). Position sizing is the next pipeline stage (not yet built as of this skill's release -- see the roadmap in the repository's workflow docs); this gate never places or recommends an order.

---

## 6. Resources

**References:**

- `skills/contrarian-setup-gate/references/gate-decision-table.md`

**Scripts:**

- `skills/contrarian-setup-gate/scripts/gate_logic.py`
- `skills/contrarian-setup-gate/scripts/run_contrarian_setup_gate.py`
