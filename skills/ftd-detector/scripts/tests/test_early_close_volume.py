"""Regression tests for the early-close volume reference (issue #892)."""

from datetime import date

import pytest
from _market_calendar import is_early_close, previous_full_session_index
from post_ftd_monitor import count_post_ftd_distribution
from rally_tracker import analyze_single_index

VOL = 1_000_000
FULL_WEDNESDAY = "2026-11-25"
EARLY_FRIDAY = "2026-11-27"
NEXT_MONDAY = "2026-11-30"

# Sessions ending with a half day and the session after it. The replay reads the
# dates the bars carry, so the list only has to be chronological and gap-free.
SESSIONS = [
    "2026-10-29",
    "2026-10-30",
    "2026-11-02",
    "2026-11-03",
    "2026-11-04",
    "2026-11-05",
    "2026-11-06",
    "2026-11-09",
    "2026-11-10",
    "2026-11-11",
    "2026-11-12",
    "2026-11-13",
    "2026-11-16",
    "2026-11-17",
    "2026-11-18",
    "2026-11-23",
    "2026-11-24",
    FULL_WEDNESDAY,
    EARLY_FRIDAY,
    NEXT_MONDAY,
]


def B(close, low=None, high=None, vol=VOL):
    """A valid candle whose close sits in the lower half of its range."""
    bar = {
        "open": close,
        "high": close * 1.006 if high is None else high,
        "low": close * 0.995 if low is None else low,
        "close": close,
        "volume": vol,
    }
    assert bar["low"] <= min(bar["open"], bar["close"]), bar
    assert max(bar["open"], bar["close"]) <= bar["high"], bar
    return bar


def rally_setup(ftd_date, ftd_volume=1_500_000, early_close_volume=500_000, normal=False):
    """A correction, Day 1-3, then an FTD on ``ftd_date`` (Day 4).

    The full session before the half day carries 1.2M volume and the half day
    ``early_close_volume``, so the two references disagree for the next session.
    ``normal`` builds the same shape one session earlier, ending on a regular
    Wednesday, so the previous-session reference applies.
    """
    bars = [B(105.0) for _ in range(8)] + [B(106.0)]
    bars += [B(104.0), B(102.5), B(101.0), B(99.5)]
    bars.append(B(98.9, low=98.0, high=100.0))  # closing low, no upper-half close
    bars += [B(100.5), B(100.7), B(100.9)]  # Day 1-3, gains below 1.25%
    bars.append(B(bars[-1]["close"] * 1.015, vol=ftd_volume))
    assert len(bars) <= len(SESSIONS)
    dates = SESSIONS[:-2] if normal else SESSIONS[-len(bars) :]
    for bar, session_date in zip(bars, dates):
        bar["date"] = session_date
    if normal:
        # The session before the FTD carries 1.2M; the FTD is a regular session.
        bars[-2]["volume"] = 1_200_000
    else:
        # Reference volumes: the last full session and the half day.
        next(bar for bar in bars if bar["date"] == FULL_WEDNESDAY)["volume"] = 1_200_000
        next(bar for bar in bars if bar["date"] == EARLY_FRIDAY)["volume"] = early_close_volume
    assert bars[-1]["date"] == ftd_date
    return bars


def ftd_of(history):
    return analyze_single_index(history, "Synthetic")["ftd"]


class TestCalendarContract:
    def test_half_day_is_classified_early_and_regular_days_are_not(self):
        assert is_early_close("XNYS", date(2026, 11, 27)) is True
        assert is_early_close("XNYS", date(2026, 11, 25)) is False
        assert is_early_close("XNYS", date(2026, 11, 30)) is False

    def test_unparseable_bar_dates_keep_the_previous_session_reference(self):
        assert previous_full_session_index(
            "XNYS", ["day-001", "day-002"], 1, order="chronological"
        ) == (
            0,
            "previous_session",
        )
        assert previous_full_session_index("XNYS", ["day-001", "day-002"], 0) == (
            1,
            "previous_session",
        )


class TestFollowThroughDay:
    def test_session_after_an_early_close_must_beat_the_last_full_session(self):
        history = rally_setup(NEXT_MONDAY, ftd_volume=1_000_000)
        # 1.0M beats the 500k half day but not the 1.2M last full session.
        assert ftd_of(history)["ftd_detected"] is False

    def test_session_after_an_early_close_beats_the_last_full_session(self):
        result = ftd_of(rally_setup(NEXT_MONDAY))
        assert result["ftd_detected"] is True
        assert result["prev_day_volume"] == 1_200_000
        assert result["volume_reference"] == {
            "basis": "previous_full_session",
            "date": FULL_WEDNESDAY,
        }

    def test_normal_sessions_still_compare_with_the_previous_session(self):
        result = ftd_of(rally_setup(FULL_WEDNESDAY, ftd_volume=1_300_000, normal=True))
        assert result["ftd_detected"] is True
        assert result["prev_day_volume"] == 1_200_000
        assert result["volume_reference"] is None


class TestPostFtdDistribution:
    def ftd_history(self, after_early_volume, early_close_volume=500_000):
        return [
            {"date": "2026-11-20", "close": 100.0, "volume": 1_000_000, "high": 100.4, "low": 98.8},
            {"date": "2026-11-23", "close": 99.5, "volume": 600_000, "high": 100.0, "low": 98.5},
            {"date": "2026-11-24", "close": 99.0, "volume": 600_000, "high": 99.5, "low": 98.0},
            {
                "date": FULL_WEDNESDAY,
                "close": 100.0,
                "volume": 1_200_000,
                "high": 100.6,
                "low": 99.0,
            },
            {
                "date": EARLY_FRIDAY,
                "close": 99.4,
                "volume": early_close_volume,
                "high": 99.9,
                "low": 98.9,
            },
            {
                "date": NEXT_MONDAY,
                "close": 98.9,
                "volume": after_early_volume,
                "high": 99.0,
                "low": 98.0,
            },
        ]

    def test_session_after_an_early_close_does_not_inherit_a_distribution_day(self):
        result = count_post_ftd_distribution(self.ftd_history(after_early_volume=900_000), 0)
        assert result["distribution_count"] == 0

    def test_session_after_an_early_close_records_the_full_session_reference(self):
        result = count_post_ftd_distribution(self.ftd_history(after_early_volume=1_400_000), 0)
        assert result["distribution_count"] == 1
        assert result["details"][0]["volume_reference"] == {
            "basis": "previous_full_session",
            "date": FULL_WEDNESDAY,
        }
        assert result["details"][0]["volume_change_pct"] == pytest.approx(16.7, abs=0.1)

    def test_early_close_session_is_compared_with_the_previous_full_session(self):
        result = count_post_ftd_distribution(
            self.ftd_history(after_early_volume=900_000, early_close_volume=800_000), 0
        )
        assert result["distribution_count"] == 0

    def test_unavailable_reference_is_a_data_gap_not_a_clean_day(self):
        truncated = [
            {
                "date": EARLY_FRIDAY,
                "close": 99.4,
                "volume": 500_000,
                "high": 99.9,
                "low": 98.9,
            },
            {
                "date": NEXT_MONDAY,
                "close": 98.9,
                "volume": 900_000,
                "high": 99.0,
                "low": 98.0,
            },
        ]
        result = count_post_ftd_distribution(truncated, 0)
        assert result["data_gap"] is True
        assert result["distribution_count"] == 0
        assert "no full session reference" in result["reason"]


def test_cycle_projection_keeps_the_volume_reference():
    from rally_tracker import _Replay

    history = [B(100.0)]
    history[0]["date"] = NEXT_MONDAY
    replay = _Replay(history, 0)
    replay.phase = "confirmed"
    replay.dds = [
        {
            "date": NEXT_MONDAY,
            "close": 98.9,
            "change_pct": -1.2,
            "active": True,
            "volume_reference": {
                "basis": "previous_full_session",
                "date": FULL_WEDNESDAY,
            },
        }
    ]
    cycle = replay.cycle(history, False)
    assert cycle["active_distribution_days"] == [
        {
            "date": NEXT_MONDAY,
            "close": 98.9,
            "change_pct": -1.2,
            "volume_reference": {
                "basis": "previous_full_session",
                "date": FULL_WEDNESDAY,
            },
        }
    ]
