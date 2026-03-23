# Tier 4: Smarter Sizing — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Size positions based on edge strength (Kelly) and market volatility (VIX) rather than a fixed risk %.

**Architecture:** Kelly multiplier added to `MultiplierStore` (extends existing learned data). VIX multiplier is a stateless helper in `pivot_monitor.py`. Both applied as multipliers in `_calc_qty()`. Tasks 1 (Kelly) and 2 (VIX) are independent and can be dispatched in parallel. Task 3 wires both in.

**Tech Stack:** Python 3.11+, standard library (json, math)

**Parallelization note:** Tasks 1 and 2 modify different files and can be executed concurrently.

**Spec:** `docs/superpowers/specs/2026-03-22-tier4-smart-sizing-design.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `learning/multiplier_store.py` | Modify | Add `get_kelly_multiplier()`, win/loss tracking to learned data |
| `learning/pattern_extractor.py` | Modify | Record win/loss counts when updating multiplier store |
| `pivot_monitor.py` | Modify | Add `_get_vix_multiplier()`, apply both multipliers in `_calc_qty()` |
| `tests/test_multiplier_store.py` | Modify | Add Kelly multiplier tests |
| `tests/test_pivot_monitor.py` | Modify | Add sizing multiplier tests |
| `settings_manager.py` | Modify | Add 3 new settings defaults |

---

## Task 1: Kelly multiplier in MultiplierStore

**Files:**
- Modify: `tests/test_multiplier_store.py`
- Modify: `learning/multiplier_store.py`
- Modify: `learning/pattern_extractor.py`

**What and why:** Kelly Criterion sizes positions larger when a setup has a high historical win rate and favourable R:R, and smaller when it doesn't. By storing `wins`/`losses` alongside the existing `observed_rr` list in `learned_multipliers.json`, we extend the data structure without breaking existing multiplier logic. `PatternExtractor._update_multipliers()` already iterates trades — we add one argument to its existing `update()` call.

### Step 1a: Write the failing tests

Add to `tests/test_multiplier_store.py`:

```python
# ── Kelly multiplier tests ────────────────────────────────────────────────────

def test_kelly_returns_1_when_insufficient_samples():
    """< 10 samples → no adjustment, return 1.0."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        write_learned(tmp, {
            "vcp+CLEAR+bull": {
                "observed_rr": [2.0, 2.5, 3.0],
                "wins": 2, "losses": 1,
                "p75": 3.0, "sample_count": 3,
            }
        })
        store = make_store(tmp)
        assert store.get_kelly_multiplier("vcp+CLEAR+bull", base_risk_pct=1.0) == 1.0


def test_kelly_high_win_rate_returns_multiplier_above_1():
    """High win rate + good R:R → multiplier > 1.0."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        # 8 wins, 2 losses, avg_rr ~3.0 → kelly > base_risk_pct/100 → mult > 1
        write_learned(tmp, {
            "vcp+CLEAR+bull": {
                "observed_rr": [3.0] * 10,
                "wins": 8, "losses": 2,
                "p75": 3.0, "sample_count": 10,
            }
        })
        store = make_store(tmp)
        result = store.get_kelly_multiplier("vcp+CLEAR+bull", base_risk_pct=1.0)
        assert result > 1.0


def test_kelly_low_win_rate_returns_multiplier_below_1():
    """Low win rate → multiplier < 1.0 (reduce size)."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        # 2 wins, 8 losses → kelly fraction small → mult < 1
        write_learned(tmp, {
            "vcp+CLEAR+bull": {
                "observed_rr": [2.0] * 10,
                "wins": 2, "losses": 8,
                "p75": 2.0, "sample_count": 10,
            }
        })
        store = make_store(tmp)
        result = store.get_kelly_multiplier("vcp+CLEAR+bull", base_risk_pct=1.0)
        assert result < 1.0


def test_kelly_multiplier_capped_at_max():
    """Multiplier never exceeds max_multiplier."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        # Perfect win rate, very high R:R → would normally produce huge multiplier
        write_learned(tmp, {
            "vcp+CLEAR+bull": {
                "observed_rr": [10.0] * 10,
                "wins": 10, "losses": 0,
                "p75": 10.0, "sample_count": 10,
            }
        })
        store = make_store(tmp)
        result = store.get_kelly_multiplier("vcp+CLEAR+bull", base_risk_pct=1.0, max_multiplier=2.0)
        assert result <= 2.0


def test_kelly_multiplier_floor_prevents_zero_size():
    """Multiplier never drops below 0.1 — always some position taken."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        # 0 wins, 10 losses → kelly fraction would be 0 or negative
        write_learned(tmp, {
            "vcp+CLEAR+bull": {
                "observed_rr": [1.0] * 10,
                "wins": 0, "losses": 10,
                "p75": 1.0, "sample_count": 10,
            }
        })
        store = make_store(tmp)
        result = store.get_kelly_multiplier("vcp+CLEAR+bull", base_risk_pct=1.0)
        assert result >= 0.1


def test_kelly_returns_1_on_corrupt_data():
    """Corrupt JSON in learned file → graceful fallback to 1.0."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        (tmp / "learned_multipliers.json").write_text("not valid json {{{")
        store = make_store(tmp)
        assert store.get_kelly_multiplier("vcp+CLEAR+bull", base_risk_pct=1.0) == 1.0
```

- [ ] Add these 6 tests to `tests/test_multiplier_store.py`
- [ ] Run `uv run pytest tests/test_multiplier_store.py -k kelly -v` — all 6 should **fail** (method does not exist yet)

### Step 1b: Implement `MultiplierStore.update()` win/loss tracking

The current `update()` signature is `update(self, bucket_key: str, achieved_rr: float) -> None`. Extend it to accept `outcome`:

```python
def update(self, bucket_key: str, achieved_rr: float, outcome: str = "win") -> None:
    """Append a real trade's achieved R:R and recompute p75. Discards bad values."""
    if achieved_rr <= 0 or achieved_rr > _MAX_VALID_RR:
        return
    data = self._load_learned()
    bucket = data.get(bucket_key, {"observed_rr": []})
    bucket["observed_rr"].append(achieved_rr)
    n = len(bucket["observed_rr"])
    bucket["p75"] = _p75(bucket["observed_rr"])
    bucket["sample_count"] = n
    bucket["last_updated"] = date.today().isoformat()
    # Win/loss tracking for Kelly
    bucket["wins"] = bucket.get("wins", 0) + (1 if outcome == "win" else 0)
    bucket["losses"] = bucket.get("losses", 0) + (0 if outcome == "win" else 1)
    data[bucket_key] = bucket
    self._learned_file.parent.mkdir(parents=True, exist_ok=True)
    self._learned_file.write_text(json.dumps(data, indent=2))
```

- [ ] Replace the existing `update()` method in `learning/multiplier_store.py` with the version above
- [ ] Verify the existing `test_update_appends_and_rewrites` and `test_update_discards_invalid_rr` and `test_update_computes_correct_p75` tests still pass — the new `outcome` param is additive and defaults to `"win"`, so no regressions are expected

### Step 1c: Implement `get_kelly_multiplier()` in MultiplierStore

Add the constant and method to `learning/multiplier_store.py` (insert constant after `_MAX_VALID_RR`, add method after `update()`):

```python
KELLY_MIN_SAMPLES = 10


def get_kelly_multiplier(self, bucket_key: str, base_risk_pct: float, max_multiplier: float = 2.0) -> float:
    """Returns Kelly-based size multiplier. Returns 1.0 if insufficient data."""
    try:
        data = self._load_learned()
        bucket = data.get(bucket_key, {})
        wins = bucket.get("wins", 0)
        losses = bucket.get("losses", 0)
        total = wins + losses
        if total < KELLY_MIN_SAMPLES:
            return 1.0

        observed = bucket.get("observed_rr", [])
        if not observed:
            return 1.0

        win_rate = wins / total
        loss_rate = losses / total
        avg_rr = sum(observed) / len(observed)

        kelly = win_rate - (loss_rate / max(avg_rr, 0.1))
        kelly = max(0.1, kelly)  # never size below 10% of base
        multiplier = kelly / (base_risk_pct / 100)
        return round(min(multiplier, max_multiplier), 3)
    except Exception:
        return 1.0
```

- [ ] Add `KELLY_MIN_SAMPLES = 10` constant after `_MAX_VALID_RR` in `learning/multiplier_store.py`
- [ ] Add `get_kelly_multiplier()` method to `MultiplierStore` (after `update()`)
- [ ] Run `uv run pytest tests/test_multiplier_store.py -v` — all tests including the 6 new Kelly tests should **pass**

### Step 1d: Update PatternExtractor to pass outcome to update()

In `learning/pattern_extractor.py`, `_update_multipliers()` currently only calls `self._multiplier_store.update(bucket_key, achieved_rr)` for wins (there is an `if t.get("outcome") != "win": continue` guard). Extend it to also record losses:

```python
def _update_multipliers(self, trades: list[dict]) -> None:
    """Update MultiplierStore for each completed trade with outcome."""
    required = ("exit_price", "stop_price", "entry_price", "screener", "confidence_tag", "regime")
    for t in trades:
        outcome = t.get("outcome")
        if outcome not in ("win", "loss"):
            continue
        if any(t.get(f) is None for f in required):
            continue
        risk = t["entry_price"] - t["stop_price"]
        if risk <= 0:
            continue
        achieved_rr = (t["exit_price"] - t["entry_price"]) / risk
        if outcome == "loss":
            # Use a small positive RR placeholder for losses so observed_rr stays valid
            # The win/loss counters are what Kelly reads; RR floor prevents division by zero
            achieved_rr = max(achieved_rr, 0.01)
            if achieved_rr <= 0:
                # Loss RR is still negative after clamp — record via counter only
                bucket_key = f"{t['screener']}+{t['confidence_tag']}+{t['regime']}"
                # Direct counter update without appending RR (avoid invalid value guard)
                self._record_loss_counter_only(bucket_key)
                continue
        bucket_key = f"{t['screener']}+{t['confidence_tag']}+{t['regime']}"
        self._multiplier_store.update(bucket_key, achieved_rr, outcome=outcome)
```

**Design note:** Losses typically have negative achieved RR (exit below entry). The `_MAX_VALID_RR` guard in `update()` discards values `<= 0`, so loss RR cannot be appended to `observed_rr`. The loss counter is the critical piece for Kelly; `observed_rr` only needs winning trade R:Rs for the avg_rr calculation. The cleanest solution: pass `outcome="loss"` to `update()` and let `update()` skip appending to `observed_rr` when outcome is loss but still increment the counter.

Revise Step 1b's `update()` to handle this correctly:

```python
def update(self, bucket_key: str, achieved_rr: float, outcome: str = "win") -> None:
    """Append a real trade's achieved R:R (wins only) and track win/loss counts."""
    data = self._load_learned()
    bucket = data.get(bucket_key, {"observed_rr": []})

    # Only append RR for wins (RR is meaningful for take-profit sizing, not for Kelly win/loss)
    if outcome == "win":
        if achieved_rr <= 0 or achieved_rr > _MAX_VALID_RR:
            return  # discard invalid win RR entirely
        bucket["observed_rr"].append(achieved_rr)
        n = len(bucket["observed_rr"])
        bucket["p75"] = _p75(bucket["observed_rr"])
        bucket["sample_count"] = n
        bucket["last_updated"] = date.today().isoformat()

    # Win/loss counters for Kelly — always updated for valid outcomes
    bucket["wins"] = bucket.get("wins", 0) + (1 if outcome == "win" else 0)
    bucket["losses"] = bucket.get("losses", 0) + (1 if outcome == "loss" else 0)
    if "last_updated" not in bucket:
        bucket["last_updated"] = date.today().isoformat()

    data[bucket_key] = bucket
    self._learned_file.parent.mkdir(parents=True, exist_ok=True)
    self._learned_file.write_text(json.dumps(data, indent=2))
```

This means `_update_multipliers()` in `PatternExtractor` can simply call `update()` for both wins and losses:

```python
def _update_multipliers(self, trades: list[dict]) -> None:
    """Update MultiplierStore for each completed trade with outcome."""
    required = ("exit_price", "stop_price", "entry_price", "screener", "confidence_tag", "regime")
    for t in trades:
        outcome = t.get("outcome")
        if outcome not in ("win", "loss"):
            continue
        if any(t.get(f) is None for f in required):
            continue
        risk = t["entry_price"] - t["stop_price"]
        if risk <= 0:
            continue
        achieved_rr = (t["exit_price"] - t["entry_price"]) / risk
        bucket_key = f"{t['screener']}+{t['confidence_tag']}+{t['regime']}"
        self._multiplier_store.update(bucket_key, achieved_rr, outcome=outcome)
```

- [ ] Update `learning/multiplier_store.py` `update()` to match the revised version above (wins-only RR append, counters for both)
- [ ] Update `learning/pattern_extractor.py` `_update_multipliers()` to remove the `outcome != "win"` early return guard and pass `outcome=outcome` to `update()`
- [ ] Run `uv run pytest tests/ -v` — full suite should be green

---

## Task 2: VIX multiplier in pivot_monitor.py

**Files:**
- Modify: `tests/test_pivot_monitor.py`
- Modify: `pivot_monitor.py`

**What and why:** VIX measures market fear/volatility. When VIX is elevated, intraday price swings are wider and stops get hit more often on noise. Reducing size in high-VIX regimes preserves capital. VIX data is already written to the cache by the bubble detector and macro regime skills — no new data source required.

### Step 2a: Write the failing tests

Create `tests/test_pivot_monitor.py` (or add to it if it already exists). Use `tmp_path` (pytest fixture) to write fake cache files:

```python
# tests/test_pivot_monitor.py  — VIX multiplier tests
import sys, json
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def make_monitor(tmp_path, settings_overrides=None):
    """Build a PivotWatchlistMonitor with a fake cache dir and minimal deps."""
    from unittest.mock import MagicMock
    from pivot_monitor import PivotWatchlistMonitor
    from settings_manager import SettingsManager

    # Patch SettingsManager.load to return controllable settings
    settings = MagicMock(spec=SettingsManager)
    base = {"vix_sizing_enabled": True, "kelly_sizing_enabled": False}
    if settings_overrides:
        base.update(settings_overrides)
    settings.load.return_value = base

    alpaca = MagicMock()
    monitor = PivotWatchlistMonitor(
        alpaca_client=alpaca,
        settings_manager=settings,
        cache_dir=tmp_path,
    )
    return monitor


def write_bubble_cache(tmp_path, vix: float):
    data = {"vix": vix, "risk_score": 30}
    (tmp_path / "us-market-bubble-detector.json").write_text(json.dumps(data))


def test_vix_below_20_returns_1_0(tmp_path):
    write_bubble_cache(tmp_path, vix=15.0)
    monitor = make_monitor(tmp_path)
    assert monitor._get_vix_multiplier() == 1.0


def test_vix_between_20_and_25_returns_0_75(tmp_path):
    write_bubble_cache(tmp_path, vix=22.5)
    monitor = make_monitor(tmp_path)
    assert monitor._get_vix_multiplier() == 0.75


def test_vix_between_25_and_30_returns_0_50(tmp_path):
    write_bubble_cache(tmp_path, vix=27.0)
    monitor = make_monitor(tmp_path)
    assert monitor._get_vix_multiplier() == 0.50


def test_vix_above_30_returns_0_25(tmp_path):
    write_bubble_cache(tmp_path, vix=35.0)
    monitor = make_monitor(tmp_path)
    assert monitor._get_vix_multiplier() == 0.25


def test_vix_cache_missing_fails_open(tmp_path):
    """No cache file → return 1.0, never block trading."""
    monitor = make_monitor(tmp_path)
    assert monitor._get_vix_multiplier() == 1.0


def test_vix_disabled_returns_1_0(tmp_path):
    write_bubble_cache(tmp_path, vix=40.0)
    monitor = make_monitor(tmp_path, settings_overrides={"vix_sizing_enabled": False})
    assert monitor._get_vix_multiplier() == 1.0
```

- [ ] Add these 6 tests to `tests/test_pivot_monitor.py`
- [ ] Run `uv run pytest tests/test_pivot_monitor.py -k vix -v` — all 6 should **fail** (method does not exist yet)

### Step 2b: Implement `_get_vix_multiplier()` in PivotWatchlistMonitor

Add this method to `PivotWatchlistMonitor` (after `_get_current_regime()`):

```python
def _get_vix_multiplier(self) -> float:
    """Returns size multiplier based on VIX. Lower VIX = full size. Fails open (1.0)."""
    settings = self._settings.load()
    if not settings.get("vix_sizing_enabled", True):
        return 1.0
    try:
        for fname in ["us-market-bubble-detector.json", "macro-regime-detector.json"]:
            fpath = self._cache_dir / fname
            if fpath.exists():
                data = json.loads(fpath.read_text())
                vix = (
                    data.get("vix")
                    or data.get("VIX")
                    or (data.get("indicators") or {}).get("vix")
                )
                if vix is not None:
                    vix = float(vix)
                    if vix < 20:
                        return 1.0
                    elif vix < 25:
                        return 0.75
                    elif vix < 30:
                        return 0.50
                    else:
                        return 0.25
    except Exception:
        pass
    return 1.0  # fail open — no VIX data = no penalty
```

- [ ] Add `_get_vix_multiplier()` to `PivotWatchlistMonitor` in `pivot_monitor.py`
- [ ] Run `uv run pytest tests/test_pivot_monitor.py -k vix -v` — all 6 should **pass**

---

## Task 3: Wire both multipliers into `_calc_qty()`

**Files:**
- Modify: `pivot_monitor.py`
- Modify: `settings_manager.py`
- Modify: `tests/test_pivot_monitor.py`

**Prerequisite:** Tasks 1 and 2 must be complete.

**What and why:** `_calc_qty()` currently returns a raw share count based on risk % and account value. Applying the Kelly and VIX multipliers here keeps all sizing logic in one place. The multipliers are applied after the base qty is calculated, so `max_position_size_pct` still acts as the hard ceiling.

### Step 3a: Add new settings defaults

In `settings_manager.py`, extend `_DEFAULTS`:

```python
_DEFAULTS = {
    "mode": DEFAULT_TRADING_MODE,
    "default_risk_pct": DEFAULT_RISK_PCT,
    "max_positions": DEFAULT_MAX_POSITIONS,
    "max_position_size_pct": DEFAULT_MAX_POSITION_SIZE_PCT,
    "environment": "paper",
    "kelly_sizing_enabled": False,   # opt-in: needs real trade history first
    "kelly_max_multiplier": 2.0,     # max Kelly can multiply base risk by
    "vix_sizing_enabled": True,      # automatic: reads from cache
}
```

- [ ] Add the three new fields to `_DEFAULTS` in `settings_manager.py`

### Step 3b: Write the failing tests

Add to `tests/test_pivot_monitor.py`:

```python
# ── _calc_qty sizing multiplier tests ─────────────────────────────────────────

def make_monitor_with_account(tmp_path, portfolio_value: float, settings_overrides=None):
    """Monitor with a mock Alpaca that returns a fixed portfolio value."""
    from unittest.mock import MagicMock
    from pivot_monitor import PivotWatchlistMonitor
    from settings_manager import SettingsManager

    alpaca = MagicMock()
    alpaca.get_account.return_value = {"portfolio_value": portfolio_value}
    alpaca.get_positions.return_value = []

    settings = MagicMock(spec=SettingsManager)
    base = {
        "default_risk_pct": 1.0,
        "max_position_size_pct": 10.0,
        "kelly_sizing_enabled": False,
        "kelly_max_multiplier": 2.0,
        "vix_sizing_enabled": False,  # disable VIX by default so tests are isolated
    }
    if settings_overrides:
        base.update(settings_overrides)
    settings.load.return_value = base

    monitor = PivotWatchlistMonitor(
        alpaca_client=alpaca,
        settings_manager=settings,
        cache_dir=tmp_path,
    )
    return monitor


def test_calc_qty_kelly_disabled_no_multiplier(tmp_path):
    """Kelly disabled → qty unchanged from base calculation."""
    monitor = make_monitor_with_account(tmp_path, portfolio_value=100_000)
    qty = monitor._calc_qty(
        entry_price=100.0, stop_price=97.0, high_conviction=False, bucket_key="vcp+CLEAR+bull"
    )
    # base: risk $1000 / $3 risk-per-share = 333 shares
    assert qty == 333


def test_calc_qty_kelly_enabled_high_win_rate_increases_qty(tmp_path):
    """Kelly enabled with a high-win-rate bucket → qty larger than base."""
    from unittest.mock import MagicMock, patch
    monitor = make_monitor_with_account(
        tmp_path, portfolio_value=100_000,
        settings_overrides={"kelly_sizing_enabled": True, "kelly_max_multiplier": 2.0},
    )
    # Inject a mock multiplier_store that returns kelly mult of 1.8
    mock_store = MagicMock()
    mock_store.get_kelly_multiplier.return_value = 1.8
    monitor._multiplier_store = mock_store

    base_qty = 333  # from 1% risk on $100k with $3 risk/share
    qty = monitor._calc_qty(
        entry_price=100.0, stop_price=97.0, high_conviction=False, bucket_key="vcp+CLEAR+bull"
    )
    assert qty > base_qty


def test_calc_qty_high_vix_reduces_qty(tmp_path):
    """VIX > 30 → qty reduced to 25% of base."""
    write_bubble_cache(tmp_path, vix=35.0)
    monitor = make_monitor_with_account(
        tmp_path, portfolio_value=100_000,
        settings_overrides={"vix_sizing_enabled": True},
    )
    qty = monitor._calc_qty(
        entry_price=100.0, stop_price=97.0, high_conviction=False, bucket_key="vcp+CLEAR+bull"
    )
    # base 333 × 0.25 = 83 (int floor, min 1)
    assert qty == max(1, int(333 * 0.25))


def test_calc_qty_kelly_and_vix_stack(tmp_path):
    """Kelly mult 1.5 × VIX mult 0.5 = net 0.75 → qty reduced from base."""
    write_bubble_cache(tmp_path, vix=27.0)  # VIX 0.50
    monitor = make_monitor_with_account(
        tmp_path, portfolio_value=100_000,
        settings_overrides={"kelly_sizing_enabled": True, "vix_sizing_enabled": True},
    )
    mock_store = MagicMock()
    mock_store.get_kelly_multiplier.return_value = 1.5
    monitor._multiplier_store = mock_store

    qty = monitor._calc_qty(
        entry_price=100.0, stop_price=97.0, high_conviction=False, bucket_key="vcp+CLEAR+bull"
    )
    expected = max(1, int(333 * 1.5 * 0.50))
    assert qty == expected
```

- [ ] Add these 4 tests to `tests/test_pivot_monitor.py`
- [ ] Run `uv run pytest tests/test_pivot_monitor.py -k calc_qty -v` — tests should **fail** because `_calc_qty` does not yet accept `bucket_key`

### Step 3c: Update `_calc_qty()` signature and body

Replace the current `_calc_qty()` in `pivot_monitor.py`:

```python
def _calc_qty(
    self,
    entry_price: float,
    stop_price: float,
    high_conviction: bool,
    bucket_key: str = "",
) -> int:
    """Calculate share count based on risk % settings, Kelly, and VIX."""
    settings = self._settings.load()
    risk_pct = settings.get("default_risk_pct", 1.0)
    if high_conviction:
        risk_pct = min(risk_pct * 1.5, 5.0)
    max_pos_pct = settings.get("max_position_size_pct", 10.0)
    if high_conviction:
        max_pos_pct = min(max_pos_pct * 1.5, 25.0)

    try:
        portfolio_value = self._alpaca.get_account()["portfolio_value"]
    except Exception:
        return 0

    risk_per_share = entry_price - stop_price
    if risk_per_share <= 0:
        return 0

    dollar_risk = portfolio_value * (risk_pct / 100)
    qty = int(dollar_risk / risk_per_share)

    max_dollar = portfolio_value * (max_pos_pct / 100)
    max_qty_by_size = int(max_dollar / entry_price)

    # Apply Kelly multiplier (opt-in — needs accumulated trade history)
    kelly_mult = 1.0
    if settings.get("kelly_sizing_enabled", False) and self._multiplier_store is not None:
        kelly_max = settings.get("kelly_max_multiplier", 2.0)
        kelly_mult = self._multiplier_store.get_kelly_multiplier(bucket_key, risk_pct, kelly_max)

    # Apply VIX multiplier (automatic — reads from cache, fails open)
    vix_mult = self._get_vix_multiplier()

    final_qty = max(1, int(qty * kelly_mult * vix_mult))
    return min(final_qty, max_qty_by_size)
```

- [ ] Replace `_calc_qty()` in `pivot_monitor.py` with the version above

### Step 3d: Update `_fire_order()` to pass `bucket_key` to `_calc_qty()`

`_fire_order()` already computes `bucket_key` when looking up the take-profit multiplier. Pass it to `_calc_qty()`:

The current call in `_fire_order()` is:
```python
qty = self._calc_qty(entry_price, stop_price, high_conviction=(tag == "HIGH_CONVICTION"))
```

The `bucket_key` is constructed a few lines later as `f"vcp+{tag}+{regime}"`. Reorder so `bucket_key` is computed before `_calc_qty()` is called, then pass it:

```python
regime = self._get_current_regime()
bucket_key = f"vcp+{tag}+{regime}"
qty = self._calc_qty(entry_price, stop_price, high_conviction=(tag == "HIGH_CONVICTION"), bucket_key=bucket_key)
```

Remove the duplicate `regime = self._get_current_regime()` call that follows (since it is now computed above).

- [ ] Update `_fire_order()` in `pivot_monitor.py` to compute `regime` and `bucket_key` before calling `_calc_qty()`, and pass `bucket_key=bucket_key`
- [ ] Ensure the subsequent `multiplier = self._multiplier_store.get(bucket_key)` call still works (bucket_key is already in scope)

### Step 3e: Run the full test suite

- [ ] Run `uv run pytest tests/ -v`
- [ ] All tests must pass — zero regressions on existing multiplier store and pattern extractor tests

---

## Acceptance Criteria

- `MultiplierStore.update()` stores `wins`/`losses` counters alongside `observed_rr`
- `MultiplierStore.get_kelly_multiplier()` returns 1.0 for < 10 samples, a clamped multiplier otherwise
- `PivotWatchlistMonitor._get_vix_multiplier()` reads from cache, applies the 4-tier table, and fails open
- `_calc_qty()` applies both multipliers after base qty, respects `kelly_sizing_enabled` / `vix_sizing_enabled` flags
- `kelly_sizing_enabled` defaults to `False` in `_DEFAULTS` (safe — requires opt-in after trade history builds up)
- `vix_sizing_enabled` defaults to `True` in `_DEFAULTS` (automatic — safe default)
- All 20 new tests pass; full suite has zero regressions

---

## Implementation Notes

- **Kelly is opt-in for safety.** New deployments have no trade history. Enabling Kelly with 0 samples would fall through to the `< KELLY_MIN_SAMPLES` guard (returns 1.0), but an explicit `False` default makes the intent clear and prevents surprises if the guard condition is ever modified.
- **VIX multiplier fails open.** If the cache files are stale, absent, or corrupt, `_get_vix_multiplier()` returns 1.0. Never block or reduce a trade because of a missing monitoring artifact.
- **Multipliers stack multiplicatively.** A high-conviction Kelly setup in a high-VIX environment can partially cancel out — this is intentional. Volatility risk is real regardless of edge strength.
- **`observed_rr` only stores winning trades.** Losses have negative RR which the existing `_MAX_VALID_RR` guard discards. The Kelly formula uses `wins`, `losses`, and `avg_rr` (from `observed_rr`) — this is correct: `avg_rr` represents the reward when you win.
- **No new files.** All changes extend existing files — `MultiplierStore`, `PatternExtractor`, `PivotWatchlistMonitor`, `SettingsManager`.
