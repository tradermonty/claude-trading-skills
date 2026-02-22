---
name: edge-candidate-agent
description: Generate and prioritize US equity long-side edge research tickets from EOD observations, then export pipeline-ready candidate specs for trade-strategy-pipeline Phase I. Use when users ask to turn hypotheses/anomalies into reproducible research tickets, convert validated ideas into `strategy.yaml` + `metadata.json`, or preflight-check interface compatibility (`edge-finder-candidate/v1`) before running pipeline backtests.
---

# Edge Candidate Agent

## Overview

Convert daily market observations into reproducible research tickets and Phase I-compatible candidate specs.
Prioritize signal quality and interface compatibility over aggressive strategy proliferation.

## When to Use

- Convert market observations, anomalies, or hypotheses into structured research tickets.
- Export validated tickets as `strategy.yaml` + `metadata.json` for `trade-strategy-pipeline` Phase I.
- Run preflight compatibility checks for `edge-finder-candidate/v1` before pipeline execution.

## Prerequisites

- Python 3.9+ with `PyYAML` installed.
- Access to the target `trade-strategy-pipeline` repository for schema/stage validation.
- `uv` available when running pipeline-managed validation via `--pipeline-root`.

## Output

- `strategies/<candidate_id>/strategy.yaml`: Phase I-compatible strategy spec.
- `strategies/<candidate_id>/metadata.json`: provenance metadata including interface version and ticket context.
- Validation status from `scripts/validate_candidate.py` (pass/fail + reasons).

## Workflow

1. Load the contract and mapping references:
   - `skills/edge-candidate-agent/references/pipeline_if_v1.md`
   - `skills/edge-candidate-agent/references/signal_mapping.md`
   - `skills/edge-candidate-agent/references/research_ticket_schema.md`
2. Build or update a research ticket using `skills/edge-candidate-agent/references/research_ticket_schema.md`.
3. Export candidate artifacts with `skills/edge-candidate-agent/scripts/export_candidate.py`.
4. Validate interface and Phase I constraints with `skills/edge-candidate-agent/scripts/validate_candidate.py`.
5. Hand off candidate directory to `trade-strategy-pipeline` and run dry-run first.

## Quick Commands

Create a candidate directory from a ticket:

```bash
python3 skills/edge-candidate-agent/scripts/export_candidate.py \
  --ticket path/to/ticket.yaml \
  --strategies-dir /path/to/trade-strategy-pipeline/strategies
```

Validate interface contract only:

```bash
python3 skills/edge-candidate-agent/scripts/validate_candidate.py \
  --strategy /path/to/trade-strategy-pipeline/strategies/my_candidate_v1/strategy.yaml
```

Validate both interface contract and pipeline schema/stage rules:

```bash
python3 skills/edge-candidate-agent/scripts/validate_candidate.py \
  --strategy /path/to/trade-strategy-pipeline/strategies/my_candidate_v1/strategy.yaml \
  --pipeline-root /path/to/trade-strategy-pipeline \
  --stage phase1
```

## Export Rules

- Keep `validation.method: full_sample`.
- Keep `validation.oos_ratio` omitted or `null`.
- Export only supported entry families for v1:
  - `pivot_breakout` with `vcp_detection`
  - `gap_up_continuation` with `gap_up_detection`
- Mark unsupported hypothesis families as research-only in ticket notes, not as export candidates.

## Guardrails

- Reject candidates that violate schema bounds (risk, exits, empty conditions).
- Reject candidate when folder name and `id` mismatch.
- Require deterministic metadata with `interface_version: edge-finder-candidate/v1`.
- Use `--dry-run` in pipeline before full execution.

## Resources

### `skills/edge-candidate-agent/scripts/export_candidate.py`
Generate `strategies/<candidate_id>/strategy.yaml` and `metadata.json` from a research ticket YAML.

### `skills/edge-candidate-agent/scripts/validate_candidate.py`
Run interface checks and optional `StrategySpec`/`validate_spec` checks against `trade-strategy-pipeline`.

### `skills/edge-candidate-agent/references/pipeline_if_v1.md`
Condensed integration contract for `edge-finder-candidate/v1`.

### `skills/edge-candidate-agent/references/signal_mapping.md`
Map hypothesis families to currently exportable signal families.

### `skills/edge-candidate-agent/references/research_ticket_schema.md`
Ticket schema used by `export_candidate.py`.
