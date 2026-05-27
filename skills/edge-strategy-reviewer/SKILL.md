---
name: edge-strategy-reviewer
description: >
  Critically review strategy drafts from edge-strategy-designer for edge
  plausibility, overfitting risk, sample size adequacy, and execution realism.
  Use when strategy_drafts/*.yaml exists and needs quality gate before pipeline
  export. Outputs PASS/REVISE/REJECT verdicts with confidence scores.
---

# Edge Strategy Reviewer

Deterministic quality gate for strategy drafts produced by `edge-strategy-designer`.

## When to Use

- After `edge-strategy-designer` generates `strategy_drafts/*.yaml`
- Before exporting drafts to `edge-candidate-agent` via the pipeline
- When manually validating a draft strategy for edge plausibility

## Prerequisites

- Strategy draft YAML files (output of `edge-strategy-designer`)
- Python 3.10+ with PyYAML

## Workflow

1. Load draft YAML files from `--drafts-dir` or a single `--draft` file
2. Evaluate each draft against 8 criteria (C1-C8) with weighted scoring
3. Compute confidence score (weighted average of all criteria)
4. Determine verdict: PASS / REVISE / REJECT
5. Assess export eligibility (PASS + export_ready_v1 + exportable family)
6. Write review output (YAML or JSON) and optional markdown summary

## Review Criteria

| # | Criterion | Weight | Key Checks |
|---|-----------|--------|------------|
| C1 | Edge Plausibility | 20 | Thesis quality, domain terms, mechanism keywords (continuous 50-95) |
| C2 | Overfitting Risk | 20 | 5-tier filter count scoring (90/80/60/40/10), precise threshold penalty |
| C3 | Sample Adequacy | 15 | Continuous scoring from estimated annual opportunities (10-95) |
| C4 | Regime Dependency | 10 | Cross-regime validation |
| C5 | Exit Calibration | 10 | Stop-loss, reward-to-risk |
| C6 | Risk Concentration | 10 | Position sizing limits |
| C7 | Execution Realism | 10 | Volume filter, export consistency |
| C8 | Invalidation Quality | 5 | Signal count and specificity |

## Verdict Logic

- C1 or C2 severity=fail → immediate REJECT
- confidence >= 70, no fail findings → PASS
- confidence < 35 → REJECT
- Otherwise → REVISE (with revision instructions)

## Running the Script

```bash
# Review all drafts in a directory
python3 skills/edge-strategy-reviewer/scripts/review_strategy_drafts.py \
  --drafts-dir reports/edge_strategy_drafts/ \
  --output-dir reports/

# Single draft review
python3 skills/edge-strategy-reviewer/scripts/review_strategy_drafts.py \
  --draft reports/edge_strategy_drafts/draft_xxx.yaml \
  --output-dir reports/

# JSON output with markdown summary
python3 skills/edge-strategy-reviewer/scripts/review_strategy_drafts.py \
  --drafts-dir reports/edge_strategy_drafts/ \
  --output-dir reports/ \
  --format json \
  --markdown-summary

# Strict export mode: export-eligible drafts with any warn → REVISE
python3 skills/edge-strategy-reviewer/scripts/review_strategy_drafts.py \
  --drafts-dir reports/edge_strategy_drafts/ \
  --output-dir reports/ \
  --strict-export
```

## Output Format

Primary output: `review.yaml` (or `review.json`)

```yaml
generated_at_utc: "2026-02-28T12:00:00+00:00"
source:
  drafts_dir: "/path/to/strategy_drafts"
  draft_count: 4
summary:
  total: 4
  PASS: 1
  REVISE: 2
  REJECT: 1
  export_eligible: 1
reviews:
  - draft_id: "draft_xxx_core"
    verdict: "PASS"
    confidence_score: 80
    export_eligible: true
    findings: [...]
    revision_instructions: []
```

## Research Quality Gate

Before any reviewed strategy advances to paper trading, the `research_quality` dimension must pass.
This is a cross-cutting gate applied after C1-C8 scoring.

| Check | Requirement | Blocks Advance? |
|-------|-------------|-----------------|
| RQ1 | No-lookahead confirmed (all 8 backtest-expert checklist items) | YES |
| RQ2 | Survivorship bias acknowledged in methodology | YES |
| RQ3 | Out-of-sample hold-out documented in draft | YES |
| RQ4 | `paper_only_until_validated: true` present in artifact | YES |
| RQ5 | Sample size ≥ 30 trades stated in draft | REVISE (not REJECT) |
| RQ6 | Parameter sensitivity tested across at least 3 variants | REVISE (not REJECT) |

A draft that fails RQ1-RQ4 is forced to REJECT regardless of C1-C8 scores.
A draft that fails RQ5-RQ6 is forced to REVISE with specific revision instructions.

Strategies that pass this gate still carry `paper_only_until_validated: true` in all exported
artifacts — this field cannot be cleared by this reviewer.

## Output Artifact

All output from this skill must be structured as one of the following canonical artifact types.
Each artifact carries `manual_review_required: true`, a `disclaimer`, and a `data_gaps[]` array.

| artifact_type | Pydantic model | Description |
|---------------|---------------|-------------|
| `strategy_review` | `StrategyReview` | Multi-criterion scoring with PASS/REVISE/REJECT verdict |

Schema: `schemas/json/strategy_review.json`

## Resources

- `references/review_criteria.md` — Detailed scoring rubric for C1-C8
- `references/overfitting_checklist.md` — Overfitting detection heuristics
