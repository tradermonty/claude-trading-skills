"""Tests for the data client's caching, rate limits, and snapshot validation."""

import json
from datetime import datetime, timedelta, timezone

import data_client
import pytest
from data_client import DataClient, load_snapshot_from_json


class _FakeResponse:
    def __init__(self, status_code, payload=None, headers=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


def _client(tmp_path):
    return DataClient(str(tmp_path), quiet=True)


def test_get_retries_on_429_then_succeeds(tmp_path, monkeypatch):
    responses = [_FakeResponse(429), _FakeResponse(429), _FakeResponse(200, {"ok": 1})]
    monkeypatch.setattr(
        data_client,
        "requests",
        type(
            "R",
            (),
            {
                "get": staticmethod(lambda url, params=None, timeout=None: responses.pop(0)),
            },
        ),
    )
    sleeps = []
    monkeypatch.setattr(data_client.time, "sleep", sleeps.append)
    assert _client(tmp_path)._get("http://x") == {"ok": 1}
    assert len(sleeps) == 2
    assert sleeps[1] > sleeps[0]  # exponential backoff


def test_get_respects_retry_after_header(tmp_path, monkeypatch):
    responses = [
        _FakeResponse(429, headers={"Retry-After": "3"}),
        _FakeResponse(200, {"ok": 1}),
    ]
    monkeypatch.setattr(
        data_client,
        "requests",
        type(
            "R",
            (),
            {
                "get": staticmethod(lambda url, params=None, timeout=None: responses.pop(0)),
            },
        ),
    )
    sleeps = []
    monkeypatch.setattr(data_client.time, "sleep", sleeps.append)
    _client(tmp_path)._get("http://x")
    assert sleeps == [3.0]


def test_get_raises_after_max_retries(tmp_path, monkeypatch):
    monkeypatch.setattr(
        data_client,
        "requests",
        type(
            "R",
            (),
            {
                "get": staticmethod(lambda url, params=None, timeout=None: _FakeResponse(429)),
            },
        ),
    )
    monkeypatch.setattr(data_client.time, "sleep", lambda _s: None)
    with pytest.raises(RuntimeError):
        _client(tmp_path)._get("http://x")


def test_universe_cache_is_scoped_by_top_n(tmp_path, monkeypatch):
    raw = [
        {"id": "bitcoin", "symbol": "btc"},
        {"id": "ethereum", "symbol": "eth"},
        {"id": "solana", "symbol": "sol"},
    ]
    calls = []

    def fake_get(_url, params=None):
        calls.append(params)
        return raw

    small = DataClient(str(tmp_path), top_n=1, quiet=True)
    large = DataClient(str(tmp_path), top_n=2, quiet=True)
    monkeypatch.setattr(small, "_get", fake_get)
    monkeypatch.setattr(large, "_get", fake_get)

    assert [coin["symbol"] for coin in small.fetch_universe()] == ["BTC"]
    assert [coin["symbol"] for coin in large.fetch_universe()] == ["BTC", "ETH"]
    assert len(calls) == 2


def test_funding_cache_is_scoped_by_symbol_cohort(tmp_path, monkeypatch):
    client = _client(tmp_path)
    calls = []

    def fake_get(_url, params=None):
        calls.append(params)
        return [
            {"symbol": "BTCUSDT", "lastFundingRate": "0.0001"},
            {"symbol": "ETHUSDT", "lastFundingRate": "0.0002"},
        ]

    monkeypatch.setattr(client, "_get", fake_get)

    assert client.fetch_funding(["BTC"]) == {"BTCUSDT": 0.0001}
    assert client.fetch_funding(["ETH"]) == {"ETHUSDT": 0.0002}
    assert len(calls) == 2


def test_dominance_history_requires_contiguous_calendar_days(tmp_path):
    client = _client(tmp_path)
    today = datetime.now(timezone.utc).date()
    history = {(today - timedelta(days=offset)).isoformat(): 50.0 + offset for offset in range(31)}
    path = tmp_path / "dominance_history.json"
    path.write_text(json.dumps(history))

    series = client.load_dominance_series()
    assert len(series) == 31
    assert series[0] == 80.0
    assert series[-1] == 50.0

    del history[(today - timedelta(days=12)).isoformat()]
    path.write_text(json.dumps(history))
    assert client.load_dominance_series() == []


def test_snapshot_validation_requires_btc(tmp_path):
    bad = tmp_path / "snap.json"
    bad.write_text('{"series": {"ETH": [1, 2]}, "dominance_series": [], "funding": {}}')
    with pytest.raises(ValueError):
        load_snapshot_from_json(str(bad))


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"series": [], "dominance_series": [], "funding": {}},
        {"series": {"BTC": [float("nan")]}, "dominance_series": [], "funding": {}},
        {"series": {"BTC": [float("inf")]}, "dominance_series": [], "funding": {}},
        {"series": {"BTC": [0.0]}, "dominance_series": [], "funding": {}},
        {"series": {"BTC": [-1.0]}, "dominance_series": [], "funding": {}},
        {"series": {"BTC": ["1.0"]}, "dominance_series": [], "funding": {}},
        {"series": {"BTC": [1.0]}, "dominance_series": [float("nan")], "funding": {}},
        {"series": {"BTC": [1.0]}, "dominance_series": [101.0], "funding": {}},
        {"series": {"BTC": [1.0]}, "dominance_series": [], "funding": {"BTC": None}},
        {"series": {"BTC": [1.0]}, "dominance_series": [], "funding": {"BTC": float("inf")}},
    ],
)
def test_snapshot_validation_rejects_malformed_or_non_finite_market_data(tmp_path, payload):
    bad = tmp_path / "snap.json"
    bad.write_text(json.dumps(payload))

    with pytest.raises(ValueError):
        load_snapshot_from_json(str(bad))


def test_load_snapshot_rejects_finite_but_impossible_funding_rate(tmp_path):
    bad = tmp_path / "bad-funding.json"
    bad.write_text(
        json.dumps(
            {
                "series": {"BTC": [100.0]},
                "dominance_series": [],
                "funding": {"BTCUSDT": 1e308, "ETHUSDT": 1e308},
            }
        )
    )

    with pytest.raises(ValueError, match="funding.*between"):
        load_snapshot_from_json(str(bad))


def test_build_snapshot_degrades_when_dominance_fetch_fails(tmp_path, monkeypatch):
    client = _client(tmp_path)
    monkeypatch.setattr(client, "fetch_universe", lambda: [{"id": "bitcoin", "symbol": "BTC"}])
    monkeypatch.setattr(client, "fetch_history", lambda _coin_id: [100.0] * 220)
    monkeypatch.setattr(
        client,
        "fetch_dominance",
        lambda: (_ for _ in ()).throw(RuntimeError("temporary failure")),
    )
    monkeypatch.setattr(client, "fetch_funding", lambda _symbols: {})

    snapshot = client.build_snapshot()

    assert snapshot["dominance_series"] == []
    assert snapshot["series"]["BTC"] == [100.0] * 220


def test_build_snapshot_skips_malformed_optional_alt_history(tmp_path, monkeypatch):
    client = _client(tmp_path)
    monkeypatch.setattr(
        client,
        "fetch_universe",
        lambda: [
            {"id": "bitcoin", "symbol": "BTC"},
            {"id": "bad-coin", "symbol": "BAD"},
        ],
    )
    monkeypatch.setattr(
        client,
        "fetch_history",
        lambda coin_id: [100.0] * 365 if coin_id == "bitcoin" else [],
    )
    monkeypatch.setattr(client, "fetch_dominance", lambda: 55.0)
    monkeypatch.setattr(client, "load_dominance_series", lambda: [])
    monkeypatch.setattr(client, "fetch_funding", lambda _symbols: {})

    snapshot = client.build_snapshot()

    assert set(snapshot["series"]) == {"BTC"}


def test_build_snapshot_skips_invalid_optional_funding_rows(tmp_path, monkeypatch):
    client = _client(tmp_path)
    monkeypatch.setattr(client, "fetch_universe", lambda: [{"id": "bitcoin", "symbol": "BTC"}])
    monkeypatch.setattr(client, "fetch_history", lambda _coin_id: [100.0] * 365)
    monkeypatch.setattr(client, "fetch_dominance", lambda: 55.0)
    monkeypatch.setattr(client, "load_dominance_series", lambda: [])
    monkeypatch.setattr(
        client,
        "fetch_funding",
        lambda _symbols: {"BTCUSDT": float("nan"), "ETHUSDT": 0.0},
    )

    snapshot = client.build_snapshot()

    assert snapshot["funding"] == {"ETHUSDT": 0.0}


def test_build_snapshot_degrades_invalid_optional_dominance_values(tmp_path, monkeypatch):
    client = _client(tmp_path)
    monkeypatch.setattr(client, "fetch_universe", lambda: [{"id": "bitcoin", "symbol": "BTC"}])
    monkeypatch.setattr(client, "fetch_history", lambda _coin_id: [100.0] * 365)
    monkeypatch.setattr(client, "fetch_dominance", lambda: 55.0)
    monkeypatch.setattr(client, "load_dominance_series", lambda: [float("nan")])
    monkeypatch.setattr(client, "fetch_funding", lambda _symbols: {})

    snapshot = client.build_snapshot()

    assert snapshot["dominance_series"] == []
