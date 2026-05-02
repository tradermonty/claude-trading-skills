"""Tests for market_clock — ET timezone helpers.

Coverage focus:
- DST boundaries (EST/EDT switch in March + November). The ET offset
  shifts from -05:00 to -04:00 mid-March and back in early November;
  any naive offset arithmetic would silently break here.
- Regular-session window (09:30 ≤ ts < 16:00 ET on weekdays only).
- session_date_for is anchored to ET wall-clock date, NOT UTC date,
  so a 21:00 UTC timestamp on a Tuesday must map to the same Tuesday.
- minutes_until_close returns None outside the session and a positive
  int inside it.
- to_utc round-trip preserves the underlying instant across DST.
"""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import market_clock as mc

ET = ZoneInfo("America/New_York")


class TestRegularSession:
    def test_open_at_9_30_et_weekday(self):
        ts = datetime(2026, 5, 5, 9, 30, tzinfo=ET)  # Tuesday
        assert mc.is_regular_session(ts) is True

    def test_just_before_open_excluded(self):
        ts = datetime(2026, 5, 5, 9, 29, 59, tzinfo=ET)
        assert mc.is_regular_session(ts) is False

    def test_close_at_16_00_excluded(self):
        # 16:00 ET is the close itself; the 15:55 bar is the last bar.
        ts = datetime(2026, 5, 5, 16, 0, tzinfo=ET)
        assert mc.is_regular_session(ts) is False

    def test_just_before_close_included(self):
        ts = datetime(2026, 5, 5, 15, 59, 59, tzinfo=ET)
        assert mc.is_regular_session(ts) is True

    def test_saturday_excluded(self):
        ts = datetime(2026, 5, 9, 12, 0, tzinfo=ET)  # Saturday
        assert mc.is_regular_session(ts) is False

    def test_sunday_excluded(self):
        ts = datetime(2026, 5, 10, 12, 0, tzinfo=ET)  # Sunday
        assert mc.is_regular_session(ts) is False


class TestSessionDateFor:
    def test_morning_et_weekday(self):
        ts = datetime(2026, 5, 5, 10, 0, tzinfo=ET)
        assert mc.session_date_for(ts) == "2026-05-05"

    def test_utc_input_converted_to_et_date(self):
        # 2026-05-06 02:00 UTC = 2026-05-05 22:00 ET (still the 5th).
        ts = datetime(2026, 5, 6, 2, 0, tzinfo=timezone.utc)
        assert mc.session_date_for(ts) == "2026-05-05"

    def test_naive_input_raises(self):
        # We require timezone-aware inputs to avoid silent local-time
        # interpretation on contributors' machines.
        import pytest

        with pytest.raises(ValueError):
            mc.session_date_for(datetime(2026, 5, 5, 10, 0))


class TestDSTBoundaries:
    """DST transitions: EST (UTC-5) ↔ EDT (UTC-4).

    2026 transitions:
      - Spring forward: 2026-03-08 02:00 → 03:00 (EST → EDT).
      - Fall back:      2026-11-01 02:00 → 01:00 (EDT → EST).
    """

    def test_pre_dst_offset_is_minus_5(self):
        ts = datetime(2026, 3, 1, 12, 0, tzinfo=ET)  # well before spring forward
        # Compare via UTC to bypass tz-name fragility on CI
        assert ts.utcoffset().total_seconds() / 3600 == -5

    def test_post_dst_offset_is_minus_4(self):
        ts = datetime(2026, 4, 1, 12, 0, tzinfo=ET)  # after spring forward
        assert ts.utcoffset().total_seconds() / 3600 == -4

    def test_to_utc_roundtrip_across_dst(self):
        # Same instant either side of spring-forward should round-trip.
        for et_ts in [
            datetime(2026, 3, 1, 14, 30, tzinfo=ET),  # EST
            datetime(2026, 4, 1, 14, 30, tzinfo=ET),  # EDT
        ]:
            utc = mc.to_utc(et_ts)
            assert utc.tzinfo == timezone.utc
            assert utc == et_ts.astimezone(timezone.utc)


class TestMinutesUntilClose:
    def test_inside_session_returns_positive(self):
        ts = datetime(2026, 5, 5, 9, 30, tzinfo=ET)
        # 09:30 → 16:00 = 6h30m = 390 min
        assert mc.minutes_until_close(ts) == 390

    def test_just_before_close(self):
        ts = datetime(2026, 5, 5, 15, 59, tzinfo=ET)
        assert mc.minutes_until_close(ts) == 1

    def test_outside_session_returns_none(self):
        before = datetime(2026, 5, 5, 9, 0, tzinfo=ET)
        after = datetime(2026, 5, 5, 16, 1, tzinfo=ET)
        weekend = datetime(2026, 5, 9, 12, 0, tzinfo=ET)
        assert mc.minutes_until_close(before) is None
        assert mc.minutes_until_close(after) is None
        assert mc.minutes_until_close(weekend) is None


class TestToUtc:
    def test_aware_et_to_utc(self):
        ts = datetime(2026, 5, 5, 9, 30, tzinfo=ET)  # EDT, -04:00
        utc = mc.to_utc(ts)
        assert utc.tzinfo == timezone.utc
        assert utc.hour == 13 and utc.minute == 30

    def test_already_utc_passthrough(self):
        ts = datetime(2026, 5, 5, 13, 30, tzinfo=timezone.utc)
        utc = mc.to_utc(ts)
        assert utc == ts

    def test_naive_input_raises(self):
        import pytest

        with pytest.raises(ValueError):
            mc.to_utc(datetime(2026, 5, 5, 9, 30))


class TestNowEt:
    def test_returns_aware_et_datetime(self):
        ts = mc.now_et()
        assert ts.tzinfo is not None
        # Confirm it's the ET zone (offset is either -4 or -5 depending on
        # current DST status; both are acceptable).
        offset_hours = ts.utcoffset().total_seconds() / 3600
        assert offset_hours in (-4, -5)
