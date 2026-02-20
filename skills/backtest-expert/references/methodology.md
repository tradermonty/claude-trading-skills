# Backtesting Methodology Reference

## Table of Contents

1. Core Testing Techniques
2. Stress Testing Methods
3. Parameter Sensitivity Analysis
4. Slippage and Friction Modeling
5. Sample Size Guidelines
6. Market Regime Analysis
7. Common Pitfalls and Biases

## 1. Core Testing Techniques

### "Beat Ideas to Death" Approach

**Core principle**: Add friction and punishment to find strategies that break the least, not those that profit the most on paper.

**Key techniques**:
- Multiple stop loss variations
- Different profit targets
- Realistic + exaggerated commissions
- Worst-case fills
- Extended time periods
- Multiple market regimes

### The 80/20 Rule for R&D Time

- 20% generating and codifying ideas
- 80% stress testing and trying to break them

## 2. Stress Testing Methods

### Execution Friction Tests

**Required friction additions**:
- Realistic commissions (actual broker rates)
- Pessimistic slippage (1.5-2x typical)
- Worst-case entry fills (ask + 1-2 ticks)
- Worst-case exit fills (bid - 1-2 ticks)
- Order rejection scenarios
- Partial fills

### Parameter Robustness Tests

Test across multiple configurations:
- Entry timing variations (±15-30 minutes)
- Stop loss distances (50%, 75%, 100%, 125%, 150% of baseline)
- Profit targets (80%, 90%, 100%, 110%, 120% of baseline)
- Position sizing rules
- Filter thresholds

**Goal**: Find "plateau" performance where small parameter changes don't drastically alter results.

### Time-Based Robustness

**Minimum requirements**:
- Test across at least 5-10 years
- Include multiple market regimes:
  - Bull markets
  - Bear markets
  - High volatility periods
  - Low volatility periods
  - Trending markets
  - Range-bound markets

**Year-by-year analysis**: Strategy should show positive expectancy in majority of years, not rely on 1-2 exceptional years.

## 3. Parameter Sensitivity Analysis

### Heat Map Analysis

Create 2D heat maps varying two parameters simultaneously:
- Profit target (rows) × Stop loss (columns)
- Entry time (rows) × Exit time (columns)
- Volatility filter (rows) × Volume filter (columns)

**Interpretation**:
- Robust strategies show "plateaus" of consistent performance
- Fragile strategies show "spikes" or narrow optimal ranges
- Avoid strategies with performance cliffs at parameter boundaries

### Walk-Forward Analysis

1. Optimize parameters on training period (e.g., Year 1-2)
2. Test with those parameters on validation period (Year 3)
3. Roll forward and repeat
4. Compare in-sample vs out-of-sample performance

**Warning signs**:
- Out-of-sample performance <50% of in-sample
- Frequent need to re-optimize parameters
- Parameters that change dramatically between periods

### Profit Factor Scoring in Evaluation Script

The evaluation script scores profit factor (PF) as one component of the Risk Management dimension (0-8 points out of 20). The mapping uses continuous linear interpolation with integer truncation:

- PF < 1.0 → 0 points (unprofitable)
- PF 1.0 to 3.0 → linear 0 to 8 points: `int((PF - 1.0) / 2.0 * 8)`
- PF >= 3.0 → 8 points (capped)

The `int()` truncation creates discrete 1-point steps (e.g., PF 1.25→1 pt, PF 1.50→2 pt). This is intentional — integer scoring avoids false precision from fractional differences in profit factor.

## 4. Slippage and Friction Modeling

### Realistic Slippage Assumptions

**By market capitalization**:
- Mega cap (>$200B): 0.01-0.02%
- Large cap ($10B-$200B): 0.02-0.05%
- Mid cap ($2B-$10B): 0.05-0.10%
- Small cap ($300M-$2B): 0.10-0.20%
- Micro cap (<$300M): 0.20-0.50%+

**By order type**:
- Market orders: Higher slippage
- Limit orders: Lower slippage but potential non-fills
- Stop orders: Significant slippage in volatile conditions

### Conservative Testing Approach

Use 1.5-2x typical slippage estimates for stress testing:
- If typical slippage is 0.05%, test with 0.075-0.10%
- If typical is 0.10%, test with 0.15-0.20%

**Rationale**: Strategies that survive pessimistic assumptions often perform better in practice than in backtests.

## 5. Sample Size Guidelines

### Minimum Trade Requirements

**Statistical significance thresholds**:
- Absolute minimum: 30 trades
- Preferred minimum: 100 trades
- High confidence: 200+ trades

**Why large samples matter**:
- Reduces impact of outliers
- Provides statistical confidence
- Reveals true edge vs luck

### Time Period Considerations

**Minimum testing period**: 5 years
**Preferred testing period**: 10+ years

**Must include**:
- At least one full market cycle
- Multiple volatility regimes
- Different Federal Reserve policy environments

## 6. Market Regime Analysis

### Regime Classification

**Volatility-based regimes**:
- Low volatility: VIX <15
- Normal volatility: VIX 15-25
- High volatility: VIX 25-35
- Extreme volatility: VIX >35

**Trend-based regimes**:
- Strong uptrend: Market +10%+ over 6 months
- Moderate uptrend: Market +5% to +10% over 6 months
- Sideways: Market -5% to +5% over 6 months
- Downtrend: Market <-5% over 6 months

### Performance Requirements by Regime

**Robust strategy characteristics**:
- Positive expectancy in majority of regimes
- Acceptable (not necessarily best) in all regimes
- No catastrophic failures in any single regime
- Understanding of which regime causes weakness

## 7. Common Pitfalls and Biases

### Survivorship Bias

**Issue**: Testing only on currently-trading stocks ignores delisted/bankrupt companies.

**Solution**: Use survivorship-bias-free datasets that include historical delistings.

### Look-Ahead Bias

**Issue**: Using information not available at the time of trade.

**Examples**:
- Using EOD data for intraday decisions
- Using next-day's open for today's close decisions
- Calculating indicators with future data points

**Prevention**: Strict timestamp control and data alignment checks.

### Curve-Fitting (Over-Optimization)

**Warning signs**:
- Too many parameters (>=7 triggers over-optimization flag; <=4 is ideal, 5-6 acceptable)
- Highly specific parameter values (e.g., RSI = 37.3)
- Perfect backtest results
- Large performance drop in validation period

**Prevention techniques**:
- Limit parameters to essential ones only
- Use round numbers when possible
- Require out-of-sample testing
- Analyze parameter sensitivity

### Sample Selection Bias

**Issue**: Testing only on hand-picked examples (e.g., known market leaders).

**Problem**: Ignoring all stocks that met criteria but failed creates false impression of strategy quality.

**Solution**: Test on ALL historical examples meeting the criteria, not just successful outcomes.

### Hindsight Bias

**Issue**: Using outcome knowledge to influence decisions.

**Prevention for systematic trading**:
- Define all rules in advance
- No manual intervention based on hindsight
- Test rules across all cases, not cherry-picked examples

### Data Mining Bias

**Issue**: Testing hundreds of strategies until finding one that "works" by random chance.

**Risk**: With enough attempts, random data will produce seemingly profitable patterns.

**Mitigation**:
- Have hypothesis before testing
- Require economic logic for the edge
- Use Bonferroni correction for multiple comparisons
- Demand higher significance thresholds (p < 0.01 instead of p < 0.05)
