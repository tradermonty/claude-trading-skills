#!/usr/bin/env python3
"""
Gap Size Calculator for Earnings Trade Analyzer

Calculates earnings gap based on BMO/AMC timing and scores the gap magnitude.

BMO (Before Market Open): gap = (open[earnings_date] / close[prev_day]) - 1
AMC (After Market Close) / unknown: gap = (open[next_day] / close[earnings_date]) - 1

Scoring (25% weight):
  |gap| >= 10%: 100
  |gap| >= 7%:   85
  |gap| >= 5%:   70
  |gap| >= 3%:   55
  |gap| >= 1%:   35
  |gap| < 1%:    15
"""


def _find_index_by_date(daily_prices: list[dict], target_date: str) -> int:
    """Find the index of target_date in daily_prices (most-recent-first).

    Returns:
        Index if found, -1 otherwise.
    """
    for i, bar in enumerate(daily_prices):
        if bar.get("date") == target_date:
            return i
    return -1


def _score_gap(abs_gap_pct: float) -> float:
    """Score the absolute gap percentage.

    Args:
        abs_gap_pct: Absolute gap percentage (e.g. 6.3 for 6.3%)

    Returns:
        Score from 0 to 100.
    """
    if abs_gap_pct >= 10.0:
        return 100.0
    elif abs_gap_pct >= 7.0:
        return 85.0
    elif abs_gap_pct >= 5.0:
        return 70.0
    elif abs_gap_pct >= 3.0:
        return 55.0
    elif abs_gap_pct >= 1.0:
        return 35.0
    else:
        return 15.0


def calculate_gap(daily_prices: list[dict], earnings_date: str, timing: str) -> dict:
    """
    Calculate earnings gap based on BMO/AMC timing.

    Args:
        daily_prices: list of dicts with 'date', 'open', 'close' (most-recent-first)
        earnings_date: YYYY-MM-DD string
        timing: 'bmo', 'amc', or 'unknown'

    BMO: gap = (open[earnings_date] / close[prev_day]) - 1
    AMC/unknown: gap = (open[next_day] / close[earnings_date]) - 1

    "prev_day" and "next_day" are resolved by index in daily_prices
    (business days only since we use actual trading data).

    Returns:
        dict with:
          - gap_pct: float (percentage, e.g. 6.3 for 6.3%)
          - gap_type: 'up' or 'down'
          - base_price: float (denominator in gap calc)
          - gap_price: float (numerator in gap calc)
          - timing_used: str
          - score: float (0-100)
          - warning: str (optional, if data issue)
          - timing_note: str (optional; present only when timing is 'unknown',
            explaining that the AMC window was assumed rather than measured)
    """
    earnings_idx = _find_index_by_date(daily_prices, earnings_date)

    if earnings_idx == -1:
        return {
            "gap_pct": 0.0,
            "gap_type": "up",
            "base_price": 0.0,
            "gap_price": 0.0,
            "timing_used": timing,
            "score": 0.0,
            "warning": f"Earnings date {earnings_date} not found in price data",
        }

    timing_lower = timing.lower() if timing else "unknown"

    if timing_lower == "bmo":
        # BMO: gap = open[earnings_date] / close[prev_day] - 1
        # In most-recent-first order, prev_day is at index earnings_idx + 1
        prev_idx = earnings_idx + 1
        if prev_idx >= len(daily_prices):
            return {
                "gap_pct": 0.0,
                "gap_type": "up",
                "base_price": 0.0,
                "gap_price": 0.0,
                "timing_used": timing_lower,
                "score": 0.0,
                "warning": "No previous trading day available for BMO gap calculation",
            }
        base_price = daily_prices[prev_idx]["close"]
        gap_price = daily_prices[earnings_idx]["open"]
    else:
        # AMC or unknown: gap = open[next_day] / close[earnings_date] - 1
        # In most-recent-first order, next_day is at index earnings_idx - 1
        next_idx = earnings_idx - 1
        if next_idx < 0:
            return {
                "gap_pct": 0.0,
                "gap_type": "up",
                "base_price": 0.0,
                "gap_price": 0.0,
                "timing_used": timing_lower,
                "score": 0.0,
                "warning": "No next trading day available for AMC gap calculation",
            }
        base_price = daily_prices[earnings_idx]["close"]
        gap_price = daily_prices[next_idx]["open"]

    if base_price == 0:
        return {
            "gap_pct": 0.0,
            "gap_type": "up",
            "base_price": base_price,
            "gap_price": gap_price,
            "timing_used": timing_lower,
            "score": 0.0,
            "warning": "Base price is zero, cannot calculate gap",
        }

    gap_pct = ((gap_price / base_price) - 1.0) * 100.0
    abs_gap = abs(gap_pct)
    gap_type = "up" if gap_pct >= 0 else "down"
    score = _score_gap(abs_gap)

    result = {
        "gap_pct": round(gap_pct, 2),
        "gap_type": gap_type,
        "base_price": round(base_price, 2),
        "gap_price": round(gap_price, 2),
        "timing_used": timing_lower,
        "score": score,
    }
    if timing_lower == "unknown":
        result["timing_note"] = (
            "timing unknown; AMC window assumed (BMO reporters may be "
            "measured on the wrong session pair)"
        )
    return result
