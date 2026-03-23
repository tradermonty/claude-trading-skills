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

    # Provide MagicMock-based stubs so tests can patch them and so that
    # calling them (e.g. Stock("EQNR", "SMART", "")) returns a usable mock
    # object rather than raising during unit tests.
    from unittest.mock import MagicMock as _MagicMock

    Stock = _MagicMock(name="Stock")
    LimitOrder = _MagicMock(name="LimitOrder")
    StopOrder = _MagicMock(name="StopOrder")
    MarketOrder = _MagicMock(name="MarketOrder")


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
                "market_value": 0.0,
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
        """Place a bracket order (parent limit + take-profit + stop-loss) on IBKR."""
        contract = self._make_contract(symbol)

        if take_profit_price is None:
            risk = limit_price - stop_price
            take_profit_price = round(limit_price + risk * 2, 2)

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
        stop_loss.transmit = True

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
        """Modify an existing stop order to a new stop price."""
        for trade in self._ib.trades():
            if str(trade.order.orderId) == str(order_id):
                trade.order.auxPrice = round(new_stop_price, 2)
                self._ib.placeOrder(trade.contract, trade.order)
                return {"id": order_id, "status": "modified"}
        raise ValueError(f"[ibkr_client] order {order_id} not found in open trades")

    async def subscribe_bars(self, symbols: list[str], callback) -> None:
        """Subscribe to real-time 5-second bars via ib_insync reqRealTimeBars."""
        if not self.is_configured:
            print("[ibkr_client] subscribe_bars: not connected", file=sys.stderr)
            return

        bar_lists = []
        for symbol in symbols:
            contract = self._make_contract(symbol)
            bars = self._ib.reqRealTimeBars(contract, 5, "TRADES", False)
            bar_lists.append((symbol, bars))

        def _make_handler(sym):
            def _handler(bars, has_new_bar):
                if has_new_bar and bars:
                    bar = bars[-1]
                    bar.symbol = sym
                    asyncio.ensure_future(callback(bar))
            return _handler

        for symbol, bars in bar_lists:
            bars.updateEvent += _make_handler(symbol)

        try:
            while True:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            for symbol, bars in bar_lists:
                self._ib.cancelRealTimeBars(bars)
            raise
