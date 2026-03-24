---
name: edge-strategy-designer
description: "Design trading strategy drafts from edge concepts. Use when generating strategy candidates from edge_concepts.yaml, creating strategy YAML drafts with risk profiles, exporting ticket files for edge-candidate-agent, or converting edge hypotheses (breakout, earnings drift, panic reversal) into actionable strategy specs with stop-loss and reward-to-risk parameters."
---

# Edge Strategy Designer

## Overview

Translate concept-level trading hypotheses from `edge_concepts.yaml` into concrete strategy draft YAML specs with per-hypothesis exit calibration. This skill sits after concept synthesis and before pipeline export validation.

## When to Use

- You have `edge_concepts.yaml` and need strategy draft candidates.
- You want multiple risk-profile variants (core, conservative, research-probe) per concept.
- You need exportable ticket YAML files for the edge-candidate-agent pipeline.
- You are running the edge research pipeline and need to convert concepts into reviewable strategy drafts.

## Prerequisites

- Python 3.9+
- `PyYAML`
- `edge_concepts.yaml` produced by concept synthesis

## Output

- `strategy_drafts/*.yaml` -- one draft per concept-variant combination
- `strategy_drafts/run_manifest.json` -- summary of generated drafts
- Optional `exportable_tickets/*.yaml` for downstream `export_candidate.py`

## Workflow

1. Load `edge_concepts.yaml`.
2. Choose risk profile (`conservative`, `balanced`, `aggressive`).
3. Generate per-concept variants with hypothesis-type exit calibration.
4. Apply `HYPOTHESIS_EXIT_OVERRIDES` to adjust stop-loss, reward-to-risk, time-stop, and trailing-stop per hypothesis type (breakout, earnings_drift, panic_reversal, etc.).
5. Clamp reward-to-risk at `RR_FLOOR=1.5` to prevent C5 review failures.
6. Validate generated drafts exist and contain required fields before proceeding.
7. Export v1-ready ticket YAML when applicable.
8. Hand off exportable tickets to `skills/edge-candidate-agent/scripts/export_candidate.py`.

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
