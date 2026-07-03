---
name: drawdown-circuit-breaker
description: Evaluate account-level drawdown circuit breaker rules from trader-memory-core state and decide whether new trade risk is allowed today. Uses realized P&L, losing-streak cooldowns, and weekly/monthly drawdown limits without any external API.
---

# Drawdown Circuit Breaker

## Overview

Evaluate whether the trader should take new trade risk today based on account-level realized P&L and recent terminal trade outcomes. This skill reads trader-memory-core thesis YAML files only. It produces a `circuit_breaker_decision` artifact that complements the market-side `exposure_decision` from exposure-coach.

The circuit breaker is a recommendation and recordkeeping tool. It does not replace human judgment, and it does not enforce broker-side blocks or automated order rejection.

## When to Use

- Before screening or sizing any new swing trade candidate
- After a losing trade or partial trim to check whether a cooldown is active
- During daily planning when trader-memory-core contains recent closed or partially closed positions
- As a workflow gate before swing-opportunity-daily proceeds to candidate generation
- When reviewing whether daily, weekly, or monthly loss limits have been breached

## Prerequisites

- Python 3.9+
- Local trader-memory-core thesis YAML files, usually under `state/theses/`
- Account size in dollars
- No API keys or network access required

## Workflow

### Step 1: Read Trader Memory State

Point the script at the thesis state directory:

```bash
python3 skills/drawdown-circuit-breaker/scripts/check_circuit_breaker.py \
  --state-dir state/theses \
  --account-size 100000 \
  --output-dir reports/
```

The script scans every `th_*.yaml` file and reads realized P&L from each thesis `status_history[]` ledger entry. It does not use `_index.json` for P&L, because the index is a lightweight lookup file and does not contain the required realized-P&L ledger.

If the state directory is missing or empty, the skill returns `TRADING_ALLOWED` with `data_quality: EMPTY_STATE` so a new user is not blocked by the absence of history.

### Step 2: Evaluate Circuit Breaker Rules

The default rules are:

| Rule | Default | Triggered State | Release |
|------|---------|-----------------|---------|
| Max daily loss | 2.0% of account | HALTED | Next ET weekday |
| Losing streak cooldown | 2 terminal losing theses | COOLDOWN | 24 hours after latest loss exit |
| Weekly drawdown halt | 5.0% of account | HALTED | Next Monday ET |
| Monthly drawdown halt | 8.0% of account | HALTED | First day of next month ET |

Day, week, and month boundaries use `America/New_York`. Date-only producer
timestamps from `trader-memory-core` are counted on the named ET date. Set
`--as-of` for deterministic evaluation; date-only `--as-of` values cover the
full ET day, while timestamp values exclude future events after that time:

```bash
python3 skills/drawdown-circuit-breaker/scripts/check_circuit_breaker.py \
  --state-dir state/theses \
  --account-size 100000 \
  --as-of 2026-07-02T12:00:00-04:00 \
  --output-dir reports/
```

### Step 3: Override Thresholds When Needed

Override individual thresholds on the CLI:

```bash
python3 skills/drawdown-circuit-breaker/scripts/check_circuit_breaker.py \
  --account-size 100000 \
  --max-daily-loss-pct 1.5 \
  --losing-streak-n 3 \
  --cooldown-hours 48 \
  --weekly-drawdown-pct 4 \
  --monthly-drawdown-pct 6
```

Or provide a JSON config file:

```json
{
  "max_daily_loss_pct": 1.5,
  "losing_streak_n": 3,
  "cooldown_hours": 48,
  "weekly_drawdown_pct": 4.0,
  "monthly_drawdown_pct": 6.0
}
```

CLI arguments override config-file values.

### Step 4: Interpret the Decision

Use the generated decision as a gate for new trade risk:

| Recommendation | Meaning |
|----------------|---------|
| TRADING_ALLOWED | No circuit breaker rule is active; new trade risk may proceed through the rest of the workflow |
| COOLDOWN | Do not open new positions; continue managing existing positions and review the recent losses |
| HALTED | Stop new entries and focus on review until the active halt expires |

Existing position management remains a human decision. The circuit breaker is designed to prevent new risk escalation after realized damage, not to force liquidation.

## Output Format

The script writes `circuit_breaker_decision_YYYY-MM-DD_HHMMSS.json` and, unless `--json-only` is set, a matching markdown report.

```json
{
  "schema_version": "1.0",
  "generated_at": "2026-07-02T16:00:00+00:00",
  "as_of_date": "2026-07-02",
  "recommendation": "COOLDOWN",
  "triggered_rules": [
    {
      "rule": "losing_streak_cooldown",
      "threshold": 2,
      "observed": 2,
      "active_until": "2026-07-02T15:30:00-04:00",
      "detail": "2 consecutive losing closes; last loss exit 2026-07-01T15:30:00-04:00."
    }
  ],
  "metrics": {
    "realized_pnl_today": 0.0,
    "realized_pnl_wtd": -250.0,
    "realized_pnl_mtd": -250.0,
    "consecutive_losses": 2,
    "last_loss_exit_at": "2026-07-01T15:30:00-04:00",
    "theses_scanned": 12
  },
  "account_size": 100000.0,
  "config": {
    "max_daily_loss_pct": 2.0,
    "losing_streak_n": 2,
    "cooldown_hours": 24.0,
    "weekly_drawdown_pct": 5.0,
    "monthly_drawdown_pct": 8.0
  },
  "data_quality": "OK",
  "warnings": [],
  "rationale": "Recent losing closes triggered a cooldown. Avoid new entries until the cooldown expires."
}
```

## Resources

- `scripts/check_circuit_breaker.py` - Main CLI and rule engine
- `references/circuit_breaker_framework.md` - Rule definitions, defaults, and data-source notes
- `skills/trader-memory-core/schemas/thesis.schema.json` - Source schema for thesis state

## Key Principles

1. **Realized damage only** - Use recorded realized P&L, not unrealized P&L or thesis-level cumulative fields for daily calculations.
2. **Survival first** - A circuit breaker exists to prevent escalation after losses.
3. **Advisory, not automatic execution** - The output informs the workflow gate; it does not place, cancel, or block broker orders.
4. **Graceful degradation** - Empty state allows trading; malformed local files degrade data quality to `PARTIAL` without crashing the planning flow.
