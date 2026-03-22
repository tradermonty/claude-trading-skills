# Tier 4: Smarter Sizing Design

**Date:** 2026-03-22
**Status:** Approved
**Goal:** Size positions based on edge strength and market conditions rather than a fixed risk %. Two systems: Kelly-adjusted sizing and volatility-adjusted sizing.

---

## Overview

Position sizing improvements that modify `_calc_qty()` in `PivotWatchlistMonitor`. Both systems apply multipliers to the base risk % rather than replacing it — this keeps the existing logic intact and makes each system independently testable.

Final qty = `base_qty × kelly_multiplier × vix_multiplier`

---

## Feature 1: Kelly-Adjusted Sizing

### What it does
Scales position size based on historical win rate per bucket (screener + confidence_tag + regime). High edge buckets get sized larger, low edge buckets get sized smaller. Only activates when a bucket has ≥10 real trades.

### Formula
`kelly_fraction = win_rate - (loss_rate / avg_rr)`
`kelly_multiplier = clamp(kelly_fraction / base_risk_pct, 0.5, kelly_max_multiplier)`

Where `avg_rr` = average R:R of winning trades in the bucket.

### Implementation
- New method `get_kelly_multiplier(bucket_key)` in `MultiplierStore`
- Reads from `learned_multipliers.json` — already has `observed_rr` and `sample_count`
- Adds win/loss tracking to the learned data: `wins`, `losses`, `avg_rr`
- `PatternExtractor` already records outcomes — add win/loss count aggregation
- Returns 1.0 (no adjustment) if sample_count < 10 or kelly_sizing_enabled = false

### New settings fields
| Field | Default | Description |
|-------|---------|-------------|
| `kelly_sizing_enabled` | false | Opt-in — needs real trade history first |
| `kelly_max_multiplier` | 2.0 | Max multiplier Kelly can apply to base risk % |

### Self-tuning
Kelly naturally self-tunes as more trades are recorded. No manual intervention needed after initial activation.

---

## Feature 2: Volatility-Adjusted Sizing

### What it does
Reduces position size when VIX is elevated. High volatility = wider intraday swings = higher chance of stop-out on noise.

### VIX tiers
| VIX | Size multiplier |
|-----|----------------|
| < 20 | 1.0 (normal) |
| 20–25 | 0.75 |
| 25–30 | 0.50 |
| > 30 | 0.25 |

### Implementation
- Read VIX from existing `cache/us-market-bubble-detector.json` or `cache/macro-regime-detector.json` (VIX already tracked by bubble detector skill)
- New helper `_get_vix_multiplier(cache_dir)` in `pivot_monitor.py`
- If VIX data unavailable → return 1.0 (fail open, no size reduction)
- Applied as multiplier in `_calc_qty()`

### New settings field
| Field | Default | Description |
|-------|---------|-------------|
| `vix_sizing_enabled` | true | Fully automatic — reads from cache |

---

## Architecture Notes
- Both multipliers applied in `_calc_qty()` after base qty calculation
- Order: `base_qty → kelly_multiplier → vix_multiplier → min(result, max_position_size)`
- Kelly multiplier stored in `MultiplierStore` — extends existing learned data structure
- VIX multiplier stateless — recalculated fresh each order

---

## Future Considerations
- Sector momentum sizing (larger positions in outperforming sectors)
- Regime confidence sizing (scale with how strongly bull/bear the regime signal is)
- ATR-based stop distance (replace hardcoded 3% with ATR × multiplier per bucket)
- Options on high-conviction setups (leverage without margin)
