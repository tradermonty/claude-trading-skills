"""Live mode without ``requests`` exits 2 with a requirements.txt hint (#497)."""

import sys

import crypto_regime_analyzer as cra
import data_client
import pytest


def test_live_mode_without_requests_exits_2(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(data_client, "requests", None)
    monkeypatch.setattr(
        sys,
        "argv",
        ["crypto_regime_analyzer.py", "--output-dir", str(tmp_path), "--cache-dir", str(tmp_path)],
    )
    assert cra.main() == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "ERROR: requests library not found" in captured.err
    assert "pip install -r" in captured.err
    assert "requirements.txt" in captured.err


def test_get_without_requests_raises_missing_dependency(monkeypatch, tmp_path):
    monkeypatch.setattr(data_client, "requests", None)
    client = data_client.DataClient(str(tmp_path), top_n=5, quiet=True)
    with pytest.raises(data_client.MissingDependencyError, match="requirements.txt"):
        client._get("https://example.invalid/x")
