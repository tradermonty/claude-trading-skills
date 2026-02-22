# Trigger Matrix (T1-T5)

Apply these rules to route tickers into `OK`, `WARN`, or `REVIEW`.

## Severity Policy

- `OK`: no forced action.
- `WARN`: queue for next checkpoint and pause optional adds.
- `REVIEW`: immediate human review ticket and pause adds.

## Trigger Definitions

| Trigger | Core signal | Default machine rule | Frequency | Default action |
|---|---|---|---|---|
| T1 | Dividend cut or suspension | `latest_regular < prior_regular * 0.99` OR `latest_regular <= 0` OR missing dividend feed | Daily | `REVIEW` |
| T2 | Coverage deterioration | `denominator <= 0` with positive dividends OR coverage ratio `>1.0` for 2 periods | Quarterly | `WARN/REVIEW` |
| T3 | Credit stress proxy | Net debt rising 3 periods + weakening interest coverage and/or stretched capital return | Weekly + Quarterly confirm | `WARN/REVIEW` |
| T4 | Governance/accounting red flag | Filing text hits Item 4.02, non-reliance, restatement, material weakness, SEC investigation | Daily | `REVIEW` |
| T5 | Structural decline | 2+ simultaneous negatives: revenue CAGR <0, margin downtrend, guidance downtrend, stalled dividend growth | Quarterly | `WARN/REVIEW` |

## Denominator Mapping For T2

| Instrument | Denominator |
|---|---|
| Stock | FCF (`CFO - CapEx`) |
| REIT | FFO/AFFO |
| BDC | NII |
| ETF | Use holdings-level quality proxies if fund-level coverage is unavailable |

## Escalation Rule

If multiple triggers fire, keep all findings and set final state to highest severity:
- `OK < WARN < REVIEW`.

Within T2 itself, sustained breach (`>1.0` for 2 periods) takes priority over single-period breach.
