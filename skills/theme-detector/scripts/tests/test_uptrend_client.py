"""Tests for uptrend_client.is_data_stale (business day logic)."""

from datetime import date
from unittest.mock import MagicMock

import uptrend_client
from uptrend_client import fetch_sector_uptrend_data, is_data_stale


class TestIsDataStale:
    """is_data_stale should count business days, not calendar days."""

    def test_friday_to_sunday_not_stale(self):
        """Friday data checked on Sunday: 0 business days -> not stale."""
        assert is_data_stale("2026-02-13", as_of_date=date(2026, 2, 15)) is False

    def test_friday_to_monday_not_stale(self):
        """Friday data checked on Monday: 1 business day -> not stale (threshold=2)."""
        assert is_data_stale("2026-02-13", as_of_date=date(2026, 2, 16)) is False

    def test_friday_to_tuesday_not_stale(self):
        """Friday data checked on Tuesday: 2 business days -> not stale (threshold=2)."""
        assert is_data_stale("2026-02-13", as_of_date=date(2026, 2, 17)) is False

    def test_friday_to_wednesday_stale(self):
        """Friday data checked on Wednesday: 3 business days -> stale (threshold=2)."""
        assert is_data_stale("2026-02-20", as_of_date=date(2026, 2, 25)) is True

    def test_monday_to_wednesday_not_stale(self):
        """Monday data checked on Wednesday: 2 business days -> not stale."""
        assert is_data_stale("2026-02-16", as_of_date=date(2026, 2, 18)) is False

    def test_monday_to_thursday_stale(self):
        """Monday data checked on Thursday: 3 business days -> stale."""
        assert is_data_stale("2026-02-16", as_of_date=date(2026, 2, 19)) is True

    def test_same_day_not_stale(self):
        """Same day data -> 0 business days -> not stale."""
        assert is_data_stale("2026-02-16", as_of_date=date(2026, 2, 16)) is False

    def test_invalid_date_returns_true(self):
        """Invalid date string -> stale (safe default)."""
        assert is_data_stale("not-a-date") is True

    def test_custom_threshold(self):
        """Custom threshold_bdays works correctly."""
        # Friday to Tuesday = 2 sessions, threshold=1 -> stale.
        assert (
            is_data_stale(
                "2026-02-20",
                threshold_bdays=1,
                as_of_date=date(2026, 2, 24),
            )
            is True
        )

    def test_exchange_holiday_is_excluded(self):
        assert is_data_stale("2026-04-02", threshold_bdays=1, as_of_date=date(2026, 4, 6)) is False

    def test_future_source_date_is_stale(self):
        assert is_data_stale("2026-04-07", as_of_date=date(2026, 4, 6)) is True


def test_fetch_uses_latest_row_on_or_before_as_of(monkeypatch):
    response = MagicMock()
    response.text = (
        "date,worksheet,ratio,ma_10,slope,trend\n"
        "2026-04-02,sec_technology,0.20,0.18,0.01,up\n"
        "2026-04-07,sec_technology,0.99,0.90,0.50,up\n"
    )
    response.raise_for_status.return_value = None
    monkeypatch.setattr(uptrend_client.requests, "get", lambda *_args, **_kwargs: response)

    result = fetch_sector_uptrend_data(as_of_date=date(2026, 4, 6))

    assert result["Technology"]["latest_date"] == "2026-04-02"
    assert result["Technology"]["ratio"] == 0.20
