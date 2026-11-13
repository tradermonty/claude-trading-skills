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

Data gaps (issue #655): a missing or non-finite close/volume is never read as 0
and bars are never dropped (the state machine compares positionally adjacent
sessions, so dropping a bar can fabricate an FTD). Each function validates the
exact slice it reads and returns its conservative degraded shape with
``data_gap: True`` and a ``reason`` instead of comparing missing operands.
"""

from enum import Enum
from typing import Optional

from _price_bars import find_bar_gaps, read_price


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

# Rally-tracker windows look back 60 sessions
ANALYSIS_LOOKBACK = 60
CLOSE_VOLUME = ("close", "volume")


def bar_gaps(bars: list[dict], required: tuple = CLOSE_VOLUME) -> dict:
    """Gap report for a chronological slice.

    Volume 0 is invalid here: for the indices this skill reads (^GSPC, QQQ) a
    zero session volume is provider missing data, and treating it as real can
    hide a distribution day or an invalidated FTD.
    """
    return find_bar_gaps(bars, required, order="chronological")


def gap_reason(gaps: dict, where: str) -> str:
    """Human-readable data-gap reason for a find_bar_gaps report."""
    return (
        f"Data gap: {gaps['bad_bars']} bar(s) with missing or invalid "
        f"{'/'.join(gaps['required'])} {where} (latest bad: {gaps['latest_bad']})"
    )


def _low_or_close(bar: dict) -> float:
    """Intraday low, falling back to the (already validated) close."""
    return read_price(bar, "low") or bar["close"]


def _is_swing_low(history: list[dict], i: int) -> Optional[dict]:
    """Check if index i in history qualifies as a swing low.

    Returns dict with swing low details, or None. A bar with a missing or
    invalid close in the range this check reads means "not a swing low".
    """
    n = len(history)
    search_start = max(0, i - 40)
    if bar_gaps(history[search_start : i + 2], ("close",))["bad_bars"]:
        return None
    low_close = history[i]["close"]

    # Look back up to 40 days for a recent high
    recent_high = 0
    recent_high_idx = search_start
    for j in range(search_start, i):
        c = history[j]["close"]
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
        if history[j]["close"] < history[j - 1]["close"]:
            down_days += 1

    if down_days < MIN_DOWN_DAYS:
        return None

    # Verify it's a local minimum (not lower closes immediately adjacent)
    if i > 0 and history[i - 1]["close"] < low_close:
        return None
    if i + 1 < n and history[i + 1]["close"] < low_close:
        return None

    return {
        "swing_low_idx": i,
        "swing_low_price": low_close,
        "swing_low_date": history[i].get("date", "N/A"),
        "swing_low_low": read_price(history[i], "low") or low_close,
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
        On a missing or invalid close/volume between the swing low and the
        latest bar, the "no rally" shape with ``data_gap: True`` and a
        ``reason``; no rally day is ever counted across a gap.
    """
    n = len(history)

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

    gaps = bar_gaps(history[swing_low_idx:])
    if gaps["bad_bars"]:
        result["data_gap"] = True
        result["reason"] = gap_reason(gaps, "since the swing low")
        return result

    if swing_low_idx >= n - 1:
        return result

    swing_low_price = history[swing_low_idx]["close"]

    # Find Day 1
    day1_idx = None
    for i in range(swing_low_idx + 1, n):
        curr_close = history[i]["close"]
        prev_close = history[i - 1]["close"]

        # Check invalidation first: close below swing low
        if curr_close < swing_low_price:
            result["invalidated"] = True
            result["invalidation_reason"] = (
                f"Close ${curr_close:.2f} below swing low ${swing_low_price:.2f} "
                f"on {history[i].get('date', 'N/A')}"
            )
            return result

        # Day 1: up close OR close in top 50% of range
        if curr_close > prev_close:
            day1_idx = i
            break
        # The range rule needs a real high and low; without either, only an
        # up close can qualify Day 1 (a missing high must not fake the top 50%).
        curr_high = read_price(history[i], "high")
        curr_low = read_price(history[i], "low")
        if curr_high is None or curr_low is None:
            continue
        day_range = curr_high - curr_low
        if day_range > 0:
            close_position = (curr_close - curr_low) / day_range
            if close_position >= 0.5:
                day1_idx = i
                break

    if day1_idx is None:
        return result

    day1_low = _low_or_close(history[day1_idx])
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
            "close": history[day1_idx]["close"],
            "volume": history[day1_idx]["volume"],
        }
    ]

    for i in range(day1_idx + 1, n):
        curr_close = history[i]["close"]
        prev_close = history[i - 1]["close"]
        curr_volume = history[i]["volume"]
        prev_volume = history[i - 1]["volume"]

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
                    round((curr_volume / prev_volume - 1) * 100, 1) if prev_volume > 0 else 0
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
        ``ftd_detected: False`` with ``data_gap: True`` and a ``reason`` when a
        bar it would read (a candidate day, the day before it, or the volume
        lookback) has a missing or invalid value.
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
    if rally_data.get("data_gap"):
        result["data_gap"] = True
        result["reason"] = rally_data.get("reason", "Data gap in rally attempt")
        return result

    rally_days = rally_data.get("rally_days", [])
    candidates = [
        d for d in rally_days if FTD_DAY_START <= d["day"] <= FTD_DAY_END and d["idx"] > 0
    ]
    if candidates:
        first_idx = min(d["idx"] for d in candidates)
        last_idx = max(d["idx"] for d in candidates)
        for gaps, where in (
            (bar_gaps(history[first_idx - 1 : last_idx + 1]), "in the FTD window"),
            (
                bar_gaps(history[max(0, first_idx - 50) : last_idx], ("volume",)),
                "in the 50-day volume lookback",
            ),
        ):
            if gaps["bad_bars"]:
                result["data_gap"] = True
                result["reason"] = gap_reason(gaps, where)
                return result

    for day_info in candidates:
        day_num = day_info["day"]
        change_pct = day_info["change_pct"]
        if change_pct < FTD_GAIN_MINIMUM:
            continue

        # Volume must be higher than previous day
        idx = day_info["idx"]
        curr_volume = day_info["volume"]
        prev_volume = history[idx - 1]["volume"]

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
        volumes = [d["volume"] for d in lookback_bars if d["volume"] > 0]
        pit_avg = sum(volumes) / len(volumes) if volumes else 0
        volume_above_avg = curr_volume > pit_avg if pit_avg > 0 else None

        result.update(
            {
                "ftd_detected": True,
                "ftd_day_number": day_num,
                "ftd_date": day_info.get("date", "N/A"),
                "ftd_price": day_info["close"],
                "ftd_low": read_price(history[idx], "low") or day_info["close"],
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
    volumes = [read_price(d, "volume") for d in history[-period:]]
    volumes = [v for v in volumes if v is not None]  # missing, invalid and 0 are skipped
    return sum(volumes) / len(volumes) if volumes else 0


def window_quality(gaps: dict) -> dict:
    """Compact data-quality summary of a find_bar_gaps report for the JSON output."""
    return {
        "window_sessions": gaps["checked_bars"],
        "bad_bars": gaps["bad_bars"],
        "bad_dates": gaps["bad_dates"],
        "latest_bad": gaps["latest_bad"],
        "required": gaps["required"],
    }


def analyze_single_index(history: list[dict], index_name: str) -> dict:
    """
    Run full FTD analysis for a single index.

    Args:
        history: Daily OHLCV in chronological order (oldest first)
        index_name: Label (e.g., "S&P 500", "NASDAQ")

    Returns:
        Complete analysis dict for this index. ``data_quality`` summarizes the
        close/volume check of the 60-session window. If any bar in that window
        has a missing or invalid close or volume, the result is the early-exit
        shape (``NO_SIGNAL``, prices ``None``) with ``data_gap: True`` and an
        ``error`` naming the gap; no rally or FTD logic runs.
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

    # Use last 60 trading days for analysis (the only bars the state machine reads)
    lookback = min(ANALYSIS_LOOKBACK, len(history or []))
    analysis_window = history[-lookback:] if lookback else []
    gaps = bar_gaps(analysis_window)
    result["data_quality"] = window_quality(gaps)

    if not history or len(history) < 10:
        result["error"] = "Insufficient data"
        return result

    if gaps["bad_bars"]:
        result["error"] = gap_reason(gaps, f"in the last {lookback} sessions")
        result["data_gap"] = True
        return result

    result["current_price"] = analysis_window[-1]["close"]

    # Find the highest close in the window
    max_close = 0
    for d in analysis_window:
        c = d["close"]
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
                    ftd_low = _low_or_close(analysis_window[ftd_idx])
                    invalidated = any(
                        analysis_window[j]["close"] < ftd_low
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
        ftd_low = _low_or_close(analysis_window[ftd_idx])
        invalidated = any(
            analysis_window[j]["close"] < ftd_low for j in range(ftd_idx + 1, len(analysis_window))
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

    # True when either index's 60-session window has a missing/invalid bar
    data_gap = bool(sp500_analysis.get("data_gap") or nasdaq_analysis.get("data_gap"))
    if data_gap:
        # A gapped index drops its own FTD context, so promoting the other
        # index could report a state more bullish than the healed data (e.g. an
        # invalidated S&P FTD hidden behind a NASDAQ confirmation). The combined
        # state is therefore unavailable: NO_SIGNAL with data_gap, no FTD source.
        # Each index's own analysis stays in the output for transparency.
        combined_state = MarketState.NO_SIGNAL.value
        dual_confirmation = False
        ftd_index = None

    return {
        "combined_state": combined_state,
        "dual_confirmation": dual_confirmation,
        "ftd_index": ftd_index,
        "sp500": sp500_analysis,
        "nasdaq": nasdaq_analysis,
        "data_gap": data_gap,
    }
