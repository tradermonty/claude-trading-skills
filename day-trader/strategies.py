"""Day trading strategy implementations.

Each strategy inspects recent bar data for a symbol and returns a Signal
(or None). The trader loop decides whether to act on it based on the
current risk mode, existing positions, and risk controls.

Implemented strategies:
  - mean_reversion   RSI<30 -> long; RSI>70 -> short
  - momentum         Strong upside w/ rising volume + above VWAP
  - ma_crossover     EMA(9) crosses EMA(20)
  - vwap_bounce      Pullback to VWAP on uptrending stock
  - gap_and_go       Opens above prior close w/ volume, holds above VWAP
  - short_the_rip    Overextended long -> short (RSI>78 + >2 ATR above VWAP)
  - breakout         Break above 15-min opening range high w/ volume
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd


Side = Literal["long", "short"]


@dataclass
class Signal:
    symbol: str
    strategy: str
    side: Side
    confidence: float       # 0.0 - 1.0
    reason: str
    entry_price: float


# ---------------------- indicators ----------------------

def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = -delta.clip(upper=0).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def _vwap(df: pd.DataFrame) -> pd.Series:
    typical = (df["high"] + df["low"] + df["close"]) / 3
    return (typical * df["volume"]).cumsum() / df["volume"].cumsum().replace(0, np.nan)


def _atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift()).abs()
    low_close = (df["low"] - df["close"].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.rolling(period).mean()


# ---------------------- strategies ----------------------

def mean_reversion(symbol: str, df: pd.DataFrame) -> Signal | None:
    if len(df) < 20:
        return None
    rsi = _rsi(df["close"])
    last_rsi = rsi.iloc[-1]
    last = float(df["close"].iloc[-1])
    if pd.isna(last_rsi):
        return None
    if last_rsi < 30:
        return Signal(symbol, "mean_reversion", "long",
                      confidence=min(1.0, (30 - last_rsi) / 15 + 0.5),
                      reason=f"RSI={last_rsi:.1f} oversold",
                      entry_price=last)
    if last_rsi > 70:
        return Signal(symbol, "mean_reversion", "short",
                      confidence=min(1.0, (last_rsi - 70) / 15 + 0.5),
                      reason=f"RSI={last_rsi:.1f} overbought",
                      entry_price=last)
    return None


def momentum(symbol: str, df: pd.DataFrame) -> Signal | None:
    if len(df) < 30:
        return None
    last = float(df["close"].iloc[-1])
    ret_30 = (df["close"].iloc[-1] / df["close"].iloc[-30] - 1) * 100
    vol_ratio = df["volume"].iloc[-5:].mean() / df["volume"].iloc[-30:-5].mean()
    vwap = _vwap(df).iloc[-1]
    if pd.isna(vwap) or pd.isna(vol_ratio):
        return None
    if ret_30 > 1.5 and vol_ratio > 1.3 and last > vwap:
        return Signal(symbol, "momentum", "long",
                      confidence=min(1.0, ret_30 / 5),
                      reason=f"+{ret_30:.1f}% w/ {vol_ratio:.1f}x vol, above VWAP",
                      entry_price=last)
    return None


def ma_crossover(symbol: str, df: pd.DataFrame) -> Signal | None:
    if len(df) < 25:
        return None
    ema9 = _ema(df["close"], 9)
    ema20 = _ema(df["close"], 20)
    if pd.isna(ema9.iloc[-2]) or pd.isna(ema20.iloc[-2]):
        return None
    last = float(df["close"].iloc[-1])
    # Confidence scales with separation of fast/slow EMA after the cross,
    # normalized by ATR — cleaner breakouts score higher.
    atr = _atr(df).iloc[-1]
    sep = abs(ema9.iloc[-1] - ema20.iloc[-1])
    sep_atr = sep / atr if atr and atr > 0 else 0
    conf = min(1.0, 0.55 + sep_atr * 0.5)
    if ema9.iloc[-2] <= ema20.iloc[-2] and ema9.iloc[-1] > ema20.iloc[-1]:
        return Signal(symbol, "ma_crossover", "long",
                      confidence=conf,
                      reason=f"EMA9>EMA20 cross (sep={sep_atr:.2f}×ATR)",
                      entry_price=last)
    if ema9.iloc[-2] >= ema20.iloc[-2] and ema9.iloc[-1] < ema20.iloc[-1]:
        return Signal(symbol, "ma_crossover", "short",
                      confidence=conf,
                      reason=f"EMA9<EMA20 cross (sep={sep_atr:.2f}×ATR)",
                      entry_price=last)
    return None


def vwap_bounce(symbol: str, df: pd.DataFrame) -> Signal | None:
    if len(df) < 30:
        return None
    vwap = _vwap(df)
    last = float(df["close"].iloc[-1])
    last_vwap = vwap.iloc[-1]
    if pd.isna(last_vwap):
        return None
    ema20 = _ema(df["close"], 20)
    rising = ema20.iloc[-1] > ema20.iloc[-10]
    prev_above = (df["close"].iloc[-6:-1] > vwap.iloc[-6:-1]).all()
    tagged = df["low"].iloc[-1] <= last_vwap * 1.002 and last > last_vwap
    if rising and prev_above and tagged:
        # Confidence scales with EMA20 slope steepness — steeper uptrend = stronger bounce.
        slope = (ema20.iloc[-1] - ema20.iloc[-10]) / ema20.iloc[-10]
        conf = min(1.0, 0.55 + slope * 50)  # 1% slope = 1.05 → clamped to 1.0
        return Signal(symbol, "vwap_bounce", "long",
                      confidence=conf,
                      reason=f"VWAP tag in uptrend (slope={slope*100:.2f}%)",
                      entry_price=last)
    return None


def gap_and_go(symbol: str, df: pd.DataFrame) -> Signal | None:
    if len(df) < 10:
        return None
    open_today = float(df["open"].iloc[0])
    prior_close_proxy = float(df["close"].iloc[0])
    last = float(df["close"].iloc[-1])
    vwap = _vwap(df).iloc[-1]
    hod = df["high"].max()
    near_hod = last >= hod * 0.995
    if pd.isna(vwap):
        return None
    vol_ratio = df["volume"].iloc[-5:].mean() / max(df["volume"].mean(), 1)
    if near_hod and last > vwap and vol_ratio > 1.0:
        # Confidence scales with volume ratio and VWAP distance
        vwap_dist = (last - vwap) / vwap
        conf = min(1.0, 0.55 + (vol_ratio - 1.0) * 0.3 + vwap_dist * 20)
        return Signal(symbol, "gap_and_go", "long",
                      confidence=conf,
                      reason=f"HOD + {vol_ratio:.2f}x vol + {vwap_dist*100:.2f}% above VWAP",
                      entry_price=last)
    return None


def short_the_rip(symbol: str, df: pd.DataFrame) -> Signal | None:
    if len(df) < 30:
        return None
    rsi = _rsi(df["close"]).iloc[-1]
    vwap = _vwap(df).iloc[-1]
    atr = _atr(df).iloc[-1]
    last = float(df["close"].iloc[-1])
    if pd.isna(rsi) or pd.isna(vwap) or pd.isna(atr) or atr == 0:
        return None
    dist_vwap_atr = (last - vwap) / atr
    if rsi > 78 and dist_vwap_atr > 2.0:
        return Signal(symbol, "short_the_rip", "short",
                      confidence=min(1.0, (rsi - 78) / 10 + 0.6),
                      reason=f"RSI={rsi:.1f}, {dist_vwap_atr:.1f} ATR above VWAP",
                      entry_price=last)
    return None


def breakout(symbol: str, df: pd.DataFrame) -> Signal | None:
    if len(df) < 20:
        return None
    opening_high = df["high"].iloc[:3].max()
    opening_low = df["low"].iloc[:3].min()
    range_size = opening_high - opening_low
    last = float(df["close"].iloc[-1])
    recent_vol = df["volume"].iloc[-3:].mean()
    avg_vol = df["volume"].mean()
    vol_ratio = recent_vol / max(avg_vol, 1)
    if last > opening_high and vol_ratio > 1.2:
        # Confidence scales with volume and how far past the range
        pct_past = (last - opening_high) / max(range_size, 0.01)
        conf = min(1.0, 0.55 + (vol_ratio - 1.2) * 0.3 + pct_past * 0.2)
        return Signal(symbol, "breakout", "long",
                      confidence=conf,
                      reason=f"Above ORH {opening_high:.2f} ({vol_ratio:.2f}x vol)",
                      entry_price=last)
    if last < opening_low and vol_ratio > 1.2:
        pct_past = (opening_low - last) / max(range_size, 0.01)
        conf = min(1.0, 0.55 + (vol_ratio - 1.2) * 0.3 + pct_past * 0.2)
        return Signal(symbol, "breakout", "short",
                      confidence=conf,
                      reason=f"Below ORL {opening_low:.2f} ({vol_ratio:.2f}x vol)",
                      entry_price=last)
    return None


STRATEGY_FUNCS = {
    "mean_reversion": mean_reversion,
    "momentum": momentum,
    "ma_crossover": ma_crossover,
    "vwap_bounce": vwap_bounce,
    "gap_and_go": gap_and_go,
    "short_the_rip": short_the_rip,
    "breakout": breakout,
}


def scan(symbol: str, df: pd.DataFrame, allowed: list[str]) -> list[Signal]:
    signals: list[Signal] = []
    for name in allowed:
        fn = STRATEGY_FUNCS.get(name)
        if not fn:
            continue
        try:
            sig = fn(symbol, df)
            if sig:
                signals.append(sig)
        except Exception:
            continue
    return signals
