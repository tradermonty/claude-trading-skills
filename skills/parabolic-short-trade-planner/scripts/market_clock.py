"""ET timezone helpers for Phase 3 (intraday trigger monitor).

Why this exists separately from the rest of the skill: Phase 1 + 2
work in calendar-day granularity (`as_of=YYYY-MM-DD`) where wall-time
doesn't matter. Phase 3 evaluates 5-min bars during a US regular
session, so it must reason about ET wall-clock time AND DST
transitions correctly. ``zoneinfo`` (stdlib in 3.9+) handles DST
automatically; we never do raw offset arithmetic.

Holidays are deliberately out of scope for v0.5. On a market holiday
the Alpaca bars endpoint simply returns ``[]``; the monitor surfaces
that as ``evaluation_status=no_bars`` per plan, not a code crash.
"""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

REGULAR_OPEN_HOUR = 9
REGULAR_OPEN_MINUTE = 30
REGULAR_CLOSE_HOUR = 16
REGULAR_CLOSE_MINUTE = 0


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

    Window: 09:30 ≤ wall-time < 16:00 on Mon–Fri. Holidays are NOT
    excluded by this check (out of scope for v0.5).
    """
    _require_aware(ts)
    et = ts.astimezone(ET)
    if et.weekday() >= 5:  # Saturday=5, Sunday=6
        return False
    open_minutes = REGULAR_OPEN_HOUR * 60 + REGULAR_OPEN_MINUTE
    close_minutes = REGULAR_CLOSE_HOUR * 60 + REGULAR_CLOSE_MINUTE
    minutes_of_day = et.hour * 60 + et.minute + et.second / 60
    return open_minutes <= minutes_of_day < close_minutes


def session_date_for(ts: datetime) -> str:
    """Return the ET wall-clock date as ``YYYY-MM-DD``.

    Anchored to ET, NOT UTC, so a Tuesday-evening UTC timestamp that
    falls before midnight ET on the same Tuesday returns the Tuesday.
    """
    _require_aware(ts)
    return ts.astimezone(ET).date().isoformat()


def minutes_until_close(ts: datetime) -> int | None:
    """Whole minutes until 16:00 ET, or ``None`` when outside session."""
    if not is_regular_session(ts):
        return None
    et = ts.astimezone(ET)
    close = et.replace(
        hour=REGULAR_CLOSE_HOUR,
        minute=REGULAR_CLOSE_MINUTE,
        second=0,
        microsecond=0,
    )
    delta = close - et
    # Round down — a partially elapsed minute counts as "still in" that minute.
    return int(delta.total_seconds() // 60)
