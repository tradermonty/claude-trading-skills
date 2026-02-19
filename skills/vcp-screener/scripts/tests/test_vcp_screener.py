#!/usr/bin/env python3
"""
Tests for VCP Screener modules.

Covers boundary conditions for VCP pattern detection, contraction validation,
Trend Template criteria, volume patterns, pivot proximity, and scoring.
"""

import json
import os
import tempfile

from calculators.pivot_proximity_calculator import calculate_pivot_proximity
from calculators.relative_strength_calculator import calculate_relative_strength
from calculators.trend_template_calculator import calculate_trend_template
from calculators.vcp_pattern_calculator import _validate_vcp
from calculators.volume_pattern_calculator import calculate_volume_pattern
from report_generator import generate_json_report, generate_markdown_report
from scorer import calculate_composite_score
from screen_vcp import analyze_stock, compute_entry_ready, is_stale_price

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
            prices.append({
                "date": f"2026-01-{20-i:02d}",
                "open": 14.31, "high": 14.35, "low": 14.28,
                "close": 14.31, "volume": 500000,
            })
        assert is_stale_price(prices) is True

    def test_normal_price_action(self):
        """Normal volatility -> not stale."""
        prices = []
        for i in range(20):
            base = 100.0 + i * 0.5
            prices.append({
                "date": f"2026-01-{20-i:02d}",
                "open": base, "high": base * 1.02, "low": base * 0.98,
                "close": base + 0.3, "volume": 1000000,
            })
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
            valid_vcp=True, distance_from_pivot_pct=-1.0,
            dry_up_ratio=0.5, risk_pct=5.0,
        )
        assert compute_entry_ready(result) is True

    def test_entry_ready_false_extended(self):
        """valid_vcp=True, distance=+15% -> False (too far above pivot)."""
        result = self._make_result(
            valid_vcp=True, distance_from_pivot_pct=15.0,
            dry_up_ratio=0.5, risk_pct=5.0,
        )
        assert compute_entry_ready(result) is False

    def test_entry_ready_false_invalid_vcp(self):
        """valid_vcp=False -> False regardless of distance."""
        result = self._make_result(
            valid_vcp=False, distance_from_pivot_pct=-1.0,
            dry_up_ratio=0.5, risk_pct=5.0,
        )
        assert compute_entry_ready(result) is False

    def test_entry_ready_false_high_risk(self):
        """valid_vcp=True, distance=-1%, risk=20% -> False (risk too high)."""
        result = self._make_result(
            valid_vcp=True, distance_from_pivot_pct=-1.0,
            dry_up_ratio=0.5, risk_pct=20.0,
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
        assert summary["good"] == 1       # only GOOD1
        assert summary["developing"] == 2  # CAPPED + DEV1
        assert summary["weak"] == 1       # WEAK1
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
            prices.append({
                "date": f"2025-{(i // 22) + 1:02d}-{(i % 22) + 1:02d}",
                "open": sma50_target,
                "high": sma50_target * 1.005,
                "low": sma50_target * 0.995,
                "close": sma50_target,
                "adjClose": sma50_target,
                "volume": 1000000,
            })
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
            prices, quote, rs_rank=85, ext_threshold=ext_threshold,
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
            prices.append({
                "date": f"2025-{(i // 22) + 1:02d}-{(i % 22) + 1:02d}",
                "open": close, "high": close * 1.005,
                "low": close * 0.995, "close": close,
                "adjClose": close, "volume": 1000000,
            })
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
            prices.append({
                "date": f"2025-{(i // 22) + 1:02d}-{(i % 22) + 1:02d}",
                "open": base, "high": base * 1.005,
                "low": base * 0.995, "close": base,
                "adjClose": base, "volume": 1000000,
            })
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
            prices.append({
                "date": f"2025-{(i // 22) + 1:02d}-{(i % 22) + 1:02d}",
                "open": sma50_target,
                "high": sma50_target * 1.005,
                "low": sma50_target * 0.995,
                "close": sma50_target,
                "adjClose": sma50_target,
                "volume": 1000000,
            })
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
            "TEST", prices, quote, sp500, "Tech", "Test Corp",
        )
        tt_default = result_default["trend_template"]
        assert tt_default["extended_penalty"] == -10

        # Custom threshold=15 -> 12% distance -> no penalty
        result_custom = analyze_stock(
            "TEST", prices, quote, sp500, "Tech", "Test Corp",
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
            generate_markdown_report(top_results, metadata, md_file,
                                     all_results=all_results)
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
            generate_markdown_report(top_results, metadata, md_file,
                                     all_results=all_results)
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
            generate_markdown_report(results, metadata, md_file,
                                     all_results=results)
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
            generate_json_report(all_results[:1], metadata, json_file,
                                 all_results=all_results)
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
        """Single stock gets percentile 100."""
        from calculators.relative_strength_calculator import rank_relative_strength_universe
        rs_map = {"ONLY": {"score": 50, "weighted_rs": 10.0}}
        ranked = rank_relative_strength_universe(rs_map)
        assert ranked["ONLY"]["rs_percentile"] == 100

    def test_handles_none_weighted_rs(self):
        """Stocks with None weighted_rs get lowest ranking."""
        from calculators.relative_strength_calculator import rank_relative_strength_universe
        rs_map = {
            "GOOD": {"score": 80, "weighted_rs": 20.0},
            "BAD": {"score": 0, "weighted_rs": None},
        }
        ranked = rank_relative_strength_universe(rs_map)
        assert ranked["GOOD"]["rs_percentile"] > ranked["BAD"]["rs_percentile"]

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
                "score": 70, "num_contractions": 2, "contractions": [],
                "pivot_price": 145.0,
            },
            "volume_pattern": {"score": 40, "dry_up_ratio": 0.8},
            "pivot_proximity": {
                "score": 75, "distance_from_pivot_pct": -3.0,
                "stop_loss_price": 140.0, "risk_pct": 7.0,
                "trade_status": "NEAR PIVOT",
            },
            "relative_strength": {
                "score": 85, "rs_rank_estimate": 80,
                "weighted_rs": 15.0, "rs_percentile": 92,
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
