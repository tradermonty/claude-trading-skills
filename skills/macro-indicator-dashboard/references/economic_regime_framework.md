# Economic Regime Framework

Classifies the macro environment into one of six regimes using a rules-based
scoring of growth and inflation direction, plus a financial-conditions overlay.

## The Two Axes

### Growth Axis

Composite of:
- `PAYEMS` 3-month annualized growth rate
- `INDPRO` 6-month change
- `ICSA` 4-week moving average, z-score (inverted: high claims = low growth)
- `UNRATE` change vs 12-month low (Sahm Rule proxy)

**Growth score:** normalized to [-2, +2]. Positive = expanding, negative = contracting.

### Inflation Axis

Composite of:
- Core PCE YoY (`PCEPI` YoY minus food/energy approximated via `CPILFESL`)
- `T5YIE` 5Y breakeven (forward inflation expectations)
- CPI 3-month annualized vs 12-month (acceleration check)

**Inflation score:** normalized to [-2, +2]. Positive = rising/high, negative = falling/low.
Target anchor is 2% (Fed's stated target).

## Regime Classification

```
                  Inflation Falling          Inflation Rising
                  ───────────────────        ───────────────────
Growth Rising     │    GOLDILOCKS    │      │    REFLATION     │
                  │                  │      │                  │
                  │  equities love   │      │  cyclicals,      │
                  │  risk-on: 70-100 │      │  commodities     │
                  │                  │      │  risk-on: 55-80  │
                  ├──────────────────┤      ├──────────────────┤
Growth Falling    │    SLOWDOWN      │      │    STAGFLATION   │
                  │                  │      │                  │
                  │  quality, long   │      │  defensives,     │
                  │  duration bonds  │      │  cash, gold      │
                  │  risk-on: 25-50  │      │  risk-on: 0-30   │
                  └──────────────────┘      └──────────────────┘

Special states (override the quadrant):
  - RECESSION:  Growth < -1.0 and NFCI > 1.0             → 0-20
  - RECOVERY:   Growth was < 0, now crossing above 0 and  → 50-75
                NFCI easing for 3+ months
```

## Classification Rules (evaluated in order)

1. **Recession check:** if Growth score <= -1.0 **and** NFCI >= 1.0, return RECESSION.
2. **Recovery check:** if 3-month-ago Growth <= -0.5 **and** current Growth > 0
   **and** NFCI falling, return RECOVERY.
3. **Stagflation check:** if Growth < 0 **and** Inflation > 0.5, return STAGFLATION.
4. **Goldilocks check:** if Growth > 0 **and** Inflation < 0, return GOLDILOCKS.
5. **Reflation check:** if Growth > 0 **and** Inflation > 0, return REFLATION.
6. **Default:** SLOWDOWN.

## Risk-on Score (0-100)

Computed as a weighted composite of normalized indicators:

```
risk_on = 50  +  (25 * growth_score)
             +  (-15 * max(0, inflation_score - 1))   # penalize high inflation
             +  (-20 * nfci_norm)                      # loose NFCI = more risk-on
             +  (-10 * credit_spread_norm)             # tight spreads = more risk-on
             +  (10 * yield_curve_norm)                # steeper = more risk-on
```

Bounded to [0, 100].

## Exposure Scale (0.0 - 1.0)

The `exposure_scale` consumed by exposure-coach is a piecewise mapping from
risk-on score:

| Risk-on Score | exposure_scale | Interpretation |
|---------------|----------------|----------------|
| 85-100 | 1.00 | Full exposure allowed |
| 70-85 | 0.85 | Near full |
| 55-70 | 0.70 | Normal |
| 40-55 | 0.50 | Cautious |
| 25-40 | 0.30 | Defensive |
| 0-25 | 0.10 | Capital preservation |

The trade-loop-orchestrator multiplies this by exposure-coach's cap and the
bubble-detector's phase cap, then takes the minimum.

## Regime-Change Alert

A regime-change alert fires when:
- The regime string changes vs the previous run, OR
- Risk-on score moves by >=15 points vs the previous run, OR
- NFCI crosses zero, OR
- Yield curve (T10Y3M) crosses zero.

Alerts are surfaced to the user and logged for the eod-reconciliation job.
