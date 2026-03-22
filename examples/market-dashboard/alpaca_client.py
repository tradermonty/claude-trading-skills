"""Alpaca trading and data client wrapper."""
from __future__ import annotations

import asyncio as _asyncio
import sys


class AlpacaClient:
    """Wraps alpaca-py TradingClient + StockHistoricalDataClient.

    Pass _trading_client / _data_client in tests to inject mocks without
    making real API calls.
    """

    def __init__(
        self,
        api_key: str,
        secret_key: str,
        paper: bool = True,
        _trading_client=None,
        _data_client=None,
    ):
        self.api_key = api_key
        self.secret_key = secret_key
        self.paper = paper
        self._trading_client = _trading_client
        self._data_client = _data_client
        self._last_fill: dict | None = None

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and self.secret_key)

    @property
    def trading_client(self):
        if self._trading_client is None:
            from alpaca.trading.client import TradingClient
            self._trading_client = TradingClient(
                api_key=self.api_key,
                secret_key=self.secret_key,
                paper=self.paper,
            )
        return self._trading_client

    @property
    def data_client(self):
        if self._data_client is None:
            from alpaca.data.historical import StockHistoricalDataClient
            self._data_client = StockHistoricalDataClient(
                api_key=self.api_key,
                secret_key=self.secret_key,
            )
        return self._data_client

    def get_account(self) -> dict:
        account = self.trading_client.get_account()
        return {
            "portfolio_value": float(account.portfolio_value),
            "buying_power": float(account.buying_power),
            "cash": float(account.cash),
        }

    def get_positions(self) -> list[dict]:
        return [
            {
                "symbol": p.symbol,
                "qty": float(p.qty),
                "market_value": float(p.market_value),
                "unrealized_pl": float(p.unrealized_pl),
                "unrealized_plpc": float(p.unrealized_plpc),
                "avg_entry_price": float(p.avg_entry_price),
                "current_price": float(p.current_price),
            }
            for p in self.trading_client.get_all_positions()
        ]

    def get_last_price(self, symbol: str) -> float:
        from alpaca.data.requests import StockLatestTradeRequest
        request = StockLatestTradeRequest(symbol_or_symbols=symbol)
        trade = self.data_client.get_stock_latest_trade(request)
        return float(trade[symbol].price)

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

    def place_bracket_order(
        self,
        symbol: str,
        qty: int,
        limit_price: float,
        stop_price: float,
        take_profit_price: float | None = None,
    ) -> dict:
        from alpaca.trading.requests import LimitOrderRequest, StopLossRequest, TakeProfitRequest
        from alpaca.trading.enums import OrderSide, TimeInForce, OrderClass
        # Alpaca requires both stop_loss AND take_profit for bracket orders.
        # Default: 2:1 risk-reward (take_profit = entry + 2 × risk).
        if take_profit_price is None:
            risk = limit_price - stop_price
            take_profit_price = round(limit_price + risk * 2, 2)
        order_data = LimitOrderRequest(
            symbol=symbol,
            qty=qty,
            side=OrderSide.BUY,
            time_in_force=TimeInForce.DAY,
            limit_price=round(limit_price, 2),
            order_class=OrderClass.BRACKET,
            stop_loss=StopLossRequest(stop_price=round(stop_price, 2)),
            take_profit=TakeProfitRequest(limit_price=round(take_profit_price, 2)),
        )
        order = self.trading_client.submit_order(order_data)
        return {
            "id": str(order.id),
            "symbol": order.symbol,
            "qty": float(order.qty),
            "limit_price": float(order.limit_price),
            "status": str(order.status),
        }

    async def start_trading_stream(self) -> None:
        """Subscribe to order fill events. Runs as a background asyncio task.

        Uses run_in_executor so the blocking public stream.run() API runs in a
        thread — avoids depending on the private _run_forever() method.
        Disconnections are logged to stderr but do not crash the server.
        """
        from alpaca.trading.stream import TradingStream
        stream = TradingStream(
            api_key=self.api_key,
            secret_key=self.secret_key,
            paper=self.paper,
        )

        @stream.subscribe_trade_updates
        async def handle_update(data):
            # _last_fill written from TradingStream's thread. Plain dict assignment
            # is atomic under CPython's GIL. A future /api/fills route reads this field.
            self._last_fill = {
                "symbol": data.order.symbol,
                "side": str(data.order.side),
                "qty": float(data.order.qty or 0),
                "event": str(data.event),
            }

        loop = _asyncio.get_running_loop()
        try:
            await loop.run_in_executor(None, stream.run)
        except Exception as e:
            print(f"[alpaca_stream] disconnected: {e}", file=sys.stderr)
