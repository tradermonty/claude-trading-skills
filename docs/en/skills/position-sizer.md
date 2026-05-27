---
layout: default
title: "Position Sizer"
grand_parent: English
parent: Skill Guides
nav_order: 47
lang_peer: /ja/skills/position-sizer/
permalink: /en/skills/position-sizer/
---

# Position Sizer
{: .no_toc }

Calculate risk-based position sizes for long stock trades. Use when user asks about position sizing, how many shares to buy, risk per trade, Kelly criterion, ATR-based sizing, or portfolio risk allocation. Supports stop-loss distance calculation, volatility scaling, and sector concentration checks.
{: .fs-6 .fw-300 }

<span class="badge badge-free">No API</span>

[Download Skill Package (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/position-sizer.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/position-sizer){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

Calculate a reference position size for a long stock trade based on risk management principles.
Output is a decision-support calculation — the trader must approve and manually enter any resulting order at the broker. Supports three sizing methods:

- **Fixed Fractional**: Risk a fixed percentage of account equity per trade (default: 1%)
- **ATR-Based**: Use Average True Range to set volatility-adjusted stop distances
- **Kelly Criterion**: Calculate mathematically optimal risk allocation from historical win/loss statistics

All methods apply portfolio constraints (max position %, max sector %) and output a final recommended share count with full risk breakdown.

---

## 2. When to Use

- User asks "how many shares to evaluate for this setup?" or "what is my reference position size?"
- User wants to calculate position size for a specific trade setup
- User mentions risk per trade, stop-loss sizing, or portfolio allocation
- User asks about Kelly Criterion or ATR-based position sizing
- User wants to check if a position fits within portfolio concentration limits

---

## 3. Prerequisites

- No API keys required
- Python 3.9+ with standard library only

---

## 4. Quick Start

```bash
# Basic: stop-loss based sizing
python3 skills/position-sizer/scripts/position_sizer.py \
  --entry 155.00 --stop 148.50 \
  --account-size 100000 --risk-pct 1.0

# ATR-based sizing
python3 skills/position-sizer/scripts/position_sizer.py \
  --entry 155.00 --atr 3.20 --atr-multiplier 2.0 \
  --account-size 100000 --risk-pct 1.0

# Kelly Criterion (budget mode: no --entry)
python3 skills/position-sizer/scripts/position_sizer.py \
  --win-rate 0.55 --avg-win 2.5 --avg-loss 1.0 \
  --account-size 100000

# With portfolio constraints
python3 skills/position-sizer/scripts/position_sizer.py \
  --entry 155.00 --stop 148.50 \
  --account-size 100000 --risk-pct 1.0 \
  --max-position-pct 10 --max-sector-pct 30 \
  --sector Technology --current-sector-exposure 22
```

---

## 5. Workflow

### Step 1: Gather Trade Parameters

Collect from the user:
- **Required**: Account size (total equity)
- **Mode A (Fixed Fractional)**: Entry price, stop price, risk percentage (default 1%)
- **Mode B (ATR-Based)**: Entry price, ATR value, ATR multiplier (default 2.0x), risk percentage
- **Mode C (Kelly Criterion)**: Win rate, average win, average loss; optionally entry and stop for share calculation
- **Optional constraints**: Max position % of account, max sector %, current sector exposure

If the user provides a stock ticker but not specific prices, use available tools to look up the current price and suggest entry/stop levels based on technical analysis.

### Step 2: Execute Position Sizer Script

Run the position sizing calculation:

```bash
# Fixed Fractional (most common)
python3 skills/position-sizer/scripts/position_sizer.py \
  --account-size 100000 \
  --entry 155 \
  --stop 148.50 \
  --risk-pct 1.0 \
  --output-dir reports/

# ATR-Based
python3 skills/position-sizer/scripts/position_sizer.py \
  --account-size 100000 \
  --entry 155 \
  --atr 3.20 \
  --atr-multiplier 2.0 \
  --risk-pct 1.0 \
  --output-dir reports/

# Kelly Criterion (budget mode - no entry)
python3 skills/position-sizer/scripts/position_sizer.py \
  --account-size 100000 \
  --win-rate 0.55 \
  --avg-win 2.5 \
  --avg-loss 1.0 \
  --output-dir reports/

# Kelly Criterion (shares mode - with entry/stop)
python3 skills/position-sizer/scripts/position_sizer.py \
  --account-size 100000 \
  --entry 155 \
  --stop 148.50 \
  --win-rate 0.55 \
  --avg-win 2.5 \
  --avg-loss 1.0 \
  --output-dir reports/
```

### Step 3: Load Methodology Reference

Read `references/sizing_methodologies.md` to provide context on the chosen method, risk guidelines, and portfolio constraint best practices.

### Step 4: Calculate Multiple Scenarios

If the user has not specified a single method, run multiple scenarios for comparison:
- Fixed Fractional at 0.5%, 1.0%, and 1.5% risk
- ATR-based at 1.5x, 2.0x, and 3.0x multipliers
- Present a comparison table showing shares, position value, and dollar risk for each

### Step 5: Apply Portfolio Constraints and Determine Final Size

Add constraints if the user has portfolio context:

```bash
python3 skills/position-sizer/scripts/position_sizer.py \
  --account-size 100000 \
  --entry 155 \
  --stop 148.50 \
  --risk-pct 1.0 \
  --max-position-pct 10 \
  --max-sector-pct 30 \
  --current-sector-exposure 22 \
  --output-dir reports/
```

Explain which constraint is binding and why it limits the position.

### Step 6: Generate Position Report

Present the final recommendation including:
- Method used and rationale
- Exact share count and position value
- Dollar risk and percentage of account
- Stop-loss price
- Any binding constraints
- Risk management reminders (portfolio heat, loss-cutting discipline)

---

## 6. Resources

**References:**

- `skills/position-sizer/references/sizing_methodologies.md`

**Scripts:**

- `skills/position-sizer/scripts/position_sizer.py`
