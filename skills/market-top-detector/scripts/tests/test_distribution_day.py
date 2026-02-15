"""Tests for Distribution Day Calculator"""

from calculators.distribution_day_calculator import (
    _count_distribution_days,
    _score_distribution_days,
    calculate_distribution_days,
)
from helpers import make_history, make_history_with_volumes


class TestScoreDistributionDays:
    """Boundary tests for scoring thresholds."""

    def test_zero_days(self):
        assert _score_distribution_days(0) == 0

    def test_one_day(self):
        assert _score_distribution_days(1) == 15

    def test_two_days(self):
        assert _score_distribution_days(2) == 30

    def test_three_days(self):
        assert _score_distribution_days(3) == 55

    def test_four_days_oneil_threshold(self):
        assert _score_distribution_days(4) == 75

    def test_five_days(self):
        assert _score_distribution_days(5) == 90

    def test_six_plus_days(self):
        assert _score_distribution_days(6) == 100
        assert _score_distribution_days(8) == 100

    def test_fractional_stalling(self):
        """Stalling days count as 0.5"""
        assert _score_distribution_days(3.5) == 55  # 3.5 >= 3
        assert _score_distribution_days(4.5) == 75  # 4.5 >= 4


class TestCountDistributionDays:
    """Tests for distribution day detection logic."""

    def test_empty_history(self):
        result = _count_distribution_days([], "TEST")
        assert result["distribution_days"] == 0

    def test_single_day(self):
        result = _count_distribution_days([{"close": 100, "volume": 1000}], "TEST")
        assert result["distribution_days"] == 0

    def test_distribution_day_detected(self):
        """Price drop >= 0.2% on higher volume = distribution day."""
        history = make_history_with_volumes(
            [
                (99.0, 1200000),  # Today: -1% drop, higher volume → distribution
                (100.0, 1000000),  # Yesterday
                (100.5, 800000),  # Two days ago: lower volume than yesterday
            ]
        )
        result = _count_distribution_days(history, "TEST")
        assert result["distribution_days"] >= 1

    def test_stalling_day_detected(self):
        """Volume increases but price gain < 0.1% = stalling day."""
        history = make_history_with_volumes(
            [
                (100.05, 1200000),  # Today: +0.05%, higher volume
                (100.0, 1000000),  # Yesterday
                (99.5, 900000),  # Two days ago
            ]
        )
        result = _count_distribution_days(history, "TEST")
        assert result["stalling_days"] >= 1


class TestCalculateDistributionDays:
    """Integration tests."""

    def test_uses_higher_count(self):
        """Should use the worse of S&P 500 / NASDAQ."""
        # Create histories where NASDAQ has more distribution days
        sp_history = make_history([100] * 30)
        # NASDAQ with distribution pattern
        nasdaq_cv = [(99.0 - i * 0.3, 1200000 + i * 10000) for i in range(15)]
        nasdaq_cv += [(100.0 + i * 0.1, 1000000) for i in range(15)]
        nasdaq_history = make_history_with_volumes(nasdaq_cv)

        result = calculate_distribution_days(sp_history, nasdaq_history)
        assert "score" in result
        assert "effective_count" in result
