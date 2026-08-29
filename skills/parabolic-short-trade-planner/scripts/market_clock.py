"""Calendar-aware ET helpers for Phase 3 (intraday trigger monitor).

Why this exists separately from the rest of the skill: Phase 1 + 2
work in calendar-day granularity (`as_of=YYYY-MM-DD`) where wall-time
doesn't matter. Phase 3 evaluates 5-min bars during a US regular
session, so it must reason about ET wall-clock time AND DST
transitions correctly. ``zoneinfo`` (stdlib in 3.9+) handles DST
automatically; we never do raw offset arithmetic.

XNYS holidays and early closes are resolved through the vendored shared
calendar contract. Calendar failures propagate instead of treating a weekday
as an open session.
"""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from _market_calendar import is_open_at, session_for_date

ET = ZoneInfo("America/New_York")


def _require_aware(ts: datetime) -> None:
    if ts.tzinfo is None:
        raise ValueError(
            "market_clock requires timezone-aware datetimes; got naive datetime "
            f"{ts!r}. Use datetime(..., tzinfo=ZoneInfo('America/New_York')) or UTC."
        )


def now_et() -> datetime:
    """Wall clock right now, expressed in America/New_York."""
    return datetime.now(tz=ET)


def to_utc(ts: datetime) -> datetime:
    """Convert an aware datetime to UTC. DST-safe via zoneinfo."""
    _require_aware(ts)
    return ts.astimezone(timezone.utc)


def is_regular_session(ts: datetime) -> bool:
    """True iff ``ts`` (in ET) is inside the regular cash session.

    The open boundary is inclusive, close is exclusive, and exchange holidays
    plus early closes come from the XNYS calendar.
    """
    _require_aware(ts)
    return is_open_at("XNYS", ts)


def session_date_for(ts: datetime) -> str:
    """Return the ET wall-clock date as ``YYYY-MM-DD``.

    Anchored to ET, NOT UTC, so a Tuesday-evening UTC timestamp that
    falls before midnight ET on the same Tuesday returns the Tuesday.
    """
    _require_aware(ts)
    return ts.astimezone(ET).date().isoformat()


def minutes_until_close(ts: datetime) -> int | None:
    """Whole minutes until the actual XNYS close, or ``None`` when closed."""
    if not is_regular_session(ts):
        return None
    et = ts.astimezone(ET)
    session = session_for_date("XNYS", et.date())
    if session is None:  # Defensive: is_regular_session already proved a session exists.
        return None
    delta = session.market_close - et
    # Round down — a partially elapsed minute counts as "still in" that minute.
    return int(delta.total_seconds() // 60)
