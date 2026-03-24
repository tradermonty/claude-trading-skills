---
name: trade-hypothesis-ideator
description: "Generate falsifiable trade strategy hypotheses from market data, trade logs, and journal snippets. Use when you want trading ideas, strategy testing candidates, or backtest hypotheses from a structured input bundle. Produces ranked hypothesis cards with experiment designs, kill criteria, and optional strategy.yaml export compatible with edge-finder-candidate/v1."
---

# Trade Hypothesis Ideator

Generate 1-5 structured hypothesis cards from a normalized input bundle, critique and rank them, then optionally export `pursue` cards into `strategy.yaml` + `metadata.json` artifacts.

## Workflow

### Pass 1 — Evidence Extraction

1. Receive and validate input JSON bundle against `schemas/input_bundle.schema.json`.
2. Normalize raw data and extract evidence summary.
3. Generate hypotheses using prompts:
   - `prompts/system_prompt.md`
   - `prompts/developer_prompt_template.md` (inject `{{evidence_summary}}`)

**Checkpoint:** Verify `evidence_summary` contains at least 3 data points before proceeding. If extraction yields fewer, review input bundle completeness and re-run normalization.

### Pass 2 — Critique, Rank, and Export

4. Critique hypotheses with `prompts/critique_prompt_template.md`.
5. Rank hypotheses, apply output formatting and guardrails.
6. Optionally export `pursue` hypotheses via Step H strategy exporter.

**Checkpoint:** If critique rejects all cards (no `pursue` verdicts), re-examine evidence quality using `references/evidence_quality_guide.md` and consider broadening hypothesis types via `references/hypothesis_types.md` before re-running.

## Scripts

Pass 1 (evidence summary):

```bash
python3 skills/trade-hypothesis-ideator/scripts/run_hypothesis_ideator.py \
  --input skills/trade-hypothesis-ideator/examples/example_input.json \
  --output-dir reports/
```

Pass 2 (rank + output + optional export):

```bash
python3 skills/trade-hypothesis-ideator/scripts/run_hypothesis_ideator.py \
  --input skills/trade-hypothesis-ideator/examples/example_input.json \
  --hypotheses reports/raw_hypotheses.json \
  --output-dir reports/ \
  --export-strategies
```

## References

- `references/hypothesis_types.md` — catalog of hypothesis archetypes and when each applies
- `references/evidence_quality_guide.md` — scoring rubric for input data reliability
