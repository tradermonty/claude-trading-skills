# Pivot Proposal Schema

Pivot drafts are `strategy_draft`-compatible YAML files with an additive `pivot_metadata` extension. Downstream tools can ignore the extension and treat pivots as regular strategy drafts.

## Required Fields (strategy_draft compatible)

```yaml
# Identity
id: pivot_{source_archetype}_to_{target_archetype}_{timestamp}
as_of: "YYYY-MM-DD"
concept_id: <original concept_id from source strategy>
variant: research_probe
name: "<Target archetype name> (pivoted from <source>)"

# Classification
hypothesis_type: <from target archetype>
mechanism_tag: <from target archetype>
regime: <inherited from source or adjusted>
export_ready_v1: <true only if entry_family in EXPORTABLE_FAMILIES>
entry_family: <from target archetype, or research_only>

# Entry
entry:
  conditions: [<list of entry condition strings>]
  trend_filter: [<list of trend filter strings>]
  note: "Probe setup with small size for hypothesis validation."

# Exit
exit:
  stop_loss_pct: <float, e.g. 0.04>
  take_profit_rr: <float, e.g. 2.0>
  time_stop_days: <int>

# Risk
risk:
  position_sizing: fixed_risk
  risk_per_trade: <float, e.g. 0.005>
  max_positions: <int>
  max_sector_exposure: <float, e.g. 0.3>

# Validation
validation_plan:
  period: "2016-01-01 to latest"
  entry_timing: next_open
  hold_days: [<list of int>]
  success_criteria:
    - "<criterion 1>"
    - "<criterion 2>"

# Context
thesis: "<strategy thesis>"
invalidation_signals: [<list of invalidation signals>]
```

## Pivot Metadata Extension (additive)

```yaml
pivot_metadata:
  pivot_technique: <assumption_inversion | archetype_switch | objective_reframe>
  source_strategy_id: <id of the original strategy draft>
  target_archetype: <archetype id from catalog>
  what_changed:
    signal: "<description of signal change>"
    horizon: "<description of horizon change>"
    risk: "<description of risk change>"
  why: "<explanation of why this pivot addresses the trigger>"
  targeted_triggers: [<list of trigger IDs this pivot addresses>]
  expected_failure_modes:
    - "<potential failure mode 1>"
    - "<potential failure mode 2>"
  scores:
    quality_potential: <float 0-1>
    novelty: <float 0-1>
    combined: <float 0-1>
```

## Output Directory Structure

```
{output-dir}/
├── pivot_drafts/
│   ├── research_only/
│   │   └── pivot_{source}_{archetype}_{timestamp}.yaml
│   └── exportable/
│       ├── pivot_{source}_{archetype}_{timestamp}.yaml
│       └── ticket_{source}_{archetype}_{timestamp}.yaml
├── pivot_report_{strategy_id}_{timestamp}.md
└── pivot_manifest_{strategy_id}_{timestamp}.json
```

## Exportable Ticket Generation

Tickets are generated only when `entry_family` is in `EXPORTABLE_FAMILIES`:
- `pivot_breakout`
- `gap_up_continuation`

Ticket format follows `build_export_ticket()` from `design_strategy_drafts.py:222`.

## Manifest Schema

```json
{
  "generated_at_utc": "ISO-8601",
  "strategy_id": "source strategy id",
  "diagnosis_file": "path to diagnosis JSON",
  "strategy_file": "path to source draft YAML",
  "triggers_fired": ["trigger_id_1", "trigger_id_2"],
  "total_pivots_generated": 3,
  "exportable_count": 1,
  "research_only_count": 2,
  "drafts": [
    {
      "id": "pivot_...",
      "path": "relative path",
      "category": "research_only | exportable",
      "ticket_path": "relative path or null",
      "scores": {"quality_potential": 0.7, "novelty": 0.8, "combined": 0.74}
    }
  ],
  "errors": []
}
```
