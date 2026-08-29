#!/usr/bin/env python3
"""
Market Analysis Utility Functions for Environment Report

This script provides common functions for market analysis report creation.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from _market_calendar import (
    CalendarUnavailableError,
    count_sessions,
    is_open_at,
    next_session_on_or_after,
    parse_aware_datetime,
    require_aware,
    session_for_date,
)

UTC = timezone.utc
MARKET_TIMEZONES = {
    "Tokyo": ("XTKS", "Asia/Tokyo"),
    "London": ("XLON", "Europe/London"),
    "New York": ("XNYS", "America/New_York"),
}


def _now() -> datetime:
    return datetime.now(UTC)


def _resolve_as_of(as_of: datetime | None) -> datetime:
    return require_aware(as_of if as_of is not None else _now(), name="as_of")


def _format_time(value: datetime) -> str:
    return f"{value:%H:%M} {value.tzname()}"


def get_market_session_times(as_of: datetime | None = None):
    """Return major market hours for the sessions on/after one aware instant.

    Shanghai, Hong Kong, and Singapore are display-only reference rows. Market
    status and trading-day calculations use the shared calendar contract.
    """
    instant = _resolve_as_of(as_of)
    result = {
        "Shanghai": {"open": "09:30 CST", "close": "15:00 CST", "lunch": "11:30-13:00"},
        "Hong Kong": {"open": "09:30 HKT", "close": "16:00 HKT", "lunch": "12:00-13:00"},
        "Singapore": {"open": "09:00 SGT", "close": "17:00 SGT", "lunch": "12:00-13:00"},
    }
    for market, (venue, timezone_name) in MARKET_TIMEZONES.items():
        local_date = instant.astimezone(ZoneInfo(timezone_name)).date()
        session = next_session_on_or_after(venue, local_date)
        lunch = None
        if session.break_start is not None and session.break_end is not None:
            lunch = f"{session.break_start:%H:%M}-{session.break_end:%H:%M}"
        result[market] = {
            "open": _format_time(session.market_open),
            "close": _format_time(session.market_close),
            "lunch": lunch,
            "session_date": session.session_date.isoformat(),
        }
    # Preserve the established display order.
    return {
        name: result[name]
        for name in ("Tokyo", "Shanghai", "Hong Kong", "Singapore", "London", "New York")
    }


def format_market_report_header(as_of: datetime | None = None):
    """Format report header"""
    now = _resolve_as_of(as_of)
    weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    return f"""
=====================================
📊 Daily Market Environment Report
=====================================
Created: {now.strftime("%Y-%m-%d")} ({weekdays[now.weekday()]}) {now.strftime("%H:%M %Z")}
=====================================
"""


def calculate_trading_days_to_event(
    event_date_str: str,
    as_of: datetime | None = None,
) -> int:
    """Count XNYS sessions from today (inclusive) to the event (exclusive)."""
    try:
        event_date = date.fromisoformat(event_date_str)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"event date must be YYYY-MM-DD: {event_date_str!r}") from exc
    today = _resolve_as_of(as_of).astimezone(ZoneInfo("America/New_York")).date()
    if event_date <= today:
        return 0
    return count_sessions(
        "XNYS",
        today,
        event_date,
        include_start=True,
        include_end=False,
    )


def format_percentage_change(value):
    """Format percentage change"""
    if value >= 0:
        return f"📈 +{value:.2f}%"
    else:
        return f"📉 {value:.2f}%"


def categorize_volatility(vix_value):
    """Categorize volatility based on VIX level"""
    if vix_value < 12:
        return "Low & Stable 😌"
    elif vix_value < 20:
        return "Normal Range 📊"
    elif vix_value < 30:
        return "Elevated ⚠️"
    elif vix_value < 40:
        return "High Volatility 🔥"
    else:
        return "Extreme Volatility 🚨"


def _market_state(name: str, venue: str, timezone_name: str, instant: datetime) -> str:
    local = instant.astimezone(ZoneInfo(timezone_name))
    session = session_for_date(venue, local.date())
    if session is None:
        return f"🔴 {name} Market: Closed (non-session)"
    if is_open_at(venue, instant):
        return f"🟢 {name} Market: Trading"
    if (
        session.break_start is not None
        and session.break_end is not None
        and session.break_start <= local < session.break_end
    ):
        return f"⏸️ {name} Market: Lunch break"
    if local < session.market_open:
        return f"⏰ {name} Market: Pre-market"
    return f"🔴 {name} Market: Closed"


def get_market_status(as_of: datetime | None = None):
    """Determine Tokyo and US cash-market status at one aware instant."""
    instant = _resolve_as_of(as_of)
    return "\n".join(
        [
            _market_state("Tokyo", "XTKS", "Asia/Tokyo", instant),
            _market_state("US", "XNYS", "America/New_York", instant),
        ]
    )


def generate_checklist():
    """Generate market analysis checklist"""
    return """
📋 Analysis Checklist
--------------------
□ US market status check
□ Asian market status check
□ European market status check
□ Forex rates (USD/JPY, EUR/USD, CNY)
□ Index futures movements
□ VIX level check
□ Oil & Gold prices
□ Economic calendar
□ Corporate earnings schedule
□ Central bank news
□ Geopolitical risks
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Show calendar-aware market environment details")
    parser.add_argument(
        "--as-of",
        help="Offset-bearing ISO-8601 timestamp (or Z); date-only values are rejected",
    )
    args = parser.parse_args(argv)
    try:
        instant = parse_aware_datetime(args.as_of) if args.as_of else _now()
        header = format_market_report_header(instant)
        status = get_market_status(instant)
        sessions = get_market_session_times(instant)
    except (ValueError, CalendarUnavailableError) as exc:
        parser.error(str(exc))

    print("Market Analysis Utility - Test Run")
    print(header)
    print("\nCurrent Market Status:")
    print(status)
    print("\nTrading Hours:")
    for market, times in sessions.items():
        lunch = f" (Lunch break: {times['lunch']})" if times.get("lunch") else ""
        print(f"  {market}: {times['open']} - {times['close']}{lunch}")
    print(generate_checklist())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
