---
description: "Analyze 18-month scenarios from a news headline. Generate a comprehensive English report including 1st/2nd/3rd-order impacts, recommended stocks, and a second opinion."
argument-hint: "<headline>"
---

# Scenario Analyzer

Analyze 18-month scenarios from a news headline and assess the impact on sectors and stocks.

## Arguments

```
$ARGUMENTS
```

**Argument interpretation**:
- If a headline is included: analyze that headline
- If the argument is empty: ask the user to enter a headline

**Usage examples**:
- `/scenario-analyzer Fed raises rates by 50bp` → analyze the Fed rate-hike scenario
- `/scenario-analyzer China announces new tariffs on US semiconductors` → analyze the tariff scenario
- `/scenario-analyzer OPEC+ agrees to cut oil production` → analyze the oil production-cut scenario
- `/scenario-analyzer` → ask for a headline, then analyze

## Analysis Contents

| Item | Description |
|------|-------------|
| **Related news** | Collect related articles from the past 2 weeks via WebSearch |
| **Scenarios** | 3 scenarios (Base/Bull/Bear) with probabilities |
| **Impact analysis** | 1st-/2nd-/3rd-order sector impact |
| **Stock selection** | 3-5 positive and 3-5 negative stocks (US market) |
| **Review** | Second opinion (points out blind spots / biases) |

## Execution Procedure

1. **Headline parsing**:
   - Extract the headline from the argument
   - If the argument is empty, ask the user for input
   - Classify the event type (Monetary Policy / Geopolitics / Regulation / Technology / Commodities / Corporate)

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
   - 3 scenarios (Base/Bull/Bear)
   - Sector impact analysis (1st/2nd/3rd-order)
   - List of recommended stocks

4. **Second opinion (strategy-reviewer agent)**:
   ```
   Agent tool:
   - subagent_type: "strategy-reviewer"
   - prompt: full text of the Step 3 analysis result
   ```

   Output:
   - Blind spots identified
   - Opinion on scenario probabilities
   - Bias detection
   - Alternative scenario proposals

5. **Report generation**:
   - Integrate the results of both agents
   - Append the final investment judgment
   - Save to `reports/scenario_analysis_<topic>_YYYYMMDD.md`

## Reference Resources

- `skills/scenario-analyzer/references/headline_event_patterns.md` - event patterns
- `skills/scenario-analyzer/references/sector_sensitivity_matrix.md` - sector sensitivity
- `skills/scenario-analyzer/references/scenario_playbooks.md` - scenario templates

## Important Instructions

- **Language**: Conduct all analysis and output in **English**
- **Target market**: Stock selection is limited to **US-listed equities only**
- **Time horizon**: Scenarios target **18 months**
- **Probability**: Base + Bull + Bear = **100%**
- **Second opinion**: Run it **mandatorily** (always invoke strategy-reviewer)

## Output

Finally, generate a `Headline Scenario Analysis Report` that includes:
- Related news articles
- Scenario overview (through 18 months out)
- Impact on sectors / industries (1st/2nd/3rd-order)
- Positive-impact stocks (3-5 tickers)
- Negative-impact stocks (3-5 tickers)
- Second opinion / review
- Final investment judgment / implications
