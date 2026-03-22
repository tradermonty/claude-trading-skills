# Tier 5: Deeper Learning Design

**Date:** 2026-03-22
**Status:** Approved
**Goal:** Make the bot continuously improve from its own trade history. Four learning systems: win rate by time-of-day, stop distance learning, regime confidence scoring, and an experiment tracker for paper trading.

---

## Overview

All four systems extend the existing learning infrastructure (`learning/` directory). They follow the same pattern as `MultiplierStore`: seed priors → observe real outcomes → gradually replace defaults with learned values.

---

## Feature 1: Win Rate by Time-of-Day

### What it does
Tracks win rates per hour of the trading day. Adjusts confidence requirements for new entries based on historical performance at that time.

### Implementation
- New class `TimeOfDayTracker` in `learning/time_of_day_tracker.py`
- Persists to `learning/time_of_day_stats.json`
- On each closed trade: record outcome + entry hour (ET)
- `get_confidence_adjustment(hour)` → returns required min confidence for that hour
  - Hour with win_rate < 40% and n >= 10: require HIGH_CONVICTION
  - Hour with win_rate < 30% and n >= 10: block entirely
  - Otherwise: normal rules apply
- `PatternExtractor` calls this during weekly extraction

### Self-tuning
Starts with no adjustments (all hours equal). Learns from real trade outcomes over weeks/months.

---

## Feature 2: Stop Distance Learning

### What it does
Replaces the hardcoded 3% stop distance with a learned optimal per bucket. Tracks how often stops get hit too early (would have been profitable with wider stop) vs stops that saved capital.

### Implementation
- Extend `MultiplierStore` or new `StopDistanceStore` in `learning/stop_distance_store.py`
- Seed prior: 3.0% (current hardcoded value)
- On each closed trade: record `stop_distance_used` and `outcome`
  - If stop hit but price recovered within same day → "stop too tight"
  - If stop held and position was profitable → "stop appropriate"
- `get_stop_pct(bucket_key)` → returns learned optimal, falls back to 3% if < 10 samples
- `_fire_order()` calls this instead of hardcoded `* 0.97`

---

## Feature 3: Regime Confidence Score

### What it does
Upgrades the binary regime signal (bull/bear/choppy) to a confidence score (0-100). Weak regime signals result in smaller position sizes.

### Implementation
- Macro regime detector already outputs a `score` field — currently ignored
- New helper `get_regime_confidence(cache_dir)` in `pivot_monitor.py`
- Returns score 0-100 from `cache/macro-regime-detector.json`
- Applied as sizing multiplier in `_calc_qty()`:
  - Score >= 75: 1.0 (full size)
  - Score 50-75: 0.75
  - Score 25-50: 0.5
  - Score < 25: 0.25 (very uncertain regime — minimal size)

---

## Feature 4: ExperimentTracker (Paper Trading Only)

### What it does
Occasionally tries parameter variations during paper trading to discover if better settings exist. Runs 90% exploitation (current best) / 10% exploration (random variation). Promotes winners to new defaults when they consistently outperform.

### Implementation
- New class `ExperimentTracker` in `learning/experiment_tracker.py`
- Persists to `learning/experiments.json`
- On each new trade (paper only): 10% chance of using a variation
  - Variation parameters: stop_pct ± 0.5%, partial_exit_at_r ± 0.25, min_volume_ratio ± 0.25
  - Trade tagged with `experiment_id` in `auto_trades.json`
- Weekly: compare experiment outcomes vs control
  - If experiment win_rate > control win_rate + 5% with n >= 10: promote to new default
  - Log promotion to `learning/experiment_log.json`
- Hard gate: NEVER runs in live trading mode

### Tests
- Experiment only fires in paper mode
- Promotion logic: experiment beats control → new default set
- No experiment fires in live mode (hard gate)

---

## Feature 5: Win Rate Dashboard (`/stats` page)

### What it does
New page showing all learned statistics, active experiments, and PDT status.

### Sections
- **Overall stats**: total trades, win rate, avg R, expectancy
- **By bucket**: win rate + avg R per (screener + confidence_tag + regime) combo
- **By time-of-day**: win rate heatmap by hour
- **Active experiments**: current variations vs control performance
- **PDT status**: slots used, slots remaining, resets on (date)
- **Drawdown status**: current weekly/daily drawdown vs limits

### Implementation
- New route `/stats` in `main.py`
- New template `templates/stats.html`
- Reads from all learning JSON files
- No real-time data needed — static render, manual refresh

---

## Architecture Notes
- All learning classes follow constructor injection pattern (testable without real files)
- `PatternExtractor.extract()` calls all learners in sequence: MultiplierStore → TimeOfDayTracker → StopDistanceStore → ExperimentTracker
- ExperimentTracker hard-gated by `alpaca.paper` flag — never runs in live mode
- `/stats` page is read-only, no actions

---

## Future Considerations
- Technical indicator learning (learn which RSI/MACD conditions predict success)
- News sentiment scoring (-10 to +10) replacing binary CLEAR/BLOCKED
- Sector win rate tracking (learn which sectors produce best VCP outcomes)
- Cross-asset correlation learning (avoid trades when correlated assets showing weakness)
- Reinforcement learning integration (more sophisticated than rule-based adaptation)
