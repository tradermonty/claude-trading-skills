"""Minimal HTTP-level tests for the FMP fetch layer (requests.get mocked, no network)."""

from unittest.mock import MagicMock

import analyze_downtrends as adt
import pytest
import requests

ROWS = [
    {"date": "2024-01-03", "open": 3, "high": 3, "low": 3, "close": 3, "volume": 30},
    {"date": "2024-01-02", "open": 2, "high": 2, "low": 2, "close": 2, "volume": 20},
]


def _resp(status, payload):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = payload
    return r


@pytest.fixture(autouse=True)
def reset_breaker(monkeypatch):
    monkeypatch.setattr(adt, "_endpoint_failures", {})


def test_historical_prices_sorted_ascending_from_v3_fallback(monkeypatch, capsys):
    # stable endpoint returns 403, v3 returns a "historical" payload.
    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append(url)
        if "stable" in url:
            return _resp(403, {})
        return _resp(200, {"historical": ROWS})

    monkeypatch.setattr(adt.requests, "get", fake_get)
    df = adt.fetch_historical_prices("k", "AAA", "2024-01-01", "2024-02-01")
    assert list(df["close"]) == [2, 3]
    assert list(df.columns) == ["date", "open", "high", "low", "close", "volume"]
    assert (
        adt._endpoint_failures["https://financialmodelingprep.com/stable/historical-price-eod/full"]
        == 1
    )
    assert calls[1].endswith("/historical-price-full/AAA")


def test_historical_stock_list_payload_matches_dash_dot_symbol(monkeypatch):
    payload = {"historicalStockList": [{"symbol": "BRK.B", "historical": ROWS}]}
    monkeypatch.setattr(adt.requests, "get", lambda *a, **k: _resp(200, payload))
    df = adt.fetch_historical_prices("k", "BRK-B", "2024-01-01", "2024-02-01")
    assert len(df) == 2


def test_empty_history_returns_empty_frame(monkeypatch):
    monkeypatch.setattr(adt.requests, "get", lambda *a, **k: _resp(200, {"historical": []}))
    assert adt.fetch_historical_prices("k", "AAA", "a", "b").empty


def test_all_endpoints_fail_prints_error_and_returns_empty(monkeypatch, capsys):
    def boom(*a, **k):
        raise requests.RequestException("down")

    monkeypatch.setattr(adt.requests, "get", boom)
    df = adt.fetch_historical_prices("k", "AAA", "a", "b")
    assert df.empty
    assert "Error fetching prices for AAA: all endpoints failed" in capsys.readouterr().err


def test_circuit_breaker_skips_tripped_endpoint(monkeypatch):
    stable = "https://financialmodelingprep.com/stable/historical-price-eod/full"
    monkeypatch.setattr(adt, "_endpoint_failures", {stable: adt._BREAKER_THRESHOLD})
    urls = []

    def fake_get(url, params=None, timeout=None):
        urls.append(url)
        return _resp(200, {"historical": ROWS})

    monkeypatch.setattr(adt.requests, "get", fake_get)
    adt.fetch_historical_prices("k", "AAA", "a", "b")
    assert urls == ["https://financialmodelingprep.com/api/v3/historical-price-full/AAA"]


def test_unrecognized_payload_counts_as_failure(monkeypatch):
    monkeypatch.setattr(adt.requests, "get", lambda *a, **k: _resp(200, {"foo": 1}))
    assert adt.fetch_historical_prices("k", "AAA", "a", "b").empty
    assert all(v == 1 for v in adt._endpoint_failures.values())


def test_stock_list_falls_back_after_request_error_and_bad_json(monkeypatch, capsys):
    bad_json = _resp(200, None)
    bad_json.json.side_effect = ValueError("not json")
    seq = iter([requests.RequestException("boom"), bad_json])

    def fake_get(*a, **k):
        item = next(seq)
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(adt.requests, "get", fake_get)
    assert adt.fetch_stock_list("k") == []
    err = capsys.readouterr().err
    assert (
        "Error fetching stock list (https://financialmodelingprep.com/stable/company-screener)"
        in err
    )
    assert "all screener endpoints failed" in err
