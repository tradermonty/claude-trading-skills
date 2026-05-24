<!-- Illustrative sample — fictional historical sample. Not investment advice. -->
<!-- Step 3 (backtest-expert, OPTIONAL): re-validate the lesson candidate.   -->

# Backtest validation — Trail under 10-EMA after 2R

**Thesis:** `th_EXMPL_growth_20260108_a1b2`
**Rule under test:** Trail under the rising 10-day EMA (1 ATR offset) after the initial 2R target is reached, for VCP breakouts in RISK_ON regimes.

## Backtest spec

| Field | Value |
|-------|-------|
| Lookback | 2020-01-01 → 2026-01-01 (6 years) |
| Sample size | 87 setups |
| Selection filter | `vcp-screener` grade A/B, RISK_ON at entry, 2R reached within 60d |
| Comparison baseline | Fixed 2R take-profit (no trail) |

## Results

| Metric | Trail rule | Fixed 2R baseline | Δ |
|--------|-----------:|------------------:|---:|
| Avg return | **14.6%** | 10.2% | **+4.4 pp** |
| Avg holding days | 38.4 | 22.1 | +16.3 d |
| Win rate | 71% | 100%¹ | -29 pp¹ |
| Premature trail exit rate | 18% | — | — |
| Max DD during trail | -4.8% | — | — |

¹ Baseline win rate is 100% **by construction** — every sample in the universe already reached 2R, so taking the fixed 2R always "wins." The trail rule's 71% reflects the rate at which the trail held above the 2R level after the initial target was hit.

## Verdict — VALIDATED_WITH_CAVEAT

Net edge is positive (+4.4 pp avg return), but at the cost of ~16 extra holding days and 18% premature trail exits. Keep the rule for VCP / RISK_ON setups, with explicit awareness of the longer holding period and the choppy-regime premature-exit risk.

## Recommended refinement

- Consider a **regime-aware trail width**: widen the ATR multiplier from 1 to 1.5 in choppy mid-cycle regimes (where the premature trail exits cluster).

## Caveats

- Backtest universe is a fictional illustrative sample for documentation purposes; real-world results will differ.
- Premature trail exits clustered in mid-cycle regimes — pure RISK_ON late-cycle setups showed a much lower premature exit rate.

> ⚠️ Illustrative sample — fictional historical sample, **not investment advice**.
