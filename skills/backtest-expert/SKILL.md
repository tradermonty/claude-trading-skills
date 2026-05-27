---
name: backtest-expert
description: Expert guidance for systematic backtesting of trading strategies. Use when developing, testing, stress-testing, or validating quantitative trading strategies. Covers "beating ideas to death" methodology, parameter robustness testing, slippage modeling, bias prevention, and interpreting backtest results. Applicable when user asks about backtesting, strategy validation, robustness testing, avoiding overfitting, or systematic trading development.
---

# Backtest Expert

Systematic approach to backtesting trading strategies based on professional methodology that prioritizes robustness over optimistic results.

## Core Philosophy

**Goal**: Find strategies that "break the least", not strategies that "profit the most" on paper.

**Principle**: Add friction, stress test assumptions, and see what survives. If a strategy holds up under pessimistic conditions, it's more likely to work in live trading.

## When to Use This Skill

Use this skill when:
- Developing or validating systematic trading strategies
- Evaluating whether a trading idea is robust enough for live implementation
- Troubleshooting why a backtest might be misleading
- Learning proper backtesting methodology
- Avoiding common pitfalls (curve-fitting, look-ahead bias, survivorship bias)
- Assessing parameter sensitivity and regime dependence
- Setting realistic expectations for slippage and execution costs

## Prerequisites

- Python 3.9+ (for evaluation script)
- No API keys required
- No external data dependencies — metrics are user-provided

## Workflow

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

## Key Testing Principles

### Punish the Strategy

Add friction everywhere:
- Commissions higher than reality
- Slippage 1.5-2x typical
- Worst-case fills
- Order rejections
- Partial fills

**Rationale**: Strategies that survive pessimistic assumptions often outperform in live trading.

### Seek Plateaus, Not Peaks

Look for parameter ranges where performance is stable, not optimal values that create performance spikes.

**Good**: Strategy profitable with stop loss anywhere from 1.5% to 3.0%
**Bad**: Strategy only works with stop loss at exactly 2.13%

Stable performance indicates genuine edge; narrow optima suggest curve-fitting.

### Test All Cases, Not Cherry-Picked Examples

**Wrong approach**: Study hand-picked "market leaders" that worked
**Right approach**: Test every stock that met criteria, including those that failed

Selective examples create survivorship bias and overestimate strategy quality.

### Separate Idea Generation from Validation

**Intuition**: Useful for generating hypotheses
**Validation**: Must be purely data-driven

Never let attachment to an idea influence interpretation of test results.

## Common Failure Patterns

Recognize these patterns early to save time:

1. **Parameter sensitivity**: Only works with exact parameter values
2. **Regime-specific**: Great in some years, terrible in others
3. **Slippage sensitivity**: Unprofitable when realistic costs added
4. **Small sample**: Too few trades for statistical confidence
5. **Look-ahead bias**: "Too good to be true" results
6. **Over-optimization**: Many parameters, poor out-of-sample results

See `references/failed_tests.md` for detailed examples and diagnostic framework.

## Output

- `reports/backtest_eval_<timestamp>.json` — structured evaluation with per-dimension scores, red flags, and verdict
- `reports/backtest_eval_<timestamp>.md` — human-readable report with dimension table, key metrics, and red flag details

## Output Artifact

All output from this skill must be structured as one of the following canonical artifact types.
Each artifact carries `manual_review_required: true`, a `disclaimer`, and a `data_gaps[]` array.

| artifact_type | Pydantic model | Description |
|---------------|---------------|-------------|
| `backtest_report` | `BacktestReport` | Scored backtest result with verdict and red-flag list |
| `backtest_spec` | `BacktestSpec` | Strategy specification with safety defaults (paper_only_until_validated: true) |

Schema: `schemas/json/backtest_report.json` (and sibling files for additional types above)

## Resources

### Methodology Reference
**File**: `references/methodology.md`

**When to read**: For detailed guidance on specific testing techniques.

**Contents**:
- Stress testing methods
- Parameter sensitivity analysis
- Slippage and friction modeling
- Sample size requirements
- Market regime classification
- Common biases and pitfalls (survivorship, look-ahead, curve-fitting, etc.)

### Failed Tests Reference
**File**: `references/failed_tests.md`

**When to read**: When strategy fails tests, or learning from past mistakes.

**Contents**:
- Why failures are valuable
- Common failure patterns with examples
- Case study documentation framework
- Red flags checklist for evaluating backtests

## Critical Reminders

**Time allocation**: Spend 20% generating ideas, 80% trying to break them.

**Context-free requirement**: If strategy requires "perfect context" to work, it's not robust enough for systematic trading.

**Red flag**: If backtest results look too good (>90% win rate, minimal drawdowns, perfect timing), audit carefully for look-ahead bias or data issues.

**Tool limitations**: Understand your backtesting platform's quirks (interpolation methods, handling of low liquidity, data alignment issues).

**Statistical significance**: Small edges require large sample sizes to prove. 5% edge per trade needs 100+ trades to distinguish from luck.

## Discretionary vs Systematic Differences

This skill focuses on **systematic/quantitative** backtesting where:
- All rules are codified in advance
- No discretion or "feel" in execution
- Testing happens on all historical examples, not cherry-picked cases
- Context (news, macro) is deliberately stripped out

Discretionary traders study differently—this skill may not apply to setups requiring subjective judgment.

## No-Lookahead Checklist

Complete this checklist before treating any backtest result as valid. A single "NO" invalidates the result.

| # | Check | Pass? |
|---|-------|-------|
| 1 | Entry/exit signals use only data available at bar close on the signal date | ☐ |
| 2 | No future prices, volumes, or events referenced in signal logic | ☐ |
| 3 | Earnings dates, dividends, and index membership known only as of signal date | ☐ |
| 4 | Survivorship bias acknowledged — delisted stocks included in universe | ☐ |
| 5 | Parameters selected before seeing test-period results (not reverse-engineered) | ☐ |
| 6 | At least 30 independent trades in the test period | ☐ |
| 7 | Out-of-sample period held back and tested only once | ☐ |
| 8 | Slippage, commissions, and borrow costs modeled (not assumed zero) | ☐ |

When producing a `BacktestSpec` artifact, populate `no_lookahead_confirmed` and
`survivorship_bias_acknowledged` only after working through this checklist.

## Paper Only Until Validated

**This skill produces decision-support output, not a live trading signal.**

A strategy is eligible for paper trading only after:
1. No-Lookahead Checklist passes (all 8 items confirmed)
2. Out-of-sample test completes with results within expected range
3. Edge degrades gracefully across parameter perturbations (plateau, not spike)

A strategy is eligible for live trading only after:
1. All paper-trading criteria met
2. Minimum 3 months paper trading with results consistent with backtest expectations
3. Trader explicitly signs off outside this repo

Output artifacts set `paper_only_until_validated: true` by default. This field must not be
set to `false` in any artifact produced by this skill.


## Data Gaps

Backtest quality depends entirely on the quality of user-supplied data. Explicit handling rules:

| Scenario | Severity | Behavior |
|----------|----------|----------|
| OHLCV history shorter than 3× the strategy lookback | HIGH | Halt — note insufficient history; do not extrapolate |
| Missing bars (gaps in OHLCV series) | HIGH | Flag in output; do not fill with averages or interpolation |
| Corporate actions (splits, dividends) not adjusted | HIGH | Warn; results may be invalid; require adjusted data |
| Fewer than 30 qualifying trade signals | MEDIUM | Continue; mark `confidence: LOW`; note small-sample caveat |
| Universe survivorship not confirmed | MEDIUM | Add survivorship warning to all output artifacts |

Do not silently ignore data quality issues. Every gap must appear in the output `data_gaps[]` array.
