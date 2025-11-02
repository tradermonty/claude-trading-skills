---
name: breadth-chart-analyst
description: This skill should be used when analyzing market breadth charts, specifically the S&P 500 Breadth Index (200-Day MA based) and the US Stock Market Uptrend Stock Ratio charts. Use this skill when the user provides breadth chart images for analysis, requests market breadth assessment, positioning strategy recommendations, or wants to understand medium-term strategic and short-term tactical market outlook based on breadth indicators. All analysis and output are conducted in English.
---

# Breadth Chart Analyst

## Overview

This skill enables specialized analysis of two complementary market breadth charts that provide strategic (medium to long-term) and tactical (short-term) market perspectives. Analyze breadth chart images to assess market health, identify trading signals based on backtested strategies, and develop positioning recommendations. All thinking and output are conducted exclusively in English.

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

### Step 1: Receive Chart Images and Prepare Analysis

When the user provides breadth chart images for analysis:

1. Confirm receipt of chart image(s)
2. Identify which chart(s) are provided:
   - Chart 1 only (200MA Breadth)
   - Chart 2 only (Uptrend Ratio)
   - Both charts
3. Note any specific focus areas or questions from the user
4. Proceed with systematic analysis

**Language Note**: All subsequent thinking, analysis, and output will be in English.

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
2. ✓ **Latest Data Trend Analysis**: Step 4.1.5 was thoroughly completed - the most recent 3-5 data points were analyzed to determine CURRENT trend direction
3. ✓ **Trend Direction Accuracy**: The stated 8MA slope (Rising/Falling/Flat) accurately reflects the RIGHTMOST data points, not historical movement
4. ✓ **Failed Reversal Check**: If a trough was identified, explicitly verified whether the reversal sustained or failed by analyzing latest trajectory
5. ✓ **Specific Values**: All readings include specific percentages/levels, not vague descriptions
6. ✓ **Signal Status**: Clear identification of active signals (CONFIRMED BUY / DEVELOPING / FAILED / SELL / WAIT)
7. ✓ **Strategy Alignment**: Recommendations align with backtested strategies and confirmation requirements
8. ✓ **Probabilities**: Scenario probabilities sum to 100%
9. ✓ **Actionable**: Clear positioning recommendations for different trader types
10. ✓ **Context**: Historical comparison and reference to similar past situations
11. ✓ **Risk Management**: Invalidation levels and risk factors clearly stated

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

## Example Usage Scenarios

### Example 1: Strategic Breadth Analysis (Chart 1 Only)

```
User: "Please analyze this S&P 500 breadth chart and tell me where we are in the market cycle."
[Provides Chart 1 image: 200MA Breadth Index]

Breadth Analyst (thinking in English):
1. Confirms receipt of Chart 1 (200MA-based breadth index)
2. Reads breadth_chart_methodology.md for Chart 1 guidance
3. Views sample chart for format reference
4. Extracts current readings:
   - 8MA: 68%
   - 200MA: 75%
   - 8MA slope: Flat to slightly declining
   - 200MA slope: Rising but may be forming peak
   - Distance from 73% threshold: +2% (above threshold = overheated)
5. Identifies signals:
   - Most recent 8MA trough: 3 months ago at 25%
   - Most recent 200MA peak: None visible yet, but 200MA at 75% suggests potential peak forming
6. Assesses regime: Overheated Bull Market approaching Distribution Phase
7. Determines strategy position: Long position should prepare to exit; watch for 200MA peak confirmation
8. Develops scenarios:
   - Base Case (55%): 200MA forms peak in next 1-2 weeks, sell signal activates
   - Alternative (35%): Further consolidation at elevated levels before eventual peak
   - Bear Case (10%): Immediate rollover without clear peak formation
9. Generates comprehensive report in English: breadth_200ma_analysis_2025-11-02.md
```

### Example 2: Tactical Uptrend Ratio Analysis (Chart 2 Only)

```
User: "Should I be buying or selling here? Analyze this uptrend ratio chart."
[Provides Chart 2 image: Uptrend Stock Ratio]

Breadth Analyst (thinking in English):
1. Confirms receipt of Chart 2 (Uptrend stock ratio)
2. Reads breadth_chart_methodology.md for Chart 2 guidance
3. Views sample chart for format reference
4. Extracts current readings:
   - Current ratio: 12%
   - Current color: Green (uptrend)
   - Ratio slope: Rising sharply
   - Just transitioned from red to green 3 days ago at 11%
5. Identifies transitions:
   - Most recent red-to-green: 3 days ago at 11% (from extreme oversold)
   - Prior green-to-red: 2 weeks ago at 28%
6. Assesses condition: Early in new uptrend from extreme oversold
7. Determines trading position: ENTER LONG signal active, excellent risk/reward
8. Develops scenarios:
   - Base Case (65%): Ratio continues higher to 30-35% over next 2-3 weeks
   - Alternative (25%): Choppy advance, consolidates around 20% before next leg
   - Bear Case (10%): False breakout, returns to red quickly
9. Generates tactical report in English: uptrend_ratio_analysis_2025-11-02.md
```

### Example 3: Combined Strategic + Tactical Analysis (Both Charts)

```
User: "Analyze both of these breadth charts and give me your overall market view."
[Provides both Chart 1 and Chart 2 images]

Breadth Analyst (thinking in English):
1. Confirms receipt of both charts
2. Reads full breadth_chart_methodology.md
3. Views both sample charts
4. Analyzes Chart 1:
   - 8MA: 55%, rising from trough 2 weeks ago at 30%
   - 200MA: 60%, still rising
   - Regime: Early Recovery to Healthy Bull Market
   - Strategy: Long position, hold
5. Analyzes Chart 2:
   - Ratio: 22%, green (uptrend)
   - Transitioned red-to-green 10 days ago from 14%
   - Condition: Moderate Bullish, building momentum
   - Trading: Hold long, entered on transition
6. Combined assessment:
   - Scenario 1: Both Bullish ✓
   - Strategic: Bullish (8MA reversal confirmed)
   - Tactical: Bullish (uptrend established from oversold)
   - Alignment: Strong alignment = Maximum conviction
7. Unified recommendation:
   - Long-term investors: Aggressive long positioning, core holdings
   - Swing traders: Hold longs entered on red-to-green, target 35%+
   - Active traders: Full position, favorable environment for longs
8. Develops integrated scenarios with probabilities
9. Generates comprehensive combined report in English: breadth_combined_analysis_2025-11-02.md
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

Structured template for breadth analysis reports in English:
- Executive Summary
- Chart 1 analysis sections (if applicable)
- Chart 2 analysis sections (if applicable)
- Combined Analysis section (when both charts analyzed)
- Summary and Conclusion
- All sections include tables, checklists, and structured formats

**Usage**: Use this template structure for every analysis report. Adapt sections based on which chart(s) are being analyzed.

### assets/SP500_Breadth_Index_200MA_8MA.jpeg

Sample Chart 1 image showing:
- 8-day MA (orange) and 200-day MA (green) lines
- Threshold levels (73% red dashed, 23% blue dashed)
- Signal markers (triangles for troughs and peaks)
- Pink background downtrend shading
- Historical patterns from 2016-2025

**Usage**: Reference this sample to understand Chart 1 visual format and identify similar patterns in user-provided charts.

### assets/US_Stock_Market_Uptrend_Ratio.jpeg

Sample Chart 2 image showing:
- Green and red color-coded trend phases
- Uptrend ratio percentage on y-axis
- Threshold levels (~10% and ~40% orange dashed lines)
- Short-term momentum patterns
- Historical patterns from 2023-2025

**Usage**: Reference this sample to understand Chart 2 visual format and identify similar patterns in user-provided charts.

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
