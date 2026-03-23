# Multi-Market Trading Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add broker abstraction layer, IBKRClient, universe builder, and multi-market orchestrator to support Oslo Børs, LSE, and any future exchange alongside existing US trading.

**Architecture:** BrokerClient Protocol defines the interface; AlpacaClient and IBKRClient both implement it. PivotWatchlistMonitor is migrated from self._alpaca to self._broker with dynamic market hours per config. One monitor instance runs per enabled market. Universe builder fetches and filters top stocks per non-US exchange weekly via IBKR with request pacing.

**Tech Stack:** Python 3.11+, FastAPI, ib_insync (pip install ib_insync), existing alpaca-py

**Spec:** `docs/superpowers/specs/2026-03-23-multi-market-trading-design.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `broker_client.py` | Create | BrokerClient Protocol definition |
| `tests/test_broker_client.py` | Create | AlpacaClient protocol compliance test |
| `alpaca_client.py` | Modify | Add `subscribe_bars`, return `stop_order_id` from bracket order |
| `tests/test_alpaca_client.py` | Create | AlpacaClient unit tests |
| `ibkr_client.py` | Create | IBKRClient implementing BrokerClient via ib_insync |
| `tests/test_ibkr_client.py` | Create | IBKRClient tests with mocked ib_insync |
| `pivot_monitor.py` | Modify | Replace self._alpaca → self._broker throughout; dynamic market hours; PDT flag; per-market earnings file; per-market trade log |
| `tests/test_pivot_monitor.py` | Modify | Multi-market test cases |
| `settings_manager.py` | Modify | Add markets defaults, get_enabled_markets(), save validation |
| `tests/test_settings_manager.py` | Create | Settings manager unit tests |
| `universe_builder.py` | Create | Weekly universe fetch and filter for non-US markets |
| `tests/test_universe_builder.py` | Create | Universe builder tests with mocked IBKR |
| `main.py` | Modify | IBKRClient instantiation, per-market monitors, /api/broker-status endpoint |
| `scheduler.py` | Modify | Weekly universe builder job |
| `tests/test_routes.py` | Modify | test_broker_status_endpoint |
| `templates/trades.html` | Modify | Add Market column, merge all *-auto_trades.json files |
| `templates/dashboard.html` | Modify | Add Market column to signals table |

---

## Task 1: BrokerClient Protocol

**Files:**
- Create: `broker_client.py`
- Create: `tests/test_broker_client.py`

### Step 1.1 — Write the failing test

Create `tests/test_broker_client.py`:

```python
# tests/test_broker_client.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from unittest.mock import MagicMock


def test_alpaca_client_satisfies_protocol():
    """AlpacaClient must satisfy BrokerClient Protocol at runtime."""
    from broker_client import BrokerClient
    from alpaca_client import AlpacaClient

    # isinstance check works for runtime_checkable Protocol
    client = AlpacaClient(api_key="k", secret_key="s", paper=True)
    assert isinstance(client, BrokerClient)


def test_broker_client_protocol_has_required_methods():
    """BrokerClient Protocol exposes all required methods."""
    from broker_client import BrokerClient
    import inspect

    required = {
        "get_account",
        "get_positions",
        "get_last_price",
        "get_current_volume",
        "place_bracket_order",
        "place_market_sell",
        "replace_order_stop",
        "subscribe_bars",
        "is_configured",
    }
    members = set(dir(BrokerClient))
    missing = required - members
    assert not missing, f"Missing from BrokerClient: {missing}"
```

- [ ] Create `tests/test_broker_client.py` with the tests above
- [ ] Run: `uv run pytest tests/test_broker_client.py -v`
- [ ] Expected: **FAIL** — `broker_client` module not found

### Step 1.2 — Create `broker_client.py`

Create `broker_client.py` in the project root:

```python
"""Shared broker interface. Both AlpacaClient and IBKRClient implement this Protocol."""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class BrokerClient(Protocol):
    """Interface all broker clients must satisfy.

    place_bracket_order must return a dict containing at minimum:
      - "id": str           — primary order ID
      - "stop_order_id": str — ID of the stop-loss leg (used by trailing stop logic)
    """

    @property
    def is_configured(self) -> bool: ...

    def get_account(self) -> dict: ...

    def get_positions(self) -> list[dict]: ...

    def get_last_price(self, symbol: str) -> float: ...

    def get_current_volume(self, symbol: str) -> int: ...

    def place_bracket_order(
        self,
        symbol: str,
        qty: int,
        limit_price: float,
        stop_price: float,
        take_profit_price: float | None = None,
    ) -> dict: ...

    def place_market_sell(self, symbol: str, qty: int) -> dict: ...

    def replace_order_stop(self, order_id: str, new_stop_price: float) -> dict: ...

    async def subscribe_bars(self, symbols: list[str], callback) -> None: ...
```

- [ ] Create `broker_client.py` with the code above
- [ ] Run: `uv run pytest tests/test_broker_client.py -v`
- [ ] Expected: **FAIL** — `test_alpaca_client_satisfies_protocol` fails because `AlpacaClient` is missing `subscribe_bars` (added in Task 2). `test_broker_client_protocol_has_required_methods` should **PASS**.

### Step 1.3 — Run full suite to check for regressions

- [ ] Run: `uv run pytest tests/ -v`
- [ ] Expected: no new failures beyond the one introduced test

### Step 1.4 — Commit

```bash
git add broker_client.py tests/test_broker_client.py
git commit -m "feat: add BrokerClient Protocol definition"
```

- [ ] Commit

---

## Task 2: AlpacaClient — add subscribe_bars and stop_order_id

**Files:**
- Modify: `alpaca_client.py`
- Create: `tests/test_alpaca_client.py`

### Step 2.1 — Write the failing tests

Create `tests/test_alpaca_client.py`:

```python
# tests/test_alpaca_client.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
import asyncio


def _make_client():
    from alpaca_client import AlpacaClient
    return AlpacaClient(api_key="test_key", secret_key="test_secret", paper=True)


def test_place_bracket_order_returns_stop_order_id():
    """place_bracket_order must return stop_order_id from the bracket order response."""
    client = _make_client()

    # Build a mock bracket order response with legs
    stop_leg = MagicMock()
    stop_leg.id = "stop-leg-id-123"

    tp_leg = MagicMock()
    tp_leg.id = "tp-leg-id-456"

    mock_order = MagicMock()
    mock_order.id = "parent-order-id-789"
    mock_order.symbol = "AAPL"
    mock_order.qty = 10
    mock_order.limit_price = 150.0
    mock_order.status = "accepted"
    # Alpaca bracket orders have legs: [take_profit_leg, stop_loss_leg]
    mock_order.legs = [tp_leg, stop_leg]

    mock_trading = MagicMock()
    mock_trading.submit_order.return_value = mock_order
    client._trading_client = mock_trading

    result = client.place_bracket_order(
        symbol="AAPL", qty=10, limit_price=150.0, stop_price=145.0
    )

    assert "id" in result
    assert "stop_order_id" in result
    assert result["id"] == "parent-order-id-789"
    assert result["stop_order_id"] == "stop-leg-id-123"


def test_alpaca_satisfies_broker_client_protocol():
    """AlpacaClient satisfies BrokerClient after subscribe_bars is added."""
    from broker_client import BrokerClient
    client = _make_client()
    assert isinstance(client, BrokerClient)


def test_subscribe_bars_calls_stream_subscribe_and_run():
    """subscribe_bars wraps StockDataStream correctly."""
    client = _make_client()

    mock_stream = MagicMock()
    mock_stream.subscribe_bars = MagicMock()
    mock_stream.run = MagicMock()

    callback = MagicMock()

    async def run():
        with patch("alpaca_client.StockDataStream", return_value=mock_stream):
            await client.subscribe_bars(["AAPL", "MSFT"], callback)

    asyncio.get_event_loop().run_until_complete(run())

    mock_stream.subscribe_bars.assert_called_once()
    mock_stream.run.assert_called_once()
```

- [ ] Create `tests/test_alpaca_client.py` with the tests above
- [ ] Run: `uv run pytest tests/test_alpaca_client.py -v`
- [ ] Expected: **FAIL** — `test_place_bracket_order_returns_stop_order_id` fails (no `stop_order_id` in response); `test_alpaca_satisfies_broker_client_protocol` fails (no `subscribe_bars`); `test_subscribe_bars_calls_stream_subscribe_and_run` fails (method doesn't exist)

### Step 2.2 — Modify `alpaca_client.py`: return stop_order_id from place_bracket_order

In `place_bracket_order`, find the Alpaca bracket response legs to extract the stop-loss order ID. Alpaca returns legs in `order.legs` — the stop-loss leg is the one with `order_class == "stop"` or can be identified by checking for a `stop_price` attribute. In practice the legs list from Alpaca contains the take-profit leg first and stop-loss leg second.

Replace the return statement in `place_bracket_order` (currently lines 125–131 of `alpaca_client.py`):

```python
        order = self.trading_client.submit_order(order_data)
        # Alpaca bracket orders return legs: [take_profit_leg, stop_loss_leg]
        stop_order_id = None
        legs = getattr(order, "legs", None) or []
        for leg in legs:
            # Stop leg has a stop_price; take-profit leg does not
            if getattr(leg, "stop_price", None) is not None:
                stop_order_id = str(leg.id)
                break
        # Fallback: second leg by position if attribute detection fails
        if stop_order_id is None and len(legs) >= 2:
            stop_order_id = str(legs[1].id)
        return {
            "id": str(order.id),
            "symbol": order.symbol,
            "qty": float(order.qty),
            "limit_price": float(order.limit_price),
            "status": str(order.status),
            "stop_order_id": stop_order_id,
        }
```

- [ ] Apply the change to `alpaca_client.py`

### Step 2.3 — Modify `alpaca_client.py`: add subscribe_bars

Add the `subscribe_bars` async method at the end of `AlpacaClient`, before `start_trading_stream`. Also add the module-level import guard at the top of the method body so `StockDataStream` is importable in tests via `patch("alpaca_client.StockDataStream", ...)`.

Add this method to `AlpacaClient`:

```python
    async def subscribe_bars(self, symbols: list[str], callback) -> None:
        """Subscribe to 1-minute bars for the given symbols and call callback on each bar.

        Wraps Alpaca StockDataStream. Runs stream.run() in a thread executor so the
        blocking WebSocket call does not block the asyncio event loop.
        Disconnections are logged but do not raise — caller handles reconnect logic.
        """
        import asyncio as _asyncio
        from alpaca.data.live import StockDataStream as _StockDataStream
        # Allow tests to patch at module level
        import alpaca_client as _self_module
        StockDataStream = getattr(_self_module, "StockDataStream", _StockDataStream)

        stream = StockDataStream(
            api_key=self.api_key,
            secret_key=self.secret_key,
        )

        async def _handle_bar(bar):
            await callback(bar)

        stream.subscribe_bars(_handle_bar, *symbols)
        loop = _asyncio.get_running_loop()
        try:
            await loop.run_in_executor(None, stream.run)
        except Exception as e:
            import sys
            print(f"[alpaca_client] subscribe_bars disconnected: {e}", file=sys.stderr)
```

> Note on patching: the test uses `patch("alpaca_client.StockDataStream", ...)`. Add the line `StockDataStream = None` at module level in `alpaca_client.py` (just below the imports) so the patch target exists. Then in `subscribe_bars`, resolve `StockDataStream` as shown above.

Add to the top of `alpaca_client.py` (after `import sys`):

```python
# Patch target for tests — overridden by subscribe_bars at runtime
StockDataStream = None
```

- [ ] Add `StockDataStream = None` near the top of `alpaca_client.py`
- [ ] Add `subscribe_bars` method to `AlpacaClient`

### Step 2.4 — Run tests

- [ ] Run: `uv run pytest tests/test_alpaca_client.py -v`
- [ ] Expected: all three tests **PASS**
- [ ] Run: `uv run pytest tests/test_broker_client.py::test_alpaca_client_satisfies_protocol -v`
- [ ] Expected: **PASS**

### Step 2.5 — Run full suite

- [ ] Run: `uv run pytest tests/ -v`
- [ ] Expected: no new failures

### Step 2.6 — Commit

```bash
git add alpaca_client.py tests/test_alpaca_client.py
git commit -m "feat: alpaca_client — add subscribe_bars and stop_order_id in bracket order response"
```

- [ ] Commit

---

## Task 3: IBKRClient

**Files:**
- Create: `ibkr_client.py`
- Create: `tests/test_ibkr_client.py`

### Step 3.1 — Write the failing tests

Create `tests/test_ibkr_client.py`:

```python
# tests/test_ibkr_client.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
import asyncio


def _make_client(connected: bool = True):
    """Build IBKRClient with a mocked ib_insync IB instance."""
    from ibkr_client import IBKRClient

    mock_ib = MagicMock()
    mock_ib.isConnected.return_value = connected
    # Simulate successful connect (no exception)
    mock_ib.connect = MagicMock()

    client = IBKRClient(paper=True, _ib=mock_ib)
    return client, mock_ib


def test_is_configured_true_when_connected():
    client, mock_ib = _make_client(connected=True)
    assert client.is_configured is True


def test_is_configured_false_when_not_connected():
    client, mock_ib = _make_client(connected=False)
    assert client.is_configured is False


def test_get_account_returns_portfolio_value():
    client, mock_ib = _make_client()

    mock_account_value = MagicMock()
    mock_account_value.tag = "NetLiquidation"
    mock_account_value.value = "125000.50"
    mock_account_value.currency = "USD"

    mock_ib.accountValues.return_value = [mock_account_value]

    result = client.get_account()
    assert "portfolio_value" in result
    assert result["portfolio_value"] == pytest.approx(125000.50)


def test_get_positions_returns_list():
    client, mock_ib = _make_client()

    mock_contract = MagicMock()
    mock_contract.symbol = "EQNR"

    mock_pos = MagicMock()
    mock_pos.contract = mock_contract
    mock_pos.position = 100.0
    mock_pos.avgCost = 300.0

    mock_ib.positions.return_value = [mock_pos]

    result = client.get_positions()
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["symbol"] == "EQNR"
    assert result[0]["qty"] == 100.0


def test_get_last_price_returns_float():
    client, mock_ib = _make_client()

    mock_ticker = MagicMock()
    mock_ticker.last = 312.50

    mock_ib.reqMktData.return_value = mock_ticker
    mock_ib.sleep = MagicMock()

    result = client.get_last_price("EQNR")
    assert result == pytest.approx(312.50)


def test_place_bracket_order_returns_id_and_stop_order_id():
    client, mock_ib = _make_client()

    mock_parent = MagicMock()
    mock_parent.orderId = 101

    mock_tp = MagicMock()
    mock_tp.orderId = 102

    mock_stop = MagicMock()
    mock_stop.orderId = 103

    mock_trade = MagicMock()
    mock_trade.order.orderId = 101

    mock_ib.placeOrder.side_effect = [mock_trade, MagicMock(), MagicMock()]
    mock_ib.client.getReqId.side_effect = [101, 102, 103]

    # Mock bracket order construction
    with patch("ibkr_client.LimitOrder") as mock_limit, \
         patch("ibkr_client.StopOrder") as mock_stop_order, \
         patch("ibkr_client.LimitOrder") as mock_tp_order:
        mock_limit.return_value = mock_parent
        result = client.place_bracket_order(
            symbol="EQNR",
            qty=10,
            limit_price=310.0,
            stop_price=300.0,
            take_profit_price=330.0,
        )

    assert "id" in result
    assert "stop_order_id" in result


def test_ibkr_satisfies_broker_client_protocol():
    """IBKRClient satisfies BrokerClient Protocol."""
    from broker_client import BrokerClient
    client, _ = _make_client()
    assert isinstance(client, BrokerClient)


def test_subscribe_bars_creates_realtime_bars():
    """subscribe_bars calls reqRealTimeBars for each symbol."""
    client, mock_ib = _make_client()

    callback = AsyncMock()

    async def run():
        # subscribe_bars should register bars and then wait; we just check it doesn't raise
        # and that reqRealTimeBars is called for each symbol
        task = asyncio.create_task(
            client.subscribe_bars(["EQNR", "SHEL"], callback)
        )
        await asyncio.sleep(0.05)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.get_event_loop().run_until_complete(run())
    assert mock_ib.reqRealTimeBars.call_count == 2
```

- [ ] Create `tests/test_ibkr_client.py` with the tests above
- [ ] Run: `uv run pytest tests/test_ibkr_client.py -v`
- [ ] Expected: **FAIL** — `ibkr_client` module not found

### Step 3.2 — Create `ibkr_client.py`

Create `ibkr_client.py` in the project root:

```python
"""IBKR broker client implementing BrokerClient Protocol via ib_insync."""
from __future__ import annotations

import asyncio
import sys
from typing import Callable


# These are imported at method level where needed; exposed here for patching in tests
try:
    from ib_insync import IB, Stock, LimitOrder, StopOrder, MarketOrder, Order
    from ib_insync import util as ib_util
    _IB_AVAILABLE = True
except ImportError:
    _IB_AVAILABLE = False
    IB = None


class IBKRClient:
    """Implements BrokerClient Protocol using ib_insync.

    Connects to IB Gateway running on localhost.
    - paper=True  → port 4002
    - paper=False → port 4001

    Pass _ib in tests to inject a mock IB instance.
    """

    PAPER_PORT = 4002
    LIVE_PORT = 4001
    HOST = "127.0.0.1"
    CLIENT_ID = 10  # Use 10 to avoid conflicts with manual TWS sessions

    def __init__(self, paper: bool = True, exchange: str = "SMART", _ib=None):
        self._paper = paper
        self._exchange = exchange
        self._port = self.PAPER_PORT if paper else self.LIVE_PORT
        if _ib is not None:
            self._ib = _ib
        else:
            if not _IB_AVAILABLE:
                raise ImportError(
                    "ib_insync not installed. Run: pip install ib_insync"
                )
            self._ib = IB()
            try:
                self._ib.connect(self.HOST, self._port, clientId=self.CLIENT_ID)
            except Exception as e:
                print(f"[ibkr_client] connect failed: {e}", file=sys.stderr)

    @property
    def is_configured(self) -> bool:
        """True only when IB Gateway connection is live."""
        try:
            return bool(self._ib.isConnected())
        except Exception:
            return False

    def _make_contract(self, symbol: str):
        """Build an IBKR Stock contract for the configured exchange."""
        if not _IB_AVAILABLE:
            raise RuntimeError("ib_insync not available")
        # Symbols on international exchanges use the plain symbol; exchange is set on the contract.
        # e.g. EQNR on OSE, SHEL on LSE
        return Stock(symbol, self._exchange, "")

    def get_account(self) -> dict:
        """Return portfolio_value, buying_power, cash from IBKR account values."""
        values = self._ib.accountValues()
        result = {"portfolio_value": 0.0, "buying_power": 0.0, "cash": 0.0}
        for v in values:
            if v.tag == "NetLiquidation" and v.currency == "BASE":
                result["portfolio_value"] = float(v.value)
            elif v.tag == "BuyingPower" and v.currency == "BASE":
                result["buying_power"] = float(v.value)
            elif v.tag == "CashBalance" and v.currency == "BASE":
                result["cash"] = float(v.value)
        # Fallback: first NetLiquidation regardless of currency
        if result["portfolio_value"] == 0.0:
            for v in values:
                if v.tag == "NetLiquidation":
                    result["portfolio_value"] = float(v.value)
                    break
        return result

    def get_positions(self) -> list[dict]:
        """Return list of open positions from IBKR account."""
        return [
            {
                "symbol": pos.contract.symbol,
                "qty": float(pos.position),
                "avg_entry_price": float(pos.avgCost),
                "market_value": 0.0,       # not available without market data snapshot
                "unrealized_pl": 0.0,
                "unrealized_plpc": 0.0,
                "current_price": 0.0,
            }
            for pos in self._ib.positions()
        ]

    def get_last_price(self, symbol: str) -> float:
        """Fetch last trade price via snapshot market data request."""
        contract = self._make_contract(symbol)
        ticker = self._ib.reqMktData(contract, "", snapshot=True, regulatorySnapshot=False)
        # ib_insync snapshot: sleep briefly to allow data to arrive
        self._ib.sleep(1)
        price = ticker.last
        if price is None or price <= 0:
            # Fallback to close price
            price = ticker.close
        if price is None or price <= 0:
            raise ValueError(f"[ibkr_client] no price data for {symbol}")
        return float(price)

    def get_current_volume(self, symbol: str) -> int:
        """Return today's volume from snapshot market data."""
        contract = self._make_contract(symbol)
        ticker = self._ib.reqMktData(contract, "", snapshot=True, regulatorySnapshot=False)
        self._ib.sleep(1)
        volume = getattr(ticker, "volume", None)
        if volume is None:
            return 0
        return int(volume)

    def place_bracket_order(
        self,
        symbol: str,
        qty: int,
        limit_price: float,
        stop_price: float,
        take_profit_price: float | None = None,
    ) -> dict:
        """Place a bracket order (parent limit + take-profit + stop-loss) on IBKR.

        Returns {"id": parent_order_id, "stop_order_id": stop_leg_order_id, ...}
        """
        if not _IB_AVAILABLE:
            raise RuntimeError("ib_insync not available")

        contract = self._make_contract(symbol)

        if take_profit_price is None:
            risk = limit_price - stop_price
            take_profit_price = round(limit_price + risk * 2, 2)

        # Allocate three order IDs
        parent_id = self._ib.client.getReqId()
        tp_id = self._ib.client.getReqId()
        stop_id = self._ib.client.getReqId()

        parent = LimitOrder("BUY", qty, round(limit_price, 2))
        parent.orderId = parent_id
        parent.transmit = False

        take_profit = LimitOrder("SELL", qty, round(take_profit_price, 2))
        take_profit.orderId = tp_id
        take_profit.parentId = parent_id
        take_profit.transmit = False

        stop_loss = StopOrder("SELL", qty, round(stop_price, 2))
        stop_loss.orderId = stop_id
        stop_loss.parentId = parent_id
        stop_loss.transmit = True  # transmit=True on last leg sends all three

        parent_trade = self._ib.placeOrder(contract, parent)
        self._ib.placeOrder(contract, take_profit)
        self._ib.placeOrder(contract, stop_loss)

        return {
            "id": str(parent_id),
            "symbol": symbol,
            "qty": qty,
            "limit_price": round(limit_price, 2),
            "status": "submitted",
            "stop_order_id": str(stop_id),
        }

    def place_market_sell(self, symbol: str, qty: int) -> dict:
        """Place a market sell order on IBKR."""
        contract = self._make_contract(symbol)
        order = MarketOrder("SELL", qty)
        trade = self._ib.placeOrder(contract, order)
        return {"id": str(trade.order.orderId), "status": "submitted"}

    def replace_order_stop(self, order_id: str, new_stop_price: float) -> dict:
        """Modify an existing stop order to a new stop price.

        order_id is the stop_order_id returned by place_bracket_order.
        """
        # Retrieve the open order by ID and modify its auxPrice (stop price)
        for trade in self._ib.trades():
            if str(trade.order.orderId) == str(order_id):
                trade.order.auxPrice = round(new_stop_price, 2)
                self._ib.placeOrder(trade.contract, trade.order)
                return {"id": order_id, "status": "modified"}
        raise ValueError(f"[ibkr_client] order {order_id} not found in open trades")

    async def subscribe_bars(self, symbols: list[str], callback) -> None:
        """Subscribe to real-time 5-second bars via ib_insync reqRealTimeBars.

        Runs indefinitely until cancelled. Each bar event calls callback(bar)
        where bar is a dict-like object with .symbol, .close, .volume attributes.
        """
        if not self.is_configured:
            print("[ibkr_client] subscribe_bars: not connected", file=sys.stderr)
            return

        bar_lists = []
        for symbol in symbols:
            contract = self._make_contract(symbol)
            bars = self._ib.reqRealTimeBars(contract, 5, "TRADES", False)
            bar_lists.append((symbol, bars))

        # Attach callbacks
        def _make_handler(sym):
            def _handler(bars, has_new_bar):
                if has_new_bar and bars:
                    bar = bars[-1]
                    # Attach symbol attribute so callback matches Alpaca bar interface
                    bar.symbol = sym
                    asyncio.ensure_future(callback(bar))
            return _handler

        for symbol, bars in bar_lists:
            bars.updateEvent += _make_handler(symbol)

        # Run ib_insync event loop until cancelled
        try:
            while True:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            for symbol, bars in bar_lists:
                self._ib.cancelRealTimeBars(bars)
            raise
```

- [ ] Create `ibkr_client.py` with the code above
- [ ] Run: `uv run pytest tests/test_ibkr_client.py -v`
- [ ] Expected: all tests **PASS** (mocked IB, no real IBKR connection needed)

### Step 3.3 — Run full suite

- [ ] Run: `uv run pytest tests/ -v`
- [ ] Expected: no new failures

### Step 3.4 — Commit

```bash
git add ibkr_client.py tests/test_ibkr_client.py
git commit -m "feat: add IBKRClient implementing BrokerClient Protocol via ib_insync"
```

- [ ] Commit

---

## Task 4: PivotWatchlistMonitor — broker abstraction

**Files:**
- Modify: `pivot_monitor.py`
- Modify: `tests/test_pivot_monitor.py` (add multi-market cases)

### Step 4.1 — Write failing tests first

Find `tests/test_pivot_monitor.py` and add the following tests **before** implementing the changes:

```python
# Add to tests/test_pivot_monitor.py

def _make_monitor_with_broker(broker, market_config=None, pdt_enabled=True, calendar_file=None):
    """Build a PivotWatchlistMonitor using the new broker abstraction interface."""
    from pivot_monitor import PivotWatchlistMonitor
    from settings_manager import SettingsManager
    from pathlib import Path
    import tempfile

    cache_dir = Path(tempfile.mkdtemp())
    sm = SettingsManager()
    if market_config is None:
        market_config = {
            "id": "us",
            "tz": "America/New_York",
            "open": "09:30",
            "close": "16:00",
        }
    return PivotWatchlistMonitor(
        broker_client=broker,
        settings_manager=sm,
        cache_dir=cache_dir,
        market_config=market_config,
        pdt_enabled=pdt_enabled,
        calendar_file=calendar_file,
    )


def test_monitor_accepts_broker_client_param():
    """PivotWatchlistMonitor accepts broker_client keyword and stores as self._broker."""
    from unittest.mock import MagicMock
    broker = MagicMock()
    broker.is_configured = True

    monitor = _make_monitor_with_broker(broker)
    assert monitor._broker is broker


def test_pdt_disabled_skips_pdt_guard():
    """When pdt_enabled=False, PDT tracker block is skipped even with 0 slots."""
    from unittest.mock import MagicMock
    from learning.pdt_tracker import PDTTracker
    import tempfile
    from pathlib import Path
    from settings_manager import SettingsManager

    broker = MagicMock()
    broker.is_configured = True
    broker.get_positions.return_value = []
    broker.get_account.return_value = {"portfolio_value": 10000.0}
    broker.get_current_volume.side_effect = Exception("no vol")

    pdt = MagicMock()
    pdt.get_allowed_tags.return_value = set()  # 0 slots — would block if PDT enabled

    from pivot_monitor import PivotWatchlistMonitor
    sm = SettingsManager()
    cache_dir = Path(tempfile.mkdtemp())
    market_config = {"id": "oslo", "tz": "Europe/Oslo", "open": "09:00", "close": "16:30"}

    monitor = PivotWatchlistMonitor(
        broker_client=broker,
        settings_manager=sm,
        cache_dir=cache_dir,
        market_config=market_config,
        pdt_enabled=False,  # PDT disabled for Oslo
        pdt_tracker=pdt,
    )

    # Patch _is_market_open_now to return True so we get past the hours check
    monitor._is_market_open_now = lambda: True

    allowed, reason = monitor._guard_rails_allow({"symbol": "EQNR"}, tag="CLEAR")
    # Should not be blocked by PDT since pdt_enabled=False
    assert "PDT" not in reason


def test_market_hours_from_config_oslo():
    """_is_market_open_now uses market_config tz/open/close, not hardcoded ET."""
    from unittest.mock import MagicMock, patch
    from datetime import datetime
    from zoneinfo import ZoneInfo

    broker = MagicMock()
    market_config = {
        "id": "oslo",
        "tz": "Europe/Oslo",
        "open": "09:00",
        "close": "16:30",
    }
    monitor = _make_monitor_with_broker(broker, market_config=market_config)

    # Simulate 10:00 Oslo time on a Tuesday → should be open
    oslo_tz = ZoneInfo("Europe/Oslo")
    mock_now = datetime(2026, 3, 24, 10, 0, 0, tzinfo=oslo_tz)  # Tuesday 10:00 Oslo

    with patch("pivot_monitor.datetime") as mock_dt:
        mock_dt.now.return_value = mock_now
        result = monitor._is_market_open_now()

    assert result is True


def test_market_hours_closed_outside_config():
    """_is_market_open_now returns False outside configured hours."""
    from unittest.mock import MagicMock, patch
    from datetime import datetime
    from zoneinfo import ZoneInfo

    broker = MagicMock()
    market_config = {
        "id": "oslo",
        "tz": "Europe/Oslo",
        "open": "09:00",
        "close": "16:30",
    }
    monitor = _make_monitor_with_broker(broker, market_config=market_config)

    oslo_tz = ZoneInfo("Europe/Oslo")
    mock_now = datetime(2026, 3, 24, 17, 0, 0, tzinfo=oslo_tz)  # 17:00 → closed

    with patch("pivot_monitor.datetime") as mock_dt:
        mock_dt.now.return_value = mock_now
        result = monitor._is_market_open_now()

    assert result is False


def test_per_market_trade_log_file():
    """_log_trade writes to cache/<market-id>-auto_trades.json."""
    from unittest.mock import MagicMock
    import tempfile
    from pathlib import Path

    broker = MagicMock()
    broker.get_account.return_value = {"portfolio_value": 10000.0}

    market_config = {"id": "oslo", "tz": "Europe/Oslo", "open": "09:00", "close": "16:30"}
    monitor = _make_monitor_with_broker(broker, market_config=market_config)

    candidate = {"symbol": "EQNR", "pivot_price": 300.0}
    monitor._log_trade(candidate, "order-123", 310.0, 300.0, 10, "CLEAR")

    trades_file = monitor._cache_dir / "oslo-auto_trades.json"
    assert trades_file.exists()
    import json
    data = json.loads(trades_file.read_text())
    assert len(data["trades"]) == 1
    assert data["trades"][0]["symbol"] == "EQNR"
    assert data["trades"][0]["market"] == "oslo"
```

- [ ] Add the tests above to `tests/test_pivot_monitor.py`
- [ ] Run: `uv run pytest tests/test_pivot_monitor.py::test_monitor_accepts_broker_client_param tests/test_pivot_monitor.py::test_pdt_disabled_skips_pdt_guard tests/test_pivot_monitor.py::test_market_hours_from_config_oslo tests/test_pivot_monitor.py::test_market_hours_closed_outside_config tests/test_pivot_monitor.py::test_per_market_trade_log_file -v`
- [ ] Expected: all five **FAIL** — pivot_monitor still expects `alpaca_client` param and has hardcoded ET hours

### Step 4.2 — Migrate `pivot_monitor.py`

Apply all changes to `pivot_monitor.py` in order:

**4.2.1 — Update imports**

Replace:
```python
from alpaca_client import AlpacaClient
```
With:
```python
from broker_client import BrokerClient
```

**4.2.2 — Update `__init__` signature and assignment**

Replace the `__init__` signature:
```python
    def __init__(
        self,
        alpaca_client: AlpacaClient,
        settings_manager: SettingsManager,
        cache_dir: Path,
        rule_store=None,
        multiplier_store=None,
        pdt_tracker=None,
        drawdown_tracker=None,
        earnings_blackout=None,
        _search_fn: Optional[Callable[[str], list[str]]] = None,
        _data_stream=None,
    ):
        self._alpaca = alpaca_client
```
With:
```python
    def __init__(
        self,
        broker_client: "BrokerClient",
        settings_manager: SettingsManager,
        cache_dir: Path,
        market_config: dict | None = None,
        pdt_enabled: bool = True,
        calendar_file: Path | None = None,
        rule_store=None,
        multiplier_store=None,
        pdt_tracker=None,
        drawdown_tracker=None,
        earnings_blackout=None,
        _search_fn: Optional[Callable[[str], list[str]]] = None,
        _data_stream=None,
    ):
        self._broker = broker_client
        self._market_config = market_config or {
            "id": "us",
            "tz": "America/New_York",
            "open": "09:30",
            "close": "16:00",
        }
        self._pdt_enabled = pdt_enabled
        self._calendar_file = calendar_file
```

**4.2.3 — Replace all `self._alpaca` with `self._broker`**

Use search-and-replace for `self._alpaca` → `self._broker` throughout the file. Full list from spec migration table:
- `_guard_rails_allow`: `self._alpaca.get_positions()` → `self._broker.get_positions()`
- `_guard_rails_allow`: `self._alpaca.get_account()` → `self._broker.get_account()`
- `_guard_rails_allow`: `self._alpaca.get_current_volume()` → `self._broker.get_current_volume()`
- `_fire_order`: `self._alpaca.get_last_price()` → `self._broker.get_last_price()`
- `_fire_order`: `self._alpaca.get_account()` → `self._broker.get_account()`
- `_fire_order`: `self._alpaca.place_bracket_order()` → `self._broker.place_bracket_order()`
- `_apply_trailing_stop`: `self._alpaca.get_last_price()` → `self._broker.get_last_price()`
- `_apply_trailing_stop`: `self._alpaca.replace_order_stop()` → `self._broker.replace_order_stop()`
- `_apply_partial_exit`: `self._alpaca.get_last_price()` → `self._broker.get_last_price()`
- `_apply_partial_exit`: `self._alpaca.place_market_sell()` → `self._broker.place_market_sell()`
- `_apply_time_stop`: `self._alpaca.get_last_price()` → `self._broker.get_last_price()`
- `_apply_time_stop`: `self._alpaca.place_market_sell()` → `self._broker.place_market_sell()`
- `start()`: `self._alpaca.is_configured` → `self._broker.is_configured`

**4.2.4 — Replace `_market_is_open_now()` call in `_guard_rails_allow` with instance method call**

In `_guard_rails_allow`, replace:
```python
        if not _market_is_open_now():
            return False, "outside market hours"
```
With:
```python
        if not self._is_market_open_now():
            return False, "outside market hours"
```

**4.2.5 — Fix hardcoded ET hours in `_guard_rails_allow` time-of-day soft lock**

Replace the time-of-day soft lock block (lines ~261–269):
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
            if in_soft_lock and tag != "HIGH_CONVICTION":
                return False, f"time-of-day soft lock: {tag} blocked in open/close window"
```
With:
```python
        # Time-of-day soft lock — uses market_config hours and timezone
        avoid_min = settings.get("avoid_open_close_minutes", 30)
        if avoid_min > 0:
            tz_str = self._market_config.get("tz", "America/New_York")
            open_str = self._market_config.get("open", "09:30")
            close_str = self._market_config.get("close", "16:00")
            open_h, open_m = int(open_str.split(":")[0]), int(open_str.split(":")[1])
            close_h, close_m = int(close_str.split(":")[0]), int(close_str.split(":")[1])
            now_local = datetime.now(ZoneInfo(tz_str))
            market_open = now_local.replace(hour=open_h, minute=open_m, second=0, microsecond=0)
            market_close = now_local.replace(hour=close_h, minute=close_m, second=0, microsecond=0)
            minutes_since_open = (now_local - market_open).total_seconds() / 60
            minutes_to_close = (market_close - now_local).total_seconds() / 60
            in_soft_lock = minutes_since_open < avoid_min or minutes_to_close < avoid_min
            if in_soft_lock and tag != "HIGH_CONVICTION":
                return False, f"time-of-day soft lock: {tag} blocked in open/close window"
```

**4.2.6 — Wrap PDT block with `if self._pdt_enabled`**

In `_guard_rails_allow`, wrap the PDT selectivity block:
```python
        # PDT selectivity
        if self._pdt_enabled and self._pdt_tracker is not None:
            from datetime import date as _date
            allowed_tags = self._pdt_tracker.get_allowed_tags(_date.today())
            if not allowed_tags:
                return False, "PDT: 3 day trades used — no new entries"
            if tag not in allowed_tags:
                return False, f"PDT: {len(allowed_tags)} slot(s) left — {tag} not allowed"
```

**4.2.7 — Add `_is_market_open_now` instance method**

Add this method to `PivotWatchlistMonitor`, replacing the `_check_exit_management` self-import:

```python
    def _is_market_open_now(self) -> bool:
        """Check if current time is within market hours using market_config."""
        tz_str = self._market_config.get("tz", "America/New_York")
        open_str = self._market_config.get("open", "09:30")
        close_str = self._market_config.get("close", "16:00")
        open_h, open_m = int(open_str.split(":")[0]), int(open_str.split(":")[1])
        close_h, close_m = int(close_str.split(":")[0]), int(close_str.split(":")[1])
        now = datetime.now(ZoneInfo(tz_str))
        if now.weekday() >= 5:  # Saturday or Sunday
            return False
        t = now.time()
        from datetime import time as _time
        market_open = _time(open_h, open_m)
        market_close = _time(close_h, close_m)
        return market_open <= t < market_close
```

Also update `_check_exit_management` to remove the self-import of `_market_is_open_now`:

Replace:
```python
    def _check_exit_management(self) -> None:
        from pivot_monitor import _market_is_open_now
        if not _market_is_open_now():
            return
```
With:
```python
    def _check_exit_management(self) -> None:
        if not self._is_market_open_now():
            return
```

**4.2.8 — Update `start()` to use `subscribe_bars`**

Replace the stream construction block in `start()`:
```python
        if self._data_stream is not None:
            stream = self._data_stream
        else:
            from alpaca.data.live import StockDataStream
            stream = StockDataStream(
                api_key=self._alpaca.api_key,
                secret_key=self._alpaca.secret_key,
            )

        symbols = [c["symbol"] for c in self._candidates]
        monitor = self  # capture for closure

        async def handle_bar(bar):
            monitor._check_breakout(bar, monitor._candidates)

        stream.subscribe_bars(handle_bar, *symbols)

        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(None, stream.run)
        except Exception as e:
            print(f"[pivot_monitor] stream disconnected: {e}", file=sys.stderr)
```
With:
```python
        symbols = [c["symbol"] for c in self._candidates]

        async def handle_bar(bar):
            self._check_breakout(bar, self._candidates)

        if self._data_stream is not None:
            # Test injection: simulate stream with a mock object that has subscribe_bars/run
            stream = self._data_stream
            stream.subscribe_bars(handle_bar, *symbols)
            loop = asyncio.get_running_loop()
            try:
                await loop.run_in_executor(None, stream.run)
            except Exception as e:
                print(f"[pivot_monitor] stream disconnected: {e}", file=sys.stderr)
        else:
            try:
                await self._broker.subscribe_bars(symbols, handle_bar)
            except Exception as e:
                print(f"[pivot_monitor] subscribe_bars error: {e}", file=sys.stderr)
```

**4.2.9 — Update `_log_trade` for per-market files**

Replace:
```python
    def _log_trade(
        self, candidate: dict, order_id: str,
        entry_price: float, stop_price: float, qty: int, tag: str,
    ) -> None:
        """Append trade context to cache/auto_trades.json for pattern extraction.
        ...
        """
        trades_file = self._cache_dir / "auto_trades.json"
```
With:
```python
    def _log_trade(
        self, candidate: dict, order_id: str,
        entry_price: float, stop_price: float, qty: int, tag: str,
    ) -> None:
        """Append trade context to cache/<market-id>-auto_trades.json.

        Each market writes to its own file to avoid concurrent write conflicts.
        Backward-compatible: US market uses 'us-auto_trades.json'.
        """
        market_id = self._market_config.get("id", "us")
        trades_file = self._cache_dir / f"{market_id}-auto_trades.json"
        # Backward-compatible read: if us-auto_trades.json missing, check auto_trades.json
        if market_id == "us" and not trades_file.exists():
            legacy_file = self._cache_dir / "auto_trades.json"
            if legacy_file.exists():
                trades_file = legacy_file
```

Also add `"market": market_id` to the trade dict that is appended:

```python
        trades["trades"].append({
            "symbol": candidate["symbol"],
            "order_id": order_id,
            "market": market_id,          # ← new field
            "entry_time": datetime.now(timezone.utc).isoformat(),
            "entry_price": entry_price,
            ...
        })
```

**4.2.10 — Update `_get_earnings_soon_symbols` to use `calendar_file`**

Replace:
```python
    def _get_earnings_soon_symbols(self) -> set:
        earnings_file = self._cache_dir / "earnings-calendar.json"
```
With:
```python
    def _get_earnings_soon_symbols(self) -> set:
        if self._calendar_file is not None:
            earnings_file = Path(self._calendar_file)
        else:
            earnings_file = self._cache_dir / "earnings-calendar.json"
```

- [ ] Apply all changes from Steps 4.2.1–4.2.10 to `pivot_monitor.py`
- [ ] Run: `uv run pytest tests/test_pivot_monitor.py -v`
- [ ] Expected: all new tests **PASS**, existing tests should also still pass (backward compat via defaults)

### Step 4.3 — Update `main.py` to pass broker_client and market_config to existing monitor

The existing single-monitor construction in `main.py` must be updated to use the new param names:

Replace:
```python
pivot_monitor = PivotWatchlistMonitor(
    alpaca_client=alpaca,
    settings_manager=settings_manager,
    cache_dir=CACHE_DIR,
    rule_store=rule_store,
    multiplier_store=multiplier_store,
    pdt_tracker=pdt_tracker,
    drawdown_tracker=drawdown_tracker,
    earnings_blackout=earnings_blackout,
)
```
With:
```python
_us_market_config = {
    "id": "us",
    "label": "US (NYSE/NASDAQ)",
    "broker": "alpaca",
    "exchange": "SMART",
    "currency": "USD",
    "tz": "America/New_York",
    "open": "09:30",
    "close": "16:00",
    "pdt_enabled": True,
    "enabled": True,
}
pivot_monitor = PivotWatchlistMonitor(
    broker_client=alpaca,
    settings_manager=settings_manager,
    cache_dir=CACHE_DIR,
    market_config=_us_market_config,
    pdt_enabled=True,
    rule_store=rule_store,
    multiplier_store=multiplier_store,
    pdt_tracker=pdt_tracker,
    drawdown_tracker=drawdown_tracker,
    earnings_blackout=earnings_blackout,
)
```

- [ ] Update `main.py`
- [ ] Run: `uv run pytest tests/ -v`
- [ ] Expected: no new failures

### Step 4.4 — Commit

```bash
git add pivot_monitor.py main.py tests/test_pivot_monitor.py
git commit -m "feat: pivot_monitor — broker abstraction, dynamic market hours, PDT flag, per-market trade log"
```

- [ ] Commit

---

## Task 5: Market configuration in settings_manager.py

**Files:**
- Modify: `settings_manager.py`
- Create: `tests/test_settings_manager.py`

### Step 5.1 — Write the failing tests

Create `tests/test_settings_manager.py`:

```python
# tests/test_settings_manager.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
import tempfile
import json
from unittest.mock import patch


def _make_manager(tmp_path):
    from settings_manager import SettingsManager
    from config import SETTINGS_FILE
    # Patch SETTINGS_FILE to use tmp_path
    settings_file = tmp_path / "settings.json"
    with patch("settings_manager.SETTINGS_FILE", settings_file):
        manager = SettingsManager()
        # monkey-patch for the duration of the test
        manager._settings_file = settings_file
    return manager, settings_file


def test_defaults_include_markets(tmp_path):
    """_DEFAULTS must contain a markets list with us, oslo, lse entries."""
    from settings_manager import _DEFAULTS
    assert "markets" in _DEFAULTS
    ids = [m["id"] for m in _DEFAULTS["markets"]]
    assert "us" in ids
    assert "oslo" in ids
    assert "lse" in ids


def test_get_enabled_markets_returns_only_enabled(tmp_path):
    """get_enabled_markets returns only markets where enabled=True."""
    from settings_manager import SettingsManager
    from config import SETTINGS_FILE
    settings_file = tmp_path / "settings.json"
    settings_file.write_text(json.dumps({
        "markets": [
            {"id": "us", "enabled": True, "broker": "alpaca"},
            {"id": "oslo", "enabled": False, "broker": "ibkr"},
            {"id": "lse", "enabled": True, "broker": "ibkr"},
        ]
    }))
    with patch("settings_manager.SETTINGS_FILE", settings_file):
        sm = SettingsManager()
        result = sm.get_enabled_markets()
    ids = [m["id"] for m in result]
    assert "us" in ids
    assert "lse" in ids
    assert "oslo" not in ids


def test_save_rejects_all_disabled_markets(tmp_path):
    """save() must reject settings where all markets are disabled."""
    from settings_manager import SettingsManager
    settings_file = tmp_path / "settings.json"
    with patch("settings_manager.SETTINGS_FILE", settings_file):
        sm = SettingsManager()
        with pytest.raises(ValueError, match="at least one market"):
            sm.save({
                "mode": "advisory",
                "environment": "paper",
                "markets": [
                    {"id": "us", "enabled": False, "broker": "alpaca"},
                    {"id": "oslo", "enabled": False, "broker": "ibkr"},
                ]
            })


def test_save_rejects_unknown_broker(tmp_path):
    """save() must reject unknown broker values in markets list."""
    from settings_manager import SettingsManager
    settings_file = tmp_path / "settings.json"
    with patch("settings_manager.SETTINGS_FILE", settings_file):
        sm = SettingsManager()
        with pytest.raises(ValueError, match="broker"):
            sm.save({
                "mode": "advisory",
                "environment": "paper",
                "markets": [
                    {"id": "us", "enabled": True, "broker": "unknown_broker"},
                ]
            })


def test_load_merges_defaults_with_stored(tmp_path):
    """load() merges _DEFAULTS with stored settings, markets preserved."""
    from settings_manager import SettingsManager
    settings_file = tmp_path / "settings.json"
    settings_file.write_text(json.dumps({"mode": "auto"}))
    with patch("settings_manager.SETTINGS_FILE", settings_file):
        sm = SettingsManager()
        result = sm.load()
    assert result["mode"] == "auto"
    assert "markets" in result
```

- [ ] Create `tests/test_settings_manager.py` with the tests above
- [ ] Run: `uv run pytest tests/test_settings_manager.py -v`
- [ ] Expected: `test_defaults_include_markets` **FAIL** (no markets in defaults yet); others also **FAIL**

### Step 5.2 — Update `settings_manager.py`

**5.2.1 — Add markets to `_DEFAULTS`**

Add after the last existing default entry:

```python
    "markets": [
        {
            "id": "us",
            "label": "US (NYSE/NASDAQ)",
            "broker": "alpaca",
            "exchange": "SMART",
            "currency": "USD",
            "tz": "America/New_York",
            "open": "09:30",
            "close": "16:00",
            "pdt_enabled": True,
            "enabled": True,
        },
        {
            "id": "oslo",
            "label": "Oslo Børs",
            "broker": "ibkr",
            "exchange": "OSE",
            "currency": "NOK",
            "tz": "Europe/Oslo",
            "open": "09:00",
            "close": "16:30",
            "pdt_enabled": False,
            "enabled": True,
        },
        {
            "id": "lse",
            "label": "London Stock Exchange",
            "broker": "ibkr",
            "exchange": "LSE",
            "currency": "GBP",
            "tz": "Europe/London",
            "open": "08:00",
            "close": "16:30",
            "pdt_enabled": False,
            "enabled": True,
        },
    ],
```

**5.2.2 — Add `get_enabled_markets()` method**

Add to `SettingsManager`:

```python
    def get_enabled_markets(self) -> list[dict]:
        """Return only markets where enabled=True."""
        settings = self.load()
        return [m for m in settings.get("markets", []) if m.get("enabled", True)]
```

**5.2.3 — Add validation in `save()`**

Add after the existing `environment` validation in `save()`:

```python
        # Markets validation
        markets = settings.get("markets", [])
        if markets:
            valid_brokers = {"alpaca", "ibkr"}
            for m in markets:
                broker_val = m.get("broker", "")
                if broker_val not in valid_brokers:
                    raise ValueError(
                        f"Invalid broker '{broker_val}' in market '{m.get('id', '?')}'. "
                        f"Must be one of {valid_brokers}"
                    )
            enabled_count = sum(1 for m in markets if m.get("enabled", True))
            if enabled_count == 0:
                raise ValueError(
                    "Invalid settings: at least one market must be enabled"
                )
```

- [ ] Apply all changes to `settings_manager.py`
- [ ] Run: `uv run pytest tests/test_settings_manager.py -v`
- [ ] Expected: all tests **PASS**

### Step 5.3 — Run full suite

- [ ] Run: `uv run pytest tests/ -v`
- [ ] Expected: no new failures

### Step 5.4 — Commit

```bash
git add settings_manager.py tests/test_settings_manager.py
git commit -m "feat: settings_manager — add markets defaults, get_enabled_markets, save validation"
```

- [ ] Commit

---

## Task 6: Universe Builder

**Files:**
- Create: `universe_builder.py`
- Create: `tests/test_universe_builder.py`

### Step 6.1 — Write the failing tests

Create `tests/test_universe_builder.py`:

```python
# tests/test_universe_builder.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
import json
import tempfile
from unittest.mock import MagicMock, patch


def _make_mock_ibkr():
    """Build an IBKRClient mock that returns plausible data."""
    mock = MagicMock()
    mock.is_configured = True

    # reqContractDetails returns a list of stock contracts
    mock_detail1 = MagicMock()
    mock_detail1.contract.symbol = "EQNR"
    mock_detail1.longName = "Equinor ASA"

    mock_detail2 = MagicMock()
    mock_detail2.contract.symbol = "DNB"
    mock_detail2.longName = "DNB Bank ASA"

    mock.reqContractDetails.return_value = [mock_detail1, mock_detail2]

    # reqHistoricalData returns OHLCV bars
    def _make_bars(symbol):
        bars = []
        for i in range(60):
            bar = MagicMock()
            bar.open = 100.0 + i
            bar.high = 105.0 + i
            bar.low = 99.0 + i
            bar.close = 102.0 + i
            bar.volume = 500_000
            bars.append(bar)
        return bars

    mock._ib = MagicMock()
    mock._ib.reqHistoricalData.side_effect = lambda *a, **kw: _make_bars("X")
    return mock


def test_build_universe_creates_cache_file():
    """build_universe writes cache/<market-id>-universe.json."""
    from universe_builder import UniverseBuilder
    import tempfile

    mock_ibkr = _make_mock_ibkr()
    cache_dir = Path(tempfile.mkdtemp())
    market_config = {
        "id": "oslo",
        "exchange": "OSE",
        "currency": "NOK",
        "tz": "Europe/Oslo",
        "min_market_cap": 1_000_000_000,
        "min_avg_volume": 100_000,
    }

    builder = UniverseBuilder(ibkr_client=mock_ibkr, cache_dir=cache_dir, request_delay=0)
    builder.build_universe(market_config)

    output_file = cache_dir / "oslo-universe.json"
    assert output_file.exists()


def test_build_universe_output_format():
    """Output JSON has market, updated, symbols fields."""
    from universe_builder import UniverseBuilder

    mock_ibkr = _make_mock_ibkr()
    cache_dir = Path(tempfile.mkdtemp())
    market_config = {
        "id": "oslo",
        "exchange": "OSE",
        "currency": "NOK",
        "tz": "Europe/Oslo",
        "min_market_cap": 0,        # no filter — include all
        "min_avg_volume": 0,
    }

    builder = UniverseBuilder(ibkr_client=mock_ibkr, cache_dir=cache_dir, request_delay=0)
    builder.build_universe(market_config)

    data = json.loads((cache_dir / "oslo-universe.json").read_text())
    assert data["market"] == "oslo"
    assert "updated" in data
    assert "symbols" in data
    assert isinstance(data["symbols"], list)


def test_build_universe_filters_by_volume():
    """Symbols below min_avg_volume threshold are excluded."""
    from universe_builder import UniverseBuilder

    mock_ibkr = _make_mock_ibkr()
    # Override bars to return low volume
    def _low_vol_bars(*a, **kw):
        bar = MagicMock()
        bar.close = 100.0
        bar.volume = 10_000  # below threshold
        return [bar] * 60

    mock_ibkr._ib.reqHistoricalData.side_effect = _low_vol_bars

    cache_dir = Path(tempfile.mkdtemp())
    market_config = {
        "id": "oslo",
        "exchange": "OSE",
        "currency": "NOK",
        "tz": "Europe/Oslo",
        "min_market_cap": 0,
        "min_avg_volume": 100_000,  # require 100k avg volume
    }

    builder = UniverseBuilder(ibkr_client=mock_ibkr, cache_dir=cache_dir, request_delay=0)
    builder.build_universe(market_config)

    data = json.loads((cache_dir / "oslo-universe.json").read_text())
    assert data["symbols"] == []


def test_build_universe_skips_when_ibkr_not_configured():
    """build_universe returns empty result when IBKR not connected."""
    from universe_builder import UniverseBuilder

    mock_ibkr = MagicMock()
    mock_ibkr.is_configured = False

    cache_dir = Path(tempfile.mkdtemp())
    market_config = {"id": "oslo", "exchange": "OSE", "currency": "NOK"}

    builder = UniverseBuilder(ibkr_client=mock_ibkr, cache_dir=cache_dir, request_delay=0)
    result = builder.build_universe(market_config)
    assert result == []


def test_request_delay_is_respected(monkeypatch):
    """build_universe sleeps request_delay seconds between symbol requests."""
    from universe_builder import UniverseBuilder
    import time

    mock_ibkr = _make_mock_ibkr()
    cache_dir = Path(tempfile.mkdtemp())
    market_config = {
        "id": "oslo",
        "exchange": "OSE",
        "currency": "NOK",
        "min_market_cap": 0,
        "min_avg_volume": 0,
    }

    sleep_calls = []
    monkeypatch.setattr("universe_builder.time.sleep", lambda s: sleep_calls.append(s))

    builder = UniverseBuilder(ibkr_client=mock_ibkr, cache_dir=cache_dir, request_delay=6)
    builder.build_universe(market_config)

    # Should have slept once per symbol fetched
    assert all(s == 6 for s in sleep_calls)
    assert len(sleep_calls) >= 1
```

- [ ] Create `tests/test_universe_builder.py`
- [ ] Run: `uv run pytest tests/test_universe_builder.py -v`
- [ ] Expected: all **FAIL** — `universe_builder` module not found

### Step 6.2 — Create `universe_builder.py`

```python
"""Weekly universe builder for non-US markets via IBKR.

For each enabled non-US market:
1. Fetch all listed stocks from IBKR for the configured exchange
2. Filter by: min average volume (default 100k/day), price above 50-day MA (uptrend)
3. Save to cache/<market-id>-universe.json
4. Also write cache/<market-id>-earnings-calendar.json

IBKR pacing: 60 historical data requests per 10 minutes.
Default request_delay=6 seconds. 100 stocks ≈ 10 minutes.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


class UniverseBuilder:
    """Builds and caches the tradeable stock universe for each non-US market.

    Inject ibkr_client in production. Pass request_delay=0 in tests.
    """

    def __init__(self, ibkr_client, cache_dir: Path, request_delay: float = 6.0):
        self._ibkr = ibkr_client
        self._cache_dir = cache_dir
        self._request_delay = request_delay

    def build_universe(self, market_config: dict) -> list[dict]:
        """Fetch, filter, and cache the universe for one market.

        Returns the filtered symbols list. Writes cache/<market-id>-universe.json.
        Returns [] and logs warning if IBKR not configured.
        """
        market_id = market_config.get("id", "unknown")
        exchange = market_config.get("exchange", "SMART")
        min_avg_volume = market_config.get("min_avg_volume", 100_000)
        min_market_cap = market_config.get("min_market_cap", 0)

        if not self._ibkr.is_configured:
            print(
                f"[universe_builder] {market_id}: IBKR not connected — skipping",
                file=sys.stderr,
            )
            return []

        # Step 1: Fetch all listed contracts for the exchange
        try:
            from ib_insync import Stock
            contracts = self._fetch_contracts(exchange)
        except Exception as e:
            print(f"[universe_builder] {market_id}: contract fetch failed: {e}", file=sys.stderr)
            return []

        if not contracts:
            print(f"[universe_builder] {market_id}: no contracts returned", file=sys.stderr)
            return []

        # Step 2: For each contract, fetch historical bars and apply filters
        symbols = []
        for detail in contracts:
            try:
                symbol = detail.contract.symbol
                long_name = getattr(detail, "longName", symbol)

                bars = self._fetch_bars(detail.contract, exchange)
                if not bars:
                    continue

                avg_vol = sum(b.volume for b in bars) / len(bars)
                if avg_vol < min_avg_volume:
                    continue

                # Uptrend filter: current close > 50-bar MA
                closes = [b.close for b in bars]
                ma50 = sum(closes[-50:]) / min(50, len(closes))
                if closes[-1] < ma50:
                    continue

                symbols.append({
                    "symbol": symbol,
                    "name": long_name,
                    "avg_volume": int(avg_vol),
                    "last_close": round(closes[-1], 4),
                })

                if self._request_delay > 0:
                    time.sleep(self._request_delay)

            except Exception as e:
                print(
                    f"[universe_builder] {market_id}/{symbol} error: {e}",
                    file=sys.stderr,
                )
                continue

        # Step 3: Write cache file
        output = {
            "market": market_id,
            "updated": datetime.now(timezone.utc).isoformat(),
            "symbols": symbols,
        }
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        output_file = self._cache_dir / f"{market_id}-universe.json"
        output_file.write_text(json.dumps(output, indent=2))
        print(
            f"[universe_builder] {market_id}: wrote {len(symbols)} symbols to {output_file}",
            file=sys.stderr,
        )
        return symbols

    def _fetch_contracts(self, exchange: str) -> list:
        """Fetch all stock contracts for an exchange from IBKR."""
        try:
            from ib_insync import Stock
            # Use reqContractDetails with a wildcard Stock contract
            # This returns all stocks on the given exchange
            template = Stock("", exchange, "")
            return self._ibkr.reqContractDetails(template)
        except Exception as e:
            print(f"[universe_builder] _fetch_contracts({exchange}) error: {e}", file=sys.stderr)
            return []

    def _fetch_bars(self, contract, exchange: str) -> list:
        """Fetch 60 daily bars for a contract."""
        try:
            return self._ibkr._ib.reqHistoricalData(
                contract,
                endDateTime="",
                durationStr="3 M",
                barSizeSetting="1 day",
                whatToShow="TRADES",
                useRTH=True,
                formatDate=1,
            )
        except Exception as e:
            print(f"[universe_builder] _fetch_bars error: {e}", file=sys.stderr)
            return []

    def build_all(self, markets: list[dict]) -> None:
        """Build universe for each non-US market in the list.

        US market is skipped — it uses the VCP screener output directly.
        """
        for market in markets:
            if not market.get("enabled", True):
                continue
            if market.get("broker") == "alpaca":
                continue  # US market — skip
            self.build_universe(market)
```

- [ ] Create `universe_builder.py`
- [ ] Run: `uv run pytest tests/test_universe_builder.py -v`
- [ ] Expected: all tests **PASS**

### Step 6.3 — Run full suite

- [ ] Run: `uv run pytest tests/ -v`
- [ ] Expected: no new failures

### Step 6.4 — Commit

```bash
git add universe_builder.py tests/test_universe_builder.py
git commit -m "feat: add UniverseBuilder — weekly IBKR universe fetch and filter for non-US markets"
```

- [ ] Commit

---

## Task 7: Multi-market orchestrator in main.py

**Files:**
- Modify: `main.py`
- Modify: `scheduler.py`
- Modify: `tests/test_routes.py`

### Step 7.1 — Write the failing test

Add to `tests/test_routes.py`:

```python
def test_broker_status_endpoint():
    """GET /api/broker-status returns JSON with alpaca and ibkr keys."""
    client = make_client()
    response = client.get("/api/broker-status")
    assert response.status_code == 200
    data = response.json()
    assert "alpaca" in data
    assert "ibkr" in data
    assert isinstance(data["alpaca"], bool)
    assert isinstance(data["ibkr"], bool)
```

- [ ] Add the test to `tests/test_routes.py`
- [ ] Run: `uv run pytest tests/test_routes.py::test_broker_status_endpoint -v`
- [ ] Expected: **FAIL** with 404

### Step 7.2 — Update `main.py` for multi-market orchestration

**7.2.1 — Import IBKRClient and UniverseBuilder**

Add after the existing imports:
```python
from ibkr_client import IBKRClient
from universe_builder import UniverseBuilder
```

**7.2.2 — Instantiate IBKRClient**

Add after the `alpaca` instantiation:
```python
ibkr = IBKRClient(paper=ALPACA_PAPER)
```

Note: if IB Gateway is not running, `IBKRClient.__init__` catches the connection error and `ibkr.is_configured` returns False. US trading continues normally.

**7.2.3 — Build per-market monitors on startup**

Replace the single `pivot_monitor` construction with a list of monitors. Change the module-level `pivot_monitor` variable to `_monitors: list[PivotWatchlistMonitor] = []` and build one per enabled market:

```python
# Module-level broker map
_broker_map = {"alpaca": alpaca, "ibkr": ibkr}
_monitors: list[PivotWatchlistMonitor] = []


def _build_monitors() -> list[PivotWatchlistMonitor]:
    """Create one PivotWatchlistMonitor per enabled market."""
    monitors = []
    for market in settings_manager.get_enabled_markets():
        broker = _broker_map.get(market.get("broker", "alpaca"), alpaca)
        if not broker.is_configured:
            print(
                f"[main] {market['id']}: broker not configured — skipping monitor",
                file=sys.stderr,
            )
            continue
        pdt_enabled = market.get("pdt_enabled", True)
        calendar_file = CACHE_DIR / f"{market['id']}-earnings-calendar.json"
        monitor = PivotWatchlistMonitor(
            broker_client=broker,
            settings_manager=settings_manager,
            cache_dir=CACHE_DIR,
            market_config=market,
            pdt_enabled=pdt_enabled,
            calendar_file=calendar_file if calendar_file.exists() else None,
            rule_store=rule_store,
            multiplier_store=multiplier_store,
            pdt_tracker=pdt_tracker if pdt_enabled else None,
            drawdown_tracker=drawdown_tracker,
        )
        monitors.append(monitor)
    return monitors
```

**7.2.4 — Keep backward-compatible `pivot_monitor` reference**

For the existing scheduler code that references `pivot_monitor` directly, expose the US monitor as `pivot_monitor`:

```python
# Backward-compat: expose US monitor as pivot_monitor for scheduler and /api/monitor/status
def _get_us_monitor() -> "PivotWatchlistMonitor | None":
    for m in _monitors:
        if m._market_config.get("id") == "us":
            return m
    return _monitors[0] if _monitors else None
```

In `startup()`, build monitors and launch streams:
```python
@app.on_event("startup")
async def startup():
    global _scheduler, _monitors
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _monitors = _build_monitors()
    us_monitor = _get_us_monitor()
    _scheduler = create_scheduler(
        runner=runner,
        cache_dir=CACHE_DIR,
        pivot_monitor=us_monitor,      # scheduler still wired to US monitor only
        pattern_extractor=pattern_extractor,
        ibkr_client=ibkr,             # for weekly universe builder job
        settings_manager=settings_manager,
    )
    _scheduler.start()
    asyncio.create_task(_refresh_stale_on_startup())
    if alpaca.is_configured:
        asyncio.create_task(alpaca.start_trading_stream())
```

Update `api_monitor_status` to use `_get_us_monitor()`:
```python
@app.get("/api/monitor/status")
async def monitor_status():
    """Return current PivotWatchlistMonitor state for the Auto mode banner."""
    monitor = _get_us_monitor()
    if monitor is None:
        return JSONResponse({"active": False, "candidate_count": 0, "triggered": []})
    with monitor._lock:
        candidates_snapshot = list(monitor._candidates)
        triggered_snapshot = list(monitor._triggered)
    return JSONResponse({
        "active": len(candidates_snapshot) > 0,
        "candidate_count": len(candidates_snapshot),
        "triggered": triggered_snapshot,
    })
```

**7.2.5 — Add `GET /api/broker-status` endpoint**

Add after `api_monitor_status`:
```python
@app.get("/api/broker-status")
async def broker_status():
    """Return connection status for each broker client."""
    return JSONResponse({
        "alpaca": alpaca.is_configured,
        "ibkr": ibkr.is_configured,
    })
```

- [ ] Apply all changes to `main.py`

### Step 7.3 — Update `scheduler.py` for universe builder

Update `create_scheduler` signature to accept `ibkr_client` and `settings_manager`:

```python
def create_scheduler(
    runner,
    cache_dir: Path,
    pivot_monitor=None,
    pattern_extractor=None,
    ibkr_client=None,
    settings_manager=None,
) -> AsyncIOScheduler:
```

Add the weekly universe builder job at the end of `create_scheduler`, before `return sched`:

```python
    # ── Weekly universe builder for non-US markets ─────────────────────────
    if ibkr_client is not None and settings_manager is not None:
        from universe_builder import UniverseBuilder
        universe_builder = UniverseBuilder(
            ibkr_client=ibkr_client,
            cache_dir=cache_dir,
            request_delay=6.0,
        )

        def universe_build_job():
            markets = settings_manager.get_enabled_markets()
            universe_builder.build_all(markets)

        sched.add_job(
            universe_build_job,
            CronTrigger(day_of_week="sun", hour=20, minute=0),
            id="universe_builder",
            replace_existing=True,
        )
```

- [ ] Apply changes to `scheduler.py`

### Step 7.4 — Run tests

- [ ] Run: `uv run pytest tests/test_routes.py::test_broker_status_endpoint -v`
- [ ] Expected: **PASS**
- [ ] Run: `uv run pytest tests/ -v`
- [ ] Expected: no new failures

### Step 7.5 — Commit

```bash
git add main.py scheduler.py tests/test_routes.py
git commit -m "feat: multi-market orchestrator — per-market monitors, IBKRClient in main, /api/broker-status, weekly universe builder job"
```

- [ ] Commit

---

## Task 8: Trade log — per-market files

**Files:**
- Modify: `main.py` (trades_page route)
- Modify: `templates/trades.html`

### Step 8.1 — Write the failing test

Add to `tests/test_routes.py`:

```python
def test_trades_route_includes_all_market_files(tmp_path):
    """GET /trades merges all cache/*-auto_trades.json files."""
    import json
    from config import CACHE_DIR

    # Write two market trade files
    us_file = CACHE_DIR / "us-auto_trades.json"
    oslo_file = CACHE_DIR / "oslo-auto_trades.json"
    us_file.write_text(json.dumps({"trades": [
        {"symbol": "AAPL", "market": "us", "entry_price": 150.0, "stop_price": 145.0,
         "qty": 10, "outcome": None, "entry_time": "2026-03-20T14:00:00+00:00"}
    ]}))
    oslo_file.write_text(json.dumps({"trades": [
        {"symbol": "EQNR", "market": "oslo", "entry_price": 310.0, "stop_price": 300.0,
         "qty": 5, "outcome": None, "entry_time": "2026-03-20T10:00:00+00:00"}
    ]}))

    try:
        client = make_client()
        response = client.get("/trades")
        assert response.status_code == 200
        # Both symbols should appear in the rendered page
        assert "AAPL" in response.text
        assert "EQNR" in response.text
    finally:
        us_file.unlink(missing_ok=True)
        oslo_file.unlink(missing_ok=True)
```

- [ ] Add the test to `tests/test_routes.py`
- [ ] Run: `uv run pytest tests/test_routes.py::test_trades_route_includes_all_market_files -v`
- [ ] Expected: **FAIL** — trades page only reads single file; EQNR won't appear

### Step 8.2 — Update `trades_page` in `main.py`

Replace the `trades_page` route handler to merge all `*-auto_trades.json` files:

```python
@app.get("/trades", response_class=HTMLResponse)
async def trades_page(request: Request):
    trades = []
    # Collect all per-market trade files: cache/*-auto_trades.json
    trade_files = list(CACHE_DIR.glob("*-auto_trades.json"))
    # Backward compat: also check legacy auto_trades.json (no market prefix)
    legacy_file = CACHE_DIR / "auto_trades.json"
    if legacy_file.exists() and legacy_file not in trade_files:
        trade_files.append(legacy_file)

    for trade_file in trade_files:
        try:
            data = json.loads(trade_file.read_text())
            file_trades = data.get("trades", [])
            # Inject market field from filename if missing
            market_id = trade_file.stem.replace("-auto_trades", "")
            for t in file_trades:
                if "market" not in t:
                    t["market"] = market_id if market_id != "auto_trades" else "us"
            trades.extend(file_trades)
        except Exception:
            continue

    # Sort newest first by entry_time
    trades.sort(key=lambda t: t.get("entry_time", ""), reverse=True)

    # Pre-compute R for each trade
    for t in trades:
        try:
            risk = t["entry_price"] - t["stop_price"]
            if risk > 0 and t.get("exit_price"):
                t["r"] = round((t["exit_price"] - t["entry_price"]) / risk, 2)
            else:
                t["r"] = None
        except Exception:
            t["r"] = None

    # Summary stats
    closed = [t for t in trades if t.get("outcome") in ("win", "loss")]
    open_trades = [t for t in trades if not t.get("outcome")]
    wins = [t for t in closed if t.get("outcome") == "win"]
    win_rate = round(len(wins) / len(closed) * 100, 1) if closed else None
    r_values = [t["r"] for t in closed if t.get("r") is not None]
    avg_r = round(sum(r_values) / len(r_values), 2) if r_values else None

    ctx = {
        "request": request,
        "market_state": _market_state(),
        "settings": settings_manager.load(),
        "trades": trades,
        "total_trades": len(trades),
        "open_count": len(open_trades),
        "win_rate": win_rate,
        "avg_r": avg_r,
    }
    return templates.TemplateResponse("trades.html", ctx)
```

- [ ] Replace `trades_page` in `main.py`

### Step 8.3 — Update `templates/trades.html` to add Market column

In the trades table header, add a Market `<th>` after the Time column:
```html
          <th style="padding:6px; text-align:left;">Market</th>
```

In the table row body, add the market cell after the time cell:
```html
          <td style="padding:6px; color:#94a3b8; font-size:11px;">
            {{ t.market | default("us") | upper }}
          </td>
```

Update `colspan="10"` in the empty state row to `colspan="11"` to account for the new column.

- [ ] Update `templates/trades.html`

### Step 8.4 — Run tests

- [ ] Run: `uv run pytest tests/test_routes.py::test_trades_route_includes_all_market_files -v`
- [ ] Expected: **PASS**
- [ ] Run: `uv run pytest tests/ -v`
- [ ] Expected: no new failures

### Step 8.5 — Commit

```bash
git add main.py templates/trades.html tests/test_routes.py
git commit -m "feat: trade log — merge all per-market *-auto_trades.json files, add Market column to trades table"
```

- [ ] Commit

---

## Task 9: Dashboard Market column

**Files:**
- Modify: `templates/dashboard.html`

### Step 9.1 — Locate the signals table in `templates/dashboard.html`

Read `templates/dashboard.html` and find the signals table. The table renders skill signals from the `signals` context variable. Signals come from `SIGNAL_PANEL_SKILLS` and are grouped per skill. Each signal row represents a symbol from a screener.

Since signals are currently US-only (from Alpaca/VCP screener), add a Market column that for now always shows "US" for all signals. When multi-market signals are added in a future task, this column will be populated dynamically.

### Step 9.2 — Add Market column to signals table header

Find the table header row in `templates/dashboard.html` and add:
```html
<th style="padding:4px 8px; text-align:left; color:#64748b; font-size:11px;">Market</th>
```
as the first column.

### Step 9.3 — Add Market column to signals table body

In each signal row `<tr>`, add as the first `<td>`:
```html
<td style="padding:4px 8px; font-size:11px; color:#94a3b8;">
  {{ signal.data.market | default("US") | upper if signal.data else "US" }}
</td>
```

Note: currently `signal.data.market` will always be missing so it defaults to "US". Future screener outputs may include a `market` field.

- [ ] Read `templates/dashboard.html` before editing to find the exact insertion points
- [ ] Add Market column to signal table header
- [ ] Add Market cell to signal table rows

### Step 9.4 — Run full suite

- [ ] Run: `uv run pytest tests/ -v`
- [ ] Expected: no new failures

### Step 9.5 — Commit

```bash
git add templates/dashboard.html
git commit -m "feat: dashboard — add Market column to signals table"
```

- [ ] Commit

---

## Acceptance Criteria

- `uv run pytest tests/test_broker_client.py -v` → all PASS
- `uv run pytest tests/test_alpaca_client.py -v` → all PASS
- `uv run pytest tests/test_ibkr_client.py -v` → all PASS
- `uv run pytest tests/test_settings_manager.py -v` → all PASS
- `uv run pytest tests/test_universe_builder.py -v` → all PASS
- `uv run pytest tests/test_routes.py -v` → all existing tests pass + new tests pass
- `uv run pytest tests/test_pivot_monitor.py -v` → all existing + new tests pass
- `uv run pytest tests/ -v` → zero new failures introduced by this feature
- `AlpacaClient` satisfies `BrokerClient` at runtime (`isinstance(alpaca, BrokerClient)` returns True)
- `IBKRClient` satisfies `BrokerClient` at runtime
- IB Gateway not running → `ibkr.is_configured == False` → IBKR monitors silently skipped, US trading continues
- Settings with all markets disabled → `settings_manager.save()` raises `ValueError`
- Each market writes trades to `cache/<market-id>-auto_trades.json`
- `/trades` page shows all trades across all markets with Market column
- `/api/broker-status` returns `{"alpaca": bool, "ibkr": bool}`
- Dashboard signals table has Market column
