# Pipeline Interface v1

This reference summarizes the `edge-finder-candidate/v1` contract used by
`trade-strategy-pipeline` Phase I.

## Required Artifact Layout

- `strategies/<candidate_id>/strategy.yaml` (required)
- `strategies/<candidate_id>/metadata.json` (recommended for provenance)
- Folder name `<candidate_id>` must match `strategy.yaml` field `id`.

## `strategy.yaml` Required Top-Level Keys

- `id`
- `name`
- `universe`
- `signals`
- `risk`
- `cost_model`
- `validation`
- `promotion_gates`

## Phase I Constraints

- `validation.method` must be `full_sample`.
- `validation.oos_ratio` must be omitted or `null`.
- `risk.risk_per_trade` must satisfy `0 < value <= 0.10`.
- `risk.max_positions` must be `>= 1`.
- `risk.max_sector_exposure` must satisfy `0 < value <= 1.0`.
- `signals.entry.conditions` must be non-empty.
- `signals.exit.stop_loss` must be non-empty.
- `signals.exit` must include `trailing_stop` or `take_profit`.

## Supported Entry Families (v1)

- `pivot_breakout` with `vcp_detection` block
- `gap_up_continuation` with `gap_up_detection` block

If both detection blocks exist, implementation may merge both as logical OR.

## Execution Handshake

Run:

```bash
uv run python -m pipeline.runner.cli \
  --strategy <candidate_id> \
  --data-dir data \
  --output-dir reports/<candidate_id>
```

Dry-run first:

```bash
uv run python -m pipeline.runner.cli --strategy <candidate_id> --dry-run
```

Minimum machine-readable outputs:

- `run_status` from CLI exit code
- `gate_status` from `Promotion gate: PASSED|FAILED`
- `report_path` from `Report: ...`
