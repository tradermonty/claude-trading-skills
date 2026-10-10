---
layout: default
title: Backtest Expert
grand_parent: English
parent: Skill Guides
nav_order: 7
lang_peer: /ja/skills/backtest-expert/
permalink: /en/skills/backtest-expert/
---

# Backtest Expert
{: .no_toc }

Expert guidance for systematic backtesting of trading strategies. Scores backtest quality across 5 dimensions (0-100), checks decision gates, and reports a separate decision with blocking reasons. Core philosophy: find strategies that break the least.
{: .fs-6 .fw-300 }

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

Backtest Expert applies a systematic, adversarial methodology to evaluate trading strategies. Instead of asking "how much does this strategy profit?", it asks "what breaks this strategy?" Strategies that survive pessimistic conditions are far more likely to work in live trading.

**What it solves:**
- Replaces subjective "looks good" backtest evaluations with a quantitative 5-dimension scoring framework
- Detects common red flags that indicate fragile or misleading backtests
- Provides a decision and explicit blocking reasons alongside the quality score
- Forces honest assessment of parameter sensitivity, sample size, and execution costs
- Prevents the most dangerous backtesting pitfalls: curve-fitting, look-ahead bias, and survivorship bias

**Key capabilities:**
- 5-dimension scoring (0-100): Sample Size, Expectancy, Risk Management, Robustness, Execution Realism
- Automated red flag detections (too few trades, negative expectancy, over-optimization, excessive drawdown, and more)
- Decision gates that prevent a favorable score from overriding unsafe or unverified conditions
- Parameter robustness evaluation (plateau vs. spike analysis)
- Slippage and friction stress testing at 1.5-2x typical estimates

<span class="badge badge-free">No API</span>

---

## 2. Prerequisites

- **API Key:** None required -- all metrics are user-provided
- **Python 3.9+:** Required to run the evaluation script
- **No additional Python dependencies** -- uses only the standard library
- **No external data needed** -- the script scores based on the numbers you provide

> Backtest Expert is a pure evaluation tool. You provide the backtest statistics and it scores them. No market data, no API calls, no internet connection needed.
{: .tip }

---

## 3. Quick Start

Tell Claude:

```
I backtested an earnings gap mean-reversion strategy over 8 years with 150 trades,
62% win rate, average win 1.8%, average loss 1.2%, max drawdown 15%, 3 parameters,
and I tested slippage. How does it score?
```

Or run the evaluation script directly:

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

The script scores across 5 dimensions and returns `decision` plus `blocking_reasons`. Read those before considering the legacy `verdict` or the numeric score.

---

## 4. How It Works

1. **Collect metrics** -- The script takes 8 inputs: total trades, win rate, average win %, average loss %, max drawdown %, years tested, number of tunable parameters, and whether slippage was modeled.
2. **Score 5 dimensions** -- Each dimension is scored independently on a 0-20 scale:
   - **Sample Size (20):** Based on total trades. 200+ trades scores highest; <30 trades scores zero.
   - **Expectancy (20):** Derived from profit factor (win rate x avg win / loss rate x avg loss). A profit factor of 1.0 means breakeven; 1.5+ is healthy.
   - **Risk Management (20):** Max drawdown severity and profit factor together determine this score. Drawdowns under 15% score best; over 40% scores near zero.
   - **Robustness (20):** Number of parameters and years tested. Fewer parameters (4 or fewer) and longer test periods (10+ years) score highest.
   - **Execution Realism (20):** Whether slippage and friction were modeled. Testing with slippage is worth full marks; skipping it caps the score.
3. **Detect red flags** -- Checks too few trades (<30), negative expectancy, over-optimization (7+ parameters), excessive drawdown (>=50%), untested slippage, short test period (<5 years), and unusually good results.
4. **Apply decision gates** -- `NOT_EVALUABLE` for too few trades (checked first, so it takes precedence over `REJECT`) or an overflowing profit-factor ratio; then `REJECT` for non-positive expectancy or drawdown >=50%; `RISK_LIMIT_EXCEEDED` for a tighter personal cap; `VALIDATION_REQUIRED` for missing slippage/friction testing or a short test period. Only then can the score yield `DEPLOY`, `REFINE`, or `ABANDON`. `DEPLOY` is an analysis result that still needs independent human risk review.
5. **Output reports** -- JSON and Markdown files are saved to the output directory.

---

## 5. Usage Examples

### Example 1: Evaluate an Earnings Gap Mean-Reversion Strategy

**Prompt:**
```
I tested an earnings gap strategy: 150 trades over 8 years, 62% win rate, avg win 1.8%,
avg loss 1.2%, max drawdown 15%, 3 parameters, slippage tested. Score it.
```

**Command:**
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

**Why useful:** This is a solid strategy with good sample size, positive expectancy, manageable drawdown, few parameters, and tested execution costs. The evaluation quantifies exactly how solid it is and identifies any remaining concerns.

---

### Example 2: Score a Technical Pattern Screener

**Prompt:**
```
My VCP screener found 85 trades over 5 years, 48% win rate but average win is 3.5%
and average loss 1.5%. Max drawdown was 22% with 5 parameters and no slippage testing yet.
```

**Command:**
```bash
python3 skills/backtest-expert/scripts/evaluate_backtest.py \
  --total-trades 85 \
  --win-rate 48 \
  --avg-win-pct 3.5 \
  --avg-loss-pct 1.5 \
  --max-drawdown-pct 22 \
  --years-tested 5 \
  --num-parameters 5 \
  --output-dir reports/
```

**Why useful:** This strategy has a low win rate but high payoff ratio (2.33:1). The evaluation determines whether the expectancy is strong enough to compensate, flags the missing slippage test as a concern, and notes the moderate parameter count.

---

### Example 3: Red Flag Detection (Fragile Backtest)

**Prompt:**
```
I found an amazing strategy: 25 trades over 2 years, 88% win rate, avg win 4.2%,
avg loss 0.8%, max drawdown 8%, 9 parameters, no slippage testing.
```

**Command:**
```bash
python3 skills/backtest-expert/scripts/evaluate_backtest.py \
  --total-trades 25 \
  --win-rate 88 \
  --avg-win-pct 4.2 \
  --avg-loss-pct 0.8 \
  --max-drawdown-pct 8 \
  --years-tested 2 \
  --num-parameters 9 \
  --output-dir reports/
```

**Why useful:** This backtest screams "curve-fitting." Despite impressive-looking returns, the evaluation flags multiple critical red flags: too few trades (25 < 30), too many parameters (9 triggers over-optimization), short test period (2 years), and untested slippage. The verdict is Abandon or a strong Refine at best. Results that look "too good to be true" almost always are.

---

### Example 4: Side-by-Side Comparison of Two Strategies

**Prompt:**
```
Compare Strategy A (200 trades, 55% win, 2.0% avg win, 1.5% avg loss, 18% drawdown,
7 years, 4 params, slippage tested) vs Strategy B (120 trades, 65% win, 1.2% avg win,
0.9% avg loss, 12% drawdown, 7 years, 6 params, slippage tested).
```

**What happens:** Claude runs the evaluation script twice and presents the scores side by side in a comparison table. Each dimension is compared, and the overall verdict explains which strategy is more robust and why.

**Why useful:** When choosing between two strategies, subjective "feel" is unreliable. The 5-dimension scoring framework makes the comparison objective and highlights exactly where each strategy is stronger or weaker.

---

### Example 5: Stress Test with Increased Slippage

**Prompt:**
```
My strategy works with standard slippage (0.05%). What happens if slippage doubles to 0.10%?
```

**What happens:** Claude guides you through re-running the backtest with pessimistic slippage assumptions (1.5-2x typical). The before-and-after comparison reveals how sensitive the strategy is to execution costs.

**Why useful:** Many backtests look profitable with zero or minimal slippage but fall apart under realistic execution costs. Stress testing at 1.5-2x typical slippage separates genuine edges from illusions.

---

### Example 6: Parameter Robustness Evaluation

**Prompt:**
```
My stop loss is set at 2.0%. Does the strategy still work if I vary it from 1.0% to 3.0%?
```

**What happens:** Claude asks you to run the backtest at multiple stop levels (1.0%, 1.5%, 2.0%, 2.5%, 3.0%) and evaluates whether performance shows a stable "plateau" (robust) or a narrow "spike" (fragile).

**Why useful:** A strategy that only works with a stop at exactly 2.0% is curve-fit. A strategy that works anywhere from 1.5% to 3.0% has a genuine edge. Seek plateaus, not peaks.

---

### Example 7: Walk-Forward Validation

**Prompt:**
```
I optimized on 2018-2022 data. How should I validate with 2023-2025 data?
```

**What happens:** Claude walks you through the walk-forward process: (1) apply 2018-2022 parameters unchanged to 2023-2025, (2) compare in-sample vs out-of-sample performance. If out-of-sample is less than 50% of in-sample, the strategy is likely overfit.

**Why useful:** Walk-forward analysis is the gold standard for detecting overfitting. Parameters that shift dramatically between periods, or performance that collapses out-of-sample, indicate noise rather than edge.

---

## 6. Understanding the Output

After execution, the script produces a JSON and Markdown report containing:

1. **Input Metrics** -- The raw backtest statistics you provided.
2. **Derived Metrics** -- Calculated values including profit factor, expectancy per trade, and trades per year.
3. **5-Dimension Scores** -- Each dimension scored 0-20 with a brief explanation:

| Dimension | Max Score | What It Measures |
|-----------|-----------|-----------------|
| Sample Size | 20 | Trade count and density (trades/year) |
| Expectancy | 20 | Profit factor and per-trade edge |
| Risk Management | 20 | Drawdown severity and risk-adjusted returns |
| Robustness | 20 | Parameter count and test period length |
| Execution Realism | 20 | Whether slippage and friction were modeled |

4. **Red Flags** -- A list of detected issues, each with severity (Critical, Warning, or Info) and a description.
5. **Quality Score** -- Sum of all 5 dimensions (0-100), retained even when a safety gate blocks adoption.
6. **Decision and blocking reasons** -- `DEPLOY`, `REFINE`, `ABANDON`, `REJECT`, `RISK_LIMIT_EXCEEDED`, `VALIDATION_REQUIRED`, or `NOT_EVALUABLE`. Use these fields for the next action. The older `verdict` field remains Deploy/Refine/Abandon for compatibility, never says Deploy when a gate blocks adoption, and is never better than the score-based verdict.

Fewer than 30 trades or a profit-factor ratio overflow cause `NOT_EVALUABLE`, and this takes precedence over every other gate. Otherwise, non-positive expectancy (within a 1e-9 float tolerance) and a drawdown of at least 50% cause `REJECT`. A personal drawdown cap below 50% causes `RISK_LIMIT_EXCEEDED` only when exceeded. Missing slippage/friction validation or fewer than five years cause `VALIDATION_REQUIRED`. The score cannot override these gates. `profit_factor: null` with `profit_factor_status: NO_LOSSES` means positive gross profit and no gross losses; `UNDEFINED_ZERO_GROSS` means neither gross profit nor gross losses; `OVERFLOW` means a ratio overflow despite nonzero losses. Invalid or unrepresentable numeric inputs exit with status 1 and no report.

---

## 7. Tips & Best Practices

- **Spend 80% of time trying to break the strategy.** Generating a hypothesis takes 20% of the effort; stress testing it takes 80%. If a strategy survives your best attempts to break it, the edge is likely real.
- **Treat "too good to be true" results as red flags.** Win rates above 80%, minimal drawdowns, and perfect timing are almost always artifacts of look-ahead bias, survivorship bias, or curve-fitting.
- **Require at least 100 trades.** The absolute minimum is 30, but 100+ is preferred and 200+ provides high confidence. Small samples cannot distinguish skill from luck.
- **Test across multiple market regimes.** A strategy that only works in bull markets is not an edge -- it is a leveraged bet on direction. Require positive expectancy in the majority of years tested.
- **Keep parameters to 4 or fewer.** Each parameter adds a degree of freedom that can fit noise. The script flags 7+ parameters as over-optimization.
- **Always test slippage.** Running without `--slippage-tested` requires more validation regardless of the score. Use 1.5-2x typical slippage estimates.
- **Separate idea generation from validation.** Intuition generates hypotheses; validation must be purely data-driven.

---

## 8. Combining with Other Skills

| Workflow | How to Combine |
|----------|---------------|
| **Strategy development pipeline** | Design strategy with domain knowledge, then run Backtest Expert to score it. Use `decision` and `blocking_reasons` for the next action |
| **Earnings momentum validation** | After Earnings Trade Analyzer identifies a pattern, backtest it systematically and use Backtest Expert to evaluate robustness before committing capital |
| **Position sizing calibration** | Only after the result has `decision: DEPLOY`, consider feeding win rate and payoff ratio into Position Sizer; retain independent human risk review |
| **Screener validation** | CANSLIM, VCP, and Dividend screener strategies should be backtested periodically. Run the historical results through Backtest Expert to confirm the edge persists |
| **Risk management review** | If max drawdown from the backtest exceeds your tolerance, use Position Sizer to reduce risk per trade until the expected drawdown is acceptable |

---

## 9. Troubleshooting

### Verdict is "Abandon" but the strategy looks profitable

**Cause:** The strategy may have positive returns but critical structural weaknesses: too few trades for statistical confidence, too many parameters (curve-fitting risk), or untested execution costs.

**Fix:** Read `decision` and `blocking_reasons` first. A high quality score cannot override a rejection or missing validation. If sample size is low, test over a longer period or broader universe. If parameters are too many, simplify the strategy. If slippage was not tested, re-run with 1.5x typical friction.

### Win rate is high but score is mediocre

**Cause:** High win rate alone does not guarantee a good score. If the average win is small relative to the average loss (poor payoff ratio), the expectancy may be weak despite frequent wins. A 90% win rate with 0.3% avg win and 3.0% avg loss produces negative expectancy.

**Fix:** Check the profit factor in the output. A profit factor below 1.0 means the system loses money. The expectancy dimension scores based on the combination of win rate AND payoff ratio, not win rate alone.

### Score seems too harsh

**Cause:** The scoring framework is intentionally conservative. It is designed to prevent deployment of fragile strategies, not to validate wishful thinking.

**Fix:** The score measures dimensions, while `decision` governs the next action. A score of 60-70 may need further work; check blocking reasons before interpreting the result.

### "Over-optimization" red flag with only 5 parameters

**Cause:** The script flags 7+ parameters as over-optimization. At 5-6 parameters, no flag is raised, but the Robustness dimension score is reduced compared to strategies with 4 or fewer parameters.

**Fix:** If you believe all 5 parameters are essential, the reduced score is appropriate -- more parameters do increase curve-fitting risk even if each one has a clear purpose. Consider whether any parameters can be eliminated or fixed to round numbers.

---

## 10. Reference

### CLI Arguments

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `--total-trades` | Yes | -- | Number of trades in backtest |
| `--win-rate` | Yes | -- | Win rate in percent (e.g., 62 for 62%) |
| `--avg-win-pct` | Yes | -- | Average winning trade in percent |
| `--avg-loss-pct` | Yes | -- | Average losing trade in percent (positive number) |
| `--max-drawdown-pct` | Yes | -- | Maximum drawdown in percent |
| `--years-tested` | Yes | -- | Number of years in backtest period |
| `--num-parameters` | Yes | -- | Number of tunable parameters in strategy |
| `--slippage-tested` | No | `false` | Flag indicating whether slippage/friction was modeled |
| `--max-acceptable-drawdown-pct` | No | `50` | Personal drawdown limit in percent; cannot override the hard 50% ceiling |
| `--output-dir` | No | `reports/` | Output directory for JSON and Markdown reports |

### 5-Dimension Scoring Summary

| Dimension | Points | Key Thresholds |
|-----------|--------|---------------|
| Sample Size | 0-20 | 200+ trades = full marks; <30 = near zero |
| Expectancy | 0-20 | Profit factor 1.5+ = healthy; <1.0 = negative edge |
| Risk Management | 0-20 | Drawdown <20% = best; >=50% = zero and a hard decision block |
| Robustness | 0-20 | 4 or fewer params + 10+ years = best; 7+ params = over-optimization flag |
| Execution Realism | 0-20 | Slippage tested = full marks; untested = capped |

### Verdict Criteria

| Verdict | Meaning | Typical Action |
|---------|---------|---------------|
| Deploy | Legacy summary for `decision: DEPLOY` | Consider paper validation and independent human risk review |
| Refine | Legacy summary for a refinement, personal cap, missing evidence, or unevaluable result whose score is not in the Abandon range (a score-based Abandon stays Abandon) | Read `decision` and `blocking_reasons` before acting |
| Abandon | Legacy summary for a rejection or low-score result | Read `decision` and `blocking_reasons` before acting |

### Common Red Flags

| Red Flag | Trigger |
|----------|---------|
| Too few trades | < 30 total trades |
| Negative expectancy | Profit factor < 1.0 |
| Over-optimization | 7+ tunable parameters |
| Excessive drawdown | >= 50% max drawdown; a stricter personal cap produces `RISK_LIMIT_EXCEEDED` |
| Short test period | < 5 years tested |
| Untested slippage | `--slippage-tested` not set |
