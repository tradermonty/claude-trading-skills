"""Tests for analyze_single_stock.py.

Verifies:
1. No references to nonexistent 'totalShares' field in source code
2. All-holder comparison (not limited to top 20)
3. Data quality information is included in analysis output
4. classify_holder-based change analysis works correctly
"""

import inspect
import re
import pytest

from analyze_single_stock import SingleStockAnalyzer


class TestSourceCodeContract:
    """Verify source code does not reference nonexistent FMP fields."""

    def test_no_totalShares_reference(self):
        """analyze_single_stock.py must not reference 'totalShares'."""
        source = inspect.getsource(SingleStockAnalyzer)
        # Allow references in comments/docstrings about the migration
        # but not in actual field access patterns like .get('totalShares')
        field_access = re.findall(r"\.get\(['\"]totalShares['\"]", source)
        assert len(field_access) == 0, (
            f"Found {len(field_access)} references to .get('totalShares') "
            f"in SingleStockAnalyzer. Use 'shares' instead."
        )

    def test_no_totalInvested_reference(self):
        """analyze_single_stock.py must not reference 'totalInvested'."""
        source = inspect.getsource(SingleStockAnalyzer)
        field_access = re.findall(r"\.get\(['\"]totalInvested['\"]", source)
        assert len(field_access) == 0, (
            f"Found {len(field_access)} references to .get('totalInvested') "
            f"in SingleStockAnalyzer. This field does not exist in FMP v3."
        )


class TestAnalyzeStockOutput:
    """Test analyze_stock output structure with mock data."""

    @pytest.fixture
    def mock_analyzer(self, monkeypatch):
        analyzer = SingleStockAnalyzer("fake_key")

        def mock_profile(symbol):
            return {
                "companyName": "Test Corp",
                "sector": "Technology",
                "mktCap": 1_000_000_000,
            }

        def mock_holders(symbol):
            holders = []
            # Q4 2025: 100 genuine holders + 10 new_full + 5 exited
            for i in range(100):
                holders.append({
                    "holder": f"Fund{i}",
                    "shares": 10_000 + i * 100,
                    "change": 500 if i % 2 == 0 else -200,
                    "dateReported": "2025-12-31",
                })
            for i in range(10):
                holders.append({
                    "holder": f"NewFund{i}",
                    "shares": 5_000,
                    "change": 5_000,
                    "dateReported": "2025-12-31",
                })
            for i in range(5):
                holders.append({
                    "holder": f"ExitFund{i}",
                    "shares": 0,
                    "change": -3_000,
                    "dateReported": "2025-12-31",
                })
            # Q3 2025: 95 holders (subset)
            for i in range(95):
                holders.append({
                    "holder": f"Fund{i}",
                    "shares": 9_500 + i * 100,
                    "change": 300,
                    "dateReported": "2025-09-30",
                })
            return holders

        monkeypatch.setattr(analyzer, "get_company_profile", mock_profile)
        monkeypatch.setattr(analyzer, "get_institutional_holders", mock_holders)
        return analyzer

    def test_analysis_returns_data_quality(self, mock_analyzer):
        """Analysis output must include data_quality section."""
        result = mock_analyzer.analyze_stock("TEST", quarters=4)
        assert "data_quality" in result
        dq = result["data_quality"]
        assert "grade" in dq
        assert "genuine_ratio" in dq
        assert dq["grade"] in ("A", "B", "C")

    def test_analysis_uses_all_holders_for_comparison(self, mock_analyzer):
        """Position changes must consider all holders, not just top 20."""
        result = mock_analyzer.analyze_stock("TEST", quarters=4)
        # We have 100 genuine holders in current quarter, all should be considered
        total_changes = (
            len(result.get("increased_positions", []))
            + len(result.get("decreased_positions", []))
            + len(result.get("new_positions", []))
        )
        # Must be more than 20 (old code limited to top 20)
        assert total_changes > 20

    def test_increased_positions_from_genuine(self, mock_analyzer):
        """increased_positions should come from genuine holders with positive change."""
        result = mock_analyzer.analyze_stock("TEST", quarters=4)
        for pos in result.get("increased_positions", []):
            assert pos["change"] > 0

    def test_decreased_positions_from_genuine(self, mock_analyzer):
        """decreased_positions should come from genuine holders with negative change."""
        result = mock_analyzer.analyze_stock("TEST", quarters=4)
        for pos in result.get("decreased_positions", []):
            assert pos["change"] < 0

    def test_new_positions_are_new_full(self, mock_analyzer):
        """new_positions should be holders classified as new_full."""
        result = mock_analyzer.analyze_stock("TEST", quarters=4)
        assert len(result.get("new_positions", [])) == 10

    def test_no_closed_positions_key(self, mock_analyzer):
        """closed_positions should not be present (unreliable with asymmetric data)."""
        result = mock_analyzer.analyze_stock("TEST", quarters=4)
        assert "closed_positions" not in result

    def test_shares_trend_with_low_genuine_ratio(self, monkeypatch):
        """shares_trend should be None when genuine_ratio < 0.7."""
        analyzer = SingleStockAnalyzer("fake_key")

        def mock_profile(symbol):
            return {
                "companyName": "Bad Data Corp",
                "sector": "Unknown",
                "mktCap": 500_000_000,
            }

        def mock_holders(symbol):
            holders = []
            # Q4: mostly new_full (low genuine ratio)
            for i in range(10):
                holders.append({
                    "holder": f"Fund{i}",
                    "shares": 10_000,
                    "change": 500,
                    "dateReported": "2025-12-31",
                })
            for i in range(90):
                holders.append({
                    "holder": f"NewFund{i}",
                    "shares": 1_000,
                    "change": 1_000,
                    "dateReported": "2025-12-31",
                })
            # Q3: minimal data
            for i in range(5):
                holders.append({
                    "holder": f"Fund{i}",
                    "shares": 9_500,
                    "change": 200,
                    "dateReported": "2025-09-30",
                })
            return holders

        monkeypatch.setattr(analyzer, "get_company_profile", mock_profile)
        monkeypatch.setattr(analyzer, "get_institutional_holders", mock_holders)

        result = analyzer.analyze_stock("BADDATA", quarters=4)
        assert result.get("shares_trend") is None


class TestSingleStockReport:
    """generate_report() must produce valid markdown with methodology and warnings."""

    def _make_mock_analysis(self, grade="A"):
        """Create mock analysis result for report generation."""
        return {
            "symbol": "TEST",
            "company_name": "Test Corp",
            "sector": "Technology",
            "market_cap": 1_000_000_000,
            "quarterly_metrics": [
                {
                    "quarter": "2025-12-31",
                    "total_shares": 5_000_000,
                    "num_holders": 100,
                    "top_holders": [
                        {"holder": f"Fund{i}", "shares": 100_000 - i * 1000, "change": 5_000}
                        for i in range(20)
                    ],
                },
                {
                    "quarter": "2025-09-30",
                    "total_shares": 4_800_000,
                    "num_holders": 95,
                    "top_holders": [],
                },
            ],
            "shares_trend": 4.17,
            "holders_trend": 5,
            "new_positions": [{"name": "NewFund1", "shares": 10_000}],
            "increased_positions": [
                {"name": "Fund0", "current_shares": 100_000, "change": 5_000, "pct_change": 5.26}
            ],
            "decreased_positions": [
                {"name": "Fund50", "current_shares": 50_000, "change": -2_000, "pct_change": -3.85}
            ],
            "data_quality": {
                "grade": grade,
                "genuine_ratio": 0.85 if grade == "A" else 0.45,
                "coverage_ratio": 1.05,
                "match_ratio": 0.90,
                "genuine_count": 85 if grade == "A" else 45,
                "total_holders": 100,
            },
        }

    def test_report_contains_correct_methodology(self, tmp_path):
        analyzer = SingleStockAnalyzer("fake_key")
        analysis = self._make_mock_analysis(grade="A")
        report = analyzer.generate_report(analysis, output_dir=str(tmp_path))

        assert "change != shares" in report

    def test_grade_b_report_contains_caution(self, tmp_path):
        analyzer = SingleStockAnalyzer("fake_key")
        analysis = self._make_mock_analysis(grade="B")
        report = analyzer.generate_report(analysis, output_dir=str(tmp_path))

        assert "CAUTION: Reference Only" in report
