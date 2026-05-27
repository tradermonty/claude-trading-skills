---
layout: default
title: "Backtest Expert"
grand_parent: English
parent: Skill Guides
nav_order: 11
lang_peer: /ja/skills/backtest-expert/
permalink: /en/skills/backtest-expert/
---

# Backtest Expert
{: .no_toc }

Expert guidance for systematic backtesting of trading strategies. Use when developing, testing, stress-testing, or validating quantitative trading strategies. Covers "beating ideas to death" methodology, parameter robustness testing, slippage modeling, bias prevention, and interpreting backtest results. Applicable when user asks about backtesting, strategy validation, robustness testing, avoiding overfitting, or systematic trading development.
{: .fs-6 .fw-300 }

<span class="badge badge-free">No API</span>

[Download Skill Package (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/backtest-expert.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/backtest-expert){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

# Backtest Expert

---

## 2. When to Use

Use this skill when:
- Developing or validating systematic trading strategies
- Evaluating whether a trading idea is robust enough for live implementation
- Troubleshooting why a backtest might be misleading
- Learning proper backtesting methodology
- Avoiding common pitfalls (curve-fitting, look-ahead bias, survivorship bias)
- Assessing parameter sensitivity and regime dependence
- Setting realistic expectations for slippage and execution costs

---

## 3. Prerequisites

- Python 3.9+ (for evaluation script)
- No API keys required
- No external data dependencies — metrics are user-provided

---

## 4. Quick Start

```bash
python3 skills/backtest-expert/scripts/evaluate_backtest.py \
  --total-trades 150 \
  --win-rate 62 \
  --avg-win-pct 1.8 \
  --avg-loss-pct 1.2 \
  --max-drawdown-pct 15 \
  --years-tested 8 \
  --num-parameters 3 \
  --slippage-tested \
  --output-dir reports/
```

---

## 5. Workflow

### 1. State the Hypothesis

Define the edge in one sentence.

**Example**: "Stocks that gap up >3% on earnings and pull back to previous day's close within first hour provide mean-reversion opportunity."

If you can't articulate the edge clearly, don't proceed to testing.

### 2. Codify Rules with Zero Discretion

Define with complete specificity:
- **Entry**: Exact conditions, timing, price type
- **Exit**: Stop loss, profit target, time-based exit
- **Position sizing**: Fixed $$, % of portfolio, volatility-adjusted
- **Filters**: Market cap, volume, sector, volatility conditions
- **Universe**: What instruments are eligible

**Critical**: No subjective judgment allowed. Every decision must be rule-based and unambiguous.

### 3. Run Initial Backtest

Test over:
- **Minimum 5 years** (preferably 10+)
- **Multiple market regimes** (bull, bear, high/low volatility)
- **Realistic costs**: Commissions + conservative slippage

Examine initial results for basic viability. If fundamentally broken, iterate on hypothesis.

### 4. Stress Test the Strategy

This is where 80% of testing time should be spent.

**Parameter sensitivity**:
- Test stop loss at 50%, 75%, 100%, 125%, 150% of baseline
- Test profit target at 80%, 90%, 100%, 110%, 120% of baseline
- Vary entry/exit timing by ±15-30 minutes
- Look for "plateaus" of stable performance, not narrow spikes

**Execution friction**:
- Increase slippage to 1.5-2x typical estimates
- Model worst-case fills (buy at ask+1 tick, sell at bid-1 tick)
- Add realistic order rejection scenarios
- Test with pessimistic commission structures

**Time robustness**:
- Analyze year-by-year performance
- Require positive expectancy in majority of years
- Ensure strategy doesn't rely on 1-2 exceptional periods
- Test in different market regimes separately

**Sample size**:
- Absolute minimum: 30 trades
- Preferred: 100+ trades
- High confidence: 200+ trades

### 5. Out-of-Sample Validation

**Walk-forward analysis**:
1. Optimize on training period (e.g., Year 1-3)
2. Test on validation period (Year 4)
3. Roll forward and repeat
4. Compare in-sample vs out-of-sample performance

**Warning signs**:
- Out-of-sample <50% of in-sample performance
- Need frequent parameter re-optimization
- Parameters change dramatically between periods

### 6. Evaluate Results

**Questions to answer**:
- Does edge survive pessimistic assumptions?
- Is performance stable across parameter variations?
- Does strategy work in multiple market regimes?
- Is sample size sufficient for statistical confidence?
- Are results realistic, not "too good to be true"?

**Decision criteria**:
- ✅ **Deploy**: Survives all stress tests with acceptable performance
- 🔄 **Refine**: Core logic sound but needs parameter adjustment
- ❌ **Abandon**: Fails stress tests or relies on fragile assumptions

Use the evaluation script for a structured, quantitative assessment:

```bash
python3 skills/backtest-expert/scripts/evaluate_backtest.py \
  --total-trades 150 \
  --win-rate 62 \
  --avg-win-pct 1.8 \
  --avg-loss-pct 1.2 \
  --max-drawdown-pct 15 \
  --years-tested 8 \
  --num-parameters 3 \
  --slippage-tested \
  --output-dir reports/
```

The script scores across 5 dimensions (Sample Size, Expectancy, Risk Management, Robustness, Execution Realism), detects red flags, and outputs a Deploy/Refine/Abandon verdict.

---

## 6. Resources

**References:**

- `skills/backtest-expert/references/failed_tests.md`
- `skills/backtest-expert/references/methodology.md`

**Scripts:**

- `skills/backtest-expert/scripts/evaluate_backtest.py`
