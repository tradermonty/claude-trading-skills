"""Tests for Defensive Rotation Calculator"""

from calculators.defensive_rotation_calculator import (
    _score_rotation,
    calculate_defensive_rotation,
)


class TestScoreRotation:
    """Boundary tests for rotation scoring."""

    def test_growth_leading(self):
        """Negative relative = growth leading = healthy."""
        assert _score_rotation(-3.0) == 0
        assert _score_rotation(-1.0) <= 15

    def test_slight_defensive_tilt(self):
        assert 20 <= _score_rotation(0.3) <= 40

    def test_strong_defensive_rotation(self):
        assert _score_rotation(5.0) == 100

    def test_moderate_rotation(self):
        assert 60 <= _score_rotation(2.0) <= 80


class TestCalculateDefensiveRotation:
    """Integration tests."""

    def test_missing_data_returns_50(self):
        """No ETF data → score 50 (neutral), data_available=False."""
        result = calculate_defensive_rotation({})
        assert result["score"] == 50
        assert result["data_available"] is False

    def test_partial_data_still_computes(self):
        """At least 1 defensive + 1 offensive ETF should compute."""
        historical = {
            "XLU": [{"close": 70 + i * 0.1, "volume": 500000} for i in range(25)],
            "XLK": [{"close": 200 - i * 0.5, "volume": 2000000} for i in range(25)],
        }
        result = calculate_defensive_rotation(historical)
        assert result["data_available"] is True
        assert "score" in result

    def test_growth_leading_scenario(self):
        """Offensive outperforming defensive → low score."""
        historical = {}
        for sym in ["XLU", "XLP", "XLV", "VNQ"]:
            # Defensive: flat
            historical[sym] = [{"close": 50, "volume": 500000} for _ in range(25)]
        for sym in ["XLK", "XLC", "XLY", "QQQ"]:
            # Offensive: +5% over 20 days
            historical[sym] = [{"close": 105 - i * 0.25, "volume": 2000000} for i in range(25)]
        result = calculate_defensive_rotation(historical)
        assert result["score"] <= 20
