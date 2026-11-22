---
layout: default
title: "Trend Reclaim Screener"
grand_parent: English
parent: Skill Guides
nav_order: 76
lang_peer: /ja/skills/trend-reclaim-screener/
permalink: /en/skills/trend-reclaim-screener/
generated: true
---

# Trend Reclaim Screener
{: .no_toc }

After-hours screener for long-side SMA50 reclaim setups — stocks that pulled back below their 50-day moving average, reset/based, and recently re-established above it. Scores reclaim quality, momentum, structure, volume participation, and trend alignment into A-D grades with top-3 picks, plan levels (next-open entry, stop below the reclaim level, T1 at pre-reset resistance), and a pre-entry checklist. Keyless Yahoo Finance data; no paid API required.
{: .fs-6 .fw-300 }

<span class="badge badge-free">No API</span>

[Download Skill Package (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/trend-reclaim-screener.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/trend-reclaim-screener){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

Screen US equities for second-chance continuation setups: stocks reclaiming
their SMA50 after a genuine reset (pullback, base, or failed move). The best
multi-week movers often don't offer their cleanest entry on the first
breakout — they reset, stabilize, then reclaim trend control. This skill
finds those reclaims the evening they confirm, grades them, and emits a
ranked watchlist with defined-risk plan levels. Detection-only: it never
sends orders.

Long-side mirror of parabolic-short-trade-planner Phase 1 — same
hard-invalidation → 5-factor weighted score → A-D grade architecture.

---

## 2. When to Use

Invoke this skill when the user wants to:

- Find stocks that recently reclaimed their SMA50 after a pullback below it.
- Build an after-hours (post-close) watchlist of trend-restoration setups
  for next-open entries.
- Grade a specific ticker's reclaim quality (`--tickers`).

Do NOT invoke for:

- First-breakout momentum screening — use vcp-screener or
  stockbee-momentum-burst-screener.
- Short-side exhaustion — use parabolic-short-trade-planner.
- Intraday signals — this scans daily bars only.

---

## 3. Prerequisites

- Keyless Yahoo EquityQuery universe screen + ~1y daily OHLCV batch download; offline JSON fixture supported for testing
- Python 3.9+ recommended

---

## 4. Quick Start

```bash
python3 skills/trend-reclaim-screener/scripts/screen_trend_reclaim.py \
     --output-dir reports/
```

---

## 5. Workflow

1. Run the screener after the close (no API key needed):
   ```bash
   python3 skills/trend-reclaim-screener/scripts/screen_trend_reclaim.py \
     --output-dir reports/
   ```
   Universe options, in precedence order:
   - `--tickers NVDA,AMD,...` — explicit list
   - `--universe-csv path.csv` — any CSV with a Ticker/Symbol column
     (e.g. a Finviz export)
   - default — keyless Yahoo screen of the ~250 most liquid US names
     ≥ $2B market cap (`--universe-size` to widen)
   - `--fixture path.json` — offline bars for testing
2. Read `reports/trend_reclaim_<date>.md`. Top Picks are the highest
   composite scores; the Watchlist lists every candidate at or above
   `--watch-min-grade` (default C) with factor breakdowns and warnings.
3. Interpret grades using `references/trend_reclaim_framework.md`:
   A = enter per plan; B = tradeable with standard sizing on a clean entry;
   C = watchlist, wait for maturation; D is excluded.
4. Walk the Pre-Entry Checklist in the report — especially the earnings
   check, which the screener does NOT perform.
5. Hand off before entry:
   - position-sizer — size from the report's stop distance (`risk_pct`).
   - technical-analyst — confirm the chart on candidates before committing.
   - trader-memory-core — register picks as theses for postmortem tracking.

---

## 6. Resources

**References:**

- `skills/trend-reclaim-screener/references/trend_reclaim_framework.md`

**Scripts:**

- `skills/trend-reclaim-screener/scripts/screen_trend_reclaim.py`
