# Example: `monthly-performance-review`

Two deterministic teaching runs for
[`monthly-performance-review`](../../../workflows/monthly-performance-review.yaml)
using three closed fictional trades from May 2026.

> **Illustrative only — not investment advice.** `EXMPL`, `DEMOX`, and `FICTA`
> are invented symbols. Returns, notes, backtest samples, and review findings
> are hand-authored fixtures and make no claim about a real strategy.

| Variant | Optional review layers | Result |
|---|---|---|
| [`sample-run/`](sample-run/) | skipped | 3 trades, 2 wins, 1 loss, `$300` fictional realized P&L; two evidence-linked operating rules |
| [`sample-run-full-path/`](sample-run-full-path/) | coaching + backtest + skill review | Same aggregate plus an `INCONCLUSIVE` hypothesis check and one repo-side backlog item |

The required-only sample contains only artifacts marked `required: true`. The
full path contains all ten workflow artifacts, including the optional
`skill_improvement_backlog` emitted at the required final step.

Trade-side operating rules and repo-side skill improvements remain separate.
Every decision and backlog entry points to an upstream evidence ID so tests can
detect invented or dangling rationales.
