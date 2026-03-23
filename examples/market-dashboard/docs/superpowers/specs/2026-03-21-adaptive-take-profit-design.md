# Adaptive Take-Profit Multiplier — Design Spec

**Date:** 2026-03-21
**Status:** Approved

## Overview

Replace the hardcoded 2:1 take-profit multiplier in `place_bracket_order()` with a per-setup learned multiplier. The system starts with published research priors (Minervini, O'Neil/IBD) and updates toward observed R:R from real closed trades. Learning is keyed on three dimensions: screener, confidence tag, and market regime.

---

## 1. Data Model

### Bucket key

Format: `"{screener}+{confidence_tag}+{regime}"`

Examples:
- `"vcp+CLEAR+bull"`
- `"canslim+UNCERTAIN+choppy"`
- `"vcp+HIGH_CONVICTION+bull"`

Dimensions:
- `screener` — which skill surfaced the candidate: `vcp`, `canslim`, etc.
- `confidence_tag` — existing field: `CLEAR`, `UNCERTAIN`, `HIGH_CONVICTION`
- `regime` — a short string: `bull`, `choppy`, `bear`, `contraction`, `unknown`

### `auto_trades.json` — field changes

**Fields already present:** `order_id`, `entry_price`, `stop_price`, `confidence_tag`, `outcome`

**New field to add at log time:**
- `screener` — which skill surfaced the candidate

**Existing field to fix:**
- `macro_regime` is the current field name (stored as a dict like `{"current_regime": "contraction", ...}`). The implementation must:
  1. Rename the field to `regime` in `_log_trade()`
  2. Extract the string value: `data.get("regime", {}).get("current_regime", "unknown")`
  3. Store the string (e.g. `"contraction"`), not the full dict

**Field written back by PatternExtractor after outcome resolution:**
- `exit_price` — actual fill price of the sell leg

R:R formula: `achieved_rr = (exit_price - entry_price) / (entry_price - stop_price)`

---

## 2. Seed Multipliers (`learning/seed_multipliers.json`)

Static JSON file encoding published research priors. Treated as a high-weight prior (equivalent to 50 trades) so it dominates until sufficient real data accumulates. The file is version-controlled and can be edited manually if better research data becomes available.

```json
{
  "vcp+CLEAR+bull":              { "multiplier": 3.0,  "sample_count": 50, "source": "Minervini Stage Analysis" },
  "vcp+CLEAR+choppy":            { "multiplier": 1.75, "sample_count": 50, "source": "Minervini — reduce targets in choppy" },
  "vcp+CLEAR+bear":              { "multiplier": 1.5,  "sample_count": 50, "source": "Minervini — tight targets in downtrends" },
  "vcp+CLEAR+contraction":       { "multiplier": 1.5,  "sample_count": 50, "source": "Minervini — contraction = bear-equivalent" },
  "vcp+UNCERTAIN+bull":          { "multiplier": 2.0,  "sample_count": 30, "source": "Minervini — lower confidence, conservative" },
  "vcp+UNCERTAIN+choppy":        { "multiplier": 1.5,  "sample_count": 30, "source": "Minervini — uncertain + choppy, take early" },
  "vcp+HIGH_CONVICTION+bull":    { "multiplier": 3.5,  "sample_count": 40, "source": "Minervini — institutional + positive catalyst" },
  "canslim+CLEAR+bull":          { "multiplier": 2.5,  "sample_count": 40, "source": "O'Neil CANSLIM documented win rates" },
  "canslim+CLEAR+choppy":        { "multiplier": 1.75, "sample_count": 30, "source": "O'Neil — reduced target in non-trending" },
  "canslim+UNCERTAIN+bull":      { "multiplier": 2.0,  "sample_count": 25, "source": "O'Neil CANSLIM" }
}
```

Any bucket not in the seed file falls back to `2.0` (preserves current hardcoded default).

---

## 3. `MultiplierStore` (`learning/multiplier_store.py`)

New class. Manages reading and writing `learning/learned_multipliers.json`.

### `get(bucket_key) -> float`

Returns the multiplier to use for an order:

1. Load `learned_data` for `bucket_key` from `learned_multipliers.json`
2. Load `seed_data` for `bucket_key` from `seed_multipliers.json`
3. Let `n_real = len(learned_data.get("observed_rr", []))`
4. Blending logic:
   - `n_real >= MIN_SAMPLE_COUNT` (5): return `learned_data["p75"]`
   - `1 <= n_real < 5`: weighted blend — `(seed_weight * seed_val + n_real * observed_p75) / (seed_weight + n_real)` where `seed_weight = seed_data["sample_count"]`
   - `n_real == 0` and bucket in seed: return `seed_data["multiplier"]`
   - `n_real == 0` and bucket not in seed: return `2.0`
5. On any file read error: log warning and return `2.0`

The 75th percentile means 75% of past winners in that bucket actually reached this target — conservative enough to be realistic, ambitious enough not to undersell.

### `update(bucket_key, achieved_rr: float) -> None`

- Discard values `<= 0` or `> 20` (data errors)
- Append `achieved_rr` to `learned_data["observed_rr"]`
- Recompute `p75` using the full list
- Update `sample_count` and `last_updated`
- Write to `learned_multipliers.json`

### `learned_multipliers.json` schema

```json
{
  "vcp+CLEAR+bull": {
    "observed_rr": [2.8, 3.1, 2.4, 3.6, 2.9],
    "p75": 3.1,
    "sample_count": 5,
    "last_updated": "2026-03-28"
  }
}
```

---

## 4. PatternExtractor Changes

Two additions to the existing weekly `extract()` job.

### 4a. Save `exit_price` on outcome resolution

`_get_order_outcome()` already fetches `leg.filled_avg_price`. Change its return type from `str | None` to `tuple[str, float] | None` — returning `(outcome_str, exit_price)`.

Update `refresh_trade_outcomes()` to unpack this tuple and write `exit_price` back to the trade entry in `auto_trades.json`.

### 4b. Update MultiplierStore after outcome resolution

Add a `MultiplierStore` parameter to `PatternExtractor.__init__()` (optional, default `None` for backwards compatibility).

After `refresh_trade_outcomes()` in `extract()`, loop over all trades with `outcome == "win"`:
- Validate all required fields are present: `exit_price`, `stop_price`, `entry_price`, `screener`, `confidence_tag`, `regime`
- Skip any trade missing any field (log at DEBUG level)
- Compute `achieved_rr = (exit_price - entry_price) / (entry_price - stop_price)`
- Build `bucket_key = f"{screener}+{confidence_tag}+{regime}"`
- Call `multiplier_store.update(bucket_key, achieved_rr)`

Losses are excluded — they inform entry quality (already handled by `RuleStore`), not how far winners run.

**Known limitation:** Orders placed before a multiplier is learned use the prior/default. The multiplier is not applied retroactively to open orders. This is acceptable and by design.

---

## 5. Order Flow Integration

There are two order paths. Both must use the learned multiplier.

### 5a. Auto mode — `pivot_monitor._fire_order()`

`PivotWatchlistMonitor` only reads from `vcp-screener.json`, so `screener` is always `"vcp"`.

Changes to `_fire_order()`:
1. Read `regime` from cache and extract the string: `data.get("regime", {}).get("current_regime", "unknown")`
2. Build `bucket_key = f"vcp+{tag}+{regime}"`
3. Call `multiplier_store.get(bucket_key)` → `multiplier`
4. Compute `take_profit_price = round(entry_price + (entry_price - stop_price) * multiplier, 2)`
5. Pass `take_profit_price` explicitly to `place_bracket_order()`

Changes to `_log_trade()`:
1. Rename `macro_regime` field to `regime` — store the extracted string, not the dict
2. Add `"screener": "vcp"` field

`MultiplierStore` is injected into `PivotWatchlistMonitor.__init__()` (optional, default `None`; when `None` falls back to `2.0` hardcoded as before).

### 5b. Manual mode — `main.py` order routes

For manual orders the user reviews the candidate before confirming.

Changes to `OrderConfirmRequest`:
- Add `skill: str` (maps to screener name)
- Add `confidence_tag: str = "CLEAR"` (default: user manually chose to order it)

Changes to `order_confirm()`:
1. Read `regime` from `cache/macro-regime-detector.json`; extract `current_regime` string; default to `"unknown"`
2. Build `bucket_key = f"{body.skill}+{body.confidence_tag}+{regime}"`
3. Call `multiplier_store.get(bucket_key)` → `multiplier`
4. Compute `take_profit_price = round(body.limit_price + (body.limit_price - body.stop_price) * multiplier, 2)`
5. Pass to `place_bracket_order()`
6. Log trade to `auto_trades.json` with `screener=body.skill`, `regime`, `confidence_tag`, `stop_price`

Changes to `order_preview()`:
- Compute and pass `multiplier` and `bucket_key` to the template context for display
- Template shows: `"Take-profit: {multiplier:.1f}× R — based on {n} {bucket_key} trades"` or `"from published research"` when using seed

Changes to `order_preview.html` template:
- Add a row showing the multiplier and its source
- Pass `skill` and `confidence_tag` as hidden fields through to the confirm form

`MultiplierStore` is instantiated once in `main.py` alongside `rule_store` and injected into both `PivotWatchlistMonitor` and the order routes.

### `place_bracket_order()` — no changes

Already accepts optional `take_profit_price`; falls back to hardcoded 2:1 only when `None`. All callers now pass an explicit value.

---

## 6. Error Handling

- `MultiplierStore` file read fails → log warning, return `2.0`
- `achieved_rr <= 0` or `> 20` → discard silently (bad fill or data corruption)
- `stop_price` missing or zero in a trade entry → skip in PatternExtractor update loop
- `regime` cache missing → default to `"unknown"` (bucket key still valid, falls back to seed or 2.0)
- Any exception in `multiplier_store.get()` → catch, log, return `2.0` (never block order placement)

---

## 7. Testing

Follow TDD — write failing tests first, then implement.

### `test_multiplier_store.py`
- `get()` returns seed value when no real trades exist
- `get()` returns weighted blend with 3 real trades
- `get()` returns p75 of observed R:R with 5+ real trades
- `get()` returns `2.0` for unknown bucket with no seed
- `update()` appends to `observed_rr` and rewrites correctly
- `update()` discards `achieved_rr <= 0` and `> 20`
- `get()` returns `2.0` when file is unreadable (error handling)
- `update()` computes correct p75 (e.g. 5 values: [2.0, 2.5, 3.0, 3.5, 4.0] → p75 = 3.5)

### `test_pattern_extractor.py` (additions)
- `exit_price` is written back to trade entry after outcome resolution
- `MultiplierStore.update()` is called for winning trades with correct `achieved_rr`
- `MultiplierStore.update()` is NOT called for losing trades
- Trade missing `stop_price` is skipped without error
- Trade missing `regime` is skipped without error

### `test_pivot_monitor.py` (additions)
- `_fire_order()` passes computed `take_profit_price` to `place_bracket_order()`
- `_log_trade()` stores `"screener": "vcp"` field
- `_log_trade()` stores `regime` as a string, not a dict

### `test_routes.py` (additions)
- `order_confirm` computes multiplier and passes `take_profit_price` to `place_bracket_order()`
- `order_confirm` with missing `regime` cache defaults to `"unknown"` bucket without error
- `order_preview` template context includes `multiplier` and `multiplier_source`

---

## 8. File Summary

| File | Change |
|------|--------|
| `learning/multiplier_store.py` | New class |
| `learning/seed_multipliers.json` | New seed data file (version-controlled) |
| `learning/learned_multipliers.json` | Auto-created on first update, gitignored |
| `learning/pattern_extractor.py` | Save exit_price; accept MultiplierStore; call update() for wins |
| `pivot_monitor.py` | _fire_order: lookup multiplier; _log_trade: add screener + fix regime field |
| `main.py` | Instantiate MultiplierStore; order_confirm: lookup multiplier + log trade; order_preview: show multiplier |
| `templates/fragments/order_preview.html` | Display multiplier and source; pass skill+confidence_tag to confirm form |
| `auto_trades.json` (runtime) | Add screener; fix regime to string; add exit_price at resolution |
| `alpaca_client.py` | No changes |
