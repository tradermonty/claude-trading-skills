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
from typing import Optional

LIFECYCLE_WEIGHTS = {
    "duration": 0.25,
    "extremity": 0.25,
    "price_extreme": 0.25,
    "valuation": 0.15,
    "etf_proliferation": 0.10,
}


def estimate_duration_score(
    perf_1m: Optional[float],
    perf_3m: Optional[float],
    perf_6m: Optional[float],
    perf_1y: Optional[float],
    is_bearish: bool,
) -> float:
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


def extremity_clustering_score(stock_metrics: list[dict], is_bearish: bool) -> Optional[float]:
    """Proportion of stocks at RSI extremes.

    Bullish: count RSI > 70
    Bearish: count RSI < 30
    Formula: min(100, pct * 200)
    Returns None if empty or no valid RSI values.
    """
    if not stock_metrics:
        return None

    valid = [s for s in stock_metrics if s.get("rsi") is not None]
    if not valid:
        return None

    if is_bearish:
        extreme_count = sum(1 for s in valid if s["rsi"] < 30)
    else:
        extreme_count = sum(1 for s in valid if s["rsi"] > 70)

    pct = extreme_count / len(valid)
    return min(100.0, pct * 200.0)


def price_extreme_saturation_score(stock_metrics: list[dict], is_bearish: bool) -> Optional[float]:
    """Proportion of stocks near 52-week extremes.

    Bullish: dist_from_52w_high <= 0.05
    Bearish: dist_from_52w_low <= 0.05
    Formula: min(100, pct * 200)
    Returns None if empty or no valid 52-week distance values.
    """
    if not stock_metrics:
        return None

    key = "dist_from_52w_low" if is_bearish else "dist_from_52w_high"
    valid = [s for s in stock_metrics if s.get(key) is not None]
    if not valid:
        return None

    near_count = sum(1 for s in valid if s[key] <= 0.05)
    pct = near_count / len(valid)
    return min(100.0, pct * 200.0)


def valuation_premium_score(stock_metrics: list[dict]) -> Optional[float]:
    """Score based on median P/E relative to market average (22).

    premium_ratio = median_PE / 22.0
    Score: min(100, max(0, (premium_ratio - 0.5) * 32))
    Needs 3+ valid P/E values, else returns None.
    """
    valid_pe = [
        s["pe_ratio"] for s in stock_metrics if s.get("pe_ratio") is not None and s["pe_ratio"] > 0
    ]

    if len(valid_pe) < 3:
        return None

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


def has_sufficient_lifecycle_data(
    extremity: Optional[float], price_extreme: Optional[float], valuation: Optional[float]
) -> bool:
    """Check whether stock-derived lifecycle sub-scores have real data.

    Returns False if all three stock-based sub-scores are None (indicating
    no stock metrics were available). Duration and etf_proliferation are
    industry-level scores and always available.
    """
    return not (extremity is None and price_extreme is None and valuation is None)


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


def calculate_lifecycle_maturity(
    duration: Optional[float],
    extremity: Optional[float],
    price_extreme: Optional[float],
    valuation: Optional[float],
    etf_prolif: Optional[float],
) -> float:
    """Weighted available lifecycle sub-scores, clamped 0-100.

    Missing inputs are excluded from the denominator rather than defaulting
    to neutral 50.0. Returns 0.0 if no components are available.
    """
    detailed = calculate_lifecycle_maturity_detailed(
        duration, extremity, price_extreme, valuation, etf_prolif
    )
    return float(detailed["score"] or 0.0)


def calculate_lifecycle_maturity_detailed(
    duration: Optional[float],
    extremity: Optional[float],
    price_extreme: Optional[float],
    valuation: Optional[float],
    etf_prolif: Optional[float],
) -> dict:
    """Calculate lifecycle maturity plus coverage metadata."""
    components = {
        "duration": duration,
        "extremity": extremity,
        "price_extreme": price_extreme,
        "valuation": valuation,
        "etf_proliferation": etf_prolif,
    }
    score, coverage = _weighted_available_score(components, LIFECYCLE_WEIGHTS)
    missing = [name for name, value in components.items() if value is None]
    return {
        "score": None if score is None else float(min(100.0, max(0.0, score))),
        "coverage": coverage,
        "missing_components": missing,
        "components": components,
    }


def _weighted_available_score(
    components: dict[str, Optional[float]], weights: dict[str, float]
) -> tuple[Optional[float], float]:
    available = {k: v for k, v in components.items() if v is not None}
    total_possible = sum(weights.values())
    total_weight = sum(weights[k] for k in available if k in weights)
    if total_weight == 0 or total_possible == 0:
        return None, 0.0

    score = sum(float(available[k]) * weights[k] for k in available if k in weights) / total_weight
    return score, total_weight / total_possible
