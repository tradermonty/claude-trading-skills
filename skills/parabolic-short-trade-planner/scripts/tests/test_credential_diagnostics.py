"""Offline credential safety for every live-check failure branch (#778)."""

from unittest.mock import Mock
from urllib.parse import quote

import check_live_apis as target
import pytest
import requests

MARKER = "issue778-marker/with+reserved?chars"


@pytest.mark.parametrize(
    "error_type", [requests.ConnectionError, requests.Timeout, requests.HTTPError]
)
@pytest.mark.parametrize("check", ["historical", "profile", "sp500", "alpaca", "raw404", "adapter"])
def test_request_failure_does_not_expose_key(monkeypatch, capsys, error_type, check):
    error = error_type(f"request failed: ?apikey={MARKER}&auth={quote(MARKER, safe='')}")
    get = Mock(side_effect=error)
    monkeypatch.setattr(target.requests, "get", get)
    if check == "adapter":
        import alpaca_inventory_adapter

        get.side_effect = None
        get.return_value.status_code = 404
        monkeypatch.setattr(
            alpaca_inventory_adapter, "AlpacaInventoryAdapter", Mock(side_effect=error)
        )
    calls = {
        "historical": lambda: target.check_fmp_historical(MARKER),
        "profile": lambda: target.check_fmp_profile(MARKER),
        "sp500": lambda: target.check_fmp_sp500(MARKER),
        "alpaca": lambda: target.check_alpaca_assets_aapl(MARKER, MARKER, True),
        "raw404": lambda: target.check_alpaca_404_graceful(MARKER, MARKER, True),
        "adapter": lambda: target.check_alpaca_404_graceful(MARKER, MARKER, True),
    }
    assert calls[check]() is (check == "sp500")
    output = capsys.readouterr()
    text = output.out + output.err
    assert MARKER not in text
    assert quote(MARKER, safe="") not in text
    assert ("WARN" if check == "sp500" else "FAIL") in text


@pytest.mark.parametrize("check", ["historical", "profile", "sp500", "alpaca", "raw404"])
@pytest.mark.parametrize("failure", ["http", "non_json"])
def test_reflected_error_body_is_not_printed(monkeypatch, capsys, check, failure):
    response = Mock(status_code=500 if failure == "http" else 200, text=MARKER)
    response.json.side_effect = ValueError(MARKER)
    monkeypatch.setattr(target.requests, "get", Mock(return_value=response))
    calls = {
        "historical": lambda: target.check_fmp_historical(MARKER),
        "profile": lambda: target.check_fmp_profile(MARKER),
        "sp500": lambda: target.check_fmp_sp500(MARKER),
        "alpaca": lambda: target.check_alpaca_assets_aapl(MARKER, MARKER, True),
        "raw404": lambda: target.check_alpaca_404_graceful(MARKER, MARKER, True),
    }
    assert calls[check]() is (check == "sp500")
    captured = capsys.readouterr()
    assert MARKER not in captured.out + captured.err
