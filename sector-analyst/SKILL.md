---
name: sector-analyst
description: This skill should be used when analyzing sector and industry performance charts to assess market positioning and rotation patterns. Use this skill when the user provides performance chart images (1-week or 1-month timeframes) for sectors or industries and requests market cycle assessment, sector rotation analysis, or strategic positioning recommendations based on performance data. All analysis and output are conducted in English.
---

# Sector Analyst

## Overview

This skill enables comprehensive analysis of sector and industry performance charts to identify market cycle positioning and predict likely rotation scenarios. The analysis combines observed performance data with established sector rotation principles to provide objective market assessment and probabilistic scenario forecasting.

## When to Use This Skill

Use this skill when:
- User provides sector performance charts (typically 1-week and 1-month timeframes)
- User provides industry performance charts showing relative performance data
- User requests analysis of current market cycle positioning
- User asks for sector rotation assessment or predictions
- User needs probability-weighted scenarios for market positioning

Example user requests:
- "Analyze these sector performance charts and tell me where we are in the market cycle"
- "Based on these performance charts, what sectors should outperform next?"
- "What's the probability of a defensive rotation based on this data?"
- "Review these sector and industry charts and provide scenario analysis"

## Analysis Workflow

Follow this structured workflow when analyzing sector/industry performance charts:

### Step 1: Data Collection and Observation

First, carefully examine all provided chart images to extract:
- **Sector-level performance**: Identify which sectors (Technology, Financials, Consumer Discretionary, etc.) are outperforming/underperforming
- **Industry-level performance**: Note specific industries showing strength or weakness
- **Timeframe comparison**: Compare 1-week vs 1-month performance to identify trend consistency or divergence
- **Magnitude of moves**: Assess the size of relative performance differences
- **Breadth of movement**: Determine if performance is concentrated or broad-based

Think in English while analyzing the charts. Document specific numerical performance figures for key sectors and industries.

### Step 2: Market Cycle Assessment

Load the sector rotation knowledge base to inform analysis:
- Read `references/sector_rotation.md` to access market cycle and sector rotation frameworks
- Compare observed performance patterns against expected patterns for each cycle phase:
  - Early Cycle Recovery
  - Mid Cycle Expansion
  - Late Cycle
  - Recession

Identify which cycle phase best matches current observations by:
- Mapping outperforming sectors to typical cycle leaders
- Mapping underperforming sectors to typical cycle laggards
- Assessing consistency across multiple sectors
- Evaluating alignment with defensive vs cyclical sector performance

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

### references/
- `sector_rotation.md` - Comprehensive knowledge base covering market cycle phases, typical sector performance patterns, and probability assessment frameworks

### assets/
Sample charts demonstrating the expected input format:
- `sector_performance.jpeg` - Example sector-level performance chart (1-week and 1-month)
- `industory_performance_1.jpeg` - Example industry performance chart (outperformers)
- `industory_performance_2.jpeg` - Example industry performance chart (underperformers)

These samples illustrate the type of visual data this skill analyzes. User-provided charts may vary in format but should contain similar relative performance information.

## Important Notes

- All analysis thinking should be conducted in English
- Output Markdown files must be in English
- Reference the sector rotation knowledge base for each analysis
- Maintain objectivity and avoid confirmation bias
- Update probability assessments if new data becomes available
- Charts typically show performance over 1-week and 1-month periods
