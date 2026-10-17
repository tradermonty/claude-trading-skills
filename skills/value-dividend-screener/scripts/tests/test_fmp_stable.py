"""FMP /stable migration for value-dividend-screener.

The retired v3 endpoints 403 for keys issued after 2025-08-31. FMPClient._get
now routes the legacy v3 path-style endpoint strings to their /stable
query-style equivalents (stable-only) and normalizes the responses back
to the v3 shapes callers expect:

- historical-price-full/stock_dividend/{sym} -> dividends?symbol= (flat list
  wrapped as {"historical": [...]})
- key-metrics: roe <- returnOnEquity
- cash-flow-statement: dividendsPaid <- netDividendsPaid

screen_stocks() also replaces the v3 server-side yield/P-E/P-B filter (which
company-screener cannot do) with client-side gates.
"""

from datetime import date
from unittest.mock import MagicMock

from screen_dividend_stocks import FMPClient, StockAnalyzer


def _quarterly(annual_by_year):
    """Build quarterly dividend records: {year: annual_amount} -> 4 records/year."""
    recs = []
    for year, annual in annual_by_year.items():
        for month in ("02", "05", "08", "11"):
            recs.append({"date": f"{year}-{month}-15", "dividend": round(annual / 4, 6)})
    return recs


def _resp(status_code, payload):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = payload
    return resp


def _client(router):
    client = FMPClient("test_key")
    session = MagicMock()
    session.get.side_effect = router
    client.session = session
    return client, session


class TestGetRouting:
    def test_statement_path_to_stable_query(self):
        def router(url, params=None, timeout=None):
            return _resp(200, [{"symbol": "AAPL", "revenue": 1, "eps": 2}])

        client, session = _client(router)
        client.get_income_statement("AAPL", limit=5)
        call = session.get.call_args_list[0]
        assert call[0][0].endswith("/stable/income-statement")
        assert call[1]["params"]["symbol"] == "AAPL"
        assert call[1]["params"]["limit"] == 5

    def test_screener_to_company_screener(self):
        client, session = _client(lambda *a, **k: _resp(200, [{"symbol": "X"}]))
        client._get("stock-screener", {"marketCapMoreThan": 1})
        assert session.get.call_args_list[0][0][0].endswith("/stable/company-screener")

    def test_dividends_normalized_to_historical(self):
        flat = [{"symbol": "AAPL", "date": "2026-05-11", "dividend": 0.27}]
        client, _ = _client(lambda *a, **k: _resp(200, flat))
        result = client.get_dividend_history("AAPL")
        assert isinstance(result, dict)
        assert result["historical"] == flat

    def test_key_metrics_roe_alias(self):
        client, _ = _client(lambda *a, **k: _resp(200, [{"returnOnEquity": 1.52}]))
        metrics = client.get_key_metrics("AAPL", limit=1)
        assert metrics[0]["roe"] == 1.52

    def test_cashflow_dividends_paid_alias(self):
        client, _ = _client(lambda *a, **k: _resp(200, [{"netDividendsPaid": -15_000_000}]))
        cf = client.get_cash_flow("AAPL", limit=1)
        assert cf[0]["dividendsPaid"] == -15_000_000

    def test_historical_prices_flat_list_stable(self):
        # /stable/historical-price-eod/full returns a flat list (most-recent-first).
        bars = [{"date": "2026-05-19", "close": 100.0}, {"date": "2026-05-18", "close": 99.0}]

        def router(url, params=None, timeout=None):
            assert url.endswith("/stable/historical-price-eod/full")
            assert "from" in (params or {}) and "to" in (params or {})
            return _resp(200, bars)

        client, _ = _client(router)
        result = client.get_historical_prices("AAPL", days=30)
        assert result == bars  # flat list returned directly, close field intact

    def test_stable_failure_never_tries_retired_v3(self):
        def router(url, params=None, timeout=None):
            assert "/api/v3/" not in url
            return _resp(403, {})

        client, session = _client(router)
        assert client.get_company_profile("AAPL") is None
        assert session.get.call_count == 1


class TestDividendGrowthTTM:
    """Dividend growth uses trailing-12m windows, not partial calendar years."""

    def test_ttm_cagr_ignores_partial_and_future(self):
        # ~10%/yr grower paying continuously through the as_of date. _quarterly
        # emits Feb/May/Aug/Nov; for 2026 the Aug/Nov payments are future-dated
        # (after as_of) and must be excluded, as must the explicit future record.
        recs = _quarterly({2022: 1.0, 2023: 1.1, 2024: 1.21, 2025: 1.331, 2026: 1.4641})
        recs.append({"date": "2026-08-15", "dividend": 99.0})  # future-dated -> ignored

        cagr, consistent, latest = StockAnalyzer.analyze_dividend_growth(
            {"historical": recs}, years_back=3, as_of=date(2026, 5, 20)
        )
        assert cagr is not None and 5 < cagr < 15  # ~10%, not the broken negative
        assert consistent is True
        assert latest < 5  # future 99.0 excluded from the trailing window

    def test_partial_year_would_break_calendar_sum(self):
        # Sanity: the same data summed by calendar year (old method) goes negative.
        by_year = {"2023": 1.1, "2024": 1.21, "2025": 1.331, "2026": 1.4641 / 4}
        years = sorted(by_year)[-4:]
        vals = [by_year[y] for y in years]
        old_cagr = StockAnalyzer.calculate_cagr(vals[0], vals[-1], 3)
        assert old_cagr is not None and old_cagr < 0  # the bug the TTM fix avoids


class TestDividendStabilityExcludesPartialYear:
    def test_flat_dividend_is_stable_despite_partial_current_year(self):
        recs = _quarterly({y: 1.0 for y in range(2022, 2026)})  # flat $1/yr complete
        recs.append({"date": "2026-02-15", "dividend": 0.25})  # partial current year
        recs.append({"date": "2026-09-15", "dividend": 0.25})  # future-dated

        result = StockAnalyzer.analyze_dividend_stability(
            {"historical": recs}, as_of=date(2026, 5, 20)
        )
        assert "2026" not in result["annual_dividends"]  # current year excluded
        assert result["volatility_pct"] < 5  # flat complete years -> low volatility
        assert result["is_stable"] is True


class TestScreenStocksClientSideGates:
    def test_yield_pe_pb_gates_exclude_funds(self):
        # HIYLD passes yield+P/E+P/B; LOWYLD fails yield; HIPE fails P/E;
        # a high-yield ETF must be excluded before any ratios call.
        universe = [
            {"symbol": "HIYLD", "price": 100.0, "lastAnnualDividend": 5.0, "marketCap": 50e9},
            {"symbol": "LOWYLD", "price": 100.0, "lastAnnualDividend": 1.0, "marketCap": 80e9},
            {"symbol": "HIPE", "price": 100.0, "lastAnnualDividend": 4.0, "marketCap": 40e9},
            {
                "symbol": "BOND",
                "price": 100.0,
                "lastAnnualDividend": 6.0,
                "marketCap": 90e9,
                "isEtf": True,
            },  # high-yield fund -> excluded
        ]
        ratios = {
            "HIYLD": [{"priceToEarningsRatio": 12.0, "priceToBookRatio": 1.5}],
            "HIPE": [{"priceToEarningsRatio": 40.0, "priceToBookRatio": 1.0}],  # P/E too high
        }

        def router(url, params=None, timeout=None):
            if url.endswith("/company-screener"):
                return _resp(200, universe)
            if url.endswith("/ratios"):
                sym = (params or {}).get("symbol")
                assert sym != "BOND", "ETF should never reach the ratios call"
                return _resp(200, ratios.get(sym, []))
            raise AssertionError(f"unexpected {url}")

        client, _ = _client(router)
        survivors = client.screen_stocks(
            dividend_yield_min=3.0, pe_max=20, pb_max=2, max_candidates=300
        )

        assert [s["symbol"] for s in survivors] == ["HIYLD"]
        assert survivors[0]["pe"] == 12.0  # attached for the report
        assert survivors[0]["priceToBook"] == 1.5

    def test_prioritizes_by_market_cap(self):
        # Two qualifying names; the cap of 1 must keep the larger-cap one.
        universe = [
            {"symbol": "SMALL", "price": 100.0, "lastAnnualDividend": 5.0, "marketCap": 5e9},
            {"symbol": "BIG", "price": 100.0, "lastAnnualDividend": 4.0, "marketCap": 200e9},
        ]

        def router(url, params=None, timeout=None):
            if url.endswith("/company-screener"):
                return _resp(200, universe)
            return _resp(200, [{"priceToEarningsRatio": 10.0, "priceToBookRatio": 1.0}])

        client, _ = _client(router)
        survivors = client.screen_stocks(
            dividend_yield_min=3.0, pe_max=20, pb_max=2, max_candidates=1
        )
        assert [s["symbol"] for s in survivors] == ["BIG"]  # market-cap priority

    def test_cap_limits_ratios_calls(self):
        universe = [
            {"symbol": f"S{i}", "price": 100.0, "lastAnnualDividend": 5.0} for i in range(10)
        ]

        def router(url, params=None, timeout=None):
            if url.endswith("/company-screener"):
                return _resp(200, universe)
            return _resp(200, [{"priceToEarningsRatio": 10.0, "priceToBookRatio": 1.0}])

        client, session = _client(router)
        client.screen_stocks(dividend_yield_min=3.0, pe_max=20, pb_max=2, max_candidates=3)

        ratios_calls = [c for c in session.get.call_args_list if c[0][0].endswith("/ratios")]
        assert len(ratios_calls) == 3  # capped, not 10
