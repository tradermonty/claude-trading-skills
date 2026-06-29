import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "run_20pct_study.py"
spec = importlib.util.spec_from_file_location("run_20pct_study", SCRIPT)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def response(status, payload):
    res = MagicMock()
    res.status_code = status
    res.text = "body"
    res.json.return_value = payload
    return res


def test_fmp_universe_uses_stable_company_screener_first(monkeypatch):
    monkeypatch.setattr(mod.time, "sleep", lambda _: None)
    session = MagicMock()
    session.get.return_value = response(
        200,
        [
            {"symbol": "AAPL", "exchangeShortName": "NASDAQ", "price": 200},
            {"symbol": "SPY", "exchangeShortName": "NYSEARCA", "price": 600, "isEtf": True},
        ],
    )
    client = mod.FMPClient(api_key="test", max_api_calls=10)
    client.session = session

    symbols = client.get_stock_list(limit=20)

    assert symbols == ["AAPL"]
    assert session.get.call_args_list[0][0][0].endswith("/stable/company-screener")


def test_fmp_universe_falls_back_to_v3_stock_screener(monkeypatch):
    monkeypatch.setattr(mod.time, "sleep", lambda _: None)
    session = MagicMock()
    session.get.side_effect = [
        response(403, {}),
        response(
            200, [{"symbol": "MSFT", "exchangeShortName": "NASDAQ", "type": "stock", "price": 300}]
        ),
    ]
    client = mod.FMPClient(api_key="test", max_api_calls=10)
    client.session = session

    symbols = client.get_stock_list(limit=10)

    urls = [call[0][0] for call in session.get.call_args_list]
    assert symbols == ["MSFT"]
    assert urls[0].endswith("/stable/company-screener")
    assert urls[1].endswith("/api/v3/stock-screener")


def test_fmp_historical_accepts_stable_flat_list(monkeypatch):
    monkeypatch.setattr(mod.time, "sleep", lambda _: None)
    session = MagicMock()
    session.get.return_value = response(
        200,
        [
            {
                "symbol": "AAPL",
                "date": "2026-01-02",
                "open": 11,
                "high": 12,
                "low": 10,
                "close": 11.5,
                "volume": 2000,
            },
            {
                "symbol": "AAPL",
                "date": "2026-01-01",
                "open": 10,
                "high": 11,
                "low": 9,
                "close": 10.5,
                "volume": 1000,
            },
        ],
    )
    client = mod.FMPClient(api_key="test", max_api_calls=10)
    client.session = session

    bars = client.get_historical_prices("AAPL", days=2)

    assert [bar["date"] for bar in bars] == ["2026-01-01", "2026-01-02"]
    assert session.get.call_args_list[0][0][0].endswith("/stable/historical-price-eod/full")


def test_fmp_historical_falls_back_to_v3_payload(monkeypatch):
    monkeypatch.setattr(mod.time, "sleep", lambda _: None)
    session = MagicMock()
    session.get.side_effect = [
        response(200, []),
        response(
            200,
            {
                "historical": [
                    {
                        "date": "2026-01-02",
                        "open": 11,
                        "high": 12,
                        "low": 10,
                        "close": 11.5,
                        "volume": 2000,
                    }
                ]
            },
        ),
    ]
    client = mod.FMPClient(api_key="test", max_api_calls=10)
    client.session = session

    bars = client.get_historical_prices("AAPL", days=2)

    urls = [call[0][0] for call in session.get.call_args_list]
    assert bars[0]["date"] == "2026-01-02"
    assert urls[0].endswith("/stable/historical-price-eod/full")
    assert urls[1].endswith("/api/v3/historical-price-full/AAPL")


def test_fmp_requires_key_for_live_path(monkeypatch):
    monkeypatch.delenv("FMP_API_KEY", raising=False)

    with pytest.raises(ValueError, match="FMP API key required"):
        mod.FMPClient()


def test_fmp_api_budget_exhaustion():
    client = mod.FMPClient(api_key="test", max_api_calls=0)

    with pytest.raises(mod.ApiCallBudgetExceeded):
        client.get_stock_list(limit=1)
