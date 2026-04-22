---
name: kill-switch
description: Continuously watch Alpaca account state against the risk limits in trading_params.yaml and trigger a flatten-all when any hard limit is breached. Monitors daily P&L vs max_daily_loss_pct, position count vs max_positions, sector exposure vs max_sector_exposure_pct, correlated positions, and market-top distribution-day count. Run by the launchd watchdog every 2 minutes during market hours. Invoke when the user asks to "check kill-switch", "am I over limits", "what's my daily P&L".
---

# Kill-Switch

The last line of defense. Reads live account state from Alpaca, compares against the
hard limits in trading_params.yaml, and if any limit is breached:

1. Writes `kill_switch_active: true` to a state file.
2. Calls `alpaca-executor/flatten_all.py` with `--reason <breach>`.
3. Blocks the trade-loop-orchestrator from placing new orders until manually reset.

## When to Use

- Every 2 minutes during market hours (launchd agent).
- Invoked on demand by the trade-loop-orchestrator before every loop iteration.
- When user asks "am I over my limit", "what's my daily P&L vs kill switch", "how
  close am I to being flattened".

## What It Checks

| Check | Source | Limit | Action on breach |
|-------|--------|-------|------------------|
| Daily loss % | Alpaca portfolio history vs start-of-day equity | max_daily_loss_pct | FLATTEN + lock |
| Open position count | Alpaca GET /positions | max_positions | BLOCK new entries |
| Sector exposure % | Positions * sector classification | max_sector_exposure_pct | BLOCK new entries in breaching sector |
| Single position % | Position value / account_value | max_position_size_pct | TRIM breaching position |
| Correlated position count | Beta/correlation groupings | max_correlated_positions | BLOCK new entries in correlated bucket |
| Distribution-day count | market-top-detector output | 6 | FORCE_TRIM 25% |

Daily loss is measured vs the `equity_at_market_open` snapshot captured by
`capture_sod.py` (called by the premarket launchd agent). The kill-switch
reads it back; if the file is missing, the check is skipped with a warning.

## Prerequisites

- Same env as alpaca-executor: `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`, `ALPACA_PAPER`
- Access to `config/trading_params.yaml`
- Writable `state/` directory for the SOD snapshot and kill-switch state file

## Workflow

### Daily SOD Capture (09:30 ET)

```bash
python3 skills/kill-switch/scripts/capture_sod.py \
  --output state/sod_$(date +%Y-%m-%d).json
```

Pulls account equity at market open, writes to state.

### Continuous Watchdog (every 2 min, 09:30-16:00 ET)

```bash
python3 skills/kill-switch/scripts/check_limits.py \
  --sod state/sod_$(date +%Y-%m-%d).json \
  --output state/kill_switch_status.json
```

On breach, the script sets `status: TRIPPED`, writes the reason, and calls
`flatten_all.py` itself.

### Pre-loop Check (called by orchestrator)

```bash
python3 skills/kill-switch/scripts/check_limits.py --pre-loop \
  --output state/kill_switch_status.json
```

Same as watchdog but does NOT trigger flatten (the continuous watchdog owns
flattening). Orchestrator reads the output and skips the loop if TRIPPED.

### Reset (manual)

```bash
python3 skills/kill-switch/scripts/reset.py --reason "manual reset after review"
```

Requires explicit user confirmation. Clears the TRIPPED state and re-enables
the loop.

## State File

`state/kill_switch_status.json`:

```json
{
  "checked_at": "2026-04-21T14:30:00Z",
  "status": "OK",
  "account": {"equity": 99500.00, "sod_equity": 100000.00, "pnl_pct": -0.50},
  "positions": {"count": 4, "limit": 6},
  "sector_exposure": {"Technology": 18.3, "Financials": 5.1},
  "breaches": [],
  "reason": null
}
```

On breach:

```json
{
  "checked_at": "2026-04-21T14:32:00Z",
  "status": "TRIPPED",
  "account": {"equity": 94500.00, "sod_equity": 100000.00, "pnl_pct": -5.50},
  "breaches": [
    {"type": "daily_loss", "value": -5.5, "limit": -5.0,
     "message": "Daily loss -5.50% exceeds -5.00% limit"}
  ],
  "reason": "daily_loss: Daily loss -5.50% exceeds -5.00% limit",
  "flatten_all_initiated": true
}
```

## Combining with Other Skills

- **trade-loop-orchestrator**: reads status before every iteration. If TRIPPED, skips.
- **alpaca-executor**: called via `flatten_all.py`.
- **market-top-detector**: if distribution-day count >= 6, also triggers trim.
- **exposure-coach**: not directly, but the kill-switch's block state effectively
  forces exposure to 0% on breach.

## Safety Properties

- **Idempotent**: running it twice when already tripped is a no-op.
- **Fail-safe**: if Alpaca is unreachable, it writes `status: UNKNOWN` and the
  orchestrator treats that as TRIPPED (refuses to trade without account state).
- **Sector classification fallback**: if no GICS sector is available for a ticker,
  it gets counted in an "Unclassified" bucket - caps still apply.
