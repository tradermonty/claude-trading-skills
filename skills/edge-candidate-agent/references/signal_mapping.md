# Signal Mapping

Use this mapping to decide whether a research ticket can be exported to
`trade-strategy-pipeline` under interface v1.

| Hypothesis Type | Export Status | Entry Family | Notes |
|---|---|---|---|
| `breakout` | exportable | `pivot_breakout` | Requires `vcp_detection` block. |
| `earnings_drift` | exportable | `gap_up_continuation` | Use gap continuation config; avoid walk-forward in Phase I. |
| `momentum` | research-only | n/a | Keep as ticket until pipeline supports dedicated momentum entry. |
| `pullback` | research-only | n/a | Keep as ticket until pullback signal family is added. |
| `sector_x_stock` | research-only | n/a | Keep as ticket until sector-relative filters are first-class in strategy spec. |
| `panic_reversal` | research-only | n/a | Keep as ticket until reversal signal family is implemented. |
| `low_vol_quality` | research-only | n/a | Keep as ticket until quality/risk filters become signal inputs. |
| `regime_shift` | research-only | n/a | Keep as ticket until regime transition entry is supported in pipeline. |

## Rule

If a ticket is `research-only`, do not generate `strategy.yaml`.
Record the ticket and queue for future interface/version expansion.
