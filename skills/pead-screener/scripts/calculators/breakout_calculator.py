#!/usr/bin/env python3
"""
Breakout Calculator for PEAD Screener

Determines breakout quality when the current weekly candle closes
above the red candle's high, confirming PEAD continuation.

Scoring (25% weight in composite):
- breakout_pct >= 3% with volume: 100
- breakout_pct >= 2% with volume: 85
- breakout_pct >= 1%:             70
- breakout_pct > 0%:              55
- No breakout:                     0
"""

from price_bar_utils import require_bars


def calculate_breakout(
    weekly_candles: list[dict],
    red_candle: dict,
    current_price: float,
) -> dict:
    """
    Determine breakout quality for a PEAD setup.

    Args:
        weekly_candles: Most-recent-first list of weekly candle dicts
        red_candle: Red candle dict from find_red_candle()
        current_price: Current stock price

    Returns:
        {
            "is_breakout": bool,
            "breakout_pct": float,  # distance above red candle high
            "volume_confirmation": bool,  # breakout week volume > avg
            "score": float  # 0-100
        }
    """
    result = {
        "is_breakout": False,
        "breakout_pct": 0.0,
        "volume_confirmation": False,
        "score": 0.0,
    }

    if not red_candle or not weekly_candles:
        return result

    red_high = red_candle["high"]
    if red_high <= 0:
        return result

    # Calculate breakout percentage
    breakout_pct = (current_price - red_high) / red_high * 100
    result["breakout_pct"] = round(breakout_pct, 2)

    if breakout_pct <= 0:
        result["is_breakout"] = False
        result["score"] = 0.0
        return result

    result["is_breakout"] = True

    # Check volume confirmation on the current (breakout) week
    current_candle = weekly_candles[0]
    volume_confirmed = _check_volume_confirmation(weekly_candles, current_candle)
    result["volume_confirmation"] = volume_confirmed

    # Score based on breakout percentage and volume
    if breakout_pct >= 3.0 and volume_confirmed:
        result["score"] = 100.0
    elif breakout_pct >= 2.0 and volume_confirmed:
        result["score"] = 85.0
    elif breakout_pct >= 1.0:
        result["score"] = 70.0
    else:
        result["score"] = 55.0

    return result


def _check_volume_confirmation(weekly_candles: list[dict], current_candle: dict) -> bool:
    """Check if the breakout week's volume is above the 4-week average.

    Args:
        weekly_candles: Most-recent-first weekly candle list
        current_candle: The current (breakout) week candle

    Returns:
        True if current volume > average of prior 4 weeks
    """
    if len(weekly_candles) < 2:
        return False

    require_bars(weekly_candles[:5], ["volume"], date_key="week_start")

    # Calculate average volume of prior 4 weeks (indices 1-4)
    prior_volumes = []
    for i in range(1, min(5, len(weekly_candles))):
        vol = weekly_candles[i]["volume"]
        if vol > 0:
            prior_volumes.append(vol)

    if not prior_volumes:
        return False

    avg_volume = sum(prior_volumes) / len(prior_volumes)
    return current_candle["volume"] > avg_volume
