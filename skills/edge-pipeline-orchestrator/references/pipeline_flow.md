# Edge Pipeline Flow

## Pipeline Stages

```
OHLCV / Tickets
       |
       v
 [auto_detect] ───> tickets/
       |
       v
 [hints]       ───> hints.yaml
       |
       v
 [concepts]    ───> edge_concepts.yaml
       |
       v
 [drafts]      ───> drafts/*.yaml  +  exportable_tickets/*.yaml
       |
       v
 [review]  <──────────────────────┐
       |                          |
       ├── PASS   → accumulated   |
       ├── REJECT → accumulated   |
       └── REVISE → [revision] ───┘  (max 2 iterations)
                          |
                   remaining REVISE → research_probe downgrade
       |
       v
 [export]      ───> strategies/<candidate_id>/
```

## Stage Script Mapping

| Stage       | Script Path                                                        |
|-------------|--------------------------------------------------------------------|
| auto_detect | skills/edge-candidate-agent/scripts/auto_detect_candidates.py      |
| hints       | skills/edge-hint-extractor/scripts/build_hints.py                  |
| concepts    | skills/edge-concept-synthesizer/scripts/synthesize_edge_concepts.py |
| drafts      | skills/edge-strategy-designer/scripts/design_strategy_drafts.py    |
| review      | skills/edge-strategy-reviewer/scripts/review_strategy_drafts.py    |
| export      | skills/edge-candidate-agent/scripts/export_candidate.py            |

## Data Contracts

### auto_detect output (tickets/)

Each ticket is a YAML file with at minimum:
- `id`: unique ticket identifier
- `hypothesis_type`: breakout, earnings_drift, etc.
- `entry_family`: pivot_breakout, gap_up_continuation, or research_only
- `priority_score`: 0-100 numeric score

### hints output (hints.yaml)

```yaml
generated_at_utc: "2026-01-01T00:00:00+00:00"
hints:
  - title: "Breadth-supported breakout regime"
    observation: "..."
    symbols: [AAPL, MSFT]
    regime_bias: "RiskOn"
    mechanism_tag: "behavior"
```

### concepts output (edge_concepts.yaml)

```yaml
concept_count: 3
concepts:
  - id: edge_concept_breakout_behavior_riskon
    hypothesis_type: breakout
    strategy_design:
      recommended_entry_family: pivot_breakout
      export_ready_v1: true
```

### drafts output (drafts/*.yaml)

Each draft YAML file contains:
- `id`: draft identifier (draft_<concept_id>_<variant>)
- `concept_id`: source concept
- `variant`: core, conservative, or research_probe
- `entry_family`: pivot_breakout, gap_up_continuation, or research_only
- `export_ready_v1`: boolean
- `entry.conditions`: list of condition strings
- `entry.trend_filter`: list of trend filter strings
- `exit`: stop_loss_pct, take_profit_rr
- `risk`: position sizing parameters

### review output (reviews/*.yaml)

Each review YAML contains:
- `draft_id`: matching draft identifier
- `verdict`: PASS, REVISE, or REJECT
- `revision_instructions`: list of strings (for REVISE verdicts)
- `confidence_score`: 0-100

### export output (strategies/<candidate_id>/)

- `strategy.yaml`: Phase I-compatible strategy specification
- `metadata.json`: provenance and research context

## Exportable Entry Families

Only these families can be exported to the trade-strategy-pipeline:
- `pivot_breakout`
- `gap_up_continuation`

All other families (research_only, etc.) remain as research probes.
