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

from typing import Dict, List, Optional, Tuple


def calculate_vcp_pattern(
    historical_prices: List[Dict],
    lookback_days: int = 120,
) -> Dict:
    """
    Detect Volatility Contraction Pattern in price data.

    Args:
        historical_prices: Daily OHLCV data (most recent first), need 30+ days
        lookback_days: Number of days to look back for pattern (default 120)

    Returns:
        Dict with score (0-100), contractions list, pattern validity, pivot point
    """
    if not historical_prices or len(historical_prices) < 30:
        return {
            "score": 0,
            "valid_vcp": False,
            "contractions": [],
            "num_contractions": 0,
            "pivot_price": None,
            "error": "Insufficient data (need 30+ days)",
        }

    # Work in chronological order (oldest first)
    prices = list(reversed(historical_prices[:lookback_days]))
    n = len(prices)

    if n < 30:
        return {
            "score": 0,
            "valid_vcp": False,
            "contractions": [],
            "num_contractions": 0,
            "pivot_price": None,
            "error": "Insufficient data in lookback window",
        }

    # Step A: Find swing points
    highs = [d.get("high", d.get("close", 0)) for d in prices]
    lows = [d.get("low", d.get("close", 0)) for d in prices]
    closes = [d.get("close", 0) for d in prices]
    dates = [d.get("date", f"day-{i}") for i, d in enumerate(prices)]

    swing_highs = _find_swing_highs(highs, window=5)
    swing_lows = _find_swing_lows(lows, window=5)

    if len(swing_highs) < 1 or len(swing_lows) < 1:
        return {
            "score": 0,
            "valid_vcp": False,
            "contractions": [],
            "num_contractions": 0,
            "pivot_price": None,
            "error": "Insufficient swing points detected",
        }

    # Step B: Identify contractions
    contractions = _identify_contractions(swing_highs, swing_lows, highs, lows, dates)

    if len(contractions) < 2:
        return {
            "score": 0,
            "valid_vcp": False,
            "contractions": contractions,
            "num_contractions": len(contractions),
            "pivot_price": _get_pivot_price(contractions, highs, swing_highs),
            "error": "Fewer than 2 contractions found" if len(contractions) < 2 else None,
        }

    # Step C: Validate VCP
    validation = _validate_vcp(contractions, n)

    # Pivot price = high of the last contraction
    pivot_price = _get_pivot_price(contractions, highs, swing_highs)

    # Calculate pattern duration
    if len(contractions) >= 2:
        first_idx = contractions[0]["high_idx"]
        last_low_idx = contractions[-1]["low_idx"]
        pattern_duration = last_low_idx - first_idx
    else:
        pattern_duration = 0

    # Score the pattern
    score = _score_vcp(contractions, validation)

    return {
        "score": score,
        "valid_vcp": validation["valid"],
        "contractions": contractions,
        "num_contractions": len(contractions),
        "pivot_price": round(pivot_price, 2) if pivot_price else None,
        "pattern_duration_days": pattern_duration,
        "validation": validation,
        "error": None,
    }


def _find_swing_highs(highs: List[float], window: int = 5) -> List[Tuple[int, float]]:
    """Find swing high points. Returns list of (index, value)."""
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


def _find_swing_lows(lows: List[float], window: int = 5) -> List[Tuple[int, float]]:
    """Find swing low points. Returns list of (index, value)."""
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
    swing_highs: List[Tuple[int, float]],
    swing_lows: List[Tuple[int, float]],
    highs: List[float],
    lows: List[float],
    dates: List[str],
) -> List[Dict]:
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
        depth_pct = (current_high_val - low_val) / current_high_val * 100 if current_high_val > 0 else 0

        contractions.append({
            "label": f"T{len(contractions) + 1}",
            "high_idx": current_high_idx,
            "high_price": round(current_high_val, 2),
            "high_date": dates[current_high_idx] if current_high_idx < len(dates) else "N/A",
            "low_idx": low_idx,
            "low_price": round(low_val, 2),
            "low_date": dates[low_idx] if low_idx < len(dates) else "N/A",
            "depth_pct": round(depth_pct, 2),
        })

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


def _validate_vcp(contractions: List[Dict], total_days: int) -> Dict:
    """Validate whether the contraction pattern qualifies as a VCP."""
    issues = []
    valid = True

    if len(contractions) < 2:
        return {"valid": False, "issues": ["Need at least 2 contractions"]}

    # Check T1 depth (8-35% for large-caps)
    t1_depth = contractions[0]["depth_pct"]
    if t1_depth < 8:
        issues.append(f"T1 depth too shallow ({t1_depth:.1f}%, need >= 8%)")
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
            if ratio > 0.75:
                issues.append(
                    f"{contractions[i]['label']} ({curr_depth:.1f}%) does not contract "
                    f"25%+ vs {contractions[i-1]['label']} ({prev_depth:.1f}%), "
                    f"ratio={ratio:.2f} (need <= 0.75)"
                )
                valid = False

    # Check successive highs within 5% of each other
    for i in range(1, len(contractions)):
        prev_high = contractions[i - 1]["high_price"]
        curr_high = contractions[i]["high_price"] if i < len(contractions) else contractions[-1]["high_price"]
        # The high of subsequent contraction should be near the first
        if prev_high > 0:
            pct_diff = abs(curr_high - contractions[0]["high_price"]) / contractions[0]["high_price"] * 100
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


def _get_pivot_price(
    contractions: List[Dict],
    highs: List[float],
    swing_highs: List[Tuple[int, float]],
) -> Optional[float]:
    """Get the pivot (breakout) price - high of the last contraction."""
    if contractions:
        return contractions[-1]["high_price"]
    elif swing_highs:
        return swing_highs[-1][1]
    return None


def _score_vcp(contractions: List[Dict], validation: Dict) -> int:
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
