"""Tests for heat_calculator module."""

import math
from calculators.heat_calculator import (
    momentum_strength_score,
    volume_intensity_score,
    uptrend_signal_score,
    breadth_signal_score,
    calculate_theme_heat,
    HEAT_WEIGHTS,
)


class TestMomentumStrengthScore:
    """Log-sigmoid formula: 100 / (1 + exp(-2.0 * (ln(1+|wr|) - ln(16))))"""

    def test_zero_return(self):
        score = momentum_strength_score(0.0)
        assert 0 <= score <= 15, f"Zero return should be very low: {score}"

    def test_low_return_5pct(self):
        score = momentum_strength_score(5.0)
        assert 8 <= score <= 20, f"|5%| should be low: {score}"

    def test_midpoint_15pct(self):
        score = momentum_strength_score(15.0)
        assert 45 <= score <= 55, f"|15%| should be near 50: {score}"

    def test_high_return_30pct(self):
        score = momentum_strength_score(30.0)
        assert 65 <= score <= 80, f"|30%| should be high: {score}"

    def test_very_high_return_50pct(self):
        score = momentum_strength_score(50.0)
        assert 80 <= score <= 92, f"|50%| should be very high: {score}"

    def test_direction_neutral(self):
        """Positive and negative returns should give same score."""
        assert momentum_strength_score(10.0) == momentum_strength_score(-10.0)

    def test_spread_across_range(self):
        """Scores should spread across a wide range, not cluster at top."""
        scores = [momentum_strength_score(r) for r in [5, 10, 15, 20, 30, 50]]
        spread = max(scores) - min(scores)
        assert spread >= 50, f"Score spread should be >= 50, got {spread}"


class TestVolumeIntensityScore:
    """Sqrt scaling: min(100, sqrt(max(0, ratio-0.8)) / sqrt(1.2) * 100)"""

    def test_none_inputs(self):
        assert volume_intensity_score(None, None) == 50.0

    def test_zero_denominator(self):
        assert volume_intensity_score(100.0, 0) == 50.0

    def test_ratio_1_0(self):
        """ratio=1.0 should be moderate, not near 100."""
        score = volume_intensity_score(100.0, 100.0)
        assert 30 <= score <= 45, f"ratio=1.0 should be moderate: {score}"

    def test_ratio_1_2(self):
        score = volume_intensity_score(120.0, 100.0)
        assert 50 <= score <= 65, f"ratio=1.2 should be mid-high: {score}"

    def test_ratio_1_5(self):
        score = volume_intensity_score(150.0, 100.0)
        assert 70 <= score <= 85, f"ratio=1.5 should be high: {score}"

    def test_ratio_2_0(self):
        score = volume_intensity_score(200.0, 100.0)
        assert score >= 95, f"ratio=2.0 should be near 100: {score}"

    def test_below_0_8(self):
        score = volume_intensity_score(70.0, 100.0)
        assert score == 0.0, f"ratio < 0.8 should be 0: {score}"

    def test_spread(self):
        """Scores should spread across range for ratios 0.8-2.0."""
        scores = [volume_intensity_score(r, 100.0) for r in [80, 100, 120, 150, 200]]
        spread = max(scores) - min(scores)
        assert spread >= 60, f"Volume score spread should be >= 60, got {spread}"


class TestBreadthSignalScore:
    """Power curve: min(100, ratio^2.5 * 80 + count_bonus)"""

    def test_none(self):
        assert breadth_signal_score(None) == 50.0

    def test_ratio_0_5(self):
        score = breadth_signal_score(0.5)
        assert 10 <= score <= 25, f"ratio=0.5 should be low: {score}"

    def test_ratio_0_7(self):
        score = breadth_signal_score(0.7)
        assert 25 <= score <= 45, f"ratio=0.7 should be mid-low: {score}"

    def test_ratio_0_9(self):
        score = breadth_signal_score(0.9)
        assert 55 <= score <= 75, f"ratio=0.9 should be mid-high: {score}"

    def test_ratio_1_0(self):
        score = breadth_signal_score(1.0)
        assert 75 <= score <= 100, f"ratio=1.0 should be high: {score}"

    def test_industry_count_bonus(self):
        """More industries should give higher score."""
        score_few = breadth_signal_score(0.8, industry_count=2)
        score_many = breadth_signal_score(0.8, industry_count=7)
        assert score_many > score_few, "More industries should score higher"

    def test_spread(self):
        scores = [breadth_signal_score(r) for r in [0.3, 0.5, 0.7, 0.9, 1.0]]
        spread = max(scores) - min(scores)
        assert spread >= 50, f"Breadth score spread should be >= 50, got {spread}"


class TestUptrendSignalScore:
    """Continuous scoring: base = min(80, ratio*100) + MA bonus + slope bonus."""

    def test_empty(self):
        assert uptrend_signal_score([], False) == 50.0

    def test_strong_uptrend(self):
        """High ratio, above MA, positive slope should score high."""
        data = [{"ratio": 0.6, "ma_10": 0.5, "slope": 0.01, "weight": 1.0}]
        score = uptrend_signal_score(data, is_bearish=False)
        assert score >= 70, f"Strong uptrend should be high: {score}"

    def test_weak_conditions(self):
        """Low ratio, below MA, negative slope should score low."""
        data = [{"ratio": 0.15, "ma_10": 0.3, "slope": -0.01, "weight": 1.0}]
        score = uptrend_signal_score(data, is_bearish=False)
        assert score <= 25, f"Weak conditions should be low: {score}"

    def test_bearish_inverts(self):
        """Bearish themes should invert the score."""
        data = [{"ratio": 0.6, "ma_10": 0.5, "slope": 0.01, "weight": 1.0}]
        bull_score = uptrend_signal_score(data, is_bearish=False)
        bear_score = uptrend_signal_score(data, is_bearish=True)
        assert abs(bull_score + bear_score - 100.0) < 1.0

    def test_continuous_not_discrete(self):
        """Scores should vary continuously, not cluster at 20/60/80."""
        scores = set()
        for ratio in [0.1, 0.2, 0.3, 0.4, 0.5, 0.6]:
            data = [{"ratio": ratio, "ma_10": 0.3, "slope": 0.005, "weight": 1.0}]
            score = uptrend_signal_score(data, is_bearish=False)
            scores.add(round(score, 1))
        assert len(scores) >= 4, f"Should produce more than 3 discrete values: {scores}"


class TestCalculateThemeHeat:
    def test_all_none_defaults(self):
        heat = calculate_theme_heat(None, None, None, None)
        assert heat == 50.0

    def test_weighted_sum(self):
        heat = calculate_theme_heat(100, 100, 100, 100)
        assert heat == 100.0

    def test_clamped_0_to_100(self):
        heat = calculate_theme_heat(0, 0, 0, 0)
        assert heat == 0.0


class TestHeatWeights:
    def test_weights_sum_to_1(self):
        total = sum(HEAT_WEIGHTS.values())
        assert abs(total - 1.0) < 0.001

    def test_expected_weights(self):
        assert HEAT_WEIGHTS["momentum"] == 0.35
        assert HEAT_WEIGHTS["volume"] == 0.20
        assert HEAT_WEIGHTS["uptrend"] == 0.25
        assert HEAT_WEIGHTS["breadth"] == 0.20
