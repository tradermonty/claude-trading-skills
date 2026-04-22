---
layout: default
title: "Paper Replay Harness"
grand_parent: English
parent: Skill Guides
nav_order: 11
lang_peer: /ja/skills/paper-replay-harness/
permalink: /en/skills/paper-replay-harness/
---

# Paper Replay Harness
{: .no_toc }

Deterministic historical replay of the trade loop. Feeds pre-generated candidate files + local OHLCV bars through the same ranking, sizing, and bracket-fill logic used in production, without touching Alpaca. Use to validate a screener change, sanity-check a sizing tweak, or produce a walk-forward P&L curve before enabling execute mode. Invoke with "replay last 30 days", "backtest this screener", "dry-run the loop against april bars".
{: .fs-6 .fw-300 }

<span class="badge badge-free">No API</span>

[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/paper-replay-harness){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

# Paper Replay Harness

---

## 2. When to Use

- Before turning on `execute` mode — replay the last 30 sessions and confirm
  the loop is well-behaved (no runaway entries, reasonable drawdown, stops
  actually fire).
- After changing screener weights, composite math, or sector caps.
- To produce a walk-forward P&L curve for strategy-review reports.

---

## 3. Prerequisites

- **API Key:** None required
- **Python 3.9+** recommended

---

## 4. Quick Start

```bash
python3 skills/paper-replay-harness/scripts/replay.py \
  --bars-dir data/bars/ \
  --candidates-dir data/historical_candidates/ \
  --from 2026-03-01 --to 2026-03-31 \
  --output-dir reports/replay/
```

---

## 5. Workflow

```bash
python3 skills/paper-replay-harness/scripts/replay.py \
  --bars-dir data/bars/ \
  --candidates-dir data/historical_candidates/ \
  --from 2026-03-01 --to 2026-03-31 \
  --output-dir reports/replay/
```

### Steps

1. Enumerate trading days in [from, to] (exclude weekends).
2. For each day:
   - Load any `candidates_<date>.json` file.
   - Filter out tickers we already hold.
   - Rank + dedupe via `rank_signals.rank_and_dedupe` (with a fixed
     GOLDILOCKS regime, risk_on=70 default, or the values passed via
     `--regime` / `--risk-on`).
   - Size each candidate (`run_loop.size_position`).
   - Sector cap / position count enforcement (per config).
   - Submit to the `SimBroker`: bracket orders queued for next day's fill.
3. After the loop iteration, advance bars:
   - Fill outstanding BUY orders at next day's open.
   - For each open position, check whether the bar touched stop or target;
     close at stop/target price if so.
   - Mark-to-market the remaining positions at close.
4. Record per-day portfolio snapshot (equity, positions, realized day P&L).
5. At the end: aggregate, write `replay_<from>_<to>.md` and `.json`.

---

## 6. Resources

**Scripts:**

- `skills/paper-replay-harness/scripts/replay.py`
