# Tier 2: Entry Quality Design

**Date:** 2026-03-22
**Status:** Approved
**Goal:** Reduce bad entries. Three filters applied before any order fires: volume confirmation, time-of-day soft lock, breadth filter.

---

## Overview

Three entry filters added to `_guard_rails_allow()` in `pivot_monitor.py`. All three are additive — a candidate must pass all active filters to proceed to order placement.

---

## Feature 1: Volume Confirmation

### What it does
Only fires orders when breakout volume exceeds a threshold relative to the 20-day average. High volume on a breakout confirms institutional participation.

### Implementation
- Read `avg_volume_20d` from VCP cache candidate data (already present in VCP screener output)
- Fetch current day volume from Alpaca: `alpaca.get_current_volume(symbol)`
- If `current_volume < avg_volume_20d * min_volume_ratio` → block with reason `"volume {current}/{avg} below {ratio}x threshold"`
- If volume data unavailable → fail open (allow trade, log warning)

### New settings field
| Field | Default | Description |
|-------|---------|-------------|
| `min_volume_ratio` | 1.5 | Current volume must be this multiple of 20d avg. 0 = disabled. |

### Tests
- Volume above threshold → allowed
- Volume below threshold → blocked
- Volume data missing → allowed (fail open)
- Disabled (ratio=0) → always allowed

---

## Feature 2: Time-of-Day Soft Lock

### What it does
During the first and last N minutes of the trading day (high spread, erratic price action), only HIGH_CONVICTION setups are allowed through. CLEAR and UNCERTAIN are blocked.

### Implementation
- Check current ET time against market open (09:30) and close (16:00)
- If within `avoid_open_close_minutes` of open or close:
  - HIGH_CONVICTION → allowed
  - CLEAR → blocked: `"time-of-day soft lock: CLEAR blocked during open/close window"`
  - UNCERTAIN → blocked (already filtered earlier)

### New settings field
| Field | Default | Description |
|-------|---------|-------------|
| `avoid_open_close_minutes` | 30 | Minutes from open/close to soft-lock. 0 = disabled. |

### Rationale
HIGH_CONVICTION already requires both institutional buying AND positive news catalyst — the strongest possible signal. This justifies trading during volatile windows.

### Tests
- HIGH_CONVICTION during open window → allowed
- CLEAR during open window → blocked
- CLEAR outside window → allowed
- Disabled (0 minutes) → always allowed

---

## Feature 3: Breadth Filter

### What it does
When market breadth is weak (fewer than `breadth_threshold_pct`% of S&P stocks above 50MA), reduce position size instead of blocking. Weak breadth = headwinds, but good setups can still work with smaller size.

### Implementation
- Read `pct_above_50ma` from `cache/market-breadth.json`
- If below threshold: multiply calculated qty by `(1 - breadth_size_reduction_pct/100)`
- Applied in `_calc_qty()` as a multiplier after normal sizing
- If breadth cache missing → fail open (use normal size, log warning)

### New settings fields
| Field | Default | Description |
|-------|---------|-------------|
| `breadth_threshold_pct` | 60 | Below this % of stocks above 50MA = weak breadth |
| `breadth_size_reduction_pct` | 50 | How much to reduce size when breadth is weak |

### Tests
- Breadth above threshold → normal size
- Breadth below threshold → reduced size
- Breadth cache missing → normal size (fail open)

---

## Architecture Notes
- All three filters are added to `_guard_rails_allow()` — checked in order: PDT (Tier 1) → drawdown (Tier 1) → earnings blackout (Tier 1) → volume → time-of-day → breadth
- Breadth size reduction is passed as a multiplier to `_calc_qty()` rather than a hard block
- No new classes needed — logic lives in `pivot_monitor.py` with helper methods

---

## Future Considerations
- RSI filter (only buy stocks with RSI 50-70 — trending but not overbought)
- Moving average confirmation (price above 50MA and 200MA)
- MACD momentum confirmation
- Support/resistance level detection
- Multi-timeframe confirmation (weekly chart must also be in uptrend)
- These deferred to later tier or separate technical indicators project
