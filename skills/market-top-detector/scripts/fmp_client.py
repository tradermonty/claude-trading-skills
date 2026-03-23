#!/usr/bin/env python3
"""
Alpaca + FRED Client for Market Top Detector

Replaces FMP API:
- OHLCV data → Alpaca Market Data API
- VIX / VIX3M spot → FRED (VIXCLS / VXVCLS series)
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


def _fetch_fred_series(series_id: str) -> Optional[float]:
    """Return the most recent non-NaN value from a FRED series."""
    try:
        from fredapi import Fred
        fred = Fred(api_key=os.environ.get("FRED_API_KEY", ""))
        series = fred.get_series(series_id)
        series = series.dropna()
        if series.empty:
            return None
        return float(series.iloc[-1])
    except Exception as e:
        print(f"WARNING: FRED fetch failed for {series_id}: {e}")
        return None


def _alpaca_symbol(symbol: str) -> str:
    """Map index symbols to tradable ETF proxies."""
    mapping = {"^GSPC": "SPY", "^VIX": None, "^VIX3M": None}
    return mapping.get(symbol, symbol)


def _bars_to_historical(alpaca_symbol: str, original_symbol: str, df, days: int) -> dict:
    """Convert Alpaca DataFrame to FMP-compatible historical list (most-recent first)."""
    if hasattr(df.index, "levels"):
        try:
            df = df.xs(alpaca_symbol, level="symbol")
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
    return {"symbol": original_symbol, "historical": historical[:days]}


class FMPClient:
    """Drop-in replacement: Alpaca + FRED backed client with same interface."""

    def __init__(self, api_key: Optional[str] = None):
        alpaca_api_key = os.environ.get("ALPACA_API_KEY", "")
        alpaca_secret = os.environ.get("ALPACA_SECRET_KEY", "")
        if not alpaca_api_key or not alpaca_secret:
            raise ValueError(
                "ALPACA_API_KEY and ALPACA_SECRET_KEY are required."
            )
        self._client = _get_alpaca_client()
        self._cache: dict = {}
        self._api_calls_made = 0

    def get_historical_prices(self, symbol: str, days: int = 260) -> Optional[dict]:
        """Fetch daily OHLCV via Alpaca. Maps ^GSPC → SPY."""
        alpaca_sym = _alpaca_symbol(symbol)
        if alpaca_sym is None:
            return None  # VIX has no OHLCV on Alpaca
        cache_key = f"hist_{alpaca_sym}_{days}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        start = (datetime.date.today() - datetime.timedelta(days=int(days * 1.6) + 10)).isoformat()
        request = StockBarsRequest(
            symbol_or_symbols=alpaca_sym,
            timeframe=TimeFrame.Day,
            start=start,
        )
        try:
            bars = self._client.get_stock_bars(request)
            self._api_calls_made += 1
        except Exception as e:
            print(f"WARNING: Alpaca bars failed for {alpaca_sym}: {e}")
            return None

        df = bars.df
        if df.empty:
            return None

        result = _bars_to_historical(alpaca_sym, symbol, df, days)
        self._cache[cache_key] = result
        return result

    def get_quote(self, symbol: str) -> Optional[list[dict]]:
        """
        Build quote dict from latest bar + 252-day range.
        VIX and VIX3M spot prices fetched from FRED.
        """
        # VIX: FRED series VIXCLS
        if symbol == "^VIX":
            price = _fetch_fred_series("VIXCLS")
            if price is None:
                return None
            return [{"symbol": "^VIX", "price": price, "yearHigh": price, "yearLow": price, "volume": 0}]

        # VIX3M: FRED series VXVCLS
        if symbol == "^VIX3M":
            price = _fetch_fred_series("VXVCLS")
            if price is None:
                return None
            return [{"symbol": "^VIX3M", "price": price, "yearHigh": price, "yearLow": price, "volume": 0}]

        alpaca_sym = _alpaca_symbol(symbol)
        if alpaca_sym is None:
            return None

        cache_key = f"quote_{alpaca_sym}"
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

    def get_batch_quotes(self, symbols: list[str]) -> dict[str, dict]:
        """Fetch quotes for a list of ETF symbols (batch via Alpaca)."""
        # Filter out non-Alpaca symbols
        alpaca_symbols = [s for s in symbols if _alpaca_symbol(s) not in (None,)]
        if not alpaca_symbols:
            return {}

        # Map back from Alpaca symbol to original if needed
        sym_map = {_alpaca_symbol(s): s for s in alpaca_symbols}
        alpaca_list = list(sym_map.keys())

        start = (datetime.date.today() - datetime.timedelta(days=400)).isoformat()
        request = StockBarsRequest(
            symbol_or_symbols=alpaca_list,
            timeframe=TimeFrame.Day,
            start=start,
        )
        try:
            bars = self._client.get_stock_bars(request)
            self._api_calls_made += 1
        except Exception as e:
            print(f"WARNING: Alpaca batch quotes failed: {e}")
            return {}

        df = bars.df
        if df.empty:
            return {}

        results = {}
        for alpaca_sym in alpaca_list:
            orig_sym = sym_map[alpaca_sym]
            try:
                sym_df = df.xs(alpaca_sym, level="symbol").sort_index(ascending=False)
                if sym_df.empty:
                    continue
                latest = sym_df.iloc[0]
                year_high = float(sym_df["high"].max())
                year_low = float(sym_df["low"].min())
                results[orig_sym] = {
                    "symbol": orig_sym,
                    "price": round(float(latest["close"]), 4),
                    "yearHigh": round(year_high, 4),
                    "yearLow": round(year_low, 4),
                    "volume": int(latest["volume"]),
                }
            except (KeyError, IndexError):
                continue
        return results

    def get_batch_historical(self, symbols: list[str], days: int = 60) -> dict[str, list[dict]]:
        """Fetch historical bars for multiple ETF symbols (single Alpaca batch request)."""
        alpaca_list = [_alpaca_symbol(s) for s in symbols if _alpaca_symbol(s) is not None]
        sym_map = {_alpaca_symbol(s): s for s in symbols if _alpaca_symbol(s) is not None}
        if not alpaca_list:
            return {}

        start = (datetime.date.today() - datetime.timedelta(days=int(days * 1.6) + 10)).isoformat()
        request = StockBarsRequest(
            symbol_or_symbols=alpaca_list,
            timeframe=TimeFrame.Day,
            start=start,
        )
        try:
            bars = self._client.get_stock_bars(request)
            self._api_calls_made += 1
        except Exception as e:
            print(f"WARNING: Alpaca batch historical failed: {e}")
            return {}

        df = bars.df
        if df.empty:
            return {}

        results = {}
        for alpaca_sym in alpaca_list:
            orig_sym = sym_map[alpaca_sym]
            try:
                sym_df = df.xs(alpaca_sym, level="symbol").sort_index(ascending=False)
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
                results[orig_sym] = historical[:days]
            except (KeyError, IndexError):
                continue
        return results

    def get_vix_term_structure(self) -> Optional[dict]:
        """Compare VIX (VIXCLS) vs VIX3M (VXVCLS) from FRED."""
        vix = _fetch_fred_series("VIXCLS")
        vix3m = _fetch_fred_series("VXVCLS")

        if vix is None or vix3m is None or vix3m <= 0:
            return None

        ratio = vix / vix3m
        if ratio < 0.85:
            classification = "steep_contango"
        elif ratio < 0.95:
            classification = "contango"
        elif ratio <= 1.05:
            classification = "flat"
        else:
            classification = "backwardation"

        return {
            "vix": round(vix, 2),
            "vix3m": round(vix3m, 2),
            "ratio": round(ratio, 3),
            "classification": classification,
        }

    def get_api_stats(self) -> dict:
        return {
            "cache_entries": len(self._cache),
            "api_calls_made": self._api_calls_made,
            "rate_limit_reached": False,
        }
