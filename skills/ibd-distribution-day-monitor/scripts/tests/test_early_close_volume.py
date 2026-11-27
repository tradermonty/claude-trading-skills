"""Regression tests for the early-close volume reference (issue #892)."""

from distribution_day_tracker import detect_distribution_days
from models import DistributionDayRule

FULL_WEDNESDAY = "2026-11-25"
EARLY_FRIDAY = "2026-11-27"


def make_bar(session_date, close, volume):
    return {
        "date": session_date,
        "close": close,
        "volume": volume,
        "high": close * 1.004,
        "low": close * 0.996,
    }


def history_most_recent_first(after_early_volume, early_close_volume=500_000):
    return [
        make_bar("2026-11-30", 98.9, after_early_volume),
        make_bar(EARLY_FRIDAY, 99.4, early_close_volume),
        make_bar(FULL_WEDNESDAY, 100.6, 1_200_000),
        make_bar("2026-11-24", 100.5, 1_000_000),
    ]


class TestEarlyCloseVolumeReference:
    def test_session_after_an_early_close_must_beat_the_last_full_session(self):
        history = history_most_recent_first(after_early_volume=900_000)
        records, skipped = detect_distribution_days(history, DistributionDayRule())
        assert records == []
        assert skipped == []

    def test_session_after_an_early_close_records_the_full_session_reference(self):
        history = history_most_recent_first(after_early_volume=1_400_000)
        records, _ = detect_distribution_days(history, DistributionDayRule())
        assert len(records) == 1
        record = records[0]
        assert record.date == "2026-11-30"
        assert record.prev_volume == 1_200_000
        assert record.volume_reference == "previous_full_session"
        assert record.volume_reference_date == FULL_WEDNESDAY
        assert record.volume_change_pct == 1_400_000 / 1_200_000 - 1

    def test_early_close_session_records_the_full_session_reference(self):
        history = history_most_recent_first(
            after_early_volume=900_000, early_close_volume=1_300_000
        )
        records, _ = detect_distribution_days(history, DistributionDayRule())
        assert len(records) == 1
        record = records[0]
        assert record.date == EARLY_FRIDAY
        assert record.volume_reference == "previous_full_session"
        assert record.volume_reference_date == FULL_WEDNESDAY

    def test_normal_sessions_keep_the_previous_session_reference(self):
        history = [
            make_bar("2026-11-30", 99.0, 1_100_000),
            make_bar("2026-11-24", 100.0, 1_000_000),
            make_bar("2026-11-23", 100.5, 1_000_000),
        ]
        records, _ = detect_distribution_days(history, DistributionDayRule())
        assert len(records) == 1
        assert records[0].prev_volume == 1_000_000
        assert records[0].volume_reference is None
        assert records[0].volume_reference_date is None

    def test_unparseable_dates_keep_the_previous_session_reference(self):
        history = [
            {"date": "day-001", "close": 99.0, "volume": 1_100_000},
            {"date": "day-000", "close": 100.0, "volume": 1_000_000},
        ]
        records, _ = detect_distribution_days(history, DistributionDayRule())
        assert len(records) == 1
        assert records[0].volume_reference is None
