---
name: technical-analyst
description: This skill should be used when analyzing weekly price charts for stocks, stock indices, cryptocurrencies, or forex pairs. Use this skill when the user provides chart images and requests technical analysis, trend identification, support/resistance levels, scenario planning, or probability assessments based purely on chart data without consideration of news or fundamental factors.
---

# Technical Analyst

## Overview

This skill enables comprehensive technical analysis of weekly price charts. Analyze chart images to identify trends, support and resistance levels, moving average relationships, volume patterns, and develop probabilistic scenarios for future price movement. All analysis is conducted objectively using only chart data, without influence from news, fundamentals, or market sentiment.

## When to Use

- User provides weekly chart images (stocks, indices, crypto, forex) and requests technical analysis
- Need to identify trend direction, strength, and potential reversal points
- Looking for support/resistance levels and key price zones
- Want probabilistic scenario planning with specific price targets
- Require objective chart-based analysis without fundamental or news considerations

## Prerequisites

- **Chart Images**: User must provide weekly timeframe chart images for analysis
- **No API Keys Required**: This skill analyzes user-provided images; no external data fetches

## Output

This skill generates markdown analysis reports saved to the `reports/` directory:
- **File format**: `[SYMBOL]_technical_analysis_[YYYY-MM-DD].md`
- **Content**: Comprehensive analysis including trend, S/R levels, MA analysis, volume, patterns, and 2-4 probabilistic scenarios with targets and invalidation levels

## Core Principles

1. **Pure Chart Analysis**: Base all conclusions exclusively on technical data visible in the chart
2. **Systematic Approach**: Follow a structured methodology for each chart analysis
3. **Objective Assessment**: Avoid subjective bias; focus on observable patterns and data
4. **Probabilistic Scenarios**: Express future possibilities as probability-weighted scenarios
5. **Sequential Processing**: Analyze each chart individually and document findings immediately

## Analysis Workflow

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

## Quality Standards

### Objectivity Requirements

- Base all analysis strictly on observable chart data
- Avoid incorporating external information (news, fundamentals, sentiment)
- Do not use subjective language like "I think" or "I feel"
- Express uncertainty clearly when signals are ambiguous
- Present both bullish and bearish possibilities to avoid confirmation bias

### Completeness Requirements

- Address all sections of the analysis template
- Provide specific price levels for support, resistance, and targets
- Justify probability estimates with technical factors
- Include invalidation levels for each scenario
- Note any limitations or caveats to the analysis

### Clarity Requirements

- Use precise technical terminology correctly
- Write in clear, professional language
- Structure information logically
- Include specific price levels (not vague descriptions)
- Make scenarios distinct and mutually exclusive

## Example Usage Scenarios

**Example 1: Single Chart Analysis**
```
User: "Please analyze this weekly chart of the S&P 500"
[Provides chart image]

Analyst:
1. Confirms receipt of chart image
2. Reads technical_analysis_framework.md for methodology
3. Conducts systematic analysis (trend, S/R, MA, volume, patterns)
4. Develops 3 scenarios with probabilities (e.g., 55% bullish continuation, 30% consolidation, 15% reversal)
5. Generates comprehensive analysis report using template
6. Saves as SPY_technical_analysis_2025-11-02.md
```

**Example 2: Multiple Chart Analysis**
```
User: "Analyze these three charts: Bitcoin, Ethereum, and Nasdaq"
[Provides 3 chart images]

Analyst:
1. Confirms receipt of 3 charts
2. Reads technical_analysis_framework.md
3. Analyzes Bitcoin chart completely → Generates report → Saves as BTC_technical_analysis_2025-11-02.md
4. Analyzes Ethereum chart completely → Generates report → Saves as ETH_technical_analysis_2025-11-02.md
5. Analyzes Nasdaq chart completely → Generates report → Saves as NDX_technical_analysis_2025-11-02.md
6. Notifies user that all three analyses are complete
```

**Example 3: Focused Analysis Request**
```
User: "I'm particularly interested in whether this stock will break above resistance. Analyze the chart."
[Provides chart image]

Analyst:
1. Conducts full systematic analysis
2. Pays special attention to resistance levels and breakout probability
3. Develops scenarios with emphasis on breakout vs. rejection possibilities
4. Assigns probabilities based on volume, trend strength, and proximity to resistance
5. Generates complete report with focused scenario analysis
```

## Contrarian Confirmation Mode (Shapiro Step 3)

This is an ADDITIVE mode, separate from the pure chart-analysis workflow
above. It activates only on an explicit contrarian-confirmation request —
typically after `cot-contrarian-detector` (step 1) has flagged a market
crowded and, optionally, `news-reaction-failure-analyzer` (step 2) has
shown it failed to react to favorable news. A plain "analyze this chart"
request still runs the original workflow (Steps 1-6 above) unchanged.

### Purpose

Confirm whether the WEEKLY chart is showing price-action evidence that a
crowded market is reversing: a weekly key reversal, an intraweek failed
extreme, or a confirmed-then-rejected failed breakout — vetoed by a
continuation check (a new closing extreme in the crowd's direction more
recent than any signal found). See
`references/contrarian-confirmation-checklist.md` for the full,
word-for-word methodology shared by both chart mode and script mode.

### Inputs

- **Crowd direction**: `CROWDED_LONG` or `CROWDED_SHORT` — from the user,
  or from a prior `cot-contrarian-detector` report.
- **Chart image (primary)**: a user-supplied weekly chart, read the same
  way as the existing workflow, using the strict definitions below.
- **Script fallback (data-driven)**: `scripts/check_weekly_price_action.py`
  when no chart is supplied, or when an auditable, deterministic result is
  wanted instead of (or alongside) a visual read.

### The Three Checks + Swing Levels

1. **Weekly key reversal**: a new swing-lookback extreme (default 13
   weeks) followed by a close through the prior week's opposite level.
2. **Failed extreme**: an intraweek poke past the prior extreme-lookback
   level (default 52 weeks) that closes back through it the same week.
3. **Failed breakout**: a weekly CLOSING breakout past the prior
   extreme-lookback level, rejected (closed back through) within <=3
   subsequent weeks — `week_of` is the FAILURE week, never the breakout
   week.
4. **Continuation veto**: a new CLOSING extreme in the crowd's direction,
   strictly more recent than the newest triggered signal above, vetoes
   confirmation regardless of what triggered.
5. **Swing levels**: the nearest fractal swing high/low (5-week pivot,
   with a documented fallback) supplies `stop_reference` — the nearest
   swing high when fading a crowded LONG, the nearest swing low when
   fading a crowded SHORT.

Every comparison is a STRICT inequality; window truncation is
per-evaluated-week, not per-run. Full definitions, the direction-mirror
table, worked examples, and the confidence-HIGH rule are in
`references/contrarian-confirmation-checklist.md` — read it before
producing a chart-mode verdict, so chart and script judge identically.

### Output Contract

```yaml
symbol: BT
direction: CROWDED_LONG
mode: data # "chart" for a Claude chart-image read
verdict: CONFIRMED | NOT_CONFIRMED | INSUFFICIENT_DATA
confidence: HIGH | MEDIUM | LOW # LOW reserved, never emitted in v1
verdict_reason: key_reversal | failed_extreme | failed_breakout |
  continuation_intact | no_reversal_evidence |
  insufficient_weekly_bars | no_price_source | ...
checks:
  weekly_key_reversal:
    { triggered, week_of, swing_window_weeks_used,
      extreme_window_weeks_used, is_full_window_extreme, detail }
  failed_extreme: { triggered, attempted_level, week_of, window_weeks_used, detail }
  failed_breakout: { triggered, breakout_level, week_of, window_weeks_used, detail }
  continuation: { new_closing_extreme_with_crowd, week_of, window_weeks_used }
swing_levels:
  nearest_swing_high: { price, week_of, fallback }
  nearest_swing_low: { price, week_of, fallback }
  stop_reference: 0.0
weekly_bars_used: 52
last_completed_week: 2026-07-06
handoff: # consumed by contrarian-setup-gate (#241)
  price_action: { verdict, confidence, stop_reference, report_path }
run_context:
  {
    price_symbol,
    price_source,
    proxy_used,
    as_of,
    lookbacks,
    recency,
    min_weeks,
    detector_json,
    detector_age_days,
    schema_version,
  }
```

**Invariant**: `checks` (and `swing_levels`) is `null` whenever
`verdict: INSUFFICIENT_DATA` — regardless of the specific reason
(`no_price_source`, `insufficient_weekly_bars`, a detector-json refusal,
...). A downstream consumer can check `verdict` alone before deciding
whether `checks.*` is safe to read, without branching on
`verdict_reason`.

**File naming**: `ta_confirmation_<SYMBOL>_<as-of>.json` and
`ta_confirmation_<SYMBOL>_<as-of>.md`, saved to `reports/`.

### Chart-Primary, Script-Fallback

Chart images remain the PRIMARY input, consistent with this skill's
identity. Run the script instead of (or alongside) a chart read when no
chart is supplied, or when an auditable, deterministic result is
preferred:

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

The script fetches weekly-resampled OHLC via a documented futures-to-ETF
fallback chain (see the module docstring in
`scripts/check_weekly_price_action.py`), truncates daily bars to `--as-of`
BEFORE resampling (no lookahead), and fails closed to
`INSUFFICIENT_DATA` — never a crash — on an unreadable (missing file),
syntactically invalid, stale, or structurally malformed `--detector-json`,
too little price history (`--min-weeks`, default 30), or no usable price
source.

### Conservative Disagreement Rule

If both chart mode and script mode produce a result for the same
symbol/direction and their verdicts DISAGREE, the final verdict is
**`NOT_CONFIRMED`** (`verdict_reason: mode_disagreement`), with both
sub-results attached for review — never silently prefer one mode. If one
mode is `INSUFFICIENT_DATA` and the other is a clean verdict, the clean
verdict stands.

### Guardrails

- **Verdict-only — never a trade recommendation on its own.** This
  confirms step 3 of 5 (Shapiro's process). Entry and exit planning are
  still manual and still required; position sizing belongs to
  `position-sizer` / `futures-position-sizer`, not this mode.
- **`INSUFFICIENT_DATA` never advances the pipeline** — fail-closed on
  every degraded input, always exits 0 with a report written.
- **Weekly timeframe only.**
- **The existing chart-analysis workflow above is unchanged** — this mode
  only activates on an explicit contrarian-confirmation request.
- **A single-signal MEDIUM verdict is deliberately weak evidence** — see
  the Confidence section of `references/contrarian-confirmation-checklist.md`.

## Resources

This skill includes the following bundled resources:

### references/technical_analysis_framework.md

Comprehensive methodology for technical analysis including:
- Trend analysis criteria and classification
- Support and resistance identification techniques
- Moving average interpretation guidelines
- Volume analysis principles
- Chart pattern recognition
- Scenario development and probability assignment framework
- Objectivity and discipline reminders

**Usage**: Read this file before conducting analysis to ensure systematic, objective approach.

### assets/analysis_template.md

Structured template for technical analysis reports with all required sections.

**Usage**: Use this template structure for every analysis report. Copy the format and populate with specific findings for each chart.

### references/contrarian-confirmation-checklist.md

Full methodology for Contrarian Confirmation Mode (Shapiro Step 3): direction
convention, window/truncation rules, the 3 signal checks + continuation
veto, swing-level (fractal pivot) rules, verdict synthesis, confidence
rules, the output contract, a chart-mode walkthrough, and the conservative
disagreement rule.

**Usage**: Read this file before producing a Contrarian Confirmation Mode
verdict — chart mode and `scripts/check_weekly_price_action.py` must judge
identically, so the same strict definitions apply to both.

### scripts/check_weekly_price_action.py

Data-driven fallback CLI for Contrarian Confirmation Mode. Fetches
weekly-resampled OHLC (documented futures-to-ETF fallback chain,
`--as-of` information cutoff applied before resampling), runs the 3
signal checks + continuation veto + swing-level detection, and writes
`ta_confirmation_<SYMBOL>_<as-of>.json`/`.md` to `reports/`.

**Usage**: Run when no chart image is supplied, or when an auditable,
deterministic result is wanted. See the Contrarian Confirmation Mode
section above for invocation examples.
