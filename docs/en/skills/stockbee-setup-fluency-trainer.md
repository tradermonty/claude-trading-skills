---
layout: default
title: "Stockbee Setup Fluency Trainer"
grand_parent: English
parent: Skill Guides
nav_order: 57
lang_peer: /ja/skills/stockbee-setup-fluency-trainer/
permalink: /en/skills/stockbee-setup-fluency-trainer/
generated: true
---

# Stockbee Setup Fluency Trainer
{: .no_toc }

Build a Stockbee-style setup model book from momentum-burst screener candidates, then update 3-day and 5-day forward outcomes with MFE/MAE, stop-hit status, outcome tags, and cohort statistics. Use when the user wants to study Stockbee Momentum Burst examples, track failed candidates, build setup fluency, review A/B setup quality, or convert screener outputs into a learning loop rather than immediate trade signals.
{: .fs-6 .fw-300 }

<span class="badge badge-free">No API</span> <span class="badge badge-optional">FMP Optional</span>

[Download Skill Package (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/stockbee-setup-fluency-trainer.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/stockbee-setup-fluency-trainer){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

# Stockbee Setup Fluency Trainer

---

## 2. When to Use

- User wants to study Stockbee Momentum Burst setups systematically
- User asks to build a model book from `stockbee-momentum-burst-screener` output
- User wants to review failed candidates, missed trades, or A/B setup quality
- User wants 3-day / 5-day forward returns, MFE, MAE, and stop-hit outcomes
- User wants to improve setup recognition before increasing position size
- User asks which Stockbee tags should be promoted, downgraded, or filtered

---

## 3. Prerequisites

- Python 3.10+
- A `stockbee-momentum-burst-screener` JSON report, or compatible candidate JSON
- Optional: FMP API key for outcome updates when offline OHLCV JSON is not supplied
- Recommended local state path: `state/stockbee/model_book.jsonl`

---

## 4. Quick Start

```bash
python3 skills/stockbee-setup-fluency-trainer/scripts/build_model_book.py ingest \
  --screener-json reports/stockbee_momentum_burst_YYYY-MM-DD_HHMMSS.json \
  --model-book state/stockbee/model_book.jsonl \
  --output-dir reports/
```

---

## 5. Workflow

### Step 1: Ingest Momentum Burst Candidates

Run after the Stockbee Momentum Burst screener has produced a JSON report.

```bash
python3 skills/stockbee-setup-fluency-trainer/scripts/build_model_book.py ingest \
  --screener-json reports/stockbee_momentum_burst_YYYY-MM-DD_HHMMSS.json \
  --model-book state/stockbee/model_book.jsonl \
  --output-dir reports/
```

Use `--include-rejects` when intentionally building a negative-example set. Otherwise rejected candidates are skipped.

### Step 2: Update 3-Day and 5-Day Outcomes

Use FMP:

```bash
python3 skills/stockbee-setup-fluency-trainer/scripts/build_model_book.py update \
  --model-book state/stockbee/model_book.jsonl \
  --horizons 3,5 \
  --output-dir reports/
```

Use offline OHLCV JSON:

```bash
python3 skills/stockbee-setup-fluency-trainer/scripts/build_model_book.py update \
  --model-book state/stockbee/model_book.jsonl \
  --prices-json data/daily_ohlcv.json \
  --horizons 3,5 \
  --output-dir reports/
```

The update step records:

- Forward close return for each horizon
- MFE and MAE over each horizon
- Stop-hit status and first stop-hit date
- Outcome tags such as `STRONG_WINNER`, `WORKED`, `FAILED_STOP`, `FAILED_FADE`, `CHOPPY_FAILURE`, or `NEUTRAL`

### Step 3: Summarize Cohorts

```bash
python3 skills/stockbee-setup-fluency-trainer/scripts/build_model_book.py summarize \
  --model-book state/stockbee/model_book.jsonl \
  --group-by rating,primary_trigger,setup_tags \
  --min-sample 5 \
  --output-dir reports/
```

Review the generated Markdown and JSON reports. Treat `rule_candidates` as evidence prompts, not automatic rule changes.

### Step 4: Convert Evidence Into Practice

For cohorts with enough examples:

- Promote tags with high win rate, positive 5-day expectancy, and acceptable average MAE
- Downgrade or filter tags with weak 5-day expectancy, frequent stop hits, or repeated fade failures
- Inspect representative charts manually before changing trade rules
- Log accepted lessons in `trader-memory-core` or the monthly review process

---

## 6. Resources

**References:**

- `skills/stockbee-setup-fluency-trainer/references/model_book_schema.md`
- `skills/stockbee-setup-fluency-trainer/references/outcome_tags.md`
- `skills/stockbee-setup-fluency-trainer/references/review_workflow.md`

**Scripts:**

- `skills/stockbee-setup-fluency-trainer/scripts/build_model_book.py`
