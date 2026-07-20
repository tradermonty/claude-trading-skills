---
layout: default
title: Position Sizer
grand_parent: English
parent: Skill Guides
nav_order: 6
lang_peer: /ja/skills/position-sizer/
permalink: /en/skills/position-sizer/
---

# Position Sizer
{: .no_toc }

Calculate risk-based position sizes for long stock trades using Fixed Fractional, ATR-Based, or Kelly Criterion methods. Supports whole-share or fractional-share output, portfolio constraints, sector concentration checks, and multi-scenario comparison.
{: .fs-6 .fw-300 }

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

Position Sizer answers the most important question in trade execution: "How many shares should I buy?" Correct sizing is the single most important factor in long-term portfolio survival. A great stock pick with bad sizing can destroy an account; a mediocre pick with proper sizing preserves capital for the next opportunity.

**What it solves:**
- Eliminates guesswork from position sizing decisions
- Enforces disciplined risk management with a fixed percentage of account equity at risk
- Adjusts for volatility differences across stocks using ATR-based sizing
- Calculates mathematically optimal allocation via Kelly Criterion
- Applies portfolio-level constraints (max position size, sector concentration limits)
- Lets small accounts use broker-supported fractional shares without rounding above the risk budget

**Key capabilities:**
- 3 sizing methods: Fixed Fractional, ATR-Based, and Kelly Criterion
- Portfolio constraints: max position % of account, max sector %, current sector exposure tracking
- Binding constraint identification: tells you which limit is capping your position
- Fractional-share mode: `--fractional --share-precision N` floors shares to the requested decimal precision
- Pure calculation -- no API keys, no internet, works completely offline

<span class="badge badge-free">No API</span>

---

## 2. Prerequisites

- **API Key:** None required -- pure mathematical calculations
- **Python 3.9+:** Required to run the calculation script
- **No additional Python dependencies** -- uses only the standard library
- **No internet connection needed** -- works completely offline

> Position Sizer is a self-contained calculator. It requires no API keys, no market data feeds, and no external dependencies. Provide the numbers and it does the math.
{: .tip }

---

## 3. Quick Start

Tell Claude:

```
I have a $100,000 account. I want to buy AAPL at $155 with a stop at $148.50, risking 1% of my account. How many shares?
```

Or run the script directly:

```bash
python3 skills/position-sizer/scripts/position_sizer.py \
  --account-size 100000 \
  --entry 155 \
  --stop 148.50 \
  --risk-pct 1.0 \
  --output-dir reports/
```

Claude calculates 153 shares ($23,715 position, $994.50 at risk) and explains the reasoning. That is all you need to get started.

For a small account or high-priced stock, enable fractional shares only if your broker supports them:

```bash
python3 skills/position-sizer/scripts/position_sizer.py \
  --account-size 1000 \
  --entry 155 \
  --stop 148.50 \
  --risk-pct 1.0 \
  --fractional \
  --share-precision 4 \
  --output-dir reports/
```

The fractional command returns 1.5384 shares, keeping planned risk at or below the $10 budget.

---

## 4. How It Works

1. **Gather parameters** -- The script collects account size, entry price, stop price (or ATR), and risk percentage. For Kelly Criterion, it collects win rate and average win/loss statistics.
2. **Calculate risk per share** -- For Fixed Fractional: `entry - stop`. For ATR-Based: `ATR * multiplier`. For Kelly: derived from the half-Kelly budget and entry/stop distance.
3. **Compute base share count** -- `dollar_risk / risk_per_share`, always floored. Whole-share mode floors to an integer; fractional mode floors to the requested decimal precision. Rounding up would exceed the risk budget.
4. **Apply portfolio constraints** -- If `--max-position-pct` or `--max-sector-pct` is specified, the share count is capped by the tightest constraint. The binding constraint is identified in the output.
5. **Generate reports** -- JSON and Markdown files are saved to the output directory with full calculation details, constraint analysis, and the final recommendation.

**Three sizing modes:**

| Mode | Required Inputs | Best For |
|------|----------------|----------|
| Fixed Fractional | Entry, stop, risk % | Discretionary trades with clear technical stops |
| ATR-Based | Entry, ATR, multiplier, risk % | Systematic trading, cross-stock volatility normalization |
| Kelly Criterion | Win rate, avg win, avg loss | Capital allocation planning with a proven track record |
| Fractional output | Any share mode + `--fractional` | Small accounts, high-priced stocks, broker-supported fractional trading |

---

## 5. Usage Examples

### Example 1: Basic Stop-Loss Based Sizing

**Prompt:**
```
I have $100,000. Buy at $155, stop at $148.50, risk 1%.
```

**Command:**
```bash
python3 skills/position-sizer/scripts/position_sizer.py \
  --account-size 100000 \
  --entry 155 \
  --stop 148.50 \
  --risk-pct 1.0 \
  --output-dir reports/
```

**Result:** 153 shares, $23,715 position value, $994.50 dollar risk (0.99% of account).

**Why useful:** The most common sizing method. Define your stop based on chart support, and the calculator tells you exactly how many shares fit within your risk budget.

---

### Example 2: ATR-Based Volatility-Adjusted Sizing

**Prompt:**
```
Size a position in NVDA at $850 entry, ATR(14) is $22.50, use 2x ATR multiplier and 1% risk on a $100,000 account.
```

**Command:**
```bash
python3 skills/position-sizer/scripts/position_sizer.py \
  --account-size 100000 \
  --entry 850 \
  --atr 22.50 \
  --atr-multiplier 2.0 \
  --risk-pct 1.0 \
  --output-dir reports/
```

**Result:** 22 shares, stop at $805.00, $990 dollar risk.

**Why useful:** ATR-based sizing automatically adjusts for volatility. A low-volatility stock gets a larger position (tighter stop), while a high-volatility stock gets a smaller position (wider stop). This normalizes risk across different stocks in your portfolio.

---

### Example 3: Kelly Criterion (Budget Mode)

**Prompt:**
```
My trading system has a 55% win rate with average wins of $2.50 and average losses of $1.00. What percentage of my $100,000 account should I allocate?
```

**Command:**
```bash
python3 skills/position-sizer/scripts/position_sizer.py \
  --account-size 100000 \
  --win-rate 0.55 \
  --avg-win 2.5 \
  --avg-loss 1.0 \
  --output-dir reports/
```

**Result:** Full Kelly = 37%, Half Kelly = 18.5%, recommended risk budget = $18,500.

**Why useful:** When you do not yet have a specific entry and stop, Kelly Criterion tells you how much capital to allocate based on your system's historical edge. Always use half Kelly in practice -- it captures 75% of the theoretical growth with dramatically lower drawdowns.

---

### Example 4: Portfolio Constraints

**Prompt:**
```
Same AAPL trade ($155 entry, $148.50 stop, 1% risk), but cap any single position at 10% of account and Tech sector at 30%. I already have 22% in Tech.
```

**Command:**
```bash
python3 skills/position-sizer/scripts/position_sizer.py \
  --account-size 100000 \
  --entry 155 \
  --stop 148.50 \
  --risk-pct 1.0 \
  --max-position-pct 10 \
  --max-sector-pct 30 \
  --sector Technology \
  --current-sector-exposure 22 \
  --output-dir reports/
```

**Result:** Risk-based = 153 shares, but sector constraint limits to 51 shares ($7,905 position). Binding constraint: sector concentration (only 8% room remaining in Tech).

**Why useful:** Portfolio constraints prevent concentration risk from creeping in. Even though the risk calculation says 153 shares, the sector limit recognizes that adding more Tech exposure would push the portfolio past 30% in a single sector.

---

### Example 5: Multiple Scenario Comparison

**Prompt:**
```
Compare position sizes at 0.5%, 1.0%, and 1.5% risk for a $200,000 account, entry $75, stop $71.
```

**What happens:** Claude runs the script three times with different `--risk-pct` values and presents a comparison table showing shares, position value, and dollar risk at each level (e.g., 250 / 500 / 750 shares respectively).

**Why useful:** Seeing multiple scenarios side-by-side helps you choose the right risk level based on conviction, market conditions, and current portfolio heat. Conservative after a losing streak? Use 0.5%. High-conviction setup in a Strong breadth zone? Consider 1.0-1.5%.

---

### Example 6: Fractional Shares for a Small Account

**Prompt:**
```
I have a $1,000 account. Entry $155, stop $148.50, risk 1%. My broker supports fractional shares.
```

**Command:**
```bash
python3 skills/position-sizer/scripts/position_sizer.py \
  --account-size 1000 \
  --entry 155 \
  --stop 148.50 \
  --risk-pct 1.0 \
  --fractional \
  --share-precision 4 \
  --output-dir reports/
```

**Result:** Whole-share mode would return 1 share. Fractional mode returns 1.5384 shares, keeping planned risk at or below $10 while using more of the intended risk budget.

**Why useful:** This avoids rounding a small account down so far that the planned risk model becomes meaningless. It still depends on broker support, minimum order value, spreads, slippage, and fees.

---

### Example 7: Sector Concentration Check

**Prompt:**
```
I already have 22% in Technology. Can I add another Tech position within my 30% limit?
```

**Command:**
```bash
python3 skills/position-sizer/scripts/position_sizer.py \
  --account-size 100000 --entry 155 --stop 148.50 --risk-pct 1.0 \
  --max-sector-pct 30 --sector Technology --current-sector-exposure 22 \
  --output-dir reports/
```

**Result:** Sector has 8% remaining ($8,000). Maximum 51 shares ($7,905), below the 153 from risk-based calculation. Sector constraint is binding.

**Why useful:** Sector checks prevent inadvertent concentration during a hot streak. The binding constraint report makes it clear exactly why the position is smaller than expected.

---

### Example 8: Natural Language Request

**Prompt:**
```
How many shares of MSFT should I buy? My account is $50,000, I want tight risk,
and the stock is at $420 with recent support at $408.
```

**What happens:** Claude interprets "tight risk" as 0.5-1.0%, uses the support level as the stop, and runs the calculation. It presents the result with an explanation of the stop placement and share count.

**Why useful:** You do not need to remember CLI arguments. Describe your situation in plain language and Claude extracts the parameters, runs the calculation, and explains the result.

---

## 6. Understanding the Output

After execution, the script produces a JSON and Markdown report containing:

1. **Parameters Summary** -- Account size, entry price, stop price, risk percentage, and any constraints.
2. **Calculation Details** -- The active sizing method with step-by-step math: risk per share, dollar risk, and base share count.
3. **Constraints Analysis** -- If max position or sector limits were specified, each constraint is evaluated and the binding constraint is identified.
4. **Final Recommendation** -- The recommended share count (always the minimum across all constraints), position value, dollar risk, and risk as a percentage of account.

### Key JSON Fields

| Field | Description |
|-------|-------------|
| `mode` | `shares` (entry/stop provided) or `budget` (Kelly only, no entry) |
| `final_recommended_shares` | The number to trade -- minimum across all constraints |
| `binding_constraint` | Which limit capped the position: `risk_based`, `max_position_pct`, or `max_sector_pct` |
| `parameters.fractional_shares` | Present when fractional-share mode is enabled |
| `parameters.share_precision` | Decimal precision used for fractional-share flooring |

---

## 7. Tips & Best Practices

- **Default to 1% risk.** The 1% rule is the industry standard for swing traders. Never exceed 2% without exceptional reason and a proven track record.
- **Always floor.** Whole-share mode floors to an integer. Fractional mode floors to the requested precision. Rounding up would exceed your risk budget.
- **Use half Kelly, never full Kelly.** Full Kelly maximizes theoretical growth but produces extreme drawdowns (50%+). Half Kelly captures 75% of the growth with far more manageable volatility.
- **Check portfolio heat.** Total open risk across all positions should stay below 6-8% of account equity. If you are already at 6%, do not add new positions until existing trades move to breakeven or close.
- **Reduce risk after losses.** After 2-3 consecutive losses, drop to 0.5% risk per trade. Protect capital during drawdowns, then scale back up after wins confirm the market environment.
- **Combine constraints for safety.** Use both `--max-position-pct` and `--max-sector-pct` together. The strictest constraint wins, preventing both single-stock and sector concentration risk.
- **Account for friction.** Small fractional orders can be dominated by spreads, slippage, fees, minimum order values, currency conversion, and settlement or margin limits.
- **Check intraday controls at the broker.** FINRA replaced the old pattern-day-trader day-count and $25,000 minimum-equity requirements with intraday margin standards effective 2026-06-04, with broker phase-in allowed through 2027-10-20. Your broker's current controls still decide what you can actually do in a margin account. Source: <https://www.finra.org/rules-guidance/notices/26-10>

---

## 8. Combining with Other Skills

| Workflow | How to Combine |
|----------|---------------|
| **Post-screener sizing** | After CANSLIM, VCP, or Dividend screeners identify candidates, use Position Sizer to calculate exact share counts before entry |
| **Breadth-adjusted risk** | Use Market Breadth Analyzer to determine the health zone, then adjust risk percentage: 1.0-1.5% in Strong zone, 0.5% in Weakening zone |
| **Backtest validation** | After Backtest Expert confirms a strategy's edge, use the win rate and payoff ratio as Kelly Criterion inputs for optimal capital allocation |
| **Technical entry planning** | Use Technical Analyst to identify the stop level (support, moving average, prior low), then feed it into Position Sizer for the share count |
| **Portfolio rebalancing** | After Portfolio Manager reviews current holdings, use Position Sizer with sector constraints to size new additions without exceeding concentration limits |

---

## 9. Troubleshooting

### "Error: --account-size is required"

**Cause:** The `--account-size` argument was not provided.

**Fix:** Always include `--account-size` with your total account equity. This is the only truly required argument.

### Position size seems too small

**Cause:** Typically one of three reasons: (1) the stop is very wide relative to the entry, (2) a portfolio constraint is binding, or (3) the stock price is high relative to account size.

**Fix:** Check the `binding_constraint` field in the JSON output. If it shows `max_position_pct` or `max_sector_pct`, the constraint is limiting you below the risk-based calculation. If the risk-based shares are already small, the stop distance is wide -- consider whether the stop is appropriately placed.

### Kelly Criterion returns 0%

**Cause:** The trading system has negative expected value. When the Kelly formula produces a negative number, it is floored at 0%, meaning "do not trade this system."

**Fix:** This is not a bug -- it is the correct mathematical answer. A negative Kelly means the system loses money over time. Re-evaluate the strategy's win rate and payoff ratio before trading.

### "No sizing method could be determined"

**Cause:** Insufficient arguments were provided. The script needs at least one complete set: (1) entry + stop + risk-pct, (2) entry + ATR + risk-pct, or (3) win-rate + avg-win + avg-loss.

**Fix:** Provide a complete set of arguments for at least one sizing method. See the CLI Arguments table below for required combinations.

---

## 10. Reference

### CLI Arguments

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `--account-size` | Yes | -- | Total account value in dollars |
| `--entry` | No | -- | Entry price per share |
| `--stop` | No | -- | Stop-loss price per share |
| `--risk-pct` | No | -- | Risk percentage per trade (e.g., 1.0 for 1%) |
| `--atr` | No | -- | Average True Range value for ATR-based sizing |
| `--atr-multiplier` | No | `2.0` | ATR multiplier for stop distance |
| `--win-rate` | No | -- | Historical win rate (0-1) for Kelly Criterion |
| `--avg-win` | No | -- | Average win amount for Kelly Criterion |
| `--avg-loss` | No | -- | Average loss amount for Kelly Criterion |
| `--max-position-pct` | No | -- | Maximum single position as % of account |
| `--max-sector-pct` | No | -- | Maximum sector exposure as % of account |
| `--sector` | No | -- | Sector name for concentration check |
| `--current-sector-exposure` | No | `0.0` | Current sector exposure as % of account |
| `--fractional` | No | `false` | Enable fractional share output |
| `--share-precision` | No | `4` | Decimal places for fractional shares, 0-8 |
| `--output-dir` | No | `reports/` | Output directory for JSON and Markdown reports |

### Sizing Method Comparison

| Feature | Fixed Fractional | ATR-Based | Kelly Criterion |
|---------|-----------------|-----------|-----------------|
| Input needed | Entry, stop, risk % | Entry, ATR, multiplier, risk % | Win rate, avg win/loss |
| Adjusts for volatility | No | Yes | No (uses historical stats) |
| Requires track record | No | No | Yes (100+ trades) |
| Best for | Discretionary trades | Systematic/mechanical | Capital allocation |
| Stop determined by | Chart analysis | ATR calculation | External (chart or ATR) |

### Standard Risk Levels

| Risk % | Trader Profile | Notes |
|--------|---------------|-------|
| 0.25-0.50% | Conservative / large account | Institutional-grade risk |
| 0.50-1.00% | Experienced swing trader | Minervini recommended range |
| 1.00-1.50% | Active trader, proven edge | Standard for tested systems |
| 1.50-2.00% | Aggressive, high win-rate | Maximum for most strategies |
| > 2.00% | Dangerous | Ruin risk increases rapidly |
