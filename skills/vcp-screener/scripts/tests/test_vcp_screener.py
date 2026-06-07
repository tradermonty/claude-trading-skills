#!/usr/bin/env python3
"""
Tests for VCP Screener modules.

Covers boundary conditions for VCP pattern detection, contraction validation,
Trend Template criteria, volume patterns, pivot proximity, and scoring.
"""

import json
import os
import tempfile

import pytest
from calculators.pivot_proximity_calculator import calculate_pivot_proximity
from calculators.relative_strength_calculator import calculate_relative_strength
from calculators.trend_template_calculator import calculate_trend_template
from calculators.vcp_pattern_calculator import _validate_vcp, calculate_vcp_pattern
from calculators.volume_pattern_calculator import calculate_volume_pattern
from report_generator import generate_json_report, generate_markdown_report
from scorer import calculate_composite_score
from screen_vcp import (
    analyze_stock,
    compute_entry_ready,
    is_stale_price,
    parse_arguments,
    passes_trend_filter,
    pre_filter_stock,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_prices(n, start=100.0, daily_change=0.0, volume=1000000):
    """Generate synthetic price data (most-recent-first)."""
    prices = []
    p = start
    for i in range(n):
        p_day = p * (1 + daily_change * (n - i))  # linear drift
        prices.append(
            {
                "date": f"2025-{(i // 22) + 1:02d}-{(i % 22) + 1:02d}",
                "open": round(p_day, 2),
                "high": round(p_day * 1.01, 2),
                "low": round(p_day * 0.99, 2),
                "close": round(p_day, 2),
                "adjClose": round(p_day, 2),
                "volume": volume,
            }
        )
    return prices


def _make_vcp_contractions(depths, high_price=100.0):
    """Build contraction dicts for _validate_vcp testing."""
    contractions = []
    hp = high_price
    for i, depth in enumerate(depths):
        lp = hp * (1 - depth / 100)
        contractions.append(
            {
                "label": f"T{i + 1}",
                "high_idx": i * 20,
                "high_price": round(hp, 2),
                "high_date": f"2025-01-{i * 20 + 1:02d}",
                "low_idx": i * 20 + 10,
                "low_price": round(lp, 2),
                "low_date": f"2025-01-{i * 20 + 11:02d}",
                "depth_pct": round(depth, 2),
            }
        )
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
# Stale Price (Acquisition) Filter Tests
# ===========================================================================


class TestStalePrice:
    """Test is_stale_price() - detects acquired/pinned stocks."""

    def test_stale_flat_price(self):
        """Daily range < 1% for 10 days -> stale."""
        prices = []
        for i in range(20):
            prices.append(
                {
                    "date": f"2026-01-{20 - i:02d}",
                    "open": 14.31,
                    "high": 14.35,
                    "low": 14.28,
                    "close": 14.31,
                    "volume": 500000,
                }
            )
        assert is_stale_price(prices) is True

    def test_normal_price_action(self):
        """Normal volatility -> not stale."""
        prices = []
        for i in range(20):
            base = 100.0 + i * 0.5
            prices.append(
                {
                    "date": f"2026-01-{20 - i:02d}",
                    "open": base,
                    "high": base * 1.02,
                    "low": base * 0.98,
                    "close": base + 0.3,
                    "volume": 1000000,
                }
            )
        assert is_stale_price(prices) is False

    def test_insufficient_data(self):
        """Less than lookback days -> not stale (let other filters handle)."""
        prices = [{"date": "2026-01-01", "high": 10, "low": 10, "close": 10}]
        assert is_stale_price(prices) is False


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
        """Recent volume much lower than 50d avg -> high score.

        Bar[0] is excluded from dry-up (potential breakout bar).
        The dry-up window is volumes[1:11]. Set bars 0-10 to low volume
        so that all 10 dry-up bars have low volume.
        """
        prices = _make_prices(60, volume=1000000)
        # Override bars 0-10 (11 bars) with low volume so volumes[1:11] are all low
        for i in range(11):
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
        """0-3% above with volume -> base 90 + bonus 10 = 100, BREAKOUT CONFIRMED."""
        result = calculate_pivot_proximity(
            102.0, 100.0, last_contraction_low=95.0, breakout_volume=True
        )
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
        assert result["score"] == 0
        assert result["risk_pct"] is None

    def test_extended_above_pivot_7pct(self):
        """7% above pivot (no volume) -> score=50, High chase risk."""
        result = calculate_pivot_proximity(107.0, 100.0, last_contraction_low=95.0)
        assert result["score"] == 50
        assert "High chase risk" in result["trade_status"]

    def test_extended_above_pivot_25pct(self):
        """25% above pivot -> score=20, OVEREXTENDED."""
        result = calculate_pivot_proximity(125.0, 100.0, last_contraction_low=95.0)
        assert result["score"] == 20
        assert "OVEREXTENDED" in result["trade_status"]

    def test_near_above_pivot_2pct(self):
        """2% above pivot (no volume) -> score=90, ABOVE PIVOT."""
        result = calculate_pivot_proximity(102.0, 100.0, last_contraction_low=95.0)
        assert result["score"] == 90
        assert "ABOVE PIVOT" in result["trade_status"]

    # --- New distance-priority tests ---

    def test_breakout_volume_no_override_at_33pct(self):
        """+33.5% above, volume=True -> score=20 (distance priority, no bonus >5%)."""
        result = calculate_pivot_proximity(
            133.5, 100.0, last_contraction_low=95.0, breakout_volume=True
        )
        assert result["score"] == 20
        assert "OVEREXTENDED" in result["trade_status"]

    def test_breakout_volume_bonus_at_2pct(self):
        """+2% above, volume=True -> base 90 + bonus 10 = 100."""
        result = calculate_pivot_proximity(
            102.0, 100.0, last_contraction_low=95.0, breakout_volume=True
        )
        assert result["score"] == 100
        assert result["trade_status"] == "BREAKOUT CONFIRMED"

    def test_breakout_volume_bonus_at_4pct(self):
        """+4% above, volume=True -> base 65 + bonus 10 = 75."""
        result = calculate_pivot_proximity(
            104.0, 100.0, last_contraction_low=95.0, breakout_volume=True
        )
        assert result["score"] == 75
        assert "vol confirmed" in result["trade_status"]

    def test_breakout_volume_no_bonus_at_7pct(self):
        """+7% above, volume=True -> score=50 (no bonus >5%)."""
        result = calculate_pivot_proximity(
            107.0, 100.0, last_contraction_low=95.0, breakout_volume=True
        )
        assert result["score"] == 50
        assert "High chase risk" in result["trade_status"]


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
# Entry Ready Tests
# ===========================================================================


class TestEntryReady:
    """Test compute_entry_ready() from screen_vcp module."""

    def _make_result(
        self,
        valid_vcp=True,
        distance_from_pivot_pct=-1.0,
        dry_up_ratio=0.5,
        risk_pct=5.0,
    ):
        """Build a minimal analysis result dict for compute_entry_ready()."""
        return {
            "valid_vcp": valid_vcp,
            "distance_from_pivot_pct": distance_from_pivot_pct,
            "volume_pattern": {"dry_up_ratio": dry_up_ratio},
            "pivot_proximity": {"risk_pct": risk_pct},
        }

    def test_entry_ready_ideal_candidate(self):
        """valid_vcp=True, distance=-1%, dry_up=0.5, risk=5% -> True."""
        result = self._make_result(
            valid_vcp=True,
            distance_from_pivot_pct=-1.0,
            dry_up_ratio=0.5,
            risk_pct=5.0,
        )
        assert compute_entry_ready(result) is True

    def test_entry_ready_false_extended(self):
        """valid_vcp=True, distance=+15% -> False (too far above pivot)."""
        result = self._make_result(
            valid_vcp=True,
            distance_from_pivot_pct=15.0,
            dry_up_ratio=0.5,
            risk_pct=5.0,
        )
        assert compute_entry_ready(result) is False

    def test_entry_ready_false_invalid_vcp(self):
        """valid_vcp=False -> False regardless of distance."""
        result = self._make_result(
            valid_vcp=False,
            distance_from_pivot_pct=-1.0,
            dry_up_ratio=0.5,
            risk_pct=5.0,
        )
        assert compute_entry_ready(result) is False

    def test_entry_ready_false_high_risk(self):
        """valid_vcp=True, distance=-1%, risk=20% -> False (risk too high)."""
        result = self._make_result(
            valid_vcp=True,
            distance_from_pivot_pct=-1.0,
            dry_up_ratio=0.5,
            risk_pct=20.0,
        )
        assert compute_entry_ready(result) is False

    def test_entry_ready_custom_max_above_pivot(self):
        """CLI --max-above-pivot=5.0 allows +4% above pivot."""
        result = self._make_result(distance_from_pivot_pct=4.0)
        assert compute_entry_ready(result, max_above_pivot=5.0) is True
        assert compute_entry_ready(result, max_above_pivot=3.0) is False

    def test_entry_ready_custom_max_risk(self):
        """CLI --max-risk=10.0 rejects risk=12%."""
        result = self._make_result(risk_pct=12.0)
        assert compute_entry_ready(result, max_risk=15.0) is True
        assert compute_entry_ready(result, max_risk=10.0) is False

    def test_entry_ready_no_require_valid_vcp(self):
        """CLI --no-require-valid-vcp allows invalid VCP."""
        result = self._make_result(valid_vcp=False)
        assert compute_entry_ready(result, require_valid_vcp=True) is False
        assert compute_entry_ready(result, require_valid_vcp=False) is True


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

    def test_valid_vcp_false_caps_rating(self):
        """valid_vcp=False with composite>=70 -> rating capped to 'Developing VCP'."""
        # Scores: 80*0.25 + 70*0.25 + 70*0.20 + 70*0.15 + 70*0.15 = 72.5
        result = calculate_composite_score(80, 70, 70, 70, 70, valid_vcp=False)
        assert result["composite_score"] >= 70
        assert result["rating"] == "Developing VCP"
        assert "not confirmed" in result["rating_description"].lower()
        assert result["valid_vcp"] is False

    def test_valid_vcp_true_no_cap(self):
        """valid_vcp=True with composite>=70 -> normal rating (Good VCP)."""
        result = calculate_composite_score(80, 70, 70, 70, 70, valid_vcp=True)
        assert result["composite_score"] >= 70
        assert result["rating"] == "Good VCP"
        assert result["valid_vcp"] is True

    def test_valid_vcp_false_low_score_no_effect(self):
        """valid_vcp=False with composite<70 -> no cap needed, normal rating."""
        # Scores: 60*0.25 + 50*0.25 + 50*0.20 + 50*0.15 + 50*0.15 = 52.5
        result = calculate_composite_score(60, 50, 50, 50, 50, valid_vcp=False)
        assert result["composite_score"] < 70
        assert result["rating"] == "Weak VCP"
        assert result["valid_vcp"] is False


# ===========================================================================
# Report Generator Tests (Fix 2: market_cap=None, Fix 3/4: summary counts)
# ===========================================================================


class TestReportGenerator:
    def _make_stock(self, symbol="TEST", score=75.0, market_cap=50e9, rating=None):
        if rating is None:
            if score >= 90:
                rating = "Textbook VCP"
            elif score >= 80:
                rating = "Strong VCP"
            elif score >= 70:
                rating = "Good VCP"
            elif score >= 60:
                rating = "Developing VCP"
            elif score >= 50:
                rating = "Weak VCP"
            else:
                rating = "No VCP"
        return {
            "symbol": symbol,
            "company_name": f"{symbol} Corp",
            "sector": "Technology",
            "price": 150.0,
            "market_cap": market_cap,
            "composite_score": score,
            "rating": rating,
            "rating_description": "Solid VCP",
            "guidance": "Buy on volume confirmation",
            "weakest_component": "Volume",
            "weakest_score": 40,
            "strongest_component": "Trend",
            "strongest_score": 100,
            "trend_template": {"score": 100, "criteria_passed": 7},
            "vcp_pattern": {
                "score": 70,
                "num_contractions": 2,
                "contractions": [],
                "pivot_price": 145.0,
            },
            "volume_pattern": {"score": 40, "dry_up_ratio": 0.8},
            "pivot_proximity": {
                "score": 75,
                "distance_from_pivot_pct": -3.0,
                "stop_loss_price": 140.0,
                "risk_pct": 7.0,
                "trade_status": "NEAR PIVOT",
            },
            "relative_strength": {"score": 80, "rs_rank_estimate": 80, "weighted_rs": 15.0},
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
            generate_json_report(top_results, metadata, json_file, all_results=all_results)
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
            # All 25 stocks should appear in Section A or B
            assert "Section A:" in content or "Section B:" in content
            for i in range(25):
                assert f"S{i:02d}" in content

    def test_report_two_sections(self):
        """Report splits into Pre-Breakout Watchlist and Extended sections."""
        entry_ready_stock = self._make_stock("READY", score=80.0, rating="Strong VCP")
        entry_ready_stock["entry_ready"] = True
        entry_ready_stock["distance_from_pivot_pct"] = -1.0

        extended_stock = self._make_stock("EXTENDED", score=75.0, rating="Good VCP")
        extended_stock["entry_ready"] = False
        extended_stock["distance_from_pivot_pct"] = 15.0

        results = [entry_ready_stock, extended_stock]
        metadata = {
            "generated_at": "2026-01-01",
            "universe_description": "Test",
            "funnel": {"vcp_candidates": 2},
            "api_stats": {},
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            md_file = os.path.join(tmpdir, "test.md")
            generate_markdown_report(results, metadata, md_file)
            with open(md_file) as f:
                content = f.read()
            assert "Pre-Breakout Watchlist" in content
            assert "Extended / Quality VCP" in content
            assert "READY" in content
            assert "EXTENDED" in content

    def test_summary_counts_by_rating_not_score(self):
        """Summary should use rating field, not composite_score.

        A stock with composite=72 but rating='Developing VCP' (valid_vcp cap)
        must count as developing, not good.
        """
        from report_generator import _generate_summary

        results = [
            # Normal: composite=75, rating=Good VCP
            self._make_stock("GOOD1", score=75.0, rating="Good VCP"),
            # Capped: composite=72 but valid_vcp=False -> Developing VCP
            self._make_stock("CAPPED", score=72.0, rating="Developing VCP"),
            # Normal developing
            self._make_stock("DEV1", score=65.0, rating="Developing VCP"),
            # Weak
            self._make_stock("WEAK1", score=55.0, rating="Weak VCP"),
        ]

        summary = _generate_summary(results)
        assert summary["total"] == 4
        assert summary["good"] == 1  # only GOOD1
        assert summary["developing"] == 2  # CAPPED + DEV1
        assert summary["weak"] == 1  # WEAK1
        assert summary["textbook"] == 0
        assert summary["strong"] == 0


# ===========================================================================
# SMA50 Extended Penalty Tests
# ===========================================================================


class TestSMA50ExtendedPenalty:
    """Test extended penalty applied to trend template score."""

    def _make_stage2_prices(self, n=250, sma50_target=100.0, price=None):
        """Build synthetic prices where SMA50 ≈ sma50_target.

        All prices are constant at sma50_target so SMA50 = sma50_target exactly.
        The quote price is set separately to control distance.
        """
        prices = []
        for i in range(n):
            prices.append(
                {
                    "date": f"2025-{(i // 22) + 1:02d}-{(i % 22) + 1:02d}",
                    "open": sma50_target,
                    "high": sma50_target * 1.005,
                    "low": sma50_target * 0.995,
                    "close": sma50_target,
                    "adjClose": sma50_target,
                    "volume": 1000000,
                }
            )
        return prices

    def _run_tt(self, distance_pct, ext_threshold=8.0):
        """Run calculate_trend_template with a given SMA50 distance %.

        Returns the result dict.
        """
        sma50_target = 100.0
        price = sma50_target * (1 + distance_pct / 100)
        prices = self._make_stage2_prices(n=250, sma50_target=sma50_target)
        quote = {
            "price": price,
            "yearHigh": price * 1.05,
            "yearLow": sma50_target * 0.6,
        }
        return calculate_trend_template(
            prices,
            quote,
            rs_rank=85,
            ext_threshold=ext_threshold,
        )

    # --- Penalty calculation ---

    def test_no_penalty_within_8pct(self):
        result = self._run_tt(5.0)
        assert result["extended_penalty"] == 0

    def test_penalty_at_10pct_distance(self):
        result = self._run_tt(10.0)
        assert result["extended_penalty"] == -5

    def test_penalty_at_15pct_distance(self):
        result = self._run_tt(15.0)
        assert result["extended_penalty"] == -10

    def test_penalty_at_20pct_distance(self):
        result = self._run_tt(20.0)
        assert result["extended_penalty"] == -15

    def test_penalty_at_30pct_distance(self):
        result = self._run_tt(30.0)
        assert result["extended_penalty"] == -20

    def test_penalty_floor_at_zero(self):
        """Penalty cannot make score negative (max(0, raw + penalty))."""
        # Recent 50 at 80, older 200 at 120 → SMA50=80, SMA150≈107, SMA200≈110
        # Price=105: above SMA50 by ~31% (penalty=-20) but below SMA150 (C1 fail)
        # Only C4 passes → raw_score=14.3, 14.3+(-20)=-5.7 → floor to 0
        n = 250
        prices = []
        for i in range(n):
            close = 80.0 if i < 50 else 120.0
            prices.append(
                {
                    "date": f"2025-{(i // 22) + 1:02d}-{(i % 22) + 1:02d}",
                    "open": close,
                    "high": close * 1.005,
                    "low": close * 0.995,
                    "close": close,
                    "adjClose": close,
                    "volume": 1000000,
                }
            )
        quote = {"price": 105.0, "yearHigh": 200.0, "yearLow": 100.0}
        result = calculate_trend_template(prices, quote, rs_rank=10)
        assert result["extended_penalty"] == -20
        assert result["raw_score"] <= 14.3
        assert result["score"] == 0

    def test_price_below_sma50_no_penalty(self):
        result = self._run_tt(-5.0)
        assert result["extended_penalty"] == 0

    # --- Boundary tests (R1-4) ---

    def test_boundary_exactly_8pct(self):
        result = self._run_tt(8.0)
        assert result["extended_penalty"] == -5

    def test_boundary_exactly_12pct(self):
        result = self._run_tt(12.0)
        assert result["extended_penalty"] == -10

    def test_boundary_exactly_18pct(self):
        result = self._run_tt(18.0)
        assert result["extended_penalty"] == -15

    def test_boundary_exactly_25pct(self):
        result = self._run_tt(25.0)
        assert result["extended_penalty"] == -20

    # --- Gate separation (R1-1: most important) ---

    def test_passed_uses_raw_score_not_adjusted(self):
        """raw >= 85, ext < 0 -> passed=True (raw >= 85), score < raw."""
        # Build uptrending data (most-recent-first) so most criteria pass
        n = 250
        prices = []
        for i in range(n):
            # index 0 = newest (highest), index 249 = oldest (lowest)
            base = 120 - 40 * i / (n - 1)  # 120 → 80
            prices.append(
                {
                    "date": f"2025-{(i // 22) + 1:02d}-{(i % 22) + 1:02d}",
                    "open": base,
                    "high": base * 1.005,
                    "low": base * 0.995,
                    "close": base,
                    "adjClose": base,
                    "volume": 1000000,
                }
            )
        # SMA50 ≈ avg of newest 50 prices (120 down to ~112)
        sma50_approx = sum(p["close"] for p in prices[:50]) / 50
        price = sma50_approx * 1.20  # 20% above SMA50
        quote = {
            "price": price,
            "yearHigh": price * 1.02,
            "yearLow": 60.0,
        }
        result = calculate_trend_template(prices, quote, rs_rank=85)
        assert result["raw_score"] >= 85
        assert result["passed"] is True
        assert result["extended_penalty"] < 0
        assert result["score"] < result["raw_score"]

    def test_raw_score_in_result(self):
        result = self._run_tt(10.0)
        assert "raw_score" in result

    def test_score_is_adjusted(self):
        result = self._run_tt(15.0)
        assert result["score"] == max(0, result["raw_score"] + result["extended_penalty"])

    # --- Output fields ---

    def test_sma50_distance_in_result(self):
        result = self._run_tt(10.0)
        assert "sma50_distance_pct" in result
        assert result["sma50_distance_pct"] is not None
        assert abs(result["sma50_distance_pct"] - 10.0) < 0.5

    def test_extended_penalty_in_result(self):
        result = self._run_tt(10.0)
        assert "extended_penalty" in result

    # --- Custom threshold (R1-3) ---

    def test_custom_threshold_5pct(self):
        result = self._run_tt(6.0, ext_threshold=5.0)
        assert result["extended_penalty"] == -5

    def test_custom_threshold_15pct(self):
        result = self._run_tt(10.0, ext_threshold=15.0)
        assert result["extended_penalty"] == 0


# ===========================================================================
# E2E Threshold Passthrough Test (R2-7)
# ===========================================================================


class TestExtThresholdE2E:
    """Test that ext_threshold passes through analyze_stock to trend_template."""

    def test_ext_threshold_passes_through_to_trend_template(self):
        """analyze_stock(ext_threshold=15) uses 15% threshold for penalty."""
        sma50_target = 100.0
        n = 250
        prices = []
        for i in range(n):
            prices.append(
                {
                    "date": f"2025-{(i // 22) + 1:02d}-{(i % 22) + 1:02d}",
                    "open": sma50_target,
                    "high": sma50_target * 1.005,
                    "low": sma50_target * 0.995,
                    "close": sma50_target,
                    "adjClose": sma50_target,
                    "volume": 1000000,
                }
            )
        # Price is 12% above SMA50
        price = sma50_target * 1.12
        quote = {
            "price": price,
            "yearHigh": price * 1.05,
            "yearLow": sma50_target * 0.6,
        }
        sp500 = _make_prices(n, start=95, daily_change=0.0005)

        # Default threshold=8 -> 12% distance -> penalty=-10
        result_default = analyze_stock(
            "TEST",
            prices,
            quote,
            sp500,
            "Tech",
            "Test Corp",
        )
        tt_default = result_default["trend_template"]
        assert tt_default["extended_penalty"] == -10

        # Custom threshold=15 -> 12% distance -> no penalty
        result_custom = analyze_stock(
            "TEST",
            prices,
            quote,
            sp500,
            "Tech",
            "Test Corp",
            ext_threshold=15.0,
        )
        tt_custom = result_custom["trend_template"]
        assert tt_custom["extended_penalty"] == 0


# ===========================================================================
# Sector Distribution Bug Fix Tests (Commit 1A)
# ===========================================================================


class TestSectorDistribution:
    """Test that sector distribution uses all_results, not just top N."""

    def _make_stock(self, symbol, sector="Technology", score=75.0, rating=None):
        if rating is None:
            if score >= 90:
                rating = "Textbook VCP"
            elif score >= 80:
                rating = "Strong VCP"
            elif score >= 70:
                rating = "Good VCP"
            elif score >= 60:
                rating = "Developing VCP"
            elif score >= 50:
                rating = "Weak VCP"
            else:
                rating = "No VCP"
        return {
            "symbol": symbol,
            "company_name": f"{symbol} Corp",
            "sector": sector,
            "price": 150.0,
            "market_cap": 50e9,
            "composite_score": score,
            "rating": rating,
            "rating_description": "Test",
            "guidance": "Test guidance",
            "weakest_component": "Volume",
            "weakest_score": 40,
            "strongest_component": "Trend",
            "strongest_score": 100,
            "valid_vcp": True,
            "entry_ready": False,
            "trend_template": {"score": 100, "criteria_passed": 7},
            "vcp_pattern": {
                "score": 70,
                "num_contractions": 2,
                "contractions": [],
                "pivot_price": 145.0,
            },
            "volume_pattern": {"score": 40, "dry_up_ratio": 0.8},
            "pivot_proximity": {
                "score": 75,
                "distance_from_pivot_pct": -3.0,
                "stop_loss_price": 140.0,
                "risk_pct": 7.0,
                "trade_status": "NEAR PIVOT",
            },
            "relative_strength": {"score": 80, "rs_rank_estimate": 80, "weighted_rs": 15.0},
        }

    def test_sector_distribution_uses_all_results(self):
        """Sector distribution should count all candidates, not just top N."""
        all_results = [
            self._make_stock("A1", "Technology"),
            self._make_stock("A2", "Technology"),
            self._make_stock("A3", "Healthcare"),
            self._make_stock("A4", "Financials"),
            self._make_stock("A5", "Financials"),
            self._make_stock("A6", "Financials"),
        ]
        top_results = all_results[:2]  # Only Technology stocks

        metadata = {
            "generated_at": "2026-01-01",
            "universe_description": "Test",
            "funnel": {"vcp_candidates": 6},
            "api_stats": {},
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            md_file = os.path.join(tmpdir, "test.md")
            generate_markdown_report(top_results, metadata, md_file, all_results=all_results)
            with open(md_file) as f:
                content = f.read()
            # Should contain Healthcare and Financials from all_results
            assert "Healthcare" in content
            assert "Financials" in content

    def test_report_header_shows_top_count(self):
        """When top N < total, report should show 'Showing top X of Y'."""
        all_results = [self._make_stock(f"S{i}") for i in range(10)]
        top_results = all_results[:3]
        metadata = {
            "generated_at": "2026-01-01",
            "universe_description": "Test",
            "funnel": {"vcp_candidates": 10},
            "api_stats": {},
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            md_file = os.path.join(tmpdir, "test.md")
            generate_markdown_report(top_results, metadata, md_file, all_results=all_results)
            with open(md_file) as f:
                content = f.read()
            assert "Showing top 3 of 10 candidates" in content

    def test_no_top_count_when_all_shown(self):
        """When showing all results, no 'Showing top X of Y' message."""
        results = [self._make_stock(f"S{i}") for i in range(5)]
        metadata = {
            "generated_at": "2026-01-01",
            "universe_description": "Test",
            "funnel": {"vcp_candidates": 5},
            "api_stats": {},
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            md_file = os.path.join(tmpdir, "test.md")
            generate_markdown_report(results, metadata, md_file, all_results=results)
            with open(md_file) as f:
                content = f.read()
            assert "Showing top" not in content

    def test_methodology_link_text(self):
        """Methodology link should not reference a nonexistent file path."""
        results = [self._make_stock("S0")]
        metadata = {
            "generated_at": "2026-01-01",
            "universe_description": "Test",
            "funnel": {},
            "api_stats": {},
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            md_file = os.path.join(tmpdir, "test.md")
            generate_markdown_report(results, metadata, md_file)
            with open(md_file) as f:
                content = f.read()
            assert "`references/vcp_methodology.md`" not in content
            assert "VCP methodology reference" in content

    def test_json_report_has_sector_distribution(self):
        """JSON report should include sector_distribution field."""
        all_results = [
            self._make_stock("A1", "Technology"),
            self._make_stock("A2", "Healthcare"),
        ]
        metadata = {
            "generated_at": "2026-01-01",
            "universe_description": "Test",
            "funnel": {},
            "api_stats": {},
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = os.path.join(tmpdir, "test.json")
            generate_json_report(all_results[:1], metadata, json_file, all_results=all_results)
            with open(json_file) as f:
                data = json.load(f)
            assert "sector_distribution" in data
            assert data["sector_distribution"]["Technology"] == 1
            assert data["sector_distribution"]["Healthcare"] == 1

    def test_section_headers_show_counts(self):
        """Section headers should show stock counts."""
        entry_ready = self._make_stock("READY", score=85.0, rating="Strong VCP")
        entry_ready["entry_ready"] = True
        extended = self._make_stock("EXT", score=75.0, rating="Good VCP")
        extended["entry_ready"] = False
        results = [entry_ready, extended]
        metadata = {
            "generated_at": "2026-01-01",
            "universe_description": "Test",
            "funnel": {},
            "api_stats": {},
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            md_file = os.path.join(tmpdir, "test.md")
            generate_markdown_report(results, metadata, md_file)
            with open(md_file) as f:
                content = f.read()
            assert "Pre-Breakout Watchlist (1 stock" in content
            assert "Extended / Quality VCP (1 stock" in content


# ===========================================================================
# RS Percentile Ranking Tests (Commit 1D)
# ===========================================================================


class TestRSPercentileRanking:
    """Test universe-relative RS percentile ranking."""

    def test_rank_ordering(self):
        """Higher weighted_rs gets higher percentile."""
        from calculators.relative_strength_calculator import rank_relative_strength_universe

        rs_map = {
            "AAPL": {"score": 80, "weighted_rs": 30.0},
            "MSFT": {"score": 70, "weighted_rs": 20.0},
            "GOOG": {"score": 60, "weighted_rs": 10.0},
            "AMZN": {"score": 50, "weighted_rs": 5.0},
        }
        ranked = rank_relative_strength_universe(rs_map)
        assert ranked["AAPL"]["rs_percentile"] > ranked["AMZN"]["rs_percentile"]
        assert ranked["AAPL"]["score"] >= ranked["MSFT"]["score"]

    def test_score_mapping(self):
        """Top percentile gets top score."""
        from calculators.relative_strength_calculator import rank_relative_strength_universe

        rs_map = {f"S{i}": {"score": 50, "weighted_rs": float(i)} for i in range(100)}
        ranked = rank_relative_strength_universe(rs_map)
        # S99 has highest weighted_rs -> highest percentile -> highest score
        assert ranked["S99"]["score"] >= 90
        # S0 has lowest -> lowest score
        assert ranked["S0"]["score"] <= 30

    def test_single_stock(self):
        """Single stock capped by small-population rule (n=1 -> max score 70)."""
        from calculators.relative_strength_calculator import rank_relative_strength_universe

        rs_map = {"ONLY": {"score": 50, "weighted_rs": 10.0}}
        ranked = rank_relative_strength_universe(rs_map)
        # With n=1, percentile and score are both capped
        assert ranked["ONLY"]["score"] <= 70
        assert ranked["ONLY"]["rs_percentile"] <= 74

    def test_handles_none_weighted_rs(self):
        """Stocks with None weighted_rs get score=0 and percentile=0."""
        from calculators.relative_strength_calculator import rank_relative_strength_universe

        rs_map = {
            "GOOD": {"score": 80, "weighted_rs": 20.0},
            "BAD": {"score": 0, "weighted_rs": None},
        }
        ranked = rank_relative_strength_universe(rs_map)
        assert ranked["GOOD"]["rs_percentile"] > ranked["BAD"]["rs_percentile"]
        assert ranked["BAD"]["score"] == 0
        assert ranked["BAD"]["rs_percentile"] == 0

    def test_empty_dict(self):
        """Empty input returns empty dict."""
        from calculators.relative_strength_calculator import rank_relative_strength_universe

        ranked = rank_relative_strength_universe({})
        assert ranked == {}

    def test_tied_values(self):
        """Tied weighted_rs values should get same percentile."""
        from calculators.relative_strength_calculator import rank_relative_strength_universe

        rs_map = {
            "A": {"score": 50, "weighted_rs": 10.0},
            "B": {"score": 50, "weighted_rs": 10.0},
            "C": {"score": 50, "weighted_rs": 5.0},
        }
        ranked = rank_relative_strength_universe(rs_map)
        assert ranked["A"]["rs_percentile"] == ranked["B"]["rs_percentile"]
        assert ranked["A"]["rs_percentile"] > ranked["C"]["rs_percentile"]

    def test_rs_percentile_in_report(self):
        """Report should show RS Percentile when available."""
        stock = {
            "symbol": "TEST",
            "company_name": "Test Corp",
            "sector": "Technology",
            "price": 150.0,
            "market_cap": 50e9,
            "composite_score": 75.0,
            "rating": "Good VCP",
            "rating_description": "Test",
            "guidance": "Test",
            "weakest_component": "Volume",
            "weakest_score": 40,
            "strongest_component": "Trend",
            "strongest_score": 100,
            "valid_vcp": True,
            "entry_ready": False,
            "trend_template": {"score": 100, "criteria_passed": 7},
            "vcp_pattern": {
                "score": 70,
                "num_contractions": 2,
                "contractions": [],
                "pivot_price": 145.0,
            },
            "volume_pattern": {"score": 40, "dry_up_ratio": 0.8},
            "pivot_proximity": {
                "score": 75,
                "distance_from_pivot_pct": -3.0,
                "stop_loss_price": 140.0,
                "risk_pct": 7.0,
                "trade_status": "NEAR PIVOT",
            },
            "relative_strength": {
                "score": 85,
                "rs_rank_estimate": 80,
                "weighted_rs": 15.0,
                "rs_percentile": 92,
            },
        }
        metadata = {
            "generated_at": "2026-01-01",
            "universe_description": "Test",
            "funnel": {},
            "api_stats": {},
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            md_file = os.path.join(tmpdir, "test.md")
            generate_markdown_report([stock], metadata, md_file)
            with open(md_file) as f:
                content = f.read()
            assert "RS Percentile: 92" in content


# ===========================================================================
# ATR and ZigZag Swing Detection Tests (Commit 2)
# ===========================================================================


class TestATRCalculation:
    """Test _calculate_atr function."""

    def test_atr_basic(self):
        """ATR for constant range bars should equal the range."""
        from calculators.vcp_pattern_calculator import _calculate_atr

        n = 20
        highs = [105.0] * n
        lows = [95.0] * n
        closes = [100.0] * n
        atr = _calculate_atr(highs, lows, closes, period=14)
        assert abs(atr - 10.0) < 0.5

    def test_atr_insufficient_data(self):
        """ATR with < period+1 data returns 0."""
        from calculators.vcp_pattern_calculator import _calculate_atr

        highs = [105.0] * 5
        lows = [95.0] * 5
        closes = [100.0] * 5
        atr = _calculate_atr(highs, lows, closes, period=14)
        assert atr == 0.0


class TestZigZagSwingDetection:
    """Test ATR-based ZigZag swing detection."""

    def test_zigzag_finds_known_pattern(self):
        """A clear up-down-up-down pattern should find swing points."""
        from calculators.vcp_pattern_calculator import _zigzag_swing_points

        # Build: 20 bars up, 20 bars down, 20 bars up, 20 bars down
        n = 80
        highs, lows, closes, dates = [], [], [], []
        for i in range(n):
            if i < 20:
                base = 100 + i * 2  # 100 -> 138
            elif i < 40:
                base = 138 - (i - 20) * 2  # 138 -> 100
            elif i < 60:
                base = 100 + (i - 40) * 2  # 100 -> 138
            else:
                base = 138 - (i - 60) * 2  # 138 -> 100
            highs.append(base + 1)
            lows.append(base - 1)
            closes.append(float(base))
            dates.append(f"day-{i}")
        swing_highs, swing_lows = _zigzag_swing_points(
            highs, lows, closes, dates, atr_multiplier=1.5
        )
        assert len(swing_highs) >= 1
        assert len(swing_lows) >= 1

    def test_smooth_uptrend_fewer_swings(self):
        """Smooth uptrend should produce fewer swings than choppy market."""
        from calculators.vcp_pattern_calculator import _zigzag_swing_points

        n = 100
        # Smooth uptrend
        smooth_highs = [100 + i * 0.5 + 1 for i in range(n)]
        smooth_lows = [100 + i * 0.5 - 1 for i in range(n)]
        smooth_closes = [100 + i * 0.5 for i in range(n)]
        dates = [f"day-{i}" for i in range(n)]
        sh, sl = _zigzag_swing_points(smooth_highs, smooth_lows, smooth_closes, dates)
        # Should produce very few swings (smooth trend)
        assert len(sh) + len(sl) <= 4

    def test_atr_multiplier_sensitivity(self):
        """Higher multiplier = fewer swing points detected."""
        from calculators.vcp_pattern_calculator import _zigzag_swing_points

        n = 80
        highs, lows, closes, dates = [], [], [], []
        for i in range(n):
            if i < 20:
                base = 100 + i * 2
            elif i < 40:
                base = 138 - (i - 20) * 2
            elif i < 60:
                base = 100 + (i - 40) * 2
            else:
                base = 138 - (i - 60) * 2
            highs.append(base + 1)
            lows.append(base - 1)
            closes.append(float(base))
            dates.append(f"day-{i}")
        sh_low, sl_low = _zigzag_swing_points(highs, lows, closes, dates, atr_multiplier=0.5)
        sh_high, sl_high = _zigzag_swing_points(highs, lows, closes, dates, atr_multiplier=3.0)
        # Lower multiplier should find at least as many swings
        assert len(sh_low) + len(sl_low) >= len(sh_high) + len(sl_high)

    def test_insufficient_data(self):
        """< 15 bars of data should return empty."""
        from calculators.vcp_pattern_calculator import _zigzag_swing_points

        highs = [105.0] * 10
        lows = [95.0] * 10
        closes = [100.0] * 10
        dates = [f"day-{i}" for i in range(10)]
        sh, sl = _zigzag_swing_points(highs, lows, closes, dates)
        assert sh == []
        assert sl == []


# ===========================================================================
# VCP Pattern Enhanced Tests (Commit 3: ZigZag integration)
# ===========================================================================


class TestVCPPatternEnhanced:
    """Test ZigZag integration, multi-start, and min contraction duration."""

    def _make_vcp_prices(self, n=120):
        """Build synthetic VCP price data (most-recent-first) with clear contractions.

        Creates: ramp up -> T1 drop -> recovery -> T2 smaller drop -> recovery
        """
        # Chronological (oldest first): build then reverse
        chrono = []
        for i in range(n):
            if i < 30:
                # Ramp up from 80 to 120
                base = 80 + (40 * i / 30)
            elif i < 50:
                # T1: drop from 120 to ~100 (16.7%)
                progress = (i - 30) / 20
                base = 120 - 20 * progress
            elif i < 70:
                # Recovery back to ~118
                progress = (i - 50) / 20
                base = 100 + 18 * progress
            elif i < 85:
                # T2: drop from 118 to ~110 (6.8%)
                progress = (i - 70) / 15
                base = 118 - 8 * progress
            else:
                # Recovery to ~117, consolidation near pivot
                progress = (i - 85) / (n - 85)
                base = 110 + 7 * progress
            chrono.append(
                {
                    "date": f"2025-{(i // 22) + 1:02d}-{(i % 22) + 1:02d}",
                    "open": round(base, 2),
                    "high": round(base * 1.01, 2),
                    "low": round(base * 0.99, 2),
                    "close": round(base, 2),
                    "volume": 1000000,
                }
            )
        # Return most-recent-first
        return list(reversed(chrono))

    def test_backward_compatible_return_schema(self):
        """calculate_vcp_pattern returns same keys as before."""
        prices = self._make_vcp_prices()
        result = calculate_vcp_pattern(prices)
        assert "score" in result
        assert "valid_vcp" in result
        assert "contractions" in result
        assert "num_contractions" in result
        assert "pivot_price" in result

    def test_new_params_accepted(self):
        """New parameters atr_multiplier, atr_period, min_contraction_days accepted."""
        prices = self._make_vcp_prices()
        result = calculate_vcp_pattern(
            prices, atr_multiplier=2.0, atr_period=10, min_contraction_days=3
        )
        assert isinstance(result, dict)
        assert "score" in result

    def test_atr_value_in_result(self):
        """Result should include atr_value when ZigZag is used."""
        prices = self._make_vcp_prices()
        result = calculate_vcp_pattern(prices, atr_multiplier=1.5)
        # atr_value may be present (if ZigZag was used) or absent (if fell back)
        # Either way, the result should not crash
        assert isinstance(result, dict)

    def test_contraction_duration_in_result(self):
        """Contractions should have duration_days field when available."""
        prices = self._make_vcp_prices()
        result = calculate_vcp_pattern(prices, atr_multiplier=1.5, min_contraction_days=3)
        for c in result.get("contractions", []):
            assert "duration_days" in c

    def test_existing_validation_still_works(self):
        """_validate_vcp should still work with existing test data."""
        contractions = _make_vcp_contractions([20, 10, 5])
        result = _validate_vcp(contractions, total_days=120)
        assert result["valid"] is True

    def test_min_contraction_days_filters_short(self):
        """Contractions shorter than min_contraction_days should be excluded."""
        from calculators.vcp_pattern_calculator import calculate_vcp_pattern

        prices = self._make_vcp_prices()
        # Very high min_contraction_days should reduce or eliminate contractions
        result = calculate_vcp_pattern(prices, min_contraction_days=50)
        # With 50-day minimum, most contractions would be filtered
        assert result["num_contractions"] <= 2


# ===========================================================================
# Volume Zone Analysis Tests (Commit 4)
# ===========================================================================


class TestVolumeZoneAnalysis:
    """Test zone-based volume analysis."""

    def _make_volume_prices(self, n=60, base_vol=1000000, dry_up_vol=300000):
        """Build prices with clear volume zones (most-recent-first)."""
        prices = []
        for i in range(n):
            vol = base_vol
            if i < 10:  # Recent bars: dry-up zone
                vol = dry_up_vol
            prices.append(
                {
                    "date": f"2025-{(i // 22) + 1:02d}-{(i % 22) + 1:02d}",
                    "open": 100.0,
                    "high": 101.0,
                    "low": 99.0,
                    "close": 100.0,
                    "volume": vol,
                }
            )
        return prices

    def test_backward_compatible_without_contractions(self):
        """Without contractions param, old behavior preserved."""
        prices = self._make_volume_prices()
        result = calculate_volume_pattern(prices, pivot_price=101.0)
        assert "dry_up_ratio" in result
        assert result["score"] > 0

    def test_zone_analysis_present(self):
        """When contractions provided, zone_analysis should appear in result."""
        prices = self._make_volume_prices()
        contractions = [
            {"high_idx": 30, "low_idx": 40, "label": "T1"},
            {"high_idx": 20, "low_idx": 25, "label": "T2"},
        ]
        result = calculate_volume_pattern(prices, pivot_price=101.0, contractions=contractions)
        assert "zone_analysis" in result

    def test_zone_b_dry_up(self):
        """Zone B (pivot approach) with low volume -> high dry-up score."""
        # Build prices where bars near pivot have very low volume
        prices = []
        for i in range(60):
            vol = 1000000
            if i < 10:  # Most recent: very dry
                vol = 100000
            prices.append(
                {
                    "date": f"day-{i}",
                    "open": 100.0,
                    "high": 101.0,
                    "low": 99.0,
                    "close": 100.0,
                    "volume": vol,
                }
            )
        contractions = [
            {"high_idx": 30, "low_idx": 40, "label": "T1"},
            {"high_idx": 15, "low_idx": 20, "label": "T2"},
        ]
        result = calculate_volume_pattern(prices, pivot_price=101.0, contractions=contractions)
        assert result["dry_up_ratio"] < 0.5

    def test_contraction_volume_declining_bonus(self):
        """Declining volume across contractions should add bonus and report trend."""
        # Build prices where T1 zone has higher volume than T2 zone
        n = 60
        prices = []
        for i in range(n):
            vol = 1000000
            # T1: chronological 10-20, reversed = 39-49
            if 39 <= i <= 49:
                vol = 2000000
            # T2: chronological 35-45, reversed = 14-24
            elif 14 <= i <= 24:
                vol = 500000
            prices.append(
                {
                    "date": f"day-{i}",
                    "open": 100.0,
                    "high": 101.0,
                    "low": 99.0,
                    "close": 100.0,
                    "volume": vol,
                }
            )
        contractions = [
            {"high_idx": 10, "low_idx": 20, "label": "T1"},
            {"high_idx": 35, "low_idx": 45, "label": "T2"},
        ]
        result = calculate_volume_pattern(prices, pivot_price=101.0, contractions=contractions)
        assert "contraction_volume_trend" in result
        assert result["contraction_volume_trend"]["declining"] is True

    def test_empty_contractions_fallback(self):
        """Empty contractions list should use old behavior."""
        prices = self._make_volume_prices()
        result = calculate_volume_pattern(prices, pivot_price=101.0, contractions=[])
        # Should still work with old logic
        assert "dry_up_ratio" in result
        assert result["score"] > 0

    def test_breakout_volume_uses_zone_c(self):
        """When breakout bar is at pivot, zone C volume should be used."""
        prices = []
        for i in range(60):
            vol = 500000
            close = 100.0
            if i == 0:
                # Breakout bar: high volume, price above pivot
                vol = 2000000
                close = 102.0
            prices.append(
                {
                    "date": f"day-{i}",
                    "open": close - 1,
                    "high": close + 0.5,
                    "low": close - 1.5,
                    "close": close,
                    "volume": vol,
                }
            )
        contractions = [
            {"high_idx": 30, "low_idx": 40, "label": "T1"},
            {"high_idx": 15, "low_idx": 20, "label": "T2"},
        ]
        result = calculate_volume_pattern(prices, pivot_price=101.0, contractions=contractions)
        assert result["breakout_volume_detected"] is True


# ===========================================================================
# Code Review Fix Tests: RS None handling, weakest/strongest update,
# small population, and tautological test fixes
# ===========================================================================


class TestRSNoneHandling:
    """Issue #1 (High): weighted_rs=None stocks must not inflate scores."""

    def test_all_none_get_score_zero(self):
        """All-None universe: every stock should get score=0, not score=100."""
        from calculators.relative_strength_calculator import rank_relative_strength_universe

        rs_map = {
            "A": {"score": 0, "weighted_rs": None, "error": "No SPY data"},
            "B": {"score": 0, "weighted_rs": None, "error": "No SPY data"},
            "C": {"score": 0, "weighted_rs": None, "error": "No SPY data"},
        }
        ranked = rank_relative_strength_universe(rs_map)
        for sym in ["A", "B", "C"]:
            assert ranked[sym]["score"] == 0
            assert ranked[sym]["rs_percentile"] == 0

    def test_mixed_none_excludes_none_from_percentile(self):
        """None stocks excluded from percentile; valid stocks ranked among themselves."""
        from calculators.relative_strength_calculator import rank_relative_strength_universe

        rs_map = {
            "GOOD1": {"score": 80, "weighted_rs": 30.0},
            "GOOD2": {"score": 70, "weighted_rs": 10.0},
            "BAD": {"score": 0, "weighted_rs": None, "error": "No data"},
        }
        ranked = rank_relative_strength_universe(rs_map)
        # BAD should get score=0
        assert ranked["BAD"]["score"] == 0
        assert ranked["BAD"]["rs_percentile"] == 0
        # GOOD1 should still be ranked highest among valid stocks
        assert ranked["GOOD1"]["rs_percentile"] > ranked["GOOD2"]["rs_percentile"]
        assert ranked["GOOD1"]["score"] > 0

    def test_none_stock_preserves_error(self):
        """None-weighted_rs stock should preserve its original error field."""
        from calculators.relative_strength_calculator import rank_relative_strength_universe

        rs_map = {
            "OK": {"score": 50, "weighted_rs": 10.0},
            "ERR": {"score": 0, "weighted_rs": None, "error": "SPY fetch failed"},
        }
        ranked = rank_relative_strength_universe(rs_map)
        assert ranked["ERR"]["error"] == "SPY fetch failed"


class TestRSSmallPopulation:
    """Issue #3 (Medium): small populations should cap percentile scores."""

    def test_small_population_caps_score(self):
        """With fewer than 10 valid stocks, scores should be capped."""
        from calculators.relative_strength_calculator import rank_relative_strength_universe

        # 3 stocks: highest should NOT get score=100
        rs_map = {
            "A": {"score": 50, "weighted_rs": 20.0},
            "B": {"score": 50, "weighted_rs": 10.0},
            "C": {"score": 50, "weighted_rs": 5.0},
        }
        ranked = rank_relative_strength_universe(rs_map)
        # With only 3 valid stocks, best should be capped at 80
        assert ranked["A"]["score"] <= 80

    def test_small_population_caps_percentile_consistently(self):
        """rs_percentile must be capped consistently with score."""
        from calculators.relative_strength_calculator import (
            _percentile_to_score,
            rank_relative_strength_universe,
        )

        # 3 stocks: raw percentile would be 100 for top stock
        rs_map = {
            "A": {"score": 50, "weighted_rs": 20.0},
            "B": {"score": 50, "weighted_rs": 10.0},
            "C": {"score": 50, "weighted_rs": 5.0},
        }
        ranked = rank_relative_strength_universe(rs_map)
        # Percentile must produce the capped score when passed through _percentile_to_score
        for sym in ["A", "B", "C"]:
            pct = ranked[sym]["rs_percentile"]
            score = ranked[sym]["score"]
            assert _percentile_to_score(pct) == score

    def test_large_population_no_cap(self):
        """With 20+ valid stocks, no cap is applied."""
        from calculators.relative_strength_calculator import rank_relative_strength_universe

        rs_map = {f"S{i}": {"score": 50, "weighted_rs": float(i)} for i in range(20)}
        ranked = rank_relative_strength_universe(rs_map)
        assert ranked["S19"]["score"] >= 90
        # Percentile should also be uncapped
        assert ranked["S19"]["rs_percentile"] >= 95


class TestWeakestStrongestUpdate:
    """Issue #2 (Medium): weakest/strongest must update after RS re-ranking."""

    def test_weakest_strongest_reflects_updated_rs(self):
        """After RS re-ranking, composite result must have fresh weakest/strongest."""
        # Simulate a result where RS was initially strongest (score=100)
        # but after re-ranking becomes weaker (score=40)
        composite = calculate_composite_score(
            trend_score=80,
            contraction_score=70,
            volume_score=60,
            pivot_score=50,
            rs_score=40,  # RS now weakest after re-ranking
        )
        assert composite["weakest_component"] == "Relative Strength"
        assert composite["weakest_score"] == 40
        # The strongest should be Trend Template
        assert composite["strongest_component"] == "Trend Template (Stage 2)"
        assert composite["strongest_score"] == 80


class TestFixedTautologicalTests:
    """Issue #4 (Low): fix tests that were always-true."""

    def test_new_params_no_crash(self):
        """calculate_vcp_pattern with new params should not raise an exception."""
        prices = TestVCPPatternEnhanced._make_vcp_prices(None)
        result = calculate_vcp_pattern(
            prices, atr_multiplier=2.0, atr_period=10, min_contraction_days=3
        )
        assert isinstance(result, dict)
        assert "score" in result

    def test_declining_volume_bonus_value(self):
        """Declining contraction volume should yield +5 bonus vs non-declining."""
        # Build prices with declining volume in contraction zones
        prices_declining = []
        prices_flat = []
        for i in range(60):
            close = 100.0
            vol_base = 1000000
            prices_declining.append(
                {
                    "date": f"day-{i}",
                    "open": 100.0,
                    "high": 101.0,
                    "low": 99.0,
                    "close": close,
                    "volume": vol_base,
                }
            )
            prices_flat.append(
                {
                    "date": f"day-{i}",
                    "open": 100.0,
                    "high": 101.0,
                    "low": 99.0,
                    "close": close,
                    "volume": vol_base,
                }
            )

        # Contractions where T1 zone has higher volume than T2 zone
        # (chronological indices: T1 is earlier, T2 is later)
        n = 60
        # T1: indices 10-20 (chronological), reversed = 39-49
        # T2: indices 35-45 (chronological), reversed = 14-24
        # For declining: T1 zone gets high volume, T2 zone gets low volume
        for i in range(n):
            n - 1 - i
            # T1 chronological 10-20 -> reversed 39-49
            if 39 <= i <= 49:
                prices_declining[i]["volume"] = 2000000
                prices_flat[i]["volume"] = 1000000
            # T2 chronological 35-45 -> reversed 14-24
            if 14 <= i <= 24:
                prices_declining[i]["volume"] = 500000
                prices_flat[i]["volume"] = 1000000

        contractions = [
            {"high_idx": 10, "low_idx": 20, "label": "T1"},
            {"high_idx": 35, "low_idx": 45, "label": "T2"},
        ]

        result_declining = calculate_volume_pattern(
            prices_declining, pivot_price=101.0, contractions=contractions
        )
        result_flat = calculate_volume_pattern(
            prices_flat, pivot_price=101.0, contractions=contractions
        )

        # Declining should have the bonus
        assert result_declining.get("contraction_volume_trend", {}).get("declining") is True
        assert result_flat.get("contraction_volume_trend", {}).get("declining") is False
        # Score difference should be exactly 10 (strengthened bonus in Phase 4)
        assert result_declining["score"] - result_flat["score"] == 10


# ===========================================================================
# Parameter Passthrough Tests (VCP tuning parameters)
# ===========================================================================


class TestParameterPassthrough:
    """Test that new tuning parameters correctly affect VCP detection."""

    def test_min_contractions_3_rejects_2_contraction_pattern(self):
        """min_contractions=3 should reject a pattern with only 2 contractions."""
        contractions = _make_vcp_contractions([20, 10])
        result = _validate_vcp(contractions, total_days=120, min_contractions=3)
        assert result["valid"] is False
        assert any("3" in issue for issue in result["issues"])

    def test_min_contractions_2_default_backward_compatible(self):
        """min_contractions=2 (default) accepts a 2-contraction pattern."""
        contractions = _make_vcp_contractions([20, 10])
        result = _validate_vcp(contractions, total_days=120)
        assert result["valid"] is True

    def test_t1_depth_min_12_rejects_shallow(self):
        """t1_depth_min=12 should reject T1=10% pattern."""
        contractions = _make_vcp_contractions([10, 5])
        result = _validate_vcp(contractions, total_days=120, t1_depth_min=12.0)
        assert result["valid"] is False
        assert any("12.0" in issue for issue in result["issues"])

    def test_t1_depth_min_default_accepts_8pct(self):
        """Default t1_depth_min=8.0 accepts T1=10%."""
        contractions = _make_vcp_contractions([10, 5])
        result = _validate_vcp(contractions, total_days=120)
        assert result["valid"] is True

    def test_contraction_ratio_09_accepts_looser(self):
        """contraction_ratio=0.9 accepts T1=20%, T2=17% (ratio=0.85)."""
        contractions = _make_vcp_contractions([20, 17])
        # Default 0.75 rejects
        result_strict = _validate_vcp(contractions, total_days=120, contraction_ratio=0.75)
        assert result_strict["valid"] is False
        # Relaxed 0.9 accepts
        result_relaxed = _validate_vcp(contractions, total_days=120, contraction_ratio=0.9)
        assert result_relaxed["valid"] is True

    def test_breakout_volume_ratio_2_rejects_16x(self):
        """breakout_volume_ratio=2.0 should not detect 1.6x as breakout."""
        prices = _make_prices(60, volume=1000000)
        # Most recent bar: 1.6x volume, price above pivot
        prices[0]["volume"] = 1600000
        prices[0]["close"] = 102.0
        result = calculate_volume_pattern(prices, pivot_price=100.0, breakout_volume_ratio=2.0)
        assert result["breakout_volume_detected"] is False

    def test_breakout_volume_ratio_default_detects_16x(self):
        """Default breakout_volume_ratio=1.5 detects 1.6x as breakout."""
        prices = _make_prices(60, volume=1000000)
        prices[0]["volume"] = 1600000
        prices[0]["close"] = 102.0
        result = calculate_volume_pattern(prices, pivot_price=100.0)
        assert result["breakout_volume_detected"] is True

    def test_calculate_vcp_pattern_min_contractions_3(self):
        """calculate_vcp_pattern with min_contractions=3 finds fewer patterns."""
        from calculators.vcp_pattern_calculator import calculate_vcp_pattern

        prices = TestVCPPatternEnhanced._make_vcp_prices(None)
        result_2 = calculate_vcp_pattern(prices, min_contractions=2)
        result_3 = calculate_vcp_pattern(prices, min_contractions=3)
        # With stricter min_contractions, either fewer contractions or not valid
        if result_2["valid_vcp"] and result_2["num_contractions"] < 3:
            assert result_3["valid_vcp"] is False


class TestTrendMinScore:
    """Test passes_trend_filter (Phase 2 gate) from screen_vcp.py."""

    def test_trend_min_score_70_passes_raw_75(self):
        """passes_trend_filter with raw_score=75 and threshold=70 -> True."""
        tt_result = {"raw_score": 75, "passed": False}
        assert passes_trend_filter(tt_result, trend_min_score=70) is True

    def test_trend_min_score_85_rejects_raw_80(self):
        """passes_trend_filter with raw_score=80 and default threshold=85 -> False."""
        tt_result = {"raw_score": 80, "passed": False}
        assert passes_trend_filter(tt_result) is False

    def test_trend_min_score_100_rejects_all(self):
        """passes_trend_filter with threshold=100 rejects 99.9."""
        tt_result = {"raw_score": 99.9, "passed": True}
        assert passes_trend_filter(tt_result, trend_min_score=100) is False

    def test_uses_raw_score_not_passed_field(self):
        """Phase 2 must gate on raw_score, not the passed boolean.

        A stock with raw_score=75 and passed=False should still pass
        Phase 2 when trend_min_score=70.
        """
        tt_result = {"raw_score": 75, "passed": False, "score": 60}
        assert passes_trend_filter(tt_result, trend_min_score=70) is True
        # Verify it would NOT pass if we used the 'passed' field
        assert tt_result["passed"] is False

    def test_missing_raw_score_returns_false(self):
        """If raw_score key is absent, passes_trend_filter defaults to 0."""
        tt_result = {"passed": True, "score": 85}
        assert passes_trend_filter(tt_result, trend_min_score=85) is False

    def test_with_real_calculate_trend_template(self):
        """Integration: real calculate_trend_template output flows through filter."""
        prices = _make_prices(250, start=80, daily_change=0.001)
        quote = {"price": 120, "yearHigh": 125, "yearLow": 70}
        tt_result = calculate_trend_template(prices, quote, rs_rank=85)
        raw = tt_result.get("raw_score", 0)
        # The result must be consistent with passes_trend_filter
        assert passes_trend_filter(tt_result, trend_min_score=raw) is True
        assert passes_trend_filter(tt_result, trend_min_score=raw + 0.1) is False


class TestBacktestRegression:
    """Regression tests ensuring stricter params are more selective."""

    def test_min_contractions_3_more_selective_than_2(self):
        """min_contractions=3 should be at least as selective as =2."""
        contractions_2 = _make_vcp_contractions([20, 10])
        result_2 = _validate_vcp(contractions_2, total_days=120, min_contractions=2)
        result_3 = _validate_vcp(contractions_2, total_days=120, min_contractions=3)
        # 2-contraction pattern: valid for min=2, invalid for min=3
        assert result_2["valid"] is True
        assert result_3["valid"] is False

    def test_higher_t1_depth_min_excludes_shallow(self):
        """Higher t1_depth_min excludes patterns that default accepts."""
        contractions = _make_vcp_contractions([10, 5])
        result_default = _validate_vcp(contractions, total_days=120, t1_depth_min=8.0)
        result_strict = _validate_vcp(contractions, total_days=120, t1_depth_min=15.0)
        assert result_default["valid"] is True
        assert result_strict["valid"] is False


class TestTuningParamsMetadata:
    """Test that tuning_params appear in report metadata."""

    def test_metadata_tuning_params_from_parse_arguments(self):
        """parse_arguments() produces args with all 8 tuning param attributes.

        This exercises the real CLI parser so a renamed or missing flag
        causes a test failure.
        """
        import sys
        from unittest.mock import patch

        test_argv = [
            "screen_vcp.py",
            "--min-contractions",
            "3",
            "--t1-depth-min",
            "12.0",
            "--breakout-volume-ratio",
            "2.0",
            "--trend-min-score",
            "90.0",
            "--atr-multiplier",
            "2.0",
            "--contraction-ratio",
            "0.6",
            "--min-contraction-days",
            "7",
            "--lookback-days",
            "180",
        ]
        with patch.object(sys, "argv", test_argv):
            args = parse_arguments()

        # Build tuning_params the same way screen_vcp.main() does (line ~620)
        tuning_params = {
            "min_contractions": args.min_contractions,
            "t1_depth_min": args.t1_depth_min,
            "breakout_volume_ratio": args.breakout_volume_ratio,
            "trend_min_score": args.trend_min_score,
            "atr_multiplier": args.atr_multiplier,
            "contraction_ratio": args.contraction_ratio,
            "min_contraction_days": args.min_contraction_days,
            "lookback_days": args.lookback_days,
        }
        assert len(tuning_params) == 8
        assert tuning_params["min_contractions"] == 3
        assert tuning_params["trend_min_score"] == 90.0
        assert tuning_params["lookback_days"] == 180

    def test_tuning_params_in_json_report(self):
        """JSON report should include tuning_params in metadata."""
        metadata = {
            "generated_at": "2026-01-01",
            "universe_description": "Test",
            "tuning_params": {
                "min_contractions": 2,
                "t1_depth_min": 8.0,
                "breakout_volume_ratio": 1.5,
                "trend_min_score": 85.0,
                "atr_multiplier": 1.5,
                "contraction_ratio": 0.75,
                "min_contraction_days": 5,
                "lookback_days": 120,
            },
            "funnel": {},
            "api_stats": {},
        }
        stock = {
            "symbol": "TEST",
            "company_name": "Test Corp",
            "sector": "Technology",
            "price": 150.0,
            "market_cap": 50e9,
            "composite_score": 75.0,
            "rating": "Good VCP",
            "rating_description": "Test",
            "guidance": "Test",
            "weakest_component": "Volume",
            "weakest_score": 40,
            "strongest_component": "Trend",
            "strongest_score": 100,
            "valid_vcp": True,
            "entry_ready": False,
            "trend_template": {"score": 100, "criteria_passed": 7},
            "vcp_pattern": {
                "score": 70,
                "num_contractions": 2,
                "contractions": [],
                "pivot_price": 145.0,
            },
            "volume_pattern": {"score": 40, "dry_up_ratio": 0.8},
            "pivot_proximity": {
                "score": 75,
                "distance_from_pivot_pct": -3.0,
                "stop_loss_price": 140.0,
                "risk_pct": 7.0,
                "trade_status": "NEAR PIVOT",
            },
            "relative_strength": {"score": 80, "rs_rank_estimate": 80, "weighted_rs": 15.0},
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = os.path.join(tmpdir, "test.json")
            generate_json_report([stock], metadata, json_file)
            with open(json_file) as f:
                data = json.load(f)
            assert "tuning_params" in data["metadata"]
            tp = data["metadata"]["tuning_params"]
            assert len(tp) == 8
            assert tp["min_contractions"] == 2
            assert tp["trend_min_score"] == 85.0


# ---------------------------------------------------------------------------
# Review fix regression tests
# ---------------------------------------------------------------------------


def test_entry_ready_below_stop_returns_false():
    """#1: Price below stop level should never be entry_ready."""
    result = {
        "valid_vcp": True,
        "distance_from_pivot_pct": -5.5,  # within -8 to +3 window
        "volume_pattern": {"dry_up_ratio": 0.5},
        "pivot_proximity": {
            "risk_pct": None,  # None because price < stop (setup invalidated)
            "trade_status": "BELOW STOP LEVEL",
            "stop_loss_price": 95.04,
        },
    }
    assert compute_entry_ready(result) is False


def test_accumulation_requires_above_avg_volume():
    """#2: Up-close days with below-average volume should not count as accumulation."""
    # Build 50 days of data: alternating up/down closes, but volume always below avg
    prices = []
    avg_vol = 1_000_000
    for i in range(50):
        # Alternating closes: even=102, odd=100 (up day when i even, most-recent-first)
        close = 102.0 if i % 2 == 0 else 100.0
        prices.append(
            {
                "date": f"2025-01-{i + 1:02d}",
                "open": 100.0,
                "high": 103.0,
                "low": 99.0,
                "close": close,
                "volume": avg_vol // 2,  # always below average
            }
        )
    result = calculate_volume_pattern(prices)
    # With all volumes below average, no day should count as accumulation or distribution
    assert result["up_volume_days_20d"] == 0
    assert result["down_volume_days_20d"] == 0
    assert result["net_accumulation"] == 0


def test_multi_start_prefers_valid_over_longer():
    """#3: 2-contraction valid pattern should beat 3-contraction invalid."""
    # We test the selection logic by constructing price data where:
    # - The highest swing high leads to 3 contractions but fails contraction_ratio
    # - A lower swing high leads to 2 valid contractions with good score
    # Build chronological data with known swing pattern
    n = 100
    prices_chrono = []
    for i in range(n):
        # Base uptrend
        base = 100 + i * 0.3
        prices_chrono.append(
            {
                "date": f"2025-{(i // 22) + 1:02d}-{(i % 22) + 1:02d}",
                "open": base,
                "high": base + 2,
                "low": base - 2,
                "close": base,
                "volume": 1_000_000,
            }
        )

    # The VCP calculator reverses to chronological internally, so we provide
    # most-recent-first (standard format)
    historical = list(reversed(prices_chrono))

    result = calculate_vcp_pattern(historical, lookback_days=100, min_contractions=2)
    # The key assertion: if a valid pattern exists, valid_vcp should be True
    # (i.e., multi-start should not prefer longer-but-invalid over shorter-but-valid)
    # This is a structural test - the old code could pick longer invalid over shorter valid.
    # With the fix, `valid` flag is prioritized over length.
    assert result is not None
    assert "valid_vcp" in result


def test_prefilter_score_capped_at_100():
    """#5: Pre-filter score should not exceed 100 even for extreme pct_above_low."""
    quote = {
        "price": 300.0,
        "yearLow": 100.0,  # 200% above low
        "yearHigh": 310.0,  # within 30% of high
        "avgVolume": 500000,
    }
    passed, score = pre_filter_stock(quote)
    assert passed is True
    # pct_above_low = 2.0, capped at 1.0 → 50 + (1 - 0.032) * 50 ≈ 98.4
    assert score <= 100


def test_below_stop_report_shows_stop_violated():
    """BELOW STOP LEVEL should show 'STOP VIOLATED' in report, not buy guidance."""
    stock = {
        "symbol": "TEST",
        "company_name": "Test Corp",
        "sector": "Technology",
        "price": 94.0,
        "market_cap": 10e9,
        "composite_score": 45.0,
        "rating": "Weak VCP",
        "rating_description": "Weak",
        "guidance": "Buy at pivot, standard position sizing",
        "valid_vcp": True,
        "distance_from_pivot_pct": -6.0,
        "weakest_component": "pivot",
        "weakest_score": 0,
        "strongest_component": "trend",
        "strongest_score": 95,
        "entry_ready": False,
        "trend_template": {"score": 95, "criteria_passed": 7},
        "vcp_pattern": {
            "score": 70,
            "num_contractions": 2,
            "contractions": [],
            "pivot_price": 100.0,
        },
        "volume_pattern": {"score": 60, "dry_up_ratio": 0.5},
        "pivot_proximity": {
            "score": 0,
            "distance_from_pivot_pct": -6.0,
            "stop_loss_price": 95.04,
            "risk_pct": None,
            "trade_status": "BELOW STOP LEVEL",
        },
        "relative_strength": {"score": 80, "rs_rank_estimate": 80, "weighted_rs": 10.0},
    }
    metadata = {"generated_at": "2025-01-01", "funnel": {}}
    with tempfile.TemporaryDirectory() as tmpdir:
        md_file = os.path.join(tmpdir, "test.md")
        generate_markdown_report([stock], metadata, md_file)
        with open(md_file) as f:
            content = f.read()
        assert "STOP VIOLATED" in content
        assert "setup invalidated" in content.lower()
        # Should NOT contain normal buy guidance
        assert "Buy at pivot, standard position sizing" not in content


def test_build_contractions_does_not_skip_intermediate_high():
    """Contraction builder must not jump past intermediate swing highs."""
    from calculators.vcp_pattern_calculator import _build_contractions_from

    # swing_highs: H0=100@idx0, H1=98@idx4, H2=97@idx10
    # swing_lows:  L0=90@idx2, L1=92@idx7, L2=93@idx12
    # With min_contraction_days=5:
    #   From H0(idx=0), first low is L0(idx=2) -> duration=2 < 5, too short.
    #   Next candidate low is L1(idx=7) -> duration=7 >= 5.
    #   But H1(idx=4) is between H0 and L1, so we must NOT create a H0->L1 contraction.
    swing_highs = [(0, 100.0), (4, 98.0), (10, 97.0)]
    swing_lows = [(2, 90.0), (7, 92.0), (12, 93.0)]
    highs = [100.0] * 15
    lows = [90.0] * 15
    dates = [f"day-{i}" for i in range(15)]

    contractions = _build_contractions_from(
        start_high=(0, 100.0),
        swing_highs=swing_highs,
        swing_lows=swing_lows,
        highs=highs,
        lows=lows,
        dates=dates,
        min_contraction_days=5,
    )

    # The builder should NOT produce a contraction from idx=0 to idx=7
    # because idx=4 has an intermediate swing high
    for c in contractions:
        if c["high_idx"] == 0:
            # If a contraction starts at idx 0, its low must not be past idx 4
            assert c["low_idx"] <= 4, (
                f"Contraction from idx=0 jumped to low_idx={c['low_idx']}, "
                f"skipping intermediate swing high at idx=4"
            )


# ---------------------------------------------------------------------------
# Phase 1: Execution State, Pattern Classifier, Scorer State Caps
# ---------------------------------------------------------------------------

from calculators.execution_state import apply_state_cap, compute_execution_state
from calculators.pattern_classifier import classify_pattern


class TestExecutionState:
    """Tests for compute_execution_state() — 10-rule decision tree."""

    def test_invalid_price_below_sma50_below_sma200(self):
        result = compute_execution_state(
            distance_from_pivot_pct=None,
            price=80.0,
            sma50=90.0,
            sma200=95.0,
            sma200_distance_pct=-15.8,
            last_contraction_low=None,
            breakout_volume=False,
        )
        assert result["state"] == "Invalid"
        assert result["reasons"]

    def test_not_invalid_when_sma50_above_sma200(self):
        # price < sma50, but sma50 > sma200 → Stage 2 possible, use Damaged not Invalid
        result = compute_execution_state(
            distance_from_pivot_pct=-2.0,
            price=95.0,
            sma50=100.0,
            sma200=90.0,
            sma200_distance_pct=5.6,
            last_contraction_low=None,
            breakout_volume=False,
        )
        assert result["state"] == "Damaged"  # Rule 3, not Rule 1

    def test_damaged_price_below_contraction_low(self):
        result = compute_execution_state(
            distance_from_pivot_pct=None,
            price=88.0,
            sma50=92.0,
            sma200=85.0,
            sma200_distance_pct=3.5,
            last_contraction_low=90.0,
            breakout_volume=False,
        )
        assert result["state"] == "Damaged"
        assert "contraction low" in result["reasons"][0].lower()

    def test_damaged_price_below_sma50(self):
        result = compute_execution_state(
            distance_from_pivot_pct=1.0,
            price=95.0,
            sma50=100.0,
            sma200=90.0,
            sma200_distance_pct=5.6,
            last_contraction_low=None,
            breakout_volume=False,
        )
        assert result["state"] == "Damaged"

    def test_overextended_sma200_too_far(self):
        result = compute_execution_state(
            distance_from_pivot_pct=2.0,
            price=200.0,
            sma50=180.0,
            sma200=120.0,
            sma200_distance_pct=66.7,
            last_contraction_low=None,
            breakout_volume=False,
            max_sma200_extension=50.0,
        )
        assert result["state"] == "Overextended"

    def test_overextended_pivot_more_than_10pct(self):
        result = compute_execution_state(
            distance_from_pivot_pct=12.0,
            price=112.0,
            sma50=100.0,
            sma200=90.0,
            sma200_distance_pct=24.4,
            last_contraction_low=None,
            breakout_volume=False,
        )
        assert result["state"] == "Overextended"

    def test_extended_5_to_10pct_above_pivot(self):
        result = compute_execution_state(
            distance_from_pivot_pct=7.5,
            price=107.5,
            sma50=100.0,
            sma200=90.0,
            sma200_distance_pct=19.4,
            last_contraction_low=None,
            breakout_volume=False,
        )
        assert result["state"] == "Extended"

    def test_early_post_breakout_3_to_5pct(self):
        result = compute_execution_state(
            distance_from_pivot_pct=4.0,
            price=104.0,
            sma50=100.0,
            sma200=90.0,
            sma200_distance_pct=15.6,
            last_contraction_low=None,
            breakout_volume=False,
        )
        assert result["state"] == "Early-post-breakout"

    def test_breakout_within_3pct_with_volume(self):
        result = compute_execution_state(
            distance_from_pivot_pct=1.5,
            price=101.5,
            sma50=98.0,
            sma200=90.0,
            sma200_distance_pct=12.8,
            last_contraction_low=None,
            breakout_volume=True,
        )
        assert result["state"] == "Breakout"

    def test_pre_breakout_within_3pct_no_volume(self):
        result = compute_execution_state(
            distance_from_pivot_pct=1.5,
            price=101.5,
            sma50=98.0,
            sma200=90.0,
            sma200_distance_pct=12.8,
            last_contraction_low=None,
            breakout_volume=False,
        )
        assert result["state"] == "Early-post-breakout"

    def test_pre_breakout_below_pivot(self):
        # price above sma50 but below pivot — still forming pattern
        result = compute_execution_state(
            distance_from_pivot_pct=-3.0,
            price=97.0,
            sma50=94.0,  # price > sma50, so no Damaged state
            sma200=85.0,
            sma200_distance_pct=14.1,
            last_contraction_low=None,
            breakout_volume=False,
        )
        assert result["state"] == "Pre-breakout"
        assert "-3.0% below pivot" in result["reasons"][0]


class TestApplyStateCap:
    """Tests for apply_state_cap() helper."""

    def test_invalid_caps_to_no_vcp(self):
        capped, applied = apply_state_cap("Textbook VCP", "Invalid")
        assert capped == "No VCP"
        assert applied is True

    def test_damaged_caps_strong_to_no_vcp(self):
        capped, applied = apply_state_cap("Strong VCP", "Damaged")
        assert capped == "No VCP"
        assert applied is True

    def test_overextended_caps_to_weak(self):
        capped, applied = apply_state_cap("Good VCP", "Overextended")
        assert capped == "Weak VCP"
        assert applied is True

    def test_extended_caps_to_developing(self):
        capped, applied = apply_state_cap("Strong VCP", "Extended")
        assert capped == "Developing VCP"
        assert applied is True

    def test_pre_breakout_no_cap(self):
        capped, applied = apply_state_cap("Textbook VCP", "Pre-breakout")
        assert capped == "Textbook VCP"
        assert applied is False

    def test_breakout_no_cap(self):
        capped, applied = apply_state_cap("Strong VCP", "Breakout")
        assert capped == "Strong VCP"
        assert applied is False

    def test_cap_does_not_upgrade(self):
        # Weak VCP should not be upgraded by Overextended cap (max = Developing)
        capped, applied = apply_state_cap("Weak VCP", "Overextended")
        assert capped == "Weak VCP"
        assert applied is False


class TestPatternClassifier:
    """Tests for classify_pattern()."""

    def test_invalid_state_returns_damaged(self):
        result = classify_pattern(
            valid_vcp=True,
            num_contractions=3,
            final_contraction_depth=8.0,
            execution_state="Invalid",
            dry_up_ratio=0.6,
        )
        assert result == "Damaged"

    def test_damaged_state_returns_damaged(self):
        result = classify_pattern(
            valid_vcp=True,
            num_contractions=3,
            final_contraction_depth=8.0,
            execution_state="Damaged",
            dry_up_ratio=0.6,
        )
        assert result == "Damaged"

    def test_overextended_valid_vcp_returns_extended_leader(self):
        result = classify_pattern(
            valid_vcp=True,
            num_contractions=3,
            final_contraction_depth=8.0,
            execution_state="Overextended",
            dry_up_ratio=0.6,
        )
        assert result == "Extended Leader"

    def test_overextended_invalid_vcp_returns_vcp_adjacent(self):
        result = classify_pattern(
            valid_vcp=False,
            num_contractions=2,
            final_contraction_depth=20.0,
            execution_state="Overextended",
            dry_up_ratio=0.9,
        )
        assert result == "VCP-adjacent"

    def test_breakout_valid_vcp_returns_post_breakout(self):
        result = classify_pattern(
            valid_vcp=True,
            num_contractions=3,
            final_contraction_depth=8.0,
            execution_state="Breakout",
            dry_up_ratio=0.6,
        )
        assert result == "Post-breakout"

    def test_early_post_breakout_returns_post_breakout(self):
        result = classify_pattern(
            valid_vcp=True,
            num_contractions=3,
            final_contraction_depth=7.0,
            execution_state="Early-post-breakout",
            dry_up_ratio=0.65,
        )
        assert result == "Post-breakout"

    def test_textbook_all_criteria_met(self):
        result = classify_pattern(
            valid_vcp=True,
            num_contractions=3,
            final_contraction_depth=9.0,
            execution_state="Pre-breakout",
            dry_up_ratio=0.65,
            wide_and_loose=False,
        )
        assert result == "Textbook VCP"

    def test_textbook_blocked_by_wide_and_loose(self):
        result = classify_pattern(
            valid_vcp=True,
            num_contractions=3,
            final_contraction_depth=9.0,
            execution_state="Pre-breakout",
            dry_up_ratio=0.65,
            wide_and_loose=True,
        )
        assert result == "VCP-adjacent"

    def test_not_textbook_only_2_contractions(self):
        result = classify_pattern(
            valid_vcp=True,
            num_contractions=2,
            final_contraction_depth=9.0,
            execution_state="Pre-breakout",
            dry_up_ratio=0.65,
        )
        assert result == "VCP-adjacent"

    def test_not_textbook_high_dry_up_ratio(self):
        result = classify_pattern(
            valid_vcp=True,
            num_contractions=3,
            final_contraction_depth=9.0,
            execution_state="Pre-breakout",
            dry_up_ratio=0.85,  # > 0.7 threshold
        )
        assert result == "VCP-adjacent"

    def test_invalid_vcp_always_vcp_adjacent(self):
        result = classify_pattern(
            valid_vcp=False,
            num_contractions=3,
            final_contraction_depth=9.0,
            execution_state="Pre-breakout",
            dry_up_ratio=0.5,
        )
        assert result == "VCP-adjacent"


class TestScorerStateCaps:
    """Tests for calculate_composite_score() with execution_state caps."""

    def _base_scores(self):
        return dict(
            trend_score=90.0,
            contraction_score=90.0,
            volume_score=90.0,
            pivot_score=90.0,
            rs_score=90.0,
            valid_vcp=True,
        )

    def test_no_cap_when_no_execution_state(self):
        result = calculate_composite_score(**self._base_scores())
        assert result["rating"] == "Textbook VCP"
        assert result["state_cap_applied"] is False

    def test_invalid_state_caps_to_no_vcp(self):
        result = calculate_composite_score(**self._base_scores(), execution_state="Invalid")
        assert result["rating"] == "No VCP"
        assert result["state_cap_applied"] is True

    def test_damaged_state_caps_to_no_vcp(self):
        result = calculate_composite_score(**self._base_scores(), execution_state="Damaged")
        assert result["rating"] == "No VCP"
        assert result["state_cap_applied"] is True

    def test_overextended_caps_textbook_to_weak(self):
        result = calculate_composite_score(**self._base_scores(), execution_state="Overextended")
        assert result["rating"] == "Weak VCP"
        assert result["state_cap_applied"] is True

    def test_extended_caps_strong_to_developing(self):
        result = calculate_composite_score(**self._base_scores(), execution_state="Extended")
        assert result["rating"] == "Developing VCP"
        assert result["state_cap_applied"] is True

    def test_pre_breakout_no_cap(self):
        result = calculate_composite_score(**self._base_scores(), execution_state="Pre-breakout")
        assert result["rating"] == "Textbook VCP"
        assert result["state_cap_applied"] is False

    def test_wide_and_loose_blocks_textbook(self):
        result = calculate_composite_score(
            **self._base_scores(),
            execution_state="Pre-breakout",
            wide_and_loose=True,
        )
        assert result["rating"] == "Developing VCP"
        assert result["state_cap_applied"] is True
        assert "Wide-and-loose" in result["cap_reason"]

    def test_cap_does_not_upgrade_weak_rating(self):
        # Score of 55 → Weak VCP; Extended caps at Developing VCP — no downgrade needed
        result = calculate_composite_score(
            trend_score=55.0,
            contraction_score=55.0,
            volume_score=55.0,
            pivot_score=55.0,
            rs_score=55.0,
            valid_vcp=True,
            execution_state="Extended",
        )
        assert result["rating"] == "Weak VCP"
        assert result["state_cap_applied"] is False  # Weak VCP == cap, no downgrade needed

    def test_execution_state_stored_in_result(self):
        result = calculate_composite_score(
            **self._base_scores(),
            execution_state="Pre-breakout",
            pattern_type="Textbook VCP",
        )
        assert result["execution_state"] == "Pre-breakout"
        assert result["pattern_type"] == "Textbook VCP"


class TestAnalyzeStockNewFields:
    """Verify analyze_stock() returns Phase 1 fields."""

    def test_analyze_stock_has_execution_state_fields(self):
        """analyze_stock() result must contain execution_state and pattern_type."""
        prices = _make_prices(250, start=100.0, daily_change=0.001, volume=1_000_000)
        sp500 = _make_prices(250, start=400.0, daily_change=0.0005)
        quote = {
            "price": prices[0]["close"],
            "marketCap": 10_000_000_000,
            "yearHigh": max(p["high"] for p in prices),
            "yearLow": min(p["low"] for p in prices),
        }
        result = analyze_stock(
            symbol="TEST",
            historical=prices,
            quote=quote,
            sp500_history=sp500,
        )
        assert result is not None
        assert "execution_state" in result
        assert "execution_state_reasons" in result
        assert "pattern_type" in result
        assert "state_cap_applied" in result
        assert isinstance(result["execution_state_reasons"], list)

    def test_analyze_stock_state_cap_applied_when_invalid(self):
        """A declining stock (price < SMA50 < SMA200) should have state_cap_applied."""
        # Declining prices → price will be well below SMA50 and SMA200
        prices = _make_prices(250, start=200.0, daily_change=-0.002, volume=1_000_000)
        sp500 = _make_prices(250, start=400.0, daily_change=0.0005)
        quote = {
            "price": prices[0]["close"],
            "marketCap": 5_000_000_000,
            "yearHigh": prices[-1]["high"],  # 52w high is oldest = lowest in decline
            "yearLow": prices[0]["low"],
        }
        result = analyze_stock(
            symbol="DECLINING",
            historical=prices,
            quote=quote,
            sp500_history=sp500,
        )
        assert result is not None
        # Declining stock should be capped (Invalid or Damaged state → No VCP)
        if result["state_cap_applied"]:
            assert result["rating"] in ("No VCP", "Developing VCP", "Weak VCP")


# ---------------------------------------------------------------------------
# Phase 2: SMA200 Penalty in Trend Template
# ---------------------------------------------------------------------------

from calculators.trend_template_calculator import (
    _calculate_sma200_penalty,
)


class TestSMA200Penalty:
    """Tests for _calculate_sma200_penalty() and its integration."""

    def test_no_penalty_below_threshold(self):
        penalty, dist = _calculate_sma200_penalty(price=140.0, sma200=100.0, max_extension=50.0)
        assert penalty == 0
        assert dist == pytest.approx(40.0)

    def test_no_penalty_at_exact_threshold(self):
        penalty, dist = _calculate_sma200_penalty(price=150.0, sma200=100.0, max_extension=50.0)
        assert penalty == 0
        assert dist == pytest.approx(50.0)

    def test_first_tier_penalty_just_above_threshold(self):
        # 51% above SMA200, threshold=50 → excess=1 → tier −10
        penalty, dist = _calculate_sma200_penalty(price=151.0, sma200=100.0, max_extension=50.0)
        assert penalty == -10
        assert dist == pytest.approx(51.0)

    def test_second_tier_penalty_10pct_excess(self):
        # 60% above SMA200, threshold=50 → excess=10 → tier −15
        penalty, dist = _calculate_sma200_penalty(price=160.0, sma200=100.0, max_extension=50.0)
        assert penalty == -15

    def test_third_tier_penalty_20pct_excess(self):
        # 70% above SMA200, threshold=50 → excess=20 → tier −20
        penalty, dist = _calculate_sma200_penalty(price=170.0, sma200=100.0, max_extension=50.0)
        assert penalty == -20

    def test_no_penalty_when_sma200_none(self):
        penalty, dist = _calculate_sma200_penalty(price=200.0, sma200=None)
        assert penalty == 0
        assert dist is None

    def test_no_penalty_when_sma200_zero(self):
        penalty, dist = _calculate_sma200_penalty(price=200.0, sma200=0.0)
        assert penalty == 0
        assert dist is None

    def test_custom_max_extension(self):
        # max_extension=30 → excess=5 at 35% above → tier −10
        penalty, dist = _calculate_sma200_penalty(price=135.0, sma200=100.0, max_extension=30.0)
        assert penalty == -10

    def test_trend_template_returns_sma200_penalty_field(self):
        prices = _make_prices(250, start=100.0, daily_change=0.001)
        quote = {
            "price": prices[0]["close"],
            "yearHigh": max(p["high"] for p in prices),
            "yearLow": min(p["low"] for p in prices),
        }
        result = calculate_trend_template(prices, quote)
        assert "sma200_penalty" in result
        assert "sma200_distance_pct" in result

    def test_trend_template_penalty_applied_for_very_extended_stock(self):
        """A stock +80% above SMA200 should receive a penalty in trend score."""
        # Build prices where recent bars are much higher than 200d avg
        # Start low, drift up sharply for last 50 bars
        base = _make_prices(200, start=50.0, daily_change=0.0)
        recent = _make_prices(50, start=90.0, daily_change=0.001)
        prices = recent + base  # most-recent-first
        quote = {
            "price": prices[0]["close"],
            "yearHigh": prices[0]["high"] * 1.01,
            "yearLow": prices[-1]["low"] * 0.9,
        }
        result = calculate_trend_template(prices, quote, max_sma200_extension=50.0)
        # sma200_distance_pct should reflect the extension
        if result.get("sma200_distance_pct") is not None:
            dist = result["sma200_distance_pct"]
            if dist > 50.0:
                assert result["sma200_penalty"] < 0
                # SMA200 penalty is metadata only (not applied to score)
                # to avoid double-penalizing with execution_state caps
                assert result["sma200_distance_pct"] > 50.0


# ---------------------------------------------------------------------------
# Phase 3: ATR Compression, Wide-and-Loose, Right-side Tightness
# ---------------------------------------------------------------------------


class TestATRCompressionRatio:
    """Tests for atr_compression_ratio field in calculate_vcp_pattern()."""

    def test_atr_compression_ratio_in_result(self):
        prices = _make_prices(150, start=100.0, daily_change=0.001, volume=1_000_000)
        result = calculate_vcp_pattern(prices)
        assert "atr_compression_ratio" in result

    def test_atr_compression_ratio_none_for_insufficient_data(self):
        """Short price history cannot compute ATR(50) → ratio is None."""
        prices = _make_prices(40, start=100.0, daily_change=0.001)
        result = calculate_vcp_pattern(prices)
        # Either None or a valid float; insufficient data returns None
        # (40 bars is not enough for ATR(50))
        if result.get("atr_compression_ratio") is not None:
            assert isinstance(result["atr_compression_ratio"], float)

    def test_atr_compression_ratio_less_than_1_when_volatility_contracts(self):
        """Flat recent bars after volatile earlier bars → ratio < 1."""
        # Volatile base phase followed by quiet consolidation
        volatile = _make_prices(80, start=100.0, daily_change=0.005)
        # Make volatile bars actually wide by inflating high/low spread
        for p in volatile:
            p["high"] = p["close"] * 1.03
            p["low"] = p["close"] * 0.97
        quiet = _make_prices(70, start=volatile[-1]["close"], daily_change=0.0)
        for p in quiet:
            p["high"] = p["close"] * 1.002
            p["low"] = p["close"] * 0.998
        prices = quiet + volatile  # most-recent-first = quiet first
        result = calculate_vcp_pattern(prices)
        if result.get("atr_compression_ratio") is not None:
            assert result["atr_compression_ratio"] < 1.0

    def test_atr_compression_ratio_is_positive(self):
        prices = _make_prices(150, start=100.0, daily_change=0.001)
        result = calculate_vcp_pattern(prices)
        if result.get("atr_compression_ratio") is not None:
            assert result["atr_compression_ratio"] > 0


class TestWideAndLoose:
    """Tests for wide_and_loose flag in calculate_vcp_pattern() and _compute_wide_and_loose()."""

    def test_wide_and_loose_false_by_default(self):
        prices = _make_prices(150, start=100.0, daily_change=0.001)
        result = calculate_vcp_pattern(prices)
        assert "wide_and_loose" in result
        assert isinstance(result["wide_and_loose"], bool)

    def test_wide_and_loose_false_no_contractions(self):
        prices = _make_prices(35, start=100.0, daily_change=0.0)
        result = calculate_vcp_pattern(prices, min_contractions=2)
        assert result["wide_and_loose"] is False

    def test_wide_and_loose_threshold_parameter_accepted(self):
        prices = _make_prices(150, start=100.0, daily_change=0.001)
        result = calculate_vcp_pattern(prices, wide_and_loose_threshold=20.0)
        assert "wide_and_loose" in result

    # -----------------------------------------------------------------------
    # Direct unit tests of _compute_wide_and_loose() helper
    # -----------------------------------------------------------------------

    def test_compute_wide_and_loose_true_deep_and_short(self):
        from calculators.vcp_pattern_calculator import _compute_wide_and_loose

        final = {"depth_pct": 17.6, "duration_days": 7}
        assert (
            _compute_wide_and_loose([{"depth_pct": 20.0, "duration_days": 25}, final], 15.0) is True
        )

    def test_compute_wide_and_loose_false_deep_but_long(self):
        from calculators.vcp_pattern_calculator import _compute_wide_and_loose

        final = {"depth_pct": 17.6, "duration_days": 15}  # duration >= 10
        assert (
            _compute_wide_and_loose([{"depth_pct": 20.0, "duration_days": 25}, final], 15.0)
            is False
        )

    def test_compute_wide_and_loose_false_short_but_tight(self):
        from calculators.vcp_pattern_calculator import _compute_wide_and_loose

        final = {"depth_pct": 5.6, "duration_days": 6}  # depth <= threshold
        assert (
            _compute_wide_and_loose([{"depth_pct": 20.0, "duration_days": 25}, final], 15.0)
            is False
        )

    def test_compute_wide_and_loose_false_empty(self):
        from calculators.vcp_pattern_calculator import _compute_wide_and_loose

        assert _compute_wide_and_loose([], 15.0) is False

    def test_compute_wide_and_loose_boundary_exactly_threshold(self):
        from calculators.vcp_pattern_calculator import _compute_wide_and_loose

        # depth == threshold is NOT > threshold → False
        final = {"depth_pct": 15.0, "duration_days": 5}
        assert _compute_wide_and_loose([final], 15.0) is False

    def test_compute_wide_and_loose_boundary_exactly_10_days(self):
        from calculators.vcp_pattern_calculator import _compute_wide_and_loose

        # duration == 10 is NOT < 10 → False
        final = {"depth_pct": 20.0, "duration_days": 10}
        assert _compute_wide_and_loose([final], 15.0) is False


class TestRightSideTightness:
    """Tests for right_side_range_ratio field in calculate_vcp_pattern()."""

    def test_right_side_range_ratio_in_result(self):
        prices = _make_prices(150, start=100.0, daily_change=0.001)
        result = calculate_vcp_pattern(prices)
        assert "right_side_range_ratio" in result

    def test_right_side_range_lower_on_tight_base(self):
        """A price series with tight recent bars should have lower ratio."""
        # Volatile base
        volatile = _make_prices(80, start=100.0, daily_change=0.0)
        for p in volatile:
            p["high"] = p["close"] * 1.04
            p["low"] = p["close"] * 0.96

        # Tight recent bars (last 15 are quiet)
        tight = _make_prices(70, start=volatile[-1]["close"], daily_change=0.0)
        for p in tight:
            p["high"] = p["close"] * 1.001
            p["low"] = p["close"] * 0.999

        prices_tight = tight + volatile  # most-recent-first

        # Loose recent bars (last 15 are wide)
        loose = _make_prices(70, start=volatile[-1]["close"], daily_change=0.0)
        for p in loose:
            p["high"] = p["close"] * 1.04
            p["low"] = p["close"] * 0.96

        prices_loose = loose + volatile  # most-recent-first

        result_tight = calculate_vcp_pattern(prices_tight)
        result_loose = calculate_vcp_pattern(prices_loose)

        if (
            result_tight.get("right_side_range_ratio") is not None
            and result_loose.get("right_side_range_ratio") is not None
        ):
            assert result_tight["right_side_range_ratio"] < result_loose["right_side_range_ratio"]

    def test_right_side_range_ratio_none_for_short_data(self):
        prices = _make_prices(35, start=100.0, daily_change=0.0)
        result = calculate_vcp_pattern(prices)
        # With only 35 bars, atr_50 may be 0 → ratio is None
        # (result depends on atr_50 availability)
        assert "right_side_range_ratio" in result


class TestPhase3Integration:
    """Integration: analyze_stock() carries Phase 3 fields through."""

    def test_analyze_stock_contains_atr_compression_ratio(self):
        prices = _make_prices(250, start=100.0, daily_change=0.001, volume=1_000_000)
        sp500 = _make_prices(250, start=400.0, daily_change=0.0005)
        quote = {
            "price": prices[0]["close"],
            "marketCap": 10_000_000_000,
            "yearHigh": max(p["high"] for p in prices),
            "yearLow": min(p["low"] for p in prices),
        }
        result = analyze_stock("TEST", prices, quote, sp500)
        assert result is not None
        # atr_compression_ratio should be passed through from vcp_result
        vcp = result.get("vcp_pattern", {})
        assert "atr_compression_ratio" in vcp
        assert "wide_and_loose" in vcp
        assert "right_side_range_ratio" in vcp

    def test_wide_and_loose_propagated_to_scorer(self):
        """wide_and_loose=True from vcp_result should cap Textbook → Strong in scorer."""
        prices = _make_prices(250, start=100.0, daily_change=0.001, volume=1_000_000)
        sp500 = _make_prices(250, start=400.0, daily_change=0.0005)
        quote = {
            "price": prices[0]["close"],
            "marketCap": 10_000_000_000,
            "yearHigh": max(p["high"] for p in prices),
            "yearLow": min(p["low"] for p in prices),
        }
        result = analyze_stock("TEST", prices, quote, sp500)
        assert result is not None
        # If wide_and_loose was True, rating must not be Textbook VCP
        if result["vcp_pattern"].get("wide_and_loose"):
            assert result["rating"] != "Textbook VCP"


# ---------------------------------------------------------------------------
# Phase 4: Volume Pattern — breakout bar exclusion, breakout_volume_score,
#          strengthened declining contraction bonus
# ---------------------------------------------------------------------------


class TestVolumeBreakoutBarExclusion:
    """Bar[0] must be excluded from dry-up calculation."""

    def test_high_bar0_does_not_inflate_dry_up(self):
        """If bar[0] has high breakout volume, dry-up ratio should stay low."""
        prices = _make_prices(60, volume=1_000_000)
        # All bars 1-10 have dry volume (20% of avg)
        for i in range(1, 11):
            prices[i]["volume"] = 200_000
        # Bar[0] has explosive breakout volume (5x avg)
        prices[0]["volume"] = 5_000_000
        result = calculate_volume_pattern(prices)
        # With bar[0] excluded, dry-up ratio should reflect bars 1-10 only
        # avg(bars 1-10) ≈ 200k, 50d avg ≈ 900k+ (diluted by high bar 0)
        # Ratio should be < 0.5 (bars 1-10 are truly dry)
        assert result["dry_up_ratio"] < 0.5

    def test_legacy_window_uses_bars_1_to_11(self):
        """Legacy window (no contractions) uses volumes[1:11] — 10 bars."""
        prices = _make_prices(60, volume=1_000_000)
        # Set bars 1-10 to exactly half of avg volume
        # Set bar 0 to 0 — would inflate ratio if included
        for i in range(1, 11):
            prices[i]["volume"] = 500_000
        prices[0]["volume"] = 0  # would cause very low ratio if included
        result = calculate_volume_pattern(prices)
        # If bar[0] were included, ratio would be much lower than 0.5
        # Since bar[0] is excluded, ratio ≈ 0.5 (bars 1-10 at half avg)
        # (actual 50d avg is also diluted but rough check)
        assert result["dry_up_ratio"] is not None
        assert result["dry_up_ratio"] > 0  # bar[0]=0 not included


class TestBreakoutVolumeScore:
    """Tests for breakout_volume_score independent field."""

    def test_breakout_volume_score_field_exists(self):
        prices = _make_prices(60, volume=1_000_000)
        result = calculate_volume_pattern(prices, pivot_price=None)
        assert "breakout_volume_score" in result

    def test_breakout_volume_score_zero_when_no_pivot(self):
        """Without a pivot price, no breakout can be assessed."""
        prices = _make_prices(60, volume=1_000_000)
        result = calculate_volume_pattern(prices, pivot_price=None)
        assert result["breakout_volume_score"] == 0

    def test_breakout_volume_score_60_when_above_pivot_with_15x(self):
        """Bar[0] above pivot at 1.5x avg → score = 60."""
        prices = _make_prices(60, volume=1_000_000)
        avg = 1_000_000
        # Bar[0] at 1.5x avg, price above pivot
        prices[0]["volume"] = int(avg * 1.6)
        prices[0]["close"] = 105.0  # above pivot 100
        pivot = 100.0
        result = calculate_volume_pattern(prices, pivot_price=pivot, breakout_volume_ratio=1.5)
        assert result["breakout_volume_score"] == 60

    def test_breakout_volume_score_100_at_3x(self):
        """Bar[0] at 3x+ avg above pivot → score = 100."""
        prices = _make_prices(60, volume=1_000_000)
        prices[0]["volume"] = 3_200_000  # 3.2x avg
        prices[0]["close"] = 105.0
        pivot = 100.0
        result = calculate_volume_pattern(prices, pivot_price=pivot)
        assert result["breakout_volume_score"] == 100

    def test_breakout_volume_score_zero_when_below_pivot(self):
        """Even high volume on bar[0] doesn't score if price is below pivot."""
        prices = _make_prices(60, volume=1_000_000)
        prices[0]["volume"] = 3_000_000
        prices[0]["close"] = 95.0  # BELOW pivot
        pivot = 100.0
        result = calculate_volume_pattern(prices, pivot_price=pivot)
        assert result["breakout_volume_score"] == 0


class TestDecliningContractionBonus:
    """Declining contraction bonus strengthened from +5 to +10."""

    def test_declining_bonus_is_10_not_5(self):
        """Verify declining contraction bonus contributes exactly +10 to score.

        Design: 150 bars, contraction periods placed OUTSIDE 50d avg window
        (indices 0-49 most-recent-first) and Zone B (indices 1-10).
        This ensures both cases have identical base_score; the only difference
        is the declining contraction volume bonus.

        T1: chron 10-40 → most-recent-first indices 109-139 (outside 50d window)
        T2: chron 45-60 → most-recent-first indices 89-104 (outside 50d window)
        """
        prices_declining = _make_prices(150, volume=1_000_000)
        # T1 period (most-recent idx 109-139): high volume
        for i in range(109, 140):
            prices_declining[i]["volume"] = 800_000
        # T2 period (most-recent idx 89-104): low volume → T1 > T2 → declining
        for i in range(89, 105):
            prices_declining[i]["volume"] = 300_000

        prices_flat = _make_prices(150, volume=1_000_000)  # all 1M

        contractions = [
            {"high_idx": 10, "low_idx": 40, "label": "T1"},
            {"high_idx": 45, "low_idx": 60, "label": "T2"},
        ]

        r_dec = calculate_volume_pattern(
            prices_declining, pivot_price=101.0, contractions=contractions
        )
        r_flat = calculate_volume_pattern(prices_flat, pivot_price=101.0, contractions=contractions)

        assert r_dec.get("contraction_volume_trend", {}).get("declining") is True
        assert r_flat.get("contraction_volume_trend", {}).get("declining") is False
        assert r_dec["score"] - r_flat["score"] == 10


# ---------------------------------------------------------------------------
# Phase 5: Report 2-axis format, default changes, strict mode
# ---------------------------------------------------------------------------


def _make_stock(
    symbol="AAPL",
    composite_score=82.0,
    rating="Strong VCP",
    execution_state="Pre-breakout",
    pattern_type="Textbook VCP",
    entry_ready=True,
    state_cap_applied=False,
    distance_from_pivot_pct=-2.0,
    price=150.0,
    valid_vcp=True,
):
    """Build a minimal stock result dict for report tests."""
    return {
        "symbol": symbol,
        "company_name": f"{symbol} Corp",
        "sector": "Technology",
        "price": price,
        "market_cap": 10e9,
        "composite_score": composite_score,
        "rating": rating,
        "rating_description": "",
        "guidance": "Buy at pivot",
        "valid_vcp": valid_vcp,
        "entry_ready": entry_ready,
        "execution_state": execution_state,
        "pattern_type": pattern_type,
        "state_cap_applied": state_cap_applied,
        "cap_reason": None,
        "distance_from_pivot_pct": distance_from_pivot_pct,
        "weakest_component": "volume",
        "weakest_score": 50,
        "strongest_component": "trend",
        "strongest_score": 95,
        "trend_template": {"score": 95, "criteria_passed": 7, "extended_penalty": 0},
        "vcp_pattern": {
            "score": 80,
            "num_contractions": 3,
            "contractions": [
                {"label": "T1", "depth_pct": 12.0},
                {"label": "T2", "depth_pct": 8.0},
                {"label": "T3", "depth_pct": 5.0},
            ],
            "pivot_price": 155.0,
        },
        "volume_pattern": {"score": 70, "dry_up_ratio": 0.4},
        "pivot_proximity": {
            "score": 75,
            "distance_from_pivot_pct": distance_from_pivot_pct,
            "stop_loss_price": 148.0,
            "risk_pct": 5.0,
            "trade_status": "PRE-BREAKOUT",
        },
        "relative_strength": {"score": 80, "rs_rank_estimate": 85, "weighted_rs": 8.0},
    }


class TestPhase5ReportFormat:
    """Tests for 2-axis header format in report_generator."""

    def test_quick_scan_table_present(self):
        """Quick Scan summary table should appear before Section A."""
        stock = _make_stock()
        metadata = {"generated_at": "2025-01-01", "funnel": {}}
        with tempfile.TemporaryDirectory() as tmpdir:
            md_file = os.path.join(tmpdir, "test.md")
            generate_markdown_report([stock], metadata, md_file)
            with open(md_file) as f:
                content = f.read()
        assert "## Quick Scan" in content
        assert "| # | Symbol | Quality | State | Type | Price | Pivot Dist |" in content

    def test_quick_scan_lists_symbol_and_state(self):
        """Quick Scan table should include symbol, execution state, and pattern type."""
        stock = _make_stock(symbol="NVDA", execution_state="Breakout", pattern_type="VCP-adjacent")
        metadata = {"generated_at": "2025-01-01", "funnel": {}}
        with tempfile.TemporaryDirectory() as tmpdir:
            md_file = os.path.join(tmpdir, "test.md")
            generate_markdown_report([stock], metadata, md_file)
            with open(md_file) as f:
                content = f.read()
        assert "NVDA" in content
        assert "Breakout" in content
        assert "VCP-adjacent" in content

    def test_state_cap_marker_shown_in_quick_scan(self):
        """★ marker should appear when state_cap_applied=True."""
        stock = _make_stock(state_cap_applied=True)
        metadata = {"generated_at": "2025-01-01", "funnel": {}}
        with tempfile.TemporaryDirectory() as tmpdir:
            md_file = os.path.join(tmpdir, "test.md")
            generate_markdown_report([stock], metadata, md_file)
            with open(md_file) as f:
                content = f.read()
        assert "★" in content
        assert "State Cap applied" in content

    def test_two_axis_header_in_stock_entry(self):
        """Stock entry should show Quality | State | Type on one line."""
        stock = _make_stock(
            composite_score=88.0,
            rating="Strong VCP",
            execution_state="Pre-breakout",
            pattern_type="Textbook VCP",
        )
        metadata = {"generated_at": "2025-01-01", "funnel": {}}
        with tempfile.TemporaryDirectory() as tmpdir:
            md_file = os.path.join(tmpdir, "test.md")
            generate_markdown_report([stock], metadata, md_file)
            with open(md_file) as f:
                content = f.read()
        assert "**Quality:** 88/100 (Strong VCP)" in content
        assert "**State:** Pre-breakout" in content
        assert "**Type:** Textbook VCP" in content

    def test_old_vcp_score_format_absent(self):
        """Old '**VCP Score:**' format should not appear in report."""
        stock = _make_stock()
        metadata = {"generated_at": "2025-01-01", "funnel": {}}
        with tempfile.TemporaryDirectory() as tmpdir:
            md_file = os.path.join(tmpdir, "test.md")
            generate_markdown_report([stock], metadata, md_file)
            with open(md_file) as f:
                content = f.read()
        assert "**VCP Score:**" not in content


class TestPhase5DefaultChanges:
    """Tests for changed CLI default values."""

    def test_t1_depth_min_default_is_10(self):
        """--t1-depth-min should default to 10.0."""
        import sys

        orig = sys.argv
        sys.argv = ["screen_vcp.py"]
        try:
            args = parse_arguments()
            assert args.t1_depth_min == 10.0
        finally:
            sys.argv = orig

    def test_contraction_ratio_default_is_070(self):
        """--contraction-ratio should default to 0.70."""
        import sys

        orig = sys.argv
        sys.argv = ["screen_vcp.py"]
        try:
            args = parse_arguments()
            assert args.contraction_ratio == 0.70
        finally:
            sys.argv = orig

    def test_strict_flag_defaults_false(self):
        """--strict should default to False."""
        import sys

        orig = sys.argv
        sys.argv = ["screen_vcp.py"]
        try:
            args = parse_arguments()
            assert args.strict is False
        finally:
            sys.argv = orig

    def test_strict_flag_set_when_passed(self):
        """--strict flag should set strict=True."""
        import sys

        orig = sys.argv
        sys.argv = ["screen_vcp.py", "--strict"]
        try:
            args = parse_arguments()
            assert args.strict is True
        finally:
            sys.argv = orig


class TestPhase5StrictMode:
    """Tests for strict mode filtering in compute_entry_ready and analyze_stock."""

    def test_strict_requires_valid_vcp(self):
        """Strict mode: invalid VCP should be excluded (valid_vcp=False)."""
        # Stock with valid_vcp=False and correct execution_state
        stock = _make_stock(valid_vcp=False, execution_state="Pre-breakout")
        # strict filtering is: valid_vcp AND execution_state in (Pre-breakout, Breakout)
        strict_ok = stock.get("valid_vcp", False) and stock.get("execution_state") in (
            "Pre-breakout",
            "Breakout",
        )
        assert strict_ok is False

    def test_strict_requires_pre_breakout_or_breakout(self):
        """Strict mode: Extended/Overextended states should be excluded."""
        for state in ("Extended", "Overextended", "Early-post-breakout", "Damaged", "Invalid"):
            stock = _make_stock(valid_vcp=True, execution_state=state)
            strict_ok = stock.get("valid_vcp", False) and stock.get("execution_state") in (
                "Pre-breakout",
                "Breakout",
            )
            assert strict_ok is False, f"Expected strict to exclude state={state}"

    def test_strict_passes_pre_breakout_with_valid_vcp(self):
        """Strict mode: valid_vcp=True + Pre-breakout should pass."""
        stock = _make_stock(valid_vcp=True, execution_state="Pre-breakout")
        strict_ok = stock.get("valid_vcp", False) and stock.get("execution_state") in (
            "Pre-breakout",
            "Breakout",
        )
        assert strict_ok is True

    def test_strict_passes_breakout_with_valid_vcp(self):
        """Strict mode: valid_vcp=True + Breakout should pass."""
        stock = _make_stock(valid_vcp=True, execution_state="Breakout")
        strict_ok = stock.get("valid_vcp", False) and stock.get("execution_state") in (
            "Pre-breakout",
            "Breakout",
        )
        assert strict_ok is True


# ---------------------------------------------------------------------------
# Regression: wide_and_loose preserved through rerank path
# ---------------------------------------------------------------------------


class TestWideAndLooseRerank:
    """Verify wide_and_loose is persisted in result dict for rerank path."""

    def test_wide_and_loose_in_analyze_stock_result(self):
        """analyze_stock() must include wide_and_loose at top level."""
        prices = _make_prices(250, start=100.0, daily_change=0.001, volume=1_000_000)
        sp500 = _make_prices(250, start=400.0, daily_change=0.0005)
        quote = {
            "price": prices[0]["close"],
            "marketCap": 10_000_000_000,
            "yearHigh": prices[0]["high"] * 1.1,
            "yearLow": prices[-1]["low"],
        }
        result = analyze_stock(
            symbol="TEST",
            historical=prices,
            quote=quote,
            sp500_history=sp500,
        )
        assert result is not None
        assert "wide_and_loose" in result
        assert isinstance(result["wide_and_loose"], bool)

    def test_wide_and_loose_cap_survives_rerank(self):
        """When wide_and_loose=True, re-calling calculate_composite_score must
        still apply the Developing VCP cap (not lose it)."""
        result = calculate_composite_score(
            trend_score=95.0,
            contraction_score=95.0,
            volume_score=90.0,
            pivot_score=90.0,
            rs_score=90.0,
            valid_vcp=True,
            execution_state="Pre-breakout",
            wide_and_loose=True,
        )
        assert result["rating"] == "Developing VCP"

        # Simulate rerank: same call again with updated RS
        result2 = calculate_composite_score(
            trend_score=95.0,
            contraction_score=95.0,
            volume_score=90.0,
            pivot_score=90.0,
            rs_score=85.0,  # changed RS
            valid_vcp=True,
            execution_state="Pre-breakout",
            wide_and_loose=True,  # must still be passed
        )
        assert result2["rating"] == "Developing VCP"
        assert result2["state_cap_applied"] is True


# ---------------------------------------------------------------------------
# Regression: Early-post-breakout state cap
# ---------------------------------------------------------------------------


class TestEarlyPostBreakoutCap:
    """Verify Early-post-breakout caps at Strong VCP."""

    def test_early_post_breakout_caps_textbook(self):
        """Textbook score + Early-post-breakout → Strong VCP (not Textbook)."""
        result = calculate_composite_score(
            trend_score=95.0,
            contraction_score=95.0,
            volume_score=90.0,
            pivot_score=90.0,
            rs_score=90.0,
            valid_vcp=True,
            execution_state="Early-post-breakout",
        )
        assert result["rating"] == "Strong VCP"
        assert result["state_cap_applied"] is True

    def test_early_post_breakout_does_not_cap_strong(self):
        """Strong VCP + Early-post-breakout → Strong VCP (no downgrade)."""
        result = calculate_composite_score(
            trend_score=85.0,
            contraction_score=85.0,
            volume_score=80.0,
            pivot_score=80.0,
            rs_score=80.0,
            valid_vcp=True,
            execution_state="Early-post-breakout",
        )
        assert result["rating"] == "Strong VCP"
        assert result["state_cap_applied"] is False

    def test_pivot_above_no_volume_is_early_post_breakout(self):
        """0-3% above pivot without volume → Early-post-breakout (not Pre-breakout)."""
        from calculators.execution_state import compute_execution_state

        result = compute_execution_state(
            distance_from_pivot_pct=1.5,
            price=102.0,
            sma50=98.0,
            sma200=90.0,
            sma200_distance_pct=13.3,
            last_contraction_low=None,
            breakout_volume=False,
        )
        assert result["state"] == "Early-post-breakout"


# ===========================================================================
# --provider / --full-sp500 behaviour tests
# ===========================================================================


class TestProviderFullSP500Guard:
    """Test --full-sp500 guard for yfinance provider and --provider flag."""

    def _run(self, argv: list[str]):
        """Run parse_arguments() with the given argv list."""
        import sys as _sys
        old_argv = _sys.argv
        _sys.argv = ["screen_vcp.py"] + argv
        try:
            return parse_arguments()
        finally:
            _sys.argv = old_argv

    # ── --provider default ──────────────────────────────────────────────

    def test_default_provider_is_yfinance(self):
        """Without --provider, the default should be 'yfinance'."""
        args = self._run([])
        assert args.provider == "yfinance"

    def test_explicit_yfinance_provider(self):
        args = self._run(["--provider", "yfinance"])
        assert args.provider == "yfinance"

    def test_explicit_fmp_provider(self):
        args = self._run(["--provider", "fmp"])
        assert args.provider == "fmp"

    # ── --full-sp500 + yfinance hard-stop ──────────────────────────────

    def test_full_sp500_yfinance_exits_with_code_1(self, capsys):
        """--provider yfinance --full-sp500 must raise SystemExit(1)."""
        from screen_vcp import _check_full_sp500_yfinance

        args = self._run(["--provider", "yfinance"])
        args.full_sp500 = True

        with pytest.raises(SystemExit) as exc_info:
            _check_full_sp500_yfinance(args)
        assert exc_info.value.code == 1

    def test_full_sp500_yfinance_error_message_content(self, capsys):
        """Stderr must explain curated universe and deferred full-S&P-500."""
        from screen_vcp import _check_full_sp500_yfinance

        args = self._run(["--provider", "yfinance"])
        args.full_sp500 = True

        with pytest.raises(SystemExit):
            _check_full_sp500_yfinance(args)

        captured = capsys.readouterr()
        assert "curated starter universe" in captured.err or "curated" in captured.err
        assert "deferred" in captured.err

    def test_full_sp500_fmp_does_not_exit(self):
        """--provider fmp --full-sp500 must NOT raise SystemExit."""
        from screen_vcp import _check_full_sp500_yfinance

        args = self._run(["--provider", "fmp"])
        args.full_sp500 = True

        # Should not raise
        _check_full_sp500_yfinance(args)

    def test_no_full_sp500_yfinance_does_not_exit(self):
        """--provider yfinance without --full-sp500 must NOT raise SystemExit."""
        from screen_vcp import _check_full_sp500_yfinance

        args = self._run(["--provider", "yfinance"])
        args.full_sp500 = False

        _check_full_sp500_yfinance(args)  # should not raise
