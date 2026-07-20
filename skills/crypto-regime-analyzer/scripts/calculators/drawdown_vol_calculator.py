#!/usr/bin/env python3
"""
Component 5: Drawdown & Volatility Position (Weight: 15%)

Locates BTC within its cycle using drawdown from the trailing 1-year high,
then adjusts for the realized-volatility regime. Shallow drawdowns with
compressed volatility historically precede continuation; deep drawdowns
with expanding volatility mark active bear phases.

Input: BTC daily closes oldest -> newest (>= 365 obs for full scoring).

Scoring (100 = healthy cycle position):
  Drawdown from trailing 365d high:
    <= 10% -> 90    <= 20% -> 75    <= 35% -> 55
    <= 50% -> 35    <= 65% -> 20    >  65% -> 10 (capitulation zone)

  Volatility modifier (30d realized vol vs its trailing 1y distribution):
    vol in bottom third of 1y range -> +10 (compression)
    vol in top third of 1y range    -> -10 (expansion / stress)

  Deep-drawdown contrarian floor: when drawdown > 65% AND volatility is in
  the top third (capitulation), score floors at 15 rather than falling
  further; extreme readings are where forward returns start improving.
"""

import math

MIN_HISTORY = 365
VOL_WINDOW = 30


def _drawdown_score(dd: float) -> int:
    if dd <= 0.10:
        return 90
    if dd <= 0.20:
        return 75
    if dd <= 0.35:
        return 55
    if dd <= 0.50:
        return 35
    if dd <= 0.65:
        return 20
    return 10


def _realized_vol(closes: list, window: int) -> float:
    # log(current) - log(previous) is algebraically identical to
    # log(current / previous), but does not overflow/underflow when both
    # prices are finite positive values at opposite IEEE-754 extremes.
    rets = [
        math.log(closes[i]) - math.log(closes[i - 1])
        for i in range(len(closes) - window + 1, len(closes))
        if closes[i - 1] > 0
    ]
    if len(rets) < 2:
        return 0.0
    mean = math.fsum(rets) / len(rets)
    var = math.fsum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
    return math.sqrt(max(0.0, var)) * math.sqrt(365)


def calculate_drawdown_vol(closes: list) -> dict:
    """
    Score BTC cycle position via drawdown and volatility regime.

    Args:
        closes: BTC daily closes oldest -> newest.

    Returns:
        Dict with score, signal, data_available, and cycle details.
    """
    if not closes or len(closes) < MIN_HISTORY:
        return {
            "score": 50,
            "signal": f"NO DATA: Need >= {MIN_HISTORY} daily closes",
            "data_available": False,
        }

    window = closes[-MIN_HISTORY:]
    high = max(window)
    price = closes[-1]
    dd = 1 - (price / high) if high > 0 else 0.0
    score = _drawdown_score(dd)

    # Volatility percentile within trailing year of rolling 30d vols
    vols = [
        _realized_vol(window[: i + 1], VOL_WINDOW)
        for i in range(VOL_WINDOW, len(window), 7)  # weekly stride for speed
    ]
    current_vol = _realized_vol(window, VOL_WINDOW)
    below = sum(1 for v in vols if v <= current_vol)
    vol_pctile = below / len(vols) if vols else 0.5

    modifier = ""
    if vol_pctile <= 1 / 3:
        score += 10
        modifier = "; volatility compressed (bottom third of 1y range)"
    elif vol_pctile >= 2 / 3:
        score -= 10
        modifier = "; volatility elevated (top third of 1y range)"

    if dd > 0.65 and vol_pctile >= 2 / 3:
        score = max(score, 15)
        modifier += "; capitulation-zone contrarian floor applied"

    score = max(0, min(100, score))
    return {
        "score": score,
        "signal": f"Drawdown {dd * 100:.1f}% from 1y high{modifier}",
        "data_available": True,
        "drawdown_pct": round(dd * 100, 2),
        "realized_vol_30d": round(current_vol, 4),
        "vol_percentile_1y": round(vol_pctile, 2),
    }
