#!/usr/bin/env python3
"""
yfinance Client for VCP Screener

Drop-in replacement for fmp_client.py using yfinance (Yahoo Finance).
No API key required. Implements the identical interface as FMPClient.

Install dependencies:
    pip install yfinance pandas lxml
"""

import sys
import time
from typing import Optional

try:
    import yfinance as yf
except ImportError:
    print("ERROR: yfinance not found. Install with: pip install yfinance", file=sys.stderr)
    sys.exit(1)

try:
    import pandas as pd
except ImportError:
    print("ERROR: pandas not found. Install with: pip install pandas", file=sys.stderr)
    sys.exit(1)


class YFinanceClient:
    """
    yfinance-based drop-in replacement for FMPClient.

    No API key required. Fetches data from Yahoo Finance via the yfinance library.
    Implements the same interface as FMPClient so screen_vcp.py needs no other changes.
    """

    def __init__(self, api_key: Optional[str] = None):
        # api_key accepted but ignored — kept for interface compatibility with FMPClient
        self.cache: dict = {}
        self.api_calls_made: int = 0
        self.rate_limit_reached: bool = False

    # ------------------------------------------------------------------
    # S&P 500 Constituents
    # ------------------------------------------------------------------

    def get_sp500_constituents(self) -> Optional[list[dict]]:
        """Fetch S&P 500 constituent list from Wikipedia.

        Returns:
            List of dicts with keys: symbol, name, sector, subSector
            or None on failure.
        """
        cache_key = "sp500_constituents"
        if cache_key in self.cache:
            return self.cache[cache_key]

        try:
            import io
            import requests as _req
            resp = _req.get(
                "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
                timeout=30,
                verify=False,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            resp.raise_for_status()
            tables = pd.read_html(io.StringIO(resp.text), attrs={"id": "constituents"})
            df = tables[0]
            result = []
            for _, row in df.iterrows():
                # Yahoo Finance uses "-" where some sources use "." (e.g. BRK-B)
                symbol = str(row["Symbol"]).replace(".", "-")
                result.append(
                    {
                        "symbol": symbol,
                        "name": str(row["Security"]),
                        "sector": str(row["GICS Sector"]),
                        "subSector": str(row["GICS Sub-Industry"]),
                    }
                )
            self.api_calls_made += 1
            self.cache[cache_key] = result
            return result
        except Exception as e:
            print(f"ERROR: Failed to fetch S&P 500 constituents: {e}", file=sys.stderr)
            return None

    def get_nasdaq100_constituents(self) -> Optional[list[dict]]:
        """Fetch Nasdaq-100 constituent list from Wikipedia.

        Returns:
            List of dicts with keys: symbol, name, sector, subSector
            or None on failure.
        """
        cache_key = "nasdaq100_constituents"
        if cache_key in self.cache:
            return self.cache[cache_key]

        try:
            import io
            import requests as _req
            time.sleep(1)  # avoid rate-limiting when called after another Wikipedia fetch
            resp = _req.get(
                "https://en.wikipedia.org/wiki/Nasdaq-100",
                timeout=30,
                verify=False,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            resp.raise_for_status()
            # The Nasdaq-100 constituents table has id="constituents"
            tables = pd.read_html(io.StringIO(resp.text), attrs={"id": "constituents"})
            df = tables[0]
            result = []
            for _, row in df.iterrows():
                symbol = str(row["Ticker"]).replace(".", "-")
                result.append(
                    {
                        "symbol": symbol,
                        "name": str(row["Company"]),
                        "sector": str(row.get("GICS Sector", "Unknown")),
                        "subSector": str(row.get("GICS Sub-Industry", "Unknown")),
                    }
                )
            self.api_calls_made += 1
            self.cache[cache_key] = result
            return result
        except Exception as e:
            print(f"WARN: Wikipedia fetch failed ({e}), using static Nasdaq-100 fallback list", file=sys.stderr)
            return self._nasdaq100_fallback()

    # fmt: off
    _NASDAQ100_TICKERS = [
        "AAPL", "MSFT", "NVDA", "AMZN", "META", "TSLA", "GOOGL", "GOOG", "AVGO",
        "COST", "NFLX", "TMUS", "AMD", "PEP", "LIN", "CSCO", "ADBE", "QCOM", "TXN",
        "AMGN", "INTU", "CMCSA", "ISRG", "AMAT", "BKNG", "HON", "MU", "VRTX", "ADP",
        "PANW", "GILD", "ADI", "REGN", "SBUX", "LRCX", "MDLZ", "KLAC", "MRVL", "INTC",
        "SNPS", "CDNS", "CEG", "PYPL", "CTAS", "ASML", "MELI", "MAR", "FTNT", "ABNB",
        "CRWD", "ORLY", "PCAR", "WDAY", "DASH", "TTD", "MNST", "ROST", "CPRT", "PAYX",
        "DXCM", "FAST", "BKR", "VRSK", "ON", "GEHC", "EXC", "IDXX", "ODFL", "CTSH",
        "MCHP", "KDP", "GFS", "TEAM", "CDW", "DDOG", "ZS", "BIIB", "XEL", "EA",
        "FANG", "ILMN", "WBD", "ANSS", "CCEP", "TTWO", "DLTR", "ZM", "SIRI", "RIVN",
        "LCID", "PDD", "SMCI", "MDB", "ENPH", "ALGN", "NXPI", "AEP", "TSCO", "EBAY",
    ]
    # fmt: on

    def _nasdaq100_fallback(self) -> list[dict]:
        """Return a static Nasdaq-100 list when Wikipedia is unavailable."""
        return [{"symbol": s, "name": s, "sector": "Unknown", "subSector": "Unknown"}
                for s in self._NASDAQ100_TICKERS]

    # ------------------------------------------------------------------
    # Historical Prices
    # ------------------------------------------------------------------

    def get_historical_prices(self, symbol: str, days: int = 365) -> Optional[dict]:
        """Fetch historical daily OHLCV data.

        Returns FMP-compatible format:
            {"symbol": str, "historical": [{"date", "open", "high", "low",
                                             "close", "adjClose", "volume"}, ...]}
        Data is sorted most-recent-first, matching FMP's default ordering.
        """
        cache_key = f"prices_{symbol}_{days}"
        if cache_key in self.cache:
            return self.cache[cache_key]

        try:
            # Choose the smallest yfinance period that covers the requested days
            if days <= 90:
                period = "6mo"
            elif days <= 260:
                period = "1y"
            elif days <= 365:
                period = "1y"
            else:
                period = "2y"

            time.sleep(0.05)  # gentle throttle
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period=period, auto_adjust=True)

            if hist is None or hist.empty:
                return None

            self.api_calls_made += 1

            # Build FMP-style list, most-recent-first
            historical = []
            for date, row in hist.iloc[::-1].iterrows():
                if pd.isna(row["Close"]):
                    continue
                historical.append(
                    {
                        "date": date.strftime("%Y-%m-%d"),
                        "open": round(float(row["Open"]), 4),
                        "high": round(float(row["High"]), 4),
                        "low": round(float(row["Low"]), 4),
                        "close": round(float(row["Close"]), 4),
                        "adjClose": round(float(row["Close"]), 4),
                        "volume": int(row["Volume"]) if not pd.isna(row["Volume"]) else 0,
                    }
                )

            # Trim to the requested window
            historical = historical[:days]

            result = {"symbol": symbol, "historical": historical}
            # Cache under multiple day-keys so sibling calls hit the cache
            for d in (120, 260, 365):
                self.cache[f"prices_{symbol}_{d}"] = result
            return result

        except Exception as e:
            print(f"WARN: Failed to fetch history for {symbol}: {e}", file=sys.stderr)
            return None

    # ------------------------------------------------------------------
    # Quotes
    # ------------------------------------------------------------------

    def get_quote(self, symbols: str) -> Optional[list[dict]]:
        """Fetch quote data for one or more symbols (comma-separated string).

        Returns FMP-compatible list of quote dicts.
        """
        cache_key = f"quote_{symbols}"
        if cache_key in self.cache:
            return self.cache[cache_key]

        symbol_list = [s.strip() for s in symbols.split(",")]
        results = []
        for symbol in symbol_list:
            q = self._get_single_quote(symbol)
            if q:
                results.append(q)

        if results:
            self.cache[cache_key] = results
        return results if results else None

    def _get_single_quote(self, symbol: str) -> Optional[dict]:
        """Build a quote dict for one symbol from its historical data."""
        cache_key = f"single_quote_{symbol}"
        if cache_key in self.cache:
            return self.cache[cache_key]

        hist_data = self.get_historical_prices(symbol, days=260)
        if not hist_data or not hist_data.get("historical"):
            return None

        hist = hist_data["historical"]  # most-recent-first
        closes = [h["close"] for h in hist]
        volumes = [h["volume"] for h in hist]
        highs = [h["high"] for h in hist]
        lows = [h["low"] for h in hist]

        if not closes:
            return None

        current_price = closes[0]
        year_high = max(highs[:252]) if len(highs) >= 252 else max(highs)
        year_low = min(lows[:252]) if len(lows) >= 252 else min(lows)
        avg_volume = int(sum(volumes[:50]) / min(50, len(volumes)))

        result = {
            "symbol": symbol,
            "name": symbol,      # name/sector populated lazily in get_batch_quotes
            "price": current_price,
            "yearHigh": year_high,
            "yearLow": year_low,
            "avgVolume": avg_volume,
            "marketCap": 0,
            "sector": "Unknown",
        }
        self.cache[cache_key] = result
        return result

    # ------------------------------------------------------------------
    # Batch Operations
    # ------------------------------------------------------------------

    def get_batch_quotes(self, symbols: list[str]) -> dict[str, dict]:
        """Fetch quotes for many symbols using a single yfinance bulk download.

        Returns dict keyed by symbol.
        """
        if not symbols:
            return {}

        # Split into already-cached and missing
        results: dict[str, dict] = {}
        missing = []
        for sym in symbols:
            ck = f"single_quote_{sym}"
            if ck in self.cache:
                results[sym] = self.cache[ck]
            else:
                missing.append(sym)

        if not missing:
            return results

        try:
            self.api_calls_made += 1
            raw = yf.download(
                tickers=missing,
                period="1y",
                auto_adjust=True,
                progress=False,
                threads=True,
            )

            if raw is None or raw.empty:
                return results

            is_multi = isinstance(raw.columns, pd.MultiIndex)

            for symbol in missing:
                try:
                    if is_multi:
                        level_values = raw.columns.get_level_values(1)
                        if symbol not in level_values:
                            continue
                        sym_data = raw.xs(symbol, axis=1, level=1).dropna(how="all")
                    else:
                        # Single-symbol download — columns are flat
                        sym_data = raw.dropna(how="all")

                    if sym_data.empty:
                        continue

                    closes = sym_data["Close"].dropna()
                    volumes = sym_data["Volume"].dropna()
                    highs = sym_data["High"].dropna()
                    lows = sym_data["Low"].dropna()

                    if closes.empty:
                        continue

                    current_price = float(closes.iloc[-1])
                    year_high = float(highs.max())
                    year_low = float(lows.min())
                    avg_volume = int(volumes.tail(50).mean())

                    # Build and cache the historical list while we have the data
                    historical = []
                    for date in reversed(sym_data.index):
                        row = sym_data.loc[date]
                        if pd.isna(row["Close"]):
                            continue
                        historical.append(
                            {
                                "date": pd.Timestamp(date).strftime("%Y-%m-%d"),
                                "open": round(float(row["Open"]), 4),
                                "high": round(float(row["High"]), 4),
                                "low": round(float(row["Low"]), 4),
                                "close": round(float(row["Close"]), 4),
                                "adjClose": round(float(row["Close"]), 4),
                                "volume": int(row["Volume"])
                                if not pd.isna(row["Volume"])
                                else 0,
                            }
                        )

                    hist_result = {"symbol": symbol, "historical": historical}
                    for d in (120, 260, 365):
                        self.cache[f"prices_{symbol}_{d}"] = hist_result

                    quote = {
                        "symbol": symbol,
                        "name": symbol,
                        "price": current_price,
                        "yearHigh": year_high,
                        "yearLow": year_low,
                        "avgVolume": avg_volume,
                        "marketCap": 0,
                        "sector": "Unknown",
                    }
                    self.cache[f"single_quote_{symbol}"] = quote
                    results[symbol] = quote

                except Exception as e:
                    print(f"WARN: Failed to process {symbol}: {e}", file=sys.stderr)
                    continue

        except Exception as e:
            print(f"ERROR: Batch download failed: {e}", file=sys.stderr)

        return results

    def get_batch_historical(self, symbols: list[str], days: int = 260) -> dict[str, list[dict]]:
        """Fetch historical prices for multiple symbols.

        Returns dict keyed by symbol, values are FMP-style historical lists.
        """
        results: dict[str, list[dict]] = {}

        # Serve from cache where possible
        missing = []
        for symbol in symbols:
            ck = f"prices_{symbol}_{days}"
            if ck in self.cache:
                data = self.cache[ck]
                if data and "historical" in data:
                    results[symbol] = data["historical"]
            else:
                missing.append(symbol)

        # Fetch remaining one by one (cache will be populated for siblings)
        for symbol in missing:
            data = self.get_historical_prices(symbol, days=days)
            if data and "historical" in data:
                results[symbol] = data["historical"]

        return results

    # ------------------------------------------------------------------
    # Utilities (identical to FMPClient)
    # ------------------------------------------------------------------

    def calculate_sma(self, prices: list[float], period: int) -> float:
        """Calculate SMA from a list of prices (most-recent-first)."""
        if len(prices) < period:
            return sum(prices) / len(prices)
        return sum(prices[:period]) / period

    def get_api_stats(self) -> dict:
        return {
            "cache_entries": len(self.cache),
            "api_calls_made": self.api_calls_made,
            "rate_limit_reached": False,
        }
