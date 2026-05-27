---
layout: default
title: "Sector Analyst"
grand_parent: English
parent: Skill Guides
nav_order: 49
lang_peer: /ja/skills/sector-analyst/
permalink: /en/skills/sector-analyst/
---

# Sector Analyst
{: .no_toc }

This skill should be used when analyzing sector rotation patterns and market cycle positioning. It fetches sector uptrend data from CSV (no API key required) and optionally accepts chart images for supplementary analysis. Use this skill when the user requests sector rotation analysis, cyclical vs defensive assessment, overbought/oversold identification, or market cycle phase estimation. All analysis and output are conducted in English.
{: .fs-6 .fw-300 }

<span class="badge badge-free">No API</span>

[Download Skill Package (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/sector-analyst.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/sector-analyst){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

This skill enables comprehensive analysis of sector rotation and market cycle positioning by fetching uptrend ratio data from TraderMonty's public CSV dataset. It ranks sectors, calculates cyclical vs defensive risk regime scores, identifies overbought/oversold conditions, and estimates the current market cycle phase. Chart images can optionally supplement the data-driven analysis with industry-level detail.

---

## 2. When to Use

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

---

## 3. Prerequisites

- **Python 3.8+** with `requests` library (for CSV fetching)
- **No API keys required** — data is fetched from a public GitHub repository
- **Optional**: Sector performance chart images for supplementary analysis

---

## 4. Quick Start

Follow this structured workflow:

### Step 1: CSV Data Collection

---

## 5. Workflow

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

---

## 6. Resources

**References:**

- `skills/sector-analyst/references/sector_rotation.md`

**Scripts:**

- `skills/sector-analyst/scripts/analyze_sector_rotation.py`
