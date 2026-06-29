---
layout: default
title: "Stockbee 20% Study"
grand_parent: English
parent: Skill Guides
nav_order: 52
lang_peer: /ja/skills/stockbee-20pct-study/
permalink: /en/skills/stockbee-20pct-study/
generated: false
---

# Stockbee 20% Study
{: .no_toc }

Build a daily model book of US stocks that moved +20% or -20%, then classify catalyst context, update forward outcomes, and mine recurring patterns without turning the study into an automatic trading signal.
{: .fs-6 .fw-300 }

<span class="badge badge-api">FMP Required</span> <span class="badge badge-optional">Local JSON Optional</span>

[Download Skill Package (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/stockbee-20pct-study.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/stockbee-20pct-study){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

Stockbee 20% Study is a research workflow for studying explosive upside and downside moves. It scans daily OHLCV data for stocks that moved at least 20% over a configurable lookback window, writes durable event records, and later updates the records with forward returns.

Use the output as a model-book and hypothesis-generation artifact:

- Which catalysts repeatedly led to continuation?
- Which moves faded after one or two days?
- Which chart contexts showed strong follow-through?
- Which setups were low-quality speculation or likely split/corporate-action noise?

The skill does not place orders, produce broker instructions, or promote a cohort directly into a trading rule.

---

## 2. When To Use

Use this skill when you want to:

- Run a daily after-close scan for +20% and -20% movers
- Backfill a historical 20% mover database from offline OHLCV files
- Enrich price events with structured catalyst/news records
- Update 1, 3, 5, 10, and 20 day forward outcomes
- Summarize cohorts by direction, catalyst, chart pattern, or close quality
- Export edge hints for later review by research skills

Do not use it as a buy/sell signal service or as a replacement for chart review, liquidity checks, and out-of-sample validation.

---

## 3. Prerequisites

- Python 3.9+
- FMP API key for live universe and historical OHLCV scans
- Optional offline OHLCV JSON through `--prices-json`
- Optional structured catalyst JSON for better event classification
- Recommended state path: `state/stockbee/20pct_study_events.jsonl`

For live FMP mode:

```bash
export FMP_API_KEY=your_api_key_here
```

Offline mode does not require an FMP key.

---

## 4. Quick Start

Daily after-close scan with FMP:

```bash
python3 skills/stockbee-20pct-study/scripts/run_20pct_study.py scan \
  --fmp-universe \
  --max-symbols 300 \
  --as-of 2026-06-28 \
  --lookback-days 5 \
  --min-abs-return-pct 20 \
  --min-price 5 \
  --min-dollar-volume 20000000 \
  --include-down-movers \
  --state-file state/stockbee/20pct_study_events.jsonl \
  --output-dir reports/
```

Offline scan:

```bash
python3 skills/stockbee-20pct-study/scripts/run_20pct_study.py scan \
  --prices-json data/us_daily_ohlcv.json \
  --as-of 2026-06-28 \
  --lookback-days 5 \
  --include-down-movers \
  --state-file state/stockbee/20pct_study_events.jsonl \
  --output-dir reports/
```

---

## 5. Workflow

### Step 1: Scan for 20% movers

The scan step compares the latest eligible close with the close from `--lookback-days` earlier. It records an `UP` event when the return is at or above `--min-abs-return-pct`; it records a `DOWN` event only when `--include-down-movers` is set.

The scanner also records liquidity, volume expansion, close location, 52-week context, prior momentum, extension risk, and data-quality flags.

### Step 2: Enrich catalyst context

If you have structured news or catalyst data, enrich the scanned events:

```bash
python3 skills/stockbee-20pct-study/scripts/run_20pct_study.py enrich \
  --events-json reports/stockbee_20pct_events_YYYY-MM-DD_HHMMSS.json \
  --news-json data/catalysts_YYYY-MM-DD.json \
  --market-regime reports/market_regime_latest.json \
  --state-file state/stockbee/20pct_study_events.jsonl \
  --output-dir reports/
```

Events without a matching catalyst remain marked `NO_CLEAR_NEWS`. This is preferable to inventing a cause after the fact.

### Step 3: Update forward outcomes

Run outcome updates after enough future bars exist:

```bash
python3 skills/stockbee-20pct-study/scripts/run_20pct_study.py update-outcomes \
  --prices-json data/us_daily_ohlcv.json \
  --state-file state/stockbee/20pct_study_events.jsonl \
  --horizons 1,3,5,10,20 \
  --output-dir reports/
```

Each horizon stores close return, MFE, MAE, direction-adjusted return, and an outcome tag such as `STRONG_CONTINUATION`, `FAILED_FADE`, `BREAKDOWN_CONTINUED`, or `REVERSAL_BOUNCE`.

### Step 4: Summarize cohorts

```bash
python3 skills/stockbee-20pct-study/scripts/run_20pct_study.py summarize \
  --state-file state/stockbee/20pct_study_events.jsonl \
  --group-by direction,catalyst.label,technical_context.pattern_label,technical_context.close_quality \
  --min-sample 10 \
  --output-dir reports/
```

The summary produces cohort statistics and `edge_hints` only when a group has enough matured examples. Treat those hints as research prompts, not execution rules.

### Step 5: Backfill historical examples

```bash
python3 skills/stockbee-20pct-study/scripts/run_20pct_study.py backfill \
  --from 2020-01-01 \
  --to 2026-06-28 \
  --prices-json data/us_daily_ohlcv.json \
  --min-abs-return-pct 20 \
  --include-down-movers \
  --state-file state/stockbee/20pct_study_events.jsonl \
  --output-dir reports/
```

Mark current-universe-only backfills as survivorship-biased unless delisted symbols are included.
The CLI adds `CURRENT_UNIVERSE_BACKFILL_SURVIVORSHIP_BIAS` to backfill records by default. Use `--survivorship-complete` only when the OHLCV file includes delisted symbols and historical universe coverage.

---

## 6. Understanding The Output

The skill writes:

- `stockbee_20pct_events_*.json` and `stockbee_20pct_daily_report_*.md`
- `stockbee_20pct_enriched_*.json`
- `stockbee_20pct_outcome_update_*.json/md`
- `stockbee_20pct_cohort_summary_*.json/md`
- `stockbee_20pct_edge_hints_*.yaml`
- `state/stockbee/20pct_study_events.jsonl`

Important fields:

- `direction`: `UP` or `DOWN`
- `price_snapshot.return_pct`: return over the configured window
- `technical_context.pattern_label`: chart-context classification
- `scores.continuation_quality_score`: continuation-study quality, not a buy signal
- `scores.reversal_risk_score`: risk that the move was low quality or likely to fade
- `data_quality.flags`: warnings such as short history or possible split noise
- `outcomes.<horizon>d`: matured or pending forward outcome

---

## 7. Guardrails

- Do not promote a cohort rule from small samples.
- Check representative winner and failure charts manually.
- Separate observation, hypothesis, and executable trade plan.
- Treat low-liquidity, low-float, and capital-structure events cautiously.
- Use offline backfills responsibly; current-universe-only data overstates survivability and should remain separated by `data_quality.flags`.

---

## 8. Resources

- `skills/stockbee-20pct-study/references/methodology.md`
- `skills/stockbee-20pct-study/references/event_schema.md`
- `skills/stockbee-20pct-study/references/catalyst_taxonomy.md`
- `skills/stockbee-20pct-study/references/scoring_system.md`
- `skills/stockbee-20pct-study/references/cohort_mining_rules.md`
- `skills/stockbee-20pct-study/scripts/run_20pct_study.py`
