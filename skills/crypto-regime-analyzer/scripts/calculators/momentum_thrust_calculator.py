#!/usr/bin/env python3
"""
Component 6: Momentum Thrust / Washout (Weight: 10%)

Short-horizon confirmation: what share of the tracked universe (BTC +
alts) has a positive trailing 30d return. Extremes in either direction
are informative — broad positive momentum confirms risk-on, while
near-total negative momentum marks washouts that often precede
mean-reversion bounces.

Input: dict of {symbol: [daily closes oldest -> newest]}, >= 31 obs each.

Scoring:
  pct with positive 30d return:
    >= 85% -> 90 (broad thrust)
    >= 65% -> 75
    >= 45% -> 55
    >= 25% -> 35
    >= 10% -> 20
    <  10% -> 35 (washout: contrarian bump vs the 20 a plain mapping gives)
"""

LOOKBACK = 30
MIN_UNIVERSE = 5


def calculate_momentum_thrust(series_map: dict) -> dict:
    """
    Score universe 30d momentum breadth.

    Args:
        series_map: {symbol: [daily closes oldest -> newest]}.

    Returns:
        Dict with score, signal, data_available, and momentum details.
    """
    positive, counted = 0, 0
    for closes in (series_map or {}).values():
        if not closes or len(closes) < LOOKBACK + 1:
            continue
        counted += 1
        if closes[-1] > closes[-(LOOKBACK + 1)]:
            positive += 1

    if counted < MIN_UNIVERSE:
        return {
            "score": 50,
            "signal": f"NO DATA: Only {counted} coins with >= {LOOKBACK + 1}d history",
            "data_available": False,
        }

    pct = positive / counted * 100
    if pct >= 85:
        score, label = 90, "BROAD THRUST"
    elif pct >= 65:
        score, label = 75, "POSITIVE"
    elif pct >= 45:
        score, label = 55, "MIXED"
    elif pct >= 25:
        score, label = 35, "WEAK"
    elif pct >= 10:
        score, label = 20, "BROADLY NEGATIVE"
    else:
        score, label = 35, "WASHOUT (contrarian: near-total negative momentum)"

    return {
        "score": score,
        "signal": f"{label}: {pct:.0f}% of {counted} coins positive over {LOOKBACK}d",
        "data_available": True,
        "pct_positive_30d": round(pct, 1),
        "universe_size": counted,
    }
