# Strategy Draft Schema

`design_strategy_drafts.py` writes one YAML per concept variant.

```yaml
id: draft_edge_concept_breakout_behavior_riskon_core
as_of: "2026-02-20"
concept_id: edge_concept_breakout_behavior_riskon
variant: core
risk_profile: balanced
name: Participation-backed trend breakout (core)
hypothesis_type: breakout
mechanism_tag: behavior
regime: RiskOn
export_ready_v1: true
entry_family: pivot_breakout
entry:
  conditions:
    - close > high20_prev
    - rel_volume >= 1.5
  trend_filter:
    - price > sma_200
exit:
  stop_loss_pct: 0.07
  take_profit_rr: 3.0
  time_stop_days: 20
risk:
  position_sizing: fixed_risk
  risk_per_trade: 0.01
  max_positions: 5
validation_plan:
  period: 2016-01-01 to latest
  hold_days: [5, 20, 60]
  success_criteria:
    - expected_value_after_costs > 0
```

`risk_profile` is persisted in each draft for traceability of sizing/limits decisions.

## Export Ticket Output (Optional)

When `--exportable-tickets-dir` is provided, export-ready drafts produce minimal ticket YAML files compatible with `skills/edge-candidate-agent/scripts/export_candidate.py`.
