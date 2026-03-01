---
name: edge-strategy-designer
description: Convert abstract edge concepts into strategy draft variants and optional exportable ticket YAMLs for edge-candidate-agent export/validation.
---

# Edge Strategy Designer

## Overview

Translate concept-level hypotheses into concrete strategy draft specs.
This skill sits after concept synthesis and before pipeline export validation.

## When to Use

- You have `edge_concepts.yaml` and need strategy candidates.
- You want multiple variants (core/conservative/research-probe) per concept.
- You want optional exportable ticket files for interface v1 families.

## Prerequisites

- Python 3.9+
- `PyYAML`
- `edge_concepts.yaml` produced by concept synthesis

## Output

- `strategy_drafts/*.yaml`
- `strategy_drafts/run_manifest.json`
- Optional `exportable_tickets/*.yaml` for downstream `export_candidate.py`

## Workflow

1. Load `edge_concepts.yaml`.
2. Choose risk profile (`conservative`, `balanced`, `aggressive`).
3. Generate per-concept variants with hypothesis-type exit calibration.
4. Apply `HYPOTHESIS_EXIT_OVERRIDES` to adjust stop-loss, reward-to-risk, time-stop, and trailing-stop per hypothesis type (breakout, earnings_drift, panic_reversal, etc.).
5. Clamp reward-to-risk at `RR_FLOOR=1.5` to prevent C5 review failures.
6. Export v1-ready ticket YAML when applicable.
7. Hand off exportable tickets to `skills/edge-candidate-agent/scripts/export_candidate.py`.

## Quick Commands

Generate drafts only:

```bash
python3 skills/edge-strategy-designer/scripts/design_strategy_drafts.py \
  --concepts /tmp/edge-concepts/edge_concepts.yaml \
  --output-dir /tmp/strategy-drafts \
  --risk-profile balanced
```

Generate drafts + exportable tickets:

```bash
python3 skills/edge-strategy-designer/scripts/design_strategy_drafts.py \
  --concepts /tmp/edge-concepts/edge_concepts.yaml \
  --output-dir /tmp/strategy-drafts \
  --exportable-tickets-dir /tmp/exportable-tickets \
  --risk-profile conservative
```

## Resources

- `skills/edge-strategy-designer/scripts/design_strategy_drafts.py`
- `references/strategy_draft_schema.md`
- `skills/edge-candidate-agent/scripts/export_candidate.py`
