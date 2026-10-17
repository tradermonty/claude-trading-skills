"""Shared offline HTTP scenarios, used by isolated and per-skill test rows."""

import contextlib
import importlib
import io
import sys
from unittest.mock import patch
from urllib.parse import quote

import requests


def run_scenarios(folder, module_name):
    with patch("time.sleep", lambda _: None):
        _run_scenarios(folder, module_name)


def _run_scenarios(folder, module_name):
    sys.path.insert(0, str(folder))
    module = importlib.import_module(module_name)
    transport = importlib.import_module("fmp_client")
    assert issubclass(module.FMPClient, transport.FMPClient)
    key = "fictional+key&only"  # pragma: allowlist secret

    class Response:
        def __init__(self, payload=None, status=200, text=""):
            self.status_code, self.payload, self.text = status, payload, text

        def json(self):
            if isinstance(self.payload, ValueError):
                raise self.payload
            return self.payload

    def client_for(*responses):
        if module_name == "build_entry_signals":
            client = module.FMPClient(key, sleep_seconds=0, timeout=7)
        else:
            client = module.FMPClient(key)
            client.RATE_LIMIT_DELAY = 0
        responses = list(responses)
        calls = []

        def get(url, params=None, timeout=None):
            assert "/api/v3/" not in url
            assert key not in url
            assert "apikey" not in (params or {})
            calls.append((url, params, timeout))
            response = responses.pop(0)
            if isinstance(response, requests.exceptions.RequestException):
                raise response
            return response

        client.session.get = get
        assert client.session.headers["apikey"] == key
        return client, calls

    # Existing interface and parameter mapping; profile/quote per-symbol behavior.
    if module_name == "build_entry_signals":
        client, calls = client_for(
            Response([{"symbol": "AAA", "price": 10}]), Response([{"symbol": "BBB", "price": 20}])
        )
        assert set(client.get_batch_quotes(["AAA", "BBB"])) == {"AAA", "BBB"}
        assert [c[1]["symbol"] for c in calls] == ["AAA", "BBB"]
        assert all(c[2] == 7 for c in calls)
        assert client.sleep_seconds == client.RATE_LIMIT_DELAY == 0
        assert client.api_calls == client.api_calls_made == 2
        client, calls = client_for(Response([{"symbol": "AAA", "lastDividend": 2}]))
        assert client.get_batch_profiles(["AAA"])["AAA"]["lastDiv"] == 2
        client, calls = client_for(Response([{"symbol": "AAA", "dividendYield": 0.04}]))
        assert client.get_ratios("AAA")[0]["dividendYield"] == 0.04
        assert calls[0][1] == {"symbol": "AAA", "limit": 10}
        client, calls = client_for(Response([{"date": "2026-01-01", "dividend": 0.5}]))
        assert client.get_stock_dividend("AAA")[0]["dividend"] == 0.5
        client, calls = client_for(
            Response([{"epsDiluted": 4, "weightedAverageShsOutDil": 2}]),
            Response([{"freeCashFlow": 6}]),
        )
        financials = client.get_financials("AAA")
        assert financials["gaap_eps"] == 4 and financials["fcf_per_share"] == 3
        assert financials["adjusted_eps_source"] == "UNAVAILABLE"
    else:
        client, calls = client_for(Response([{"revenue": 10}]))
        assert client.get_income_statement("AAA", limit=3) == [{"revenue": 10}]
        assert calls[0][0].endswith("/stable/income-statement")
        assert calls[0][1] == {"symbol": "AAA", "limit": 3}
        client, calls = client_for(Response([{"date": "2026-01-01", "dividend": 0.5}]))
        assert client.get_dividend_history("AAA") == {
            "historical": [{"date": "2026-01-01", "dividend": 0.5}]
        }
        client, calls = client_for(Response([{"returnOnEquity": 0.2}]))
        assert client.get_key_metrics("AAA")[0]["roe"] == 0.2
        client, calls = client_for(Response([{"netDividendsPaid": -2}]))
        assert client.get_cash_flow("AAA")[0]["dividendsPaid"] == -2
        client, calls = client_for(Response([{"close": i} for i in range(5)]))
        assert client.get_historical_prices("AAA", days=2) == [{"close": 0}, {"close": 1}]
        assert set(calls[0][1]) == {"symbol", "from", "to"}
        client, calls = client_for(Response([], status=200))
        expected = [] if module_name == "screen_dividend_stocks" else None
        assert client.get_historical_prices("AAA") == expected
        assert len(calls) == 1

    # All targets use the same bounded JSON retry, 429 behavior and redaction.
    client, calls = client_for(Response(ValueError("broken")), Response([{"symbol": "AAA"}]))
    assert client._get("profile", {"symbol": "AAA"}) == [{"symbol": "AAA"}]
    assert len(calls) == client.api_calls_made == 2
    client, calls = client_for(Response(ValueError("broken")), Response(ValueError("broken")))
    assert client._get("profile", {"symbol": "AAA"}) is None
    assert len(calls) == 2
    client, calls = client_for(Response(status=429), Response([{"symbol": "AAA"}]))
    assert client._get("profile", {"symbol": "AAA"}) == [{"symbol": "AAA"}]
    assert len(calls) == 2 and not client.rate_limit_reached
    client, calls = client_for(Response(status=429), Response(status=429))
    assert client._get("profile", {"symbol": "AAA"}) is None
    assert client.rate_limit_reached
    assert client._get("profile", {"symbol": "AAA"}) is None
    assert len(calls) == 2
    for failure in [
        Response(status=402, text=key + " " + quote(key, safe="")),
        Response(status=503, text=key),
        requests.exceptions.Timeout(key + " " + quote(key, safe="")),
    ]:
        client, calls = client_for(failure)
        output = io.StringIO()
        with contextlib.redirect_stderr(output):
            assert client._get("profile", {"symbol": "AAA"}) is None
        assert key not in output.getvalue()
        assert quote(key, safe="") not in output.getvalue()
        assert len(calls) == 1
    client, calls = client_for()
    assert client._get("unrecognized/path") is None
    assert not calls
    print("BATCH_B_TRANSPORT_OK")
