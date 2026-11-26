"""Endpoint circuit breaker and skip reporting in this skill's own fmp_client (#844).

Synthetic responses only: the session transport is replaced, no network is used.
"""

import importlib.util
from pathlib import Path

import pytest

CLIENT_PATH = Path(__file__).resolve().parents[1] / "fmp_client.py"
KEY = "SYNTHETIC_TEST_KEY"  # pragma: allowlist secret


def _load():
    spec = importlib.util.spec_from_file_location("options_fmp_client_under_test", CLIENT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Response:
    text = ""

    def __init__(self, status_code=200, symbol=None):
        self.status_code = status_code
        self.symbol = symbol

    def json(self):
        if self.status_code != 200:
            raise ValueError("no json")
        return {"symbol": self.symbol, "historical": [{"date": "2026-01-09", "close": 10}]}


def _symbol_from(url, kwargs):
    if "symbol" in (kwargs.get("params") or {}):
        return kwargs["params"]["symbol"]
    return url.rstrip("/").rsplit("/", 1)[-1]


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda _: None)
    instance = _load().FMPClient(api_key=KEY)
    instance.RATE_LIMIT_DELAY = 0
    instance.max_retries = 0
    return instance


def _install(monkeypatch, client, stable_status, legacy=lambda url, kwargs: None):
    """Stable endpoints answer ``stable_status``; the legacy one is served or scripted."""

    def get(url, **kwargs):
        if "/stable/" in url:
            return Response(stable_status)
        scripted = legacy(url, kwargs)
        if scripted is not None:
            return scripted
        return Response(200, _symbol_from(url, kwargs))

    monkeypatch.setattr(client.session, "get", get)


def _trip_breaker(client, status):
    for i in range(client._ENDPOINT_FAILURE_THRESHOLD):
        client.get_historical_prices(f"T{i}")


@pytest.mark.parametrize("status", [500, 503])
def test_provider_outage_trips_breaker(client, monkeypatch, status):
    _install(monkeypatch, client, status)
    _trip_breaker(client, status)
    assert client._disabled_endpoints
    assert client.get_endpoint_report()["disabled_endpoints"]


@pytest.mark.parametrize("status", [400, 404])
def test_per_symbol_4xx_does_not_trip_breaker(client, monkeypatch, status):
    _install(monkeypatch, client, status)
    _trip_breaker(client, status)
    assert not client._disabled_endpoints
    assert client.get_endpoint_report()["skipped_symbols"] == []


def test_transport_exception_counts_toward_breaker(client, monkeypatch):
    mod = _load()

    def get(url, **kwargs):
        raise mod.requests.exceptions.ConnectionError("synthetic outage")

    monkeypatch.setattr(client.session, "get", get)
    for i in range(client._ENDPOINT_FAILURE_THRESHOLD):
        assert client.get_historical_prices(f"X{i}") is None
    assert client._disabled_endpoints


def test_failure_kind_classification(client):
    for kind, counts in [
        ("transport", True),
        ("http_429", True),
        ("http_5xx", True),
        ("http_4xx", False),
        ("response_contract", False),
        (None, False),
    ]:
        client._last_failure_kind = kind
        assert client._failure_kind_counts_toward_breaker() is counts


def test_unserved_symbol_is_reported_once_with_warning(client, monkeypatch, capsys):
    _install(monkeypatch, client, 503, legacy=lambda url, kwargs: Response(503))
    _trip_breaker(client, 503)
    assert client._disabled_endpoints
    capsys.readouterr()
    assert client.get_historical_prices("SKIPME") is None
    assert client.get_historical_prices("SKIPME") is None
    entries = client.get_endpoint_report()["skipped_symbols"]
    assert entries and all(entry.endswith(":SKIPME") for entry in entries)
    assert len(entries) == len(set(entries))
    assert capsys.readouterr().err.count("skipping SKIPME") == len(entries)


def test_fallback_served_symbol_is_not_reported(client, monkeypatch, capsys):
    _install(monkeypatch, client, 503)
    for i in range(client._ENDPOINT_FAILURE_THRESHOLD):
        assert client.get_historical_prices(f"S{i}") is not None
    assert client._disabled_endpoints
    capsys.readouterr()
    assert client.get_historical_prices("DEF") is not None
    assert client.get_endpoint_report()["skipped_symbols"] == []
    assert "skipping" not in capsys.readouterr().err


def test_rate_limit_end_is_not_reported_as_breaker_skip(client, monkeypatch, capsys):
    _install(
        monkeypatch,
        client,
        503,
        legacy=lambda url, kwargs: Response(429) if "RATED" in url else None,
    )
    for i in range(client._ENDPOINT_FAILURE_THRESHOLD):
        assert client.get_historical_prices(f"S{i}") is not None
    capsys.readouterr()
    assert client.get_historical_prices("RATED") is None
    assert client.rate_limit_reached
    assert client.get_endpoint_report()["skipped_symbols"] == []
    assert "skipping" not in capsys.readouterr().err


def test_requests_after_rate_limit_fail_fast_without_network(client, monkeypatch):
    client.rate_limit_reached = True
    calls = []
    monkeypatch.setattr(client.session, "get", lambda *a, **kw: calls.append(a))
    assert client.get_historical_prices("ANY") is None
    assert calls == []
    assert client._last_error == "daily rate limit already reached"


def test_success_resets_failure_count(client, monkeypatch):
    state = {"stable": 503}

    def get(url, **kwargs):
        if "/stable/" in url:
            return Response(state["stable"], _symbol_from(url, kwargs))
        return Response(200, _symbol_from(url, kwargs))

    monkeypatch.setattr(client.session, "get", get)
    client.get_historical_prices("A0")
    assert any(client._endpoint_failures.values())
    state["stable"] = 200
    assert client.get_historical_prices("A1") is not None
    assert not client._disabled_endpoints


def test_http_429_exhausts_retries_and_sets_rate_limit(client, monkeypatch):
    _install(monkeypatch, client, 429)
    assert client.get_historical_prices("LIM") is None
    assert client.rate_limit_reached
