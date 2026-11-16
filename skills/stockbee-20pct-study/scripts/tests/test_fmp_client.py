import argparse
import importlib.util
import sys
import time
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "run_20pct_study.py"
spec = importlib.util.spec_from_file_location("run_20pct_study", SCRIPT)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)

BAR = {
    "symbol": "AAPL",
    "date": "2026-01-02",
    "open": 11,
    "high": 12,
    "low": 10,
    "close": 11.5,
    "volume": 2000,
}


def response(status, payload, text="body"):
    res = MagicMock()
    res.status_code = status
    res.text = text
    res.json.return_value = payload
    return res


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    # `time` is the process-wide module, so this also covers the shared client.
    monkeypatch.setattr(time, "sleep", lambda _: None)


def make_client(session, max_api_calls=10):
    client = mod.FMPClient(api_key="test", max_api_calls=max_api_calls)
    client.session = session
    return client


def urls_of(session):
    return [call[0][0] for call in session.get.call_args_list]


def stable(name):
    return f"https://financialmodelingprep.com/stable/{name}"


def patch_client_session(monkeypatch, session):
    real = mod.FMPClient

    def factory(**kw):
        client = real(**kw)
        client.session = session
        return client

    monkeypatch.setattr(mod, "FMPClient", factory)


def fetch_args(**kw):
    base = dict(
        api_key="test",  # pragma: allowlist secret
        max_api_calls=10,
        fmp_universe=False,
        symbols=["AAA"],
        max_symbols=5,
    )
    base.update(kw)
    return argparse.Namespace(**base)


def test_fmp_universe_uses_stable_company_screener():
    session = MagicMock()
    session.get.return_value = response(
        200,
        [
            {"symbol": "AAPL", "exchangeShortName": "NASDAQ", "price": 200},
            {"symbol": "SPY", "exchangeShortName": "NYSEARCA", "price": 600, "isEtf": True},
        ],
    )
    client = make_client(session)

    assert client.get_stock_list(limit=20) == ["AAPL"]
    assert urls_of(session) == [stable("company-screener")]


def test_universe_params_filters_and_cache():
    session = MagicMock()
    session.get.return_value = response(
        200,
        [
            {"symbol": "BRK.B", "exchangeShortName": "NYSE", "price": 5},
            {"symbol": "ZZZ", "exchangeShortName": "NASDAQ", "type": "adr", "price": 5},
            {"symbol": "LOW", "exchangeShortName": "NASDAQ", "price": 0},
            {"symbol": "OTC", "exchangeShortName": "OTC", "price": 5},
            {"symbol": "AAA", "exchange": "AMEX", "price": 5},
            "junk",
        ],
    )
    client = make_client(session)

    symbols = client.get_stock_list(limit=1)

    assert symbols == ["AAA"]
    assert client.get_stock_list(limit=1) is symbols
    assert session.get.call_count == 1
    params = session.get.call_args_list[0][1]["params"]
    assert params == {"exchange": "NASDAQ,NYSE,AMEX", "priceMoreThan": 0, "limit": 10000}


def test_universe_unlimited_sorted_and_deduped():
    session = MagicMock()
    session.get.return_value = response(
        200,
        [
            {"symbol": "MSFT", "exchangeShortName": "NASDAQ", "price": 3},
            {"symbol": "AAPL", "exchangeShortName": "NASDAQ", "price": 3},
            {"symbol": "AAPL", "exchangeShortName": "NASDAQ", "price": 3},
        ],
    )
    assert make_client(session).get_stock_list() == ["AAPL", "MSFT"]


def test_universe_never_falls_back_to_v3_and_uses_header_auth():
    session = MagicMock()
    session.get.return_value = response(402, {})
    client = make_client(session)

    assert client.get_stock_list(limit=5) == []

    assert urls_of(session) == [stable("company-screener")]
    assert "apikey" not in session.get.call_args_list[0][1]["params"]


def test_real_session_carries_header_auth():
    client = mod.FMPClient(api_key="hdrkey")
    assert client.session.headers["apikey"] == "hdrkey"  # pragma: allowlist secret


def test_fmp_historical_accepts_stable_flat_list_and_window():
    session = MagicMock()
    session.get.return_value = response(200, [BAR, dict(BAR, date="2026-01-01")])
    client = make_client(session)

    bars = client.get_historical_prices("aapl", days=2)

    assert [bar["date"] for bar in bars] == ["2026-01-01", "2026-01-02"]
    assert urls_of(session) == [stable("historical-price-eod/full")]
    params = session.get.call_args_list[0][1]["params"]
    assert params["symbol"] == "AAPL"
    span = date.fromisoformat(params["to"]) - date.fromisoformat(params["from"])
    assert span.days == 2 * 2 + 20
    assert client.get_historical_prices("AAPL", days=2) is bars


def test_historical_trims_to_days():
    rows = [dict(BAR, date=f"2026-01-0{i}") for i in range(1, 6)]
    session = MagicMock()
    session.get.return_value = response(200, rows)

    bars = make_client(session).get_historical_prices("AAPL", days=2)

    assert [b["date"] for b in bars] == ["2026-01-04", "2026-01-05"]


@pytest.mark.parametrize("answer", [response(200, []), response(402, {}), response(200, {"x": 1})])
def test_historical_never_requests_v3(answer):
    session = MagicMock()
    session.get.return_value = answer

    assert make_client(session).get_historical_prices("AAPL", days=2) == []

    assert len(urls_of(session)) == 1
    assert not any("/api/v3/" in url for url in urls_of(session))


def test_historical_malformed_json_retries_once():
    bad = response(200, None)
    bad.json.side_effect = ValueError("bad json")
    session = MagicMock()
    session.get.side_effect = [bad, response(200, [BAR])]
    client = make_client(session)

    bars = client.get_historical_prices("AAPL", days=1)

    assert [b["date"] for b in bars] == ["2026-01-02"]
    assert client.stats()["api_calls_made"] == 2


def test_rate_limit_sets_flag_after_one_retry():
    session = MagicMock()
    session.get.return_value = response(429, {})
    client = make_client(session)

    assert client.get_historical_prices("AAPL", days=1) == []

    assert client.rate_limit_reached is True
    assert len(urls_of(session)) == 2


def test_transport_exception_is_soft_and_redacted(capsys):
    session = MagicMock()
    session.get.side_effect = mod.requests.exceptions.ConnectionError("boom SECRETKEY123")
    client = mod.FMPClient(api_key="SECRETKEY123", max_api_calls=5)
    client.session = session

    assert client.get_historical_prices("AAPL", days=1) == []

    assert "SECRETKEY123" not in capsys.readouterr().err


@pytest.mark.parametrize("echo", ["SECRET+KEY/1", "SECRET%2BKEY%2F1", "SECRET%2bKEY%2f1"])
def test_error_body_key_echo_redacted(echo, capsys):
    session = MagicMock()
    session.get.return_value = response(500, {}, text=f"denied for {echo}")
    client = mod.FMPClient(api_key="SECRET+KEY/1", max_api_calls=5)
    client.session = session

    client.get_stock_list(limit=1)

    err = capsys.readouterr().err
    assert "denied for" in err
    assert "SECRET" not in err
    assert "***REDACTED***" in err


def test_no_circuit_breaker_after_empty_symbols():
    session = MagicMock()
    session.get.side_effect = [response(200, [])] * 5 + [response(200, [BAR])]
    client = make_client(session)

    for sym in ["A", "B", "C", "D", "E"]:
        assert client.get_historical_prices(sym, days=1) == []
    bars = client.get_historical_prices("AAPL", days=1)

    assert [b["date"] for b in bars] == ["2026-01-02"]
    assert len(urls_of(session)) == 6


def test_stats_keys_and_delegated_attributes():
    session = MagicMock()
    session.get.return_value = response(200, [BAR])
    client = make_client(session, max_api_calls=3)
    client.get_historical_prices("AAPL", days=1)

    assert client.stats() == {
        "api_calls_made": 1,
        "max_api_calls": 3,
        "budget_remaining": 2,
        "rate_limit_reached": False,
    }
    client.api_calls_made = 3
    client.max_api_calls = 4
    client.last_call_time = 1.0
    client.rate_limit_reached = True
    assert client._client.api_calls_made == 3
    assert client._client.max_api_calls == 4
    assert client._client.last_call_time == 1.0
    assert client._client.rate_limit_reached is True
    assert client.stats()["budget_remaining"] == 1
    assert client.stats()["rate_limit_reached"] is True
    assert client.session is session


def test_default_budget_is_500():
    assert mod.FMPClient(api_key="k").max_api_calls == 500


def test_shared_client_loaded_by_path_and_cached():
    shared = mod._load_shared_fmp()

    assert shared is mod._load_shared_fmp()
    assert shared.__name__ == "_stockbee_20pct_study_fmp_client"
    assert sys.modules[shared.__name__] is shared


def test_fmp_requires_key_for_live_path(monkeypatch):
    monkeypatch.delenv("FMP_API_KEY", raising=False)

    with pytest.raises(ValueError, match="FMP API key required"):
        mod.FMPClient()


def test_explicit_key_beats_env(monkeypatch):
    monkeypatch.setenv("FMP_API_KEY", "envkey")

    assert mod.FMPClient(api_key="argkey").api_key == "argkey"  # pragma: allowlist secret
    assert mod.FMPClient().api_key == "envkey"  # pragma: allowlist secret


def test_missing_requests_still_raises(monkeypatch):
    monkeypatch.setattr(mod, "requests", None)

    with pytest.raises(RuntimeError, match="requests library not found"):
        mod.FMPClient(api_key="k")


def test_budget_exhaustion_in_stock_list_raises_local_exception():
    client = mod.FMPClient(api_key="test", max_api_calls=0)

    with pytest.raises(mod.ApiCallBudgetExceeded):
        client.get_stock_list(limit=1)


def test_budget_exhaustion_in_history_raises_local_exception():
    client = mod.FMPClient(api_key="test", max_api_calls=0)

    with pytest.raises(mod.ApiCallBudgetExceeded):
        client.get_historical_prices("AAPL", days=1)


def test_fetch_prices_budget_exhaustion_mid_loop(monkeypatch):
    session = MagicMock()
    session.get.return_value = response(200, [dict(BAR, symbol="AAA")])
    patch_client_session(monkeypatch, session)

    with pytest.raises(mod.ApiCallBudgetExceeded):
        mod.fetch_prices_from_fmp(fetch_args(symbols=["AAA", "BBB"], max_api_calls=1), days=1)

    assert session.get.call_count == 1


def test_fetch_prices_budget_exhaustion_from_universe():
    with pytest.raises(mod.ApiCallBudgetExceeded):
        mod.fetch_prices_from_fmp(fetch_args(fmp_universe=True, max_api_calls=0), days=1)


def test_fetch_prices_propagates_runtime_error(monkeypatch):
    def boom(*_a, **_k):
        raise RuntimeError("tzdata missing")

    monkeypatch.setattr(mod._load_shared_fmp(), "_et_today", boom)
    session = MagicMock()
    patch_client_session(monkeypatch, session)

    with pytest.raises(RuntimeError, match="tzdata"):
        mod.fetch_prices_from_fmp(fetch_args(), days=1)

    session.get.assert_not_called()


def test_fetch_prices_skips_symbol_with_data_error(monkeypatch, capsys):
    class Flaky:
        def __init__(self, **kw):
            pass

        def get_historical_prices(self, symbol, days=320):
            if symbol == "BAD":
                raise ValueError("garbled")
            return [dict(BAR, symbol=symbol)]

        def stats(self):
            return {}

    monkeypatch.setattr(mod, "FMPClient", Flaky)

    prices, _ = mod.fetch_prices_from_fmp(fetch_args(symbols=["BAD", "OK"]), days=1)

    assert list(prices) == ["OK"]
    assert "failed to fetch BAD" in capsys.readouterr().err


def test_shared_quote_row_and_non_list_rows(capsys):
    shared_client = make_client(MagicMock())._client
    shared_client.session.get.side_effect = [
        response(200, [{"symbol": "AAPL", "price": 1}]),
        response(200, []),
        response(200, {"Error Message": "nope"}),
        response(200, {"Error Message": "nope"}),
    ]

    assert shared_client.fetch_quote_row("AAPL") == {"symbol": "AAPL", "price": 1}
    assert shared_client.fetch_quote_row("AAPL") is None
    assert shared_client.fetch_screener_rows({"limit": 1}) is None
    assert "non-list" in capsys.readouterr().err
    assert shared_client.fetch_eod_rows("AAPL", 1, quiet=True) is None


def test_shared_malformed_json_twice_fails_soft(capsys):
    bad = response(200, None)
    bad.json.side_effect = ValueError("bad json")
    session = MagicMock()
    session.get.return_value = bad
    client = make_client(session)

    assert client.get_stock_list(limit=1) == []

    assert session.get.call_count == 2
    assert "invalid JSON" in capsys.readouterr().err


def test_shared_rate_limit_short_circuits_later_calls():
    session = MagicMock()
    session.get.return_value = response(429, {})
    client = make_client(session)

    client.get_historical_prices("AAA", days=1)
    calls = session.get.call_count
    assert client.get_historical_prices("BBB", days=1) == []

    assert session.get.call_count == calls


def test_shared_et_today_helpers():
    from datetime import datetime, timezone

    shared = mod._load_shared_fmp()
    instant = datetime(2026, 1, 3, 2, 0, tzinfo=timezone.utc)

    assert shared._et_today(instant) == date(2026, 1, 2)
    assert isinstance(shared._et_today(), date)
    assert isinstance(make_client(MagicMock())._client.et_today(), date)
    with pytest.raises(ValueError):
        shared._et_today(datetime(2026, 1, 3))


def test_shared_et_today_missing_tzdata(monkeypatch):
    shared = mod._load_shared_fmp()

    def missing(_name):
        raise shared.ZoneInfoNotFoundError("x")

    monkeypatch.setattr(shared, "ZoneInfo", missing)

    with pytest.raises(RuntimeError, match="tzdata"):
        shared._et_today()


def test_shared_api_stats_and_redaction_helper():
    shared = mod._load_shared_fmp()
    client = make_client(MagicMock(), max_api_calls=4)

    assert client._client.get_api_stats()["budget_remaining"] == 4
    assert "REDACTED" in shared._redact_key("https://x?apikey=abc&y=1")


def test_shared_core_historical_prices_stable_shape():
    shared_client = make_client(MagicMock())._client
    shared_client.session.get.return_value = response(200, [BAR, dict(BAR, date="2026-01-01")])

    rows = shared_client.get_historical_prices("AAPL", days=2)

    assert [r["date"] for r in rows] == ["2026-01-02", "2026-01-01"]
    assert shared_client.get_historical_prices("AAPL", days=2) is rows
