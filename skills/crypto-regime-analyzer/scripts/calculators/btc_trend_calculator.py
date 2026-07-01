#!/usr/bin/env python3
"""
Component 1: BTC Trend Structure (Weight: 25%)

Bitcoin is the reserve asset of the crypto market: alt regimes almost never
stay risk-on while BTC trend structure is broken. This component scores the
health of BTC's primary trend using daily closes.

Input: list of BTC daily closes, oldest first (>= 210 observations for full
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
    falling -> -10

  Cross proximity modifier:
    |50DMA - 200DMA| / 200DMA < 1.5% -> signal notes an imminent cross
    (no score change; informational)

Score is clamped to [0, 100].
"""

MIN_FULL_HISTORY = 210
SLOPE_LOOKBACK = 20
CROSS_PROXIMITY_PCT = 0.015


def _sma(values: list, window: int) -> float:
    return sum(values[-window:]) / window


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
            "signal": "NO DATA: Need >= 210 daily closes for BTC trend structure",
            "data_available": False,
        }

    price = closes[-1]
    ma50 = _sma(closes, 50)
    ma200 = _sma(closes, 200)
    ma200_prev = sum(closes[-(200 + SLOPE_LOOKBACK) : -SLOPE_LOOKBACK]) / 200
    ma200_rising = ma200 > ma200_prev

    if price > ma50 > ma200:
        base, structure = 90, "BULL STACK (price > 50DMA > 200DMA)"
    elif price > ma200 and price <= ma50 and ma50 > ma200:
        base, structure = 65, "BULL PULLBACK (price between 200DMA and 50DMA)"
    elif price <= ma200 and price <= ma50 and ma50 > ma200:
        base, structure = 55, "STACK INTACT, PRICE BELOW (deep pullback / early break)"
    elif price > ma50 and ma50 <= ma200:
        base, structure = 45, "RECOVERY ATTEMPT (price above 50DMA, stack still bearish)"
    else:
        base, structure = 15, "BEAR STACK (price < 50DMA < 200DMA)"

    score = base + (10 if ma200_rising else -10)
    score = max(0, min(100, score))

    signal = f"{structure}; 200DMA {'rising' if ma200_rising else 'falling'}"
    if ma200 > 0 and abs(ma50 - ma200) / ma200 < CROSS_PROXIMITY_PCT:
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
    }
