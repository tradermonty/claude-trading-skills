#!/usr/bin/env python3
"""Coverage tests for the CANSLIM screening pipeline (Issue #293).

Covers the FMP client (fake HTTP session), the Finviz client (fake session),
the institutional endpoint probe, scorer, report generator and the
screen_canslim CLI/main path. No network access and no dependence on the
wall clock: dates are injected or patched.
"""

import json
import os
import runpy
import sys
import types
from datetime import date, datetime, timedelta, timezone

import check_institutional_endpoint as cie
import finviz_stock_client as fsc
import fmp_client
import pytest
import report_generator as rg
import requests
import scorer
import screen_canslim as sc
from fmp_client import FMPClient

TEST_KEY = "unit-test-key-123"  # pragma: allowlist secret


# ---------------------------------------------------------------- helpers


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json = json_data
        self.text = text

    def json(self):
        return self._json


class FakeSession:
    """Routes GET requests through ``handler(url, params)``."""

    def __init__(self, handler):
        self.handler = handler
        self.calls = []
        self.headers = {}

    def get(self, url, params=None, timeout=30):
        self.calls.append((url, dict(params or {})))
        result = self.handler(url, dict(params or {}))
        if isinstance(result, Exception):
            raise result
        return result

    def urls(self):
        return [c[0] for c in self.calls]


@pytest.fixture
def sleeps(monkeypatch):
    """Freeze fmp_client's clock at t=1000 and record sleeps instead of waiting."""
    recorded = []
    fake_time = types.SimpleNamespace(time=lambda: 1000.0, sleep=recorded.append)
    monkeypatch.setattr(fmp_client, "time", fake_time)
    return recorded


@pytest.fixture
def make_client(monkeypatch, sleeps):
    monkeypatch.delenv("FMP_API_KEY", raising=False)

    def _make(handler, key=TEST_KEY):
        client = FMPClient(api_key=key)
        client.session = FakeSession(handler)
        return client

    return _make


STABLE = "https://financialmodelingprep.com/stable"
V3 = "https://financialmodelingprep.com/api/v3"


def ok(data):
    return FakeResponse(200, data)


def fail(status=500, text="boom"):
    return FakeResponse(status, None, text)


# ---------------------------------------------------------------- FMPClient basics


class TestFMPClientInit:
    def test_missing_key_raises(self, monkeypatch):
        monkeypatch.delenv("FMP_API_KEY", raising=False)
        with pytest.raises(ValueError, match="FMP API key required"):
            FMPClient()

    def test_whitespace_only_key_raises(self, monkeypatch):
        monkeypatch.setenv("FMP_API_KEY", "   ")
        with pytest.raises(ValueError):
            FMPClient()

    def test_env_key_is_stripped_and_sent_as_header(self, monkeypatch):
        monkeypatch.setenv("FMP_API_KEY", f"  {TEST_KEY}\n")
        client = FMPClient()
        assert client.api_key == TEST_KEY
        assert client.session.headers["apikey"] == TEST_KEY

    def test_explicit_key_wins_over_env(self, monkeypatch):
        monkeypatch.setenv("FMP_API_KEY", "env-key")  # pragma: allowlist secret
        assert FMPClient(api_key="arg-key").api_key == "arg-key"  # pragma: allowlist secret


class TestRateLimitedGet:
    def test_success_returns_json_and_resets_retry_count(self, make_client):
        client = make_client(lambda url, p: ok([{"a": 1}]))
        client.retry_count = 1
        assert client._rate_limited_get("http://x/y", {"q": 1}) == [{"a": 1}]
        assert client.retry_count == 0
        assert client.session.calls == [("http://x/y", {"q": 1})]

    def test_second_call_waits_for_rate_limit(self, make_client, sleeps):
        client = make_client(lambda url, p: ok({"ok": True}))
        client._rate_limited_get("http://x")
        assert sleeps == []
        client._rate_limited_get("http://x")
        assert sleeps == [pytest.approx(FMPClient.RATE_LIMIT_DELAY)]

    def test_429_then_success_waits_60s(self, make_client, sleeps, capsys):
        responses = [fail(429, "slow down"), ok({"v": 1})]
        client = make_client(lambda url, p: responses.pop(0))
        assert client._rate_limited_get("http://x") == {"v": 1}
        assert 60 in sleeps
        assert "Waiting 60 seconds" in capsys.readouterr().err
        assert client.rate_limit_reached is False

    def test_repeated_429_sets_rate_limit_flag_and_short_circuits(self, make_client, capsys):
        client = make_client(lambda url, p: fail(429))
        assert client._rate_limited_get("http://x") is None
        assert client.rate_limit_reached is True
        assert "Daily API rate limit reached" in capsys.readouterr().err
        n_calls = len(client.session.calls)
        assert client._rate_limited_get("http://x") is None
        assert len(client.session.calls) == n_calls  # no further HTTP once flagged

    def test_http_error_prints_redacted_message(self, make_client, capsys):
        client = make_client(lambda url, p: fail(403, f"bad key {TEST_KEY} apikey=zzz"))
        assert client._rate_limited_get("http://x") is None
        err = capsys.readouterr().err
        assert "API request failed: 403" in err
        assert TEST_KEY not in err
        assert "***REDACTED***" in err

    def test_quiet_suppresses_http_error(self, make_client, capsys):
        client = make_client(lambda url, p: fail(404))
        assert client._rate_limited_get("http://x", quiet=True) is None
        assert capsys.readouterr().err == ""

    def test_request_exception_is_swallowed_and_redacted(self, make_client, capsys):
        exc = requests.exceptions.ConnectionError(f"https://h/p?apikey={TEST_KEY}&x=1")
        client = make_client(lambda url, p: exc)
        assert client._rate_limited_get("http://x") is None
        err = capsys.readouterr().err
        assert "Request exception" in err
        assert TEST_KEY not in err


class TestRedaction:
    def test_redact_key_masks_query_params(self):
        assert fmp_client._redact_key("u?apikey=SECRET&x=1") == "u?apikey=REDACTED&x=1"
        assert fmp_client._redact_key("u?x=1&API_KEY=SECRET") == "u?x=1&API_KEY=REDACTED"

    def test_redact_secret_masks_raw_and_url_encoded_key(self, make_client):
        key = "ab/cd+ef gh"  # pragma: allowlist secret
        client = make_client(lambda url, p: ok({}), key=key)
        text = "raw ab/cd+ef gh enc ab%2Fcd%2Bef%20gh plus ab%2fcd%2bef+gh"
        out = client._redact_secret(text)
        assert "ab/cd" not in out
        assert "%2F" not in out and "%2f" not in out
        assert out.count("***REDACTED***") == 3


class TestEtToday:
    def test_explicit_aware_now_converted_to_new_york(self):
        # 03:00 UTC on 2025-07-01 is still 2025-06-30 in New York (EDT, UTC-4)
        now = datetime(2025, 7, 1, 3, 0, tzinfo=timezone.utc)
        assert fmp_client._et_today(now) == date(2025, 6, 30)

    def test_naive_now_rejected(self):
        with pytest.raises(ValueError, match="timezone-aware"):
            fmp_client._et_today(datetime(2025, 7, 1, 3, 0))

    def test_missing_tzdata_raises_runtime_error(self, monkeypatch):
        def boom(name):
            raise fmp_client.ZoneInfoNotFoundError(name)

        monkeypatch.setattr(fmp_client, "ZoneInfo", boom)
        with pytest.raises(RuntimeError, match="tzdata"):
            fmp_client._et_today()

    def test_default_uses_current_instant_in_new_york(self, monkeypatch):
        class FixedDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime(2025, 1, 2, 1, 0, tzinfo=timezone.utc).astimezone(tz)

        monkeypatch.setattr(fmp_client, "datetime", FixedDatetime)
        # 01:00 UTC on Jan 2 is Jan 1, 20:00 in New York (EST)
        assert fmp_client._et_today() == date(2025, 1, 1)


class TestUrlBuilders:
    def test_stable_quote_url_sets_symbol(self):
        assert fmp_client._stable_quote_url("b", "^GSPC", {}) == ("b", {"symbol": "^GSPC"})

    def test_v3_urls_use_path_style(self):
        assert fmp_client._v3_quote_url("b", "AAPL", {"x": 1}) == ("b/AAPL", {"x": 1})
        assert fmp_client._v3_hist_url("b", "AAPL", {}) == ("b/AAPL", {})

    def test_stable_hist_url_converts_timeseries_to_date_range(self, monkeypatch):
        monkeypatch.setattr(fmp_client, "_et_today", lambda now=None: date(2025, 6, 30))
        url, params = fmp_client._stable_hist_url("b", "SPY", {"timeseries": 10})
        assert url == "b"
        assert params == {"symbol": "SPY", "from": "2025-06-10", "to": "2025-06-30"}

    def test_stable_hist_url_without_timeseries_has_no_range(self):
        _, params = fmp_client._stable_hist_url("b", "SPY", {})
        assert params == {"symbol": "SPY"}


class TestNormalizeEodFlatList:
    def test_non_list_passthrough(self):
        payload = {"historical": []}
        assert fmp_client._normalize_eod_flat_list(payload, "SPY") is payload

    def test_empty_list_returns_none(self):
        assert fmp_client._normalize_eod_flat_list([], "SPY") is None

    def test_filters_symbol_strips_symbol_key_and_limits(self):
        rows = [
            {"symbol": "SPY", "date": "d3", "close": 3},
            {"symbol": "QQQ", "date": "d2x", "close": 9},
            {"date": "d2", "close": 2},  # missing symbol -> belongs to request
            "junk",
            {"symbol": "SPY", "date": "d1", "close": 1},
        ]
        out = fmp_client._normalize_eod_flat_list(rows, "SPY", limit=2)
        assert out == {
            "symbol": "SPY",
            "historical": [{"date": "d3", "close": 3}, {"date": "d2", "close": 2}],
        }

    def test_dash_and_dot_symbols_match(self):
        rows = [{"symbol": "BRK.B", "date": "d", "close": 1}]
        out = fmp_client._normalize_eod_flat_list(rows, "BRK-B")
        assert out["symbol"] == "BRK.B"
        assert out["historical"] == [{"date": "d", "close": 1}]

    def test_no_matching_rows_returns_none(self):
        assert fmp_client._normalize_eod_flat_list([{"symbol": "QQQ"}], "SPY") is None


# ---------------------------------------------------------------- FMPClient fallback


class TestRequestWithFallback:
    def test_quote_wrong_symbol_on_stable_falls_back_to_v3(self, make_client):
        def handler(url, params):
            if url.startswith(STABLE):
                return ok([{"symbol": "MSFT", "price": 1}])
            return ok([{"symbol": "AAPL", "price": 2}])

        client = make_client(handler)
        assert client.get_quote("AAPL") == [{"symbol": "AAPL", "price": 2}]
        assert client._endpoint_failures[f"{STABLE}/quote"] == 1
        assert client.session.calls[1][0] == f"{V3}/quote/AAPL"

    def test_quote_is_cached(self, make_client):
        client = make_client(lambda url, p: ok([{"symbol": "AAPL", "price": 2}]))
        client.get_quote("AAPL")
        client.get_quote("AAPL")
        assert len(client.session.calls) == 1

    def test_batch_quote_skips_symbol_check(self, make_client):
        data = [{"symbol": "A", "price": 1}, {"symbol": "B", "price": 2}]
        client = make_client(lambda url, p: ok(data))
        assert client.get_quote("A,B") == data

    def test_non_list_quote_payload_is_invalid(self, make_client):
        client = make_client(lambda url, p: ok({"error": "nope"}))
        assert client.get_quote("AAPL") is None

    def test_all_endpoints_fail_returns_none_and_is_not_cached(self, make_client):
        client = make_client(lambda url, p: fail(500))
        assert client.get_quote("AAPL") is None
        assert "quote_AAPL" not in client.cache

    def test_circuit_breaker_disables_failing_endpoint_after_three_failures(self, make_client):
        def handler(url, params):
            if url.startswith(STABLE):
                return fail(500)
            return ok([{"symbol": params_symbol(url), "price": 1}])

        def params_symbol(url):
            return url.rsplit("/", 1)[1]

        client = make_client(handler)
        for sym in ("AAA", "BBB", "CCC"):
            assert client.get_quote(sym)[0]["symbol"] == sym
        assert f"{STABLE}/quote" in client._disabled_endpoints
        before = len(client.session.calls)
        assert client.get_quote("DDD")[0]["symbol"] == "DDD"
        new_urls = [c[0] for c in client.session.calls[before:]]
        assert new_urls == [f"{V3}/quote/DDD"]

    def test_historical_stable_flat_list_normalized_and_truncated(self, make_client, monkeypatch):
        monkeypatch.setattr(fmp_client, "_et_today", lambda now=None: date(2025, 6, 30))
        rows = [{"symbol": "SPY", "date": f"d{i}", "close": i} for i in range(5)]
        client = make_client(lambda url, p: ok(rows))
        out = client.get_historical_prices("SPY", days=2)
        assert out["symbol"] == "SPY"
        assert [r["date"] for r in out["historical"]] == ["d0", "d1"]
        url, params = client.session.calls[0]
        assert url == f"{STABLE}/historical-price-eod/full"
        assert params == {"symbol": "SPY", "from": "2025-06-26", "to": "2025-06-30"}
        assert client.get_historical_prices("SPY", days=2) is out  # cached

    def test_historical_stable_wrong_symbol_then_v3_dict(self, make_client):
        def handler(url, params):
            if url.startswith(STABLE):
                return ok([{"symbol": "QQQ", "date": "d", "close": 1}])
            return ok({"symbol": "SPY", "historical": [{"date": "d", "close": 7}]})

        client = make_client(handler)
        out = client.get_historical_prices("SPY", days=5)
        assert out == {"symbol": "SPY", "historical": [{"date": "d", "close": 7}]}

    def test_historical_v3_symbol_mismatch_rejected(self, make_client):
        def handler(url, params):
            if url.startswith(STABLE):
                return fail(500)
            return ok({"symbol": "QQQ", "historical": [{"date": "d"}]})

        assert make_client(handler).get_historical_prices("SPY") is None

    def test_historical_dict_without_historical_key_rejected(self, make_client):
        def handler(url, params):
            return fail(500) if url.startswith(STABLE) else ok({"symbol": "SPY"})

        assert make_client(handler).get_historical_prices("SPY") is None

    def test_historical_stock_list_picks_requested_symbol(self, make_client):
        payload = {
            "historicalStockList": [
                {"symbol": "QQQ", "historical": [{"date": "q"}]},
                {"symbol": "SPY", "historical": [{"date": "s"}]},
            ]
        }

        def handler(url, params):
            return fail(500) if url.startswith(STABLE) else ok(payload)

        out = make_client(handler).get_historical_prices("SPY")
        assert out == {"symbol": "SPY", "historical": [{"date": "s"}]}

    def test_historical_stock_list_without_symbol_rejected(self, make_client):
        payload = {"historicalStockList": [{"symbol": "QQQ", "historical": []}]}

        def handler(url, params):
            return fail(500) if url.startswith(STABLE) else ok(payload)

        assert make_client(handler).get_historical_prices("SPY") is None


class TestFMPEndpointsWrappers:
    def test_income_statement_stable_success_cached(self, make_client):
        data = [{"date": "2024-12-31", "eps": 1.0}]
        client = make_client(lambda url, p: ok(data))
        assert client.get_income_statement("AAPL", period="annual", limit=5) == data
        assert client.session.calls[0] == (
            f"{STABLE}/income-statement",
            {"period": "annual", "limit": 5, "symbol": "AAPL"},
        )
        client.get_income_statement("AAPL", period="annual", limit=5)
        assert len(client.session.calls) == 1

    def test_income_statement_falls_back_to_v3(self, make_client):
        data = [{"date": "x"}]

        def handler(url, params):
            return fail(402) if url.startswith(STABLE) else ok(data)

        client = make_client(handler)
        assert client.get_income_statement("AAPL") == data
        assert client.session.calls[1] == (
            f"{V3}/income-statement/AAPL",
            {"period": "quarter", "limit": 8},
        )

    def test_income_statement_both_fail(self, make_client):
        client = make_client(lambda url, p: fail(500))
        assert client.get_income_statement("AAPL") is None
        assert client.cache == {}

    def test_profile_exposes_mktcap_from_marketcap(self, make_client):
        client = make_client(
            lambda url, p: ok(
                [{"symbol": "X", "marketCap": 5e9}, "junk", {"mktCap": 1, "marketCap": 2}]
            )
        )
        profile = client.get_profile("X")
        assert profile[0]["mktCap"] == 5e9
        assert profile[2]["mktCap"] == 1  # existing value is not overwritten
        assert client.get_profile("X") is profile

    def test_profile_v3_fallback_and_failure(self, make_client):
        def handler(url, params):
            return fail(404) if url.startswith(STABLE) else ok([{"symbol": "X", "mktCap": 3}])

        client = make_client(handler)
        assert client.get_profile("X") == [{"symbol": "X", "mktCap": 3}]
        assert make_client(lambda url, p: fail(500)).get_profile("X") is None


class TestInstitutionalHolders:
    def test_recent_13f_quarters_wrap_year(self):
        got = list(FMPClient._recent_13f_quarters(date(2025, 8, 15), count=4))
        assert got == [(2025, 2), (2025, 1), (2024, 4), (2024, 3)]
        jan = list(FMPClient._recent_13f_quarters(date(2025, 1, 10), count=2))
        assert jan == [(2024, 4), (2024, 3)]

    def test_stable_summary_walks_back_to_available_quarter(self, make_client, monkeypatch):
        class FixedDate(date):
            @classmethod
            def today(cls):
                return date(2025, 2, 10)

        monkeypatch.setattr(fmp_client, "date", FixedDate)

        def handler(url, params):
            if url.endswith("symbol-positions-summary"):
                if (params["year"], params["quarter"]) == (2024, 3):
                    return ok([{"investorsHolding": 120, "ownershipPercent": 55.5}])
                return ok([])
            if url.endswith("extract-analytics/holder"):
                return ok(
                    [
                        {"investorName": "Fund A", "sharesNumber": 10, "changeInSharesNumber": 2},
                        "junk",
                    ]
                )
            return fail(404)

        client = make_client(handler)
        result = client.get_institutional_holders("AAPL")
        assert result == {
            "num_holders": 120,
            "ownership_pct": 55.5,
            "top_holders": [{"holder": "Fund A", "shares": 10, "change": 2}],
        }
        summary_calls = [c for c in client.session.calls if c[0].endswith("positions-summary")]
        assert [(c[1]["year"], c[1]["quarter"]) for c in summary_calls] == [(2024, 4), (2024, 3)]
        top_call = [c for c in client.session.calls if c[0].endswith("holder")][0]
        assert top_call[1]["page"] == 0
        assert client.get_institutional_holders("AAPL") is result  # cached

    def test_stable_summary_with_missing_top_holders(self, make_client):
        def handler(url, params):
            if url.endswith("symbol-positions-summary"):
                return ok([{"investorsHolding": 5}])
            return fail(402)

        result = make_client(handler).get_institutional_holders("AAPL")
        assert result == {"num_holders": 5, "ownership_pct": None, "top_holders": []}

    def test_v3_fallback_when_stable_unavailable(self, make_client):
        holders = [{"holder": f"H{i}", "shares": i, "change": 0} for i in range(12)]

        def handler(url, params):
            return ok(holders) if url.startswith(V3) else fail(402)

        result = make_client(handler).get_institutional_holders("AAPL")
        assert result["num_holders"] == 12
        assert result["ownership_pct"] is None
        assert result["top_holders"] == holders[:10]

    def test_all_sources_fail_returns_none(self, make_client):
        client = make_client(lambda url, p: fail(403))
        assert client.get_institutional_holders("AAPL") is None
        assert "institutional_AAPL" not in client.cache


class TestFMPClientMisc:
    def test_calculate_ema_matches_manual_computation(self, make_client):
        client = make_client(lambda url, p: ok({}))
        assert client.calculate_ema([2.0, 4.0], period=5) == 3.0
        # newest-first [30, 20, 10] with period 2: SMA(10,20)=15, then 30*2/3 + 15/3 = 25
        assert client.calculate_ema([30.0, 20.0, 10.0], period=2) == pytest.approx(25.0)

    def test_clear_cache_and_stats(self, make_client, capsys):
        client = make_client(lambda url, p: ok([{"symbol": "AAPL"}]))
        client.get_quote("AAPL")
        assert client.get_api_stats() == {
            "cache_entries": 1,
            "rate_limit_reached": False,
            "retry_count": 0,
        }
        client.clear_cache()
        assert client.cache == {}
        assert "Cache cleared" in capsys.readouterr().err

    def test_builtin_smoke_function_reports_success(self, monkeypatch, capsys):
        class Smoke:
            def get_quote(self, symbols):
                if "," in symbols:
                    return [{"symbol": "^GSPC", "price": 10.0}, {"symbol": "^VIX", "price": 20.0}]
                return [{"symbol": "AAPL", "price": 10.0}]

            def get_income_statement(self, symbol, period="quarter", limit=8):
                return [{"date": "2024-01-01", "eps": 1.5}]

            def get_historical_prices(self, symbol, days=365):
                return {"historical": [{"date": "2024-01-01", "close": 2.0}]}

            def get_api_stats(self):
                return {"cache_entries": 4, "rate_limit_reached": False}

        monkeypatch.setattr(fmp_client, "FMPClient", Smoke)
        fmp_client.test_client()
        out = capsys.readouterr().out
        assert "Quote: AAPL @ $10.00" in out
        assert "Latest quarter: 2024-01-01, EPS: $1.5" in out
        assert "Latest year: 2024-01-01, EPS: $1.5" in out
        assert "Fetched 1 days of price history" in out
        assert "^VIX: 20.00" in out
        assert "Cache entries: 4" in out

    def test_builtin_smoke_function_reports_failures(self, monkeypatch, capsys):
        class Broken:
            def get_quote(self, symbols):
                return None

            def get_income_statement(self, symbol, period="quarter", limit=8):
                return None

            def get_historical_prices(self, symbol, days=365):
                return None

            def get_api_stats(self):
                return {"cache_entries": 0, "rate_limit_reached": True}

        monkeypatch.setattr(fmp_client, "FMPClient", Broken)
        fmp_client.test_client()
        out = capsys.readouterr().out
        assert "Quote failed" in out
        assert "Quarterly income statement failed" in out
        assert "Annual income statement failed" in out
        assert "Historical prices failed" in out
        assert "Market indices failed" in out
        assert "Rate limit reached: True" in out


# ---------------------------------------------------------------- Finviz client

FINVIZ_HTML = """
<html><body>
<table class="snapshot-table2">
<tr><td>Inst Own</td><td>61.25%</td><td>Inst Trans</td><td>-1.50%</td></tr>
<tr><td>P/E</td><td>25.1</td><td>Odd</td></tr>
</table>
</body></html>
"""


@pytest.fixture
def finviz(monkeypatch):
    sleeps = []
    monkeypatch.setattr(fsc.time, "sleep", sleeps.append)
    client = fsc.FinvizStockClient(rate_limit_seconds=2.0)
    client.sleeps = sleeps
    return client


class TestFinvizClient:
    def test_parse_page_extracts_label_value_pairs(self, finviz):
        data = finviz._parse_finviz_page(FINVIZ_HTML)
        assert data == {
            "Inst Own": "61.25%",
            "Inst Trans": "-1.50%",
            "P/E": "25.1",
        }

    def test_parse_page_without_table_is_empty(self, finviz):
        assert finviz._parse_finviz_page("<html><body>nothing</body></html>") == {}

    @pytest.mark.parametrize(
        "text,expected",
        [("60.50%", 60.5), ("-", None), ("", None), (None, None), ("abc%", None), ("-1.5%", -1.5)],
    )
    def test_parse_percentage(self, text, expected):
        assert fsc.FinvizStockClient._parse_percentage(text) == expected

    def test_institutional_ownership_success_and_cache(self, finviz):
        finviz.session = FakeSession(lambda url, p: FakeResponse(200, text=FINVIZ_HTML))
        result = finviz.get_institutional_ownership("AAPL")
        assert result == {"inst_own_pct": 61.25, "inst_trans_pct": -1.5, "error": None}
        assert finviz.session.calls[0][0] == "https://finviz.com/quote.ashx?t=AAPL"
        assert finviz.get_institutional_ownership("AAPL") is result
        assert len(finviz.session.calls) == 1

    def test_missing_ownership_fields_give_none(self, finviz):
        html = '<table class="snapshot-table2"><tr><td>P/E</td><td>9</td></tr></table>'
        finviz.session = FakeSession(lambda url, p: FakeResponse(200, text=html))
        result = finviz.get_institutional_ownership("ZZZ")
        assert result == {"inst_own_pct": None, "inst_trans_pct": None, "error": None}

    def test_http_error_returns_error_result(self, finviz, capsys):
        finviz.session = FakeSession(lambda url, p: FakeResponse(403, text="no"))
        result = finviz.get_institutional_ownership("AAPL")
        assert result["inst_own_pct"] is None
        assert result["error"] == "Failed to fetch data from Finviz for AAPL"
        assert "status 403" in capsys.readouterr().err

    def test_exception_returns_error_result(self, finviz, capsys):
        finviz.session = FakeSession(lambda url, p: RuntimeError("net down"))
        result = finviz.get_institutional_ownership("AAPL")
        assert result["error"] == "Failed to fetch data from Finviz for AAPL"
        assert "net down" in capsys.readouterr().err

    def test_rate_limit_sleeps_between_requests(self, finviz, monkeypatch):
        monkeypatch.setattr(fsc.time, "time", lambda: 100.0)
        finviz.session = FakeSession(lambda url, p: FakeResponse(200, text=FINVIZ_HTML))
        finviz.get_stock_data("AAA")
        assert finviz.sleeps == []
        finviz.get_stock_data("BBB")
        assert finviz.sleeps == [pytest.approx(2.0)]

    def test_get_stock_data_returns_full_dict_and_caches(self, finviz):
        finviz.session = FakeSession(lambda url, p: FakeResponse(200, text=FINVIZ_HTML))
        data = finviz.get_stock_data("AAPL")
        assert data["P/E"] == "25.1"
        assert finviz.get_stock_data("AAPL") is data
        assert len(finviz.session.calls) == 1

    def test_get_stock_data_failure_returns_none_uncached(self, finviz):
        finviz.session = FakeSession(lambda url, p: FakeResponse(500, text=""))
        assert finviz.get_stock_data("AAPL") is None
        assert "finviz_full_AAPL" not in finviz.cache

    def test_empty_page_counts_as_failure(self, finviz):
        finviz.session = FakeSession(lambda url, p: FakeResponse(200, text="<html></html>"))
        result = finviz.get_institutional_ownership("AAPL")
        assert result["error"] == "Failed to fetch data from Finviz for AAPL"


# ---------------------------------------------------------------- check_institutional_endpoint


class TestCheckInstitutionalEndpoint:
    def test_latest_completed_quarter(self):
        assert cie._latest_completed_quarter(date(2025, 2, 1)) == (2024, 4)
        assert cie._latest_completed_quarter(date(2025, 4, 1)) == (2025, 1)
        assert cie._latest_completed_quarter(date(2025, 12, 31)) == (2025, 3)

    def _patch_quarter(self, monkeypatch):
        monkeypatch.setattr(cie, "_latest_completed_quarter", lambda as_of=None: (2025, 2))

    def test_missing_key(self, monkeypatch, capsys):
        monkeypatch.delenv("FMP_API_KEY", raising=False)
        assert cie.check_institutional_endpoint() is False
        assert "FMP_API_KEY environment variable not set" in capsys.readouterr().out

    def test_available(self, monkeypatch, capsys):
        monkeypatch.setenv("FMP_API_KEY", TEST_KEY)
        self._patch_quarter(monkeypatch)
        seen = {}

        def fake_get(url, params=None, timeout=None):
            seen["url"], seen["params"] = url, params
            return FakeResponse(200, [{"investorsHolding": 321, "ownershipPercent": 61.5}], "x" * 7)

        monkeypatch.setattr(cie.requests, "get", fake_get)
        assert cie.check_institutional_endpoint() is True
        out = capsys.readouterr().out
        assert "AAPL: 321 holders, ownership 61.5%" in out
        assert "year=2025 Q2" in out
        assert "Response length: 7 bytes" in out
        assert seen["params"] == {
            "symbol": "AAPL",
            "year": 2025,
            "quarter": 2,
            "apikey": TEST_KEY,
        }
        assert seen["url"].endswith("/stable/institutional-ownership/symbol-positions-summary")

    @pytest.mark.parametrize("payload", [[], [{"investorsHolding": 0}], {"Error": "x"}])
    def test_no_data_for_latest_quarter(self, monkeypatch, capsys, payload):
        monkeypatch.setenv("FMP_API_KEY", TEST_KEY)
        self._patch_quarter(monkeypatch)
        monkeypatch.setattr(cie.requests, "get", lambda *a, **k: FakeResponse(200, payload, "t"))
        assert cie.check_institutional_endpoint() is False
        assert "No institutional data for the latest quarter" in capsys.readouterr().out

    @pytest.mark.parametrize(
        "status,msg",
        [(401, "RESTRICTED"), (403, "RESTRICTED"), (500, "Unexpected status code 500")],
    )
    def test_error_statuses(self, monkeypatch, capsys, status, msg):
        monkeypatch.setenv("FMP_API_KEY", TEST_KEY)
        self._patch_quarter(monkeypatch)
        monkeypatch.setattr(cie.requests, "get", lambda *a, **k: FakeResponse(status, None, ""))
        assert cie.check_institutional_endpoint() is False
        assert msg in capsys.readouterr().out

    def test_request_exception(self, monkeypatch, capsys):
        monkeypatch.setenv("FMP_API_KEY", TEST_KEY)
        self._patch_quarter(monkeypatch)

        def boom(*a, **k):
            raise requests.exceptions.Timeout("timed out")

        monkeypatch.setattr(cie.requests, "get", boom)
        assert cie.check_institutional_endpoint() is False
        assert "Request failed - timed out" in capsys.readouterr().out

    @pytest.mark.parametrize("key,code", [(None, 1), (TEST_KEY, 0)])
    def test_script_entrypoint_exit_codes(self, monkeypatch, capsys, key, code):
        if key is None:
            monkeypatch.delenv("FMP_API_KEY", raising=False)
        else:
            monkeypatch.setenv("FMP_API_KEY", key)
        payload = [{"investorsHolding": 9, "ownershipPercent": 1.0}]
        monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResponse(200, payload, "t"))
        with pytest.raises(SystemExit) as exc:
            runpy.run_path(cie.__file__, run_name="__main__")
        assert exc.value.code == code
        assert "FMP Institutional-Holder Endpoint Availability Test" in capsys.readouterr().out


# ---------------------------------------------------------------- scorer


class TestScorer:
    def test_phase1_composite(self):
        result = scorer.calculate_composite_score(c_score=100, a_score=95, n_score=98, m_score=100)
        # 27 + 34.2 + 26.46 + 10 = 97.66
        assert result["composite_score"] == 97.7
        assert result["rating"] == "Exceptional+"
        assert result["weakest_component"] == "A"
        assert result["weakest_score"] == 95
        assert result["component_scores"] == {"C": 100, "A": 95, "N": 98, "M": 100}

    def test_phase1_weights_sum_to_one(self):
        assert sum(scorer.WEIGHTS_PHASE1.values()) == pytest.approx(1.0)
        assert sum(scorer.WEIGHTS_PHASE2.values()) == pytest.approx(1.0)
        assert sum(scorer.WEIGHTS_PHASE3.values()) == pytest.approx(1.0)

    def test_phase2_composite(self):
        result = scorer.calculate_composite_score_phase2(
            c_score=100, a_score=100, n_score=0, s_score=50, i_score=100, m_score=100
        )
        # 19 + 25 + 0 + 9 + 13 + 6 = 72
        assert result["composite_score"] == 72.0
        assert result["rating"] == "Strong"
        assert result["weakest_component"] == "N"
        assert result["component_scores"]["S"] == 50

    def test_phase3_composite(self):
        result = scorer.calculate_composite_score_phase3(95, 90, 88, 85, 92, 80, 100)
        # 14.25 + 18 + 13.2 + 12.75 + 18.4 + 8 + 5 = 89.6
        assert result["composite_score"] == 89.6
        assert result["rating"] == "Exceptional"
        assert result["weakest_component"] == "I"
        assert result["weakest_score"] == 80
        assert set(result["component_scores"]) == set("CANSLIM")

    @pytest.mark.parametrize(
        "composite,rating,guidance_start",
        [
            (95, "Exceptional+", "Immediate buy"),
            (85, "Exceptional", "Strong buy"),
            (75, "Strong", "Buy, standard"),
            (65, "Above Average", "Buy on pullback"),
            (55, "Average", "Watchlist only"),
            (45, "Below Average", "Monitor"),
            (10, "Weak", "Avoid"),
            (90, "Exceptional+", "Immediate buy"),
            (40, "Below Average", "Monitor"),
        ],
    )
    def test_interpret_composite_score(self, composite, rating, guidance_start):
        info = scorer.interpret_composite_score(composite)
        assert info["rating"] == rating
        assert info["guidance"].startswith(guidance_start)

    def test_phase1_thresholds(self):
        ok_ = scorer.check_minimum_thresholds(70, 60, 65, 70)
        assert ok_ == {
            "passes_all": True,
            "failed_components": [],
            "recommendation": "buy",
            "reason": "All minimum thresholds met",
        }
        one = scorer.check_minimum_thresholds(50, 60, 65, 70)
        assert (one["recommendation"], one["failed_components"]) == ("watchlist", ["C"])
        many = scorer.check_minimum_thresholds(50, 45, 35, 60)
        assert many["recommendation"] == "avoid"
        assert many["failed_components"] == ["C", "A", "N"]
        assert many["reason"] == "Multiple components below threshold: C, A, N"
        bear = scorer.check_minimum_thresholds(95, 90, 92, 0)
        assert bear["recommendation"] == "avoid"
        assert bear["failed_components"] == ["M"]
        assert "Bear market" in bear["reason"]

    def test_phase2_thresholds(self):
        assert scorer.check_minimum_thresholds_phase2(60, 50, 40, 40, 40, 40)["passes_all"] is True
        one = scorer.check_minimum_thresholds_phase2(60, 50, 40, 39, 40, 40)
        assert (one["recommendation"], one["failed_components"]) == ("watchlist", ["S"])
        many = scorer.check_minimum_thresholds_phase2(10, 10, 40, 40, 40, 40)
        assert many["recommendation"] == "avoid"
        assert many["failed_components"] == ["C", "A"]
        bear = scorer.check_minimum_thresholds_phase2(99, 99, 99, 99, 99, 0)
        assert bear["failed_components"] == ["M"]
        assert bear["recommendation"] == "avoid"

    def test_phase3_thresholds_buy_watchlist_avoid(self):
        buy = scorer.check_minimum_thresholds_phase3(60, 50, 40, 40, 50, 40, 40)
        assert buy["passes_all"] is True
        assert "All 7 CANSLIM thresholds met" in buy["reason"]
        watch = scorer.check_minimum_thresholds_phase3(60, 50, 40, 40, 45, 40, 40)
        assert (watch["recommendation"], watch["failed_components"]) == ("watchlist", ["L"])
        many = scorer.check_minimum_thresholds_phase3(0, 0, 40, 40, 50, 40, 40)
        assert many["recommendation"] == "avoid"
        assert many["failed_components"] == ["C", "A"]

    def test_phase3_low_leadership_forces_avoid_even_if_only_failure(self):
        result = scorer.check_minimum_thresholds_phase3(90, 90, 90, 90, 39, 90, 90)
        assert result["recommendation"] == "avoid"
        assert result["failed_components"] == ["L"]
        assert "L=39" in result["reason"]

    def test_phase3_low_leadership_keeps_other_failures_listed(self):
        result = scorer.check_minimum_thresholds_phase3(10, 90, 90, 90, 20, 90, 90)
        assert result["failed_components"] == ["C", "L"]
        assert result["recommendation"] == "avoid"

    def test_phase3_bear_market_overrides_leadership(self):
        result = scorer.check_minimum_thresholds_phase3(90, 90, 90, 90, 10, 90, 0)
        assert result["failed_components"] == ["M"]
        assert "Bear market" in result["reason"]

    @pytest.mark.parametrize(
        "score,rng,rating",
        [
            (95, "160-200", "Exceptional"),
            (85, "140-159", "Strong"),
            (75, "120-139", "Above Average"),
            (65, "105-119", "Average"),
            (59.9, "<105", "Below Average"),
        ],
    )
    def test_compare_to_full_canslim(self, score, rng, rating):
        result = scorer.compare_to_full_canslim(score)
        assert result["estimated_full_range"] == rng
        assert result["equivalent_rating"] == rating
        assert result["phase1_score"] == score
        assert "4 of 7 components" in result["note"]


# ---------------------------------------------------------------- report generator


def make_result(symbol="AAA", score=95.0, **overrides):
    result = {
        "symbol": symbol,
        "company_name": f"{symbol} Corp",
        "price": 123.456,
        "market_cap": 2.5e9,
        "sector": "Technology",
        "composite_score": score,
        "rating": "Exceptional+",
        "rating_description": "Rare setup",
        "guidance": "Buy now",
        "weakest_component": "A",
        "weakest_score": 90,
        "c_component": {
            "score": 100,
            "latest_qtr_eps_growth": 42.0,
            "latest_qtr_revenue_growth": 12.5,
        },
        "a_component": {"score": 90, "eps_cagr_3yr": 33.33, "stability": "stable"},
        "n_component": {"score": 80, "distance_from_high_pct": -3.2, "breakout_detected": True},
        "s_component": {"score": 80, "up_down_ratio": 1.789, "accumulation_detected": True},
        "l_component": {
            "score": 90,
            "rs_3m_return": 10.0,
            "rs_6m_return": 20.0,
            "rs_12m_return": 30.0,
            "rel_3m": 1.0,
            "rel_6m": 2.0,
            "rel_12m": 3.0,
            "rs_rating": "Strong",
            "rs_rank_percentile": 80,
        },
        "i_component": {
            "score": 70,
            "num_holders": 75,
            "ownership_pct": 45.55,
            "superinvestor_present": True,
        },
        "m_component": {"score": 90, "trend": "strong_uptrend"},
    }
    result.update(overrides)
    return result


BASE_META = {
    "generated_at": "2025-01-01 00:00:00 UTC",
    "phase": "3.1 (test)",
    "candidates_analyzed": 2,
}


def render(tmp_path, results, metadata=None):
    path = tmp_path / "report.md"
    rg.generate_markdown_report(results, metadata or dict(BASE_META), str(path))
    return path.read_text(encoding="utf-8")


class TestReportGenerator:
    def test_summary_stats_buckets(self):
        results = [{"composite_score": s} for s in (95, 90, 85, 80, 79.9, 70, 65, 60, 59.9, 0)]
        assert rg.generate_summary_stats(results) == {
            "total_stocks": 10,
            "exceptional": 2,
            "strong": 2,
            "above_average": 2,
            "average": 2,
            "below_average": 2,
        }

    def test_summary_stats_empty(self):
        assert rg.generate_summary_stats([]) == {
            "total_stocks": 0,
            "exceptional": 0,
            "strong": 0,
            "above_average": 0,
            "average": 0,
            "below_average": 0,
        }

    @pytest.mark.parametrize(
        "score,emoji",
        [(95, "⭐⭐⭐"), (85, "⭐⭐"), (75, "⭐"), (65, "✓"), (59, "")],
    )
    def test_rating_emoji(self, score, emoji):
        assert rg.get_rating_emoji(score) == emoji

    def test_json_report_roundtrip(self, tmp_path, capsys):
        path = tmp_path / "out.json"
        results = [make_result("AAA", 95.0), make_result("BBB", 65.0)]
        rg.generate_json_report(results, {"k": "v"}, str(path))
        report = json.loads(path.read_text(encoding="utf-8"))
        assert report["metadata"] == {"k": "v"}
        assert [r["symbol"] for r in report["results"]] == ["AAA", "BBB"]
        assert report["summary"]["exceptional"] == 1
        assert report["summary"]["average"] == 1
        assert "JSON report saved to" in capsys.readouterr().out

    def test_markdown_header_and_defaults(self, tmp_path):
        text = render(tmp_path, [make_result()])
        assert "**Generated:** 2025-01-01 00:00:00 UTC" in text
        assert "**Phase:** 3.1 (test) (Components: C, A, N, S, I, M)" in text
        assert "**Stocks Analyzed:** 2" in text
        assert "Schema Version" not in text
        assert "RS Benchmark" not in text
        assert "## Market Condition Summary" not in text

    def test_markdown_metadata_sections(self, tmp_path):
        meta = dict(
            BASE_META,
            schema_version="3.1",
            components_included=["C", "A"],
            screening_options={"rs_benchmark": "SPY", "rs_disabled": True},
            market_condition={"trend": "bear_market", "M_score": 0, "warning": "Go to cash"},
        )
        text = render(tmp_path, [make_result()], meta)
        assert "(Components: C, A)" in text
        assert "**Schema Version:** 3.1" in text
        assert "**RS Benchmark:** SPY (DISABLED via --disable-rs)" in text
        assert "RS Disabled: L component fixed at neutral 50" in text
        assert "- **Trend:** bear_market" in text
        assert "- **M Score:** 0/100" in text
        assert "- **⚠️ Warning:** Go to cash" in text

    def test_rs_disabled_without_benchmark_defaults_label(self, tmp_path):
        meta = dict(BASE_META, screening_options={"rs_disabled": True})
        text = render(tmp_path, [make_result()], meta)
        assert "**RS Benchmark:** ^GSPC (DISABLED via --disable-rs)" in text

    def test_rs_benchmark_only(self, tmp_path):
        meta = dict(BASE_META, screening_options={"rs_benchmark": "QQQ"})
        text = render(tmp_path, [make_result()], meta)
        assert "**RS Benchmark:** QQQ\n" in text
        assert "DISABLED" not in text

    def test_market_condition_without_optional_keys(self, tmp_path):
        text = render(tmp_path, [make_result()], dict(BASE_META, market_condition={}))
        assert "- **Trend:** unknown" in text
        assert "- **M Score:** N/A/100" in text
        assert "Warning" not in text.split("## Summary Table")[0]

    def test_summary_table_rows(self, tmp_path):
        weak_l = {"score": 10, "rs_rank_percentile": None}
        text = render(
            tmp_path,
            [
                make_result("AAA", 95.0),
                make_result("BBB", 61.234, rating="Above Average", l_component=weak_l),
            ],
        )
        assert "| 1 | AAA | 95.0 | Exceptional+ | Strong | 80 |" in text
        assert "| 2 | BBB | 61.2 | Above Average | N/A | N/A |" in text
        assert "## Top 2 CANSLIM Candidates" in text
        assert "### 1. AAA - AAA Corp ⭐⭐⭐" in text
        assert "### 2. BBB - BBB Corp ✓" in text

    def test_empty_results_report(self, tmp_path):
        text = render(tmp_path, [])
        assert "## Summary Table" not in text
        assert "## Top 0 CANSLIM Candidates" in text
        assert "- **Total Stocks Screened:** 0" in text
        assert "## Methodology" in text
        assert "**Disclaimer:**" in text

    def test_summary_statistics_section(self, tmp_path):
        text = render(tmp_path, [make_result("A", 95), make_result("B", 85), make_result("C", 10)])
        assert "- **Total Stocks Screened:** 3" in text
        assert "- **Exceptional (90+):** 1 stocks" in text
        assert "- **Strong (80-89):** 1 stocks" in text
        assert "- **Below Average (<60):** 1 stocks" in text

    def test_stock_entry_basic_fields(self):
        lines = rg.format_stock_entry(3, make_result())
        text = "\n".join(lines)
        assert lines[0] == "### 3. AAA - AAA Corp ⭐⭐⭐"
        assert "**Price:** $123.46 | **Market Cap:** $2.5B | **Sector:** Technology" in text
        assert "**Composite Score:** 95.0/100 (Exceptional+)" in text
        assert "| 🅲 Current Earnings | 100/100 | EPS: +42.0%, Revenue: +12.5% |" in text
        assert "| 🅰 Annual Growth | 90/100 | 3yr CAGR: 33.3%, stable |" in text
        assert "| 🅽 Newness | 80/100 | -3.2% from 52wk high ✓ Breakout |" in text
        assert "Up/Down Volume Ratio: 1.79 ✓ Accumulation |" in text
        assert "| 🅸 Institutional | 70/100 | 75 holders, 45.5% ownership ⭐ Superinvestor |" in text
        assert "| 🅼 Market Direction | 90/100 | Strong Uptrend |" in text
        assert "**Rating:** Exceptional+ - Rare setup" in text
        assert "**Guidance:** Buy now" in text
        assert "**Weakest Component:** A (90/100)" in text
        assert "**Warnings:**" not in text

    def test_stock_entry_multi_period_leadership_with_benchmark(self):
        text = "\n".join(rg.format_stock_entry(1, make_result()))
        assert (
            "| 🅻 Leadership | 90/100 | 3m/6m/12m: +10.0%/+20.0%/+30.0% "
            "(rel +1.0%/+2.0%/+3.0%) | RS: 80 (Strong) |"
        ) in text

    def test_stock_entry_multi_period_leadership_without_benchmark(self):
        l_comp = {
            "score": 40,
            "rs_3m_return": 5.0,
            "rs_6m_return": None,
            "rs_12m_return": None,
            "rel_3m": None,
            "rel_6m": None,
            "rel_12m": None,
        }
        text = "\n".join(rg.format_stock_entry(1, make_result(l_component=l_comp)))
        assert "| 🅻 Leadership | 40/100 | 3m/6m/12m: +5.0%/N/A/N/A (no benchmark) |" in text

    def test_stock_entry_skipped_leadership(self):
        text = "\n".join(
            rg.format_stock_entry(1, make_result(l_component={"score": 50, "skipped": True}))
        )
        assert "| 🅻 Leadership | 50/100 | Skipped via --disable-rs (neutral 50) |" in text

    def test_stock_entry_legacy_leadership_with_rank(self):
        l_comp = {
            "score": 80,
            "stock_52w_performance": 25.0,
            "relative_performance": 12.0,
            "rs_rank_estimate": 80,
            "rs_rating": "Strong",
        }
        text = "\n".join(rg.format_stock_entry(1, make_result(l_component=l_comp)))
        assert (
            "| 🅻 Leadership | 80/100 | 52wk: +25.0% (+12.0% vs benchmark) | RS: 80 (Strong) |"
            in text
        )

    def test_stock_entry_legacy_leadership_rank_without_rating_or_benchmark(self):
        l_comp = {"score": 60, "stock_52w_performance": 5.0, "rs_rank_estimate": 54}
        text = "\n".join(rg.format_stock_entry(1, make_result(l_component=l_comp)))
        assert "52wk: +5.0% ((no benchmark)) | RS: 54 |" in text

    def test_stock_entry_missing_optional_inputs(self):
        stock = make_result(price=None, market_cap=None)
        del stock["sector"]
        stock["c_component"] = {}
        stock["a_component"] = {}
        stock["n_component"] = {}
        stock["s_component"] = {}
        stock["i_component"] = {}
        stock["m_component"] = {}
        stock["l_component"] = {}
        text = "\n".join(rg.format_stock_entry(1, stock))
        assert "**Price:** N/A | **Market Cap:** N/A | **Sector:** N/A" in text
        assert "| 🅲 Current Earnings | 0/100 | EPS: N/A, Revenue: N/A |" in text
        assert "| 🅰 Annual Growth | 0/100 | 3yr CAGR: N/A, unknown |" in text
        assert "| 🅼 Market Direction | 0/100 | Unknown |" in text
        assert "| 🅸 Institutional | 0/100 | N/A holders, N/A ownership  |" in text
        assert "| 🅻 Leadership | 0/100 | 52wk: N/A ((no benchmark)) |" in text

    def test_stock_entry_none_values_render_as_none_text(self):
        """Pin: None (as emitted by failed calculators) is rendered literally as 'None'."""
        stock = make_result()
        stock["c_component"] = {
            "score": 0,
            "latest_qtr_eps_growth": None,
            "latest_qtr_revenue_growth": None,
        }
        stock["i_component"] = {"score": 0, "num_holders": 0, "ownership_pct": None}
        text = "\n".join(rg.format_stock_entry(1, stock))
        assert "EPS: None, Revenue: None" in text
        assert "0 holders, None ownership" in text

    def test_stock_entry_warnings_from_every_component(self):
        stock = make_result()
        stock["c_component"]["quality_warning"] = "c warn"
        stock["a_component"]["quality_warning"] = "a warn"
        stock["s_component"]["quality_warning"] = "s warn"
        stock["l_component"]["quality_warning"] = "l warn"
        stock["i_component"]["quality_warning"] = "i warn"
        stock["m_component"]["warning"] = "m warn"
        lines = rg.format_stock_entry(1, stock)
        start = lines.index("**Warnings:**")
        assert lines[start + 1 : start + 7] == [
            "- ⚠️ c warn",
            "- ⚠️ a warn",
            "- ⚠️ s warn",
            "- ⚠️ l warn",
            "- ⚠️ i warn",
            "- ⚠️ m warn",
        ]

    def test_markdown_file_written_and_announced(self, tmp_path, capsys):
        render(tmp_path, [make_result()])
        assert "Markdown report saved to" in capsys.readouterr().out
        assert (tmp_path / "report.md").read_text(encoding="utf-8").endswith("\n")


# ---------------------------------------------------------------- screen_canslim helpers


def _iso(i):
    return (date(2024, 1, 1) + timedelta(days=i)).isoformat()


def price_history(n, start, end, zigzag=0.0, up_vol=2000, down_vol=1000):
    """Newest-first FMP-style history; even chronological index = up day."""
    step = (end - start) / (n - 1) if n > 1 else 0.0
    chrono = []
    for i in range(n):
        close = start + step * i + (zigzag if i % 2 == 0 else 0.0)
        chrono.append(
            {
                "date": _iso(i),
                "close": close,
                "volume": up_vol if i % 2 == 0 else down_vol,
            }
        )
    return {"symbol": "X", "historical": chrono[::-1]}


def quarters(eps_latest, eps_year_ago, rev_latest, rev_year_ago):
    rows = [{"date": f"q{i}", "eps": 1.0, "revenue": 100.0} for i in range(8)]
    rows[0] = {"date": "2024-06-30", "eps": eps_latest, "revenue": rev_latest}
    rows[4] = {"date": "2023-06-30", "eps": eps_year_ago, "revenue": rev_year_ago}
    return rows


def annual(eps_newest_first, revenues):
    return [
        {"date": f"{2024 - i}-12-31", "eps": e, "revenue": r}
        for i, (e, r) in enumerate(zip(eps_newest_first, revenues))
    ]


def strong_stock(symbol):
    return {
        "profile": [
            {"symbol": symbol, "companyName": f"{symbol} Inc", "sector": "Tech", "mktCap": 3e9}
        ],
        "quote": [
            {
                "symbol": symbol,
                "price": 99.8,
                "yearHigh": 100.0,
                "yearLow": 50.0,
                "volume": 1_500_000,
                "avgVolume": 1_000_000,
            }
        ],
        "quarterly": quarters(3.0, 1.0, 300.0, 100.0),
        "annual": annual([8, 4, 2, 1], [800.0, 400.0, 200.0, 100.0]),
        "prices_90": price_history(90, 100, 110, zigzag=1.0),
        "prices_365": price_history(365, 100, 1000),
        "institutional": {"num_holders": 75, "ownership_pct": 45.0, "top_holders": []},
    }


def weak_stock(symbol):
    data = strong_stock(symbol)
    data["quote"] = [
        {
            "symbol": symbol,
            "price": 60.0,
            "yearHigh": 100.0,
            "yearLow": 50.0,
            "volume": 1,
            "avgVolume": 1,
        }
    ]
    data["quarterly"] = quarters(1.0, 1.0, 100.0, 100.0)
    data["annual"] = annual([1, 1, 1, 1], [100.0, 100.0, 100.0, 100.0])
    data["prices_365"] = price_history(365, 100, 100.5)
    data["institutional"] = {"num_holders": 5, "ownership_pct": 5.0, "top_holders": []}
    return data


class FakeFMP:
    """Stand-in for FMPClient driven by per-symbol dicts."""

    def __init__(self, stocks, market=None, api_key=None):
        self.stocks = stocks
        self.market = market if market is not None else default_market()
        self.api_key = api_key
        self.calls = []

    def _stock(self, symbol):
        return self.stocks.get(symbol)

    def get_profile(self, symbol):
        self.calls.append(("profile", symbol))
        stock = self._stock(symbol)
        return stock["profile"] if stock else None

    def get_quote(self, symbol):
        self.calls.append(("quote", symbol))
        if symbol in self.market["quotes"]:
            return self.market["quotes"][symbol]
        stock = self._stock(symbol)
        return stock["quote"] if stock else None

    def get_income_statement(self, symbol, period="quarter", limit=8):
        stock = self._stock(symbol)
        if not stock:
            return None
        return stock["quarterly" if period == "quarter" else "annual"]

    def get_historical_prices(self, symbol, days=365):
        self.calls.append(("prices", symbol, days))
        if symbol in self.market["history"]:
            return self.market["history"][symbol]
        stock = self._stock(symbol)
        if not stock:
            return None
        return stock["prices_90"] if days == 90 else stock["prices_365"]

    def get_institutional_holders(self, symbol):
        stock = self._stock(symbol)
        return stock["institutional"] if stock else None

    def get_api_stats(self):
        return {"cache_entries": 7, "rate_limit_reached": False, "retry_count": 0}


def default_market(price=103.0, vix=12.0):
    return {
        "quotes": {
            "^GSPC": [{"symbol": "^GSPC", "price": price}],
            "^VIX": [{"symbol": "^VIX", "price": vix}],
        },
        "history": {
            "^GSPC": price_history(365, 100.0, 100.0),
            "SPY": price_history(365, 100.0, 110.0),
        },
    }


def market_result(score=100, trend="strong_uptrend"):
    return {"score": score, "trend": trend, "interpretation": "test market", "warning": None}


# ---------------------------------------------------------------- analyze_stock


class TestAnalyzeStock:
    def test_strong_stock_scores_all_components(self, capsys):
        client = FakeFMP({"AAA": strong_stock("AAA")})
        result = sc.analyze_stock(
            "AAA", client, market_result(), rs_benchmark_historical=price_history(365, 100.0, 100.0)
        )
        assert result["symbol"] == "AAA"
        assert result["company_name"] == "AAA Inc"
        assert result["sector"] == "Tech"
        assert result["market_cap"] == 3e9
        assert result["price"] == 99.8
        assert result["c_component"]["score"] == 100
        assert result["a_component"]["score"] == 100
        assert result["n_component"]["score"] == 100
        assert result["s_component"]["score"] == 100
        assert result["l_component"]["score"] == 100
        assert result["i_component"]["score"] == 100
        assert result["m_component"]["score"] == 100
        assert result["composite_score"] == 100.0
        assert result["rating"] == "Exceptional+"
        assert result["threshold_check"]["recommendation"] == "buy"
        assert "Score: 100.0 (Exceptional+)" in capsys.readouterr().out

    def test_composite_is_consistent_with_components(self):
        client = FakeFMP({"BBB": weak_stock("BBB")})
        result = sc.analyze_stock("BBB", client, market_result(score=70, trend="uptrend"))
        expected = scorer.calculate_composite_score_phase3(
            result["c_component"]["score"],
            result["a_component"]["score"],
            result["n_component"]["score"],
            result["s_component"]["score"],
            result["l_component"]["score"],
            result["i_component"]["score"],
            70,
        )
        assert result["composite_score"] == expected["composite_score"]
        assert result["weakest_component"] == expected["weakest_component"]
        assert result["composite_score"] < 70
        assert result["threshold_check"]["recommendation"] != "buy"

    def test_profile_unavailable(self, capsys):
        assert sc.analyze_stock("NOPE", FakeFMP({}), market_result()) is None
        assert "Profile unavailable" in capsys.readouterr().out

    def test_quote_unavailable(self, capsys):
        stock = strong_stock("AAA")
        stock["quote"] = None
        assert sc.analyze_stock("AAA", FakeFMP({"AAA": stock}), market_result()) is None
        assert "Quote unavailable" in capsys.readouterr().out

    def test_missing_statements_and_prices_use_defaults(self):
        stock = strong_stock("AAA")
        stock["quarterly"] = None
        stock["annual"] = None
        stock["prices_90"] = None
        stock["prices_365"] = None
        stock["institutional"] = None
        result = sc.analyze_stock("AAA", FakeFMP({"AAA": stock}), market_result())
        assert result["c_component"] == {"score": 0, "error": "No quarterly data"}
        assert result["a_component"] == {"score": 50, "error": "No annual data"}
        assert result["s_component"] == {"score": 0, "error": "No price history data"}
        assert result["l_component"]["score"] == 0
        assert result["l_component"]["error"] == "No 52-week price history"
        assert result["l_component"]["rs_benchmark"] == "^GSPC"
        assert result["i_component"]["score"] == 0

    def test_profile_defaults_when_fields_missing(self):
        stock = strong_stock("AAA")
        stock["profile"] = [{"symbol": "AAA"}]
        result = sc.analyze_stock("AAA", FakeFMP({"AAA": stock}), market_result())
        assert result["company_name"] == "AAA"
        assert result["sector"] == "Unknown"
        assert result["market_cap"] == 0

    def test_disable_rs_skips_365_day_fetch_and_returns_neutral_l(self):
        client = FakeFMP({"AAA": strong_stock("AAA")})
        result = sc.analyze_stock(
            "AAA", client, market_result(), disable_rs=True, rs_benchmark="SPY"
        )
        l_comp = result["l_component"]
        assert l_comp["score"] == 50
        assert l_comp["skipped"] is True
        assert l_comp["rs_rating"] == "Skipped"
        assert l_comp["rs_benchmark"] == "SPY"
        assert l_comp["missing_periods"] == ["3m", "6m", "12m"]
        assert ("prices", "AAA", 365) not in client.calls
        assert ("prices", "AAA", 90) in client.calls

    def test_rs_benchmark_history_changes_l_score(self):
        stock = strong_stock("AAA")
        bench = price_history(365, 100.0, 5000.0)  # benchmark outruns the stock
        result = sc.analyze_stock(
            "AAA", FakeFMP({"AAA": stock}), market_result(), rs_benchmark_historical=bench
        )
        assert result["l_component"]["rel_12m"] < 0
        assert result["l_component"]["score"] < 60

    def test_missing_benchmark_history_applies_absolute_fallback_penalty(self):
        result = sc.analyze_stock(
            "AAA",
            FakeFMP({"AAA": strong_stock("AAA")}),
            market_result(),
            rs_benchmark_historical=None,
        )
        l_comp = result["l_component"]
        assert "unavailable" in l_comp["quality_warning"]
        assert l_comp["score"] == 80  # int(100 * 0.8)

    def test_exception_inside_analysis_returns_none(self, capsys):
        class Exploding(FakeFMP):
            def get_quote(self, symbol):
                raise RuntimeError("kaput")

        assert (
            sc.analyze_stock("AAA", Exploding({"AAA": strong_stock("AAA")}), market_result())
            is None
        )
        assert "Error: kaput" in capsys.readouterr().out


# ---------------------------------------------------------------- parse_arguments / main


def run_main(monkeypatch, argv, fake=None, real_client=False):
    monkeypatch.setattr(sys, "argv", ["screen_canslim.py", *argv])
    if not real_client:
        monkeypatch.setattr(sc, "FMPClient", lambda api_key=None: fake)
    sc.main()


def read_reports(out_dir):
    jsons = sorted(out_dir.glob("canslim_screener_*.json"))
    mds = sorted(out_dir.glob("canslim_screener_*.md"))
    assert len(jsons) == 1 and len(mds) == 1
    return json.loads(jsons[0].read_text(encoding="utf-8")), mds[0].read_text(encoding="utf-8")


class TestParseArguments:
    def test_defaults(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["screen_canslim.py"])
        args = sc.parse_arguments()
        assert args.api_key is None
        assert args.max_candidates == 40
        assert args.top == 20
        assert args.output_dir == "reports/"
        assert args.universe is None
        assert args.rs_benchmark == "^GSPC"
        assert args.disable_rs is False

    def test_all_options(self, monkeypatch):
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "screen_canslim.py",
                "--api-key", "k",
                "--max-candidates", "3",
                "--top", "2",
                "--output-dir", "out",
                "--universe", "A", "B",
                "--rs-benchmark", "QQQ",
                "--disable-rs",
            ],
        )  # fmt: skip
        args = sc.parse_arguments()
        assert (args.api_key, args.max_candidates, args.top) == ("k", 3, 2)
        assert args.output_dir == "out"
        assert args.universe == ["A", "B"]
        assert args.rs_benchmark == "QQQ"
        assert args.disable_rs is True

    def test_default_universe_has_40_unique_symbols(self):
        assert len(sc.DEFAULT_UNIVERSE) == 40
        assert len(set(sc.DEFAULT_UNIVERSE)) == 40


class TestMain:
    def test_missing_api_key_exits_1(self, monkeypatch, capsys):
        monkeypatch.delenv("FMP_API_KEY", raising=False)
        with pytest.raises(SystemExit) as exc:
            run_main(monkeypatch, [], real_client=True)
        assert exc.value.code == 1
        assert "FMP API key required" in capsys.readouterr().err

    def test_missing_sp500_quote_exits_1(self, monkeypatch, capsys, tmp_path):
        market = default_market()
        market["quotes"]["^GSPC"] = None
        fake = FakeFMP({}, market=market)
        with pytest.raises(SystemExit) as exc:
            run_main(monkeypatch, ["--output-dir", str(tmp_path)], fake)
        assert exc.value.code == 1
        assert "Unable to fetch S&P 500 data" in capsys.readouterr().err
        assert list(tmp_path.iterdir()) == []

    def test_full_run_writes_sorted_reports(self, monkeypatch, capsys, tmp_path):
        stocks = {"AAA": strong_stock("AAA"), "BBB": weak_stock("BBB")}
        fake = FakeFMP(stocks)
        out_dir = tmp_path / "nested" / "reports"
        run_main(
            monkeypatch,
            ["--universe", "BBB", "AAA", "MISSING", "--output-dir", str(out_dir)],
            fake,
        )
        report, md = read_reports(out_dir)
        meta = report["metadata"]
        assert meta["schema_version"] == "3.1"
        assert meta["components_included"] == ["C", "A", "N", "S", "L", "I", "M"]
        assert meta["candidates_analyzed"] == 2
        assert meta["universe_size"] == 3
        assert meta["screening_options"] == {"rs_benchmark": "^GSPC", "rs_disabled": False}
        assert meta["market_condition"]["trend"] == "strong_uptrend"
        assert meta["market_condition"]["M_score"] == 100
        symbols = [r["symbol"] for r in report["results"]]
        assert symbols == ["AAA", "BBB"]
        assert report["results"][0]["composite_score"] > report["results"][1]["composite_score"]
        assert report["summary"]["total_stocks"] == 2
        assert "### 1. AAA - AAA Inc" in md
        assert "**Stocks Analyzed:** 2" in md
        out = capsys.readouterr().out
        assert "Custom universe: 3 stocks" in out
        assert "Successfully analyzed 2 stocks" in out
        assert "1. AAA" in out
        assert "S&P 500: $103.00" in out
        assert "Trend: strong_uptrend" in out
        assert "M Score: 100/100" in out
        assert "Cache entries: 7" in out
        assert "Estimated calls: ~24 (3 market data calls + 3 stocks × 7 API calls each)" in out

    def test_top_limits_reports_but_not_count(self, monkeypatch, tmp_path):
        stocks = {s: strong_stock(s) for s in ("AAA", "BBB", "CCC")}
        run_main(
            monkeypatch,
            ["--universe", "AAA", "BBB", "CCC", "--top", "2", "--output-dir", str(tmp_path)],
            FakeFMP(stocks),
        )
        report, _ = read_reports(tmp_path)
        assert len(report["results"]) == 2
        assert report["metadata"]["candidates_analyzed"] == 3

    def test_max_candidates_truncates_custom_universe(self, monkeypatch, capsys, tmp_path):
        stocks = {s: strong_stock(s) for s in ("AAA", "BBB", "CCC")}
        run_main(
            monkeypatch,
            [
                "--universe",
                "AAA",
                "BBB",
                "CCC",
                "--max-candidates",
                "2",
                "--output-dir",
                str(tmp_path),
            ],
            FakeFMP(stocks),
        )
        report, _ = read_reports(tmp_path)
        assert report["metadata"]["universe_size"] == 2
        assert sorted(r["symbol"] for r in report["results"]) == ["AAA", "BBB"]
        assert "Custom universe: 2 stocks" in capsys.readouterr().out

    def test_default_universe_respects_max_candidates(self, monkeypatch, capsys, tmp_path):
        fake = FakeFMP({})
        run_main(monkeypatch, ["--max-candidates", "2", "--output-dir", str(tmp_path)], fake)
        profile_calls = [c[1] for c in fake.calls if c[0] == "profile"]
        assert profile_calls == sc.DEFAULT_UNIVERSE[:2]
        report, md = read_reports(tmp_path)
        assert report["results"] == []
        assert "Default universe (S&P 500 top 2): 2 stocks" in capsys.readouterr().out
        assert "## Top 0 CANSLIM Candidates" in md

    def test_custom_rs_benchmark_is_fetched_and_reported(self, monkeypatch, capsys, tmp_path):
        fake = FakeFMP({"AAA": strong_stock("AAA")})
        run_main(
            monkeypatch,
            ["--universe", "AAA", "--rs-benchmark", "SPY", "--output-dir", str(tmp_path)],
            fake,
        )
        assert ("prices", "SPY", 365) in fake.calls
        report, md = read_reports(tmp_path)
        assert report["metadata"]["screening_options"]["rs_benchmark"] == "SPY"
        assert report["results"][0]["l_component"]["rs_benchmark"] == "SPY"
        assert "**RS Benchmark:** SPY" in md
        out = capsys.readouterr().out
        assert "SPY historical data: 365 days" in out
        assert "Estimated calls: ~11 (4 market data calls + 1 stocks × 7 API calls each)" in out

    def test_custom_rs_benchmark_unavailable_falls_back_with_penalty(
        self, monkeypatch, capsys, tmp_path
    ):
        market = default_market()
        del market["history"]["SPY"]
        fake = FakeFMP({"AAA": strong_stock("AAA")}, market=market)
        run_main(
            monkeypatch,
            ["--universe", "AAA", "--rs-benchmark", "SPY", "--output-dir", str(tmp_path)],
            fake,
        )
        report, _ = read_reports(tmp_path)
        assert report["results"][0]["l_component"]["score"] == 80
        assert "SPY historical data unavailable" in capsys.readouterr().out

    def test_disable_rs_skips_benchmark_and_adjusts_call_estimate(
        self, monkeypatch, capsys, tmp_path
    ):
        fake = FakeFMP({"AAA": strong_stock("AAA")})
        run_main(
            monkeypatch,
            [
                "--universe",
                "AAA",
                "--rs-benchmark",
                "SPY",
                "--disable-rs",
                "--output-dir",
                str(tmp_path),
            ],
            fake,
        )
        assert ("prices", "SPY", 365) not in fake.calls
        report, md = read_reports(tmp_path)
        assert report["metadata"]["screening_options"]["rs_disabled"] is True
        assert report["results"][0]["l_component"]["skipped"] is True
        assert "DISABLED via --disable-rs" in md
        out = capsys.readouterr().out
        assert "--disable-rs set: L component will be fixed at neutral 50" in out
        assert (
            "Estimated calls: ~9 (3 market data calls + 1 stocks × 6 API calls each, --disable-rs)"
            in out
        )

    def test_bear_market_prints_warning_and_records_it(self, monkeypatch, capsys, tmp_path):
        market = default_market(price=90.0, vix=25.0)
        fake = FakeFMP({"AAA": strong_stock("AAA")}, market=market)
        run_main(monkeypatch, ["--universe", "AAA", "--output-dir", str(tmp_path)], fake)
        out = capsys.readouterr().out
        assert "WARNING: ⚠️ BEAR MARKET" in out
        assert "CANSLIM doesn't work in bear markets" in out
        assert "Distance from 50-EMA: -10.00%" in out
        report, md = read_reports(tmp_path)
        assert report["metadata"]["market_condition"]["M_score"] == 0
        assert "BEAR MARKET" in report["metadata"]["market_condition"]["warning"]
        assert report["results"][0]["threshold_check"]["recommendation"] == "avoid"
        assert "- **M Score:** 0/100" in md

    def test_missing_sp500_history_uses_neutral_market(self, monkeypatch, capsys, tmp_path):
        market = default_market()
        market["history"] = {}
        fake = FakeFMP({"AAA": strong_stock("AAA")}, market=market)
        run_main(monkeypatch, ["--universe", "AAA", "--output-dir", str(tmp_path)], fake)
        out = capsys.readouterr().out
        assert "^GSPC historical data unavailable" in out
        assert "Distance from 50-EMA: N/A (insufficient history)" in out
        assert "Trend: unknown" in out
        report, md = read_reports(tmp_path)
        # The run still publishes, but both artifacts say the M component is degraded.
        assert report["metadata"]["market_condition"] == {
            "trend": "unknown",
            "M_score": 50,
            "warning": None,
            "error": "Insufficient S&P 500 history for 50-day EMA",
        }
        assert (
            "- **⚠️ Data quality:** DEGRADED - M component: "
            "Insufficient S&P 500 history for 50-day EMA"
        ) in md

    def test_missing_vix_quote_is_tolerated(self, monkeypatch, tmp_path):
        market = default_market()
        market["quotes"]["^VIX"] = None
        run_main(
            monkeypatch,
            ["--universe", "AAA", "--output-dir", str(tmp_path)],
            FakeFMP({"AAA": strong_stock("AAA")}, market=market),
        )
        report, _ = read_reports(tmp_path)
        # strong uptrend (90) with no VIX bonus
        assert report["metadata"]["market_condition"]["M_score"] == 90

    @pytest.mark.parametrize("quote", [{"symbol": "^GSPC", "price": None}, {}])
    def test_sp500_quote_without_price_fails_closed(self, monkeypatch, tmp_path, capsys, quote):
        # Regression: main() indexed market_data["sp500_price"], which the error dict
        # omits, so a ^GSPC quote without a price crashed with KeyError. Like a missing
        # quote, it must stop with exit 1 and publish nothing, not rank candidates on
        # a fabricated neutral M score.
        market = default_market()
        market["quotes"]["^GSPC"] = [quote]
        with pytest.raises(SystemExit) as exc:
            run_main(
                monkeypatch,
                ["--universe", "AAA", "--output-dir", str(tmp_path)],
                FakeFMP({"AAA": strong_stock("AAA")}, market=market),
            )
        assert exc.value.code == 1
        assert "ERROR: Unable to determine market direction" in capsys.readouterr().err
        assert list(tmp_path.iterdir()) == []

    def test_api_key_flag_is_forwarded_to_client(self, monkeypatch, tmp_path):
        seen = {}

        def factory(api_key=None):
            seen["api_key"] = api_key
            return FakeFMP({})

        monkeypatch.setattr(sys, "argv", ["screen_canslim.py", "--api-key", "cli-key", "--max-candidates", "1", "--output-dir", str(tmp_path)])  # fmt: skip  # pragma: allowlist secret
        monkeypatch.setattr(sc, "FMPClient", factory)
        sc.main()
        assert seen["api_key"] == "cli-key"  # pragma: allowlist secret

    def test_script_guard_runs_main(self, monkeypatch, tmp_path):
        """Executing the file as __main__ without a key exits 1 via main()."""
        monkeypatch.delenv("FMP_API_KEY", raising=False)
        monkeypatch.setattr(sys, "argv", ["screen_canslim.py", "--output-dir", str(tmp_path)])
        with pytest.raises(SystemExit) as exc:
            runpy.run_path(os.path.abspath(sc.__file__), run_name="__main__")
        assert exc.value.code == 1
