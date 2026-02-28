---
name: data-quality-checker
description: Validate data quality in market analysis documents and blog articles before publication. Use when checking for price scale inconsistencies (ETF vs futures), instrument notation errors, date/day-of-week mismatches, allocation total errors, and unit mismatches. Supports English and Japanese content. Advisory mode -- flags issues as warnings for human review, not as blockers.
---

## Overview

Detect common data quality issues in market analysis documents before
publication. The checker validates five categories: price scale consistency,
instrument notation, date/weekday accuracy, allocation totals, and unit usage.
All findings are advisory -- they flag potential issues for human review rather
than blocking publication.

## When to Use

- Before publishing a weekly strategy blog or market analysis report
- After generating automated market summaries
- When reviewing translated documents (English/Japanese) for data accuracy
- When combining data from multiple sources (FRED, FMP, FINVIZ) into one report
- As a pre-flight check for any document containing financial data

## Prerequisites

- Python 3.9+
- No external API keys required
- No third-party Python packages required (uses only standard library)

## Workflow

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

## Output Format

### JSON Finding Structure

```json
{
  "severity": "WARNING",
  "category": "price_scale",
  "message": "GLD: $2,800 has 4 digits (expected 2-3 digits)",
  "line_number": 5,
  "context": "GLD: $2,800"
}
```

### Markdown Report Structure

```markdown
# Data Quality Report
**Source:** path/to/document.md
**Generated:** 2026-02-28 14:30:00
**Total findings:** 3

## ERROR (1)
- **[dates]** (line 12): Date-weekday mismatch: January 1, 2026 (Monday) -- actual weekday is Thursday

## WARNING (2)
- **[price_scale]** (line 5): GLD: $2,800 has 4 digits (expected 2-3 digits)
  > `GLD: $2,800`
- **[allocations]**: Allocation total: 110.0% (expected ~100%)
```

## Resources

- `scripts/check_data_quality.py` -- Main validation script
- `references/instrument_notation_standard.md` -- Notation and price scale reference
- `references/common_data_errors.md` -- Common error patterns and prevention

## Key Principles

1. **Advisory mode**: All findings are warnings for human review. The script
   always exits with code 0 on successful execution, even when findings are
   present. Exit code 1 is reserved for script failures (file not found, parse
   errors).

2. **Section-aware allocation checking**: Only percentages within allocation
   sections (identified by headings like "配分", "Allocation", or table columns
   like "ウェイト", "目安比率") are checked. Random percentages in body text
   (probability, RSI, YoY growth) are ignored.

3. **Bilingual support**: Handles both English and Japanese date formats,
   weekday names, and section headings. Full-width characters (％, 〜, en-dash)
   are normalized before processing.

4. **Year inference**: For dates without an explicit year, the checker infers
   the year using (in priority order): the `--as-of` option, a YYYY pattern
   found in the document title/metadata, or the current year with a 6-month
   cross-year heuristic.

5. **Digit-count heuristic**: Price scale validation uses digit counts (number
   of digits before the decimal point) rather than absolute price ranges. This
   approach is resilient to price changes over time while still catching
   ETF/futures confusion errors.
