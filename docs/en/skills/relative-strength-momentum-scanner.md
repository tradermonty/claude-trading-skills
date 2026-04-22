---
layout: default
title: "Relative Strength Momentum Scanner"
grand_parent: English
parent: Skill Guides
nav_order: 11
lang_peer: /ja/skills/relative-strength-momentum-scanner/
permalink: /en/skills/relative-strength-momentum-scanner/
---

# Relative Strength Momentum Scanner
{: .no_toc }

IBD-style relative strength screener. Ranks tickers by composite 3/6/9/12-month returns vs a benchmark, filters for trend quality (above MA50 and MA200), and emits a pullback-to-MA20 entry plan. Produces the same Candidate schema as vcp-screener, canslim-screener, and pead-screener so it plugs straight into the trade-loop orchestrator. Invoke with "run momentum screen", "RS rating scan", "find leading stocks", "pullback momentum candidates".
{: .fs-6 .fw-300 }

<span class="badge badge-free">No API</span>

[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/relative-strength-momentum-scanner){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

# Relative Strength Momentum Scanner

---

## 2. When to Use

- Daily leaderboard generation (runs premarket as part of the screener fan-out)
- Ad-hoc "what's leading the market right now" query
- Sector-rotation scan (group leaders by GICS sector)

---

## 3. Prerequisites

- **API Key:** None required
- **Python 3.9+** recommended

---

## 4. Quick Start

1. Load the ticker universe (CLI flag or default).
2. Load local OHLCV CSV bars from `--bars-dir` (same format as
   paper-replay-harness: `<TICKER>.csv` with columns
   `date,open,high,low,close,volume`).
3. Skip tickers with fewer than 252 trading days of history.
4. Compute returns, moving averages, 52-week high, trend filters.
5. Percentile-rank the composite RS across surviving tickers.
6. Apply pullback trigger to assign `entry_ready` vs `watchlist` status.
7. Compute entry/stop/target and package into candidate dicts.
8. Sort descending by `rs_score`.

---

## 5. Workflow

1. Load the ticker universe (CLI flag or default).
2. Load local OHLCV CSV bars from `--bars-dir` (same format as
   paper-replay-harness: `<TICKER>.csv` with columns
   `date,open,high,low,close,volume`).
3. Skip tickers with fewer than 252 trading days of history.
4. Compute returns, moving averages, 52-week high, trend filters.
5. Percentile-rank the composite RS across surviving tickers.
6. Apply pullback trigger to assign `entry_ready` vs `watchlist` status.
7. Compute entry/stop/target and package into candidate dicts.
8. Sort descending by `rs_score`.
9. Write JSON + markdown to `--output-dir` (default `reports/`).

---

## 6. Resources

**References:**

- `skills/relative-strength-momentum-scanner/references/sp500.txt`

**Scripts:**

- `skills/relative-strength-momentum-scanner/scripts/scan_rsm.py`
