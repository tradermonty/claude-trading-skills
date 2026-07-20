#!/usr/bin/env python3
"""
Component 1: BTC Trend Structure (Weight: 25%)

Bitcoin is the reserve asset of the crypto market: alt regimes almost never
stay risk-on while BTC trend structure is broken. This component scores the
health of BTC's primary trend using daily closes.

Input: list of BTC daily closes, oldest first (>= 220 observations for full
scoring; degrades gracefully below that).

Scoring (100 = healthy risk-on trend):
  Base score from price vs 50DMA / 200DMA structure:
    price > 50DMA > 200DMA (bull stack)      -> 90
    price > 200DMA, price < 50DMA (pullback) -> 65
    price < 50DMA and 50DMA > 200DMA         -> 55 (uses stack, price below both)
    price > 50DMA, price < 200DMA (recovery) -> 45
    price < 50DMA < 200DMA (bear stack)      -> 15

  200DMA slope modifier (20-day lookback):
    rising  -> +10
    flat    ->   0
    falling -> -10

  Cross proximity modifier:
    |50DMA - 200DMA| / 200DMA < 1.5% -> signal notes an imminent cross
    (no score change; informational)

An exactly flat price/MA structure is neutral (50), not a bear stack.
Score is clamped to [0, 100].
"""

import math

from numeric_utils import scaled_mean

SLOPE_LOOKBACK = 20
MIN_FULL_HISTORY = 200 + SLOPE_LOOKBACK
CROSS_PROXIMITY_PCT = 0.015
FLAT_REL_TOLERANCE = 1e-12


def _sma(values: list, window: int) -> float:
    return scaled_mean(values[-window:])


def calculate_btc_trend(closes: list) -> dict:
    """
    Score BTC primary trend structure.

    Args:
        closes: BTC daily closing prices sorted oldest -> newest.

    Returns:
        Dict with score, signal, data_available, and trend details.
    """
    if not closes or len(closes) < MIN_FULL_HISTORY:
        return {
            "score": 50,
            "signal": f"NO DATA: Need >= {MIN_FULL_HISTORY} daily closes for BTC trend structure",
            "data_available": False,
        }

    price = closes[-1]
    ma50 = _sma(closes, 50)
    ma200 = _sma(closes, 200)
    ma200_prev = scaled_mean(closes[-(200 + SLOPE_LOOKBACK) : -SLOPE_LOOKBACK])
    if math.isclose(ma200, ma200_prev, rel_tol=FLAT_REL_TOLERANCE, abs_tol=0.0):
        ma200_direction = "flat"
    elif ma200 > ma200_prev:
        ma200_direction = "rising"
    else:
        ma200_direction = "falling"
    ma200_rising = ma200_direction == "rising"

    is_flat_structure = all(
        math.isclose(value, ma200, rel_tol=FLAT_REL_TOLERANCE, abs_tol=0.0)
        for value in (price, ma50)
    )
    if is_flat_structure:
        base, structure = 50, "FLAT (price = 50DMA = 200DMA)"
    elif price > ma50 > ma200:
        base, structure = 90, "BULL STACK (price > 50DMA > 200DMA)"
    elif price > ma200 and price <= ma50 and ma50 > ma200:
        base, structure = 65, "BULL PULLBACK (price between 200DMA and 50DMA)"
    elif price <= ma200 and price <= ma50 and ma50 > ma200:
        base, structure = 55, "STACK INTACT, PRICE BELOW (deep pullback / early break)"
    elif price > ma50 and ma50 <= ma200:
        base, structure = 45, "RECOVERY ATTEMPT (price above 50DMA, stack still bearish)"
    else:
        base, structure = 15, "BEAR STACK (price < 50DMA < 200DMA)"

    slope_modifier = (
        10 if ma200_direction == "rising" else -10 if ma200_direction == "falling" else 0
    )
    score = base + slope_modifier
    score = max(0, min(100, score))

    signal = f"{structure}; 200DMA {ma200_direction}"
    if not is_flat_structure and ma200 > 0 and abs(ma50 - ma200) / ma200 < CROSS_PROXIMITY_PCT:
        cross = "golden cross" if ma50 <= ma200 and price > ma50 else "cross"
        signal += f"; 50/200DMA within 1.5% ({cross} watch)"

    return {
        "score": score,
        "signal": signal,
        "data_available": True,
        "price": round(price, 2),
        "ma50": round(ma50, 2),
        "ma200": round(ma200, 2),
        "ma200_rising": ma200_rising,
        "ma200_direction": ma200_direction,
    }
