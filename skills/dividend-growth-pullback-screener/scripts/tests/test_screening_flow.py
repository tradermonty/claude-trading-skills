"""Behavior tests for FINVIZ/FMP clients, the screening pipeline, report and CLI.

All HTTP is replaced with in-memory fakes; no network, no real API keys.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import time
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "screen_dividend_growth_rsi.py"


@pytest.fixture(scope="module")
def mod():
    spec = importlib.util.spec_from_file_location("screen_dg_flow", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["screen_dg_flow"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def no_sleep(mod, monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda *_a, **_k: None)


class FakeResponse:
    def __init__(self, status_code=200, payload=None, content=b""):
        self.status_code = status_code
        self._payload = payload
        self.content = content
        self.text = content.decode("utf-8")

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class FakeSession:
    """Session whose get() pops queued responses (or raises queued exceptions)."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.headers = {}

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params))
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


# ---------------------------------------------------------------------------
# FINVIZClient
# ---------------------------------------------------------------------------


class TestFinvizClient:
    def _client(self, mod, response):
        client = mod.FINVIZClient("fake-key")
        client.session = FakeSession([response])
        return client

    def test_parses_tickers_and_sends_auth(self, mod):
        csv_body = b"No.,Ticker,Company\n1,AAPL,Apple\n2, MSFT ,Microsoft\n3,,Blank\n"
        client = self._client(mod, FakeResponse(200, content=csv_body))
        assert client.screen_stocks() == {"AAPL", "MSFT"}
        url, params = client.session.calls[0]
        assert url == mod.FINVIZClient.BASE_URL
        assert params["auth"] == "fake-key"
        assert "ta_rsi_os40" in params["f"]

    @pytest.mark.parametrize("status", [401, 403])
    def test_auth_failure_returns_empty(self, mod, status, capsys):
        client = self._client(mod, FakeResponse(status))
        assert client.screen_stocks() == set()
        assert "authentication failed" in capsys.readouterr().err

    def test_other_status_returns_empty(self, mod, capsys):
        client = self._client(mod, FakeResponse(500))
        assert client.screen_stocks() == set()
        assert "request failed: 500" in capsys.readouterr().err

    def test_request_exception_returns_empty(self, mod, capsys):
        client = mod.FINVIZClient("k")
        client.session = FakeSession([mod.requests.exceptions.ConnectionError("boom")])
        assert client.screen_stocks() == set()
        assert "boom" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# FMPClient request / retry paths
# ---------------------------------------------------------------------------


class TestFmpRequest:
    def _client(self, mod, responses):
        client = mod.FMPClient("fake-key")
        client.session = FakeSession(responses)
        return client

    def test_success_resets_retry_count(self, mod):
        client = self._client(mod, [FakeResponse(200, [{"a": 1}])])
        client.retry_count = 1
        assert client._request("http://x", {}) == [{"a": 1}]
        assert client.retry_count == 0

    def test_rate_limit_retries_once_then_succeeds(self, mod, monkeypatch):
        sleeps = []
        monkeypatch.setattr(time, "sleep", lambda s: sleeps.append(s))
        client = self._client(mod, [FakeResponse(429), FakeResponse(200, {"ok": True})])
        assert client._request("http://x", {}) == {"ok": True}
        assert 60 in sleeps
        assert client.rate_limit_reached is False

    def test_second_rate_limit_sets_flag_and_short_circuits(self, mod):
        client = self._client(mod, [FakeResponse(429), FakeResponse(429)])
        assert client._request("http://x", {}) is None
        assert client.rate_limit_reached is True
        # Once flagged, no further HTTP is attempted.
        assert client._request("http://x", {}) is None
        assert client._get("income-statement/AAPL") is None
        assert len(client.session.calls) == 2

    def test_non_200_warns_unless_quiet(self, mod, capsys):
        client = self._client(mod, [FakeResponse(403), FakeResponse(500)])
        assert client._request("http://x", {}, quiet=True) is None
        assert capsys.readouterr().err == ""
        assert client._request("http://y", {}) is None
        assert "HTTP 500" in capsys.readouterr().err

    def test_transport_exceptions_use_shared_visible_diagnostics(self, mod, capsys):
        client = self._client(
            mod,
            [
                mod.requests.exceptions.Timeout("net down"),
                mod.requests.exceptions.Timeout("quiet one"),
            ],
        )
        assert client._request("http://x", {}) is None
        assert "net down" in capsys.readouterr().err
        assert client._request("http://x", {}, quiet=True) is None
        assert "quiet one" in capsys.readouterr().err


class TestFmpGetAndWrappers:
    def test_get_stable_failure_never_tries_retired_v3(self, mod):
        client = mod.FMPClient("k")
        client.session = FakeSession([FakeResponse(403)])
        assert client._get("income-statement/AAPL", {"limit": 2}) is None
        assert len(client.session.calls) == 1
        url, query = client.session.calls[0]
        assert url.endswith("/stable/income-statement")
        assert query == {"limit": 2, "symbol": "AAPL"}

    def test_get_returns_none_when_all_attempts_fail(self, mod):
        client = mod.FMPClient("k")
        client.session = FakeSession([FakeResponse(500), FakeResponse(500)])
        assert client._get("profile/AAPL") is None

    def test_unsupported_endpoint_never_attempts_http(self, mod):
        client = mod.FMPClient("k")
        client.session = FakeSession([])
        assert client._get("something-else/1") is None
        assert client.session.calls == []

    def test_normalize_dividends_wraps_flat_list(self, mod):
        out = mod.FMPClient._normalize(
            "historical-price-full/stock_dividend/AAPL", [{"date": "2020-01-01"}]
        )
        assert out == {"historical": [{"date": "2020-01-01"}]}
        passthrough = mod.FMPClient._normalize(
            "historical-price-full/stock_dividend/AAPL", {"historical": []}
        )
        assert passthrough == {"historical": []}

    def test_normalize_renames_fields(self, mod):
        km = mod.FMPClient._normalize("key-metrics/AAPL", [{"returnOnEquity": 0.3}])
        assert km[0]["roe"] == 0.3
        cf = mod.FMPClient._normalize("cash-flow-statement/AAPL", [{"netDividendsPaid": -5.0}])
        assert cf[0]["dividendsPaid"] == -5.0
        assert mod.FMPClient._normalize("quote/AAPL", None) is None

    def test_screen_stocks_wrapper(self, mod):
        client = mod.FMPClient("k")
        client.session = FakeSession([FakeResponse(200, [{"symbol": "AAA"}])])
        assert client.screen_stocks(min_market_cap=5, exchange="NYSE") == [{"symbol": "AAA"}]
        url, params = client.session.calls[0]
        assert url.endswith("/stable/company-screener")
        assert params == {"marketCapMoreThan": 5, "exchange": "NYSE"}

    def test_screen_stocks_failure_gives_empty_list(self, mod):
        client = mod.FMPClient("k")
        client.session = FakeSession([FakeResponse(500), FakeResponse(500)])
        assert client.screen_stocks() == []

    def test_statement_wrappers_return_empty_list_on_failure(self, mod):
        client = mod.FMPClient("k")
        client.rate_limit_reached = True
        assert client.get_balance_sheet("A") == []
        assert client.get_cash_flow("A") == []
        assert client.get_key_metrics("A") == []
        assert client.get_income_statement("A") == []
        assert client.get_dividend_history("A") is None

    def test_company_profile_first_element_or_none(self, mod):
        client = mod.FMPClient("k")
        client.session = FakeSession([FakeResponse(200, [{"sector": "Tech"}, {"sector": "X"}])])
        assert client.get_company_profile("A") == {"sector": "Tech"}
        client.session = FakeSession([FakeResponse(200, [])])
        assert client.get_company_profile("A") is None

    def test_quote_with_profile_merges_sector(self, mod):
        client = mod.FMPClient("k")
        client.session = FakeSession(
            [
                FakeResponse(200, [{"symbol": "A", "price": 10, "name": "A Inc"}]),
                FakeResponse(
                    200, [{"sector": "Tech", "companyName": "A Corp", "industry": "Software"}]
                ),
            ]
        )
        merged = client.get_quote_with_profile("A")
        assert merged["sector"] == "Tech"
        assert merged["companyName"] == "A Corp"
        assert merged["industry"] == "Software"
        assert merged["price"] == 10

    def test_quote_with_profile_falls_back_without_profile(self, mod):
        client = mod.FMPClient("k")
        client.session = FakeSession(
            [
                FakeResponse(200, [{"symbol": "A", "price": 10, "name": "A Inc"}]),
                FakeResponse(500),
                FakeResponse(500),
            ]
        )
        merged = client.get_quote_with_profile("A")
        assert merged["sector"] == "Unknown"
        assert merged["companyName"] == "A Inc"

    def test_quote_with_profile_none_when_no_quote(self, mod):
        client = mod.FMPClient("k")
        client.session = FakeSession(
            [
                FakeResponse(200, []),
            ]
        )
        assert client.get_quote_with_profile("A") is None


class TestHistoricalPrices:
    def _bars(self, n):
        return [{"close": 100.0 - i} for i in range(n)]

    def test_stable_list_truncated_to_days(self, mod):
        client = mod.FMPClient("k")
        client.session = FakeSession([FakeResponse(200, self._bars(40))])
        out = client.get_historical_prices("AAPL", days=30)
        assert len(out) == 30
        url, params = client.session.calls[0]
        assert url.endswith("/stable/historical-price-eod/full")
        assert params["symbol"] == "AAPL"
        assert params["from"] < params["to"]

    def test_failed_stable_history_has_no_retired_fallback(self, mod):
        client = mod.FMPClient("k")
        client.session = FakeSession([FakeResponse(403)])
        assert client.get_historical_prices("AAPL", days=30) is None
        assert len(client.session.calls) == 1
        assert "/api/v3/" not in client.session.calls[0][0]

    def test_retired_wrapper_is_not_valid_stable_history(self, mod):
        client = mod.FMPClient("k")
        client.session = FakeSession([FakeResponse(200, {"historicalStockList": []})])
        assert client.get_historical_prices("BRK-B") is None
        assert len(client.session.calls) == 1

    def test_all_failures_return_none_and_disable_endpoint(self, mod):
        client = mod.FMPClient("k")
        stable = f"{mod.FMPClient.STABLE_URL}/historical-price-eod/full"
        client.session = FakeSession([FakeResponse(500)] * 3)
        for _ in range(3):
            assert client.get_historical_prices("AAPL") is None
        assert stable in client._disabled_endpoints
        client.session = FakeSession([])
        assert client.get_historical_prices("AAPL") is None
        assert client.session.calls == []

    def test_unrecognised_dict_counts_as_failure(self, mod):
        client = mod.FMPClient("k")
        client.session = FakeSession([FakeResponse(200, {"unexpected": 1})] * 2)
        assert client.get_historical_prices("AAPL") is None
        assert (
            client._endpoint_failures[f"{mod.FMPClient.STABLE_URL}/historical-price-eod/full"] == 1
        )


# ---------------------------------------------------------------------------
# Pure analysis helpers not covered elsewhere
# ---------------------------------------------------------------------------


class TestAnalyzerHelpers:
    def test_rsi_insufficient_data_and_all_gains(self, mod):
        assert mod.RSICalculator.calculate_rsi([1.0] * 10) is None
        assert mod.RSICalculator.calculate_rsi([float(i) for i in range(1, 30)]) == 100.0

    def test_rsi_mixed_known_value(self, mod):
        # 14 changes: 7 gains of +1 and 7 losses of -1 -> RS == 1 -> RSI 50.
        prices = [100.0]
        for i in range(14):
            prices.append(prices[-1] + (1 if i % 2 == 0 else -1))
        assert mod.RSICalculator.calculate_rsi(prices) == 50.0

    def test_cagr_invalid_inputs_and_value(self, mod):
        a = mod.StockAnalyzer
        assert a.calculate_cagr(0, 5, 3) is None
        assert a.calculate_cagr(5, -1, 3) is None
        assert a.calculate_cagr(5, 10, 0) is None
        assert a.calculate_cagr(1.0, 8.0, 3) == 100.0

    def _div_history(self, amounts_by_year):
        return {
            "historical": [
                {"date": f"{year}-06-15", "dividend": amt} for year, amt in amounts_by_year.items()
            ]
        }

    def test_dividend_growth_cagr_consistency_and_streak(self, mod):
        hist = self._div_history({2018: 1.0, 2019: 1.2, 2020: 1.5, 2021: 2.0, 2022: 2.7})
        cagr, consistent, latest, streak = mod.StockAnalyzer.analyze_dividend_growth(hist)
        # last four years: 1.2 -> 2.7 over 3 years
        assert cagr == round(((2.7 / 1.2) ** (1 / 3) - 1) * 100, 2)
        assert consistent is True
        assert latest == 2.7
        assert streak == 4

    def test_dividend_cut_breaks_consistency(self, mod):
        hist = self._div_history({2018: 2.0, 2019: 2.2, 2020: 1.0, 2021: 1.5, 2022: 2.0})
        _cagr, consistent, _latest, streak = mod.StockAnalyzer.analyze_dividend_growth(hist)
        assert consistent is False
        assert streak == 2

    def test_dividend_growth_insufficient_history(self, mod):
        a = mod.StockAnalyzer
        assert a.analyze_dividend_growth(None) == (None, False, None, 0)
        assert a.analyze_dividend_growth({"x": 1}) == (None, False, None, 0)
        short = self._div_history({2020: 1.0, 2021: 1.1, 2022: 1.2})
        assert a.analyze_dividend_growth(short) == (None, False, None, 0)

    def test_dividend_growth_ignores_current_year(self, mod):
        from datetime import date

        current = date.today().year
        # 4 rows but only 3 completed years once the current year is dropped.
        hist = self._div_history(
            {current - 3: 1.0, current - 2: 1.1, current - 1: 1.2, current: 1.3}
        )
        assert mod.StockAnalyzer.analyze_dividend_growth(hist) == (None, False, None, 0)

    def test_finite_amount_rejects_non_numeric(self, mod):
        f = mod.StockAnalyzer._finite_amount
        assert f(True) is None
        assert f("5") is None
        assert f(float("nan")) is None
        assert f(float("inf")) is None
        assert f(10**400) is None  # OverflowError on float()
        assert f(3) == 3.0

    def test_ffo_calculation(self, mod):
        a = mod.StockAnalyzer
        assert a.calculate_ffo([]) is None
        assert a.calculate_ffo([{"netIncome": 100}]) is None
        assert a.calculate_ffo([{"netIncome": 100, "depreciationAndAmortization": 50}]) == 150.0
        assert a.calculate_ffo([{"netIncome": 1e308, "depreciationAndAmortization": 1e308}]) is None

    def test_ffo_payout_ratio(self, mod):
        a = mod.StockAnalyzer
        cf = {"netIncome": 100, "depreciationAndAmortization": 100, "dividendsPaid": -100}
        assert a.calculate_ffo_payout_ratio([cf]) == 50.0
        assert a.calculate_ffo_payout_ratio([]) is None
        assert a.calculate_ffo_payout_ratio([{**cf, "netIncome": -500}]) is None
        assert a.calculate_ffo_payout_ratio([{**cf, "dividendsPaid": 0}]) is None
        assert a.calculate_ffo_payout_ratio([{**cf, "dividendsPaid": None}]) is None

    def test_metrics_payout_ratio_fallback(self, mod):
        g = mod.StockAnalyzer.get_payout_ratio_from_metrics
        assert g([]) is None
        assert g([{"payoutRatio": 0.316}]) == pytest.approx(31.6)
        assert g([{"payoutRatio": -0.1}]) is None
        assert g([{"payoutRatio": "n/a"}]) is None
        assert g([{"payoutRatio": 1e308}]) is None  # *100 overflows to inf

    def test_financial_health(self, mod):
        h = mod.StockAnalyzer.analyze_financial_health
        assert h([]) == {}
        good = h(
            [
                {
                    "totalDebt": 50,
                    "totalStockholdersEquity": 100,
                    "totalCurrentAssets": 200,
                    "totalCurrentLiabilities": 100,
                }
            ]
        )
        assert good == {"debt_to_equity": 0.5, "current_ratio": 2.0, "financially_healthy": True}
        levered = h(
            [
                {
                    "totalDebt": 300,
                    "totalStockholdersEquity": 100,
                    "totalCurrentAssets": 200,
                    "totalCurrentLiabilities": 100,
                }
            ]
        )
        assert levered["financially_healthy"] is False
        illiquid = h(
            [
                {
                    "totalDebt": 10,
                    "totalStockholdersEquity": 100,
                    "totalCurrentAssets": 50,
                    "totalCurrentLiabilities": 100,
                }
            ]
        )
        assert illiquid["financially_healthy"] is False
        # Zero equity / liabilities yield None ratios, which are not penalised.
        assert h([{}]) == {
            "debt_to_equity": None,
            "current_ratio": None,
            "financially_healthy": True,
        }

    def test_growth_metrics(self, mod):
        g = mod.StockAnalyzer.analyze_growth_metrics
        assert g([]) == {"revenue_cagr_3y": None, "eps_cagr_3y": None}
        assert g([{}, {}, {}]) == {"revenue_cagr_3y": None, "eps_cagr_3y": None}
        stmts = [
            {"revenue": 800, "eps": 8},
            {},
            {},
            {"revenue": 100, "eps": 1},
        ]
        assert g(stmts) == {"revenue_cagr_3y": 100.0, "eps_cagr_3y": 100.0}

    @pytest.mark.parametrize(("cagr", "expected_points"), [(25, 40), (16, 35), (13, 30), (5, 20)])
    def test_composite_score_dividend_tiers(self, mod, cagr, expected_points):
        base = {
            "dividend_cagr_3y": cagr,
            "roe": 0,
            "profit_margin": 0,
            "debt_to_equity": 999,
            "rsi": 99,
            "pe_ratio": 999,
            "pb_ratio": 999,
        }
        # roe(3) + margin(3) + rsi(5) are the floor contributions.
        assert mod.StockAnalyzer.calculate_composite_score(base) == expected_points + 11

    def test_composite_score_best_case_and_cap(self, mod):
        best = {
            "dividend_cagr_3y": 25,
            "dividend_consistent": True,
            "roe": 25,
            "profit_margin": 25,
            "debt_to_equity": 0.1,
            "rsi": 20,
            "pe_ratio": 10,
            "pb_ratio": 1,
        }
        # 40+5+12+10+8+20+5+5 = 105 -> capped at 100
        assert mod.StockAnalyzer.calculate_composite_score(best) == 100.0

    @pytest.mark.parametrize(
        ("roe", "margin", "de", "rsi", "pe", "pb", "extra"),
        [
            (16, 16, 0.9, 28, 20, 4, 10 + 8 + 6 + 18 + 3 + 3),
            (12, 12, 1.5, 33, 30, 6, 7 + 6 + 3 + 15 + 0 + 0),
            (5, 5, 5.0, 38, 30, 6, 3 + 3 + 0 + 12 + 0 + 0),
        ],
    )
    def test_composite_score_mid_tiers(self, mod, roe, margin, de, rsi, pe, pb, extra):
        stock = {
            "dividend_cagr_3y": 12,
            "roe": roe,
            "profit_margin": margin,
            "debt_to_equity": de,
            "rsi": rsi,
            "pe_ratio": pe,
            "pb_ratio": pb,
        }
        assert mod.StockAnalyzer.calculate_composite_score(stock) == 30 + extra

    def test_payout_ratios_reit_ffo(self, mod):
        cf = [
            {
                "netIncome": 100,
                "depreciationAndAmortization": 100,
                "dividendsPaid": -100,
                "freeCashFlow": 10,
            }
        ]
        out = mod.StockAnalyzer.calculate_payout_ratios([], cf, is_reit=True)
        assert out["payout_ratio"] == 50.0
        assert out["sustainable"] is True
        assert out["sustainability_basis"] == "FFO"
        assert out["fcf_coverage_status"] == "INSUFFICIENT_FCF"

    def test_payout_ratios_reit_without_ffo_data(self, mod):
        cf = [{"dividendsPaid": -10, "freeCashFlow": 50}]
        out = mod.StockAnalyzer.calculate_payout_ratios([], cf, is_reit=True)
        assert out["payout_ratio"] is None
        assert out["sustainable"] is False
        assert "FFO coverage cannot be assessed" in out["sustainability_note"]

    def test_payout_ratios_reit_high_ffo_payout(self, mod):
        cf = [{"netIncome": 50, "depreciationAndAmortization": 50, "dividendsPaid": -95}]
        out = mod.StockAnalyzer.calculate_payout_ratios([], cf, is_reit=True)
        assert out["sustainable"] is False
        assert "under-80%" in out["sustainability_note"]

    def test_payout_ratios_missing_inputs(self, mod):
        calc = mod.StockAnalyzer.calculate_payout_ratios
        assert calc([], [])["fcf_coverage_status"] == "MISSING_DATA"
        no_div = calc([], [{"freeCashFlow": 5}])
        assert no_div["fcf_status"] == "POSITIVE"
        assert "Dividend payment data is unavailable" in no_div["sustainability_note"]
        zero_div = calc([], [{"dividendsPaid": 0}])
        assert zero_div["fcf_coverage_status"] == "NO_DIVIDEND"
        assert zero_div["sustainable"] is False

    @pytest.mark.parametrize(
        ("fcf", "status", "note_fragment"),
        [
            (-5, "NEGATIVE_FCF", "negative free cash flow"),
            (0, "ZERO_FCF", "zero free cash flow"),
            (10, "INSUFFICIENT_FCF", "below dividends"),
            (20, "AT_LIMIT", "exactly equals"),
        ],
    )
    def test_payout_ratios_non_reit_fcf_states(self, mod, fcf, status, note_fragment):
        income = [{"netIncome": 1000}]
        cf = [{"dividendsPaid": -20, "freeCashFlow": fcf}]
        out = mod.StockAnalyzer.calculate_payout_ratios(income, cf)
        assert out["fcf_coverage_status"] == status
        assert out["sustainable"] is False
        assert note_fragment in out["sustainability_note"]

    def test_payout_ratios_non_reit_missing_fcf(self, mod):
        out = mod.StockAnalyzer.calculate_payout_ratios(
            [{"netIncome": 1000}], [{"dividendsPaid": -20}]
        )
        assert out["fcf_coverage_status"] == "MISSING_DATA"
        assert "free cash flow is unavailable" in out["sustainability_note"]

    def test_payout_ratios_non_reit_covered_and_sustainable(self, mod):
        out = mod.StockAnalyzer.calculate_payout_ratios(
            [{"netIncome": 1000}], [{"dividendsPaid": -200, "freeCashFlow": 800}]
        )
        assert out["payout_ratio"] == 20.0
        assert out["fcf_payout_ratio"] == 25.0
        assert out["sustainable"] is True
        assert "buffer" in out["sustainability_note"]

    def test_payout_ratios_non_reit_high_or_unknown_earnings_payout(self, mod):
        cf = [{"dividendsPaid": -900, "freeCashFlow": 1000}]
        high = mod.StockAnalyzer.calculate_payout_ratios([{"netIncome": 1000}], cf)
        assert high["payout_ratio"] == 90.0
        assert high["sustainable"] is False
        assert "under-80%" in high["sustainability_note"]
        unknown = mod.StockAnalyzer.calculate_payout_ratios([{"netIncome": -5}], cf)
        assert unknown["payout_ratio"] is None
        assert "cannot be assessed" in unknown["sustainability_note"]

    def test_is_reit_flags(self, mod):
        r = mod.StockAnalyzer.is_reit
        assert r({"isReit": True}) is True
        assert r({"industry": "REIT - Retail"}) is True
        assert r({"industry": "Non-REIT Real Estate"}) is False
        assert r({"industry": None}) is False


# ---------------------------------------------------------------------------
# screen_dividend_growth_pullbacks orchestration
# ---------------------------------------------------------------------------

GOOD_DIVIDENDS = {
    "historical": [
        {"date": "2018-06-01", "dividend": 1.0},
        {"date": "2019-06-01", "dividend": 1.3},
        {"date": "2020-06-01", "dividend": 1.7},
        {"date": "2021-06-01", "dividend": 2.2},
    ]
}


def _oversold_bars(n=30):
    # most-recent-first and rising => oldest-first is falling => RSI 0.
    return [{"close": 70.0 + i} for i in range(n)]


def _income(n=5):
    return [
        {"netIncome": 1000, "revenue": 1000 + 100 * (n - i), "eps": 5 + (n - i)} for i in range(n)
    ]


class FakeFMP:
    """Stand-in for FMPClient with per-symbol overridable data."""

    instances: list = []

    def __init__(self, api_key):
        self.api_key = api_key
        self.rate_limit_reached = False
        self.data = {}
        self.screen_result = []
        self.quote_calls = []
        FakeFMP.instances.append(self)

    # Behavior configured via class-level registry set by tests.
    registry: dict = {}

    def screen_stocks(self, min_market_cap=0, exchange=None):
        return list(FakeFMP.registry.get("screen", []))

    def get_quote_with_profile(self, symbol):
        self.quote_calls.append(symbol)
        return FakeFMP.registry.get("quotes", {}).get(symbol)

    def _per(self, key, symbol, default):
        return FakeFMP.registry.get(key, {}).get(symbol, default)

    def get_dividend_history(self, symbol):
        return self._per("div", symbol, GOOD_DIVIDENDS)

    def get_historical_prices(self, symbol, days=30):
        return self._per("prices", symbol, _oversold_bars())

    def get_income_statement(self, symbol, limit=5):
        return self._per("income", symbol, _income())

    def get_balance_sheet(self, symbol, limit=5):
        return self._per(
            "balance",
            symbol,
            [
                {
                    "totalDebt": 40,
                    "totalStockholdersEquity": 100,
                    "totalCurrentAssets": 200,
                    "totalCurrentLiabilities": 100,
                }
            ],
        )

    def get_cash_flow(self, symbol, limit=5):
        return self._per("cf", symbol, [{"dividendsPaid": -200, "freeCashFlow": 800}])

    def get_key_metrics(self, symbol, limit=1):
        return self._per(
            "metrics",
            symbol,
            [{"roe": 0.25, "netProfitMargin": 0.22, "peRatio": 12, "pbRatio": 2}],
        )


@pytest.fixture
def fake_fmp(mod, monkeypatch):
    FakeFMP.registry = {}
    FakeFMP.instances = []
    monkeypatch.setattr(mod, "FMPClient", FakeFMP)
    return FakeFMP


def _stock(symbol, price=20.0, **extra):
    return {
        "symbol": symbol,
        "companyName": f"{symbol} Inc",
        "price": price,
        "sector": "Tech",
        **extra,
    }


class TestScreeningPipeline:
    def test_qualifying_stock_full_result(self, mod, fake_fmp):
        fake_fmp.registry["screen"] = [_stock("AAA")]
        results = mod.screen_dividend_growth_pullbacks("key")
        assert len(results) == 1
        r = results[0]
        assert r["symbol"] == "AAA"
        assert r["dividend_yield"] == 11.0  # 2.2 / 20
        assert r["annual_dividend"] == 2.2
        assert r["dividend_cagr_3y"] == round(((2.2 / 1.0) ** (1 / 3) - 1) * 100, 2)
        assert r["rsi"] == 0.0
        assert r["roe"] == pytest.approx(25.0)
        assert r["profit_margin"] == pytest.approx(22.0)
        assert r["payout_ratio"] == 20.0
        assert r["fcf_payout_ratio"] == 25.0
        assert r["dividend_sustainable"] is True
        assert r["financially_healthy"] is True
        assert r["composite_score"] == mod.StockAnalyzer.calculate_composite_score(r)
        assert 0 < r["composite_score"] <= 100

    def test_results_sorted_by_composite_score_desc(self, mod, fake_fmp):
        fake_fmp.registry["screen"] = [_stock("LOW"), _stock("HIGH")]
        fake_fmp.registry["metrics"] = {
            "LOW": [{"roe": 0.05, "netProfitMargin": 0.05, "peRatio": 40, "pbRatio": 9}],
        }
        results = mod.screen_dividend_growth_pullbacks("key")
        assert [r["symbol"] for r in results] == ["HIGH", "LOW"]
        assert results[0]["composite_score"] > results[1]["composite_score"]

    def test_max_candidates_limits_fmp_only_mode(self, mod, fake_fmp):
        fake_fmp.registry["screen"] = [_stock("A1"), _stock("A2"), _stock("A3")]
        results = mod.screen_dividend_growth_pullbacks("key", max_candidates=2)
        assert {r["symbol"] for r in results} == {"A1", "A2"}

    def test_no_candidates_returns_empty(self, mod, fake_fmp, capsys):
        assert mod.screen_dividend_growth_pullbacks("key") == []
        assert "No candidates found" in capsys.readouterr().err

    def test_finviz_symbols_fetch_quotes_and_skip_missing(self, mod, fake_fmp):
        fake_fmp.registry["quotes"] = {"AAA": _stock("AAA")}  # BBB has no quote
        results = mod.screen_dividend_growth_pullbacks(
            "key", max_candidates=1, finviz_symbols={"AAA", "BBB"}
        )
        assert [r["symbol"] for r in results] == ["AAA"]
        assert sorted(fake_fmp.instances[0].quote_calls) == ["AAA", "BBB"]

    def test_finviz_quote_stage_stops_on_rate_limit(self, mod, fake_fmp, monkeypatch, capsys):
        fake_fmp.registry["quotes"] = {"AAA": _stock("AAA")}
        original = fake_fmp.get_quote_with_profile

        def limited(self, symbol):
            out = original(self, symbol)
            self.rate_limit_reached = True
            return out

        monkeypatch.setattr(fake_fmp, "get_quote_with_profile", limited)
        results = mod.screen_dividend_growth_pullbacks("key", finviz_symbols={"AAA", "BBB"})
        err = capsys.readouterr().err
        assert "rate limit reached while fetching quotes" in err
        assert len(fake_fmp.instances[0].quote_calls) == 1
        assert results == []  # loop breaks before analysis when limit is hit

    @pytest.mark.parametrize(
        ("overrides", "message"),
        [
            ({"price": 0}, "No valid price data"),
            ({"div": {"X": None}}, "No dividend history"),
            ({"div": {"X": {"historical": GOOD_DIVIDENDS["historical"][:2]}}}, "Dividend CAGR"),
            ({"price": 1000.0}, "Dividend yield"),
            ({"prices": {"X": _oversold_bars(10)}}, "Insufficient price data"),
            ({"prices": {"X": [{"close": 100.0 - i} for i in range(30)]}}, "RSI"),
            (
                {
                    "income": {
                        "X": [
                            {"revenue": 50, "eps": 5},
                            {},
                            {},
                            {"revenue": 100, "eps": 1},
                        ]
                    }
                },
                "Negative revenue growth",
            ),
            (
                {
                    "income": {
                        "X": [
                            {"revenue": 200, "eps": 0.5},
                            {},
                            {},
                            {"revenue": 100, "eps": 1},
                        ]
                    }
                },
                "Negative EPS growth",
            ),
            (
                {
                    "balance": {
                        "X": [
                            {
                                "totalDebt": 500,
                                "totalStockholdersEquity": 100,
                                "totalCurrentAssets": 200,
                                "totalCurrentLiabilities": 100,
                            }
                        ]
                    }
                },
                "Financial health concerns",
            ),
        ],
    )
    def test_filter_rejections(self, mod, fake_fmp, capsys, overrides, message):
        overrides = dict(overrides)
        price = overrides.pop("price", 20.0)
        fake_fmp.registry.update(overrides)
        fake_fmp.registry["screen"] = [_stock("X", price=price)]
        assert mod.screen_dividend_growth_pullbacks("key") == []
        assert message in capsys.readouterr().err

    def test_rsi_above_max_rejected_but_passes_with_looser_max(self, mod, fake_fmp):
        # Alternating prices give a mid-range RSI.
        bars = [{"close": 100.0 + (1 if i % 2 else -1)} for i in range(30)]
        fake_fmp.registry["prices"] = {"X": bars}
        fake_fmp.registry["screen"] = [_stock("X")]
        assert mod.screen_dividend_growth_pullbacks("key", rsi_max=40.0) == []
        assert len(mod.screen_dividend_growth_pullbacks("key", rsi_max=60.0)) == 1

    def test_reit_uses_ffo_basis(self, mod, fake_fmp):
        fake_fmp.registry["screen"] = [_stock("REIT1", industry="REIT - Retail")]
        fake_fmp.registry["cf"] = {
            "REIT1": [
                {
                    "netIncome": 100,
                    "depreciationAndAmortization": 100,
                    "dividendsPaid": -100,
                    "freeCashFlow": 50,
                }
            ]
        }
        (r,) = mod.screen_dividend_growth_pullbacks("key")
        assert r["sustainability_basis"] == "FFO"
        assert r["payout_ratio"] == 50.0

    def test_payout_falls_back_to_key_metrics_but_stays_unsustainable(self, mod, fake_fmp):
        fake_fmp.registry["screen"] = [_stock("X")]
        fake_fmp.registry["income"] = {"X": [{"netIncome": -1, "revenue": 1}]}
        fake_fmp.registry["metrics"] = {
            "X": [{"payoutRatio": 0.4, "roe": 0.2, "netProfitMargin": 0.2}]
        }
        (r,) = mod.screen_dividend_growth_pullbacks("key")
        assert r["payout_ratio"] == 40.0
        assert r["dividend_sustainable"] is False

    @pytest.mark.parametrize(
        "stage",
        ["div", "prices", "income", "balance", "cf", "metrics"],
    )
    def test_rate_limit_during_stage_stops_analysis(self, mod, fake_fmp, monkeypatch, stage):
        method = {
            "div": "get_dividend_history",
            "prices": "get_historical_prices",
            "income": "get_income_statement",
            "balance": "get_balance_sheet",
            "cf": "get_cash_flow",
            "metrics": "get_key_metrics",
        }[stage]
        original = getattr(fake_fmp, method)

        def trip(self, *a, **k):
            out = original(self, *a, **k)
            self.rate_limit_reached = True
            return out

        monkeypatch.setattr(fake_fmp, method, trip)
        fake_fmp.registry["screen"] = [_stock("A1"), _stock("A2")]
        # Rate limit trips during A1's analysis; nothing qualifies and A2 is never reached.
        assert mod.screen_dividend_growth_pullbacks("key") == []

    def test_rate_limit_on_second_candidate_returns_partial(self, mod, fake_fmp, monkeypatch):
        fake_fmp.registry["screen"] = [_stock("A1"), _stock("A2")]

        def flag_on_second_div(self, symbol):
            if symbol == "A2":
                self.rate_limit_reached = True
            return GOOD_DIVIDENDS

        monkeypatch.setattr(fake_fmp, "get_dividend_history", flag_on_second_div)
        results = mod.screen_dividend_growth_pullbacks("key")
        assert [r["symbol"] for r in results] == ["A1"]


# ---------------------------------------------------------------------------
# generate_markdown_report
# ---------------------------------------------------------------------------

CRITERIA = {"dividend_yield_min": 1.5, "dividend_cagr_min": 12.0, "rsi_max": 40.0}


def _result(**over):
    base = {
        "symbol": "ZZZ",
        "company_name": "Zed Corp",
        "sector": "Tech",
        "market_cap": 5e9,
        "price": 50.0,
        "composite_score": 77.5,
        "dividend_yield": 2.5,
        "annual_dividend": 1.25,
        "dividend_cagr_3y": 22.0,
        "dividend_consistent": True,
        "payout_ratio": 35.0,
        "rsi": 28.0,
        "revenue_cagr_3y": 8.0,
        "eps_cagr_3y": 9.0,
        "roe": 21.0,
        "profit_margin": 12.0,
        "dividend_sustainable": True,
        "debt_to_equity": 0.4,
        "current_ratio": 1.5,
    }
    base.update(over)
    return base


class TestMarkdownReport:
    def test_empty_results_report(self, mod, tmp_path):
        out = tmp_path / "r.md"
        mod.generate_markdown_report([], CRITERIA, str(out))
        text = out.read_text(encoding="utf-8")
        assert "**Total Qualified Stocks:** 0" in text
        assert "## No Stocks Qualified" in text
        assert "**Dividend Yield:** ≥ 1.5%" in text
        assert "## Methodology" in text

    def test_extreme_oversold_stock_section(self, mod, tmp_path):
        out = tmp_path / "r.md"
        mod.generate_markdown_report([_result()], CRITERIA, str(out))
        text = out.read_text(encoding="utf-8")
        assert "## 1. ZZZ - Zed Corp" in text
        assert "**Market Cap:** $5.0B" in text
        assert "Extreme Oversold" in text
        assert "Immediate - Scale in 50%" in text
        assert "8% below entry" in text
        assert "🔥 Exceptional" in text
        assert "✓ Above 2%" in text
        assert "✓ Sustainable" in text
        assert "✓ Excellent" in text  # ROE >= 20
        assert "Sustainability confirmed: Yes" in text
        assert "Year 5 Yield on Cost: %.2f%%" % (2.5 * 1.22**5) in text
        assert "No No" not in text

    def test_strong_oversold_and_risk_factors(self, mod, tmp_path):
        out = tmp_path / "r.md"
        stock = _result(
            rsi=33.0,
            dividend_yield=1.6,
            dividend_cagr_3y=16.0,
            payout_ratio=85.0,
            debt_to_equity=1.4,
            dividend_consistent=False,
            dividend_sustainable=False,
            roe=16.0,
            current_ratio=1.1,
        )
        mod.generate_markdown_report([stock], CRITERIA, str(out))
        text = out.read_text(encoding="utf-8")
        assert "Strong Oversold" in text
        assert "Good - Full position OK" in text
        assert "⚠ Below 2%" in text
        assert "✓ Excellent" in text  # CAGR >= 15
        assert "⚠ High" in text  # payout 70-100
        assert "Payout ratio 85% limits dividend growth runway" in text
        assert "Debt-to-equity 1.4 requires monitoring" in text
        assert "Sustainability confirmed: No" in text
        assert "✓ Good" in text  # ROE >= 15
        assert "⚠ Adequate" in text

    def test_early_pullback_and_missing_values(self, mod, tmp_path):
        out = tmp_path / "r.md"
        stock = _result(
            rsi=38.0,
            payout_ratio=None,
            revenue_cagr_3y=None,
            eps_cagr_3y=None,
            roe=0,
            profit_margin=0,
            debt_to_equity=None,
            current_ratio=None,
            dividend_cagr_3y=13.0,
        )
        mod.generate_markdown_report([stock], CRITERIA, str(out))
        text = out.read_text(encoding="utf-8")
        assert "Early Pullback" in text
        assert "Conservative - High conviction" in text
        assert "3-5% stop loss" in text
        assert "| Payout Ratio | N/A | N/A |" in text
        assert "| Debt-to-Equity | N/A | N/A |" in text
        assert "Monitor payout ratio sustainability" in text

    def test_payout_over_100_flagged_as_risk(self, mod, tmp_path):
        out = tmp_path / "r.md"
        mod.generate_markdown_report([_result(payout_ratio=120.0)], CRITERIA, str(out))
        assert "❌ Risk" in out.read_text(encoding="utf-8")

    def test_multiple_stocks_numbered_in_order(self, mod, tmp_path):
        out = tmp_path / "r.md"
        mod.generate_markdown_report(
            [_result(symbol="AAA"), _result(symbol="BBB", rsi=36.0)], CRITERIA, str(out)
        )
        text = out.read_text(encoding="utf-8")
        assert text.index("## 1. AAA") < text.index("## 2. BBB")
        assert "**Total Qualified Stocks:** 2" in text


# ---------------------------------------------------------------------------
# main() CLI
# ---------------------------------------------------------------------------


@pytest.fixture
def cli_env(mod, tmp_path, monkeypatch):
    """Redirect main()'s project-root logs/ dir into tmp_path and clear keys."""
    fake_script = tmp_path / "skills" / "dividend-growth-pullback-screener" / "scripts" / "x.py"
    fake_script.parent.mkdir(parents=True)
    monkeypatch.setattr(mod, "__file__", str(fake_script))
    monkeypatch.delenv("FMP_API_KEY", raising=False)
    monkeypatch.delenv("FINVIZ_API_KEY", raising=False)
    return tmp_path


def _run_main(mod, monkeypatch, argv):
    monkeypatch.setattr(sys, "argv", ["screen_dividend_growth_rsi.py", *argv])
    mod.main()


class TestMain:
    def test_missing_fmp_key_exits_1(self, mod, cli_env, monkeypatch, capsys):
        with pytest.raises(SystemExit) as exc:
            _run_main(mod, monkeypatch, [])
        assert exc.value.code == 1
        assert "FMP API key required" in capsys.readouterr().err
        assert not (cli_env / "logs").exists()

    def test_finviz_flag_without_key_exits_1(self, mod, cli_env, monkeypatch, capsys):
        monkeypatch.setenv("FMP_API_KEY", "fmp")
        with pytest.raises(SystemExit) as exc:
            _run_main(mod, monkeypatch, ["--use-finviz"])
        assert exc.value.code == 1
        assert "FINVIZ API key required" in capsys.readouterr().err

    def test_finviz_empty_result_exits_1(self, mod, cli_env, monkeypatch, capsys):
        class EmptyFinviz:
            def __init__(self, key):
                assert key == "fv-arg"

            def screen_stocks(self):
                return set()

        monkeypatch.setattr(mod, "FINVIZClient", EmptyFinviz)
        monkeypatch.setenv("FMP_API_KEY", "fmp")
        with pytest.raises(SystemExit) as exc:
            _run_main(mod, monkeypatch, ["--use-finviz", "--finviz-api-key", "fv-arg"])
        assert exc.value.code == 1
        assert "No stocks found in FINVIZ pre-screening" in capsys.readouterr().err

    def test_fmp_only_run_writes_json_and_markdown(self, mod, cli_env, monkeypatch):
        captured = {}

        def fake_screen(**kwargs):
            captured.update(kwargs)
            return [_result()]

        monkeypatch.setattr(mod, "screen_dividend_growth_pullbacks", fake_screen)
        monkeypatch.setenv("FMP_API_KEY", "env-fmp")
        _run_main(
            mod,
            monkeypatch,
            [
                "--min-yield",
                "2.0",
                "--min-div-growth",
                "15",
                "--rsi-max",
                "35",
                "--max-candidates",
                "7",
            ],
        )
        assert captured == {
            "api_key": "env-fmp",  # pragma: allowlist secret
            "min_yield": 2.0,
            "min_div_growth": 15.0,
            "rsi_max": 35.0,
            "max_candidates": 7,
            "finviz_symbols": None,
        }
        logs = cli_env / "logs"
        (json_path,) = logs.glob("dividend_growth_pullback_results_*.json")
        (md_path,) = logs.glob("dividend_growth_pullback_screening_*.md")
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        assert payload["metadata"]["total_results"] == 1
        assert payload["metadata"]["criteria"]["dividend_yield_min"] == 2.0
        assert payload["metadata"]["criteria"]["rsi_max"] == 35.0
        assert payload["stocks"][0]["symbol"] == "ZZZ"
        assert "## 1. ZZZ - Zed Corp" in md_path.read_text(encoding="utf-8")

    def test_two_stage_run_passes_finviz_symbols(self, mod, cli_env, monkeypatch):
        class OkFinviz:
            def __init__(self, key):
                self.key = key

            def screen_stocks(self):
                return {"AAA", "BBB"}

        captured = {}

        def fake_screen(**kwargs):
            captured.update(kwargs)
            return []

        monkeypatch.setattr(mod, "FINVIZClient", OkFinviz)
        monkeypatch.setattr(mod, "screen_dividend_growth_pullbacks", fake_screen)
        monkeypatch.setenv("FINVIZ_API_KEY", "fv-env")
        _run_main(mod, monkeypatch, ["--use-finviz", "--fmp-api-key", "fmp-arg"])
        assert captured["api_key"] == "fmp-arg"  # pragma: allowlist secret
        assert captured["finviz_symbols"] == {"AAA", "BBB"}
        (json_path,) = (cli_env / "logs").glob("dividend_growth_pullback_results_*.json")
        assert json.loads(json_path.read_text(encoding="utf-8"))["stocks"] == []
        (md_path,) = (cli_env / "logs").glob("dividend_growth_pullback_screening_*.md")
        assert "No Stocks Qualified" in md_path.read_text(encoding="utf-8")
