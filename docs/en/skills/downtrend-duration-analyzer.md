---
layout: default
title: "Downtrend Duration Analyzer"
grand_parent: English
parent: Skill Guides
nav_order: 11
lang_peer: /ja/skills/downtrend-duration-analyzer/
permalink: /en/skills/downtrend-duration-analyzer/
---

# Downtrend Duration Analyzer
{: .no_toc }

Analyze historical downtrend durations and generate interactive HTML histograms showing typical correction lengths by sector and market cap.
{: .fs-6 .fw-300 }

<span class="badge badge-free">No API</span>

[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/downtrend-duration-analyzer){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

Analyze historical price data to identify downtrend periods (peak-to-trough) and build statistical distributions of correction durations. Generate interactive HTML visualizations with histograms segmented by sector and market cap to help traders understand typical recovery timeframes and set realistic expectations for mean reversion strategies.

---

## 2. When to Use

- Trader asks about typical correction lengths for a sector or market cap tier
- User wants to understand historical drawdown recovery times
- Building mean reversion or pullback strategies that need realistic holding period estimates
- Comparing correction behavior across different market segments
- Setting stop-loss timeouts or position holding period limits

---

## 3. Prerequisites

- Python 3.9+
- FMP API key (set `FMP_API_KEY` environment variable or use `--api-key`)
- Required packages: `requests`, `pandas`, `numpy` (standard data analysis stack)

---

## 4. Quick Start

```bash
python3 skills/downtrend-duration-analyzer/scripts/analyze_downtrends.py \
  --sector "Technology" \
  --lookback-years 5 \
  --output-dir reports/
```

---

## 5. Workflow

### Step 1: Fetch Historical Price Data

Run the analysis script to fetch OHLC data for a universe of stocks and identify downtrend periods.

```bash
python3 skills/downtrend-duration-analyzer/scripts/analyze_downtrends.py \
  --sector "Technology" \
  --lookback-years 5 \
  --output-dir reports/
```

### Step 2: Analyze Downtrend Durations

The script automatically:
1. Identifies local peaks and troughs using rolling window analysis
2. Calculates duration (trading days) and depth (% decline) for each downtrend
3. Segments results by sector and market cap tier (Mega, Large, Mid, Small)
4. Computes summary statistics (median, mean, percentiles)

### Step 3: Generate Interactive HTML Visualization

```bash
python3 skills/downtrend-duration-analyzer/scripts/generate_histogram_html.py \
  --input reports/downtrend_analysis_*.json \
  --output-dir reports/
```

This creates an interactive HTML file with:
- Histogram of downtrend durations
- Filters for sector and market cap
- Hover tooltips with percentile information
- Summary statistics table

### Step 4: Review Distribution Insights

Load the generated markdown report to interpret the findings:
- **Short corrections (5-15 days)**: Typical pullbacks within uptrends
- **Medium corrections (15-40 days)**: Standard sector rotations
- **Extended corrections (40+ days)**: Trend changes or bear markets

---

## 6. Resources

**References:**

- `skills/downtrend-duration-analyzer/references/downtrend_methodology.md`

**Scripts:**

- `skills/downtrend-duration-analyzer/scripts/analyze_downtrends.py`
- `skills/downtrend-duration-analyzer/scripts/generate_histogram_html.py`
