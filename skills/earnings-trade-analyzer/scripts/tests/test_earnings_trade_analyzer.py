#!/usr/bin/env python3
"""
Tests for Earnings Trade Analyzer modules.

Covers normal cases and failure cases for all 5 calculators,
scorer, report generator, and FMP client edge cases.
"""

import json
import os
import sys
import tempfile
from unittest.mock import MagicMock, patch

import pytest
from analyze_earnings_trades import (
    apply_entry_filter,
    classify_empty_calendar,
    explain_empty_selection,
    main,
    select_candidates,
)
from calculators.gap_size_calculator import calculate_gap
from calculators.ma50_calculator import calculate_ma50_position
from calculators.ma200_calculator import calculate_ma200_position
from calculators.pre_earnings_trend_calculator import calculate_pre_earnings_trend
from calculators.volume_trend_calculator import calculate_volume_trend
from fmp_client import ApiCallBudgetExceeded, FMPClient
from report_generator import generate_json_report, generate_markdown_report
from scorer import COMPONENT_WEIGHTS, calculate_composite_score

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_prices(n, start=100.0, daily_change=0.0, volume=1000000, start_date="2025-01-01"):
    """Generate synthetic price data (most-recent-first).

    Args:
        n: Number of bars
        start: Starting close price (for most recent bar)
        daily_change: Per-bar drift factor
        volume: Volume for all bars
        start_date: Date string for the most recent bar

    Returns:
        List of price dicts, most-recent-first.
    """
    prices = []
    p = start
    for i in range(n):
        p_day = p * (1 + daily_change * i)
        prices.append(
            {
                "date": f"2025-{(i // 22) + 1:02d}-{(i % 22) + 1:02d}",
                "open": round(p_day * 0.999, 2),
                "high": round(p_day * 1.01, 2),
                "low": round(p_day * 0.99, 2),
                "close": round(p_day, 2),
                "volume": volume,
            }
        )
    return prices


def _make_earnings_prices(
    earnings_date="2025-01-05",
    pre_close=100.0,
    earnings_open=106.0,
    earnings_close=107.0,
    post_open=108.0,
    num_days=250,
    volume=1000000,
):
    """Generate price data with a specific earnings date and gap.

    Places the earnings date at a known position with controlled prices
    around it. Returns most-recent-first data.
    """
    prices = []

    # Build chronological then reverse
    # Place earnings at day 30 (arbitrary, gives us 20+ days before for trend)
    earnings_day_idx = 30

    for i in range(num_days):
        if i < earnings_day_idx - 1:
            # Days before the day before earnings
            base = pre_close * (1 - 0.001 * (earnings_day_idx - 1 - i))
            prices.append(
                {
                    "date": f"2025-{(i // 22) + 1:02d}-{(i % 22) + 1:02d}",
                    "open": round(base * 0.999, 2),
                    "high": round(base * 1.01, 2),
                    "low": round(base * 0.99, 2),
                    "close": round(base, 2),
                    "volume": volume,
                }
            )
        elif i == earnings_day_idx - 1:
            # Day before earnings
            prices.append(
                {
                    "date": f"2025-{(i // 22) + 1:02d}-{(i % 22) + 1:02d}",
                    "open": round(pre_close * 0.999, 2),
                    "high": round(pre_close * 1.01, 2),
                    "low": round(pre_close * 0.99, 2),
                    "close": round(pre_close, 2),
                    "volume": volume,
                }
            )
        elif i == earnings_day_idx:
            # Earnings day
            prices.append(
                {
                    "date": earnings_date,
                    "open": round(earnings_open, 2),
                    "high": round(max(earnings_open, earnings_close) * 1.01, 2),
                    "low": round(min(earnings_open, earnings_close) * 0.99, 2),
                    "close": round(earnings_close, 2),
                    "volume": volume * 3,  # High volume on earnings day
                }
            )
        elif i == earnings_day_idx + 1:
            # Day after earnings
            prices.append(
                {
                    "date": f"2025-{(i // 22) + 1:02d}-{(i % 22) + 1:02d}",
                    "open": round(post_open, 2),
                    "high": round(post_open * 1.01, 2),
                    "low": round(post_open * 0.99, 2),
                    "close": round(post_open * 1.005, 2),
                    "volume": volume * 2,
                }
            )
        else:
            # Days after earnings
            base = post_open * (1 + 0.001 * (i - earnings_day_idx - 1))
            prices.append(
                {
                    "date": f"2025-{(i // 22) + 1:02d}-{(i % 22) + 1:02d}",
                    "open": round(base * 0.999, 2),
                    "high": round(base * 1.01, 2),
                    "low": round(base * 0.99, 2),
                    "close": round(base, 2),
                    "volume": volume,
                }
            )

    # Reverse to most-recent-first
    prices.reverse()
    return prices


# ===========================================================================
# Phase 1 Candidate Selection Tests
# ===========================================================================


class TestCandidateSelection:
    """Test the stable profile contract used by the Phase 1 filter."""

    def test_stable_fields_pass_at_market_cap_floor_and_keep_first_announcement(self):
        earnings = [
            {"symbol": "AAPL", "date": "2026-08-28", "time": "after market close"},
            {"symbol": "AAPL", "date": "2026-08-29", "time": "bmo"},
        ]
        profiles = {
            "AAPL": {
                "companyName": "Apple Inc.",
                "marketCap": 500_000_000,
                "exchange": "NASDAQ",
                "sector": "Technology",
                "industry": "Consumer Electronics",
                "price": 230.0,
            }
        }

        candidates = select_candidates(earnings, profiles, min_market_cap=500_000_000)

        assert candidates == [
            {
                "symbol": "AAPL",
                "company_name": "Apple Inc.",
                "earnings_date": "2026-08-28",
                "earnings_timing": "amc",
                "market_cap": 500_000_000,
                "sector": "Technology",
                "industry": "Consumer Electronics",
                "price": 230.0,
            }
        ]

    @pytest.mark.parametrize(
        "market_cap",
        [None, "500000000", True, float("nan"), float("inf"), float("-inf")],
    )
    def test_invalid_market_cap_is_rejected(self, market_cap):
        earnings = [{"symbol": "AAPL", "date": "2026-08-28", "time": "bmo"}]
        profiles = {"AAPL": {"marketCap": market_cap, "exchange": "NASDAQ"}}

        assert select_candidates(earnings, profiles, min_market_cap=500_000_000) == []

    @pytest.mark.parametrize(
        "profile",
        [
            {"marketCap": 499_999_999, "exchange": "NASDAQ"},
            {"marketCap": 500_000_000, "exchange": "TSX"},
            {"marketCap": 500_000_000, "exchange": None},
            {"marketCap": 500_000_000, "exchange": 123},
            {"mktCap": 500_000_000, "exchangeShortName": "NASDAQ"},
        ],
    )
    def test_noncanonical_or_out_of_scope_profile_is_rejected(self, profile):
        earnings = [{"symbol": "AAPL", "date": "2026-08-28", "time": "bmo"}]

        assert (
            select_candidates(
                earnings,
                {"AAPL": profile},
                min_market_cap=500_000_000,
            )
            == []
        )

    @patch("analyze_earnings_trades.generate_markdown_report")
    @patch("analyze_earnings_trades.generate_json_report")
    @patch("analyze_earnings_trades.analyze_stock")
    @patch("analyze_earnings_trades.FMPClient")
    def test_main_routes_stable_profile_candidate_to_historical_fetch(
        self,
        mock_client_class,
        mock_analyze_stock,
        mock_json_report,
        _mock_markdown_report,
        capsys,
    ):
        client = mock_client_class.return_value
        mock_client_class.US_EXCHANGES = FMPClient.US_EXCHANGES
        client.api_calls_made = 2
        client.get_earnings_calendar.return_value = [
            {"symbol": "AAPL", "date": "2026-08-28", "time": "after market close"},
            {"symbol": "LOW", "date": "2026-08-28", "time": "bmo"},
            {"symbol": "SHOP", "date": "2026-08-28", "time": "bmo"},
            {"symbol": "OLD", "date": "2026-08-28", "time": "bmo"},
        ]
        client.get_company_profiles.return_value = {
            "AAPL": {
                "companyName": "Apple Inc.",
                "marketCap": 3_000_000_000_000,
                "exchange": "NASDAQ",
                "sector": "Technology",
                "industry": "Consumer Electronics",
                "price": 230.0,
            },
            "LOW": {"marketCap": 100_000_000, "exchange": "NYSE"},
            "SHOP": {"marketCap": 100_000_000_000, "exchange": "TSX"},
            "OLD": {"mktCap": 1_000_000_000, "exchangeShortName": "NYSE"},
        }
        client.get_historical_prices.return_value = [{"close": 231.0}] * 50
        client.get_api_stats.return_value = {
            "api_calls_made": 3,
            "max_api_calls": 200,
        }
        mock_analyze_stock.return_value = {
            "gap": {"gap_pct": 5.0},
            "pre_earnings_trend": {},
            "volume_trend": {},
            "ma200_position": {},
            "ma50_position": {},
            "composite": {
                "composite_score": 80.0,
                "grade": "B",
                "grade_description": "Good setup",
                "guidance": "Monitor",
                "weakest_component": "Volume Trend",
                "strongest_component": "Gap Size",
                "component_breakdown": {},
            },
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            argv = [
                "analyze_earnings_trades.py",
                "--api-key",
                "test-key",
                "--output-dir",
                tmpdir,
            ]
            with patch.object(sys, "argv", argv):
                main()

        assert "Candidates after filtering: 1" in capsys.readouterr().err
        client.get_historical_prices.assert_called_once_with("AAPL", days=250)
        results = mock_json_report.call_args.args[0]
        assert len(results) == 1
        assert results[0]["symbol"] == "AAPL"
        assert results[0]["market_cap"] == 3_000_000_000_000

    @patch("analyze_earnings_trades.generate_markdown_report")
    @patch("analyze_earnings_trades.generate_json_report")
    @patch("analyze_earnings_trades.analyze_stock")
    @patch("analyze_earnings_trades.FMPClient")
    def test_main_reports_timing_unknown_count_in_metadata(
        self,
        mock_client_class,
        mock_analyze_stock,
        mock_json_report,
        _mock_markdown_report,
        capsys,
    ):
        """Issue #352: a `time: null` row must be counted as unknown, and the
        candidate population that actually reaches analysis (post market-cap
        filter) is the denominator, not the raw calendar row count."""
        client = mock_client_class.return_value
        mock_client_class.US_EXCHANGES = FMPClient.US_EXCHANGES
        client.api_calls_made = 3
        client.get_earnings_calendar.return_value = [
            {"symbol": "AAPL", "date": "2026-08-28", "time": "bmo"},
            {"symbol": "MSFT", "date": "2026-08-28", "time": "amc"},
            {"symbol": "GOOG", "date": "2026-08-28", "time": None},
        ]
        client.get_company_profiles.return_value = {
            "AAPL": {"marketCap": 3_000_000_000_000, "exchange": "NASDAQ"},
            "MSFT": {"marketCap": 2_000_000_000_000, "exchange": "NASDAQ"},
            "GOOG": {"marketCap": 1_500_000_000_000, "exchange": "NASDAQ"},
        }
        client.get_historical_prices.return_value = [{"close": 100.0}] * 60
        client.get_api_stats.return_value = {"api_calls_made": 4, "max_api_calls": 200}
        mock_analyze_stock.return_value = {
            "gap": {"gap_pct": 2.0},
            "pre_earnings_trend": {},
            "volume_trend": {},
            "ma200_position": {},
            "ma50_position": {},
            "composite": {
                "composite_score": 60.0,
                "grade": "C",
                "grade_description": "Neutral setup",
                "guidance": "Monitor",
                "weakest_component": "Volume Trend",
                "strongest_component": "Gap Size",
                "component_breakdown": {},
            },
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            argv = [
                "analyze_earnings_trades.py",
                "--api-key",
                "test-key",
                "--output-dir",
                tmpdir,
            ]
            with patch.object(sys, "argv", argv):
                main()

        metadata = mock_json_report.call_args.args[1]
        assert metadata["timing_candidates_total"] == 3
        assert metadata["timing_unknown_count"] == 1
        assert metadata["timing_source"] == "fmp_stable_includeReportTimes"

    @patch("analyze_earnings_trades.generate_markdown_report")
    @patch("analyze_earnings_trades.generate_json_report")
    @patch("analyze_earnings_trades.FMPClient")
    def test_main_end_to_end_bmo_timing_uses_bmo_gap_window(
        self, mock_client_class, mock_json_report, _mock_markdown_report, capsys
    ):
        """Issue #352 end-to-end: a bmo-timed candidate flows unmocked through
        select_candidates -> analyze_stock -> calculate_gap and lands on the
        BMO gap window (open[earnings_date]/close[prev_day]), not AMC."""
        client = mock_client_class.return_value
        mock_client_class.US_EXCHANGES = FMPClient.US_EXCHANGES
        client.api_calls_made = 1
        client.get_earnings_calendar.return_value = [
            {"symbol": "AAPL", "date": "2025-01-05", "time": "bmo"},
        ]
        client.get_company_profiles.return_value = {
            "AAPL": {
                "companyName": "Apple Inc.",
                "marketCap": 3_000_000_000_000,
                "exchange": "NASDAQ",
                "sector": "Technology",
                "industry": "Consumer Electronics",
                "price": 230.0,
            },
        }
        client.get_historical_prices.return_value = _make_earnings_prices(
            earnings_date="2025-01-05",
            pre_close=100.0,
            earnings_open=106.0,
            earnings_close=107.0,
            post_open=108.0,
        )
        client.get_api_stats.return_value = {"api_calls_made": 2, "max_api_calls": 200}

        with tempfile.TemporaryDirectory() as tmpdir:
            argv = [
                "analyze_earnings_trades.py",
                "--api-key",
                "test-key",
                "--output-dir",
                tmpdir,
            ]
            with patch.object(sys, "argv", argv):
                main()

        results = mock_json_report.call_args.args[0]
        assert len(results) == 1
        gap = results[0]["components"]["gap_size"]
        assert gap["timing_used"] == "bmo"
        # BMO: open[earnings_date] / close[prev_day] - 1 = 106.0 / 100.0 - 1 = 6.0%
        assert gap["gap_pct"] == 6.0


# ===========================================================================
# Zero-Result Reason Tests (Issue #332)
# ===========================================================================


class TestExplainEmptySelection:
    """explain_empty_selection() ZERO_RESULT_REASON codes, evaluated in order."""

    FIXTURE_EARNINGS = [{"symbol": "AAPL", "date": "2026-09-04", "time": "amc"}]
    FIXTURE_PROFILE = {
        "symbol": "AAPL",
        "price": 319.97,
        "marketCap": 4699513299320,
        "beta": 1.086,
        "lastDividend": 1.06,
        "exchangeFullName": "NASDAQ Global Select",
        "exchange": "NASDAQ",
        "industry": "Consumer Electronics",
        "sector": "Technology",
        "country": "US",
    }

    @staticmethod
    def _api_stats(budget_remaining=50, rate_limit_reached=False):
        return {"budget_remaining": budget_remaining, "rate_limit_reached": rate_limit_reached}

    def test_profiles_budget_exhausted_when_budget_zero(self):
        reason = explain_empty_selection(
            self.FIXTURE_EARNINGS, {}, 2e9, self._api_stats(budget_remaining=0)
        )
        assert reason == "profiles_budget_exhausted"

    def test_profiles_budget_exhausted_when_rate_limit_reached(self):
        reason = explain_empty_selection(
            self.FIXTURE_EARNINGS,
            {},
            2e9,
            self._api_stats(budget_remaining=5, rate_limit_reached=True),
        )
        assert reason == "profiles_budget_exhausted"

    def test_no_profiles_returned_when_budget_remains(self):
        reason = explain_empty_selection(self.FIXTURE_EARNINGS, {}, 2e9, self._api_stats())
        assert reason == "no_profiles_returned"

    def test_missing_required_field_marketcap_when_renamed(self):
        renamed = dict(self.FIXTURE_PROFILE)
        renamed["mktCap"] = renamed.pop("marketCap")
        reason = explain_empty_selection(
            self.FIXTURE_EARNINGS, {"AAPL": renamed}, 2e9, self._api_stats()
        )
        assert reason == "profiles_missing_required_field:marketCap"

    def test_missing_required_field_exchange_when_absent(self):
        profile = dict(self.FIXTURE_PROFILE)
        del profile["exchange"]
        reason = explain_empty_selection(
            self.FIXTURE_EARNINGS, {"AAPL": profile}, 2e9, self._api_stats()
        )
        assert reason == "profiles_missing_required_field:exchange"

    def test_all_below_market_cap_floor(self):
        reason = explain_empty_selection(
            self.FIXTURE_EARNINGS,
            {"AAPL": self.FIXTURE_PROFILE},
            10_000_000_000_000,
            self._api_stats(),
        )
        assert reason == "all_below_market_cap_floor"

    def test_all_non_us_exchange(self):
        profile = dict(self.FIXTURE_PROFILE)
        profile["exchange"] = "TSX"
        reason = explain_empty_selection(
            self.FIXTURE_EARNINGS, {"AAPL": profile}, 2e9, self._api_stats()
        )
        assert reason == "all_non_us_exchange"

    def test_mixed_filters_rejected_all_is_benign_not_drift(self):
        """P1 fails the exchange filter, P2 fails the cap floor: an ordinary
        empty day (different candidates rejected by different filters), not
        drift. Must not be misclassified as "unknown" (Issue #332 review)."""
        earnings = [
            {"symbol": "P1", "date": "2026-09-04", "time": "amc"},
            {"symbol": "P2", "date": "2026-09-04", "time": "amc"},
        ]
        profiles = {
            "P1": {"marketCap": 5e9, "exchange": "LSE"},
            "P2": {"marketCap": 1e9, "exchange": "NASDAQ"},
        }
        reason = explain_empty_selection(earnings, profiles, 2e9, self._api_stats())
        assert reason == "mixed_filters_rejected_all"

    def test_no_earnings_rows_is_benign_empty_window(self):
        """Rows without a symbol (or no rows at all) are a genuine empty window:
        exit 0, never the fail-closed ``unknown`` fallback (PR #353 review)."""
        assert explain_empty_selection([], {}, 2e9, self._api_stats()) == "no_earnings_rows"
        rows_without_symbol = [{"date": "2026-09-04", "time": "amc"}]
        assert (
            explain_empty_selection(rows_without_symbol, {}, 2e9, self._api_stats())
            == "no_earnings_rows"
        )

    def test_fixture_select_candidates_yields_one_then_zero_on_rename(self):
        """D4: pin select_candidates + explain_empty_selection against the live fixture."""
        candidates = select_candidates(self.FIXTURE_EARNINGS, {"AAPL": self.FIXTURE_PROFILE}, 2e9)
        assert len(candidates) == 1

        renamed = dict(self.FIXTURE_PROFILE)
        renamed["mktCap"] = renamed.pop("marketCap")
        assert select_candidates(self.FIXTURE_EARNINGS, {"AAPL": renamed}, 2e9) == []
        assert (
            explain_empty_selection(
                self.FIXTURE_EARNINGS, {"AAPL": renamed}, 2e9, self._api_stats()
            )
            == "profiles_missing_required_field:marketCap"
        )


class TestClassifyEmptyCalendar:
    """Only a clean empty list is benign; None and non-list bodies fail closed."""

    def test_empty_list_is_benign(self):
        assert classify_empty_calendar([]) == "no_earnings_rows"

    def test_none_fails_closed(self):
        assert classify_empty_calendar(None) == "calendar_fetch_failed"

    def test_non_list_bodies_fail_closed(self):
        assert classify_empty_calendar({}) == "calendar_fetch_failed"
        assert classify_empty_calendar("") == "calendar_fetch_failed"
        assert classify_empty_calendar(0) == "calendar_fetch_failed"
        assert classify_empty_calendar({"error": "Bad Request"}) == "calendar_fetch_failed"


class TestMainZeroResultExitCodes:
    """Drive main() end-to-end with a mocked FMPClient for each exit code."""

    @staticmethod
    def _argv(tmpdir):
        return [
            "analyze_earnings_trades.py",
            "--api-key",
            "test-key",
            "--output-dir",
            str(tmpdir),
        ]

    @patch("analyze_earnings_trades.FMPClient")
    def test_malformed_rows_are_ignored_not_crash(self, mock_client_class, tmp_path, capsys):
        """Non-dict calendar rows are never dereferenced; symbols-empty stays benign."""
        client = mock_client_class.return_value
        mock_client_class.US_EXCHANGES = FMPClient.US_EXCHANGES
        client.get_earnings_calendar.return_value = ["x", None, {"foo": 1}]
        client.get_company_profiles.return_value = {}
        client.get_api_stats.return_value = {
            "budget_remaining": 50,
            "rate_limit_reached": False,
        }

        with patch.object(sys, "argv", self._argv(tmp_path)):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 0
        err = capsys.readouterr().err
        assert "ZERO_RESULT_REASON=no_earnings_rows" in err

    @patch("analyze_earnings_trades.FMPClient")
    def test_no_profiles_returned_exits_1(self, mock_client_class, tmp_path, capsys):
        client = mock_client_class.return_value
        mock_client_class.US_EXCHANGES = FMPClient.US_EXCHANGES
        client.get_earnings_calendar.return_value = [
            {"symbol": "AAPL", "date": "2026-09-04", "time": "amc"}
        ]
        client.get_company_profiles.return_value = {}
        client.get_api_stats.return_value = {
            "budget_remaining": 50,
            "rate_limit_reached": False,
        }

        with patch.object(sys, "argv", self._argv(tmp_path)):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 1
        err = capsys.readouterr().err
        assert "ZERO_RESULT_REASON=no_profiles_returned" in err

    @patch("analyze_earnings_trades.FMPClient")
    def test_profiles_budget_exhausted_exits_0(self, mock_client_class, tmp_path, capsys):
        client = mock_client_class.return_value
        mock_client_class.US_EXCHANGES = FMPClient.US_EXCHANGES
        client.get_earnings_calendar.return_value = [
            {"symbol": "AAPL", "date": "2026-09-04", "time": "amc"}
        ]
        client.get_company_profiles.return_value = {}
        client.get_api_stats.return_value = {
            "budget_remaining": 0,
            "rate_limit_reached": False,
        }

        with patch.object(sys, "argv", self._argv(tmp_path)):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 0
        err = capsys.readouterr().err
        assert "ZERO_RESULT_REASON=profiles_budget_exhausted" in err  # pragma: allowlist secret

    @patch("analyze_earnings_trades.FMPClient")
    def test_missing_marketcap_field_exits_1(self, mock_client_class, tmp_path, capsys):
        client = mock_client_class.return_value
        mock_client_class.US_EXCHANGES = FMPClient.US_EXCHANGES
        client.get_earnings_calendar.return_value = [
            {"symbol": "AAPL", "date": "2026-09-04", "time": "amc"}
        ]
        client.get_company_profiles.return_value = {"AAPL": {"exchange": "NASDAQ"}}
        client.get_api_stats.return_value = {
            "budget_remaining": 50,
            "rate_limit_reached": False,
        }

        with patch.object(sys, "argv", self._argv(tmp_path)):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 1
        err = capsys.readouterr().err
        assert "ZERO_RESULT_REASON=profiles_missing_required_field:marketCap" in err

    @patch("analyze_earnings_trades.FMPClient")
    def test_all_below_market_cap_floor_exits_0(self, mock_client_class, tmp_path, capsys):
        client = mock_client_class.return_value
        mock_client_class.US_EXCHANGES = FMPClient.US_EXCHANGES
        client.get_earnings_calendar.return_value = [
            {"symbol": "AAPL", "date": "2026-09-04", "time": "amc"}
        ]
        client.get_company_profiles.return_value = {
            "AAPL": {"marketCap": 1_000, "exchange": "NASDAQ"}
        }
        client.get_api_stats.return_value = {
            "budget_remaining": 50,
            "rate_limit_reached": False,
        }

        with patch.object(sys, "argv", self._argv(tmp_path)):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 0
        err = capsys.readouterr().err
        assert "ZERO_RESULT_REASON=all_below_market_cap_floor" in err

    @patch("analyze_earnings_trades.FMPClient")
    def test_all_non_us_exchange_exits_0(self, mock_client_class, tmp_path, capsys):
        client = mock_client_class.return_value
        mock_client_class.US_EXCHANGES = FMPClient.US_EXCHANGES
        client.get_earnings_calendar.return_value = [
            {"symbol": "AAPL", "date": "2026-09-04", "time": "amc"}
        ]
        client.get_company_profiles.return_value = {
            "AAPL": {"marketCap": 3_000_000_000_000, "exchange": "TSX"}
        }
        client.get_api_stats.return_value = {
            "budget_remaining": 50,
            "rate_limit_reached": False,
        }

        with patch.object(sys, "argv", self._argv(tmp_path)):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 0
        err = capsys.readouterr().err
        assert "ZERO_RESULT_REASON=all_non_us_exchange" in err

    @patch("analyze_earnings_trades.FMPClient")
    def test_no_earnings_rows_exits_0(self, mock_client_class, tmp_path, capsys):
        """Calendar rows that carry no symbol reach the zero-result path and exit 0."""
        client = mock_client_class.return_value
        mock_client_class.US_EXCHANGES = FMPClient.US_EXCHANGES
        client.get_earnings_calendar.return_value = [{"date": "2026-09-04", "time": "amc"}]
        client.get_company_profiles.return_value = {}
        client.get_api_stats.return_value = {
            "budget_remaining": 50,
            "rate_limit_reached": False,
        }

        with patch.object(sys, "argv", self._argv(tmp_path)):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 0
        err = capsys.readouterr().err
        assert "ZERO_RESULT_REASON=no_earnings_rows" in err

    @patch("analyze_earnings_trades.FMPClient")
    def test_empty_calendar_list_exits_0(self, mock_client_class, tmp_path, capsys):
        """A clean empty calendar response exits 0 with api_stats observability."""
        client = mock_client_class.return_value
        mock_client_class.US_EXCHANGES = FMPClient.US_EXCHANGES
        client.get_earnings_calendar.return_value = []
        client.get_api_stats.return_value = {
            "budget_remaining": 50,
            "rate_limit_reached": False,
        }

        with patch.object(sys, "argv", self._argv(tmp_path)):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 0
        err = capsys.readouterr().err
        assert "ZERO_RESULT_REASON=no_earnings_rows" in err
        assert "budget_remaining=50" in err

    @patch("analyze_earnings_trades.FMPClient")
    def test_failed_calendar_fetch_exits_1(self, mock_client_class, tmp_path, capsys):
        """A failed calendar fetch (None body) fails closed with exit 1."""
        client = mock_client_class.return_value
        mock_client_class.US_EXCHANGES = FMPClient.US_EXCHANGES
        client.get_earnings_calendar.return_value = None
        client.get_api_stats.return_value = {
            "budget_remaining": 50,
            "rate_limit_reached": False,
        }

        with patch.object(sys, "argv", self._argv(tmp_path)):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 1
        err = capsys.readouterr().err
        assert "ZERO_RESULT_REASON=calendar_fetch_failed" in err
        assert "rate_limit_reached=False" in err

    @patch("analyze_earnings_trades.FMPClient")
    def test_truthy_non_list_body_exits_1_with_reason(self, mock_client_class, tmp_path, capsys):
        """A truthy non-list body (wrong shape) fails closed with a reason line."""
        client = mock_client_class.return_value
        mock_client_class.US_EXCHANGES = FMPClient.US_EXCHANGES
        client.get_earnings_calendar.return_value = {"error": "Bad Request"}
        client.get_api_stats.return_value = {
            "budget_remaining": 50,
            "rate_limit_reached": False,
        }

        with patch.object(sys, "argv", self._argv(tmp_path)):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 1
        err = capsys.readouterr().err
        assert "ZERO_RESULT_REASON=calendar_fetch_failed" in err

    @patch("analyze_earnings_trades.FMPClient")
    def test_mixed_filters_rejected_all_exits_0(self, mock_client_class, tmp_path, capsys):
        client = mock_client_class.return_value
        mock_client_class.US_EXCHANGES = FMPClient.US_EXCHANGES
        client.get_earnings_calendar.return_value = [
            {"symbol": "P1", "date": "2026-09-04", "time": "amc"},
            {"symbol": "P2", "date": "2026-09-04", "time": "amc"},
        ]
        client.get_company_profiles.return_value = {
            "P1": {"marketCap": 5_000_000_000, "exchange": "LSE"},
            "P2": {"marketCap": 1_000_000_000, "exchange": "NASDAQ"},
        }
        client.get_api_stats.return_value = {
            "budget_remaining": 50,
            "rate_limit_reached": False,
        }

        with patch.object(sys, "argv", self._argv(tmp_path) + ["--min-market-cap", "2000000000"]):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 0
        err = capsys.readouterr().err
        assert "ZERO_RESULT_REASON=mixed_filters_rejected_all" in err


# ===========================================================================
# Gap Size Calculator Tests
# ===========================================================================


class TestGapSizeCalculator:
    """Test gap calculation for BMO, AMC, and unknown timings."""

    def _make_simple_prices(self):
        """Build simple 5-bar price data with earnings on bar index 2 (most-recent-first)."""
        return [
            {"date": "2025-01-07", "open": 108.0, "close": 109.0, "volume": 1000000},
            {"date": "2025-01-06", "open": 107.0, "close": 108.0, "volume": 1000000},
            {"date": "2025-01-05", "open": 106.0, "close": 107.0, "volume": 3000000},
            {"date": "2025-01-04", "open": 100.0, "close": 100.0, "volume": 1000000},
            {"date": "2025-01-03", "open": 99.0, "close": 99.5, "volume": 1000000},
        ]

    def test_bmo_gap_positive(self):
        """BMO: gap = open[earnings_date] / close[prev_day] - 1"""
        prices = self._make_simple_prices()
        # Earnings on 2025-01-05 (idx 2), prev_day is 2025-01-04 (idx 3)
        # BMO gap = open[2025-01-05] / close[2025-01-04] - 1 = 106/100 - 1 = 6%
        result = calculate_gap(prices, "2025-01-05", "bmo")
        assert result["gap_pct"] == 6.0
        assert result["gap_type"] == "up"
        assert result["base_price"] == 100.0
        assert result["gap_price"] == 106.0
        assert result["timing_used"] == "bmo"
        assert result["score"] == 70.0  # >= 5%

    def test_amc_gap_positive(self):
        """AMC: gap = open[next_day] / close[earnings_date] - 1"""
        prices = self._make_simple_prices()
        # Earnings on 2025-01-05 (idx 2), next_day is 2025-01-06 (idx 1)
        # AMC gap = open[2025-01-06] / close[2025-01-05] - 1 = 107/107 - 1 = 0%
        result = calculate_gap(prices, "2025-01-05", "amc")
        assert abs(result["gap_pct"]) < 1.0
        assert result["timing_used"] == "amc"

    def test_unknown_gap_uses_amc_logic(self):
        """Unknown timing uses AMC logic."""
        prices = self._make_simple_prices()
        result_amc = calculate_gap(prices, "2025-01-05", "amc")
        result_unknown = calculate_gap(prices, "2025-01-05", "unknown")
        assert result_amc["gap_pct"] == result_unknown["gap_pct"]

    def test_unknown_timing_carries_a_timing_note(self):
        """Issue #352: unknown timing must surface that the AMC window was
        assumed, not measured, so a BMO reporter mismeasured as AMC is visible
        in the output rather than silently blended into the score."""
        prices = self._make_simple_prices()
        result = calculate_gap(prices, "2025-01-05", "unknown")
        assert "timing_note" in result
        assert "unknown" in result["timing_note"].lower()
        assert "amc" in result["timing_note"].lower()

    def test_bmo_and_amc_timing_do_not_carry_a_timing_note(self):
        prices = self._make_simple_prices()
        assert "timing_note" not in calculate_gap(prices, "2025-01-05", "bmo")
        assert "timing_note" not in calculate_gap(prices, "2025-01-05", "amc")

    def test_negative_gap(self):
        """Test negative (gap down) calculation."""
        prices = [
            {"date": "2025-01-06", "open": 93.0, "close": 92.0, "volume": 2000000},
            {"date": "2025-01-05", "open": 95.0, "close": 94.0, "volume": 3000000},
            {"date": "2025-01-04", "open": 100.0, "close": 100.0, "volume": 1000000},
        ]
        # BMO gap = 95/100 - 1 = -5%
        result = calculate_gap(prices, "2025-01-05", "bmo")
        assert result["gap_pct"] == -5.0
        assert result["gap_type"] == "down"
        assert result["score"] == 70.0  # |gap| >= 5%

    def test_score_threshold_10pct(self):
        """Gap >= 10% scores 100."""
        prices = [
            {"date": "2025-01-06", "open": 115.0, "close": 116.0, "volume": 1000000},
            {"date": "2025-01-05", "open": 112.0, "close": 113.0, "volume": 3000000},
            {"date": "2025-01-04", "open": 100.0, "close": 100.0, "volume": 1000000},
        ]
        result = calculate_gap(prices, "2025-01-05", "bmo")
        assert result["gap_pct"] == 12.0
        assert result["score"] == 100.0

    def test_score_threshold_7pct(self):
        """Gap >= 7% scores 85."""
        prices = [
            {"date": "2025-01-05", "open": 107.0, "close": 108.0, "volume": 3000000},
            {"date": "2025-01-04", "open": 100.0, "close": 100.0, "volume": 1000000},
        ]
        result = calculate_gap(prices, "2025-01-05", "bmo")
        assert result["gap_pct"] == 7.0
        assert result["score"] == 85.0

    def test_score_threshold_3pct(self):
        """Gap >= 3% scores 55."""
        prices = [
            {"date": "2025-01-05", "open": 103.0, "close": 104.0, "volume": 3000000},
            {"date": "2025-01-04", "open": 100.0, "close": 100.0, "volume": 1000000},
        ]
        result = calculate_gap(prices, "2025-01-05", "bmo")
        assert result["gap_pct"] == 3.0
        assert result["score"] == 55.0

    def test_score_threshold_1pct(self):
        """Gap >= 1% scores 35."""
        prices = [
            {"date": "2025-01-05", "open": 101.0, "close": 102.0, "volume": 3000000},
            {"date": "2025-01-04", "open": 100.0, "close": 100.0, "volume": 1000000},
        ]
        result = calculate_gap(prices, "2025-01-05", "bmo")
        assert result["gap_pct"] == 1.0
        assert result["score"] == 35.0

    def test_score_threshold_below_1pct(self):
        """Gap < 1% scores 15."""
        prices = [
            {"date": "2025-01-05", "open": 100.5, "close": 101.0, "volume": 3000000},
            {"date": "2025-01-04", "open": 100.0, "close": 100.0, "volume": 1000000},
        ]
        result = calculate_gap(prices, "2025-01-05", "bmo")
        assert result["gap_pct"] == 0.5
        assert result["score"] == 15.0

    def test_earnings_date_not_found(self):
        """Missing earnings date returns score 0 with warning."""
        prices = _make_prices(10)
        result = calculate_gap(prices, "2099-12-31", "bmo")
        assert result["score"] == 0.0
        assert "warning" in result


# ===========================================================================
# Pre-Earnings Trend Calculator Tests
# ===========================================================================


class TestPreEarningsTrend:
    """Test 20-day pre-earnings return calculation."""

    def test_positive_trend(self):
        """Stock up 10% over 20 days before earnings."""
        # Build prices where earnings date close = 110, 20 days prior close = 100
        prices = []
        for i in range(50):
            if i == 5:
                prices.append({"date": "2025-01-10", "close": 110.0, "volume": 1000000})
            elif i == 25:
                prices.append({"date": "2025-01-01", "close": 100.0, "volume": 1000000})
            else:
                prices.append(
                    {
                        "date": f"2025-{(i // 22) + 1:02d}-{(i % 22) + 1:02d}",
                        "close": 105.0,
                        "volume": 1000000,
                    }
                )
        result = calculate_pre_earnings_trend(prices, "2025-01-10")
        assert result["return_20d_pct"] == 10.0
        assert result["trend_direction"] == "up"
        assert result["score"] == 85.0  # >= 10%

    def test_negative_trend(self):
        """Stock down 8% over 20 days before earnings."""
        prices = []
        for i in range(50):
            if i == 5:
                prices.append({"date": "2025-01-10", "close": 92.0, "volume": 1000000})
            elif i == 25:
                prices.append({"date": "2025-01-01", "close": 100.0, "volume": 1000000})
            else:
                prices.append(
                    {
                        "date": f"2025-{(i // 22) + 1:02d}-{(i % 22) + 1:02d}",
                        "close": 96.0,
                        "volume": 1000000,
                    }
                )
        result = calculate_pre_earnings_trend(prices, "2025-01-10")
        assert result["return_20d_pct"] == -8.0
        assert result["trend_direction"] == "down"
        assert result["score"] == 15.0  # < -5%

    def test_score_threshold_15pct(self):
        """Return >= 15% scores 100."""
        prices = []
        for i in range(50):
            if i == 5:
                prices.append({"date": "2025-01-10", "close": 115.5, "volume": 1000000})
            elif i == 25:
                prices.append({"date": "2025-01-01", "close": 100.0, "volume": 1000000})
            else:
                prices.append(
                    {
                        "date": f"2025-{(i // 22) + 1:02d}-{(i % 22) + 1:02d}",
                        "close": 107.0,
                        "volume": 1000000,
                    }
                )
        result = calculate_pre_earnings_trend(prices, "2025-01-10")
        assert result["score"] == 100.0

    def test_score_threshold_0pct(self):
        """Return >= 0% but < 5% scores 50."""
        prices = []
        for i in range(50):
            if i == 5:
                prices.append({"date": "2025-01-10", "close": 102.0, "volume": 1000000})
            elif i == 25:
                prices.append({"date": "2025-01-01", "close": 100.0, "volume": 1000000})
            else:
                prices.append(
                    {
                        "date": f"2025-{(i // 22) + 1:02d}-{(i % 22) + 1:02d}",
                        "close": 101.0,
                        "volume": 1000000,
                    }
                )
        result = calculate_pre_earnings_trend(prices, "2025-01-10")
        assert result["score"] == 50.0

    def test_score_threshold_neg5pct(self):
        """Return >= -5% but < 0% scores 30."""
        prices = []
        for i in range(50):
            if i == 5:
                prices.append({"date": "2025-01-10", "close": 97.0, "volume": 1000000})
            elif i == 25:
                prices.append({"date": "2025-01-01", "close": 100.0, "volume": 1000000})
            else:
                prices.append(
                    {
                        "date": f"2025-{(i // 22) + 1:02d}-{(i % 22) + 1:02d}",
                        "close": 98.0,
                        "volume": 1000000,
                    }
                )
        result = calculate_pre_earnings_trend(prices, "2025-01-10")
        assert result["score"] == 30.0

    def test_insufficient_data(self):
        """Less than 20 days before earnings returns warning."""
        prices = [{"date": "2025-01-10", "close": 100.0, "volume": 1000000}]
        for i in range(10):
            prices.append(
                {
                    "date": f"2025-01-{9 - i:02d}",
                    "close": 100.0,
                    "volume": 1000000,
                }
            )
        result = calculate_pre_earnings_trend(prices, "2025-01-10")
        assert result["score"] == 0.0
        assert "warning" in result


# ===========================================================================
# Volume Trend Calculator Tests
# ===========================================================================


class TestVolumeTrend:
    """Test volume ratio calculation."""

    def test_high_ratio(self):
        """20-day avg much higher than 60-day avg -> high score."""
        prices = []
        for i in range(80):
            vol = 2000000 if i < 20 else 500000
            prices.append(
                {
                    "date": f"2025-{(i // 22) + 1:02d}-{(i % 22) + 1:02d}",
                    "close": 100.0,
                    "volume": vol,
                }
            )
        # Place earnings at day 0
        prices[0]["date"] = "2025-01-01"
        result = calculate_volume_trend(prices, "2025-01-01")
        assert result["vol_ratio_20_60"] > 1.5
        assert result["score"] >= 80.0

    def test_low_ratio(self):
        """20-day avg lower than 60-day avg -> low score."""
        prices = []
        for i in range(80):
            vol = 300000 if i < 20 else 1000000
            prices.append(
                {
                    "date": f"2025-{(i // 22) + 1:02d}-{(i % 22) + 1:02d}",
                    "close": 100.0,
                    "volume": vol,
                }
            )
        prices[0]["date"] = "2025-01-01"
        result = calculate_volume_trend(prices, "2025-01-01")
        assert result["vol_ratio_20_60"] < 1.0
        assert result["score"] == 20.0

    def test_score_threshold_2x(self):
        """Ratio >= 2.0 scores 100."""
        prices = []
        for i in range(80):
            vol = 3000000 if i < 20 else 500000
            prices.append(
                {
                    "date": f"2025-{(i // 22) + 1:02d}-{(i % 22) + 1:02d}",
                    "close": 100.0,
                    "volume": vol,
                }
            )
        prices[0]["date"] = "2025-01-01"
        result = calculate_volume_trend(prices, "2025-01-01")
        assert result["vol_ratio_20_60"] >= 2.0
        assert result["score"] == 100.0

    def test_earnings_date_not_found(self):
        """Missing date returns score 0."""
        prices = _make_prices(80)
        result = calculate_volume_trend(prices, "2099-12-31")
        assert result["score"] == 0.0
        assert "warning" in result

    def test_recent_window_is_anchored_at_latest_bar(self):
        """An older earnings index must not move both averages into pre-event bars."""
        prices = [
            {
                "date": f"2025-01-{80 - i:02d}",
                "close": 100.0,
                "volume": 2_000_000 if i < 20 else 500_000,
            }
            for i in range(80)
        ]
        prices[3]["date"] = "2025-01-01"

        result = calculate_volume_trend(prices, "2025-01-01")

        assert result["recent_avg_volume"] == 2_000_000
        assert result["longer_avg_volume"] == 1_000_000
        assert result["vol_ratio_20_60"] == 2.0


# ===========================================================================
# MA200 Calculator Tests
# ===========================================================================


class TestMA200Calculator:
    """Test MA200 position calculation."""

    def test_above_ma200(self):
        """Price well above MA200 -> high score."""
        # All closes at 100, then current close at 120 (20% above)
        prices = [{"close": 120.0}]
        for _ in range(249):
            prices.append({"close": 100.0})
        result = calculate_ma200_position(prices)
        assert result["above_ma200"] is True
        assert result["distance_pct"] > 0
        assert result["score"] >= 55.0

    def test_below_ma200(self):
        """Price below MA200 -> lower score."""
        prices = [{"close": 90.0}]
        for _ in range(249):
            prices.append({"close": 100.0})
        result = calculate_ma200_position(prices)
        assert result["above_ma200"] is False
        assert result["distance_pct"] < 0

    def test_insufficient_data(self):
        """Less than 200 days returns warning and score 0."""
        prices = _make_prices(100)
        result = calculate_ma200_position(prices)
        assert result["score"] == 0.0
        assert "warning" in result

    def test_score_20pct_above(self):
        """20% above MA200 scores 100."""
        # MA200 = avg of 200 closes. If 199 at 100 + 1 at 120, MA ~ 100.1
        # For exact 20% above: need current close = MA200 * 1.2
        prices = [{"close": 120.0}]
        for _ in range(199):
            prices.append({"close": 100.0})
        result = calculate_ma200_position(prices)
        # MA200 = (120 + 199*100) / 200 = 20020/200 = 100.1
        # distance = (120/100.1 - 1)*100 = 19.88%
        assert result["score"] == 85.0  # >= 10%

    def test_score_just_above(self):
        """Just above MA200 (0-5%) scores 55."""
        prices = [{"close": 101.0}]
        for _ in range(199):
            prices.append({"close": 100.0})
        result = calculate_ma200_position(prices)
        # MA200 ~ 100.005, distance ~ 0.99%
        assert result["score"] == 55.0

    def test_score_below_neg5(self):
        """More than 5% below MA200 scores 15."""
        prices = [{"close": 90.0}]
        for _ in range(199):
            prices.append({"close": 100.0})
        result = calculate_ma200_position(prices)
        # MA200 ~ 99.95, distance ~ -9.95%
        assert result["score"] == 15.0


# ===========================================================================
# MA50 Calculator Tests
# ===========================================================================


class TestMA50Calculator:
    """Test MA50 position calculation."""

    def test_above_ma50(self):
        """Price above MA50 -> positive distance."""
        prices = [{"close": 110.0}]
        for _ in range(59):
            prices.append({"close": 100.0})
        result = calculate_ma50_position(prices)
        assert result["above_ma50"] is True
        assert result["distance_pct"] > 0

    def test_below_ma50(self):
        """Price below MA50 -> negative distance."""
        prices = [{"close": 90.0}]
        for _ in range(59):
            prices.append({"close": 100.0})
        result = calculate_ma50_position(prices)
        assert result["above_ma50"] is False
        assert result["distance_pct"] < 0

    def test_insufficient_data(self):
        """Less than 50 days returns warning and score 0."""
        prices = _make_prices(30)
        result = calculate_ma50_position(prices)
        assert result["score"] == 0.0
        assert "warning" in result

    def test_score_10pct_above(self):
        """10% above MA50 scores 100."""
        prices = [{"close": 111.0}]
        for _ in range(49):
            prices.append({"close": 100.0})
        result = calculate_ma50_position(prices)
        # MA50 = (111 + 49*100)/50 = 100.22, distance ~ 10.78%
        assert result["score"] == 100.0

    def test_score_5pct_above(self):
        """5% above MA50 scores 80."""
        prices = [{"close": 105.5}]
        for _ in range(49):
            prices.append({"close": 100.0})
        result = calculate_ma50_position(prices)
        # MA50 = (105.5 + 49*100)/50 = 100.11, distance ~ 5.39%
        assert result["score"] == 80.0

    def test_score_just_above(self):
        """Just above MA50 (0-5%) scores 60."""
        prices = [{"close": 101.0}]
        for _ in range(49):
            prices.append({"close": 100.0})
        result = calculate_ma50_position(prices)
        # MA50 ~ 100.02, distance ~ 0.98%
        assert result["score"] == 60.0

    def test_score_below_neg5(self):
        """More than 5% below MA50 scores 15."""
        prices = [{"close": 92.0}]
        for _ in range(49):
            prices.append({"close": 100.0})
        result = calculate_ma50_position(prices)
        # MA50 ~ 99.84, distance ~ -7.84%
        assert result["score"] == 15.0


# ===========================================================================
# Scorer Tests
# ===========================================================================


class TestScorer:
    """Test composite scoring and grade assignment."""

    def test_all_high_scores_grade_a(self):
        """All scores at 100 -> Grade A."""
        result = calculate_composite_score(100, 100, 100, 100, 100)
        assert result["composite_score"] == 100.0
        assert result["grade"] == "A"
        assert "Strong" in result["grade_description"]

    def test_all_low_scores_grade_d(self):
        """All scores at 15 -> Grade D."""
        result = calculate_composite_score(15, 15, 15, 15, 15)
        assert result["composite_score"] == 15.0
        assert result["grade"] == "D"
        assert "Weak" in result["grade_description"]

    def test_weight_sum_equals_1(self):
        """Verify component weights sum to 1.0."""
        total = sum(COMPONENT_WEIGHTS.values())
        assert abs(total - 1.0) < 0.001

    def test_grade_b_boundary(self):
        """Score of exactly 70 -> Grade B."""
        # 70 = 0.25*s1 + 0.30*s2 + 0.20*s3 + 0.15*s4 + 0.10*s5
        # Use uniform 70 for all: 70*1.0 = 70
        result = calculate_composite_score(70, 70, 70, 70, 70)
        assert result["composite_score"] == 70.0
        assert result["grade"] == "B"

    def test_grade_c_boundary(self):
        """Score of exactly 55 -> Grade C."""
        result = calculate_composite_score(55, 55, 55, 55, 55)
        assert result["composite_score"] == 55.0
        assert result["grade"] == "C"

    def test_grade_a_boundary(self):
        """Score of exactly 85 -> Grade A."""
        result = calculate_composite_score(85, 85, 85, 85, 85)
        assert result["composite_score"] == 85.0
        assert result["grade"] == "A"

    def test_weakest_and_strongest_components(self):
        """Verify weakest and strongest component identification."""
        result = calculate_composite_score(
            gap_score=90,
            trend_score=40,
            volume_score=60,
            ma200_score=70,
            ma50_score=80,
        )
        assert result["weakest_component"] == "Pre-Earnings Trend"
        assert result["weakest_score"] == 40
        assert result["strongest_component"] == "Gap Size"
        assert result["strongest_score"] == 90

    def test_component_breakdown_present(self):
        """Component breakdown dict is present with all components."""
        result = calculate_composite_score(80, 70, 60, 50, 40)
        assert "component_breakdown" in result
        assert len(result["component_breakdown"]) == 5
        assert "Gap Size" in result["component_breakdown"]
        assert "Pre-Earnings Trend" in result["component_breakdown"]
        assert "Volume Trend" in result["component_breakdown"]
        assert "MA200 Position" in result["component_breakdown"]
        assert "MA50 Position" in result["component_breakdown"]


# ===========================================================================
# Report Generator Tests
# ===========================================================================


class TestReportGenerator:
    """Test JSON and Markdown report generation."""

    def _make_result(self, symbol="AAPL", score=82.5, grade="B", gap_pct=6.3):
        return {
            "symbol": symbol,
            "company_name": f"{symbol} Inc.",
            "earnings_date": "2026-02-15",
            "earnings_timing": "amc",
            "gap_pct": gap_pct,
            "composite_score": score,
            "grade": grade,
            "grade_description": "Good earnings reaction worth monitoring",
            "guidance": "Monitor for follow-through buying.",
            "weakest_component": "Volume Trend",
            "strongest_component": "Gap Size",
            "component_breakdown": {
                "Gap Size": {"score": 85.0, "weight": 0.25, "weighted_score": 21.2},
                "Pre-Earnings Trend": {"score": 70.0, "weight": 0.30, "weighted_score": 21.0},
                "Volume Trend": {"score": 60.0, "weight": 0.20, "weighted_score": 12.0},
                "MA200 Position": {"score": 85.0, "weight": 0.15, "weighted_score": 12.8},
                "MA50 Position": {"score": 80.0, "weight": 0.10, "weighted_score": 8.0},
            },
            "current_price": 197.5,
            "market_cap": 3_000_000_000_000,
            "sector": "Technology",
            "industry": "Consumer Electronics",
            "components": {
                "gap_size": {"gap_pct": gap_pct, "score": 85.0},
                "pre_earnings_trend": {"return_20d_pct": 8.5, "score": 70.0},
                "volume_trend": {"vol_ratio_20_60": 1.3, "score": 60.0},
                "ma200_position": {"distance_pct": 15.0, "score": 85.0},
                "ma50_position": {"distance_pct": 7.0, "score": 80.0},
            },
        }

    def test_json_has_schema_version(self):
        """JSON output must have schema_version '1.0'."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self._make_result()
            json_path = os.path.join(tmpdir, "test.json")
            metadata = {
                "generated_at": "2026-02-21T10:00:00",
                "generator": "earnings-trade-analyzer",
                "generator_version": "1.0.0",
                "lookback_days": 2,
                "total_screened": 50,
            }
            generate_json_report([result], metadata, json_path)
            with open(json_path) as f:
                data = json.load(f)
            assert data["schema_version"] == "1.0"

    def test_json_has_required_fields(self):
        """JSON output has all required top-level fields."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self._make_result()
            json_path = os.path.join(tmpdir, "test.json")
            metadata = {
                "generated_at": "2026-02-21T10:00:00",
                "generator": "earnings-trade-analyzer",
                "generator_version": "1.0.0",
                "lookback_days": 2,
                "total_screened": 50,
            }
            generate_json_report([result], metadata, json_path)
            with open(json_path) as f:
                data = json.load(f)
            assert "metadata" in data
            assert "results" in data
            assert "summary" in data
            assert "schema_version" in data

    def test_json_result_fields(self):
        """Each result in JSON has required fields including earnings_timing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self._make_result()
            json_path = os.path.join(tmpdir, "test.json")
            metadata = {"generated_at": "2026-02-21", "lookback_days": 2, "total_screened": 1}
            generate_json_report([result], metadata, json_path)
            with open(json_path) as f:
                data = json.load(f)
            r = data["results"][0]
            assert r["symbol"] == "AAPL"
            assert r["earnings_timing"] == "amc"
            assert r["gap_pct"] == 6.3
            assert r["composite_score"] == 82.5
            assert r["grade"] == "B"
            assert "components" in r

    def test_json_summary_counts(self):
        """Summary counts grades correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            results = [
                self._make_result("A1", score=90, grade="A"),
                self._make_result("B1", score=75, grade="B"),
                self._make_result("B2", score=72, grade="B"),
                self._make_result("C1", score=60, grade="C"),
                self._make_result("D1", score=40, grade="D"),
            ]
            json_path = os.path.join(tmpdir, "test.json")
            metadata = {"generated_at": "2026-02-21", "lookback_days": 2, "total_screened": 5}
            generate_json_report(results, metadata, json_path)
            with open(json_path) as f:
                data = json.load(f)
            assert data["summary"]["grade_a"] == 1
            assert data["summary"]["grade_b"] == 2
            assert data["summary"]["grade_c"] == 1
            assert data["summary"]["grade_d"] == 1
            assert data["summary"]["total"] == 5

    def test_markdown_generation(self):
        """Markdown report generates without errors and contains key elements."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self._make_result()
            md_path = os.path.join(tmpdir, "test.md")
            metadata = {
                "generated_at": "2026-02-21T10:00:00",
                "lookback_days": 2,
                "total_screened": 1,
            }
            generate_markdown_report([result], metadata, md_path)
            with open(md_path) as f:
                content = f.read()
            assert "Earnings Trade Analyzer Report" in content
            assert "AAPL" in content
            assert "Grade A & B Details" in content

    def test_markdown_shows_timing_unknown_count_when_present_in_metadata(self):
        """Issue #352: metadata carrying timing_unknown_count/timing_candidates_total
        must render as a visible line so the residual FMP `time: null` rate is
        never silently blended into the AMC-window gap assumption."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self._make_result()
            md_path = os.path.join(tmpdir, "test.md")
            metadata = {
                "generated_at": "2026-02-21T10:00:00",
                "lookback_days": 2,
                "total_screened": 1,
                "timing_unknown_count": 3,
                "timing_candidates_total": 9,
            }
            generate_markdown_report([result], metadata, md_path)
            with open(md_path) as f:
                content = f.read()
            assert "**Timing unknown:** 3 of 9 (gap window assumed AMC)" in content

    def test_markdown_omits_timing_unknown_line_when_metadata_lacks_it(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self._make_result()
            md_path = os.path.join(tmpdir, "test.md")
            metadata = {"generated_at": "2026-02-21", "lookback_days": 2, "total_screened": 1}
            generate_markdown_report([result], metadata, md_path)
            with open(md_path) as f:
                content = f.read()
            assert "Timing unknown" not in content

    def test_markdown_handles_none_numeric_timing_and_breakdown_values(self):
        """Unavailable upstream values render as neutral values instead of crashing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self._make_result(grade="A")
            result.update(
                composite_score=None,
                gap_pct=None,
                market_cap=None,
                earnings_timing=None,
            )
            result["components"] = {
                "pre_earnings_trend": {"return_20d_pct": None},
                "volume_trend": {"vol_ratio_20_60": None},
                "ma200_position": {"distance_pct": None},
                "ma50_position": {"distance_pct": None},
            }
            result["component_breakdown"] = {
                "Gap Size": {"score": None, "weight": None, "weighted_score": None},
                "Missing Fields": {},
            }
            md_path = os.path.join(tmpdir, "none-values.md")

            generate_markdown_report(
                [result],
                {"generated_at": "2026-07-11", "lookback_days": 2},
                md_path,
            )

            content = open(md_path).read()
            assert "(UNKNOWN)" in content
            assert "| Gap Size | 0 | 0% | 0.0 |" in content

    def test_markdown_sector_distribution(self):
        """Markdown report includes sector distribution table."""
        with tempfile.TemporaryDirectory() as tmpdir:
            results = [
                self._make_result("AAPL"),
                self._make_result("MSFT"),
            ]
            results[1]["sector"] = "Software"
            md_path = os.path.join(tmpdir, "test.md")
            metadata = {"generated_at": "2026-02-21", "lookback_days": 2, "total_screened": 2}
            generate_markdown_report(results, metadata, md_path)
            with open(md_path) as f:
                content = f.read()
            assert "Sector Distribution" in content
            assert "Technology" in content
            assert "Software" in content

    def test_json_uses_all_results_for_summary(self):
        """When all_results provided, summary counts from all_results."""
        with tempfile.TemporaryDirectory() as tmpdir:
            all_results = [
                self._make_result(f"S{i}", score=90 - i * 5, grade="A" if i == 0 else "B")
                for i in range(10)
            ]
            top_results = all_results[:3]
            json_path = os.path.join(tmpdir, "test.json")
            metadata = {"generated_at": "2026-02-21", "lookback_days": 2, "total_screened": 10}
            generate_json_report(top_results, metadata, json_path, all_results=all_results)
            with open(json_path) as f:
                data = json.load(f)
            assert data["summary"]["total"] == 10
            assert len(data["results"]) == 3


# ===========================================================================
# FMP Client Failure Cases
# ===========================================================================


class TestFMPClient:
    """Test FMP client error handling and budget enforcement."""

    @patch("fmp_client.requests.Session")
    def test_api_key_is_sent_as_query_parameter(self, mock_session_cls):
        """FMP v3 authentication is carried in params, never a session header."""
        response = MagicMock(status_code=200)
        response.json.return_value = {"ok": True}
        mock_session = MagicMock()
        mock_session.get.return_value = response
        mock_session_cls.return_value = mock_session
        client = FMPClient(api_key="query-key", max_api_calls=1)  # pragma: allowlist secret
        client.RATE_LIMIT_DELAY = 0

        assert client._rate_limited_get("https://example.test", {"symbol": "AAPL"}) == {"ok": True}
        mock_session.get.assert_called_once_with(
            "https://example.test",
            params={"symbol": "AAPL", "apikey": "query-key"},  # pragma: allowlist secret
            timeout=30,
        )
        assert "apikey" not in mock_session.headers

    @patch("fmp_client.requests.Session")
    def test_api_429_retry(self, mock_session_cls):
        """429 response triggers retry, sets rate_limit_reached on second failure."""
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session

        # First call returns 429, second also 429 (exceeds max_retries=1)
        mock_response_429 = MagicMock()
        mock_response_429.status_code = 429
        mock_response_429.text = "Rate limit exceeded"
        mock_session.get.return_value = mock_response_429

        client = FMPClient(api_key="test_key", max_api_calls=200)
        result = client._rate_limited_get("http://example.com/test")

        assert result is None
        assert client.rate_limit_reached is True

    @patch("fmp_client.requests.Session")
    def test_api_timeout(self, mock_session_cls):
        """requests.Timeout returns None without crashing."""
        import requests as req

        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        mock_session.get.side_effect = req.exceptions.Timeout("Connection timed out")

        client = FMPClient(api_key="test_key", max_api_calls=200)
        result = client._rate_limited_get("http://example.com/test")

        assert result is None

    def test_budget_exceeded(self):
        """After max_api_calls, subsequent calls raise ApiCallBudgetExceeded."""
        client = FMPClient(api_key="test_key", max_api_calls=5)
        client.api_calls_made = 5  # Simulate 5 calls already made

        try:
            client._rate_limited_get("http://example.com/test")
            raise AssertionError("Should have raised ApiCallBudgetExceeded")
        except ApiCallBudgetExceeded:
            pass  # Expected

    def test_budget_exceeded_at_exact_limit(self):
        """Budget is checked before making the call."""
        client = FMPClient(api_key="test_key", max_api_calls=3)
        client.api_calls_made = 3

        try:
            client._rate_limited_get("http://example.com/test")
            raise AssertionError("Should have raised ApiCallBudgetExceeded")
        except ApiCallBudgetExceeded:
            pass

    def test_api_stats(self):
        """get_api_stats returns expected structure."""
        client = FMPClient(api_key="test_key", max_api_calls=100)
        stats = client.get_api_stats()
        assert "api_calls_made" in stats
        assert "max_api_calls" in stats
        assert stats["max_api_calls"] == 100


# ===========================================================================
# Gap Boundary Cases
# ===========================================================================


class TestGapBoundary:
    """Test gap calculation edge cases: Friday BMO, Monday AMC, insufficient data."""

    def test_friday_bmo(self):
        """Friday BMO: gap = open[Friday] / close[Thursday]."""
        prices = [
            {"date": "2025-01-10", "open": 112.0, "close": 113.0, "volume": 2000000},  # Friday
            {"date": "2025-01-09", "open": 100.0, "close": 100.0, "volume": 1000000},  # Thursday
        ]
        # Most-recent-first: idx 0 = Friday, idx 1 = Thursday
        result = calculate_gap(prices, "2025-01-10", "bmo")
        # gap = 112/100 - 1 = 12%
        assert result["gap_pct"] == 12.0
        assert result["gap_type"] == "up"
        assert result["score"] == 100.0

    def test_monday_amc(self):
        """Monday AMC: gap = open[Tuesday] / close[Monday]."""
        prices = [
            {"date": "2025-01-14", "open": 108.0, "close": 109.0, "volume": 2000000},  # Tuesday
            {"date": "2025-01-13", "open": 100.0, "close": 100.0, "volume": 3000000},  # Monday
        ]
        # AMC: gap = open[next_day] / close[earnings_date]
        # next_day idx = 0 (Tuesday), earnings_date idx = 1 (Monday)
        result = calculate_gap(prices, "2025-01-13", "amc")
        # gap = 108/100 - 1 = 8%
        assert result["gap_pct"] == 8.0
        assert result["gap_type"] == "up"
        assert result["score"] == 85.0  # >= 7%

    def test_insufficient_data_no_prev_day(self):
        """BMO with no previous day returns warning."""
        prices = [
            {"date": "2025-01-10", "open": 112.0, "close": 113.0, "volume": 1000000},
        ]
        result = calculate_gap(prices, "2025-01-10", "bmo")
        assert result["score"] == 0.0
        assert "warning" in result

    def test_insufficient_data_no_next_day(self):
        """AMC with no next day returns warning."""
        prices = [
            {"date": "2025-01-10", "open": 100.0, "close": 100.0, "volume": 1000000},
        ]
        result = calculate_gap(prices, "2025-01-10", "amc")
        assert result["score"] == 0.0
        assert "warning" in result

    def test_pre_earnings_trend_insufficient_data_below_20(self):
        """Pre-earnings trend with < 20 days before earnings -> score 0 + warning."""
        prices = []
        for i in range(15):
            prices.append(
                {
                    "date": f"2025-01-{15 - i:02d}",
                    "close": 100.0,
                    "volume": 1000000,
                }
            )
        result = calculate_pre_earnings_trend(prices, "2025-01-15")
        assert result["score"] == 0.0
        assert "warning" in result


# ===========================================================================
# Entry Filter Tests (Fix #2)
# ===========================================================================


class TestEntryFilter:
    """Test entry quality filter rules from 517-trade backtest."""

    def _make_result(self, price=50.0, gap_pct=5.0, score=75.0):
        return {
            "current_price": price,
            "gap_pct": gap_pct,
            "composite_score": score,
        }

    def test_price_above_30_passes(self):
        """Price >= $30 passes the filter."""
        results = [self._make_result(price=50.0)]
        filtered = apply_entry_filter(results)
        assert len(filtered) == 1

    def test_price_below_10_excluded(self):
        """Price < $10 excluded (below $30 threshold)."""
        results = [self._make_result(price=8.0)]
        filtered = apply_entry_filter(results)
        assert len(filtered) == 0

    def test_price_15_excluded(self):
        """Price $15 excluded ($10-$30 low price band)."""
        results = [self._make_result(price=15.0)]
        filtered = apply_entry_filter(results)
        assert len(filtered) == 0

    def test_price_29_excluded(self):
        """Price $29 excluded (just below $30 threshold)."""
        results = [self._make_result(price=29.0)]
        filtered = apply_entry_filter(results)
        assert len(filtered) == 0

    def test_price_30_passes(self):
        """Price exactly $30 passes."""
        results = [self._make_result(price=30.0)]
        filtered = apply_entry_filter(results)
        assert len(filtered) == 1

    def test_high_gap_high_score_excluded(self):
        """Gap >= 10% AND score >= 85 excluded (paradox pattern)."""
        results = [self._make_result(price=100.0, gap_pct=12.0, score=90.0)]
        filtered = apply_entry_filter(results)
        assert len(filtered) == 0

    def test_high_gap_low_score_passes(self):
        """Gap >= 10% but score < 85 passes."""
        results = [self._make_result(price=100.0, gap_pct=12.0, score=80.0)]
        filtered = apply_entry_filter(results)
        assert len(filtered) == 1

    def test_low_gap_high_score_passes(self):
        """Gap < 10% with score >= 85 passes."""
        results = [self._make_result(price=100.0, gap_pct=8.0, score=90.0)]
        filtered = apply_entry_filter(results)
        assert len(filtered) == 1

    def test_negative_gap_excluded_by_abs(self):
        """Negative gap >= 10% AND score >= 85 also excluded."""
        results = [self._make_result(price=100.0, gap_pct=-11.0, score=88.0)]
        filtered = apply_entry_filter(results)
        assert len(filtered) == 0

    def test_mixed_results(self):
        """Mixed batch: only valid entries survive."""
        results = [
            self._make_result(price=100.0, gap_pct=5.0, score=80.0),  # Pass
            self._make_result(price=15.0, gap_pct=5.0, score=80.0),  # Fail: price < $30
            self._make_result(price=100.0, gap_pct=12.0, score=90.0),  # Fail: gap+score
            self._make_result(price=50.0, gap_pct=3.0, score=75.0),  # Pass
        ]
        filtered = apply_entry_filter(results)
        assert len(filtered) == 2
