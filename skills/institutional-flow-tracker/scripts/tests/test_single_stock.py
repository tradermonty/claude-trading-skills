"""Tests for analyze_single_stock.py (/stable aggregate).

Verifies:
1. Source code no longer references the retired /api/v3 institutional-holder feed
2. Multi-quarter trend is built from the aggregate summary
3. Reliability (coverage) grade is included in analysis output
4. New / increased / decreased lists are derived from the named top holders
"""

import datetime
import inspect

from analyze_single_stock import SingleStockAnalyzer
from data_quality import quarter_end_date

AS_OF = datetime.date(2026, 3, 31)

# Four quarters of accumulation, most recent first.
SHARES = {
    (2026, 1): 6_000_000,
    (2025, 4): 5_500_000,
    (2025, 3): 5_000_000,
    (2025, 2): 4_500_000,
}
HOLDERS = {
    (2026, 1): 220,
    (2025, 4): 215,
    (2025, 3): 205,
    (2025, 2): 200,
}


def _make_summary(year, quarter):
    shares = SHARES[(year, quarter)]
    holders = HOLDERS[(year, quarter)]
    return {
        "date": quarter_end_date(year, quarter),
        "investorsHolding": holders,
        "lastInvestorsHolding": holders - 10,
        "investorsHoldingChange": 10,
        "numberOf13Fshares": shares,
        "lastNumberOf13Fshares": shares - 200_000,
        "numberOf13FsharesChange": 200_000,
        "increasedPositions": 120,
        "reducedPositions": 50,
        "newPositions": 20,
        "closedPositions": 10,
        "ownershipPercent": 65.0,
        "ownershipPercentChange": 1.5,
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
            "change": -30_000,
            "is_new": False,
            "is_sold_out": False,
        },
        {
            "name": "NewFund",
            "shares": 200_000,
            "change": 200_000,
            "is_new": True,
            "is_sold_out": False,
        },
        {"name": "FlatFund", "shares": 100_000, "change": 0, "is_new": False, "is_sold_out": False},
    ]


class TestSourceCodeContract:
    """Source must not reference the retired /api/v3 institutional-holder feed."""

    def test_no_v3_api_path(self):
        source = inspect.getsource(SingleStockAnalyzer)
        assert "/api/v3" not in source
        assert "institutional-holder/" not in source


class TestAnalyzeStockOutput:
    """analyze_stock output structure with mocked /stable responses."""

    def _analyzer(self, monkeypatch, top_holders=None):
        analyzer = SingleStockAnalyzer("fake_key", as_of=AS_OF)

        monkeypatch.setattr(
            analyzer,
            "get_company_profile",
            lambda symbol: {
                "companyName": "Test Corp",
                "sector": "Technology",
                "marketCap": 1_000_000_000,
            },
        )

        def mock_summary(symbol, year, quarter):
            key = (year, quarter)
            return _make_summary(year, quarter) if key in SHARES else None

        monkeypatch.setattr(analyzer, "get_ownership_summary", mock_summary)
        monkeypatch.setattr(
            analyzer,
            "get_top_holders",
            lambda *a, **k: top_holders if top_holders is not None else _make_top_holders(),
        )
        return analyzer

    def test_analysis_returns_coverage_grade(self, monkeypatch):
        result = self._analyzer(monkeypatch).analyze_stock("TEST", quarters=4)
        dq = result["data_quality"]
        assert dq["grade"] in ("A", "B", "C")
        assert dq["institution_count"] == 220
        assert dq["ownership_percent"] == 65.0
        assert dq["prior_quarter_available"] is True

    def test_quarterly_metrics_count(self, monkeypatch):
        result = self._analyzer(monkeypatch).analyze_stock("TEST", quarters=4)
        assert len(result["quarterly_metrics"]) == 4
        # Most recent quarter carries the named top holders; older ones do not.
        assert result["quarterly_metrics"][0]["top_holders"]
        assert result["quarterly_metrics"][-1]["top_holders"] == []

    def test_shares_trend_accumulation(self, monkeypatch):
        result = self._analyzer(monkeypatch).analyze_stock("TEST", quarters=4)
        # (6.0M - 4.5M) / 4.5M * 100 == +33.33%
        assert result["shares_trend"] > 30
        assert result["holders_trend"] == 20  # 220 - 200

    def test_new_positions_from_top_holders(self, monkeypatch):
        result = self._analyzer(monkeypatch).analyze_stock("TEST", quarters=4)
        names = [p["name"] for p in result["new_positions"]]
        assert names == ["NewFund"]

    def test_increased_positions_positive_change(self, monkeypatch):
        result = self._analyzer(monkeypatch).analyze_stock("TEST", quarters=4)
        assert [p["name"] for p in result["increased_positions"]] == ["Vanguard"]
        for pos in result["increased_positions"]:
            assert pos["change"] > 0

    def test_decreased_positions_negative_change(self, monkeypatch):
        result = self._analyzer(monkeypatch).analyze_stock("TEST", quarters=4)
        assert [p["name"] for p in result["decreased_positions"]] == ["BlackRock"]
        for pos in result["decreased_positions"]:
            assert pos["change"] < 0

    def test_insufficient_data_returns_empty(self, monkeypatch):
        analyzer = SingleStockAnalyzer("fake_key", as_of=AS_OF)
        monkeypatch.setattr(
            analyzer, "get_company_profile", lambda s: {"companyName": "X", "sector": "Y"}
        )

        # Only the latest quarter has data -> fewer than 2 quarters -> {}
        def one_quarter(symbol, year, quarter):
            return _make_summary(2026, 1) if (year, quarter) == (2026, 1) else None

        monkeypatch.setattr(analyzer, "get_ownership_summary", one_quarter)
        monkeypatch.setattr(analyzer, "get_top_holders", lambda *a, **k: _make_top_holders())
        assert analyzer.analyze_stock("TEST", quarters=4) == {}


class TestSingleStockReport:
    """generate_report() must produce valid markdown with methodology and warnings."""

    def _make_mock_analysis(self, grade="A"):
        return {
            "symbol": "TEST",
            "company_name": "Test Corp",
            "sector": "Technology",
            "market_cap": 1_000_000_000,
            "quarterly_metrics": [
                {
                    "quarter": "2026-03-31",
                    "total_shares": 5_000_000,
                    "num_holders": 220,
                    "top_holders": [
                        {"name": f"Fund{i}", "shares": 100_000 - i * 1000, "change": 5_000}
                        for i in range(20)
                    ],
                },
                {
                    "quarter": "2025-12-31",
                    "total_shares": 4_800_000,
                    "num_holders": 210,
                    "top_holders": [],
                },
            ],
            "shares_trend": 4.17,
            "holders_trend": 10,
            "new_positions": [{"name": "NewFund1", "shares": 10_000}],
            "increased_positions": [
                {"name": "Fund0", "current_shares": 100_000, "change": 5_000, "pct_change": 5.26}
            ],
            "decreased_positions": [
                {"name": "Fund50", "current_shares": 50_000, "change": -2_000, "pct_change": -3.85}
            ],
            "data_quality": {
                "grade": grade,
                "institution_count": 220 if grade == "A" else 30,
                "ownership_percent": 65.0,
                "ownership_percent_change": 1.5,
                "prior_quarter_available": True,
                "increased": 120,
                "reduced": 50,
                "new": 20,
                "closed": 10,
            },
        }

    def test_report_contains_methodology(self, tmp_path):
        analyzer = SingleStockAnalyzer("fake_key", as_of=AS_OF)
        report = analyzer.generate_report(self._make_mock_analysis("A"), output_dir=str(tmp_path))
        assert "symbol-positions-summary" in report

    def test_grade_b_report_contains_caution(self, tmp_path):
        analyzer = SingleStockAnalyzer("fake_key", as_of=AS_OF)
        report = analyzer.generate_report(self._make_mock_analysis("B"), output_dir=str(tmp_path))
        assert "CAUTION: Reference Only" in report

    def test_grade_c_report_contains_warning(self, tmp_path):
        analyzer = SingleStockAnalyzer("fake_key", as_of=AS_OF)
        report = analyzer.generate_report(self._make_mock_analysis("C"), output_dir=str(tmp_path))
        assert "INSUFFICIENT COVERAGE" in report
