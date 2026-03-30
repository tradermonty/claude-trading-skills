---
name: downtrend-duration-analyzer
description: Analyze historical downtrend durations and generate interactive HTML histograms showing typical correction lengths by sector and market cap.
---

# Downtrend Duration Analyzer

## Overview

Analyze historical price data to identify downtrend periods (peak-to-trough) and build statistical distributions of correction durations. Generate interactive HTML visualizations with histograms segmented by sector and market cap to help traders understand typical recovery timeframes and set realistic expectations for mean reversion strategies.

## When to Use

- Trader asks about typical correction lengths for a sector or market cap tier
- User wants to understand historical drawdown recovery times
- Building mean reversion or pullback strategies that need realistic holding period estimates
- Comparing correction behavior across different market segments
- Setting stop-loss timeouts or position holding period limits

## Prerequisites

- Python 3.9+
- FMP API key (set `FMP_API_KEY` environment variable or use `--api-key`)
- Required packages: `requests`, `pandas`, `numpy` (standard data analysis stack)

## Workflow

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

## Output Format

### JSON Report

```json
{
  "schema_version": "1.0",
  "analysis_date": "2026-03-28T07:00:00Z",
  "parameters": {
    "lookback_years": 5,
    "sector_filter": "Technology",
    "peak_window": 20,
    "trough_window": 20
  },
  "summary": {
    "total_downtrends": 1234,
    "median_duration_days": 18,
    "mean_duration_days": 24.5,
    "p25_duration_days": 10,
    "p75_duration_days": 32,
    "p90_duration_days": 55
  },
  "by_sector": {
    "Technology": {
      "count": 456,
      "median_days": 15,
      "mean_days": 20.3
    }
  },
  "by_market_cap": {
    "Mega": {"count": 200, "median_days": 12},
    "Large": {"count": 300, "median_days": 16},
    "Mid": {"count": 400, "median_days": 22},
    "Small": {"count": 334, "median_days": 28}
  },
  "downtrends": [
    {
      "symbol": "AAPL",
      "sector": "Technology",
      "market_cap_tier": "Mega",
      "peak_date": "2025-01-15",
      "trough_date": "2025-02-10",
      "duration_days": 18,
      "depth_pct": -12.5
    }
  ]
}
```

### Markdown Report

```markdown
# Downtrend Duration Analysis

**Date**: 2026-03-28
**Lookback**: 5 years
**Sector**: Technology

## Summary Statistics

| Metric | Value |
|--------|-------|
| Total Downtrends | 1,234 |
| Median Duration | 18 days |
| Mean Duration | 24.5 days |
| 25th Percentile | 10 days |
| 75th Percentile | 32 days |
| 90th Percentile | 55 days |

## By Market Cap Tier

| Tier | Count | Median | Mean |
|------|-------|--------|------|
| Mega ($200B+) | 200 | 12 days | 15.2 days |
| Large ($10-200B) | 300 | 16 days | 20.1 days |
| Mid ($2-10B) | 400 | 22 days | 28.4 days |
| Small (<$2B) | 334 | 28 days | 35.6 days |

## Key Insights

1. Larger companies recover faster from corrections
2. Technology sector shows shorter median correction than market average
3. 90% of corrections resolve within 55 trading days
```

### HTML Visualization

Interactive histogram saved to `reports/downtrend_histogram_YYYY-MM-DD.html` with:
- Plotly.js-based interactive charts
- Sector and market cap dropdown filters
- Duration distribution with bin controls
- Percentile markers (P25, P50, P75, P90)

Reports are saved to `reports/` with filenames:
- `downtrend_analysis_YYYY-MM-DD_HHMMSS.json`
- `downtrend_analysis_YYYY-MM-DD_HHMMSS.md`
- `downtrend_histogram_YYYY-MM-DD_HHMMSS.html`

## Resources

- `scripts/analyze_downtrends.py` -- Main analysis script for fetching data and computing downtrend durations
- `scripts/generate_histogram_html.py` -- HTML visualization generator with interactive histograms
- `references/downtrend_methodology.md` -- Peak/trough detection algorithms and market cap tier definitions

## Key Principles

1. **Statistical Rigor**: Use robust peak/trough detection to avoid noise-induced false signals
2. **Segmentation Matters**: Always analyze by sector and market cap; averages hide important differences
3. **Realistic Expectations**: Use percentiles (not just means) to understand the full distribution of outcomes
