---
layout: default
title: "Technical Analyst"
grand_parent: English
parent: Skill Guides
nav_order: 56
lang_peer: /ja/skills/technical-analyst/
permalink: /en/skills/technical-analyst/
---

# Technical Analyst
{: .no_toc }

This skill should be used when analyzing weekly price charts for stocks, stock indices, cryptocurrencies, or forex pairs. Use this skill when the user provides chart images and requests technical analysis, trend identification, support/resistance levels, scenario planning, or probability assessments based purely on chart data without consideration of news or fundamental factors.
{: .fs-6 .fw-300 }

<span class="badge badge-free">No API</span>

[Download Skill Package (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/technical-analyst.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/technical-analyst){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

This skill enables comprehensive technical analysis of weekly price charts. Analyze chart images to identify trends, support and resistance levels, moving average relationships, volume patterns, and develop probabilistic scenarios for future price movement. All analysis is conducted objectively using only chart data, without influence from news, fundamentals, or market sentiment.

---

## 2. When to Use

- User provides weekly chart images (stocks, indices, crypto, forex) and requests technical analysis
- Need to identify trend direction, strength, and potential reversal points
- Looking for support/resistance levels and key price zones
- Want probabilistic scenario planning with specific price targets
- Require objective chart-based analysis without fundamental or news considerations

---

## 3. Prerequisites

- **Chart Images**: User must provide weekly timeframe chart images for analysis
- **No API Keys Required**: This skill analyzes user-provided images; no external data fetches

---

## 4. Quick Start

```bash
Read: references/technical_analysis_framework.md
```

---

## 5. Workflow

### Step 1: Receive Chart Images

When the user provides one or more weekly chart images for analysis:

1. Confirm receipt of all chart images
2. Identify the number of charts to analyze
3. Note any specific focus areas requested by the user
4. Proceed to analyze charts sequentially, one at a time

### Step 2: Load Technical Analysis Framework

Before beginning analysis, read the comprehensive technical analysis methodology:

```
Read: references/technical_analysis_framework.md
```

This reference contains detailed guidance on:
- Trend analysis and classification
- Support and resistance identification
- Moving average interpretation
- Volume analysis
- Chart patterns and candlestick analysis
- Scenario development and probability assignment
- Analysis discipline and objectivity

### Step 3: Analyze Each Chart Systematically

For each chart image, conduct a systematic analysis following this sequence:

#### 3.1 Trend Analysis
- Identify trend direction (uptrend, downtrend, sideways)
- Assess trend strength (strong, moderate, weak)
- Note trend duration and potential exhaustion signals
- Examine higher highs/lows or lower highs/lows pattern

#### 3.2 Support and Resistance Analysis
- Mark significant horizontal support levels
- Mark significant horizontal resistance levels
- Identify trendline support/resistance
- Note any support-resistance role reversals
- Assess confluence zones where multiple S/R levels align

#### 3.3 Moving Average Analysis
- Determine price position relative to 20-week, 50-week, and 200-week MAs
- Assess MA alignment (bullish, bearish, or neutral configuration)
- Note MA slope (rising, falling, flat)
- Identify any recent or pending MA crossovers
- Observe MAs acting as dynamic support or resistance

#### 3.4 Volume Analysis
- Assess overall volume trend (increasing, decreasing, stable)
- Identify volume spikes and their context (at support/resistance, on breakouts)
- Check for volume confirmation or divergence with price
- Note any volume climax or exhaustion patterns

#### 3.5 Chart Patterns and Price Action
- Identify any reversal patterns (hammers, shooting stars, engulfing patterns, etc.)
- Identify any continuation patterns (flags, triangles, etc.)
- Note significant candlestick formations
- Observe recent breakouts or breakdowns

#### 3.6 Synthesize Observations
- Integrate all technical elements into coherent current assessment
- Identify the most significant factors influencing the chart
- Note any conflicting signals or ambiguity
- Establish key levels that will determine future direction

### Step 4: Develop Probabilistic Scenarios

For each analyzed chart, create 2-4 distinct scenarios for future price movement:

#### Scenario Structure

Each scenario must include:
1. **Scenario Name**: Clear, descriptive title (e.g., "Bull Case: Breakout Above Resistance")
2. **Probability Estimate**: Percentage likelihood based on technical factors (must sum to 100% across all scenarios)
3. **Description**: What this scenario entails and how it would unfold
4. **Supporting Factors**: Technical evidence supporting this scenario (minimum 2-3 factors)
5. **Target Levels**: Expected price levels if scenario plays out
6. **Invalidation Level**: Specific price level that would negate this scenario

#### Typical Scenario Framework

- **Base Case Scenario (40-60%)**: Most likely outcome based on current structure
- **Bull Case Scenario (20-40%)**: Optimistic scenario requiring upside breakout
- **Bear Case Scenario (20-40%)**: Pessimistic scenario requiring downside breakdown
- **Alternative Scenario (5-15%)**: Lower probability but technically plausible outcome

Adjust probabilities based on strength of supporting technical factors. Ensure probabilities are realistic and sum to 100%.

### Step 5: Generate Analysis Report

For each chart analyzed, create a comprehensive markdown report using the template structure:

```
Read and use as template: assets/analysis_template.md
```

The report must include all sections:
1. Chart Overview
2. Trend Analysis
3. Support and Resistance Levels
4. Moving Average Analysis
5. Volume Analysis
6. Chart Patterns and Price Action
7. Current Market Assessment
8. Scenario Analysis (2-4 scenarios with probabilities)
9. Summary
10. Disclaimer

**File Naming Convention**: Save each analysis as `[SYMBOL]_technical_analysis_[YYYY-MM-DD].md`

Example: `SPY_technical_analysis_2025-11-02.md`

### Step 6: Repeat for Multiple Charts

If multiple charts are provided:

1. Complete the full analysis workflow (Steps 3-5) for the first chart
2. Save the analysis report
3. Proceed to the next chart
4. Repeat until all charts have been analyzed and documented

Do not batch analyses. Complete and save each report before moving to the next chart.

---

## 6. Resources

**References:**

- `skills/technical-analyst/references/technical_analysis_framework.md`
