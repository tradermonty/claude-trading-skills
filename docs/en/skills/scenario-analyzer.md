---
layout: default
title: "Scenario Analyzer"
grand_parent: English
parent: Skill Guides
nav_order: 54
lang_peer: /ja/skills/scenario-analyzer/
permalink: /en/skills/scenario-analyzer/
generated: true
---

# Scenario Analyzer
{: .no_toc }

Skill that analyzes 18-month scenarios from a news headline.
Runs the primary analysis with the scenario-analyst agent and obtains a
second opinion with the strategy-reviewer agent.
Generates a comprehensive English report covering 1st/2nd/3rd-order
impacts, recommended stocks, and a critical review.
Example: /scenario-analyzer "Fed raises rates by 50bp"
Triggers: news analysis, scenario analysis, 18-month outlook,
medium-to-long-term investment strategy

{: .fs-6 .fw-300 }

<span class="badge badge-free">No API</span>

[Download Skill Package (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/scenario-analyzer.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/scenario-analyzer){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

This skill analyzes medium-to-long-term (18-month) investment scenarios
starting from a news headline. It invokes two specialized agents in sequence
(`scenario-analyst` and `strategy-reviewer`) and integrates multi-angle
analysis with a critical review into a comprehensive report.

---

## 2. When to Use

Use this skill when:

- You want to analyze the medium-to-long-term investment impact of a news headline
- You want to construct multiple 18-month scenarios
- You want sector/stock impacts organized into 1st/2nd/3rd-order effects
- You need a comprehensive analysis that includes a second opinion

**Examples:**
```
/scenario-analyzer "Fed raises interest rates by 50bp, signals more hikes ahead"
/scenario-analyzer "China announces new tariffs on US semiconductors"
/scenario-analyzer "OPEC+ agrees to cut oil production by 2 million barrels per day"
```

---

## 3. Prerequisites

- **API Keys**: None. WebSearch/WebFetch drive the qualitative analysis; the
  optional `scripts/polymarket_odds.py` uses the **free, keyless Polymarket
  Gamma API** to add quantified forward base rates.
- **MCP Servers**: None
- **Dependencies**: The scenario-analyst and strategy-reviewer agents must be available via the Task tool

---

## 4. Quick Start

```bash
Read references/headline_event_patterns.md
Read references/sector_sensitivity_matrix.md
Read references/scenario_playbooks.md
```

---

## 5. Workflow

### Phase 1: Preparation

#### Step 1.1: Headline Parsing

Parse the headline provided by the user.

1. **Headline check**
   - Confirm a headline was passed as an argument
   - If not provided, ask the user for input

2. **Keyword extraction**
   - Key entities (company names, country names, institution names)
   - Numeric data (rates, prices, quantities)
   - Actions (raise, cut, announce, agree, etc.)

#### Step 1.2: Event Type Classification

Classify the headline into one of the following categories:

| Category | Examples |
|----------|----------|
| Monetary Policy | FOMC, ECB, BOJ, rate hike, rate cut, QE/QT |
| Geopolitics | War, sanctions, tariffs, trade friction |
| Regulation & Policy | Environmental regulation, financial regulation, antitrust |
| Technology | AI, EV, renewables, semiconductors |
| Commodities | Crude oil, gold, copper, agricultural products |
| Corporate & M&A | Acquisitions, bankruptcies, earnings, industry restructuring |

#### Step 1.3: Reference Loading

Based on the event type, load the relevant references:

```
Read references/headline_event_patterns.md
Read references/sector_sensitivity_matrix.md
Read references/scenario_playbooks.md
```

**Reference contents:**
- `headline_event_patterns.md`: Historical event patterns and market reactions
- `sector_sensitivity_matrix.md`: Event × sector impact-magnitude matrix
- `scenario_playbooks.md`: Scenario-construction templates and best practices

#### Step 1.4: Fetch Prediction-Market Base Rates (Optional but Recommended)

For monetary-policy, geopolitical, election, macro, or crypto headlines, pull
**live market-implied probabilities** from Polymarket so the scenario
probabilities are anchored to a quantified base rate the crowd is actually
pricing — not just qualitative judgment. This uses the **free, keyless
Polymarket Gamma API**.

```bash
# Derive 1-3 topic keywords from the parsed headline (e.g. "Fed rate cut",
# "US recession 2026", "US government shutdown"). Writes JSON + markdown to reports/.
python3 skills/scenario-analyzer/scripts/polymarket_odds.py "Fed rate cut" "US recession 2026"

# Offline / reproducible run against a saved Gamma payload:
python3 skills/scenario-analyzer/scripts/polymarket_odds.py "Fed rate cut" \
  --fixture skills/scenario-analyzer/scripts/tests/fixtures/gamma_search_fed.json --stdout
```

The script queries the Gamma `public-search` endpoint, keeps only **open,
forward-looking** markets (drops resolved/closed and past-dated ones), ranks
them by traded volume, and parses each market's `outcomePrices` JSON-string
array into implied probabilities (a "Yes" at 0.76 = **76%**). Each record
carries the implied probability, traded volume (depth), resolution date, and
1-week move.

**How to use the base rate:** treat a high-volume market probability as the
crowd's priced odds, then reconcile it with your Base/Bull/Bear allocation. If
Polymarket prices a 76% chance of a Fed cut but your Bull case (which assumes a
cut) sits at 20%, either the market or your scenario is mispriced — document the
divergence. Deeper markets (higher volume) deserve more weight; treat thin
markets as weak signals. Polymarket coverage is concentrated in macro,
political, geopolitical, and crypto events; a specific single-stock headline may
return no markets, in which case proceed without this input.

If the script reports a topic as unavailable (network error) or returns no
matches, proceed with the qualitative analysis unchanged.

---

### Phase 2: Agent Invocation

#### Step 2.1: Invoke scenario-analyst

Use the Agent tool to invoke the primary analysis agent.

```
Agent tool:
- subagent_type: "scenario-analyst"
- prompt: |
    Perform an 18-month scenario analysis for the following headline.

    ## Target Headline
    [the input headline]

    ## Event Type
    [classification result]

    ## Reference Information
    [summary of the loaded references]

    ## Prediction-Market Base Rates (if fetched in Step 1.4)
    [the ranked Polymarket implied probabilities: question, Yes%, volume, resolves]

    ## Analysis Requirements
    1. Use WebSearch to collect related news from the past 2 weeks
    2. Construct 3 scenarios — Base/Bull/Bear (probabilities sum to 100%),
       reconciling the allocation with the Polymarket base rates and flagging
       any material divergence
    3. Analyze 1st/2nd/3rd-order impacts by sector
    4. Select 3-5 positive- and 3-5 negative-impact stocks (US market only)
    5. Output everything in English
```

**Expected output:**
- List of related news articles
- Details of the 3 scenarios (Base/Bull/Bear)
- Sector impact analysis (1st/2nd/3rd-order)
- Stock recommendation list

#### Step 2.2: Invoke strategy-reviewer

Using the scenario-analyst's results, invoke the review agent.

```
Agent tool:
- subagent_type: "strategy-reviewer"
- prompt: |
    Review the following scenario analysis.

    ## Target Headline
    [the input headline]

    ## Analysis Result
    [the full scenario-analyst output]

    ## Review Requirements
    Review from the following angles:
    1. Overlooked sectors/stocks
    2. Validity of the scenario probability allocation
    3. Logical consistency of the impact analysis
    4. Detection of optimism/pessimism bias
    5. Proposal of alternative scenarios
    6. Realism of the timeline

    Output constructive and specific feedback in English.
```

**Expected output:**
- Pointing out blind spots
- Opinion on the scenario probabilities
- Pointing out bias
- Proposal of alternative scenarios
- Final recommendations

---

### Phase 3: Integration & Report Generation

#### Step 3.1: Integrate Results

Integrate the output of both agents to produce the final investment judgment.

**Integration points:**
1. Fill in the blind spots raised in the review
2. Adjust the probability allocation (if needed)
3. Make the final judgment accounting for bias
4. Formulate a concrete action plan

#### Step 3.2: Generate Report

Generate the final report in the following format and save it to a file.

**Save location:** `reports/scenario_analysis_<topic>_YYYYMMDD.md`

```markdown
# Headline Scenario Analysis Report

**Analyzed at**: YYYY-MM-DD HH:MM
**Target headline**: [the input headline]
**Event type**: [classification category]

---

---

## 6. Resources

**References:**

- `skills/scenario-analyzer/references/headline_event_patterns.md`
- `skills/scenario-analyzer/references/scenario_playbooks.md`
- `skills/scenario-analyzer/references/sector_sensitivity_matrix.md`

**Scripts:**

- `skills/scenario-analyzer/scripts/polymarket_odds.py`
