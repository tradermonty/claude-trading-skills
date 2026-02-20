#!/usr/bin/env python3
"""
Tests for CANSLIM screener bug fixes.

Covers:
- B1: M component EMA calculation (should use real historical data, not fallback)
- B2: I component condition ordering (extreme < 10% should score 20, not 40)
- B3: I component mktCap key (FMP API returns "mktCap", not "marketCap")
- C1: report_generator --top parameter (should respect len(results), not hardcode 20)
"""

import os
import sys
import json
import tempfile

import pytest

# Add scripts directories to path
SCRIPTS_DIR = os.path.join(os.path.dirname(__file__), '..', 'scripts')
CALCULATORS_DIR = os.path.join(SCRIPTS_DIR, 'calculators')
sys.path.insert(0, SCRIPTS_DIR)
sys.path.insert(0, CALCULATORS_DIR)

from calculators.market_calculator import calculate_market_direction, calculate_ema
from calculators.institutional_calculator import (
    calculate_institutional_sponsorship,
    score_institutional_sponsorship,
)
from report_generator import generate_markdown_report


# ---------------------------------------------------------------------------
# B1: M Component - EMA calculation with real historical data
# ---------------------------------------------------------------------------

class TestMComponentEMA:
    """Verify that calculate_market_direction uses real historical prices
    instead of the sp500_price * 0.98 fallback."""

    @staticmethod
    def _generate_declining_prices(start_price, days, daily_decline_pct=0.15):
        """Generate a list of declining daily prices (most recent first)."""
        prices = []
        price = start_price
        for i in range(days):
            prices.append({
                "date": f"2025-01-{days - i:02d}",
                "close": round(price, 2),
                "open": round(price + 1, 2),
                "high": round(price + 2, 2),
                "low": round(price - 1, 2),
                "volume": 3_000_000_000,
            })
            price *= (1 - daily_decline_pct / 100)
        return prices

    @staticmethod
    def _generate_rising_prices(start_price, days, daily_rise_pct=0.15):
        """Generate a list of rising daily prices (most recent first)."""
        prices = []
        price = start_price
        for i in range(days):
            prices.append({
                "date": f"2025-01-{days - i:02d}",
                "close": round(price, 2),
                "open": round(price - 1, 2),
                "high": round(price + 1, 2),
                "low": round(price - 2, 2),
                "volume": 3_000_000_000,
            })
            price *= (1 + daily_rise_pct / 100)
        return prices

    def test_ema_calculation_with_sufficient_data(self):
        """EMA should be computed from historical data when >= 50 data points."""
        # 60 days of constant price = 100 -> EMA should be ~100
        prices = [100.0] * 60
        ema = calculate_ema(prices, period=50)
        assert abs(ema - 100.0) < 0.01, f"EMA of constant prices should be ~100, got {ema}"

    def test_bear_market_detection_with_historical_data(self):
        """When S&P 500 is well below its 50-EMA, M score should be 0-20."""
        # Build 60 days of prices that were high (~5000) and then crashed
        # Prices declined steadily so EMA remains high relative to current price
        historical = []
        price = 5000.0
        for i in range(60):
            historical.append({"close": round(price, 2)})
            price *= 0.995  # ~0.5% daily decline

        # Current price is the most recent (lowest) ~3700
        current_price = historical[0]["close"]  # most recent = lowest after decline
        # Actually with 0.5% daily decline over 60 days: 5000 * 0.995^60 ≈ 3700

        sp500_quote = {"price": current_price}
        result = calculate_market_direction(
            sp500_quote=sp500_quote,
            sp500_prices=historical,
            vix_quote={"price": 32.0},  # High VIX = panic
        )

        assert result["score"] == 0, (
            f"Bear market (price well below 50-EMA) should score 0, got {result['score']}. "
            f"distance_from_ema_pct={result.get('distance_from_ema_pct')}"
        )

    def test_fallback_always_gives_high_score(self):
        """Without historical data, fallback EMA = price * 0.98, always ~+2% -> strong_uptrend."""
        sp500_quote = {"price": 5000.0}
        result = calculate_market_direction(
            sp500_quote=sp500_quote,
            sp500_prices=None,  # No historical data -> fallback
            vix_quote={"price": 14.0},
        )
        # Fallback: EMA = 5000 * 0.98 = 4900, distance = +2.04% -> strong_uptrend
        assert result["score"] >= 90, (
            f"Fallback (no historical data) should give high score, got {result['score']}"
        )
        assert result["trend"] == "strong_uptrend"

    def test_real_ema_differs_from_fallback(self):
        """With real declining prices, EMA should differ from the naive 0.98 fallback."""
        # Build prices that start at 5500 and decline to 5000
        historical = []
        price = 5500.0
        for i in range(60):
            historical.append({"close": round(price, 2)})
            price -= 8.33  # Decline from 5500 to ~5000

        current_price = historical[0]["close"]  # Most recent = 5500
        sp500_quote = {"price": current_price}

        # With real data
        result_real = calculate_market_direction(
            sp500_quote=sp500_quote,
            sp500_prices=historical,
        )

        # Without real data (fallback)
        result_fallback = calculate_market_direction(
            sp500_quote=sp500_quote,
            sp500_prices=None,
        )

        # The EMA values should be different
        real_ema = result_real.get("sp500_ema_50")
        fallback_ema = result_fallback.get("sp500_ema_50")

        assert real_ema != fallback_ema, (
            f"Real EMA ({real_ema}) should differ from fallback ({fallback_ema})"
        )


# ---------------------------------------------------------------------------
# B2: I Component - Condition ordering in score_institutional_sponsorship
# ---------------------------------------------------------------------------

class TestIComponentConditionOrdering:
    """Verify that extreme ownership ranges (<10% or >90%) score 20,
    not 40 (which would happen if the <20% check catches them first)."""

    def test_extreme_low_ownership_scores_20(self):
        """ownership_pct=5 should score 20 (extreme), not 40 (suboptimal)."""
        score = score_institutional_sponsorship(
            num_holders=10,
            ownership_pct=5.0,
            superinvestor_present=False,
            quality_warning=None,
        )
        assert score == 20, (
            f"Extreme low ownership (5%) should score 20, got {score}"
        )

    def test_extreme_high_ownership_scores_20(self):
        """ownership_pct=95 should score 20 (extreme), not 40 (suboptimal)."""
        score = score_institutional_sponsorship(
            num_holders=200,
            ownership_pct=95.0,
            superinvestor_present=False,
            quality_warning=None,
        )
        assert score == 20, (
            f"Extreme high ownership (95%) should score 20, got {score}"
        )

    def test_suboptimal_ownership_scores_40(self):
        """ownership_pct=15 should score 40 (suboptimal, between 10-20%)."""
        score = score_institutional_sponsorship(
            num_holders=10,
            ownership_pct=15.0,
            superinvestor_present=False,
            quality_warning=None,
        )
        assert score == 40, (
            f"Suboptimal ownership (15%) should score 40, got {score}"
        )

    def test_suboptimal_high_ownership_scores_40(self):
        """ownership_pct=85 should score 40 (suboptimal, between 80-90%)."""
        score = score_institutional_sponsorship(
            num_holders=200,
            ownership_pct=85.0,
            superinvestor_present=False,
            quality_warning=None,
        )
        assert score == 40, (
            f"Suboptimal high ownership (85%) should score 40, got {score}"
        )

    def test_boundary_10pct_is_extreme(self):
        """ownership_pct=9.99 should score 20 (extreme: < 10)."""
        score = score_institutional_sponsorship(
            num_holders=10,
            ownership_pct=9.99,
            superinvestor_present=False,
            quality_warning=None,
        )
        assert score == 20, (
            f"Boundary (9.99%) should score 20, got {score}"
        )

    def test_boundary_90pct_is_extreme(self):
        """ownership_pct=90.01 should score 20 (extreme: > 90)."""
        score = score_institutional_sponsorship(
            num_holders=200,
            ownership_pct=90.01,
            superinvestor_present=False,
            quality_warning=None,
        )
        assert score == 20, (
            f"Boundary (90.01%) should score 20, got {score}"
        )


# ---------------------------------------------------------------------------
# B3: I Component - mktCap key from FMP profile
# ---------------------------------------------------------------------------

class TestIComponentMktCapKey:
    """Verify that institutional_calculator handles both 'mktCap' and 'marketCap' keys."""

    def _make_holders(self, count, shares_each=1_000_000):
        """Create a list of dummy institutional holders."""
        return [
            {"holder": f"Institution {i}", "shares": shares_each, "dateReported": "2025-01-01", "change": 0}
            for i in range(count)
        ]

    def test_mktCap_key_calculates_shares_outstanding(self):
        """Profile with 'mktCap' (FMP format) should calculate shares_outstanding correctly."""
        holders = self._make_holders(60, shares_each=500_000)
        profile = {"mktCap": 1_000_000_000, "price": 100.0}  # 1B / 100 = 10M shares

        result = calculate_institutional_sponsorship(
            institutional_holders=holders,
            profile=profile,
            symbol="TEST",
            use_finviz_fallback=False,
        )

        # shares_outstanding = mktCap / price = 1e9 / 100 = 10,000,000
        assert result["shares_outstanding"] == 10_000_000, (
            f"Expected shares_outstanding=10M, got {result['shares_outstanding']}"
        )
        # ownership_pct = (60 * 500_000) / 10_000_000 * 100 = 300%
        # This is extreme but the point is that shares_outstanding is calculated
        assert result["ownership_pct"] is not None, (
            "ownership_pct should be calculated when mktCap is available"
        )

    def test_marketCap_key_also_works(self):
        """Profile with 'marketCap' (alternative format) should also work."""
        holders = self._make_holders(60, shares_each=500_000)
        profile = {"marketCap": 2_000_000_000, "price": 200.0}  # 2B / 200 = 10M shares

        result = calculate_institutional_sponsorship(
            institutional_holders=holders,
            profile=profile,
            symbol="TEST",
            use_finviz_fallback=False,
        )

        assert result["shares_outstanding"] == 10_000_000, (
            f"Expected shares_outstanding=10M with marketCap key, got {result['shares_outstanding']}"
        )

    def test_sharesOutstanding_takes_priority(self):
        """If profile has sharesOutstanding directly, it should be used first."""
        holders = self._make_holders(60, shares_each=500_000)
        profile = {
            "sharesOutstanding": 5_000_000,
            "mktCap": 1_000_000_000,
            "price": 100.0,
        }

        result = calculate_institutional_sponsorship(
            institutional_holders=holders,
            profile=profile,
            symbol="TEST",
            use_finviz_fallback=False,
        )

        assert result["shares_outstanding"] == 5_000_000, (
            f"sharesOutstanding should take priority, got {result['shares_outstanding']}"
        )


# ---------------------------------------------------------------------------
# C1: report_generator --top parameter
# ---------------------------------------------------------------------------

class TestReportGeneratorTopParameter:
    """Verify that generate_markdown_report outputs all results, not just 20."""

    @staticmethod
    def _make_stock(rank):
        """Create a minimal stock result dict."""
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
            "l_component": {"score": 60},
            "i_component": {"score": 55},
            "m_component": {"score": 70, "trend": "uptrend"},
        }

    def test_30_results_all_appear_in_report(self):
        """When 30 results are passed, all 30 should appear in the Markdown report."""
        results = [self._make_stock(i) for i in range(1, 31)]

        metadata = {
            "generated_at": "2025-01-01 00:00:00 UTC",
            "phase": "3 (7 components - FULL CANSLIM)",
            "components_included": ["C", "A", "N", "S", "L", "I", "M"],
            "candidates_analyzed": 30,
            "market_condition": {
                "trend": "uptrend",
                "M_score": 80,
                "warning": None,
            },
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            output_file = f.name

        try:
            generate_markdown_report(results, metadata, output_file)

            with open(output_file, 'r') as f:
                content = f.read()

            # Check that the header says "Top 30" not "Top 20"
            assert "Top 30" in content, (
                f"Report header should say 'Top 30', found: "
                + [line for line in content.split('\n') if 'Top' in line and 'CANSLIM' in line][0]
            )

            # Check that SYM30 (the 30th stock) appears in the report
            assert "SYM30" in content, (
                "30th stock (SYM30) should appear in the report but was not found"
            )

            # Count the number of stock entries (each starts with "### N.")
            import re
            stock_entries = re.findall(r'^### \d+\.', content, re.MULTILINE)
            assert len(stock_entries) == 30, (
                f"Expected 30 stock entries, found {len(stock_entries)}"
            )
        finally:
            os.unlink(output_file)

    def test_5_results_shows_5(self):
        """When only 5 results, report should show 5 not truncate."""
        results = [self._make_stock(i) for i in range(1, 6)]

        metadata = {
            "generated_at": "2025-01-01 00:00:00 UTC",
            "phase": "3 (7 components - FULL CANSLIM)",
            "components_included": ["C", "A", "N", "S", "L", "I", "M"],
            "candidates_analyzed": 5,
            "market_condition": {"trend": "uptrend", "M_score": 80, "warning": None},
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            output_file = f.name

        try:
            generate_markdown_report(results, metadata, output_file)

            with open(output_file, 'r') as f:
                content = f.read()

            assert "Top 5" in content, "Report header should say 'Top 5'"

            import re
            stock_entries = re.findall(r'^### \d+\.', content, re.MULTILINE)
            assert len(stock_entries) == 5, (
                f"Expected 5 stock entries, found {len(stock_entries)}"
            )
        finally:
            os.unlink(output_file)


# ---------------------------------------------------------------------------
# Integration: ^GSPC/SPY scale mismatch detection
# ---------------------------------------------------------------------------

class TestBenchmarkScaleConsistency:
    """Verify that M component rejects or handles mixed price scales.

    The ^GSPC index trades at ~5000 while the SPY ETF trades at ~500.
    If the quote comes from ^GSPC and historical data comes from SPY,
    the EMA will be ~500 and distance_from_ema_pct will be ~+900%,
    giving a falsely bullish M score.
    """

    def test_mixed_scale_produces_extreme_distance(self):
        """Demonstrate the bug: ^GSPC quote + SPY historical = +900% distance."""
        # Simulated ^GSPC quote (index level ~5000)
        gspc_quote = {"price": 5000.0}

        # Simulated SPY historical (ETF level ~500)
        spy_historical = [{"close": 500.0 + i * 0.1} for i in range(60)]

        result = calculate_market_direction(
            sp500_quote=gspc_quote,
            sp500_prices=spy_historical,
            vix_quote={"price": 15.0},
        )

        # This demonstrates the scale mismatch problem:
        # EMA(~500) vs price(5000) → distance ≈ +900%
        # Any distance > 20% is unreasonable and indicates a data problem
        distance = result.get("distance_from_ema_pct", 0)
        assert abs(distance) > 100, (
            f"Mixed ^GSPC/SPY scales should produce extreme distance, got {distance:.1f}%"
        )
        # This will always be "strong_uptrend" with score 90-100 - clearly wrong
        assert result["score"] >= 90, (
            f"Mixed scales should produce falsely bullish score (>=90), got {result['score']}"
        )

    def test_same_scale_gspc_produces_reasonable_distance(self):
        """With ^GSPC for both quote and historical, distance is reasonable."""
        # Both at ^GSPC scale (~5000)
        gspc_quote = {"price": 5100.0}

        # Slight uptrend: prices from 4900 to 5100 over 60 days
        gspc_historical = []
        for i in range(60):
            price = 4900.0 + (200.0 / 60) * i
            gspc_historical.append({"close": round(price, 2)})

        result = calculate_market_direction(
            sp500_quote=gspc_quote,
            sp500_prices=gspc_historical,
            vix_quote={"price": 15.0},
        )

        distance = result.get("distance_from_ema_pct", 0)
        # With same-scale data, distance should be modest (< 20%)
        assert abs(distance) < 20, (
            f"Same-scale ^GSPC data should produce reasonable distance (<20%), got {distance:.1f}%"
        )

    def test_same_scale_spy_produces_reasonable_distance(self):
        """With SPY for both quote and historical, distance is also reasonable."""
        # Both at SPY scale (~500)
        spy_quote = {"price": 510.0}

        spy_historical = []
        for i in range(60):
            price = 490.0 + (20.0 / 60) * i
            spy_historical.append({"close": round(price, 2)})

        result = calculate_market_direction(
            sp500_quote=spy_quote,
            sp500_prices=spy_historical,
            vix_quote={"price": 15.0},
        )

        distance = result.get("distance_from_ema_pct", 0)
        assert abs(distance) < 20, (
            f"Same-scale SPY data should produce reasonable distance (<20%), got {distance:.1f}%"
        )

    def test_screen_canslim_uses_gspc_for_historical(self):
        """Verify that screen_canslim.py uses ^GSPC (not SPY) for historical data."""
        import re
        screen_file = os.path.join(SCRIPTS_DIR, "screen_canslim.py")

        with open(screen_file, "r") as f:
            content = f.read()

        # Find all get_historical_prices calls for S&P 500 / market data
        hist_calls = re.findall(
            r'client\.get_historical_prices\(\s*["\']([^"\']+)["\']',
            content,
        )

        # Find the quote call for S&P 500
        quote_calls = re.findall(
            r'client\.get_quote\(\s*["\'](\^GSPC[^"\']*)["\']',
            content,
        )

        assert len(quote_calls) >= 1, "Should have at least one ^GSPC quote call"

        # The historical call for market data should use ^GSPC, not SPY
        market_hist_tickers = [t for t in hist_calls if t in ("^GSPC", "SPY")]
        assert "^GSPC" in market_hist_tickers, (
            f"Historical prices for market data should use ^GSPC, "
            f"found tickers: {market_hist_tickers}"
        )
        assert "SPY" not in market_hist_tickers, (
            f"Historical prices should NOT use SPY (scale mismatch with ^GSPC quote), "
            f"found tickers: {market_hist_tickers}"
        )
