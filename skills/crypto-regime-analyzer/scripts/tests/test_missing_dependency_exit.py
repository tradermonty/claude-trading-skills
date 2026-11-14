"""Live mode without ``requests`` exits 2 with a requirements.txt hint (#497).

A warm same-day cache must keep working without ``requests``: the dependency is
only required when a network fetch is actually needed.
"""

import sys

import crypto_regime_analyzer as cra
import data_client
import pytest


def _argv(tmp_path):
    return [
        "crypto_regime_analyzer.py",
        "--output-dir",
        str(tmp_path / "out"),
        "--cache-dir",
        str(tmp_path / "cache"),
        "--top-n",
        "2",
        "--quiet",
    ]


def test_live_mode_cold_cache_without_requests_exits_2(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(data_client, "requests", None)
    monkeypatch.setattr(sys, "argv", _argv(tmp_path))
    assert cra.main() == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "ERROR: requests library not found" in captured.err
    assert "pip install -r" in captured.err
    assert "requirements.txt" in captured.err


def test_warm_cache_runs_without_requests(monkeypatch, capsys, tmp_path):
    closes = [100.0 + i * 0.5 for i in range(400)]

    def fake_get(self, url, params=None):
        if url.endswith("/coins/markets"):
            return [
                {"id": "bitcoin", "symbol": "btc"},
                {"id": "ethereum", "symbol": "eth"},
            ]
        if "market_chart" in url:
            return {"prices": [[i, c] for i, c in enumerate(closes)]}
        if url.endswith("/global"):
            return {"data": {"market_cap_percentage": {"btc": 52.0}}}
        if url.endswith("/fapi/v1/premiumIndex"):
            return [{"symbol": "BTCUSDT", "lastFundingRate": "0.0001"}]
        raise AssertionError(url)

    monkeypatch.setattr(data_client.DataClient, "_get", fake_get)
    monkeypatch.setattr(data_client, "REQUEST_DELAY_S", 0)
    monkeypatch.setattr(sys, "argv", _argv(tmp_path))
    assert cra.main() == 0  # warms the same-day cache

    # Now block requests and restore the real _get: only cache reads may happen.
    monkeypatch.undo()
    monkeypatch.setattr(data_client, "requests", None)
    monkeypatch.setattr(sys, "argv", _argv(tmp_path))
    capsys.readouterr()
    assert cra.main() == 0
    assert "requests library not found" not in capsys.readouterr().err


def test_get_without_requests_raises_missing_dependency(monkeypatch, tmp_path):
    monkeypatch.setattr(data_client, "requests", None)
    client = data_client.DataClient(str(tmp_path), top_n=5, quiet=True)
    with pytest.raises(data_client.MissingDependencyError, match="requirements.txt"):
        client._get("https://example.invalid/x")
