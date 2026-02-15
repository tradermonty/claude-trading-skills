#!/usr/bin/env python3
"""
FTD Detector - Post-FTD Health Monitor

Monitors the health of a confirmed Follow-Through Day by tracking:
1. Distribution days after FTD (early distribution = high failure risk)
2. FTD invalidation (close below FTD day's low)
3. Power Trend confirmation (21EMA > 50SMA, slope positive)
4. Quality score calculation (0-100)
"""

from typing import Dict, List, Optional


def count_post_ftd_distribution(history: List[Dict], ftd_idx: int) -> Dict:
    """
    Count distribution days (down days on higher volume) after FTD.

    Distribution within first 1-2 days = very bearish (FTD likely fails)
    Distribution on day 3 = moderately bearish
    Distribution on day 4-5 = mild negative

    Args:
        history: Daily OHLCV in chronological order
        ftd_idx: Index of the FTD day in history

    Returns:
        Dict with distribution count, timing, and details
    """
    if ftd_idx >= len(history) - 1:
        return {
            "distribution_count": 0,
            "days_monitored": 0,
            "earliest_distribution_day": None,
            "details": [],
        }

    n = len(history)
    distributions = []
    days_monitored = 0

    for i in range(ftd_idx + 1, min(ftd_idx + 6, n)):  # Monitor up to 5 days post-FTD
        days_monitored += 1
        curr_close = history[i].get("close", 0)
        prev_close = history[i - 1].get("close", 0)
        curr_volume = history[i].get("volume", 0)
        prev_volume = history[i - 1].get("volume", 0)

        if prev_close <= 0:
            continue

        change_pct = (curr_close - prev_close) / prev_close * 100

        # Distribution day: down >= 0.2% on higher volume
        if change_pct <= -0.2 and curr_volume > prev_volume:
            day_num = i - ftd_idx
            distributions.append({
                "day": day_num,
                "date": history[i].get("date", "N/A"),
                "change_pct": round(change_pct, 2),
                "volume_change_pct": round((curr_volume / prev_volume - 1) * 100, 1),
            })

    earliest = distributions[0]["day"] if distributions else None

    return {
        "distribution_count": len(distributions),
        "days_monitored": days_monitored,
        "earliest_distribution_day": earliest,
        "details": distributions,
    }


def check_ftd_invalidation(history: List[Dict], ftd_idx: int) -> Dict:
    """
    Check if FTD has been invalidated by a close below FTD day's low.

    Args:
        history: Daily OHLCV in chronological order
        ftd_idx: Index of the FTD day in history

    Returns:
        Dict with invalidated flag and details
    """
    ftd_low = history[ftd_idx].get("low", history[ftd_idx].get("close", 0))
    n = len(history)

    for i in range(ftd_idx + 1, n):
        curr_close = history[i].get("close", 0)
        if curr_close < ftd_low:
            return {
                "invalidated": True,
                "invalidation_date": history[i].get("date", "N/A"),
                "invalidation_close": curr_close,
                "ftd_low": ftd_low,
                "days_after_ftd": i - ftd_idx,
            }

    return {
        "invalidated": False,
        "ftd_low": ftd_low,
        "days_since_ftd": n - 1 - ftd_idx,
    }


def detect_power_trend(history: List[Dict]) -> Dict:
    """
    Detect Power Trend confirmation signals.

    Power Trend conditions:
    1. 21-day EMA > 50-day SMA
    2. 50-day SMA slope is positive (rising over last 5 days)
    3. Price above 21-day EMA

    Args:
        history: Daily OHLCV in chronological order (need 50+ days)

    Returns:
        Dict with power_trend flag and component checks
    """
    if len(history) < 50:
        return {
            "power_trend": False,
            "reason": "Insufficient data (need 50+ days)",
            "ema_21": None,
            "sma_50": None,
            "price_above_21ema": None,
            "sma_50_rising": None,
        }

    closes = [d.get("close", 0) for d in history]

    # Calculate 21-day EMA (using most recent data)
    ema_21 = _calculate_ema(closes, 21)

    # Calculate 50-day SMA (current)
    sma_50_current = sum(closes[-50:]) / 50

    # Calculate 50-day SMA from 5 days ago
    if len(closes) >= 55:
        sma_50_5d_ago = sum(closes[-55:-5]) / 50
        sma_50_rising = sma_50_current > sma_50_5d_ago
    else:
        sma_50_rising = None

    current_price = closes[-1]
    price_above_21ema = current_price > ema_21
    ema_above_sma = ema_21 > sma_50_current

    power_trend = (
        ema_above_sma
        and (sma_50_rising is True)
        and price_above_21ema
    )

    conditions_met = sum([
        ema_above_sma,
        sma_50_rising is True,
        price_above_21ema,
    ])

    return {
        "power_trend": power_trend,
        "conditions_met": conditions_met,
        "ema_21": round(ema_21, 2),
        "sma_50": round(sma_50_current, 2),
        "current_price": round(current_price, 2),
        "ema_above_sma": ema_above_sma,
        "sma_50_rising": sma_50_rising,
        "price_above_21ema": price_above_21ema,
    }


def calculate_ftd_quality_score(market_state: Dict) -> Dict:
    """
    Calculate FTD quality score (0-100) based on multiple factors.

    Scoring:
    - Base (FTD Day): Day 4-7 = 60pts, Day 8-10 = 50pts
    - Price Gain: >=2.0% = +15, >=1.5% = +10, >=1.25% = +5
    - Volume vs 50-day avg: Above = +10, Below = +0
    - Dual Index Confirm: Both = +15, Single = +0
    - Post-FTD Health (Day 1-5): No dist = +10, Dist Day 4-5 = -5,
                                  Dist Day 3 = -15, Dist Day 1-2 = -30

    Args:
        market_state: Output from get_market_state() with post-FTD analysis

    Returns:
        Dict with total_score, breakdown, signal, and guidance
    """
    score = 0
    breakdown = {}

    # Find the primary FTD data
    sp500 = market_state.get("sp500", {})
    nasdaq = market_state.get("nasdaq", {})
    dual = market_state.get("dual_confirmation", False)

    # Use whichever index confirmed FTD
    ftd_data = None
    ftd_source = None
    for label, idx_data in [("S&P 500", sp500), ("NASDAQ", nasdaq)]:
        ftd = idx_data.get("ftd", {})
        if ftd and ftd.get("ftd_detected"):
            ftd_data = ftd
            ftd_source = label
            break

    if ftd_data is None:
        return {
            "total_score": 0,
            "breakdown": {},
            "signal": "No FTD",
            "guidance": "No Follow-Through Day detected. Stay defensive.",
            "exposure_range": "0-25%",
        }

    # 1. Base score from FTD day number
    day_num = ftd_data.get("ftd_day_number", 0)
    if 4 <= day_num <= 7:
        base = 60
        breakdown["base"] = f"Day {day_num} FTD: +60 (prime window)"
    elif 8 <= day_num <= 10:
        base = 50
        breakdown["base"] = f"Day {day_num} FTD: +50 (late window)"
    else:
        base = 40
        breakdown["base"] = f"Day {day_num} FTD: +40 (out of window)"
    score += base

    # 2. Price gain bonus
    gain = ftd_data.get("gain_pct", 0)
    if gain >= FTD_GAIN_STRONG:
        gain_bonus = 15
        breakdown["gain"] = f"{gain:+.2f}% gain: +15 (strong)"
    elif gain >= FTD_GAIN_RECOMMENDED:
        gain_bonus = 10
        breakdown["gain"] = f"{gain:+.2f}% gain: +10 (recommended)"
    elif gain >= FTD_GAIN_MINIMUM:
        gain_bonus = 5
        breakdown["gain"] = f"{gain:+.2f}% gain: +5 (minimum)"
    else:
        gain_bonus = 0
        breakdown["gain"] = f"{gain:+.2f}% gain: +0"
    score += gain_bonus

    # 3. Volume vs 50-day average
    vol_above = ftd_data.get("volume_above_avg")
    if vol_above is True:
        vol_bonus = 10
        breakdown["volume"] = "Above 50-day avg volume: +10"
    elif vol_above is False:
        vol_bonus = 0
        breakdown["volume"] = "Below 50-day avg volume: +0"
    else:
        vol_bonus = 0
        breakdown["volume"] = "Volume avg data unavailable: +0"
    score += vol_bonus

    # 4. Dual index confirmation
    if dual:
        dual_bonus = 15
        breakdown["dual_confirm"] = "Both S&P 500 + NASDAQ confirmed: +15"
    else:
        dual_bonus = 0
        breakdown["dual_confirm"] = f"Single index ({ftd_source}): +0"
    score += dual_bonus

    # 5. Post-FTD health (distribution days)
    post_ftd = market_state.get("post_ftd_distribution", {})
    dist_count = post_ftd.get("distribution_count", 0)
    days_monitored = post_ftd.get("days_monitored", 0)
    earliest_dist = post_ftd.get("earliest_distribution_day")

    if days_monitored == 0:
        health_adj = 0
        breakdown["post_ftd"] = "Post-FTD data not yet available: +0"
    elif dist_count == 0:
        health_adj = 10
        breakdown["post_ftd"] = f"No post-FTD distribution ({days_monitored} days clean): +10"
    elif earliest_dist is not None and earliest_dist <= 2:
        health_adj = -30
        breakdown["post_ftd"] = f"Distribution on Day {earliest_dist}: -30 (very bearish)"
    elif earliest_dist is not None and earliest_dist == 3:
        health_adj = -15
        breakdown["post_ftd"] = f"Distribution on Day 3: -15 (moderately bearish)"
    elif earliest_dist is not None and earliest_dist >= 4:
        health_adj = -5
        breakdown["post_ftd"] = f"Distribution on Day {earliest_dist}: -5 (mild negative)"
    else:
        health_adj = 0
        breakdown["post_ftd"] = "Post-FTD data unavailable: +0"
    score += health_adj

    # Clamp score
    score = max(0, min(100, score))

    # Determine signal and guidance
    if score >= 80:
        signal = "Strong FTD"
        guidance = "Aggressively increase exposure to 75-100%."
        exposure = "75-100%"
    elif score >= 60:
        signal = "Moderate FTD"
        guidance = "Gradually increase exposure to 50-75%."
        exposure = "50-75%"
    elif score >= 40:
        signal = "Weak FTD"
        guidance = "Cautious increase to 25-50%, use tight stops."
        exposure = "25-50%"
    else:
        signal = "Failed/Weak"
        guidance = "Stay defensive, wait for new signal."
        exposure = "0-25%"

    return {
        "total_score": score,
        "breakdown": breakdown,
        "signal": signal,
        "guidance": guidance,
        "exposure_range": exposure,
        "ftd_source": ftd_source,
    }


def assess_post_ftd_health(market_state: Dict,
                            sp500_history: List[Dict],
                            nasdaq_history: List[Dict]) -> Dict:
    """
    Full post-FTD health assessment including distribution, invalidation,
    and power trend.

    Args:
        market_state: Output from get_market_state()
        sp500_history: S&P 500 chronological history
        nasdaq_history: NASDAQ chronological history

    Returns:
        Enriched market_state with post-FTD analysis
    """
    # Find which index has the confirmed FTD
    for label, idx_data, hist in [
        ("sp500", market_state.get("sp500", {}), sp500_history),
        ("nasdaq", market_state.get("nasdaq", {}), nasdaq_history),
    ]:
        ftd = idx_data.get("ftd", {})
        if ftd and ftd.get("ftd_detected") and hist:
            # Find FTD index in history
            ftd_date = ftd.get("ftd_date")
            ftd_idx = None
            for i, d in enumerate(hist):
                if d.get("date") == ftd_date:
                    ftd_idx = i
                    break

            if ftd_idx is not None:
                # Distribution check
                dist = count_post_ftd_distribution(hist, ftd_idx)
                market_state["post_ftd_distribution"] = dist

                # Invalidation check
                inv = check_ftd_invalidation(hist, ftd_idx)
                market_state["ftd_invalidation"] = inv

                if inv.get("invalidated"):
                    market_state["combined_state"] = "FTD_INVALIDATED"

                break  # Use first confirmed FTD index only (matches quality score logic)

    # Power trend check (use S&P 500 as primary)
    if sp500_history and len(sp500_history) >= 50:
        market_state["power_trend"] = detect_power_trend(sp500_history)
    else:
        market_state["power_trend"] = {
            "power_trend": False,
            "reason": "Insufficient S&P 500 data",
        }

    # Calculate quality score
    market_state["quality_score"] = calculate_ftd_quality_score(market_state)

    return market_state


# --- Helper ---

# Import thresholds from rally_tracker
FTD_GAIN_STRONG = 2.0
FTD_GAIN_RECOMMENDED = 1.5
FTD_GAIN_MINIMUM = 1.25


def _calculate_ema(prices: List[float], period: int) -> float:
    """Calculate EMA from chronological price list."""
    if len(prices) < period:
        return sum(prices) / len(prices) if prices else 0

    sma = sum(prices[:period]) / period
    ema = sma
    k = 2 / (period + 1)
    for price in prices[period:]:
        ema = price * k + ema * (1 - k)
    return ema
