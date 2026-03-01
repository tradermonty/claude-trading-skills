# Overfitting Detection Checklist

Heuristics for identifying strategy drafts that are likely overfit to historical data.

## Red Flags

### 1. Excessive Condition Count

Strategies with many entry conditions have fewer degrees of freedom and are more likely to describe noise rather than signal.

- **10+ total conditions** (entry + trend filter): Warning threshold
- **12+ total conditions**: Almost certainly overfit

### 2. Precise Threshold Values

Thresholds specified to decimal precision (e.g., "RSI > 33.5" vs "RSI > 30") suggest curve-fitting to historical data rather than capturing a robust pattern.

Detection: look for numbers containing a decimal point in condition strings.

Examples of precise thresholds:
- "RSI > 33.5" (precise: has decimal)
- "volume > 1.73 * avg" (precise: has decimal)
- "close > ma50 * 1.025" (precise: has decimal)

Examples of acceptable thresholds:
- "RSI > 30" (round number)
- "rel_volume >= 1.5" (half-step, commonly used)
- "close > ma50" (no threshold number with decimal)

### 3. Narrow Regime Specificity

Strategies designed for a single market regime (e.g., RiskOn only) with no validation across other regimes may not generalize.

### 4. Low Estimated Sample Size

If a strategy's conditions are so restrictive that fewer than 10 opportunities per year are expected, the backtest results are statistically unreliable.

### 5. Asymmetric Exit Parameters

- Stop losses wider than 15% suggest the strategy tolerates extreme adverse moves, which often indicates poor entry timing or overfit entry conditions.
- Risk-reward ratios below 1.5:1 require unrealistically high win rates to be profitable.

## Mitigation Strategies

1. Reduce condition count to essential filters only
2. Use round-number thresholds that capture behavioral levels (e.g., RSI 30/70, 50-day MA)
3. Validate across multiple regimes and time periods
4. Ensure sufficient sample size (30+ opportunities per year minimum)
5. Keep stop losses under 10% and target 2:1+ reward-to-risk
