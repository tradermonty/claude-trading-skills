"""Tests for scorer.py - Theme Detector scoring and labeling"""

import pytest
from scorer import (
    HEAT_LABELS,
    get_heat_label,
    calculate_confidence,
    determine_data_mode,
    score_theme,
)


# ── get_heat_label ───────────────────────────────────────────────────

class TestGetHeatLabel:

    def test_hot(self):
        assert get_heat_label(80) == "Hot"
        assert get_heat_label(90) == "Hot"
        assert get_heat_label(100) == "Hot"

    def test_warm(self):
        assert get_heat_label(60) == "Warm"
        assert get_heat_label(70) == "Warm"
        assert get_heat_label(79.9) == "Warm"

    def test_neutral(self):
        assert get_heat_label(40) == "Neutral"
        assert get_heat_label(50) == "Neutral"
        assert get_heat_label(59.9) == "Neutral"

    def test_cool(self):
        assert get_heat_label(20) == "Cool"
        assert get_heat_label(30) == "Cool"
        assert get_heat_label(39.9) == "Cool"

    def test_cold(self):
        assert get_heat_label(0) == "Cold"
        assert get_heat_label(10) == "Cold"
        assert get_heat_label(19.9) == "Cold"


# ── calculate_confidence ─────────────────────────────────────────────

class TestCalculateConfidence:

    def test_three_layers_high(self):
        assert calculate_confidence(
            quant_confirmed=True, breadth_confirmed=True,
            narrative_confirmed=True, stale_data_penalty=False
        ) == "High"

    def test_two_layers_medium(self):
        assert calculate_confidence(
            quant_confirmed=True, breadth_confirmed=True,
            narrative_confirmed=False, stale_data_penalty=False
        ) == "Medium"

    def test_one_layer_low(self):
        assert calculate_confidence(
            quant_confirmed=True, breadth_confirmed=False,
            narrative_confirmed=False, stale_data_penalty=False
        ) == "Low"

    def test_zero_layers_low(self):
        assert calculate_confidence(
            quant_confirmed=False, breadth_confirmed=False,
            narrative_confirmed=False, stale_data_penalty=False
        ) == "Low"

    def test_stale_penalty_downgrades_high_to_medium(self):
        assert calculate_confidence(
            quant_confirmed=True, breadth_confirmed=True,
            narrative_confirmed=True, stale_data_penalty=True
        ) == "Medium"

    def test_stale_penalty_downgrades_medium_to_low(self):
        assert calculate_confidence(
            quant_confirmed=True, breadth_confirmed=True,
            narrative_confirmed=False, stale_data_penalty=True
        ) == "Low"

    def test_stale_penalty_low_stays_low(self):
        assert calculate_confidence(
            quant_confirmed=True, breadth_confirmed=False,
            narrative_confirmed=False, stale_data_penalty=True
        ) == "Low"

    def test_all_combinations_without_penalty(self):
        # 3 confirmed => High
        assert calculate_confidence(True, True, True, False) == "High"
        # 2 confirmed => Medium (multiple combos)
        assert calculate_confidence(True, True, False, False) == "Medium"
        assert calculate_confidence(True, False, True, False) == "Medium"
        assert calculate_confidence(False, True, True, False) == "Medium"
        # 1 confirmed => Low
        assert calculate_confidence(True, False, False, False) == "Low"
        assert calculate_confidence(False, True, False, False) == "Low"
        assert calculate_confidence(False, False, True, False) == "Low"


# ── determine_data_mode ──────────────────────────────────────────────

class TestDetermineDataMode:

    def test_both_available(self):
        result = determine_data_mode(fmp_available=True, finviz_elite=True)
        assert "FINVIZ" in result and "FMP" in result

    def test_fmp_only(self):
        result = determine_data_mode(fmp_available=True, finviz_elite=False)
        assert "FMP" in result

    def test_finviz_public_only(self):
        result = determine_data_mode(fmp_available=False, finviz_elite=False)
        assert "Public" in result or "public" in result.lower()

    def test_finviz_elite_no_fmp(self):
        result = determine_data_mode(fmp_available=False, finviz_elite=True)
        assert "FINVIZ" in result

    def test_returns_string(self):
        assert isinstance(determine_data_mode(True, True), str)


# ── score_theme ──────────────────────────────────────────────────────

class TestScoreTheme:

    def test_returns_complete_dict(self):
        result = score_theme(
            theme_heat=75.0,
            lifecycle_maturity=45.0,
            lifecycle_stage="Trending",
            direction="bullish",
            confidence="High",
            data_mode="FINVIZ-Elite+FMP",
        )
        assert "theme_heat" in result
        assert "heat_label" in result
        assert "lifecycle_maturity" in result
        assert "lifecycle_stage" in result
        assert "direction" in result
        assert "confidence" in result
        assert "data_mode" in result

    def test_heat_label_populated(self):
        result = score_theme(
            theme_heat=85.0,
            lifecycle_maturity=50.0,
            lifecycle_stage="Trending",
            direction="bullish",
            confidence="Medium",
            data_mode="FMP-only",
        )
        assert result["heat_label"] == "Hot"

    def test_all_fields_passed_through(self):
        result = score_theme(
            theme_heat=30.0,
            lifecycle_maturity=15.0,
            lifecycle_stage="Emerging",
            direction="bearish",
            confidence="Low",
            data_mode="FINVIZ-Public",
        )
        assert result["theme_heat"] == 30.0
        assert result["lifecycle_maturity"] == 15.0
        assert result["lifecycle_stage"] == "Emerging"
        assert result["direction"] == "bearish"
        assert result["confidence"] == "Low"
        assert result["data_mode"] == "FINVIZ-Public"

    def test_heat_label_matches_score(self):
        for heat, expected_label in [(5, "Cold"), (25, "Cool"), (45, "Neutral"),
                                      (65, "Warm"), (85, "Hot")]:
            result = score_theme(
                theme_heat=heat,
                lifecycle_maturity=50.0,
                lifecycle_stage="Trending",
                direction="bullish",
                confidence="Medium",
                data_mode="FMP-only",
            )
            assert result["heat_label"] == expected_label
