"""Tests for representative_stock_selector module."""

import time
from unittest.mock import MagicMock, patch

import pytest
from representative_stock_selector import (
    _MAX_CONSECUTIVE_FAILURES,
    RepresentativeStockSelector,
    _parse_change,
    _parse_market_cap,
    _parse_volume,
)

# ---------------------------------------------------------------------------
# Parse helpers
# ---------------------------------------------------------------------------


class TestParseMarketCap:
    def test_trillions(self):
        assert _parse_market_cap("2.8T") == 2_800_000_000_000

    def test_billions(self):
        assert _parse_market_cap("150B") == 150_000_000_000

    def test_millions(self):
        assert _parse_market_cap("500M") == 500_000_000

    def test_none_returns_zero(self):
        assert _parse_market_cap(None) == 0

    def test_dash_returns_zero(self):
        assert _parse_market_cap("-") == 0

    def test_numeric_passthrough(self):
        assert _parse_market_cap(1_000_000) == 1_000_000

    def test_float_passthrough(self):
        assert _parse_market_cap(1.5e9) == 1_500_000_000


class TestParseChange:
    def test_percent_string(self):
        assert _parse_change("12.50%") == pytest.approx(12.50)

    def test_negative_percent(self):
        assert _parse_change("-3.20%") == pytest.approx(-3.20)

    def test_float_fraction(self):
        # finvizfinance returns 0.125 meaning 12.5%
        assert _parse_change(0.125) == pytest.approx(12.5)

    def test_negative_float_fraction(self):
        assert _parse_change(-0.032) == pytest.approx(-3.2)

    def test_already_float_large(self):
        # abs > 1 means already in percent form
        assert _parse_change(12.5) == pytest.approx(12.5)

    def test_negative_already_float_large(self):
        assert _parse_change(-5.3) == pytest.approx(-5.3)

    def test_dash_returns_none(self):
        assert _parse_change("-") is None

    def test_none_returns_none(self):
        assert _parse_change(None) is None


class TestParseVolume:
    def test_comma_string(self):
        assert _parse_volume("1,234,567") == 1234567

    def test_int_passthrough(self):
        assert _parse_volume(1234567) == 1234567

    def test_float_passthrough(self):
        assert _parse_volume(1234567.0) == 1234567

    def test_m_suffix(self):
        assert _parse_volume("1.2M") == 1200000

    def test_dash_returns_none(self):
        assert _parse_volume("-") is None

    def test_none_returns_none(self):
        assert _parse_volume(None) is None


# ---------------------------------------------------------------------------
# Composite score
# ---------------------------------------------------------------------------


class TestCompositeScore:
    def _make_selector(self):
        return RepresentativeStockSelector()

    def test_ranks_by_composite_not_market_cap_alone(self):
        """A stock with large market_cap but low change/volume is not #1."""
        sel = self._make_selector()
        stocks = [
            {
                "symbol": "BIG",
                "source": "finviz_public",
                "market_cap": 2_000_000_000_000,
                "change": 1.0,
                "volume": 100_000,
                "matched_industries": ["X"],
                "reasons": [],
            },
            {
                "symbol": "SMALL",
                "source": "finviz_public",
                "market_cap": 10_000_000_000,
                "change": 20.0,
                "volume": 5_000_000,
                "matched_industries": ["X"],
                "reasons": [],
            },
        ]
        scored = sel._compute_composite_score(stocks, is_bearish=False)
        # SMALL ranks #1: cap_rank=2 (0.4*0) but change_rank=1 (0.3*1) + vol_rank=1 (0.3*1)
        # BIG ranks #2: cap_rank=1 (0.4*1) but change_rank=2 (0.3*0) + vol_rank=2 (0.3*0)
        assert scored[0]["symbol"] == "SMALL"
        assert scored[1]["symbol"] == "BIG"
        assert scored[0]["composite_score"] > scored[1]["composite_score"]

    def test_weights_are_applied(self):
        """composite = 0.4 * cap_rank + 0.3 * change_rank + 0.3 * vol_rank"""
        sel = self._make_selector()
        stocks = [
            {
                "symbol": "A",
                "source": "finviz_public",
                "market_cap": 100_000_000_000,
                "change": 10.0,
                "volume": 1_000_000,
                "matched_industries": [],
                "reasons": [],
            },
        ]
        scored = sel._compute_composite_score(stocks, is_bearish=False)
        # Single stock => rank 1/1 => score = 0.4*1 + 0.3*1 + 0.3*1 = 1.0
        assert scored[0]["composite_score"] == pytest.approx(1.0)

    def test_bearish_uses_abs_change(self):
        """is_bearish=True => abs(change) ranks descending."""
        sel = self._make_selector()
        stocks = [
            {
                "symbol": "DROP",
                "source": "finviz_public",
                "market_cap": 50_000_000_000,
                "change": -15.0,
                "volume": 1_000_000,
                "matched_industries": [],
                "reasons": [],
            },
            {
                "symbol": "FLAT",
                "source": "finviz_public",
                "market_cap": 50_000_000_000,
                "change": -1.0,
                "volume": 1_000_000,
                "matched_industries": [],
                "reasons": [],
            },
        ]
        scored = sel._compute_composite_score(stocks, is_bearish=True)
        # DROP has larger abs(change), should score higher
        drop = next(s for s in scored if s["symbol"] == "DROP")
        flat = next(s for s in scored if s["symbol"] == "FLAT")
        assert drop["composite_score"] > flat["composite_score"]

    def test_missing_fields_renormalize(self):
        """change/volume=None => re-normalize with available metrics only."""
        sel = self._make_selector()
        stocks = [
            {
                "symbol": "A",
                "source": "etf_holdings",
                "market_cap": 100_000_000_000,
                "change": None,
                "volume": None,
                "matched_industries": [],
                "reasons": [],
            },
            {
                "symbol": "B",
                "source": "etf_holdings",
                "market_cap": 50_000_000_000,
                "change": None,
                "volume": None,
                "matched_industries": [],
                "reasons": [],
            },
        ]
        scored = sel._compute_composite_score(stocks, is_bearish=False)
        # Should not crash; A has bigger cap so should rank higher
        assert scored[0]["symbol"] == "A"
        assert scored[0]["composite_score"] > scored[1]["composite_score"]

    def test_empty_input(self):
        sel = self._make_selector()
        assert sel._compute_composite_score([], is_bearish=False) == []


# ---------------------------------------------------------------------------
# Merge and rank
# ---------------------------------------------------------------------------


class TestMergeAndRank:
    def _make_selector(self):
        return RepresentativeStockSelector()

    def test_deduplicates_by_symbol(self):
        sel = self._make_selector()
        candidates = [
            {
                "symbol": "NVDA",
                "source": "finviz_public",
                "market_cap": 100,
                "matched_industries": ["Semi"],
                "reasons": ["reason1"],
                "composite_score": 0.9,
            },
            {
                "symbol": "NVDA",
                "source": "finviz_public",
                "market_cap": 100,
                "matched_industries": ["Hardware"],
                "reasons": ["reason2"],
                "composite_score": 0.8,
            },
        ]
        result = sel._merge_and_rank(candidates, max_stocks=10)
        assert len(result) == 1
        assert result[0]["symbol"] == "NVDA"

    def test_merges_matched_industries_on_duplicate(self):
        sel = self._make_selector()
        candidates = [
            {
                "symbol": "NVDA",
                "source": "finviz_public",
                "market_cap": 100,
                "matched_industries": ["Semi"],
                "reasons": [],
                "composite_score": 0.9,
            },
            {
                "symbol": "NVDA",
                "source": "finviz_public",
                "market_cap": 100,
                "matched_industries": ["Hardware"],
                "reasons": [],
                "composite_score": 0.8,
            },
        ]
        result = sel._merge_and_rank(candidates, max_stocks=10)
        assert "Semi" in result[0]["matched_industries"]
        assert "Hardware" in result[0]["matched_industries"]

    def test_accumulates_reasons_on_duplicate(self):
        sel = self._make_selector()
        candidates = [
            {
                "symbol": "X",
                "source": "finviz_public",
                "market_cap": 0,
                "matched_industries": [],
                "reasons": ["r1"],
                "composite_score": 0.5,
            },
            {
                "symbol": "X",
                "source": "finviz_public",
                "market_cap": 0,
                "matched_industries": [],
                "reasons": ["r2"],
                "composite_score": 0.4,
            },
        ]
        result = sel._merge_and_rank(candidates, max_stocks=10)
        assert "r1" in result[0]["reasons"]
        assert "r2" in result[0]["reasons"]

    def test_sorts_by_composite_score_descending(self):
        sel = self._make_selector()
        candidates = [
            {
                "symbol": "A",
                "source": "s",
                "market_cap": 0,
                "matched_industries": [],
                "reasons": [],
                "composite_score": 0.3,
            },
            {
                "symbol": "B",
                "source": "s",
                "market_cap": 0,
                "matched_industries": [],
                "reasons": [],
                "composite_score": 0.9,
            },
            {
                "symbol": "C",
                "source": "s",
                "market_cap": 0,
                "matched_industries": [],
                "reasons": [],
                "composite_score": 0.6,
            },
        ]
        result = sel._merge_and_rank(candidates, max_stocks=10)
        assert [r["symbol"] for r in result] == ["B", "C", "A"]

    def test_respects_max_stocks(self):
        sel = self._make_selector()
        candidates = [
            {
                "symbol": f"S{i}",
                "source": "s",
                "market_cap": 0,
                "matched_industries": [],
                "reasons": [],
                "composite_score": i * 0.1,
            }
            for i in range(20)
        ]
        result = sel._merge_and_rank(candidates, max_stocks=5)
        assert len(result) == 5

    def test_empty_input(self):
        sel = self._make_selector()
        assert sel._merge_and_rank([], max_stocks=10) == []

    def test_duplicate_uses_max_composite_score(self):
        sel = self._make_selector()
        candidates = [
            {
                "symbol": "X",
                "source": "s",
                "market_cap": 0,
                "matched_industries": [],
                "reasons": [],
                "composite_score": 0.3,
            },
            {
                "symbol": "X",
                "source": "s",
                "market_cap": 0,
                "matched_industries": [],
                "reasons": [],
                "composite_score": 0.9,
            },
        ]
        result = sel._merge_and_rank(candidates, max_stocks=10)
        assert result[0]["composite_score"] == 0.9


# ---------------------------------------------------------------------------
# select_stocks fallback chain
# ---------------------------------------------------------------------------


def _mock_finviz_public_stocks(industry, limit, is_bearish):
    """Return fake stocks for FINVIZ public."""
    return [
        {
            "symbol": f"{industry[:3].upper()}{i}",
            "source": "finviz_public",
            "market_cap": (10 - i) * 1_000_000_000,
            "change": 5.0 + i,
            "volume": 1_000_000,
            "matched_industries": [industry],
            "reasons": [f"Top in {industry}"],
        }
        for i in range(min(limit, 8))
    ]


def _mock_finviz_elite_stocks(industry, limit, is_bearish):
    """Return fake stocks for FINVIZ elite."""
    return [
        {
            "symbol": f"E{industry[:2].upper()}{i}",
            "source": "finviz_elite",
            "market_cap": (10 - i) * 2_000_000_000,
            "change": 8.0 + i,
            "volume": 2_000_000,
            "matched_industries": [industry],
            "reasons": [f"Elite top in {industry}"],
        }
        for i in range(min(limit, 8))
    ]


def _mock_etf_holdings(etf, limit):
    """Return fake ETF holdings."""
    return [
        {
            "symbol": f"ETF{etf}{i}",
            "source": "etf_holdings",
            "market_cap": (5 - i) * 500_000_000,
            "change": None,
            "volume": None,
            "matched_industries": [],
            "reasons": [f"Held by {etf}"],
        }
        for i in range(min(limit, 5))
    ]


class TestSelectStocks:
    def test_finviz_elite_priority(self):
        """finviz_mode=elite + key => Elite is used."""
        sel = RepresentativeStockSelector(
            finviz_elite_key="test_key",
            finviz_mode="elite",
        )
        with (
            patch.object(sel, "_fetch_finviz_elite", side_effect=_mock_finviz_elite_stocks),
            patch.object(sel, "_fetch_finviz_public", side_effect=_mock_finviz_public_stocks),
            patch.object(sel, "_rate_limit"),
        ):
            theme = {
                "direction": "bullish",
                "matching_industries": [{"name": "Gold"}],
                "proxy_etfs": [],
                "static_stocks": [],
            }
            result = sel.select_stocks(theme, max_stocks=5)
            assert len(result) > 0
            assert all(d["source"] == "finviz_elite" for d in result)

    def test_finviz_mode_public_ignores_elite_key(self):
        """finviz_mode=public + key => Public is used, not Elite."""
        sel = RepresentativeStockSelector(
            finviz_elite_key="test_key",
            finviz_mode="public",
        )
        with (
            patch.object(
                sel, "_fetch_finviz_elite", side_effect=_mock_finviz_elite_stocks
            ) as elite_mock,
            patch.object(sel, "_fetch_finviz_public", side_effect=_mock_finviz_public_stocks),
            patch.object(sel, "_rate_limit"),
        ):
            theme = {
                "direction": "bullish",
                "matching_industries": [{"name": "Gold"}],
                "proxy_etfs": [],
                "static_stocks": [],
            }
            result = sel.select_stocks(theme, max_stocks=5)
            elite_mock.assert_not_called()
            assert all(d["source"] == "finviz_public" for d in result)

    def test_finviz_public_fallback(self):
        """No elite key => public screener."""
        sel = RepresentativeStockSelector()
        with (
            patch.object(sel, "_fetch_finviz_public", side_effect=_mock_finviz_public_stocks),
            patch.object(sel, "_rate_limit"),
        ):
            theme = {
                "direction": "bullish",
                "matching_industries": [{"name": "Gold"}],
                "proxy_etfs": [],
                "static_stocks": [],
            }
            result = sel.select_stocks(theme, max_stocks=5)
            assert len(result) > 0
            assert all(d["source"] == "finviz_public" for d in result)

    def test_etf_holdings_supplement(self):
        """FINVIZ returns few stocks => ETF holdings supplement."""
        sel = RepresentativeStockSelector(fmp_api_key="test_key")

        def empty_finviz(industry, limit, is_bearish):
            return []

        with (
            patch.object(sel, "_fetch_finviz_public", side_effect=empty_finviz),
            patch.object(sel, "_fetch_etf_holdings", side_effect=_mock_etf_holdings),
            patch.object(sel, "_rate_limit"),
        ):
            theme = {
                "direction": "bullish",
                "matching_industries": [{"name": "Gold"}],
                "proxy_etfs": ["GDX", "GLD"],
                "static_stocks": [],
            }
            result = sel.select_stocks(theme, max_stocks=5)
            assert len(result) > 0
            assert any(d["source"] == "etf_holdings" for d in result)

    def test_static_final_fallback(self):
        """All sources fail => static_stocks."""
        sel = RepresentativeStockSelector()

        def fail_finviz(industry, limit, is_bearish):
            return []

        with (
            patch.object(sel, "_fetch_finviz_public", side_effect=fail_finviz),
            patch.object(sel, "_rate_limit"),
        ):
            theme = {
                "direction": "bullish",
                "matching_industries": [{"name": "Gold"}],
                "proxy_etfs": [],
                "static_stocks": ["NEM", "GOLD", "AEM"],
            }
            result = sel.select_stocks(theme, max_stocks=5)
            assert len(result) == 3
            assert all(d["source"] == "static" for d in result)
            assert [d["symbol"] for d in result] == ["NEM", "GOLD", "AEM"]

    def test_vertical_theme_gets_stocks(self):
        """Vertical theme (static_stocks=[]) gets stocks from FINVIZ."""
        sel = RepresentativeStockSelector()
        with (
            patch.object(sel, "_fetch_finviz_public", side_effect=_mock_finviz_public_stocks),
            patch.object(sel, "_rate_limit"),
        ):
            theme = {
                "direction": "bullish",
                "matching_industries": [
                    {"name": "Gold"},
                    {"name": "Silver"},
                    {"name": "Copper"},
                ],
                "proxy_etfs": [],
                "static_stocks": [],
            }
            result = sel.select_stocks(theme, max_stocks=10)
            assert len(result) > 0

    def test_bearish_theme_uses_month_down_filter(self):
        """Bearish theme passes is_bearish=True to fetch methods."""
        sel = RepresentativeStockSelector()
        calls = []

        def track_finviz(industry, limit, is_bearish):
            calls.append(is_bearish)
            return _mock_finviz_public_stocks(industry, limit, is_bearish)

        with (
            patch.object(sel, "_fetch_finviz_public", side_effect=track_finviz),
            patch.object(sel, "_rate_limit"),
        ):
            theme = {
                "direction": "bearish",
                "matching_industries": [{"name": "Retail"}],
                "proxy_etfs": [],
                "static_stocks": [],
            }
            sel.select_stocks(theme, max_stocks=5)
            assert all(c is True for c in calls)

    def test_bearish_composite_ranks_by_abs_change(self):
        """Bearish theme: abs(change) ranks stocks by drop magnitude."""
        sel = RepresentativeStockSelector()

        def bearish_stocks(industry, limit, is_bearish):
            return [
                {
                    "symbol": "BIG_DROP",
                    "source": "finviz_public",
                    "market_cap": 10_000_000_000,
                    "change": -20.0,
                    "volume": 1_000_000,
                    "matched_industries": [industry],
                    "reasons": [],
                },
                {
                    "symbol": "SMALL_DROP",
                    "source": "finviz_public",
                    "market_cap": 10_000_000_000,
                    "change": -2.0,
                    "volume": 1_000_000,
                    "matched_industries": [industry],
                    "reasons": [],
                },
            ]

        with (
            patch.object(sel, "_fetch_finviz_public", side_effect=bearish_stocks),
            patch.object(sel, "_rate_limit"),
        ):
            theme = {
                "direction": "bearish",
                "matching_industries": [{"name": "Retail"}],
                "proxy_etfs": [],
                "static_stocks": [],
            }
            result = sel.select_stocks(theme, max_stocks=5)
            assert result[0]["symbol"] == "BIG_DROP"

    def test_max_per_industry_quota(self):
        """Each industry contributes at most max_per_industry in 1st pass.

        With max_per_industry=2 and max_stocks=4 (== 2 industries * 2),
        no 2nd pass occurs, so exactly 4 stocks are returned with each
        industry providing exactly 2.
        """
        sel = RepresentativeStockSelector(max_per_industry=2)

        def distinct_stocks(industry, limit, is_bearish):
            """Return stocks with industry-unique prefixes."""
            prefix = industry[:3].upper()
            return [
                {
                    "symbol": f"{prefix}{i}",
                    "source": "finviz_public",
                    "market_cap": (10 - i) * 1_000_000_000,
                    "change": 5.0,
                    "volume": 1_000_000,
                    "matched_industries": [industry],
                    "reasons": [],
                }
                for i in range(8)
            ]

        with (
            patch.object(sel, "_fetch_finviz_public", side_effect=distinct_stocks),
            patch.object(sel, "_rate_limit"),
        ):
            theme = {
                "direction": "bullish",
                "matching_industries": [
                    {"name": "Gold"},
                    {"name": "Silver"},
                ],
                "proxy_etfs": [],
                "static_stocks": [],
            }
            result = sel.select_stocks(theme, max_stocks=4)
            assert len(result) == 4
            # Verify each industry contributes exactly 2 (no more)
            gold_count = sum(1 for r in result if "Gold" in r.get("matched_industries", []))
            silver_count = sum(1 for r in result if "Silver" in r.get("matched_industries", []))
            assert gold_count == 2
            assert silver_count == 2

    def test_single_industry_theme_2nd_pass_fills(self):
        """Single industry theme: 2nd pass fills up to max_stocks."""
        sel = RepresentativeStockSelector(max_per_industry=4)

        def many_stocks(industry, limit, is_bearish):
            return [
                {
                    "symbol": f"S{i}",
                    "source": "finviz_public",
                    "market_cap": (20 - i) * 1_000_000_000,
                    "change": 5.0,
                    "volume": 1_000_000,
                    "matched_industries": [industry],
                    "reasons": [],
                }
                for i in range(min(limit, 15))
            ]

        with (
            patch.object(sel, "_fetch_finviz_public", side_effect=many_stocks),
            patch.object(sel, "_rate_limit"),
        ):
            theme = {
                "direction": "bullish",
                "matching_industries": [{"name": "Gold"}],
                "proxy_etfs": [],
                "static_stocks": [],
            }
            result = sel.select_stocks(theme, max_stocks=10)
            assert len(result) == 10

    def test_fetch_limit_at_least_max_stocks(self):
        """fetch_limit = max(max_stocks, max_per_industry*2)."""
        sel = RepresentativeStockSelector(max_per_industry=4)
        fetch_limits = []

        def track_limit(industry, limit, is_bearish):
            fetch_limits.append(limit)
            return []

        with (
            patch.object(sel, "_fetch_finviz_public", side_effect=track_limit),
            patch.object(sel, "_rate_limit"),
        ):
            theme = {
                "direction": "bullish",
                "matching_industries": [{"name": "Gold"}],
                "proxy_etfs": [],
                "static_stocks": ["A"],
            }
            sel.select_stocks(theme, max_stocks=10)
            assert all(fl >= 10 for fl in fetch_limits)

    def test_cache_prevents_duplicate_queries(self):
        """Same (industry, direction) only queried once."""
        sel = RepresentativeStockSelector()
        call_count = 0

        def count_calls(industry, limit, is_bearish):
            nonlocal call_count
            call_count += 1
            return _mock_finviz_public_stocks(industry, limit, is_bearish)

        with (
            patch.object(sel, "_fetch_finviz_public", side_effect=count_calls),
            patch.object(sel, "_rate_limit"),
        ):
            theme1 = {
                "direction": "bullish",
                "matching_industries": [{"name": "Gold"}],
                "proxy_etfs": [],
                "static_stocks": [],
            }
            theme2 = {
                "direction": "bullish",
                "matching_industries": [{"name": "Gold"}],
                "proxy_etfs": [],
                "static_stocks": [],
            }
            sel.select_stocks(theme1, max_stocks=5)
            sel.select_stocks(theme2, max_stocks=5)
            assert call_count == 1  # 2nd call uses cache

    def test_selector_none_uses_static(self):
        """When selector is None, static_stocks are used directly."""
        # This tests the _get_representative_stocks wrapper in theme_detector
        # but we verify the static fallback path in select_stocks
        sel = RepresentativeStockSelector()

        def fail_finviz(industry, limit, is_bearish):
            return []

        with (
            patch.object(sel, "_fetch_finviz_public", side_effect=fail_finviz),
            patch.object(sel, "_rate_limit"),
        ):
            theme = {
                "direction": "bullish",
                "matching_industries": [],
                "proxy_etfs": [],
                "static_stocks": ["A", "B", "C"],
            }
            result = sel.select_stocks(theme, max_stocks=5)
            assert [d["symbol"] for d in result] == ["A", "B", "C"]


# ---------------------------------------------------------------------------
# Circuit breaker
# ---------------------------------------------------------------------------


class TestCircuitBreaker:
    def test_consecutive_failures_disables_elite_only(self):
        """Elite 3 consecutive failures => Elite disabled, Public still active."""
        sel = RepresentativeStockSelector(
            finviz_elite_key="key",
            finviz_mode="elite",
        )
        for _ in range(_MAX_CONSECUTIVE_FAILURES):
            sel._record_failure("elite")
        assert sel._source_states["elite"].disabled is True
        assert sel._source_states["public"].disabled is False

    def test_mixed_source_failures_independent(self):
        """Elite fail -> Public success -> FMP fail: independent counters."""
        sel = RepresentativeStockSelector(
            finviz_elite_key="key",
            fmp_api_key="key",
            finviz_mode="elite",
        )
        sel._record_failure("elite")
        sel._record_success("public")
        sel._record_failure("fmp")

        assert sel._source_states["elite"].consecutive_failures == 1
        assert sel._source_states["public"].consecutive_failures == 0
        assert sel._source_states["fmp"].consecutive_failures == 1

    def test_success_resets_own_source_count(self):
        """Success resets only that source's consecutive counter."""
        sel = RepresentativeStockSelector(
            finviz_elite_key="key",
            finviz_mode="elite",
        )
        sel._record_failure("elite")
        sel._record_failure("elite")
        assert sel._source_states["elite"].consecutive_failures == 2
        sel._record_success("elite")
        assert sel._source_states["elite"].consecutive_failures == 0
        # total_failures stays
        assert sel._source_states["elite"].total_failures == 2

    def test_status_degraded_when_one_active_source_disabled(self):
        """One active source disabled => status='degraded'."""
        sel = RepresentativeStockSelector(
            finviz_elite_key="key",
            fmp_api_key="key",
            finviz_mode="elite",
        )
        for _ in range(_MAX_CONSECUTIVE_FAILURES):
            sel._record_failure("elite")
        assert sel.status == "degraded"

    def test_status_circuit_broken_when_all_active_disabled(self):
        """All active sources disabled => status='circuit_broken'."""
        sel = RepresentativeStockSelector(
            finviz_elite_key="key",
            fmp_api_key="key",
            finviz_mode="elite",
        )
        for source in ["elite", "public", "fmp"]:
            for _ in range(_MAX_CONSECUTIVE_FAILURES):
                sel._record_failure(source)
        assert sel.status == "circuit_broken"

    def test_status_active_ignores_elite_when_mode_public(self):
        """finviz_mode=public => elite not in active sources."""
        sel = RepresentativeStockSelector(
            finviz_elite_key="key",
            finviz_mode="public",
        )
        for _ in range(_MAX_CONSECUTIVE_FAILURES):
            sel._record_failure("elite")
        # elite is disabled but not in active sources
        assert sel.status == "active"

    def test_status_active_ignores_fmp_when_no_key(self):
        """fmp_api_key=None => fmp not in active sources."""
        sel = RepresentativeStockSelector()
        for _ in range(_MAX_CONSECUTIVE_FAILURES):
            sel._record_failure("fmp")
        assert sel.status == "active"


# ---------------------------------------------------------------------------
# FINVIZ Public fetch
# ---------------------------------------------------------------------------


class TestFetchFinvizPublic:
    def test_returns_stock_dicts_with_schema(self):
        """Each element has required keys."""
        sel = RepresentativeStockSelector()
        pd = pytest.importorskip("pandas")
        mock_df = pd.DataFrame(
            {
                "Ticker": ["NVDA", "AMD"],
                "Company": ["NVIDIA", "AMD Inc"],
                "Sector": ["Technology", "Technology"],
                "Industry": ["Semiconductors", "Semiconductors"],
                "Country": ["USA", "USA"],
                "Market Cap": [2_800_000_000_000, 200_000_000_000],
                "P/E": [60.0, 40.0],
                "Price": [800.0, 150.0],
                "Change": [0.05, 0.03],
                "Volume": [50_000_000, 30_000_000],
            }
        )
        with patch("representative_stock_selector.Overview") as MockOverview:
            mock_instance = MockOverview.return_value
            mock_instance.screener_view.return_value = mock_df
            with patch.object(sel, "_rate_limit"):
                result = sel._fetch_finviz_public("Semiconductors", limit=10, is_bearish=False)
        assert len(result) == 2
        for stock in result:
            assert "symbol" in stock
            assert "source" in stock
            assert stock["source"] == "finviz_public"
            assert "market_cap" in stock
            assert "matched_industries" in stock

    def test_uses_correct_filter_option_names(self):
        """filter_dict uses exact finvizfinance option names."""
        sel = RepresentativeStockSelector(min_cap="small")
        pd = pytest.importorskip("pandas")
        mock_df = pd.DataFrame(
            {
                "Ticker": ["X"],
                "Market Cap": [1_000_000_000],
                "Change": [0.01],
                "Volume": [100_000],
            }
        )
        with patch("representative_stock_selector.Overview") as MockOverview:
            mock_instance = MockOverview.return_value
            mock_instance.screener_view.return_value = mock_df
            with patch.object(sel, "_rate_limit"):
                sel._fetch_finviz_public("Gold", limit=10, is_bearish=False)
            # Verify set_filter was called with correct filter names
            call_args = mock_instance.set_filter.call_args
            filters = (
                call_args[1].get("filters_dict", {})
                if call_args[1]
                else call_args[0][0]
                if call_args[0]
                else {}
            )
            assert filters.get("Market Cap.") == "+Small (over $300mln)"
            assert filters.get("Average Volume") == "Over 100K"
            assert filters.get("Price") == "Over $10"
            assert filters.get("Performance 2") == "Month Up"

    def test_bearish_uses_month_down_filter(self):
        """Bearish => Performance 2: Month Down."""
        sel = RepresentativeStockSelector()
        pd = pytest.importorskip("pandas")
        mock_df = pd.DataFrame(
            {
                "Ticker": ["X"],
                "Market Cap": [1_000_000_000],
                "Change": [-0.05],
                "Volume": [100_000],
            }
        )
        with patch("representative_stock_selector.Overview") as MockOverview:
            mock_instance = MockOverview.return_value
            mock_instance.screener_view.return_value = mock_df
            with patch.object(sel, "_rate_limit"):
                sel._fetch_finviz_public("Retail", limit=10, is_bearish=True)
            call_args = mock_instance.set_filter.call_args
            filters = (
                call_args[1].get("filters_dict", {})
                if call_args[1]
                else call_args[0][0]
                if call_args[0]
                else {}
            )
            assert filters.get("Performance 2") == "Month Down"

    def test_rate_limiting(self):
        """Consecutive calls have rate_limit_sec delay."""
        sel = RepresentativeStockSelector(rate_limit_sec=0.1)
        pd = pytest.importorskip("pandas")
        mock_df = pd.DataFrame(
            {
                "Ticker": ["X"],
                "Market Cap": [1_000_000_000],
                "Change": [0.01],
                "Volume": [100_000],
            }
        )
        with patch("representative_stock_selector.Overview") as MockOverview:
            mock_instance = MockOverview.return_value
            mock_instance.screener_view.return_value = mock_df
            start = time.time()
            sel._fetch_finviz_public("Gold", limit=5, is_bearish=False)
            sel._fetch_finviz_public("Silver", limit=5, is_bearish=False)
            elapsed = time.time() - start
            assert elapsed >= 0.1  # At least one rate limit pause

    def test_failure_returns_empty_and_records(self):
        """Exception => empty list + failure recorded."""
        sel = RepresentativeStockSelector()
        with patch("representative_stock_selector.Overview") as MockOverview:
            mock_instance = MockOverview.return_value
            mock_instance.screener_view.side_effect = Exception("network error")
            with patch.object(sel, "_rate_limit"):
                result = sel._fetch_finviz_public("Gold", limit=10, is_bearish=False)
        assert result == []
        assert sel._source_states["public"].consecutive_failures == 1


# ---------------------------------------------------------------------------
# FINVIZ Elite fetch
# ---------------------------------------------------------------------------


class TestFetchFinvizElite:
    def test_csv_parsing(self):
        """CSV response is correctly parsed."""
        sel = RepresentativeStockSelector(
            finviz_elite_key="test_key",
            finviz_mode="elite",
        )
        csv_content = (
            "No.,Ticker,Company,Sector,Industry,Country,Market Cap,P/E,Price,Change,Volume\n"
            '1,NEM,Newmont,Basic Materials,Gold,USA,50.5B,20.5,45.30,5.20%,"1,234,567"\n'
            '2,GOLD,Barrick Gold,Basic Materials,Gold,Canada,30.2B,15.3,18.50,3.10%,"2,345,678"\n'
        )
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = csv_content
        with (
            patch("representative_stock_selector.requests.get", return_value=mock_response),
            patch.object(sel, "_rate_limit"),
        ):
            result = sel._fetch_finviz_elite("Gold", limit=10, is_bearish=False)
        assert len(result) == 2
        assert result[0]["symbol"] == "NEM"
        assert result[0]["source"] == "finviz_elite"

    @pytest.mark.parametrize(
        "min_cap,expected_code",
        [
            ("micro", "cap_microover"),
            ("small", "cap_smallover"),
            ("mid", "cap_midover"),
        ],
    )
    def test_filter_string_format(self, min_cap, expected_code):
        """Filter string contains correct cap code."""
        sel = RepresentativeStockSelector(
            finviz_elite_key="test_key",
            finviz_mode="elite",
            min_cap=min_cap,
        )
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "No.,Ticker,Company\n"
        with (
            patch(
                "representative_stock_selector.requests.get", return_value=mock_response
            ) as mock_get,
            patch.object(sel, "_rate_limit"),
        ):
            sel._fetch_finviz_elite("Gold", limit=10, is_bearish=False)
            url = mock_get.call_args[0][0]
            assert expected_code in url

    def test_bearish_filter_uses_4wdown(self):
        """is_bearish=True => ta_perf2_4wdown in URL."""
        sel = RepresentativeStockSelector(
            finviz_elite_key="test_key",
            finviz_mode="elite",
        )
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "No.,Ticker,Company\n"
        with (
            patch(
                "representative_stock_selector.requests.get", return_value=mock_response
            ) as mock_get,
            patch.object(sel, "_rate_limit"),
        ):
            sel._fetch_finviz_elite("Gold", limit=10, is_bearish=True)
            url = mock_get.call_args[0][0]
            assert "ta_perf2_4wdown" in url

    def test_auth_failure_returns_empty(self):
        """401/403 => empty list."""
        sel = RepresentativeStockSelector(
            finviz_elite_key="bad_key",
            finviz_mode="elite",
        )
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.text = "Forbidden"
        with (
            patch("representative_stock_selector.requests.get", return_value=mock_response),
            patch.object(sel, "_rate_limit"),
        ):
            result = sel._fetch_finviz_elite("Gold", limit=10, is_bearish=False)
        assert result == []
        assert sel._source_states["elite"].consecutive_failures == 1


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------


class TestProperties:
    def test_query_count(self):
        sel = RepresentativeStockSelector()
        sel._source_states["public"].total_queries = 5
        sel._source_states["fmp"].total_queries = 2
        assert sel.query_count == 7

    def test_failure_count(self):
        sel = RepresentativeStockSelector()
        sel._source_states["public"].total_failures = 3
        sel._source_states["elite"].total_failures = 1
        assert sel.failure_count == 4

    def test_active_sources_public_mode(self):
        sel = RepresentativeStockSelector(finviz_mode="public")
        assert sel._active_sources == ["public"]

    def test_active_sources_public_mode_with_fmp(self):
        sel = RepresentativeStockSelector(finviz_mode="public", fmp_api_key="key")
        assert sel._active_sources == ["public", "fmp"]

    def test_active_sources_elite_mode(self):
        sel = RepresentativeStockSelector(
            finviz_elite_key="key",
            finviz_mode="elite",
            fmp_api_key="key",
        )
        assert sel._active_sources == ["elite", "public", "fmp"]

    def test_active_sources_elite_mode_no_key(self):
        """elite mode but no key => elite not in active sources."""
        sel = RepresentativeStockSelector(finviz_mode="elite")
        assert "elite" not in sel._active_sources

    def test_source_states_property(self):
        sel = RepresentativeStockSelector()
        states = sel.source_states
        assert "elite" in states
        assert "public" in states
        assert "fmp" in states


def test_overlapping_etfs_merge_through_actual_fallback(monkeypatch):
    """Two ETF responses sharing a ticker must retain both reasons without a score crash."""
    from unittest.mock import Mock

    import representative_stock_selector as selector_module

    response = Mock(status_code=200)
    response.json.return_value = [{"asset": "FICT", "marketValue": 100}]
    get = Mock(return_value=response)
    monkeypatch.setattr(selector_module.requests, "get", get)
    selector = RepresentativeStockSelector(fmp_api_key="fictional-key", rate_limit_sec=0)
    theme = {"direction": "bullish", "matching_industries": [], "proxy_etfs": ["FUND1", "FUND2"]}
    first = selector.select_stocks(theme, max_stocks=10)
    assert len(first) == 1
    assert first[0]["composite_score"] == 0
    assert first[0]["reasons"] == ["Held by FUND1", "Held by FUND2"]
    assert selector.select_stocks(theme, max_stocks=10) == first
    assert get.call_count == 2


@pytest.mark.parametrize("order", ["etf-first", "scored-first"])
def test_mixed_unscored_and_scored_candidates_keep_max_score(order):
    selector = RepresentativeStockSelector()
    etf = {"symbol": "FICT", "source": "etf_holdings", "reasons": ["ETF"], "matched_industries": []}
    scored = {
        "symbol": "FICT",
        "source": "finviz_public",
        "composite_score": 0.8,
        "reasons": ["Public"],
        "matched_industries": ["Industry"],
    }
    candidates = [etf, scored] if order == "etf-first" else [scored, etf]
    result = selector._merge_and_rank(candidates, 1)
    assert result[0]["composite_score"] == 0.8
    assert set(result[0]["reasons"]) == {"ETF", "Public"}
    assert result[0]["matched_industries"] == ["Industry"]
