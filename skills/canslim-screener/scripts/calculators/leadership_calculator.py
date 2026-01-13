#!/usr/bin/env python3
"""
L Component - Leadership / Relative Strength Calculator

Calculates CANSLIM 'L' component score based on relative price performance vs market.

O'Neil's Rule: "The top-performing stocks, prior to major advances, have Relative Strength
Ratings averaging 87 at pivot points. You want to see 80+ RS Rank - meaning the stock is
outperforming 80% of all other stocks over the past 52 weeks."

Key Principles:
- RS Rank 90+: Market leader, top 10% performer
- RS Rank 80-89: Strong performer, top 20%
- RS Rank 70-79: Above average, top 30%
- RS Rank 60-69: Average performer
- RS Rank <60: Laggard, underperforming majority

Implementation Note:
Since IBD's official RS Rank is proprietary, we estimate RS using:
1. 52-week price performance vs S&P 500
2. Sector-relative performance (optional enhancement)

Scoring:
- 100 points: Relative outperformance > +30% vs S&P 500 (market leader)
- 90 points: Relative outperformance +20% to +30%
- 80 points: Relative outperformance +10% to +20% (strong)
- 60 points: Relative outperformance 0% to +10% (above average)
- 40 points: Relative performance -10% to 0% (lagging)
- 20 points: Relative performance -20% to -10% (weak)
- 0 points: Relative underperformance > -20% (avoid)
"""

from typing import Dict, List, Optional


def calculate_leadership(
    historical_prices: List[Dict],
    sp500_historical: Optional[List[Dict]] = None,
    sp500_performance: Optional[float] = None
) -> Dict:
    """
    Calculate Leadership/Relative Strength score (L component)

    Args:
        historical_prices: List of daily price data for the stock (oldest to newest)
                          Each entry: {"date": str, "close": float, "volume": int}
        sp500_historical: Optional list of S&P 500 daily prices (for RS calculation)
        sp500_performance: Optional pre-calculated S&P 500 52-week performance (%)

    Returns:
        Dict with:
            - score: 0-100 points
            - stock_52w_performance: Stock's 52-week return (%)
            - sp500_52w_performance: S&P 500's 52-week return (%)
            - relative_performance: Stock return - S&P 500 return (%)
            - rs_rank_estimate: Estimated RS Rank (0-99)
            - interpretation: Human-readable interpretation
            - quality_warning: Warning if data quality issues
            - error: Error message if calculation failed

    Example:
        >>> prices = client.get_historical_prices("NVDA", days=365)
        >>> sp500 = client.get_historical_prices("SPY", days=365)
        >>> result = calculate_leadership(prices, sp500)
        >>> print(f"L Score: {result['score']}, RS Estimate: {result['rs_rank_estimate']}")
    """
    # Validate input
    if not historical_prices or len(historical_prices) < 50:
        return {
            "score": 0,
            "error": "Insufficient historical price data (need 50+ days)",
            "stock_52w_performance": None,
            "sp500_52w_performance": None,
            "relative_performance": None,
            "rs_rank_estimate": None,
            "interpretation": "Data unavailable"
        }

    # Calculate stock's 52-week (or available period) performance
    # Prices should be sorted oldest to newest
    try:
        # Get start and end prices (handle both orderings)
        if historical_prices[0].get("date", "") < historical_prices[-1].get("date", ""):
            # Oldest first (ascending)
            start_price = historical_prices[0].get("close", 0)
            end_price = historical_prices[-1].get("close", 0)
        else:
            # Newest first (descending)
            start_price = historical_prices[-1].get("close", 0)
            end_price = historical_prices[0].get("close", 0)

        if start_price <= 0:
            return {
                "score": 0,
                "error": "Invalid start price (zero or negative)",
                "stock_52w_performance": None,
                "sp500_52w_performance": None,
                "relative_performance": None,
                "rs_rank_estimate": None,
                "interpretation": "Data quality issue"
            }

        stock_performance = ((end_price - start_price) / start_price) * 100
        days_analyzed = len(historical_prices)

    except (KeyError, TypeError, ZeroDivisionError) as e:
        return {
            "score": 0,
            "error": f"Price calculation error: {str(e)}",
            "stock_52w_performance": None,
            "sp500_52w_performance": None,
            "relative_performance": None,
            "rs_rank_estimate": None,
            "interpretation": "Calculation error"
        }

    # Calculate S&P 500 performance for comparison
    sp500_perf = None
    quality_warning = None

    if sp500_performance is not None:
        # Use pre-calculated S&P 500 performance
        sp500_perf = sp500_performance
    elif sp500_historical and len(sp500_historical) >= 50:
        # Calculate from provided S&P 500 data
        try:
            if sp500_historical[0].get("date", "") < sp500_historical[-1].get("date", ""):
                sp500_start = sp500_historical[0].get("close", 0)
                sp500_end = sp500_historical[-1].get("close", 0)
            else:
                sp500_start = sp500_historical[-1].get("close", 0)
                sp500_end = sp500_historical[0].get("close", 0)

            if sp500_start > 0:
                sp500_perf = ((sp500_end - sp500_start) / sp500_start) * 100
        except (KeyError, TypeError, ZeroDivisionError):
            quality_warning = "S&P 500 performance calculation failed"
    else:
        quality_warning = "S&P 500 data unavailable - using absolute performance only"

    # Calculate relative performance
    if sp500_perf is not None:
        relative_performance = stock_performance - sp500_perf
    else:
        # Fallback: use absolute performance with penalty
        relative_performance = stock_performance
        if quality_warning is None:
            quality_warning = "Using absolute performance (S&P 500 comparison unavailable)"

    # Score based on relative performance
    score, rs_rank_estimate = score_leadership(relative_performance, sp500_perf is not None)

    # Generate interpretation
    interpretation = interpret_leadership(
        score, stock_performance, sp500_perf, relative_performance, days_analyzed
    )

    return {
        "score": score,
        "stock_52w_performance": round(stock_performance, 2),
        "sp500_52w_performance": round(sp500_perf, 2) if sp500_perf is not None else None,
        "relative_performance": round(relative_performance, 2),
        "rs_rank_estimate": rs_rank_estimate,
        "days_analyzed": days_analyzed,
        "interpretation": interpretation,
        "quality_warning": quality_warning,
        "error": None
    }


def score_leadership(relative_performance: float, has_benchmark: bool) -> tuple:
    """
    Score leadership based on relative performance

    Args:
        relative_performance: Stock performance minus S&P 500 performance (%)
        has_benchmark: True if S&P 500 comparison was available

    Returns:
        tuple: (score, rs_rank_estimate)
    """
    # Scoring thresholds for relative performance
    if relative_performance >= 50:
        score = 100
        rs_rank_estimate = 99  # Top 1%
    elif relative_performance >= 30:
        score = 95
        rs_rank_estimate = 95  # Top 5%
    elif relative_performance >= 20:
        score = 90
        rs_rank_estimate = 90  # Top 10%
    elif relative_performance >= 10:
        score = 80
        rs_rank_estimate = 80  # Top 20%
    elif relative_performance >= 5:
        score = 70
        rs_rank_estimate = 70  # Top 30%
    elif relative_performance >= 0:
        score = 60
        rs_rank_estimate = 60  # Top 40%
    elif relative_performance >= -5:
        score = 50
        rs_rank_estimate = 50  # Average
    elif relative_performance >= -10:
        score = 40
        rs_rank_estimate = 40  # Below average
    elif relative_performance >= -20:
        score = 20
        rs_rank_estimate = 25  # Weak
    else:
        score = 0
        rs_rank_estimate = 10  # Laggard

    # Apply penalty if no benchmark comparison available
    if not has_benchmark:
        score = int(score * 0.8)  # 20% penalty for absolute-only comparison
        rs_rank_estimate = int(rs_rank_estimate * 0.9)

    return score, rs_rank_estimate


def interpret_leadership(
    score: int,
    stock_performance: float,
    sp500_performance: Optional[float],
    relative_performance: float,
    days_analyzed: int
) -> str:
    """
    Generate human-readable interpretation

    Args:
        score: Leadership score (0-100)
        stock_performance: Stock's period return (%)
        sp500_performance: S&P 500's period return (%)
        relative_performance: Stock - S&P 500 (%)
        days_analyzed: Number of days analyzed

    Returns:
        str: Interpretation string
    """
    # Period description
    if days_analyzed >= 250:
        period = "52-week"
    elif days_analyzed >= 180:
        period = "9-month"
    elif days_analyzed >= 90:
        period = "quarterly"
    else:
        period = f"{days_analyzed}-day"

    # Performance description
    if stock_performance > 0:
        stock_msg = f"+{stock_performance:.1f}%"
    else:
        stock_msg = f"{stock_performance:.1f}%"

    # Relative performance description
    if sp500_performance is not None:
        if relative_performance > 0:
            rel_msg = f"+{relative_performance:.1f}% vs S&P 500"
        else:
            rel_msg = f"{relative_performance:.1f}% vs S&P 500"
    else:
        rel_msg = "(absolute performance)"

    # Rating based on score
    if score >= 90:
        rating = "Market Leader"
        action = "Strong momentum, prime CANSLIM candidate"
    elif score >= 80:
        rating = "Strong Performer"
        action = "Outperforming market significantly"
    elif score >= 60:
        rating = "Above Average"
        action = "Slight outperformance"
    elif score >= 40:
        rating = "Average"
        action = "Matching or slightly lagging market"
    elif score >= 20:
        rating = "Laggard"
        action = "Underperforming market - caution"
    else:
        rating = "Weak"
        action = "Significant underperformance - avoid"

    return f"{rating} - {period} return {stock_msg} ({rel_msg}). {action}"


def calculate_sector_relative_strength(
    stock_performance: float,
    sector_stocks_performance: List[float]
) -> Dict:
    """
    Calculate relative strength within sector (optional enhancement)

    Args:
        stock_performance: Target stock's period return (%)
        sector_stocks_performance: List of sector peers' period returns (%)

    Returns:
        Dict with:
            - sector_rank: Stock's rank within sector (1 = best)
            - sector_percentile: Percentile within sector (0-100)
            - is_sector_leader: True if top 20% in sector
    """
    if not sector_stocks_performance:
        return {
            "sector_rank": None,
            "sector_percentile": None,
            "is_sector_leader": False,
            "error": "No sector data available"
        }

    # Add stock to list and sort (descending)
    all_stocks = sector_stocks_performance + [stock_performance]
    all_stocks_sorted = sorted(all_stocks, reverse=True)

    # Find rank
    rank = all_stocks_sorted.index(stock_performance) + 1
    total = len(all_stocks)
    percentile = ((total - rank) / total) * 100

    return {
        "sector_rank": rank,
        "sector_total": total,
        "sector_percentile": round(percentile, 1),
        "is_sector_leader": percentile >= 80
    }


# Example usage
if __name__ == "__main__":
    print("Testing Leadership Calculator (L Component)...")
    print()

    # Test 1: Strong outperformer
    sample_prices = [
        {"date": "2024-01-01", "close": 100.0},
        {"date": "2024-06-01", "close": 120.0},
        {"date": "2025-01-01", "close": 180.0}  # +80% YoY
    ]
    sample_sp500 = [
        {"date": "2024-01-01", "close": 4500.0},
        {"date": "2024-06-01", "close": 4700.0},
        {"date": "2025-01-01", "close": 5400.0}  # +20% YoY
    ]

    result = calculate_leadership(sample_prices, sample_sp500)
    print("Test 1: Strong Outperformer (+80% stock vs +20% S&P)")
    print(f"  Stock Performance: {result['stock_52w_performance']}%")
    print(f"  S&P 500 Performance: {result['sp500_52w_performance']}%")
    print(f"  Relative Performance: {result['relative_performance']}%")
    print(f"  L Score: {result['score']}/100")
    print(f"  RS Rank Estimate: {result['rs_rank_estimate']}")
    print(f"  Interpretation: {result['interpretation']}")
    print()

    # Test 2: Underperformer
    sample_prices_weak = [
        {"date": "2024-01-01", "close": 100.0},
        {"date": "2025-01-01", "close": 90.0}  # -10% YoY
    ]

    result2 = calculate_leadership(sample_prices_weak, sample_sp500)
    print("Test 2: Underperformer (-10% stock vs +20% S&P)")
    print(f"  Stock Performance: {result2['stock_52w_performance']}%")
    print(f"  Relative Performance: {result2['relative_performance']}%")
    print(f"  L Score: {result2['score']}/100")
    print(f"  Interpretation: {result2['interpretation']}")
    print()

    # Test 3: Without S&P 500 data (fallback)
    result3 = calculate_leadership(sample_prices)
    print("Test 3: Without S&P 500 Data (Fallback)")
    print(f"  L Score: {result3['score']}/100 (20% penalty applied)")
    print(f"  Warning: {result3['quality_warning']}")
    print()

    print("✓ All tests completed")
