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
| [`trade-memory-loop/sample-run/`](trade-memory-loop/sample-run/) | [`trade-memory-loop.yaml`](../../workflows/trade-memory-loop.yaml) | per closed trade | required-only | trader-memory-core → signal-postmortem → trader-memory-core |
| [`trade-memory-loop/sample-run-full-path/`](trade-memory-loop/sample-run-full-path/) | same | per closed trade | **full-path** | + optional backtest-expert at step 3 |

Each workflow ships two sample variants:

- **`sample-run/` (required-only)** — exercises just the required steps. The
  one optional step in each workflow is intentionally skipped and documented
  in that example's `manifest.yaml` (`optional_steps_skipped`).
- **`sample-run-full-path/` (full-path)** — runs the optional step too, so
  every step in the workflow manifest is exercised. For `market-regime-daily`
  this also strips the top-level `*_score` workflow hand-off fields from the
  upstream fixtures so the sample exercises the **nested-shape parser** in
  `exposure-coach` directly (see the "Artifact convention" note below).

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

## Coupling

These files are intentionally **decoupled** from the generated-docs / drift-gate
machinery: no generator, validator, snapshot builder, catalog, CI metadata
job, or pytest path reads `examples/`. Editing or extending them cannot cause
catalog/snapshot/docs drift. (They are still subject to the standard
hygiene pre-commit hooks — whitespace, YAML syntax, `detect-secrets`,
`no-absolute-paths`, etc.)
