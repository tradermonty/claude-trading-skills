# Tier 1: Capital Protection Design

**Date:** 2026-03-22
**Status:** Approved
**Goal:** Protect capital before optimizing for profit. Three guard rails: PDT counter, drawdown circuit breaker, earnings blackout.

---

## Overview

Three independent features that act as safety layers on top of the existing auto-trading system. All three check before any order is placed in `_guard_rails_allow()` in `pivot_monitor.py`. All three are also checked in `order_confirm` for manual trades.

---

## Feature 1: PDT Counter

### What it does
Tracks day trades (same-day open + close) in a rolling 5-business-day window. As slots fill up, the bot gets more selective about new entries. Preserves slots for capital protection exits.

### New file: `learning/pdt_tracker.py`
- `PDTTracker` class
- Persists state to `learning/pdt_trades.json`
- `record_day_trade(symbol, date)` — logs a completed day trade
- `day_trades_used(as_of_date)` — counts day trades in last 5 business days
- `slots_remaining(as_of_date)` — returns 3 - used (min 0)

### Selectivity gates (in `_guard_rails_allow`)
| Slots used | Allowed tags |
|------------|-------------|
| 0 | UNCERTAIN, CLEAR, HIGH_CONVICTION |
| 1 | CLEAR, HIGH_CONVICTION |
| 2 | HIGH_CONVICTION only |
| 3 | No new entries |

When slots = 3, no new entries are opened. Existing positions stay open and managed normally.

### PDT-aware exits
- Default: hold overnight (never same-day exit unless necessary)
- Same-day exit allowed if: price drops within 0.5% of stop-loss OR take-profit hits same day
- A day trade slot is recorded only when both entry and exit occur on the same calendar day

### Tests
- `test_pdt_tracker.py`: 8+ tests covering slot counting, rolling window, edge cases (weekends, holidays)
- `test_pivot_monitor.py`: guard rail tests for each selectivity tier

---

## Feature 2: Drawdown Circuit Breaker

### What it does
Tracks portfolio value at the start of each trading week. If drawdown exceeds the configured threshold, auto trading pauses until Monday.

### Implementation
- `DrawdownTracker` class in `learning/drawdown_tracker.py`
- Persists `week_start_value` and `day_start_value` to `learning/drawdown_state.json`
- Called from `_guard_rails_allow()` — if weekly or daily drawdown exceeded, returns `(False, "drawdown circuit breaker triggered")`
- Portfolio value fetched from Alpaca (`alpaca.get_account()["portfolio_value"]`)

### New settings fields
| Field | Default | Description |
|-------|---------|-------------|
| `max_weekly_drawdown_pct` | 10 | % drop from week start to pause. Set to 100 to disable. |
| `max_daily_loss_pct` | 5 | % drop from day start to pause. Set to 100 to disable. |

### Tests
- `test_drawdown_tracker.py`: weekly trigger, daily trigger, disabled (100%), edge cases

---

## Feature 3: Earnings Blackout

### What it does
Prevents opening new positions in stocks with earnings within `earnings_blackout_days` calendar days. Reads from the existing `earnings-calendar.json` cache.

### Implementation
- `EarningsBlackout` class in `learning/earnings_blackout.py`
- `is_blacked_out(symbol, as_of_date)` — returns True if symbol has earnings within blackout window
- Reads `cache/earnings-calendar.json` (already populated by earnings-calendar skill)
- Called from `_guard_rails_allow()` — returns `(False, "earnings blackout: {symbol} reports in {n} days")`

### New settings field
| Field | Default | Description |
|-------|---------|-------------|
| `earnings_blackout_days` | 5 | Days before earnings to block. 0 = disabled. |

### Tests
- `test_earnings_blackout.py`: symbol in blackout, symbol outside window, missing cache (fail open), disabled

---

## Architecture Notes
- All three classes follow the same pattern as `MultiplierStore`: file-based persistence, constructor injection for testability, graceful fallback on file errors
- `PivotWatchlistMonitor.__init__` gets three new optional parameters: `pdt_tracker=None`, `drawdown_tracker=None`, `earnings_blackout=None`
- `main.py` instantiates all three and passes them in
- Settings modal gets three new fields in the existing settings form

---

## Future Considerations
- Technical indicator confirmation (RSI, MACD, moving average crossovers, support/resistance levels) — deferred to later tier or separate project
- Correlation limiter (don't hold multiple stocks from same sector) — Tier 3+
