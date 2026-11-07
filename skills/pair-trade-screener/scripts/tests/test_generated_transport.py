"""Public pair adapters must use the generated transport, never requests.get."""

import time
from datetime import date, timedelta

import analyze_spread
import find_pairs
import pytest
import requests

MODULES = (find_pairs, analyze_spread)
TOKEN = "PAIR_FIXTURE_ONLY"  # pragma: allowlist secret


class Response:
    def __init__(self, data=None, status=200, text="", json_error=None):
        self.status_code = status
        self.text = text
        self.data = data
        self.json_error = json_error

    def json(self):
        if self.json_error:
            raise self.json_error
        return self.data


@pytest.fixture
def transport(monkeypatch):
    calls = []
    responses = []

    class Session:
        def __init__(self):
            self.headers = {}

        def get(self, url, params=None, timeout=None):
            calls.append((url, dict(params or {}), dict(self.headers), timeout))
            response = responses.pop(0) if len(responses) > 1 else responses[0]
            if isinstance(response, Exception):
                raise response
            return response

    def direct_http_forbidden(*args, **kwargs):
        raise AssertionError("Adapter bypassed generated Session transport")

    monkeypatch.setattr(requests, "Session", Session)
    monkeypatch.setattr(requests, "get", direct_http_forbidden)
    monkeypatch.setattr(time, "sleep", lambda _: None)
    return responses, calls


def rows(symbol="AAA"):
    """Flat /stable/historical-price-eod/full rows: unadjusted close, no adjClose."""
    return [
        {"symbol": symbol, "date": "2026-10-30", "close": 12.0},
        {"symbol": symbol, "date": "2026-10-29", "close": 11.0},
        {"symbol": symbol, "date": "2026-10-28", "close": 10.0},
    ]


def adj_rows(symbol="AAA"):
    """Flat /stable/historical-price-eod/dividend-adjusted rows, newest first."""
    return [
        {"symbol": symbol, "date": "2026-10-30", "adjClose": 22.0, "volume": 3},
        {"symbol": symbol, "date": "2026-10-29", "adjClose": 21.0, "volume": 2},
        {"symbol": symbol, "date": "2026-10-28", "adjClose": 20.0, "volume": 1},
    ]


def test_sector_filters_and_mapping_use_generated_session(transport):
    responses, calls = transport
    responses.append(
        Response(
            [
                {
                    "symbol": "AAA",
                    "companyName": "Fictional A",
                    "marketCap": 3000,
                    "sector": "Energy",
                    "exchangeShortName": "NYSE",
                    "isActivelyTrading": True,
                },
                {"symbol": "OFF", "isActivelyTrading": False},
            ]
        )
    )
    stocks = find_pairs.fetch_sector_stocks("Energy", TOKEN, 1000)
    assert stocks == [
        {
            "symbol": "AAA",
            "name": "Fictional A",
            "marketCap": 3000,
            "sector": "Energy",
            "exchange": "NYSE",
        }
    ]
    assert len(calls) == 1
    url, params, headers, timeout = calls[0]
    assert url.endswith("/stable/company-screener")
    assert params == {"sector": "Energy", "marketCapMoreThan": 1000, "limit": 1000}
    assert headers == {"apikey": TOKEN} and timeout == 30
    assert TOKEN not in url and TOKEN not in str(params)


@pytest.mark.parametrize("module", MODULES)
def test_dividend_adjusted_history_is_preferred_and_trimmed(module, transport):
    responses, calls = transport
    responses.append(Response(adj_rows()))
    result = module.fetch_historical_prices("AAA", TOKEN, lookback_days=2)
    assert result.tolist() == [21.0, 22.0]
    assert result.index.strftime("%Y-%m-%d").tolist() == ["2026-10-29", "2026-10-30"]
    assert result.name == "AAA"
    assert result.attrs["price_basis"] == "dividend_adjusted"
    # One request: neither the unadjusted `full` endpoint nor v3 is touched.
    assert len(calls) == 1
    assert calls[0][0].endswith("/stable/historical-price-eod/dividend-adjusted")
    assert calls[0][1] == {"symbol": "AAA"}
    assert calls[0][2] == {"apikey": TOKEN} and calls[0][3] == 30


@pytest.mark.parametrize("module", MODULES)
@pytest.mark.parametrize("adjusted", [Response(status=402), Response([])])
def test_unavailable_adjusted_endpoint_falls_back_to_close_and_warns(
    module, adjusted, transport, capsys
):
    responses, calls = transport
    responses.extend([adjusted, Response(rows())])
    result = module.fetch_historical_prices("AAA", TOKEN, lookback_days=2)
    assert result.tolist() == [11.0, 12.0]
    assert result.attrs["price_basis"] == "close"
    assert [c[0].rsplit("/", 1)[1] for c in calls] == ["dividend-adjusted", "full"]
    err = capsys.readouterr().err
    assert err.count("AAA: using raw close prices that are NOT dividend-adjusted") == 1


@pytest.mark.parametrize("module", MODULES)
def test_fallback_uses_adjclose_when_supplied_without_warning(module, transport, capsys):
    responses, _ = transport
    responses.extend([Response(status=402), Response({"symbol": "AAA", "historical": adj_rows()})])
    result = module.fetch_historical_prices("AAA", TOKEN, lookback_days=3)
    assert result.tolist() == [20.0, 21.0, 22.0]
    assert result.attrs["price_basis"] == "adj_close"
    assert "NOT dividend-adjusted" not in capsys.readouterr().err


@pytest.mark.parametrize(("module", "default"), [(find_pairs, 730), (analyze_spread, 365)])
def test_public_history_defaults_remain_distinct(module, default, transport):
    responses, calls = transport
    old_rows = [
        {
            "symbol": "AAA",
            "date": (date(2000, 1, 1) + timedelta(days=i)).isoformat(),
            "close": i + 1.0,
        }
        for i in range(800)
    ][::-1]
    responses.extend([Response(status=402), Response(old_rows)])
    result = module.fetch_historical_prices("AAA", TOKEN)
    assert len(result) == default
    assert result.tolist() == [row["close"] for row in old_rows[:default]][::-1]
    assert calls[1][0].endswith("/stable/historical-price-eod/full")
    assert calls[1][1] == {"symbol": "AAA"}


@pytest.mark.parametrize("module", MODULES)
def test_canonical_historical_fallback_and_symbol_alias(module, transport):
    responses, calls = transport
    responses.extend(
        [
            Response(status=402),
            Response(status=403),
            Response({"historicalStockList": [{"symbol": "BRK.B", "historical": rows("BRK.B")}]}),
        ]
    )
    result = module.fetch_historical_prices("BRK-B", TOKEN, lookback_days=2)
    assert result.tolist() == [11.0, 12.0]
    assert calls[2][0].endswith("/api/v3/historical-price-full/BRK-B")
    assert calls[2][1] == {}


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {},
        {"Error Message": "denied"},
        [],
        [None],
        ["bad"],
        [{}],
        [{"symbol": None}],
        [{"symbol": 1}],
    ],
)
def test_bad_screener_payload_exits_cleanly(transport, payload):
    responses, calls = transport
    responses.append(Response(payload))
    with pytest.raises(SystemExit) as exc:
        find_pairs.fetch_sector_stocks("Energy", TOKEN)
    assert exc.value.code == 1
    assert all("/api/v3/" not in call[0] for call in calls)


@pytest.mark.parametrize("status", [401, 402, 403, 429, 500])
def test_screener_errors_are_redacted_stderr_and_never_legacy(transport, status, capsys):
    responses, calls = transport
    responses.append(Response(status=status, text=f"?apikey={TOKEN} raw {TOKEN}"))
    with pytest.raises(SystemExit):
        find_pairs.fetch_sector_stocks("Energy", TOKEN)
    output = capsys.readouterr()
    assert TOKEN not in output.out + output.err
    assert output.err
    assert all("/api/v3/" not in call[0] for call in calls)


@pytest.mark.parametrize(
    "failure", [requests.Timeout(f"?apikey={TOKEN} bare {TOKEN}"), ValueError(f"malformed {TOKEN}")]
)
def test_screener_transport_and_json_failures_are_redacted(transport, failure, capsys):
    responses, _ = transport
    responses.append(
        failure if isinstance(failure, requests.RequestException) else Response(json_error=failure)
    )
    with pytest.raises(SystemExit):
        find_pairs.fetch_sector_stocks("Energy", TOKEN)
    output = capsys.readouterr()
    assert TOKEN not in output.out + output.err


@pytest.mark.parametrize("module", MODULES)
def test_failed_call_does_not_disable_later_public_fetches(module, transport):
    responses, calls = transport
    responses.append(Response(status=403))
    for _ in range(4):
        assert module.fetch_historical_prices("AAA", TOKEN) is None
    count = len(calls)
    responses[:] = [Response(rows())]
    assert module.fetch_historical_prices("AAA", TOKEN) is not None
    assert len(calls) > count


@pytest.mark.parametrize("module", MODULES)
@pytest.mark.parametrize(
    "payload",
    [
        {"historical": None},
        {"historical": {}},
        {"historical": "bad"},
        {"historical": [None]},
        {"historical": [{"date": None, "close": 1}]},
        {"historical": [{"date": "bad", "close": 1}]},
        {"historical": [{"date": "2026-10-30", "close": "bad"}]},
        {"historical": [{"date": "2026-10-30", "close": float("nan")}]},
        {"historical": [{"date": "2026-10-30", "close": 10**400}]},
        {"symbol": 1, "historical": []},
        {"historicalStockList": None},
        {"historicalStockList": [None]},
        {"historicalStockList": [{"symbol": None}]},
        [{"symbol": 1, "date": "2026-10-30", "close": 1}],
        [None],
        ["bad"],
    ],
)
def test_malformed_history_returns_controlled_none(module, payload, transport, capsys):
    responses, _ = transport
    responses.append(Response(payload))
    assert module.fetch_historical_prices("AAA", TOKEN) is None
    assert "Traceback" not in capsys.readouterr().err


@pytest.mark.parametrize("module", MODULES)
@pytest.mark.parametrize("symbol", [TOKEN, f"?apikey={TOKEN}"])
def test_provider_symbol_mismatch_cannot_echo_the_key(module, symbol, transport, capsys):
    responses, _ = transport
    responses.append(Response({"symbol": symbol, "historical": rows()}))
    assert module.fetch_historical_prices("AAA", TOKEN) is None
    output = capsys.readouterr()
    assert TOKEN not in output.out + output.err
