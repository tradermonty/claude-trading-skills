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

## Coach decision handoff (offline replay)

The full replay passes all three step-3 coach artifacts to step 6. The final
human approval preserves the exact `coach_rule_decision` (source review ID,
action, accepted/modified text, and human notes) in the decision log and the
next-month rules artifact. The log records hashes of all three coach inputs.
`accept_rules` may select only original coach proposals; rewritten text uses
`modify_rules`. `defer` and `journal_only` carry no accepted rules. Duplicate
rule text, stale review IDs, and incomplete coach artifact groups fail validation.
When coaching is skipped, the coach decision and its source hashes are null.

The replay decision fixtures are fictional human inputs. Final `human_approved`
ratifies that recorded coach decision and the separate postmortem-driven
`trade_rule_changes`; these suggestions are not automatically active rules.
Both final artifacts report `rule_activation: not_performed`. The local approved
rule ledger, effective dates, expiry/supersession, pre-trade integration, and next
month's adherence review remain unimplemented under #514. Neither a successful
replay nor its final approval places trades or writes broker state.
