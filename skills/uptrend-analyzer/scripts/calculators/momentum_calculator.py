#!/usr/bin/env python3
"""
Component 4: Momentum - Weight: 20%

Evaluates the rate of change (slope) and acceleration of the overall
uptrend ratio, plus sector-level slope breadth.

Data Source: Timeseries "all" + Sector Summary

Sub-scores:
  - Slope Score (50%): Current slope mapped to 0-100 (typical range: -0.02~+0.02)
  - Acceleration (30%): Recent 5-point slope avg vs prior 5-point
  - Sector Slope Breadth (20%): Count of sectors with positive slope
"""

from typing import Dict, List, Optional


def calculate_momentum(all_timeseries: List[Dict],
                       sector_summary: List[Dict]) -> Dict:
    """
    Calculate momentum score from slope, acceleration, and sector breadth.

    Args:
        all_timeseries: Full "all" timeseries sorted by date ascending
        sector_summary: Latest sector summary rows

    Returns:
        Dict with score (0-100), signal, and detail fields
    """
    if not all_timeseries:
        return {
            "score": 50,
            "signal": "NO DATA: Timeseries unavailable (neutral default)",
            "data_available": False,
            "slope": None,
            "acceleration": None,
            "sector_slope_breadth": None,
        }

    latest = all_timeseries[-1]
    current_slope = latest.get("slope")

    # Sub-score 1: Slope Score (50%)
    slope_score = _score_slope(current_slope) if current_slope is not None else 50

    # Sub-score 2: Acceleration (30%)
    accel_score, accel_value, accel_label = _score_acceleration(all_timeseries)

    # Sub-score 3: Sector Slope Breadth (20%)
    breadth_score, positive_slope_count, total_sectors = _score_sector_slope_breadth(
        sector_summary
    )

    # Composite
    raw_score = slope_score * 0.50 + accel_score * 0.30 + breadth_score * 0.20
    score = round(min(100, max(0, raw_score)))

    signal = _build_signal(score, current_slope, accel_label)

    return {
        "score": score,
        "signal": signal,
        "data_available": True,
        "slope": current_slope,
        "slope_score": round(slope_score),
        "acceleration": accel_value,
        "acceleration_label": accel_label,
        "acceleration_score": round(accel_score),
        "sector_positive_slope_count": positive_slope_count,
        "sector_total": total_sectors,
        "sector_slope_breadth_score": round(breadth_score),
        "date": latest.get("date", "N/A"),
    }


def _score_slope(slope: float) -> float:
    """Map current slope to 0-100 score.

    Typical slope range: -0.02 to +0.02
    Extreme range: -0.03 to +0.03

      >= +0.02 -> 95-100 (strong bullish momentum)
      +0.01~+0.02 -> 75-94
      0~+0.01 -> 55-74 (mild positive)
      -0.01~0 -> 35-54 (mild negative)
      -0.02~-0.01 -> 10-34
      < -0.02 -> 0-9 (strong bearish momentum)
    """
    if slope >= 0.02:
        return min(100, 95 + (slope - 0.02) / 0.01 * 5)
    elif slope >= 0.01:
        return 75 + (slope - 0.01) / 0.01 * 19
    elif slope >= 0:
        return 55 + slope / 0.01 * 19
    elif slope >= -0.01:
        return 35 + (slope + 0.01) / 0.01 * 19
    elif slope >= -0.02:
        return 10 + (slope + 0.02) / 0.01 * 24
    else:
        return max(0, 9 + (slope + 0.02) / 0.01 * 9)


def _score_acceleration(timeseries: List[Dict]) -> tuple:
    """Calculate acceleration: recent vs prior slope average.

    Returns: (score, acceleration_value, label)
    """
    if len(timeseries) < 10:
        return 50, None, "insufficient_data"

    # Get slopes for recent 10 data points
    recent_slopes = []
    for row in timeseries[-10:]:
        s = row.get("slope")
        if s is not None:
            recent_slopes.append(s)

    if len(recent_slopes) < 10:
        return 50, None, "insufficient_data"

    recent_5_avg = sum(recent_slopes[-5:]) / 5
    prior_5_avg = sum(recent_slopes[:5]) / 5

    acceleration = recent_5_avg - prior_5_avg

    if acceleration > 0.005:
        label = "strong_accelerating"
        score = 90
    elif acceleration > 0.001:
        label = "accelerating"
        score = 75
    elif acceleration > -0.001:
        label = "steady"
        score = 50
    elif acceleration > -0.005:
        label = "decelerating"
        score = 25
    else:
        label = "strong_decelerating"
        score = 10

    return score, round(acceleration, 6), label


def _score_sector_slope_breadth(sector_summary: List[Dict]) -> tuple:
    """Score based on count of sectors with positive slope.

    Returns: (score, positive_count, total_count)
    """
    if not sector_summary:
        return 50, 0, 0

    total = len(sector_summary)
    positive = sum(
        1 for s in sector_summary
        if s.get("Slope") is not None and s["Slope"] > 0
    )

    if total == 0:
        return 50, 0, 0

    # Linear mapping: 0 sectors -> 0, all sectors -> 100
    score = (positive / total) * 100

    return score, positive, total


def _build_signal(score: int, slope: Optional[float], accel_label: str) -> str:
    """Build human-readable signal."""
    slope_str = f"slope={slope:.4f}" if slope is not None else "slope=N/A"
    accel_str = accel_label.replace("_", " ")

    if score >= 80:
        return f"STRONG MOMENTUM: {slope_str}, {accel_str}"
    elif score >= 60:
        return f"POSITIVE MOMENTUM: {slope_str}, {accel_str}"
    elif score >= 40:
        return f"NEUTRAL MOMENTUM: {slope_str}, {accel_str}"
    elif score >= 20:
        return f"WEAK MOMENTUM: {slope_str}, {accel_str}"
    else:
        return f"NEGATIVE MOMENTUM: {slope_str}, {accel_str}"
