#!/usr/bin/env python3
"""
Relative Strength Calculator - Minervini Weighted RS

Calculates relative price performance vs S&P 500 using Minervini's weighting:
- 40% weight: Last 3 months (63 trading days)
- 20% weight: Last 6 months (126 trading days)
- 20% weight: Last 9 months (189 trading days)
- 20% weight: Last 12 months (252 trading days)

This emphasizes recent momentum more than a simple 52-week calculation.

Scoring:
- 100: Weighted RS outperformance >= +50% (top 1%)
- 95:  >= +30% (top 5%)
- 90:  >= +20% (top 10%)
- 80:  >= +10% (top 20%)
- 70:  >= +5% (top 30%)
- 60:  >= 0% (top 40%)
- 50:  >= -5% (average)
- 40:  >= -10% (below average)
- 20:  >= -20% (weak)
- 0:   < -20% (laggard)
"""

from typing import Dict, List, Optional


# Minervini weighting periods (trading days) and weights
RS_PERIODS = [
    (63, 0.40),   # 3 months - 40%
    (126, 0.20),  # 6 months - 20%
    (189, 0.20),  # 9 months - 20%
    (252, 0.20),  # 12 months - 20%
]


def calculate_relative_strength(
    stock_prices: List[Dict],
    sp500_prices: List[Dict],
) -> Dict:
    """
    Calculate Minervini-weighted relative strength vs S&P 500.

    Args:
        stock_prices: Daily OHLCV for stock (most recent first), need 252+ days
        sp500_prices: Daily OHLCV for SPY (most recent first), need 252+ days

    Returns:
        Dict with score (0-100), rs_rank_estimate, weighted_rs, period details
    """
    if not stock_prices or len(stock_prices) < 63:
        return {
            "score": 0,
            "rs_rank_estimate": 0,
            "weighted_rs": None,
            "error": "Insufficient stock price data (need 63+ days)",
        }

    if not sp500_prices or len(sp500_prices) < 63:
        return {
            "score": 0,
            "rs_rank_estimate": 0,
            "weighted_rs": None,
            "error": "Insufficient S&P 500 price data (need 63+ days)",
        }

    stock_closes = [d.get("close", d.get("adjClose", 0)) for d in stock_prices]
    sp500_closes = [d.get("close", d.get("adjClose", 0)) for d in sp500_prices]

    weighted_rs = 0.0
    total_weight = 0.0
    period_details = []

    for period_days, weight in RS_PERIODS:
        if len(stock_closes) > period_days and len(sp500_closes) > period_days:
            stock_return = _period_return(stock_closes, period_days)
            sp500_return = _period_return(sp500_closes, period_days)
            relative = stock_return - sp500_return

            weighted_rs += relative * weight
            total_weight += weight

            period_details.append({
                "period_days": period_days,
                "weight": weight,
                "stock_return_pct": round(stock_return, 2),
                "sp500_return_pct": round(sp500_return, 2),
                "relative_pct": round(relative, 2),
            })
        elif len(stock_closes) > period_days // 2 and len(sp500_closes) > period_days // 2:
            # Partial data: use available days with reduced weight
            available = min(len(stock_closes) - 1, len(sp500_closes) - 1)
            stock_return = _period_return(stock_closes, available)
            sp500_return = _period_return(sp500_closes, available)
            relative = stock_return - sp500_return
            reduced_weight = weight * 0.5

            weighted_rs += relative * reduced_weight
            total_weight += reduced_weight

            period_details.append({
                "period_days": period_days,
                "weight": reduced_weight,
                "stock_return_pct": round(stock_return, 2),
                "sp500_return_pct": round(sp500_return, 2),
                "relative_pct": round(relative, 2),
                "note": f"Partial data ({available} days available)",
            })

    if total_weight > 0:
        weighted_rs = weighted_rs / total_weight
    else:
        return {
            "score": 0,
            "rs_rank_estimate": 0,
            "weighted_rs": None,
            "error": "Unable to calculate weighted RS (insufficient overlapping data)",
        }

    # Score based on weighted relative performance
    score, rs_rank = _score_rs(weighted_rs)

    return {
        "score": score,
        "rs_rank_estimate": rs_rank,
        "weighted_rs": round(weighted_rs, 2),
        "period_details": period_details,
        "error": None,
    }


def _period_return(closes: List[float], period: int) -> float:
    """Calculate return over period. Closes are most-recent-first."""
    if len(closes) <= period or closes[period] <= 0:
        return 0.0
    return ((closes[0] - closes[period]) / closes[period]) * 100


def _score_rs(weighted_rs: float) -> tuple:
    """Score based on weighted relative strength."""
    if weighted_rs >= 50:
        return 100, 99
    elif weighted_rs >= 30:
        return 95, 95
    elif weighted_rs >= 20:
        return 90, 90
    elif weighted_rs >= 10:
        return 80, 80
    elif weighted_rs >= 5:
        return 70, 70
    elif weighted_rs >= 0:
        return 60, 60
    elif weighted_rs >= -5:
        return 50, 50
    elif weighted_rs >= -10:
        return 40, 40
    elif weighted_rs >= -20:
        return 20, 25
    else:
        return 0, 10
