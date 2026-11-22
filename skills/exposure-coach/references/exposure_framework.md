# Exposure Framework

## Overview

This document defines the scoring rules and threshold logic used by the Exposure Coach to synthesize multiple market signals into a unified exposure recommendation.

## Component Scoring (0-100 Scale)

Each input dimension is normalized to a 0-100 score where:
- **0-30**: Bearish / Risk-off signal
- **31-50**: Cautious / Neutral-bearish
- **51-70**: Neutral-bullish / Constructive
- **71-100**: Bullish / Risk-on signal

### Breadth Score

Derived from advance/decline ratios and new highs vs new lows:

| A/D Ratio (10-day) | NH/NL Ratio | Breadth Score |
|-------------------|-------------|---------------|
| > 1.5 | > 3.0 | 80-100 |
| 1.0 - 1.5 | 1.0 - 3.0 | 50-79 |
| 0.7 - 1.0 | 0.5 - 1.0 | 30-49 |
| < 0.7 | < 0.5 | 0-29 |

### Uptrend Score

Direct mapping from uptrend participation percentage:

| Uptrend % | Score |
|-----------|-------|
| > 50% | 75-100 |
| 35-50% | 50-74 |
| 20-35% | 30-49 |
| < 20% | 0-29 |

### Regime Score

Based on macro-regime-detector output:

| Regime | Score | Rationale |
|--------|-------|-----------|
| Broadening | 80 | Healthy expansion; rising tide lifts all boats |
| Concentration | 60 | Narrow leadership; selective opportunities |
| Transitional | 50 | Uncertainty; reduce commitment |
| Inflationary | 40 | Rotation stress; defensive posture |
| Contraction | 20 | Risk-off; preserve capital |

### Top Risk Score (Inverted)

Higher distribution day counts and top probability → lower score:

| Distribution Days | Top Probability | Score |
|-------------------|-----------------|-------|
| 0-2 | < 20% | 80-100 |
| 3-4 | 20-40% | 50-79 |
| 5-6 | 40-60% | 30-49 |
| 7+ | > 60% | 0-29 |

### FTD Score (Follow-Through Day)

ftd-detector reports Follow-Through Day quality as `quality_score.total_score`
(0-100). The score is used directly, with no inversion: higher means stronger
technical confirmation of a rally attempt.

The following are the base bands before lifecycle overrides:

| `quality_score.total_score` | ftd-detector `signal` |
|-----------------------------|-----------------------|
| 80-100 | Strong FTD |
| 60-79 | Moderate FTD |
| 40-59 | Weak FTD |
| < 40 | Very weak FTD |

When `ftd_invalidation.warning` is true, the detector caps quality at 59 and
replaces the base-band signal with `FTD under pressure`. This FTD-day-low
warning weakens confirmation without invalidating the rally. Read the emitted
signal and lifecycle metadata rather than reconstructing the signal from a band.

A score of 0 does not say what happened. Read `quality_score.signal`, the
market state and `quality_score.data_gap` to tell the cases apart:

- `No FTD`: no qualifying Follow-Through Day in the current window.
- `Failed/Invalidated`: the FTD was invalidated (for example
  `market_state.combined_state: FTD_INVALIDATED`).
- `Unavailable: data gap`, with `data_gap: true`: the price inputs had a gap,
  so the quality could not be measured.
- `Very weak FTD`: an FTD was detected, but its penalties took the score down
  to the 0 floor.
- `FTD under pressure`: a warning is active and health penalties took the
  score to 0; the warning signal still overrides the base band.

Exposure Coach scores every 0 the same way, as no confirmation. The quality
score is neither a success probability nor an allocation percentage. FTD is
one component of the composite, with a 5% base weight that is renormalized
over the usable inputs like every other weight. It has no separate exposure
ceiling adjustment.

Legacy input: a top-level `anomaly_level` field (`none` 90, `low` 80,
`moderate` 55, `elevated` 35, `critical` 15) is still accepted for backward
compatibility. The current ftd-detector does not emit it.

### Theme Score

Canonical theme-detector reports use `themes.all` once and require valid
`data_quality` (`ok`/`warning` plus string-list flags). Each theme must have a
bullish/bearish direction and finite numeric non-boolean heat in [0,100]. Compute
`round(50 + mean(signed_heat)/2)`, with bullish positive and bearish negative
(Python nearest integer, ties to even). Heat 80 maps to 90 bullish / 10 bearish;
equal opposing heat maps to 50. This equally weighted integration heuristic is
uncalibrated, not a forecast or freshness check. Upstream flags remain visible.
Invalid/missing rows or quality reject the whole input; don't substitute zeros.

Legacy theme-strength labels retain the following qualitative mapping (exact
scores: strong=85, stable=65, rotating=40, collapsing=20):

| Theme Status | Score |
|--------------|-------|
| Strong, expanding | 80-100 |
| Stable | 50-79 |
| Rotating / Churning | 30-49 |
| Collapsing | 0-29 |

### Sector Score

#### Canonical Sector Analyst reports

Consume `analyze_sector_rotation.py --json --save` output without adding flat
legacy fields. The consumer owns mapping version `sector_uptrend_health_v1`.
It is an uncalibrated equal-sector health heuristic, not a forecast or a
stock-weighted market ratio. `groups.score` measures relative cyclical versus
defensive rotation and is not substituted for absolute sector health.

Require `ranking` to contain each of these sectors exactly once: Technology,
Consumer Cyclical, Communication Services, Financial, Industrials, Utilities,
Consumer Defensive, Healthcare, Real Estate, Energy, and Basic Materials.
Names and Up/Down labels are case-insensitive and trimmed. Each row requires
a finite non-boolean `ratio` in [0,1], a `slope` that is null or a finite
non-boolean number in [-1,1], and a string trend label. A null slope (the
producer emits it for a blank CSV cell) or a label that disagrees with the
slope sign is accepted with a warning and gets no trend adjustment.
A report whose slopes are all null is rejected, as the provider contract requires.
Both `trends.uptrend_count`/`downtrend_count` must be integers, and both sector
lists must match the ranking rows without duplicates. Reject the whole report
on missing, partial, contradictory or invalid required data. A canonical-shaped
payload cannot bypass validation by adding `sector_score` or legacy context.

For each ratio `r`, reuse Uptrend Analyzer's absolute ratio bands:

| Ratio range | Unrounded base score |
|---|---|
| `0 <= r < 0.097` | `9 * r / 0.097` |
| `0.097 <= r < 0.25` | `10 + 29 * (r - 0.097) / (0.25 - 0.097)` |
| `0.25 <= r < 0.37` | `40 + 29 * (r - 0.25) / (0.37 - 0.25)` |
| `0.37 <= r < 0.50` | `70 + 19 * (r - 0.37) / (0.50 - 0.37)` |
| `0.50 <= r <= 1` | `min(100, 90 + 10 * (r - 0.50) / 0.10)` |

Add +5 for an Up label with positive slope, -5 for a Down label with negative
slope, and 0 otherwise (as Uptrend Analyzer does); clamp
each adjusted value to [0,100]. Average the 11 **unrounded** adjusted values
equally, then round once to the nearest integer, ties to even. There is no
low-spread bonus: uniformly weak sectors must not gain health points merely
because their ratios are similar.

This mapping supplies only the sector component of the composite (base weight
5%). Canonical ranking, rotation and ratio spread do not supply `leadership` or
`dispersion` to the separate bias/participation rules; those outputs use other
accepted inputs. Rejected sector data contributes neither score nor context.

`sector_integration` records `mapping_version`, `score`, `sector_count`,
`positive_slope_count`, `mean_ratio`, per-sector `sector_health`, and the scope.
Its `source_freshness` preserves the producer's metadata and
`freshness_verified` is false. `meta` must be an object; absent/null
`meta.freshness` is accepted with an unknown-freshness warning. A freshness
object requires a YYYY-MM-DD `date`, boolean `is_fresh`, and string/null
`warning`; malformed metadata rejects the input. Producer-reported stale data
and nonempty warnings remain visible in JSON, Markdown and stderr without
excluding an otherwise usable report. Even `is_fresh: true` is only the
producer's statement. Without `--as-of`, the consumer does not recheck current
age. It never binds that date to every ranking row.
With `--as-of`, the sector source date (`meta.freshness.date`) is also
age-gated: it is compared with the evaluation date in America/New_York, and a
source date after that date or older than `--max-age-days` excludes sector as
unusable. In `--require-provenance` mode, unknown freshness and undated legacy
sector input are excluded too. An excluded sector never stops the run; it is
reported in `inputs_unparseable`, `input_warnings`, Markdown and stderr. A
passing check sets `freshness_verified: true` and records `freshness_check`.
Outside strict mode, an `--as-of` that is not timezone-aware or a negative
`--max-age-days` does not stop the run: the sector age gate is skipped with a
sector warning.
Sector and Uptrend share upstream data; Confidence
counts accepted inputs, not independent evidence or verified freshness.

#### Supported legacy sector inputs

An explicit finite non-boolean `sector_score` in [0,100] retains integer
conversion. Otherwise use the existing `dispersion`/`leadership` mapping in
the following order:

| Legacy condition | Score |
|---|---:|
| Dispersion < 0.1 and Technology or Consumer Discretionary leads | 85 |
| Otherwise, dispersion < 0.2 | 65 |
| Otherwise, Utilities, Staples or Healthcare leads | 35 |
| Otherwise | 50 |

Require finite non-boolean dispersion in [0,1] and nonempty string leadership
when those fields are supplied, including alongside an explicit score. Valid
legacy context retains its existing bias/participation behavior. Omitted sector
input stays in `inputs_missing`; a supplied unreadable or unusable sector file
appears in `inputs_unparseable`, with the reason in `input_warnings` and stderr.

### Institutional Score

Net institutional buying/selling trend:

| Flow Direction | Score |
|----------------|-------|
| Strong net buying | 80-100 |
| Mild net buying | 50-79 |
| Neutral / Mixed | 30-49 |
| Net selling | 0-29 |

## Composite Calculation

### Weighted Average

The composite score uses these weights:

| Component | Weight | Rationale |
|-----------|--------|-----------|
| Regime | 25% | Sets the macro baseline |
| Top Risk | 20% | Critical for downside protection |
| Breadth | 15% | Market health indicator |
| Uptrend | 15% | Participation confirmation |
| Institutional | 10% | Smart money signal |
| Sector | 5% | Rotation context |
| Theme | 5% | Thematic momentum |
| FTD | 5% | Rally confirmation (Follow-Through Day quality) |

### Missing Input Handling

When inputs are missing:
1. Exclude missing components from weighted average
2. Reduce confidence level proportionally
3. Apply a 10% haircut per missing critical input (Regime, Top Risk, Breadth)

## Exposure Ceiling Mapping

| Composite Score | Exposure Ceiling |
|-----------------|------------------|
| 80-100 | 90-100% |
| 65-79 | 70-89% |
| 50-64 | 50-69% |
| 35-49 | 30-49% |
| 20-34 | 10-29% |
| 0-19 | 0-9% |

## Recommendation Logic

### NEW_ENTRY_ALLOWED
- Composite score >= 50
- Top risk score >= 40
- No critical inputs missing

### REDUCE_ONLY
- Composite score 30-49, OR
- Top risk score 25-39, OR
- 2+ critical inputs missing

### CASH_PRIORITY
- Composite score < 30, OR
- Top risk score < 25, OR
- Regime = Contraction with top risk score < 50

## Bias Determination

### Growth Bias
- Regime = Broadening or Concentration
- Theme score > 60
- Sector shows technology/growth leadership

### Value Bias
- Regime = Inflationary
- Sector shows financials/energy/materials leadership
- Institutional flow favoring value sectors

### Neutral Bias
- Conflicting signals or transitional regime
- Balanced sector performance

## Participation Assessment

### Broad Participation
- Uptrend score >= 50
- Breadth score >= 50
- Low sector dispersion

### Narrow Participation
- Uptrend score < 50
- Breadth score < 50 OR high sector dispersion
- Few sectors carrying the market

## Confidence Levels

| Condition | Confidence |
|-----------|------------|
| 6+ inputs provided, no conflicts | HIGH |
| 4-5 inputs provided OR minor conflicts | MEDIUM |
| < 4 inputs OR major conflicts | LOW |
