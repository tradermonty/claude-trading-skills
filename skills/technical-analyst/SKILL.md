---
name: technical-analyst
description: "Use when the user provides weekly price chart images for stocks, stock indices, cryptocurrencies, or forex pairs and requests technical analysis. Triggers on requests to identify trends, draw trendlines, calculate moving average crossovers, map support/resistance zones, analyze volume patterns, recognize chart patterns (head-and-shoulders, flags, triangles), or develop probability-weighted price scenarios. Performs pure chart-data analysis without news or fundamental factors."
---

# Technical Analyst

Analyze weekly price chart images to identify trends, support/resistance levels, moving average relationships, volume patterns, and chart formations. Develop probability-weighted scenarios for future price movement using only visible chart data.

## Analysis Workflow

### Step 1: Receive and Confirm Charts

1. Confirm receipt of all chart images
2. Identify the number of charts and any user-specified focus areas
3. Process charts sequentially -- complete each analysis before starting the next

### Step 2: Load Framework

Read the technical analysis methodology before beginning:

```
Read: references/technical_analysis_framework.md
```

### Step 3: Systematic Analysis

For each chart, analyze these elements in order:

**Trend** -- Direction (up/down/sideways), strength (strong/moderate/weak), duration, higher-highs/lows or lower-highs/lows pattern, exhaustion signals.

**Support & Resistance** -- Horizontal S/R levels, trendline S/R, role reversals, confluence zones where multiple levels align.

**Moving Averages** -- Price position vs 20/50/200-week MAs, alignment (bullish/bearish/neutral), slope direction, crossovers, dynamic S/R behavior.

**Volume** -- Overall trend, spikes at key levels or breakouts, price-volume confirmation/divergence, climax or exhaustion patterns.

**Chart Patterns & Price Action** -- Reversal patterns (hammers, engulfing), continuation patterns (flags, triangles), significant candlestick formations, recent breakouts/breakdowns.

**Synthesis** -- Integrate all elements into a coherent assessment. Identify the dominant factors, note conflicting signals, and establish the key levels that determine future direction.

#### Example Analysis Output (abbreviated)

```markdown
## Trend Analysis
SPY is in a **moderate uptrend** on the weekly chart. Price has formed a
series of higher highs ($585 → $598) and higher lows ($562 → $571) since
October. However, momentum is decelerating -- the most recent weekly candle
shows a smaller body with an upper wick near $598 resistance.

## Key Levels
- **Resistance**: $598 (double top), $610 (measured move target)
- **Support**: $571 (recent swing low), $558 (50-week MA, rising)
```

### Step 4: Develop Scenarios

Create 2-4 probability-weighted scenarios for each chart:

| Element | Required |
|---------|----------|
| Scenario name | Descriptive title (e.g., "Bull Case: Breakout Above $598") |
| Probability | Percentage based on technical evidence (all must sum to 100%) |
| Description | How the scenario unfolds |
| Supporting factors | 2-3 technical evidence points |
| Target levels | Expected price levels |
| Invalidation level | Specific price that negates this scenario |

Typical distribution: Base case 40-60%, Bull case 20-40%, Bear case 20-40%, Alternative 5-15%. Adjust based on weight of technical evidence.

### Step 5: Generate Report

Create a markdown report for each chart using the template:

```
Read and use as template: assets/analysis_template.md
```

Required sections: Chart Overview, Trend Analysis, Support & Resistance, Moving Average Analysis, Volume Analysis, Chart Patterns, Current Assessment, Scenario Analysis (2-4 with probabilities), Summary, Disclaimer.

**File naming**: `[SYMBOL]_technical_analysis_[YYYY-MM-DD].md` (e.g., `SPY_technical_analysis_2025-11-02.md`)

### Step 6: Multiple Charts

If multiple charts are provided, complete Steps 3-5 fully for each chart before proceeding to the next. Do not batch analyses.

## Constraints

- Base all conclusions exclusively on observable chart data -- no news, fundamentals, or sentiment
- Express uncertainty clearly when signals conflict
- Present both bullish and bearish possibilities to avoid confirmation bias
- Provide specific price levels, not vague descriptions
- Make scenarios distinct and mutually exclusive
- Include invalidation levels for every scenario

## Resources

- **references/technical_analysis_framework.md** -- Comprehensive methodology covering trend classification, S/R identification, MA interpretation, volume analysis, chart pattern recognition, and scenario probability assignment. Read before each analysis session.
- **assets/analysis_template.md** -- Structured report template with all required sections. Use for every analysis report.
