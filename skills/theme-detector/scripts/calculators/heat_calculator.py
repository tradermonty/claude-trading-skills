"""
Theme Heat Calculator (0-100)

ThemeHeat = momentum_strength * 0.35
           + volume_intensity * 0.20
           + uptrend_signal * 0.25
           + breadth_signal * 0.20

All sub-scores are direction-neutral (0-100 for "strength").
Formulas are designed to spread scores across the full 0-100 range,
avoiding ceiling effects that compress most themes into 80+.
"""

import math
from typing import List, Dict, Optional


HEAT_WEIGHTS = {
    "momentum": 0.35,
    "volume": 0.20,
    "uptrend": 0.25,
    "breadth": 0.20,
}


def momentum_strength_score(weighted_return_pct: float) -> float:
    """Log-sigmoid score based on absolute weighted return.

    Formula: 100 / (1 + exp(-2.0 * (ln(1 + |wr|) - ln(16))))

    Midpoint at |wr| = 15% (typical strong industry weighted return).
    Log transform compresses extreme values for better mid-range separation.

    Examples:
        |0%|  -> ~3
        |5%|  -> ~27
        |15%| -> 50 (midpoint)
        |30%| -> ~73
        |50%| -> ~86
    """
    x = abs(weighted_return_pct)
    log_x = math.log(1.0 + x)
    log_mid = math.log(16.0)
    return 100.0 / (1.0 + math.exp(-2.0 * (log_x - log_mid)))


def volume_intensity_score(vol_20d: Optional[float],
                           vol_60d: Optional[float]) -> float:
    """Score based on short-term vs long-term volume ratio using sqrt scaling.

    Formula: min(100, sqrt(max(0, ratio - 0.8)) / sqrt(1.2) * 100)

    Ceiling at ratio=2.0 instead of 1.2, with better mid-range separation.

    Examples:
        ratio=1.0  -> ~37
        ratio=1.2  -> ~58
        ratio=1.5  -> ~76
        ratio=2.0  -> 100

    Returns 50.0 if either input is None or vol_60d == 0.
    """
    if vol_20d is None or vol_60d is None or vol_60d == 0:
        return 50.0
    ratio = vol_20d / vol_60d
    raw = max(0.0, ratio - 0.8)
    return min(100.0, math.sqrt(raw) / math.sqrt(1.2) * 100.0)


def uptrend_signal_score(sector_data: List[Dict],
                         is_bearish: bool) -> float:
    """Continuous score from sector uptrend data.

    Each sector entry: {"sector", "ratio", "ma_10", "slope", "weight"}

    Scoring per sector:
      base = min(80, ratio * 100)   # continuous 0-80
      +10 if ratio > ma_10          # MA above bonus
      +10 if slope > 0              # positive slope bonus
      Total: 0-100 continuous

    If is_bearish: result = 100 - weighted_average
    Returns 50.0 if empty.
    """
    if not sector_data:
        return 50.0

    total_weight = 0.0
    weighted_sum = 0.0

    for entry in sector_data:
        ratio = entry.get("ratio") or 0
        ma_10 = entry.get("ma_10") or 0
        slope = entry.get("slope") or 0
        weight = entry.get("weight") or 1.0

        base = min(80.0, ratio * 100.0)
        ma_bonus = 10.0 if ratio > ma_10 else 0.0
        slope_bonus = 10.0 if slope > 0 else 0.0
        direction_score = base + ma_bonus + slope_bonus

        weighted_sum += direction_score * weight
        total_weight += weight

    if total_weight == 0:
        return 50.0

    result = weighted_sum / total_weight

    if is_bearish:
        result = 100.0 - result

    return result


def breadth_signal_score(positive_ratio: Optional[float],
                         industry_count: int = 0) -> float:
    """Score based on breadth ratio (0-1) with power curve and industry count bonus.

    Formula: min(100, ratio^2.5 * 80 + count_bonus)
    count_bonus = min(20, industry_count * 2)

    Power curve (exponent 2.5) suppresses low ratios and amplifies high ones,
    creating better separation in the 0.5-1.0 range.

    Examples (no bonus):
        ratio=0.5  -> ~14
        ratio=0.7  -> ~33
        ratio=0.9  -> ~61
        ratio=1.0  -> 80

    Returns 50.0 if None.
    """
    if positive_ratio is None:
        return 50.0
    count_bonus = min(20.0, industry_count * 2.0)
    raw = math.pow(max(0.0, positive_ratio), 2.5) * 80.0 + count_bonus
    return min(100.0, max(0.0, raw))


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
