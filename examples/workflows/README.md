# Workflow Examples

Canonical, hand-authored **sample runs** for the multi-skill workflows defined
in [`workflows/*.yaml`](../../workflows/). Each sub-directory shows the exact
prompt you would give Claude, plus the artifact each required step contributes
to the workflow's data flow, plus a machine-readable `manifest.yaml` that a
future fixture/replay harness can consume.

> ⚠️ **Illustrative only — not investment advice.** Every artifact here uses
> **fictional / hand-authored data** (the trade example uses the fictional
> ticker `EXMPL`; the market-regime example uses a fictional market snapshot
> with **no individual tickers**). These files are teaching/reference samples,
> **not** live signals, recommendations, or real skill output captured from a
> real account. Do not trade off them.

## Available examples

| Example | Workflow | Cadence | Sample variant | Skills |
|---|---|---|---|---|
| [`market-regime-daily/sample-run/`](market-regime-daily/sample-run/) | [`market-regime-daily.yaml`](../../workflows/market-regime-daily.yaml) | daily | required-only | market-breadth-analyzer → uptrend-analyzer → exposure-coach |
| [`market-regime-daily/sample-run-full-path/`](market-regime-daily/sample-run-full-path/) | same | daily | **full-path** | + optional market-top-detector at step 3 |
| [`core-portfolio-weekly/sample-run/`](core-portfolio-weekly/sample-run/) | [`core-portfolio-weekly.yaml`](../../workflows/core-portfolio-weekly.yaml) | weekly | required-only | portfolio-manager → trader-memory-core |
| [`core-portfolio-weekly/sample-run-full-path/`](core-portfolio-weekly/sample-run-full-path/) | same | weekly | **full-path** | + optional kanchi-dividend-review-monitor at step 3 |
| [`swing-opportunity-daily/sample-run/`](swing-opportunity-daily/sample-run/) | [`swing-opportunity-daily.yaml`](../../workflows/swing-opportunity-daily.yaml) | daily | required-only | circuit breaker → VCP → chart validation → sizing → journal → discipline gate |
| [`swing-opportunity-daily/sample-run-full-path/`](swing-opportunity-daily/sample-run-full-path/) | same | daily | **full-path** | + all five optional candidate/plan steps |
| [`trade-memory-loop/sample-run/`](trade-memory-loop/sample-run/) | [`trade-memory-loop.yaml`](../../workflows/trade-memory-loop.yaml) | per closed trade | required-only | trader-memory-core → signal-postmortem → trader-memory-core |
| [`trade-memory-loop/sample-run-full-path/`](trade-memory-loop/sample-run-full-path/) | same | per closed trade | **full-path** | + optional backtest-expert at step 3 |
| [`monthly-performance-review/sample-run/`](monthly-performance-review/sample-run/) | [`monthly-performance-review.yaml`](../../workflows/monthly-performance-review.yaml) | monthly | required-only | trader-memory-core → signal-postmortem → trader-memory-core |
| [`monthly-performance-review/sample-run-full-path/`](monthly-performance-review/sample-run-full-path/) | same | monthly | **full-path** | + coaching, backtest, skill review, and improvement backlog |

The three samples added for `core-portfolio-weekly`,
`swing-opportunity-daily`, and `monthly-performance-review` use this strict
variant contract:

- **`sample-run/` (required-only)** — includes every artifact declared
  `required: true` and records every optional workflow step in
  `optional_steps_skipped`.
- **`sample-run-full-path/` (full-path)** — runs every workflow step and
  includes every declared artifact, including optional artifacts emitted by a
  required step.

The older `market-regime-daily` and `trade-memory-loop` examples predate this
strict coverage contract and retain their historical fixture layouts.
`market-regime-daily/sample-run-full-path/` also strips the top-level
`*_score` workflow hand-off fields from the upstream fixtures so the sample
exercises the **nested-shape parser** in `exposure-coach` directly (see the
"Artifact convention" note below).

Every sample is a static teaching fixture. Fixed dates and explicitly fictional
symbols/accounts make the calculations reproducible. They contain no broker
credentials, real account data, order submission, or investment advice.
`swing-opportunity-daily` also carries a self-contained, non-restrictive
`market-regime-daily` prerequisite artifact; the sample stops at the manual
pre-trade discipline gate.

## Artifact convention: `raw-plus-handoff`

The sample JSON artifacts are **workflow hand-off artifacts**, not byte-for-byte
copies of raw skill stdout:

- The nested `composite { … }` block **mirrors the real skill output
  structure** (e.g. `market-breadth-analyzer` and `uptrend-analyzer` both nest
  their score at `composite.composite_score`).
- A **top-level hand-off field** (`breadth_score` / `uptrend_score`) is added
  alongside it. This is the field the Claude-orchestrated next step actually
  consumes when it hands a score to `exposure-coach`.

This convention exists in `sample-run/` because the original parser in
`exposure-coach` only read the top-level `*_score` hand-off fields for
breadth and top-risk — the nested `composite.composite_score` shape that the
real upstream skills actually emit was silently dropped. That parser gap was
**fixed by [PR #137](https://github.com/tradermonty/claude-trading-skills/pull/137)**
(merged 2026-05-24), which added nested-shape reading and correct polarity
for `breadth` (direct), `top_risk` (inverted as `100 - score`), and `ftd`
(direct, since a Follow-Through Day is bullish bottom-confirmation).

The new **`sample-run-full-path/`** variant therefore omits the top-level
hand-off fields and provides raw nested fixtures so that running the
post-PR-#137 `exposure-coach` extractors over them reproduces the scores in
`04_exposure_decision.json`. The required-only `sample-run/` is kept
unchanged (raw-plus-handoff convention preserved) as a reference for
workflows that already produce both shapes.

## Validation and coupling

These files remain **decoupled** from generated docs, catalogs, snapshots,
skill packages, and workflow generation. A focused pytest contract covers the
three strict samples above: manifest/workflow parity, optional-step coverage,
safe relative paths, schema/business invariants where available, and
cross-artifact arithmetic. The historical examples are not silently rewritten
by that contract. All files also remain subject to standard hygiene hooks
(whitespace, YAML syntax, `detect-secrets`, `no-absolute-paths`, and related
checks).
