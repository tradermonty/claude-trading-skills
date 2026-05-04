#!/usr/bin/env python3
"""
Tests for CANSLIM L component multi-period RS extension (Phase 3.1).

Covers:
- slice_period_return: window slicing & graceful fallback
- compute_multi_period_rs: full / partial / no-benchmark cases
- classify_rs_rating: threshold mapping with boundary values
- calculate_leadership: extended fields, legacy fields preserved, legacy path
- screen_canslim CLI flags: --rs-benchmark / --disable-rs propagation
- report_generator: summary table + multi-period L row
"""

import os
import tempfile
from unittest.mock import MagicMock

from calculators.leadership_calculator import (
    DEFAULT_PERIODS_DAYS,
    calculate_leadership,
    classify_rs_rating,
    compute_multi_period_rs,
    slice_period_return,
)
from report_generator import generate_markdown_report

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _make_price_series(start_price: float, daily_pct: float, days: int) -> list[dict]:
    """
    Build a simple ascending-date series of {"date", "close"} dicts.

    daily_pct: daily compounded return (e.g. 0.001 = +0.1%/day).
    """
    series = []
    price = start_price
    for i in range(days):
        # Use a synthetic date that sorts correctly lexicographically.
        date_str = f"2024-{(i // 30) + 1:02d}-{(i % 30) + 1:02d}"
        series.append({"date": date_str, "close": round(price, 4)})
        price *= 1 + daily_pct
    return series


# ---------------------------------------------------------------------------
# slice_period_return
# ---------------------------------------------------------------------------


class TestSlicePeriodReturn:
    def test_basic_window(self):
        # 100 days, +0.1% per day => total ~+10.46%
        series = _make_price_series(100.0, 0.001, 100)
        ret = slice_period_return(series, 100)
        assert ret is not None
        assert 10.0 < ret < 10.6

    def test_smaller_window(self):
        # Take only the most recent 30 days from a 100-day series.
        series = _make_price_series(100.0, 0.001, 100)
        ret = slice_period_return(series, 30)
        assert ret is not None
        # 29 compounded days at +0.1% => ~+2.94%
        assert 2.5 < ret < 3.5

    def test_insufficient_data_returns_none(self):
        series = _make_price_series(100.0, 0.001, 30)
        assert slice_period_return(series, 60) is None

    def test_empty_input(self):
        assert slice_period_return([], 30) is None
        assert slice_period_return(None, 30) is None

    def test_invalid_start_price(self):
        bad = [{"date": "2024-01-01", "close": 0}, {"date": "2024-01-02", "close": 100}]
        assert slice_period_return(bad, 2) is None

    def test_normalizes_descending_input(self):
        ascending = _make_price_series(100.0, 0.001, 100)
        descending = list(reversed(ascending))
        # Both orderings should yield the same return because slice_period_return
        # normalizes internally.
        asc_ret = slice_period_return(ascending, 50)
        desc_ret = slice_period_return(descending, 50)
        assert asc_ret is not None and desc_ret is not None
        assert abs(asc_ret - desc_ret) < 1e-6


# ---------------------------------------------------------------------------
# compute_multi_period_rs
# ---------------------------------------------------------------------------


class TestComputeMultiPeriodRS:
    def test_all_periods_available(self):
        stock = _make_price_series(100.0, 0.002, 260)  # strong uptrend
        bench = _make_price_series(100.0, 0.001, 260)  # weaker uptrend
        result = compute_multi_period_rs(stock, bench)

        assert result["rs_3m_return"] is not None
        assert result["rs_6m_return"] is not None
        assert result["rs_12m_return"] is not None
        assert result["benchmark_3m_return"] is not None
        assert result["rel_12m"] > 0  # stock outperforms benchmark
        assert result["weighted_relative_performance"] > 0
        assert result["weighted_stock_performance"] is not None
        assert set(result["available_periods"]) == {"3m", "6m", "12m"}
        assert result["missing_periods"] == []

    def test_only_3m_and_6m_available(self):
        # 200 days < 252 (12m) but >= 126 (6m) and 63 (3m)
        stock = _make_price_series(100.0, 0.002, 200)
        bench = _make_price_series(100.0, 0.001, 200)
        result = compute_multi_period_rs(stock, bench)

        assert result["rs_3m_return"] is not None
        assert result["rs_6m_return"] is not None
        assert result["rs_12m_return"] is None
        assert result["weighted_stock_performance"] is not None
        assert result["weighted_relative_performance"] is not None
        assert "12m" in result["missing_periods"]
        assert set(result["available_periods"]) == {"3m", "6m"}

    def test_no_benchmark(self):
        stock = _make_price_series(100.0, 0.002, 260)
        result = compute_multi_period_rs(stock, None)

        assert result["rs_3m_return"] is not None
        assert result["benchmark_3m_return"] is None
        assert result["rel_3m"] is None
        assert result["weighted_stock_performance"] is not None
        # Without a benchmark, the weighted RELATIVE performance is undefined.
        assert result["weighted_relative_performance"] is None

    def test_all_missing(self):
        # Far less than 63 bars
        stock = _make_price_series(100.0, 0.002, 30)
        result = compute_multi_period_rs(stock, None)
        assert result["weighted_stock_performance"] is None
        assert result["weighted_relative_performance"] is None
        assert result["available_periods"] == []


# ---------------------------------------------------------------------------
# classify_rs_rating
# ---------------------------------------------------------------------------


class TestClassifyRsRating:
    def test_market_leader(self):
        assert classify_rs_rating(99) == "Market Leader"
        assert classify_rs_rating(90) == "Market Leader"

    def test_strong(self):
        assert classify_rs_rating(89) == "Strong"
        assert classify_rs_rating(80) == "Strong"

    def test_above_average(self):
        assert classify_rs_rating(79) == "Above Average"
        assert classify_rs_rating(60) == "Above Average"

    def test_average(self):
        assert classify_rs_rating(59) == "Average"
        assert classify_rs_rating(40) == "Average"

    def test_laggard(self):
        assert classify_rs_rating(39) == "Laggard"
        assert classify_rs_rating(25) == "Laggard"

    def test_weak(self):
        assert classify_rs_rating(24) == "Weak"
        assert classify_rs_rating(10) == "Weak"
        assert classify_rs_rating(0) == "Weak"

    def test_none_returns_weak(self):
        assert classify_rs_rating(None) == "Weak"


# ---------------------------------------------------------------------------
# calculate_leadership (extended)
# ---------------------------------------------------------------------------


class TestCalculateLeadershipExtended:
    def test_legacy_fields_preserved(self):
        stock = _make_price_series(100.0, 0.002, 260)
        bench = _make_price_series(100.0, 0.001, 260)
        result = calculate_leadership(stock, bench)

        # Legacy fields must remain present and numeric.
        assert "stock_52w_performance" in result
        assert "sp500_52w_performance" in result
        assert "relative_performance" in result
        assert "rs_rank_estimate" in result
        assert isinstance(result["stock_52w_performance"], float)
        assert isinstance(result["sp500_52w_performance"], float)

    def test_new_fields_present(self):
        stock = _make_price_series(100.0, 0.002, 260)
        bench = _make_price_series(100.0, 0.001, 260)
        result = calculate_leadership(stock, bench, rs_benchmark="^GSPC")

        new_fields = [
            "rs_3m_return",
            "rs_6m_return",
            "rs_12m_return",
            "benchmark_3m_return",
            "benchmark_6m_return",
            "benchmark_12m_return",
            "rel_3m",
            "rel_6m",
            "rel_12m",
            "weighted_stock_performance",
            "weighted_relative_performance",
            "benchmark_52w_performance",
            "rs_benchmark",
            "rs_benchmark_relative_return",
            "rs_rating",
            "rs_component_score",
            "rs_rank_percentile",
        ]
        for field in new_fields:
            assert field in result, f"Expected new field '{field}' in result"

    def test_rs_benchmark_default(self):
        stock = _make_price_series(100.0, 0.002, 260)
        bench = _make_price_series(100.0, 0.001, 260)
        result = calculate_leadership(stock, bench)
        assert result["rs_benchmark"] == "^GSPC"

    def test_rs_benchmark_custom(self):
        stock = _make_price_series(100.0, 0.002, 260)
        bench = _make_price_series(100.0, 0.001, 260)
        result = calculate_leadership(stock, bench, rs_benchmark="SPY")
        assert result["rs_benchmark"] == "SPY"

    def test_no_benchmark_applies_penalty(self):
        stock = _make_price_series(100.0, 0.002, 260)
        bench = _make_price_series(100.0, 0.001, 260)
        with_bench = calculate_leadership(stock, bench)
        no_bench = calculate_leadership(stock, None)
        # Without a benchmark, the score is reduced (20% penalty in score_leadership).
        assert no_bench["score"] <= with_bench["score"]
        assert no_bench["quality_warning"] is not None

    def test_legacy_sp500_performance_path(self):
        """
        When sp500_performance is supplied (pre-calculated benchmark return), the
        function must take the legacy single-period path and leave multi-period
        fields as None.
        """
        stock = _make_price_series(100.0, 0.002, 260)
        result = calculate_leadership(stock, sp500_performance=10.0)

        assert result["score"] > 0
        assert result["relative_performance"] is not None
        assert result["rs_3m_return"] is None
        assert result["rs_6m_return"] is None
        assert result["rs_12m_return"] is None
        assert result["weighted_relative_performance"] is None

    def test_outperformer_scores_high(self):
        # Stock +0.3%/day, benchmark +0.05%/day over a year => significant outperformance.
        stock = _make_price_series(100.0, 0.003, 260)
        bench = _make_price_series(100.0, 0.0005, 260)
        result = calculate_leadership(stock, bench)
        assert result["score"] >= 90
        assert result["rs_rating"] in ("Market Leader", "Strong")

    def test_60_bars_with_benchmark_uses_legacy_relative(self):
        """
        Regression: when stock and benchmark both have 50-62 bars (multi-period 3m
        window of 63 bars cannot be filled), scoring must fall back to the legacy
        365-day relative performance with has_benchmark=True (not the absolute +
        20% penalty path).
        """
        # 60 bars: shorter than the 63-bar 3m window, so multi-period is fully missing.
        # Stock returns ~+12.6%, benchmark returns ~+5.97% over the window.
        stock = _make_price_series(100.0, 0.002, 60)
        bench = _make_price_series(100.0, 0.001, 60)
        result = calculate_leadership(stock, bench)

        # Multi-period must indeed be empty for this regression to be meaningful.
        assert result["weighted_relative_performance"] is None
        assert result["weighted_stock_performance"] is None
        # Legacy relative must be calculated (benchmark and stock both have >=50 bars).
        assert result["relative_performance"] is not None
        assert result["relative_performance"] > 0  # stock outperforms

        # Compare against the no-benchmark path: with the proper fallback the
        # benchmark-aware score must NOT be reduced by the 20% penalty.
        no_bench = calculate_leadership(stock, None)
        assert result["score"] >= no_bench["score"], (
            "60-bar stock+benchmark should use legacy relative scoring, "
            "not fall through to the absolute + 20% penalty path"
        )


# ---------------------------------------------------------------------------
# screen_canslim CLI flags
# ---------------------------------------------------------------------------


class TestScreenCanslimCLIFlags:
    """
    Verify that the CLI flag parser exposes --rs-benchmark and --disable-rs with
    the expected defaults. We import lazily to avoid loading the FMP client at
    module import time.
    """

    def test_rs_benchmark_default(self):
        import sys

        from screen_canslim import parse_arguments

        argv_backup = sys.argv
        sys.argv = ["screen_canslim.py"]
        try:
            args = parse_arguments()
        finally:
            sys.argv = argv_backup
        assert args.rs_benchmark == "^GSPC"
        assert args.disable_rs is False

    def test_rs_benchmark_custom(self):
        import sys

        from screen_canslim import parse_arguments

        argv_backup = sys.argv
        sys.argv = ["screen_canslim.py", "--rs-benchmark", "SPY"]
        try:
            args = parse_arguments()
        finally:
            sys.argv = argv_backup
        assert args.rs_benchmark == "SPY"

    def test_disable_rs_flag(self):
        import sys

        from screen_canslim import parse_arguments

        argv_backup = sys.argv
        sys.argv = ["screen_canslim.py", "--disable-rs"]
        try:
            args = parse_arguments()
        finally:
            sys.argv = argv_backup
        assert args.disable_rs is True


class TestAnalyzeStockDisableRs:
    """
    When disable_rs=True, analyze_stock should NOT call client.get_historical_prices
    for the per-stock 365-day fetch and L should be a neutral 50 placeholder.
    """

    def test_disable_rs_skips_365d_fetch(self):
        from screen_canslim import analyze_stock

        client = MagicMock()
        client.get_profile.return_value = [
            {"companyName": "Test Corp", "sector": "Technology", "mktCap": 1_000_000_000}
        ]
        client.get_quote.return_value = [{"price": 100.0, "yearHigh": 110.0, "yearLow": 70.0}]
        client.get_income_statement.return_value = [
            {"eps": 1.0, "revenue": 100_000_000, "date": "2024-12-31"}
        ] * 8
        # Per-stock 90-day fetch for S component (still called)
        ninety_day_series = [
            {
                "date": f"2024-{(i // 30) + 1:02d}-{(i % 30) + 1:02d}",
                "close": 100 + i,
                "volume": 1_000_000,
            }
            for i in range(90)
        ]
        client.get_historical_prices.return_value = {"historical": ninety_day_series}
        client.get_institutional_holders.return_value = [
            {"holder": f"Inst {i}", "shares": 1000, "dateReported": "2025-01-01"} for i in range(50)
        ]

        market_data = {
            "score": 80,
            "trend": "uptrend",
            "sp500_price": 5000.0,
            "sp500_ema_50": 4900.0,
            "distance_from_ema_pct": 2.0,
        }

        result = analyze_stock(
            "TEST",
            client,
            market_data,
            rs_benchmark_historical=None,
            rs_benchmark="^GSPC",
            disable_rs=True,
        )

        assert result is not None
        assert result["l_component"]["skipped"] is True
        assert result["l_component"]["score"] == 50
        assert result["l_component"]["rs_rating"] == "Skipped"

        # Verify the only 365-day call (if any) did not happen by inspecting
        # how many distinct days values were requested.
        days_requested = {
            call.kwargs.get("days", call.args[1] if len(call.args) > 1 else None)
            for call in client.get_historical_prices.call_args_list
        }
        assert 365 not in days_requested, (
            f"--disable-rs should not request 365-day history, got days={days_requested}"
        )


# ---------------------------------------------------------------------------
# report_generator (summary table + L row)
# ---------------------------------------------------------------------------


class TestReportGeneratorRSColumn:
    @staticmethod
    def _make_stock_with_rs(rank: int) -> dict:
        return {
            "symbol": f"SYM{rank:02d}",
            "company_name": f"Company {rank}",
            "price": 100.0 + rank,
            "market_cap": 1_000_000_000 * rank,
            "sector": "Technology",
            "composite_score": 90.0 - rank * 0.5,
            "rating": "Strong",
            "rating_description": "Solid across all components",
            "guidance": "Buy",
            "weakest_component": "M",
            "weakest_score": 70,
            "c_component": {"score": 80},
            "a_component": {"score": 75},
            "n_component": {"score": 70},
            "s_component": {"score": 65},
            "l_component": {
                "score": 80,
                "rs_3m_return": 12.4,
                "rs_6m_return": 18.7,
                "rs_12m_return": 44.1,
                "rel_3m": 5.2,
                "rel_6m": 8.3,
                "rel_12m": 22.0,
                "rs_rating": "Strong",
                "rs_rank_percentile": 82,
                "rs_benchmark": "^GSPC",
            },
            "i_component": {"score": 55},
            "m_component": {"score": 70, "trend": "uptrend"},
        }

    def test_summary_table_appears(self):
        results = [self._make_stock_with_rs(i) for i in range(1, 4)]
        metadata = {
            "generated_at": "2025-01-01 00:00:00 UTC",
            "schema_version": "3.1",
            "phase": "3.1 (7 components - FULL CANSLIM with multi-period RS)",
            "components_included": ["C", "A", "N", "S", "L", "I", "M"],
            "candidates_analyzed": 3,
            "screening_options": {"rs_benchmark": "^GSPC", "rs_disabled": False},
            "market_condition": {"trend": "uptrend", "M_score": 80, "warning": None},
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            output_file = f.name

        try:
            generate_markdown_report(results, metadata, output_file)
            with open(output_file) as f:
                content = f.read()

            assert "## Summary Table" in content
            assert "| RS Rating |" in content
            assert "Strong" in content  # rs_rating from fixture
            assert "Schema Version" in content
            # Multi-period RS row
            assert "3m/6m/12m" in content
        finally:
            os.unlink(output_file)

    def test_disable_rs_banner(self):
        results = [self._make_stock_with_rs(1)]
        # Override l_component to simulate a skipped run
        results[0]["l_component"] = {"score": 50, "skipped": True, "rs_rating": "Skipped"}
        metadata = {
            "generated_at": "2025-01-01 00:00:00 UTC",
            "schema_version": "3.1",
            "phase": "3.1 (7 components - FULL CANSLIM with multi-period RS)",
            "components_included": ["C", "A", "N", "S", "L", "I", "M"],
            "candidates_analyzed": 1,
            "screening_options": {"rs_benchmark": "^GSPC", "rs_disabled": True},
            "market_condition": {"trend": "uptrend", "M_score": 80, "warning": None},
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            output_file = f.name
        try:
            generate_markdown_report(results, metadata, output_file)
            with open(output_file) as f:
                content = f.read()
            assert "RS Disabled" in content
            assert "Skipped via --disable-rs" in content
        finally:
            os.unlink(output_file)


# ---------------------------------------------------------------------------
# Sanity check that DEFAULT_PERIODS_DAYS is consistent with the spec.
# ---------------------------------------------------------------------------


def test_default_periods_days():
    assert DEFAULT_PERIODS_DAYS == {"3m": 63, "6m": 126, "12m": 252}
