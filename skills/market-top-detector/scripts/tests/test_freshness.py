"""Tests for Data Freshness Management"""

from datetime import date, timedelta

import pytest
from utils import count_business_days


def _expected_factor(biz_days: int) -> float:
    """Map business days to expected freshness factor."""
    if biz_days <= 1:
        return 1.0
    elif biz_days <= 3:
        return 0.95
    elif biz_days <= 7:
        return 0.85
    else:
        return 0.70


class TestDataFreshness:
    """Test data freshness computation."""

    def test_today_returns_1(self):
        """Data from today -> freshness factor 1.0."""
        from market_top_detector import compute_data_freshness

        today = date.today().isoformat()
        result = compute_data_freshness({"breadth_200dma_date": today})
        assert result["breadth_200dma"]["factor"] == 1.0

    def test_recent_data_factor(self):
        """Data from a few calendar days ago uses business day counting."""
        from market_top_detector import compute_data_freshness

        d = date.today() - timedelta(days=2)
        result = compute_data_freshness({"breadth_200dma_date": d.isoformat()})
        biz = count_business_days(d, date.today())
        assert result["breadth_200dma"]["factor"] == _expected_factor(biz)

    def test_week_old_data_factor(self):
        """Data from ~1 week ago uses business day counting."""
        from market_top_detector import compute_data_freshness

        d = date.today() - timedelta(days=5)
        result = compute_data_freshness({"breadth_200dma_date": d.isoformat()})
        biz = count_business_days(d, date.today())
        assert result["breadth_200dma"]["factor"] == _expected_factor(biz)

    def test_old_data_returns_070(self):
        """Data from many calendar days ago -> 0.70 (business days > 7)."""
        from market_top_detector import compute_data_freshness

        # 20 calendar days guarantees 14+ business days -> factor 0.70
        d = (date.today() - timedelta(days=20)).isoformat()
        result = compute_data_freshness({"breadth_200dma_date": d})
        assert result["breadth_200dma"]["factor"] == 0.70

    def test_no_date_returns_1(self):
        """No date provided -> assume fresh (1.0)."""
        from market_top_detector import compute_data_freshness

        result = compute_data_freshness({})
        assert result["overall_confidence"] == 1.0

    def test_no_value_returns_none(self):
        """Date given but no value -> entry should still compute."""
        from market_top_detector import compute_data_freshness

        d = date.today().isoformat()
        result = compute_data_freshness({"put_call_date": d})
        assert result["put_call"]["factor"] == 1.0

    def test_overall_confidence_is_min(self):
        """Overall confidence = min of all provided factors."""
        from market_top_detector import compute_data_freshness

        today = date.today().isoformat()
        # 20 calendar days -> 14+ business days -> factor 0.70
        old = (date.today() - timedelta(days=20)).isoformat()
        result = compute_data_freshness(
            {
                "breadth_200dma_date": today,
                "put_call_date": old,
            }
        )
        assert result["overall_confidence"] == 0.70

    def test_future_date_returns_070(self):
        """Future date should be treated as anomaly with factor 0.70."""
        from market_top_detector import compute_data_freshness

        future = (date.today() + timedelta(days=5)).isoformat()
        result = compute_data_freshness({"breadth_200dma_date": future})
        assert result["breadth_200dma"]["factor"] == 0.70
        assert result["breadth_200dma"]["age_days"] is None

    def test_weekend_tolerance(self):
        """Friday data should still be fresh on Monday (1 business day).

        Instead of mocking date, we test the underlying count_business_days
        that compute_data_freshness now uses.
        """
        from utils import count_business_days

        friday = date(2026, 3, 13)  # Friday
        monday = date(2026, 3, 16)  # Monday
        biz_days = count_business_days(friday, monday)
        # 1 business day -> factor would be 1.0 (<=1 threshold)
        assert biz_days == 1

    def test_exchange_holiday_is_not_counted(self):
        """Good Friday is not an XNYS freshness day."""
        from market_top_detector import compute_data_freshness

        result = compute_data_freshness(
            {"breadth_200dma_date": "2026-04-02"},
            as_of_date=date(2026, 4, 6),
        )
        assert result["breadth_200dma"]["age_days"] == 1
        assert result["breadth_200dma"]["factor"] == 1.0

    def test_explicit_as_of_rejects_future_source_date(self):
        from market_top_detector import compute_data_freshness

        result = compute_data_freshness(
            {"put_call_date": "2026-04-07"},
            as_of_date=date(2026, 4, 6),
        )
        assert result["put_call"] == {
            "date": "2026-04-07",
            "age_days": None,
            "factor": 0.70,
        }


def test_history_filter_removes_future_and_invalid_rows():
    from market_top_detector import _history_on_or_before

    rows = [
        {"date": "2026-07-07", "close": 3},
        {"date": "bad", "close": 2},
        {"date": "2026-07-06", "close": 1},
    ]
    assert _history_on_or_before(rows, date(2026, 7, 6)) == [rows[2]]


def test_batch_history_filter_protects_leading_and_sector_calculators():
    from market_top_detector import _batch_histories_on_or_before

    valid = {"date": "2026-04-06", "close": 100}
    raw = {
        "LEADER": [
            {"date": "2026-04-07", "close": 999},
            {"date": "invalid", "close": 888},
            valid,
        ],
        "DEFENSIVE": [{"date": "2026-04-08", "close": 777}],
    }

    filtered = _batch_histories_on_or_before(raw, date(2026, 4, 6))

    assert filtered == {"LEADER": [valid]}


def test_future_dated_scored_cli_input_fails_before_live_fetch(capsys):
    from market_top_detector import main

    rc = main(
        [
            "--breadth-200dma",
            "80",
            "--breadth-200dma-date",
            "2099-01-04",
        ]
    )

    captured = capsys.readouterr()
    assert rc == 2
    assert "future-dated scored input" in captured.err
    assert captured.out == ""


@pytest.mark.parametrize("value", ["2026-7-6", "not-a-date"])
def test_as_of_parser_requires_strict_iso_date(value):
    from market_top_detector import parse_arguments

    with pytest.raises(SystemExit) as exc:
        parse_arguments(["--as-of", value])
    assert exc.value.code == 2
