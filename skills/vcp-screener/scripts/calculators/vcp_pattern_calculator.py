#!/usr/bin/env python3
"""
VCP Pattern Calculator - Core Volatility Contraction Pattern Detection

Implements Mark Minervini's VCP detection algorithm:
1. Find swing highs and lows within a 120-day lookback window
2. Identify successive contractions (T1, T2, T3, T4)
3. Validate that each contraction is tighter than the previous
4. Score based on number of contractions, tightness, and depth ratios

VCP Characteristics:
- T1 (first correction): 8-35% depth for S&P 500 large-caps
- Each successive contraction should be 25%+ tighter than the previous
- Minimum 2 contractions required for valid VCP
- Successive highs should be within 5% of each other
- Pattern duration: 15-325 trading days
"""

from typing import Optional


def calculate_vcp_pattern(
    historical_prices: list[dict],
    lookback_days: int = 120,
    atr_multiplier: float = 1.5,
    atr_period: int = 14,
    min_contraction_days: int = 5,
    min_contractions: int = 2,
    t1_depth_min: float = 8.0,
    contraction_ratio: float = 0.75,
    wide_and_loose_threshold: float = 15.0,
) -> dict:
    """
    Detect Volatility Contraction Pattern in price data.

    Uses ATR-based ZigZag swing detection with fallback to fixed-window method.
    Tries multiple starting highs (multi-start) and selects the best pattern.

    Args:
        historical_prices: Daily OHLCV data (most recent first), need 30+ days
        lookback_days: Number of days to look back for pattern (default 120)
        atr_multiplier: ATR multiplier for ZigZag swing threshold
        atr_period: ATR calculation period
        min_contraction_days: Minimum days for a contraction to count
        wide_and_loose_threshold: Final contraction depth % above which (combined
            with <10-day duration) flags a wide-and-loose pattern (default 15.0)

    Returns:
        Dict with score (0-100), contractions list, pattern validity, pivot point,
        atr_compression_ratio, wide_and_loose, right_side_range_ratio
    """
    empty_result = {
        "score": 0,
        "valid_vcp": False,
        "contractions": [],
        "num_contractions": 0,
        "pivot_price": None,
        "atr_compression_ratio": None,
        "wide_and_loose": False,
        "right_side_range_ratio": None,
        "error": None,
    }

    if not historical_prices or len(historical_prices) < 30:
        empty_result["error"] = "Insufficient data (need 30+ days)"
        return empty_result

    # Work in chronological order (oldest first)
    prices = list(reversed(historical_prices[:lookback_days]))
    n = len(prices)

    if n < 30:
        empty_result["error"] = "Insufficient data in lookback window"
        return empty_result

    # Extract price arrays
    highs = [d.get("high", d.get("close", 0)) for d in prices]
    lows = [d.get("low", d.get("close", 0)) for d in prices]
    closes = [d.get("close", 0) for d in prices]
    dates = [d.get("date", f"day-{i}") for i, d in enumerate(prices)]

    # Step A: Find swing points using ZigZag (primary) with fixed-window fallback
    atr_val = _calculate_atr(highs, lows, closes, atr_period)
    atr_10 = _calculate_atr(highs, lows, closes, 10)
    atr_50 = _calculate_atr(highs, lows, closes, 50)
    zz_highs, zz_lows = _zigzag_swing_points(highs, lows, closes, dates, atr_multiplier, atr_period)

    # Use ZigZag results if they have enough points, otherwise fallback
    if len(zz_highs) >= 1 and len(zz_lows) >= 1:
        swing_highs = zz_highs
        swing_lows = zz_lows
    else:
        swing_highs = _find_swing_highs(highs, window=5)
        swing_lows = _find_swing_lows(lows, window=5)

    if len(swing_highs) < 1 or len(swing_lows) < 1:
        empty_result["error"] = "Insufficient swing points detected"
        return empty_result

    # Step B: Multi-start contraction detection
    # Try top 3 swing highs as starting points, pick the best pattern
    sorted_highs = sorted(swing_highs, key=lambda x: x[1], reverse=True)
    best_contractions = []
    best_score = -1
    best_valid = False

    for start_high in sorted_highs[:3]:
        candidate = _build_contractions_from(
            start_high,
            swing_highs,
            swing_lows,
            highs,
            lows,
            dates,
            min_contraction_days=min_contraction_days,
        )
        if len(candidate) >= min_contractions:
            v = _validate_vcp(candidate, n, min_contractions, t1_depth_min, contraction_ratio)
            s = _score_vcp(candidate, v)
        else:
            v = {"valid": False}
            s = 0
        # Compare: valid first, then score, then length as tiebreaker
        key = (int(v.get("valid", False)), s, len(candidate))
        best_key = (int(best_valid), best_score, len(best_contractions))
        if key > best_key:
            best_contractions = candidate
            best_score = s
            best_valid = v.get("valid", False)

    contractions = best_contractions

    if len(contractions) < min_contractions:
        atr_compression_ratio = (atr_10 / atr_50) if (atr_50 > 0 and atr_10 > 0) else None
        return {
            "score": 0,
            "valid_vcp": False,
            "contractions": contractions,
            "num_contractions": len(contractions),
            "pivot_price": _get_pivot_price(contractions, highs, swing_highs),
            "atr_value": round(atr_val, 4) if atr_val else None,
            "atr_compression_ratio": round(atr_compression_ratio, 3)
            if atr_compression_ratio is not None
            else None,
            "wide_and_loose": False,
            "right_side_range_ratio": None,
            "error": f"Fewer than {min_contractions} contractions found",
        }

    # Step C: Validate VCP
    validation = _validate_vcp(contractions, n, min_contractions, t1_depth_min, contraction_ratio)

    # Pivot price = high of the last contraction
    pivot_price = _get_pivot_price(contractions, highs, swing_highs)

    # Calculate pattern duration
    first_idx = contractions[0]["high_idx"]
    last_low_idx = contractions[-1]["low_idx"]
    pattern_duration = last_low_idx - first_idx

    # Score the pattern
    score = _score_vcp(contractions, validation)

    # ATR compression ratio: recent ATR(10) / ATR(50) — lower = more compressed
    atr_compression_ratio: Optional[float] = None
    if atr_10 > 0 and atr_50 > 0:
        atr_compression_ratio = atr_10 / atr_50

    # Wide-and-loose flag: final contraction is deep AND very short
    wide_and_loose = _compute_wide_and_loose(contractions, wide_and_loose_threshold)

    # Right-side tightness: 15-bar price range / ATR(50)
    # Measures how compact the right side of the base is (lower = tighter)
    right_side_range_ratio: Optional[float] = None
    if atr_50 > 0 and n >= 15:
        recent_range = max(highs[-15:]) - min(lows[-15:])
        right_side_range_ratio = recent_range / atr_50

    return {
        "score": score,
        "valid_vcp": validation["valid"],
        "contractions": contractions,
        "num_contractions": len(contractions),
        "pivot_price": round(pivot_price, 2) if pivot_price else None,
        "pattern_duration_days": pattern_duration,
        "validation": validation,
        "atr_value": round(atr_val, 4) if atr_val else None,
        "atr_compression_ratio": round(atr_compression_ratio, 3)
        if atr_compression_ratio is not None
        else None,
        "wide_and_loose": wide_and_loose,
        "right_side_range_ratio": round(right_side_range_ratio, 3)
        if right_side_range_ratio is not None
        else None,
        "error": None,
    }


def _calculate_atr(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    period: int = 14,
) -> float:
    """Calculate Average True Range.

    Args:
        highs: High prices in chronological order (oldest first)
        lows: Low prices in chronological order
        closes: Close prices in chronological order
        period: ATR period (default 14)

    Returns:
        ATR value, or 0.0 if insufficient data
    """
    n = len(highs)
    if n < period + 1:
        return 0.0

    true_ranges = []
    for i in range(1, n):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        true_ranges.append(tr)

    if len(true_ranges) < period:
        return 0.0

    # Simple moving average of true ranges for the last `period` values
    return sum(true_ranges[-period:]) / period


def _zigzag_swing_points(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    dates: list[str],
    atr_multiplier: float = 1.5,
    atr_period: int = 14,
) -> tuple:
    """ATR-based ZigZag swing detection.

    Reversal is recognized only when price moves ATR * multiplier from
    the current extreme. This filters out noise while adapting to volatility.

    Args:
        highs: High prices (chronological, oldest first)
        lows: Low prices (chronological, oldest first)
        closes: Close prices (chronological, oldest first)
        dates: Date strings (chronological, oldest first)
        atr_multiplier: Multiplier for ATR threshold
        atr_period: ATR calculation period

    Returns:
        (swing_highs: [(idx, val)], swing_lows: [(idx, val)])
    """
    n = len(highs)
    if n < atr_period + 1:
        return [], []

    atr = _calculate_atr(highs, lows, closes, atr_period)
    if atr <= 0:
        return [], []

    threshold = atr * atr_multiplier

    swing_highs = []
    swing_lows = []

    # Start by finding initial direction from first few bars
    direction = 1  # 1 = looking for high, -1 = looking for low
    extreme_idx = 0
    extreme_val = highs[0]

    # Find initial extreme
    for i in range(min(atr_period, n)):
        if highs[i] > extreme_val:
            extreme_val = highs[i]
            extreme_idx = i

    direction = 1  # Start looking for a swing high
    extreme_val = highs[extreme_idx]

    for i in range(extreme_idx + 1, n):
        if direction == 1:  # Looking for swing high
            if highs[i] > extreme_val:
                extreme_val = highs[i]
                extreme_idx = i
            elif extreme_val - lows[i] >= threshold:
                # Swing high confirmed at extreme_idx
                swing_highs.append((extreme_idx, extreme_val))
                # Start looking for swing low
                direction = -1
                extreme_val = lows[i]
                extreme_idx = i
        else:  # direction == -1, looking for swing low
            if lows[i] < extreme_val:
                extreme_val = lows[i]
                extreme_idx = i
            elif highs[i] - extreme_val >= threshold:
                # Swing low confirmed at extreme_idx
                swing_lows.append((extreme_idx, extreme_val))
                # Start looking for swing high
                direction = 1
                extreme_val = highs[i]
                extreme_idx = i

    return swing_highs, swing_lows


def _find_swing_highs(highs: list[float], window: int = 5) -> list[tuple[int, float]]:
    """Find swing high points using fixed window. Returns list of (index, value)."""
    swing_highs = []
    for i in range(window, len(highs) - window):
        is_high = True
        for j in range(1, window + 1):
            if highs[i] <= highs[i - j] or highs[i] <= highs[i + j]:
                is_high = False
                break
        if is_high:
            swing_highs.append((i, highs[i]))
    return swing_highs


def _find_swing_lows(lows: list[float], window: int = 5) -> list[tuple[int, float]]:
    """Find swing low points using fixed window. Returns list of (index, value)."""
    swing_lows = []
    for i in range(window, len(lows) - window):
        is_low = True
        for j in range(1, window + 1):
            if lows[i] >= lows[i - j] or lows[i] >= lows[i + j]:
                is_low = False
                break
        if is_low:
            swing_lows.append((i, lows[i]))
    return swing_lows


def _identify_contractions(
    swing_highs: list[tuple[int, float]],
    swing_lows: list[tuple[int, float]],
    highs: list[float],
    lows: list[float],
    dates: list[str],
) -> list[dict]:
    """
    Identify successive contractions from swing points.
    Each contraction is defined by a swing high followed by a swing low.
    """
    if not swing_highs:
        return []

    # Start from the highest swing high in the lookback
    h1_idx, h1_val = max(swing_highs, key=lambda x: x[1])

    contractions = []
    current_high_idx = h1_idx
    current_high_val = h1_val

    # Find successive contraction pairs
    for _ in range(4):  # Max 4 contractions
        # Find next swing low after current high
        next_low = None
        for idx, val in swing_lows:
            if idx > current_high_idx:
                next_low = (idx, val)
                break

        if next_low is None:
            break

        low_idx, low_val = next_low
        depth_pct = (
            (current_high_val - low_val) / current_high_val * 100 if current_high_val > 0 else 0
        )

        contractions.append(
            {
                "label": f"T{len(contractions) + 1}",
                "high_idx": current_high_idx,
                "high_price": round(current_high_val, 2),
                "high_date": dates[current_high_idx] if current_high_idx < len(dates) else "N/A",
                "low_idx": low_idx,
                "low_price": round(low_val, 2),
                "low_date": dates[low_idx] if low_idx < len(dates) else "N/A",
                "depth_pct": round(depth_pct, 2),
            }
        )

        # Find next swing high after this low (for the next contraction)
        next_high = None
        for idx, val in swing_highs:
            if idx > low_idx:
                next_high = (idx, val)
                break

        if next_high is None:
            break

        current_high_idx, current_high_val = next_high

    return contractions


def _build_contractions_from(
    start_high: tuple[int, float],
    swing_highs: list[tuple[int, float]],
    swing_lows: list[tuple[int, float]],
    highs: list[float],
    lows: list[float],
    dates: list[str],
    min_contraction_days: int = 5,
) -> list[dict]:
    """Build contraction sequence from a specific swing high starting point.

    Args:
        start_high: (index, value) of starting swing high
        swing_highs: All swing highs
        swing_lows: All swing lows
        highs: All high prices
        lows: All low prices
        dates: All dates
        min_contraction_days: Minimum days between high and low for a contraction
    """
    h1_idx, h1_val = start_high
    contractions = []
    current_high_idx = h1_idx
    current_high_val = h1_val

    for _ in range(4):  # Max 4 contractions
        # Find next swing low after current high
        next_low = None
        for idx, val in swing_lows:
            if idx > current_high_idx:
                next_low = (idx, val)
                break

        if next_low is None:
            break

        low_idx, low_val = next_low
        duration = low_idx - current_high_idx

        # Skip contractions that are too short
        if duration < min_contraction_days:
            # Find the next swing high after current_high to bound the search
            next_high_boundary = None
            for idx, _val in swing_highs:
                if idx > current_high_idx:
                    next_high_boundary = idx
                    break

            # Try to find a later swing low, but only before the next swing high
            found_valid = False
            for idx, val in swing_lows:
                if idx > current_high_idx and (idx - current_high_idx) >= min_contraction_days:
                    if next_high_boundary is not None and idx > next_high_boundary:
                        break  # Don't jump past an intermediate swing high
                    next_low = (idx, val)
                    low_idx, low_val = next_low
                    duration = low_idx - current_high_idx
                    found_valid = True
                    break
            if not found_valid:
                break

        depth_pct = (
            (current_high_val - low_val) / current_high_val * 100 if current_high_val > 0 else 0
        )

        # Right-shoulder validation: subsequent highs within 5% of H1
        if contractions:
            pct_from_h1 = abs(current_high_val - h1_val) / h1_val * 100
            if pct_from_h1 > 5:
                break

        contractions.append(
            {
                "label": f"T{len(contractions) + 1}",
                "high_idx": current_high_idx,
                "high_price": round(current_high_val, 2),
                "high_date": dates[current_high_idx] if current_high_idx < len(dates) else "N/A",
                "low_idx": low_idx,
                "low_price": round(low_val, 2),
                "low_date": dates[low_idx] if low_idx < len(dates) else "N/A",
                "depth_pct": round(depth_pct, 2),
                "duration_days": duration,
            }
        )

        # Find next swing high after this low
        next_high = None
        for idx, val in swing_highs:
            if idx > low_idx:
                next_high = (idx, val)
                break

        if next_high is None:
            break

        current_high_idx, current_high_val = next_high

    return contractions


def _validate_vcp(
    contractions: list[dict],
    total_days: int,
    min_contractions: int = 2,
    t1_depth_min: float = 8.0,
    contraction_ratio: float = 0.75,
) -> dict:
    """Validate whether the contraction pattern qualifies as a VCP."""
    issues = []
    valid = True

    if len(contractions) < min_contractions:
        return {"valid": False, "issues": [f"Need at least {min_contractions} contractions"]}

    # Check T1 depth (8-35% for large-caps)
    t1_depth = contractions[0]["depth_pct"]
    if t1_depth < t1_depth_min:
        issues.append(f"T1 depth too shallow ({t1_depth:.1f}%, need >= {t1_depth_min}%)")
        valid = False
    elif t1_depth > 35:
        issues.append(f"T1 depth too deep ({t1_depth:.1f}%, prefer <= 35%)")
        # Don't invalidate, just flag

    # Check contraction tightening (each T should be <= 75% of previous)
    contraction_ratios = []
    for i in range(1, len(contractions)):
        prev_depth = contractions[i - 1]["depth_pct"]
        curr_depth = contractions[i]["depth_pct"]
        if prev_depth > 0:
            ratio = curr_depth / prev_depth
            contraction_ratios.append(ratio)
            if ratio > contraction_ratio:
                issues.append(
                    f"{contractions[i]['label']} ({curr_depth:.1f}%) does not contract "
                    f"vs {contractions[i - 1]['label']} ({prev_depth:.1f}%), "
                    f"ratio={ratio:.2f} (need <= {contraction_ratio})"
                )
                valid = False

    # Check successive highs within 5% of each other
    for i in range(1, len(contractions)):
        prev_high = contractions[i - 1]["high_price"]
        curr_high = (
            contractions[i]["high_price"]
            if i < len(contractions)
            else contractions[-1]["high_price"]
        )
        # The high of subsequent contraction should be near the first
        if prev_high > 0:
            pct_diff = (
                abs(curr_high - contractions[0]["high_price"]) / contractions[0]["high_price"] * 100
            )
            if pct_diff > 5:
                issues.append(
                    f"{contractions[i]['label']} high ${curr_high:.2f} is "
                    f"{pct_diff:.1f}% from H1 ${contractions[0]['high_price']:.2f}"
                )

    # Pattern duration check (15-325 trading days)
    if len(contractions) >= 2:
        duration = contractions[-1]["low_idx"] - contractions[0]["high_idx"]
        if duration < 15:
            issues.append(f"Pattern too short ({duration} days, need >= 15)")
            valid = False
        elif duration > 325:
            issues.append(f"Pattern too long ({duration} days, prefer <= 325)")

    return {
        "valid": valid,
        "issues": issues,
        "contraction_ratios": [round(r, 3) for r in contraction_ratios],
        "t1_depth": t1_depth,
    }


def _compute_wide_and_loose(contractions: list[dict], threshold: float) -> bool:
    """Return True if the final contraction is wide-and-loose.

    Wide-and-loose: depth > threshold AND duration < 10 days.
    This flags patterns where the final consolidation is too deep and
    too brief to be a quality VCP setup.

    Args:
        contractions: List of contraction dicts (must have depth_pct, duration_days)
        threshold: Maximum acceptable depth % (final contraction)

    Returns:
        True if final contraction qualifies as wide-and-loose
    """
    if not contractions:
        return False
    final = contractions[-1]
    final_depth = final.get("depth_pct", 0.0)
    final_duration = final.get("duration_days", 999)
    return final_depth > threshold and final_duration < 10


def _get_pivot_price(
    contractions: list[dict],
    highs: list[float],
    swing_highs: list[tuple[int, float]],
) -> Optional[float]:
    """Get the pivot (breakout) price - high of the last contraction."""
    if contractions:
        return contractions[-1]["high_price"]
    elif swing_highs:
        return swing_highs[-1][1]
    return None


def _score_vcp(contractions: list[dict], validation: dict) -> int:
    """Score the VCP pattern quality (0-100)."""
    if not validation["valid"]:
        # Even invalid patterns get partial credit for structure
        return min(40, len(contractions) * 15)

    num = len(contractions)

    # Base score by contraction count
    if num >= 4:
        base = 90
    elif num >= 3:
        base = 80
    elif num >= 2:
        base = 60
    else:
        return 20

    score = base

    # Bonus: tight final contraction (< 5% depth)
    final_depth = contractions[-1]["depth_pct"]
    if final_depth < 5:
        score += 10

    # Bonus: good contraction ratio (avg < 0.4 of T1)
    ratios = validation.get("contraction_ratios", [])
    if ratios and sum(ratios) / len(ratios) < 0.4:
        score += 10

    # Penalty: deep T1 (> 30%)
    t1_depth = validation.get("t1_depth", 0)
    if t1_depth > 30:
        score -= 10

    return max(0, min(100, score))
