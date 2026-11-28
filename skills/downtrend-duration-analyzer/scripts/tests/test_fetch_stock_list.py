"""Downtrend screener uses the generated stable-only HTTP transport (#495)."""

import importlib
from unittest.mock import MagicMock

import analyze_downtrends
import pytest


@pytest.fixture
def session(monkeypatch):
    generated = importlib.import_module(analyze_downtrends.FMPClient.__module__)
    value = MagicMock()
    monkeypatch.setattr(generated.requests, "Session", lambda: value)
    return value


def test_uses_stable_company_screener(session):
    session.get.return_value.status_code = 200
    session.get.return_value.json.return_value = [
        {"symbol": "XOM", "sector": "Energy", "marketCap": 500_000_000_000}
    ]
    stocks = analyze_downtrends.fetch_stock_list("key", sector="Energy")
    assert stocks[0]["symbol"] == "XOM"
    args, kwargs = session.get.call_args
    assert args[0] == "https://financialmodelingprep.com/stable/company-screener"
    assert kwargs["params"] == {
        "apikey": "key",  # pragma: allowlist secret (fictional test value)
        "sector": "Energy",
        "isActivelyTrading": "true",
        "limit": 500,
    }
    assert kwargs["timeout"] == 30
    session.close.assert_called_once()


def test_denied_stable_endpoint_does_not_fall_back_to_v3(session):
    session.get.return_value.status_code = 403
    session.get.return_value.text = "denied"
    assert analyze_downtrends.fetch_stock_list("key") == []
    assert session.get.call_count == 1
    assert "/stable/company-screener" in session.get.call_args[0][0]
    session.close.assert_called_once()


def test_returns_empty_for_valid_empty_universe(session):
    session.get.return_value.status_code = 200
    session.get.return_value.json.return_value = []
    assert analyze_downtrends.fetch_stock_list("key") == []
    assert session.get.call_count == 1


@pytest.mark.parametrize("status", [402, 403])
def test_plan_restricted_screener_is_reported_as_plan_gate(session, capsys, status):
    session.get.return_value.status_code = status
    session.get.return_value.text = "Restricted Endpoint"
    assert analyze_downtrends.fetch_stock_list("key") == []
    err = capsys.readouterr().err
    assert "plan" in err and "getting-started.md#fmp-plans" in err
    assert "unusable screener response" not in err
