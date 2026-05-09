---
name: scenario-analyzer
description: |
  Skill that analyzes 18-month scenarios from a news headline.
  Runs the main analysis with the scenario-analyst agent and obtains a second
  opinion with the strategy-reviewer agent. Generates a comprehensive English
  report covering 1st/2nd/3rd-order impacts, recommended stocks, and review.
  Example: /scenario-analyzer "Fed raises rates by 50bp"
  Triggers: news analysis, scenario analysis, 18-month outlook, medium-to-long-term investment strategy
---

# Scenario Analyzer

## Overview

This skill analyzes medium-to-long-term (18-month) investment scenarios starting from a news headline.
It sequentially calls two specialist agents (`scenario-analyst` and `strategy-reviewer`) and
produces a comprehensive report that combines multi-angle analysis with critical review.

## When to Use This Skill

Use this skill when:

- You want to analyze the medium-to-long-term investment impact of a news headline
- You want to construct multiple scenarios out to 18 months
- You want sector / stock impact organized by 1st / 2nd / 3rd-order effects
- You need a comprehensive analysis that includes a second opinion
- You need an English-language report

**Examples:**
```
/scenario-analyzer "Fed raises interest rates by 50bp, signals more hikes ahead"
/scenario-analyzer "China announces new tariffs on US semiconductors"
/scenario-analyzer "OPEC+ agrees to cut oil production by 2 million barrels per day"
```

## Prerequisites

- **API Keys**: None (only WebSearch / WebFetch are used)
- **MCP Servers**: None
- **Dependencies**: `scenario-analyst` and `strategy-reviewer` agents must be available via the Task tool

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Skill (Orchestrator)                              │
│                                                                      │
│  Phase 1: Preparation                                                │
│  ├─ Headline parsing                                                 │
│  ├─ Event type classification                                        │
│  └─ Reference loading                                                │
│                                                                      │
│  Phase 2: Agent invocation                                           │
│  ├─ scenario-analyst (main analysis)                                 │
│  └─ strategy-reviewer (second opinion)                               │
│                                                                      │
│  Phase 3: Integration / Report generation                            │
│  └─ reports/scenario_analysis_<topic>_YYYYMMDD.md                    │
└─────────────────────────────────────────────────────────────────────┘
```

## Workflow

### Phase 1: Preparation

#### Step 1.1: Headline Parsing

Parse the headline provided by the user.

1. **Confirm the headline**
   - Check whether a headline was passed as the argument
   - If not, ask the user to provide one

2. **Extract keywords**
   - Main entities (company / country / institution names)
   - Numerical data (rates, prices, quantities)
   - Actions (raise, cut, announce, agree, etc.)

#### Step 1.2: Event Type Classification

Classify the headline into one of the following categories:

| Category | Examples |
|----------|----------|
| Monetary policy | FOMC, ECB, BOJ, rate hikes, rate cuts, QE/QT |
| Geopolitics | Wars, sanctions, tariffs, trade friction |
| Regulation / Policy | Environmental rules, financial regulation, antitrust |
| Technology | AI, EV, renewables, semiconductors |
| Commodities | Crude oil, gold, copper, agricultural products |
| Corporate / M&A | Acquisitions, bankruptcies, earnings, industry restructuring |

#### Step 1.3: Reference Loading

Based on the event type, load relevant references:

```
Read references/headline_event_patterns.md
Read references/sector_sensitivity_matrix.md
Read references/scenario_playbooks.md
```

**Reference contents:**
- `headline_event_patterns.md`: Past event patterns and market reactions
- `sector_sensitivity_matrix.md`: Event × sector impact matrix
- `scenario_playbooks.md`: Scenario-construction templates and best practices

---

### Phase 2: Agent Invocation

#### Step 2.1: Invoke scenario-analyst

Use the Agent tool to invoke the main analysis agent.

```
Agent tool:
- subagent_type: "scenario-analyst"
- prompt: |
    Run an 18-month scenario analysis on the following headline.

    ## Target Headline
    [The input headline]

    ## Event Type
    [Classification result]

    ## Reference Information
    [Summary of the loaded references]

    ## Analysis Requirements
    1. Use WebSearch to gather related news from the past two weeks
    2. Build three scenarios — Base / Bull / Bear (probabilities sum to 100%)
    3. Analyze 1st / 2nd / 3rd-order impacts by sector
    4. Select 3-5 positive and 3-5 negative-impact stocks (US market only)
    5. Output everything in English
```

**Expected output:**
- List of related news articles
- Detailed Base / Bull / Bear scenarios
- Sector impact analysis (1st / 2nd / 3rd order)
- Recommended stock list

#### Step 2.2: Invoke strategy-reviewer

After receiving the scenario-analyst's output, invoke the review agent.

```
Agent tool:
- subagent_type: "strategy-reviewer"
- prompt: |
    Please review the following scenario analysis.

    ## Target Headline
    [The input headline]

    ## Analysis Result
    [Full output from scenario-analyst]

    ## Review Requirements
    Review from the following angles:
    1. Overlooked sectors / stocks
    2. Reasonableness of scenario probability allocations
    3. Logical consistency of impact analysis
    4. Detection of optimism / pessimism bias
    5. Alternative scenario proposals
    6. Realism of the timeline

    Provide constructive, concrete feedback in English.
```

**Expected output:**
- Identified blind spots
- Comments on scenario probabilities
- Bias findings
- Alternative scenario proposals
- Final recommendations

---

### Phase 3: Integration / Report Generation

#### Step 3.1: Integrate Results

Combine the outputs of both agents and craft the final investment judgment.

**Integration points:**
1. Address blind spots flagged in the review
2. Adjust probability allocations if needed
3. Form a final judgment that accounts for biases
4. Lay out a concrete action plan

#### Step 3.2: Generate the Report

Generate the final report in the format below and save it to a file.

**Save location:** `reports/scenario_analysis_<topic>_YYYYMMDD.md`

```markdown
# Headline Scenario Analysis Report

**Analysis date**: YYYY-MM-DD HH:MM
**Target headline**: [The input headline]
**Event type**: [Classification]

---

## 1. Related News Articles
[News list gathered by scenario-analyst]

## 2. Scenario Overview (out to 18 months)

### Base Case (XX% probability)
[Scenario detail]

### Bull Case (XX% probability)
[Scenario detail]

### Bear Case (XX% probability)
[Scenario detail]

## 3. Sector / Industry Impact

### 1st-Order Impact (Direct)
[Impact table]

### 2nd-Order Impact (Value chain / related industries)
[Impact table]

### 3rd-Order Impact (Macro / regulatory / technology)
[Impact table]

## 4. Stocks Likely to Benefit (3-5 names)
[Stock table]

## 5. Stocks Likely to Be Hurt (3-5 names)
[Stock table]

## 6. Second-Opinion Review
[Output from strategy-reviewer]

## 7. Final Investment Judgment / Implications

### Recommended Actions
[Concrete actions reflecting the review]

### Risk Factors
[List of key risks]

### Monitoring Points
[Indicators / events to track]

---
**Generated by**: scenario-analyzer skill
**Agents**: scenario-analyst, strategy-reviewer
```

#### Step 3.3: Save the Report

1. Create the `reports/` directory if it does not exist
2. Save as `scenario_analysis_<topic>_YYYYMMDD.md` (e.g., `scenario_analysis_venezuela_20260104.md`)
3. Notify the user when the file is saved
4. **Do not save directly in the project root**

---

## Output

This skill produces the following file:

| File | Format | Description |
|------|--------|-------------|
| `reports/scenario_analysis_<topic>_YYYYMMDD.md` | Markdown | Comprehensive scenario analysis report |

**Output contents:**
- List of related news articles
- Three scenarios — Base / Bull / Bear (with probability allocations)
- Sector impact analysis (1st / 2nd / 3rd order)
- Positive / negative stock recommendations
- Second-opinion review
- Final investment judgment / implications

## Resources

### References
- `references/headline_event_patterns.md` — Event patterns and market reactions
- `references/sector_sensitivity_matrix.md` — Sector sensitivity matrix
- `references/scenario_playbooks.md` — Scenario-construction templates

### Agents
- `scenario-analyst` — Main scenario analysis
- `strategy-reviewer` — Second-opinion review

---

## Important Notes

### Language
- All analysis and output is in **English**
- Stock tickers remain in their standard ticker form

### Target Market
- Stock selection is limited to **US-listed equities only**
- Includes ADRs

### Time Horizon
- Scenarios cover an **18-month** window
- Described in three phases: 0-6 / 6-12 / 12-18 months

### Probability Allocation
- Base + Bull + Bear = **100%**
- Document the rationale alongside each probability

### Second Opinion
- **Required** — always invoke strategy-reviewer
- Reflect the review findings in the final judgment

### Output Location (Important)
- **Always** save under the `reports/` directory
- Path: `reports/scenario_analysis_<topic>_YYYYMMDD.md`
- Example: `reports/scenario_analysis_fed_rate_hike_20260104.md`
- Create the `reports/` directory if it does not exist
- **Never save directly in the project root**

---

## Quality Checklist

Before completing the report, verify:

- [ ] Was the headline parsed correctly?
- [ ] Is the event type classification appropriate?
- [ ] Do the three scenarios sum to 100%?
- [ ] Are the 1st / 2nd / 3rd-order impacts logically connected?
- [ ] Does each stock selection have concrete rationale?
- [ ] Is the strategy-reviewer's review included?
- [ ] Does the final judgment incorporate the review?
- [ ] Was the report saved to the correct path?
