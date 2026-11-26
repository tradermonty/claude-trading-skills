"""Raw endpoint drift and corrupt caches must not become valid market evidence."""

import json
from pathlib import Path

import data_client
import pytest
from data_client import DataClient

BAD_NUMBERS = [None, True, "12", 0, -1, float("nan"), float("inf"), 10**400]


@pytest.fixture(autouse=True)
def no_request_delay(monkeypatch):
    monkeypatch.setattr(data_client.time, "sleep", lambda _: None)


@pytest.mark.parametrize("value", BAD_NUMBERS)
def test_invalid_price_never_reaches_cache(tmp_path, monkeypatch, value):
    client = DataClient(str(tmp_path), quiet=True)
    monkeypatch.setattr(client, "_get", lambda *a, **k: {"prices": [[1000, value]]})
    with pytest.raises(ValueError, match="COINGECKO_MARKET_CHART"):
        client.fetch_history("bitcoin")
    assert not Path(client._cache_path("hist_bitcoin")).exists()


@pytest.mark.parametrize("value", BAD_NUMBERS)
def test_invalid_timestamp_in_singleton_is_rejected(tmp_path, monkeypatch, value):
    client = DataClient(str(tmp_path), quiet=True)
    monkeypatch.setattr(client, "_get", lambda *a, **k: {"prices": [[value, 100]]})
    with pytest.raises(ValueError, match="COINGECKO_MARKET_CHART"):
        client.fetch_history("bitcoin")
    assert not Path(client._cache_path("hist_bitcoin")).exists()


@pytest.mark.parametrize("value", BAD_NUMBERS + [100.1])
def test_invalid_global_never_updates_cache_or_history(tmp_path, monkeypatch, value):
    client = DataClient(str(tmp_path), quiet=True)
    history = tmp_path / "dominance_history.json"
    original = '{"2026-01-01": 50}'
    history.write_text(original)
    monkeypatch.setattr(
        client, "_get", lambda *a, **k: {"data": {"market_cap_percentage": {"btc": value}}}
    )
    with pytest.raises(ValueError, match="COINGECKO_GLOBAL"):
        client.fetch_dominance()
    assert not Path(client._cache_path("dominance_now")).exists()
    assert history.read_text() == original


@pytest.mark.parametrize(
    "name,payload",
    [
        ("hist_bitcoin", None),
        ("hist_bitcoin", []),
        ("hist_bitcoin", [float("nan")]),
        ("dominance_now", None),
        ("dominance_now", 0),
        ("dominance_now", True),
        ("dominance_now", float("inf")),
    ],
)
def test_corrupt_cache_is_preserved_without_network(tmp_path, monkeypatch, name, payload):
    client = DataClient(str(tmp_path), quiet=True)
    path = Path(client._cache_path(name))
    original = json.dumps(payload)
    path.write_text(original)
    monkeypatch.setattr(
        client, "_get", lambda *a, **k: pytest.fail("invalid cache must not refetch")
    )
    with pytest.raises(ValueError, match="COINGECKO_"):
        client.fetch_history("bitcoin") if name.startswith("hist") else client.fetch_dominance()
    assert path.read_text() == original


def test_recorded_endpoints_reach_consumer_and_healthy_cache(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[4]
    contracts = root / "config/provider-contracts/coingecko"
    chart = json.loads((contracts / "market-chart.v1.json").read_text())
    global_contract = json.loads((contracts / "global.v1.json").read_text())
    client = DataClient(str(tmp_path), quiet=True)
    monkeypatch.setattr(
        client,
        "_get",
        lambda url, params=None, **kw: (
            chart["response_fixture"]
            if "market_chart" in url
            else global_contract["response_fixture"]
        ),
    )
    closes = [row["price"] for row in chart["fixture"]]
    dom = global_contract["fixture"][0]["btc_dominance"]
    assert client.fetch_history("bitcoin") == closes
    assert client.fetch_dominance() == dom
    history = json.loads((tmp_path / "dominance_history.json").read_text())
    assert list(history.values()) == [dom]
    monkeypatch.setattr(client, "_get", lambda *a, **kw: pytest.fail("warm cache must not fetch"))
    assert client.fetch_history("bitcoin") == closes
    assert client.fetch_dominance() == dom


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"renamed_prices": [[1, 2]]},
        {"prices": []},
        {"prices": None},
        {"prices": [[1]]},
        {"prices": [[1, 2, 3]]},
        {"prices": [[2, 3], [1, 4]]},
        {"prices": [[1, 3], [1, 4]]},
    ],
)
def test_bad_chart_shapes_never_cache_partial_prefix(tmp_path, monkeypatch, payload):
    client = DataClient(str(tmp_path), quiet=True)
    monkeypatch.setattr(client, "_get", lambda *a, **k: payload)
    with pytest.raises(ValueError, match="COINGECKO_MARKET_CHART"):
        client.fetch_history("bitcoin")
    assert not Path(client._cache_path("hist_bitcoin")).exists()


@pytest.mark.parametrize("name", ["hist_bitcoin", "dominance_now"])
def test_truncated_cache_is_preserved(tmp_path, monkeypatch, name):
    client = DataClient(str(tmp_path), quiet=True)
    path = Path(client._cache_path(name))
    path.write_bytes(b'{"truncated":')
    monkeypatch.setattr(client, "_get", lambda *a, **k: pytest.fail("network"))
    with pytest.raises(ValueError, match="COINGECKO_"):
        client.fetch_history("bitcoin") if name.startswith("hist") else client.fetch_dominance()
    assert path.read_bytes() == b'{"truncated":'


def test_invalid_btc_history_exits_actual_cli_without_report(tmp_path, monkeypatch, capsys):
    import sys

    import crypto_regime_analyzer as cli

    def get(self, url, params=None):
        if url.endswith("/coins/markets"):
            return [{"id": "bitcoin", "symbol": "btc"}]
        if "market_chart" in url:
            return {"prices": [[1000, float("nan")]]}
        if url.endswith("/global"):
            return {"data": {"market_cap_percentage": {"btc": 55}}}
        return []

    monkeypatch.setattr(DataClient, "_get", get)
    output = tmp_path / "reports"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "crypto_regime_analyzer.py",
            "--cache-dir",
            str(tmp_path / "cache"),
            "--output-dir",
            str(output),
        ],
    )
    assert cli.main() == 1
    assert not output.exists() or not list(output.iterdir())
    assert "BTC" in capsys.readouterr().err


def test_optional_dominance_failure_remains_explicitly_unavailable(tmp_path, monkeypatch):
    from crypto_regime_analyzer import run_analysis

    def get(url, params=None):
        if url.endswith("/coins/markets"):
            return [{"id": "bitcoin", "symbol": "btc"}]
        if "market_chart" in url:
            return {"prices": [[i + 1, 100 + i] for i in range(220)]}
        if url.endswith("/global"):
            return {"data": {"market_cap_percentage": {"btc": True}}}
        return []

    client = DataClient(str(tmp_path), quiet=True)
    monkeypatch.setattr(client, "_get", get)
    snapshot = client.build_snapshot()
    assert snapshot["dominance_series"] == []
    result = run_analysis(snapshot)
    assert result["components"]["dominance"]["data_available"] is False
    assert not Path(client._cache_path("dominance_now")).exists()
    assert not (tmp_path / "dominance_history.json").exists()
