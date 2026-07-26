# Example: `core-portfolio-weekly`

Two deterministic teaching runs for the
[`core-portfolio-weekly`](../../../workflows/core-portfolio-weekly.yaml)
workflow. Both use the same fixed, fictional `$100,000` account and stop before
any broker action.

> **Illustrative only — not investment advice.** `FICTA`, `FICTB`, and `FICTC`
> are invented symbols. The account, holdings, prices, and recommendations are
> hand-authored fixtures; they are not real brokerage data.

| Variant | Optional dividend review | Outcome |
|---|---|---|
| [`sample-run/`](sample-run/) | skipped | Trim 50 fictional `FICTA` shares to restore the 25% target and retain 15% cash |
| [`sample-run-full-path/`](sample-run-full-path/) | included | Same rebalance, plus a T2 `WARN` that pauses optional adds to fictional `FICTC` |

The required-only variant contains only artifacts marked `required: true` in
the workflow manifest. The full-path variant also runs
`kanchi-dividend-review-monitor` and includes its optional artifact.

Each `manifest.yaml` maps workflow steps and artifact IDs to files. The
holdings, allocation, rebalance plan, and journal entry use identical values so
the focused contract test can recompute totals and detect hand-off drift.
Nothing here places or schedules an order.
