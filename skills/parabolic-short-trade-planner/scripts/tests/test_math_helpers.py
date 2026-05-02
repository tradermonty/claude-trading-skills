"""Tests for math_helpers.py — pure Python sma/ema/rolling_mean/log10_scale."""

import pytest
from math_helpers import ema, log10_scale, rolling_mean, sma


class TestSMA:
    def test_period_equals_length_returns_arithmetic_mean(self):
        assert sma([1, 2, 3, 4, 5], period=5) == pytest.approx(3.0)

    def test_period_smaller_uses_last_n(self):
        # Latest 3 of [1, 2, 3, 4, 5] = [3, 4, 5], mean = 4
        assert sma([1, 2, 3, 4, 5], period=3) == pytest.approx(4.0)

    def test_insufficient_data_returns_none(self):
        assert sma([1, 2, 3], period=5) is None


class TestEMA:
    def test_constant_series_returns_constant(self):
        result = ema([10.0] * 20, period=10)
        assert result == pytest.approx(10.0)

    def test_increasing_series_lags_below_latest(self):
        result = ema(list(range(1, 21)), period=10)
        # EMA of 1..20 with period 10 should be > seed mean but < latest
        assert result < 20
        assert result > 5


class TestRollingMean:
    def test_returns_list_of_means(self):
        out = rolling_mean([1, 2, 3, 4, 5], period=2)
        # window means: (1+2)/2, (2+3)/2, (3+4)/2, (4+5)/2 → [1.5, 2.5, 3.5, 4.5]
        assert out == pytest.approx([1.5, 2.5, 3.5, 4.5])

    def test_period_equals_length_single_value(self):
        out = rolling_mean([2, 4, 6, 8], period=4)
        assert out == pytest.approx([5.0])


class TestLog10Scale:
    def test_at_lo_returns_zero(self):
        assert log10_scale(10**7, lo=7.0, hi=8.5, max_score=10.0) == pytest.approx(0.0)

    def test_at_hi_returns_max_score(self):
        assert log10_scale(10**8.5, lo=7.0, hi=8.5, max_score=10.0) == pytest.approx(10.0)

    def test_clamps_below_lo(self):
        assert log10_scale(10**5, lo=7.0, hi=8.5, max_score=10.0) == 0.0

    def test_clamps_above_hi(self):
        assert log10_scale(10**10, lo=7.0, hi=8.5, max_score=10.0) == 10.0

    def test_zero_value_clamps_to_zero(self):
        assert log10_scale(0, lo=7.0, hi=8.5, max_score=10.0) == 0.0

    def test_negative_value_clamps_to_zero(self):
        assert log10_scale(-100, lo=7.0, hi=8.5, max_score=10.0) == 0.0
