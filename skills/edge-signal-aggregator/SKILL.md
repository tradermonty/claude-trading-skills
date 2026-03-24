---
name: edge-signal-aggregator
description: "Aggregate and rank signals from multiple edge-finding skills (edge-candidate-agent, theme-detector, sector-analyst, institutional-flow-tracker) into a prioritized conviction dashboard with weighted scoring, deduplication, and contradiction detection. Use when the user wants to combine edge signals, prioritize trading opportunities, see a summary of all detected edges, rank top opportunities, or review signal consensus and conflicts across analysis skills."
---

# Edge Signal Aggregator

## Overview

Combine outputs from multiple upstream edge-finding skills into a single weighted conviction dashboard. Apply configurable signal weights, deduplicate overlapping themes, flag contradictions, and rank composite edge ideas by aggregate confidence score. The result is a prioritized edge shortlist with provenance links to each contributing skill.

## When to Use

- After running multiple edge-finding skills and needing a unified ranked view
- When consolidating signals from edge-candidate-agent, theme-detector, sector-analyst, and institutional-flow-tracker
- Before portfolio allocation decisions requiring multi-source signal consensus
- To surface contradictions between different analysis approaches
- When prioritizing which edge ideas deserve deeper research

## Prerequisites

- Python 3.9+
- No API keys required (processes local JSON/YAML files from other skills)
- Dependencies: `pyyaml` (standard in most environments)

## Workflow

### Step 1: Gather Upstream Skill Outputs

Collect output files from the upstream skills you want to aggregate:
- `reports/edge_candidate_*.json` from edge-candidate-agent
- `reports/edge_concepts_*.yaml` from edge-concept-synthesizer
- `reports/theme_detector_*.json` from theme-detector
- `reports/sector_analyst_*.json` from sector-analyst
- `reports/institutional_flow_*.json` from institutional-flow-tracker
- `reports/edge_hints_*.yaml` from edge-hint-extractor

**Validation:** Before proceeding, verify that at least one upstream output file exists and contains valid JSON/YAML. If files are missing or malformed, re-run the relevant upstream skill first.

### Step 2: Run Signal Aggregation

Execute the aggregator script with paths to upstream outputs:

```bash
python3 skills/edge-signal-aggregator/scripts/aggregate_signals.py \
  --edge-candidates reports/edge_candidate_agent_*.json \
  --edge-concepts reports/edge_concepts_*.yaml \
  --themes reports/theme_detector_*.json \
  --sectors reports/sector_analyst_*.json \
  --institutional reports/institutional_flow_*.json \
  --hints reports/edge_hints_*.yaml \
  --output-dir reports/
```

Optional: Use a custom weights configuration:

```bash
python3 skills/edge-signal-aggregator/scripts/aggregate_signals.py \
  --edge-candidates reports/edge_candidate_agent_*.json \
  --weights-config skills/edge-signal-aggregator/assets/custom_weights.yaml \
  --output-dir reports/
```

### Step 3: Review Aggregated Dashboard

Open the generated report to review:
1. **Ranked Edge Ideas** - Sorted by composite conviction score
2. **Signal Provenance** - Which skills contributed to each idea
3. **Contradictions** - Conflicting signals flagged for manual review
4. **Deduplication Log** - Merged overlapping themes

### Step 4: Act on High-Conviction Signals

Filter the shortlist by minimum conviction threshold:

```bash
python3 skills/edge-signal-aggregator/scripts/aggregate_signals.py \
  --edge-candidates reports/edge_candidate_agent_*.json \
  --min-conviction 0.7 \
  --output-dir reports/
```

## Output Format

The aggregator produces both JSON and markdown reports saved to `reports/` as `edge_signal_aggregator_YYYY-MM-DD_HHMMSS.{json,md}`.

### JSON Report Structure

Each report contains four top-level sections:

- **`summary`** -- Total input signals, unique count after dedup, contradictions found, signals above threshold
- **`ranked_signals`** -- Sorted by composite conviction score, each entry includes:

```json
{
  "rank": 1,
  "signal_id": "sig_001",
  "title": "AI Infrastructure Capex Acceleration",
  "composite_score": 0.87,
  "contributing_skills": [
    {"skill": "edge_candidate_agent", "signal_ref": "ticket_2026-03-01_001", "raw_score": 0.92, "weighted_contribution": 0.23}
  ],
  "tickers": ["NVDA", "AMD", "AVGO"],
  "direction": "LONG",
  "time_horizon": "3-6 months",
  "confidence_breakdown": {"multi_skill_agreement": 0.30, "signal_strength": 0.35, "recency": 0.22}
}
```

- **`contradictions`** -- Conflicting signals between skills, each with a `resolution_hint` (e.g., timeframe mismatch)
- **`deduplication_log`** -- Merged signals with similarity scores and source references

### Markdown Report

Human-readable dashboard with ranked edge ideas, contradiction flags, and dedup summary. See a generated example in `reports/` after running the aggregator.

## Error Handling

- **Missing input files:** The aggregator skips missing upstream outputs and logs a warning. Ensure at least one valid input file is provided.
- **Malformed JSON/YAML:** Invalid files are skipped with an error logged to stderr. Re-run the upstream skill to regenerate.
- **No signals above threshold:** If `--min-conviction` filters out all signals, the report will contain an empty `ranked_signals` array. Lower the threshold or review upstream signal quality.

## Resources

- `scripts/aggregate_signals.py` -- Main aggregation script with CLI interface
- `references/signal-weighting-framework.md` -- Rationale for default weights and scoring methodology
- `assets/default_weights.yaml` -- Default skill weights configuration

## Key Principles

1. **Provenance Tracking** -- Every aggregated signal links back to its source skill and original reference
2. **Contradiction Transparency** -- Conflicting signals are flagged, not hidden, to enable informed decisions
3. **Configurable Weights** -- Default weights reflect typical reliability but can be customized per user
4. **Deduplication Without Loss** -- Merged signals retain references to all original sources
5. **Actionable Output** -- Ranked list with clear tickers, direction, and time horizon for each idea
