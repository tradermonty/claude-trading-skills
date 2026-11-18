import json

import pytest
from app import alpaca


class FakeResponse:
    def __init__(self, payload):
        self._payload = json.dumps(payload).encode()

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_not_configured_without_keys():
    client = alpaca.from_env({})
    assert client is None


def test_paper_is_default_base_url():
    client = alpaca.from_env({"ALPACA_API_KEY": "k", "ALPACA_SECRET_KEY": "s"})
    assert client.base_url == "https://paper-api.alpaca.markets"
    assert client.paper is True


def test_alpaca_env_live_switches_base_url():
    client = alpaca.from_env(
        {"ALPACA_API_KEY": "k", "ALPACA_SECRET_KEY": "s", "ALPACA_ENV": "LIVE"}
    )
    assert client.base_url == "https://api.alpaca.markets"
    assert client.paper is False


@pytest.mark.parametrize("value", ["paper", "", "typo", "lve"])
def test_anything_but_live_stays_paper(value):
    env = {"ALPACA_API_KEY": "k", "ALPACA_SECRET_KEY": "s", "ALPACA_ENV": value}
    assert alpaca.from_env(env).paper is True


def test_alpaca_env_wins_over_legacy_flag():
    env = {
        "ALPACA_API_KEY": "k",
        "ALPACA_SECRET_KEY": "s",
        "ALPACA_ENV": "paper",
        "ALPACA_PAPER": "false",
    }
    assert alpaca.from_env(env).paper is True


def test_live_base_url_only_when_paper_false():
    client = alpaca.from_env(
        {"ALPACA_API_KEY": "k", "ALPACA_SECRET_KEY": "s", "ALPACA_PAPER": "false"}
    )
    assert client.base_url == "https://api.alpaca.markets"


def test_only_get_requests_are_sent(monkeypatch):
    seen = []

    def fake_urlopen(req, timeout):
        seen.append((req.get_method(), req.full_url, req.headers, timeout))
        return FakeResponse({"equity": "100"})

    monkeypatch.setattr(alpaca, "urlopen", fake_urlopen)
    client = alpaca.AlpacaReadOnly("k", "s", paper=True)
    assert client.account() == {"equity": "100"}
    method, url, headers, timeout = seen[0]
    assert method == "GET"
    assert url == "https://paper-api.alpaca.markets/v2/account"
    assert headers["Apca-api-key-id"] == "k"
    assert timeout == 10


def test_client_has_no_order_methods():
    client = alpaca.AlpacaReadOnly("k", "s")
    for name in ("submit_order", "order", "orders", "post", "cancel", "close_position"):
        assert not hasattr(client, name)


def test_errors_are_wrapped(monkeypatch):
    def boom(req, timeout):
        raise OSError("network down")

    monkeypatch.setattr(alpaca, "urlopen", boom)
    with pytest.raises(alpaca.AlpacaError):
        alpaca.AlpacaReadOnly("k", "s").positions()


def test_snapshot_caches(monkeypatch):
    calls = []

    def fake_urlopen(req, timeout):
        calls.append(req.full_url)
        return FakeResponse([] if req.full_url.endswith("positions") else {"equity": "1"})

    monkeypatch.setattr(alpaca, "urlopen", fake_urlopen)
    client = alpaca.AlpacaReadOnly("k", "s", cache_seconds=60)
    first = client.snapshot()
    second = client.snapshot()
    assert first == second
    assert len(calls) == 2  # account + positions, fetched once


def test_snapshot_reports_error(monkeypatch):
    def boom(req, timeout):
        raise OSError("nope")

    monkeypatch.setattr(alpaca, "urlopen", boom)
    snap = alpaca.AlpacaReadOnly("k", "s").snapshot()
    assert snap["error"]
    assert snap["account"] is None
