# Drawdown Circuit Breaker Framework

## Purpose

The drawdown circuit breaker is an account-level risk gate for new trade risk. It answers one question before screening or sizing: "Is the trader's account state clear enough to take another new trade today?"

This is the trader-side companion to the market-side exposure gate. Exposure-coach asks whether the market environment allows new exposure. Drawdown-circuit-breaker asks whether the trader's realized account damage and recent execution results allow new risk.

## Source Data

Read only trader-memory-core thesis YAML files from `state/theses/` or a caller-provided `--state-dir`.

Use these fields:

- `status_history[][].realized_pnl` for realized P&L ledger entries
- `status_history[][].at` for the realized P&L event timestamp
- `status` to identify terminal theses (`CLOSED`, `INVALIDATED`)
- `exit.actual_date`, falling back to the last terminal `status_history[].at`, parsed and converted to `America/New_York` for terminal trade ordering
- `outcome.pnl_dollars` for terminal win/loss classification

Do not use `_index.json` for P&L. It is a lightweight lookup index and does not contain the ledger required for partial trims or daily realized-P&L accounting.

## Calendar Rules

All daily, weekly, and monthly realized-P&L aggregations use `America/New_York` dates.

- Daily: events whose ET date equals the as-of date and whose timestamp is not after `--as-of`
- Weekly: events from Monday ET through the as-of timestamp
- Monthly: events from the first calendar day of the ET month through the as-of timestamp

`trader-memory-core` widens bare producer dates to UTC midnight (for example
`2026-07-02T00:00:00+00:00`). This artifact is counted on the named ET
accounting date, not the prior ET evening.

The script accepts `--as-of` so tests and sample runs can freeze the evaluation date.
Date-only values cover the full ET day; timestamp values are exact cutoffs.

## Default Rules

| Rule | Default | State | Active Until |
|------|---------|-------|--------------|
| `max_daily_loss` | Realized loss reaches 2.0% of account size on the as-of ET date | `HALTED` | Next ET weekday |
| `losing_streak_cooldown` | Two consecutive terminal theses have negative `outcome.pnl_dollars` | `COOLDOWN` | 24 hours after the latest losing exit |
| `weekly_drawdown_halt` | Week-to-date realized loss reaches 5.0% of account size | `HALTED` | Next Monday ET |
| `monthly_drawdown_halt` | Month-to-date realized loss reaches 8.0% of account size | `HALTED` | First day of next ET month |

Break-even terminal theses count as wins. This matches trader-memory-core monthly review behavior, where `pnl >= 0` is classified as a win.

If multiple rules trigger, return the strictest state:

1. `HALTED`
2. `COOLDOWN`
3. `TRADING_ALLOWED`

Include every active triggered rule in the JSON artifact even when a stricter rule determines the final recommendation.

## Data Quality

| Value | Meaning |
|-------|---------|
| `OK` | State directory existed, thesis files loaded, and no malformed ledger or terminal records were skipped |
| `EMPTY_STATE` | State directory was missing, or it was an existing directory containing no `th_*.yaml` files |
| `PARTIAL` | At least one data warning was emitted, including skipped/conflicting risk data or a recovered finite legacy outcome |

`EMPTY_STATE` returns `TRADING_ALLOWED`. The skill should not block a new user just because no trader-memory-core state exists yet.

`PARTIAL` fails closed with `HALTED` and an `incomplete_state_data` rule whenever the configured state path is not a directory, or whenever a thesis, ledger entry, or terminal result is skipped, malformed, non-finite, missing, or conflicts with another P&L source. Its `active_until` is `null` because release requires state repair and a rerun, not elapsed time. The sole recoverable warning is a finite `outcome.pnl_dollars` value used for a legacy terminal thesis that has no realized-P&L ledger entry and otherwise has parseable terminal history. For `ACTIVE`, `PARTIALLY_CLOSED`, `CLOSED`, and `INVALIDATED` theses, every history event must be an object with a recognized `status` and parseable `at`, and the last history status must match the thesis status. `ACTIVE` and `PARTIALLY_CLOSED` theses must also carry entry actuals; `PARTIALLY_CLOSED` must carry a position. Malformed, stale, or skeletal lifecycle history disqualifies the fallback and halts. Ledger-shaped events -- `status: PARTIALLY_CLOSED`, or any of `shares_sold`, `quantity_sold`, `price`, `proceeds` -- whose `realized_pnl` is missing, untyped, or non-finite also halt instead of being coerced. The recoverable fallback remains `PARTIAL` for audit visibility but does not by itself change the calculated recommendation.

Account size and all percentage/hour thresholds must be positive and finite. Non-finite P&L never enters metrics or terminal streak calculations, and JSON output is serialized with non-finite values disabled.

## Configuration

Defaults can be overridden with CLI flags or a JSON config file. CLI flags take precedence.

```json
{
  "max_daily_loss_pct": 2.0,
  "losing_streak_n": 2,
  "cooldown_hours": 24,
  "weekly_drawdown_pct": 5.0,
  "monthly_drawdown_pct": 8.0
}
```

Use lower thresholds for capital-preservation mode and higher thresholds only after the trader has documented why the extra variance is acceptable.

## Workflow Gate Contract

The workflow artifact ID is `circuit_breaker_decision`.

The swing-opportunity-daily workflow should proceed to new candidate generation only when:

```text
circuit_breaker_decision.recommendation == "TRADING_ALLOWED"
```

`COOLDOWN` and `HALTED` both block new entries. They do not automatically force exits or broker actions.
