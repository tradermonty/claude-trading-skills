#!/usr/bin/env python3
"""
Theme Detector - ETF & Stock Metrics Scanner

Uses FMP API (preferred) with yfinance fallback for batch downloading
stock/ETF data and computing technical metrics: RSI-14, 52-week distance,
PE ratio, volume ratios.

FMP API key is optional; without it, yfinance is used exclusively.
"""

import sys
import time
from datetime import date, timedelta
from typing import Any, Optional

try:
    import numpy as np
    import pandas as pd
except ImportError:
    print("ERROR: pandas/numpy not found. Install with: pip install pandas numpy", file=sys.stderr)
    sys.exit(1)

try:
    import yfinance as yf

    HAS_YFINANCE = True
except ImportError:
    HAS_YFINANCE = False

try:
    import requests as _requests_lib

    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


# ---------------------------------------------------------------------------
# FMP endpoint definitions (R2-1: callable URL builders for stable/v3)
# ---------------------------------------------------------------------------


def _stable_quote_url(base: str, symbols_str: str, params: dict) -> tuple[str, dict]:
    """stable/quote?symbol=A,B"""
    params["symbol"] = symbols_str
    return base, params


def _v3_quote_url(base: str, symbols_str: str, params: dict) -> tuple[str, dict]:
    """api/v3/quote/A,B"""
    return f"{base}/{symbols_str}", params


def _stable_hist_url(base: str, symbols_str: str, params: dict) -> tuple[str, dict]:
    """stable/historical-price-eod/full?symbol=SYM&from=&to="""
    params["symbol"] = symbols_str
    # The /stable EOD endpoint ignores `timeseries`; convert it to a from/to
    # range (~2x calendar days to cover N trading days, +10 slack).
    days = params.pop("timeseries", None)
    as_of = params.pop("_as_of", None)
    if days is not None:
        today = date.fromisoformat(as_of) if as_of else date.today()
        params["from"] = (today - timedelta(days=int(days) * 2 + 10)).isoformat()
        params["to"] = today.isoformat()
    return base, params


def _v3_hist_url(base: str, symbols_str: str, params: dict) -> tuple[str, dict]:
    """api/v3/historical-price-full/A,B?..."""
    params.pop("_as_of", None)
    return f"{base}/{symbols_str}", params


def _normalize_eod_flat_list(data: Any, symbols_str: str) -> Any:
    """Convert a /stable historical-price-eod/full flat list to the v3 shape.

    Input  : [{"symbol": "AAPL", "date": .., "close": .., ...}, ...]
    Output : {"symbol": "AAPL", "historical": [...]}
    Non-list input (v3 dict / historicalStockList) passes through unchanged;
    returns None when no row matches the requested symbol.
    """
    if not isinstance(data, list):
        return data
    norm = symbols_str.replace("-", ".")
    rows = [
        r
        for r in data
        if isinstance(r, dict) and (r.get("symbol") or symbols_str).replace("-", ".") == norm
    ]
    if not rows:
        return None
    return {"symbol": symbols_str, "historical": rows}


_FMP_ENDPOINTS = {
    "quote": [
        ("https://financialmodelingprep.com/stable/quote", _stable_quote_url),
        ("https://financialmodelingprep.com/api/v3/quote", _v3_quote_url),
    ],
    "historical": [
        ("https://financialmodelingprep.com/stable/historical-price-eod/full", _stable_hist_url),
        ("https://financialmodelingprep.com/api/v3/historical-price-full", _v3_hist_url),
    ],
}


def _history_row_on_or_before(row: Any, as_of_date: date) -> bool:
    """Accept only well-formed dated rows that do not exceed the PIT ceiling."""
    if not isinstance(row, dict):
        return False
    raw_date = row.get("date")
    if not isinstance(raw_date, str):
        return False
    try:
        row_date = date.fromisoformat(raw_date[:10])
    except ValueError:
        return False
    return row_date <= as_of_date


def _frame_on_or_before(data: pd.DataFrame, as_of_date: date) -> pd.DataFrame:
    """Remove invalid and post-as-of rows from a provider DataFrame.

    ``Timestamp.date()`` intentionally preserves the provider row's displayed
    date for both timezone-aware and naive indexes. Numeric indexes are not
    dates and must not be silently interpreted as Unix nanoseconds.
    """
    if data is None or data.empty:
        return data
    keep: list[bool] = []
    for raw_index in data.index:
        if isinstance(raw_index, (bool, int, float, complex)):
            keep.append(False)
            continue
        try:
            timestamp = pd.Timestamp(raw_index)
        except (TypeError, ValueError):
            keep.append(False)
            continue
        keep.append(not pd.isna(timestamp) and timestamp.date() <= as_of_date)
    return data.loc[keep].copy()


class ETFScanner:
    """Scans ETFs and stocks for volume ratios and technical metrics.

    Supports FMP API (preferred) with automatic yfinance fallback.
    """

    # One symbol per request: FMP's /stable endpoints do not support
    # comma-batched symbols (that is a paid legacy feature that silently
    # returns []), so quotes/history are fetched individually.
    FMP_HIST_BATCH_SIZE = 1
    FMP_QUOTE_BATCH_SIZE = 1

    _ENDPOINT_FAILURE_THRESHOLD = 3  # disable endpoint after N consecutive failures

    def __init__(
        self,
        fmp_api_key: Optional[str] = None,
        rate_limit_sec: float = 0.3,
        as_of_date: Optional[date] = None,
    ):
        self._cache: dict[str, pd.DataFrame] = {}
        self._fmp_api_key = fmp_api_key
        self._rate_limit_sec = rate_limit_sec
        self._as_of_date = as_of_date
        self._last_request_time = 0.0
        self._fmp_quote_cache: dict[str, dict] = {}  # normalized_symbol -> quote dict
        self._stats: dict[str, dict[str, int]] = {
            "stock": {"fmp_calls": 0, "fmp_failures": 0, "yf_calls": 0, "yf_fallbacks": 0},
            "etf": {"fmp_calls": 0, "fmp_failures": 0, "yf_calls": 0, "yf_fallbacks": 0},
        }
        self._current_stats_context: str = "stock"
        # Circuit breaker: track consecutive failures per endpoint URL prefix
        self._endpoint_failures: dict[str, int] = {}
        self._disabled_endpoints: set[str] = set()

    def backend_stats(self) -> dict[str, Any]:
        """Return backend usage statistics with both flat and nested formats.

        Flat keys (backward compatible): fmp_calls, fmp_failures, yf_calls, yf_fallbacks
        Nested keys: stock.{...}, etf.{...}
        """
        flat: dict[str, int] = {}
        for key in ["fmp_calls", "fmp_failures", "yf_calls", "yf_fallbacks"]:
            flat[key] = self._stats["stock"][key] + self._stats["etf"][key]
        return {
            **flat,
            "stock": dict(self._stats["stock"]),
            "etf": dict(self._stats["etf"]),
        }

    # -------------------------------------------------------------------
    # Symbol normalization (R2-4)
    # -------------------------------------------------------------------
    @staticmethod
    def _normalize_symbol_for_fmp(symbol: str) -> str:
        """Normalize symbol for FMP API (e.g., BRK-B -> BRK.B)."""
        return symbol.replace("-", ".")

    # -------------------------------------------------------------------
    # FMP infrastructure (R2-1: callable URL builder)
    # -------------------------------------------------------------------
    def _fmp_rate_limit(self):
        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < self._rate_limit_sec:
            time.sleep(self._rate_limit_sec - elapsed)
        self._last_request_time = time.time()

    def _fmp_request(
        self, endpoint_key: str, symbols_str: str, extra_params: Optional[dict] = None
    ) -> Optional[Any]:
        """Try each endpoint (stable -> v3) with circuit breaker.

        Endpoints that fail consecutively are disabled to avoid wasting
        API calls and triggering rate limits from the provider.

        Args:
            endpoint_key: "quote" or "historical"
            symbols_str: comma-separated symbols (already normalized)
            extra_params: e.g. {"timeseries": 20}

        Returns:
            Parsed JSON or None on all failures.
        """
        if not HAS_REQUESTS or not self._fmp_api_key:
            return None

        params = {}
        if extra_params:
            params.update(extra_params)

        ctx = self._current_stats_context
        for base_url, url_builder in _FMP_ENDPOINTS[endpoint_key]:
            # Circuit breaker: skip endpoints with too many consecutive failures
            if base_url in self._disabled_endpoints:
                continue

            url, final_params = url_builder(base_url, symbols_str, dict(params))
            self._fmp_rate_limit()
            self._stats[ctx]["fmp_calls"] += 1
            try:
                resp = _requests_lib.get(
                    url, params=final_params, headers={"apikey": self._fmp_api_key}, timeout=15
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if endpoint_key == "historical":
                        # /stable returns a flat OHLCV list; reshape to the v3
                        # {"symbol", "historical"} dict the parser expects.
                        data = _normalize_eod_flat_list(data, symbols_str)
                    if data:
                        # Reset failure count on success
                        self._endpoint_failures[base_url] = 0
                        return data
            except Exception:
                pass

            self._stats[ctx]["fmp_failures"] += 1
            failures = self._endpoint_failures.get(base_url, 0) + 1
            self._endpoint_failures[base_url] = failures
            if failures >= self._ENDPOINT_FAILURE_THRESHOLD:
                self._disabled_endpoints.add(base_url)

        return None

    # -------------------------------------------------------------------
    # FMP quote fetch (R2-4: normalized cache)
    # -------------------------------------------------------------------
    def _fetch_fmp_quotes(self, symbols: list[str]) -> dict[str, dict]:
        """Batch fetch quotes. Returns {original_symbol: quote_dict}."""
        result: dict[str, dict] = {}
        uncached = []
        for s in symbols:
            norm = self._normalize_symbol_for_fmp(s)
            if norm not in self._fmp_quote_cache:
                uncached.append(s)

        for i in range(0, len(uncached), self.FMP_QUOTE_BATCH_SIZE):
            batch = uncached[i : i + self.FMP_QUOTE_BATCH_SIZE]
            normalized = [self._normalize_symbol_for_fmp(s) for s in batch]
            data = self._fmp_request("quote", ",".join(normalized))
            if isinstance(data, list):
                for item in data:
                    sym = self._normalize_symbol_for_fmp(item.get("symbol", ""))
                    self._fmp_quote_cache[sym] = item

        # Per-symbol retry for missing: try original symbol if different
        for s in uncached:
            norm = self._normalize_symbol_for_fmp(s)
            if norm in self._fmp_quote_cache:
                continue
            if norm != s:
                data = self._fmp_request("quote", s)
                if isinstance(data, list):
                    for item in data:
                        sym = self._normalize_symbol_for_fmp(item.get("symbol", ""))
                        self._fmp_quote_cache[sym] = item

        for s in symbols:
            norm = self._normalize_symbol_for_fmp(s)
            cached = self._fmp_quote_cache.get(norm)
            if cached:
                result[s] = cached
        return result

    # -------------------------------------------------------------------
    # FMP historical fetch (R2-2: per-symbol retry)
    # -------------------------------------------------------------------
    def _fetch_fmp_historical(
        self, symbols: list[str], timeseries: int = 20
    ) -> dict[str, list[dict]]:
        """Batch fetch historical prices with per-symbol retry on partial failure."""
        result: dict[str, list[dict]] = {}
        extra = {"timeseries": timeseries}
        if self._as_of_date is not None:
            extra["_as_of"] = self._as_of_date.isoformat()

        # Phase 1: batch fetch
        for i in range(0, len(symbols), self.FMP_HIST_BATCH_SIZE):
            batch = symbols[i : i + self.FMP_HIST_BATCH_SIZE]
            normalized = [self._normalize_symbol_for_fmp(s) for s in batch]
            data = self._fmp_request("historical", ",".join(normalized), extra)
            if data is None:
                continue
            self._parse_historical_response(data, result)

        # Phase 2: per-symbol retry for missing symbols
        # Try normalized form first, then original if different
        missing = [s for s in symbols if self._normalize_symbol_for_fmp(s) not in result]
        for s in missing:
            norm = self._normalize_symbol_for_fmp(s)
            data = self._fmp_request("historical", norm, extra)
            if data is not None:
                self._parse_historical_response(data, result)
                continue
            # Retry with original symbol if normalization changed it
            if norm != s:
                data = self._fmp_request("historical", s, extra)
                if data is not None:
                    self._parse_historical_response(data, result)

        # Map normalized keys back to original symbols
        mapped: dict[str, list[dict]] = {}
        for s in symbols:
            norm = self._normalize_symbol_for_fmp(s)
            if norm in result:
                rows = result[norm]
                if self._as_of_date is not None:
                    rows = [row for row in rows if _history_row_on_or_before(row, self._as_of_date)]
                if rows:
                    mapped[s] = rows
        return mapped

    def _parse_historical_response(self, data: Any, result: dict) -> None:
        """Parse FMP historical response (batch or single format).

        Keys in result are always normalized (e.g., BRK.B not BRK-B).
        """
        if isinstance(data, dict):
            if "historicalStockList" in data:
                for entry in data["historicalStockList"]:
                    sym = entry.get("symbol", "")
                    if sym and "historical" in entry:
                        result[self._normalize_symbol_for_fmp(sym)] = entry["historical"]
            elif "historical" in data:
                sym = data.get("symbol", "")
                if sym:
                    result[self._normalize_symbol_for_fmp(sym)] = data["historical"]

    # -------------------------------------------------------------------
    # FMP-based stock metrics
    # -------------------------------------------------------------------
    def _batch_stock_metrics_fmp(self, symbols: list[str]) -> list[dict]:
        """Compute stock metrics using FMP quote + historical data."""
        quotes = self._fetch_fmp_quotes(symbols)
        historical = self._fetch_fmp_historical(symbols, timeseries=20)

        results = []
        for s in symbols:
            entry = {
                "symbol": s,
                "rsi_14": None,
                "dist_from_52w_high": None,
                "dist_from_52w_low": None,
                "pe_ratio": None,
            }

            # PE and 52w from quote
            q = quotes.get(s, {})
            pe = q.get("pe")
            if pe is not None:
                entry["pe_ratio"] = pe

            price = q.get("price")
            year_high = q.get("yearHigh")
            year_low = q.get("yearLow")
            if price and year_high and year_high > 0:
                entry["dist_from_52w_high"] = round((year_high - price) / year_high, 4)
            if price and year_low is not None and price > 0:
                entry["dist_from_52w_low"] = round((price - year_low) / price, 4)

            # RSI from historical close
            hist = historical.get(s, [])
            if hist:
                closes = [d.get("close") for d in hist if d.get("close") is not None]
                if len(closes) >= 15:
                    # Historical comes newest-first from FMP; reverse for RSI
                    prices_series = pd.Series(list(reversed(closes)))
                    entry["rsi_14"] = self._calculate_rsi(prices_series, period=14)

            results.append(entry)
        return results

    # -------------------------------------------------------------------
    # FMP-based ETF volume ratios
    # -------------------------------------------------------------------
    def _batch_etf_volume_ratios_fmp(self, symbols: list[str]) -> dict[str, dict]:
        """Compute ETF volume ratios using FMP historical data."""
        historical = self._fetch_fmp_historical(symbols, timeseries=60)

        result: dict[str, dict] = {}
        for s in symbols:
            entry = {"symbol": s, "vol_20d": None, "vol_60d": None, "vol_ratio": None}
            hist = historical.get(s, [])
            volumes = [d.get("volume") for d in hist if d.get("volume") is not None]

            if len(volumes) >= 20:
                # Historical comes newest-first
                vol_20d = float(np.mean(volumes[:20]))
                vol_60d = (
                    float(np.mean(volumes[:60])) if len(volumes) >= 60 else float(np.mean(volumes))
                )
                entry["vol_20d"] = vol_20d
                entry["vol_60d"] = vol_60d
                entry["vol_ratio"] = vol_20d / vol_60d if vol_60d > 0 else None

            result[s] = entry
        return result

    # -------------------------------------------------------------------
    # yfinance-based methods (original implementations)
    # -------------------------------------------------------------------
    def _get_etf_volume_ratio_yfinance(self, symbol: str) -> dict:
        """Get 20-day / 60-day average volume ratio via yfinance."""
        result = {"symbol": symbol, "vol_20d": None, "vol_60d": None, "vol_ratio": None}

        if not HAS_YFINANCE:
            print("WARNING: yfinance not installed.", file=sys.stderr)
            return result

        try:
            data = self._get_cached(symbol, period="6mo")
            if data is None or data.empty or "Volume" not in data.columns:
                return result

            volume = data["Volume"].dropna()
            if len(volume) < 20:
                return result

            vol_20d = float(volume.tail(20).mean())
            vol_60d = float(volume.tail(60).mean()) if len(volume) >= 60 else float(volume.mean())

            result["vol_20d"] = vol_20d
            result["vol_60d"] = vol_60d
            result["vol_ratio"] = vol_20d / vol_60d if vol_60d > 0 else None

        except Exception as e:
            print(f"WARNING: Volume ratio failed for {symbol}: {e}", file=sys.stderr)

        return result

    def _batch_stock_metrics_yfinance(self, symbols: list[str]) -> list[dict]:
        """Batch-download stock data and compute metrics via yfinance."""
        if not HAS_YFINANCE:
            print("WARNING: yfinance not installed.", file=sys.stderr)
            return [
                {
                    "symbol": s,
                    "rsi_14": None,
                    "dist_from_52w_high": None,
                    "dist_from_52w_low": None,
                    "pe_ratio": None,
                }
                for s in symbols
            ]

        try:
            kwargs = {
                "group_by": "ticker",
                "threads": True,
                "progress": False,
            }
            if self._as_of_date is None:
                kwargs["period"] = "1y"
            else:
                kwargs["start"] = (self._as_of_date - timedelta(days=370)).isoformat()
                kwargs["end"] = (self._as_of_date + timedelta(days=1)).isoformat()
            data = yf.download(symbols, **kwargs)
            if self._as_of_date is not None:
                data = _frame_on_or_before(data, self._as_of_date)
        except Exception as e:
            print(f"WARNING: Batch download failed: {e}", file=sys.stderr)
            return [
                {
                    "symbol": s,
                    "rsi_14": None,
                    "dist_from_52w_high": None,
                    "dist_from_52w_low": None,
                    "pe_ratio": None,
                }
                for s in symbols
            ]

        results = []
        for symbol in symbols:
            entry = {
                "symbol": symbol,
                "rsi_14": None,
                "dist_from_52w_high": None,
                "dist_from_52w_low": None,
                "pe_ratio": None,
            }
            try:
                if len(symbols) == 1:
                    sym_data = data
                else:
                    sym_data = data[symbol]

                if sym_data is None or sym_data.empty:
                    results.append(entry)
                    continue

                close = sym_data["Close"].dropna()
                high = sym_data["High"].dropna()
                low = sym_data["Low"].dropna()

                if len(close) < 2:
                    results.append(entry)
                    continue

                entry["rsi_14"] = self._calculate_rsi(close, period=14)

                distances = self._calculate_52w_distances(close, high, low)
                entry["dist_from_52w_high"] = distances["dist_from_52w_high"]
                entry["dist_from_52w_low"] = distances["dist_from_52w_low"]

                entry["pe_ratio"] = self._get_pe_ratio(symbol)

            except Exception as e:
                print(f"WARNING: Metrics failed for {symbol}: {e}", file=sys.stderr)

            results.append(entry)

        return results

    # -------------------------------------------------------------------
    # Public methods (FMP -> yfinance symbol-level fallback)
    # -------------------------------------------------------------------
    def get_etf_volume_ratio(self, symbol: str) -> dict:
        """Get 20-day / 60-day average volume ratio for an ETF.

        Args:
            symbol: Ticker symbol (e.g., "XLK")

        Returns:
            Dict with keys: symbol, vol_20d, vol_60d, vol_ratio.
            Values are None if data unavailable.
        """
        if self._fmp_api_key and HAS_REQUESTS:
            fmp_result = self._batch_etf_volume_ratios_fmp([symbol])
            data = fmp_result.get(symbol, {})
            if data.get("vol_20d") is not None:
                return data

        return self._get_etf_volume_ratio_yfinance(symbol)

    def batch_etf_volume_ratios(self, symbols: list[str]) -> dict[str, dict]:
        """Batch fetch ETF volume ratios with FMP -> yfinance fallback.

        Args:
            symbols: List of ETF ticker symbols

        Returns:
            Dict mapping symbol -> {symbol, vol_20d, vol_60d, vol_ratio}
        """
        if not symbols:
            return {}

        self._current_stats_context = "etf"
        # Phase 1: Try FMP batch
        fmp_results: dict[str, dict] = {}
        fmp_attempted = self._fmp_api_key and HAS_REQUESTS
        if fmp_attempted:
            fmp_results = self._batch_etf_volume_ratios_fmp(symbols)

        # Phase 2: yfinance for missing/empty
        result: dict[str, dict] = {}
        missing_for_yf = []
        for sym in symbols:
            fmp_data = fmp_results.get(sym, {})
            if fmp_data.get("vol_20d") is not None:
                result[sym] = fmp_data
            else:
                missing_for_yf.append(sym)

        if missing_for_yf:
            if fmp_attempted:
                self._stats["etf"]["yf_fallbacks"] += 1
            for sym in missing_for_yf:
                self._stats["etf"]["yf_calls"] += 1
                result[sym] = self._get_etf_volume_ratio_yfinance(sym)

        return result

    def batch_stock_metrics(self, symbols: list[str]) -> list[dict]:
        """Batch compute stock metrics with FMP -> yfinance symbol-level fallback.

        Args:
            symbols: List of ticker symbols

        Returns:
            List of dicts with keys: symbol, rsi_14, dist_from_52w_high,
            dist_from_52w_low, pe_ratio. Values are None if unavailable.
        """
        if not symbols:
            return []

        self._current_stats_context = "stock"
        # Phase 1: FMP results (accept any non-empty result)
        fmp_results: dict[str, dict] = {}
        fmp_attempted = self._fmp_api_key and HAS_REQUESTS
        metric_keys = ["pe_ratio", "rsi_14", "dist_from_52w_high", "dist_from_52w_low"]
        if fmp_attempted:
            fmp_list = self._batch_stock_metrics_fmp(symbols)
            for m in fmp_list:
                sym = m["symbol"]
                has_any = any(m.get(k) is not None for k in metric_keys)
                if has_any:
                    fmp_results[sym] = m

        # Phase 2: yfinance for symbols missing RSI (not just missing entirely)
        missing_rsi = [
            s for s in symbols if s not in fmp_results or fmp_results[s].get("rsi_14") is None
        ]
        yf_results: dict[str, dict] = {}
        if missing_rsi:
            if fmp_attempted:
                self._stats["stock"]["yf_fallbacks"] += 1
            yf_list = self._batch_stock_metrics_yfinance(missing_rsi)
            self._stats["stock"]["yf_calls"] += 1
            for m in yf_list:
                sym = m["symbol"]
                if sym in fmp_results:
                    # Field-level merge: fill only None fields from yfinance
                    for k, v in m.items():
                        if k != "symbol" and fmp_results[sym].get(k) is None and v is not None:
                            fmp_results[sym][k] = v
                else:
                    yf_results[sym] = m

        # Merge: FMP takes priority, yfinance fills gaps
        results = []
        for s in symbols:
            if s in fmp_results:
                results.append(fmp_results[s])
            elif s in yf_results:
                results.append(yf_results[s])
            else:
                results.append(
                    {
                        "symbol": s,
                        "rsi_14": None,
                        "dist_from_52w_high": None,
                        "dist_from_52w_low": None,
                        "pe_ratio": None,
                    }
                )
        return results

    # -------------------------------------------------------------------
    # Shared utilities (unchanged)
    # -------------------------------------------------------------------
    @staticmethod
    def _calculate_rsi(prices: pd.Series, period: int = 14) -> Optional[float]:
        """Calculate RSI using Wilder's smoothing method."""
        if prices is None or len(prices) < period + 1:
            return None

        deltas = prices.diff()

        gains = deltas.where(deltas > 0, 0.0)
        losses = (-deltas).where(deltas < 0, 0.0)

        first_avg_gain = gains.iloc[1 : period + 1].mean()
        first_avg_loss = losses.iloc[1 : period + 1].mean()

        avg_gain = first_avg_gain
        avg_loss = first_avg_loss

        for i in range(period + 1, len(prices)):
            avg_gain = (avg_gain * (period - 1) + gains.iloc[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses.iloc[i]) / period

        if avg_loss == 0:
            return 100.0

        rs = avg_gain / avg_loss
        rsi = 100.0 - (100.0 / (1.0 + rs))
        return round(rsi, 2)

    @staticmethod
    def _calculate_52w_distances(close: pd.Series, high: pd.Series, low: pd.Series) -> dict:
        """Calculate distance from 52-week high and low."""
        result = {"dist_from_52w_high": None, "dist_from_52w_low": None}

        if close.empty:
            return result

        current = float(close.iloc[-1])
        if current <= 0:
            return result

        high_52w = float(high.max())
        low_52w = float(low.min())

        if high_52w > 0:
            result["dist_from_52w_high"] = round((high_52w - current) / high_52w, 4)

        if low_52w >= 0:
            result["dist_from_52w_low"] = (
                round((current - low_52w) / current, 4) if current > 0 else None
            )

        return result

    def _get_pe_ratio(self, symbol: str) -> Optional[float]:
        """Get trailing P/E ratio for a symbol via yfinance info."""
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            pe = info.get("trailingPE")
            if pe is not None:
                return round(float(pe), 2)
        except Exception:
            pass
        return None

    def _get_cached(self, symbol: str, period: str = "6mo") -> Optional[pd.DataFrame]:
        """Get cached download or fetch new data."""
        cache_key = f"{symbol}_{period}_{self._as_of_date or 'live'}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        try:
            if self._as_of_date is None:
                data = yf.download(symbol, period=period, progress=False)
            else:
                lookback_days = 190 if period == "6mo" else 370
                data = yf.download(
                    symbol,
                    start=(self._as_of_date - timedelta(days=lookback_days)).isoformat(),
                    end=(self._as_of_date + timedelta(days=1)).isoformat(),
                    progress=False,
                )
            if self._as_of_date is not None:
                data = _frame_on_or_before(data, self._as_of_date)
            self._cache[cache_key] = data
            return data
        except Exception as e:
            print(f"WARNING: Download failed for {symbol}: {e}", file=sys.stderr)
            return None
