"""Exercise generated HTTP with fictional data; never contact a provider."""

import subprocess
import sys
import types
import zipfile
from pathlib import Path
from urllib.parse import quote

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import analyze_news_reaction as analyzer  # noqa: E402

KEY = "fictional+news&495"  # pragma: allowlist secret
MARKER = "UNTRUSTED-RESPONSE-MARKER"
ROWS = [{"date": "2026-07-10", "price": 123.0}]


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
    close = requests.Session.close

    def get(self, url, params=None, timeout=None):
        calls.append((url, dict(params or {}), timeout))
        if not pending:
            raise AssertionError("Unexpected HTTP")
        value = pending.pop(0)
        if isinstance(value, Exception):
            raise value
        return value

    def finish(self):
        closed.append(self)
        close(self)

    monkeypatch.setattr(requests.Session, "get", get)
    monkeypatch.setattr(requests.Session, "close", finish)

    def setup(*values):
        pending.extend(values)
        return calls, closed

    return setup


def fetch(client):
    return client.get_eod_rows("NQUSD", "2026-03-01", "2026-07-20", as_of="2026-07-10")


def test_generated_adjacent_client_exact_stable_range_and_owned_session(http, monkeypatch):
    monkeypatch.setitem(sys.modules, "fmp_client", types.SimpleNamespace(FMPClient=None))
    calls, closed = http(Response(ROWS))
    with analyzer.PriceClient(KEY, sleep_seconds=0) as client:
        assert fetch(client) == (ROWS, None)
        assert client.api_calls_made == 1
    assert len(closed) == 1
    assert calls == [
        (
            "https://financialmodelingprep.com/stable/historical-price-eod/light",
            {"symbol": "NQUSD", "from": "2026-03-01", "to": "2026-07-20", "apikey": KEY},
            30,
        )
    ]
    assert "_news_reaction_generated_fmp" in sys.modules


@pytest.mark.parametrize("status", [401, 402, 403, 404, 500, 503])
def test_shared_http_failures_once_static_and_closed(http, capsys, status):
    calls, closed = http(Response(status=status, text=MARKER + KEY + quote(KEY, safe="")))
    with analyzer.PriceClient(KEY, sleep_seconds=0) as client:
        rows, error = fetch(client)
        assert rows is None
        assert analyzer._status_code_for_error(error) == f"http_{status}"
        assert client.api_calls_made == 1
    assert len(calls) == 1 and len(closed) == 1
    output = capsys.readouterr()
    for marker in [MARKER, KEY, quote(KEY, safe="")]:
        assert marker not in error + output.out + output.err


def test_json_retry_counts_actual_attempts_and_success(http):
    calls, _ = http(Response(ValueError(MARKER + KEY)), Response(ROWS))
    with analyzer.PriceClient(KEY, sleep_seconds=0) as client:
        assert fetch(client) == (ROWS, None)
        assert client.api_calls_made == 2
    assert len(calls) == 2 and calls[0] == calls[1]


def test_exhausted_json_is_not_empty_success(http, capsys):
    calls, _ = http(Response(ValueError(MARKER + KEY)), Response(ValueError(MARKER)))
    with analyzer.PriceClient(KEY, sleep_seconds=0) as client:
        rows, error = fetch(client)
        assert rows is None and analyzer._status_code_for_error(error) == "invalid_json"
    output = capsys.readouterr()
    assert MARKER not in error + output.out + output.err
    assert KEY not in error + output.out + output.err
    assert len(calls) == 2


def test_exhausted_429_retains_generated_stop_state(http):
    calls, _ = http(Response(status=429), Response(status=429))
    with analyzer.PriceClient(KEY, sleep_seconds=0) as client:
        rows, error = fetch(client)
        assert rows is None and analyzer._status_code_for_error(error) == "http_429"
        assert client.api_calls_made == 2
        again, error = fetch(client)
        assert again is None and analyzer._status_code_for_error(error) == "http_429"
    assert len(calls) == 2


@pytest.mark.parametrize("exception", [requests.Timeout, requests.ConnectionError])
def test_transport_failure_static_without_local_retry(http, capsys, exception):
    calls, _ = http(exception(MARKER + KEY + quote(KEY, safe="")))
    with analyzer.PriceClient(KEY, sleep_seconds=0) as client:
        rows, error = fetch(client)
        assert rows is None and analyzer._status_code_for_error(error) == "request_exception"
    output = capsys.readouterr()
    assert len(calls) == 1
    for marker in [MARKER, KEY, quote(KEY, safe="")]:
        assert marker not in error + output.err + output.out


@pytest.mark.parametrize("payload", [[], None, {}, [{"date": "2026-07-10", "close": 100}]])
def test_empty_is_distinct_from_invalid_schema(http, payload):
    http(Response(payload))
    with analyzer.PriceClient(KEY, sleep_seconds=0) as client:
        rows, error = fetch(client)
    if payload == []:
        assert rows == [] and error is None
    else:
        assert rows is None and error.startswith("schema_drift:")


def test_replacement_and_idempotent_close(http):
    _, closed = http()
    client = analyzer.PriceClient(KEY, sleep_seconds=0)
    old = client.session
    replacement = requests.Session()
    client.session = replacement
    assert closed == [old]
    client.close()
    client.close()
    assert closed == [old, replacement]


@pytest.mark.parametrize("kind", ["success", "no_source", "exception"])
def test_main_closes_before_report_or_exception(tmp_path, monkeypatch, http, kind):
    from test_price_source_cutoff import run_main, weekday_rows

    _, closed = http()
    if kind == "exception":

        def fail(*args, **kwargs):
            raise RuntimeError("fictional computation failure")

        monkeypatch.setattr(analyzer, "fetch_price_series", fail)
        with pytest.raises(RuntimeError, match="fictional computation"):
            run_main(tmp_path, monkeypatch, {})
    else:
        by_symbol = (
            {"NQUSD": (200, weekday_rows(1))}
            if kind == "success"
            else {"NQUSD": (402, MARKER), "QQQ": (403, MARKER)}
        )
        run_main(tmp_path, monkeypatch, by_symbol)
    assert len(closed) == 1


def test_help_and_early_validation_without_requests_or_credentials(tmp_path):
    script = Path(analyzer.__file__).resolve()
    code = "import sys,runpy;sys.modules['requests']=None;sys.path.insert(0,sys.argv[1]);sys.argv=[sys.argv[2],'--help'];runpy.run_path(sys.argv[0],run_name='__main__')"
    result = subprocess.run(
        [sys.executable, "-c", code, str(script.parent), str(script)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0 and "--as-of" in result.stdout


def test_extracted_package_uses_local_generated_client(tmp_path):
    root = Path(__file__).resolve().parents[4]
    with zipfile.ZipFile(root / "skill-packages/news-reaction-failure-analyzer.skill") as archive:
        archive.extractall(tmp_path)
    scripts = tmp_path / "news-reaction-failure-analyzer/scripts"
    code = """
import sys,types,requests
sys.path.insert(0,sys.argv[1])
sys.modules['fmp_client']=types.SimpleNamespace(FMPClient=None)
closed=[]
class Response:
    status_code=200
    def json(self): return [{'date':'2026-07-10','price':123.0}]
class Session:
    def get(self,url,params,timeout):
        assert url.endswith('/stable/historical-price-eod/light')
        assert params['from']=='2026-03-01' and params['to']=='2026-07-20'
        assert params['apikey']=='fictional-marker' and timeout==30  # pragma: allowlist secret
        return Response()
    def close(self): closed.append(True)
requests.Session=Session
from analyze_news_reaction import PriceClient
with PriceClient('fictional-marker',sleep_seconds=0) as client:
    rows,error=client.get_eod_rows('NQUSD','2026-03-01','2026-07-20')
    assert rows==[{'date':'2026-07-10','price':123.0}] and error is None
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


def test_configurable_pacing_is_shared_across_source_probes(http, monkeypatch):
    delays = []
    calls, _ = http(Response(ROWS), Response(ROWS))
    monkeypatch.setattr("time.time", lambda: 1000.0)
    monkeypatch.setattr("time.sleep", delays.append)
    with analyzer.PriceClient(KEY, sleep_seconds=0.4) as client:
        fetch(client)
        fetch(client)
    assert delays == [0.4] and len(calls) == 2


def test_explicit_blank_key_cannot_inherit_ambient_credential(monkeypatch, http):
    calls, _ = http()
    monkeypatch.setenv("FMP_API_KEY", "fictional-ambient")
    with pytest.raises(ValueError, match="explicit FMP API key"):
        analyzer.PriceClient("")
    assert not calls


def test_closed_client_rejects_new_requests_without_http(http):
    calls, _ = http()
    client = analyzer.PriceClient(KEY)
    client.close()
    with pytest.raises(RuntimeError, match="closed"):
        fetch(client)
    assert not calls


def test_later_proxy_attempt_keeps_429_reason_without_more_http(http):
    calls, _ = http(Response(status=429), Response(status=429))
    with analyzer.PriceClient(KEY, sleep_seconds=0) as client:
        result = analyzer.fetch_price_series(
            client,
            [("NQUSD", "futures", False), ("QQQ", "etf", False)],
            "2026-03-01",
            "2026-07-20",
            "2026-07-10",
        )
    assert [attempt["status"] for attempt in result["attempts"]] == ["http_429", "http_429"]
    assert len(calls) == 2
