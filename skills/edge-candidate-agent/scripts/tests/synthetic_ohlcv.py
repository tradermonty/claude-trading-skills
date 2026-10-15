"""Deterministic synthetic OHLCV builders for edge-candidate-agent tests."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

END_DATE = "2026-02-20"
FILLER_SYMBOLS = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF", "GGG", "HHH"]


def _bars(
    symbol: str,
    dates: pd.DatetimeIndex,
    closes: np.ndarray,
    volumes: np.ndarray,
    rng: np.random.Generator,
) -> list[dict[str, Any]]:
    rows = []
    prev = closes[0]
    for ts, close, vol in zip(dates, closes, volumes):
        open_ = prev * (1 + rng.normal(0, 0.001))
        high = max(open_, close) * 1.004
        low = min(open_, close) * 0.996
        rows.append(
            {
                "symbol": symbol,
                "timestamp": ts,
                "open": float(open_),
                "high": float(high),
                "low": float(low),
                "close": float(close),
                "volume": float(vol),
            }
        )
        prev = close
    return rows


def _walk(rng: np.random.Generator, n: int, start: float, drift: float, vol: float) -> np.ndarray:
    rets = rng.normal(drift, vol, n)
    return start * np.exp(np.cumsum(rets))


def build_market(n_days: int = 280, seed: int = 7) -> pd.DataFrame:
    """Build a universe with a breakout, a gap-up and a panic-reversal on the last day."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(end=END_DATE, periods=n_days, tz="UTC")
    rows: list[dict[str, Any]] = []

    def vols(base: float = 2_000_000.0) -> np.ndarray:
        return base * (1 + rng.normal(0, 0.05, n_days)).clip(0.5, 1.5)

    # Strong uptrend leader: breaks out above its 20d high on the final day.
    brk = _walk(rng, n_days, 50.0, 0.003, 0.004)
    brk[-1] = brk[-2] * 1.07
    v = vols()
    v[-1] *= 3.0
    rows += _bars("BRK", dates, brk, v, rng)

    # Gap-up name: modest uptrend, final-day gap above prior close with strong close.
    gap = _walk(rng, n_days, 80.0, 0.0012, 0.006)
    gap_bars = _bars("GAPPER", dates, gap, vols(), rng)
    gap_bars[-1]["open"] = gap[-2] * 1.065
    gap_bars[-1]["close"] = gap[-2] * 1.08
    gap_bars[-1]["high"] = gap[-2] * 1.081
    gap_bars[-1]["low"] = gap[-2] * 1.064
    gap_bars[-1]["volume"] = 2_000_000.0 * 3.0
    rows += gap_bars

    # Panic reversal: steady name, -10% on the final day with heavy volume.
    pan = _walk(rng, n_days, 120.0, 0.0008, 0.006)
    pan[-1] = pan[-2] * 0.90
    v = vols()
    v[-1] *= 3.5
    rows += _bars("PANIC", dates, pan, v, rng)

    for sym in FILLER_SYMBOLS:
        closes = _walk(rng, n_days, 60.0, 0.0004, 0.008)
        rows += _bars(sym, dates, closes, vols(), rng)

    spy = _walk(rng, n_days, 400.0, 0.0005, 0.005)
    rows += _bars("SPY", dates, spy, vols(30_000_000.0), rng)

    return pd.DataFrame(rows)


def build_seasonal_history(years: int = 9, seed: int = 11) -> pd.DataFrame:
    """Long history where SEAS rallies every February; used for calendar anomalies."""
    rng = np.random.default_rng(seed)
    end = pd.Timestamp(END_DATE, tz="UTC")
    dates = pd.bdate_range(end=end, periods=years * 252, tz="UTC")
    rows: list[dict[str, Any]] = []
    n = len(dates)

    feb = np.asarray(dates.month == 2)
    seas_rets = rng.normal(0.0, 0.002, n)
    seas_rets[feb] += np.log(1.06) / max(int(feb.sum() / (years + 1)), 1)
    seas = 40.0 * np.exp(np.cumsum(seas_rets))
    v = 2_000_000.0 * (1 + rng.normal(0, 0.03, n)).clip(0.5, 1.5)
    rows += _bars("SEAS", dates, seas, v, rng)

    for sym in ("AAA", "BBB", "CCC"):
        closes = _walk(rng, n, 50.0, 0.0002, 0.01)
        rows += _bars(sym, dates, closes, v, rng)
    return pd.DataFrame(rows)


def build_selloff(n_days: int = 280, seed: int = 5) -> pd.DataFrame:
    """Highly correlated market that rolls over with rising volatility (RiskOff)."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(end=END_DATE, periods=n_days, tz="UTC")
    split = n_days - 60
    factor = np.concatenate(
        [rng.normal(0.002, 0.004, split), rng.normal(-0.012, 0.02, n_days - split)]
    )
    rows: list[dict[str, Any]] = []
    for sym in ["SPY", "AAA", "BBB", "CCC", "DDD", "EEE"]:
        rets = factor + rng.normal(0, 0.001, n_days)
        closes = 100.0 * np.exp(np.cumsum(rets))
        vols = np.full(n_days, 2_000_000.0)
        rows += _bars(sym, dates, closes, vols, rng)
    return pd.DataFrame(rows)
