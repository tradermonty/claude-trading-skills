"""Offline dividend-coverage regressions for Issue #509."""

import json
import math

import pytest
import screen_dividend_stocks as module


def analyze(*, fcf=40, dividends=-20, net_income=100, is_reit=False, **cashflow):
    cash_flow = {
        "dividendsPaid": dividends,
        "operatingCashFlow": fcf,
        "capitalExpenditure": 0,
        "netIncome": net_income,
        "depreciationAndAmortization": 50,
    }
    cash_flow.update(cashflow)
    return module.StockAnalyzer.analyze_dividend_sustainability(
        [{"netIncome": net_income}], [cash_flow], is_reit=is_reit
    )


@pytest.mark.parametrize(
    ("fcf", "coverage", "sustainable", "note_fragment"),
    [
        (40, "COVERED", True, "covers dividends"),
        (20, "AT_LIMIT", False, "no coverage buffer"),
        (10, "INSUFFICIENT_FCF", False, "below dividends"),
        (0, "ZERO_FCF", False, "zero free cash flow"),
        (-20, "NEGATIVE_FCF", False, "negative free cash flow"),
    ],
)
def test_non_reit_fcf_coverage(fcf, coverage, sustainable, note_fragment):
    result = analyze(fcf=fcf)
    assert result["fcf_amount"] == fcf
    assert result["fcf_status"] == ("POSITIVE" if fcf > 0 else "NEGATIVE" if fcf < 0 else "ZERO")
    assert result["fcf_coverage_status"] == coverage
    assert result["sustainable"] is sustainable
    assert result["sustainability_basis"] == "EARNINGS_AND_FCF"
    assert note_fragment in result["sustainability_note"]
    if fcf < 20:
        assert "future cut is not certain" in result["sustainability_note"]
    json.dumps(result, allow_nan=False)


def test_exact_negative_fcf_reproduction():
    result = module.StockAnalyzer.analyze_dividend_sustainability(
        [{"netIncome": 100}],
        [{"dividendsPaid": -20, "operatingCashFlow": 10, "capitalExpenditure": -30}],
    )
    assert result["payout_ratio"] == 20
    assert result["fcf_amount"] == -20
    assert result["fcf_payout_ratio"] is None
    assert result["fcf_status"] == "NEGATIVE"
    assert result["sustainable"] is False


@pytest.mark.parametrize("missing_field", ["operatingCashFlow", "capitalExpenditure"])
def test_missing_fcf_field_stays_missing(missing_field):
    cash_flow = {"dividendsPaid": -20, "operatingCashFlow": 40, "capitalExpenditure": -10}
    del cash_flow[missing_field]
    result = module.StockAnalyzer.analyze_dividend_sustainability([{"netIncome": 100}], [cash_flow])
    assert result["fcf_amount"] is None
    assert result["fcf_status"] == "MISSING_DATA"
    assert result["fcf_coverage_status"] == "MISSING_DATA"
    assert result["sustainable"] is False
    assert "cannot be calculated" in result["sustainability_note"]


@pytest.mark.parametrize("dividends", [None, math.nan, math.inf, "20"])
@pytest.mark.parametrize("is_reit", [False, True])
def test_invalid_dividend_payment_is_missing_but_observed_fcf_survives(dividends, is_reit):
    result = analyze(fcf=40, dividends=dividends, is_reit=is_reit)
    assert result["fcf_amount"] == 40
    assert result["fcf_status"] == "POSITIVE"
    assert result["fcf_coverage_status"] == "MISSING_DATA"
    assert result["sustainable"] is False
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("is_reit", [False, True])
def test_missing_dividend_key_is_not_zero(is_reit):
    result = module.StockAnalyzer.analyze_dividend_sustainability(
        [{"netIncome": 100}],
        [
            {
                "operatingCashFlow": 40,
                "capitalExpenditure": 0,
                "netIncome": 100,
                "depreciationAndAmortization": 50,
            }
        ],
        is_reit=is_reit,
    )
    assert result["fcf_status"] == "POSITIVE"
    assert result["fcf_coverage_status"] == "MISSING_DATA"
    assert result["sustainable"] is False


@pytest.mark.parametrize("is_reit", [False, True])
def test_no_dividend_keeps_negative_fcf_observation(is_reit):
    result = analyze(fcf=-20, dividends=0, is_reit=is_reit)
    assert result["fcf_amount"] == -20
    assert result["fcf_status"] == "NEGATIVE"
    assert result["fcf_coverage_status"] == "NO_DIVIDEND"
    assert result["sustainable"] is False


@pytest.mark.parametrize(
    ("cashflow", "income", "expected"),
    [
        ({"operatingCashFlow": None}, 100, "MISSING_DATA"),
        ({"capitalExpenditure": math.inf}, 100, "MISSING_DATA"),
        ({"operatingCashFlow": 1e308, "capitalExpenditure": -1e308}, 100, "ZERO"),
        ({"operatingCashFlow": -1e308, "capitalExpenditure": -1e308}, 100, "MISSING_DATA"),
    ],
)
def test_invalid_and_derived_fcf_stay_json_finite(cashflow, income, expected):
    result = analyze(net_income=income, **cashflow)
    assert result["fcf_status"] == expected
    assert result["sustainable"] is False
    json.dumps(result, allow_nan=False)


def test_nonfinite_payout_ratio_never_supports_bonus():
    result = analyze(fcf=1e308, dividends=-1e308, net_income=1e-300)
    assert result["payout_ratio"] is None
    assert result["sustainable"] is False
    json.dumps(result, allow_nan=False)


def test_tiny_fcf_with_nonfinite_fcf_ratio_cannot_gain_bonus():
    result = analyze(fcf=1e-300, dividends=-1e308)
    assert result["fcf_status"] == "POSITIVE"
    assert result["fcf_coverage_status"] == "INSUFFICIENT_FCF"
    assert result["fcf_payout_ratio"] is None
    assert result["sustainable"] is False
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("income", [[], [{}], [{"netIncome": None}], [{"netIncome": math.inf}]])
def test_missing_or_invalid_earnings_never_support_non_reit_bonus(income):
    result = module.StockAnalyzer.analyze_dividend_sustainability(
        income,
        [{"dividendsPaid": -20, "operatingCashFlow": 50, "capitalExpenditure": 0}],
    )
    assert result["fcf_coverage_status"] == "COVERED"
    assert result["payout_ratio"] is None
    assert result["sustainable"] is False


def test_reit_uses_ffo_even_when_fcf_is_negative():
    result = analyze(fcf=-20, is_reit=True)
    assert result["fcf_status"] == "NEGATIVE"
    assert result["fcf_coverage_status"] == "NEGATIVE_FCF"
    assert result["payout_ratio"] == pytest.approx(20 / 150 * 100)
    assert result["sustainable"] is True
    assert result["sustainability_basis"] == "FFO"
    assert "FFO" in result["sustainability_note"]


@pytest.mark.parametrize("field", ["netIncome", "depreciationAndAmortization"])
def test_reit_missing_ffo_component_cannot_be_sustainable(field):
    cash_flow = {
        "dividendsPaid": -20,
        "operatingCashFlow": 40,
        "capitalExpenditure": -10,
        "netIncome": 100,
        "depreciationAndAmortization": 50,
    }
    del cash_flow[field]
    result = module.StockAnalyzer.analyze_dividend_sustainability([], [cash_flow], is_reit=True)
    assert result["payout_ratio"] is None
    assert result["sustainable"] is False


def test_reit_low_ffo_cannot_be_sustainable():
    result = analyze(fcf=40, net_income=-40, is_reit=True)
    assert result["payout_ratio"] == 200
    assert result["sustainable"] is False


def test_reit_ffo_threshold_uses_unrounded_ratio():
    result = analyze(
        fcf=-20,
        dividends=-1999,
        net_income=2000,
        is_reit=True,
        depreciationAndAmortization=500,
    )
    assert result["payout_ratio"] == pytest.approx(79.96)
    assert result["sustainable"] is True


def test_reit_classification_requires_explicit_reit_evidence():
    assert (
        module.StockAnalyzer.is_reit({"sector": "Real Estate", "industry": "Real Estate Services"})
        is False
    )
    assert module.StockAnalyzer.is_reit({"industry": "REIT - Residential"}) is True
    assert module.StockAnalyzer.is_reit({"industry": "REITs - Residential"}) is True
    assert module.StockAnalyzer.is_reit({"industry": "Real Estate Investment Trust"}) is True
    assert module.StockAnalyzer.is_reit({"industry": "Real Estate Investment Trusts"}) is True
    assert (
        module.StockAnalyzer.is_reit({"isReit": True, "industry": "Real Estate Services"}) is True
    )
    assert module.StockAnalyzer.is_reit({"isReit": False, "industry": "Non-REIT Property"}) is False
    assert module.StockAnalyzer.is_reit({"industry": "Non-REITs Property"}) is False


def test_screen_ranking_bonus_only_for_supported_coverage(monkeypatch):
    class FakeClient:
        rate_limit_reached = False

        def __init__(self, _key):
            pass

        def screen_stocks(self, **_kwargs):
            return [
                {
                    "symbol": "SHORT",
                    "name": "Fictional Shortfall",
                    "sector": "Industrials",
                    "price": 50,
                },
                {
                    "symbol": "COVER",
                    "name": "Fictional Coverage",
                    "sector": "Industrials",
                    "price": 50,
                },
            ]

        def get_income_statement(self, _symbol, **_kwargs):
            return [{"netIncome": 100} for _ in range(4)]

        def get_balance_sheet(self, _symbol, **_kwargs):
            return [{}]

        def get_cash_flow(self, symbol, **_kwargs):
            return [
                {
                    "dividendsPaid": -20,
                    "operatingCashFlow": 10 if symbol == "SHORT" else 60,
                    "capitalExpenditure": -30,
                }
            ]

        def get_key_metrics(self, _symbol, **_kwargs):
            return [{}]

        def get_dividend_history(self, _symbol):
            return {"historical": []}

        def get_historical_prices(self, _symbol, **_kwargs):
            return [{"close": 100} for _ in range(30)]

    monkeypatch.setattr(module, "FMPClient", FakeClient)
    monkeypatch.setattr(module.RSICalculator, "calculate_rsi", staticmethod(lambda *_a, **_k: 30.0))
    monkeypatch.setattr(
        module.StockAnalyzer,
        "analyze_dividend_growth",
        staticmethod(lambda *_a, **_k: (6.0, True, 2.0)),
    )
    monkeypatch.setattr(
        module.StockAnalyzer, "analyze_revenue_growth", staticmethod(lambda *_a, **_k: (True, 10.0))
    )
    monkeypatch.setattr(
        module.StockAnalyzer, "analyze_eps_growth", staticmethod(lambda *_a, **_k: (True, 10.0))
    )
    monkeypatch.setattr(
        module.StockAnalyzer,
        "analyze_dividend_stability",
        staticmethod(
            lambda *_a, **_k: {
                "is_stable": True,
                "is_growing": True,
                "years_of_growth": 3,
                "volatility_pct": 5.0,
            }
        ),
    )
    monkeypatch.setattr(
        module.StockAnalyzer,
        "analyze_revenue_trend",
        staticmethod(lambda *_a, **_k: {"is_uptrend": True, "years_of_growth": 3, "cagr": 10}),
    )
    monkeypatch.setattr(
        module.StockAnalyzer,
        "analyze_earnings_trend",
        staticmethod(lambda *_a, **_k: {"is_uptrend": True, "years_of_growth": 3, "cagr": 10}),
    )
    monkeypatch.setattr(
        module.StockAnalyzer,
        "calculate_quality_score",
        staticmethod(lambda *_a, **_k: {"quality_score": 0, "profit_margin": None}),
    )

    results = module.screen_value_dividend_stocks("fictional-key", top_n=2)
    assert [row["symbol"] for row in results] == ["COVER", "SHORT"]
    covered, shortfall = results
    assert covered["sustainability_bonus"] == 10
    assert covered["dividend_sustainable"] is True
    assert shortfall["sustainability_bonus"] == 0
    assert shortfall["dividend_sustainable"] is False
    assert shortfall["fcf_amount"] == -20
    assert shortfall["fcf_coverage_status"] == "NEGATIVE_FCF"
    assert covered["composite_score"] - shortfall["composite_score"] == 10
    json.dumps(results, allow_nan=False)
