# Workflows

Operational workflow manifests for the solo-trader OS. Each manifest names exactly one skill per step, declares decision gates, and documents the artifacts that flow between steps.

These files are the **canonical** definition of multi-skill workflows. If any prose elsewhere (`README.md`, `CLAUDE.md`, blog posts, docs site) disagrees with a manifest in this directory, the YAML is correct.

For the full schema, error codes, and validator rules, see [`docs/dev/metadata-and-workflow-schema.md`](../docs/dev/metadata-and-workflow-schema.md).

## Available workflows

| Workflow | Cadence | API profile | Anchor skills |
|---|---|---|---|
| [`market-regime-daily.yaml`](market-regime-daily.yaml) | daily (~15 min) | no-api-basic | market-breadth-analyzer, uptrend-analyzer, exposure-coach |
| [`core-portfolio-weekly.yaml`](core-portfolio-weekly.yaml) | weekly (~60 min) | mixed | portfolio-manager, kanchi-dividend-review-monitor, trader-memory-core |
| [`swing-opportunity-daily.yaml`](swing-opportunity-daily.yaml) | daily (~35 min) | fmp-required | vcp-screener, technical-analyst, position-sizer |
| [`multi-asset-opportunity-daily.yaml`](multi-asset-opportunity-daily.yaml) | daily (~45 min) | mixed | macro-regime-detector, theme-detector, trade-hypothesis-ideator |
| [`stockbee-ep-daily.yaml`](stockbee-ep-daily.yaml) | daily (~35 min) | mixed | stockbee-episodic-pivot-analyzer, technical-analyst, position-sizer |
| [`stockbee-20pct-study-daily.yaml`](stockbee-20pct-study-daily.yaml) | daily (~30 min) | mixed | stockbee-20pct-study |
| [`stockbee-fluency-loop.yaml`](stockbee-fluency-loop.yaml) | daily (~20 min) | no-api-basic | stockbee-setup-fluency-trainer |
| [`trade-memory-loop.yaml`](trade-memory-loop.yaml) | ad-hoc (per closed trade) | no-api-basic | trader-memory-core, signal-postmortem |
| [`monthly-performance-review.yaml`](monthly-performance-review.yaml) | monthly (~90 min) | no-api-basic | trader-memory-core, signal-postmortem, backtest-expert |

## How to read a manifest

A workflow manifest has these main sections:

1. **Header** — `id`, `display_name`, `cadence`, `estimated_minutes`, `target_users`, `difficulty`, `api_profile`, plus `when_to_run` / `when_not_to_run` guidance.
2. **`required_skills` / `optional_skills`** — the skills you need installed to run this workflow. Required skills must appear in at least one non-optional step.
3. **`prerequisite_workflows`** *(optional)* — informational hint that this workflow expects an artifact from another workflow upstream (e.g. `swing-opportunity-daily` expects `exposure_decision` from `market-regime-daily`). Validator does NOT enforce — see "Inter-workflow data flow" below.
4. **`artifacts`** — every named output, with `produced_by_step`, `required` flag, and (optional) `downstream_hints` for navigation. The validator cross-checks `produced_by_step` against each step's `produces:` list.
5. **`steps`** — ordered execution. Each step names exactly one skill, may be `optional`, may be a `decision_gate` (which requires a `decision_question`), and declares what it `consumes` and `produces`.

Below the steps:
- **`manual_review`** — checklist items the human must confirm. Workflows are semi-automated, not auto-execution. Human judgment remains in the loop.
- **`journal_destination`** — which skill captures the workflow's outcome (always `trader-memory-core` here).
- **`final_outputs`** — only on `monthly-performance-review`. Separates trade-side improvements from repo-side improvements.

### `consumes:` means "use if available", not "required input"

A step's `consumes:` list documents which artifacts the step **may read** if earlier steps produced them. Whether the artifact actually exists at run time depends on whether its producing step ran:

- If the producing step is **non-optional**, the artifact always exists. Treat it as required input.
- If the producing step is **optional** (`optional: true`), the consuming step must gracefully handle the absent case. Example: `exposure-coach` runs with or without `top_risk_report`.

This is intentionally minimal — there is no separate `optional_consumes:` field. The optionality lives on the *producer*, and the consumer must handle it. See `docs/dev/metadata-and-workflow-schema.md` § 2.3 for the full rule.

## Worked example

Running `market-regime-daily` looks like this in practice:

```text
[ Step 1 ] Run market-breadth-analyzer
              → produces: market_breadth_report

[ Step 2 ] Run uptrend-analyzer
              → produces: uptrend_report

[ Step 3 ] (optional) Run market-top-detector
              → produces: top_risk_report

[ Step 4 ] Run exposure-coach (decision gate)
              consumes: market_breadth_report, uptrend_report, top_risk_report
              → produces: exposure_decision
              → DECISION: "Is new swing-trade risk allowed today?"

[ Manual ] Confirm output is not used as a buy/sell signal.
           Confirm exposure adjustment direction.

[ Journal ] Write the day's regime decision to trader-memory-core.
```

Step 4 is a decision gate — the workflow does not proceed mechanically. The human reads the report, weighs the question, and records the answer in the journal.

## Inter-workflow data flow

Two informational fields document inter-workflow ordering. **Both are NOT validated.** They exist for human navigation and a future Navigator skill. If a hard inter-workflow contract is needed, it will be added as a new field, never by repurposing these.

- **`artifacts[].downstream_hints`** — on the upstream workflow, lists workflows that may consume this artifact. (E.g. `market-regime-daily`'s `exposure_decision` hints `swing-opportunity-daily`.)
- **`prerequisite_workflows`** — on the downstream workflow, lists upstream workflows that should run first. (E.g. `swing-opportunity-daily.prerequisite_workflows` declares it expects `exposure_decision` from `market-regime-daily`.)

The two fields point at the same dependency from opposite sides. Use both for clarity; do not assume the validator enforces either. The trader is responsible for actually feeding the upstream artifact into the downstream workflow.

## Running a workflow

There is no auto-runner yet. Workflows are followed manually:

1. Read the manifest top-to-bottom for `when_to_run` / `when_not_to_run`.
2. Confirm the API profile matches your environment.
3. Walk the steps, invoking each named skill in turn.
4. At each `decision_gate`, pause and answer the `decision_question` honestly.
5. Pass artifact outputs from one step into the next as inputs.
6. Complete the `manual_review` checklist before journaling.
7. Write the workflow's outcome to the `journal_destination` (always `trader-memory-core`).

Future versions of this repo (vision Phase 1: Trading Skills Navigator) may automate step orchestration. The schema is designed for that, but PR2 ships only the manifests + manual workflow.

## Validation

Manifests are validated by `scripts/validate_skills_index.py --strict-workflows` (run on `pre-push` and CI). Errors are stable codes (WF001-012). See `docs/dev/metadata-and-workflow-schema.md` for the full catalog.
