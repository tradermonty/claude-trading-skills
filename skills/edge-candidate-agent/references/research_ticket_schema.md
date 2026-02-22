# Research Ticket Schema

Use this schema as input to `scripts/export_candidate.py`.

## Required Fields

- `id`: unique ticket identifier
- `hypothesis_type`: one of your edge library labels
- `entry_family`: export target (`pivot_breakout` or `gap_up_continuation`)

## Optional Fields

- `name`, `description`
- `mechanism_tag`
- `regime`
- `holding_horizon`
- `universe`, `data`
- `entry`, `exit`
- `risk`, `cost_model`, `promotion_gates`
- `detection.vcp_detection` or `detection.gap_up_detection`
- `strategy_overrides`

## Minimal Example (pivot breakout)

```yaml
id: edge_vcp_breakout_v1
hypothesis_type: breakout
entry_family: pivot_breakout
name: VCP Breakout Candidate v1
description: Relative strength leaders breaking above pivot with volume.
mechanism_tag: behavior
regime: RiskOn
holding_horizon: 20D
```

## Minimal Example (gap continuation)

```yaml
id: edge_gap_followthrough_v1
hypothesis_type: earnings_drift
entry_family: gap_up_continuation
name: Gap-Up Continuation Candidate v1
description: Earnings gap-up with follow-through above gap-day high.
mechanism_tag: structure
regime: Neutral
holding_horizon: 20D
```

## Export Rule

Keep Phase I compatibility:

- Do not set `validation.method` to `walk_forward`.
- Do not set `validation.oos_ratio`.
