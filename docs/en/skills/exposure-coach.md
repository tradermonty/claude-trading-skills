---
layout: default
title: "Exposure Coach"
grand_parent: English
parent: Skill Guides
nav_order: 11
lang_peer: /ja/skills/exposure-coach/
permalink: /en/skills/exposure-coach/
---

# Exposure Coach
{: .no_toc }

Generate a one-page Market Posture summary with net exposure ceiling, growth-vs-value bias, participation breadth, and new-entry-allowed vs cash-priority recommendation by integrating signals from breadth, regime, and flow analysis skills.
{: .fs-6 .fw-300 }

<span class="badge badge-optional">FMP Optional</span>

[Download Skill Package (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/exposure-coach.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/exposure-coach){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

Exposure Coach synthesizes outputs from market-breadth-analyzer, uptrend-analyzer, macro-regime-detector, market-top-detector, ftd-detector, theme-detector, sector-analyst, and institutional-flow-tracker into a unified control-plane decision. The skill answers the solo trader's core question: "How much capital should I commit to equities right now?" before any individual stock analysis begins.

---

## 2. When to Use

- Before initiating any new stock positions to determine appropriate capital commitment
- At the start of each trading week to calibrate portfolio exposure
- When multiple market signals conflict and a unified posture is needed
- After significant macro or market events to reassess exposure ceiling
- When transitioning between market regimes (broadening, concentration, contraction)

---

## 3. Prerequisites

- Python 3.9+
- FMP API key (set `FMP_API_KEY` environment variable) for institutional-flow-tracker data
- Input JSON files from upstream skills (see Workflow Step 1)
- Standard library + `argparse`, `json`, `datetime`

---

## 4. Quick Start

```bash
python3 skills/exposure-coach/scripts/calculate_exposure.py \
  --breadth reports/breadth_latest.json \
  --uptrend reports/uptrend_latest.json \
  --regime reports/regime_latest.json \
  --top-risk reports/top_risk_latest.json \
  --ftd reports/ftd_latest.json \
  --theme reports/theme_latest.json \
  --sector reports/sector_latest.json \
  --institutional reports/institutional_latest.json \
  --output-dir reports/
```

---

## 5. Workflow

### Step 1: Gather Upstream Skill Outputs

Collect the most recent JSON outputs from integrated skills. Each file provides a specific signal dimension:

| Skill | Output File Pattern | Signal Provided |
|-------|---------------------|-----------------|
| market-breadth-analyzer | `breadth_*.json` | Advance/decline ratios, new highs/lows |
| uptrend-analyzer | `uptrend_*.json` | Uptrend participation percentage |
| macro-regime-detector | `regime_*.json` | Current regime (Concentration, Broadening, etc.) |
| market-top-detector | `top_risk_*.json` | Distribution day count, top probability score |
| ftd-detector | `ftd_*.json` | Follow-Through Day quality (market bottom confirmation) |
| theme-detector | `theme_*.json` | Active investment themes and rotation |
| sector-analyst | `sector_rotation_*.json` | Sector uptrend ratios and trend direction |
| institutional-flow-tracker | `institutional_*.json` | Net institutional buying/selling |

### Step 2: Run Exposure Scoring Engine

Execute the exposure scoring script with paths to upstream outputs:

```bash
python3 skills/exposure-coach/scripts/calculate_exposure.py \
  --breadth reports/breadth_latest.json \
  --uptrend reports/uptrend_latest.json \
  --regime reports/regime_latest.json \
  --top-risk reports/top_risk_latest.json \
  --ftd reports/ftd_latest.json \
  --theme reports/theme_latest.json \
  --sector reports/sector_latest.json \
  --institutional reports/institutional_latest.json \
  --output-dir reports/
```

The script accepts partial inputs; missing files reduce confidence but do not block execution.

If an input declares `evaluation_coverage`, only valid schema 1.0 with
`verdict: complete` is used. Partial, unavailable or malformed coverage is warned
on stderr and excluded from scoring; its score and raw context cannot increase
confidence or supply a bias. Legacy inputs without coverage remain supported.

Canonical macro-regime reports must include nested `regime.confidence` and `composite.data_quality` with valid integer component counts. Missing or malformed availability metadata, `very_low` confidence, and zero usable components are treated as missing critical input. They do not contribute a regime score or bias, and the normal missing-input haircut and confidence cap apply. Never override this degradation by manually copying the report's regime label into the exposure decision.

Canonical theme reports use only `themes.all` with valid bullish/bearish heat
in [0,100] and `data_quality` (`ok`/`warning`, string-list flags). Exposure Coach
owns the uncalibrated mapping `round(50 + mean(signed_heat)/2)`, bullish positive
and bearish negative (nearest integer, ties to even). Heat 80 yields 90 bullish
or 10 bearish; equal opposing heat yields 50. Legacy theme fields remain supported.
Missing/invalid rows or quality make the whole theme input unparsable.

#### Sector Analyst input

Generate `sector_rotation_*.json` with
`python3 skills/sector-analyst/scripts/analyze_sector_rotation.py --json --save`
and pass the printed JSON path unchanged to `--sector`.

Canonical input requires all 11 known sectors exactly once in `ranking`.
Each row must have a finite non-boolean `ratio` in [0,1], a `slope` that is null
or in [-1,1], and a string trend label. A null slope, or a label that disagrees
with the slope sign, is accepted with a warning and no trend adjustment. Both
`trends` counts and sector
lists must agree with the rows. `meta` must be an object; missing/null freshness
is allowed with a warning, while malformed freshness metadata is rejected.
Missing, invalid or inconsistent required data excludes the whole input;
inserting a legacy score cannot bypass validation.

The consumer-owned `sector_uptrend_health_v1` heuristic uses Uptrend Analyzer's
absolute ratio bands (boundaries 0.097, 0.25, 0.37 and 0.50). It adds +5 for Up
with positive slope, -5 for Down with negative slope and 0 otherwise, clamps each
unrounded sector value to [0,100],
averages all 11 equally, and rounds only the final mean (nearest integer, ties
to even). It neither copies the relative rotation `groups.score` nor rewards
low ratio dispersion. This is an uncalibrated equal-sector measure; see the
[Sector Score reference](https://github.com/tradermonty/claude-trading-skills/blob/main/skills/exposure-coach/references/exposure_framework.md#sector-score)
for exact formulas and required fields.

Canonical sector data contributes to the composite score only. Bias and
participation use other accepted inputs; canonical ratio spread is not treated
as legacy dispersion. Supported legacy `sector_score` or
`dispersion`/`leadership` inputs retain their scoring and validated context rules.

Inspect `sector_integration` for the mapping version, per-sector values and
`source_freshness`. Stale/unknown freshness and producer warnings are preserved
in JSON, Markdown and stderr. Without `--as-of`, they do not exclude otherwise
usable sector data.
Even `is_fresh: true` is only a producer statement. Without `--as-of`,
`freshness_verified` remains false and current age is not rechecked.
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
Sector and Uptrend share upstream data, so an
additional accepted input is not an independent confirmation.

Check `inputs_provided`, `inputs_missing`, `inputs_unparseable` and `input_warnings`.
The diagnostic fields appear only when nonempty; ordinary calls retain their existing JSON shape.
A supplied but unusable theme or sector file is excluded, warned on stderr, and
listed as unparsable rather than omitted. Upstream quality flags appear in JSON,
Markdown and stderr. Confidence measures input completeness, not freshness,
verified data quality, independent evidence or forecast accuracy; do not manually
restore rejected data.

### Step 3: Interpret the Market Posture Summary

Review the generated posture report containing:

1. **Exposure Ceiling** -- Maximum recommended equity allocation (0-100%)
2. **Bias Direction** -- Growth vs Value tilt based on regime and flow
3. **Participation Assessment** -- Broad (healthy) vs Narrow (fragile) market
4. **Action Recommendation** -- NEW_ENTRY_ALLOWED, REDUCE_ONLY, or CASH_PRIORITY
5. **Confidence Level** -- HIGH, MEDIUM, or LOW based on input completeness

### Step 4: Apply Exposure Guidance

Map the posture recommendation to portfolio actions:

| Recommendation | Action |
|----------------|--------|
| NEW_ENTRY_ALLOWED | Proceed with stock-level analysis and new positions |
| REDUCE_ONLY | No new entries; trim existing positions on strength |
| CASH_PRIORITY | Raise cash aggressively; avoid all new commitments |

---

## 6. Resources

**References:**

- `skills/exposure-coach/references/exposure_framework.md`
- `skills/exposure-coach/references/regime_exposure_map.md`

**Scripts:**

- `skills/exposure-coach/scripts/calculate_exposure.py`
- `skills/exposure-coach/scripts/sector_contract.py`

## Strict provenance for market-regime-daily

Add `--require-provenance --run-id daily-20261017-unique
--as-of 2026-10-17T13:00:00Z --max-age-days 3` to validate breadth and uptrend
before scoring. Both producers must receive the same unique run ID; pass their
exact printed JSON paths. `--as-of` is the timezone-aware evaluation instant,
not an override of the source business date.

The gate checks schema 1.0, expected run ID, UTC retrieval no later than evaluation,
nonfuture source date and configured age. Default three calendar days is a
conservative policy, not an exchange holiday calendar. Failure stops before
report output. Successful output records accepted lineage and verification limits.
Optional top-risk/other inputs and auxiliary summary dates remain outside this
gate; unknown quality flags stay false. Legacy mode retains its existing schema.
Run IDs are consistency markers, not authenticity or point-in-time proof.
