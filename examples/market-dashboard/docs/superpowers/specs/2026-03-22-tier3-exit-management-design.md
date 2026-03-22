# Tier 3: Exit Management Design

**Date:** 2026-03-22
**Status:** Approved
**Goal:** Let winners run and cut losers efficiently. Three exit improvements: trailing stop, partial exits, time stop.

---

## Overview

Exit management improvements that modify how bracket orders are managed after entry. These run as a background monitoring loop (already exists via APScheduler) that checks open positions and adjusts stops/takes partial exits as needed.

---

## Feature 1: Trailing Stop

### What it does
Once a position reaches 1R profit, the stop-loss tightens to breakeven. At 2R, stop moves to 1R. Locks in profit as the trade moves in your favor while still letting winners reach the full take-profit target.

### Implementation
- New method `_check_trailing_stops()` in `PivotWatchlistMonitor`
- Runs every 5 minutes via APScheduler during market hours
- For each open position in `auto_trades.json`:
  - Fetch current price from Alpaca
  - Calculate current R: `(current_price - entry_price) / (entry_price - stop_price)`
  - If R >= 1.0 and stop < entry: update stop to entry (breakeven)
  - If R >= 2.0 and stop < entry + 1R: update stop to entry + 1R
  - Update stop order via Alpaca `replace_order()`
- Falls back gracefully if Alpaca order can't be modified (logs warning, continues)

### New settings field
| Field | Default | Description |
|-------|---------|-------------|
| `trailing_stop_enabled` | true | Enable trailing stop management |

### Tests
- At 1R: stop moves to breakeven
- At 2R: stop moves to 1R
- Below 1R: stop unchanged
- Disabled: no changes made

---

## Feature 2: Partial Exits

### What it does
At `partial_exit_at_r` profit, sell `partial_exit_pct`% of the position. Locks in guaranteed profit on every winner while still capturing the full move on remaining shares.

### Implementation
- Tracked in `auto_trades.json` with `partial_exit_done: false` flag per trade
- Checked in same `_check_trailing_stops()` loop
- When R >= `partial_exit_at_r` and `partial_exit_done == false`:
  - Calculate shares to sell: `floor(original_qty * partial_exit_pct / 100)`
  - Place market sell order for that quantity via Alpaca
  - Update `auto_trades.json`: set `partial_exit_done: true`, record `partial_exit_price`
  - Cancel existing take-profit leg, replace with new qty
- If partial exit fails → log error, set flag to avoid retry loop

### New settings fields
| Field | Default | Description |
|-------|---------|-------------|
| `partial_exit_enabled` | true | Enable partial exits |
| `partial_exit_at_r` | 1.0 | R multiple at which to take partial profit |
| `partial_exit_pct` | 50 | % of position to sell at partial exit |

### Tests
- At 1R: partial exit fires, flag set
- Partial exit not repeated (flag check)
- Disabled: no partial exit

---

## Feature 3: Time Stop

### What it does
If a position has been open for `time_stop_days` trading days and price is within ±0.5R of entry (going nowhere), exit and free up capital for better setups.

### Implementation
- Checked in same `_check_trailing_stops()` loop (runs every 5 min)
- For each open position: check `entry_time` vs current date
- If days_open >= `time_stop_days`:
  - Calculate current R
  - If abs(current_R) <= 0.5: place market sell order (exit)
  - Log reason: `"time stop: {symbol} flat after {n} days"`
- Does NOT trigger if position is up >0.5R (let winners run)

### New settings field
| Field | Default | Description |
|-------|---------|-------------|
| `time_stop_days` | 5 | Trading days before flat position is exited. 0 = disabled. |

### Self-tuning (future)
`time_stop_days` will eventually be learned per bucket — some setups resolve faster than others. Seed default = 5, learned from trade history.

---

## Architecture Notes
- New APScheduler job: `check_exit_management` every 5 minutes during market hours
- All three features share one loop (`_check_trailing_stops`) to avoid redundant Alpaca calls
- PDT-aware: trailing stop and partial exit modifications do NOT count as new day trades — only full position closes on the same entry day count
- `auto_trades.json` schema additions: `partial_exit_done`, `partial_exit_price`, `trailing_stop_level`

---

## Future Considerations
- Technical indicator-based exits (exit when RSI drops below 50, MACD crosses negative)
- News-based exits (exit if negative catalyst appears for held position)
- Sector rotation exits (exit if sector starts underperforming)
- Correlation-based position management
