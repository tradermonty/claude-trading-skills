# Tier 2: Entry Quality — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add three entry quality filters to reduce bad trades: volume confirmation, time-of-day soft lock, and breadth-based size reduction.

**Architecture:** All three filters added to `pivot_monitor.py`. Volume and time-of-day checks go in `_guard_rails_allow()`. Breadth reduction applies as a multiplier in `_calc_qty()`. No new files needed. Tasks 1-3 are sequential (same file) but straightforward.

**Tech Stack:** Python 3.11+, FastAPI, Alpaca-py, standard library (datetime, zoneinfo)

**Dependency note:** Tier 2 builds on the same `_guard_rails_allow()` method extended in Tier 1. Implement after Tier 1 Task 4 is complete.

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `pivot_monitor.py` | Modify | Add volume check, time-of-day soft lock, breadth size reduction |
| `alpaca_client.py` | Modify | Add `get_current_volume(symbol)` method if not present |
| `tests/test_pivot_monitor.py` | Modify | Add filter tests |
| `settings_manager.py` | Modify | Add 3 new default settings |
| `templates/fragments/settings_modal.html` | Modify | Add new fields |

---

## Current State Observations

Before starting, read these key facts established by reading the source files:

- `_guard_rails_allow()` currently checks: market hours → market-top-detector pause → max positions. New checks append after max positions.
- `_calc_qty()` currently computes risk-based qty, caps by max position size, and returns `min(qty, max_qty_by_size)`. The breadth multiplier wraps this final `min(...)` result.
- `AlpacaClient` has `get_last_price()` (uses `StockLatestTradeRequest`) and `get_account()` / `get_positions()`, but **no `get_current_volume()` method** — Task 1 must add it.
- `SettingsManager._DEFAULTS` currently has 5 keys. All 5 new keys go here so `load()` always returns them as fallbacks.
- `settings_modal.html` is a plain Jinja2 form with no existing entry-quality fields. New fields append before the Save/Cancel button row.
- `tests/test_pivot_monitor.py` uses a `make_monitor()` helper with `settings.load.return_value` set to a dict. Any test that exercises new settings must extend that dict.
- The `make_monitor()` helper's default settings dict will need the 5 new keys added — update it at the **top of the test file** once, then all existing tests continue to pass.

---

## Tasks

### Task 1: Volume Confirmation

**Scope:** Add `get_current_volume(symbol)` to `AlpacaClient`, add volume check to `_guard_rails_allow()`, add new default setting, write 4 tests.

#### Step 1.1 — Write failing tests

- [ ] Open `tests/test_pivot_monitor.py`
- [ ] Update `make_monitor()` helper to include new defaults in `settings.load.return_value`:
  ```python
  settings.load.return_value = {
      "mode": "auto", "default_risk_pct": 1.0,
      "max_positions": 5, "max_position_size_pct": 10.0,
      "min_volume_ratio": 1.5,
      "avoid_open_close_minutes": 0,   # disabled — keep existing tests green
      "breadth_threshold_pct": 60.0,
      "breadth_size_reduction_pct": 0.0,  # disabled — keep existing tests green
  }
  ```
- [ ] Add test `test_volume_above_threshold_allowed`:
  - Build monitor with `make_monitor(tmp_path)`
  - Patch `monitor._alpaca.get_current_volume` to return `200_000`
  - Set candidate `avg_volume_20d = 100_000` (ratio 2.0 > 1.5 threshold)
  - Patch `_market_is_open_now` → `True`; `get_positions` → `[]`
  - Call `monitor._guard_rails_allow(candidate)`
  - Assert `allowed is True`
- [ ] Add test `test_volume_below_threshold_blocked`:
  - Same setup but `get_current_volume` returns `100_000` and `avg_volume_20d = 200_000` (ratio 0.5 < 1.5)
  - Assert `allowed is False`
  - Assert `"volume"` in reason (case-insensitive)
- [ ] Add test `test_volume_data_missing_fails_open`:
  - `get_current_volume` raises `Exception("API error")`
  - `avg_volume_20d` is present in candidate
  - Assert `allowed is True` (fail open)
- [ ] Add test `test_volume_ratio_zero_always_allows`:
  - Set `min_volume_ratio = 0` in the mock settings dict
  - `get_current_volume` returns `1` (far below any threshold)
  - Assert `allowed is True`
- [ ] Run `uv run pytest tests/test_pivot_monitor.py -v -k "volume"` — confirm all 4 tests **fail** (AttributeError or AssertionError)

#### Step 1.2 — Add `get_current_volume()` to `AlpacaClient`

- [ ] Open `alpaca_client.py`
- [ ] Add method after `get_last_price()`:
  ```python
  def get_current_volume(self, symbol: str) -> int:
      """Return today's accumulated volume for symbol using the latest daily bar."""
      from alpaca.data.requests import StockBarsRequest
      from alpaca.data.timeframe import TimeFrame
      from datetime import date
      request = StockBarsRequest(
          symbol_or_symbols=symbol,
          timeframe=TimeFrame.Day,
          start=date.today().isoformat(),
      )
      bars = self.data_client.get_stock_bars(request)
      symbol_bars = bars.get(symbol, [])
      if not symbol_bars:
          raise ValueError(f"No bar data for {symbol} today")
      return int(symbol_bars[-1].volume)
  ```
- [ ] Verify the method signature matches what the tests expect: `get_current_volume(symbol: str) -> int`

#### Step 1.3 — Add volume check to `_guard_rails_allow()`

- [ ] Open `pivot_monitor.py`
- [ ] Locate `_guard_rails_allow()`. The current final block returns `True, ""`. Insert the volume check **before** that final return, after the max_positions check:
  ```python
  # Volume confirmation
  min_vol_ratio = settings.get("min_volume_ratio", 1.5)
  if min_vol_ratio > 0:
      avg_vol = candidate.get("avg_volume_20d")
      if avg_vol:
          try:
              current_vol = self._alpaca.get_current_volume(candidate["symbol"])
              if current_vol < avg_vol * min_vol_ratio:
                  return False, (
                      f"volume {current_vol}/{int(avg_vol)} "
                      f"below {min_vol_ratio}x threshold"
                  )
          except Exception:
              pass  # fail open — log missing but allow
  ```
- [ ] Note: `settings` is already loaded earlier in `_guard_rails_allow()` for `max_positions`. The volume check reuses that same `settings` dict — do not load it a second time.

#### Step 1.4 — Add new default setting

- [ ] Open `settings_manager.py`
- [ ] Add `"min_volume_ratio": 1.5` to `_DEFAULTS`

#### Step 1.5 — Run tests

- [ ] Run `uv run pytest tests/test_pivot_monitor.py -v -k "volume"` — all 4 tests must **pass**
- [ ] Run `uv run pytest tests/test_pivot_monitor.py -v` — full suite must stay green (no regressions)

#### Step 1.6 — Commit

```
git add pivot_monitor.py alpaca_client.py settings_manager.py tests/test_pivot_monitor.py
git commit -m "feat: Tier 2 Task 1 — volume confirmation guard rail"
```

---

### Task 2: Time-of-Day Soft Lock

**Scope:** Add time-of-day check to `_guard_rails_allow()`, add new default setting, write 4 tests using datetime mocking.

#### Step 2.1 — Write failing tests

- [ ] Open `tests/test_pivot_monitor.py`
- [ ] The `make_monitor()` helper already has `avoid_open_close_minutes: 0` (added in Task 1 Step 1.1). For the time-of-day tests, override the setting in the monitor's mock individually rather than changing the shared helper.
- [ ] Add helper at the top of the new test block:
  ```python
  def make_time_monitor(tmp_path, avoid_minutes=30):
      """make_monitor variant with time-of-day lock enabled."""
      from unittest.mock import MagicMock
      from pivot_monitor import PivotWatchlistMonitor
      alpaca = MagicMock(); alpaca.is_configured = False
      settings = MagicMock()
      settings.load.return_value = {
          "mode": "auto", "default_risk_pct": 1.0,
          "max_positions": 5, "max_position_size_pct": 10.0,
          "min_volume_ratio": 0,           # disable volume check
          "avoid_open_close_minutes": avoid_minutes,
          "breadth_threshold_pct": 60.0,
          "breadth_size_reduction_pct": 0.0,
      }
      alpaca.get_positions.return_value = []
      return PivotWatchlistMonitor(
          alpaca_client=alpaca, settings_manager=settings,
          cache_dir=tmp_path, _search_fn=lambda s: [],
      )
  ```
- [ ] Add test `test_time_lock_high_conviction_allowed_in_open_window`:
  - Use `make_time_monitor(tmp_path, avoid_minutes=30)`
  - Mock `datetime.now()` to return 09:35 ET (5 min after open — inside window)
  - Candidate has `confidence_tag = "HIGH_CONVICTION"`
  - Patch `_market_is_open_now` → `True`
  - Assert `allowed is True`
- [ ] Add test `test_time_lock_clear_blocked_in_open_window`:
  - Same time (09:35 ET), `confidence_tag = "CLEAR"`
  - Assert `allowed is False`
  - Assert `"time-of-day"` in reason (case-insensitive)
- [ ] Add test `test_time_lock_clear_allowed_outside_window`:
  - Mock time to 11:00 ET (mid-session, well outside window)
  - `confidence_tag = "CLEAR"`
  - Assert `allowed is True`
- [ ] Add test `test_time_lock_disabled_when_zero`:
  - `make_time_monitor(tmp_path, avoid_minutes=0)`
  - Mock time to 09:31 ET (right at open)
  - `confidence_tag = "CLEAR"`
  - Assert `allowed is True`
- [ ] Run `uv run pytest tests/test_pivot_monitor.py -v -k "time_lock"` — confirm all 4 **fail**

**Mocking pattern for datetime in `_guard_rails_allow()`:**

The method calls `datetime.now(ZoneInfo("America/New_York"))`. The cleanest approach is to patch `pivot_monitor.datetime` using `unittest.mock.patch`. Use this pattern:

```python
from unittest.mock import patch
from datetime import datetime
from zoneinfo import ZoneInfo

def make_et_time(hour, minute):
    return datetime(2026, 3, 22, hour, minute, 0, tzinfo=ZoneInfo("America/New_York"))

# In test:
with patch("pivot_monitor.datetime") as mock_dt:
    mock_dt.now.return_value = make_et_time(9, 35)
    allowed, reason = monitor._guard_rails_allow(candidate)
```

Note: `pivot_monitor.py` already imports `datetime` from the standard library at the module level (`from datetime import datetime, timezone`). Patching `pivot_monitor.datetime` patches the name in that module's namespace.

#### Step 2.2 — Add time-of-day check to `_guard_rails_allow()`

- [ ] Open `pivot_monitor.py`
- [ ] Insert the following block **after** the volume confirmation block, before `return True, ""`:
  ```python
  # Time-of-day soft lock
  avoid_min = settings.get("avoid_open_close_minutes", 30)
  if avoid_min > 0:
      now_et = datetime.now(ZoneInfo("America/New_York"))
      market_open = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
      market_close = now_et.replace(hour=16, minute=0, second=0, microsecond=0)
      minutes_since_open = (now_et - market_open).total_seconds() / 60
      minutes_to_close = (market_close - now_et).total_seconds() / 60
      in_soft_lock = minutes_since_open < avoid_min or minutes_to_close < avoid_min
      tag = candidate.get("confidence_tag", "CLEAR")
      if in_soft_lock and tag != "HIGH_CONVICTION":
          return False, f"time-of-day soft lock: {tag} blocked in open/close window"
  ```
- [ ] Verify: `ZoneInfo` is already imported at the top of `pivot_monitor.py` (it is — check line 11). No new import needed.
- [ ] Verify: `datetime` is already imported at line 8 as `from datetime import datetime, timezone`. The check uses `datetime.now(...)` which refers to the class — this is what the mock patches.

#### Step 2.3 — Add new default setting

- [ ] Open `settings_manager.py`
- [ ] Add `"avoid_open_close_minutes": 30` to `_DEFAULTS`

#### Step 2.4 — Run tests

- [ ] Run `uv run pytest tests/test_pivot_monitor.py -v -k "time_lock"` — all 4 must **pass**
- [ ] Run `uv run pytest tests/test_pivot_monitor.py -v` — full suite green

#### Step 2.5 — Commit

```
git add pivot_monitor.py settings_manager.py tests/test_pivot_monitor.py
git commit -m "feat: Tier 2 Task 2 — time-of-day soft lock guard rail"
```

---

### Task 3: Breadth-Based Size Reduction

**Scope:** Add `_get_breadth_multiplier()` helper to `PivotWatchlistMonitor`, apply multiplier in `_calc_qty()`, add 2 new default settings, write 4 tests.

#### Step 3.1 — Write failing tests

- [ ] Open `tests/test_pivot_monitor.py`
- [ ] Add helper to write a mock breadth cache:
  ```python
  def write_breadth_cache(tmp_path: Path, pct_above_50ma: float):
      (tmp_path / "market-breadth.json").write_text(json.dumps({
          "pct_above_50ma": pct_above_50ma,
          "generated_at": "2026-03-22T09:35:00",
      }))
  ```
- [ ] Add test `test_breadth_above_threshold_full_size`:
  - Write breadth cache with `pct_above_50ma = 70.0` (above default threshold 60)
  - Settings: `breadth_threshold_pct = 60.0`, `breadth_size_reduction_pct = 50.0`
  - `monitor._alpaca.get_account.return_value = {"portfolio_value": 100_000.0}`
  - Call `monitor._calc_qty(entry_price=100.0, stop_price=97.0, high_conviction=False)`
  - Store result as `qty_with_breadth`
  - Write breadth cache with `pct_above_50ma = 0` (triggers reduction)
  - Set reduction to 0 on the same monitor (patch settings)
  - Call `_calc_qty` again for a baseline
  - Assert `qty_with_breadth` equals the baseline (no reduction applied)

  **Simpler alternative** (preferred — avoids double calculation):
  - Write cache with `pct_above_50ma = 70.0`
  - Set `breadth_size_reduction_pct = 50.0`
  - Call `monitor._get_breadth_multiplier()`
  - Assert result `== 1.0`

- [ ] Add test `test_breadth_below_threshold_reduces_size`:
  - Write cache with `pct_above_50ma = 45.0` (below threshold 60)
  - `breadth_size_reduction_pct = 50.0`
  - Call `monitor._get_breadth_multiplier()`
  - Assert result `== 0.5`
- [ ] Add test `test_breadth_cache_missing_returns_full_size`:
  - Do **not** write `market-breadth.json`
  - Call `monitor._get_breadth_multiplier()`
  - Assert result `== 1.0`
- [ ] Add test `test_breadth_reduction_zero_disables_filter`:
  - Write cache with `pct_above_50ma = 10.0` (very low — would normally trigger)
  - Override settings: `breadth_size_reduction_pct = 0.0`
  - Call `monitor._get_breadth_multiplier()`
  - Assert result `== 1.0`

  **Implementation note:** When `breadth_size_reduction_pct = 0`, the formula `1.0 - (0 / 100) = 1.0`. This naturally returns full size even when below threshold. The test verifies no special-casing is needed, but the logic is: multiply by 1.0 = no reduction. Acceptable to either check `reduction == 0` as an early exit, or rely on the math. Both are fine.

- [ ] Run `uv run pytest tests/test_pivot_monitor.py -v -k "breadth"` — all 4 must **fail** (`AttributeError: '_get_breadth_multiplier'`)

#### Step 3.2 — Add `_get_breadth_multiplier()` helper

- [ ] Open `pivot_monitor.py`
- [ ] Add the helper method to `PivotWatchlistMonitor`, after `_read_cache_field()`:
  ```python
  def _get_breadth_multiplier(self) -> float:
      """Returns size multiplier based on market breadth. 1.0 = full size."""
      settings = self._settings.load()
      threshold = settings.get("breadth_threshold_pct", 60.0)
      reduction = settings.get("breadth_size_reduction_pct", 50.0)
      try:
          data = json.loads((self._cache_dir / "market-breadth.json").read_text())
          pct_above_50ma = float(data.get("pct_above_50ma", 100.0))
          if pct_above_50ma < threshold:
              return 1.0 - (reduction / 100.0)
      except Exception:
          pass
      return 1.0
  ```

#### Step 3.3 — Apply multiplier in `_calc_qty()`

- [ ] Open `pivot_monitor.py`, locate `_calc_qty()`
- [ ] The current final return line is:
  ```python
  return min(qty, max_qty_by_size)
  ```
- [ ] Replace it with:
  ```python
  breadth_mult = self._get_breadth_multiplier()
  return max(1, min(int(min(qty, max_qty_by_size) * breadth_mult), max_qty_by_size))
  ```
  **Rationale for this exact form:**
  - `min(qty, max_qty_by_size)` — cap by position size limit first
  - `* breadth_mult` — apply breadth reduction to the already-capped qty
  - `int(...)` — truncate to whole shares
  - `max(1, ...)` — never return 0 from breadth alone (a 1-share order is still allowed; `_fire_order` checks for `qty <= 0` and will skip)
  - The outer `min(..., max_qty_by_size)` is not strictly needed here because `breadth_mult <= 1.0` always reduces or maintains, but it makes the invariant explicit

  **Alternative simpler form** (also acceptable):
  ```python
  raw_qty = min(qty, max_qty_by_size)
  breadth_mult = self._get_breadth_multiplier()
  return max(1, int(raw_qty * breadth_mult))
  ```

#### Step 3.4 — Add new default settings

- [ ] Open `settings_manager.py`
- [ ] Add both keys to `_DEFAULTS`:
  ```python
  "breadth_threshold_pct": 60.0,
  "breadth_size_reduction_pct": 50.0,
  ```

#### Step 3.5 — Run tests

- [ ] Run `uv run pytest tests/test_pivot_monitor.py -v -k "breadth"` — all 4 must **pass**
- [ ] Run `uv run pytest tests/test_pivot_monitor.py -v` — full suite green

#### Step 3.6 — Commit

```
git add pivot_monitor.py settings_manager.py tests/test_pivot_monitor.py
git commit -m "feat: Tier 2 Task 3 — breadth-based size reduction in _calc_qty"
```

---

### Task 4: Settings Defaults + Modal UI

**Scope:** Verify all 5 new keys are in `_DEFAULTS`, add the fields to `settings_modal.html`, write 2 route-level tests.

#### Step 4.1 — Write failing tests

- [ ] Open `tests/test_routes.py`
- [ ] Add test `test_new_settings_fields_round_trip`:
  ```python
  def test_new_settings_fields_round_trip():
      """All 5 Tier 2 settings fields survive a POST /api/settings round-trip."""
      client = make_client()
      r = client.post("/api/settings", data={
          "mode": "advisory",
          "default_risk_pct": "1.0",
          "max_positions": "5",
          "max_position_size_pct": "10.0",
          "environment": "paper",
          "min_volume_ratio": "2.0",
          "avoid_open_close_minutes": "15",
          "breadth_threshold_pct": "55.0",
          "breadth_size_reduction_pct": "40.0",
      })
      assert r.status_code == 200
      # Verify the saved settings contain the new fields
      from settings_manager import SettingsManager
      saved = SettingsManager().load()
      assert saved["min_volume_ratio"] == 2.0
      assert saved["avoid_open_close_minutes"] == 15
      assert saved["breadth_threshold_pct"] == 55.0
      assert saved["breadth_size_reduction_pct"] == 40.0
  ```

  **Note:** This test will fail for two reasons: (1) the POST handler in `main.py` may not yet forward the new fields — check `main.py` to see how it constructs the settings dict before saving. If it uses `Form(...)` parameters explicitly, add the 4 new Form parameters. If it passes `form_data` through generically, it may already work. (2) The fields need to be numeric (float/int) not strings after save — check how `main.py` type-casts form values.

- [ ] Add test `test_defaults_present_without_settings_file`:
  ```python
  def test_defaults_present_without_settings_file():
      """When settings.json doesn't exist, all Tier 2 defaults must be returned."""
      # clean_settings fixture already deletes the file
      from settings_manager import SettingsManager
      s = SettingsManager().load()
      assert "min_volume_ratio" in s
      assert s["min_volume_ratio"] == 1.5
      assert "avoid_open_close_minutes" in s
      assert s["avoid_open_close_minutes"] == 30
      assert "breadth_threshold_pct" in s
      assert s["breadth_threshold_pct"] == 60.0
      assert "breadth_size_reduction_pct" in s
      assert s["breadth_size_reduction_pct"] == 50.0
  ```

- [ ] Run `uv run pytest tests/test_routes.py -v -k "new_settings or defaults_present"` — confirm both **fail**

#### Step 4.2 — Check and update `main.py` settings route

- [ ] Open `main.py`, find the `POST /api/settings` handler
- [ ] Check how form fields are read. The handler likely reads `Form(...)` typed parameters. Add the 4 new parameters with appropriate types:
  - `min_volume_ratio: float = Form(1.5)`
  - `avoid_open_close_minutes: int = Form(30)`
  - `breadth_threshold_pct: float = Form(60.0)`
  - `breadth_size_reduction_pct: float = Form(50.0)`
- [ ] Make sure the dict passed to `settings_manager.save()` includes all 4 new keys
- [ ] If the handler builds the dict explicitly (e.g. `{"mode": mode, "default_risk_pct": default_risk_pct, ...}`), add the 4 new keys to that dict

#### Step 4.3 — Add fields to `settings_modal.html`

- [ ] Open `templates/fragments/settings_modal.html`
- [ ] Add a visual section divider and the 4 new input rows before the `<div style="display:flex; gap:8px; margin-top:16px;">` (Save/Cancel row). The new section should read:

```html
<!-- Entry Quality (Tier 2) -->
<div style="font-size:11px; color:#9ca3af; margin-top:16px; margin-bottom:8px; text-transform:uppercase; letter-spacing:0.05em;">Entry Quality Filters</div>

<div class="form-row">
  <div class="form-label">Min Volume Ratio (× 20d avg)</div>
  <input type="number" name="min_volume_ratio" class="form-input"
         value="{{ settings.get('min_volume_ratio', 1.5) }}" min="0" max="5" step="0.1">
  <div style="font-size:10px; color:#6b7280; margin-top:2px;">0 = disabled</div>
</div>

<div class="form-row">
  <div class="form-label">Avoid Open/Close (minutes)</div>
  <input type="number" name="avoid_open_close_minutes" class="form-input"
         value="{{ settings.get('avoid_open_close_minutes', 30) }}" min="0" max="60" step="5">
  <div style="font-size:10px; color:#6b7280; margin-top:2px;">0 = disabled; only HIGH_CONVICTION trades in this window</div>
</div>

<div class="form-row">
  <div class="form-label">Breadth Threshold (% above 50MA)</div>
  <input type="number" name="breadth_threshold_pct" class="form-input"
         value="{{ settings.get('breadth_threshold_pct', 60.0) }}" min="0" max="100" step="5">
</div>

<div class="form-row">
  <div class="form-label">Breadth Size Reduction (%)</div>
  <input type="number" name="breadth_size_reduction_pct" class="form-input"
         value="{{ settings.get('breadth_size_reduction_pct', 50.0) }}" min="0" max="100" step="5">
  <div style="font-size:10px; color:#6b7280; margin-top:2px;">0 = disabled; applied when breadth is below threshold</div>
</div>
```

**Note on Jinja2 access:** The existing template accesses settings as `settings.mode`, `settings.default_risk_pct`, etc. (attribute access). If `settings` is a dict, use `settings.get('key', default)`. If it's an object, use `settings.key`. Check `main.py` `GET /api/settings` to see what object type is passed to the template. If it's a plain dict (most likely), use `.get()` as shown above.

#### Step 4.4 — Run tests

- [ ] Run `uv run pytest tests/test_routes.py -v -k "new_settings or defaults_present"` — both must **pass**
- [ ] Run `uv run pytest tests/ -v` — entire test suite green

#### Step 4.5 — Commit

```
git add main.py settings_manager.py templates/fragments/settings_modal.html tests/test_routes.py
git commit -m "feat: Tier 2 Task 4 — entry quality settings defaults and modal UI"
```

---

## Test Commands Reference

| Command | When to use |
|---------|------------|
| `uv run pytest tests/test_pivot_monitor.py -v -k "volume"` | Task 1 red/green cycle |
| `uv run pytest tests/test_pivot_monitor.py -v -k "time_lock"` | Task 2 red/green cycle |
| `uv run pytest tests/test_pivot_monitor.py -v -k "breadth"` | Task 3 red/green cycle |
| `uv run pytest tests/test_routes.py -v -k "new_settings or defaults_present"` | Task 4 red/green cycle |
| `uv run pytest tests/test_pivot_monitor.py -v` | Regression check after each task |
| `uv run pytest tests/ -v` | Full suite — run before final commit |

---

## Guard Rails Order After Tier 2

When fully implemented, `_guard_rails_allow()` checks in this order:

1. Market hours (`_market_is_open_now`) — hard block
2. Market Top Detector risk score ≥ 65 — hard block *(Tier 1)*
3. Max drawdown exceeded — hard block *(Tier 1)*
4. Earnings blackout — hard block *(Tier 1)*
5. Max positions reached — hard block
6. Volume confirmation — soft block (fail open if data missing)
7. Time-of-day soft lock — blocks CLEAR/UNCERTAIN during open/close window

Then in `_calc_qty()`:
8. Breadth multiplier — size reduction (not a block; fail open if cache missing)

---

## Failure Mode Summary

| Filter | Data missing | Ratio/minutes = 0 |
|--------|-------------|-------------------|
| Volume confirmation | Fail open (allow) | Skip check (allow) |
| Time-of-day soft lock | N/A (uses system clock) | Skip check (allow) |
| Breadth size reduction | Fail open (full size) | Skip reduction (full size) |

All three filters follow the same convention: when uncertain, allow the trade at full size. Blocking on missing data would cause false rejections during API outages or on startup before caches are warm.
