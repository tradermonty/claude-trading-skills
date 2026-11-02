"""Tests for dividend-growth-pullback-screener screening logic.

These tests validate the core calculation functions without requiring
live API keys (FMP or FINVIZ). All external I/O is stubbed.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
import screen_dividend_growth_rsi as subject

SCRIPT_PATH = Path(subject.__file__)


def _load_script():
    return subject


@pytest.mark.parametrize(
    "prices,expected",
    [
        ([100.0 + i for i in range(30)], 100.0),
        ([100.0 - i for i in range(30)], 0.0),
        ([100.0] * 30, 100.0),  # Existing zero-loss convention, including flat series.
        ([100.0 + i for i in range(15)], 100.0),
        ([100.0] * 14, None),
        ([], None),
    ],
)
def test_rsi_public_boundaries(prices, expected):
    assert subject.RSICalculator.calculate_rsi(prices) == expected


def test_rsi_wilder_smoothing():
    # period=3: initial gains=2/3, losses=1/3; next gain=2 gives
    # smoothed gains=10/9 and losses=2/9 -> RSI=83.33.
    assert subject.RSICalculator.calculate_rsi([10, 11, 10, 11, 13], period=3) == 83.33


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -float("inf"), True])
def test_rsi_invalid_prices_rejected(bad):
    assert subject.RSICalculator.calculate_rsi([100.0] * 14 + [bad]) is None


@pytest.mark.parametrize("period", [0, -1, True, 1.5])
def test_rsi_invalid_period_rejected(period):
    assert subject.RSICalculator.calculate_rsi([100.0] * 30, period=period) is None


@pytest.mark.parametrize(
    "start,end,years,expected",
    [
        (1.0, 2.0, 6, 12.25),
        (2.0, 1.0, 1, -50.0),
        (1.0, 1.0, 3, 0.0),
        (0, 2, 3, None),
        (-1, 2, 3, None),
        (1, 0, 3, None),
        (1, -2, 3, None),
        (1, 2, 0, None),
        (1, 2, -1, None),
    ],
)
def test_cagr_public_boundaries(start, end, years, expected):
    assert subject.StockAnalyzer.calculate_cagr(start, end, years) == expected


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -float("inf"), True])
@pytest.mark.parametrize("operand", [0, 1, 2])
def test_cagr_invalid_operands_rejected(bad, operand):
    args = [1.0, 2.0, 6]
    args[operand] = bad
    assert subject.StockAnalyzer.calculate_cagr(*args) is None


# ---------------------------------------------------------------------------
# Script structure / CLI smoke tests
# ---------------------------------------------------------------------------


class TestScriptStructure:
    """Ensure the script file meets structural requirements."""

    def test_script_exists(self):
        assert SCRIPT_PATH.exists(), f"Main script missing: {SCRIPT_PATH}"

    def test_script_has_main_guard(self):
        source = SCRIPT_PATH.read_text(encoding="utf-8")
        assert 'if __name__ == "__main__"' in source or "if __name__ == '__main__'" in source, (
            "Script should have a __main__ guard"
        )

    def test_script_references_fmp_api(self):
        source = SCRIPT_PATH.read_text(encoding="utf-8")
        assert "FMP_API_KEY" in source or "fmp_api_key" in source or "fmp-api-key" in source, (
            "Script should reference FMP_API_KEY"
        )

    def test_script_references_rsi(self):
        source = SCRIPT_PATH.read_text(encoding="utf-8")
        assert "rsi" in source.lower(), "Script should implement or reference RSI"

    def test_output_dir_argument(self):
        """Script should accept --output-dir for report placement."""
        source = SCRIPT_PATH.read_text(encoding="utf-8")
        assert "output" in source.lower(), "Script should support an output directory argument"


def test_fmp_decimal_roe_and_margin_are_converted_to_percent(monkeypatch):
    """FMP decimal fundamentals must match percent-based scoring/report fields."""
    mod = _load_script()
    client = MagicMock()
    client.rate_limit_reached = False
    client.screen_stocks.return_value = [
        {"symbol": "TEST", "companyName": "Test Inc", "price": 100, "sector": "Tech"}
    ]
    client.get_dividend_history.return_value = [{}]
    client.get_historical_prices.return_value = [{"close": 100}] * 30
    client.get_income_statement.return_value = [{}]
    client.get_balance_sheet.return_value = [
        {
            "totalDebt": 10,
            "totalStockholdersEquity": 100,
            "totalCurrentAssets": 100,
            "totalCurrentLiabilities": 20,
        }
    ]
    client.get_cash_flow.return_value = [{}]
    client.get_key_metrics.return_value = [{"roe": 0.25, "netProfitMargin": 0.125}]

    analyzer = MagicMock()
    analyzer.analyze_dividend_growth.return_value = (15.0, True, 2.0, 5)
    analyzer.analyze_growth_metrics.return_value = {
        "revenue_cagr_3y": 1.0,
        "eps_cagr_3y": 1.0,
    }
    analyzer.analyze_financial_health.return_value = {"financially_healthy": True}
    analyzer.is_reit.return_value = False
    analyzer.calculate_payout_ratios.return_value = {
        "payout_ratio": 50.0,
        "fcf_payout_ratio": 60.0,
        "sustainable": True,
        "fcf_amount": 100.0,
        "fcf_status": "POSITIVE",
        "fcf_coverage_status": "COVERED",
        "sustainability_basis": "EARNINGS_AND_FCF",
        "sustainability_note": "Coverage confirmed.",
    }
    analyzer.calculate_composite_score.return_value = 80.0

    monkeypatch.setattr(mod, "FMPClient", MagicMock(return_value=client))
    monkeypatch.setattr(mod, "StockAnalyzer", MagicMock(return_value=analyzer))
    monkeypatch.setattr(
        mod,
        "RSICalculator",
        MagicMock(return_value=MagicMock(calculate_rsi=MagicMock(return_value=30.0))),
    )

    result = mod.screen_dividend_growth_pullbacks("test-key")[0]

    assert result["roe"] == 25.0
    assert result["profit_margin"] == 12.5


@pytest.mark.parametrize(
    "fcf,status,coverage,sustainable",
    [
        (100, "POSITIVE", "COVERED", True),
        (20, "POSITIVE", "AT_LIMIT", False),
        (10, "POSITIVE", "INSUFFICIENT_FCF", False),
        (0, "ZERO", "ZERO_FCF", False),
        (-20, "NEGATIVE", "NEGATIVE_FCF", False),
        (None, "MISSING_DATA", "MISSING_DATA", False),
        (float("nan"), "MISSING_DATA", "MISSING_DATA", False),
        (float("inf"), "MISSING_DATA", "MISSING_DATA", False),
        (True, "MISSING_DATA", "MISSING_DATA", False),
        ("100", "MISSING_DATA", "MISSING_DATA", False),
    ],
)
def test_cash_flow_coverage_states(fcf, status, coverage, sustainable):
    analyzer = _load_script().StockAnalyzer
    result = analyzer.calculate_payout_ratios(
        [{"netIncome": 100}], [{"freeCashFlow": fcf, "dividendsPaid": -20}]
    )
    assert result["fcf_status"] == status
    assert result["fcf_coverage_status"] == coverage
    assert result["sustainable"] is sustainable
    assert result["sustainability_note"]


@pytest.mark.parametrize(
    "profile,expected",
    [
        ({"sector": "Real Estate", "industry": "Real Estate Services"}, False),
        ({"industry": "Non-REIT Real Estate"}, False),
        ({"industry": None}, False),
        ({"industry": "REIT - Retail"}, True),
        ({"industry": "Real Estate Investment Trust"}, True),
        ({"isReit": True}, True),
        ({"isReit": "true"}, False),
    ],
)
def test_explicit_reit_identification(profile, expected):
    assert _load_script().StockAnalyzer.is_reit(profile) is expected


@pytest.mark.parametrize("dividends,expected", [(79.999, True), (80, False), (80.001, False)])
def test_unrounded_earnings_and_ffo_threshold(dividends, expected):
    analyzer = _load_script().StockAnalyzer
    cf = [
        {
            "netIncome": 50,
            "depreciationAndAmortization": 50,
            "dividendsPaid": -dividends,
            "freeCashFlow": 200,
        }
    ]
    assert analyzer.calculate_payout_ratios([{"netIncome": 100}], cf)["sustainable"] is expected
    assert analyzer.calculate_payout_ratios([], cf, is_reit=True)["sustainable"] is expected


@pytest.mark.parametrize(
    "cf",
    [
        {},
        {"netIncome": 100},
        {"depreciationAndAmortization": 100},
        {"netIncome": float("inf"), "depreciationAndAmortization": 20},
        {"netIncome": True, "depreciationAndAmortization": 20},
    ],
)
def test_incomplete_ffo_is_not_confirmed(cf):
    cf = dict(cf, dividendsPaid=-20, freeCashFlow=100)
    result = _load_script().StockAnalyzer.calculate_payout_ratios([], [cf], is_reit=True)
    assert result["sustainable"] is False
    assert result["payout_ratio"] is None


@pytest.mark.parametrize("dividends", [None, True, float("nan"), 0])
def test_missing_invalid_or_zero_dividends_are_not_confirmed(dividends):
    result = _load_script().StockAnalyzer.calculate_payout_ratios(
        [{"netIncome": 100}], [{"freeCashFlow": 100, "dividendsPaid": dividends}]
    )
    assert result["sustainable"] is False


@pytest.mark.parametrize("fallback", [None, True, float("nan"), float("inf"), -0.2, 0.2])
def test_metrics_fallback_cannot_confirm_missing_coverage(monkeypatch, tmp_path, fallback):
    mod = _load_script()
    client = MagicMock()
    client.rate_limit_reached = False
    client.screen_stocks.return_value = [
        {"symbol": "TEST", "companyName": "Test Inc", "price": 100, "sector": "Tech"}
    ]
    client.get_dividend_history.return_value = [{}]
    client.get_historical_prices.return_value = [{"close": 100}] * 30
    client.get_income_statement.return_value = [{}]
    client.get_balance_sheet.return_value = [
        {
            "totalDebt": 10,
            "totalStockholdersEquity": 100,
            "totalCurrentAssets": 100,
            "totalCurrentLiabilities": 20,
        }
    ]
    client.get_cash_flow.return_value = [{"dividendsPaid": -20}]
    client.get_key_metrics.return_value = [{"payoutRatio": fallback}]
    monkeypatch.setattr(mod, "FMPClient", MagicMock(return_value=client))
    monkeypatch.setattr(
        mod.StockAnalyzer, "analyze_dividend_growth", staticmethod(lambda _: (15.0, True, 2.0, 5))
    )
    monkeypatch.setattr(
        mod.StockAnalyzer,
        "analyze_growth_metrics",
        staticmethod(lambda *_: {"revenue_cagr_3y": 1.0, "eps_cagr_3y": 1.0}),
    )
    monkeypatch.setattr(
        mod,
        "RSICalculator",
        MagicMock(return_value=MagicMock(calculate_rsi=MagicMock(return_value=30.0))),
    )
    result = mod.screen_dividend_growth_pullbacks("test-key")[0]
    assert result["dividend_sustainable"] is False
    assert result["fcf_status"] == "MISSING_DATA"
    assert result["fcf_coverage_status"] == "MISSING_DATA"
    assert result["payout_ratio"] == (20.0 if fallback == 0.2 else None)
    report = tmp_path / "report.md"
    mod.generate_markdown_report(
        [result], {"dividend_yield_min": 1.5, "dividend_cagr_min": 12, "rsi_max": 40}, str(report)
    )
    assert result["sustainability_note"] in report.read_text()
    assert "Sustainability confirmed: No" in report.read_text()


def test_unrepresentable_integer_inputs_rejected():
    huge = 10**400
    assert subject.RSICalculator.calculate_rsi([huge] * 15) is None
    assert subject.StockAnalyzer.calculate_cagr(huge, huge, 1) is None
