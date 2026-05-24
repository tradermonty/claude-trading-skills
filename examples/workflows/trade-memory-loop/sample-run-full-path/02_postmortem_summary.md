# Postmortem Summary — `sig_EXMPL_20260108_a1b2`

> ⚠️ Illustrative sample — fictional ticker **EXMPL**. Not investment advice.
> Companion of [`02_postmortem_findings.json`](02_postmortem_findings.json).

**Ticker:** EXMPL  **Source:** vcp-screener  **Direction:** LONG
**Outcome:** `TRUE_POSITIVE`

| Field | Value |
|---|---|
| Signal date | 2026-01-08 |
| Exit date | 2026-02-27 |
| Holding days | 50 |
| Entry price | 142.10 |
| Exit price | 168.40 |
| Realized return (5d) | +2.1% |
| Realized return (20d) | +8.3% |
| Regime at signal → exit | RISK_ON → RISK_ON |

## Classification rationale

The 5-day return (+2.1%) is the primary classifier input. Predicted
direction was **LONG** and the 5-day return was **positive**, so the signal is
a **direction match → `TRUE_POSITIVE`**. Regime was unchanged
(`RISK_ON → RISK_ON`), so no `REGIME_MISMATCH` override applied; the move was
well above the ±0.5% neutral band.

## Root-cause read (decision gate)

This was **thesis-driven, not luck**: the VCP base breakout resolved exactly
as the thesis predicted, MAE stayed shallow (-4.2%), and the advance tracked
the expected measured move. Execution (entry on the pivot, trailed exit)
added to the result rather than detracting. No process change required —
catalogue as a repeatable setup.
