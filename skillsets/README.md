# Skillsets

Purpose-specific **skillset manifests** for the solo-trader OS. A skillset is a
category-scoped bundle of skills (required / recommended / optional) tied to the
workflow(s) that operationalize it. Skillsets are the "what to install for this
goal" layer; workflows are the "what to run, in order" layer.

These files are the **canonical** definition of skill bundles. If any prose
elsewhere (`README.md`, `CLAUDE.md`, docs site) disagrees with a manifest here,
the YAML is correct.

A skillset `id` is exactly a `skills-index.yaml` **category**, so the Trading
Skills Navigator maps a recommendation's dominant category straight to its
manifest with no lookup table.

For the full schema, error codes, and validator rules, see
[`docs/dev/metadata-and-workflow-schema.md`](../docs/dev/metadata-and-workflow-schema.md).

## Available skillsets

| Skillset | API profile | Related workflow(s) | Required skills |
|---|---|---|---|
| [`market-regime.yaml`](market-regime.yaml) | no-api-basic | market-regime-daily | market-breadth-analyzer, uptrend-analyzer, exposure-coach |
| [`core-portfolio.yaml`](core-portfolio.yaml) | mixed | core-portfolio-weekly | portfolio-manager, trader-memory-core |
| [`swing-opportunity.yaml`](swing-opportunity.yaml) | fmp-required | swing-opportunity-daily | vcp-screener, technical-analyst, position-sizer, trader-memory-core |
| [`trade-memory.yaml`](trade-memory.yaml) | no-api-basic | trade-memory-loop, monthly-performance-review | trader-memory-core, signal-postmortem |

This is the minimal Phase-2 set: the four categories that already have a
shipped workflow. `dividend-income`, `strategy-research`, and
`advanced-satellite` are deferred until a real workflow backs them — the
Navigator keeps returning an honest gap (`manifest_status: deferred`) for those.

## Naming: category id is canonical

`PROJECT_VISION.md` §12 lists a `trade-memory-loop` skillset candidate. The
**category id is `trade-memory`** (the `skills-index.yaml` category); the file
is `skillsets/trade-memory.yaml`. The `trade-memory-loop` *workflow* is listed
under `related_workflows`. **Never create `skillsets/trade-memory-loop.yaml`** —
a skillset id must be a skills-index category, and `trade-memory-loop` is a
workflow id, not a category.

## How to read a manifest

A skillset manifest has these fields (all required, all validated):

1. **Header** — `schema_version` (==1), `id` (== filename stem == a skills-index
   category), `display_name`, `category` (== `id`), `timeframe`
   (`daily|weekly|event-driven|research`), `difficulty`
   (`beginner|intermediate|advanced`), `api_profile`
   (`no-api-basic|fmp-required|alpaca-required|mixed`).
2. **`target_users`** — non-empty list of canonical persona ids
   (`part-time-swing-trader`, `growth-investor`, `long-term-investor`,
   `dividend-investor`).
3. **`when_to_use` / `when_not_to_use`** — non-empty prose. `when_not_to_use`
   echoes the related workflow's `when_not_to_run` guard.
4. **`required_skills` / `recommended_skills` / `optional_skills`** — pairwise
   disjoint skill-id lists, all resolving to `skills-index.yaml`.
   `required_skills` is non-empty; the `recommended_skills` /
   `optional_skills` **keys are required** (use `[]` if none — a missing key
   is an error).
5. **`related_workflows`** — non-empty list of `workflows/<id>.yaml` ids that
   operationalize this skillset.

### The `required_skills ⊆ related_workflows` coherence contract

A skillset is the install bundle for its workflow(s). The validator enforces a
live coherence contract so a workflow edit cannot silently desync a skillset:

- The union of every related workflow's `required_skills` must be a subset of
  this skillset's `required_skills` (a skill a workflow *requires* cannot be
  merely recommended/optional here, or missing).
- When a skillset has exactly one related workflow, its `required_skills` must
  equal that workflow's `required_skills` set.
- `api_profile` must **cover** every related workflow's: `mixed` is the
  multi-provider umbrella and covers all; any profile covers a `no-api-basic`
  workflow; otherwise the provider must match exactly (`fmp-required` and
  `alpaca-required` are the same paid tier but are NOT interchangeable).
- A `no-api-basic` skillset may not list **any** paid-required skill (an
  `fmp`/`finviz`/`alpaca` integration at `requirement: required` in
  `skills-index.yaml`) in `required`, `recommended`, **or** `optional` — the
  bundle must be fully runnable without paid keys. This mirrors the Navigator's
  own credential-aware rule.

Because the validator's pre-commit hook also fires on `workflows/*.yaml`,
editing a workflow's `required_skills` without updating its skillset **fails
the hook**.

## Validation

Manifests are validated by `scripts/validate_skillsets.py` (run on pre-commit,
pre-push, and CI). Errors are stable codes `SK001`–`SK013` (+ `SK-PARSE` /
`SK-MISSING`). See `docs/dev/metadata-and-workflow-schema.md` for the full
catalog.

## Consumed by

The Trading Skills Navigator (`skills/trading-skills-navigator`) reads these
manifests: when a recommendation's dominant skills-index category has a
manifest here, the Navigator reports `skillset.manifest_status: active`
(otherwise `deferred`). The Navigator only needs the manifest **ids** (carried
in its bundled metadata snapshot for the Claude Web App); it does not bundle the
manifest files.
