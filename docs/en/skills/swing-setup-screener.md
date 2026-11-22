---
layout: default
title: "Swing Setup Screener"
grand_parent: English
parent: Skill Guides
nav_order: 69
lang_peer: /ja/skills/swing-setup-screener/
permalink: /en/skills/swing-setup-screener/
generated: true
---

# Swing Setup Screener
{: .no_toc }

Seven-in-one EOD screener over keyless Yahoo daily bars — swing-trend longs (SMA50/200 alignment + Pullback/Breakout/Extended trigger), swing-trend shorts (Bear Flag/Breakdown/Oversold), 52-week-high strength leaders with SMA20 pullback plans, high-ATR% volatility candidates, and three next-session RVOL watchlists (in-play movers, unusual volume with accumulation/distribution quadrant, weakness on selling volume). A-D grades from documented factor weights, plan levels, hard timing contract (last completed session only; RVOL screens are explicitly next-session watchlists, never live Day-1 signals). No paid API required.
{: .fs-6 .fw-300 }

<span class="badge badge-free">No API</span>

[Download Skill Package (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/swing-setup-screener.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/swing-setup-screener){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

Screen US equities after the close across seven complementary setups from a
single script with shared universe, indicators, grading, and reports. Four
swing screens (swing-long, swing-short, leaders, volatility) are fully
faithful on daily bars; three RVOL screens (in-play, unusual-volume, weak)
are honest EOD reconstructions of live intraday scanners and are labeled
**next-session watchlists** in every report. Detection-only: never sends
orders.

Sibling of trend-reclaim-screener (same keyless Yahoo stack and
invalidation → factor-score → A-D grade architecture); reclaim setups stay
in that skill.

---

## 2. When to Use

Invoke this skill when the user wants to:

- Build an after-hours watchlist of trend-following longs or shorts
  (`--screen swing-long` / `swing-short`).
- Find 52-week-high leaders and know whether to buy now or wait
  (`--screen leaders`, Pullback Plan labels).
- Rank tradeable high-ATR% names (`--screen volatility`).
- See which stocks had abnormal participation today for tomorrow's focus
  list (`--screen in-play`, `unusual-volume`, `weak`).
- Run the whole board: `--screen all` (seven report pairs).

Do NOT invoke for:

- SMA50 reclaim-after-reset setups — use trend-reclaim-screener.
- Live intraday HOD breaks, runners, or gap plays — daily bars cannot do
  this; use a real-time scanner and interpret with technical-analyst.
- Stockbee-method momentum bursts — use stockbee-momentum-burst-screener.

---

## 3. Prerequisites

- Keyless Yahoo EquityQuery universe screen + ~1y daily OHLCV batch download; offline JSON fixture supported for testing
- Python 3.9+ recommended

---

## 4. Quick Start

```bash
python3 skills/swing-setup-screener/scripts/screen_swing_setups.py \
     --screen swing-long --output-dir reports/
```

---

## 5. Workflow

1. Run after the close (no API key needed):
   ```bash
   python3 skills/swing-setup-screener/scripts/screen_swing_setups.py \
     --screen swing-long --output-dir reports/
   ```
   Universe options, in precedence order: `--tickers NVDA,AMD`,
   `--universe-csv file.csv` (Ticker/Symbol column), default keyless Yahoo
   screen of every US name ≥ $2B / price > $5 / avg vol > 500K (~1.8k
   tickers, paginated 250 per request; `--universe-size 250` for a quick
   most-liquid scan), or `--fixture path.json` offline. Partial coverage is
   disclosed in the report header, never silent.
2. Read `reports/swing_setups_<screen>_<date>.md`. Check the market-regime
   line first (SPY vs SMA50/SMA200) — longs fight a `risk_off` tape, shorts
   fight `risk_on`.
3. Interpret grades and labels with the matching reference file
   (`references/`). A = actionable per plan, B = standard sizing on a clean
   entry, C = watchlist only, D excluded. Grade caps (Extended, Oversold,
   Wait Deeper, chaotic tape, chop quadrant, faded close, gap bought back)
   are printed as warnings.
4. Walk the report's Pre-Entry Checklist; resolve every UNKNOWN warning
   manually (catalyst, earnings without a date, short interest).
5. Hand off before entry: position-sizer (size from `risk_pct`),
   technical-analyst (confirm the chart), short-squeeze-radar (mandatory for
   swing-short/weak candidates), trader-memory-core (register theses).

---

## 6. Resources

**References:**

- `skills/swing-setup-screener/references/rvol_screens.md`
- `skills/swing-setup-screener/references/strength_leaders.md`
- `skills/swing-setup-screener/references/swing_trend_long.md`
- `skills/swing-setup-screener/references/swing_trend_short.md`
- `skills/swing-setup-screener/references/volatility_high.md`

**Scripts:**

- `skills/swing-setup-screener/scripts/backtest_swing_setups.py`
- `skills/swing-setup-screener/scripts/evaluate_forward_log.py`
- `skills/swing-setup-screener/scripts/screen_swing_setups.py`
