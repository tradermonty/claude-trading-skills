---
name: trade-hypothesis-ideator
description: >
  Generate falsifiable trade strategy hypotheses from market data, trade logs,
  and journal snippets. Use when you have a structured input bundle and want
  ranked hypothesis cards with experiment designs, kill criteria, and optional
  strategy.yaml export compatible with edge-finder-candidate/v1.
---

# Trade Hypothesis Ideator

Generate 1-5 structured hypothesis cards from a normalized input bundle, critique and rank them, then optionally export `pursue` cards into `strategy.yaml` + `metadata.json` artifacts.

## Workflow

1. Receive input JSON bundle.
2. Run pass 1 normalization + evidence extraction.
3. Generate hypotheses with prompts:
   - `prompts/system_prompt.md`
   - `prompts/developer_prompt_template.md` (inject `{{evidence_summary}}`)
4. Critique hypotheses with `prompts/critique_prompt_template.md`.
5. Run pass 2 ranking + output formatting + guardrails.
6. Optionally export `pursue` hypotheses via Step H strategy exporter.

## Scripts

- Pass 1 (evidence summary):

```bash
python3 skills/trade-hypothesis-ideator/scripts/run_hypothesis_ideator.py \
  --input skills/trade-hypothesis-ideator/examples/example_input.json \
  --output-dir reports/
```

- Pass 2 (rank + output + optional export):

```bash
python3 skills/trade-hypothesis-ideator/scripts/run_hypothesis_ideator.py \
  --input skills/trade-hypothesis-ideator/examples/example_input.json \
  --hypotheses reports/raw_hypotheses.json \
  --output-dir reports/ \
  --export-strategies
```

## References

- `references/hypothesis_types.md`
- `references/evidence_quality_guide.md`
- `references/what-is-priced-in-framework.md` - Framework for translating research into sized positions: score/rank (quant), fair-value gap (expectational), and what-is-priced-in (fundamental discretionary). Load when hypothesis involves an earnings catalyst, valuation gap, or consensus revision thesis.

## Output Artifact

All output from this skill must be structured as one of the following canonical artifact types.
Each artifact carries `manual_review_required: true`, a `disclaimer`, and a `data_gaps[]` array.

| artifact_type | Pydantic model | Description |
|---------------|---------------|-------------|
| `trade_thesis` | `TradeThesis` | Full trade thesis with ThesisLifecycle state and provenance |

Schema: `schemas/json/trade_thesis.json`
