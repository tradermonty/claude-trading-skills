#!/usr/bin/env python3
"""
Component 5: Historical Context - Weight: 10%

Evaluates the current uptrend ratio relative to its full historical
distribution (2023/08~present) using percentile rank.

Data Source: Timeseries "all" worksheet

Score = percentile rank of current ratio in historical distribution
Additional context: min, max, median, 30d avg, 90d avg
"""

from typing import Dict, List, Optional


def calculate_historical_context(all_timeseries: List[Dict]) -> Dict:
    """
    Calculate historical context score via percentile rank.

    Args:
        all_timeseries: Full "all" timeseries sorted by date ascending

    Returns:
        Dict with score (0-100), signal, and context fields
    """
    if not all_timeseries:
        return {
            "score": 50,
            "signal": "NO DATA: Historical timeseries unavailable (neutral default)",
            "data_available": False,
            "percentile": None,
            "current_ratio": None,
            "historical_min": None,
            "historical_max": None,
            "historical_median": None,
        }

    # Extract all valid ratios
    ratios = [r["ratio"] for r in all_timeseries if r.get("ratio") is not None]

    if len(ratios) < 2:
        return {
            "score": 50,
            "signal": "INSUFFICIENT DATA: Need at least 2 data points",
            "data_available": False,
            "percentile": None,
            "current_ratio": None,
            "data_points": len(ratios),
        }

    current_ratio = ratios[-1]

    # Calculate percentile rank
    below_count = sum(1 for r in ratios if r < current_ratio)
    equal_count = sum(1 for r in ratios if r == current_ratio)
    percentile = (below_count + equal_count * 0.5) / len(ratios) * 100
    percentile = round(percentile, 1)

    # Score = percentile rank (direct mapping)
    score = round(min(100, max(0, percentile)))

    # Historical statistics
    sorted_ratios = sorted(ratios)
    hist_min = sorted_ratios[0]
    hist_max = sorted_ratios[-1]
    n = len(sorted_ratios)
    if n % 2 == 0:
        hist_median = (sorted_ratios[n // 2 - 1] + sorted_ratios[n // 2]) / 2
    else:
        hist_median = sorted_ratios[n // 2]

    # Recent averages
    avg_30d = _avg_last_n(ratios, 30)
    avg_90d = _avg_last_n(ratios, 90)

    signal = _build_signal(score, percentile, current_ratio)

    return {
        "score": score,
        "signal": signal,
        "data_available": True,
        "percentile": percentile,
        "current_ratio": current_ratio,
        "current_ratio_pct": round(current_ratio * 100, 1),
        "historical_min": round(hist_min, 4),
        "historical_min_pct": round(hist_min * 100, 1),
        "historical_max": round(hist_max, 4),
        "historical_max_pct": round(hist_max * 100, 1),
        "historical_median": round(hist_median, 4),
        "historical_median_pct": round(hist_median * 100, 1),
        "avg_30d": round(avg_30d, 4) if avg_30d is not None else None,
        "avg_30d_pct": round(avg_30d * 100, 1) if avg_30d is not None else None,
        "avg_90d": round(avg_90d, 4) if avg_90d is not None else None,
        "avg_90d_pct": round(avg_90d * 100, 1) if avg_90d is not None else None,
        "data_points": len(ratios),
        "date_range": f"{all_timeseries[0].get('date', '?')} to {all_timeseries[-1].get('date', '?')}",
    }


def _avg_last_n(values: List[float], n: int) -> Optional[float]:
    """Average of the last n values, or all if fewer than n."""
    if not values:
        return None
    subset = values[-n:]
    return sum(subset) / len(subset)


def _build_signal(score: int, percentile: float, current_ratio: float) -> str:
    """Build human-readable signal."""
    ratio_pct = round(current_ratio * 100, 1)

    if score >= 80:
        return f"ABOVE AVERAGE: {ratio_pct}% at {percentile}th percentile historically"
    elif score >= 60:
        return f"SLIGHTLY ABOVE: {ratio_pct}% at {percentile}th percentile historically"
    elif score >= 40:
        return f"NEAR MEDIAN: {ratio_pct}% at {percentile}th percentile historically"
    elif score >= 20:
        return f"BELOW AVERAGE: {ratio_pct}% at {percentile}th percentile historically"
    else:
        return f"HISTORICALLY LOW: {ratio_pct}% at {percentile}th percentile historically"
