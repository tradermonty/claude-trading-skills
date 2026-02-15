#!/usr/bin/env python3
"""
FTD Detector - Rally Tracker (State Machine)

Implements a state machine for tracking market correction → rally attempt → FTD sequence.
Supports dual-index tracking (S&P 500 + NASDAQ/QQQ).

States:
  NO_SIGNAL → CORRECTION → RALLY_ATTEMPT → FTD_WINDOW → FTD_CONFIRMED
                   ↑              ↓               ↓              ↓
                   └── RALLY_FAILED ←─────────────┘     FTD_INVALIDATED

O'Neil's FTD Rules:
- Swing low: 3%+ decline from recent high with 3+ down days
- Day 1: first up close (or close in top 50% of range) after swing low
- Day 2-3: close must not breach Day 1 intraday low
- Day 4-10: FTD requires >=1.25% gain on volume > previous day
"""

from typing import Dict, List, Optional, Tuple
from enum import Enum


class MarketState(Enum):
    NO_SIGNAL = "NO_SIGNAL"
    CORRECTION = "CORRECTION"
    RALLY_ATTEMPT = "RALLY_ATTEMPT"
    FTD_WINDOW = "FTD_WINDOW"
    FTD_CONFIRMED = "FTD_CONFIRMED"
    RALLY_FAILED = "RALLY_FAILED"
    FTD_INVALIDATED = "FTD_INVALIDATED"


# Minimum correction depth to qualify
MIN_CORRECTION_PCT = 3.0
# Minimum down days during correction
MIN_DOWN_DAYS = 3
# FTD window bounds (inclusive)
FTD_DAY_START = 4
FTD_DAY_END = 10
# Minimum FTD gain thresholds
FTD_GAIN_MINIMUM = 1.25
FTD_GAIN_RECOMMENDED = 1.5
FTD_GAIN_STRONG = 2.0


def find_swing_low(history: List[Dict]) -> Optional[Dict]:
    """
    Find the most recent swing low in chronological history.

    A swing low requires:
    1. A decline of MIN_CORRECTION_PCT from a recent high (within 40 days)
    2. At least MIN_DOWN_DAYS down days during the decline
    3. Must be a local minimum (not lower closes on both adjacent days)

    Args:
        history: Daily OHLCV in chronological order (oldest first)

    Returns:
        Dict with swing_low_idx, swing_low_price, swing_low_date,
        recent_high_price, decline_pct, down_days, or None
    """
    if not history or len(history) < 5:
        return None

    n = len(history)

    # Scan from recent to old to find the most recent swing low
    for i in range(n - 1, 3, -1):
        low_close = history[i].get("close", 0)
        if low_close <= 0:
            continue

        # Look back up to 40 days for a recent high
        search_start = max(0, i - 40)
        recent_high = 0
        recent_high_idx = search_start
        for j in range(search_start, i):
            c = history[j].get("close", 0)
            if c > recent_high:
                recent_high = c
                recent_high_idx = j

        if recent_high <= 0:
            continue

        decline_pct = (low_close - recent_high) / recent_high * 100

        if decline_pct > -MIN_CORRECTION_PCT:
            continue

        # Count down days from high to this point
        down_days = 0
        for j in range(recent_high_idx + 1, i + 1):
            prev_c = history[j - 1].get("close", 0)
            curr_c = history[j].get("close", 0)
            if prev_c > 0 and curr_c < prev_c:
                down_days += 1

        if down_days < MIN_DOWN_DAYS:
            continue

        # Verify it's a local minimum (not lower closes immediately adjacent)
        is_local_low = True
        if i > 0:
            prev_close = history[i - 1].get("close", 0)
            if prev_close > 0 and prev_close < low_close:
                is_local_low = False
        if i + 1 < n:
            next_close = history[i + 1].get("close", 0)
            if next_close > 0 and next_close < low_close:
                is_local_low = False

        if not is_local_low:
            continue

        return {
            "swing_low_idx": i,
            "swing_low_price": low_close,
            "swing_low_date": history[i].get("date", "N/A"),
            "swing_low_low": history[i].get("low", low_close),
            "recent_high_price": recent_high,
            "recent_high_idx": recent_high_idx,
            "recent_high_date": history[recent_high_idx].get("date", "N/A"),
            "decline_pct": round(decline_pct, 2),
            "down_days": down_days,
        }

    return None


def track_rally_attempt(history: List[Dict], swing_low_idx: int) -> Dict:
    """
    Track rally attempt starting after swing low.

    Day 1: First up close OR close in top 50% of day's range after swing low.
    Day 2-3: Close must not breach Day 1 intraday low.
    Invalidation: Close below swing low resets the attempt.

    Args:
        history: Daily OHLCV in chronological order
        swing_low_idx: Index of the swing low in history

    Returns:
        Dict with day1_idx, current_day, rally_days list, invalidated flag, etc.
    """
    n = len(history)
    swing_low_price = history[swing_low_idx].get("close", 0)

    result = {
        "day1_idx": None,
        "day1_date": None,
        "day1_low": None,
        "current_day_count": 0,
        "rally_days": [],
        "invalidated": False,
        "invalidation_reason": None,
        "reset_count": 0,
    }

    if swing_low_idx >= n - 1:
        return result

    # Find Day 1
    day1_idx = None
    for i in range(swing_low_idx + 1, n):
        curr_close = history[i].get("close", 0)
        prev_close = history[i - 1].get("close", 0)
        curr_high = history[i].get("high", curr_close)
        curr_low = history[i].get("low", curr_close)

        # Check invalidation first: close below swing low
        if curr_close < swing_low_price:
            result["invalidated"] = True
            result["invalidation_reason"] = (
                f"Close ${curr_close:.2f} below swing low ${swing_low_price:.2f} "
                f"on {history[i].get('date', 'N/A')}"
            )
            return result

        # Day 1: up close OR close in top 50% of range
        day_range = curr_high - curr_low
        if prev_close > 0 and curr_close > prev_close:
            day1_idx = i
            break
        elif day_range > 0:
            close_position = (curr_close - curr_low) / day_range
            if close_position >= 0.5:
                day1_idx = i
                break

    if day1_idx is None:
        return result

    day1_low = history[day1_idx].get("low", history[day1_idx].get("close", 0))
    result["day1_idx"] = day1_idx
    result["day1_date"] = history[day1_idx].get("date", "N/A")
    result["day1_low"] = day1_low

    # Track days from Day 1 onward
    day_count = 1
    rally_days = [{
        "day": 1,
        "idx": day1_idx,
        "date": history[day1_idx].get("date", "N/A"),
        "close": history[day1_idx].get("close", 0),
        "volume": history[day1_idx].get("volume", 0),
    }]

    for i in range(day1_idx + 1, n):
        curr_close = history[i].get("close", 0)
        prev_close = history[i - 1].get("close", 0)
        curr_volume = history[i].get("volume", 0)

        # Invalidation: close below swing low
        if curr_close < swing_low_price:
            result["invalidated"] = True
            result["invalidation_reason"] = (
                f"Close ${curr_close:.2f} below swing low ${swing_low_price:.2f} "
                f"on {history[i].get('date', 'N/A')}"
            )
            break

        # Day 2-3 special check: close must not breach Day 1 intraday low
        day_count += 1
        if day_count <= 3 and curr_close < day1_low:
            result["invalidated"] = True
            result["invalidation_reason"] = (
                f"Day {day_count} close ${curr_close:.2f} below Day 1 low "
                f"${day1_low:.2f} on {history[i].get('date', 'N/A')}"
            )
            break

        change_pct = 0
        if prev_close > 0:
            change_pct = (curr_close - prev_close) / prev_close * 100

        rally_days.append({
            "day": day_count,
            "idx": i,
            "date": history[i].get("date", "N/A"),
            "close": curr_close,
            "volume": curr_volume,
            "change_pct": round(change_pct, 2),
            "volume_vs_prev": (
                round((curr_volume / history[i - 1].get("volume", 1) - 1) * 100, 1)
                if history[i - 1].get("volume", 0) > 0 else 0
            ),
        })

    result["current_day_count"] = day_count
    result["rally_days"] = rally_days
    return result


def detect_ftd(history: List[Dict], rally_data: Dict,
               avg_volume_50d: Optional[float] = None) -> Dict:
    """
    Detect Follow-Through Day within the FTD window (Day 4-10).

    FTD Criteria:
    - Day 4-10 of rally attempt
    - Price gain >= 1.25% (minimum), 1.5% (recommended), 2.0% (strong)
    - Volume > previous day (mandatory)
    - Volume > 50-day average (bonus)

    Args:
        history: Daily OHLCV in chronological order
        rally_data: Output from track_rally_attempt()
        avg_volume_50d: Optional 50-day average volume for bonus scoring

    Returns:
        Dict with ftd_detected, ftd_day_number, gain_pct, volume details, etc.
    """
    result = {
        "ftd_detected": False,
        "ftd_day_number": None,
        "ftd_date": None,
        "ftd_price": None,
        "gain_pct": None,
        "volume": None,
        "prev_day_volume": None,
        "volume_above_avg": None,
        "gain_tier": None,
    }

    if rally_data.get("invalidated"):
        return result

    rally_days = rally_data.get("rally_days", [])

    for day_info in rally_days:
        day_num = day_info.get("day", 0)
        if day_num < FTD_DAY_START or day_num > FTD_DAY_END:
            continue

        change_pct = day_info.get("change_pct", 0)
        if change_pct < FTD_GAIN_MINIMUM:
            continue

        # Volume must be higher than previous day
        idx = day_info.get("idx", 0)
        curr_volume = day_info.get("volume", 0)
        prev_volume = history[idx - 1].get("volume", 0) if idx > 0 else 0

        if prev_volume <= 0 or curr_volume <= prev_volume:
            continue

        # FTD detected
        if change_pct >= FTD_GAIN_STRONG:
            gain_tier = "strong"
        elif change_pct >= FTD_GAIN_RECOMMENDED:
            gain_tier = "recommended"
        else:
            gain_tier = "minimum"

        volume_above_avg = None
        if avg_volume_50d and avg_volume_50d > 0:
            volume_above_avg = curr_volume > avg_volume_50d

        result.update({
            "ftd_detected": True,
            "ftd_day_number": day_num,
            "ftd_date": day_info.get("date", "N/A"),
            "ftd_price": day_info.get("close", 0),
            "gain_pct": change_pct,
            "volume": curr_volume,
            "prev_day_volume": prev_volume,
            "volume_above_avg": volume_above_avg,
            "gain_tier": gain_tier,
        })
        break  # Take the first qualifying FTD

    return result


def calculate_avg_volume(history: List[Dict], period: int = 50) -> float:
    """Calculate average volume over the specified period (most recent data)."""
    if not history:
        return 0
    volumes = [d.get("volume", 0) for d in history[-period:] if d.get("volume", 0) > 0]
    return sum(volumes) / len(volumes) if volumes else 0


def analyze_single_index(history: List[Dict], index_name: str) -> Dict:
    """
    Run full FTD analysis for a single index.

    Args:
        history: Daily OHLCV in chronological order (oldest first)
        index_name: Label (e.g., "S&P 500", "NASDAQ")

    Returns:
        Complete analysis dict for this index
    """
    result = {
        "index": index_name,
        "state": MarketState.NO_SIGNAL.value,
        "swing_low": None,
        "rally_attempt": None,
        "ftd": None,
        "current_price": None,
        "lookback_high": None,
        "correction_depth_pct": None,
    }

    if not history or len(history) < 10:
        result["error"] = "Insufficient data"
        return result

    # Use last 60 trading days for analysis
    lookback = min(60, len(history))
    analysis_window = history[-lookback:]
    n = len(analysis_window)

    result["current_price"] = analysis_window[-1].get("close", 0)

    # Find the highest close in the window
    max_close = 0
    for d in analysis_window:
        c = d.get("close", 0)
        if c > max_close:
            max_close = c
    result["lookback_high"] = max_close

    if max_close > 0 and result["current_price"] > 0:
        result["correction_depth_pct"] = round(
            (result["current_price"] - max_close) / max_close * 100, 2
        )

    # Do NOT early-return based on current correction depth.
    # A valid FTD may be in progress even if price has recovered near highs.
    # Instead, let find_swing_low() determine whether a qualifying correction occurred.

    # Find swing low
    swing_low = find_swing_low(analysis_window)
    if swing_low is None:
        return result

    result["swing_low"] = swing_low
    result["state"] = MarketState.CORRECTION.value

    # Track rally attempt
    rally = track_rally_attempt(analysis_window, swing_low["swing_low_idx"])
    result["rally_attempt"] = rally

    if rally["invalidated"]:
        result["state"] = MarketState.RALLY_FAILED.value
        return result

    if rally["day1_idx"] is None:
        # Still in correction, no rally attempt started
        return result

    day_count = rally["current_day_count"]

    if day_count < FTD_DAY_START:
        result["state"] = MarketState.RALLY_ATTEMPT.value
        return result

    # In FTD window or beyond
    result["state"] = MarketState.FTD_WINDOW.value

    # Calculate 50-day average volume for scoring
    avg_vol = calculate_avg_volume(analysis_window)

    # Detect FTD
    ftd = detect_ftd(analysis_window, rally, avg_volume_50d=avg_vol)
    result["ftd"] = ftd

    if ftd["ftd_detected"]:
        result["state"] = MarketState.FTD_CONFIRMED.value

    elif day_count > FTD_DAY_END:
        # FTD window passed without qualifying day
        result["state"] = MarketState.RALLY_FAILED.value

    return result


def get_market_state(sp500_history: List[Dict],
                     nasdaq_history: List[Dict]) -> Dict:
    """
    Analyze both indices and produce a merged market state assessment.

    Priority logic:
    - If either index has FTD_CONFIRMED → overall FTD (single sufficient)
    - If both have FTD_CONFIRMED → strong FTD (dual confirmation)
    - Otherwise, use the more advanced state

    Args:
        sp500_history: S&P 500 daily OHLCV, most recent first (API format)
        nasdaq_history: NASDAQ/QQQ daily OHLCV, most recent first (API format)

    Returns:
        Combined market state with both index analyses
    """
    # Convert to chronological order (oldest first)
    sp500_chrono = list(reversed(sp500_history)) if sp500_history else []
    nasdaq_chrono = list(reversed(nasdaq_history)) if nasdaq_history else []

    sp500_analysis = analyze_single_index(sp500_chrono, "S&P 500")
    nasdaq_analysis = analyze_single_index(nasdaq_chrono, "NASDAQ")

    sp500_state = MarketState(sp500_analysis["state"])
    nasdaq_state = MarketState(nasdaq_analysis["state"])

    # Determine combined state
    sp500_ftd = sp500_state == MarketState.FTD_CONFIRMED
    nasdaq_ftd = nasdaq_state == MarketState.FTD_CONFIRMED

    if sp500_ftd and nasdaq_ftd:
        combined_state = MarketState.FTD_CONFIRMED.value
        dual_confirmation = True
    elif sp500_ftd or nasdaq_ftd:
        combined_state = MarketState.FTD_CONFIRMED.value
        dual_confirmation = False
    else:
        # Use the more advanced (hopeful) state
        state_priority = [
            MarketState.FTD_WINDOW,
            MarketState.RALLY_ATTEMPT,
            MarketState.CORRECTION,
            MarketState.RALLY_FAILED,
            MarketState.FTD_INVALIDATED,
            MarketState.NO_SIGNAL,
        ]
        combined_state = MarketState.NO_SIGNAL.value
        for state in state_priority:
            if sp500_state == state or nasdaq_state == state:
                combined_state = state.value
                break
        dual_confirmation = False

    # Determine which index triggered FTD (if any)
    ftd_index = None
    if sp500_ftd:
        ftd_index = "S&P 500"
    if nasdaq_ftd:
        ftd_index = "NASDAQ" if ftd_index is None else "Both"

    return {
        "combined_state": combined_state,
        "dual_confirmation": dual_confirmation,
        "ftd_index": ftd_index,
        "sp500": sp500_analysis,
        "nasdaq": nasdaq_analysis,
    }
