#!/usr/bin/env python3
"""
Component 4: Perpetual Funding Regime (Weight: 15%)

Perp funding rates proxy aggregate leverage positioning. The scoring is
deliberately contrarian at the extremes and trend-friendly in the middle:

  Average 8h funding across tracked majors (annualized shown in signal):
    strongly negative (<= -0.010%)          -> 80  (washed out; shorts pay)
    mildly negative (-0.010% .. 0%)         -> 65  (skeptical positioning)
    neutral-positive (0% .. +0.010%)        -> 75  (healthy, near baseline)
    warm (+0.010% .. +0.030%)               -> 55  (leverage building)
    hot (+0.030% .. +0.060%)                -> 30  (crowded longs)
    extreme (> +0.060%)                     -> 10  (euphoric leverage;
                                                    liquidation-cascade risk)

Baseline note: Binance's default funding is +0.010% per 8h, so "neutral"
clusters slightly positive by construction.

Input: dict of {symbol: latest 8h funding rate as decimal} e.g.
{"BTCUSDT": 0.0001} for +0.010%. Rates outside [-1, 1] are rejected as
invalid data before averaging or annualizing.
"""

import math

from numeric_utils import MAX_ABS_FUNDING_RATE, scaled_mean

MIN_SYMBOLS = 2


def calculate_funding_regime(funding_map: dict) -> dict:
    """
    Score perp funding regime from latest 8h rates.

    Args:
        funding_map: {symbol: funding rate as decimal per 8h period}.

    Returns:
        Dict with score, signal, data_available, and funding details.
    """
    raw_rates = [rate for rate in (funding_map or {}).values() if rate is not None]
    invalid = [
        rate
        for rate in raw_rates
        if isinstance(rate, bool)
        or not isinstance(rate, (int, float))
        or not math.isfinite(rate)
        or abs(rate) > MAX_ABS_FUNDING_RATE
    ]
    if invalid:
        return {
            "score": 50,
            "signal": "INVALID DATA: funding rate must be finite and between -1 and 1",
            "data_available": False,
        }

    rates = raw_rates
    if len(rates) < MIN_SYMBOLS:
        return {
            "score": 50,
            "signal": f"NO DATA: Need funding for >= {MIN_SYMBOLS} symbols",
            "data_available": False,
        }

    avg = scaled_mean(rates)
    if avg <= -0.00010:
        score, label = 80, "WASHED OUT (negative funding; shorts paying longs)"
    elif avg < 0.0:
        score, label = 65, "SKEPTICAL (mildly negative funding)"
    elif avg <= 0.00010:
        score, label = 75, "NEUTRAL (funding near baseline)"
    elif avg <= 0.00030:
        score, label = 55, "WARMING (long leverage building)"
    elif avg <= 0.00060:
        score, label = 30, "CROWDED (hot funding; crowded longs)"
    else:
        score, label = 10, "EUPHORIC (extreme funding; cascade risk)"

    annualized = avg * 3 * 365 * 100
    return {
        "score": score,
        "signal": f"{label}; avg {avg * 100:.4f}%/8h "
        f"(~{annualized:.1f}% annualized) across {len(rates)} perps",
        "data_available": True,
        "avg_funding_8h": avg,
        "annualized_pct": round(annualized, 2),
        "n_symbols": len(rates),
    }
