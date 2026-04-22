"""Alpaca paper trading client wrapper.

Thin adapter over alpaca-py to keep the rest of the agent decoupled from
broker specifics. All methods are safe to call when the market is closed —
they return empty data instead of raising.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal

import pandas as pd
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest, StockLatestQuoteRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import (
    ClosePositionRequest,
    GetOrdersRequest,
    MarketOrderRequest,
)
from dotenv import load_dotenv

load_dotenv(override=False)


@dataclass
class AccountSnapshot:
    equity: float
    cash: float
    buying_power: float
    portfolio_value: float
    long_market_value: float
    short_market_value: float
    initial_margin: float
    maintenance_margin: float
    status: str
    pattern_day_trader: bool
    trading_blocked: bool


@dataclass
class PositionSnapshot:
    symbol: str
    qty: float                      # signed: negative = short
    avg_entry_price: float
    current_price: float
    market_value: float
    unrealized_pl: float
    unrealized_plpc: float
    side: str                       # long | short


class AlpacaPaperClient:
    def __init__(self) -> None:
        key = os.environ.get("ALPACA_API_KEY")
        secret = os.environ.get("ALPACA_SECRET_KEY")
        if not key or not secret:
            raise RuntimeError(
                "ALPACA_API_KEY and ALPACA_SECRET_KEY must be set in environment (.env)."
            )
        self.trading = TradingClient(key, secret, paper=True)
        self.data = StockHistoricalDataClient(key, secret)

    # ---------------------- account ----------------------

    def account(self) -> AccountSnapshot:
        a = self.trading.get_account()
        return AccountSnapshot(
            equity=float(a.equity or 0),
            cash=float(a.cash or 0),
            buying_power=float(a.buying_power or 0),
            portfolio_value=float(a.portfolio_value or 0),
            long_market_value=float(a.long_market_value or 0),
            short_market_value=float(a.short_market_value or 0),
            initial_margin=float(a.initial_margin or 0),
            maintenance_margin=float(a.maintenance_margin or 0),
            status=str(a.status),
            pattern_day_trader=bool(a.pattern_day_trader),
            trading_blocked=bool(a.trading_blocked),
        )

    # ---------------------- positions ----------------------

    def positions(self) -> list[PositionSnapshot]:
        out: list[PositionSnapshot] = []
        for p in self.trading.get_all_positions():
            out.append(PositionSnapshot(
                symbol=p.symbol,
                qty=float(p.qty or 0),
                avg_entry_price=float(p.avg_entry_price or 0),
                current_price=float(p.current_price or 0),
                market_value=float(p.market_value or 0),
                unrealized_pl=float(p.unrealized_pl or 0),
                unrealized_plpc=float(p.unrealized_plpc or 0),
                side=str(p.side).lower().replace("positionside.", ""),
            ))
        return out

    def position(self, symbol: str) -> PositionSnapshot | None:
        for p in self.positions():
            if p.symbol.upper() == symbol.upper():
                return p
        return None

    def close_position(self, symbol: str) -> None:
        try:
            self.trading.close_position(symbol)
        except Exception:
            pass  # already closed / no position

    def close_all_positions(self, cancel_orders: bool = True) -> None:
        try:
            self.trading.close_all_positions(cancel_orders=cancel_orders)
        except Exception:
            pass

    # ---------------------- orders ----------------------

    def market_order(
        self,
        symbol: str,
        qty: float,
        side: Literal["buy", "sell"],
        extended_hours: bool = False,
    ) -> dict:
        req = MarketOrderRequest(
            symbol=symbol,
            qty=qty,
            side=OrderSide.BUY if side == "buy" else OrderSide.SELL,
            time_in_force=TimeInForce.DAY,
            extended_hours=extended_hours,
        )
        order = self.trading.submit_order(req)
        return {
            "id": str(order.id),
            "symbol": order.symbol,
            "qty": float(order.qty or 0),
            "side": str(order.side).lower().replace("orderside.", ""),
            "status": str(order.status),
            "filled_avg_price": float(order.filled_avg_price or 0),
        }

    def recent_orders(self, limit: int = 50) -> list[dict]:
        req = GetOrdersRequest(status="all", limit=limit)
        orders = self.trading.get_orders(filter=req)
        return [{
            "id": str(o.id),
            "symbol": o.symbol,
            "qty": float(o.qty or 0),
            "filled_qty": float(o.filled_qty or 0),
            "side": str(o.side).lower().replace("orderside.", ""),
            "status": str(o.status),
            "filled_avg_price": float(o.filled_avg_price or 0),
            "submitted_at": o.submitted_at.isoformat() if o.submitted_at else None,
        } for o in orders]

    def cancel_all_orders(self) -> None:
        try:
            self.trading.cancel_orders()
        except Exception:
            pass

    # ---------------------- market data ----------------------

    def latest_price(self, symbol: str) -> float | None:
        try:
            q = self.data.get_stock_latest_quote(
                StockLatestQuoteRequest(symbol_or_symbols=symbol)
            )
            quote = q[symbol]
            mid = (float(quote.ask_price) + float(quote.bid_price)) / 2
            return mid if mid > 0 else float(quote.ask_price or quote.bid_price or 0) or None
        except Exception:
            return None

    def bars(self, symbol: str, timeframe: str = "5Min", lookback_minutes: int = 240) -> pd.DataFrame:
        """Return recent bars as a DataFrame indexed by timestamp."""
        tf_map = {
            "1Min": TimeFrame.Minute,
            "5Min": TimeFrame(5, TimeFrameUnit.Minute),
            "15Min": TimeFrame(15, TimeFrameUnit.Minute),
            "1Hour": TimeFrame.Hour,
            "1Day": TimeFrame.Day,
        }
        tf = tf_map.get(timeframe, TimeFrame(5, TimeFrameUnit.Minute))
        end = datetime.now(timezone.utc) - timedelta(minutes=16)  # IEX feed has ~15min delay
        start = end - timedelta(minutes=lookback_minutes)
        try:
            req = StockBarsRequest(
                symbol_or_symbols=symbol,
                timeframe=tf,
                start=start,
                end=end,
            )
            bars = self.data.get_stock_bars(req).df
            if bars is None or bars.empty:
                return pd.DataFrame()
            # drop multi-index if present
            if isinstance(bars.index, pd.MultiIndex):
                bars = bars.xs(symbol, level=0) if symbol in bars.index.get_level_values(0) else bars
            return bars
        except Exception:
            return pd.DataFrame()

    # ---------------------- clock ----------------------

    def is_market_open(self) -> bool:
        try:
            return bool(self.trading.get_clock().is_open)
        except Exception:
            return False

    def market_clock(self) -> dict:
        try:
            c = self.trading.get_clock()
            return {
                "is_open": bool(c.is_open),
                "next_open": c.next_open.isoformat() if c.next_open else None,
                "next_close": c.next_close.isoformat() if c.next_close else None,
                "timestamp": c.timestamp.isoformat() if c.timestamp else None,
            }
        except Exception as e:
            return {"is_open": False, "error": str(e)}
