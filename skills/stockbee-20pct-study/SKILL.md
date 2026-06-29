---
name: stockbee-20pct-study
description: Build and maintain a Stockbee-style daily 20% mover study for US equities by scanning +20%/-20% movers, classifying catalysts and setup context, updating forward outcomes, and summarizing cohort patterns. Use when the user asks to run a daily 20% study, backfill historical 20% movers, find recurring edge patterns, or build a model book of explosive market moves.
---

# Stockbee 20% Study

Build a daily event study of US equities that moved +20% or -20% over a defined window. Convert large movers into structured study records, classify the catalyst and chart context, update forward outcomes, and summarize recurring patterns for research.

This skill is a research, model-book, and setup-fluency workflow. It does not generate buy/sell signals, place orders, or output broker execution instructions.

## When to Use

- User wants to run a Stockbee-style daily 20% mover study
- User asks which stocks moved +20% or -20% today, this week, or over a configurable lookback window
- User wants to backfill historical 20% movers and study what happened next
- User wants to identify continuation, reversal, exhaustion, or theme-cluster patterns
- User wants to build a model book of explosive winners, major failures, and failed low-quality pops
- User wants edge hints for downstream strategy research rather than immediate trade signals

## Prerequisites

- Python 3.9+
- FMP API key for live US universe scans, or offline OHLCV JSON via `--prices-json`
- Optional structured news/catalyst JSON for higher-quality catalyst classification
- Recommended market regime artifact from `market-regime-daily`
- Recommended local state path: `state/stockbee/20pct_study_events.jsonl`

## Workflow

### Step 1: Scan for 20% Movers

Run after the US market close, or against the latest complete daily bar in an offline OHLCV file.

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

Use offline data instead of FMP:

```bash
python3 skills/stockbee-20pct-study/scripts/run_20pct_study.py scan \
  --prices-json data/us_daily_ohlcv.json \
  --as-of 2026-06-28 \
  --lookback-days 5 \
  --include-down-movers \
  --state-file state/stockbee/20pct_study_events.jsonl \
  --output-dir reports/
```

### Step 2: Enrich and Classify Events

Use structured catalyst data when available. The enrichment step is best-effort: if no news record is found, the event remains a price-only `NO_CLEAR_NEWS` study record.

```bash
python3 skills/stockbee-20pct-study/scripts/run_20pct_study.py enrich \
  --events-json reports/stockbee_20pct_events_YYYY-MM-DD_HHMMSS.json \
  --news-json data/catalysts_YYYY-MM-DD.json \
  --market-regime reports/market_regime_latest.json \
  --state-file state/stockbee/20pct_study_events.jsonl \
  --output-dir reports/
```

### Step 3: Update Matured Forward Outcomes

Update 1-day, 3-day, 5-day, 10-day, and 20-day forward outcomes after enough future bars exist.

```bash
python3 skills/stockbee-20pct-study/scripts/run_20pct_study.py update-outcomes \
  --prices-json data/us_daily_ohlcv.json \
  --state-file state/stockbee/20pct_study_events.jsonl \
  --horizons 1,3,5,10,20 \
  --output-dir reports/
```

The update records close return, MFE, MAE, direction-adjusted continuation return, and outcome tags.

### Step 4: Summarize Cohorts

```bash
python3 skills/stockbee-20pct-study/scripts/run_20pct_study.py summarize \
  --state-file state/stockbee/20pct_study_events.jsonl \
  --group-by direction,catalyst.label,technical_context.pattern_label,technical_context.close_quality \
  --min-sample 10 \
  --output-dir reports/
```

Treat `rule_candidates` and exported edge hints as research prompts. Require representative chart review, sample-size thresholds, and out-of-sample validation before changing trade rules.

### Step 5: Historical Backfill

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

Backfill records are marked `CURRENT_UNIVERSE_BACKFILL_SURVIVORSHIP_BIAS` by default. Add `--survivorship-complete` only when the supplied OHLCV includes delisted symbols and historical universe coverage.

## Output Format

- `stockbee_20pct_events_YYYY-MM-DD_HHMMSS.json` — scan metadata and event records
- `stockbee_20pct_daily_report_YYYY-MM-DD_HHMMSS.md` — human-readable daily 20% study report
- `stockbee_20pct_enriched_YYYY-MM-DD_HHMMSS.json` — enriched event records
- `stockbee_20pct_outcome_update_YYYY-MM-DD_HHMMSS.json/md` — matured forward outcome update
- `stockbee_20pct_cohort_summary_YYYY-MM-DD_HHMMSS.json/md` — cohort statistics and rule candidates
- `stockbee_20pct_edge_hints_YYYY-MM-DD_HHMMSS.yaml` — edge-hint export for downstream research skills
- `state/stockbee/20pct_study_events.jsonl` — durable 20% mover model book

## Resources

- `references/methodology.md` — 20% study methodology and review checklist
- `references/event_schema.md` — JSONL event record schema
- `references/catalyst_taxonomy.md` — catalyst and risk label definitions
- `references/scoring_system.md` — event quality and study priority scoring
- `references/cohort_mining_rules.md` — overfitting controls and sample-size rules
- `scripts/run_20pct_study.py` — CLI for scan, enrich, update-outcomes, summarize, and backfill
