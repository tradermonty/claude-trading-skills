"""Tests for heat_calculator.py - Theme Heat Score (0-100)

Tests are calibrated against the CURRENT formulas documented in
theme_detection_methodology.md:

  momentum: 100 / (1 + exp(-2.0 * (ln(1+|wr%|) - ln(16))))  midpoint at 15%
  volume:   min(100, sqrt(max(0, ratio-0.8)) / sqrt(1.2) * 100)
  uptrend:  continuous base = min(80, ratio*100) + 10*(ratio>ma_10) + 10*(slope>0)
  breadth:  min(100, ratio^2.5 * 80 + count_bonus)
  heat:     momentum*0.35 + volume*0.20 + uptrend*0.25 + breadth*0.20
"""

import math

import pytest
from calculators.heat_calculator import (
    breadth_signal_score,
    calculate_theme_heat,
    momentum_strength_score,
    uptrend_signal_score,
    volume_intensity_score,
)

# ── momentum_strength_score ──────────────────────────────────────────


class TestMomentumStrengthScore:
    """Log-sigmoid: 100 / (1 + exp(-2.0 * (ln(1+|wr%|) - ln(16))))

    Midpoint at |15%| weighted return.
    Examples: |0%|->~0.4, |5%|->~12.3, |15%|->50, |20%|->~63.3, |30%|->~73
    """

    def test_zero_return(self):
        # ln(1+0)=0, far below midpoint ln(16)≈2.77 → near-zero score
        score = momentum_strength_score(0.0)
        assert 0.0 <= score < 1.0

    def test_five_percent(self):
        # ln(6)≈1.79 < ln(16) → well below midpoint → ~12.3
        score = momentum_strength_score(5.0)
        assert score == pytest.approx(12.33, abs=0.1)

    def test_negative_five_percent(self):
        # Symmetric: abs(-5) == abs(5)
        score = momentum_strength_score(-5.0)
        assert score == pytest.approx(12.33, abs=0.1)

    def test_fifteen_percent_is_midpoint(self):
        # ln(16) - ln(16) = 0 → sigmoid(0) = 50.0 exactly
        score = momentum_strength_score(15.0)
        assert score == pytest.approx(50.0, abs=0.01)

    def test_twenty_percent(self):
        # ln(21)≈3.04 > ln(16)≈2.77 → above midpoint → ~63.3
        score = momentum_strength_score(20.0)
        assert score == pytest.approx(63.27, abs=0.1)

    def test_negative_twenty_percent(self):
        score = momentum_strength_score(-20.0)
        assert score == pytest.approx(63.27, abs=0.1)

    def test_returns_float(self):
        assert isinstance(momentum_strength_score(3.0), float)

    def test_monotonically_increasing_with_abs_return(self):
        # Larger absolute return → higher score
        scores = [momentum_strength_score(x) for x in [0, 5, 10, 15, 20, 30, 50]]
        assert scores == sorted(scores)

    def test_bounded_0_to_100(self):
        for x in [-100, -50, 0, 50, 100]:
            s = momentum_strength_score(x)
            assert 0.0 <= s <= 100.0


# ── volume_intensity_score ───────────────────────────────────────────


class TestVolumeIntensityScore:
    """sqrt scaling: min(100, sqrt(max(0, ratio-0.8)) / sqrt(1.2) * 100)

    Ceiling at ratio=2.0. Floor at ratio<=0.8 → 0.
    Examples: ratio=0.8->0, ratio=1.0->~40.8, ratio=1.2->~57.7, ratio=2.0->100
    """

    def test_ratio_0_8_returns_zero(self):
        # sqrt(0.8-0.8) = 0
        assert volume_intensity_score(80.0, 100.0) == pytest.approx(0.0)

    def test_ratio_1_0(self):
        # sqrt(0.2) / sqrt(1.2) * 100 ≈ 40.8
        assert volume_intensity_score(100.0, 100.0) == pytest.approx(40.82, abs=0.1)

    def test_ratio_1_2(self):
        # sqrt(0.4) / sqrt(1.2) * 100 ≈ 57.7
        assert volume_intensity_score(120.0, 100.0) == pytest.approx(57.74, abs=0.1)

    def test_ratio_2_0_hits_ceiling(self):
        # sqrt(1.2) / sqrt(1.2) * 100 = 100.0 exactly
        assert volume_intensity_score(200.0, 100.0) == pytest.approx(100.0)

    def test_ratio_above_2_clamped_to_100(self):
        assert volume_intensity_score(500.0, 100.0) == pytest.approx(100.0)

    def test_ratio_below_floor_clamped_to_0(self):
        # max(0, 0.5-0.8) = 0 → sqrt(0) = 0
        assert volume_intensity_score(50.0, 100.0) == pytest.approx(0.0)

    def test_none_vol_20d(self):
        assert volume_intensity_score(None, 100.0) == pytest.approx(50.0)

    def test_none_vol_60d(self):
        assert volume_intensity_score(100.0, None) == pytest.approx(50.0)

    def test_zero_vol_60d(self):
        assert volume_intensity_score(100.0, 0.0) == pytest.approx(50.0)


# ── uptrend_signal_score ─────────────────────────────────────────────


class TestUptrendSignalScore:
    """Continuous scoring per sector entry (ratio in 0-1 range):

      base         = min(80, ratio * 100)
      ma_bonus     = 10 if ratio > ma_10 else 0
      slope_bonus  = 10 if slope > 0 else 0
      entry_score  = base + ma_bonus + slope_bonus

    Final = weighted average. Bearish: 100 - result.
    """

    def _make_sector(self, ratio, ma_10, slope, weight=1.0):
        return {
            "sector": "test",
            "ratio": ratio,
            "ma_10": ma_10,
            "slope": slope,
            "weight": weight,
        }

    def test_high_ratio_both_conditions_met(self):
        # ratio=0.5 (50%): base=50, ma_bonus=10 (0.5>0.4), slope_bonus=10 → 70
        data = [self._make_sector(ratio=0.5, ma_10=0.4, slope=0.5)]
        score = uptrend_signal_score(data, is_bearish=False)
        assert score == pytest.approx(70.0)

    def test_high_ratio_ma_bonus_only(self):
        # ratio=0.5: base=50, ma_bonus=10 (0.5>0.4), slope_bonus=0 → 60
        data = [self._make_sector(ratio=0.5, ma_10=0.4, slope=-0.1)]
        score = uptrend_signal_score(data, is_bearish=False)
        assert score == pytest.approx(60.0)

    def test_low_ratio_slope_bonus_only(self):
        # ratio=0.3: base=30, ma_bonus=0 (0.3<0.4), slope_bonus=10 → 40
        data = [self._make_sector(ratio=0.3, ma_10=0.4, slope=0.5)]
        score = uptrend_signal_score(data, is_bearish=False)
        assert score == pytest.approx(40.0)

    def test_low_ratio_no_conditions_met(self):
        # ratio=0.3: base=30, no bonuses → 30
        data = [self._make_sector(ratio=0.3, ma_10=0.4, slope=-0.1)]
        score = uptrend_signal_score(data, is_bearish=False)
        assert score == pytest.approx(30.0)

    def test_full_ratio_both_conditions(self):
        # ratio=0.8: base=80 (ceiling), +10+10 → 100
        data = [self._make_sector(ratio=0.8, ma_10=0.5, slope=0.5)]
        score = uptrend_signal_score(data, is_bearish=False)
        assert score == pytest.approx(100.0)

    def test_weighted_average(self):
        # sector A: ratio=0.5, both → 70, weight 2
        # sector B: ratio=0.3, neither → 30, weight 1
        # weighted = (70*2 + 30*1) / 3 = 56.67
        data = [
            self._make_sector(ratio=0.5, ma_10=0.4, slope=0.5, weight=2.0),
            self._make_sector(ratio=0.3, ma_10=0.4, slope=-0.1, weight=1.0),
        ]
        score = uptrend_signal_score(data, is_bearish=False)
        assert score == pytest.approx(56.67, abs=0.01)

    def test_bearish_inversion(self):
        # ratio=0.5, both → 70; bearish → 100-70 = 30
        data = [self._make_sector(ratio=0.5, ma_10=0.4, slope=0.5)]
        score = uptrend_signal_score(data, is_bearish=True)
        assert score == pytest.approx(30.0)

    def test_empty_list(self):
        assert uptrend_signal_score([], is_bearish=False) == pytest.approx(50.0)

    def test_equal_ratio_and_ma10(self):
        # ratio == ma_10 (not strictly >) → no ma_bonus; slope<=0 → no slope_bonus
        # base = min(80, 40) = 40 → 40
        data = [self._make_sector(ratio=0.4, ma_10=0.4, slope=0)]
        score = uptrend_signal_score(data, is_bearish=False)
        assert score == pytest.approx(40.0)


# ── uptrend_signal_score with None values ────────────────────────────


class TestUptrendSignalNoneValues:
    """Ensure None values in sector_data don't cause TypeError."""

    def test_none_ma_10(self):
        """ma_10=None treated as 0: ratio(0.5)>ma_10(0) AND slope(0.01)>0.
        base=50, ma_bonus=10, slope_bonus=10 → 70.
        """
        data = [{"sector": "Tech", "ratio": 0.5, "ma_10": None, "slope": 0.01, "weight": 1.0}]
        score = uptrend_signal_score(data, is_bearish=False)
        assert score == pytest.approx(70.0)

    def test_none_slope(self):
        """slope=None treated as 0: ratio(0.5)>ma_10(0.3) AND slope(0) not>0.
        base=50, ma_bonus=10, slope_bonus=0 → 60.
        """
        data = [{"sector": "Tech", "ratio": 0.5, "ma_10": 0.3, "slope": None, "weight": 1.0}]
        score = uptrend_signal_score(data, is_bearish=False)
        assert score == pytest.approx(60.0)

    def test_none_ratio(self):
        """ratio=None treated as 0: ratio(0) not>ma_10(0.3), slope(0.01)>0.
        base=0, ma_bonus=0, slope_bonus=10 → 10.
        """
        data = [{"sector": "Tech", "ratio": None, "ma_10": 0.3, "slope": 0.01, "weight": 1.0}]
        score = uptrend_signal_score(data, is_bearish=False)
        assert score == pytest.approx(10.0)

    def test_all_none(self):
        """All values None: ratio(0) not>ma_10(0), slope(0) not>0.
        base=0, no bonuses → 0.
        """
        data = [{"sector": "Tech", "ratio": None, "ma_10": None, "slope": None, "weight": 1.0}]
        score = uptrend_signal_score(data, is_bearish=False)
        assert score == pytest.approx(0.0)


# ── breadth_signal_score ─────────────────────────────────────────────


class TestBreadthSignalScore:
    """Power curve: min(100, ratio^2.5 * 80 + count_bonus)

    count_bonus = min(20, industry_count * 2); default count=0 → no bonus.
    Examples (no bonus): 0.0->0, 0.5->~14.1, 0.7->~32.8, 0.9->~61.5, 1.0->80, 1.5->100
    """

    def test_zero(self):
        assert breadth_signal_score(0.0) == pytest.approx(0.0)

    def test_half(self):
        # 0.5^2.5 * 80 = 0.1768 * 80 ≈ 14.14
        assert breadth_signal_score(0.5) == pytest.approx(14.14, abs=0.1)

    def test_seventy_percent(self):
        # 0.7^2.5 * 80 ≈ 32.8
        assert breadth_signal_score(0.7) == pytest.approx(32.80, abs=0.1)

    def test_full_without_bonus(self):
        # 1.0^2.5 * 80 = 80.0 (no count bonus)
        assert breadth_signal_score(1.0) == pytest.approx(80.0)

    def test_full_with_industry_count_bonus(self):
        # 1.0^2.5 * 80 + min(20, 5*2) = 80 + 10 = 90
        assert breadth_signal_score(1.0, industry_count=5) == pytest.approx(90.0)

    def test_count_bonus_capped_at_20(self):
        # 1.0^2.5 * 80 + min(20, 50*2) = 80 + 20 = 100
        assert breadth_signal_score(1.0, industry_count=50) == pytest.approx(100.0)

    def test_above_one_clamped(self):
        # 1.5^2.5 * 80 > 100 → clamped
        assert breadth_signal_score(1.5) == pytest.approx(100.0)

    def test_negative_clamped(self):
        assert breadth_signal_score(-0.3) == pytest.approx(0.0)

    def test_none(self):
        assert breadth_signal_score(None) == pytest.approx(50.0)


# ── calculate_theme_heat ─────────────────────────────────────────────


class TestCalculateThemeHeat:
    """Weights: momentum*0.35 + volume*0.20 + uptrend*0.25 + breadth*0.20"""

    def test_weighted_sum(self):
        # 80*0.35 + 60*0.20 + 70*0.25 + 50*0.20
        # = 28 + 12 + 17.5 + 10 = 67.5
        result = calculate_theme_heat(80.0, 60.0, 70.0, 50.0)
        assert result == pytest.approx(67.5)

    def test_all_100(self):
        result = calculate_theme_heat(100.0, 100.0, 100.0, 100.0)
        assert result == pytest.approx(100.0)

    def test_all_zero(self):
        result = calculate_theme_heat(0.0, 0.0, 0.0, 0.0)
        assert result == pytest.approx(0.0)

    def test_none_defaults_to_50(self):
        # All None → 50*0.35 + 50*0.20 + 50*0.25 + 50*0.20 = 50
        result = calculate_theme_heat(None, None, None, None)
        assert result == pytest.approx(50.0)

    def test_partial_none(self):
        # 80*0.35 + 50*0.20 + 50*0.25 + 50*0.20
        # = 28 + 10 + 12.5 + 10 = 60.5
        result = calculate_theme_heat(80.0, None, None, None)
        assert result == pytest.approx(60.5)

    def test_clamped_above_100(self):
        result = calculate_theme_heat(200.0, 200.0, 200.0, 200.0)
        assert result == 100.0

    def test_clamped_below_0(self):
        result = calculate_theme_heat(-50.0, -50.0, -50.0, -50.0)
        assert result == 0.0

    def test_returns_float(self):
        assert isinstance(calculate_theme_heat(50, 50, 50, 50), float)
