"""Coverage for FINVIZ/FMP clients, analyzers, the screening pipeline, and CLI."""

import json
import time
from datetime import date, timedelta
from unittest.mock import MagicMock

import pytest
import requests
import screen_dividend_stocks as mod
from screen_dividend_stocks import (
    FINVIZClient,
    FMPClient,
    RSICalculator,
    StockAnalyzer,
)


def _resp(status_code=200, payload=None, content=b"", text=""):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = payload
    resp.content = content
    resp.text = text
    return resp


# --------------------------------------------------------------------------
# FINVIZClient
# --------------------------------------------------------------------------
class TestFINVIZClient:
    def _client(self, response=None, exc=None):
        client = FINVIZClient("fake")
        session = MagicMock()
        if exc:
            session.get.side_effect = exc
        else:
            session.get.return_value = response
        client.session = session
        return client, session

    def test_parses_tickers_and_skips_blank(self):
        csv_bytes = b"No.,Ticker,Company\n1,AAA,A Co\n2, BBB ,B Co\n3,,Blank\n"
        client, session = self._client(_resp(200, content=csv_bytes))
        assert client.screen_stocks() == {"AAA", "BBB"}
        params = session.get.call_args[1]["params"]
        assert params["auth"] == "fake"
        assert "geo_usa" in params["f"]

    @pytest.mark.parametrize("status", [401, 403])
    def test_auth_failure_returns_empty(self, status, capsys):
        client, _ = self._client(_resp(status))
        assert client.screen_stocks() == set()
        assert "authentication failed" in capsys.readouterr().err

    def test_other_status_returns_empty(self, capsys):
        client, _ = self._client(_resp(500))
        assert client.screen_stocks() == set()
        assert "request failed: 500" in capsys.readouterr().err

    def test_request_exception_returns_empty(self, capsys):
        client, _ = self._client(exc=requests.exceptions.ConnectionError("boom"))
        assert client.screen_stocks() == set()
        assert "boom" in capsys.readouterr().err


# --------------------------------------------------------------------------
# FMPClient request handling
# --------------------------------------------------------------------------
class TestFMPRequest:
    def _client(self, *responses):
        client = FMPClient("k")
        session = MagicMock()
        session.get.side_effect = list(responses)
        client.session = session
        return client, session

    def test_200_resets_retry_count_and_returns_json(self):
        client, _ = self._client(_resp(200, {"ok": 1}))
        client.retry_count = 1
        assert client._request("u", {}) == {"ok": 1}
        assert client.retry_count == 0

    def test_429_retries_once_then_succeeds(self, monkeypatch):
        sleeps = []
        monkeypatch.setattr(time, "sleep", lambda s: sleeps.append(s))
        client, session = self._client(_resp(429), _resp(200, [1]))
        assert client._request("u", {}) == [1]
        assert 60 in sleeps
        assert session.get.call_count == 2
        assert client.rate_limit_reached is False

    def test_429_twice_sets_rate_limit_flag(self):
        client, _ = self._client(_resp(429), _resp(429))
        assert client._request("u", {}) is None
        assert client.rate_limit_reached is True
        # Once flagged, further requests short-circuit without HTTP.
        assert client._request("u", {}) is None
        assert client._get("income-statement/AAPL") is None

    def test_non_200_reports_unless_quiet(self, capsys):
        client, _ = self._client(_resp(500, text="server down"), _resp(500, text="server down"))
        assert client._request("u", {}) is None
        assert "server down" in capsys.readouterr().err
        assert client._request("u", {}, quiet=True) is None
        assert capsys.readouterr().err == ""

    def test_transport_exceptions_use_shared_visible_diagnostics(self, capsys):
        client = FMPClient("k")
        client.session = MagicMock()
        client.session.get.side_effect = requests.exceptions.Timeout("slow")
        assert client._request("u", {}) is None
        assert "slow" in capsys.readouterr().err
        assert client._request("u", {}, quiet=True) is None
        assert "slow" in capsys.readouterr().err

    def test_stable_failure_has_no_retired_fallback(self):
        client, session = self._client(_resp(403))
        assert client.get_income_statement("AAPL") == []
        assert session.get.call_count == 1
        assert "/stable/income-statement" in session.get.call_args[0][0]

    def test_unmapped_endpoint_fails_without_http(self):
        client, session = self._client()
        assert client._get("some-other/thing") is None
        assert session.get.call_count == 0

    def test_helper_getters_default_to_empty(self):
        client = FMPClient("k")
        client._get = lambda *a, **k: None
        assert client.get_balance_sheet("A") == []
        assert client.get_cash_flow("A") == []
        assert client.get_key_metrics("A") == []
        assert client.get_dividend_history("A") == {}
        assert client.get_company_profile("A") is None

    def test_company_profile_returns_first_record(self):
        client = FMPClient("k")
        client._get = lambda *a, **k: [{"sector": "Utilities"}, {"sector": "x"}]
        assert client.get_company_profile("A") == {"sector": "Utilities"}


# --------------------------------------------------------------------------
# FMPClient.screen_stocks client-side gates
# --------------------------------------------------------------------------
class TestScreenStocks:
    def test_gates_filter_and_cap_by_market_cap(self):
        universe = [
            {"symbol": "ETF", "isEtf": True, "price": 10, "lastAnnualDividend": 1},
            {"symbol": "FND", "isFund": True, "price": 10, "lastAnnualDividend": 1},
            {"symbol": "NOPRICE", "price": 0, "lastAnnualDividend": 1},
            {"symbol": "LOWYLD", "price": 100, "lastAnnualDividend": 1, "marketCap": 9},
            {"symbol": "BIG", "price": 10, "lastAnnualDividend": 1, "marketCap": 500},
            {"symbol": "MID", "price": 10, "lastAnnualDividend": 1, "marketCap": 300},
            {"symbol": "SMALL", "price": 10, "lastAnnualDividend": 1, "marketCap": 100},
            {"price": 10, "lastAnnualDividend": 1, "marketCap": 400},  # no symbol
            {"symbol": "BADPE", "price": 10, "lastAnnualDividend": 1, "marketCap": 450},
            {"symbol": "NONE", "price": 10, "lastAnnualDividend": 1, "marketCap": 440},
        ]
        ratios = {
            "BIG": [{"priceToEarningsRatio": 10, "priceToBookRatio": 1.5}],
            "MID": [{"priceToEarningsRatio": 25, "priceToBookRatio": 1.5}],
            "BADPE": [{"priceToEarningsRatio": -3, "priceToBookRatio": 1.0}],
            "NONE": [{"priceToEarningsRatio": None, "priceToBookRatio": 1.0}],
        }
        client = FMPClient("k")
        asked = []

        def fake_get(endpoint, params=None):
            if endpoint == "stock-screener":
                return universe
            sym = endpoint.split("/")[1]
            asked.append(sym)
            return ratios.get(sym, [])

        client._get = fake_get
        out = client.screen_stocks(3.0, 20, 2, max_candidates=5)
        assert [s["symbol"] for s in out] == ["BIG"]
        assert out[0]["pe"] == 10 and out[0]["priceToBook"] == 1.5
        # SMALL (6th by cap among yield-qualified) is cut by max_candidates;
        # ETF/fund/no-price/low-yield never reach the ratios stage.
        assert "SMALL" not in asked and "ETF" not in asked and "LOWYLD" not in asked

    def test_stops_when_rate_limited(self):
        universe = [
            {"symbol": "A", "price": 10, "lastAnnualDividend": 1, "marketCap": 3},
            {"symbol": "B", "price": 10, "lastAnnualDividend": 1, "marketCap": 2},
        ]
        client = FMPClient("k")
        calls = []

        def fake_get(endpoint, params=None):
            if endpoint == "stock-screener":
                return universe
            calls.append(endpoint)
            client.rate_limit_reached = True
            return [{"priceToEarningsRatio": 10, "priceToBookRatio": 1}]

        client._get = fake_get
        out = client.screen_stocks(3.0, 20, 2)
        assert calls == ["ratios/A"]
        assert [s["symbol"] for s in out] == ["A"]

    def test_empty_universe(self):
        client = FMPClient("k")
        client._get = lambda *a, **k: None
        assert client.screen_stocks(3.0, 20, 2) == []


# --------------------------------------------------------------------------
# Historical prices
# --------------------------------------------------------------------------
class TestHistoricalPrices:
    def _client(self, *responses):
        client = FMPClient("k")
        session = MagicMock()
        session.get.side_effect = list(responses)
        client.session = session
        return client, session

    def test_stable_list_is_truncated_to_days(self):
        bars = [{"close": i} for i in range(50)]
        client, session = self._client(_resp(200, bars))
        out = client.get_historical_prices("AAPL", days=30)
        assert out == bars[:30]
        params = session.get.call_args[1]["params"]
        assert params["symbol"] == "AAPL" and "from" in params and "to" in params

    def test_empty_stable_history_does_not_try_v3(self):
        client, session = self._client(_resp(200, []))
        assert client.get_historical_prices("AAPL", days=30) == []
        assert client._endpoint_failures[f"{FMPClient.STABLE_URL}/historical-price-eod/full"] == 1
        assert session.get.call_count == 1

    def test_retired_wrapper_shape_is_not_a_valid_stable_history(self):
        client, session = self._client(
            _resp(200, {"historicalStockList": [{"symbol": "BRK.B", "historical": [{"close": 1}]}]})
        )
        assert client.get_historical_prices("BRK-B", days=2) == []
        assert session.get.call_count == 1

    def test_unrecognised_payload_returns_empty_and_counts_failures(self):
        client, session = self._client(_resp(200, {"weird": 1}))
        assert client.get_historical_prices("AAPL") == []
        assert client._endpoint_failures[f"{FMPClient.STABLE_URL}/historical-price-eod/full"] == 1
        assert session.get.call_count == 1

    def test_exception_is_recorded_and_returns_empty(self):
        client = FMPClient("k")
        client.session = MagicMock()
        client.session.get.side_effect = requests.exceptions.Timeout("slow")
        assert client.get_historical_prices("AAPL") == []
        assert all(v == 1 for v in client._endpoint_failures.values())

    def test_endpoint_disabled_after_threshold(self):
        client = FMPClient("k")
        stable = f"{FMPClient.STABLE_URL}/historical-price-eod/full"
        for _ in range(FMPClient._ENDPOINT_FAILURE_THRESHOLD):
            client._record_endpoint_failure(stable)
        assert stable in client._disabled_endpoints
        client.session = MagicMock()
        assert client.get_historical_prices("AAPL") == []
        assert client.session.get.call_count == 0


# --------------------------------------------------------------------------
# RSI
# --------------------------------------------------------------------------
class TestRSI:
    def test_insufficient_data(self):
        assert RSICalculator.calculate_rsi([1.0] * 14) is None

    def test_monotonic_rise_is_100(self):
        assert RSICalculator.calculate_rsi([float(i) for i in range(1, 30)]) == 100.0

    def test_monotonic_fall_is_0(self):
        assert RSICalculator.calculate_rsi([float(i) for i in range(30, 1, -1)]) == 0.0

    def test_known_mixed_series(self):
        prices = [44, 44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84]
        prices += [46.08, 45.89, 46.03, 45.61, 46.28, 46.28, 46.00, 46.03, 46.41, 46.22]
        rsi = RSICalculator.calculate_rsi(prices, period=14)
        assert 60 < rsi < 75


# --------------------------------------------------------------------------
# StockAnalyzer helpers
# --------------------------------------------------------------------------
class TestAnalyzerHelpers:
    def test_ffo_and_payout(self):
        cf = [{"netIncome": 60, "depreciationAndAmortization": 40, "dividendsPaid": -50}]
        assert StockAnalyzer.calculate_ffo(cf) == 100
        assert StockAnalyzer.calculate_ffo_payout_ratio(cf) == 50

    def test_ffo_missing_inputs(self):
        assert StockAnalyzer.calculate_ffo([]) is None
        assert StockAnalyzer.calculate_ffo([{"netIncome": 1}]) is None
        assert StockAnalyzer.calculate_ffo_payout_ratio([]) is None
        negative = [{"netIncome": -5, "depreciationAndAmortization": 1, "dividendsPaid": -1}]
        assert StockAnalyzer.calculate_ffo_payout_ratio(negative) is None
        zero_div = [{"netIncome": 5, "depreciationAndAmortization": 1, "dividendsPaid": 0}]
        assert StockAnalyzer.calculate_ffo_payout_ratio(zero_div) is None

    def test_cagr(self):
        assert StockAnalyzer.calculate_cagr(100, 121, 2) == pytest.approx(10.0)
        assert StockAnalyzer.calculate_cagr(0, 10, 2) is None
        assert StockAnalyzer.calculate_cagr(10, 10, 0) is None

    def test_positive_trend(self):
        assert StockAnalyzer.check_positive_trend([1, 2]) is False
        assert StockAnalyzer.check_positive_trend([5, 4, 3]) is False
        assert StockAnalyzer.check_positive_trend([1, 3, 2, 4]) is True  # one dip
        assert StockAnalyzer.check_positive_trend([1, 3, 2, 4, 3, 5]) is False  # two dips

    def test_revenue_and_eps_growth(self):
        stmts = [
            {"revenue": 133.1, "eps": 3.0},
            {"revenue": 121, "eps": 2.5},
            {"revenue": 110, "eps": 2.0},
            {"revenue": 100, "eps": 1.5},
        ]
        ok, cagr = StockAnalyzer.analyze_revenue_growth(stmts)
        assert ok and cagr == pytest.approx(10.0)
        ok, cagr = StockAnalyzer.analyze_eps_growth(stmts)
        assert ok and cagr == pytest.approx((2 ** (1 / 3) - 1) * 100)
        assert StockAnalyzer.analyze_revenue_growth(stmts[:3]) == (False, None)
        assert StockAnalyzer.analyze_eps_growth(stmts[:3]) == (False, None)

    def test_growth_with_nonpositive_base_has_no_cagr(self):
        stmts = [{"revenue": 5, "eps": 5}, {"revenue": 4, "eps": 4}] + [
            {"revenue": 3, "eps": 3},
            {"revenue": 0, "eps": 0},
        ]
        assert StockAnalyzer.analyze_revenue_growth(stmts)[1] is None
        assert StockAnalyzer.analyze_eps_growth(stmts)[1] is None

    def test_financial_health(self):
        healthy = StockAnalyzer.analyze_financial_health(
            [
                {
                    "totalDebt": 100,
                    "totalStockholdersEquity": 100,
                    "totalCurrentAssets": 200,
                    "totalCurrentLiabilities": 100,
                }
            ]
        )
        assert healthy == {"debt_to_equity": 1.0, "current_ratio": 2.0, "healthy": True}
        leveraged = StockAnalyzer.analyze_financial_health(
            [
                {
                    "totalDebt": 500,
                    "totalStockholdersEquity": 100,
                    "totalCurrentAssets": 200,
                    "totalCurrentLiabilities": 100,
                }
            ]
        )
        assert leveraged["healthy"] is False
        empty = StockAnalyzer.analyze_financial_health([{}])
        assert empty["debt_to_equity"] is None and empty["healthy"] is False
        assert StockAnalyzer.analyze_financial_health([])["healthy"] is False

    def test_quality_score(self):
        out = StockAnalyzer.calculate_quality_score(
            [{"roe": 0.20}], [{"revenue": 100, "netIncome": 15}]
        )
        assert out["roe"] == 0.20
        assert out["profit_margin"] == pytest.approx(15.0)
        assert out["quality_score"] == 100.0
        empty = StockAnalyzer.calculate_quality_score([], [])
        assert empty == {"roe": None, "profit_margin": None, "quality_score": 0}
        zero_rev = StockAnalyzer.calculate_quality_score([{}], [{"revenue": 0, "netIncome": 1}])
        assert zero_rev["profit_margin"] is None and zero_rev["quality_score"] == 0

    def test_stability_score(self):
        assert (
            StockAnalyzer.calculate_stability_score(
                {"is_stable": True, "is_growing": True, "years_of_growth": 5}
            )
            == 100
        )
        # Partial credit: 40 - 50*0.4 = 20, plus 2 years * 10
        assert (
            StockAnalyzer.calculate_stability_score({"volatility_pct": 50, "years_of_growth": 2})
            == 40.0
        )
        assert StockAnalyzer.calculate_stability_score({"volatility_pct": 150}) == 0
        assert StockAnalyzer.calculate_stability_score({}) == 0

    def test_revenue_trend(self):
        up = [{"revenue": r} for r in (140, 130, 120, 100)]
        res = StockAnalyzer.analyze_revenue_trend(up)
        assert res["is_uptrend"] is True and res["years_of_growth"] == 3
        assert res["cagr"] == pytest.approx(((140 / 100) ** (1 / 3) - 1) * 100, abs=0.01)
        down = [{"revenue": r} for r in (100, 110, 120, 130)]
        assert StockAnalyzer.analyze_revenue_trend(down)["is_uptrend"] is False
        assert StockAnalyzer.analyze_revenue_trend(up[:2])["cagr"] is None

    def test_earnings_trend(self):
        up = [{"netIncome": r} for r in (14, 13, 12, 10)]
        res = StockAnalyzer.analyze_earnings_trend(up)
        assert res["is_uptrend"] is True and res["years_of_growth"] == 3
        loss = [{"netIncome": r} for r in (14, -1, 12, 10)]
        res = StockAnalyzer.analyze_earnings_trend(loss)
        assert res == {"is_uptrend": False, "years_of_growth": 0, "cagr": None}
        assert StockAnalyzer.analyze_earnings_trend(up[:2])["is_uptrend"] is False


class TestDividendGrowthAndStability:
    def test_growth_empty_and_short_history(self):
        today = date(2026, 6, 1)
        assert StockAnalyzer.analyze_dividend_growth({}, as_of=today) == (None, False, None)
        recent = {"historical": [{"date": "2026-01-15", "dividend": 1.0}]}
        assert StockAnalyzer.analyze_dividend_growth(recent, as_of=today) == (None, False, None)

    def test_growth_ignores_future_bad_and_nonpositive(self):
        today = date(2026, 6, 1)
        hist = {
            "historical": [
                {"date": "2027-01-01", "dividend": 5.0},  # future
                {"date": "garbage", "dividend": 1.0},  # unparsable
                {"date": None, "dividend": 1.0},  # undated
                {"date": "2025-01-01", "dividend": 0},  # non-positive
            ]
        }
        assert StockAnalyzer.analyze_dividend_growth(hist, as_of=today) == (None, False, None)

    def test_growth_zero_edge_window_returns_none(self):
        today = date(2026, 6, 1)
        # Old record only, latest TTM window is empty.
        hist = {"historical": [{"date": "2020-01-01", "dividend": 1.0}]}
        assert StockAnalyzer.analyze_dividend_growth(hist, as_of=today) == (None, False, None)

    def test_growth_cagr_and_cut_detected(self):
        today = date(2026, 6, 1)
        steady = []
        for k, amt in enumerate([1.0, 1.1, 1.2, 1.3]):  # oldest -> newest window
            end = today - timedelta(days=365 * (3 - k))
            steady.append({"date": (end - timedelta(days=10)).isoformat(), "dividend": amt})
        cagr, consistent, latest = StockAnalyzer.analyze_dividend_growth(
            {"historical": steady}, as_of=today
        )
        assert latest == pytest.approx(1.3)
        assert cagr == pytest.approx(((1.3 / 1.0) ** (1 / 3) - 1) * 100)
        assert consistent is True
        cut = [dict(r) for r in steady]
        cut[1]["dividend"] = 0.5  # window 2 is -50% vs window 1 -> not consistent
        cut[0]["dividend"] = 1.0
        _, consistent, _ = StockAnalyzer.analyze_dividend_growth({"historical": cut}, as_of=today)
        assert consistent is False

    def test_stability_requires_enough_data(self):
        as_of = date(2026, 6, 1)
        assert StockAnalyzer.analyze_dividend_stability({}, as_of=as_of)["is_stable"] is False
        few = {"historical": [{"date": "2024-01-01", "dividend": 1}] * 3}
        assert StockAnalyzer.analyze_dividend_stability(few, as_of=as_of)["volatility_pct"] is None
        # Four records but only two complete years
        two_years = {
            "historical": [
                {"date": "2024-01-01", "dividend": 1},
                {"date": "2024-06-01", "dividend": 1},
                {"date": "2025-01-01", "dividend": 1},
                {"date": "2026-02-01", "dividend": 1},  # in-progress year, excluded
            ]
        }
        res = StockAnalyzer.analyze_dividend_stability(two_years, as_of=as_of)
        assert res["annual_dividends"] == {} and res["is_stable"] is False

    def test_stability_growing_and_stable(self):
        as_of = date(2026, 6, 1)
        recs = []
        for year, amt in ((2022, 1.0), (2023, 1.1), (2024, 1.2), (2025, 1.3)):
            recs.append({"date": f"{year}-03-01", "dividend": amt})
        res = StockAnalyzer.analyze_dividend_stability({"historical": recs}, as_of=as_of)
        assert res["is_stable"] is True and res["is_growing"] is True
        assert res["years_of_growth"] == 3
        assert res["volatility_pct"] == pytest.approx(round((0.3 / 1.15) * 100, 1))

    def test_stability_cut_resets_growth(self):
        as_of = date(2026, 6, 1)
        recs = [
            {"date": f"{y}-03-01", "dividend": a}
            for y, a in ((2022, 1.0), (2023, 1.2), (2024, 0.5), (2025, 0.55))
        ]
        res = StockAnalyzer.analyze_dividend_stability({"historical": recs}, as_of=as_of)
        assert res["years_of_growth"] == 1  # reset at the 2024 cut, then +1
        assert res["is_growing"] is False


class TestSustainabilityBranches:
    @staticmethod
    def _cf(div, ocf, capex, ni=0, da=0):
        return [
            {
                "dividendsPaid": div,
                "operatingCashFlow": ocf,
                "capitalExpenditure": capex,
                "netIncome": ni,
                "depreciationAndAmortization": da,
            }
        ]

    def test_no_cash_flows(self):
        res = StockAnalyzer.analyze_dividend_sustainability([], [])
        assert res["sustainable"] is False and res["fcf_status"] == "MISSING_DATA"

    def test_missing_dividend_field(self):
        res = StockAnalyzer.analyze_dividend_sustainability(
            [], [{"operatingCashFlow": 100, "capitalExpenditure": -10}]
        )
        assert res["fcf_status"] == "POSITIVE" and res["fcf_amount"] == 90
        assert "Dividend payment data is unavailable" in res["sustainability_note"]

    def test_zero_dividend(self):
        res = StockAnalyzer.analyze_dividend_sustainability([], self._cf(0, 100, -10))
        assert res["fcf_coverage_status"] == "NO_DIVIDEND" and res["sustainable"] is False

    @pytest.mark.parametrize(
        "ocf,capex,expected,status",
        [
            (50, -100, "NEGATIVE_FCF", "NEGATIVE"),
            (100, -100, "ZERO_FCF", "ZERO"),
            (130, -100, "INSUFFICIENT_FCF", "POSITIVE"),
            (140, -100, "AT_LIMIT", "POSITIVE"),
        ],
    )
    def test_fcf_coverage_levels(self, ocf, capex, expected, status):
        # dividends paid = 40
        res = StockAnalyzer.analyze_dividend_sustainability(
            [{"netIncome": 200}], self._cf(-40, ocf, capex)
        )
        assert res["fcf_coverage_status"] == expected
        assert res["fcf_status"] == status
        assert res["sustainable"] is False

    def test_covered_and_sustainable(self):
        res = StockAnalyzer.analyze_dividend_sustainability(
            [{"netIncome": 200}], self._cf(-40, 300, -100)
        )
        assert res["fcf_coverage_status"] == "COVERED"
        assert res["payout_ratio"] == pytest.approx(20.0)
        assert res["fcf_payout_ratio"] == pytest.approx(20.0)
        assert res["sustainable"] is True
        assert "below 80%" in res["sustainability_note"]

    def test_high_payout_not_sustainable(self):
        res = StockAnalyzer.analyze_dividend_sustainability(
            [{"netIncome": 45}], self._cf(-40, 300, -100)
        )
        assert res["payout_ratio"] >= 80 and res["sustainable"] is False
        assert "under-80%" in res["sustainability_note"]

    def test_missing_net_income_note(self):
        res = StockAnalyzer.analyze_dividend_sustainability([], self._cf(-40, 300, -100))
        assert res["payout_ratio"] is None
        assert "Earnings payout cannot be assessed" in res["sustainability_note"]

    def test_missing_fcf_inputs_note(self):
        res = StockAnalyzer.analyze_dividend_sustainability(
            [{"netIncome": 200}], [{"dividendsPaid": -40}]
        )
        assert res["fcf_coverage_status"] == "MISSING_DATA"
        assert "Free cash flow cannot be calculated" in res["sustainability_note"]

    def test_reit_uses_ffo(self):
        cf = self._cf(-50, 300, -100, ni=60, da=40)
        res = StockAnalyzer.analyze_dividend_sustainability([], cf, is_reit=True)
        assert res["sustainability_basis"] == "FFO"
        assert res["payout_ratio"] == pytest.approx(50.0)
        assert res["sustainable"] is True
        high = self._cf(-90, 300, -100, ni=60, da=40)
        res = StockAnalyzer.analyze_dividend_sustainability([], high, is_reit=True)
        assert res["sustainable"] is False and "80%" in res["sustainability_note"]

    def test_reit_without_ffo_data(self):
        cf = [{"dividendsPaid": -50, "operatingCashFlow": 300, "capitalExpenditure": -100}]
        res = StockAnalyzer.analyze_dividend_sustainability([], cf, is_reit=True)
        assert res["payout_ratio"] is None and res["sustainable"] is False
        assert "FFO coverage cannot be assessed" in res["sustainability_note"]

    def test_is_reit_detection(self):
        assert StockAnalyzer.is_reit({"isReit": True}) is True
        assert StockAnalyzer.is_reit({"industry": "REIT - Retail"}) is True
        assert StockAnalyzer.is_reit({"industry": "Non-REIT Services"}) is False
        assert StockAnalyzer.is_reit({"industry": None}) is False


# --------------------------------------------------------------------------
# Screening pipeline
# --------------------------------------------------------------------------
def _dividend_history(today=None):
    """~5.5 years of quarterly dividends growing ~8%/yr, newest within 30 days."""
    today = today or date.today()
    recs = []
    for n in range(22):
        d = today - timedelta(days=30 + 91 * n)
        amt = round(0.30 * (1.08 ** (-(n * 91 / 365))), 4)
        recs.append({"date": d.isoformat(), "dividend": amt})
    return {"historical": recs}


def _income(growing=True):
    revs = [130, 120, 110, 100] if growing else [100, 110, 120, 130]
    eps = [4.0, 3.6, 3.3, 3.0] if growing else [3.0, 3.3, 3.6, 4.0]
    return [
        {"revenue": r * 1e9, "eps": e, "netIncome": r * 1e8, "date": f"{2025 - i}"}
        for i, (r, e) in enumerate(zip(revs, eps))
    ]


def _falling_prices(n=30):
    # newest first; strictly declining toward the present -> RSI 0
    return [{"close": 100 - (n - i)} for i in range(n)]


class FakeFMP:
    """Stands in for FMPClient inside screen_value_dividend_stocks."""

    instances = []

    def __init__(self, api_key):
        self.api_key = api_key
        self.rate_limit_reached = False
        self.trip_on = None
        self.screen_args = None
        self.cfg = FakeFMP.cfg
        FakeFMP.instances.append(self)

    def _maybe_trip(self, name):
        if self.trip_on == name:
            self.rate_limit_reached = True

    def screen_stocks(self, **kwargs):
        self.screen_args = kwargs
        return [dict(c) for c in self.cfg["candidates"]]

    def _get(self, endpoint, params=None):
        kind = endpoint.split("/")[0]
        sym = endpoint.split("/")[-1]
        if kind == "quote":
            return self.cfg.get("quotes", {}).get(sym)
        if kind == "ratios":
            return self.cfg.get("ratios", {}).get(sym)
        return None

    def get_company_profile(self, symbol):
        self._maybe_trip("profile")
        return self.cfg.get("profiles", {}).get(symbol)

    def get_income_statement(self, symbol, limit=5):
        self._maybe_trip("income")
        return self.cfg["income"].get(symbol, [])

    def get_balance_sheet(self, symbol, limit=5):
        self._maybe_trip("balance")
        return [
            {
                "totalDebt": 50,
                "totalStockholdersEquity": 100,
                "totalCurrentAssets": 200,
                "totalCurrentLiabilities": 100,
            }
        ]

    def get_cash_flow(self, symbol, limit=5):
        self._maybe_trip("cash")
        return [
            {
                "dividendsPaid": -1e9,
                "operatingCashFlow": 9e9,
                "capitalExpenditure": -1e9,
                "netIncome": 1e10,
            }
        ]

    def get_key_metrics(self, symbol, limit=5):
        self._maybe_trip("metrics")
        return [{"roe": 0.15}]

    def get_dividend_history(self, symbol):
        self._maybe_trip("dividend")
        return self.cfg["dividends"].get(symbol, {})

    def get_historical_prices(self, symbol, days=30):
        self._maybe_trip("prices")
        return self.cfg["prices"].get(symbol, [])


@pytest.fixture
def fake_fmp(monkeypatch):
    FakeFMP.instances = []
    FakeFMP.cfg = {}
    monkeypatch.setattr(mod, "FMPClient", FakeFMP)
    return FakeFMP


def _good_candidate(symbol="GOOD", price=20.0, **extra):
    c = {"symbol": symbol, "name": f"{symbol} Corp", "price": price, "marketCap": 5e10}
    c.update(extra)
    return c


class TestScreeningPipeline:
    def test_fmp_only_happy_path_builds_full_result(self, fake_fmp, capsys):
        fake_fmp.cfg = {
            "candidates": [_good_candidate(pe=12.0, priceToBook=1.4)],
            "income": {"GOOD": _income()},
            "dividends": {"GOOD": _dividend_history()},
            "prices": {"GOOD": _falling_prices()},
            "profiles": {"GOOD": {"sector": "Utilities", "industry": "Regulated Electric"}},
        }
        results = mod.screen_value_dividend_stocks("key", top_n=5, max_candidates=42)
        client = fake_fmp.instances[0]
        assert client.api_key == "key"  # pragma: allowlist secret
        assert client.screen_args["max_candidates"] == 42
        assert len(results) == 1
        r = results[0]
        assert r["symbol"] == "GOOD" and r["company_name"] == "GOOD Corp"
        assert r["sector"] == "Utilities"
        assert r["rsi"] == 0.0
        assert r["dividend_yield"] > 3.0
        assert r["dividend_cagr_3y"] >= 4.0
        assert r["pe_ratio"] == 12.0 and r["pb_ratio"] == 1.4
        assert r["revenue_uptrend"] is True and r["earnings_uptrend"] is True
        assert r["dividend_sustainable"] is True and r["sustainability_bonus"] == 10
        assert r["financially_healthy"] is True
        assert r["roe"] == 15.0
        assert r["composite_score"] > 40
        err = capsys.readouterr().err
        assert "Found 1 initial candidates" in err
        assert "Found 1 oversold stocks" in err

    def test_no_candidates_returns_empty(self, fake_fmp, capsys):
        fake_fmp.cfg = {"candidates": []}
        assert mod.screen_value_dividend_stocks("key") == []
        assert "No stocks found matching initial criteria" in capsys.readouterr().err

    @pytest.mark.parametrize(
        "cfg_patch,message",
        [
            ({"prices": {"GOOD": _falling_prices(10)}}, "RSI calculation failed"),
            ({"income": {"GOOD": _income()[:3]}}, "Insufficient income statement"),
            ({"dividends": {"GOOD": {}}}, "Dividend CAGR < 4%"),
            ({"income": {"GOOD": _income(growing=False)}}, "Revenue trend not positive"),
        ],
    )
    def test_rejections(self, fake_fmp, capsys, cfg_patch, message):
        cfg = {
            "candidates": [_good_candidate(sector="Utilities")],
            "income": {"GOOD": _income()},
            "dividends": {"GOOD": _dividend_history()},
            "prices": {"GOOD": _falling_prices()},
        }
        cfg.update(cfg_patch)
        fake_fmp.cfg = cfg
        assert mod.screen_value_dividend_stocks("key") == []
        assert message in capsys.readouterr().err

    def test_low_actual_yield_rejected(self, fake_fmp, capsys):
        fake_fmp.cfg = {
            "candidates": [_good_candidate(price=500.0, sector="Utilities")],
            "income": {"GOOD": _income()},
            "dividends": {"GOOD": _dividend_history()},
            "prices": {"GOOD": _falling_prices()},
        }
        assert mod.screen_value_dividend_stocks("key") == []
        assert "< 3.0%" in capsys.readouterr().err

    def test_missing_price_rejected(self, fake_fmp, capsys):
        fake_fmp.cfg = {
            "candidates": [_good_candidate(price=0, sector="Utilities")],
            "income": {"GOOD": _income()},
            "dividends": {"GOOD": _dividend_history()},
            "prices": {"GOOD": _falling_prices()},
        }
        assert mod.screen_value_dividend_stocks("key") == []
        assert "Cannot calculate dividend yield" in capsys.readouterr().err

    def test_eps_trend_not_positive_rejected(self, fake_fmp, capsys):
        inc = _income()
        for stmt, eps in zip(inc, (3.0, 3.3, 3.6, 4.0)):
            stmt["eps"] = eps  # revenue grows, EPS falls
        fake_fmp.cfg = {
            "candidates": [_good_candidate(sector="Utilities")],
            "income": {"GOOD": inc},
            "dividends": {"GOOD": _dividend_history()},
            "prices": {"GOOD": _falling_prices()},
        }
        assert mod.screen_value_dividend_stocks("key") == []
        assert "EPS trend not positive" in capsys.readouterr().err

    def test_volatile_dividend_rejected(self, fake_fmp, capsys):
        today = date.today()
        hist = _dividend_history()["historical"]
        # Add a special distribution in a complete prior year -> >100% volatility.
        hist.append({"date": date(today.year - 2, 1, 5).isoformat(), "dividend": 40.0})
        fake_fmp.cfg = {
            "candidates": [_good_candidate(sector="Utilities")],
            "income": {"GOOD": _income()},
            "dividends": {"GOOD": {"historical": hist}},
            "prices": {"GOOD": _falling_prices()},
        }
        assert mod.screen_value_dividend_stocks("key") == []
        assert "Dividend too volatile" in capsys.readouterr().err

    def test_profile_fetched_when_sector_missing(self, fake_fmp):
        fake_fmp.cfg = {
            "candidates": [_good_candidate()],
            "income": {"GOOD": _income()},
            "dividends": {"GOOD": _dividend_history()},
            "prices": {"GOOD": _falling_prices()},
            "profiles": {"GOOD": {"sector": "Financials", "industry": "Banks"}},
        }
        results = mod.screen_value_dividend_stocks("key")
        assert results[0]["sector"] == "Financials"

    def test_non_oversold_sorted_by_rsi_and_limited(self, fake_fmp, capsys):
        # Alternating-with-uptrend prices give RSI well above 40.
        rising = [{"close": 100 - i} for i in range(30)]  # newest first, rising to present
        base = 50.0
        series = []
        for i in range(30):
            base += 1.0 if i % 3 else -0.5
            series.append(base)
        mixed = [{"close": p} for p in reversed(series)]
        fake_fmp.cfg = {
            "candidates": [
                _good_candidate("AAA", sector="Utilities"),
                _good_candidate("BBB", sector="Utilities"),
            ],
            "income": {"AAA": _income(), "BBB": _income()},
            "dividends": {"AAA": _dividend_history(), "BBB": _dividend_history()},
            "prices": {"AAA": rising, "BBB": mixed},
        }
        results = mod.screen_value_dividend_stocks("key", top_n=1)
        assert "No oversold stocks found" in capsys.readouterr().err
        assert len(results) == 1
        assert results[0]["rsi"] > 40
        # Lowest RSI first: BBB (mixed) has lower RSI than a pure uptrend (100).
        assert results[0]["symbol"] == "BBB"

    def test_oversold_sorted_by_composite_and_top_n(self, fake_fmp):
        low_quality = [dict(s, netIncome=s["netIncome"] / 20) for s in _income()]
        fake_fmp.cfg = {
            "candidates": [
                _good_candidate("LOWQ", sector="Utilities"),
                _good_candidate("HIGHQ", sector="Utilities"),
            ],
            "income": {"LOWQ": low_quality, "HIGHQ": _income()},
            "dividends": {"LOWQ": _dividend_history(), "HIGHQ": _dividend_history()},
            "prices": {"LOWQ": _falling_prices(), "HIGHQ": _falling_prices()},
        }
        results = mod.screen_value_dividend_stocks("key", top_n=5)
        assert [r["symbol"] for r in results][0] == "HIGHQ"
        assert results[0]["composite_score"] >= results[1]["composite_score"]
        assert len(mod.screen_value_dividend_stocks("key", top_n=1)) == 1

    @pytest.mark.parametrize(
        "stage", ["income", "balance", "cash", "metrics", "dividend", "prices", "profile"]
    )
    def test_rate_limit_mid_analysis_stops_with_partial_results(self, fake_fmp, stage, capsys):
        # Candidate 1 trips the limit at `stage`; candidate 2 must never be analyzed.
        fake_fmp.cfg = {
            "candidates": [_good_candidate("AAA"), _good_candidate("BBB")],
            "income": {"AAA": _income(), "BBB": _income()},
            "dividends": {"AAA": _dividend_history(), "BBB": _dividend_history()},
            "prices": {"AAA": _falling_prices(), "BBB": _falling_prices()},
            "profiles": {"AAA": {"sector": "Utilities"}, "BBB": {"sector": "Utilities"}},
        }
        orig_init = FakeFMP.__init__

        def init(self, api_key):
            orig_init(self, api_key)
            self.trip_on = stage

        FakeFMP.__init__ = init
        try:
            results = mod.screen_value_dividend_stocks("key")
        finally:
            FakeFMP.__init__ = orig_init
        assert results == []
        err = capsys.readouterr().err
        assert "Analyzing BBB" not in err

    def test_rate_limit_message_when_flag_already_set(self, fake_fmp, capsys):
        fake_fmp.cfg = {"candidates": [_good_candidate("AAA")]}
        orig_screen = FakeFMP.screen_stocks

        def screen(self, **kwargs):
            out = orig_screen(self, **kwargs)
            self.rate_limit_reached = True
            return out

        FakeFMP.screen_stocks = screen
        try:
            assert mod.screen_value_dividend_stocks("key") == []
        finally:
            FakeFMP.screen_stocks = orig_screen
        assert "API rate limit reached after analyzing 0 stocks" in capsys.readouterr().err


class TestFinvizStage:
    def test_finviz_symbols_enriched_with_quote_profile_ratios(self, fake_fmp, capsys):
        fake_fmp.cfg = {
            "quotes": {
                "GOOD": [{"symbol": "GOOD", "name": "Good Co", "price": 20.0, "marketCap": 1e10}],
                "NOQUOTE": None,
            },
            "ratios": {"GOOD": [{"priceToEarningsRatio": 11.0, "priceToBookRatio": 1.2}]},
            "profiles": {"GOOD": {"sector": "Utilities", "industry": "Power", "companyName": "G"}},
            "income": {"GOOD": _income()},
            "dividends": {"GOOD": _dividend_history()},
            "prices": {"GOOD": _falling_prices()},
        }
        results = mod.screen_value_dividend_stocks("key", finviz_symbols={"GOOD", "NOQUOTE"})
        assert fake_fmp.instances[0].screen_args is None  # FMP screener not used
        assert len(results) == 1
        r = results[0]
        assert r["sector"] == "Utilities"
        assert r["pe_ratio"] == 11.0 and r["pb_ratio"] == 1.2
        err = capsys.readouterr().err
        assert "Using FINVIZ pre-screened symbols (2 stocks)" in err
        assert "Retrieved quote and profile data for 1 symbols" in err

    def test_finviz_stage_stops_on_rate_limit(self, fake_fmp, capsys):
        fake_fmp.cfg = {
            "quotes": {"A": [{"symbol": "A", "price": 1.0}]},
            "profiles": {},
        }
        orig = FakeFMP.get_company_profile

        def profile(self, symbol):
            self.rate_limit_reached = True
            return None

        FakeFMP.get_company_profile = profile
        try:
            results = mod.screen_value_dividend_stocks("key", finviz_symbols={"A"})
        finally:
            FakeFMP.get_company_profile = orig
        assert results == []
        err = capsys.readouterr().err
        assert "FMP rate limit reached while fetching quotes" in err


# --------------------------------------------------------------------------
# main() / CLI
# --------------------------------------------------------------------------
class TestMain:
    def _run(self, monkeypatch, argv):
        monkeypatch.setattr("sys.argv", ["screen_dividend_stocks.py", *argv])
        return mod.main()

    def test_missing_fmp_key_exits_1(self, monkeypatch, capsys):
        monkeypatch.delenv("FMP_API_KEY", raising=False)
        with pytest.raises(SystemExit) as exc:
            self._run(monkeypatch, [])
        assert exc.value.code == 1
        assert "FMP API key required" in capsys.readouterr().err

    def test_use_finviz_without_key_exits_1(self, monkeypatch, capsys):
        monkeypatch.setenv("FMP_API_KEY", "fmp")
        monkeypatch.delenv("FINVIZ_API_KEY", raising=False)
        with pytest.raises(SystemExit) as exc:
            self._run(monkeypatch, ["--use-finviz"])
        assert exc.value.code == 1
        assert "FINVIZ API key required" in capsys.readouterr().err

    def test_finviz_returns_nothing_exits_1(self, monkeypatch, capsys):
        monkeypatch.setenv("FMP_API_KEY", "fmp")
        monkeypatch.setattr(FINVIZClient, "screen_stocks", lambda self: set())
        with pytest.raises(SystemExit) as exc:
            self._run(monkeypatch, ["--use-finviz", "--finviz-api-key", "fv"])
        assert exc.value.code == 1
        assert "pre-screening failed" in capsys.readouterr().err

    def test_no_results_exits_1_without_writing(self, monkeypatch, tmp_path, capsys):
        out = tmp_path / "res.json"
        monkeypatch.setenv("FMP_API_KEY", "fmp")
        monkeypatch.setattr(mod, "screen_value_dividend_stocks", lambda *a, **k: [])
        with pytest.raises(SystemExit) as exc:
            self._run(monkeypatch, ["--output", str(out)])
        assert exc.value.code == 1
        assert not out.exists()
        assert "No stocks found matching all criteria" in capsys.readouterr().err

    def test_fmp_only_writes_json_report(self, monkeypatch, tmp_path):
        out = tmp_path / "nested" / "res.json"
        captured = {}

        def fake_screen(key, top_n, finviz_symbols, max_candidates):
            captured.update(
                key=key, top_n=top_n, finviz=finviz_symbols, max_candidates=max_candidates
            )
            return [{"symbol": "AAA", "composite_score": 55.0}]

        monkeypatch.setenv("FMP_API_KEY", "env-fmp")
        monkeypatch.setattr(mod, "screen_value_dividend_stocks", fake_screen)
        self._run(monkeypatch, ["--output", str(out), "--top", "7", "--max-candidates", "9"])
        assert captured == {"key": "env-fmp", "top_n": 7, "finviz": None, "max_candidates": 9}
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["metadata"]["total_results"] == 1
        assert data["metadata"]["criteria"]["dividend_yield_min"] == 3.0
        assert data["metadata"]["generated_at"].endswith("Z")
        assert data["stocks"] == [{"symbol": "AAA", "composite_score": 55.0}]

    def test_finviz_two_stage_passes_symbols_and_cli_key_wins(self, monkeypatch, tmp_path):
        out = tmp_path / "res.json"
        seen = {}

        def fake_finviz_init(self, api_key):
            seen["finviz_key"] = api_key

        def fake_screen(key, top_n, finviz_symbols, max_candidates):
            seen["fmp_key"] = key
            seen["symbols"] = finviz_symbols
            return [{"symbol": "ZZZ", "composite_score": 1.0}]

        monkeypatch.setenv("FMP_API_KEY", "env-fmp")
        monkeypatch.setenv("FINVIZ_API_KEY", "env-fv")
        monkeypatch.setattr(FINVIZClient, "__init__", fake_finviz_init)
        monkeypatch.setattr(FINVIZClient, "screen_stocks", lambda self: {"ZZZ", "YYY"})
        monkeypatch.setattr(mod, "screen_value_dividend_stocks", fake_screen)
        self._run(
            monkeypatch,
            ["--use-finviz", "--fmp-api-key", "cli-fmp", "--finviz-api-key", "cli-fv"]
            + ["--output", str(out)],
        )
        assert seen == {
            "finviz_key": "cli-fv",
            "fmp_key": "cli-fmp",
            "symbols": {"ZZZ", "YYY"},
        }
        assert json.loads(out.read_text(encoding="utf-8"))["stocks"][0]["symbol"] == "ZZZ"
