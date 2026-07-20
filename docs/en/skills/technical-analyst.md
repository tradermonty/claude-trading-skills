---
layout: default
title: "Technical Analyst"
grand_parent: English
parent: Skill Guides
nav_order: 42
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

## 2. Prerequisites

- Image-based chart analysis
- Python 3.9+ recommended

---

## 3. Quick Start

```bash
Read: references/technical_analysis_framework.md
```

---

## 4. Workflow

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

## 5. Contrarian Confirmation Mode (Shapiro Step 3)

This is an ADDITIVE mode, separate from the pure chart-analysis workflow above. It activates only on an explicit contrarian-confirmation request -- typically after `cot-contrarian-detector` (step 1) has flagged a market crowded and, optionally, `news-reaction-failure-analyzer` (step 2) has shown it failed to react to favorable news. A plain "analyze this chart" request still runs the original workflow (Steps 1-6 above) unchanged.

### Purpose

Confirm whether the weekly chart shows price-action evidence that a crowded market is reversing: a weekly key reversal, an intraweek failed extreme, or a confirmed-then-rejected failed breakout, all vetoed by a continuation check (a new closing extreme in the crowd's direction more recent than any signal found). See `references/contrarian-confirmation-checklist.md` for the full methodology, shared word-for-word by both chart mode and script mode.

### The Three Checks + Swing Levels

1. **Weekly key reversal** -- a new swing-lookback extreme (default 13 weeks) followed by a close through the prior week's opposite level.
2. **Failed extreme** -- an intraweek poke past the prior extreme-lookback level (default 52 weeks) that closes back through it the same week.
3. **Failed breakout** -- a weekly closing breakout past the prior extreme-lookback level, rejected within <=3 subsequent weeks; `week_of` is the FAILURE week, never the breakout week.
4. **Continuation veto** -- a new closing extreme in the crowd's direction, more recent than the newest triggered signal, vetoes confirmation regardless of what triggered.
5. **Swing levels** -- the nearest fractal swing high/low (5-week pivot, with a documented fallback) supplies `stop_reference`.

Every comparison is a strict inequality; window truncation is per-evaluated-week, not per-run.

### Chart-Primary, Script-Fallback

Chart images remain the primary input. Run the script instead of (or alongside) a chart read when no chart is supplied, or an auditable, deterministic result is preferred:

```bash
python3 skills/technical-analyst/scripts/check_weekly_price_action.py \
  --symbol BT --direction CROWDED_LONG --as-of 2026-07-15 \
  --output-dir reports/
```

Or resolve direction from a `cot-contrarian-detector` report directly:

```bash
python3 skills/technical-analyst/scripts/check_weekly_price_action.py \
  --symbol BT --detector-json reports/cot_crowding_2026-07-12.json \
  --as-of 2026-07-15 --output-dir reports/
```

The script fetches weekly-resampled OHLC via a documented futures-to-ETF fallback chain, truncates daily bars to `--as-of` before resampling (no lookahead), and fails closed to `INSUFFICIENT_DATA` -- never a crash -- on a missing/stale/malformed `--detector-json`, too little price history (`--min-weeks`, default 30), or no usable price source.

### Output

- **JSON/Markdown**: `ta_confirmation_<SYMBOL>_<as-of>.json` / `.md`, saved to `reports/`.
- **verdict**: `CONFIRMED` / `NOT_CONFIRMED` / `INSUFFICIENT_DATA`, with `confidence` (`HIGH`/`MEDIUM`) and a `verdict_reason`.
- **handoff**: a `price_action` block (`verdict`, `confidence`, `stop_reference`, `report_path`) intended for `contrarian-setup-gate` (#241, not yet built).

### Guardrails

- Verdict-only -- never a trade recommendation on its own; entry/exit planning and position sizing belong to downstream skills.
- `INSUFFICIENT_DATA` never advances the pipeline -- fail-closed on every degraded input.
- Weekly timeframe only.
- The existing chart-analysis workflow above is unchanged; this mode only activates on an explicit contrarian-confirmation request.
- A single-signal `MEDIUM` verdict is deliberately weak evidence -- see the Confidence section of `references/contrarian-confirmation-checklist.md`.

---

## 6. Resources

**References:**

- `skills/technical-analyst/references/technical_analysis_framework.md`
- `skills/technical-analyst/references/contrarian-confirmation-checklist.md`

**Scripts:**

- `skills/technical-analyst/scripts/check_weekly_price_action.py`
