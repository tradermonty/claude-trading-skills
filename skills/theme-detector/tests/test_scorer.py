"""Tests for scorer module."""

from scorer import calculate_confidence, get_heat_label, score_theme


class TestCalculateConfidence:
    def test_all_confirmed_is_high(self):
        assert calculate_confidence(True, True, True, False) == "High"

    def test_narrative_false_caps_at_medium(self):
        """Without narrative confirmation, max confidence is Medium."""
        conf = calculate_confidence(True, True, False, False)
        assert conf == "Medium"

    def test_one_confirmed_is_low(self):
        assert calculate_confidence(True, False, False, False) == "Low"

    def test_none_confirmed_is_low(self):
        assert calculate_confidence(False, False, False, False) == "Low"

    def test_stale_data_downgrades(self):
        # High -> Medium
        assert calculate_confidence(True, True, True, True) == "Medium"
        # Medium -> Low
        assert calculate_confidence(True, True, False, True) == "Low"

    def test_stale_data_no_effect_on_low(self):
        assert calculate_confidence(False, False, False, True) == "Low"


class TestGetHeatLabel:
    def test_hot(self):
        assert get_heat_label(85.0) == "Hot"

    def test_warm(self):
        assert get_heat_label(65.0) == "Warm"

    def test_neutral(self):
        assert get_heat_label(45.0) == "Neutral"

    def test_cool(self):
        assert get_heat_label(25.0) == "Cool"

    def test_cold(self):
        assert get_heat_label(10.0) == "Cold"


class TestScoreTheme:
    def test_returns_all_keys(self):
        result = score_theme(75.0, 50.0, "growth", "bullish", "Medium", "FMP-only")
        assert "theme_heat" in result
        assert "heat_label" in result
        assert "lifecycle_maturity" in result
        assert "lifecycle_stage" in result
        assert "direction" in result
        assert "confidence" in result
        assert "data_mode" in result
