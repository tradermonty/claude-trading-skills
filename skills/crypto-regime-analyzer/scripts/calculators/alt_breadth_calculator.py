#!/usr/bin/env python3
"""
Component 2: Alt Breadth Participation (Weight: 20%)

Measures how broadly the altcoin market participates in the trend, the
crypto analog of "% of stocks above the 200DMA". Narrow markets (BTC up,
alts dead) are late-cycle or defensive; broad participation confirms
risk-on.

Input: dict of {symbol: [daily closes oldest -> newest]} for the tracked
alt universe (BTC excluded upstream). Coins with insufficient history are
skipped and reported.

Scoring (100 = broad participation):
  pct_above_200dma drives the base score:
    >= 80% -> 95    >= 65% -> 80    >= 50% -> 65
    >= 35% -> 45    >= 20% -> 25    <  20% -> 10

  50DMA confirmation modifier:
    pct_above_50dma >= pct_above_200dma + 15pts -> +5  (fresh thrust)
    pct_above_50dma <= pct_above_200dma - 15pts -> -5  (rolling over)
"""

MIN_HISTORY = 200
MIN_UNIVERSE = 5


def _pct_above_sma(series_map: dict, window: int) -> tuple:
    above, counted, skipped = 0, 0, []
    for symbol, closes in series_map.items():
        if not closes or len(closes) < window:
            skipped.append(symbol)
            continue
        counted += 1
        if closes[-1] > sum(closes[-window:]) / window:
            above += 1
    pct = (above / counted * 100) if counted else 0.0
    return pct, counted, skipped


def _base_score(pct_200: float) -> int:
    if pct_200 >= 80:
        return 95
    if pct_200 >= 65:
        return 80
    if pct_200 >= 50:
        return 65
    if pct_200 >= 35:
        return 45
    if pct_200 >= 20:
        return 25
    return 10


def calculate_alt_breadth(alt_series: dict) -> dict:
    """
    Score altcoin breadth participation.

    Args:
        alt_series: {symbol: [daily closes oldest -> newest]}.

    Returns:
        Dict with score, signal, data_available, and breadth details.
    """
    pct_200, counted, skipped = _pct_above_sma(alt_series or {}, MIN_HISTORY)
    if counted < MIN_UNIVERSE:
        return {
            "score": 50,
            "signal": f"NO DATA: Only {counted} alts with >= {MIN_HISTORY}d history "
            f"(need {MIN_UNIVERSE})",
            "data_available": False,
        }

    pct_50, _, _ = _pct_above_sma(alt_series, 50)
    score = _base_score(pct_200)
    modifier = ""
    if pct_50 >= pct_200 + 15:
        score += 5
        modifier = "; short-term thrust (50DMA breadth leading)"
    elif pct_50 <= pct_200 - 15:
        score -= 5
        modifier = "; short-term breadth rolling over"
    score = max(0, min(100, score))

    return {
        "score": score,
        "signal": f"{pct_200:.0f}% of {counted} tracked alts above 200DMA "
        f"({pct_50:.0f}% above 50DMA){modifier}",
        "data_available": True,
        "pct_above_200dma": round(pct_200, 1),
        "pct_above_50dma": round(pct_50, 1),
        "universe_size": counted,
        "skipped": skipped,
    }
