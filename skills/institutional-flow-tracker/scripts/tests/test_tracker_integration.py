"""Integration tests for InstitutionalFlowTracker pipeline (/stable aggregate).

Verifies end-to-end behavior of the screening pipeline including:
- Grade C filtering (no prior quarter / thin breadth)
- ETF/fund filtering before API calls
- Missing screener fields safety
- Share class deduplication
- Output field cleanliness
- Report generation
"""

import datetime

from track_institutional_flow import InstitutionalFlowTracker

# Deterministic "as of" so latest_summary resolves to a fixed quarter in tests.
AS_OF = datetime.date(2026, 3, 31)


def _make_summary(
    investors=200,
    last_investors=190,
    shares=5_000_000,
    last_shares=4_500_000,
    increased=120,
    reduced=50,
    new=20,
    closed=10,
    ownership=65.0,
    date="2026-03-31",
):
    """Build a /stable symbol-positions-summary row."""
    return {
        "date": date,
        "investorsHolding": investors,
        "lastInvestorsHolding": last_investors,
        "investorsHoldingChange": investors - last_investors,
        "numberOf13Fshares": shares,
        "lastNumberOf13Fshares": last_shares,
        "numberOf13FsharesChange": shares - last_shares,
        "increasedPositions": increased,
        "reducedPositions": reduced,
        "newPositions": new,
        "closedPositions": closed,
        "ownershipPercent": ownership,
        "ownershipPercentChange": 1.2,
    }


def _make_top_holders():
    return [
        {
            "name": "Vanguard",
            "shares": 1_000_000,
            "change": 50_000,
            "is_new": False,
            "is_sold_out": False,
        },
        {
            "name": "BlackRock",
            "shares": 900_000,
            "change": 30_000,
            "is_new": False,
            "is_sold_out": False,
        },
    ]


def _make_screener_stock(
    symbol,
    company_name="Test Corp",
    market_cap=5_000_000_000,
    is_etf=False,
    is_fund=False,
    is_active=True,
    sector="Technology",
):
    """Create a screener result matching FMP company-screener schema."""
    return {
        "symbol": symbol,
        "companyName": company_name,
        "marketCap": market_cap,
        "isEtf": is_etf,
        "isFund": is_fund,
        "isActivelyTrading": is_active,
        "sector": sector,
    }


class TestGradeCFiltering:
    """Grade C stocks (no prior quarter / thin breadth) must be excluded."""

    def test_grade_c_stock_excluded(self, monkeypatch):
        tracker = InstitutionalFlowTracker("fake_key", as_of=AS_OF)

        monkeypatch.setattr(
            tracker,
            "get_company_screener",
            lambda **kw: [
                _make_screener_stock("GOOD"),
                _make_screener_stock("BAD"),
            ],
        )

        def mock_summary(symbol, year, quarter):
            if symbol == "GOOD":
                return _make_summary(investors=200, last_investors=190)
            # BAD: no comparable prior quarter -> Grade C
            return _make_summary(investors=300, last_investors=0)

        monkeypatch.setattr(tracker, "get_ownership_summary", mock_summary)
        monkeypatch.setattr(tracker, "get_top_holders", lambda *a, **k: _make_top_holders())

        results = tracker.screen_stocks(min_change_percent=0.1, min_institutions=1, limit=10)

        symbols = [r["symbol"] for r in results]
        assert "GOOD" in symbols
        assert "BAD" not in symbols


class TestETFFiltering:
    """ETFs and funds must be excluded before any ownership API calls."""

    def test_etf_excluded_from_screening(self, monkeypatch):
        tracker = InstitutionalFlowTracker("fake_key", as_of=AS_OF)

        monkeypatch.setattr(
            tracker,
            "get_company_screener",
            lambda **kw: [
                _make_screener_stock("AAPL", is_etf=False),
                _make_screener_stock("SPY", company_name="SPDR S&P 500", is_etf=True),
                _make_screener_stock("VFINX", company_name="Vanguard Fund", is_fund=True),
            ],
        )

        called_symbols = []

        def mock_summary(symbol, year, quarter):
            called_symbols.append(symbol)
            return _make_summary()

        monkeypatch.setattr(tracker, "get_ownership_summary", mock_summary)
        monkeypatch.setattr(tracker, "get_top_holders", lambda *a, **k: _make_top_holders())

        tracker.screen_stocks(min_change_percent=0.1, min_institutions=1, limit=10)

        assert "SPY" not in called_symbols
        assert "VFINX" not in called_symbols
        assert "AAPL" in called_symbols


class TestScreenerMissingFields:
    """Screener results with missing isEtf/isFund/isActivelyTrading should pass safely."""

    def test_missing_fields_defaults_to_tradable(self, monkeypatch):
        tracker = InstitutionalFlowTracker("fake_key", as_of=AS_OF)

        monkeypatch.setattr(
            tracker,
            "get_company_screener",
            lambda **kw: [
                {"symbol": "NEWCO", "companyName": "New Corp", "marketCap": 5_000_000_000},
            ],
        )
        monkeypatch.setattr(tracker, "get_ownership_summary", lambda *a, **k: _make_summary())
        monkeypatch.setattr(tracker, "get_top_holders", lambda *a, **k: _make_top_holders())

        results = tracker.screen_stocks(min_change_percent=0.1, min_institutions=1, limit=10)

        symbols = [r["symbol"] for r in results]
        assert "NEWCO" in symbols


class TestDeduplicationIntegration:
    """BRK-A/B must be deduplicated within the pipeline."""

    def test_brk_deduplicated_in_pipeline(self, monkeypatch):
        tracker = InstitutionalFlowTracker("fake_key", as_of=AS_OF)

        monkeypatch.setattr(
            tracker,
            "get_company_screener",
            lambda **kw: [
                _make_screener_stock("BRK-A", market_cap=800_000_000_000),
                _make_screener_stock("BRK-B", market_cap=800_000_000_000),
                _make_screener_stock("AAPL", market_cap=3_000_000_000_000),
            ],
        )
        monkeypatch.setattr(tracker, "get_ownership_summary", lambda *a, **k: _make_summary())
        monkeypatch.setattr(tracker, "get_top_holders", lambda *a, **k: _make_top_holders())

        results = tracker.screen_stocks(min_change_percent=0.1, min_institutions=1, limit=10)

        symbols = [r["symbol"] for r in results]
        brk_count = sum(1 for s in symbols if s.startswith("BRK"))
        assert brk_count == 1, f"Expected 1 BRK variant, got {brk_count}: {symbols}"
        assert "AAPL" in symbols


class TestOutputFieldsClean:
    """Output must carry the aggregate contract and no removed value_* fields."""

    def test_no_value_change_in_output(self, monkeypatch):
        tracker = InstitutionalFlowTracker("fake_key", as_of=AS_OF)

        monkeypatch.setattr(
            tracker, "get_company_screener", lambda **kw: [_make_screener_stock("AAPL")]
        )
        monkeypatch.setattr(tracker, "get_ownership_summary", lambda *a, **k: _make_summary())
        monkeypatch.setattr(tracker, "get_top_holders", lambda *a, **k: _make_top_holders())

        results = tracker.screen_stocks(min_change_percent=0.1, min_institutions=1, limit=10)

        assert len(results) >= 1
        for r in results:
            assert "value_change" not in r
            assert "current_value" not in r
            assert "previous_value" not in r
            assert "genuine_ratio" not in r  # retired with the per-holder grading

    def test_required_fields_present(self, monkeypatch):
        tracker = InstitutionalFlowTracker("fake_key", as_of=AS_OF)

        monkeypatch.setattr(
            tracker, "get_company_screener", lambda **kw: [_make_screener_stock("MSFT")]
        )
        monkeypatch.setattr(tracker, "get_ownership_summary", lambda *a, **k: _make_summary())
        monkeypatch.setattr(tracker, "get_top_holders", lambda *a, **k: _make_top_holders())

        results = tracker.screen_stocks(min_change_percent=0.1, min_institutions=1, limit=10)

        assert len(results) >= 1
        required_fields = [
            "symbol",
            "company_name",
            "market_cap",
            "current_quarter",
            "percent_change",
            "current_institution_count",
            "institution_count_change",
            "buyers",
            "sellers",
            "new_positions",
            "closed_positions",
            "ownership_percent",
            "reliability_grade",
            "top_holders",
        ]
        for r in results:
            for field in required_fields:
                assert field in r, f"Missing required field: {field}"


class TestScreeningReport:
    """generate_report() must produce valid markdown with expected sections."""

    def _make_mock_results(self):
        """Create mock screening results matching the aggregate contract."""
        return [
            {
                "symbol": "AAPL",
                "company_name": "Apple Inc.",
                "market_cap": 3_000_000_000_000,
                "current_quarter": "2026-03-31",
                "previous_quarter": "2025-12-31",
                "current_total_shares": 5_000_000,
                "previous_total_shares": 4_500_000,
                "shares_change": 500_000,
                "percent_change": 11.11,
                "current_institution_count": 200,
                "previous_institution_count": 190,
                "institution_count_change": 10,
                "buyers": 120,
                "sellers": 50,
                "unchanged": 10,
                "new_positions": 20,
                "closed_positions": 10,
                "ownership_percent": 65.0,
                "ownership_percent_change": 1.2,
                "top_holders": [
                    {"name": "Vanguard", "shares": 1_000_000, "change": 50_000},
                    {"name": "BlackRock", "shares": 900_000, "change": 30_000},
                ],
                "reliability_grade": "A",
            },
            {
                "symbol": "TSLA",
                "company_name": "Tesla Inc.",
                "market_cap": 800_000_000_000,
                "current_quarter": "2026-03-31",
                "previous_quarter": "2025-12-31",
                "current_total_shares": 2_000_000,
                "previous_total_shares": 2_200_000,
                "shares_change": -200_000,
                "percent_change": -9.09,
                "current_institution_count": 30,
                "previous_institution_count": 35,
                "institution_count_change": -5,
                "buyers": 8,
                "sellers": 18,
                "unchanged": 4,
                "new_positions": 2,
                "closed_positions": 6,
                "ownership_percent": 45.0,
                "ownership_percent_change": -2.0,
                "top_holders": [
                    {"name": "ARK Invest", "shares": 500_000, "change": -100_000},
                ],
                "reliability_grade": "B",
            },
        ]

    def test_report_contains_grade_a_or_b(self, tmp_path):
        tracker = InstitutionalFlowTracker("fake_key", as_of=AS_OF)
        report = tracker.generate_report(self._make_mock_results(), output_dir=str(tmp_path))
        assert "Grade A" in report or "Grade B" in report

    def test_report_detailed_results_exclude_grade_c(self, tmp_path):
        """Detailed Results section should only contain Grade A/B stocks."""
        tracker = InstitutionalFlowTracker("fake_key", as_of=AS_OF)
        report = tracker.generate_report(self._make_mock_results(), output_dir=str(tmp_path))
        detailed = report.split("## Detailed Results")[1].split("## Methodology")[0]
        assert "Grade C" not in detailed

    def test_report_mentions_ownership(self, tmp_path):
        tracker = InstitutionalFlowTracker("fake_key", as_of=AS_OF)
        report = tracker.generate_report(self._make_mock_results(), output_dir=str(tmp_path))
        assert "ownership" in report.lower()
