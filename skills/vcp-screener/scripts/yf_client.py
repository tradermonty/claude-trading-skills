#!/usr/bin/env python3
"""
Yahoo Finance client for VCP Screener bulk data download.

Key design decisions
--------------------
* yf.download() is ONE function call but internally dispatches multiple HTTP
  connections (one per ticker or small batch, using a thread pool). A network
  failure can therefore affect individual symbols while leaving others intact,
  which is why per-symbol retry and skipped-symbol tracking are necessary.
* auto_adjust=False is set explicitly so that both Close (unadjusted) and
  Adj Close (split/dividend adjusted) columns are preserved in the output.
* All quote fields (price, yearHigh, yearLow, avgVolume) are derived from the
  bulk OHLCV download — no per-ticker yf.Ticker().info calls in the scan path.
* marketCap is not available from OHLCV; it is returned as None and the
  existing report_generator renders it as "N/A".
"""

from __future__ import annotations

import sys
import time
from statistics import mean
from typing import Optional

try:
    import pandas as pd
    import yfinance as yf
except ImportError as exc:
    print(
        f"ERROR: Required library not found ({exc}). "
        "Install with: pip install yfinance pandas",
        file=sys.stderr,
    )
    sys.exit(1)

# Bounded retry: 3 attempts, exponential backoff
RETRY_DELAYS: list[int] = [2, 4, 8]
MAX_RETRIES: int = len(RETRY_DELAYS)

# Rolling volume windows used for derived quote dict
AVG_VOLUME_DAYS: int = 20


def _df_to_hist(df: pd.DataFrame, symbol: str) -> list[dict]:
    """Convert a single-symbol yfinance DataFrame to most-recent-first list of dicts.

    Preserves both Close (unadjusted) and Adj Close (dividend/split adjusted).
    Returns [] when the DataFrame is empty or all-NaN for the required columns.

    yf.download() with group_by='ticker' (used in all list-based calls) returns
    a MultiIndex where level-0 = ticker, level-1 = field, regardless of whether
    the tickers argument has 1 or N elements.
    The only exception is a bare string call without group_by, which yields
    level-0 = field, level-1 = ticker; both cases are handled below.
    """
    if df is None or df.empty:
        return []

    # Normalise MultiIndex columns to a flat per-symbol DataFrame
    if isinstance(df.columns, pd.MultiIndex):
        level0 = set(df.columns.get_level_values(0))
        level1 = set(df.columns.get_level_values(1))

        if symbol in level0:
            # group_by='ticker' layout: ticker at level-0, field at level-1
            df = df[symbol]
        elif symbol in level1:
            # Bare-string download layout: field at level-0, ticker at level-1
            df = df.xs(symbol, axis=1, level=1)
        else:
            return []

    required = {"Open", "High", "Low", "Close", "Volume"}
    if not required.issubset(df.columns):
        return []

    # Drop rows where Close is NaN (incomplete bars)
    df = df.dropna(subset=["Close"])
    if df.empty:
        return []

    rows = []
    for ts, row in df.iterrows():
        date_str = ts.strftime("%Y-%m-%d") if hasattr(ts, "strftime") else str(ts)[:10]
        adj_close = float(row["Adj Close"]) if "Adj Close" in row and pd.notna(row["Adj Close"]) else float(row["Close"])
        rows.append({
            "date":     date_str,
            "open":     float(row["Open"])   if pd.notna(row["Open"])   else None,
            "high":     float(row["High"])   if pd.notna(row["High"])   else None,
            "low":      float(row["Low"])    if pd.notna(row["Low"])    else None,
            "close":    float(row["Close"])  if pd.notna(row["Close"])  else None,
            "adjClose": adj_close,
            "volume":   int(row["Volume"])   if pd.notna(row["Volume"]) else 0,
        })

    # Return most-recent-first (yfinance returns oldest-first)
    rows.reverse()
    return rows


def _derive_quote(symbol: str, hist: list[dict]) -> dict:
    """Derive pre-filter quote fields from OHLCV history (no extra HTTP calls).

    Fields returned match what pre_filter_stock() and analyze_stock() expect:
      price, yearHigh, yearLow, avgVolume, volume, marketCap (None)
    """
    if not hist:
        return {}

    price = hist[0]["close"] or 0.0
    year_high = max((h["high"] for h in hist if h.get("high")), default=0.0)
    year_low = min((h["low"] for h in hist if h.get("low") and h["low"] > 0), default=0.0)
    recent_vols = [h["volume"] for h in hist[:AVG_VOLUME_DAYS] if h.get("volume")]
    avg_volume = int(mean(recent_vols)) if recent_vols else 0

    return {
        "symbol":    symbol,
        "price":     price,
        "yearHigh":  year_high,
        "yearLow":   year_low,
        "avgVolume": avg_volume,
        "volume":    hist[0].get("volume", 0),
        "marketCap": None,  # not available from OHLCV; report shows N/A
        "name":      symbol,
    }


class YFinanceClient:
    """Bulk yfinance downloader with retry, cache, and skipped-symbol reporting.

    Interface mirrors FMPClient's data methods so screen_vcp.py can route to
    either provider with minimal branching.
    """

    def __init__(self) -> None:
        # Cache keyed by (frozenset(symbols), period); value = {sym: hist_list}
        self._cache: dict[tuple, dict[str, list[dict]]] = {}
        self._skipped: list[dict] = []
        self._retries_attempted: int = 0
        self._symbols_requested: int = 0
        self._symbols_downloaded: int = 0
        self._cache_hits: int = 0

    # ──────────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────────

    def bulk_download(
        self,
        symbols: list[str],
        period: str = "1y",
    ) -> dict[str, list[dict]]:
        """Download OHLCV for all symbols in one yf.download() call.

        yf.download() is one function call but internally fires multiple HTTP
        connections. Symbols that return empty data are retried individually
        with exponential backoff; those that remain empty after MAX_RETRIES
        are logged in get_skipped_symbols().

        auto_adjust=False is set explicitly to preserve both Close and Adj Close.

        Returns {symbol: [most-recent-first hist dicts]}.
        """
        cache_key = (frozenset(symbols), period)
        if cache_key in self._cache:
            self._cache_hits += 1
            return self._cache[cache_key]

        self._symbols_requested += len(symbols)

        result = self._download_bulk(symbols, period)

        # Identify missing symbols after the initial bulk call
        missing = [s for s in symbols if not result.get(s)]
        if missing:
            result.update(self._retry_missing(missing, period))

        # Log anything still missing as skipped
        for sym in symbols:
            if not result.get(sym):
                self._skipped.append({
                    "symbol":         sym,
                    "http_status":    0,
                    "error_category": "yf_download_failed",
                    "endpoint":       "yfinance_bulk",
                })
            else:
                self._symbols_downloaded += 1

        self._cache[cache_key] = result
        return result

    def get_batch_quotes(self, symbols: list[str], period: str = "1y") -> dict[str, dict]:
        """Return derived quote dicts for all symbols.

        Triggers a bulk download if not already cached. Symbols with no data
        are silently absent from the returned dict (recorded in skipped list).
        """
        hist_map = self.bulk_download(symbols, period=period)
        quotes = {}
        for sym, hist in hist_map.items():
            if hist:
                quotes[sym] = _derive_quote(sym, hist)
        return quotes

    def get_historical_prices(self, symbol: str, period: str = "1y") -> Optional[dict]:
        """Return v3-compatible dict for a single symbol, using the bulk cache if warm.

        Returns {"symbol": sym, "historical": [most-recent-first dicts]} or None.
        """
        # Check cache for any bulk download that included this symbol
        for (syms, p), hist_map in self._cache.items():
            if symbol in syms and p == period and symbol in hist_map:
                hist = hist_map[symbol]
                return {"symbol": symbol, "historical": hist} if hist else None

        # Fall back to individual download
        hist_map = self.bulk_download([symbol], period=period)
        hist = hist_map.get(symbol, [])
        return {"symbol": symbol, "historical": hist} if hist else None

    def get_skipped_symbols(self) -> list[dict]:
        """Return a copy of the per-symbol failure log.

        Each entry: {"symbol": str, "http_status": int,
                     "error_category": str, "endpoint": str}
        Matches the format of FMPClient.get_quote_failures().
        """
        return list(self._skipped)

    def get_provider_stats(self) -> dict:
        """Return download statistics for the summary block."""
        return {
            "provider":           "yfinance",
            "symbols_requested":  self._symbols_requested,
            "symbols_downloaded": self._symbols_downloaded,
            "symbols_skipped":    len(self._skipped),
            "retries_attempted":  self._retries_attempted,
            "cache_hits":         self._cache_hits,
        }

    # ──────────────────────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────────────────────

    def _download_bulk(self, symbols: list[str], period: str) -> dict[str, list[dict]]:
        """Single yf.download() call; parse result into {sym: hist_list}."""
        try:
            raw = yf.download(
                tickers=symbols,
                period=period,
                interval="1d",
                auto_adjust=False,   # explicit: preserve Close AND Adj Close
                progress=False,
                group_by="ticker",
                threads=True,
            )
        except Exception as exc:
            print(f"WARNING: yf.download() raised {type(exc).__name__}: {exc}", file=sys.stderr)
            return {}

        if raw is None or raw.empty:
            return {}

        result: dict[str, list[dict]] = {}

        if len(symbols) == 1:
            # Single-symbol list with group_by='ticker': MultiIndex, ticker at level-0.
            # _df_to_hist handles level-0 extraction; just pass raw as-is.
            sym = symbols[0]
            result[sym] = _df_to_hist(raw, sym)
        else:
            # Multi-ticker with group_by='ticker': MultiIndex, ticker at level-0,
            # field at level-1. Use get_level_values(0) to enumerate tickers.
            tickers_in_df = set()
            if isinstance(raw.columns, pd.MultiIndex):
                tickers_in_df = set(raw.columns.get_level_values(0))
            for sym in symbols:
                if sym in tickers_in_df:
                    result[sym] = _df_to_hist(raw, sym)

        return result

    def _retry_missing(self, missing: list[str], period: str) -> dict[str, list[dict]]:
        """Retry each missing symbol individually with exponential backoff."""
        recovered: dict[str, list[dict]] = {}
        for sym in missing:
            for attempt, delay in enumerate(RETRY_DELAYS):
                self._retries_attempted += 1
                print(
                    f"  Retry {attempt + 1}/{MAX_RETRIES} for {sym} "
                    f"(waiting {delay}s)...",
                    file=sys.stderr,
                )
                time.sleep(delay)
                batch = self._download_bulk([sym], period)
                if batch.get(sym):
                    recovered[sym] = batch[sym]
                    break
        return recovered
