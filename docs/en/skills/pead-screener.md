---
layout: default
title: "PEAD Screener"
grand_parent: English
parent: Skill Guides
nav_order: 45
lang_peer: /ja/skills/pead-screener/
permalink: /en/skills/pead-screener/
---

# PEAD Screener
{: .no_toc }

Screen post-earnings gap-up stocks for PEAD (Post-Earnings Announcement Drift) patterns. Analyzes weekly candle formation to detect red candle pullbacks and breakout signals. Supports two input modes - FMP earnings calendar (Mode A) or earnings-trade-analyzer JSON output (Mode B). Use when user asks about PEAD screening, post-earnings drift, earnings gap follow-through, red candle breakout patterns, or weekly earnings momentum setups.
{: .fs-6 .fw-300 }

<span class="badge badge-api">FMP Required</span>

[Download Skill Package (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/pead-screener.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/pead-screener){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

# PEAD Screener - Post-Earnings Announcement Drift

---

## 2. When to Use

- User asks for PEAD screening or post-earnings drift analysis
- User wants to find earnings gap-up stocks with follow-through potential
- User requests red candle breakout patterns after earnings
- User asks for weekly earnings momentum setups
- User provides earnings-trade-analyzer JSON output for further screening

---

## 3. Prerequisites

- FMP API key (set `FMP_API_KEY` environment variable or pass `--api-key`)
  ```bash
  export FMP_API_KEY=your_api_key_here
  ```
- Free tier (250 calls/day) is sufficient for default screening
- For Mode B: earnings-trade-analyzer JSON output file with schema_version "1.0"

---

## 4. Quick Start

```bash
# Mode A: FMP earnings calendar (standalone)
python3 skills/pead-screener/scripts/screen_pead.py \
  --lookback-days 14 --min-gap 3.0 --max-api-calls 200 \
  --output-dir reports/

# Mode B: Pipeline from earnings-trade-analyzer output
python3 skills/pead-screener/scripts/screen_pead.py \
  --candidates-json reports/earnings_trade_*.json \
  --min-grade B --output-dir reports/
```

---

## 5. Workflow

### Step 1: Prepare and Execute Screening

Run the PEAD screener script in one of two modes:

**Mode A (FMP earnings calendar):**
```bash
# Default: last 14 days of earnings, 5-week monitoring window
python3 skills/pead-screener/scripts/screen_pead.py --output-dir reports/

# Custom parameters
python3 skills/pead-screener/scripts/screen_pead.py \
  --lookback-days 21 \
  --watch-weeks 6 \
  --min-gap 5.0 \
  --min-market-cap 1000000000 \
  --output-dir reports/
```

**Mode B (earnings-trade-analyzer JSON input):**
```bash
# From earnings-trade-analyzer output
python3 skills/pead-screener/scripts/screen_pead.py \
  --candidates-json reports/earnings_trade_analyzer_YYYY-MM-DD_HHMMSS.json \
  --min-grade B \
  --output-dir reports/
```

### Step 2: Review Results

1. Read the generated JSON and Markdown reports
2. Load `references/pead_strategy.md` for PEAD theory and pattern context
3. Load `references/entry_exit_rules.md` for trade management rules

### Step 3: Present Analysis

For each candidate, present:
- Stage classification (MONITORING, SIGNAL_READY, BREAKOUT, EXPIRED)
- Weekly candle pattern details (red candle location, breakout status)
- Composite score and rating
- Trade setup: entry, stop-loss, target, risk/reward ratio
- Liquidity metrics (ADV20, average volume)

### Step 4: Provide Actionable Guidance

Based on stages and ratings:
- **BREAKOUT + Strong Setup (85+):** High-conviction PEAD trade, full position size
- **BREAKOUT + Good Setup (70-84):** Solid PEAD setup, standard position size
- **SIGNAL_READY:** Red candle formed, set alert for breakout above red candle high
- **MONITORING:** Post-earnings, no red candle yet, add to watchlist
- **EXPIRED:** Beyond monitoring window, remove from watchlist

---

## 6. Resources

**References:**

- `skills/pead-screener/references/entry_exit_rules.md`
- `skills/pead-screener/references/pead_strategy.md`

**Scripts:**

- `skills/pead-screener/scripts/fmp_client.py`
- `skills/pead-screener/scripts/report_generator.py`
- `skills/pead-screener/scripts/scorer.py`
- `skills/pead-screener/scripts/screen_pead.py`
