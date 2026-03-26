---
name: sector-analyst
description: This skill should be used when analyzing sector rotation patterns and market cycle positioning. It fetches sector uptrend data from CSV (no API key required) and optionally accepts chart images for supplementary analysis. Use this skill when the user requests sector rotation analysis, cyclical vs defensive assessment, overbought/oversold identification, or market cycle phase estimation. All analysis and output are conducted in English.
---

# Sector Analyst

## Overview

This skill enables comprehensive analysis of sector rotation and market cycle positioning by fetching uptrend ratio data from TraderMonty's public CSV dataset. It ranks sectors, calculates cyclical vs defensive risk regime scores, identifies overbought/oversold conditions, and estimates the current market cycle phase. Chart images can optionally supplement the data-driven analysis with industry-level detail.

## When to Use This Skill

Use this skill when:
- User requests sector rotation analysis (no chart images required)
- User asks about cyclical vs defensive positioning
- User wants to know which sectors are overbought or oversold
- User requests market cycle phase estimation
- User provides sector performance charts for supplementary analysis
- User asks for sector-based scenario analysis or predictions

Example user requests:
- "Run a sector rotation analysis"
- "Which sectors are leading — cyclical or defensive?"
- "Are any sectors overbought right now?"
- "What phase of the market cycle are we in?"
- "Analyze these sector performance charts and tell me where we are in the market cycle"

## Prerequisites

- **Python 3.8+** with `requests` library (for CSV fetching)
- **No API keys required** — data is fetched from a public GitHub repository
- **Optional**: Sector performance chart images for supplementary analysis

## Data Source

Sector uptrend ratios are fetched from TraderMonty's public GitHub repository (no API key required):
- **Sector Summary**: `sector_summary.csv` — uptrend ratio, trend, slope, and status per sector
- **Freshness Check**: `uptrend_ratio_timeseries.csv` — max(date) used to verify data recency

## Running the Script

```bash
# Default: fetch CSV, print human-readable analysis
python3 scripts/analyze_sector_rotation.py

# JSON output
python3 scripts/analyze_sector_rotation.py --json

# Save to file
python3 scripts/analyze_sector_rotation.py --save --output-dir reports/
```

## Analysis Workflow

Follow this structured workflow:

### Step 1: CSV Data Collection

1. Run the analysis script: `python3 scripts/analyze_sector_rotation.py`
2. Extract from the output:
   - Sector ranking by uptrend ratio
   - Risk regime (cyclical vs defensive) and score
   - Overbought/oversold sectors
   - Cycle phase estimate and confidence level
3. If a data freshness warning appears, note it in the analysis

### Step 2: Market Cycle Assessment

Use the script's cycle phase estimate as a starting point:
- Read `references/sector_rotation.md` to access market cycle and sector rotation frameworks
- Compare the script's quantitative findings against expected patterns for each cycle phase:
  - Early Cycle Recovery
  - Mid Cycle Expansion
  - Late Cycle
  - Recession
- Add qualitative interpretation informed by the knowledge base

If chart images are provided, use them to supplement with industry-level detail:
- Extract industry-level performance data from chart images
- Compare 1-week vs 1-month performance for trend consistency
- Note specific industries showing strength or weakness within sectors

### Step 3: Current Situation Analysis

Synthesize observations into an objective assessment:
- State which market cycle phase current performance most closely resembles
- Highlight supporting evidence (which sectors/industries confirm this view)
- Note any contradictory signals or unusual patterns
- Assess confidence level based on consistency of signals

Use data-driven language and specific references to performance figures.

### Step 4: Scenario Development

Based on sector rotation principles and current positioning, develop 2-4 potential scenarios for the next phase:

For each scenario:
- Describe the market cycle transition
- Identify which sectors would likely outperform
- Identify which sectors would likely underperform
- Specify the catalysts or conditions that would confirm this scenario
- Assign a probability (see Probability Assessment Framework in sector_rotation.md)

Scenarios should range from most likely (highest probability) to alternative/contrarian scenarios.

### Step 5: Output Generation

Create a structured Markdown document with the following sections:

**Required Sections:**
1. **Executive Summary**: 2-3 sentence overview of key findings
2. **Current Situation**: Detailed analysis of current performance patterns and market cycle positioning
3. **Supporting Evidence**: Specific sector and industry performance data supporting the cycle assessment
4. **Scenario Analysis**: 2-4 scenarios with descriptions and probability assignments
5. **Recommended Positioning**: Strategic and tactical positioning recommendations based on scenario probabilities
6. **Key Risks**: Notable risks or contradictory signals to monitor

## Output Format

Save analysis results as a Markdown file with naming convention: `sector_analysis_YYYY-MM-DD.md`

Use this structure:

```markdown
# Sector Performance Analysis - [Date]

## Executive Summary

[2-3 sentences summarizing key findings]

## Current Situation

### Market Cycle Assessment
[Which cycle phase and why]

### Performance Patterns Observed

#### 1-Week Performance
[Analysis of recent performance]

#### 1-Month Performance
[Analysis of medium-term trends]

#### Sector-Level Analysis
[Detailed breakdown by sector]

#### Industry-Level Analysis
[Notable industry-specific observations]

## Supporting Evidence

### Confirming Signals
- [List data points supporting cycle assessment]

### Contradictory Signals
- [List any conflicting indicators]

## Scenario Analysis

### Scenario 1: [Name] (Probability: XX%)
**Description**: [What happens]
**Outperformers**: [Sectors/industries]
**Underperformers**: [Sectors/industries]
**Catalysts**: [What would confirm this scenario]

### Scenario 2: [Name] (Probability: XX%)
[Repeat structure]

[Additional scenarios as appropriate]

## Recommended Positioning

### Strategic Positioning (Medium-term)
[Sector allocation recommendations]

### Tactical Positioning (Short-term)
[Specific adjustments or opportunities]

## Key Risks and Monitoring Points

[What to watch that could invalidate the analysis]

---
*Analysis Date: [Date]*
*Data Period: [Timeframe of charts analyzed]*
```

## Key Analysis Principles

When conducting analysis:

1. **Objectivity First**: Let the data guide conclusions, not preconceptions
2. **Probabilistic Thinking**: Express uncertainty through probability ranges
3. **Multiple Timeframes**: Compare 1-week and 1-month data for trend confirmation
4. **Relative Performance**: Focus on relative strength, not absolute returns
5. **Breadth Matters**: Broad-based moves are more significant than isolated movements
6. **No Absolutes**: Markets rarely follow textbook patterns exactly
7. **Historical Context**: Reference typical rotation patterns but acknowledge uniqueness

## Probability Guidelines

Apply these probability ranges based on evidence strength:

- **70-85%**: Strong evidence with multiple confirming signals across sectors and timeframes
- **50-70%**: Moderate evidence with some confirming signals but mixed indicators
- **30-50%**: Weak evidence with limited or conflicting signals
- **15-30%**: Speculative scenario contrary to current indicators but possible

Total probabilities across all scenarios should sum to approximately 100%.

## Resources

### scripts/
- `analyze_sector_rotation.py` - Fetches sector CSV data and produces sector rankings, risk regime scoring, overbought/oversold flags, and cycle phase estimation. No API key required.

### references/
- `sector_rotation.md` - Comprehensive knowledge base covering market cycle phases, typical sector performance patterns, and probability assessment frameworks

### assets/
Sample charts demonstrating the expected input format for optional image-based analysis:
- `sector_performance.jpeg` - Example sector-level performance chart (1-week and 1-month)
- `industory_performance_1.jpeg` - Example industry performance chart (outperformers)
- `industory_performance_2.jpeg` - Example industry performance chart (underperformers)

## Important Notes

- All analysis thinking should be conducted in English
- Output Markdown files must be in English
- Reference the sector rotation knowledge base for each analysis
- Maintain objectivity and avoid confirmation bias
- Update probability assessments if new data becomes available
- Chart images are optional; CSV data provides the primary analysis input
- The script uses the same sector classification as uptrend-analyzer for consistency
