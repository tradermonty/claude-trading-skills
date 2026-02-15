#!/usr/bin/env python3
"""
Pivot Proximity Calculator - Breakout Distance & Risk Analysis

Calculates how close the current price is to the VCP pivot (breakout) point
and computes the risk profile for a potential trade.

Scoring by distance from pivot:
- Breakout confirmed (above pivot + volume): 100
- Within 2% below pivot:   90
- 2-5% below:              75
- 5-8% below:              60
- 8-10% below:             45
- 10-15% below:            30
- > 15% below:             10

Also calculates:
- Stop-loss price (below last contraction low)
- Risk % per share (entry to stop distance)
"""

from typing import Dict, List, Optional


def calculate_pivot_proximity(
    current_price: float,
    pivot_price: Optional[float],
    last_contraction_low: Optional[float] = None,
    breakout_volume: bool = False,
) -> Dict:
    """
    Calculate proximity to pivot point and risk metrics.

    Args:
        current_price: Current stock price
        pivot_price: The pivot (breakout) price from VCP pattern
        last_contraction_low: Low of the last contraction (for stop-loss)
        breakout_volume: Whether current volume is 1.5x+ above average

    Returns:
        Dict with score (0-100), distance_pct, stop_loss, risk_pct
    """
    if not pivot_price or pivot_price <= 0:
        return {
            "score": 0,
            "distance_from_pivot_pct": None,
            "stop_loss_price": None,
            "risk_pct": None,
            "trade_status": "NO PIVOT",
            "error": "No valid pivot price",
        }

    if current_price <= 0:
        return {
            "score": 0,
            "distance_from_pivot_pct": None,
            "stop_loss_price": None,
            "risk_pct": None,
            "trade_status": "INVALID PRICE",
            "error": "Invalid current price",
        }

    # Distance from pivot (negative = below pivot)
    distance_pct = (current_price - pivot_price) / pivot_price * 100

    # Determine trade status and score
    if distance_pct > 0 and breakout_volume:
        score = 100
        trade_status = "BREAKOUT CONFIRMED"
    elif distance_pct > 0:
        # Above pivot but without volume confirmation
        score = 85
        trade_status = "ABOVE PIVOT (no volume confirmation)"
    elif distance_pct >= -2:
        score = 90
        trade_status = "AT PIVOT (within 2%)"
    elif distance_pct >= -5:
        score = 75
        trade_status = "NEAR PIVOT (2-5% below)"
    elif distance_pct >= -8:
        score = 60
        trade_status = "APPROACHING (5-8% below)"
    elif distance_pct >= -10:
        score = 45
        trade_status = "DEVELOPING (8-10% below)"
    elif distance_pct >= -15:
        score = 30
        trade_status = "EARLY (10-15% below)"
    else:
        score = 10
        trade_status = "FAR FROM PIVOT (>15% below)"

    # Calculate stop-loss and risk
    stop_loss_price = None
    risk_pct = None

    if last_contraction_low and last_contraction_low > 0:
        # Stop-loss is 1-2% below the last contraction low
        stop_loss_price = round(last_contraction_low * 0.99, 2)

        # Risk per share from current price to stop
        if current_price > stop_loss_price:
            risk_pct = round((current_price - stop_loss_price) / current_price * 100, 2)
        else:
            # Price already below stop level
            risk_pct = 0
            trade_status = "BELOW STOP LEVEL"
            score = max(0, score - 20)

    return {
        "score": score,
        "distance_from_pivot_pct": round(distance_pct, 2),
        "pivot_price": round(pivot_price, 2),
        "stop_loss_price": stop_loss_price,
        "risk_pct": risk_pct,
        "trade_status": trade_status,
        "error": None,
    }
