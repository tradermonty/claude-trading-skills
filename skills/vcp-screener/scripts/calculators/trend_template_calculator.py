#!/usr/bin/env python3
"""
Trend Template Calculator - Minervini's 7-Point Stage 2 Filter

Evaluates whether a stock meets Minervini's Stage 2 uptrend criteria.
This is the primary gate filter - stocks must pass this to be evaluated for VCP.

The 7-Point Trend Template:
1. Price > 150-day SMA AND Price > 200-day SMA
2. 150-day SMA > 200-day SMA
3. 200-day SMA trending up for at least 22 trading days (1 month)
4. Price > 50-day SMA
5. Price at least 25% above 52-week low
6. Price within 25% of 52-week high
7. Relative Strength rating > 70 (estimated)

Scoring: Each criterion = 14.3 points (7 x 14.3 = ~100)
Pass threshold: >= 85 (must meet at least 6 of 7 criteria)
"""

from typing import Dict, List, Optional


def calculate_trend_template(
    historical_prices: List[Dict],
    quote_data: Dict,
    rs_rank: Optional[int] = None,
    ext_threshold: float = 8.0,
) -> Dict:
    """
    Evaluate stock against Minervini's 7-point Trend Template.

    Args:
        historical_prices: Daily OHLCV data (most recent first), need 200+ days
        quote_data: Current quote with price, yearHigh, yearLow
        rs_rank: Pre-calculated RS rank estimate (0-99). If None, criterion 7 is skipped.

    Returns:
        Dict with score (0-100), criteria details, pass/fail status
    """
    if not historical_prices or len(historical_prices) < 50:
        return {
            "score": 0,
            "passed": False,
            "criteria": {},
            "error": "Insufficient historical data (need 50+ days)",
        }

    closes = [d.get("close", d.get("adjClose", 0)) for d in historical_prices]
    price = quote_data.get("price", closes[0] if closes else 0)
    year_high = quote_data.get("yearHigh", 0)
    year_low = quote_data.get("yearLow", 0)

    criteria = {}
    points_per_criterion = 14.3

    # Criterion 1: Price > SMA150 AND Price > SMA200
    sma150 = _sma(closes, 150)
    sma200 = _sma(closes, 200)
    c1_pass = False
    if sma150 is not None and sma200 is not None:
        c1_pass = price > sma150 and price > sma200
    elif sma150 is not None:
        c1_pass = price > sma150
    criteria["c1_price_above_sma150_200"] = {
        "passed": c1_pass,
        "detail": f"Price ${price:.2f} vs SMA150 ${sma150:.2f}" + (f" / SMA200 ${sma200:.2f}" if sma200 else ""),
    }

    # Criterion 2: SMA150 > SMA200
    c2_pass = False
    if sma150 is not None and sma200 is not None:
        c2_pass = sma150 > sma200
    criteria["c2_sma150_above_sma200"] = {
        "passed": c2_pass,
        "detail": f"SMA150 ${sma150:.2f} vs SMA200 ${sma200:.2f}" if sma150 and sma200 else "Insufficient data",
    }

    # Criterion 3: SMA200 trending up for 22+ trading days
    c3_pass = False
    if len(closes) >= 222 and sma200 is not None:
        sma200_22d_ago = _sma(closes[22:], 200)
        if sma200_22d_ago is not None:
            c3_pass = sma200 > sma200_22d_ago
            criteria["c3_sma200_trending_up"] = {
                "passed": c3_pass,
                "detail": f"SMA200 today ${sma200:.2f} vs 22d ago ${sma200_22d_ago:.2f}",
            }
        else:
            criteria["c3_sma200_trending_up"] = {
                "passed": False,
                "detail": "Insufficient data for 22d SMA200 comparison",
            }
    elif sma200 is not None and len(closes) >= 200:
        # Not enough data to compute SMA200 from 22 days ago - fail conservatively
        c3_pass = False
        criteria["c3_sma200_trending_up"] = {
            "passed": c3_pass,
            "detail": f"Cannot verify 22d SMA200 trend (only {len(closes)} days available, need 222+)",
        }
    else:
        criteria["c3_sma200_trending_up"] = {
            "passed": False,
            "detail": "Insufficient data",
        }

    # Criterion 4: Price > SMA50
    sma50 = _sma(closes, 50)
    c4_pass = False
    if sma50 is not None:
        c4_pass = price > sma50
    criteria["c4_price_above_sma50"] = {
        "passed": c4_pass,
        "detail": f"Price ${price:.2f} vs SMA50 ${sma50:.2f}" if sma50 else "Insufficient data",
    }

    # Criterion 5: Price at least 25% above 52-week low
    c5_pass = False
    if year_low > 0:
        pct_above_low = (price - year_low) / year_low * 100
        c5_pass = pct_above_low >= 25
        criteria["c5_25pct_above_52w_low"] = {
            "passed": c5_pass,
            "detail": f"{pct_above_low:.1f}% above 52w low ${year_low:.2f} (need >= 25%)",
        }
    else:
        criteria["c5_25pct_above_52w_low"] = {
            "passed": False,
            "detail": "52-week low data unavailable",
        }

    # Criterion 6: Price within 25% of 52-week high
    c6_pass = False
    if year_high > 0:
        pct_below_high = (year_high - price) / year_high * 100
        c6_pass = pct_below_high <= 25
        criteria["c6_within_25pct_52w_high"] = {
            "passed": c6_pass,
            "detail": f"{pct_below_high:.1f}% below 52w high ${year_high:.2f} (need <= 25%)",
        }
    else:
        criteria["c6_within_25pct_52w_high"] = {
            "passed": False,
            "detail": "52-week high data unavailable",
        }

    # Criterion 7: RS Rating > 70
    c7_pass = False
    if rs_rank is not None:
        c7_pass = rs_rank > 70
        criteria["c7_rs_rank_above_70"] = {
            "passed": c7_pass,
            "detail": f"RS Rank: {rs_rank} (need > 70)",
        }
    else:
        criteria["c7_rs_rank_above_70"] = {
            "passed": False,
            "detail": "RS Rank not yet calculated",
        }

    # Raw score from 7 criteria (gate判定用)
    passed_count = sum(1 for c in criteria.values() if c["passed"])
    raw_score = round(passed_count * points_per_criterion, 1)
    raw_score = min(100, raw_score)

    # Pass threshold: 85+ (6/7 criteria) - uses RAW score only
    passed = raw_score >= 85

    # Extended penalty: deduct for price too far above SMA50 (ranking用)
    extended_penalty, sma50_distance_pct = _calculate_extended_penalty(
        price, sma50, base_threshold=ext_threshold
    )
    score = max(0, raw_score + extended_penalty)

    return {
        "score": score,
        "raw_score": raw_score,
        "passed": passed,
        "extended_penalty": extended_penalty,
        "sma50_distance_pct": round(sma50_distance_pct, 2) if sma50_distance_pct is not None else None,
        "criteria_passed": passed_count,
        "criteria_total": 7,
        "criteria": criteria,
        "sma50": round(sma50, 2) if sma50 else None,
        "sma150": round(sma150, 2) if sma150 else None,
        "sma200": round(sma200, 2) if sma200 else None,
        "error": None,
    }


def _calculate_extended_penalty(
    price: float, sma50: Optional[float], base_threshold: float = 8.0
) -> tuple:
    """Calculate penalty for price extended too far above SMA 50.

    Args:
        price: Current stock price
        sma50: 50-day simple moving average
        base_threshold: Distance % where penalty starts (default 8.0)

    Returns:
        (penalty: int, distance_pct: float or None)
        penalty is 0 or negative.
    """
    if sma50 is None or sma50 <= 0:
        return 0, None

    distance_pct = (price - sma50) / sma50 * 100

    if distance_pct < base_threshold:
        return 0, distance_pct

    excess = distance_pct - base_threshold
    if excess >= 17:       # base+17% (default: 25%+)
        return -20, distance_pct
    elif excess >= 10:     # base+10% (default: 18%+)
        return -15, distance_pct
    elif excess >= 4:      # base+4%  (default: 12%+)
        return -10, distance_pct
    else:                  # base+0%  (default: 8%+)
        return -5, distance_pct


def _sma(prices: List[float], period: int) -> Optional[float]:
    """Calculate Simple Moving Average. Prices are most-recent-first."""
    if len(prices) < period:
        return None
    return sum(prices[:period]) / period
