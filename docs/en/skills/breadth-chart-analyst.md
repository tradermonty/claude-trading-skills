---
layout: default
title: "Breadth Chart Analyst"
grand_parent: English
parent: Skill Guides
nav_order: 11
lang_peer: /ja/skills/breadth-chart-analyst/
permalink: /en/skills/breadth-chart-analyst/
---

# Breadth Chart Analyst
{: .no_toc }

Analyze market breadth using the S&P 500 Breadth Index (200-Day MA based) and the US Stock Market Uptrend Stock Ratio. Works in two modes: **CSV data mode** (no chart images needed -- fetches live data from public sources) and **chart image mode** (visual analysis with two-stage right-edge extraction). Provides medium-term strategic and short-term tactical market outlook with backtested positioning signals. All output in English.
{: .fs-6 .fw-300 }

<span class="badge badge-free">No API</span>

[Download Skill Package (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/breadth-chart-analyst.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/breadth-chart-analyst){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

This skill enables specialized analysis of two complementary market breadth indicators that provide strategic (medium to long-term) and tactical (short-term) market perspectives.

**Two operating modes:**

| Mode | Input | Data Source | Best For |
|------|-------|-------------|----------|
| **CSV Data** (primary) | No images needed | Public CSV from GitHub Pages | Quick numerical analysis, automation |
| **Chart Image** (supplementary) | User-provided screenshots | Visual analysis + CSV cross-check | Historical pattern context, visual confirmation |

CSV data is always the **PRIMARY** source for numerical values. Chart images provide supplementary visual context and historical pattern recognition.

---

## 2. When to Use

- User requests market breadth assessment or market health evaluation
- User asks about medium-term strategic positioning based on breadth indicators
- User needs short-term tactical timing signals for swing trading
- User wants combined strategic and tactical market outlook
- **User requests breadth analysis without providing chart images** (CSV data mode)
- User provides breadth chart images for visual analysis

Do NOT use this skill when:
- User asks about individual stock analysis (use `us-stock-analysis` skill instead)
- User needs sector rotation analysis without breadth charts (use `sector-analyst` skill instead)
- User wants news-based market analysis (use `market-news-analyst` skill instead)

---

## 3. Prerequisites

- **Chart Images Optional**: CSV data from public sources is the PRIMARY data source; chart images provide supplementary visual context
- **No API Keys Required**: CSV data is fetched from public GitHub Pages; no subscriptions needed
- **Python 3.9+**: For running the CSV fetch script (stdlib only -- no pip installs)
- **Language**: All analysis and output conducted in English

---

## 4. Quick Start

```bash
# Fetch latest breadth data (no chart images needed)
python3 skills/breadth-chart-analyst/scripts/fetch_breadth_csv.py

# JSON output for programmatic use
python3 skills/breadth-chart-analyst/scripts/fetch_breadth_csv.py --json
```

**Sample output:**
```
============================================================
Breadth Data (CSV) - 2026-03-13
============================================================
--- Market Breadth (S&P 500) ---
200-Day MA: 62.13% (healthy (>=60%))
8-Day MA:   55.05% (neutral (40-60%))
8MA vs 200MA: -7.08pt (8MA BELOW -- DEAD CROSS)
Trend: -1
--- Uptrend Ratio (All Markets) ---
Current: 12.55% RED (bearish)
10MA: 15.67%, Slope: -0.0157, Trend: DOWN
--- Sector Summary ---
Overbought: Energy (50.3%)
Oversold: Industrials (8.4%), Communication Services (5.8%), ...
============================================================
```

---

## 5. Workflow

### Step 0: Fetch CSV Data (PRIMARY SOURCE -- MANDATORY)

CSV data is the PRIMARY source for all breadth values. This step MUST be executed BEFORE any image analysis.

```bash
python3 skills/breadth-chart-analyst/scripts/fetch_breadth_csv.py
```

**Data Sources:**

| Source | URL | Provides |
|--------|-----|----------|
| Market Breadth | `sydcurie.github.io/.../market_breadth_data.csv` | 200-Day MA, 8-Day MA, Trend, Dead Cross |
| Uptrend Ratio | `github.com/sydcurie/uptrend-dashboard/.../uptrend_ratio_timeseries.csv` | Ratio, 10MA, slope, trend, color |
| Sector Summary | `github.com/sydcurie/uptrend-dashboard/.../sector_summary.csv` | Per-sector ratio, trend, status |

**Data Source Priority:**

| Priority | Source | Reliability |
|----------|--------|-------------|
| 1 (PRIMARY) | **CSV Data** | HIGH |
| 2 (SUPPLEMENTARY) | Chart Image | MEDIUM |
| 3 (DEPRECATED) | ~~OpenCV scripts~~ | UNRELIABLE |

If no chart images are provided, skip Steps 1 and 1.5 and proceed directly to analysis using CSV data.

### Step 1: Receive Chart Images (if provided)

When the user provides breadth chart images:

1. Confirm receipt of chart image(s)
2. Identify which chart(s) are provided (Chart 1: 200MA Breadth, Chart 2: Uptrend Ratio, or both)
3. Proceed to Step 1.5 for two-stage chart analysis

### Step 1.5: Two-Stage Chart Analysis (when charts provided)

Use a **two-stage approach** to prevent misreading historical data as current values:

**Stage 1: Full Chart** -- analyze for historical context, past troughs/peaks, cycles

**Stage 2: Right Edge** -- extract and analyze the rightmost 25% for current values:

```bash
python3 skills/breadth-chart-analyst/scripts/extract_chart_right_edge.py <image_path> --percent 25
```

If Stage 1 and Stage 2 values differ, **Stage 2 takes precedence**. Always cross-check against CSV data from Step 0.

### Step 2: Load Methodology

```
Read: references/breadth_chart_methodology.md
```

### Step 3: Analyze Chart 1 (200MA-Based Breadth Index)

#### Key readings to extract:
- **8MA level** (orange line) and **200MA level** (green line)
- Slopes, distance from 73% and 23% thresholds
- Signal markers: 8MA troughs (purple ▼), 200MA peaks (red ▲)

#### Critical: Line Color Verification
- **8MA = ORANGE** (fast-moving, more volatile)
- **200MA = GREEN** (slow-moving, smoother)

#### BUY Signal (ALL criteria must be met):
1. 8MA formed a clear trough (purple ▼)
2. 8MA has begun to move upward from the trough
3. 8MA has risen for 2-3 CONSECUTIVE periods
4. 8MA is CURRENTLY rising (not falling)
5. 8MA has maintained the upward trajectory

**Signal Status**: CONFIRMED / DEVELOPING / FAILED / NO SIGNAL

#### SELL Signal:
- 200MA formed a peak (red ▲) near or above 73%

#### Death Cross / Golden Cross Detection:
- 8MA below 200MA and converging = **Death Cross** (bearish)
- 8MA below 200MA and diverging upward = **Golden Cross** (bullish)

### Step 4: Analyze Chart 2 (Uptrend Stock Ratio)

#### Key readings:
- Current ratio, color (GREEN/RED), slope
- Distance from 10% (oversold) and 40% (overbought) thresholds
- Recent color transitions (red-to-green = BUY, green-to-red = SELL)

### Step 5: Combined Analysis

When both data sets are available, classify into one of four scenarios:

| Scenario | Strategic (Chart 1) | Tactical (Chart 2) | Implication |
|----------|-------------------|-------------------|-------------|
| Both Bullish | 8MA rising | GREEN, rising | Maximum bullish |
| Strategic Bull / Tactical Bear | 8MA rising | RED, falling | Hold core, wait for entry |
| Strategic Bear / Tactical Bull | 200MA peaked | GREEN, rising | Tactical trades only |
| Both Bearish | Both MAs declining | RED, falling | Defensive positioning |

### Step 6: Generate Report

Save to `reports/` directory:
- `breadth_200ma_analysis_[YYYY-MM-DD].md`
- `uptrend_ratio_analysis_[YYYY-MM-DD].md`
- `breadth_combined_analysis_[YYYY-MM-DD].md`

### Step 7: Quality Assurance

Key verification points:
1. All output in English
2. Line colors verified (8MA=ORANGE, 200MA=GREEN)
3. Trend direction reflects RIGHTMOST data points, not historical
4. Death/Golden cross status explicitly stated
5. Signal status clearly identified
6. Scenario probabilities sum to 100%
7. Actionable positioning for each trader type

---

## 6. Resources

**References:**

- `skills/breadth-chart-analyst/references/breadth_chart_methodology.md`

**Scripts:**

- `skills/breadth-chart-analyst/scripts/fetch_breadth_csv.py` -- PRIMARY data source (stdlib only)
- `skills/breadth-chart-analyst/scripts/extract_chart_right_edge.py` -- Chart right-edge extractor (PIL)
- `skills/breadth-chart-analyst/scripts/detect_uptrend_ratio.py` -- OpenCV uptrend detection (DEPRECATED)
- `skills/breadth-chart-analyst/scripts/detect_breadth_values.py` -- OpenCV breadth detection (DEPRECATED)
