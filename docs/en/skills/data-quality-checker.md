---
layout: default
title: "Data Quality Checker"
grand_parent: English
parent: Skill Guides
nav_order: 15
lang_peer: /ja/skills/data-quality-checker/
permalink: /en/skills/data-quality-checker/
---

# Data Quality Checker
{: .no_toc }

Validate data quality in market analysis documents and blog articles before publication. Use when checking for price scale inconsistencies (ETF vs futures), instrument notation errors, date/day-of-week mismatches, allocation total errors, and unit mismatches. Supports English and Japanese content. Advisory mode -- flags issues as warnings for human review, not as blockers.
{: .fs-6 .fw-300 }

<span class="badge badge-free">No API</span>

[Download Skill Package (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/data-quality-checker.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/data-quality-checker){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

Detect common data quality issues in market analysis documents before
publication. The checker validates five categories: price scale consistency,
instrument notation, date/weekday accuracy, allocation totals, and unit usage.
All findings are advisory -- they flag potential issues for human review rather
than blocking publication.

---

## 2. When to Use

- Before publishing a weekly strategy blog or market analysis report
- After generating automated market summaries
- When reviewing translated documents (English/Japanese) for data accuracy
- When combining data from multiple sources (FRED, FMP, FINVIZ) into one report
- As a pre-flight check for any document containing financial data

---

## 3. Prerequisites

- Python 3.9+
- No external API keys required
- No third-party Python packages required (uses only standard library)

---

## 4. Quick Start

```bash
# Check a markdown file
python3 skills/data-quality-checker/scripts/check_data_quality.py \
  --file reports/weekly_strategy.md

# Run specific checks only
python3 skills/data-quality-checker/scripts/check_data_quality.py \
  --file report.md --checks price_scale,dates,allocations

# With reference date for year inference
python3 skills/data-quality-checker/scripts/check_data_quality.py \
  --file report.md --as-of 2026-02-28 --output-dir reports/
```

---

## 5. Workflow

### Step 1: Receive Input Document

Accept the target markdown file path and optional parameters:
- `--file`: Path to the markdown document to validate (required)
- `--checks`: Comma-separated list of checks to run (optional; default: all)
- `--as-of`: Reference date for year inference in YYYY-MM-DD format (optional)
- `--output-dir`: Directory for report output (optional; default: `reports/`)

### Step 2: Execute Validation Script

Run the data quality checker script:

```bash
python3 skills/data-quality-checker/scripts/check_data_quality.py \
  --file path/to/document.md \
  --output-dir reports/
```

To run specific checks only:

```bash
python3 skills/data-quality-checker/scripts/check_data_quality.py \
  --file path/to/document.md \
  --checks price_scale,dates,allocations
```

To provide a reference date for year inference (useful for documents without
explicit year in dates):

```bash
python3 skills/data-quality-checker/scripts/check_data_quality.py \
  --file path/to/document.md \
  --as-of 2026-02-28
```

### Step 3: Load Reference Standards

Read the relevant reference documents to contextualize findings:

- `references/instrument_notation_standard.md` -- Standard ticker notation,
  digit-count hints, and naming conventions for each instrument class
- `references/common_data_errors.md` -- Catalog of frequently observed errors
  including FRED data delays, ETF/futures scale confusion, holiday oversights,
  allocation total pitfalls, and unit confusion patterns

Use these references to explain findings and suggest corrections.

### Step 4: Review Findings

Examine each finding in the output:

- **ERROR** -- High confidence issues (e.g., date-weekday mismatches verified
  by calendar computation). Strongly recommend correction.
- **WARNING** -- Likely issues that need human judgment (e.g., price scale
  anomalies, notation inconsistencies, allocation sums off by more than 0.5%).
- **INFO** -- Informational notes (e.g., mixed bp/% usage that may be
  intentional).

### Step 5: Generate Quality Report

The script produces two output files:

1. **JSON report** (`data_quality_YYYY-MM-DD_HHMMSS.json`): Machine-readable
   list of findings with severity, category, message, line number, and context.
2. **Markdown report** (`data_quality_YYYY-MM-DD_HHMMSS.md`): Human-readable
   report grouped by severity level.

Present the findings to the user with explanations referencing the knowledge
base. Suggest specific corrections for each issue.

---

## 6. Resources

**References:**

- `skills/data-quality-checker/references/common_data_errors.md`
- `skills/data-quality-checker/references/instrument_notation_standard.md`

**Scripts:**

- `skills/data-quality-checker/scripts/check_data_quality.py`
