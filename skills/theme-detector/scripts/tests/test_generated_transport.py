"""Theme generated transport, synthetic HTTP only."""

import importlib
import sys
import types
from urllib.parse import quote

import pytest
import requests
from etf_scanner import ETFScanner
from representative_stock_selector import RepresentativeStockSelector

KEY = "fictional+theme&495"  # pragma: allowlist secret
MARKER = "UNTRUSTED-BODY-MARKER"


class Response:
    def __init__(self, data=None, status=200, text=""):
        self.status_code, self.data, self.text = status, data, text

    def json(self):
        if isinstance(self.data, Exception):
            raise self.data
        return self.data


@pytest.fixture
def http(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda _: None)
    calls, closed, pending = [], [], []
    original_close = requests.Session.close

    def get(self, url, params=None, timeout=None):
        calls.append((url, dict(params or {}), timeout))
        if not pending:
            raise AssertionError("Unexpected HTTP")
        response = pending.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def close(self):
        closed.append(self)
        original_close(self)

    def forbid(*a, **kw):
        raise AssertionError("Handwritten requests.get forbidden")

    monkeypatch.setattr(requests, "get", forbid)
    monkeypatch.setattr(requests.Session, "get", get)
    monkeypatch.setattr(requests.Session, "close", close)

    def setup(*responses):
        pending.extend(responses)
        return calls, closed

    return setup


@pytest.mark.parametrize(
    "kind,path",
    [("quote", "quote"), ("historical", "historical-price-eod/full"), ("holdings", "etf/holdings")],
)
def test_owned_adjacent_generated_stable_requests(http, monkeypatch, kind, path):
    adapter = importlib.import_module("fmp_adapter")
    monkeypatch.setitem(sys.modules, "fmp_client", types.SimpleNamespace(FMPClient=None))
    calls, closed = http(Response([{"symbol": "AAA"}]))
    data = adapter.fetch_fmp(
        kind, "AAA", KEY, {"from": "2026-01-01", "to": "2026-02-01"}, rate_limit_sec=0
    )
    assert data == [{"symbol": "AAA"}]
    assert calls == [
        (
            "https://financialmodelingprep.com/stable/" + path,
            {"symbol": "AAA", "from": "2026-01-01", "to": "2026-02-01", "apikey": KEY},
            15,
        )
    ]
    assert len(closed) == 1


@pytest.mark.parametrize(
    "outcome",
    [
        Response(status=402, text=MARKER + KEY),
        Response(status=403, text=MARKER + KEY),
        requests.Timeout(MARKER + KEY + quote(KEY, safe="")),
    ],
)
def test_failure_safe_diagnostics_and_cleanup(http, capsys, outcome):
    adapter = importlib.import_module("fmp_adapter")
    calls, closed = http(outcome)
    assert adapter.fetch_fmp("quote", "AAA", KEY, rate_limit_sec=0) is None
    output = capsys.readouterr()
    assert len(calls) == len(closed) == 1
    for marker in [MARKER, KEY, quote(KEY, safe="")]:
        assert marker not in output.out + output.err


def test_generated_json_retry_closes_one_owned_session(http):
    adapter = importlib.import_module("fmp_adapter")
    calls, closed = http(Response(ValueError(MARKER)), Response([{"symbol": "AAA"}]))
    assert adapter.fetch_fmp("quote", "AAA", KEY, rate_limit_sec=0) == [{"symbol": "AAA"}]
    assert len(calls) == 2 and calls[0] == calls[1] and len(closed) == 1


def test_empty_symbols_never_disable_later_quote_endpoint(http):
    calls, closed = http(*([Response([])] * 4), Response([{"symbol": "HEALTHY", "price": 100}]))
    scanner = ETFScanner(fmp_api_key=KEY, rate_limit_sec=0)
    for symbol in ["EMPTY1", "EMPTY2", "EMPTY3", "EMPTY4"]:
        assert scanner._fmp_request("quote", symbol) is None
    assert scanner._fmp_request("quote", "HEALTHY") == [{"symbol": "HEALTHY", "price": 100}]
    assert len(calls) == len(closed) == 5
    assert scanner.backend_stats()["fmp_failures"] == 4


def test_holdings_generated_path_preserves_selection(http):
    calls, closed = http(Response([{"asset": "AAA", "marketValue": 1e9}]))
    selector = RepresentativeStockSelector(fmp_api_key=KEY, rate_limit_sec=0)
    result = selector._fetch_etf_holdings("FICT", limit=1)
    assert result[0]["symbol"] == "AAA" and result[0]["source"] == "etf_holdings"
    assert len(calls) == len(closed) == 1 and calls[0][0].endswith("/stable/etf/holdings")


def test_missing_key_does_not_load_client(monkeypatch):
    adapter = importlib.import_module("fmp_adapter")

    def forbid():
        raise AssertionError("HTTP client loaded without a key")

    monkeypatch.setattr(adapter, "_client_class", forbid)
    monkeypatch.setenv("FMP_API_KEY", "fictional-ambient")
    assert adapter.fetch_fmp("quote", "AAA", "") is None


def test_programming_errors_propagate_after_session_cleanup(http):
    adapter = importlib.import_module("fmp_adapter")
    _, closed = http(AssertionError("fictional bug"))
    with pytest.raises(AssertionError, match="fictional bug"):
        adapter.fetch_fmp("quote", "AAA", KEY, rate_limit_sec=0)
    assert len(closed) == 1


def test_generated_429_retry_closes_owned_session(http):
    adapter = importlib.import_module("fmp_adapter")
    calls, closed = http(Response(status=429), Response([{"symbol": "AAA"}]))
    assert adapter.fetch_fmp("quote", "AAA", KEY, rate_limit_sec=0) == [{"symbol": "AAA"}]
    assert len(calls) == 2 and calls[0] == calls[1] and len(closed) == 1


def test_historical_range_is_pinned_without_mutating_parameters(http):
    from datetime import date, timedelta

    calls, _ = http(Response([{"symbol": "AAA", "date": "2026-04-06", "close": 100}]))
    scanner = ETFScanner(fmp_api_key=KEY, rate_limit_sec=0, as_of_date=date(2026, 4, 6))
    params = {"timeseries": 20, "_as_of": "2026-04-06"}
    assert scanner._fmp_request("historical", "AAA", params)["historical"][0]["close"] == 100
    assert calls[0][1] == {
        "symbol": "AAA",
        "from": (date(2026, 4, 6) - timedelta(days=50)).isoformat(),
        "to": "2026-04-06",
        "apikey": KEY,
    }
    assert params == {"timeseries": 20, "_as_of": "2026-04-06"}


def test_standalone_archive_loads_its_own_transport(tmp_path):
    import subprocess
    import zipfile
    from pathlib import Path

    root = Path(__file__).resolve().parents[4]
    with zipfile.ZipFile(root / "skill-packages/theme-detector.skill") as archive:
        archive.extractall(tmp_path)
    scripts = tmp_path / "theme-detector/scripts"
    code = """
import sys,types,requests
sys.path.insert(0,sys.argv[1])
sys.modules['fmp_client']=types.SimpleNamespace(FMPClient=None)
closed=[]
class Response:
    status_code=200
    def json(self):return [{'symbol':'AAA','price':100}]
class Session:
    def get(self,url,params,timeout):
        assert url.endswith('/stable/quote') and timeout==15
        assert params=={'symbol':'AAA','apikey':'fictional-marker'}  # pragma: allowlist secret
        return Response()
    def close(self):closed.append(True)
requests.Session=Session
from fmp_adapter import fetch_fmp
assert fetch_fmp('quote','AAA','fictional-marker')==[{'symbol':'AAA','price':100}]
assert closed==[True]
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(scripts)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("caller", ["scanner", "holdings"])
def test_retry_completion_preserves_spacing_before_next_operation(monkeypatch, caller):
    clock = [100.0]
    starts = []
    outcomes = [
        Response(status=429),
        Response([{"symbol": "AAA", "asset": "AAA", "marketValue": 100}]),
        Response([{"symbol": "AAA", "asset": "AAA", "marketValue": 100}]),
    ]
    monkeypatch.setattr("time.time", lambda: clock[0])
    monkeypatch.setattr("time.sleep", lambda delay: clock.__setitem__(0, clock[0] + delay))

    def get(self, *args, **kwargs):
        starts.append(clock[0])
        return outcomes.pop(0)

    monkeypatch.setattr(requests.Session, "get", get)
    if caller == "scanner":
        client = ETFScanner(fmp_api_key=KEY, rate_limit_sec=0.3)

        def operation():
            return client._fmp_request("quote", "AAA")
    else:
        client = RepresentativeStockSelector(fmp_api_key=KEY, rate_limit_sec=0.3)

        def operation():
            return client._fetch_etf_holdings("FICT", 1)

    assert operation()
    assert operation()
    assert len(starts) == 3
    assert starts[-1] - starts[-2] >= 0.3 - 1e-9
