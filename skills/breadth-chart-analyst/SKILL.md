---
name: breadth-chart-analyst
description: This skill should be used when analyzing market breadth charts, specifically the S&P 500 Breadth Index (200-Day MA based) and the US Stock Market Uptrend Stock Ratio charts. Use this skill when the user provides breadth chart images for analysis, requests market breadth assessment, positioning strategy recommendations, or wants to understand medium-term strategic and short-term tactical market outlook based on breadth indicators. Also works WITHOUT chart images by fetching CSV data directly from public sources. All analysis and output are conducted in English.
---

# Breadth Chart Analyst

## Overview

This skill enables specialized analysis of two complementary market breadth charts that provide strategic (medium to long-term) and tactical (short-term) market perspectives. Analyze breadth chart images to assess market health, identify trading signals based on backtested strategies, and develop positioning recommendations. All thinking and output are conducted exclusively in English.

## When to Use

Use this skill when:
- User provides S&P 500 Breadth Index (200-Day MA based) chart images for analysis
- User provides US Stock Market Uptrend Stock Ratio chart images for analysis
- User requests market breadth assessment or market health evaluation
- User asks about medium-term strategic positioning based on breadth indicators
- User needs short-term tactical timing signals for swing trading
- User wants combined strategic and tactical market outlook
- **User requests breadth analysis WITHOUT providing chart images** (CSV data mode)

Do NOT use this skill when:
- User asks about individual stock analysis (use `us-stock-analysis` skill instead)
- User needs sector rotation analysis without breadth charts (use `sector-analyst` skill instead)
- User wants news-based market analysis (use `market-news-analyst` skill instead)

## Prerequisites

- **Chart Images Optional**: CSV data from public sources is the PRIMARY data source; chart images provide supplementary visual context
- **No API Keys Required**: CSV data is fetched from public GitHub Pages; no external API subscriptions needed
- **Language**: All analysis and output conducted in English

## Output

This skill generates markdown analysis reports saved to the `reports/` directory:
- Chart 1 only: `breadth_200ma_analysis_[YYYY-MM-DD].md`
- Chart 2 only: `uptrend_ratio_analysis_[YYYY-MM-DD].md`
- Both charts: `breadth_combined_analysis_[YYYY-MM-DD].md`

Reports include executive summaries, current readings, signal identification, scenario analysis with probabilities, and actionable positioning recommendations for different trader types.

## Core Principles

1. **Dual-Timeframe Analysis**: Combine strategic (Chart 1: 200MA Breadth) and tactical (Chart 2: Uptrend Ratio) perspectives
2. **Backtested Strategy Focus**: Apply proven systematic strategies based on historical patterns
3. **Objective Signal Identification**: Focus on clearly defined thresholds, transitions, and markers
4. **English Communication**: Conduct all analysis and generate all reports in English
5. **Actionable Recommendations**: Provide specific positioning guidance for different investor types

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

### Step 0: Fetch CSV Data (PRIMARY SOURCE - MANDATORY)

**CRITICAL**: CSV data is the PRIMARY source for all Breadth values. This step MUST be executed BEFORE any image analysis.

```bash
python3 skills/breadth-chart-analyst/scripts/fetch_breadth_csv.py
```

**Why CSV is PRIMARY**:
- OpenCV image detection is fragile -- chart format changes cause catastrophic failures (Issue #7)
- CSV provides exact numerical values directly from the data source
- Image analysis is SUPPLEMENTARY only (for visual trend context)

**Data Sources**:
1. **Market Breadth**: `tradermonty.github.io/market-breadth-analysis/market_breadth_data.csv`
   - Provides: 200-Day MA, 8-Day MA, Trend, Dead Cross status
2. **Uptrend Ratio**: `tradermonty/uptrend-dashboard/data/uptrend_ratio_timeseries.csv`
   - Provides: Current ratio, 10MA, slope, trend (UP/DOWN), color (GREEN/RED)
3. **Sector Summary**: `tradermonty/uptrend-dashboard/data/sector_summary.csv`
   - Provides: Per-sector ratio, trend, status (overbought/oversold)

**Data Source Priority**:
| Priority | Source | Use For | Reliability |
|----------|--------|---------|-------------|
| 1 (PRIMARY) | **CSV Data** | All numerical values, dead cross status, color | HIGH |
| 2 (SUPPLEMENTARY) | **Chart Image** | Visual trend context, pattern confirmation | MEDIUM |
| 3 (DEPRECATED) | ~~OpenCV detect_breadth_values.py~~ | ~~Breadth detection~~ | **UNRELIABLE** |
| 4 (LAST RESORT) | ~~LLM visual reading~~ | ~~Emergency only~~ | LOW |

**Expected Output**:
```
============================================================
Breadth Data (CSV) - 2026-02-13
============================================================
--- Market Breadth (S&P 500) ---
200-Day MA: 62.26% (healthy (>=60%))
8-Day MA:   67.56% (healthy_bullish (60-73%))
8MA vs 200MA: +5.30pt (8MA ABOVE -- NO dead cross)
Trend: UPTREND
--- Uptrend Ratio (All Markets) ---
Current: 33.03% GREEN (neutral_bullish)
10MA: 32.65%, Slope: +0.0055, Trend: UP
--- Sector Summary ---
...
============================================================
```

**Validation**: After running CSV fetch, verify:
- [ ] CSV data retrieved successfully
- [ ] 200-Day MA value recorded
- [ ] 8-Day MA value recorded
- [ ] Dead cross status determined (8MA < 200MA = dead cross)
- [ ] Uptrend Ratio value + color + trend recorded
- [ ] Use these CSV values as the authoritative source for all subsequent analysis

---

### Step 1: Receive Chart Images and Prepare Analysis

When the user provides breadth chart images for analysis:

1. Confirm receipt of chart image(s)
2. Identify which chart(s) are provided:
   - Chart 1 only (200MA Breadth)
   - Chart 2 only (Uptrend Ratio)
   - Both charts
3. Note any specific focus areas or questions from the user
4. **CRITICAL: Extract right edge of chart images before analysis** (Step 1.5)

**If NO chart images are provided**: Skip Steps 1, 1.5, and image-based analysis. Use CSV data from Step 0 as the sole data source and proceed directly to the analysis and report generation steps.

**Language Note**: All subsequent thinking, analysis, and output will be in English.

### Step 1.5: Two-Stage Chart Analysis (MANDATORY when charts provided)

**CRITICAL**: Use a **two-stage analysis** approach to prevent misreading historical data as current values.

#### Stage 1: Full Chart Analysis (Historical Context)

First, analyze the FULL chart image to understand:
- Overall historical trend and cycles
- Key historical events (troughs, peaks, recoveries)
- Long-term patterns and context

#### Stage 2: Right Edge Focused Analysis (Current Values)

Then, extract and analyze the **rightmost 25%** of the chart to accurately determine CURRENT values.

**Execute the Python script to extract the right edge:**

```bash
python3 skills/breadth-chart-analyst/scripts/extract_chart_right_edge.py <image_path> --percent 25
```

#### Why Two-Stage Analysis is Mandatory

| Stage | Purpose | What to Extract |
|-------|---------|-----------------|
| **Stage 1 (Full)** | Historical context, trend cycles | Overall patterns, past troughs/peaks |
| **Stage 2 (Right Edge)** | **Current values (CRITICAL)** | 8MA value, 200MA value, current color, current slope |

**Common Error This Prevents:**
- LLM reads 2025 mid-year dip (8MA ~25-30%) instead of current value (8MA ~60-65%)
- By isolating the right edge, the "current" data is unambiguous

#### Analysis Protocol

1. **Read full chart** → Document historical context
2. **Run extraction script** → Generate right edge image
3. **Read right edge image** → Document current values with HIGH CONFIDENCE
4. **Cross-check**: If Stage 1 and Stage 2 values differ significantly, **Stage 2 (right edge) takes precedence**
5. **Report both**: Include Stage 1 context AND Stage 2 current values in analysis

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
View: assets/SP500_Breadth_Index_200MA_8MA.jpeg
View: assets/US_Stock_Market_Uptrend_Ratio.jpeg
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

#### 4.1.5 CRITICAL: Latest Data Point Detailed Trend Analysis

**This step is MANDATORY to avoid misreading recent trend changes.**

**CRITICAL WARNING**: Charts can be deceptive. The MAJORITY of analysis errors occur because the analyst:
1. Confuses the 8MA (orange) with the 200MA (green)
2. Reads historical trends instead of the CURRENT rightmost data points
3. Misidentifies which line is rising vs falling

**BEFORE analyzing trend direction, FIRST confirm line colors**:
- ✓ **8MA = ORANGE line** (fast-moving, more volatile)
- ✓ **200MA = GREEN line** (slow-moving, smoother)
- If unsure which is which, STOP and re-examine the chart legend/colors

Focus intensively on the **rightmost 3-5 data points** of the chart (most recent weeks):

**For 8MA (Orange Line) - Analyze the very latest trajectory**:
1. **Identify the absolute latest position**: Where is the 8MA at the rightmost edge of the chart?
2. **Trace back 3-5 data points** (approximately 3-5 weeks):
   - What was the 8MA level 1 week ago?
   - What was the 8MA level 2 weeks ago?
   - What was the 8MA level 3 weeks ago?
3. **Calculate the directional change**:
   - Is the latest value HIGHER or LOWER than 1 week ago?
   - Is the latest value HIGHER or LOWER than 2 weeks ago?
   - What is the trend: consistently rising, consistently falling, or mixed?
4. **Determine the CURRENT slope** (not historical slope):
   - **Rising**: Latest data point is higher than previous 2-3 points AND shows upward curvature
   - **Falling**: Latest data point is lower than previous 2-3 points AND shows downward curvature
   - **Flat**: Latest data point is approximately equal to previous points (within 2-3%)

**Critical Questions to Answer**:
- [ ] Is the 8MA currently moving UP or DOWN at the rightmost edge?
- [ ] If there was a recent trough, has the 8MA **sustained** the upward move, or has it rolled over?
- [ ] Count consecutive periods of increase: How many consecutive periods has 8MA risen? (Need 2-3 for confirmation)
- [ ] Count consecutive periods of decrease: How many consecutive periods has 8MA fallen? (Indicates failed reversal if declining after trough)

**For 200MA (Green Line) - Analyze the very latest trajectory**:
1. **Identify the absolute latest position**: Where is the 200MA at the rightmost edge?
2. **Trace back 4-6 weeks**:
   - What was the 200MA level 2 weeks ago?
   - What was the 200MA level 4 weeks ago?
3. **Determine the CURRENT slope**:
   - Is it rising, falling, or flat in the most recent period?

**Failed Reversal Detection** (CRITICAL):
If an 8MA trough (purple ▼) was recently identified:
- [ ] Did the 8MA rise for only 1-2 periods and then turn back down?
- [ ] Did the 8MA fail to reach 60% before turning down?
- [ ] Is the 8MA currently declining again after the bounce?
- **If YES to any**: This is a **FAILED REVERSAL** - DO NOT ENTER, signal is INVALID

**Example Analysis Format**:
```
Latest 8MA Data Points (rightmost to left):
- Current (Week 0): 48%
- 1 week ago: 52%
- 2 weeks ago: 55%
- 3 weeks ago: 50%

Analysis: 8MA is FALLING. It rose from 50% to 55% (weeks 3-2), but has since declined to 48%.
This shows a failed reversal pattern - bounce was temporary, downtrend has resumed.
SLOPE: Falling (not rising!)
```

**MANDATORY CROSS-CHECK** (to catch misreadings):
After determining the trend, ask yourself:
- [ ] "If I claimed 8MA is RISING, but it's actually been FALLING for weeks, what would that look like?"
  - Answer: The rightmost data points would be LOWER than previous points (confirming FALLING)
- [ ] "Does my analysis match the visual slope of the orange line at the rightmost edge?"
  - If orange line visually slopes DOWN at the right edge → It's FALLING
  - If orange line visually slopes UP at the right edge → It's RISING
- [ ] "Is there any pink background shading (downtrend) near the rightmost edge?"
  - If YES → This confirms downtrend conditions, 8MA is likely FALLING
- [ ] "Are the 8MA and 200MA converging (getting closer) or diverging?"
  - Converging from below → Potential death cross forming → BEARISH
  - Converging from above → Potential golden cross forming → BULLISH

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

#### 5.0 ~~MANDATORY~~ DEPRECATED: Uptrend Ratio Detection Script (Superseded by Step 0 CSV Fetch)

**NOTE (Issue #7)**: This OpenCV detection step is **DEPRECATED**. Use CSV data from Step 0 as the PRIMARY source. The OpenCV script may be run for supplementary validation only, but CSV values take precedence in all cases.

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

### Step 7: Generate Analysis Report in English

Create a comprehensive markdown report using the template structure:

```
Read and use as template: assets/breadth_analysis_template.md
```

**IMPORTANT**: All analysis and output must be in English.

The report structure varies based on which chart(s) are analyzed:

**If Chart 1 only**:
- Executive Summary
- Chart 1 full analysis sections
- Summary and Conclusion
- Omit Chart 2 and Combined Analysis sections

**If Chart 2 only**:
- Executive Summary
- Chart 2 full analysis sections
- Summary and Conclusion
- Omit Chart 1 and Combined Analysis sections

**If Both Charts**:
- Executive Summary
- Chart 1 full analysis sections
- Chart 2 full analysis sections
- Combined Analysis section (mandatory)
- Summary and Conclusion

**File Naming Convention**: Save each analysis as:
- Chart 1 only: `breadth_200ma_analysis_[YYYY-MM-DD].md`
- Chart 2 only: `uptrend_ratio_analysis_[YYYY-MM-DD].md`
- Both charts: `breadth_combined_analysis_[YYYY-MM-DD].md`

### Step 8: Quality Assurance

Before finalizing the report, verify:

1. ✓ **Language**: All content is in English (thinking and output)
2. ✓ **Line Color Verification**: Explicitly confirmed 8MA = ORANGE, 200MA = GREEN before trend analysis
3. ✓ **Latest Data Trend Analysis**: Step 4.1.5 was thoroughly completed - the most recent 3-5 data points were analyzed to determine CURRENT trend direction
4. ✓ **Trend Direction Accuracy**: The stated 8MA slope (Rising/Falling/Flat) accurately reflects the RIGHTMOST data points, not historical movement
5. ✓ **Cross-Check Completed**: MANDATORY CROSS-CHECK questions were answered to confirm trend direction matches visual slope
6. ✓ **Death/Golden Cross Check**: If 8MA and 200MA are converging, explicitly identified whether death cross or golden cross is forming
7. ✓ **Failed Reversal Check**: If a trough was identified, explicitly verified whether the reversal sustained or failed by analyzing latest trajectory
8. ✓ **Specific Values**: All readings include specific percentages/levels, not vague descriptions
9. ✓ **Signal Status**: Clear identification of active signals (CONFIRMED BUY / DEVELOPING / FAILED / SELL / WAIT)
10. ✓ **Strategy Alignment**: Recommendations align with backtested strategies and confirmation requirements
11. ✓ **Probabilities**: Scenario probabilities sum to 100%
12. ✓ **Actionable**: Clear positioning recommendations for different trader types
13. ✓ **Context**: Historical comparison and reference to similar past situations
14. ✓ **Risk Management**: Invalidation levels and risk factors clearly stated

**FINAL SANITY CHECK**:
- [ ] If report claims "BUY signal" or "8MA rising", confirm this doesn't contradict user's chart showing death cross or downtrend
- [ ] If report claims "bullish", confirm there's no pink background shading or death cross visible
- [ ] If unsure about ANY trend direction, explicitly state uncertainty rather than guessing

## Quality Standards

### Objectivity Requirements

- Base all analysis strictly on observable chart data
- Do not incorporate external information (news, fundamentals) unless specifically relevant
- Use precise technical terminology consistently
- Distinguish clearly between factual observations and probabilistic forecasts
- Acknowledge uncertainty when signals are ambiguous

### Completeness Requirements

- Address all relevant sections of the analysis template
- Provide specific numerical values for all key metrics
- Justify probability estimates with technical factors
- Include invalidation levels for each scenario
- Compare current readings to historical patterns visible on the charts

### Clarity Requirements

- Write in professional, analytical English
- Use clear section headings and structure
- Present information in tables where appropriate
- Make recommendations specific and actionable
- Avoid jargon without explanation

### Strategy Adherence Requirements

- Apply backtested strategy rules correctly
- Distinguish between strategic (Chart 1) and tactical (Chart 2) signals
- Provide clear position status (Long/Flat/Entering/Exiting)
- Include specific entry/exit levels when applicable
- Address risk management (stop losses, position sizing)

## Common Analysis Errors and How to Avoid Them

### Error 1: Confusing 8MA with 200MA

**Symptom**: Report claims 8MA is rising when it's actually the 200MA that's rising

**Prevention**:
- ALWAYS verify: 8MA = ORANGE, 200MA = GREEN
- Check line volatility: 8MA moves faster with more volatility
- If unsure, state: "Based on line color, I identify the [orange/green] line as [8MA/200MA]"

### Error 2: Reading Historical Trends Instead of Current Direction

**Symptom**: Report describes what happened 1-2 months ago, not what's happening NOW

**Prevention**:
- Focus ONLY on rightmost 3-5 data points
- Explicitly write: "At the CURRENT rightmost edge, 8MA is at X% and is [rising/falling]"
- Ignore what happened in September if we're analyzing November

### Error 3: Missing Death Cross or Golden Cross Formation

**Symptom**: Report is bullish when 8MA and 200MA are about to death cross (bearish)

**Prevention**:
- ALWAYS check: "Are 8MA and 200MA getting closer (converging) or further apart (diverging)?"
- If converging with 8MA above 200MA → Potential death cross → BEARISH
- If converging with 8MA below 200MA → Potential golden cross → BULLISH
- Explicitly state: "8MA is currently [above/below] 200MA, and they are [converging/diverging]"

### Error 4: Ignoring Pink Background Shading

**Symptom**: Report claims bullish setup when chart shows pink downtrend background

**Prevention**:
- Check for pink shading at the rightmost edge
- Pink background = Downtrend period = Bearish conditions
- If pink shading present, report MUST acknowledge bearish conditions

### Error 5: Claiming Reversal Too Early

**Symptom**: Report says "BUY signal confirmed" after only 1 week of increase

**Prevention**:
- Require 2-3 CONSECUTIVE weeks of 8MA increase for confirmation
- If only 1 week: Signal is "DEVELOPING", not "CONFIRMED"
- If 8MA rises then falls again: Signal is "FAILED", not valid

## Example Usage Scenarios

### Example 1: CSV-Only Analysis (No Charts)

```
User: "breadth分析して" (Analyze breadth)
[No chart images provided]

Breadth Analyst:
1. Executes fetch_breadth_csv.py to get latest CSV data
2. Reads breadth_chart_methodology.md
3. Analyzes CSV data:
   - 200MA: 62.26% (healthy)
   - 8MA: 67.56% (healthy_bullish)
   - 8MA vs 200MA: +5.30pt (NO dead cross)
   - Uptrend Ratio: 33.03% GREEN (neutral_bullish)
   - Sector summary with overbought/oversold sectors
4. Assesses market regime based on CSV values
5. Generates report: breadth_combined_analysis_2026-03-16.md
```

### Example 2: Strategic Breadth Analysis (Chart 1 Only)

```
User: "Please analyze this S&P 500 breadth chart and tell me where we are in the market cycle."
[Provides Chart 1 image: 200MA Breadth Index]

Breadth Analyst (thinking in English):
1. Executes CSV fetch for authoritative numerical values
2. Confirms receipt of Chart 1 (200MA-based breadth index)
3. Reads breadth_chart_methodology.md for Chart 1 guidance
4. Two-stage analysis: full chart → right edge extraction
5. Cross-checks CSV values with chart readings
6. Generates comprehensive report in English
```

### Example 3: Combined Strategic + Tactical Analysis (Both Charts)

```
User: "Analyze both of these breadth charts and give me your overall market view."
[Provides both Chart 1 and Chart 2 images]

Breadth Analyst (thinking in English):
1. Executes CSV fetch as PRIMARY source
2. Confirms receipt of both charts
3. Reads full breadth_chart_methodology.md
4. Two-stage analysis for each chart
5. Cross-checks all values against CSV data
6. Combined assessment and unified recommendation
7. Generates comprehensive combined report
```

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

### Language Requirement

**CRITICAL**: All analysis, thinking, and output MUST be in English. This includes:
- Internal analysis and reasoning
- Report generation
- Tables and data presentation
- Scenario descriptions
- Recommendations

Do not translate or use any other language. The user expects English output exclusively.

### Strategy Focus

This skill emphasizes backtested, systematic strategies rather than discretionary interpretation. Always:
- Apply the strategy rules as documented
- Reference historical performance patterns
- Provide specific entry/exit criteria
- Include risk management guidance

### Practical Application

The goal is actionable intelligence. Every analysis should answer:
- **Strategic**: Should I be long, flat, or short the market over the medium term?
- **Tactical**: Should I enter or exit positions in the short term?
- **Timing**: When should I act, and at what levels?
- **Risk**: What would invalidate this view, and where should stops be?
