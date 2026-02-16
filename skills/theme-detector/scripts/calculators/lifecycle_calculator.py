"""
Lifecycle Maturity Calculator (0-100)

Maturity = duration * 0.25
         + extremity * 0.25
         + price_extreme * 0.25
         + valuation * 0.15
         + etf_proliferation * 0.10

All sub-scores are direction-aware.
"""

import statistics
from typing import List, Dict, Optional


LIFECYCLE_WEIGHTS = {
    "duration": 0.25,
    "extremity": 0.25,
    "price_extreme": 0.25,
    "valuation": 0.15,
    "etf_proliferation": 0.10,
}


def estimate_duration_score(perf_1m: Optional[float],
                            perf_3m: Optional[float],
                            perf_6m: Optional[float],
                            perf_1y: Optional[float],
                            is_bearish: bool) -> float:
    """Count horizons where trend is active. Each active = 25 points.

    Bullish: perf > 2%
    Bearish: perf < -2%
    None values treated as inactive.
    """
    horizons = [perf_1m, perf_3m, perf_6m, perf_1y]
    count = 0
    for p in horizons:
        if p is None:
            continue
        if is_bearish and p < -2.0:
            count += 1
        elif not is_bearish and p > 2.0:
            count += 1
    return float(count * 25)


def extremity_clustering_score(stock_metrics: List[Dict],
                               is_bearish: bool) -> float:
    """Proportion of stocks at RSI extremes.

    Bullish: count RSI > 70
    Bearish: count RSI < 30
    Formula: min(100, pct * 200)
    Returns 50.0 if empty.
    """
    if not stock_metrics:
        return 50.0

    valid = [s for s in stock_metrics if s.get("rsi") is not None]
    if not valid:
        return 50.0

    if is_bearish:
        extreme_count = sum(1 for s in valid if s["rsi"] < 30)
    else:
        extreme_count = sum(1 for s in valid if s["rsi"] > 70)

    pct = extreme_count / len(valid)
    return min(100.0, pct * 200.0)


def price_extreme_saturation_score(stock_metrics: List[Dict],
                                   is_bearish: bool) -> float:
    """Proportion of stocks near 52-week extremes.

    Bullish: dist_from_52w_high <= 0.05
    Bearish: dist_from_52w_low <= 0.05
    Formula: min(100, pct * 200)
    Returns 50.0 if empty.
    """
    if not stock_metrics:
        return 50.0

    key = "dist_from_52w_low" if is_bearish else "dist_from_52w_high"
    valid = [s for s in stock_metrics if s.get(key) is not None]
    if not valid:
        return 50.0

    near_count = sum(1 for s in valid if s[key] <= 0.05)
    pct = near_count / len(valid)
    return min(100.0, pct * 200.0)


def valuation_premium_score(stock_metrics: List[Dict]) -> float:
    """Score based on median P/E relative to market average (22).

    premium_ratio = median_PE / 22.0
    Score: min(100, max(0, (premium_ratio - 0.5) * 32))
    Needs 3+ valid P/E values, else returns 50.0.
    """
    valid_pe = [s["pe_ratio"] for s in stock_metrics
                if s.get("pe_ratio") is not None and s["pe_ratio"] > 0]

    if len(valid_pe) < 3:
        return 50.0

    median_pe = statistics.median(valid_pe)
    premium_ratio = median_pe / 22.0
    return min(100.0, max(0.0, (premium_ratio - 0.5) * 32.0))


def etf_proliferation_score(etf_count: int) -> float:
    """Score based on number of theme-related ETFs.

    0 => 0, 1 => 20, <=3 => 40, <=6 => 60, <=10 => 80, >10 => 100
    """
    if etf_count == 0:
        return 0.0
    elif etf_count == 1:
        return 20.0
    elif etf_count <= 3:
        return 40.0
    elif etf_count <= 6:
        return 60.0
    elif etf_count <= 10:
        return 80.0
    else:
        return 100.0


def classify_stage(maturity: float) -> str:
    """Classify lifecycle stage from maturity score.

    0-20: Emerging, 20-40: Accelerating, 40-60: Trending,
    60-80: Mature, 80-100: Exhausting
    """
    if maturity < 20:
        return "Emerging"
    elif maturity < 40:
        return "Accelerating"
    elif maturity < 60:
        return "Trending"
    elif maturity < 80:
        return "Mature"
    else:
        return "Exhausting"


def calculate_lifecycle_maturity(duration: Optional[float],
                                 extremity: Optional[float],
                                 price_extreme: Optional[float],
                                 valuation: Optional[float],
                                 etf_prolif: Optional[float]) -> float:
    """Weighted sum of lifecycle sub-scores, clamped 0-100.

    Any None input defaults to 50.0.
    """
    d = duration if duration is not None else 50.0
    e = extremity if extremity is not None else 50.0
    p = price_extreme if price_extreme is not None else 50.0
    v = valuation if valuation is not None else 50.0
    et = etf_prolif if etf_prolif is not None else 50.0

    raw = (d * LIFECYCLE_WEIGHTS["duration"]
           + e * LIFECYCLE_WEIGHTS["extremity"]
           + p * LIFECYCLE_WEIGHTS["price_extreme"]
           + v * LIFECYCLE_WEIGHTS["valuation"]
           + et * LIFECYCLE_WEIGHTS["etf_proliferation"])

    return float(min(100.0, max(0.0, raw)))
