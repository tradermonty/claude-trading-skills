# Example: `swing-opportunity-daily`

Two deterministic teaching runs for
[`swing-opportunity-daily`](../../../workflows/swing-opportunity-daily.yaml).
Both begin with a self-contained, non-restrictive
`market-regime-daily/exposure_decision` fixture and stop at the manual
pre-trade discipline gate.

> **Illustrative only — not investment advice.** `EXMPL` is an invented
> symbol. Prices, chart findings, and account values are hand-authored
> fixtures. No order is submitted or represented as submitted.

| Variant | Optional steps | Final gate |
|---|---|---|
| [`sample-run/`](sample-run/) | skipped | `GO` for a fictional, not-submitted 200-share plan |
| [`sample-run-full-path/`](sample-run-full-path/) | all included | `GO` after four optional screens and an optional trade plan |

The required-only variant includes only artifacts marked `required: true`.
The full path includes all eleven artifacts in the workflow manifest. The
upstream exposure fixture is recorded separately as a prerequisite input, not
as an artifact produced by this workflow.

The position-sizer output uses an entry of `$50.00`, stop of `$47.50`, a
`$100,000` fictional account, and `0.5%` planned risk. The deterministic result
is 200 whole shares and `$500` risk. The same values flow through the thesis
and discipline decision, which makes cross-artifact drift testable.
