"""Issue #778 follow-up: every theme-detector network call has a finite timeout."""

import math
import re
import threading
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import etf_scanner
import fmp_adapter
import pandas as pd
import pytest
import requests
from etf_scanner import ETFScanner

SCRIPTS = Path(__file__).resolve().parents[1]
MARKER = "issue778-marker-key"


def _finite(value):
    return isinstance(value, (int, float)) and math.isfinite(value) and value > 0


def _frame():
    index = pd.date_range("2025-01-01", periods=300, freq="B")
    return pd.DataFrame(
        {"Close": range(300), "High": range(300), "Low": range(300), "Volume": [1000] * 300},
        index=index,
    )


@pytest.fixture
def fake_yf(monkeypatch):
    fake = MagicMock()
    fake.download.return_value = _frame()
    monkeypatch.setattr(etf_scanner, "yf", fake)
    monkeypatch.setattr(etf_scanner, "HAS_YFINANCE", True)
    return fake


def test_batch_download_has_finite_timeout(fake_yf):
    ETFScanner(rate_limit_sec=0)._batch_stock_metrics_yfinance(["AAA", "BBB"])
    assert fake_yf.download.called
    for call in fake_yf.download.call_args_list:
        assert _finite(call.kwargs.get("timeout"))


@pytest.mark.parametrize("as_of", [None, date(2025, 6, 2)])
def test_cached_download_has_finite_timeout(fake_yf, as_of):
    scanner = ETFScanner(rate_limit_sec=0, as_of_date=as_of)
    scanner._get_cached("AAA")
    assert fake_yf.download.called
    for call in fake_yf.download.call_args_list:
        assert _finite(call.kwargs.get("timeout"))


def test_pe_lookup_is_bounded_when_the_provider_hangs(monkeypatch, capsys):
    release = threading.Event()

    class HangingTicker:
        def __init__(self, symbol):
            self.symbol = symbol

        @property
        def info(self):
            release.wait(10)
            return {"trailingPE": 12.0}

    fake = MagicMock()
    fake.Ticker = HangingTicker
    monkeypatch.setattr(etf_scanner, "yf", fake)
    monkeypatch.setattr(etf_scanner, "_INFO_DEADLINE_SEC", 0.05)
    try:
        assert ETFScanner(rate_limit_sec=0)._get_pe_ratio("FAKE") is None
    finally:
        release.set()
    err = capsys.readouterr().err
    assert "Degraded" in err and MARKER not in err


def test_pe_lookup_still_returns_the_value(monkeypatch):
    fake = MagicMock()
    fake.Ticker.return_value = MagicMock(info={"trailingPE": 17.256})
    monkeypatch.setattr(etf_scanner, "yf", fake)
    assert ETFScanner(rate_limit_sec=0)._get_pe_ratio("FAKE") == 17.26


def test_pe_lookup_connection_error_never_prints_the_marker(monkeypatch, capsys):
    error = requests.ConnectionError(f"https://example.invalid/?apikey={MARKER}")
    fake = MagicMock()
    fake.Ticker.return_value = MagicMock()
    type(fake.Ticker.return_value).info = property(lambda self: (_ for _ in ()).throw(error))
    monkeypatch.setattr(etf_scanner, "yf", fake)
    assert ETFScanner(rate_limit_sec=0)._get_pe_ratio("FAKE") is None
    captured = capsys.readouterr()
    assert MARKER not in captured.out + captured.err


def test_generated_fmp_client_default_timeout_is_the_old_adapter_value():
    source = (SCRIPTS / "fmp_client.py").read_text(encoding="utf-8")
    assert re.findall(r"self\.timeout = (\d+)", source) == ["15"]
    adapter = (SCRIPTS / "fmp_adapter.py").read_text(encoding="utf-8")
    assert ".timeout" not in adapter


def test_fmp_adapter_requests_use_the_bounded_client_timeout(monkeypatch):
    seen = []

    class Response:
        status_code = 200
        text = "[]"

        def json(self):
            return []

        def raise_for_status(self):
            return None

    class Session:
        headers = {}

        def get(self, url, params=None, timeout=None, **_):
            seen.append(timeout)
            return Response()

        def close(self):
            return None

    monkeypatch.setattr(requests, "Session", Session)
    fmp_adapter.fetch_fmp("quote", "AAA", MARKER, rate_limit_sec=0)
    assert seen and all(value == 15 for value in seen)
