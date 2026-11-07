"""Offline contracts for the fetch-to-report CLI and provider failure paths."""

import json
import sys
from dataclasses import dataclass

import fetch_earnings_fmp as fetcher
import generate_report as reporter
import pytest
import requests

# Patch targets use fetcher.FMPClient — the vendored class object the script
# actually instantiates — instead of the sys.modules-cached module name, so
# cross-suite pytest processes that cached a different skill's fmp_client
# never patch the wrong class (Issue #495).
FMPClient = fetcher.FMPClient


@dataclass
class RateFailure:
    """Shaped failure injected through the vendored client's transport."""

    message: str


@pytest.fixture(autouse=True)
def offline(monkeypatch, tmp_path):
    """Never use developer credentials, the network, or repository output paths."""
    monkeypatch.delenv("FMP_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)

    def forbidden(*args, **kwargs):
        pytest.fail("Unexpected network request")

    monkeypatch.setattr(requests.sessions.Session, "request", forbidden)


def patch_rate_get(monkeypatch, replies):
    """Replace FMPClient._rate_limited_get with an offline fake transport.

    Each item of ``replies`` is consumed per call: a json-able payload on
    success, None plus a RateFailure to simulate the generated client's
    HTTP-failure contract (None payload + _last_error), or an exception
    instance to raise. Returns the captured calls as
    ``[{"url", "params", "quiet", "client"}, ...]``.
    """
    calls = []

    def fake(self, url, params=None, quiet=False):
        self_obj = self
        item = replies.pop(0)
        record = {"url": url, "params": params, "quiet": quiet, "client": self_obj}
        calls.append(record)
        if isinstance(item, Exception):
            raise item
        if isinstance(item, RateFailure):
            # Generated-client HTTP-failure contract: None payload + _last_error.
            self._last_error = item.message
            return None
        self._last_error = None
        return item

    monkeypatch.setattr(fetcher.FMPClient, "_rate_limited_get", fake)
    return calls


def fetch_args(monkeypatch, *extra):
    monkeypatch.setattr(sys, "argv", ["fetch_earnings_fmp.py", "2026-09-07", "2026-09-11", *extra])


@pytest.mark.parametrize(
    "failure,message",
    [
        ("HTTP 401 - invalid key", "Invalid API key"),
        ("HTTP 429 (daily rate limit)", "Rate limit exceeded"),
        ("HTTP 503 - fixture outage", "Unexpected error"),
    ],
)
def test_fetch_failure_emits_no_json(monkeypatch, capsys, failure, message):
    fetch_args(monkeypatch, "fixture-key")
    with pytest.raises(SystemExit) as error:
        calls = patch_rate_get(monkeypatch, [RateFailure(failure)])
        fetcher.main()
    assert error.value.code == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert message in captured.err
    assert "fixture-key" not in captured.err
    # The calendar GET carries no apikey query param (header auth, Issue #495);
    # the key travels only in the client session headers and RateFailure does
    # the rest.
    # The first of the per-day requests (gh-672 chunking): from == to.
    assert calls[0]["params"] == {
        "from": "2026-09-07",
        "to": "2026-09-07",
        "includeReportTimes": "true",
    }
    assert calls[0]["client"].session.headers.get("apikey") == "fixture-key"


def test_fetch_error_message_payload_emits_no_json(monkeypatch, capsys):
    fetch_args(monkeypatch, "fixture-key")
    with pytest.raises(SystemExit) as error:
        patch_rate_get(monkeypatch, [{"Error Message": "fixture provider error"}])
        fetcher.main()
    assert error.value.code == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "fixture provider error" in captured.err
    assert "fixture-key" not in captured.err


def test_fetch_to_report_pipeline(monkeypatch, tmp_path, capsys):
    earnings = [
        {"symbol": "LATE", "date": "2026-09-08", "time": "amc", "epsEstimated": 1.25},
        {"symbol": "EARLY", "date": "2026-09-07", "time": "bmo"},
        {"symbol": "SMALL", "date": "2026-09-07"},
        {"symbol": "FOREIGN", "date": "2026-09-07"},
        {"symbol": "UNAVAILABLE", "date": "2026-09-07"},
    ]
    profiles = {
        "LATE": {"symbol": "LATE", "marketCap": 12e9, "exchange": "NASDAQ"},
        "EARLY": {"symbol": "EARLY", "marketCap": 3e9, "exchange": "NYSE"},
        "SMALL": {"symbol": "SMALL", "marketCap": 1e9, "exchange": "NYSE"},
        "FOREIGN": {"symbol": "FOREIGN", "marketCap": 20e9, "exchange": "LSE"},
    }
    seen = []

    earnings_by_date = {}
    for row in earnings:
        earnings_by_date.setdefault(row["date"], []).append(row)

    def fake_rate(self, url, params=None, quiet=False):
        if url.endswith("/earnings-calendar"):
            # One request per day of the window (gh-672 chunking).
            assert params["from"] == params["to"]
            assert params["includeReportTimes"] == "true"
            self._last_error = None
            return earnings_by_date.get(params["from"], [])
        # /stable/profile?symbol=SYMBOL per-symbol (v3 path symbol is
        # rewritten to the query param by _fmp_compat).
        assert url.endswith("/stable/profile")

        symbol = params["symbol"]
        assert set(params) == {"symbol"}
        seen.append(symbol)
        if symbol == "UNAVAILABLE":
            raise requests.Timeout("fixture timeout")
        self._last_error = None
        return [profiles[symbol]]

    monkeypatch.setattr(FMPClient, "_rate_limited_get", fake_rate)
    monkeypatch.setenv("FMP_API_KEY", "fixture-key")
    fetch_args(monkeypatch)
    fetcher.main()
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert sorted(seen) == ["EARLY", "FOREIGN", "LATE", "SMALL", "UNAVAILABLE"]
    assert [row["symbol"] for row in payload] == ["EARLY", "LATE"]
    assert [row["timing"] for row in payload] == ["BMO", "AMC"]
    assert [row["marketCapFormatted"] for row in payload] == ["$3.0B", "$12.0B"]
    assert payload[1]["epsEstimated"] == 1.25
    assert payload[0]["epsEstimated"] is None
    assert "Failed to fetch profile for UNAVAILABLE" in captured.err
    assert "Final dataset: 2 companies" in captured.err
    assert "fixture-key" not in captured.err

    source = tmp_path / "earnings.json"
    source.write_text(captured.out, encoding="utf-8")
    output = tmp_path / "calendar.md"
    monkeypatch.setattr(sys, "argv", ["generate_report.py", str(source), str(output)])
    reporter.main()
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Report saved to:" in captured.err
    report = output.read_text(encoding="utf-8")
    assert "**Total Companies**: 2" in report
    assert "**Mega/Large Cap (>$10B)**: 1" in report
    assert "**Mid Cap ($2B-$10B)**: 1" in report
    assert "| EARLY | EARLY | $3.0B | N/A | N/A | N/A |" in report
    assert "| LATE | LATE | $12.0B | N/A | $1.25 | N/A |" in report
    assert "SMALL" not in report and "FOREIGN" not in report and "UNAVAILABLE" not in report


@pytest.mark.parametrize("has_earnings", [False, True])
def test_empty_fetch_outputs_array(monkeypatch, capsys, has_earnings):
    # gh-672: one calendar request per day of the 2026-09-07..2026-09-11
    # window (5 days), then one profile request when a symbol was found.
    day_rows = [{"symbol": "MISSING", "date": "2026-09-07"}] if has_earnings else []
    replies = [day_rows and list(day_rows) or [] for _ in range(5)]
    if has_earnings:
        replies.append([])  # the profile request finds no row
    expected_calls = len(replies)
    calls = patch_rate_get(monkeypatch, replies)
    fetch_args(monkeypatch, "fixture-key")
    with pytest.raises(SystemExit) as error:
        fetcher.main()
    assert error.value.code == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out) == []
    assert "Warning:" in captured.err
    assert len(calls) == expected_calls


@pytest.mark.parametrize(
    "args,message",
    [
        ([], "Missing required arguments"),
        (["invalid", "2026-09-11"], "Invalid start date"),
        (["2026-09-07", "invalid"], "Invalid end date"),
        (["2026-09-07", "2026-09-11"], "No API key found"),
    ],
)
def test_fetch_cli_rejects_invalid_setup(monkeypatch, capsys, args, message):
    monkeypatch.setattr(sys, "argv", ["fetch_earnings_fmp.py", *args])
    with pytest.raises(SystemExit) as error:
        fetcher.main()
    assert error.value.code == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert message in captured.err


@pytest.mark.parametrize("module", [fetcher, reporter])
def test_help_exits_without_network(monkeypatch, capsys, module):
    monkeypatch.setattr(sys, "argv", [module.__name__, "--help"])
    with pytest.raises(SystemExit) as error:
        module.main()
    assert error.value.code == 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Usage:" in captured.err


@pytest.mark.parametrize(
    "content,message",
    [
        (None, "File not found"),
        ("not json", "Invalid JSON"),
        ('{"symbol":"X"}', "must contain an array"),
    ],
)
def test_report_bad_input_does_not_create_output(monkeypatch, tmp_path, capsys, content, message):
    source = tmp_path / "input.json"
    if content is not None:
        source.write_text(content, encoding="utf-8")
    output = tmp_path / "report.md"
    monkeypatch.setattr(sys, "argv", ["generate_report.py", str(source), str(output)])
    with pytest.raises(SystemExit) as error:
        reporter.main()
    assert error.value.code == 1
    assert not output.exists()
    captured = capsys.readouterr()
    assert captured.out == ""
    assert message in captured.err


def test_empty_report_to_stdout(monkeypatch, tmp_path, capsys):
    source = tmp_path / "empty.json"
    source.write_text("[]", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["generate_report.py", str(source)])
    reporter.main()
    captured = capsys.readouterr()
    assert captured.out.strip() == "# Earnings Calendar\n\nNo earnings data available."
    assert "Loaded 0 companies" in captured.err


def test_no_api_key_via_client_falls_back_to_script_message(monkeypatch, capsys):
    # The generated client self-resolves FMP_API_KEY; the script never relies
    # on that fallback and keeps its own no-key usage path pinned here.
    monkeypatch.setattr(sys, "argv", ["fetch_earnings_fmp.py", "2026-09-07", "2026-09-11"])
    monkeypatch.delenv("FMP_API_KEY", raising=False)
    with pytest.raises(SystemExit) as error:
        fetcher.main()
    assert error.value.code == 1
    captured = capsys.readouterr()
    assert "No API key found" in captured.err
