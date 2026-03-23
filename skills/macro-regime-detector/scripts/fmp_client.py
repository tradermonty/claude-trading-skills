#!/usr/bin/env python3
"""
Alpaca + FRED Client for Macro Regime Detector

Replaces FMP API:
- ETF OHLCV → Alpaca Market Data API
- Treasury rates (2Y/10Y yield curve) → FRED (DGS2, DGS10)
"""

import os
import datetime
from typing import Optional

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame


def _get_alpaca_client() -> StockHistoricalDataClient:
    return StockHistoricalDataClient(
        api_key=os.environ.get("ALPACA_API_KEY", ""),
        secret_key=os.environ.get("ALPACA_SECRET_KEY", ""),
    )


class FMPClient:
    """Drop-in replacement: Alpaca + FRED backed client with same interface."""

    def __init__(self, api_key: Optional[str] = None):
        alpaca_api_key = os.environ.get("ALPACA_API_KEY", "")
        alpaca_secret = os.environ.get("ALPACA_SECRET_KEY", "")
        if not alpaca_api_key or not alpaca_secret:
            raise ValueError(
                "ALPACA_API_KEY and ALPACA_SECRET_KEY are required."
            )
        self._alpaca = _get_alpaca_client()
        self._cache: dict = {}
        self._api_calls_made = 0

    def get_historical_prices(self, symbol: str, days: int = 600) -> Optional[dict]:
        """Fetch daily OHLCV via Alpaca (most-recent first, FMP-compatible format)."""
        cache_key = f"hist_{symbol}_{days}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        start = (datetime.date.today() - datetime.timedelta(days=int(days * 1.6) + 10)).isoformat()
        request = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=TimeFrame.Day,
            start=start,
        )
        try:
            bars = self._alpaca.get_stock_bars(request)
            self._api_calls_made += 1
        except Exception as e:
            print(f"WARNING: Alpaca bars failed for {symbol}: {e}")
            return None

        df = bars.df
        if df.empty:
            return None

        # Flatten MultiIndex
        if hasattr(df.index, "levels"):
            try:
                df = df.xs(symbol, level="symbol")
            except KeyError:
                pass
        df = df.sort_index(ascending=False)

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

    def get_batch_historical(self, symbols: list[str], days: int = 600) -> dict[str, list[dict]]:
        """Fetch historical bars for multiple symbols (single Alpaca batch request)."""
        cache_key = f"batch_{','.join(sorted(symbols))}_{days}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        start = (datetime.date.today() - datetime.timedelta(days=int(days * 1.6) + 10)).isoformat()
        request = StockBarsRequest(
            symbol_or_symbols=symbols,
            timeframe=TimeFrame.Day,
            start=start,
        )
        try:
            bars = self._alpaca.get_stock_bars(request)
            self._api_calls_made += 1
        except Exception as e:
            print(f"WARNING: Alpaca batch fetch failed: {e}")
            return {}

        df = bars.df
        if df.empty:
            return {}

        results = {}
        for symbol in symbols:
            try:
                sym_df = df.xs(symbol, level="symbol").sort_index(ascending=False)
                historical = []
                for ts, row in sym_df.iterrows():
                    historical.append({
                        "date": str(ts.date()) if hasattr(ts, "date") else str(ts)[:10],
                        "open": round(float(row["open"]), 4),
                        "high": round(float(row["high"]), 4),
                        "low": round(float(row["low"]), 4),
                        "close": round(float(row["close"]), 4),
                        "volume": int(row["volume"]),
                    })
                results[symbol] = historical[:days]
            except (KeyError, IndexError):
                results[symbol] = []
        self._cache[cache_key] = results
        return results

    def get_treasury_rates(self, days: int = 600) -> Optional[list[dict]]:
        """
        Fetch 2Y and 10Y Treasury yields from FRED (DGS2, DGS10).

        Returns list of dicts (most-recent first) matching FMP format:
        {"date": "YYYY-MM-DD", "year2": float, "year10": float}
        """
        cache_key = f"treasury_{days}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        try:
            from fredapi import Fred
            fred = Fred(api_key=os.environ.get("FRED_API_KEY", ""))
            yield_2y = fred.get_series("DGS2").dropna()
            yield_10y = fred.get_series("DGS10").dropna()
        except Exception as e:
            print(f"WARNING: FRED treasury fetch failed: {e}")
            return None

        # Align on common dates
        import pandas as pd
        combined = pd.DataFrame({"year2": yield_2y, "year10": yield_10y}).dropna()
        combined = combined.sort_index(ascending=False).head(days)

        rates = []
        for date_idx, row in combined.iterrows():
            rates.append({
                "date": str(date_idx.date()) if hasattr(date_idx, "date") else str(date_idx)[:10],
                "year2": round(float(row["year2"]), 4),
                "year10": round(float(row["year10"]), 4),
            })

        self._cache[cache_key] = rates
        return rates

    def get_api_stats(self) -> dict:
        return {
            "cache_entries": len(self._cache),
            "api_calls_made": self._api_calls_made,
            "rate_limit_reached": False,
        }
