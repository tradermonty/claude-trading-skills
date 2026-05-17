# Metadata and Workflow Schema (Developer Reference)

This document is the single reference for the two YAML schemas that connect this repository together:

- `skills-index.yaml` — single source of truth for skill metadata
- `workflows/*.yaml` — operational workflow manifests

Both schemas are versioned (`schema_version: 1`). New fields are always additive. Existing fields are never repurposed. If a meaning needs to change, add a new field and deprecate the old one.

The companion validator is `scripts/validate_skills_index.py`.

---

## 1. `skills-index.yaml`

### 1.1 Top-level shape

```yaml
schema_version: 1

categories:
  - market-regime
  - core-portfolio
  - swing-opportunity
  - trade-planning
  - trade-memory
  - strategy-research
  - advanced-satellite
  - meta

skills:
  - id: <skill-id>
    display_name: <Human Title>
    category: <one of categories>
    status: production | beta | experimental | deprecated
    summary: >-
      One-sentence description.

    timeframe: daily | weekly | event-driven | research | unknown
    difficulty: beginner | intermediate | advanced | unknown

    integrations:
      - id: <integration-id>
        type: <integration_type>
        requirement: <requirement>
        note: <free-text>

    inputs: [<input-name>, ...]
    outputs: [<output-name>, ...]
    workflows: [<workflow-id>, ...]
```

### 1.2 Required vs best-effort fields

**Required** (validator hard-blocks under all strictness levels):

| Field | Rule | Error code |
|---|---|---|
| `id` | Equals the directory name under `skills/`. Must match SKILL.md frontmatter `name`. | `IDX003`, `IDX004` |
| `display_name` | Non-empty string. Index-owned (NOT cross-checked against frontmatter). | — |
| `category` | One of the 8 enum values above. | `IDX005` |
| `status` | One of `production` / `beta` / `experimental` / `deprecated`. | `IDX006` |
| `summary` | Non-empty string. | `IDX009` |

**Best-effort** (warn-only by default; required under `--strict-metadata`):

| Field | Rule |
|---|---|
| `timeframe` | One of the enum values. `unknown` allowed under `default` / `--strict-workflows` (warn); rejected under `--strict-metadata`. |
| `difficulty` | One of the enum values. `unknown` allowed under `default` / `--strict-workflows` (warn); rejected under `--strict-metadata`. |
| `integrations` | List form (see §1.3). May be empty for skills with no dependencies, but prefer `[{id: local_calculation, type: calculation, requirement: not_required}]`. |
| `inputs` | List of strings. Empty list (`[]`) allowed under `default` / `--strict-workflows` (warn); `--strict-metadata` requires at least one entry. |
| `outputs` | List of strings. Empty list (`[]`) allowed under `default` / `--strict-workflows` (warn); `--strict-metadata` requires at least one entry. |
| `workflows` | List of workflow IDs. Default mode warns on missing files; `--strict-workflows` errors. |

As of 2026-05-12 the canonical `skills-index.yaml` populates `timeframe`, `difficulty`, `inputs`, and `outputs` for all 54 skills, and `--strict-metadata` is enforced in CI + the pre-push hook. New skill entries must satisfy `--strict-metadata` to merge.

### 1.3 `integrations` schema

```yaml
integrations:
  - id: <integration-id>          # alpaca, fmp, finviz, holdings_csv, websearch, local_calculation, ...
    type: <integration_type>      # see enum below
    requirement: <requirement>    # see enum below
    note: <free-text>             # short justification or pointer
```

**`integration_type` enum:**

| Value | Use for |
|---|---|
| `broker` | Alpaca, IBKR, brokerage APIs |
| `market_data` | FMP, yfinance, paid market data APIs |
| `screener` | FINVIZ Elite and similar screener APIs |
| `web` | WebSearch / WebFetch / general HTTP |
| `local_file` | CSV / YAML / JSON / Markdown inputs from local disk |
| `image` | Chart screenshots and other image inputs |
| `mcp` | MCP servers (non-broker) |
| `calculation` | Pure local computation, no I/O |
| `none` | Edge case: no integration record applies |
| `unknown` | Bootstrap could not determine; flagged for owner review |

**`requirement` enum:**

| Value | Meaning |
|---|---|
| `required` | Skill cannot run without this integration |
| `recommended` | Works without it but degraded |
| `optional` | Alternative input path |
| `not_required` | Explicit "no dependency" marker; pair with `type: none` or `type: calculation` |
| `unknown` | Bootstrap could not determine; flagged for owner review |

`not_used` is intentionally NOT supported — in a list form, integrations that aren't used are simply omitted.

**`type: calculation` vs `type: none`:**

- `type: calculation` — skill performs deterministic local computation. Pair with `id: local_calculation` and `requirement: not_required`. Use this for `position-sizer` and similar pure-compute skills.
- `type: none` — explicit "no integration record applies". Reserved for edge cases. Prefer `calculation` whenever the skill does any computation.

### 1.4 `workflows` field semantics

Each entry is a `workflow id` (= filename in `workflows/` minus `.yaml`).

- **Default mode**: missing workflow files emit a warning. Useful while bootstrapping.
- **`--strict-workflows`**: missing workflow files are errors (`WF001`).

This field is the back-reference. The forward reference (workflow → skill) is in each `workflows/<id>.yaml`'s `required_skills` / `optional_skills` / `steps`.

### 1.5 Governance rules

1. **`display_name` is index-owned.** Validator does NOT cross-check it against `SKILL.md` frontmatter. Only `id` ↔ frontmatter `name` parity is enforced.
2. **Deprecated skills stay in the index.** `status: deprecated` entries remain. They are excluded from `.skill` bundles and from any workflow's `required_skills`, but they remain queryable. Skills physically removed from `skills/` are also removed from the index.
3. **`bootstrap_skills_index.py` is a one-time migration helper.** After PR1 merges, `skills-index.yaml` is the source of truth; do not re-run bootstrap as a sync tool. `CLAUDE.md` becomes a downstream consumer of the index.
4. **No CLAUDE.md ↔ index parity check.** Once the index exists, the CLAUDE.md API matrix is informational. A future PR may regenerate the matrix from the index, but the index is canonical.

---

## 2. Workflow manifests (`workflows/*.yaml`)

### 2.1 Top-level shape

```yaml
schema_version: 1
id: <workflow-id>                 # must equal filename (sans .yaml)
display_name: <Human Title>
cadence: daily | weekly | monthly | ad-hoc
estimated_minutes: <int>
target_users: [<user-persona>, ...]
difficulty: beginner | intermediate | advanced
api_profile: no-api-basic | fmp-required | alpaca-required | mixed

when_to_run: >-
  <prose>
when_not_to_run: >-
  <prose>

required_skills: [<skill-id>, ...]
optional_skills: [<skill-id>, ...]

prerequisite_workflows:           # informational only, NOT validated
  - id: <workflow-id>
    artifact: <artifact-id>       # which upstream artifact this workflow expects
    rationale: <why>

artifacts:
  - id: <artifact-id>
    produced_by_step: <step-number>
    required: true | false
    downstream_hints: [<workflow-id>, ...]   # informational only, NOT validated

steps:
  - step: <int>
    name: <step-title>
    skill: <skill-id>
    optional: true | false       # default false
    consumes: [<artifact-id>, ...]
    produces: [<artifact-id>, ...]
    decision_gate: true | false
    decision_question: >-
      <question, required when decision_gate is true>
    depends_on: [<step-number>, ...]   # only earlier steps

manual_review:
  - <prose, one item per line>

journal_destination: <skill-id>

# Only on monthly-performance-review:
final_outputs:
  - id: <output-id>
```

### 2.2 Internal-consistency rules

These are validated under `--strict-workflows`:

| Rule | Error code |
|---|---|
| Workflow filename equals `id` | `WF002` |
| Every `step.skill` exists in `skills-index.yaml` | `WF003` |
| `depends_on` references only earlier steps | `WF004` |
| `decision_gate: true` step has non-empty `decision_question` | `WF005` |
| `journal_destination` resolves to a skill `id` | `WF006` |
| `consumes` artifacts produced by an earlier step | `WF007` |
| No `deprecated` skill in `required_skills` | `WF008` |
| Every `required_skills` entry appears in at least one non-optional step | `WF009` |
| Every non-optional `step.skill` appears in `required_skills` | `WF010` |
| Workflow file referenced by an index entry's `workflows:` exists | `WF001` |

### 2.3 `consumes:` semantics — "use if available", not "required input"

A step's `consumes:` list documents which artifacts the step **may read** if those artifacts have been produced by earlier steps. It is NOT a hard "required input" declaration.

Concretely:

- If a consumed artifact's producing step is **non-optional**, the artifact will always exist at execution time. Treat it as required input.
- If a consumed artifact's producing step is **optional** (`optional: true`), the consuming step must handle the case where the artifact is absent. The consuming skill itself decides graceful-degrade behavior — e.g. `exposure-coach` runs with or without `top_risk_report`.

Validator rules:

- The artifact must be declared in `artifacts:` ✅ (`WF007`)
- The artifact must be produced by an earlier step ✅ (`WF007`)
- Whether the producing step actually executes at runtime — NOT validated. That is operational concern, not schema concern.

A step's `consumes:` list MAY NOT reference an artifact produced in a later step (covered by `WF007`).

Why no `optional_consumes:` field? In a list-form schema, "use if available" is the default for any artifact whose producer is `optional: true`. Adding a parallel field would duplicate information already encoded in `artifacts[].produced_by_step` + `steps[].optional`. If a future case needs hard "required input" semantics, that will be added as a new field — never by repurposing `consumes:`.

### 2.4 `prerequisite_workflows:` — informational ordering hint

Some workflows depend on the output of another workflow (e.g. `swing-opportunity-daily` should only run after a non-restrictive `market-regime-daily` exposure decision). To make this dependency machine-readable for a future Navigator, declare it at the top of the workflow:

```yaml
prerequisite_workflows:
  - id: market-regime-daily
    artifact: exposure_decision
    rationale: >-
      Swing trade entries require a non-restrictive exposure decision. Skip this
      workflow on cash-priority days.
```

This field is **informational only**. The validator does NOT check that the named workflow exists, that the artifact exists, or that the prerequisite ran today. It is the trader's responsibility (and, eventually, the Navigator's) to enforce ordering.

If a hard inter-workflow contract is needed in the future, it will be added as a new field — never by repurposing `prerequisite_workflows`.

### 2.5 `downstream_hints` is informational

`artifacts[].downstream_hints` is a free-form list of workflow IDs that *might* consume the artifact downstream. The validator does not check this. It is meant for human navigation and (future) Navigator hints.

If a hard inter-workflow contract is needed later, add a separate field (e.g. `consumed_by_workflows: [...]` with strict semantics). Never repurpose `downstream_hints`.

### 2.6 `one_of:` is intentionally NOT in v1

Cases like "either `vcp-screener` or `canslim-screener`" are expressed by:

- Promoting one to `required_skills`
- Demoting the alternative to `optional_skills`

Adding `one_of:` later is an additive schema change.

---

## 3. Skillset manifests (`skillsets/*.yaml`)

A skillset is a **category-scoped skill bundle** tied to the workflow(s) that
operationalize it. A skillset `id` is exactly a `skills-index.yaml` **category**
(so the Trading Skills Navigator maps a recommendation's dominant category
straight to its manifest). Validated by `scripts/validate_skillsets.py`
(pre-commit / pre-push / CI), error codes `SK001`–`SK013`.

### 3.1 Top-level shape

```yaml
schema_version: 1
id: market-regime                 # == filename stem == a skills-index category
display_name: Market Regime
category: market-regime           # == id (validated equal)
timeframe: daily                  # daily | weekly | event-driven | research
difficulty: beginner              # beginner | intermediate | advanced
api_profile: no-api-basic         # no-api-basic | fmp-required | alpaca-required | mixed
target_users: [<persona>, ...]    # non-empty
when_to_use: >-
  <prose, non-empty>
when_not_to_use: >-
  <prose, non-empty — echoes the related workflow's when_not_to_run>
required_skills:    [<skill-id>, ...]   # non-empty
recommended_skills: [<skill-id>, ...]   # may be empty
optional_skills:    [<skill-id>, ...]   # may be empty
related_workflows:  [<workflow-id>, ...]  # non-empty; resolves to workflows/<id>.yaml
```

### 3.2 Naming normalization (Vision → category id)

`PROJECT_VISION.md` §12 lists a `trade-memory-loop` skillset candidate. The
**category id is `trade-memory`** (a `skills-index.yaml` category); the file is
`skillsets/trade-memory.yaml`, and `trade-memory-loop` appears under
`related_workflows`. A skillset id MUST be a skills-index category — never a
workflow id. Do not create `skillsets/trade-memory-loop.yaml`.

### 3.3 `required_skills ⊆ related_workflows` coherence

The validator enforces a live coherence contract (and its pre-commit hook
fires on `workflows/*.yaml`, so a workflow edit that desyncs a skillset is a
hard error):

| Rule | Error code |
|---|---|
| `id` ≠ filename stem | `SK001` |
| `id` not a canonical category, or `category` ≠ `id` | `SK002` |
| Missing/invalid scalar (`schema_version`/`display_name`/`timeframe`/`difficulty`/`api_profile`) | `SK003` |
| Missing/blank `when_to_use` / `when_not_to_use` | `SK004` |
| List fields: `target_users`/`required_skills`/`related_workflows` non-empty `list[str]`; `recommended_skills`/`optional_skills` keys **required** (list[str], may be empty — a missing key is an error) | `SK005` |
| A listed skill not in `skills-index.yaml` | `SK006` |
| `required_skills` contains a deprecated skill | `SK007` |
| `required`/`recommended`/`optional` not pairwise disjoint | `SK008` |
| A `related_workflows` id has no `workflows/<id>.yaml` | `SK009` |
| `⋃(related workflow.required_skills)` ⊄ this skillset's `required_skills` | `SK010` |
| Single related workflow: `required_skills` set ≠ that workflow's | `SK011` |
| `api_profile` does not **cover** a related workflow's: `mixed` covers all; any profile covers a `no-api-basic` workflow; otherwise the provider must match exactly (`fmp-required` ≠ `alpaca-required` even though same tier) | `SK012` |
| `no-api-basic` skillset lists a paid-required skill in required/recommended/optional | `SK013` |

---

## 4. Validator strictness levels

```bash
# Default — pre-commit mode
python3 scripts/validate_skills_index.py

# PR2+ — CI / pre-push mode
python3 scripts/validate_skills_index.py --strict-workflows

# Future — tighten metadata completeness
python3 scripts/validate_skills_index.py --strict-metadata
```

| Check group | default | `--strict-workflows` | `--strict-metadata` |
|---|---|---|---|
| Index ↔ folder bijection | ✅ | ✅ | ✅ |
| Frontmatter `name` ↔ index `id` | ✅ | ✅ | ✅ |
| Required fields populated | ✅ | ✅ | ✅ |
| `category` / `status` enum | ✅ | ✅ | ✅ |
| No duplicate `id` | ✅ | ✅ | ✅ |
| `integrations[].requirement` enum | ✅ | ✅ | ✅ |
| `summary` non-empty | ✅ | ✅ | ✅ |
| `workflows[]` references resolve | ⚠️ warn | ✅ error | ✅ error |
| Workflow internal-consistency rules | — | ✅ error | ✅ error |
| `timeframe` / `difficulty` not `unknown` | ⚠️ warn | ⚠️ warn | ✅ error |
| `inputs` / `outputs` populated | ⚠️ warn | ⚠️ warn | ✅ error |
| `unknown` integrations allowed | ⚠️ warn | ⚠️ warn | ❌ rejected |

---

## 5. Error code catalog

### Index-level (always strict)

| Code | Meaning |
|---|---|
| `IDX001` | Duplicate skill `id` |
| `IDX002` | Index entry exists but `skills/<id>/` does not |
| `IDX003` | `skills/<id>/` exists but no index entry |
| `IDX004` | SKILL.md frontmatter `name` ≠ index `id` |
| `IDX005` | Invalid `category` |
| `IDX006` | Invalid `status` |
| `IDX007` | Invalid `integration_type` |
| `IDX008` | Invalid `requirement` |
| `IDX009` | Empty `summary` |
| `IDX010` | Missing or wrong `schema_version` (must equal `1`) |
| `IDX011` | Missing `categories:` block, or contents do not match the canonical 8 |

### Tiered severity (default warn → strict-metadata error)

| Code | Meaning |
|---|---|
| `IDX012` | Integration uses an `unknown` marker (`id` / `type` / `requirement`); flagged for owner review. Warning by default; error under `--strict-metadata`. |

### Workflow-level (strict-workflows)

| Code | Meaning |
|---|---|
| `WF001` | Workflow file referenced by index does not exist |
| `WF002` | Workflow `id` does not match filename |
| `WF003` | Step `skill` not found in `skills-index.yaml` |
| `WF004` | `depends_on` references a future step |
| `WF005` | `decision_gate: true` step missing `decision_question` |
| `WF006` | `journal_destination` does not resolve to a skill |
| `WF007` | Step consumes an artifact before it is produced |
| `WF008` | Deprecated skill listed in `required_skills` |
| `WF009` | `required_skills` entry never appears in a non-optional step |
| `WF010` | Non-optional step `skill` missing from `required_skills` |
| `WF011` | `required_skills` / `optional_skills` entry not in `skills-index.yaml` |
| `WF012` | `artifacts[].produced_by_step` does not match the corresponding step's `produces` (either direction) |

### Skillset-level (`scripts/validate_skillsets.py`, always strict)

| Code | Meaning |
|---|---|
| `SK001` | Manifest `id` ≠ filename stem |
| `SK002` | `id` not a canonical skills-index category, or `category` ≠ `id` |
| `SK003` | Missing/invalid scalar (`schema_version`/`display_name`/`timeframe`/`difficulty`/`api_profile`) |
| `SK004` | Missing/blank `when_to_use` / `when_not_to_use` |
| `SK005` | List-field violation: `target_users`/`required_skills`/`related_workflows` not a non-empty `list[str]`; or `recommended_skills`/`optional_skills` key absent or not a `list[str]` (empty list allowed, missing key is not) |
| `SK006` | A `required`/`recommended`/`optional` skill not in `skills-index.yaml` |
| `SK007` | A `required_skills` id is `deprecated` |
| `SK008` | `required`/`recommended`/`optional` not pairwise disjoint |
| `SK009` | A `related_workflows` id has no `workflows/<id>.yaml` |
| `SK010` | `⋃(related workflow.required_skills)` not a subset of this skillset's `required_skills` |
| `SK011` | Single related workflow: `required_skills` set ≠ that workflow's |
| `SK012` | `api_profile` does not cover a related workflow's (`mixed` covers all; any covers `no-api-basic`; else exact provider match — `fmp-required` ≠ `alpaca-required`) |
| `SK013` | `no-api-basic` skillset lists a paid-required skill (fmp/finviz/alpaca @ `required`) anywhere |
| `SK-PARSE` / `SK-MISSING` | YAML parse error / `skillsets/` absent (absent dir = OK) |

---

## 6. Migration policy

- Schema changes: bump `schema_version` only when the change is breaking. Additive fields do NOT bump.
- Field renames: never. Add a new field, deprecate the old one in a comment, remove after one full version cycle.
- Enum value additions: allowed without bumping `schema_version`. Validator must accept unknown enum values gracefully (warn, never crash).
- Removed fields: marked `deprecated` in this doc for one cycle before deletion.

See also: project memory `feedback_schema_evolution.md` — "Add new schema fields, never mutate existing ones for backward compat".
