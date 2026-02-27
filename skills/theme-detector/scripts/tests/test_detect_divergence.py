"""Tests for detect_divergence function."""

from theme_detector import detect_divergence


class TestDetectDivergence:
    """Unit tests for ETF price vs breadth divergence detection."""

    def test_no_divergence_small_gap(self):
        """Gap < 25 returns None (no divergence detected)."""
        heat_breakdown = {"momentum_strength": 60, "uptrend_signal": 50}
        result = detect_divergence(heat_breakdown, "bullish")
        assert result is None

    def test_no_divergence_exact_threshold(self):
        """Gap == 24.9 (just under 25) returns None."""
        heat_breakdown = {"momentum_strength": 74.9, "uptrend_signal": 50}
        result = detect_divergence(heat_breakdown, "bullish")
        assert result is None

    def test_no_divergence_zero_gap(self):
        """Identical momentum and uptrend returns None."""
        heat_breakdown = {"momentum_strength": 50, "uptrend_signal": 50}
        result = detect_divergence(heat_breakdown, "bullish")
        assert result is None

    def test_narrow_rally_momentum_exceeds_uptrend(self):
        """Momentum >> uptrend returns narrow_rally type."""
        heat_breakdown = {"momentum_strength": 85, "uptrend_signal": 40}
        result = detect_divergence(heat_breakdown, "bullish")
        assert result is not None
        assert result["type"] == "narrow_rally"
        assert result["gap"] == 45.0
        assert "concentrated" in result["description"]
        assert "fragile" in result["description"]

    def test_narrow_rally_exact_threshold(self):
        """Gap == 25 returns narrow_rally (threshold is inclusive for abs >= 25)."""
        heat_breakdown = {"momentum_strength": 75, "uptrend_signal": 50}
        result = detect_divergence(heat_breakdown, "bullish")
        assert result is not None
        assert result["type"] == "narrow_rally"
        assert result["gap"] == 25.0

    def test_internal_recovery_bearish_direction(self):
        """Uptrend >> momentum with bearish direction returns reversal candidate."""
        heat_breakdown = {"momentum_strength": 30, "uptrend_signal": 70}
        result = detect_divergence(heat_breakdown, "bearish")
        assert result is not None
        assert result["type"] == "internal_recovery"
        assert result["gap"] == 40.0
        assert "reversal candidate" in result["description"]

    def test_internal_recovery_bullish_direction(self):
        """Uptrend >> momentum with bullish direction returns acceleration candidate."""
        heat_breakdown = {"momentum_strength": 30, "uptrend_signal": 70}
        result = detect_divergence(heat_breakdown, "bullish")
        assert result is not None
        assert result["type"] == "internal_recovery"
        assert result["gap"] == 40.0
        assert "acceleration candidate" in result["description"]

    def test_defaults_to_50_when_keys_missing(self):
        """Missing keys default to 50, so gap is 0 and returns None."""
        result = detect_divergence({}, "bullish")
        assert result is None

    def test_gap_rounding(self):
        """Gap values are rounded to 1 decimal place."""
        heat_breakdown = {"momentum_strength": 80.333, "uptrend_signal": 45.777}
        result = detect_divergence(heat_breakdown, "bullish")
        assert result is not None
        assert result["gap"] == 34.6  # 80.333 - 45.777 = 34.556 -> 34.6

    def test_narrow_rally_bearish_direction(self):
        """Narrow rally detection works for bearish themes too."""
        heat_breakdown = {"momentum_strength": 90, "uptrend_signal": 30}
        result = detect_divergence(heat_breakdown, "bearish")
        assert result is not None
        assert result["type"] == "narrow_rally"
        assert result["gap"] == 60.0
