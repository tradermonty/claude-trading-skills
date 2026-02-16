"""Tests for lifecycle_calculator.py - Lifecycle Maturity Score (0-100)"""

import pytest
from calculators.lifecycle_calculator import (
    estimate_duration_score,
    extremity_clustering_score,
    price_extreme_saturation_score,
    valuation_premium_score,
    etf_proliferation_score,
    classify_stage,
    calculate_lifecycle_maturity,
)


# ── estimate_duration_score ──────────────────────────────────────────

class TestEstimateDurationScore:

    def test_bullish_all_active(self):
        # All 4 horizons > 2% => 100
        score = estimate_duration_score(3.0, 5.0, 10.0, 20.0, is_bearish=False)
        assert score == pytest.approx(100.0)

    def test_bullish_none_active(self):
        # All < 2% => 0
        score = estimate_duration_score(0.5, 1.0, 1.5, 1.9, is_bearish=False)
        assert score == pytest.approx(0.0)

    def test_bullish_two_active(self):
        # 2 out of 4 => 50
        score = estimate_duration_score(3.0, 5.0, 1.0, 0.5, is_bearish=False)
        assert score == pytest.approx(50.0)

    def test_bearish_all_active(self):
        # All < -2% => 100
        score = estimate_duration_score(-3.0, -5.0, -10.0, -20.0, is_bearish=True)
        assert score == pytest.approx(100.0)

    def test_bearish_none_active(self):
        # None < -2%
        score = estimate_duration_score(-0.5, -1.0, 0.0, 1.0, is_bearish=True)
        assert score == pytest.approx(0.0)

    def test_bearish_mixed(self):
        # 3 out of 4 < -2% => 75
        score = estimate_duration_score(-3.0, -5.0, -10.0, 0.0, is_bearish=True)
        assert score == pytest.approx(75.0)

    def test_boundary_exactly_2_percent(self):
        # 2.0 is NOT > 2 => not active
        score = estimate_duration_score(2.0, 2.0, 2.0, 2.0, is_bearish=False)
        assert score == pytest.approx(0.0)

    def test_boundary_just_above(self):
        score = estimate_duration_score(2.1, 2.1, 2.1, 2.1, is_bearish=False)
        assert score == pytest.approx(100.0)

    def test_none_values_treated_as_inactive(self):
        score = estimate_duration_score(None, None, 5.0, 10.0, is_bearish=False)
        assert score == pytest.approx(50.0)


# ── extremity_clustering_score ───────────────────────────────────────

class TestExtremityClusteringScore:

    def _make_stocks(self, rsi_values):
        return [{"rsi": r} for r in rsi_values]

    def test_bullish_50pct_above_70(self):
        # 5 out of 10 RSI > 70 => 50% * 200 = 100
        stocks = self._make_stocks([75, 80, 72, 85, 71, 40, 50, 60, 30, 20])
        score = extremity_clustering_score(stocks, is_bearish=False)
        assert score == pytest.approx(100.0)

    def test_bullish_25pct_above_70(self):
        # 2 out of 8 => 25% * 200 = 50
        stocks = self._make_stocks([75, 80, 40, 50, 60, 30, 20, 65])
        score = extremity_clustering_score(stocks, is_bearish=False)
        assert score == pytest.approx(50.0)

    def test_bearish_50pct_below_30(self):
        # 5 out of 10 RSI < 30
        stocks = self._make_stocks([10, 15, 20, 25, 29, 40, 50, 60, 70, 80])
        score = extremity_clustering_score(stocks, is_bearish=True)
        assert score == pytest.approx(100.0)

    def test_empty_returns_50(self):
        assert extremity_clustering_score([], is_bearish=False) == pytest.approx(50.0)

    def test_none_rsi_ignored(self):
        stocks = [{"rsi": None}, {"rsi": 75}, {"rsi": 80}]
        # 2 out of 3 valid, both > 70 => 2/3 ≈ 66.7% * 200 ≈ 133 => clamped 100
        score = extremity_clustering_score(stocks, is_bearish=False)
        assert score == pytest.approx(100.0)

    def test_zero_extreme(self):
        stocks = self._make_stocks([50, 55, 60, 65])
        score = extremity_clustering_score(stocks, is_bearish=False)
        assert score == pytest.approx(0.0)

    def test_boundary_rsi_70_not_counted_bullish(self):
        # RSI == 70 is NOT > 70
        stocks = self._make_stocks([70])
        score = extremity_clustering_score(stocks, is_bearish=False)
        assert score == pytest.approx(0.0)

    def test_boundary_rsi_30_not_counted_bearish(self):
        # RSI == 30 is NOT < 30
        stocks = self._make_stocks([30])
        score = extremity_clustering_score(stocks, is_bearish=True)
        assert score == pytest.approx(0.0)


# ── price_extreme_saturation_score ───────────────────────────────────

class TestPriceExtremeSaturationScore:

    def test_bullish_50pct_near_high(self):
        # 5 out of 10 within 5% of 52w high
        stocks = [{"dist_from_52w_high": d} for d in
                  [0.01, 0.02, 0.03, 0.04, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30]]
        score = price_extreme_saturation_score(stocks, is_bearish=False)
        assert score == pytest.approx(100.0)

    def test_bullish_25pct_near_high(self):
        stocks = [{"dist_from_52w_high": d} for d in
                  [0.01, 0.02, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35]]
        score = price_extreme_saturation_score(stocks, is_bearish=False)
        assert score == pytest.approx(50.0)

    def test_bullish_zero_near_high(self):
        stocks = [{"dist_from_52w_high": d} for d in [0.10, 0.20, 0.30]]
        score = price_extreme_saturation_score(stocks, is_bearish=False)
        assert score == pytest.approx(0.0)

    def test_bearish_50pct_near_low(self):
        stocks = [{"dist_from_52w_low": d} for d in
                  [0.01, 0.02, 0.03, 0.04, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30]]
        score = price_extreme_saturation_score(stocks, is_bearish=True)
        assert score == pytest.approx(100.0)

    def test_empty_returns_50(self):
        assert price_extreme_saturation_score([], is_bearish=False) == pytest.approx(50.0)

    def test_boundary_exactly_5pct(self):
        # dist <= 0.05 => counted
        stocks = [{"dist_from_52w_high": 0.05}]
        score = price_extreme_saturation_score(stocks, is_bearish=False)
        # 1/1 = 100% * 200 = 200 => clamped 100
        assert score == pytest.approx(100.0)

    def test_boundary_just_above_5pct(self):
        stocks = [{"dist_from_52w_high": 0.051}]
        score = price_extreme_saturation_score(stocks, is_bearish=False)
        assert score == pytest.approx(0.0)


# ── valuation_premium_score ──────────────────────────────────────────

class TestValuationPremiumScore:

    def _make_stocks(self, pe_values):
        return [{"pe_ratio": p} for p in pe_values]

    def test_half_market_premium(self):
        # median PE = 11 => ratio = 0.5 => (0.5-0.5)*32 = 0
        stocks = self._make_stocks([11, 11, 11])
        assert valuation_premium_score(stocks) == pytest.approx(0.0)

    def test_market_premium(self):
        # median PE = 22 => ratio = 1.0 => (1.0-0.5)*32 = 16
        stocks = self._make_stocks([22, 22, 22])
        assert valuation_premium_score(stocks) == pytest.approx(16.0)

    def test_double_premium(self):
        # median PE = 44 => ratio = 2.0 => (2.0-0.5)*32 = 48
        stocks = self._make_stocks([44, 44, 44])
        assert valuation_premium_score(stocks) == pytest.approx(48.0)

    def test_triple_premium(self):
        # median PE = 66 => ratio = 3.0 => (3.0-0.5)*32 = 80
        stocks = self._make_stocks([66, 66, 66])
        assert valuation_premium_score(stocks) == pytest.approx(80.0)

    def test_capped_at_100(self):
        # median PE = 110 => ratio = 5.0 => (5.0-0.5)*32 = 144 => clamped 100
        stocks = self._make_stocks([110, 110, 110])
        assert valuation_premium_score(stocks) == pytest.approx(100.0)

    def test_fewer_than_3_valid_returns_50(self):
        stocks = self._make_stocks([22, 22])
        assert valuation_premium_score(stocks) == pytest.approx(50.0)

    def test_none_pe_excluded(self):
        stocks = self._make_stocks([None, 22, 22])
        assert valuation_premium_score(stocks) == pytest.approx(50.0)

    def test_negative_pe_excluded(self):
        stocks = self._make_stocks([-10, 22, 22, 22])
        # valid: [22, 22, 22] => median 22 => ratio 1.0 => 16
        assert valuation_premium_score(stocks) == pytest.approx(16.0)

    def test_empty_returns_50(self):
        assert valuation_premium_score([]) == pytest.approx(50.0)


# ── etf_proliferation_score ──────────────────────────────────────────

class TestEtfProliferationScore:

    def test_zero(self):
        assert etf_proliferation_score(0) == pytest.approx(0.0)

    def test_one(self):
        assert etf_proliferation_score(1) == pytest.approx(20.0)

    def test_three(self):
        assert etf_proliferation_score(3) == pytest.approx(40.0)

    def test_six(self):
        assert etf_proliferation_score(6) == pytest.approx(60.0)

    def test_ten(self):
        assert etf_proliferation_score(10) == pytest.approx(80.0)

    def test_fifteen(self):
        assert etf_proliferation_score(15) == pytest.approx(100.0)

    def test_two(self):
        # 1 < 2 <= 3 => 40
        assert etf_proliferation_score(2) == pytest.approx(40.0)

    def test_five(self):
        # 3 < 5 <= 6 => 60
        assert etf_proliferation_score(5) == pytest.approx(60.0)


# ── classify_stage ───────────────────────────────────────────────────

class TestClassifyStage:

    def test_emerging(self):
        assert classify_stage(0) == "Emerging"
        assert classify_stage(10) == "Emerging"
        assert classify_stage(19.9) == "Emerging"

    def test_accelerating(self):
        assert classify_stage(20) == "Accelerating"
        assert classify_stage(30) == "Accelerating"
        assert classify_stage(39.9) == "Accelerating"

    def test_trending(self):
        assert classify_stage(40) == "Trending"
        assert classify_stage(50) == "Trending"
        assert classify_stage(59.9) == "Trending"

    def test_mature(self):
        assert classify_stage(60) == "Mature"
        assert classify_stage(70) == "Mature"
        assert classify_stage(79.9) == "Mature"

    def test_exhausting(self):
        assert classify_stage(80) == "Exhausting"
        assert classify_stage(90) == "Exhausting"
        assert classify_stage(100) == "Exhausting"


# ── calculate_lifecycle_maturity ─────────────────────────────────────

class TestCalculateLifecycleMaturity:

    def test_weighted_sum(self):
        # 60*0.25 + 80*0.25 + 40*0.25 + 50*0.15 + 30*0.10
        # = 15 + 20 + 10 + 7.5 + 3 = 55.5
        result = calculate_lifecycle_maturity(60.0, 80.0, 40.0, 50.0, 30.0)
        assert result == pytest.approx(55.5)

    def test_all_100(self):
        result = calculate_lifecycle_maturity(100.0, 100.0, 100.0, 100.0, 100.0)
        assert result == pytest.approx(100.0)

    def test_all_zero(self):
        result = calculate_lifecycle_maturity(0.0, 0.0, 0.0, 0.0, 0.0)
        assert result == pytest.approx(0.0)

    def test_none_defaults(self):
        # All None => 50 each
        result = calculate_lifecycle_maturity(None, None, None, None, None)
        assert result == pytest.approx(50.0)

    def test_clamped_above_100(self):
        result = calculate_lifecycle_maturity(200.0, 200.0, 200.0, 200.0, 200.0)
        assert result == 100.0

    def test_clamped_below_0(self):
        result = calculate_lifecycle_maturity(-50.0, -50.0, -50.0, -50.0, -50.0)
        assert result == 0.0

    def test_returns_float(self):
        assert isinstance(calculate_lifecycle_maturity(50, 50, 50, 50, 50), float)
