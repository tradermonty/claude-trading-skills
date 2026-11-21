#!/usr/bin/env python3
"""
Volume Pattern Calculator - Volume Dry-Up Analysis

Analyzes volume behavior near the pivot point of a VCP pattern.
Key principle: Volume should contract (dry up) as the pattern tightens,
then expand on breakout.

Key Metric: Volume dry-up ratio = avg volume (10 bars before pivot, bar[0] excluded)
            / 50-day avg volume

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
- Declining contraction volume: +10

Note: Bar[0] (potential breakout bar) is excluded from dry-up calculation
to avoid contaminating the dry-up ratio with high breakout volume.
The breakout quality is tracked separately via breakout_volume_score.
"""

from typing import Optional

from _price_bars import find_bar_gaps, read_price
from price_bar_utils import find_close_gaps, read_close, unavailable_component


def calculate_volume_pattern(
    historical_prices: list[dict],
    pivot_price: Optional[float] = None,
    contractions: Optional[list[dict]] = None,
    breakout_volume_ratio: float = 1.5,
) -> dict:
    """
    Analyze volume behavior near the VCP pivot point.

    When contractions are provided, uses zone-based analysis:
    - Zone A: Last contraction period (volume during tightening)
    - Zone B: Pivot approach (5-10 bars before pivot)
    - Zone C: Breakout bar (price above pivot on high volume)

    When contractions is None or empty, uses legacy 10-bar window.

    Args:
        historical_prices: Daily OHLCV data (most recent first), need 50+ days
        pivot_price: The pivot (breakout) price level. If None, uses recent high.
        contractions: List of contraction dicts with high_idx/low_idx (chronological)

    Returns:
        Dict with score (0-100), dry_up_ratio, volume details
    """
    if not historical_prices or len(historical_prices) < 20:
        return {
            "score": 0,
            "dry_up_ratio": None,
            "error": "Insufficient data (need 20+ days)",
        }

    n = len(historical_prices)
    volume_indices = set(range(min(50, n)))
    for contraction in contractions or []:
        start, end = sorted((n - 1 - contraction["low_idx"], n - 1 - contraction["high_idx"]))
        volume_indices.update(range(max(0, start), min(n, end + 1)))
    gaps = find_bar_gaps(
        [historical_prices[i] for i in sorted(volume_indices)],
        ["volume"],
        zero_ok=["volume"],
        order="newest_first",
    )
    if gaps["bad_bars"]:
        return unavailable_component(gaps, dry_up_ratio=None, breakout_volume_detected=False)
    volumes = [read_price(d, "volume", allow_zero=True) for d in historical_prices]
    closes = [read_close(d) for d in historical_prices]

    # 50-day average volume (or available)
    vol_period = min(50, len(volumes))
    avg_volume_50d = sum(volumes[:vol_period]) / vol_period if vol_period > 0 else 0

    if avg_volume_50d <= 0:
        return {
            "score": 0,
            "dry_up_ratio": None,
            "error": "No volume data available",
        }

    close_indices = {0} if pivot_price else set()
    for i in range(min(20, n - 1)):
        if volumes[i] > avg_volume_50d:
            close_indices.update((i, i + 1))
    gaps = find_close_gaps(historical_prices, close_indices)
    if gaps["bad_bars"]:
        return unavailable_component(gaps, dry_up_ratio=None, breakout_volume_detected=False)

    # Zone-based analysis when contractions are provided
    zone_analysis = None
    contraction_volume_trend = None
    use_zone = contractions is not None and len(contractions) >= 1

    if use_zone:
        zone_analysis, contraction_volume_trend = _zone_volume_analysis(
            volumes, closes, contractions, pivot_price, avg_volume_50d
        )

    # Dry-up ratio: use Zone B if available, otherwise legacy window.
    # Bar[0] (potential breakout bar) is excluded from both paths to avoid
    # contaminating dry-up with high breakout volume.
    if use_zone and zone_analysis and zone_analysis.get("zone_b_avg_volume"):
        avg_volume_recent = zone_analysis["zone_b_avg_volume"]
    else:
        # volumes[1:11] — 10 bars, skip bar[0]
        legacy_vols = volumes[1:11] if len(volumes) > 1 else []
        avg_volume_recent = sum(legacy_vols) / len(legacy_vols) if legacy_vols else 0

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

    # Modifier: Breakout volume confirmation (bar[0])
    # Tracked independently from dry-up — high breakout volume on a clean
    # bar[0] above pivot is a positive signal, not a contaminator of dry-up.
    breakout_volume = False
    breakout_volume_score = 0
    current_price = closes[0] if closes else 0
    if len(volumes) >= 1 and avg_volume_50d > 0:
        bar0_ratio = volumes[0] / avg_volume_50d
        if pivot_price and current_price > pivot_price:
            if bar0_ratio >= breakout_volume_ratio:
                breakout_volume = True
                score += 10
            # Independent breakout volume score regardless of pivot position
            if bar0_ratio >= 3.0:
                breakout_volume_score = 100
            elif bar0_ratio >= 2.0:
                breakout_volume_score = 80
            elif bar0_ratio >= breakout_volume_ratio:
                breakout_volume_score = 60
            elif bar0_ratio >= 1.0:
                breakout_volume_score = 30

    # Modifier: Net accumulation/distribution in last 20 days
    # Only count days where volume exceeds 50-day average (institutional activity)
    up_vol_days = 0
    down_vol_days = 0
    analysis_period = min(20, len(closes) - 1)

    for i in range(analysis_period):
        if i + 1 < len(closes) and volumes[i] > avg_volume_50d:
            if closes[i] > closes[i + 1]:
                up_vol_days += 1
            elif closes[i] < closes[i + 1]:
                down_vol_days += 1

    net_accumulation = up_vol_days - down_vol_days
    if net_accumulation > 3:
        score += 10
    elif net_accumulation < -3:
        score -= 10

    # Zone bonus: declining contraction volume (strengthened +5 → +10)
    if contraction_volume_trend and contraction_volume_trend.get("declining"):
        score += 10

    score = max(0, min(100, score))

    result = {
        "score": score,
        "dry_up_ratio": round(dry_up_ratio, 3),
        "avg_volume_50d": int(avg_volume_50d),
        "avg_volume_recent_10d": int(avg_volume_recent),
        "breakout_volume_detected": breakout_volume,
        "breakout_volume_score": breakout_volume_score,
        "up_volume_days_20d": up_vol_days,
        "down_volume_days_20d": down_vol_days,
        "net_accumulation": net_accumulation,
        "error": None,
    }

    if zone_analysis is not None:
        result["zone_analysis"] = zone_analysis
    if contraction_volume_trend is not None:
        result["contraction_volume_trend"] = contraction_volume_trend

    return result


def _zone_volume_analysis(
    volumes: list[int],
    closes: list[float],
    contractions: list[dict],
    pivot_price: Optional[float],
    avg_volume_50d: float,
) -> tuple:
    """Perform zone-based volume analysis using contraction boundaries.

    Data is most-recent-first. Contraction indices are chronological (oldest-first).
    We convert contraction indices to most-recent-first by: rev_idx = n - 1 - chrono_idx

    Returns:
        (zone_analysis dict, contraction_volume_trend dict)
    """
    n = len(volumes)

    # Zone A: Last contraction period
    last_c = contractions[-1]
    # Convert chronological indices to most-recent-first
    zone_a_start_rev = n - 1 - last_c["low_idx"]
    zone_a_end_rev = n - 1 - last_c["high_idx"]
    zone_a_start = min(zone_a_start_rev, zone_a_end_rev)
    zone_a_end = max(zone_a_start_rev, zone_a_end_rev)
    zone_a_vols = volumes[max(0, zone_a_start) : min(n, zone_a_end + 1)]
    zone_a_avg = int(sum(zone_a_vols) / len(zone_a_vols)) if zone_a_vols else 0

    # Zone B: Pivot approach (10 bars before current, bar[0] excluded)
    # volumes[1:11] = bars 1..10 (10 bars) — breakout bar excluded
    zone_b_start = 1  # skip bar 0 (potential breakout)
    zone_b_end = min(11, n)
    zone_b_vols = volumes[zone_b_start:zone_b_end]
    zone_b_avg = int(sum(zone_b_vols) / len(zone_b_vols)) if zone_b_vols else 0

    # Zone C: Breakout bar (bar 0 if price > pivot)
    zone_c_vol = None
    zone_c_ratio = None
    if pivot_price and n > 0 and closes[0] > pivot_price:
        zone_c_vol = volumes[0]
        zone_c_ratio = round(zone_c_vol / avg_volume_50d, 3) if avg_volume_50d > 0 else None

    zone_analysis = {
        "zone_a_avg_volume": zone_a_avg,
        "zone_a_ratio": round(zone_a_avg / avg_volume_50d, 3) if avg_volume_50d > 0 else None,
        "zone_b_avg_volume": zone_b_avg,
        "zone_b_ratio": round(zone_b_avg / avg_volume_50d, 3) if avg_volume_50d > 0 else None,
        "zone_c_volume": zone_c_vol,
        "zone_c_ratio": zone_c_ratio,
    }

    # Contraction volume trend: check if volume declines across contractions
    contraction_avgs = []
    for c in contractions:
        c_start_rev = n - 1 - c["low_idx"]
        c_end_rev = n - 1 - c["high_idx"]
        c_start = min(c_start_rev, c_end_rev)
        c_end = max(c_start_rev, c_end_rev)
        c_vols = volumes[max(0, c_start) : min(n, c_end + 1)]
        if c_vols:
            contraction_avgs.append(int(sum(c_vols) / len(c_vols)))

    declining = False
    if len(contraction_avgs) >= 2:
        declining = all(
            contraction_avgs[i] > contraction_avgs[i + 1] for i in range(len(contraction_avgs) - 1)
        )

    contraction_volume_trend = {
        "declining": declining,
        "contraction_volumes": contraction_avgs,
    }

    return zone_analysis, contraction_volume_trend
