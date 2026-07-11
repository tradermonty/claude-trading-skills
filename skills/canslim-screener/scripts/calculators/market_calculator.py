#!/usr/bin/env python3
"""
M Component - Market Direction Calculator

Calculates CANSLIM 'M' component score based on overall market trend.

O'Neil's Rule: "You can be right about a stock but wrong about the market,
and still lose money. Three out of four stocks follow the market's trend."

Scoring:
- 100: Strong uptrend (S&P 500 >2% above 50-EMA) + VIX <15
- 80: Uptrend (S&P 500 above 50-EMA) + VIX <20
- 60: Early uptrend (S&P 500 just above 50-EMA)
- 40: Choppy/neutral (S&P 500 near 50-EMA ±2%)
- 20: Downtrend forming (S&P 500 below 50-EMA)
- 0: Bear market (S&P 500 well below 50-EMA OR VIX >30) - DO NOT BUY
"""

from typing import Optional


def calculate_market_direction(
    sp500_quote: dict, sp500_prices: Optional[list[dict]] = None, vix_quote: Optional[dict] = None
) -> dict:
    """
    Calculate M component score based on S&P 500 trend and VIX

    Args:
        sp500_quote: S&P 500 quote data (symbol ^GSPC)
        sp500_prices: Optional historical prices for EMA calculation
        vix_quote: Optional VIX quote (symbol ^VIX)

    Returns:
        Dict with:
            - score: 0-100 points
            - trend: "strong_uptrend", "uptrend", "choppy", "downtrend", "bear_market"
            - sp500_price: Current S&P 500 level
            - sp500_ema_50: 50-day EMA (if calculated)
            - distance_from_ema_pct: Distance from 50-EMA (%)
            - vix_level: Current VIX level
            - interpretation: Human-readable interpretation
            - warning: Warning message if bear market (M=0)
    """
    # Validate input
    if not sp500_quote:
        return {
            "score": 50,  # Default to neutral if data unavailable
            "error": "S&P 500 quote data missing",
            "trend": "unknown",
            "interpretation": "Market data unavailable",
        }

    sp500_price = sp500_quote.get("price")
    if not sp500_price:
        return {
            "score": 50,
            "error": "S&P 500 price missing",
            "trend": "unknown",
            "interpretation": "Market data unavailable",
        }

    # Calculate 50-day EMA (requires real historical bars)
    sp500_ema_50 = None
    if sp500_prices and len(sp500_prices) >= 50:
        # Calculate from historical data
        close_prices = [day.get("close") for day in sp500_prices if day.get("close")]
        if len(close_prices) >= 50:
            sp500_ema_50 = calculate_ema(close_prices, period=50)

    if not sp500_ema_50:
        # Do not fabricate a trend when history is missing. Fabricating a fixed
        # -2% EMA offset would always trip the 'uptrend'/'strong_uptrend' branch,
        # inverting the safety purpose of the M component during a data outage.
        return {
            "score": 50,  # Neutral when trend cannot be determined
            "error": "Insufficient S&P 500 history for 50-day EMA",
            "trend": "unknown",
            "sp500_price": sp500_price,
            "sp500_ema_50": None,
            "interpretation": "Market trend unavailable - insufficient historical data",
        }

    # Calculate distance from EMA
    distance_from_ema_pct = ((sp500_price / sp500_ema_50) - 1) * 100 if sp500_ema_50 else 0

    # Get VIX level
    vix_level = None
    if vix_quote:
        vix_level = vix_quote.get("price")

    # Determine trend
    if distance_from_ema_pct >= 2.0:
        trend = "strong_uptrend"
    elif distance_from_ema_pct >= 0:
        trend = "uptrend"
    elif distance_from_ema_pct >= -2.0:
        trend = "choppy"
    elif distance_from_ema_pct >= -5.0:
        trend = "downtrend"
    else:
        trend = "bear_market"

    # Calculate score
    score = score_market_direction(trend, vix_level)

    # Generate interpretation
    interpretation = interpret_market_score(score, trend, distance_from_ema_pct, vix_level)

    # Warning for bear market
    warning = None
    if score == 0:
        warning = (
            "⚠️ BEAR MARKET - Do not buy stocks regardless of C, A, N scores. "
            "Raise 80-100% cash and wait for market recovery."
        )

    return {
        "score": score,
        "trend": trend,
        "sp500_price": sp500_price,
        "sp500_ema_50": sp500_ema_50,
        "distance_from_ema_pct": round(distance_from_ema_pct, 2),
        "vix_level": vix_level,
        "interpretation": interpretation,
        "warning": warning,
        "error": None,
    }


def calculate_ema(prices: list[float], period: int = 50) -> float:
    """
    Calculate Exponential Moving Average

    Args:
        prices: List of prices (most recent first)
        period: EMA period (default 50)

    Returns:
        EMA value

    Formula: EMA = Price * k + EMA_prev * (1-k), where k = 2/(period+1)
    """
    if len(prices) < period:
        return sum(prices) / len(prices)  # Fallback to simple average

    # Reverse to oldest-first for calculation
    prices_reversed = prices[::-1]

    # Initialize with SMA
    sma = sum(prices_reversed[:period]) / period
    ema = sma

    # Calculate EMA
    k = 2 / (period + 1)
    for price in prices_reversed[period:]:
        ema = price * k + ema * (1 - k)

    return ema


def score_market_direction(trend: str, vix_level: Optional[float]) -> int:
    """
    Score M component based on trend and VIX

    Args:
        trend: Market trend classification
        vix_level: Current VIX level

    Returns:
        Score (0-100)
    """
    # Base score from trend
    if trend == "strong_uptrend":
        base_score = 90
    elif trend == "uptrend":
        base_score = 70
    elif trend == "choppy":
        base_score = 40
    elif trend == "downtrend":
        base_score = 20
    else:  # bear_market
        base_score = 0

    # VIX adjustments
    if vix_level:
        if vix_level < 15:
            base_score += 10  # Low fear, bullish
        elif vix_level > 30:
            base_score = 0  # Panic mode - override trend

    return min(max(base_score, 0), 100)


def interpret_market_score(score: int, trend: str, distance: float, vix: Optional[float]) -> str:
    """
    Generate human-readable market interpretation

    Args:
        score: M component score
        trend: Trend classification
        distance: Distance from 50-EMA (%)
        vix: VIX level

    Returns:
        Interpretation string
    """
    vix_text = f", VIX {vix:.1f}" if vix else ""

    if score >= 90:
        return f"Strong bull market - Aggressive buying recommended (S&P 500 {distance:+.1f}% from 50-EMA{vix_text})"
    elif score >= 70:
        return f"Bull market - Standard position sizing (S&P 500 {distance:+.1f}% from 50-EMA{vix_text})"
    elif score >= 50:
        return f"Early uptrend - Small initial positions (S&P 500 {distance:+.1f}% from 50-EMA{vix_text})"
    elif score >= 30:
        return f"Choppy/neutral - Reduce exposure, be selective (S&P 500 {distance:+.1f}% from 50-EMA{vix_text})"
    elif score >= 10:
        return f"Downtrend forming - Defensive posture (S&P 500 {distance:+.1f}% from 50-EMA{vix_text})"
    else:
        return f"Bear market - Raise 80-100% cash, DO NOT BUY (S&P 500 {distance:+.1f}% from 50-EMA{vix_text})"


# Example usage
if __name__ == "__main__":
    print("Testing Market Calculator (M Component)...\n")

    # Test 1: Strong uptrend (score 100)
    test_sp500_1 = {"symbol": "^GSPC", "price": 4900}
    test_vix_1 = {"symbol": "^VIX", "price": 12.5}
    result1 = calculate_market_direction(test_sp500_1, vix_quote=test_vix_1)
    print(f"Test 1: Strong Uptrend - Score: {result1['score']}")
    print(f"  {result1['interpretation']}\n")

    # Test 2: Choppy market (score 40)
    test_sp500_2 = {"symbol": "^GSPC", "price": 4700}
    # EMA estimated at 4750 (price 1% below)
    test_vix_2 = {"symbol": "^VIX", "price": 18.0}
    result2 = calculate_market_direction(test_sp500_2, vix_quote=test_vix_2)
    print(f"Test 2: Choppy Market - Score: {result2['score']}")
    print(f"  {result2['interpretation']}\n")

    # Test 3: Bear market (score 0)
    test_sp500_3 = {"symbol": "^GSPC", "price": 4200}
    # EMA estimated at 4600 (price 8.7% below)
    test_vix_3 = {"symbol": "^VIX", "price": 32.0}
    result3 = calculate_market_direction(test_sp500_3, vix_quote=test_vix_3)
    print(f"Test 3: Bear Market - Score: {result3['score']}")
    print(f"  {result3['interpretation']}")
    if result3["warning"]:
        print(f"  {result3['warning']}\n")

    print("✓ All tests completed")
