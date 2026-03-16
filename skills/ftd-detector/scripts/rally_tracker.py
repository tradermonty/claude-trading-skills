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

from enum import Enum
from typing import Optional


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


def _is_swing_low(history: list[dict], i: int) -> Optional[dict]:
    """Check if index i in history qualifies as a swing low.

    Returns dict with swing low details, or None.
    """
    n = len(history)
    low_close = history[i].get("close", 0)
    if low_close <= 0:
        return None

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
        return None

    decline_pct = (low_close - recent_high) / recent_high * 100

    if decline_pct > -MIN_CORRECTION_PCT:
        return None

    # Count down days from high to this point
    down_days = 0
    for j in range(recent_high_idx + 1, i + 1):
        prev_c = history[j - 1].get("close", 0)
        curr_c = history[j].get("close", 0)
        if prev_c > 0 and curr_c < prev_c:
            down_days += 1

    if down_days < MIN_DOWN_DAYS:
        return None

    # Verify it's a local minimum (not lower closes immediately adjacent)
    if i > 0:
        prev_close = history[i - 1].get("close", 0)
        if prev_close > 0 and prev_close < low_close:
            return None
    if i + 1 < n:
        next_close = history[i + 1].get("close", 0)
        if next_close > 0 and next_close < low_close:
            return None

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


def find_swing_low(history: list[dict]) -> Optional[dict]:
    """Find the most recent qualifying swing low in chronological history."""
    if not history or len(history) < 5:
        return None
    for i in range(len(history) - 1, 3, -1):
        result = _is_swing_low(history, i)
        if result:
            return result
    return None


def _find_all_swing_lows(history: list[dict], max_count: int = 6) -> list[dict]:
    """Find all qualifying swing lows, most recent first (up to max_count)."""
    if not history or len(history) < 5:
        return []
    results = []
    for i in range(len(history) - 1, 3, -1):
        sl = _is_swing_low(history, i)
        if sl:
            results.append(sl)
            if len(results) >= max_count:
                break
    return results


def track_rally_attempt(history: list[dict], swing_low_idx: int) -> dict:
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
    rally_days = [
        {
            "day": 1,
            "idx": day1_idx,
            "date": history[day1_idx].get("date", "N/A"),
            "close": history[day1_idx].get("close", 0),
            "volume": history[day1_idx].get("volume", 0),
        }
    ]

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

        rally_days.append(
            {
                "day": day_count,
                "idx": i,
                "date": history[i].get("date", "N/A"),
                "close": curr_close,
                "volume": curr_volume,
                "change_pct": round(change_pct, 2),
                "volume_vs_prev": (
                    round((curr_volume / history[i - 1].get("volume", 1) - 1) * 100, 1)
                    if history[i - 1].get("volume", 0) > 0
                    else 0
                ),
            }
        )

    result["current_day_count"] = day_count
    result["rally_days"] = rally_days
    return result


def detect_ftd(history: list[dict], rally_data: dict) -> dict:
    """
    Detect Follow-Through Day within the FTD window (Day 4-10).

    FTD Criteria:
    - Day 4-10 of rally attempt
    - Price gain >= 1.25% (minimum), 1.5% (recommended), 2.0% (strong)
    - Volume > previous day (mandatory)
    - Volume > point-in-time 50-day average (bonus, no look-ahead)

    Args:
        history: Daily OHLCV in chronological order
        rally_data: Output from track_rally_attempt()

    Returns:
        Dict with ftd_detected, ftd_day_number, gain_pct, volume details, etc.
    """
    result = {
        "ftd_detected": False,
        "ftd_day_number": None,
        "ftd_date": None,
        "ftd_price": None,
        "ftd_low": None,
        "gain_pct": None,
        "volume": None,
        "prev_day_volume": None,
        "volume_above_avg": None,
        "gain_tier": None,
        "_ftd_idx": None,
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

        # Point-in-time 50-day average volume (no look-ahead)
        lookback_bars = history[max(0, idx - 50) : idx]
        volumes = [d.get("volume", 0) for d in lookback_bars if d.get("volume", 0) > 0]
        pit_avg = sum(volumes) / len(volumes) if volumes else 0
        volume_above_avg = curr_volume > pit_avg if pit_avg > 0 else None

        result.update(
            {
                "ftd_detected": True,
                "ftd_day_number": day_num,
                "ftd_date": day_info.get("date", "N/A"),
                "ftd_price": day_info.get("close", 0),
                "ftd_low": history[idx].get("low", day_info.get("close", 0)),
                "gain_pct": change_pct,
                "volume": curr_volume,
                "prev_day_volume": prev_volume,
                "volume_above_avg": volume_above_avg,
                "gain_tier": gain_tier,
                "_ftd_idx": idx,
            }
        )
        break  # Take the first qualifying FTD

    return result


def calculate_avg_volume(history: list[dict], period: int = 50) -> float:
    """Calculate average volume over the specified period (most recent data)."""
    if not history:
        return 0
    volumes = [d.get("volume", 0) for d in history[-period:] if d.get("volume", 0) > 0]
    return sum(volumes) / len(volumes) if volumes else 0


def analyze_single_index(history: list[dict], index_name: str) -> dict:
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
    len(analysis_window)

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

    swing_lows = _find_all_swing_lows(analysis_window)
    if not swing_lows:
        return result

    # ── Step 1: Process most recent swing low to determine current_state ──
    most_recent_sl = swing_lows[0]
    result["swing_low"] = most_recent_sl
    result["state"] = MarketState.CORRECTION.value

    rally = track_rally_attempt(analysis_window, most_recent_sl["swing_low_idx"])
    result["rally_attempt"] = rally

    if rally["invalidated"]:
        result["state"] = MarketState.RALLY_FAILED.value
    elif rally["day1_idx"] is None:
        pass  # CORRECTION
    else:
        day_count = rally["current_day_count"]
        if day_count < FTD_DAY_START:
            result["state"] = MarketState.RALLY_ATTEMPT.value
        else:
            result["state"] = MarketState.FTD_WINDOW.value
            ftd = detect_ftd(analysis_window, rally)
            result["ftd"] = ftd
            if ftd["ftd_detected"]:
                # Inline invalidation check
                ftd_idx = ftd.get("_ftd_idx")
                if ftd_idx is not None:
                    ftd_low = analysis_window[ftd_idx].get(
                        "low", analysis_window[ftd_idx].get("close", 0)
                    )
                    invalidated = any(
                        analysis_window[j].get("close", 0) < ftd_low
                        for j in range(ftd_idx + 1, len(analysis_window))
                    )
                    if not invalidated:
                        result["state"] = MarketState.FTD_CONFIRMED.value
                    else:
                        result["state"] = MarketState.FTD_INVALIDATED.value
                else:
                    result["state"] = MarketState.FTD_CONFIRMED.value
            elif day_count > FTD_DAY_END:
                result["state"] = MarketState.RALLY_FAILED.value

    # If Step 1 found FTD context (confirmed or invalidated), return immediately
    if result["state"] in (
        MarketState.FTD_CONFIRMED.value,
        MarketState.FTD_INVALIDATED.value,
    ):
        return result

    # ── Step 2: Search older swing lows for a valid FTD ──
    # Handles post-FTD pullback: new swing low exists but FTD low not breached
    current_state = result["state"]

    for older_sl in swing_lows[1:]:
        older_rally = track_rally_attempt(analysis_window, older_sl["swing_low_idx"])
        if older_rally["invalidated"] or older_rally["day1_idx"] is None:
            continue
        if older_rally["current_day_count"] < FTD_DAY_START:
            continue
        older_ftd = detect_ftd(analysis_window, older_rally)
        if not older_ftd["ftd_detected"]:
            continue

        # FTD found — inline invalidation check
        ftd_idx = older_ftd.get("_ftd_idx")
        if ftd_idx is None:
            continue
        ftd_low = analysis_window[ftd_idx].get("low", analysis_window[ftd_idx].get("close", 0))
        invalidated = any(
            analysis_window[j].get("close", 0) < ftd_low
            for j in range(ftd_idx + 1, len(analysis_window))
        )

        if not invalidated:
            # Valid FTD still active through post-FTD pullback
            result["swing_low"] = older_sl
            result["rally_attempt"] = older_rally
            result["ftd"] = older_ftd
            result["state"] = MarketState.FTD_CONFIRMED.value
            return result
        else:
            # Invalidated FTD — STOP (no fallback to even older FTDs)
            # If newer swing low has active rally, keep that state
            active_states = (
                MarketState.RALLY_ATTEMPT.value,
                MarketState.FTD_WINDOW.value,
            )
            if current_state not in active_states:
                result["swing_low"] = older_sl
                result["rally_attempt"] = older_rally
                result["ftd"] = older_ftd
                result["state"] = MarketState.FTD_INVALIDATED.value
            return result

    return result


def get_market_state(sp500_history: list[dict], nasdaq_history: list[dict]) -> dict:
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
        # FTD_INVALIDATED above CORRECTION: more informative than bare correction
        state_priority = [
            MarketState.FTD_WINDOW,
            MarketState.RALLY_ATTEMPT,
            MarketState.FTD_INVALIDATED,
            MarketState.CORRECTION,
            MarketState.RALLY_FAILED,
            MarketState.NO_SIGNAL,
        ]
        combined_state = MarketState.NO_SIGNAL.value
        for state in state_priority:
            if sp500_state == state or nasdaq_state == state:
                combined_state = state.value
                break
        dual_confirmation = False

    # Determine which index triggered FTD (confirmed or invalidated)
    ftd_index = None
    if sp500_ftd:
        ftd_index = "S&P 500"
    if nasdaq_ftd:
        ftd_index = "NASDAQ" if ftd_index is None else "Both"

    # Also track invalidated FTD index for reporting
    if ftd_index is None and combined_state == MarketState.FTD_INVALIDATED.value:
        for label, analysis in [("S&P 500", sp500_analysis), ("NASDAQ", nasdaq_analysis)]:
            if analysis.get("state") == MarketState.FTD_INVALIDATED.value:
                ftd_index = label
                break

    return {
        "combined_state": combined_state,
        "dual_confirmation": dual_confirmation,
        "ftd_index": ftd_index,
        "sp500": sp500_analysis,
        "nasdaq": nasdaq_analysis,
    }
