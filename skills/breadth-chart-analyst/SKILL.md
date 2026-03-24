---
name: breadth-chart-analyst
description: "Use when the user asks to analyze market breadth charts (S&P 500 Breadth Index 200-Day MA, US Stock Market Uptrend Stock Ratio), calculate breadth ratios from CSV data, identify bullish/bearish divergences between 8MA and 200MA, detect buy/sell signals at key thresholds (23% oversold, 73% overbought), compare current readings to historical patterns, determine swing-trade entry/exit timing from uptrend ratio color transitions, or generate combined strategic and tactical positioning reports. Triggers on terms like 'market breadth', 'breadth chart', 'S&P 500 breadth', '200-Day MA', 'uptrend ratio', 'breadth indicators', 'market health', 'positioning strategy'. Works with or without chart images by fetching CSV data from public sources."
---

# Breadth Chart Analyst

## Overview

Analyze two complementary market breadth charts — strategic (Chart 1: 200MA Breadth) and tactical (Chart 2: Uptrend Ratio) — to identify trading signals, assess market health, and generate positioning recommendations. CSV data is the primary source; chart images are supplementary.

## When to Use

- User provides S&P 500 Breadth Index or Uptrend Stock Ratio charts
- User requests market breadth assessment or market health evaluation
- User asks about medium/long-term strategic or short-term tactical positioning
- User requests breadth analysis without chart images (CSV data mode)

**Do NOT use** for individual stocks (`us-stock-analysis`), sector rotation (`sector-analyst`), or news analysis (`market-news-analyst`).

## Prerequisites

- **No API Keys Required**: CSV fetched from public GitHub Pages
- **Chart images optional**: CSV is primary; images are supplementary context

## Output

This skill generates markdown analysis reports saved to the `reports/` directory:
- Chart 1 only: `breadth_200ma_analysis_[YYYY-MM-DD].md`
- Chart 2 only: `uptrend_ratio_analysis_[YYYY-MM-DD].md`
- Both charts: `breadth_combined_analysis_[YYYY-MM-DD].md`

Reports include executive summaries, current readings, signal identification, scenario analysis with probabilities, and actionable positioning recommendations for different trader types.

## Core Principles

1. **Dual-Timeframe Analysis**: Combine strategic (Chart 1) and tactical (Chart 2) perspectives
2. **Backtested Strategy Focus**: Apply proven systematic strategies from historical patterns
3. **Objective Signal Identification**: Use clearly defined thresholds and transitions
4. **Actionable Recommendations**: Provide specific positioning guidance per investor type
5. **All output in English**

## Chart Types and Purposes

### Chart 1: S&P 500 Breadth Index (200-Day MA Based)

**Purpose**: Medium to long-term strategic market positioning

**Key Elements**:
- **8-Day MA (Orange Line)**: Short-term breadth trend, primary entry signal generator
- **200-Day MA (Green Line)**: Long-term breadth trend, primary exit signal generator
- **Red Dashed Line (73%)**: Average peak level - market overheating threshold
- **Blue Dashed Line (23%)**: Average 8MA trough level - extreme oversold, excellent buying opportunity
- **Triangles**:
  - Purple ▼ = 8MA troughs (buy signal when reverses)
  - Blue ▼ = 200MA troughs (major cycle lows)
  - Red ▲ = 200MA peaks (sell signal)
- **Pink Background**: Downtrend periods

**Backtested Strategy**:
- **BUY**: When 8MA reverses from a trough (especially below 23%)
- **SELL**: When 200MA forms a peak (typically near/above 73%)
- **Result**: Historically high performance, avoids bear markets

### Chart 2: US Stock Market - Uptrend Stock Ratio

**Purpose**: Short-term tactical timing and swing trading

**Key Elements**:
- **Uptrend Stock Definition**: Stocks above 200MA/50MA/20MA with positive 1-month performance
- **Green Regions**: Market in uptrend phase
- **Red Regions**: Market in downtrend phase
- **~10% Level (Lower Orange Dashed)**: Short-term bottom, extreme oversold
- **~40% Level (Upper Orange Dashed)**: Short-term top, market overheating

**Swing Trading Strategy**:
- **ENTER LONG**: When color changes from red to green (especially from <10-15% levels)
- **EXIT LONG**: When color changes from green to red (especially from >35-40% levels)
- **Timeframe**: Days to weeks

## Analysis Workflow

### Step 0: Fetch CSV Data (PRIMARY SOURCE — MANDATORY)

Run before any image analysis. CSV provides exact numerical values; images are supplementary only.

```bash
python3 skills/breadth-chart-analyst/scripts/fetch_breadth_csv.py
```

**Data Sources**:
| Source | Provides | Priority |
|--------|----------|----------|
| `market_breadth_data.csv` | 200-Day MA, 8-Day MA, Trend, Dead Cross | PRIMARY |
| `uptrend_ratio_timeseries.csv` | Ratio, 10MA, slope, trend, color | PRIMARY |
| `sector_summary.csv` | Per-sector ratio, trend, overbought/oversold | PRIMARY |
| Chart Image | Visual trend context, pattern confirmation | SUPPLEMENTARY |

**Validation checklist**:
- [ ] CSV data retrieved successfully
- [ ] 200-Day MA and 8-Day MA values recorded
- [ ] Dead cross status determined (8MA < 200MA = dead cross)
- [ ] Uptrend Ratio value + color + trend recorded

Use these CSV values as the authoritative source for all subsequent analysis.

---

### Step 1: Receive Chart Images and Prepare Analysis

1. Identify which chart(s) are provided: Chart 1 (200MA Breadth), Chart 2 (Uptrend Ratio), or both
2. Note specific focus areas or questions from the user
3. Proceed to two-stage chart analysis (Step 1.5)

**If NO chart images provided**: Skip to Step 2, using CSV data as sole source.

### Step 1.5: Two-Stage Chart Analysis (MANDATORY when charts provided)

Use two-stage analysis to prevent misreading historical data as current values.

| Stage | Purpose | What to Extract |
|-------|---------|-----------------|
| **Stage 1 (Full)** | Historical context, trend cycles | Overall patterns, past troughs/peaks |
| **Stage 2 (Right Edge)** | **Current values** | 8MA, 200MA, current color, slope |

```bash
python3 skills/breadth-chart-analyst/scripts/extract_chart_right_edge.py <image_path> --percent 25
```

**Protocol**: Read full chart for context → Run extraction script → Read right edge for current values → If Stage 1 and Stage 2 conflict, **Stage 2 takes precedence**.

### Step 2: Load Breadth Chart Methodology

Before beginning analysis, read the comprehensive breadth chart methodology:

```
Read: references/breadth_chart_methodology.md
```

This reference contains detailed guidance on:
- Chart 1: 200MA-based breadth index interpretation and strategy
- Chart 2: Uptrend stock ratio interpretation and strategy
- Signal identification and threshold significance
- Strategy rules and risk management
- Combining both charts for optimal decision-making
- Common pitfalls to avoid

### Step 3: Examine Sample Charts (First Time or for Reference)

To understand the chart format and visual elements, review the sample charts included in this skill:

```
View: skills/breadth-chart-analyst/assets/SP500_Breadth_Index_200MA_8MA.jpeg
View: skills/breadth-chart-analyst/assets/US_Stock_Market_Uptrend_Ratio.jpeg
```

These samples demonstrate:
- Visual appearance and structure of each chart type
- How signals and thresholds are displayed
- Color coding and marker systems
- Historical patterns and cycles

### Step 4: Analyze Chart 1 (200MA-Based Breadth Index)

If Chart 1 is provided, conduct systematic analysis:

#### 4.1 Extract Current Readings

From the chart image, identify:
- **Current 8MA level** (orange line): Specific percentage
- **Current 200MA level** (green line): Specific percentage
- **8MA slope**: Rising, falling, or flat
- **200MA slope**: Rising, falling, or flat
- **Distance from 73% threshold**: How close to overheating
- **Distance from 23% threshold**: How close to extreme oversold
- **Most recent date** visible on the chart

#### 4.1.5 Latest Data Point Trend Analysis (MANDATORY)

**Line identification**: 8MA = ORANGE (fast, volatile) | 200MA = GREEN (slow, smooth). Confirm before proceeding.

**8MA (Orange) — Analyze rightmost 3-5 data points**:
1. Record values at current, -1w, -2w, -3w
2. Determine slope: **Rising** (higher than previous 2-3 points) | **Falling** (lower) | **Flat** (within 2-3%)
3. Count consecutive increases (need 2-3 for confirmation) or decreases (failed reversal indicator)

**200MA (Green) — Analyze rightmost 4-6 weeks**: Record slope (rising/falling/flat).

**Failed Reversal Detection**: If 8MA trough (purple triangle) was recent, check:
- Did 8MA rise only 1-2 periods then turn down? Fail to reach 60%? Currently declining again?
- If YES to any → **FAILED REVERSAL** — signal is INVALID, do not enter

**Cross-check checklist**:
- [ ] Does stated 8MA slope match the visual slope of the orange line at rightmost edge?
- [ ] If pink background shading present at right edge → confirms bearish conditions
- [ ] Are 8MA and 200MA converging (death/golden cross forming) or diverging?

#### 4.2 Identify Signal Markers

Look for and document:
- **Most recent 8MA trough (purple ▼)**: Date and level
- **Most recent 200MA trough (blue ▼)**: Date and level (if visible in timeframe)
- **Most recent 200MA peak (red ▲)**: Date and level
- **Days/weeks since most recent signals**
- **Any pink background shading** (downtrend periods)

#### 4.3 Assess Market Regime

Based on readings and patterns, classify the current market as:
- Healthy Bull Market
- Overheated Bull Market
- Market Top/Distribution Phase
- Bear Market/Correction
- Capitulation/Extreme Oversold
- Early Recovery

Support the classification with specific evidence from the chart.

#### 4.4 Determine Strategy Position

Apply the backtested strategy rules with STRICT confirmation requirements:

**Check for BUY signal** (ALL criteria must be met):
1. ✓ **Trough Formation**: Has 8MA formed a clear trough (purple ▼)?
2. ✓ **Reversal Initiated**: Has 8MA begun to move upward from the trough?
3. ✓ **Confirmation Achieved**: Has 8MA risen for 2-3 CONSECUTIVE periods after the trough?
4. ✓ **No Recent Reversal**: Based on Step 4.1.5 analysis, is 8MA CURRENTLY rising (not falling)?
5. ✓ **Sustained Move**: Has 8MA maintained the upward trajectory without rolling over?
6. ⭐ **Optional but Strong**: Is 8MA below or near 23% (extreme oversold) at trough?

**BUY Signal Status**:
- **CONFIRMED**: All 5 required criteria met → ENTER LONG
- **DEVELOPING**: Trough formed, but < 2-3 consecutive increases → WAIT, MONITOR
- **FAILED**: Trough formed, but 8MA has rolled over and is declining → DO NOT ENTER, WAIT FOR NEXT TROUGH
- **NO SIGNAL**: No trough formed → WAIT

**Check for SELL signal**:
- Has 200MA formed a peak (red ▲)?
- Is 200MA near or above 73%?
- Is this an active sell signal requiring position exit?

**Current position determination**:
- **Long**: BUY signal confirmed, position entered and held
- **Preparing to Enter**: BUY signal developing (trough formed, watching for confirmation)
- **WAIT / Flat**: No valid signal OR failed reversal detected
- **Preparing to Exit**: SELL signal developing (200MA approaching peak)

#### 4.5 Develop Scenarios

Create 2-3 scenarios with probability estimates:
- Base case scenario (highest probability)
- Alternative scenario(s)
- Each scenario includes: description, supporting factors, strategy implications, key levels

### Step 5: Analyze Chart 2 (Uptrend Stock Ratio)

If Chart 2 is provided, conduct systematic analysis:

#### 5.0 Uptrend Ratio Detection Script (DEPRECATED)

Superseded by Step 0 CSV fetch. CSV values take precedence. OpenCV script available for supplementary validation only:
```bash
python3 skills/breadth-chart-analyst/scripts/detect_uptrend_ratio.py <image_path> [--debug]
```

#### 5.1 Extract Current Readings

From the chart image, identify:
- **Current uptrend stock ratio**: Specific percentage
- **Current color**: Green (uptrend) or Red (downtrend)
- **Ratio slope**: Rising, falling, or flat
- **Distance from 10% threshold**: How close to extreme oversold
- **Distance from 40% threshold**: How close to overbought
- **Most recent date** visible on the chart

#### 5.2 Identify Trend Transitions

Look for and document:
- **Most recent red-to-green transition**: Date and ratio level at transition
- **Most recent green-to-red transition**: Date and ratio level at transition
- **Duration of current color phase**: How long in current trend
- **Days/weeks since most recent transition**

#### 5.3 Assess Market Condition

Based on current ratio and color, classify as:
- Extreme Oversold (<10%)
- Moderate Bearish (10-20%, red)
- Neutral/Transitional (20-30%)
- Moderate Bullish (30-37%, green)
- Extreme Overbought (>37-40%)

Support the classification with specific evidence from the chart.

#### 5.4 Determine Trading Position

Apply the swing trading strategy rules:

**Check for ENTER LONG signal**:
- Has color changed from red to green?
- Was the transition from an oversold level (<15%)?
- Is the transition confirmed (2-3 days of green)?

**Check for EXIT LONG signal**:
- Has color changed from green to red?
- Was the transition from an overbought level (>35%)?
- Is momentum weakening?

**Current position**: Long, Flat, Preparing to Enter, or Preparing to Exit

#### 5.5 Develop Scenarios

Create 2-3 scenarios with probability estimates:
- Base case scenario (highest probability)
- Alternative scenario(s)
- Each scenario includes: description, supporting factors, trading implications, key levels

### Step 6: Combined Analysis (When Both Charts Provided)

If both charts are provided, integrate the strategic and tactical perspectives:

#### 6.1 Alignment Assessment

Create a positioning matrix:
- **Chart 1 (Strategic)**: Bullish / Bearish / Neutral + signal status
- **Chart 2 (Tactical)**: Bullish / Bearish / Neutral + signal status
- **Combined Implication**: How do they align or conflict?

#### 6.2 Scenario Classification

Determine which of the four scenarios applies:

**Scenario 1: Both Bullish**
- Chart 1: 8MA rising, 200MA not yet peaked
- Chart 2: Green (uptrend), ratio rising from oversold
- Implication: Maximum bullish stance, aggressive positioning

**Scenario 2: Strategic Bullish, Tactical Bearish**
- Chart 1: 8MA rising, 200MA not yet peaked
- Chart 2: Red (downtrend), ratio falling or elevated
- Implication: Hold core long positions, wait for tactical entry

**Scenario 3: Strategic Bearish, Tactical Bullish**
- Chart 1: 200MA peaked or declining
- Chart 2: Green (uptrend), ratio rising
- Implication: Short-term tactical trades only, tight stops

**Scenario 4: Both Bearish**
- Chart 1: Both MAs declining
- Chart 2: Red (downtrend), ratio falling
- Implication: Defensive positioning, cash or shorts

#### 6.3 Unified Recommendation

Provide integrated positioning guidance for:
- **Long-term investors** (based primarily on Chart 1)
- **Swing traders** (based primarily on Chart 2)
- **Active tactical traders** (based on combination)

Address any conflicts between charts and explain resolution.

### Step 7: Generate Analysis Report

Use the template: `skills/breadth-chart-analyst/assets/breadth_analysis_template.md`

Include only the sections relevant to the chart(s) analyzed. If both charts provided, the Combined Analysis section is mandatory.

**File naming**: `breadth_200ma_analysis_[date].md` | `uptrend_ratio_analysis_[date].md` | `breadth_combined_analysis_[date].md`

### Step 8: Quality Assurance

**Pre-publish checklist**:
- [ ] All content in English
- [ ] Line colors verified (8MA=ORANGE, 200MA=GREEN)
- [ ] Step 4.1.5 trend analysis completed on rightmost data points
- [ ] 8MA slope matches visual slope at right edge
- [ ] Death/golden cross check completed if lines converging
- [ ] Failed reversal check completed if trough was identified
- [ ] All readings have specific percentages, not vague descriptions
- [ ] Signal status explicitly stated (CONFIRMED BUY / DEVELOPING / FAILED / SELL / WAIT)
- [ ] Scenario probabilities sum to 100%
- [ ] Positioning recommendations for each trader type
- [ ] Invalidation levels and risk factors stated

**Sanity check**: If report claims bullish/BUY, confirm no pink shading or death cross visible. If uncertain about trend direction, state uncertainty explicitly.

## Quality Standards

- **Objectivity**: Base analysis on observable data; distinguish observations from forecasts; acknowledge ambiguity
- **Completeness**: Specific numerical values for all metrics; probability estimates with justification; invalidation levels; historical comparisons
- **Clarity**: Professional English; tables where appropriate; actionable recommendations
- **Strategy Adherence**: Apply backtested rules; distinguish strategic vs tactical signals; clear position status (Long/Flat/Entering/Exiting); include entry/exit levels and risk management

## Common Analysis Errors

| Error | Symptom | Prevention |
|-------|---------|------------|
| Confusing 8MA/200MA | Wrong line attributed | Verify: 8MA=ORANGE (volatile), 200MA=GREEN (smooth) |
| Reading historical not current | Describes data from months ago | Focus on rightmost 3-5 data points only |
| Missing death/golden cross | Bullish call during convergence | Check if 8MA and 200MA are converging or diverging |
| Ignoring pink shading | Bullish call during downtrend | Pink background = bearish — must acknowledge |
| Premature reversal call | "BUY confirmed" after 1 week | Require 2-3 consecutive weeks of 8MA increase |

## Example Usage Scenarios

- **CSV-Only** (no charts): Fetch CSV → Load methodology → Analyze values → Generate `breadth_combined_analysis_[date].md`
- **Chart 1 Only**: Fetch CSV → Two-stage chart analysis → Cross-check CSV vs image → Generate `breadth_200ma_analysis_[date].md`
- **Both Charts**: Fetch CSV → Two-stage analysis per chart → Cross-check → Combined assessment → Generate `breadth_combined_analysis_[date].md`

## Resources

This skill includes the following bundled resources:

### references/breadth_chart_methodology.md

Comprehensive methodology covering:
- **Chart 1 (200MA Breadth)**: Components, interpretation, market regimes, backtested strategy, analysis checklist
- **Chart 2 (Uptrend Ratio)**: Components, interpretation, market conditions, swing trading strategy, analysis checklist
- **Combined Analysis**: Alignment scenarios, integrated decision-making
- **Common Pitfalls**: Mistakes to avoid for each chart type

**Usage**: Read this file before conducting any breadth chart analysis to ensure systematic, accurate interpretation.

### assets/breadth_analysis_template.md

Structured template for breadth analysis reports in English.

**Usage**: Use this template structure for every analysis report.

### assets/SP500_Breadth_Index_200MA_8MA.jpeg

Sample Chart 1 image for format reference.

### assets/US_Stock_Market_Uptrend_Ratio.jpeg

Sample Chart 2 image for format reference.

### scripts/fetch_breadth_csv.py

**PRIMARY data source**. Fetches market breadth, uptrend ratio, and sector summary data from public CSV sources. Uses only stdlib (urllib + csv) -- no external dependencies.

```bash
python3 skills/breadth-chart-analyst/scripts/fetch_breadth_csv.py        # Human-readable
python3 skills/breadth-chart-analyst/scripts/fetch_breadth_csv.py --json  # JSON output
```

### scripts/extract_chart_right_edge.py

Extracts the rightmost portion of chart images to help focus on latest data points. Requires PIL/Pillow.

```bash
python3 skills/breadth-chart-analyst/scripts/extract_chart_right_edge.py <image_path> --percent 25
```

### scripts/detect_uptrend_ratio.py (DEPRECATED)

OpenCV-based uptrend ratio detection. Superseded by CSV fetch. Requires opencv-python + numpy.

### scripts/detect_breadth_values.py (DEPRECATED)

OpenCV-based breadth value detection. Superseded by CSV fetch. Requires opencv-python + numpy.

## Special Notes

- **Language**: All analysis, thinking, and output MUST be in English exclusively
- **Strategy Focus**: Apply backtested systematic rules — not discretionary interpretation
- **Actionable Output**: Every analysis must answer: Should I be long/flat/short? Enter or exit now? At what levels? What invalidates this view?
