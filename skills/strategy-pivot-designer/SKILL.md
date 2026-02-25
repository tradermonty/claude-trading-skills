---
name: strategy-pivot-designer
description: Detect backtest iteration stagnation and generate structurally different strategy pivot proposals when parameter tuning reaches a local optimum.
---

# Strategy Pivot Designer

## Overview

Detect when a strategy's backtest iteration loop has stalled and propose structurally different strategy architectures. This skill acts as the feedback loop for the Edge pipeline (hint-extractor -> concept-synthesizer -> strategy-designer -> candidate-agent), breaking out of local optima by redesigning the strategy's skeleton rather than tweaking parameters.

## When to Use

- Backtest scores have plateaued despite multiple refinement iterations.
- A strategy shows signs of overfitting (high in-sample, low robustness).
- Transaction costs defeat the strategy's thin edge.
- Tail risk or drawdown exceeds acceptable thresholds.
- You want to explore fundamentally different strategy architectures for the same market hypothesis.

## Prerequisites

- Python 3.9+
- `PyYAML`
- Iteration history JSON (accumulated backtest-expert evaluations)
- Source strategy draft YAML (from edge-strategy-designer)

## Output

- `pivot_drafts/research_only/*.yaml` — strategy_draft compatible YAML proposals
- `pivot_drafts/exportable/*.yaml` — export-ready drafts + ticket YAML for candidate-agent
- `pivot_report_*.md` — human-readable pivot analysis
- `pivot_manifest_*.json` — metadata for all generated files
- `pivot_diagnosis_*.json` — stagnation detection results

## Workflow

1. Accumulate backtest evaluation results into an iteration history file using `--append-eval`.
2. Run stagnation detection on the history to identify triggers (plateau, overfitting, cost defeat, tail risk).
3. If stagnation detected, generate pivot proposals using three techniques: assumption inversion, archetype switch, objective reframe.
4. Review ranked proposals (scored by quality potential + novelty).
5. For exportable proposals, ticket YAML is ready for edge-candidate-agent pipeline.
6. For research_only proposals, manual strategy design needed before pipeline integration.
7. Feed the selected pivot draft back into backtest-expert for the next iteration cycle.

## Quick Commands

Append a backtest evaluation to history (creates history if new):

```bash
python3 skills/strategy-pivot-designer/scripts/detect_stagnation.py \
  --append-eval reports/backtest_eval_2026-02-10_120000.json \
  --history reports/iteration_history.json \
  --strategy-id draft_edge_concept_breakout_behavior_riskon_core \
  --changes "Widened stop_loss from 5% to 7%"
```

Detect stagnation:

```bash
python3 skills/strategy-pivot-designer/scripts/detect_stagnation.py \
  --history reports/iteration_history.json \
  --output-dir reports/
```

Generate pivot proposals:

```bash
python3 skills/strategy-pivot-designer/scripts/generate_pivots.py \
  --diagnosis reports/pivot_diagnosis_*.json \
  --strategy reports/edge_strategy_drafts/draft_*.yaml \
  --max-pivots 3 \
  --output-dir reports/
```

## Resources

- `skills/strategy-pivot-designer/scripts/detect_stagnation.py`
- `skills/strategy-pivot-designer/scripts/generate_pivots.py`
- `references/stagnation_triggers.md`
- `references/strategy_archetypes.md`
- `references/pivot_techniques.md`
- `references/pivot_proposal_schema.md`
- `skills/backtest-expert/scripts/evaluate_backtest.py`
- `skills/edge-strategy-designer/scripts/design_strategy_drafts.py`
