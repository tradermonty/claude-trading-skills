---
layout: default
title: "Trade Loop Orchestrator"
grand_parent: English
parent: Skill Guides
nav_order: 11
lang_peer: /ja/skills/trade-loop-orchestrator/
permalink: /en/skills/trade-loop-orchestrator/
---

# Trade Loop Orchestrator
{: .no_toc }

Main automated trading loop. Every 5 minutes during US market hours, this skill (1) checks the kill-switch, (2) reads macro regime + exposure scale, (3) runs all configured screeners, (4) ranks/dedupes signals, (5) sizes positions via position-sizer, (6) submits bracket orders via alpaca-executor with full safety gates, and (7) writes a per-iteration audit log. Invoke when the user asks "run the loop", "execute the trader", "start the bot", "scan and place trades".
{: .fs-6 .fw-300 }

<span class="badge badge-free">No API</span>

[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/trade-loop-orchestrator){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

# Trade Loop Orchestrator

---

## 2. When to Use

- Scheduled by launchd `com.trade-analysis.trade-loop.plist` every 5 min,
  09:35-15:55 ET, weekdays.
- On demand by the user: "run the loop now", "what would the trader do right
  now?".
- Smoke test: `--mode plan` outputs would-be orders without invoking executor.

---

## 3. Prerequisites

- **API Key:** None required
- **Python 3.9+** recommended

---

## 4. Quick Start

```bash
# Plan-only (smoke test, no orders):
python3 skills/trade-loop-orchestrator/scripts/run_loop.py \
  --mode plan --output state/loop/

# Live loop (still gated by TRADE_LOOP_DRY_RUN):
python3 skills/trade-loop-orchestrator/scripts/run_loop.py \
  --mode execute --output state/loop/
```

---

## 5. Workflow

```bash
# Plan-only (smoke test, no orders):
python3 skills/trade-loop-orchestrator/scripts/run_loop.py \
  --mode plan --output state/loop/

# Live loop (still gated by TRADE_LOOP_DRY_RUN):
python3 skills/trade-loop-orchestrator/scripts/run_loop.py \
  --mode execute --output state/loop/
```

### Per-iteration sequence

1. Acquire file-lock at `state/loop/.lock` (prevents overlapping runs).
2. Pre-loop kill-switch check. If not OK, write `iter_<utc>_blocked.json`, exit 2.
3. Read macro state. If stale (>4h old) or missing, fall back to neutral
   (exposure_scale=0.5) and log a warning.
4. Load all screener outputs for today. Each adapter returns a uniform
   `Candidate` shape (see `references/candidate_schema.md`).
5. Rank + dedupe. Cap to `entries_allowed_this_loop`.
6. For each top candidate:
   - Resolve sector from `sector_map.yaml`
   - Skip if sector cap would be breached after this entry
   - Run position-sizer to compute `quantity` and `risk_amount`
   - Skip if quantity == 0 or risk > per-trade cap
   - Build payload and call `alpaca-executor/execute_trade.py`
7. Write iteration audit JSON with: macro snapshot, kill-switch status, all
   considered candidates, all decisions, all order results.

### Gates - in order, all must pass

| Gate | Source | Failure action |
|------|--------|----------------|
| Kill-switch OK | kill-switch | abort loop |
| Inside trading window | trading_params.yaml `global.trading_hours` | abort loop |
| Not a blackout date | trading_params.yaml `global.blackout_dates` | abort loop |
| risk_on_score >= macro_min_risk_on | macro-indicator-dashboard | skip new entries |
| current_positions < cap * exposure_scale | computed | skip new entries |
| Sector cap not breached by this entry | sector_map | skip this candidate |
| Per-trade risk within profile cap | position-sizer | skip this candidate |
| `validate_order` accepts | alpaca-executor | order refused, logged |

---

## 6. Resources

**References:**

- `skills/trade-loop-orchestrator/references/candidate_schema.md`

**Scripts:**

- `skills/trade-loop-orchestrator/scripts/rank_signals.py`
- `skills/trade-loop-orchestrator/scripts/run_loop.py`
- `skills/trade-loop-orchestrator/scripts/screener_adapters.py`
