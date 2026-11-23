"""CoinGecko HTTP-200 drift must not become a cached empty universe (#332)."""

import json
from pathlib import Path

import pytest
from data_client import DataClient

CONTRACT = (
    Path(__file__).resolve().parents[4]
    / "config/provider-contracts/coingecko/coins-markets.v1.json"
)


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {},
        None,
        [None],
        [{"id": "bitcoin"}],
        [{"id": "bitcoin", "symbol": None}],
        [{"id": 1, "symbol": "btc"}],
        [{"id": "bitcoin", "symbol": "  "}],
        [{"id": "", "symbol": "btc"}],
        [{"id": "../escape", "symbol": "btc"}],
        [{"id": "bitcoin\n", "symbol": "btc"}],
    ],
)
def test_bad_live_universe_is_not_cached(tmp_path, monkeypatch, payload):
    client = DataClient(str(tmp_path), quiet=True)
    monkeypatch.setattr(client, "_get", lambda *a, **k: payload)
    with pytest.raises(ValueError, match="COINGECKO_UNIVERSE"):
        client.fetch_universe()
    assert not Path(client._cache_path("universe_top20")).exists()


@pytest.mark.parametrize(
    "payload", [None, [], {}, [{"id": "bitcoin", "symbol": ""}], [{"id": "bitcoin"}]]
)
def test_invalid_cached_universe_fails_before_network(tmp_path, monkeypatch, payload):
    client = DataClient(str(tmp_path), quiet=True)
    path = Path(client._cache_path("universe_top20"))
    original = json.dumps(payload)
    path.write_text(original)
    monkeypatch.setattr(
        client, "_get", lambda *a, **k: pytest.fail("invalid cache must not silently refetch")
    )
    with pytest.raises(ValueError, match="COINGECKO_UNIVERSE"):
        client.fetch_universe()
    assert path.read_text() == original


def test_all_excluded_response_is_unavailable(tmp_path, monkeypatch):
    client = DataClient(str(tmp_path), quiet=True)
    monkeypatch.setattr(client, "_get", lambda *a, **k: [{"id": "tether", "symbol": "usdt"}])
    with pytest.raises(ValueError, match="COINGECKO_UNIVERSE"):
        client.fetch_universe()
    assert not Path(client._cache_path("universe_top20")).exists()


@pytest.mark.parametrize("top_n", [0, -1, True, 1.5])
def test_invalid_top_n_is_rejected(tmp_path, top_n):
    with pytest.raises(ValueError, match="top_n"):
        DataClient(str(tmp_path), top_n=top_n)


def test_recorded_contract_rows_reach_actual_consumer(tmp_path, monkeypatch):
    rows = json.loads(CONTRACT.read_text())["fixture"]
    client = DataClient(str(tmp_path), top_n=3, quiet=True)
    monkeypatch.setattr(client, "_get", lambda *a, **k: rows)
    expected = [{"id": "bitcoin", "symbol": "BTC"}, {"id": "ethereum", "symbol": "ETH"}]
    assert client.fetch_universe() == expected
    monkeypatch.setattr(client, "_get", lambda *a, **k: pytest.fail("healthy cache must be reused"))
    assert client.fetch_universe() == expected


def test_failed_cache_refresh_preserves_previous_bytes(tmp_path, monkeypatch):
    client = DataClient(str(tmp_path), quiet=True)
    path = Path(client._cache_path("universe_top20"))
    original = json.dumps([{"id": "usd1-wlfi", "symbol": "USD1"}])
    path.write_text(original)
    monkeypatch.setattr(client, "_get", lambda *a, **k: [])
    with pytest.raises(ValueError, match="COINGECKO_UNIVERSE"):
        client.fetch_universe()
    assert path.read_text() == original


def test_cli_invalid_universe_exits_without_report(tmp_path, monkeypatch, capsys):
    import sys

    import crypto_regime_analyzer as analyzer

    output = tmp_path / "reports"
    monkeypatch.setattr(DataClient, "_get", lambda *a, **k: [])
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
    assert analyzer.main() == 1
    assert not output.exists() or not list(output.iterdir())
    assert "COINGECKO_UNIVERSE" in capsys.readouterr().err
