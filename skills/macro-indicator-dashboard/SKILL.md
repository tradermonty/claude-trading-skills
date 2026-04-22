---
name: macro-indicator-dashboard
description: Pull free macroeconomic data from the Federal Reserve Economic Data (FRED) API, score the current economic regime (Goldilocks, Reflation, Stagflation, Slowdown, Recession, Recovery), and emit a 0-100 risk-on score that exposure-coach uses to scale equity ceilings. Run when the user asks about macro regime, financial conditions, recession probability, FRED indicators, NFCI, yield curve, jobs report context, inflation trend, or "what does the macro say".
---

# Macro Indicator Dashboard

Pulls a curated set of free macroeconomic series from FRED, normalizes them into z-scores
relative to their long-run history, classifies the current regime using a rules-based
framework, and emits a 0-100 risk-on score consumed by exposure-coach and the
trade-loop-orchestrator.

## When to Use

- Daily, before the trade-loop runs (the orchestrator calls this skill automatically).
- When the user asks "what does the macro say", "are we in a recession", "what's the regime",
  "is the Fed easing", "are financial conditions tight", or similar macro-context questions.
- After major economic data releases (CPI, NFP, GDP, FOMC) to refresh the regime score.

## Prerequisites

- Python 3.9+
- `FRED_API_KEY` environment variable (free at https://fred.stlouisfed.org/docs/api/api_key.html)
- `requests`, `pyyaml` (standard install)

## Workflow

1. Load reference documents as needed:
   - `references/series_catalog.md` for the list of FRED series and their meaning
   - `references/economic_regime_framework.md` for regime classification rules
   - `references/interpretation_guide.md` for how to read each indicator

2. Fetch the data:
   ```bash
   python3 skills/macro-indicator-dashboard/scripts/fetch_fred_data.py \
     --output reports/macro_raw_$(date +%Y-%m-%d).json
   ```

3. Compute the regime + risk-on score:
   ```bash
   python3 skills/macro-indicator-dashboard/scripts/compute_regime.py \
     --input reports/macro_raw_$(date +%Y-%m-%d).json \
     --output reports/macro_regime_$(date +%Y-%m-%d).json
   ```

4. Generate the markdown dashboard for human review:
   ```bash
   python3 skills/macro-indicator-dashboard/scripts/generate_dashboard.py \
     --input reports/macro_regime_$(date +%Y-%m-%d).json \
     --output-dir reports/
   ```

5. Optionally check for regime-change alerts vs the previous run:
   ```bash
   python3 skills/macro-indicator-dashboard/scripts/check_alerts.py \
     --current reports/macro_regime_$(date +%Y-%m-%d).json \
     --previous reports/macro_regime_latest.json \
     --output reports/macro_alerts_$(date +%Y-%m-%d).json
   ```

6. Present the regime classification, risk-on score (0-100), top 3 contributing
   indicators, and any regime-change alerts to the user.

## Output Format

`compute_regime.py` emits JSON shaped like:

```json
{
  "as_of": "2026-04-21",
  "regime": "Goldilocks",
  "regime_confidence": 0.78,
  "risk_on_score": 72,
  "exposure_scale": 0.85,
  "indicators": {
    "yield_curve_10y2y": {"value": 0.42, "z_score": -0.6, "signal": "neutral"},
    "nfci": {"value": -0.31, "z_score": -1.2, "signal": "risk_on"},
    ...
  },
  "regime_change_alert": false,
  "narrative": "Financial conditions easing, labor still tight, inflation cooling..."
}
```

The `exposure_scale` field (0.0 - 1.0) is consumed by exposure-coach to scale its
ceiling. `risk_on_score` is also surfaced to the user.

## Six Regime States

| Regime | Growth | Inflation | Risk-on Score | Equity Posture |
|--------|--------|-----------|---------------|----------------|
| Goldilocks | + | falling | 70-100 | Aggressive long |
| Reflation | + | rising | 55-80 | Cyclicals + commodities |
| Stagflation | - | rising | 0-30 | Defensives + cash |
| Slowdown | flat/- | falling | 25-50 | Quality + duration |
| Recession | -- | -- | 0-20 | Cash heavy, scale into oversold |
| Recovery | rising | low | 50-75 | Re-risking, beta exposure |

See `references/economic_regime_framework.md` for the exact classification rules.

## Combining with Other Skills

- **exposure-coach**: consumes `exposure_scale` to set the equity ceiling.
- **trade-loop-orchestrator**: reads `risk_on_score` as one of its regime gates.
- **sector-analyst**: cross-reference regime with sector relative strength.
- **us-market-bubble-detector**: triangulate frothy regimes with bubble phase.
- **macro-regime-detector**: cross-asset ratio view; this skill is the
  fundamentals-driven complement.

## Troubleshooting

- `FRED_API_KEY not set`: export it or pass `--api-key`.
- `Series fetch failed (404)`: FRED occasionally renames series. Check the catalog.
- `Insufficient history for z-score`: the script needs >=3 years of monthly data; it
  will skip the indicator and continue.
