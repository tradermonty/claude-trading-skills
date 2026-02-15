#!/usr/bin/env python3
"""
Volume Pattern Calculator - Volume Dry-Up Analysis

Analyzes volume behavior near the pivot point of a VCP pattern.
Key principle: Volume should contract (dry up) as the pattern tightens,
then expand on breakout.

Key Metric: Volume dry-up ratio = avg volume (last 10 bars near pivot) / 50-day avg volume

Scoring:
- Dry-up ratio < 0.30:  90 (exceptional volume contraction)
- 0.30-0.50:            75 (strong dry-up)
- 0.50-0.70:            60 (moderate dry-up)
- 0.70-1.00:            40 (weak dry-up)
- > 1.00:               20 (no dry-up, not ideal)

Modifiers:
- Breakout on 1.5x+ volume: +10
- Net accumulation > 3 days: +10
- Net distribution > 3 days: -10
"""

from typing import Dict, List, Optional


def calculate_volume_pattern(
    historical_prices: List[Dict],
    pivot_price: Optional[float] = None,
) -> Dict:
    """
    Analyze volume behavior near the VCP pivot point.

    Args:
        historical_prices: Daily OHLCV data (most recent first), need 50+ days
        pivot_price: The pivot (breakout) price level. If None, uses recent high.

    Returns:
        Dict with score (0-100), dry_up_ratio, volume details
    """
    if not historical_prices or len(historical_prices) < 20:
        return {
            "score": 0,
            "dry_up_ratio": None,
            "error": "Insufficient data (need 20+ days)",
        }

    volumes = [d.get("volume", 0) for d in historical_prices]
    closes = [d.get("close", d.get("adjClose", 0)) for d in historical_prices]

    # 50-day average volume (or available)
    vol_period = min(50, len(volumes))
    avg_volume_50d = sum(volumes[:vol_period]) / vol_period if vol_period > 0 else 0

    if avg_volume_50d <= 0:
        return {
            "score": 0,
            "dry_up_ratio": None,
            "error": "No volume data available",
        }

    # Recent volume (last 10 bars, representing area near pivot)
    recent_period = min(10, len(volumes))
    avg_volume_recent = sum(volumes[:recent_period]) / recent_period if recent_period > 0 else 0

    # Volume dry-up ratio
    dry_up_ratio = avg_volume_recent / avg_volume_50d if avg_volume_50d > 0 else 1.0

    # Base score from dry-up ratio
    if dry_up_ratio < 0.30:
        base_score = 90
    elif dry_up_ratio < 0.50:
        base_score = 75
    elif dry_up_ratio < 0.70:
        base_score = 60
    elif dry_up_ratio <= 1.00:
        base_score = 40
    else:
        base_score = 20

    score = base_score

    # Modifier: Check for breakout volume (most recent day)
    breakout_volume = False
    if len(volumes) >= 2 and volumes[0] > avg_volume_50d * 1.5:
        current_price = closes[0] if closes else 0
        if pivot_price and current_price > pivot_price:
            breakout_volume = True
            score += 10

    # Modifier: Net accumulation/distribution in last 20 days
    # Count up-volume vs down-volume days
    up_vol_days = 0
    down_vol_days = 0
    analysis_period = min(20, len(closes) - 1)

    for i in range(analysis_period):
        if i + 1 < len(closes) and closes[i] > closes[i + 1]:
            up_vol_days += 1
        elif i + 1 < len(closes) and closes[i] < closes[i + 1]:
            down_vol_days += 1

    net_accumulation = up_vol_days - down_vol_days
    if net_accumulation > 3:
        score += 10
    elif net_accumulation < -3:
        score -= 10

    score = max(0, min(100, score))

    return {
        "score": score,
        "dry_up_ratio": round(dry_up_ratio, 3),
        "avg_volume_50d": int(avg_volume_50d),
        "avg_volume_recent_10d": int(avg_volume_recent),
        "breakout_volume_detected": breakout_volume,
        "up_volume_days_20d": up_vol_days,
        "down_volume_days_20d": down_vol_days,
        "net_accumulation": net_accumulation,
        "error": None,
    }
