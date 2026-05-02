"""Tests for calculators.range_expansion_calculator."""

from range_expansion_calculator import calculate_range_expansion


class TestRangeExpansion:
    def test_parabolic_series_shows_expansion(self, parabolic_bars_chrono):
        highs = [b["high"] for b in parabolic_bars_chrono]
        lows = [b["low"] for b in parabolic_bars_chrono]
        closes = [b["close"] for b in parabolic_bars_chrono]
        out = calculate_range_expansion(highs, lows, closes)
        assert out["expansion_ratio"] is not None
        # Last 5 days have much wider TR than the prior 20
        assert out["expansion_ratio"] > 2.0

    def test_normal_series_close_to_one(self, normal_bars_chrono):
        highs = [b["high"] for b in normal_bars_chrono]
        lows = [b["low"] for b in normal_bars_chrono]
        closes = [b["close"] for b in normal_bars_chrono]
        out = calculate_range_expansion(highs, lows, closes)
        assert out["expansion_ratio"] is not None
        assert 0.5 <= out["expansion_ratio"] <= 2.0

    def test_short_history_returns_none(self, short_bars_chrono):
        highs = [b["high"] for b in short_bars_chrono]
        lows = [b["low"] for b in short_bars_chrono]
        closes = [b["close"] for b in short_bars_chrono]
        out = calculate_range_expansion(highs, lows, closes)
        assert out["expansion_ratio"] is None
