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
| ftd-detector | `ftd_*.json` | Failure-to-deliver anomalies |
| theme-detector | `theme_*.json` | Active investment themes and rotation |
| sector-analyst | `sector_*.json` | Sector performance rankings |
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
on stderr and excluded as missing; its score and raw context cannot increase
confidence or supply a bias. Legacy inputs without coverage remain supported.

Canonical macro-regime reports must include nested `regime.confidence` and `composite.data_quality` with valid integer component counts. Missing or malformed availability metadata, `very_low` confidence, and zero usable components are treated as missing critical input. They do not contribute a regime score or bias, and the normal missing-input haircut and confidence cap apply. Never override this degradation by manually copying the report's regime label into the exposure decision.

Canonical theme reports use only `themes.all` with valid bullish/bearish heat
in [0,100] and `data_quality` (`ok`/`warning`, string-list flags). Exposure Coach
owns the uncalibrated mapping `round(50 + mean(signed_heat)/2)`, bullish positive
and bearish negative (nearest integer, ties to even). Heat 80 yields 90 bullish
or 10 bearish; equal opposing heat yields 50. Legacy theme fields remain supported.
Missing/invalid rows or quality make the whole theme input unparsable.

Check `inputs_provided`, `inputs_missing`, `inputs_unparseable` and `input_warnings`.
The diagnostic fields appear only when nonempty; ordinary calls retain their existing JSON shape.
A supplied but unusable theme file is excluded, warned on stderr, and listed as
unparsable rather than omitted. Upstream theme quality flags appear in JSON,
Markdown and stderr. Confidence measures input completeness, not freshness,
verified data quality or forecast accuracy; do not manually restore rejected data.

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
