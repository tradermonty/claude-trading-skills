"""Offline contracts for the fetch-to-report CLI and provider failure paths."""

import json
import sys
from unittest.mock import Mock

import fetch_earnings_fmp as fetcher
import generate_report as reporter
import pytest
import requests


@pytest.fixture(autouse=True)
def offline(monkeypatch, tmp_path):
    """Never use developer credentials, the network, or repository output paths."""
    monkeypatch.delenv("FMP_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)

    def forbidden(*args, **kwargs):
        pytest.fail("Unexpected network request")

    monkeypatch.setattr(requests.sessions.Session, "request", forbidden)


def response(payload, status=200):
    result = Mock(status_code=status)
    result.json.return_value = payload
    if status >= 400:
        result.raise_for_status.side_effect = requests.HTTPError(f"HTTP {status}")
    return result


def fetch_args(monkeypatch, *extra):
    monkeypatch.setattr(sys, "argv", ["fetch_earnings_fmp.py", "2026-09-07", "2026-09-11", *extra])


@pytest.mark.parametrize(
    "reply,message",
    [
        (response([], 401), "Invalid API key"),
        (response([], 429), "Rate limit exceeded"),
        (response([], 503), "Unexpected error"),
        (response({"Error Message": "fixture provider error"}), "fixture provider error"),
        (requests.Timeout(), "Request timeout"),
        (requests.ConnectionError(), "Connection error"),
    ],
)
def test_fetch_failure_emits_no_json(monkeypatch, capsys, reply, message):
    fake_get = Mock(side_effect=reply) if isinstance(reply, Exception) else Mock(return_value=reply)
    monkeypatch.setattr(fetcher.requests, "get", fake_get)
    fetch_args(monkeypatch, "fixture-key")
    with pytest.raises(SystemExit) as error:
        fetcher.main()
    assert error.value.code == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert message in captured.err
    assert "fixture-key" not in captured.err
    fake_get.assert_called_once_with(
        "https://financialmodelingprep.com/stable/earnings-calendar",
        params={
            "from": "2026-09-07",
            "to": "2026-09-11",
            "apikey": "fixture-key",  # pragma: allowlist secret
        },
        timeout=30,
    )


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

    def fake_get(url, *, params, timeout):
        assert timeout == 30
        assert params["apikey"] == "fixture-key"  # pragma: allowlist secret
        if url.endswith("/earnings-calendar"):
            assert params == {
                "from": "2026-09-07",
                "to": "2026-09-11",
                "apikey": "fixture-key",  # pragma: allowlist secret
            }
            return response(earnings)
        assert url == "https://financialmodelingprep.com/stable/profile"
        assert set(params) == {"symbol", "apikey"}
        symbol = params["symbol"]
        seen.append(symbol)
        if symbol == "UNAVAILABLE":
            raise requests.Timeout("fixture timeout")
        return response([profiles[symbol]])

    monkeypatch.setattr(fetcher.requests, "get", fake_get)
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
    rows = [{"symbol": "MISSING", "date": "2026-09-07"}] if has_earnings else []
    fake_get = Mock(side_effect=[response(rows), response([])])
    monkeypatch.setattr(fetcher.requests, "get", fake_get)
    fetch_args(monkeypatch, "fixture-key")
    with pytest.raises(SystemExit) as error:
        fetcher.main()
    assert error.value.code == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out) == []
    assert "Warning:" in captured.err
    assert fake_get.call_count == (2 if has_earnings else 1)


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
