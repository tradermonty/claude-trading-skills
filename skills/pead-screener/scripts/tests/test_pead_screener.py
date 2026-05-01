#!/usr/bin/env python3
"""
Tests for PEAD Screener modules.

Covers weekly candle conversion, breakout detection, liquidity scoring,
risk/reward calculation, composite scoring, pattern analysis, report
generation, Mode B validation, FMP client error handling, and edge cases.
"""

import json
import logging
import os
import tempfile
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

from calculators.breakout_calculator import calculate_breakout
from calculators.liquidity_calculator import calculate_liquidity
from calculators.risk_reward_calculator import calculate_risk_reward
from calculators.weekly_candle_calculator import (
    analyze_weekly_pattern,
    daily_to_weekly,
)
from fmp_client import ApiCallBudgetExceeded, FMPClient
from report_generator import generate_json_report, generate_markdown_report
from scorer import COMPONENT_WEIGHTS, calculate_composite_score
from screen_pead import (
    analyze_stock,
    calculate_price_gap,
    calculate_setup_quality,
    validate_input_json,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_daily_prices(
    n: int,
    start_date: str = "2026-02-01",
    base_price: float = 100.0,
    daily_change: float = 0.0,
    volume: int = 1_500_000,
    green: bool = True,
) -> list[dict]:
    """Generate synthetic daily price data (most-recent-first).

    Args:
        n: Number of trading days
        start_date: Earliest date in the series
        base_price: Starting price
        daily_change: Daily price change (additive)
        volume: Daily volume
        green: If True, close > open for each day
    """
    start = date.fromisoformat(start_date)
    prices = []
    for i in range(n):
        day = start + timedelta(days=i)
        # Skip weekends
        while day.weekday() >= 5:
            day += timedelta(days=1)
        p = base_price + daily_change * i
        o = p if green else p + 0.5
        c = p + 0.5 if green else p
        prices.append(
            {
                "date": day.strftime("%Y-%m-%d"),
                "open": round(o, 2),
                "high": round(max(o, c) + 1.0, 2),
                "low": round(min(o, c) - 1.0, 2),
                "close": round(c, 2),
                "volume": volume,
            }
        )
    # Return most-recent-first
    prices.reverse()
    return prices


def _make_weekly_candle(
    week_start: str,
    year: int,
    week: int,
    open_: float,
    high: float,
    low: float,
    close: float,
    volume: int = 5_000_000,
    partial: bool = False,
) -> dict:
    """Helper to build a weekly candle dict."""
    return {
        "week_start": week_start,
        "year": year,
        "week": week,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
        "is_green": close >= open_,
        "partial_week": partial,
        "trading_days": 3 if partial else 5,
    }


# ===========================================================================
# TestWeeklyCandleCalculator
# ===========================================================================


class TestWeeklyCandleCalculator:
    """Test daily_to_weekly conversion."""

    def test_daily_to_weekly_basic(self):
        """10 trading days -> 2 weekly candles."""
        # Create 10 days spanning 2 ISO weeks
        # Mon 2026-02-02 to Fri 2026-02-13 (week 6 and 7)
        prices = _make_daily_prices(10, start_date="2026-02-02", base_price=100.0)
        weekly = daily_to_weekly(prices)
        assert len(weekly) == 2
        # Most-recent-first
        assert weekly[0]["week"] >= weekly[1]["week"]
        # Each candle should have OHLCV
        for candle in weekly:
            assert "open" in candle
            assert "high" in candle
            assert "low" in candle
            assert "close" in candle
            assert "volume" in candle
            assert "is_green" in candle
            assert "trading_days" in candle

    def test_earnings_week_split(self):
        """Days before earnings_date are excluded from earnings week candle."""
        # Week of 2026-02-02 (Mon) to 2026-02-06 (Fri)
        # Earnings on Wednesday 2026-02-04
        prices = _make_daily_prices(5, start_date="2026-02-02", base_price=100.0)
        weekly = daily_to_weekly(prices, earnings_date="2026-02-04")
        # The earnings week should only have Wed-Fri (3 days)
        # Find the earnings week candle
        earnings_week = None
        for candle in weekly:
            iso = date(2026, 2, 4).isocalendar()
            if candle["year"] == iso[0] and candle["week"] == iso[1]:
                earnings_week = candle
                break
        assert earnings_week is not None
        assert earnings_week["trading_days"] == 3  # Wed, Thu, Fri

    def test_partial_week(self):
        """Current incomplete week is marked partial_week=True."""
        # Create prices where the latest day is a Wednesday (not Friday)
        # 2026-02-18 is a Wednesday
        prices = [
            {
                "date": "2026-02-18",
                "open": 100,
                "high": 102,
                "low": 99,
                "close": 101,
                "volume": 1000000,
            },
            {
                "date": "2026-02-17",
                "open": 99,
                "high": 101,
                "low": 98,
                "close": 100,
                "volume": 1000000,
            },
            {
                "date": "2026-02-16",
                "open": 98,
                "high": 100,
                "low": 97,
                "close": 99,
                "volume": 1000000,
            },
            # Previous week (complete)
            {
                "date": "2026-02-13",
                "open": 97,
                "high": 99,
                "low": 96,
                "close": 98,
                "volume": 1000000,
            },
            {
                "date": "2026-02-12",
                "open": 96,
                "high": 98,
                "low": 95,
                "close": 97,
                "volume": 1000000,
            },
            {
                "date": "2026-02-11",
                "open": 95,
                "high": 97,
                "low": 94,
                "close": 96,
                "volume": 1000000,
            },
            {
                "date": "2026-02-10",
                "open": 94,
                "high": 96,
                "low": 93,
                "close": 95,
                "volume": 1000000,
            },
            {
                "date": "2026-02-09",
                "open": 93,
                "high": 95,
                "low": 92,
                "close": 94,
                "volume": 1000000,
            },
        ]
        weekly = daily_to_weekly(prices)
        # Most recent week should be partial
        assert weekly[0]["partial_week"] is True
        # Previous week should not be partial
        assert weekly[1]["partial_week"] is False

    def test_iso_week_monday_start(self):
        """Verify weeks are grouped by ISO week (Monday start)."""
        # 2026-02-02 is a Monday
        prices = _make_daily_prices(5, start_date="2026-02-02", base_price=100.0)
        weekly = daily_to_weekly(prices)
        # Should produce exactly 1 week (Mon-Fri)
        assert len(weekly) == 1
        # week_start should be a Monday
        ws = date.fromisoformat(weekly[0]["week_start"])
        assert ws.weekday() == 0  # 0 = Monday

    def test_empty_input(self):
        """Empty daily prices returns empty weekly candles."""
        assert daily_to_weekly([]) == []


# ===========================================================================
# TestBreakoutCalculator
# ===========================================================================


class TestBreakoutCalculator:
    def test_breakout_detected(self):
        """Current price above red candle high -> breakout detected."""
        weekly = [
            _make_weekly_candle(
                "2026-02-16", 2026, 8, 100, 105, 99, 104, volume=6_000_000
            ),  # Green, current
            _make_weekly_candle("2026-02-09", 2026, 7, 102, 103, 97, 98, volume=4_000_000),  # Red
            _make_weekly_candle("2026-02-02", 2026, 6, 95, 102, 94, 101, volume=5_000_000),  # Green
        ]
        red_candle = {
            "high": 103,
            "low": 97,
            "open": 102,
            "close": 98,
            "week_start": "2026-02-09",
            "week_index": 1,
        }
        result = calculate_breakout(weekly, red_candle, current_price=104)
        assert result["is_breakout"] is True
        assert result["breakout_pct"] > 0

    def test_no_breakout(self):
        """Current price below red candle high -> no breakout."""
        weekly = [
            _make_weekly_candle("2026-02-16", 2026, 8, 100, 102, 99, 101, volume=4_000_000),
        ]
        red_candle = {
            "high": 103,
            "low": 97,
            "open": 102,
            "close": 98,
            "week_start": "2026-02-09",
            "week_index": 1,
        }
        result = calculate_breakout(weekly, red_candle, current_price=101)
        assert result["is_breakout"] is False
        assert result["score"] == 0.0

    def test_volume_confirmation(self):
        """Breakout with volume above 4-week average -> volume_confirmation=True."""
        weekly = [
            _make_weekly_candle(
                "2026-02-16", 2026, 8, 100, 107, 99, 106, volume=8_000_000
            ),  # High vol breakout
            _make_weekly_candle("2026-02-09", 2026, 7, 102, 103, 97, 98, volume=3_000_000),
            _make_weekly_candle("2026-02-02", 2026, 6, 95, 102, 94, 101, volume=3_000_000),
            _make_weekly_candle("2026-01-26", 2026, 5, 90, 96, 89, 95, volume=3_000_000),
            _make_weekly_candle("2026-01-19", 2026, 4, 88, 91, 87, 90, volume=3_000_000),
        ]
        red_candle = {
            "high": 103,
            "low": 97,
            "open": 102,
            "close": 98,
            "week_start": "2026-02-09",
            "week_index": 1,
        }
        result = calculate_breakout(weekly, red_candle, current_price=106)
        assert result["volume_confirmation"] is True
        assert result["score"] >= 85

    def test_no_red_candle(self):
        """No red candle -> score 0."""
        weekly = [_make_weekly_candle("2026-02-16", 2026, 8, 100, 105, 99, 104)]
        result = calculate_breakout(weekly, None, current_price=104)
        assert result["score"] == 0.0


# ===========================================================================
# TestLiquidityCalculator
# ===========================================================================


class TestLiquidityCalculator:
    def test_passes_all(self):
        """High liquidity stock passes all thresholds."""
        prices = _make_daily_prices(20, base_price=150.0, volume=2_000_000)
        result = calculate_liquidity(prices, current_price=150.0)
        assert result["passes_all"] is True
        assert result["score"] >= 70

    def test_fails_one(self):
        """Moderate price stock fails only ADV20 threshold (price + volume pass)."""
        # Price=$15 passes ($10+), Volume=2M passes (1M+),
        # but ADV20=$15*2M=$30M barely above $25M — use lower volume to fail ADV20
        prices = _make_daily_prices(20, base_price=15.0, volume=500_000)
        calculate_liquidity(prices, current_price=15.0)
        # ADV20 = $15 * 500K = $7.5M < $25M (fail), volume 500K < 1M (fail), price $15 >= $10 (pass)
        # That's 1 of 3 pass -> score 15. Let's use params where exactly 2 pass.
        # Price=$15 (pass), Volume=2M (pass), ADV20=$15*2M=$30M (pass) -> all pass
        # Instead: price=$8 (fail), volume=5M (pass), ADV20=$8*5M=$40M (pass) -> 2 pass
        prices2 = _make_daily_prices(20, base_price=8.0, volume=5_000_000)
        result2 = calculate_liquidity(prices2, current_price=8.0)
        assert result2["passes_all"] is False
        assert result2["score"] == 40  # 2 of 3 pass (volume + ADV20, price fails)

    def test_fails_all(self):
        """Low price, low volume -> fails all."""
        prices = _make_daily_prices(20, base_price=3.0, volume=50_000)
        result = calculate_liquidity(prices, current_price=3.0)
        assert result["passes_all"] is False
        assert result["score"] == 15

    def test_high_adv20(self):
        """Very high dollar volume -> score 100."""
        prices = _make_daily_prices(20, base_price=200.0, volume=5_000_000)
        result = calculate_liquidity(prices, current_price=200.0)
        assert result["passes_all"] is True
        assert result["adv20_dollar"] > 100_000_000
        assert result["score"] == 100


# ===========================================================================
# TestRiskRewardCalculator
# ===========================================================================


class TestRiskRewardCalculator:
    def test_good_rr(self):
        """R:R >= 2.0 -> score 70."""
        red_candle = {"high": 100, "low": 95, "open": 100, "close": 96}
        result = calculate_risk_reward(
            current_price=101, red_candle=red_candle, target_multiplier=2.0
        )
        assert result["risk_reward_ratio"] == 2.0
        assert result["score"] == 70

    def test_poor_rr(self):
        """Small risk distance -> high R:R but very small absolute risk."""
        red_candle = {"high": 100, "low": 99.5, "open": 100, "close": 99.6}
        result = calculate_risk_reward(
            current_price=100.1, red_candle=red_candle, target_multiplier=2.0
        )
        assert result["risk_reward_ratio"] == 2.0
        assert result["score"] == 70

    def test_excellent_rr(self):
        """R:R >= 3.0 -> score 100."""
        red_candle = {"high": 100, "low": 95, "open": 100, "close": 96}
        result = calculate_risk_reward(
            current_price=101, red_candle=red_candle, target_multiplier=3.0
        )
        assert result["risk_reward_ratio"] == 3.0
        assert result["score"] == 100

    def test_no_red_candle(self):
        """No red candle -> default score 25."""
        result = calculate_risk_reward(current_price=100, red_candle=None)
        assert result["score"] == 25

    def test_stop_above_entry(self):
        """Stop >= entry (invalid) -> default score 25."""
        red_candle = {"high": 100, "low": 105, "open": 100, "close": 104}
        result = calculate_risk_reward(current_price=100, red_candle=red_candle)
        assert result["score"] == 25


# ===========================================================================
# TestScorer
# ===========================================================================


class TestScorer:
    def test_all_high_strong_setup(self):
        """All scores 100 -> Strong Setup."""
        result = calculate_composite_score(100, 100, 100, 100)
        assert result["composite_score"] == 100.0
        assert result["rating"] == "Strong Setup"

    def test_all_low_weak(self):
        """All scores 0 -> Weak."""
        result = calculate_composite_score(0, 0, 0, 0)
        assert result["composite_score"] == 0.0
        assert result["rating"] == "Weak"

    def test_weights_sum_to_1(self):
        """Verify component weights sum to 1.0."""
        total = sum(COMPONENT_WEIGHTS.values())
        assert abs(total - 1.0) < 0.001

    def test_mixed_scores_good(self):
        """Mixed scores in the Good range."""
        # 80*0.30 + 75*0.25 + 70*0.25 + 65*0.20 = 24 + 18.75 + 17.5 + 13 = 73.25
        result = calculate_composite_score(80, 75, 70, 65)
        assert 70 <= result["composite_score"] < 85
        assert result["rating"] == "Good Setup"

    def test_component_breakdown_present(self):
        """Result includes component breakdown."""
        result = calculate_composite_score(80, 70, 60, 50)
        assert "component_breakdown" in result
        assert len(result["component_breakdown"]) == 4

    def test_weakest_strongest(self):
        """Weakest and strongest components identified correctly."""
        result = calculate_composite_score(90, 80, 70, 60)
        assert result["weakest_component"] == "Risk/Reward"
        assert result["weakest_score"] == 60
        assert result["strongest_component"] == "Setup Quality"
        assert result["strongest_score"] == 90


# ===========================================================================
# TestWeeklyPattern
# ===========================================================================


class TestWeeklyPattern:
    """Test analyze_weekly_pattern stage classification."""

    def _build_candles_for_stage(self, stage: str) -> tuple:
        """Build weekly candles that produce the given stage."""
        # Earnings on 2026-02-02 (Monday, ISO week 6)
        earnings_date = "2026-02-02"

        if stage == "MONITORING":
            # All green candles after earnings, no red candle
            candles = [
                _make_weekly_candle("2026-02-09", 2026, 7, 105, 110, 104, 109),  # Green
                _make_weekly_candle(
                    "2026-02-02", 2026, 6, 100, 106, 99, 105
                ),  # Green (earnings week)
            ]
        elif stage == "SIGNAL_READY":
            # Red candle exists but no breakout
            candles = [
                _make_weekly_candle(
                    "2026-02-16", 2026, 8, 106, 108, 104, 105
                ),  # Green, below red high
                _make_weekly_candle(
                    "2026-02-09", 2026, 7, 109, 110, 104, 106
                ),  # Red (close < open)
                _make_weekly_candle(
                    "2026-02-02", 2026, 6, 100, 110, 99, 109
                ),  # Green (earnings week)
            ]
        elif stage == "BREAKOUT":
            # Red candle exists and current candle breaks above it
            candles = [
                _make_weekly_candle(
                    "2026-02-16", 2026, 8, 108, 115, 107, 114
                ),  # Green, above red high=110
                _make_weekly_candle("2026-02-09", 2026, 7, 109, 110, 104, 106),  # Red
                _make_weekly_candle(
                    "2026-02-02", 2026, 6, 100, 110, 99, 109
                ),  # Green (earnings week)
            ]
        elif stage == "EXPIRED":
            # More than 5 weeks since earnings
            candles = [
                _make_weekly_candle("2026-03-16", 2026, 12, 105, 108, 104, 107),
                _make_weekly_candle("2026-03-09", 2026, 11, 104, 107, 103, 106),
                _make_weekly_candle("2026-03-02", 2026, 10, 103, 106, 102, 105),
                _make_weekly_candle("2026-02-23", 2026, 9, 102, 105, 101, 104),
                _make_weekly_candle("2026-02-16", 2026, 8, 101, 104, 100, 103),
                _make_weekly_candle("2026-02-09", 2026, 7, 100, 103, 99, 102),
                _make_weekly_candle("2026-02-02", 2026, 6, 95, 101, 94, 100),  # Earnings week
            ]
        else:
            candles = []

        return candles, earnings_date

    def test_monitoring_stage(self):
        candles, earnings_date = self._build_candles_for_stage("MONITORING")
        result = analyze_weekly_pattern(candles, earnings_date)
        assert result["stage"] == "MONITORING"
        assert result["red_candle"] is None

    def test_signal_ready_stage(self):
        candles, earnings_date = self._build_candles_for_stage("SIGNAL_READY")
        result = analyze_weekly_pattern(candles, earnings_date)
        assert result["stage"] == "SIGNAL_READY"
        assert result["red_candle"] is not None
        assert result["is_breakout"] is False

    def test_breakout_stage(self):
        candles, earnings_date = self._build_candles_for_stage("BREAKOUT")
        result = analyze_weekly_pattern(candles, earnings_date)
        assert result["stage"] == "BREAKOUT"
        assert result["is_breakout"] is True
        assert result["breakout_pct"] > 0

    def test_expired_stage(self):
        candles, earnings_date = self._build_candles_for_stage("EXPIRED")
        result = analyze_weekly_pattern(candles, earnings_date, watch_weeks=5)
        assert result["stage"] == "EXPIRED"


# ===========================================================================
# TestReportGenerator
# ===========================================================================


class TestReportGenerator:
    def _make_result(self, symbol="TEST", stage="BREAKOUT", score=82.5):
        return {
            "symbol": symbol,
            "stage": stage,
            "earnings_date": "2026-02-15",
            "earnings_timing": "amc",
            "gap_pct": 6.3,
            "weeks_since_earnings": 2,
            "red_candle": {
                "high": 195.0,
                "low": 188.0,
                "week_start": "2026-02-17",
                "open": 194.0,
                "close": 189.0,
                "week_index": 1,
            },
            "current_price": 197.5,
            "breakout_pct": 1.28,
            "entry_price": 197.5,
            "stop_price": 188.0,
            "target_price": 216.5,
            "risk_pct": 4.81,
            "risk_reward_ratio": 2.0,
            "adv20_dollar": 45_000_000,
            "composite_score": score,
            "rating": "Good Setup" if score >= 70 else "Developing",
            "guidance": "Solid PEAD setup, standard position size",
            "components": {
                "setup_quality": {
                    "label": "Setup Quality",
                    "score": 90,
                    "weight": 0.30,
                    "weighted": 27.0,
                },
                "breakout_strength": {
                    "label": "Breakout Strength",
                    "score": 70,
                    "weight": 0.25,
                    "weighted": 17.5,
                },
                "liquidity": {"label": "Liquidity", "score": 85, "weight": 0.25, "weighted": 21.25},
                "risk_reward": {
                    "label": "Risk/Reward",
                    "score": 70,
                    "weight": 0.20,
                    "weighted": 14.0,
                },
            },
        }

    def test_json_structure(self):
        """JSON report has correct structure."""
        results = [self._make_result("AAPL", "BREAKOUT", 85)]
        metadata = {
            "generated_at": "2026-02-21 10:00:00",
            "lookback_days": 14,
            "watch_weeks": 5,
            "mode": "A",
            "api_stats": {"api_calls_made": 50, "budget_remaining": 150},
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = os.path.join(tmpdir, "test.json")
            generate_json_report(results, metadata, json_file)
            with open(json_file) as f:
                data = json.load(f)
            assert "metadata" in data
            assert "results" in data
            assert "summary" in data
            assert data["summary"]["breakout"] == 1

    def test_markdown_generation(self):
        """Markdown report generates without errors."""
        results = [
            self._make_result("AAPL", "BREAKOUT", 85),
            self._make_result("MSFT", "SIGNAL_READY", 65),
            self._make_result("GOOG", "MONITORING", 40),
        ]
        metadata = {
            "generated_at": "2026-02-21 10:00:00",
            "lookback_days": 14,
            "watch_weeks": 5,
            "mode": "A",
            "api_stats": {"api_calls_made": 50, "budget_remaining": 150},
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            md_file = os.path.join(tmpdir, "test.md")
            generate_markdown_report(results, metadata, md_file)
            with open(md_file) as f:
                content = f.read()
            assert "PEAD Screener Report" in content
            assert "BREAKOUT" in content
            assert "SIGNAL_READY" in content
            assert "MONITORING" in content
            assert "AAPL" in content
            assert "MSFT" in content
            assert "GOOG" in content

    def test_stage_grouping(self):
        """Results are grouped by stage in the report."""
        results = [
            self._make_result("A", "MONITORING", 40),
            self._make_result("B", "BREAKOUT", 85),
            self._make_result("C", "SIGNAL_READY", 65),
        ]
        metadata = {
            "generated_at": "2026-02-21",
            "mode": "A",
            "watch_weeks": 5,
            "lookback_days": 14,
            "api_stats": {},
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = os.path.join(tmpdir, "test.json")
            generate_json_report(results, metadata, json_file)
            with open(json_file) as f:
                data = json.load(f)
            # First result should be BREAKOUT (highest priority)
            assert data["results"][0]["stage"] == "BREAKOUT"


# ===========================================================================
# TestValidateInputJson (Mode B Failure Cases)
# ===========================================================================


class TestValidateInputJson:
    def test_schema_version_mismatch(self):
        """schema_version '2.0' -> ValueError."""
        data = {
            "schema_version": "2.0",
            "results": [
                {
                    "symbol": "AAPL",
                    "earnings_date": "2026-02-15",
                    "earnings_timing": "amc",
                    "gap_pct": 5.0,
                    "grade": "A",
                }
            ],
        }
        try:
            validate_input_json(data)
            raise AssertionError("Should have raised ValueError")
        except ValueError as e:
            assert "Schema version mismatch" in str(e)
            assert "2.0" in str(e)

    def test_missing_required_field(self, caplog):
        """Result missing 'symbol' -> skip + warning log."""
        data = {
            "schema_version": "1.0",
            "results": [
                {
                    "symbol": "AAPL",
                    "earnings_date": "2026-02-15",
                    "earnings_timing": "amc",
                    "gap_pct": 5.0,
                    "grade": "A",
                },
                {
                    "earnings_date": "2026-02-16",  # Missing 'symbol'
                    "earnings_timing": "bmo",
                    "gap_pct": 3.0,
                    "grade": "B",
                },
            ],
        }
        with caplog.at_level(logging.WARNING):
            validated = validate_input_json(data)
        assert len(validated) == 1
        assert validated[0]["symbol"] == "AAPL"
        # Check warning was logged
        assert any("missing required fields" in r.message.lower() for r in caplog.records)

    def test_valid_input(self):
        """Proper schema '1.0' with all fields -> passes."""
        data = {
            "schema_version": "1.0",
            "results": [
                {
                    "symbol": "AAPL",
                    "earnings_date": "2026-02-15",
                    "earnings_timing": "amc",
                    "gap_pct": 5.0,
                    "grade": "A",
                },
                {
                    "symbol": "MSFT",
                    "earnings_date": "2026-02-16",
                    "earnings_timing": "bmo",
                    "gap_pct": 3.5,
                    "grade": "B",
                },
            ],
        }
        validated = validate_input_json(data)
        assert len(validated) == 2

    def test_all_records_invalid(self):
        """All records missing fields -> ValueError (empty results)."""
        data = {
            "schema_version": "1.0",
            "results": [
                {"earnings_date": "2026-02-15"},  # Missing symbol, timing, gap, grade
                {"gap_pct": 5.0},  # Missing symbol, date, timing, grade
            ],
        }
        try:
            validate_input_json(data)
            raise AssertionError("Should have raised ValueError")
        except ValueError as e:
            assert "All" in str(e) and "records failed" in str(e)

    def test_invalid_timing_skipped(self, caplog):
        """Invalid earnings_timing value -> skip + warning."""
        data = {
            "schema_version": "1.0",
            "results": [
                {
                    "symbol": "AAPL",
                    "earnings_date": "2026-02-15",
                    "earnings_timing": "amc",
                    "gap_pct": 5.0,
                    "grade": "A",
                },
                {
                    "symbol": "MSFT",
                    "earnings_date": "2026-02-16",
                    "earnings_timing": "invalid_timing",
                    "gap_pct": 3.0,
                    "grade": "B",
                },
            ],
        }
        with caplog.at_level(logging.WARNING):
            validated = validate_input_json(data)
        assert len(validated) == 1
        assert validated[0]["symbol"] == "AAPL"

    def test_invalid_grade_skipped(self, caplog):
        """Invalid grade value -> skip + warning."""
        data = {
            "schema_version": "1.0",
            "results": [
                {
                    "symbol": "AAPL",
                    "earnings_date": "2026-02-15",
                    "earnings_timing": "amc",
                    "gap_pct": 5.0,
                    "grade": "A",
                },
                {
                    "symbol": "MSFT",
                    "earnings_date": "2026-02-16",
                    "earnings_timing": "bmo",
                    "gap_pct": 3.0,
                    "grade": "Z",
                },
            ],
        }
        with caplog.at_level(logging.WARNING):
            validated = validate_input_json(data)
        assert len(validated) == 1

    def test_gap_pct_string_skipped(self, caplog):
        """gap_pct as string -> skip + warning."""
        data = {
            "schema_version": "1.0",
            "results": [
                {
                    "symbol": "AAPL",
                    "earnings_date": "2026-02-15",
                    "earnings_timing": "amc",
                    "gap_pct": "not_a_number",
                    "grade": "A",
                },
                {
                    "symbol": "MSFT",
                    "earnings_date": "2026-02-16",
                    "earnings_timing": "bmo",
                    "gap_pct": 3.0,
                    "grade": "B",
                },
            ],
        }
        with caplog.at_level(logging.WARNING):
            validated = validate_input_json(data)
        assert len(validated) == 1
        assert validated[0]["symbol"] == "MSFT"

    def test_empty_symbol_skipped(self, caplog):
        """Empty symbol string -> skip + warning."""
        data = {
            "schema_version": "1.0",
            "results": [
                {
                    "symbol": "",
                    "earnings_date": "2026-02-15",
                    "earnings_timing": "amc",
                    "gap_pct": 5.0,
                    "grade": "A",
                },
                {
                    "symbol": "MSFT",
                    "earnings_date": "2026-02-16",
                    "earnings_timing": "bmo",
                    "gap_pct": 3.0,
                    "grade": "B",
                },
            ],
        }
        with caplog.at_level(logging.WARNING):
            validated = validate_input_json(data)
        assert len(validated) == 1
        assert validated[0]["symbol"] == "MSFT"


# ===========================================================================
# TestCalculatePriceGap (Fix #1: actual price gap in Mode A)
# ===========================================================================


class TestCalculatePriceGap:
    """Test actual price gap calculation from daily OHLCV data."""

    def test_bmo_gap(self):
        """BMO: gap = open[earnings_date] / close[prev_day] - 1"""
        prices = [
            {
                "date": "2026-02-17",
                "open": 110.0,
                "high": 112.0,
                "low": 109.0,
                "close": 111.0,
                "volume": 1000000,
            },
            {
                "date": "2026-02-16",
                "open": 106.0,
                "high": 111.0,
                "low": 105.0,
                "close": 110.0,
                "volume": 3000000,
            },
            {
                "date": "2026-02-13",
                "open": 99.0,
                "high": 101.0,
                "low": 98.0,
                "close": 100.0,
                "volume": 1000000,
            },
        ]
        # BMO on 2026-02-16: gap = 106.0 / 100.0 - 1 = 6.0%
        gap = calculate_price_gap(prices, "2026-02-16", "bmo")
        assert gap == 6.0

    def test_amc_gap(self):
        """AMC: gap = open[next_day] / close[earnings_date] - 1"""
        prices = [
            {
                "date": "2026-02-17",
                "open": 108.0,
                "high": 110.0,
                "low": 107.0,
                "close": 109.0,
                "volume": 2000000,
            },
            {
                "date": "2026-02-16",
                "open": 99.0,
                "high": 101.0,
                "low": 98.0,
                "close": 100.0,
                "volume": 3000000,
            },
            {
                "date": "2026-02-13",
                "open": 98.0,
                "high": 100.0,
                "low": 97.0,
                "close": 99.0,
                "volume": 1000000,
            },
        ]
        # AMC on 2026-02-16: gap = 108.0 / 100.0 - 1 = 8.0%
        gap = calculate_price_gap(prices, "2026-02-16", "amc")
        assert gap == 8.0

    def test_unknown_timing_uses_amc(self):
        """Unknown timing falls back to AMC logic."""
        prices = [
            {
                "date": "2026-02-17",
                "open": 105.0,
                "high": 107.0,
                "low": 104.0,
                "close": 106.0,
                "volume": 1000000,
            },
            {
                "date": "2026-02-16",
                "open": 99.0,
                "high": 101.0,
                "low": 98.0,
                "close": 100.0,
                "volume": 3000000,
            },
        ]
        gap_amc = calculate_price_gap(prices, "2026-02-16", "amc")
        gap_unknown = calculate_price_gap(prices, "2026-02-16", "")
        assert gap_amc == gap_unknown

    def test_missing_earnings_date(self):
        """Earnings date not in data -> 0.0."""
        prices = [
            {"date": "2026-02-17", "open": 100.0, "close": 101.0},
        ]
        gap = calculate_price_gap(prices, "2099-12-31", "bmo")
        assert gap == 0.0

    def test_no_prev_day_bmo(self):
        """BMO with no previous day -> 0.0."""
        prices = [
            {"date": "2026-02-16", "open": 106.0, "close": 107.0},
        ]
        gap = calculate_price_gap(prices, "2026-02-16", "bmo")
        assert gap == 0.0


# ===========================================================================
# TestFMPClient (Error Handling)
# ===========================================================================


class TestFMPClient:
    @patch("fmp_client.requests.Session")
    def test_api_429(self, mock_session_class):
        """Mock 429 -> rate_limit_reached, returns None."""
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.text = "Rate limit exceeded"
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        client = FMPClient(api_key="test_key", max_api_calls=200)
        client.session = mock_session
        client.max_retries = 0  # Don't retry for test speed

        result = client.get_earnings_calendar("2026-02-01", "2026-02-15")
        assert result is None
        assert client.rate_limit_reached is True

    @patch("fmp_client.requests.Session")
    def test_api_timeout(self, mock_session_class):
        """Mock Timeout -> returns None."""
        import requests as req

        mock_session = MagicMock()
        mock_session.get.side_effect = req.exceptions.Timeout("Connection timed out")
        mock_session_class.return_value = mock_session

        client = FMPClient(api_key="test_key", max_api_calls=200)
        client.session = mock_session

        result = client.get_historical_prices("AAPL", days=90)
        assert result is None

    def test_budget_exceeded(self):
        """Raises ApiCallBudgetExceeded when budget exhausted."""
        client = FMPClient(api_key="test_key", max_api_calls=0)
        try:
            client._rate_limited_get("https://example.com/api/v3/test")
            raise AssertionError("Should have raised ApiCallBudgetExceeded")
        except ApiCallBudgetExceeded as e:
            assert "budget exhausted" in str(e).lower()


class TestFMPHistoricalNormalizer:
    """Cover stable/historical-price-eod/full flat-list normalization (Issue #64)."""

    @staticmethod
    def _mock_response(status_code, json_payload):
        resp = MagicMock()
        resp.status_code = status_code
        resp.json.return_value = json_payload
        resp.text = ""
        return resp

    @staticmethod
    def _make_client(mock_session):
        client = FMPClient(api_key="test_key", max_api_calls=200)
        client.session = mock_session
        client.max_retries = 0
        return client

    @patch("fmp_client.requests.Session")
    def test_eod_flat_list_truncated_to_days(self, mock_session_class):
        """Contract: returned historical is truncated to `days` rows.

        The new EOD endpoint ignores `timeseries` and returns full history.
        The normalizer must truncate so callers receive at most N rows,
        preserving the legacy v3 `timeseries=N` contract.
        """
        mock_session = MagicMock()
        mock_session.get.return_value = self._mock_response(
            200,
            [
                {
                    "symbol": "SPY",
                    "date": f"2026-04-{30 - i:02d}",
                    "open": 500.0,
                    "high": 502.0,
                    "low": 499.0,
                    "close": 500.0 + i,
                    "volume": 1_000_000,
                }
                for i in range(5)
            ],
        )
        mock_session_class.return_value = mock_session
        client = self._make_client(mock_session)

        result = client.get_historical_prices("SPY", days=2)
        assert result is not None
        # API returned 5 rows but we requested days=2; normalizer must truncate
        assert len(result["historical"]) == 2, (
            f"expected truncation to 2 rows, got {len(result['historical'])}"
        )
        # Most recent first preserved
        assert result["historical"][0]["date"] == "2026-04-30"
        assert result["historical"][1]["date"] == "2026-04-29"

    @patch("fmp_client.requests.Session")
    def test_eod_flat_list_normalized(self, mock_session_class):
        """New stable EOD flat list -> v3-compat dict with historical[]."""
        mock_session = MagicMock()
        mock_session.get.return_value = self._mock_response(
            200,
            [
                {
                    "symbol": "SPY",
                    "date": "2026-04-29",
                    "open": 500.0,
                    "high": 502.0,
                    "low": 499.0,
                    "close": 501.0,
                    "volume": 1_000_000,
                },
                {
                    "symbol": "SPY",
                    "date": "2026-04-28",
                    "open": 498.0,
                    "high": 501.0,
                    "low": 497.0,
                    "close": 500.0,
                    "volume": 1_100_000,
                },
            ],
        )
        mock_session_class.return_value = mock_session
        client = self._make_client(mock_session)

        result = client.get_historical_prices("SPY", days=2)
        assert result is not None
        assert result["symbol"] == "SPY"
        assert len(result["historical"]) == 2
        assert result["historical"][0]["date"] == "2026-04-29"
        assert result["historical"][0]["close"] == 501.0
        assert "symbol" not in result["historical"][0], (
            "row-level symbol should be stripped to mirror v3 shape"
        )

    @patch("fmp_client.requests.Session")
    def test_empty_list_falls_back_via_falsy_path(self, mock_session_class):
        """Empty list response is caught by `if not data: continue` before normalizer."""
        mock_session = MagicMock()
        mock_session.get.return_value = self._mock_response(200, [])
        mock_session_class.return_value = mock_session
        client = self._make_client(mock_session)

        result = client.get_historical_prices("SPY", days=2)
        # Both stable and v3 fallback see empty/None -> final result None
        assert result is None

    @patch("fmp_client.requests.Session")
    def test_eod_symbol_mismatch_rejected(self, mock_session_class):
        """List with no matching symbol -> normalizer returns None, fallback exhausted."""
        mock_session = MagicMock()
        mock_session.get.return_value = self._mock_response(
            200,
            [{"symbol": "QQQ", "date": "2026-04-29", "open": 1.0, "close": 1.0}],
        )
        mock_session_class.return_value = mock_session
        client = self._make_client(mock_session)

        result = client.get_historical_prices("SPY", days=2)
        assert result is None

    @patch("fmp_client.requests.Session")
    def test_eod_row_without_symbol_field(self, mock_session_class):
        """Single-symbol endpoint may omit per-row 'symbol' -> treat as requested symbol."""
        mock_session = MagicMock()
        mock_session.get.return_value = self._mock_response(
            200,
            [
                {"date": "2026-04-29", "open": 500.0, "close": 501.0},
                {"date": "2026-04-28", "open": 498.0, "close": 500.0},
            ],
        )
        mock_session_class.return_value = mock_session
        client = self._make_client(mock_session)

        result = client.get_historical_prices("SPY", days=2)
        assert result is not None
        assert result["symbol"] == "SPY"
        assert len(result["historical"]) == 2
        assert result["historical"][0]["close"] == 501.0

    @patch("fmp_client.requests.Session")
    def test_eod_index_symbol_normalized(self, mock_session_class):
        """Dot/dash normalization (BRK.B vs BRK-B style) works."""
        mock_session = MagicMock()
        mock_session.get.return_value = self._mock_response(
            200,
            [{"symbol": "BRK.B", "date": "2026-04-29", "open": 400.0, "close": 401.0}],
        )
        mock_session_class.return_value = mock_session
        client = self._make_client(mock_session)

        result = client.get_historical_prices("BRK-B", days=1)
        assert result is not None
        assert result["historical"][0]["close"] == 401.0

    @patch("fmp_client.requests.Session")
    def test_legacy_v3_dict_passthrough(self, mock_session_class):
        """v3 fallback dict shape passes normalizer untouched."""
        mock_session = MagicMock()
        mock_session.get.return_value = self._mock_response(
            200,
            {"symbol": "SPY", "historical": [{"date": "2026-04-29", "close": 501.0}]},
        )
        mock_session_class.return_value = mock_session
        client = self._make_client(mock_session)

        result = client.get_historical_prices("SPY", days=1)
        assert result is not None
        assert result["historical"][0]["close"] == 501.0

    @patch("fmp_client.requests.Session")
    def test_legacy_historicalStockList_still_works(self, mock_session_class):
        """historicalStockList batch shape still handled by existing branch."""
        mock_session = MagicMock()
        mock_session.get.return_value = self._mock_response(
            200,
            {
                "historicalStockList": [
                    {"symbol": "SPY", "historical": [{"date": "2026-04-29", "close": 501.0}]},
                    {"symbol": "QQQ", "historical": [{"date": "2026-04-29", "close": 400.0}]},
                ]
            },
        )
        mock_session_class.return_value = mock_session
        client = self._make_client(mock_session)

        result = client.get_historical_prices("SPY", days=1)
        assert result is not None
        assert result["symbol"] == "SPY"
        assert result["historical"][0]["close"] == 501.0

    @patch("fmp_client.requests.Session")
    def test_url_uses_eod_endpoint(self, mock_session_class):
        """Regression: stable URL must be /historical-price-eod/full, not /historical-price-full."""
        mock_session = MagicMock()
        mock_session.get.return_value = self._mock_response(
            200,
            [{"symbol": "SPY", "date": "2026-04-29", "close": 1.0}],
        )
        mock_session_class.return_value = mock_session
        client = self._make_client(mock_session)

        client.get_historical_prices("SPY", days=1)
        # First call should hit the new EOD URL with from/to params (not timeseries)
        first_call = mock_session.get.call_args_list[0]
        url = first_call[0][0]
        params = first_call[1]["params"]
        assert "historical-price-eod/full" in url
        assert "historical-price-full" not in url.replace("historical-price-eod/full", "")
        assert params.get("symbol") == "SPY"
        assert "from" in params and "to" in params
        assert "timeseries" not in params, (
            "timeseries must be converted to from/to since stable EOD ignores timeseries"
        )


# ===========================================================================
# TestPartialWeekBoundary
# ===========================================================================


class TestPartialWeekBoundary:
    def test_friday_only_week(self):
        """Single Friday -> valid partial weekly candle."""
        # 2026-02-20 is a Friday
        prices = [
            {
                "date": "2026-02-20",
                "open": 100,
                "high": 102,
                "low": 99,
                "close": 101,
                "volume": 1000000,
            },
        ]
        weekly = daily_to_weekly(prices)
        assert len(weekly) == 1
        # It's the only day in the week, and it's Friday (day 5 in ISO)
        # Since isocalendar day_of_week is 5 (Friday), it should NOT be partial
        assert weekly[0]["trading_days"] == 1
        assert weekly[0]["open"] == 100
        assert weekly[0]["close"] == 101

    def test_monday_earnings_bmo(self):
        """Monday BMO earnings -> earnings week starts Monday (full week)."""
        # 2026-02-16 is a Monday
        prices = _make_daily_prices(5, start_date="2026-02-16", base_price=100.0)
        weekly = daily_to_weekly(prices, earnings_date="2026-02-16")
        # Earnings on Monday BMO -> include Monday and all subsequent days
        assert len(weekly) == 1
        assert weekly[0]["trading_days"] == 5  # Full week Mon-Fri


# ===========================================================================
# TestSetupQuality
# ===========================================================================


class TestSetupQuality:
    """Test calculate_setup_quality scoring."""

    def test_large_gap_breakout(self):
        """10%+ gap with BREAKOUT stage -> high score."""
        pattern = {"stage": "BREAKOUT", "weeks_since_earnings": 2, "red_candle": None}
        score = calculate_setup_quality(10.0, pattern)
        assert score == 100  # 50 (gap) + 50 (breakout)

    def test_small_gap_monitoring(self):
        """3% gap with MONITORING early -> moderate score."""
        pattern = {"stage": "MONITORING", "weeks_since_earnings": 1, "red_candle": None}
        score = calculate_setup_quality(3.0, pattern)
        assert score == 45  # 20 (gap) + 25 (monitoring early)

    def test_expired_stage(self):
        """EXPIRED stage -> only gap points."""
        pattern = {"stage": "EXPIRED", "weeks_since_earnings": 6, "red_candle": None}
        score = calculate_setup_quality(5.0, pattern)
        assert score == 30  # 30 (gap) + 0 (expired)


# ===========================================================================
# TestAnalyzeStock (Integration)
# ===========================================================================


class TestAnalyzeStock:
    """Integration test for analyze_stock."""

    def test_basic_analysis(self):
        """analyze_stock returns expected structure."""
        # Create daily prices spanning 3+ weeks
        prices = _make_daily_prices(30, start_date="2026-01-19", base_price=100.0, daily_change=0.5)
        result = analyze_stock(
            symbol="TEST",
            daily_prices=prices,
            earnings_date="2026-01-19",
            earnings_timing="bmo",
            gap_pct=5.0,
            current_price=115.0,
            watch_weeks=5,
        )
        assert result is not None
        assert result["symbol"] == "TEST"
        assert "stage" in result
        assert "composite_score" in result
        assert "rating" in result
        assert "components" in result

    def test_insufficient_data(self):
        """Very few data points -> returns None."""
        prices = _make_daily_prices(2, start_date="2026-02-18", base_price=100.0)
        result = analyze_stock(
            symbol="TEST",
            daily_prices=prices,
            earnings_date="2026-02-18",
            earnings_timing="bmo",
            gap_pct=5.0,
            current_price=101.0,
        )
        assert result is None
