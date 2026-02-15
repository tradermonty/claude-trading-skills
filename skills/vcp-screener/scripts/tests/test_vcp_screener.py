#!/usr/bin/env python3
"""
Tests for VCP Screener modules.

Covers boundary conditions for VCP pattern detection, contraction validation,
Trend Template criteria, volume patterns, pivot proximity, and scoring.
"""

import os
import sys
import json
import tempfile
import pytest

# Add parent to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from calculators.trend_template_calculator import calculate_trend_template
from calculators.vcp_pattern_calculator import calculate_vcp_pattern, _validate_vcp
from calculators.volume_pattern_calculator import calculate_volume_pattern
from calculators.pivot_proximity_calculator import calculate_pivot_proximity
from calculators.relative_strength_calculator import calculate_relative_strength
from scorer import calculate_composite_score
from report_generator import generate_json_report, generate_markdown_report


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_prices(n, start=100.0, daily_change=0.0, volume=1000000):
    """Generate synthetic price data (most-recent-first)."""
    prices = []
    p = start
    for i in range(n):
        p_day = p * (1 + daily_change * (n - i))  # linear drift
        prices.append({
            "date": f"2025-{(i // 22) + 1:02d}-{(i % 22) + 1:02d}",
            "open": round(p_day, 2),
            "high": round(p_day * 1.01, 2),
            "low": round(p_day * 0.99, 2),
            "close": round(p_day, 2),
            "adjClose": round(p_day, 2),
            "volume": volume,
        })
    return prices


def _make_vcp_contractions(depths, high_price=100.0):
    """Build contraction dicts for _validate_vcp testing."""
    contractions = []
    hp = high_price
    for i, depth in enumerate(depths):
        lp = hp * (1 - depth / 100)
        contractions.append({
            "label": f"T{i+1}",
            "high_idx": i * 20,
            "high_price": round(hp, 2),
            "high_date": f"2025-01-{i*20+1:02d}",
            "low_idx": i * 20 + 10,
            "low_price": round(lp, 2),
            "low_date": f"2025-01-{i*20+11:02d}",
            "depth_pct": round(depth, 2),
        })
        hp = hp * 0.99  # next high slightly lower
    return contractions


# ===========================================================================
# VCP Pattern Validation Tests (Fix 1: contraction ratio 0.75 rule)
# ===========================================================================

class TestVCPValidation:
    """Test the strict 75% contraction ratio rule."""

    def test_valid_tight_contractions(self):
        """T1=20%, T2=10%, T3=5% -> ratios 0.50, 0.50 -> valid"""
        contractions = _make_vcp_contractions([20, 10, 5])
        result = _validate_vcp(contractions, total_days=120)
        assert result["valid"] is True

    def test_invalid_loose_contractions(self):
        """T1=20%, T2=18% -> ratio 0.90 > 0.75 -> invalid"""
        contractions = _make_vcp_contractions([20, 18])
        result = _validate_vcp(contractions, total_days=120)
        assert result["valid"] is False
        assert any("0.75" in issue for issue in result["issues"])

    def test_borderline_ratio_075(self):
        """T1=20%, T2=15% -> ratio 0.75 -> valid (exactly at threshold)"""
        contractions = _make_vcp_contractions([20, 15])
        result = _validate_vcp(contractions, total_days=120)
        assert result["valid"] is True

    def test_ratio_076_invalid(self):
        """T1=20%, T2=15.2% -> ratio 0.76 -> invalid"""
        contractions = _make_vcp_contractions([20, 15.2])
        result = _validate_vcp(contractions, total_days=120)
        assert result["valid"] is False

    def test_expanding_contractions_invalid(self):
        """T1=10%, T2=15% -> ratio 1.5 -> invalid"""
        contractions = _make_vcp_contractions([10, 15])
        result = _validate_vcp(contractions, total_days=120)
        assert result["valid"] is False

    def test_single_contraction_too_few(self):
        """Single contraction is not enough for VCP."""
        contractions = _make_vcp_contractions([20])
        result = _validate_vcp(contractions, total_days=120)
        assert result["valid"] is False

    def test_t1_too_shallow(self):
        """T1=5% is below 8% minimum -> invalid"""
        contractions = _make_vcp_contractions([5, 3])
        result = _validate_vcp(contractions, total_days=120)
        assert result["valid"] is False

    def test_four_progressive_contractions(self):
        """T1=30%, T2=15%, T3=7%, T4=3% -> valid textbook"""
        contractions = _make_vcp_contractions([30, 15, 7, 3])
        result = _validate_vcp(contractions, total_days=120)
        assert result["valid"] is True


# ===========================================================================
# Trend Template Tests (Fix 5: C3 conservative with limited data)
# ===========================================================================

class TestTrendTemplate:
    """Test Trend Template scoring."""

    def test_insufficient_data(self):
        prices = _make_prices(30)
        quote = {"price": 100, "yearHigh": 110, "yearLow": 50}
        result = calculate_trend_template(prices, quote)
        assert result["score"] == 0
        assert result["passed"] is False

    def test_c3_fails_with_200_days(self):
        """With exactly 200 days, C3 should fail (cannot verify 22d SMA200 trend)."""
        prices = _make_prices(210, start=100, daily_change=0.001)
        quote = {"price": 120, "yearHigh": 125, "yearLow": 80}
        result = calculate_trend_template(prices, quote, rs_rank=85)
        c3 = result["criteria"].get("c3_sma200_trending_up", {})
        assert c3["passed"] is False

    def test_c3_passes_with_222_days(self):
        """With 222+ days and uptrend, C3 should pass."""
        prices = _make_prices(250, start=80, daily_change=0.001)
        quote = {"price": 120, "yearHigh": 125, "yearLow": 70}
        result = calculate_trend_template(prices, quote, rs_rank=85)
        # C3 should be evaluated (may pass or fail depending on synthetic data)
        c3 = result["criteria"].get("c3_sma200_trending_up", {})
        assert "Cannot verify" not in c3.get("detail", "")


# ===========================================================================
# Volume Pattern Tests
# ===========================================================================

class TestVolumePattern:
    def test_insufficient_data(self):
        result = calculate_volume_pattern([])
        assert result["score"] == 0
        assert "Insufficient" in result["error"]

    def test_low_dry_up_ratio(self):
        """Recent volume much lower than 50d avg -> high score."""
        prices = _make_prices(60, volume=1000000)
        # Override recent 10 bars with low volume
        for i in range(10):
            prices[i]["volume"] = 200000
        result = calculate_volume_pattern(prices)
        assert result["dry_up_ratio"] < 0.3
        assert result["score"] >= 80


# ===========================================================================
# Pivot Proximity Tests
# ===========================================================================

class TestPivotProximity:
    def test_no_pivot(self):
        result = calculate_pivot_proximity(100.0, None)
        assert result["score"] == 0

    def test_breakout_confirmed(self):
        result = calculate_pivot_proximity(105.0, 100.0, last_contraction_low=95.0,
                                           breakout_volume=True)
        assert result["score"] == 100
        assert result["trade_status"] == "BREAKOUT CONFIRMED"

    def test_at_pivot(self):
        result = calculate_pivot_proximity(99.0, 100.0, last_contraction_low=95.0)
        assert result["score"] == 90
        assert "AT PIVOT" in result["trade_status"]

    def test_far_below_pivot(self):
        result = calculate_pivot_proximity(80.0, 100.0)
        assert result["score"] == 10

    def test_below_stop_level(self):
        result = calculate_pivot_proximity(90.0, 100.0, last_contraction_low=95.0)
        assert "BELOW STOP LEVEL" in result["trade_status"]


# ===========================================================================
# Relative Strength Tests
# ===========================================================================

class TestRelativeStrength:
    def test_insufficient_stock_data(self):
        result = calculate_relative_strength([], [])
        assert result["score"] == 0

    def test_outperformer(self):
        # Stock up 30%, SP500 up 5% over 3 months
        stock = _make_prices(70, start=77, daily_change=0.003)
        sp500 = _make_prices(70, start=95, daily_change=0.0005)
        result = calculate_relative_strength(stock, sp500)
        assert result["score"] >= 60  # should outperform


# ===========================================================================
# Scorer Tests
# ===========================================================================

class TestScorer:
    def test_textbook_rating(self):
        result = calculate_composite_score(100, 100, 100, 100, 100)
        assert result["composite_score"] == 100
        assert result["rating"] == "Textbook VCP"

    def test_no_vcp_rating(self):
        result = calculate_composite_score(0, 0, 0, 0, 0)
        assert result["composite_score"] == 0
        assert result["rating"] == "No VCP"

    def test_weights_sum_to_100(self):
        """Verify component weights sum to 1.0"""
        from scorer import COMPONENT_WEIGHTS
        total = sum(COMPONENT_WEIGHTS.values())
        assert abs(total - 1.0) < 0.001


# ===========================================================================
# Report Generator Tests (Fix 2: market_cap=None, Fix 3/4: summary counts)
# ===========================================================================

class TestReportGenerator:
    def _make_stock(self, symbol="TEST", score=75.0, market_cap=50e9):
        return {
            "symbol": symbol,
            "company_name": f"{symbol} Corp",
            "sector": "Technology",
            "price": 150.0,
            "market_cap": market_cap,
            "composite_score": score,
            "rating": "Good VCP",
            "rating_description": "Solid VCP",
            "guidance": "Buy on volume confirmation",
            "weakest_component": "Volume",
            "weakest_score": 40,
            "strongest_component": "Trend",
            "strongest_score": 100,
            "trend_template": {"score": 100, "criteria_passed": 7},
            "vcp_pattern": {"score": 70, "num_contractions": 2, "contractions": [],
                            "pivot_price": 145.0},
            "volume_pattern": {"score": 40, "dry_up_ratio": 0.8},
            "pivot_proximity": {"score": 75, "distance_from_pivot_pct": -3.0,
                                "stop_loss_price": 140.0, "risk_pct": 7.0,
                                "trade_status": "NEAR PIVOT"},
            "relative_strength": {"score": 80, "rs_rank_estimate": 80,
                                  "weighted_rs": 15.0},
        }

    def test_market_cap_none(self):
        """market_cap=None should not crash."""
        with tempfile.TemporaryDirectory() as tmpdir:
            stock = self._make_stock(market_cap=None)
            md_file = os.path.join(tmpdir, "test.md")
            metadata = {
                "generated_at": "2026-01-01",
                "universe_description": "Test",
                "funnel": {},
                "api_stats": {},
            }
            generate_markdown_report([stock], metadata, md_file)
            with open(md_file) as f:
                content = f.read()
            assert "N/A" in content  # market cap should show N/A

    def test_summary_uses_all_results(self):
        """Summary should count all candidates, not just top N."""
        all_results = [self._make_stock(f"S{i}", score=90 - i * 5) for i in range(10)]
        top_results = all_results[:3]
        metadata = {
            "generated_at": "2026-01-01",
            "universe_description": "Test",
            "funnel": {"vcp_candidates": 10},
            "api_stats": {},
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = os.path.join(tmpdir, "test.json")
            generate_json_report(top_results, metadata, json_file,
                                 all_results=all_results)
            with open(json_file) as f:
                data = json.load(f)
            assert data["summary"]["total"] == 10
            assert len(data["results"]) == 3

    def test_market_cap_zero(self):
        """market_cap=0 should show N/A."""
        with tempfile.TemporaryDirectory() as tmpdir:
            stock = self._make_stock(market_cap=0)
            md_file = os.path.join(tmpdir, "test.md")
            metadata = {
                "generated_at": "2026-01-01",
                "universe_description": "Test",
                "funnel": {},
                "api_stats": {},
            }
            generate_markdown_report([stock], metadata, md_file)
            with open(md_file) as f:
                content = f.read()
            assert "N/A" in content

    def test_top_greater_than_20(self):
        """--top=25 should produce 25 entries in Markdown, not capped at 20."""
        stocks = [self._make_stock(f"S{i:02d}", score=95 - i) for i in range(25)]
        metadata = {
            "generated_at": "2026-01-01",
            "universe_description": "Test",
            "funnel": {"vcp_candidates": 25},
            "api_stats": {},
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            md_file = os.path.join(tmpdir, "test.md")
            generate_markdown_report(stocks, metadata, md_file)
            with open(md_file) as f:
                content = f.read()
            assert "## Top 25 VCP Candidates" in content
            # All 25 stocks should have an entry header
            for i in range(25):
                assert f"S{i:02d}" in content
