#!/usr/bin/env python3
"""
Alpaca Data Client for FTD Detector

Replaces FMP API with Alpaca Market Data API (free tier, no call limits).
Uses SPY as S&P 500 proxy (^GSPC not available on Alpaca).
"""

import os
import datetime
from typing import Optional

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame


class FMPClient:
    """Drop-in replacement: Alpaca-backed client with same interface as FMP version."""

    def __init__(self, api_key: Optional[str] = None):
        # api_key param kept for CLI backward compat; Alpaca uses env vars
        alpaca_api_key = os.environ.get("ALPACA_API_KEY", "")
        alpaca_secret = os.environ.get("ALPACA_SECRET_KEY", "")
        if not alpaca_api_key or not alpaca_secret:
            raise ValueError(
                "ALPACA_API_KEY and ALPACA_SECRET_KEY are required. "
                "Set them as environment variables."
            )
        self._client = StockHistoricalDataClient(
            api_key=alpaca_api_key,
            secret_key=alpaca_secret,
        )
        self._cache: dict = {}
        self._api_calls_made = 0

    def get_historical_prices(self, symbol: str, days: int = 80) -> Optional[dict]:
        """Fetch daily OHLCV. Maps ^GSPC -> SPY. Returns FMP-compatible dict."""
        alpaca_symbol = "SPY" if symbol in ("^GSPC", "SPX") else symbol
        cache_key = f"hist_{alpaca_symbol}_{days}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        start = (datetime.date.today() - datetime.timedelta(days=int(days * 1.6) + 10)).isoformat()
        request = StockBarsRequest(
            symbol_or_symbols=alpaca_symbol,
            timeframe=TimeFrame.Day,
            start=start,
        )
        try:
            bars = self._client.get_stock_bars(request)
            self._api_calls_made += 1
        except Exception as e:
            print(f"WARNING: Alpaca bars failed for {alpaca_symbol}: {e}")
            return None

        df = bars.df
        if df.empty:
            return None

        # Flatten MultiIndex (symbol, timestamp) → timestamp only for single symbol
        if hasattr(df.index, "levels"):
            df = df.xs(alpaca_symbol, level="symbol") if alpaca_symbol in df.index.get_level_values("symbol") else df
        df = df.sort_index(ascending=False)  # most-recent first

        historical = []
        for ts, row in df.iterrows():
            historical.append({
                "date": str(ts.date()) if hasattr(ts, "date") else str(ts)[:10],
                "open": round(float(row["open"]), 4),
                "high": round(float(row["high"]), 4),
                "low": round(float(row["low"]), 4),
                "close": round(float(row["close"]), 4),
                "volume": int(row["volume"]),
            })

        result = {"symbol": symbol, "historical": historical[:days]}
        self._cache[cache_key] = result
        return result

    def get_quote(self, symbol: str) -> Optional[list[dict]]:
        """Build a quote dict from the latest bar + 252-day high/low."""
        alpaca_symbol = "SPY" if symbol in ("^GSPC", "SPX") else symbol
        cache_key = f"quote_{alpaca_symbol}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        hist = self.get_historical_prices(symbol, days=252)
        if not hist or not hist.get("historical"):
            return None

        bars = hist["historical"]
        latest = bars[0]
        year_high = max(b["high"] for b in bars)
        year_low = min(b["low"] for b in bars)

        result = [{
            "symbol": symbol,
            "price": latest["close"],
            "yearHigh": year_high,
            "yearLow": year_low,
            "volume": latest["volume"],
        }]
        self._cache[cache_key] = result
        return result

    def get_api_stats(self) -> dict:
        return {
            "cache_entries": len(self._cache),
            "api_calls_made": self._api_calls_made,
            "rate_limit_reached": False,
        }
