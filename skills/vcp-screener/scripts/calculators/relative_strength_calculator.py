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

from price_bar_utils import find_close_gaps, read_close, unavailable_component

# Minervini weighting periods (trading days) and weights
RS_PERIODS = [
    (63, 0.40),  # 3 months - 40%
    (126, 0.20),  # 6 months - 20%
    (189, 0.20),  # 9 months - 20%
    (252, 0.20),  # 12 months - 20%
]


def calculate_relative_strength(
    stock_prices: list[dict],
    sp500_prices: list[dict],
) -> dict:
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

    available = min(len(stock_prices), len(sp500_prices)) - 1
    endpoints = {0}
    for period_days, _weight in RS_PERIODS:
        if available >= period_days:
            endpoints.add(period_days)
        elif available >= period_days // 2:
            endpoints.add(available)
    for source, bars in [("stock", stock_prices), ("benchmark", sp500_prices)]:
        gaps = find_close_gaps(bars, endpoints)
        if gaps["bad_bars"]:
            gaps["source"] = source
            return unavailable_component(gaps, rs_rank_estimate=0, weighted_rs=None)

    stock_closes = [read_close(d) for d in stock_prices]
    sp500_closes = [read_close(d) for d in sp500_prices]

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

            period_details.append(
                {
                    "period_days": period_days,
                    "weight": weight,
                    "stock_return_pct": round(stock_return, 2),
                    "sp500_return_pct": round(sp500_return, 2),
                    "relative_pct": round(relative, 2),
                }
            )
        elif len(stock_closes) > period_days // 2 and len(sp500_closes) > period_days // 2:
            # Partial data: use available days with reduced weight
            available = min(len(stock_closes) - 1, len(sp500_closes) - 1)
            stock_return = _period_return(stock_closes, available)
            sp500_return = _period_return(sp500_closes, available)
            relative = stock_return - sp500_return
            reduced_weight = weight * 0.5

            weighted_rs += relative * reduced_weight
            total_weight += reduced_weight

            period_details.append(
                {
                    "period_days": period_days,
                    "weight": reduced_weight,
                    "stock_return_pct": round(stock_return, 2),
                    "sp500_return_pct": round(sp500_return, 2),
                    "relative_pct": round(relative, 2),
                    "note": f"Partial data ({available} days available)",
                }
            )

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


def _period_return(closes: list[float], period: int) -> float:
    """Calculate return over period. Closes are most-recent-first."""
    return ((closes[0] - closes[period]) / closes[period]) * 100


def rank_relative_strength_universe(rs_results: dict[str, dict]) -> dict[str, dict]:
    """Rank all candidates by weighted_rs and assign percentile-based scores.

    Stocks with weighted_rs=None are excluded from percentile ranking and
    assigned score=0, rs_percentile=0. Small populations (fewer than
    MIN_POPULATION_FOR_FULL_SCORE valid stocks) have their scores capped
    to prevent inflated rankings.

    Args:
        rs_results: {symbol: {score, weighted_rs, ...}} for each candidate

    Returns:
        Updated dict with rs_percentile and recalculated score for each symbol
    """
    if not rs_results:
        return {}

    # Separate valid (weighted_rs is not None) from invalid
    valid_symbols = [s for s in rs_results if rs_results[s].get("weighted_rs") is not None]
    invalid_symbols = [s for s in rs_results if rs_results[s].get("weighted_rs") is None]

    # Handle invalid stocks: score=0, rs_percentile=0
    result = {}
    for sym in invalid_symbols:
        updated = dict(rs_results[sym])
        updated["rs_percentile"] = 0
        updated["score"] = 0
        result[sym] = updated

    if not valid_symbols:
        return result

    # Sort valid symbols by weighted_rs
    valid_symbols.sort(key=lambda s: rs_results[s]["weighted_rs"])

    n = len(valid_symbols)
    # Assign percentiles (handle ties by giving same percentile)
    percentiles = {}
    i = 0
    while i < n:
        current_val = rs_results[valid_symbols[i]]["weighted_rs"]
        j = i + 1
        while j < n and rs_results[valid_symbols[j]]["weighted_rs"] == current_val:
            j += 1
        pct = int(round(j / n * 100))
        for k in range(i, j):
            percentiles[valid_symbols[k]] = pct
        i = j

    # Small population cap: with fewer valid stocks, cap score and percentile
    max_score = _small_population_max_score(n)
    max_percentile = _score_to_max_percentile(max_score)

    for sym in valid_symbols:
        updated = dict(rs_results[sym])
        capped_pct = min(percentiles[sym], max_percentile)
        updated["rs_percentile"] = capped_pct
        updated["score"] = _percentile_to_score(capped_pct)
        result[sym] = updated

    return result


# Minimum population for unrestricted percentile scoring
MIN_POPULATION_FOR_FULL_SCORE = 20


def _small_population_max_score(n: int) -> int:
    """Cap maximum RS score when population is too small for reliable percentiles."""
    if n >= MIN_POPULATION_FOR_FULL_SCORE:
        return 100
    if n >= 10:
        return 90
    if n >= 5:
        return 80
    return 70


def _score_to_max_percentile(max_score: int) -> int:
    """Return the highest percentile that maps to max_score via _percentile_to_score.

    This ensures rs_percentile and score stay consistent when capped.
    """
    if max_score >= 100:
        return 100
    if max_score >= 90:
        return 94  # _percentile_to_score(94) == 90
    if max_score >= 80:
        return 84  # _percentile_to_score(84) == 80
    if max_score >= 70:
        return 74  # _percentile_to_score(74) == 70
    if max_score >= 60:
        return 59
    if max_score >= 50:
        return 44
    if max_score >= 40:
        return 29
    return 14


def _percentile_to_score(percentile: int) -> int:
    """Map percentile rank to RS score."""
    if percentile >= 95:
        return 100
    elif percentile >= 85:
        return 90
    elif percentile >= 75:
        return 80
    elif percentile >= 60:
        return 70
    elif percentile >= 45:
        return 60
    elif percentile >= 30:
        return 50
    elif percentile >= 15:
        return 40
    else:
        return 20


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
