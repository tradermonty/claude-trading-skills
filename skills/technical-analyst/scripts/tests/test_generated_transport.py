"""Exercise the generated HTTP path, not an adapter-method stub; no live calls."""

import json
import subprocess
import sys
import types
import zipfile
from pathlib import Path
from urllib.parse import quote

import check_weekly_price_action as checker
import pytest
import requests

SECRET = "fictional/key+token"  # pragma: allowlist secret


class Response:
    def __init__(self, payload=None, code=200, invalid=False, text=""):
        self.payload, self.status_code, self.invalid = payload, code, invalid
        self.text = text or json.dumps(payload)

    def json(self):
        if self.invalid:
            raise ValueError(f"invalid body {SECRET}")
        return self.payload


class Session:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, dict(params), timeout))
        value = self.responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


@pytest.fixture
def client(monkeypatch):
    value = checker.PriceClient(SECRET, sleep_seconds=0)
    monkeypatch.setattr(checker.time, "sleep", lambda _: None)
    return value


def test_explicit_range_query_auth_and_unmodified_rows(client):
    rows = [{"date": "2026-01-02", "close": 20}, {"date": "2026-01-01", "close": 19}]
    client.session = Session(Response(rows))
    assert client.get_eod_rows("BRK-B", "2026-01-01", "2026-01-02") == (rows, None)
    assert client.session.calls == [
        (
            "https://financialmodelingprep.com/stable/historical-price-eod/full",
            {"symbol": "BRK-B", "from": "2026-01-01", "to": "2026-01-02", "apikey": SECRET},
            30,
        )
    ]
    assert client.api_calls_made == 1


@pytest.mark.parametrize("payload", [[], {}, {"Error Message": "denied"}, "bad", [None]])
def test_empty_vs_malformed_success(client, payload):
    client.session = Session(Response(payload))
    rows, error = client.get_eod_rows("AAPL", "2026-01-01", "2026-01-02")
    if payload == []:
        assert rows == [] and error is None
    else:
        assert rows is None and "flat list" in error


def failure_report(result, path):
    output = checker._insufficient_data_output("NQ", "CROWDED_LONG", "no_price_source", {})
    output["price_source_attempts"] = result["attempts"]
    checker.generate_json_report(output, str(path))
    return path.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "failure",
    [
        Response(code=402, text=f"denied {SECRET}"),
        Response(code=403, text=f"apikey={SECRET}"),
        Response(code=500, text=f"apikey%3D{quote(SECRET, safe='')}"),
        requests.exceptions.ConnectionError(f"bare key {SECRET}"),
    ],
)
def test_ordinary_failure_sends_next_source_and_redacts(client, failure, capsys, tmp_path):
    client.session = Session(failure, Response([]))
    result = checker.fetch_price_series(
        client,
        [("NQUSD", "futures", False), ("QQQ", "etf", False)],
        "2026-01-01",
        "2026-01-02",
        "2026-01-02",
    )
    assert len(client.session.calls) == 2
    assert [call[1]["symbol"] for call in client.session.calls] == ["NQUSD", "QQQ"]
    assert result["error"] == "no_price_source" and len(result["attempts"]) == 2
    saved = failure_report(result, tmp_path / "failure.json")
    diagnostics = str(result) + saved + capsys.readouterr().err
    assert SECRET not in diagnostics and quote(SECRET, safe="") not in diagnostics
    assert "REDACTED" in diagnostics


def test_invalid_json_retries_once_and_fails_redacted(client, capsys):
    client.session = Session(Response(invalid=True), Response(invalid=True))
    rows, error = client.get_eod_rows("AAPL", "2026-01-01", "2026-01-02")
    assert rows is None and "invalid JSON" in error
    assert len(client.session.calls) == 2 and client.api_calls_made == 2
    assert SECRET not in error + capsys.readouterr().err


def test_exhausted_429_stops_entire_source_chain_without_extra_wait(client, monkeypatch, tmp_path):
    sleeps = []
    monkeypatch.setattr(checker.time, "sleep", sleeps.append)
    client.session = Session(Response(code=429), Response(code=429))
    result = checker.fetch_price_series(
        client,
        [("NQUSD", "futures", False), ("QQQ", "etf", False)],
        "2026-01-01",
        "2026-01-02",
        "2026-01-02",
    )
    assert len(client.session.calls) == 2 and sleeps == [60]
    assert client.api_calls_made == 2
    assert result["error"] == "no_price_source"
    assert "HTTP 429" in result["attempts"][0]["status"]
    assert "daily rate limit already reached" in result["attempts"][1]["status"]
    assert SECRET not in failure_report(result, tmp_path / "rate-limit.json")


def test_429_can_recover_on_single_retry(client):
    client.session = Session(Response(code=429), Response([]))
    assert client.get_eod_rows("AAPL", "2026-01-01", "2026-01-02") == ([], None)
    assert len(client.session.calls) == 2
    assert not client._transport.rate_limit_reached


def test_key_priority_and_blank_cli_fail_without_environment_fallback(monkeypatch):
    monkeypatch.setenv("FMP_API_KEY", "fictional-environment")
    assert checker.get_api_key("explicit") == "explicit"
    assert checker.get_api_key("   ") is None
    assert checker.get_api_key(None) == "fictional-environment"


def test_unpacked_package_uses_own_generated_transport(tmp_path):
    root = Path(__file__).resolve().parents[4]
    with zipfile.ZipFile(root / "skill-packages/technical-analyst.skill") as bundle:
        bundle.extractall(tmp_path)
    script = next(tmp_path.rglob("check_weekly_price_action.py"))
    program = """
import sys
sys.path.insert(0, sys.argv[1])
import check_weekly_price_action as checker
class Response:
    status_code = 200
    def json(self): return []
class Session:
    def get(self, url, params=None, timeout=None):
        assert url.endswith('/stable/historical-price-eod/full')
        assert timeout == 30
        return Response()
client = checker.PriceClient('fictional', sleep_seconds=0)
client.session = Session()
assert client.get_eod_rows('AAPL', '2026-01-01', '2026-01-02') == ([], None)
import fmp_client
assert fmp_client.__file__.startswith(sys.argv[1])
"""
    result = subprocess.run(
        [sys.executable, "-c", program, str(script.parent)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr


def test_real_cli_writes_safe_json_and_markdown_after_provider_failures(
    client, monkeypatch, tmp_path, capsys
):
    client.session = Session(
        Response(code=402, text=f"denied {SECRET}"),
        Response(code=500, text=f"key {quote(SECRET, safe='')}"),
    )
    monkeypatch.setattr(checker, "PriceClient", lambda **kwargs: client)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "check_weekly_price_action.py",
            "--symbol",
            "NQ",
            "--direction",
            "CROWDED_LONG",
            "--as-of",
            "2026-01-02",
            "--api-key",
            SECRET,
            "--output-dir",
            str(tmp_path),
        ],
    )
    with pytest.raises(SystemExit) as exit_:
        checker.main()
    assert exit_.value.code == 0
    report = json.loads(next(tmp_path.glob("*.json")).read_text(encoding="utf-8"))
    assert report["verdict"] == "INSUFFICIENT_DATA"
    assert report["verdict_reason"] == "no_price_source"
    assert next(tmp_path.glob("*.md")).is_file()
    captured = capsys.readouterr()
    published = (
        captured.out
        + captured.err
        + "".join(p.read_text(encoding="utf-8") for p in tmp_path.iterdir())
    )
    assert SECRET not in published and quote(SECRET, safe="") not in published
    assert len(client.session.calls) == 2


def test_foreign_cached_client_cannot_replace_the_sibling_transport(monkeypatch):
    foreign = types.ModuleType("fmp_client")

    class ForeignClient:
        def __init__(self, **kwargs):
            raise AssertionError("Foreign client must never be used")

    foreign.FMPClient = ForeignClient
    monkeypatch.setitem(sys.modules, "fmp_client", foreign)
    value = checker.PriceClient("fictional", sleep_seconds=0)
    value.session = Session(Response([]))
    assert value.get_eod_rows("AAPL", "2026-01-01", "2026-01-02") == ([], None)
    assert value.api_calls_made == 1
    assert sys.modules["fmp_client"] is foreign
