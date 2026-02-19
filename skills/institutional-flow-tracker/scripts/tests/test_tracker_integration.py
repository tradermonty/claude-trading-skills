"""Integration tests for InstitutionalFlowTracker pipeline.

Verifies end-to-end behavior of the screening pipeline including:
- Grade C filtering
- ETF/fund filtering
- Missing screener fields safety
- Share class deduplication
- Output field cleanliness
- Report generation
"""

import os
import pytest
from unittest.mock import patch, MagicMock
from track_institutional_flow import InstitutionalFlowTracker


def _make_holder(holder, shares, change, date="2025-12-31"):
    """Create a holder record matching FMP v3 institutional-holder schema."""
    return {
        "holder": holder,
        "shares": shares,
        "change": change,
        "dateReported": date,
    }


def _make_screener_stock(symbol, company_name="Test Corp", market_cap=5_000_000_000,
                         is_etf=False, is_fund=False, is_active=True, sector="Technology"):
    """Create a screener result matching FMP stock-screener schema."""
    return {
        "symbol": symbol,
        "companyName": company_name,
        "marketCap": market_cap,
        "isEtf": is_etf,
        "isFund": is_fund,
        "isActivelyTrading": is_active,
        "sector": sector,
    }


def _make_grade_a_holders(symbol):
    """Generate holders that produce Grade A data (high genuine ratio, good match)."""
    holders = []
    # Current quarter: 50 genuine holders
    for i in range(50):
        holders.append(_make_holder(f"Fund{i}", 100_000 + i * 1000, 5_000, "2025-12-31"))
    # Previous quarter: 45 of the same holders (match_ratio = 45/50 = 0.9)
    for i in range(45):
        holders.append(_make_holder(f"Fund{i}", 95_000 + i * 1000, 3_000, "2025-09-30"))
    return holders


def _make_grade_c_holders(symbol):
    """Generate holders that produce Grade C data (low genuine ratio)."""
    holders = []
    # Current quarter: almost all new_full (change == shares)
    for i in range(100):
        holders.append(_make_holder(f"NewFund{i}", 1_000, 1_000, "2025-12-31"))
    # A few genuine
    for i in range(3):
        holders.append(_make_holder(f"Old{i}", 50_000, 500, "2025-12-31"))
    # Previous quarter: very few holders
    for i in range(5):
        holders.append(_make_holder(f"Old{i}", 49_500, 200, "2025-09-30"))
    return holders


class TestGradeCFiltering:
    """Grade C stocks must be excluded from screening results."""

    def test_grade_c_stock_excluded(self, monkeypatch):
        tracker = InstitutionalFlowTracker("fake_key")

        monkeypatch.setattr(tracker, "get_stock_screener", lambda **kw: [
            _make_screener_stock("GOOD"),
            _make_screener_stock("BAD"),
        ])

        def mock_holders(symbol):
            if symbol == "GOOD":
                return _make_grade_a_holders(symbol)
            else:
                return _make_grade_c_holders(symbol)

        monkeypatch.setattr(tracker, "get_institutional_holders", mock_holders)

        # Use very low threshold to ensure both stocks would qualify if not filtered
        results = tracker.screen_stocks(
            min_change_percent=0.1,
            min_institutions=1,
            limit=10,
        )

        symbols = [r["symbol"] for r in results]
        assert "GOOD" in symbols
        assert "BAD" not in symbols


class TestETFFiltering:
    """ETFs and funds must be excluded from screening."""

    def test_etf_excluded_from_screening(self, monkeypatch):
        tracker = InstitutionalFlowTracker("fake_key")

        monkeypatch.setattr(tracker, "get_stock_screener", lambda **kw: [
            _make_screener_stock("AAPL", is_etf=False),
            _make_screener_stock("SPY", company_name="SPDR S&P 500", is_etf=True),
            _make_screener_stock("VFINX", company_name="Vanguard Fund", is_fund=True),
        ])

        call_symbols = []

        def mock_holders(symbol):
            call_symbols.append(symbol)
            return _make_grade_a_holders(symbol)

        monkeypatch.setattr(tracker, "get_institutional_holders", mock_holders)

        tracker.screen_stocks(min_change_percent=0.1, min_institutions=1, limit=10)

        # ETF and fund should be filtered BEFORE API calls
        assert "SPY" not in call_symbols
        assert "VFINX" not in call_symbols
        assert "AAPL" in call_symbols


class TestScreenerMissingFields:
    """Screener results with missing isEtf/isFund/isActivelyTrading should pass safely."""

    def test_missing_fields_defaults_to_tradable(self, monkeypatch):
        tracker = InstitutionalFlowTracker("fake_key")

        # Screener result with NO isEtf/isFund/isActivelyTrading fields
        monkeypatch.setattr(tracker, "get_stock_screener", lambda **kw: [
            {"symbol": "NEWCO", "companyName": "New Corp", "marketCap": 5_000_000_000},
        ])
        monkeypatch.setattr(tracker, "get_institutional_holders",
                            lambda sym: _make_grade_a_holders(sym))

        results = tracker.screen_stocks(
            min_change_percent=0.1,
            min_institutions=1,
            limit=10,
        )

        # Should not crash, and NEWCO should be analyzed
        symbols = [r["symbol"] for r in results]
        assert "NEWCO" in symbols


class TestDeduplicationIntegration:
    """BRK-A/B must be deduplicated within the pipeline."""

    def test_brk_deduplicated_in_pipeline(self, monkeypatch):
        tracker = InstitutionalFlowTracker("fake_key")

        monkeypatch.setattr(tracker, "get_stock_screener", lambda **kw: [
            _make_screener_stock("BRK-A", market_cap=800_000_000_000),
            _make_screener_stock("BRK-B", market_cap=800_000_000_000),
            _make_screener_stock("AAPL", market_cap=3_000_000_000_000),
        ])
        monkeypatch.setattr(tracker, "get_institutional_holders",
                            lambda sym: _make_grade_a_holders(sym))

        results = tracker.screen_stocks(
            min_change_percent=0.1,
            min_institutions=1,
            limit=10,
        )

        symbols = [r["symbol"] for r in results]
        brk_count = sum(1 for s in symbols if s.startswith("BRK"))
        assert brk_count == 1, f"Expected 1 BRK variant, got {brk_count}: {symbols}"
        assert "AAPL" in symbols


class TestOutputFieldsClean:
    """Output must not contain removed fields (value_change etc.)."""

    def test_no_value_change_in_output(self, monkeypatch):
        tracker = InstitutionalFlowTracker("fake_key")

        monkeypatch.setattr(tracker, "get_stock_screener", lambda **kw: [
            _make_screener_stock("AAPL"),
        ])
        monkeypatch.setattr(tracker, "get_institutional_holders",
                            lambda sym: _make_grade_a_holders(sym))

        results = tracker.screen_stocks(
            min_change_percent=0.1,
            min_institutions=1,
            limit=10,
        )

        assert len(results) >= 1
        for r in results:
            assert "value_change" not in r, "value_change field should be removed"
            assert "current_value" not in r, "current_value field should be removed"
            assert "previous_value" not in r, "previous_value field should be removed"

    def test_required_fields_present(self, monkeypatch):
        tracker = InstitutionalFlowTracker("fake_key")

        monkeypatch.setattr(tracker, "get_stock_screener", lambda **kw: [
            _make_screener_stock("MSFT"),
        ])
        monkeypatch.setattr(tracker, "get_institutional_holders",
                            lambda sym: _make_grade_a_holders(sym))

        results = tracker.screen_stocks(
            min_change_percent=0.1,
            min_institutions=1,
            limit=10,
        )

        assert len(results) >= 1
        required_fields = [
            "symbol", "company_name", "market_cap", "current_quarter",
            "percent_change", "current_institution_count", "buyers",
            "sellers", "reliability_grade", "genuine_ratio", "top_holders",
        ]
        for r in results:
            for field in required_fields:
                assert field in r, f"Missing required field: {field}"


class TestScreeningReport:
    """generate_report() must produce valid markdown with expected sections."""

    def _make_mock_results(self):
        """Create mock screening results with Grade A and B stocks."""
        return [
            {
                "symbol": "AAPL",
                "company_name": "Apple Inc.",
                "market_cap": 3_000_000_000_000,
                "current_quarter": "2025-12-31",
                "previous_quarter": "2025-09-30",
                "current_total_shares": 5_000_000,
                "previous_total_shares": 4_500_000,
                "shares_change": 500_000,
                "percent_change": 11.11,
                "current_institution_count": 200,
                "previous_institution_count": 190,
                "institution_count_change": 10,
                "buyers": 120,
                "sellers": 50,
                "unchanged": 30,
                "top_holders": [
                    {"name": "Vanguard", "shares": 1_000_000, "change": 50_000},
                    {"name": "BlackRock", "shares": 900_000, "change": 30_000},
                ],
                "reliability_grade": "A",
                "genuine_ratio": 0.85,
            },
            {
                "symbol": "TSLA",
                "company_name": "Tesla Inc.",
                "market_cap": 800_000_000_000,
                "current_quarter": "2025-12-31",
                "previous_quarter": "2025-09-30",
                "current_total_shares": 2_000_000,
                "previous_total_shares": 2_200_000,
                "shares_change": -200_000,
                "percent_change": -9.09,
                "current_institution_count": 150,
                "previous_institution_count": 160,
                "institution_count_change": -10,
                "buyers": 40,
                "sellers": 80,
                "unchanged": 30,
                "top_holders": [
                    {"name": "ARK Invest", "shares": 500_000, "change": -100_000},
                ],
                "reliability_grade": "B",
                "genuine_ratio": 0.45,
            },
        ]

    def test_report_contains_grade_a_or_b(self, tmp_path):
        tracker = InstitutionalFlowTracker("fake_key")
        results = self._make_mock_results()
        report = tracker.generate_report(results, output_dir=str(tmp_path))

        assert "Grade A" in report or "Grade B" in report

    def test_report_detailed_results_exclude_grade_c(self, tmp_path):
        """Detailed Results section should only contain Grade A/B stocks."""
        tracker = InstitutionalFlowTracker("fake_key")
        results = self._make_mock_results()
        report = tracker.generate_report(results, output_dir=str(tmp_path))

        # Extract the Detailed Results section
        detailed = report.split("## Detailed Results")[1].split("## Methodology")[0]
        assert "Grade C" not in detailed

    def test_report_grade_a_mentions_match_ratio(self, tmp_path):
        tracker = InstitutionalFlowTracker("fake_key")
        results = self._make_mock_results()
        report = tracker.generate_report(results, output_dir=str(tmp_path))

        assert "match ratio" in report.lower() or "match" in report.lower()
