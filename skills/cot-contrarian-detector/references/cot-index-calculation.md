# COT Index Calculation

## Formula

```
COT Index = (current_net - window_min) / (window_max - window_min) * 100
```

Where `current_net` is the most recent week's large-speculator net position
(non-commercial long minus non-commercial short), and `window_min` /
`window_max` are the minimum and maximum net position observed over the
lookback window (including the current week).

- **100** = current net position is the highest (most net-long) of the
  lookback window
- **0** = current net position is the lowest (most net-short) of the
  lookback window
- **50** = current net position sits at the midpoint of the window's range

This is the standard "Stochastics of positioning" formulation used across COT
index literature (crowdedmarketreport.com, various CFTC-data commentary
sites) — it is mathematically identical to a %K stochastic applied to net
position instead of price.

**Undefined cases:** the index is `None` (not zero, not fifty) when:
- Fewer than `lookback_weeks` of history are available — there is nothing
  meaningful to compare "current" against
- `window_max == window_min` — every week in the window had the *identical*
  net position, so the range is zero and the division is undefined

Both cases are treated identically by `cot_index.compute_cot_index()`: return
`None` rather than raising, so callers can decide how to surface "no data"
(this skill's screener puts such markets in a `skipped` list with a reason,
never silently drops them or reports a misleading 50).

## Lookback Windows

This skill computes two indices per market:

- **Primary: 156 weeks (~3 years), default `--lookback-weeks`.** The
  conventional COT-index lookback — long enough to span multiple full
  positioning cycles (a market can stay "crowded" for months at a time), short
  enough to stay relevant to the current volatility/rate regime. This is the
  index used for the CROWDED_LONG/CROWDED_SHORT classification.
- **Short: 26 weeks (~6 months), default `--short-lookback-weeks`.** Context
  only — shown alongside the 3-year index so the user can tell whether an
  extreme is *fresh* (also extreme on the 26-week window) or *aging* (was
  more extreme weeks ago and has already started to normalize). A market that
  is CROWDED_LONG on both windows is a stronger, more current signal than one
  that is CROWDED_LONG only on the 3-year window because it peaked months ago.

Both lookbacks are CLI flags (`--lookback-weeks`, `--short-lookback-weeks`)
so the user can adjust for a specific market's cycle length if needed.

## Extreme Thresholds

Default thresholds: **high >= 90**, **low <= 10** (`--threshold-high`,
`--threshold-low`). These are inclusive boundaries — a market at exactly 90.0
classifies as `CROWDED_LONG`.

**Sensitivity note:** 90/10 is a conservative, "clearly extreme" threshold
that will flag fewer markets but with higher conviction. Loosening to 80/20
roughly doubles the number of markets flagged in a typical universe scan but
increases false positives — markets that are "elevated" rather than
"crowded." There is no universally correct threshold; 90/10 is the
conventional starting point in COT-index commentary and matches
crowdedmarketreport.com's public framework. Tighten toward 95/5 for
higher-conviction, fewer signals; loosen toward 80/20 for an earlier,
noisier read.

## Open Interest Normalization

`compute_oi_normalized_net()` expresses net position as a fraction of total
open interest (`net_position / openInterestAll`). This exists because raw net
position isn't comparable across markets of very different sizes — a net
position of -50,000 contracts is trivial in a 2,000,000-contract-OI market
(ES) but enormous in a 100,000-contract-OI market. Normalizing by OI gives a
rough cross-market comparability check; it is *not* used in the
CROWDED_LONG/SHORT classification itself (which is purely about the market's
own historical range via the COT Index), but is surfaced in reports as
additional context.

Returns `None` when open interest is zero, missing, or non-numeric — a
division by an unreliable denominator should never silently produce a
misleading ratio.

## Legacy vs. Disaggregated Report

The CFTC publishes COT data in two formats:

- **Legacy report** (used by this skill): three trader categories —
  Non-Commercial (large speculators), Commercial (hedgers), and
  Non-Reportable (small traders below reporting thresholds). This is the
  original, longest-running COT format and matches Shapiro's own framework of
  fading the speculative crowd.
- **Disaggregated report** (not used): splits traders into four finer
  categories (Producer/Merchant, Swap Dealers, Managed Money, Other
  Reportables) for physical-commodity futures only (not financials). More
  granular but not available for financial futures (equity indices, rates,
  FX) and not what Shapiro's methodology is built around.

This skill exclusively uses the legacy report's non-commercial long/short
fields (`noncommPositionsLongAll` / `noncommPositionsShortAll`) as the
"large speculator" proxy across all 65 markets FMP's COT API covers, so the
same methodology applies uniformly to indices, rates, FX, metals, energy,
agri, and crypto futures.

## FMP API Field Glossary

Field names as returned by `stable/commitment-of-traders-report` (verified
live against the FMP API, 2026-07). All fields below are on a single weekly
report row, one row per market per Tuesday-dated report.

| Field | Meaning |
|---|---|
| `date` | Report date, format `"YYYY-MM-DD 00:00:00"`; positions as of the Tuesday of that week |
| `sector` | Market category, e.g. `"INDICES"`, `"CURRENCIES"`, `"METALS"` |
| `name` | Human-readable market name, e.g. `"S&P 500 E-Mini (ES)"` |
| `contractUnits` | Contract size/unit description, e.g. `"($50 X S&P 500 INDEX)"` |
| `openInterestAll` | Total open interest across all trader categories |
| `noncommPositionsLongAll` | Large-speculator ("non-commercial") long contracts — used as the "large speculator" proxy in `compute_net_position()` |
| `noncommPositionsShortAll` | Large-speculator short contracts |
| `noncommPositionsSpreadAll` | Large-speculator spread contracts (not used — spreads are market-neutral by construction) |
| `commPositionsLongAll` / `commPositionsShortAll` | Commercial (hedger) long/short — not used; see "Why speculators, not commercials" in `shapiro-methodology.md` |
| `nonreptPositionsLongAll` / `nonreptPositionsShortAll` | Non-reportable (small trader) long/short — not used |
| `changeInNoncommLongAll` / `changeInNoncommShortAll` | Week-over-week change in speculator long/short (FMP-computed; this skill computes its own week-over-week net change from the raw series instead, via `compute_week_over_week_change()`, to stay self-consistent with the net-position series used everywhere else) |
| `pctOfOiNoncommLongAll` / `pctOfOiNoncommShortAll` | Speculator long/short as % of open interest — surfaced directly in reports as participation context |
| `tradersNoncommLongAll` / `tradersNoncommShortAll` | Number of distinct large-speculator traders holding long/short — surfaced as participation-breadth context (see "Participation and Open Interest Context" in `shapiro-methodology.md`) |
| `concNetLe4TdrLongAll` / `concNetLe4TdrShortAll` | % of net long/short position held by the largest 4 traders — a concentration signal (not currently used in classification, available for future extension) |

## Handling Data Gaps

`sort_dedupe_rows()` sorts rows ascending by `date` and, when two rows share
the same date (observed occasionally with re-published/corrected reports),
keeps the *last* one in the input order — treated as the more recently
fetched/corrected value. Rows missing a `date` are dropped rather than kept
in an arbitrary position, since an undated row can't be placed in the
lookback window correctly.
