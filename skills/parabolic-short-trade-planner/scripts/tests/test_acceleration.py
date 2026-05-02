"""Tests for calculators.acceleration_calculator."""

import pytest
from acceleration_calculator import (
    acceleration_ratio,
    calculate_acceleration,
    consecutive_green_days,
    return_pct,
)


class TestReturnPct:
    def test_basic_5d_return(self):
        closes = [100, 101, 102, 103, 104, 105]
        # base = closes[-6] = 100, latest = 105 → 5%
        assert return_pct(closes, 5) == pytest.approx(5.0)

    def test_insufficient_history_returns_none(self):
        assert return_pct([100, 101], days=5) is None

    def test_negative_base_returns_none(self):
        assert return_pct([-1.0, 1.0, 2.0], days=2) is None


class TestConsecutiveGreen:
    def test_counts_recent_streak(self):
        opens = [10, 11, 12, 13, 14]
        closes = [11, 12, 13, 14, 15]  # all green
        assert consecutive_green_days(opens, closes) == 5

    def test_stops_at_red_bar(self):
        opens = [10, 11, 12, 13, 14]
        closes = [11, 10, 13, 14, 15]  # day 2 was red
        assert consecutive_green_days(opens, closes) == 3


class TestAccelerationRatio:
    def test_accelerating_move_returns_above_one(self, parabolic_bars_chrono):
        closes = [b["close"] for b in parabolic_bars_chrono]
        ratio = acceleration_ratio(closes, short_window=3, long_window=10)
        assert ratio is not None
        # Recent 3-day returns must outpace the 10-day average.
        # The fixture's late bars compound at ~12-13%/day vs. ~10-11%
        # over the full 10-day window — the ratio is comfortably > 1.
        assert ratio > 1.05

    def test_flat_returns_none_or_low(self):
        closes = [50.0] * 20
        ratio = acceleration_ratio(closes)
        # Flat → long_avg = 0 → None
        assert ratio is None


class TestAggregated:
    def test_all_keys_present(self, parabolic_bars_chrono):
        opens = [b["open"] for b in parabolic_bars_chrono]
        closes = [b["close"] for b in parabolic_bars_chrono]
        out = calculate_acceleration(opens, closes)
        assert set(out.keys()) >= {
            "return_3d_pct",
            "return_5d_pct",
            "return_10d_pct",
            "return_15d_pct",
            "consecutive_green_days",
            "acceleration_ratio_3_over_10",
        }
        assert out["return_5d_pct"] is not None
        assert out["return_5d_pct"] > 30  # parabolic fixture's 5-day move
