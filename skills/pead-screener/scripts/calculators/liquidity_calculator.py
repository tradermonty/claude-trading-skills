#!/usr/bin/env python3
"""
Liquidity Calculator for PEAD Screener

Calculates liquidity metrics for position sizing feasibility.

Thresholds:
- ADV20 (20-day avg dollar volume) >= $25M
- Average volume >= 1M shares
- Price >= $10

Scoring (25% weight in composite):
- All 3 pass + ADV20 > $100M: 100
- All 3 pass + ADV20 > $50M:   85
- All 3 pass:                   70
- 2 of 3 pass:                  40
- 1 or 0 pass:                  15
"""

from price_bar_utils import require_bars


def calculate_liquidity(daily_prices: list[dict], current_price: float) -> dict:
    """
    Calculate liquidity metrics for position sizing feasibility.

    Args:
        daily_prices: Most-recent-first list of daily price dicts with
                      date, open, high, low, close, volume
        current_price: Current stock price

    Returns:
        {
            "adv20_dollar": float,   # 20-day average dollar volume
            "avg_volume_20d": float, # 20-day average share volume
            "price": float,
            "passes_all": bool,
            "score": float  # 0-100
        }
    """
    result = {
        "adv20_dollar": 0.0,
        "avg_volume_20d": 0.0,
        "price": current_price,
        "passes_all": False,
        "score": 15.0,
    }

    if not daily_prices or current_price <= 0:
        return result

    # Calculate 20-day average volume
    recent_20 = daily_prices[:20]
    require_bars(recent_20, ["close", "volume"])
    volumes = [d["volume"] for d in recent_20]
    if not volumes:
        return result

    avg_volume = sum(volumes) / len(volumes)
    result["avg_volume_20d"] = round(avg_volume, 0)

    # Calculate ADV20 (average dollar volume)
    dollar_volumes = []
    for d in recent_20:
        vol = d["volume"]
        close = d["close"]
        if vol > 0 and close > 0:
            dollar_volumes.append(vol * close)

    if dollar_volumes:
        adv20 = sum(dollar_volumes) / len(dollar_volumes)
    else:
        adv20 = avg_volume * current_price

    result["adv20_dollar"] = round(adv20, 0)

    # Check individual thresholds
    passes_adv20 = adv20 >= 25_000_000
    passes_volume = avg_volume >= 1_000_000
    passes_price = current_price >= 10.0

    passes_count = sum([passes_adv20, passes_volume, passes_price])
    result["passes_all"] = passes_count == 3

    # Score
    if passes_count == 3:
        if adv20 > 100_000_000:
            result["score"] = 100.0
        elif adv20 > 50_000_000:
            result["score"] = 85.0
        else:
            result["score"] = 70.0
    elif passes_count == 2:
        result["score"] = 40.0
    else:
        result["score"] = 15.0

    return result
