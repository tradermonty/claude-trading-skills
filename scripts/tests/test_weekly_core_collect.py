from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_DIR))

import weekly_core_collect as collector  # noqa: E402

DUMMY_FMP_VALUE = "placeholder"


class FakeResponse:
    def __init__(self, status_code: int, payload=None, text: str = ""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        return self._payload


def test_parse_bool_treats_one_as_paper_endpoint() -> None:
    assert collector.parse_bool("1", "ALPACA_PAPER") is True
    assert collector.parse_bool("true", "ALPACA_PAPER") is True
    assert collector.parse_bool("0", "ALPACA_PAPER") is False
    assert collector.parse_bool("false", "ALPACA_PAPER") is False


def test_parse_bool_rejects_invalid_values() -> None:
    with pytest.raises(SystemExit, match="refusing to choose a live Alpaca endpoint"):
        collector.parse_bool("maybe", "ALPACA_PAPER")


def test_fmp_get_prefers_stable_then_falls_back_to_v3(monkeypatch) -> None:
    calls = []

    def fake_get(url, params, timeout):
        calls.append({"url": url, "params": dict(params), "timeout": timeout})
        if url == "https://financialmodelingprep.com/stable/profile":
            return FakeResponse(403, text="stable forbidden")
        return FakeResponse(200, [{"symbol": "AAPL", "sector": "Technology"}])

    monkeypatch.setattr(collector.requests, "get", fake_get)

    client = collector.FmpClient(DUMMY_FMP_VALUE)
    result = client.get("profile/AAPL")

    assert result == [{"symbol": "AAPL", "sector": "Technology"}]
    assert calls == [
        {
            "url": "https://financialmodelingprep.com/stable/profile",
            "params": {"symbol": "AAPL", "apikey": DUMMY_FMP_VALUE},
            "timeout": 30,
        },
        {
            "url": "https://financialmodelingprep.com/api/v3/profile/AAPL",
            "params": {"apikey": DUMMY_FMP_VALUE},
            "timeout": 30,
        },
    ]
    assert client.diagnostics()["status"] == "degraded"


def test_fmp_cash_flow_normalizes_stable_dividend_field(monkeypatch) -> None:
    def fake_get(url, params, timeout):
        return FakeResponse(
            200,
            [{"symbol": "AAPL", "netDividendsPaid": -100, "operatingCashFlow": 500}],
        )

    monkeypatch.setattr(collector.requests, "get", fake_get)

    client = collector.FmpClient(DUMMY_FMP_VALUE)
    result = client.get("cash-flow-statement/AAPL", limit=4)

    assert result == [
        {
            "symbol": "AAPL",
            "netDividendsPaid": -100,
            "dividendsPaid": -100,
            "operatingCashFlow": 500,
        }
    ]
    assert client.diagnostics()["status"] == "ok"


def test_fmp_diagnostics_fail_when_all_attempts_fail(monkeypatch) -> None:
    def fake_get(url, params, timeout):
        return FakeResponse(403, text="forbidden")

    monkeypatch.setattr(collector.requests, "get", fake_get)

    client = collector.FmpClient(DUMMY_FMP_VALUE)
    assert client.get("profile/AAPL") is None

    diagnostics = client.diagnostics()
    assert diagnostics["status"] == "failed"
    assert diagnostics["attempts"] == 2
    assert diagnostics["successes"] == 0
    assert diagnostics["failures"] == 2
