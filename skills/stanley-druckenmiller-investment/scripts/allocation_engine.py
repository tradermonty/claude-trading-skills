#!/usr/bin/env python3
"""
Strategy Synthesizer - Allocation Engine

Generates target asset allocation based on conviction score, pattern,
and macro regime. Provides position sizing guidance.

Asset classes: equity, bonds, alternatives (gold/commodities), cash
All allocations sum to 100%.
"""

from typing import Dict


# ---------------------------------------------------------------------------
# Base allocations by conviction zone (sum to 100%)
# ---------------------------------------------------------------------------

ZONE_BASE_ALLOCATIONS = {
    "Maximum Conviction": {
        "equity": 90,
        "bonds": 0,
        "alternatives": 5,
        "cash": 5,
    },
    "High Conviction": {
        "equity": 75,
        "bonds": 5,
        "alternatives": 5,
        "cash": 15,
    },
    "Moderate Conviction": {
        "equity": 55,
        "bonds": 10,
        "alternatives": 10,
        "cash": 25,
    },
    "Low Conviction": {
        "equity": 30,
        "bonds": 15,
        "alternatives": 15,
        "cash": 40,
    },
    "Capital Preservation": {
        "equity": 10,
        "bonds": 20,
        "alternatives": 20,
        "cash": 50,
    },
}

# ---------------------------------------------------------------------------
# Regime adjustments (additive shifts)
# ---------------------------------------------------------------------------

REGIME_ADJUSTMENTS = {
    "broadening": {"equity": +5, "bonds": 0, "alternatives": 0, "cash": -5},
    "concentration": {"equity": +3, "bonds": 0, "alternatives": 0, "cash": -3},
    "transitional": {"equity": 0, "bonds": 0, "alternatives": 0, "cash": 0},
    "inflationary": {"equity": -5, "bonds": -5, "alternatives": +10, "cash": 0},
    "contraction": {"equity": -10, "bonds": +5, "alternatives": 0, "cash": +5},
}

# ---------------------------------------------------------------------------
# Pattern adjustments (additive shifts)
# ---------------------------------------------------------------------------

PATTERN_ADJUSTMENTS = {
    "policy_pivot_anticipation": {"equity": +5, "bonds": +3, "alternatives": -3, "cash": -5},
    "unsustainable_distortion": {"equity": -10, "bonds": 0, "alternatives": +5, "cash": +5},
    "extreme_sentiment_contrarian": {"equity": +10, "bonds": -5, "alternatives": 0, "cash": -5},
    "wait_and_observe": {"equity": -5, "bonds": 0, "alternatives": 0, "cash": +5},
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_allocation(
    conviction_score: float,
    zone: str,
    pattern: str,
    regime: str,
) -> Dict:
    """
    Generate target allocation based on conviction, pattern, and regime.

    Returns dict with equity, bonds, alternatives, cash (sum = 100).
    """
    # Start with zone base allocation
    base = dict(ZONE_BASE_ALLOCATIONS.get(zone, ZONE_BASE_ALLOCATIONS["Moderate Conviction"]))

    # Apply regime adjustment
    regime_adj = REGIME_ADJUSTMENTS.get(regime, REGIME_ADJUSTMENTS["transitional"])
    for asset, shift in regime_adj.items():
        base[asset] += shift

    # Apply pattern adjustment
    pattern_adj = PATTERN_ADJUSTMENTS.get(pattern, PATTERN_ADJUSTMENTS["wait_and_observe"])
    for asset, shift in pattern_adj.items():
        base[asset] += shift

    # Clamp all to non-negative
    for asset in base:
        base[asset] = max(0, base[asset])

    # Re-normalize to 100%
    total = sum(base.values())
    if total > 0:
        for asset in base:
            base[asset] = round(base[asset] / total * 100, 1)
    else:
        base = {"equity": 0, "bonds": 0, "alternatives": 0, "cash": 100}

    # Fix rounding to exactly 100
    diff = 100 - sum(base.values())
    if abs(diff) > 0:
        # Add/subtract from largest allocation
        largest = max(base, key=base.get)
        base[largest] = round(base[largest] + diff, 1)

    return base


def calculate_position_sizing(
    conviction_score: float,
    zone: str,
) -> Dict:
    """
    Calculate position sizing parameters based on conviction level.

    Returns:
        max_single_position: Max % of portfolio in one position
        daily_vol_target: Target daily portfolio volatility %
        max_positions: Max number of open positions
    """
    sizing_map = {
        "Maximum Conviction": {
            "max_single_position": 25,
            "daily_vol_target": 0.4,
            "max_positions": 8,
        },
        "High Conviction": {
            "max_single_position": 15,
            "daily_vol_target": 0.3,
            "max_positions": 12,
        },
        "Moderate Conviction": {
            "max_single_position": 10,
            "daily_vol_target": 0.25,
            "max_positions": 15,
        },
        "Low Conviction": {
            "max_single_position": 5,
            "daily_vol_target": 0.15,
            "max_positions": 20,
        },
        "Capital Preservation": {
            "max_single_position": 3,
            "daily_vol_target": 0.1,
            "max_positions": 25,
        },
    }

    return sizing_map.get(zone, sizing_map["Moderate Conviction"])
