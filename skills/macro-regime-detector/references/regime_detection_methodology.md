# Regime Detection Methodology

## Overview

The Macro Regime Detector uses a 3-layer signal detection approach applied to 6 cross-asset ratios, analyzed at monthly frequency with 6-month and 12-month Simple Moving Averages.

## Data Pipeline

```
Daily OHLCV (600 days, ~2.4 years)
  → Monthly Downsampling (last business day per month, ~24 points)
  → Ratio Calculation (e.g., RSP close / SPY close)
  → Moving Average Computation (6M SMA, 12M SMA)
  → Signal Detection (3 layers)
  → Component Scoring (0-100 per component)
  → Weighted Composite (6 components)
  → Regime Classification (decision tree)
  → Transition Probability Assessment
```

## Monthly Downsampling

Daily data is downsampled to monthly frequency by selecting the most recent trading day in each calendar month. This filters out daily noise and focuses on structural trends.

Why monthly: Regime transitions are structural (1-2 year) phenomena. Daily or weekly data introduces noise without adding signal for this time horizon.

## 3-Layer Signal Detection

### Layer 1: MA Crossover (0-40 points)

The primary signal is the relationship between the 6-month and 12-month SMA of each ratio.

- **Golden Cross**: 6M SMA crosses above 12M SMA (recent = 40pts, older = 20pts)
- **Death Cross**: 6M SMA crosses below 12M SMA (recent = 40pts, older = 20pts)
- **Converging**: SMAs within 1% gap, no crossover yet (0-25pts based on proximity)
- **None**: SMAs well separated, established trend (0pts)

Recency matters: A crossover 1-2 months ago is much more actionable than one 6+ months ago.

### Layer 2: Momentum Shift (0-30 points)

Compares 3-month Rate of Change (ROC) against 12-month ROC to detect early reversals.

- **Reversal Signal**: 12M ROC negative but 3M ROC positive (or vice versa). This means the long-term trend is one direction but short-term momentum has reversed — an early warning of transition.
- **Acceleration**: Strong 3M ROC in the same direction as 12M ROC confirms an existing move.

Scoring scales linearly with the magnitude of the short-term ROC (capped at 5%).

### Layer 3: Cross-Confirmation (0-30 points)

Checks alignment of multiple signals for confirmation:

1. Crossover is present (+10)
2. Short-term ROC confirms the crossover direction (+10)
3. SMA gap is widening (momentum building) (+10)

When all three align, the transition signal is strong (80-100 range).

### Signed spreads: the Treasury 10Y-2Y yield curve

The percentage thresholds above apply to positive ratios. The 10Y-2Y spread is signed and can be zero, so a percentage change would flip sign or divide by zero. When Treasury rates are available, the yield curve therefore uses changes in percentage points (pp), and its output carries `roc_unit: "pp"`:

- `roc_3m` / `roc_12m` are the signed spread changes in pp, not percentages.
- The crossover gap is the signed `6M SMA - 12M SMA` in pp. With no crossover detected, `abs(gap) < 0.10` counts as "converging".
- Reversal scoring is capped at a 0.50 pp short-term change. Acceleration needs `abs(roc_3m) > 0.30`, and the gap confirms when `abs(gap) > 0.05`.
- Spreads are rounded to 6 decimals and changes to 9. For Treasury rates quoted to three decimals, float noise therefore cannot cross a threshold or fabricate a crossover. Moves smaller than 0.000001 pp are treated as no move.
- Steepening type applies only when the curve is steepening, and uses the signed 3-month change of each yield. A falling 2Y means a bull steepener. Otherwise a rising 10Y means a bear steepener; anything else is a mixed steepener.
- Compared with percentage scoring, small moves on a positive curve now score lower. A 5 bp drift no longer scores like a 50 bp steepening.

The SHY/TLT fallback is a positive price ratio and keeps the percentage rules.

## Component Scoring Scale

Each component produces a score from 0 to 100, representing **transition signal strength** (not "good" or "bad"):

| Range | Interpretation |
|-------|---------------|
| 0-20 | Stable regime, no transition signal |
| 20-40 | Minor fluctuation, possibly noise |
| 40-60 | Transition zone — MAs converging, potential crossover in 3-6 months |
| 60-80 | Clear transition signal — recent crossover or sharp momentum reversal |
| 80-100 | Strong confirmed transition — crossover + momentum + acceleration aligned |

## Composite Score

The 6 component scores are combined using fixed weights:

| Component | Weight | Rationale |
|-----------|--------|-----------|
| Market Concentration (RSP/SPY) | 25% | Primary indicator of market structure |
| Yield Curve (10Y-2Y) | 20% | Most reliable macro cycle indicator |
| Credit Conditions (HYG/LQD) | 15% | Leading indicator of financial stress |
| Size Factor (IWM/SPY) | 15% | Economic sentiment barometer |
| Equity-Bond (SPY/TLT) | 15% | Cross-asset risk regime |
| Sector Rotation (XLY/XLP) | 10% | Consumer sentiment proxy |

## Regime Classification

A decision-tree approach scores each of 5 possible regimes based on component directions:

### Scoring Rules

**Concentration** (+2 each):
- RSP/SPY direction = "concentrating"
- IWM/SPY direction = "large_cap_leading"
- Credit direction = stable/easing (+1)

**Broadening** (+2 each):
- RSP/SPY direction = "broadening"
- IWM/SPY direction = "small_cap_leading"
- Credit direction = stable/easing (+1)
- XLY/XLP direction = risk_on (+1)

**Contraction** (+2 each):
- Credit direction = "tightening"
- XLY/XLP direction = "risk_off"
- SPY/TLT direction = "risk_off" (+1)

**Inflationary** (+3):
- Stock-bond correlation = "positive"
- SPY/TLT direction = "risk_off" (+1)

**Transitional**: Assigned when 3+ components are signaling (score >= 40) but no regime scores >= 3.

### Confidence Levels

- **High**: Best regime score >= 4
- **Moderate**: Best regime score >= 3
- **Low**: Best regime score >= 2
- **Very Low**: Best regime score < 2

## Transition Probability

Combines signaling count and average component scores:

| Signaling Count | Avg Score | Probability |
|----------------|-----------|-------------|
| 4+ | >= 50 | High (70-90%) |
| 3+ | >= 40 | Moderate (40-60%) |
| 2+ | >= 30 | Low (20-40%) |
| < 2 | < 30 | Minimal (<20%) |

## Limitations

1. **Lagging by design**: Monthly frequency means signals appear weeks to months after daily-frequency indicators. This is intentional — the goal is structural confirmation, not early detection.

2. **False positives**: Converging MAs can generate transition signals that reverse before completing. Always check cross-component confirmation.

3. **Regime overlap**: Real markets often exhibit characteristics of multiple regimes simultaneously. The "Transitional" classification explicitly acknowledges this.

4. **Historical bias**: Regime classification rules are derived from post-2000 market patterns. Novel regimes may not fit existing categories.
