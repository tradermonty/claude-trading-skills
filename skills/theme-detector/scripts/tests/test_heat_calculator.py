"""Tests for heat_calculator.py - Theme Heat Score (0-100)"""

import pytest
from calculators.heat_calculator import (
    momentum_strength_score,
    volume_intensity_score,
    uptrend_signal_score,
    breadth_signal_score,
    calculate_theme_heat,
)


# ── momentum_strength_score ──────────────────────────────────────────

class TestMomentumStrengthScore:
    """sigmoid: 100 / (1 + exp(-0.15 * (abs(wr%) - 5.0)))"""

    def test_zero_return(self):
        # abs(0) - 5 = -5 => sigmoid(0.75) ≈ 32
        score = momentum_strength_score(0.0)
        assert 30 <= score <= 35

    def test_five_percent(self):
        # abs(5) - 5 = 0 => sigmoid(0) = 50
        score = momentum_strength_score(5.0)
        assert score == pytest.approx(50.0, abs=0.1)

    def test_negative_five_percent(self):
        # abs(-5) - 5 = 0 => 50
        score = momentum_strength_score(-5.0)
        assert score == pytest.approx(50.0, abs=0.1)

    def test_fifteen_percent(self):
        # abs(15) - 5 = 10 => sigmoid(-1.5) ≈ 82
        score = momentum_strength_score(15.0)
        assert 80 <= score <= 85

    def test_twenty_percent(self):
        # abs(20) - 5 = 15 => sigmoid(-2.25) ≈ 90
        score = momentum_strength_score(20.0)
        assert 88 <= score <= 92

    def test_negative_twenty_percent(self):
        score = momentum_strength_score(-20.0)
        assert 88 <= score <= 92

    def test_returns_float(self):
        assert isinstance(momentum_strength_score(3.0), float)


# ── volume_intensity_score ───────────────────────────────────────────

class TestVolumeIntensityScore:
    """min(100, max(0, (vol_20d/vol_60d - 0.8) * 250))"""

    def test_ratio_0_8_returns_zero(self):
        # (0.8 - 0.8) * 250 = 0
        assert volume_intensity_score(80.0, 100.0) == pytest.approx(0.0)

    def test_ratio_1_0_returns_50(self):
        # (1.0 - 0.8) * 250 = 50
        assert volume_intensity_score(100.0, 100.0) == pytest.approx(50.0)

    def test_ratio_1_2_returns_100(self):
        # (1.2 - 0.8) * 250 = 100
        assert volume_intensity_score(120.0, 100.0) == pytest.approx(100.0)

    def test_ratio_above_cap_clamped_to_100(self):
        # (2.0 - 0.8) * 250 = 300 => clamped 100
        assert volume_intensity_score(200.0, 100.0) == pytest.approx(100.0)

    def test_ratio_below_floor_clamped_to_0(self):
        # (0.5 - 0.8) * 250 = -75 => clamped 0
        assert volume_intensity_score(50.0, 100.0) == pytest.approx(0.0)

    def test_none_vol_20d(self):
        assert volume_intensity_score(None, 100.0) == pytest.approx(50.0)

    def test_none_vol_60d(self):
        assert volume_intensity_score(100.0, None) == pytest.approx(50.0)

    def test_zero_vol_60d(self):
        assert volume_intensity_score(100.0, 0.0) == pytest.approx(50.0)


# ── uptrend_signal_score ─────────────────────────────────────────────

class TestUptrendSignalScore:

    def _make_sector(self, ratio, ma_10, slope, weight=1.0):
        return {
            "sector": "test",
            "ratio": ratio,
            "ma_10": ma_10,
            "slope": slope,
            "weight": weight,
        }

    def test_both_positive_gives_80(self):
        # ratio>ma_10 AND slope>0 => 80
        data = [self._make_sector(ratio=50, ma_10=40, slope=0.5)]
        score = uptrend_signal_score(data, is_bearish=False)
        assert score == pytest.approx(80.0)

    def test_ratio_only_gives_60(self):
        # ratio>ma_10 but slope<=0 => 60
        data = [self._make_sector(ratio=50, ma_10=40, slope=-0.1)]
        score = uptrend_signal_score(data, is_bearish=False)
        assert score == pytest.approx(60.0)

    def test_slope_only_gives_60(self):
        # ratio<=ma_10 but slope>0 => 60
        data = [self._make_sector(ratio=30, ma_10=40, slope=0.5)]
        score = uptrend_signal_score(data, is_bearish=False)
        assert score == pytest.approx(60.0)

    def test_neither_gives_20(self):
        # ratio<=ma_10 AND slope<=0 => 20
        data = [self._make_sector(ratio=30, ma_10=40, slope=-0.1)]
        score = uptrend_signal_score(data, is_bearish=False)
        assert score == pytest.approx(20.0)

    def test_weighted_average(self):
        # sector A: both positive => 80, weight 2
        # sector B: neither => 20, weight 1
        # weighted = (80*2 + 20*1) / 3 = 60
        data = [
            self._make_sector(ratio=50, ma_10=40, slope=0.5, weight=2.0),
            self._make_sector(ratio=30, ma_10=40, slope=-0.1, weight=1.0),
        ]
        score = uptrend_signal_score(data, is_bearish=False)
        assert score == pytest.approx(60.0)

    def test_bearish_inversion(self):
        # both positive => 80, bearish => 100-80 = 20
        data = [self._make_sector(ratio=50, ma_10=40, slope=0.5)]
        score = uptrend_signal_score(data, is_bearish=True)
        assert score == pytest.approx(20.0)

    def test_empty_list(self):
        assert uptrend_signal_score([], is_bearish=False) == pytest.approx(50.0)

    def test_equal_ratio_and_ma10(self):
        # ratio == ma_10 => not > => slope<=0 => 20
        data = [self._make_sector(ratio=40, ma_10=40, slope=0)]
        score = uptrend_signal_score(data, is_bearish=False)
        assert score == pytest.approx(20.0)


# ── breadth_signal_score ─────────────────────────────────────────────

class TestBreadthSignalScore:

    def test_zero(self):
        assert breadth_signal_score(0.0) == pytest.approx(0.0)

    def test_half(self):
        assert breadth_signal_score(0.5) == pytest.approx(50.0)

    def test_full(self):
        assert breadth_signal_score(1.0) == pytest.approx(100.0)

    def test_above_one_clamped(self):
        assert breadth_signal_score(1.5) == pytest.approx(100.0)

    def test_negative_clamped(self):
        assert breadth_signal_score(-0.3) == pytest.approx(0.0)

    def test_none(self):
        assert breadth_signal_score(None) == pytest.approx(50.0)


# ── calculate_theme_heat ─────────────────────────────────────────────

class TestCalculateThemeHeat:

    def test_weighted_sum(self):
        # 80*0.40 + 60*0.25 + 70*0.20 + 50*0.15
        # = 32 + 15 + 14 + 7.5 = 68.5
        result = calculate_theme_heat(80.0, 60.0, 70.0, 50.0)
        assert result == pytest.approx(68.5)

    def test_all_100(self):
        result = calculate_theme_heat(100.0, 100.0, 100.0, 100.0)
        assert result == pytest.approx(100.0)

    def test_all_zero(self):
        result = calculate_theme_heat(0.0, 0.0, 0.0, 0.0)
        assert result == pytest.approx(0.0)

    def test_none_defaults_to_50(self):
        # All None => 50*0.40 + 50*0.25 + 50*0.20 + 50*0.15 = 50
        result = calculate_theme_heat(None, None, None, None)
        assert result == pytest.approx(50.0)

    def test_partial_none(self):
        # 80*0.40 + 50*0.25 + 50*0.20 + 50*0.15
        # = 32 + 12.5 + 10 + 7.5 = 62.0
        result = calculate_theme_heat(80.0, None, None, None)
        assert result == pytest.approx(62.0)

    def test_clamped_above_100(self):
        result = calculate_theme_heat(200.0, 200.0, 200.0, 200.0)
        assert result == 100.0

    def test_clamped_below_0(self):
        result = calculate_theme_heat(-50.0, -50.0, -50.0, -50.0)
        assert result == 0.0

    def test_returns_float(self):
        assert isinstance(calculate_theme_heat(50, 50, 50, 50), float)
