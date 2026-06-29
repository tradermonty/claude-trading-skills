---
layout: default
title: "Stockbee Momentum Burst Screener"
grand_parent: English
parent: Skill Guides
nav_order: 51
lang_peer: /ja/skills/stockbee-momentum-burst-screener/
permalink: /en/skills/stockbee-momentum-burst-screener/
generated: true
---

# Stockbee Momentum Burst Screener
{: .no_toc }

Screen US stocks for Stockbee-style short-term Momentum Burst setups using 4% breakout, dollar breakout, range expansion, volume expansion, prior range contraction, close-location, failure filters, and risk-distance scoring. Use when the user asks for Stockbee, Pradeep Bonde, momentum burst, 4% breakout, range expansion, dollar breakout, short-term swing momentum candidates, or 3-5 day burst setup review.
{: .fs-6 .fw-300 }

<span class="badge badge-api">FMP Required</span>

[Download Skill Package (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/stockbee-momentum-burst-screener.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/stockbee-momentum-burst-screener){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

# Stockbee Momentum Burst Screener

---

## 2. When to Use

- User asks for Stockbee / Pradeep Bonde style Momentum Burst screening
- User wants 4% breakout, dollar breakout, or range expansion candidates
- User asks for short-term 3-5 day swing momentum setups
- User wants to review whether a daily breakout has A/B/C setup quality
- User provides a symbol list, universe file, or historical OHLCV JSON for screening
- User wants candidate outputs to feed into `technical-analyst`, `position-sizer`, or `trader-memory-core`

---

## 3. Prerequisites

- FMP API key for live universe and historical OHLCV screening:
  ```bash
  export FMP_API_KEY=your_api_key_here
  ```
- Optional no-API path: provide `--prices-json` containing daily OHLCV bars by symbol.
- Run only after the market-regime workflow allows new swing risk, or mark output as manual-review-only.

---

## 4. Quick Start

```bash
python3 skills/stockbee-momentum-burst-screener/scripts/screen_momentum_burst.py \
  --fmp-universe \
  --max-symbols 300 \
  --output-dir reports/
```

---

## 5. Workflow

### Step 1: Choose Input Mode

Use one of three modes:

**Mode A: FMP universe scan**
```bash
python3 skills/stockbee-momentum-burst-screener/scripts/screen_momentum_burst.py \
  --fmp-universe \
  --max-symbols 300 \
  --output-dir reports/
```

**Mode B: Explicit symbols**
```bash
python3 skills/stockbee-momentum-burst-screener/scripts/screen_momentum_burst.py \
  --symbols NVDA SMCI PLTR TSLA \
  --output-dir reports/
```

**Mode C: Offline OHLCV JSON**
```bash
python3 skills/stockbee-momentum-burst-screener/scripts/screen_momentum_burst.py \
  --prices-json data/daily_ohlcv.json \
  --output-dir reports/
```

### Step 2: Run the Screening Pass

The script detects these trigger families:

- **4% Breakout:** `close / previous_close >= 1.04`, volume above previous day, and volume above the liquidity floor
- **Dollar Breakout:** `close - open >= 0.90`, volume above the liquidity floor
- **Range Expansion:** current daily range exceeds the prior three daily ranges while the prior day was not already extended

It then scores setup quality using:

- Trigger strength
- Volume expansion
- Prior base / range contraction quality
- Close location near the high of day
- Risk distance to the trigger-day low
- Failure filters such as prior 3-day run-up or recent 4% breakdown
- Market gate alignment

### Step 3: Review Output

Read the generated JSON and Markdown reports. For each candidate, present:

- Trigger type and all matched trigger tags
- Day gain, dollar gain, volume ratio, and close-location percentage
- Prior base length and base width
- Entry reference, stop reference, and risk percentage to stop
- Setup score, rating, state, and reject reasons
- Suggested downstream action

### Step 4: Send Survivors to Trade Planning

Use the output conservatively:

- **A / A- candidates:** send to `technical-analyst` for manual chart validation, then `position-sizer`
- **B candidates:** watchlist or smaller-risk review only
- **Watch-only candidates:** keep in model book; do not plan a trade unless chart review upgrades the setup
- **Rejected candidates:** retain for post-analysis, not for execution

---

## 6. Resources

**References:**

- `skills/stockbee-momentum-burst-screener/references/entry_exit_rules.md`
- `skills/stockbee-momentum-burst-screener/references/momentum_burst_methodology.md`
- `skills/stockbee-momentum-burst-screener/references/scoring_system.md`

**Scripts:**

- `skills/stockbee-momentum-burst-screener/scripts/screen_momentum_burst.py`
