---
description: "Analyze 18-month scenarios from news headlines. Generate a comprehensive English report including 1st/2nd/3rd-order impacts, recommended stocks, and a second-opinion review."
argument-hint: "<headline>"
---

# Scenario Analyzer

Analyze 18-month scenarios from a news headline and assess the impact on sectors and individual stocks.

## Arguments

```
$ARGUMENTS
```

**Argument interpretation**:
- If a headline is provided: analyze that headline
- If the argument is empty: ask the user to provide a headline

**Examples**:
- `/scenario-analyzer Fed raises rates by 50bp` → Analyze a Fed rate-hike scenario
- `/scenario-analyzer China announces new tariffs on US semiconductors` → Analyze a tariff scenario
- `/scenario-analyzer OPEC+ agrees to cut oil production` → Analyze an oil-production-cut scenario
- `/scenario-analyzer` → Ask for a headline first, then analyze

## Analysis Contents

| Item | Description |
|------|-------------|
| **Related news** | Gather articles from the past two weeks via WebSearch |
| **Scenarios** | Three scenarios — Base / Bull / Bear (with probabilities) |
| **Impact analysis** | 1st / 2nd / 3rd-order sector impacts |
| **Stock selection** | 3-5 positive and 3-5 negative names (US market) |
| **Review** | Second opinion (blind spots, biases) |

## Procedure

1. **Headline parsing**:
   - Extract the headline from the argument
   - If the argument is empty, ask the user to provide one
   - Classify the event type (monetary policy / geopolitics / regulation / technology / commodities / corporate)

2. **Load references**:
   ```
   Read skills/scenario-analyzer/references/headline_event_patterns.md
   Read skills/scenario-analyzer/references/sector_sensitivity_matrix.md
   Read skills/scenario-analyzer/references/scenario_playbooks.md
   ```

3. **Main analysis (scenario-analyst agent)**:
   ```
   Agent tool:
   - subagent_type: "scenario-analyst"
   - prompt: headline + event type + reference information
   ```

   Output:
   - List of related news articles
   - Three scenarios (Base / Bull / Bear)
   - Sector impact analysis (1st / 2nd / 3rd order)
   - Recommended stock list

4. **Second opinion (strategy-reviewer agent)**:
   ```
   Agent tool:
   - subagent_type: "strategy-reviewer"
   - prompt: Full analysis output from Step 3
   ```

   Output:
   - Identified blind spots
   - Comments on scenario probabilities
   - Bias detection
   - Alternative scenario proposals

5. **Report generation**:
   - Integrate the outputs of both agents
   - Append the final investment judgment
   - Save to `reports/scenario_analysis_<topic>_YYYYMMDD.md`

## Reference Resources

- `skills/scenario-analyzer/references/headline_event_patterns.md` — Event patterns
- `skills/scenario-analyzer/references/sector_sensitivity_matrix.md` — Sector sensitivities
- `skills/scenario-analyzer/references/scenario_playbooks.md` — Scenario templates

## Important Instructions

- **Language**: All analysis and output must be in **English**
- **Target market**: Stock selection is limited to **US-listed equities only**
- **Time horizon**: Scenarios cover an **18-month** window
- **Probabilities**: Base + Bull + Bear must equal **100%**
- **Second opinion**: **Required** — always invoke strategy-reviewer

## Output

Generate a `Headline Scenario Analysis Report` containing:
- Related news articles
- Scenario overview (out to 18 months)
- Sector / industry impact (1st / 2nd / 3rd order)
- Stocks likely to benefit (3-5 names)
- Stocks likely to be hurt (3-5 names)
- Second-opinion review
- Final investment judgment / implications
