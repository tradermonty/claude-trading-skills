#!/usr/bin/env python3
"""
Theme Detector - ETF & Stock Metrics Scanner

Uses yfinance for batch downloading stock/ETF data and computing
technical metrics: RSI-14, 52-week distance, volume ratios.

No API key required.
"""

import sys
from typing import Dict, List, Optional

try:
    import pandas as pd
    import numpy as np
except ImportError:
    print("ERROR: pandas/numpy not found. Install with: pip install pandas numpy",
          file=sys.stderr)
    sys.exit(1)

try:
    import yfinance as yf
    HAS_YFINANCE = True
except ImportError:
    HAS_YFINANCE = False


class ETFScanner:
    """Scans ETFs and stocks for volume ratios and technical metrics."""

    def __init__(self):
        self._cache: Dict[str, pd.DataFrame] = {}

    def get_etf_volume_ratio(self, symbol: str) -> Dict:
        """Get 20-day / 60-day average volume ratio for an ETF.

        Args:
            symbol: Ticker symbol (e.g., "XLK")

        Returns:
            Dict with keys: symbol, vol_20d, vol_60d, vol_ratio.
            Values are None if data unavailable.
        """
        result = {"symbol": symbol, "vol_20d": None, "vol_60d": None,
                  "vol_ratio": None}

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
            print(f"WARNING: Volume ratio failed for {symbol}: {e}",
                  file=sys.stderr)

        return result

    def batch_stock_metrics(self, symbols: List[str]) -> List[Dict]:
        """Batch-download stock data and compute metrics for each symbol.

        Uses yf.download with group_by="ticker" for efficiency.

        Args:
            symbols: List of ticker symbols

        Returns:
            List of dicts with keys: symbol, rsi_14, dist_from_52w_high,
            dist_from_52w_low, pe_ratio. Values are None if unavailable.
        """
        if not symbols:
            return []

        if not HAS_YFINANCE:
            print("WARNING: yfinance not installed.", file=sys.stderr)
            return [{"symbol": s, "rsi_14": None, "dist_from_52w_high": None,
                     "dist_from_52w_low": None, "pe_ratio": None}
                    for s in symbols]

        # Batch download 1 year of data for 52-week calculations
        try:
            data = yf.download(
                symbols,
                period="1y",
                group_by="ticker",
                threads=True,
                progress=False,
            )
        except Exception as e:
            print(f"WARNING: Batch download failed: {e}", file=sys.stderr)
            return [{"symbol": s, "rsi_14": None, "dist_from_52w_high": None,
                     "dist_from_52w_low": None, "pe_ratio": None}
                    for s in symbols]

        results = []
        for symbol in symbols:
            entry = {"symbol": symbol, "rsi_14": None,
                     "dist_from_52w_high": None, "dist_from_52w_low": None,
                     "pe_ratio": None}
            try:
                # Extract per-symbol data from MultiIndex DataFrame
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

                # RSI
                entry["rsi_14"] = self._calculate_rsi(close, period=14)

                # 52-week distances
                distances = self._calculate_52w_distances(close, high, low)
                entry["dist_from_52w_high"] = distances["dist_from_52w_high"]
                entry["dist_from_52w_low"] = distances["dist_from_52w_low"]

                # P/E ratio from yfinance info (cached)
                entry["pe_ratio"] = self._get_pe_ratio(symbol)

            except Exception as e:
                print(f"WARNING: Metrics failed for {symbol}: {e}",
                      file=sys.stderr)

            results.append(entry)

        return results

    @staticmethod
    def _calculate_rsi(prices: pd.Series, period: int = 14) -> Optional[float]:
        """Calculate RSI using Wilder's smoothing method.

        Args:
            prices: Series of closing prices
            period: RSI period (default 14)

        Returns:
            RSI value (0-100) or None if insufficient data
        """
        if prices is None or len(prices) < period + 1:
            return None

        deltas = prices.diff()

        gains = deltas.where(deltas > 0, 0.0)
        losses = (-deltas).where(deltas < 0, 0.0)

        # First average: simple mean of first 'period' values
        first_avg_gain = gains.iloc[1:period + 1].mean()
        first_avg_loss = losses.iloc[1:period + 1].mean()

        # Wilder's smoothing for subsequent values
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
    def _calculate_52w_distances(close: pd.Series,
                                  high: pd.Series,
                                  low: pd.Series) -> Dict:
        """Calculate distance from 52-week high and low.

        Args:
            close: Closing prices
            high: High prices
            low: Low prices

        Returns:
            Dict with dist_from_52w_high and dist_from_52w_low.
            - dist_from_52w_high: (high52 - current) / high52
              0.0 at the high, positive below
            - dist_from_52w_low: (current - low52) / current
              0.0 at the low, small when near low
        """
        result = {"dist_from_52w_high": None, "dist_from_52w_low": None}

        if close.empty:
            return result

        current = float(close.iloc[-1])
        if current <= 0:
            return result

        high_52w = float(high.max())
        low_52w = float(low.min())

        if high_52w > 0:
            result["dist_from_52w_high"] = round(
                (high_52w - current) / high_52w, 4
            )

        if low_52w >= 0:
            result["dist_from_52w_low"] = round(
                (current - low_52w) / current, 4
            ) if current > 0 else None

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
        cache_key = f"{symbol}_{period}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        try:
            data = yf.download(symbol, period=period, progress=False)
            self._cache[cache_key] = data
            return data
        except Exception as e:
            print(f"WARNING: Download failed for {symbol}: {e}",
                  file=sys.stderr)
            return None
