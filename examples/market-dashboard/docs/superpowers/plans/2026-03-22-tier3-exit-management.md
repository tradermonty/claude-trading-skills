# Tier 3: Exit Management — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add trailing stops, partial exits, and time stops to manage open positions after entry.

**Architecture:** New `_check_exit_management()` method in `PivotWatchlistMonitor` handles all three exit types in one loop. Runs every 5 minutes via APScheduler during market hours. Reads/writes `auto_trades.json` for state. Tier 3 is independent of Tiers 1 and 2 — can be implemented in parallel.

**Tech Stack:** Python 3.11+, APScheduler, Alpaca-py, standard library (json, datetime)

**Parallelization note:** Tier 3 is fully independent of Tiers 1 and 2. Can be implemented concurrently.

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `pivot_monitor.py` | Modify | Add `_check_exit_management()` + 3 exit methods |
| `alpaca_client.py` | Modify | Add `replace_order_stop()`, `place_market_sell()` if missing |
| `scheduler.py` | Modify | Add 5-minute exit management job |
| `main.py` | Modify | Pass pivot_monitor to scheduler for exit job |
| `tests/test_pivot_monitor.py` | Modify | Add exit management tests |
| `settings_manager.py` | Modify | Add 3 new settings defaults |
| `templates/fragments/settings_modal.html` | Modify | Add exit management fields |

---

## Task 1: AlpacaClient — add order management methods

**Files:**
- Modify: `alpaca_client.py`
- Modify: `tests/test_alpaca_client.py` (create if not present)

**Context:** `alpaca_client.py` currently has `place_bracket_order`, `get_last_price`, `get_positions`, and `get_account`. It does not have `replace_order_stop` or `place_market_sell`. Both are needed by the exit management loop.

- [ ] **Step 1: Write the failing tests**

Create or append to `tests/test_alpaca_client.py`:

```python
# tests/test_alpaca_client.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from unittest.mock import MagicMock, patch
from alpaca_client import AlpacaClient


def make_client(trading_client=None):
    return AlpacaClient(
        api_key="test_key",
        secret_key="test_secret",
        paper=True,
        _trading_client=trading_client or MagicMock(),
    )


# ── replace_order_stop ───────────────────────────────────────────────────────

def test_replace_order_stop_calls_replace_on_trading_client():
    mock_tc = MagicMock()
    mock_result = MagicMock()
    mock_result.id = "ord-abc"
    mock_result.status = "accepted"
    mock_tc.replace_order_by_id.return_value = mock_result

    client = make_client(mock_tc)
    result = client.replace_order_stop("ord-abc", 98.50)

    mock_tc.replace_order_by_id.assert_called_once()
    call_args = mock_tc.replace_order_by_id.call_args
    assert call_args[0][0] == "ord-abc"
    assert result == {"id": "ord-abc", "status": "accepted"}


def test_replace_order_stop_passes_new_stop_price():
    mock_tc = MagicMock()
    mock_result = MagicMock()
    mock_result.id = "ord-xyz"
    mock_result.status = "pending_replace"
    mock_tc.replace_order_by_id.return_value = mock_result

    client = make_client(mock_tc)
    client.replace_order_stop("ord-xyz", 102.25)

    _, call_kwargs = mock_tc.replace_order_by_id.call_args
    # The second argument should be a ReplaceOrderRequest with stop_price set
    replace_req = mock_tc.replace_order_by_id.call_args[0][1]
    assert replace_req.stop_price == 102.25


# ── place_market_sell ────────────────────────────────────────────────────────

def test_place_market_sell_calls_submit_order():
    mock_tc = MagicMock()
    mock_result = MagicMock()
    mock_result.id = "sell-ord-1"
    mock_result.status = "new"
    mock_tc.submit_order.return_value = mock_result

    client = make_client(mock_tc)
    result = client.place_market_sell("AAPL", 10)

    mock_tc.submit_order.assert_called_once()
    assert result == {"id": "sell-ord-1", "status": "new"}


def test_place_market_sell_uses_sell_side_and_day_tif():
    from alpaca.trading.enums import OrderSide, TimeInForce

    mock_tc = MagicMock()
    mock_result = MagicMock()
    mock_result.id = "sell-ord-2"
    mock_result.status = "new"
    mock_tc.submit_order.return_value = mock_result

    client = make_client(mock_tc)
    client.place_market_sell("TSLA", 5)

    req = mock_tc.submit_order.call_args[0][0]
    assert req.symbol == "TSLA"
    assert req.qty == 5
    assert req.side == OrderSide.SELL
    assert req.time_in_force == TimeInForce.DAY
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd examples/market-dashboard
uv run pytest tests/test_alpaca_client.py -v
```

Expected: `AttributeError` — `replace_order_stop` and `place_market_sell` do not exist yet.

- [ ] **Step 3: Add methods to alpaca_client.py**

Append these two methods to the `AlpacaClient` class (after `place_bracket_order`, before `start_trading_stream`):

```python
def replace_order_stop(self, order_id: str, new_stop_price: float) -> dict:
    """Replace the stop price on an existing order leg."""
    from alpaca.trading.requests import ReplaceOrderRequest
    req = ReplaceOrderRequest(stop_price=new_stop_price)
    result = self.trading_client.replace_order_by_id(order_id, req)
    return {"id": str(result.id), "status": str(result.status)}

def place_market_sell(self, symbol: str, qty: int) -> dict:
    """Place an immediate market sell order."""
    from alpaca.trading.requests import MarketOrderRequest
    from alpaca.trading.enums import OrderSide, TimeInForce
    req = MarketOrderRequest(
        symbol=symbol, qty=qty, side=OrderSide.SELL, time_in_force=TimeInForce.DAY
    )
    result = self.trading_client.submit_order(req)
    return {"id": str(result.id), "status": str(result.status)}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd examples/market-dashboard
uv run pytest tests/test_alpaca_client.py -v
```

Expected: all 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add alpaca_client.py tests/test_alpaca_client.py
git commit -m "feat: add replace_order_stop and place_market_sell to AlpacaClient"
```

---

## Task 2: Exit management loop — `_check_exit_management()`

**Files:**
- Modify: `pivot_monitor.py`
- Modify: `tests/test_pivot_monitor.py`

**Context:** This is the orchestrator method. It guards on market hours, reads `auto_trades.json`, filters to open trades (where `outcome is None`), and calls each of the three exit sub-methods. It writes the file back only if any sub-method returned `True`. The three sub-methods (`_apply_trailing_stop`, `_apply_partial_exit`, `_apply_time_stop`) are added in Tasks 3–5. Write a stub for each here to make the loop tests pass independently.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_pivot_monitor.py`:

```python
# ── Exit management loop ─────────────────────────────────────────────────────

def write_auto_trades(tmp_path: Path, trades: list):
    (tmp_path / "auto_trades.json").write_text(json.dumps({"trades": trades}, indent=2))


def test_check_exit_management_skips_when_no_trades_file():
    """Should return without error when auto_trades.json does not exist."""
    with tempfile.TemporaryDirectory() as d:
        monitor = make_monitor(Path(d))
        import pivot_monitor as pm
        original = pm._market_is_open_now
        pm._market_is_open_now = lambda: True
        try:
            monitor._check_exit_management()  # must not raise
        finally:
            pm._market_is_open_now = original


def test_check_exit_management_skips_outside_market_hours():
    """Should return immediately when market is closed."""
    with tempfile.TemporaryDirectory() as d:
        monitor = make_monitor(Path(d))
        write_auto_trades(Path(d), [
            {"symbol": "AAPL", "entry_price": 100.0, "stop_price": 97.0,
             "qty": 10, "outcome": None, "stop_order_id": "ord1",
             "entry_time": "2026-03-20T14:00:00+00:00"},
        ])
        import pivot_monitor as pm
        pm._market_is_open_now = lambda: False
        called = []
        monitor._apply_trailing_stop = lambda t, s: called.append("trailing") or False
        monitor._apply_partial_exit = lambda t, s: called.append("partial") or False
        monitor._apply_time_stop = lambda t, s: called.append("time") or False
        monitor._check_exit_management()
        assert called == []


def test_check_exit_management_skips_closed_trades():
    """Trades with outcome set must not be passed to sub-methods."""
    with tempfile.TemporaryDirectory() as d:
        monitor = make_monitor(Path(d))
        write_auto_trades(Path(d), [
            {"symbol": "AAPL", "entry_price": 100.0, "stop_price": 97.0,
             "qty": 10, "outcome": "win", "stop_order_id": "ord1",
             "entry_time": "2026-03-15T14:00:00+00:00"},
        ])
        import pivot_monitor as pm
        original = pm._market_is_open_now
        pm._market_is_open_now = lambda: True
        called = []
        monitor._apply_trailing_stop = lambda t, s: called.append("trailing") or False
        try:
            monitor._check_exit_management()
        finally:
            pm._market_is_open_now = original
        assert called == []


def test_check_exit_management_writes_file_when_changed():
    """File must be rewritten when any sub-method returns True."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        monitor = make_monitor(tmp)
        write_auto_trades(tmp, [
            {"symbol": "AAPL", "entry_price": 100.0, "stop_price": 97.0,
             "qty": 10, "outcome": None, "stop_order_id": "ord1",
             "entry_time": "2026-03-20T14:00:00+00:00"},
        ])
        import pivot_monitor as pm
        original = pm._market_is_open_now
        pm._market_is_open_now = lambda: True

        def fake_trailing(trade, settings):
            trade["stop_price"] = 100.0  # mutate trade to simulate a change
            return True

        monitor._apply_trailing_stop = fake_trailing
        monitor._apply_partial_exit = lambda t, s: False
        monitor._apply_time_stop = lambda t, s: False
        try:
            monitor._check_exit_management()
        finally:
            pm._market_is_open_now = original

        result = json.loads((tmp / "auto_trades.json").read_text())
        assert result["trades"][0]["stop_price"] == 100.0


def test_check_exit_management_does_not_write_file_when_unchanged():
    """File must NOT be rewritten when all sub-methods return False."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        monitor = make_monitor(tmp)
        write_auto_trades(tmp, [
            {"symbol": "AAPL", "entry_price": 100.0, "stop_price": 97.0,
             "qty": 10, "outcome": None, "stop_order_id": "ord1",
             "entry_time": "2026-03-20T14:00:00+00:00"},
        ])
        import os
        mtime_before = os.path.getmtime(str(tmp / "auto_trades.json"))

        import pivot_monitor as pm
        original = pm._market_is_open_now
        pm._market_is_open_now = lambda: True
        monitor._apply_trailing_stop = lambda t, s: False
        monitor._apply_partial_exit = lambda t, s: False
        monitor._apply_time_stop = lambda t, s: False
        try:
            monitor._check_exit_management()
        finally:
            pm._market_is_open_now = original

        mtime_after = os.path.getmtime(str(tmp / "auto_trades.json"))
        assert mtime_before == mtime_after
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd examples/market-dashboard
uv run pytest tests/test_pivot_monitor.py::test_check_exit_management_skips_when_no_trades_file tests/test_pivot_monitor.py::test_check_exit_management_skips_outside_market_hours tests/test_pivot_monitor.py::test_check_exit_management_skips_closed_trades tests/test_pivot_monitor.py::test_check_exit_management_writes_file_when_changed tests/test_pivot_monitor.py::test_check_exit_management_does_not_write_file_when_unchanged -v
```

Expected: `AttributeError: 'PivotWatchlistMonitor' object has no attribute '_check_exit_management'`

- [ ] **Step 3: Add `_check_exit_management()` and method stubs to pivot_monitor.py**

Add the following block to `PivotWatchlistMonitor`, after the `_read_cache_field` method and before `start()`:

```python
# ── Exit management ──────────────────────────────────────────────────────────

def _check_exit_management(self) -> None:
    """Check all open positions for trailing stop, partial exit, and time stop triggers."""
    from pivot_monitor import _market_is_open_now
    if not _market_is_open_now():
        return

    settings = self._settings.load()
    trades_file = self._cache_dir / "auto_trades.json"
    if not trades_file.exists():
        return

    try:
        data = json.loads(trades_file.read_text())
    except (json.JSONDecodeError, OSError):
        return

    open_trades = [t for t in data.get("trades", []) if t.get("outcome") is None]
    if not open_trades:
        return

    changed = False
    for trade in open_trades:
        try:
            changed |= self._apply_trailing_stop(trade, settings)
            changed |= self._apply_partial_exit(trade, settings)
            changed |= self._apply_time_stop(trade, settings)
        except Exception as e:
            print(f"[exit_mgmt] {trade.get('symbol')} error: {e}", file=sys.stderr)

    if changed:
        trades_file.write_text(json.dumps(data, indent=2))

def _apply_trailing_stop(self, trade: dict, settings: dict) -> bool:
    """Stub — implemented in Task 3."""
    return False

def _apply_partial_exit(self, trade: dict, settings: dict) -> bool:
    """Stub — implemented in Task 4."""
    return False

def _apply_time_stop(self, trade: dict, settings: dict) -> bool:
    """Stub — implemented in Task 5."""
    return False
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd examples/market-dashboard
uv run pytest tests/test_pivot_monitor.py::test_check_exit_management_skips_when_no_trades_file tests/test_pivot_monitor.py::test_check_exit_management_skips_outside_market_hours tests/test_pivot_monitor.py::test_check_exit_management_skips_closed_trades tests/test_pivot_monitor.py::test_check_exit_management_writes_file_when_changed tests/test_pivot_monitor.py::test_check_exit_management_does_not_write_file_when_unchanged -v
```

Expected: all 5 PASS.

- [ ] **Step 5: Run the full test suite to confirm no regressions**

```bash
cd examples/market-dashboard
uv run pytest tests/ -v
```

Expected: all existing tests still PASS.

- [ ] **Step 6: Commit**

```bash
git add pivot_monitor.py tests/test_pivot_monitor.py
git commit -m "feat: add _check_exit_management() orchestrator loop with stubs for three exit methods"
```

---

## Task 3: Trailing stop — `_apply_trailing_stop()`

**Files:**
- Modify: `pivot_monitor.py` (replace stub)
- Modify: `tests/test_pivot_monitor.py`

**Logic:**
- At 1R: move stop to breakeven (`entry_price`)
- At 2R: move stop to 1R profit (`entry_price + risk`)
- Both moves only fire if the new stop is strictly greater than the current stop (no ratchet backwards)
- Calls `self._alpaca.replace_order_stop(stop_order_id, new_stop)` to push the change to Alpaca
- Mutates `trade["stop_price"]` and `trade["trailing_stop_level"]` in-place; returns `True`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_pivot_monitor.py`:

```python
# ── Trailing stop ────────────────────────────────────────────────────────────

def make_trailing_trade(entry=100.0, stop=97.0, stop_order_id="stop-ord-1"):
    return {
        "symbol": "AAPL",
        "entry_price": entry,
        "stop_price": stop,
        "stop_order_id": stop_order_id,
        "qty": 10,
        "outcome": None,
        "entry_time": "2026-03-20T14:00:00+00:00",
    }


def test_trailing_stop_moves_to_breakeven_at_1r():
    """At 1R profit (price=103), stop should move from 97 to 100 (entry)."""
    with tempfile.TemporaryDirectory() as d:
        monitor = make_monitor(Path(d))
        monitor._alpaca.get_last_price.return_value = 103.0  # entry=100, stop=97 → risk=3, 1R=103
        monitor._alpaca.replace_order_stop.return_value = {"id": "stop-ord-1", "status": "accepted"}
        trade = make_trailing_trade()
        settings = {"trailing_stop_enabled": True}

        result = monitor._apply_trailing_stop(trade, settings)

        assert result is True
        assert trade["stop_price"] == 100.0
        assert trade["trailing_stop_level"] == 100.0
        monitor._alpaca.replace_order_stop.assert_called_once_with("stop-ord-1", 100.0)


def test_trailing_stop_moves_to_1r_profit_at_2r():
    """At 2R profit (price=106), stop should move to entry+risk=103."""
    with tempfile.TemporaryDirectory() as d:
        monitor = make_monitor(Path(d))
        monitor._alpaca.get_last_price.return_value = 106.0  # 2R
        monitor._alpaca.replace_order_stop.return_value = {"id": "stop-ord-1", "status": "accepted"}
        trade = make_trailing_trade()
        settings = {"trailing_stop_enabled": True}

        result = monitor._apply_trailing_stop(trade, settings)

        assert result is True
        assert trade["stop_price"] == 103.0
        assert trade["trailing_stop_level"] == 103.0
        monitor._alpaca.replace_order_stop.assert_called_once_with("stop-ord-1", 103.0)


def test_trailing_stop_no_change_below_1r():
    """Below 1R (price=102.5 < 103), stop must not move."""
    with tempfile.TemporaryDirectory() as d:
        monitor = make_monitor(Path(d))
        monitor._alpaca.get_last_price.return_value = 102.5
        trade = make_trailing_trade()
        settings = {"trailing_stop_enabled": True}

        result = monitor._apply_trailing_stop(trade, settings)

        assert result is False
        assert trade["stop_price"] == 97.0
        monitor._alpaca.replace_order_stop.assert_not_called()


def test_trailing_stop_no_change_when_already_at_breakeven():
    """If stop is already at entry, no further update at 1R."""
    with tempfile.TemporaryDirectory() as d:
        monitor = make_monitor(Path(d))
        monitor._alpaca.get_last_price.return_value = 103.0  # 1R
        trade = make_trailing_trade(stop=100.0)  # already at breakeven
        settings = {"trailing_stop_enabled": True}

        result = monitor._apply_trailing_stop(trade, settings)

        assert result is False
        monitor._alpaca.replace_order_stop.assert_not_called()


def test_trailing_stop_disabled_by_setting():
    """When trailing_stop_enabled=False, nothing should happen regardless of price."""
    with tempfile.TemporaryDirectory() as d:
        monitor = make_monitor(Path(d))
        monitor._alpaca.get_last_price.return_value = 110.0  # well above 2R
        trade = make_trailing_trade()
        settings = {"trailing_stop_enabled": False}

        result = monitor._apply_trailing_stop(trade, settings)

        assert result is False
        monitor._alpaca.replace_order_stop.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd examples/market-dashboard
uv run pytest tests/test_pivot_monitor.py::test_trailing_stop_moves_to_breakeven_at_1r tests/test_pivot_monitor.py::test_trailing_stop_moves_to_1r_profit_at_2r tests/test_pivot_monitor.py::test_trailing_stop_no_change_below_1r tests/test_pivot_monitor.py::test_trailing_stop_no_change_when_already_at_breakeven tests/test_pivot_monitor.py::test_trailing_stop_disabled_by_setting -v
```

Expected: all 5 FAIL (stub always returns `False`).

- [ ] **Step 3: Replace the `_apply_trailing_stop` stub in pivot_monitor.py**

Replace the stub body with the real implementation:

```python
def _apply_trailing_stop(self, trade: dict, settings: dict) -> bool:
    """Tighten stop to breakeven at 1R, to 1R profit at 2R. Returns True if changed."""
    if not settings.get("trailing_stop_enabled", True):
        return False

    entry = trade.get("entry_price")
    stop = trade.get("stop_price")
    stop_order_id = trade.get("stop_order_id")
    if not all([entry, stop, stop_order_id]):
        return False

    try:
        current_price = self._alpaca.get_last_price(trade["symbol"])
    except Exception:
        return False

    risk = entry - stop
    if risk <= 0:
        return False

    current_r = (current_price - entry) / risk
    new_stop = None

    if current_r >= 2.0 and stop < entry + risk:
        new_stop = round(entry + risk, 2)  # move stop to 1R profit
    elif current_r >= 1.0 and stop < entry:
        new_stop = entry  # move stop to breakeven

    if new_stop is not None and new_stop > stop:
        try:
            self._alpaca.replace_order_stop(stop_order_id, new_stop)
            trade["stop_price"] = new_stop
            trade["trailing_stop_level"] = new_stop
            print(f"[trailing_stop] {trade['symbol']}: stop → {new_stop}", file=sys.stderr)
            return True
        except Exception as e:
            print(f"[trailing_stop] {trade['symbol']} replace failed: {e}", file=sys.stderr)
    return False
```

- [ ] **Step 4: Run trailing stop tests to verify they pass**

```bash
cd examples/market-dashboard
uv run pytest tests/test_pivot_monitor.py::test_trailing_stop_moves_to_breakeven_at_1r tests/test_pivot_monitor.py::test_trailing_stop_moves_to_1r_profit_at_2r tests/test_pivot_monitor.py::test_trailing_stop_no_change_below_1r tests/test_pivot_monitor.py::test_trailing_stop_no_change_when_already_at_breakeven tests/test_pivot_monitor.py::test_trailing_stop_disabled_by_setting -v
```

Expected: all 5 PASS.

- [ ] **Step 5: Run the full test suite**

```bash
cd examples/market-dashboard
uv run pytest tests/ -v
```

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add pivot_monitor.py tests/test_pivot_monitor.py
git commit -m "feat: implement _apply_trailing_stop — breakeven at 1R, 1R profit at 2R"
```

---

## Task 4: Partial exit — `_apply_partial_exit()`

**Files:**
- Modify: `pivot_monitor.py` (replace stub)
- Modify: `tests/test_pivot_monitor.py`

**Logic:**
- Check `partial_exit_done` flag first — skip if already fired (idempotent)
- Calculate current R; fire only when `current_r >= partial_exit_at_r` (default 1.0)
- Calculate shares: `max(1, int(qty * partial_exit_pct / 100))`
- Call `self._alpaca.place_market_sell(symbol, shares_to_sell)`
- Set `trade["partial_exit_done"] = True` unconditionally on any attempt, even on sell failure (prevents retry loops). Set `trade["partial_exit_price"]` and `trade["partial_exit_qty"]` on success only.
- Returns `True` if state changed (flag was set)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_pivot_monitor.py`:

```python
# ── Partial exit ─────────────────────────────────────────────────────────────

def make_partial_trade(entry=100.0, stop=97.0, qty=20):
    return {
        "symbol": "AAPL",
        "entry_price": entry,
        "stop_price": stop,
        "qty": qty,
        "stop_order_id": "stop-ord-1",
        "outcome": None,
        "partial_exit_done": False,
        "entry_time": "2026-03-20T14:00:00+00:00",
    }


def test_partial_exit_fires_at_target_r():
    """At 1R (price=103), 50% of 20 shares = 10 shares sold."""
    with tempfile.TemporaryDirectory() as d:
        monitor = make_monitor(Path(d))
        monitor._alpaca.get_last_price.return_value = 103.0
        monitor._alpaca.place_market_sell.return_value = {"id": "sell-1", "status": "new"}
        trade = make_partial_trade()
        settings = {
            "partial_exit_enabled": True,
            "partial_exit_at_r": 1.0,
            "partial_exit_pct": 50,
        }

        result = monitor._apply_partial_exit(trade, settings)

        assert result is True
        assert trade["partial_exit_done"] is True
        assert trade["partial_exit_qty"] == 10
        assert trade["partial_exit_price"] == 103.0
        monitor._alpaca.place_market_sell.assert_called_once_with("AAPL", 10)


def test_partial_exit_does_not_fire_below_target_r():
    """Below 1R (price=102.5), partial exit must not trigger."""
    with tempfile.TemporaryDirectory() as d:
        monitor = make_monitor(Path(d))
        monitor._alpaca.get_last_price.return_value = 102.5
        trade = make_partial_trade()
        settings = {
            "partial_exit_enabled": True,
            "partial_exit_at_r": 1.0,
            "partial_exit_pct": 50,
        }

        result = monitor._apply_partial_exit(trade, settings)

        assert result is False
        assert trade["partial_exit_done"] is False
        monitor._alpaca.place_market_sell.assert_not_called()


def test_partial_exit_skipped_when_flag_already_set():
    """When partial_exit_done=True, do not call place_market_sell again."""
    with tempfile.TemporaryDirectory() as d:
        monitor = make_monitor(Path(d))
        monitor._alpaca.get_last_price.return_value = 106.0  # well above target
        trade = make_partial_trade()
        trade["partial_exit_done"] = True
        settings = {
            "partial_exit_enabled": True,
            "partial_exit_at_r": 1.0,
            "partial_exit_pct": 50,
        }

        result = monitor._apply_partial_exit(trade, settings)

        assert result is False
        monitor._alpaca.place_market_sell.assert_not_called()


def test_partial_exit_disabled_by_setting():
    """When partial_exit_enabled=False, no sell regardless of price."""
    with tempfile.TemporaryDirectory() as d:
        monitor = make_monitor(Path(d))
        monitor._alpaca.get_last_price.return_value = 110.0
        trade = make_partial_trade()
        settings = {"partial_exit_enabled": False}

        result = monitor._apply_partial_exit(trade, settings)

        assert result is False
        monitor._alpaca.place_market_sell.assert_not_called()


def test_partial_exit_sets_flag_on_sell_failure():
    """If place_market_sell raises, partial_exit_done must still be set to prevent retry loop."""
    with tempfile.TemporaryDirectory() as d:
        monitor = make_monitor(Path(d))
        monitor._alpaca.get_last_price.return_value = 103.0
        monitor._alpaca.place_market_sell.side_effect = RuntimeError("order rejected")
        trade = make_partial_trade()
        settings = {
            "partial_exit_enabled": True,
            "partial_exit_at_r": 1.0,
            "partial_exit_pct": 50,
        }

        result = monitor._apply_partial_exit(trade, settings)

        # flag must be set to True even on failure to stop retry loop
        assert trade["partial_exit_done"] is True
        # return value can be False (sell didn't succeed) but flag was written
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd examples/market-dashboard
uv run pytest tests/test_pivot_monitor.py::test_partial_exit_fires_at_target_r tests/test_pivot_monitor.py::test_partial_exit_does_not_fire_below_target_r tests/test_pivot_monitor.py::test_partial_exit_skipped_when_flag_already_set tests/test_pivot_monitor.py::test_partial_exit_disabled_by_setting tests/test_pivot_monitor.py::test_partial_exit_sets_flag_on_sell_failure -v
```

Expected: all 5 FAIL (stub always returns `False`).

- [ ] **Step 3: Replace the `_apply_partial_exit` stub in pivot_monitor.py**

```python
def _apply_partial_exit(self, trade: dict, settings: dict) -> bool:
    """Sell partial_exit_pct% of position at partial_exit_at_r. Returns True if fired."""
    if not settings.get("partial_exit_enabled", True):
        return False
    if trade.get("partial_exit_done"):
        return False

    entry = trade.get("entry_price")
    stop = trade.get("stop_price")
    qty = trade.get("qty")
    if not all([entry, stop, qty]):
        return False

    try:
        current_price = self._alpaca.get_last_price(trade["symbol"])
    except Exception:
        return False

    risk = entry - stop
    if risk <= 0:
        return False

    target_r = settings.get("partial_exit_at_r", 1.0)
    current_r = (current_price - entry) / risk

    if current_r < target_r:
        return False

    exit_pct = settings.get("partial_exit_pct", 50)
    shares_to_sell = max(1, int(qty * exit_pct / 100))

    try:
        self._alpaca.place_market_sell(trade["symbol"], shares_to_sell)
        trade["partial_exit_done"] = True
        trade["partial_exit_price"] = current_price
        trade["partial_exit_qty"] = shares_to_sell
        print(f"[partial_exit] {trade['symbol']}: sold {shares_to_sell}sh @ {current_price}", file=sys.stderr)
        return True
    except Exception as e:
        print(f"[partial_exit] {trade['symbol']} sell failed: {e}", file=sys.stderr)
        trade["partial_exit_done"] = True  # set flag to avoid retry loop
    return False
```

- [ ] **Step 4: Run partial exit tests to verify they pass**

```bash
cd examples/market-dashboard
uv run pytest tests/test_pivot_monitor.py::test_partial_exit_fires_at_target_r tests/test_pivot_monitor.py::test_partial_exit_does_not_fire_below_target_r tests/test_pivot_monitor.py::test_partial_exit_skipped_when_flag_already_set tests/test_pivot_monitor.py::test_partial_exit_disabled_by_setting tests/test_pivot_monitor.py::test_partial_exit_sets_flag_on_sell_failure -v
```

Expected: all 5 PASS.

- [ ] **Step 5: Run the full test suite**

```bash
cd examples/market-dashboard
uv run pytest tests/ -v
```

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add pivot_monitor.py tests/test_pivot_monitor.py
git commit -m "feat: implement _apply_partial_exit — sell configured % at target R multiple"
```

---

## Task 5: Time stop — `_apply_time_stop()`

**Files:**
- Modify: `pivot_monitor.py` (replace stub)
- Modify: `tests/test_pivot_monitor.py`

**Logic:**
- Read `time_stop_days` setting (default 5); if 0, return immediately (disabled)
- Parse `entry_time` from trade dict; compute `days_open = (now_utc - entry_dt).days`
- If `days_open < time_stop_days`, return False — trade is within time limit
- Fetch current price, compute `current_r = abs((current_price - entry) / risk)`
- If `current_r > 0.5`, skip — trade is moving; let the winner run
- Otherwise place a full market sell and set `trade["outcome"] = "time_stop"` and `trade["exit_price"]`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_pivot_monitor.py`:

```python
# ── Time stop ────────────────────────────────────────────────────────────────

def make_time_stop_trade(days_ago: int, entry=100.0, stop=97.0, qty=10):
    from datetime import datetime, timezone, timedelta
    entry_time = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    return {
        "symbol": "AAPL",
        "entry_price": entry,
        "stop_price": stop,
        "qty": qty,
        "stop_order_id": "stop-ord-1",
        "outcome": None,
        "entry_time": entry_time,
    }


def test_time_stop_exits_flat_position_after_time_limit():
    """Flat trade (price=100.5, <0.5R) open 6 days should be exited."""
    with tempfile.TemporaryDirectory() as d:
        monitor = make_monitor(Path(d))
        monitor._alpaca.get_last_price.return_value = 100.5  # 0.5/3 ≈ 0.167R — flat
        monitor._alpaca.place_market_sell.return_value = {"id": "sell-ts", "status": "new"}
        trade = make_time_stop_trade(days_ago=6)
        settings = {"time_stop_days": 5}

        result = monitor._apply_time_stop(trade, settings)

        assert result is True
        assert trade["outcome"] == "time_stop"
        assert trade["exit_price"] == 100.5
        monitor._alpaca.place_market_sell.assert_called_once_with("AAPL", 10)


def test_time_stop_no_exit_within_time_limit():
    """Flat trade still within 5-day limit must not be exited."""
    with tempfile.TemporaryDirectory() as d:
        monitor = make_monitor(Path(d))
        monitor._alpaca.get_last_price.return_value = 100.2
        trade = make_time_stop_trade(days_ago=3)
        settings = {"time_stop_days": 5}

        result = monitor._apply_time_stop(trade, settings)

        assert result is False
        monitor._alpaca.place_market_sell.assert_not_called()


def test_time_stop_no_exit_when_position_above_half_r():
    """Trade above 0.5R after time limit must not be exited — let winner run."""
    with tempfile.TemporaryDirectory() as d:
        monitor = make_monitor(Path(d))
        monitor._alpaca.get_last_price.return_value = 102.0  # (102-100)/3 = 0.67R > 0.5
        trade = make_time_stop_trade(days_ago=7)
        settings = {"time_stop_days": 5}

        result = monitor._apply_time_stop(trade, settings)

        assert result is False
        monitor._alpaca.place_market_sell.assert_not_called()


def test_time_stop_disabled_when_days_zero():
    """time_stop_days=0 means disabled — no exit regardless of age."""
    with tempfile.TemporaryDirectory() as d:
        monitor = make_monitor(Path(d))
        monitor._alpaca.get_last_price.return_value = 100.1
        trade = make_time_stop_trade(days_ago=30)
        settings = {"time_stop_days": 0}

        result = monitor._apply_time_stop(trade, settings)

        assert result is False
        monitor._alpaca.place_market_sell.assert_not_called()


def test_time_stop_skips_when_entry_time_missing():
    """Trade with no entry_time must not raise and must return False."""
    with tempfile.TemporaryDirectory() as d:
        monitor = make_monitor(Path(d))
        trade = {
            "symbol": "AAPL", "entry_price": 100.0, "stop_price": 97.0,
            "qty": 10, "outcome": None,
            # entry_time deliberately omitted
        }
        settings = {"time_stop_days": 5}

        result = monitor._apply_time_stop(trade, settings)  # must not raise

        assert result is False
        monitor._alpaca.place_market_sell.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd examples/market-dashboard
uv run pytest tests/test_pivot_monitor.py::test_time_stop_exits_flat_position_after_time_limit tests/test_pivot_monitor.py::test_time_stop_no_exit_within_time_limit tests/test_pivot_monitor.py::test_time_stop_no_exit_when_position_above_half_r tests/test_pivot_monitor.py::test_time_stop_disabled_when_days_zero tests/test_pivot_monitor.py::test_time_stop_skips_when_entry_time_missing -v
```

Expected: all 5 FAIL (stub always returns `False`, so the first test fails because `outcome` is never set).

- [ ] **Step 3: Replace the `_apply_time_stop` stub in pivot_monitor.py**

```python
def _apply_time_stop(self, trade: dict, settings: dict) -> bool:
    """Exit flat positions after time_stop_days trading days."""
    time_stop_days = settings.get("time_stop_days", 5)
    if time_stop_days == 0:
        return False

    entry_time_str = trade.get("entry_time")
    if not entry_time_str:
        return False

    entry_dt = datetime.fromisoformat(entry_time_str)
    now = datetime.now(timezone.utc)
    days_open = (now - entry_dt).days

    if days_open < time_stop_days:
        return False

    entry = trade.get("entry_price")
    stop = trade.get("stop_price")
    qty = trade.get("qty")
    if not all([entry, stop, qty]):
        return False

    try:
        current_price = self._alpaca.get_last_price(trade["symbol"])
    except Exception:
        return False

    risk = entry - stop
    if risk <= 0:
        return False

    current_r = abs((current_price - entry) / risk)
    if current_r > 0.5:
        return False  # not flat — let winner run

    try:
        self._alpaca.place_market_sell(trade["symbol"], qty)
        trade["outcome"] = "time_stop"
        trade["exit_price"] = current_price
        print(f"[time_stop] {trade['symbol']}: flat after {days_open} days, exiting", file=sys.stderr)
        return True
    except Exception as e:
        print(f"[time_stop] {trade['symbol']} exit failed: {e}", file=sys.stderr)
    return False
```

- [ ] **Step 4: Run time stop tests to verify they pass**

```bash
cd examples/market-dashboard
uv run pytest tests/test_pivot_monitor.py::test_time_stop_exits_flat_position_after_time_limit tests/test_pivot_monitor.py::test_time_stop_no_exit_within_time_limit tests/test_pivot_monitor.py::test_time_stop_no_exit_when_position_above_half_r tests/test_pivot_monitor.py::test_time_stop_disabled_when_days_zero tests/test_pivot_monitor.py::test_time_stop_skips_when_entry_time_missing -v
```

Expected: all 5 PASS.

- [ ] **Step 5: Run the full test suite**

```bash
cd examples/market-dashboard
uv run pytest tests/ -v
```

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add pivot_monitor.py tests/test_pivot_monitor.py
git commit -m "feat: implement _apply_time_stop — exit flat positions after configured trading days"
```

---

## Task 6: Wire into scheduler, settings defaults, and settings UI

**Files:**
- Modify: `scheduler.py`
- Modify: `settings_manager.py`
- Modify: `templates/fragments/settings_modal.html`

**Context:** `scheduler.py`'s `create_scheduler()` already accepts `pivot_monitor` as an optional parameter. It adds `pivot_stage1` and `pivot_monitor_start` jobs inside the `if pivot_monitor is not None:` block. The new exit job belongs in the same block. `settings_manager.py`'s `_DEFAULTS` needs 5 new keys. The settings modal needs a new "Exit Management" section with fields for each setting.

There are no unit tests for `scheduler.py` job wiring — the scheduler is tested indirectly by the monitor tests. A simple smoke test is added here.

- [ ] **Step 1: Write the failing smoke test**

Append to `tests/test_pivot_monitor.py`:

```python
# ── Scheduler wiring smoke test ──────────────────────────────────────────────

def test_create_scheduler_registers_exit_management_job():
    """create_scheduler must register an 'exit_management' job when pivot_monitor is provided."""
    with tempfile.TemporaryDirectory() as d:
        from scheduler import create_scheduler
        from unittest.mock import MagicMock
        runner = MagicMock()
        monitor = make_monitor(Path(d))
        sched = create_scheduler(runner=runner, cache_dir=Path(d), pivot_monitor=monitor)
        job_ids = {job.id for job in sched.get_jobs()}
        assert "exit_management" in job_ids
```

- [ ] **Step 2: Run smoke test to verify it fails**

```bash
cd examples/market-dashboard
uv run pytest tests/test_pivot_monitor.py::test_create_scheduler_registers_exit_management_job -v
```

Expected: FAIL — `exit_management` job not yet registered.

- [ ] **Step 3: Add exit management job to scheduler.py**

Inside the `if pivot_monitor is not None:` block in `create_scheduler()`, add after the `pivot_monitor_start` job and before the closing of the block:

```python
    sched.add_job(
        lambda: pivot_monitor._check_exit_management(),
        IntervalTrigger(minutes=5),
        id="exit_management",
        replace_existing=True,
    )
```

The full updated block (for clarity — only the new `sched.add_job` call needs adding):

```python
    if pivot_monitor is not None:
        # ... existing stage1_job and monitor_start_job unchanged ...

        sched.add_job(
            lambda: pivot_monitor._check_exit_management(),
            IntervalTrigger(minutes=5),
            id="exit_management",
            replace_existing=True,
        )
```

- [ ] **Step 4: Run smoke test to verify it passes**

```bash
cd examples/market-dashboard
uv run pytest tests/test_pivot_monitor.py::test_create_scheduler_registers_exit_management_job -v
```

Expected: PASS.

- [ ] **Step 5: Add new defaults to settings_manager.py**

In `settings_manager.py`, update `_DEFAULTS` to include the five new exit management keys:

```python
_DEFAULTS = {
    "mode": DEFAULT_TRADING_MODE,
    "default_risk_pct": DEFAULT_RISK_PCT,
    "max_positions": DEFAULT_MAX_POSITIONS,
    "max_position_size_pct": DEFAULT_MAX_POSITION_SIZE_PCT,
    "environment": "paper",
    # Exit management (Tier 3)
    "trailing_stop_enabled": True,
    "partial_exit_enabled": True,
    "partial_exit_at_r": 1.0,
    "partial_exit_pct": 50,
    "time_stop_days": 5,
}
```

- [ ] **Step 6: Add exit management fields to settings_modal.html**

Insert a new "Exit Management" section inside the `<form>` in `templates/fragments/settings_modal.html`, after the `max_position_size_pct` row and before the Save/Cancel button row:

```html
      <!-- Exit Management (Tier 3) -->
      <div style="margin-top:14px; margin-bottom:6px; font-size:11px; color:#8b949e; text-transform:uppercase; letter-spacing:0.05em;">Exit Management</div>

      <div class="form-row">
        <div class="form-label">Trailing Stop</div>
        <select name="trailing_stop_enabled" class="form-input">
          <option value="true" {% if settings.trailing_stop_enabled %}selected{% endif %}>Enabled — tighten stop at 1R / 2R</option>
          <option value="false" {% if not settings.trailing_stop_enabled %}selected{% endif %}>Disabled</option>
        </select>
      </div>

      <div class="form-row">
        <div class="form-label">Partial Exit</div>
        <select name="partial_exit_enabled" class="form-input">
          <option value="true" {% if settings.partial_exit_enabled %}selected{% endif %}>Enabled</option>
          <option value="false" {% if not settings.partial_exit_enabled %}selected{% endif %}>Disabled</option>
        </select>
      </div>

      <div class="form-row">
        <div class="form-label">Partial Exit at R</div>
        <input type="number" name="partial_exit_at_r" class="form-input"
               value="{{ settings.partial_exit_at_r }}" min="0.5" max="3.0" step="0.25">
      </div>

      <div class="form-row">
        <div class="form-label">Partial Exit Size (%)</div>
        <input type="number" name="partial_exit_pct" class="form-input"
               value="{{ settings.partial_exit_pct }}" min="10" max="90" step="5">
      </div>

      <div class="form-row">
        <div class="form-label">Time Stop (days, 0 = off)</div>
        <input type="number" name="time_stop_days" class="form-input"
               value="{{ settings.time_stop_days }}" min="0" max="30">
      </div>
```

**Note:** The `post_settings` route in `main.py` must also accept these new form fields. Update the route signature to parse them:

```python
@app.post("/api/settings", response_class=HTMLResponse)
async def post_settings(
    request: Request,
    mode: str = Form(...),
    default_risk_pct: float = Form(...),
    max_positions: int = Form(...),
    max_position_size_pct: float = Form(...),
    environment: str = Form(...),
    live_confirm: str = Form(""),
    # Exit management
    trailing_stop_enabled: str = Form("true"),
    partial_exit_enabled: str = Form("true"),
    partial_exit_at_r: float = Form(1.0),
    partial_exit_pct: int = Form(50),
    time_stop_days: int = Form(5),
):
```

Update the `settings_manager.save(...)` call to include the new fields:

```python
    settings_manager.save({
        "mode": mode,
        "default_risk_pct": default_risk_pct,
        "max_positions": max_positions,
        "max_position_size_pct": max_position_size_pct,
        "environment": environment,
        "trailing_stop_enabled": trailing_stop_enabled == "true",
        "partial_exit_enabled": partial_exit_enabled == "true",
        "partial_exit_at_r": partial_exit_at_r,
        "partial_exit_pct": partial_exit_pct,
        "time_stop_days": time_stop_days,
    })
```

- [ ] **Step 7: Run the full test suite**

```bash
cd examples/market-dashboard
uv run pytest tests/ -v
```

Expected: all tests PASS.

- [ ] **Step 8: Commit**

```bash
git add scheduler.py settings_manager.py templates/fragments/settings_modal.html main.py tests/test_pivot_monitor.py
git commit -m "feat: wire exit management into scheduler, settings defaults, and settings UI"
```

---

## Done

At this point Tier 3 is fully operational:

- `AlpacaClient` has `replace_order_stop` and `place_market_sell`
- `PivotWatchlistMonitor._check_exit_management()` runs every 5 minutes during market hours
- Three exit strategies are live: trailing stop, partial exit, and time stop
- All behaviour is controlled by 5 new settings fields with sensible defaults
- 19 new unit tests cover every meaningful code path across the three exit methods
- The scheduler registers the job automatically when `pivot_monitor` is passed to `create_scheduler()`
- The settings modal exposes all controls so parameters can be tuned at runtime without restarting the server
