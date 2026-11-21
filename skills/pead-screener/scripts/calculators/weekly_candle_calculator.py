#!/usr/bin/env python3
"""
Weekly Candle Calculator for PEAD Screener

Converts daily OHLCV prices to weekly candles using ISO week (Monday start)
and analyzes patterns for Post-Earnings Announcement Drift (PEAD) setups.

Key Features:
- ISO week grouping (Monday-start weeks)
- Earnings week splitting (only post-earnings days)
- Partial week detection
- Red candle identification for pullback entry
- Stage-based pattern classification
"""

from datetime import date, datetime, timedelta
from typing import Optional

from _price_bars import read_price
from price_bar_utils import require_bars


def _aggregate_field(days, field, aggregate):
    values = [read_price(day, field, allow_zero=field == "volume") for day in days]
    if any(value is None for value in values):
        return None
    return aggregate(values)


def daily_to_weekly(daily_prices: list[dict], earnings_date: str = None) -> list[dict]:
    """
    Convert daily OHLCV to weekly candles using ISO week (Monday start).

    Args:
        daily_prices: Most-recent-first list of dicts with date, open, high,
                      low, close, volume
        earnings_date: If provided, split earnings week (only use post-earnings days)

    Rules:
    - Group by ISO week: date.isocalendar() -> (year, week)
    - Earnings week: only include days on/after earnings_date
    - Current (partial) week: mark with partial_week=True
    - Weekly OHLC: open=first_day_open, high=max(highs), low=min(lows),
                   close=last_day_close
    - Weekly volume: sum of daily volumes

    Returns:
        List of weekly candle dicts (most-recent-first):
        {
            "week_start": "YYYY-MM-DD",  # Monday date
            "year": int, "week": int,
            "open": float, "high": float, "low": float, "close": float,
            "volume": int,
            "is_green": bool,  # close >= open
            "partial_week": bool,
            "trading_days": int
        }
    """
    if not daily_prices:
        return []

    # Parse earnings date if provided
    earnings_dt = None
    if earnings_date:
        earnings_dt = _parse_date(earnings_date)

    # Sort daily prices chronologically (oldest first) for grouping
    sorted_prices = sorted(daily_prices, key=lambda p: p["date"])

    # Group by ISO week
    week_groups = {}
    for day in sorted_prices:
        day_dt = _parse_date(day["date"])
        iso_year, iso_week, _ = day_dt.isocalendar()
        week_key = (iso_year, iso_week)

        # Earnings week filter: only include days on or after earnings_date
        if earnings_dt:
            earnings_iso = earnings_dt.isocalendar()
            earnings_week_key = (earnings_iso[0], earnings_iso[1])
            if week_key == earnings_week_key and day_dt < earnings_dt:
                continue

        if week_key not in week_groups:
            week_groups[week_key] = []
        week_groups[week_key].append(day)

    # Determine current (most recent) week for partial detection
    if sorted_prices:
        latest_dt = _parse_date(sorted_prices[-1]["date"])
        latest_iso = latest_dt.isocalendar()
        latest_week_key = (latest_iso[0], latest_iso[1])

        # Check if the latest week is complete (has Friday data)
        # A week is partial if the latest day is not Friday (weekday 5 in isocalendar)
        is_latest_partial = latest_iso[2] < 5
    else:
        latest_week_key = None
        is_latest_partial = False

    # Build weekly candles
    weekly_candles = []
    for week_key in sorted(week_groups.keys()):
        days = week_groups[week_key]
        if not days:
            continue

        iso_year, iso_week = week_key

        # Calculate Monday date for this ISO week
        monday = _iso_week_to_monday(iso_year, iso_week)

        pre_earnings = (
            earnings_dt is not None
            and earnings_week_key in week_groups
            and week_key < earnings_week_key
        )
        if not pre_earnings:
            require_bars(days, ["open", "high", "low", "close", "volume"])

        # OHLCV aggregation
        week_open = read_price(days[0], "open")
        week_high = _aggregate_field(days, "high", max)
        week_low = _aggregate_field(days, "low", min)
        week_close = read_price(days[-1], "close")
        week_volume = _aggregate_field(days, "volume", sum)

        # Partial week detection
        partial = False
        if week_key == latest_week_key and is_latest_partial:
            partial = True
        # Earnings week with filtered days is also partial
        if earnings_dt:
            earnings_iso = earnings_dt.isocalendar()
            earnings_week_key = (earnings_iso[0], earnings_iso[1])
            if week_key == earnings_week_key and len(days) < 5:
                partial = True

        weekly_candles.append(
            {
                "week_start": monday.strftime("%Y-%m-%d"),
                "year": iso_year,
                "week": iso_week,
                "open": round(week_open, 2) if week_open is not None else None,
                "high": round(week_high, 2) if week_high is not None else None,
                "low": round(week_low, 2) if week_low is not None else None,
                "close": round(week_close, 2) if week_close is not None else None,
                "volume": week_volume,
                "is_green": (
                    week_close >= week_open
                    if week_close is not None and week_open is not None
                    else None
                ),
                "partial_week": partial,
                "trading_days": len(days),
            }
        )
        if not pre_earnings:
            # Rounded aggregates are consumed downstream too. Reject a value
            # rounded to zero here, inside the caller's per-symbol gap boundary.
            require_bars(
                [weekly_candles[-1]],
                ["open", "high", "low", "close", "volume"],
                date_key="week_start",
            )

    # Return most-recent-first
    weekly_candles.reverse()
    return weekly_candles


def find_red_candle(weekly_candles: list[dict], earnings_week_idx: int = None) -> Optional[dict]:
    """
    Find the most recent red candle (close < open) after earnings week.

    Args:
        weekly_candles: Most-recent-first list of weekly candle dicts
        earnings_week_idx: Index of the earnings week in weekly_candles
                          (0=most recent). If None, search from index 0.

    Returns:
        Dict with red candle info or None if not found:
        {
            "high": float, "low": float, "open": float, "close": float,
            "week_start": str, "week_index": int,
            "lower_wick_pct": float,  # (min(open,close) - low) / (high - low) * 100
            "volume_vs_avg": float  # this candle volume / avg of surrounding candles
        }
    """
    if not weekly_candles:
        return None

    # Start searching from the candle after the current (partial) week
    # but before or at the earnings week
    start_idx = 0
    end_idx = earnings_week_idx if earnings_week_idx is not None else len(weekly_candles) - 1

    for i in range(start_idx, min(end_idx, len(weekly_candles))):
        candle = weekly_candles[i]
        if not candle["is_green"]:  # Red candle: close < open
            # Calculate lower wick percentage
            candle_range = candle["high"] - candle["low"]
            if candle_range > 0:
                body_low = min(candle["open"], candle["close"])
                lower_wick_pct = (body_low - candle["low"]) / candle_range * 100
            else:
                lower_wick_pct = 0.0

            # Calculate volume vs surrounding candles average
            surrounding_volumes = []
            for j in range(max(0, i - 2), min(len(weekly_candles), i + 3)):
                if j != i:
                    require_bars([weekly_candles[j]], ["volume"], date_key="week_start")
                    surrounding_volumes.append(weekly_candles[j]["volume"])
            if surrounding_volumes:
                avg_vol = sum(surrounding_volumes) / len(surrounding_volumes)
                volume_vs_avg = candle["volume"] / avg_vol if avg_vol > 0 else 1.0
            else:
                volume_vs_avg = 1.0

            return {
                "high": candle["high"],
                "low": candle["low"],
                "open": candle["open"],
                "close": candle["close"],
                "week_start": candle["week_start"],
                "week_index": i,
                "lower_wick_pct": round(lower_wick_pct, 1),
                "volume_vs_avg": round(volume_vs_avg, 2),
            }

    return None


def analyze_weekly_pattern(
    weekly_candles: list[dict],
    earnings_date: str,
    watch_weeks: int = 5,
) -> dict:
    """
    Full weekly pattern analysis for PEAD.

    Args:
        weekly_candles: Most-recent-first list of weekly candle dicts
        earnings_date: Earnings announcement date (YYYY-MM-DD)
        watch_weeks: Maximum weeks to monitor after earnings (default: 5)

    Returns:
        {
            "weeks_since_earnings": int,
            "earnings_week_idx": int or None,
            "red_candle": dict or None,
            "is_breakout": bool,
            "breakout_pct": float,
            "stage": str  # MONITORING, SIGNAL_READY, BREAKOUT, EXPIRED
        }
    """
    result = {
        "weeks_since_earnings": 0,
        "earnings_week_idx": None,
        "red_candle": None,
        "is_breakout": False,
        "breakout_pct": 0.0,
        "stage": "MONITORING",
    }

    if not weekly_candles:
        return result

    # Find earnings week
    earnings_dt = _parse_date(earnings_date)
    earnings_iso = earnings_dt.isocalendar()
    earnings_week_key = (earnings_iso[0], earnings_iso[1])

    earnings_week_idx = None
    for i, candle in enumerate(weekly_candles):
        if candle["year"] == earnings_week_key[0] and candle["week"] == earnings_week_key[1]:
            earnings_week_idx = i
            break

    result["earnings_week_idx"] = earnings_week_idx

    # Calculate weeks since earnings
    if earnings_week_idx is not None:
        result["weeks_since_earnings"] = earnings_week_idx
    else:
        # Earnings week not in data; estimate from dates
        if weekly_candles:
            latest_dt = _parse_date(weekly_candles[0]["week_start"])
            delta_days = (latest_dt - earnings_dt).days
            result["weeks_since_earnings"] = max(0, delta_days // 7)

    # Check expiration
    if result["weeks_since_earnings"] > watch_weeks:
        result["stage"] = "EXPIRED"
        return result

    # Find red candle after earnings week
    red_candle = find_red_candle(
        weekly_candles,
        earnings_week_idx=earnings_week_idx,
    )
    result["red_candle"] = red_candle

    if red_candle is None:
        result["stage"] = "MONITORING"
        return result

    # Check for breakout: current (most recent) candle is green and price > red candle high
    current_candle = weekly_candles[0]
    if current_candle["is_green"] and current_candle["close"] > red_candle["high"]:
        result["is_breakout"] = True
        result["breakout_pct"] = round(
            (current_candle["close"] - red_candle["high"]) / red_candle["high"] * 100, 2
        )
        result["stage"] = "BREAKOUT"
    else:
        result["stage"] = "SIGNAL_READY"

    return result


def _parse_date(date_str: str) -> date:
    """Parse a date string in YYYY-MM-DD format."""
    return datetime.strptime(date_str, "%Y-%m-%d").date()


def _iso_week_to_monday(iso_year: int, iso_week: int) -> date:
    """Convert ISO year and week number to the Monday date of that week."""
    # January 4 is always in ISO week 1
    jan4 = date(iso_year, 1, 4)
    # Find the Monday of week 1
    week1_monday = jan4 - timedelta(days=jan4.weekday())
    # Add weeks to get target Monday
    return week1_monday + timedelta(weeks=iso_week - 1)
