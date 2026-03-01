# Strategy Draft Review Criteria

Eight criteria (C1-C8) are applied to each strategy draft. Each criterion produces a score (0-100), a severity level, and optional revision instructions.

## Severity Levels

- **pass**: Score >= 60, no issues detected
- **warn**: Score 30-59, minor concerns that should be addressed
- **fail**: Score < 30, critical issues that must be resolved

## Verdict Logic

1. If C1 or C2 severity is "fail" -> immediate REJECT
2. Compute weighted confidence_score across all criteria
3. confidence_score >= 70 and no "fail" findings -> PASS
4. confidence_score < 35 -> REJECT
5. Otherwise -> REVISE (with revision instructions)

## C1: Edge Plausibility (Weight: 20)

Evaluate whether the strategy has a coherent, testable edge hypothesis.

| Condition | Severity | Score |
|-----------|----------|-------|
| thesis is empty or fewer than 5 words | fail | 10 |
| thesis is generic (no causal mechanism described) | warn | 40 |
| thesis contains specific causal reasoning | pass | 80 |

Generic thesis indicators: fewer than 10 words with no domain-specific terms like "momentum", "reversion", "drift", "earnings", "breakout", "gap", "volume", "sentiment".

## C2: Overfitting Risk (Weight: 20)

Assess the complexity of entry conditions relative to practical sample sizes.

| Condition | Severity | Score |
|-----------|----------|-------|
| conditions + trend_filter total > 12 | fail | 10 |
| conditions + trend_filter total > 10 | warn | 40 |
| conditions + trend_filter total <= 10 | pass | 80 |

Additional penalty: -10 per precise threshold detected in conditions (numbers with decimal points like "RSI > 33.5" or "volume > 1.73").

Minimum score after penalties: 0.

## C3: Sample Adequacy (Weight: 15)

Estimate annual trading opportunities and flag strategies that are too restrictive.

Estimation formula:
```
base = 252 (trading days)
if sector filter in conditions: base //= 3
if regime is not Neutral/Unknown/empty: base //= 2
base *= 0.8 ^ len(conditions)
base *= 0.85 ^ len(trend_filter)
result = max(base, 1)
```

| Estimated Opportunities | Severity | Score |
|------------------------|----------|-------|
| < 10 per year | fail | 10 |
| < 30 per year | warn | 40 |
| >= 30 per year | pass | 80 |

## C4: Regime Dependency (Weight: 10)

Check whether the strategy accounts for varying market regimes.

| Condition | Severity | Score |
|-----------|----------|-------|
| Single regime with no cross-regime validation plan | warn | 40 |
| Otherwise | pass | 80 |

A strategy has cross-regime validation if its validation_plan mentions "regime" or "regimes" (case-insensitive) in any of its values.

## C5: Exit Calibration (Weight: 10)

Validate stop-loss and take-profit parameters.

| Condition | Severity | Score |
|-----------|----------|-------|
| stop_loss_pct > 0.15 | fail | 10 |
| take_profit_rr < 1.5 | fail | 10 |
| Both within range | pass | 80 |

If both fail conditions are met, score is 10 (minimum).

## C6: Risk Concentration (Weight: 10)

Evaluate position sizing and concentration limits.

| Condition | Severity | Score |
|-----------|----------|-------|
| risk_per_trade > 0.02 | fail | 10 |
| risk_per_trade > 0.015 | warn | 40 |
| max_positions > 10 | fail | 10 |
| All within range | pass | 80 |

If multiple fail conditions met, use the worst (lowest) score.

## C7: Execution Realism (Weight: 10)

Check for practical execution concerns.

| Condition | Severity | Score |
|-----------|----------|-------|
| No volume filter in conditions | warn | 50 |
| export_ready_v1=true but entry_family not in EXPORTABLE_FAMILIES | fail | 10 |
| Otherwise | pass | 80 |

EXPORTABLE_FAMILIES = {"pivot_breakout", "gap_up_continuation"}

If both conditions trigger, use the worst (lowest) score and severity.

## C8: Invalidation Quality (Weight: 5)

Assess the quality of invalidation signals.

| Condition | Severity | Score |
|-----------|----------|-------|
| invalidation_signals is empty | fail | 10 |
| invalidation_signals has fewer than 2 entries | warn | 40 |
| 2 or more entries | pass | 80 |

## Weight Summary

| Criterion | Weight |
|-----------|--------|
| C1 Edge Plausibility | 20 |
| C2 Overfitting Risk | 20 |
| C3 Sample Adequacy | 15 |
| C4 Regime Dependency | 10 |
| C5 Exit Calibration | 10 |
| C6 Risk Concentration | 10 |
| C7 Execution Realism | 10 |
| C8 Invalidation Quality | 5 |
| **Total** | **100** |
