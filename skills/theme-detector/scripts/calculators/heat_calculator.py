"""
Theme Heat Calculator (0-100)

ThemeHeat = momentum_strength * 0.40
           + volume_intensity * 0.25
           + uptrend_signal * 0.20
           + breadth_signal * 0.15

All sub-scores are direction-neutral (0-100 for "strength").
"""

import math
from typing import List, Dict, Optional


HEAT_WEIGHTS = {
    "momentum": 0.40,
    "volume": 0.25,
    "uptrend": 0.20,
    "breadth": 0.15,
}


def momentum_strength_score(weighted_return_pct: float) -> float:
    """Sigmoid score based on absolute weighted return.

    Formula: 100 / (1 + exp(-0.15 * (abs(wr%) - 5.0)))
    """
    x = abs(weighted_return_pct)
    return 100.0 / (1.0 + math.exp(-0.15 * (x - 5.0)))


def volume_intensity_score(vol_20d: Optional[float],
                           vol_60d: Optional[float]) -> float:
    """Score based on short-term vs long-term volume ratio.

    Formula: min(100, max(0, (vol_20d/vol_60d - 0.8) * 250))
    Returns 50.0 if either is None or vol_60d == 0.
    """
    if vol_20d is None or vol_60d is None or vol_60d == 0:
        return 50.0
    ratio = vol_20d / vol_60d
    return min(100.0, max(0.0, (ratio - 0.8) * 250.0))


def uptrend_signal_score(sector_data: List[Dict],
                         is_bearish: bool) -> float:
    """Weighted average of per-sector uptrend direction scores.

    Each sector entry: {"sector", "ratio", "ma_10", "slope", "weight"}
    Scoring per sector:
      ratio > ma_10 AND slope > 0 => 80
      ratio > ma_10 OR slope > 0  => 60
      neither                     => 20
    If is_bearish: result = 100 - weighted_average
    Returns 50.0 if empty.
    """
    if not sector_data:
        return 50.0

    total_weight = 0.0
    weighted_sum = 0.0

    for entry in sector_data:
        ratio = entry.get("ratio", 0)
        ma_10 = entry.get("ma_10", 0)
        slope = entry.get("slope", 0)
        weight = entry.get("weight", 1.0)

        above_ma = ratio > ma_10
        positive_slope = slope > 0

        if above_ma and positive_slope:
            direction_score = 80.0
        elif above_ma or positive_slope:
            direction_score = 60.0
        else:
            direction_score = 20.0

        weighted_sum += direction_score * weight
        total_weight += weight

    if total_weight == 0:
        return 50.0

    result = weighted_sum / total_weight

    if is_bearish:
        result = 100.0 - result

    return result


def breadth_signal_score(positive_ratio: Optional[float]) -> float:
    """Score based on breadth ratio (0-1).

    Formula: min(100, max(0, positive_ratio * 100))
    Returns 50.0 if None.
    """
    if positive_ratio is None:
        return 50.0
    return min(100.0, max(0.0, positive_ratio * 100.0))


def calculate_theme_heat(momentum: Optional[float],
                         volume: Optional[float],
                         uptrend: Optional[float],
                         breadth: Optional[float]) -> float:
    """Weighted sum of sub-scores, clamped 0-100.

    Any None input defaults to 50.0.
    """
    m = momentum if momentum is not None else 50.0
    v = volume if volume is not None else 50.0
    u = uptrend if uptrend is not None else 50.0
    b = breadth if breadth is not None else 50.0

    raw = (m * HEAT_WEIGHTS["momentum"]
           + v * HEAT_WEIGHTS["volume"]
           + u * HEAT_WEIGHTS["uptrend"]
           + b * HEAT_WEIGHTS["breadth"])

    return float(min(100.0, max(0.0, raw)))
