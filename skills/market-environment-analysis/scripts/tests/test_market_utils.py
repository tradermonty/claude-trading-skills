#!/usr/bin/env python3
"""Tests for market_utils.py"""

import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from market_utils import (
    calculate_trading_days_to_event,
    categorize_volatility,
    format_market_report_header,
    format_percentage_change,
    generate_checklist,
    get_market_session_times,
    get_market_status,
    main,
)

UTC = ZoneInfo("UTC")


class TestGetMarketSessionTimes:
    def test_returns_dict_with_major_markets(self):
        result = get_market_session_times()
        assert isinstance(result, dict)
        expected_markets = ["Tokyo", "Shanghai", "Hong Kong", "Singapore", "London", "New York"]
        for market in expected_markets:
            assert market in result

    def test_each_market_has_open_and_close(self):
        result = get_market_session_times()
        for market, times in result.items():
            assert "open" in times, f"{market} missing 'open'"
            assert "close" in times, f"{market} missing 'close'"

    def test_asian_markets_have_lunch_break(self):
        result = get_market_session_times()
        asian_markets = ["Tokyo", "Shanghai", "Hong Kong", "Singapore"]
        for market in asian_markets:
            assert result[market].get("lunch") is not None, f"{market} should have lunch break"

    def test_tokyo_close_reflects_2024_jpx_cutover(self):
        before = get_market_session_times(datetime(2024, 11, 1, 0, tzinfo=UTC))
        after = get_market_session_times(datetime(2024, 11, 5, 0, tzinfo=UTC))
        assert before["Tokyo"]["close"] == "15:00 JST"
        assert after["Tokyo"]["close"] == "15:30 JST"

    def test_london_and_new_york_labels_follow_dst(self):
        summer = get_market_session_times(datetime(2026, 7, 6, 12, tzinfo=UTC))
        winter = get_market_session_times(datetime(2026, 1, 5, 12, tzinfo=UTC))
        assert summer["London"]["open"].endswith("BST")
        assert winter["London"]["open"].endswith("GMT")
        assert summer["New York"]["open"].endswith("EDT")
        assert winter["New York"]["open"].endswith("EST")

    def test_western_markets_no_lunch_break(self):
        result = get_market_session_times()
        western_markets = ["London", "New York"]
        for market in western_markets:
            assert result[market].get("lunch") is None, f"{market} should not have lunch break"


class TestFormatMarketReportHeader:
    def test_returns_string(self):
        result = format_market_report_header()
        assert isinstance(result, str)

    def test_contains_title(self):
        result = format_market_report_header()
        assert "Market Environment Report" in result

    def test_contains_formatted_date(self):
        result = format_market_report_header(datetime(2025, 3, 15, 14, 30, tzinfo=UTC))
        assert "2025-03-15" in result
        assert "Saturday" in result
        assert "14:30 UTC" in result


class TestCalculateTradingDaysToEvent:
    def test_same_day_returns_zero(self):
        result = calculate_trading_days_to_event(
            "2025-03-10", datetime(2025, 3, 10, 12, tzinfo=UTC)
        )
        assert result == 0

    def test_weekend_excluded(self):
        # Monday Mar 10 to Monday Mar 17 = 5 trading days
        result = calculate_trading_days_to_event(
            "2025-03-17", datetime(2025, 3, 10, 12, tzinfo=UTC)
        )
        assert result == 5

    def test_within_week(self):
        # Monday Mar 10 to Friday Mar 14 = 4 trading days
        result = calculate_trading_days_to_event(
            "2025-03-14", datetime(2025, 3, 10, 12, tzinfo=UTC)
        )
        assert result == 4

    def test_holiday_is_excluded(self):
        # Mon Jun 29 through Mon Jul 6 excludes Fri Jul 3 exchange holiday.
        result = calculate_trading_days_to_event(
            "2026-07-06", datetime(2026, 6, 29, 12, tzinfo=UTC)
        )
        assert result == 4


class TestFormatPercentageChange:
    def test_positive_value(self):
        result = format_percentage_change(1.5)
        assert "+1.50%" in result
        assert "📈" in result

    def test_negative_value(self):
        result = format_percentage_change(-2.3)
        assert "-2.30%" in result
        assert "📉" in result

    def test_zero_value(self):
        result = format_percentage_change(0)
        assert "+0.00%" in result
        assert "📈" in result


class TestCategorizeVolatility:
    def test_low_volatility(self):
        result = categorize_volatility(10)
        assert "Low" in result

    def test_normal_range(self):
        result = categorize_volatility(15)
        assert "Normal" in result

    def test_elevated(self):
        result = categorize_volatility(25)
        assert "Elevated" in result

    def test_high_volatility(self):
        result = categorize_volatility(35)
        assert "High" in result

    def test_extreme_volatility(self):
        result = categorize_volatility(45)
        assert "Extreme" in result

    def test_boundary_values(self):
        assert "Low" in categorize_volatility(11.99)
        assert "Normal" in categorize_volatility(12)
        assert "Normal" in categorize_volatility(19.99)
        assert "Elevated" in categorize_volatility(20)
        assert "Elevated" in categorize_volatility(29.99)
        assert "High" in categorize_volatility(30)
        assert "High" in categorize_volatility(39.99)
        assert "Extreme" in categorize_volatility(40)


class TestGetMarketStatus:
    def test_returns_string(self):
        result = get_market_status()
        assert isinstance(result, str)

    def test_contains_market_names(self):
        result = get_market_status()
        assert "Tokyo" in result
        assert "US" in result

    def test_tokyo_lunch_and_us_early_close(self):
        tokyo_lunch = datetime(2024, 11, 5, 3, 0, tzinfo=UTC)
        assert "Tokyo Market: Lunch break" in get_market_status(tokyo_lunch)

        us_early_close = datetime(2026, 11, 27, 18, 0, tzinfo=UTC)
        assert "US Market: Closed" in get_market_status(us_early_close)

    def test_holiday_is_not_treated_as_open(self):
        good_friday = datetime(2026, 4, 3, 15, 0, tzinfo=UTC)
        assert "US Market: Closed (non-session)" in get_market_status(good_friday)


class TestCli:
    def test_offset_as_of_is_accepted(self, capsys):
        assert main(["--as-of", "2026-07-06T14:00:00Z"]) == 0
        assert "US Market: Trading" in capsys.readouterr().out

    @pytest.mark.parametrize("value", ["2026-07-06", "not-a-date", "2026-07-06T10:00:00"])
    def test_date_only_naive_and_invalid_as_of_are_rejected(self, value, capsys):
        with pytest.raises(SystemExit) as exc:
            main(["--as-of", value])
        assert exc.value.code == 2
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "as-of" in captured.err


class TestGenerateChecklist:
    def test_returns_string(self):
        result = generate_checklist()
        assert isinstance(result, str)

    def test_contains_checklist_items(self):
        result = generate_checklist()
        assert "US market" in result
        assert "Asian market" in result
        assert "European market" in result
        assert "VIX" in result
        assert "Oil" in result
        assert "Gold" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
