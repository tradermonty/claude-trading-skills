"""Tests for the Portfolio Manager Alpaca connection check."""

from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import MagicMock

import check_alpaca_connection as alpaca
import pytest
import requests

API_KEY = "public-api-key-value"  # pragma: allowlist secret
SECRET_KEY = "private-secret-key-value"  # pragma: allowlist secret
ACCOUNT_NUMBER = "PA123456789"

NUMERIC_PLACEHOLDER_RE = re.compile(
    r"\$[XYZ]+(?:,[XYZ]+)*(?:\.[XYZ]+)?"
    r"|(?<![A-Za-z])(?:X{2,3}|Y{2,3}|Z{2,3})(?:\.[XYZ]+)?%?(?![A-Za-zXYZ])"
    r"|(?<![A-Za-z])[XYZ]\.[XYZ]+%?"
    r"|(?<![A-Za-z])[XYZ]%"
)


def _response(status_code, payload=None, text="response body"):
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = payload
    response.text = text
    return response


def _assert_secrets_hidden(captured):
    combined = captured.out + captured.err
    assert API_KEY not in combined
    assert SECRET_KEY not in combined
    assert ACCOUNT_NUMBER not in combined


def test_numeric_placeholder_pattern_covers_known_formats():
    samples = (
        "$XXX,XXX",
        "$XX.XX",
        "XX.X%",
        "YY.Y%",
        "Z.Z%",
        "XX%",
        "X.X%",
        "X%",
        "XX/100",
    )

    assert all(NUMERIC_PLACEHOLDER_RE.search(sample) for sample in samples)


def test_skill_has_no_numeric_placeholders():
    skill_file = Path(__file__).resolve().parents[2] / "SKILL.md"

    assert NUMERIC_PLACEHOLDER_RE.findall(skill_file.read_text(encoding="utf-8")) == []


def test_load_credentials_and_base_urls(monkeypatch):
    monkeypatch.setenv("ALPACA_API_KEY", API_KEY)
    monkeypatch.setenv("ALPACA_SECRET_KEY", SECRET_KEY)
    monkeypatch.setenv("ALPACA_PAPER", "false")

    assert alpaca.load_credentials() == (API_KEY, SECRET_KEY, False)
    assert alpaca.get_base_url(True) == "https://paper-api.alpaca.markets"
    assert alpaca.get_base_url(False) == "https://api.alpaca.markets"


def test_load_credentials_rejects_missing_values_without_leaking(monkeypatch, capsys):
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)

    with pytest.raises(SystemExit, match="1"):
        alpaca.load_credentials()

    _assert_secrets_hidden(capsys.readouterr())


def test_account_success_masks_account_and_uses_timeout(monkeypatch, capsys):
    mock_get = MagicMock(
        return_value=_response(
            200,
            {
                "status": "ACTIVE",
                "account_number": ACCOUNT_NUMBER,
                "equity": "10000",
                "cash": "2500",
                "buying_power": "5000",
                "portfolio_value": "10000",
            },
        )
    )
    monkeypatch.setattr(alpaca.requests, "get", mock_get)

    assert alpaca.test_account_info(API_KEY, SECRET_KEY, alpaca.get_base_url()) is True

    assert f"****{ACCOUNT_NUMBER[-4:]}" in capsys.readouterr().out
    assert mock_get.call_args.kwargs["timeout"] == alpaca.REQUEST_TIMEOUT_SECONDS


@pytest.mark.parametrize(
    ("status_code", "message"),
    ((401, "Authentication failed"), (403, "Forbidden"), (500, "Unexpected error")),
)
def test_account_http_errors_hide_credentials(monkeypatch, capsys, status_code, message):
    monkeypatch.setattr(
        alpaca.requests,
        "get",
        MagicMock(return_value=_response(status_code, text="safe error")),
    )

    assert alpaca.test_account_info(API_KEY, SECRET_KEY, alpaca.get_base_url()) is False

    captured = capsys.readouterr()
    assert message in captured.out
    _assert_secrets_hidden(captured)


def test_account_network_error_hides_credentials(monkeypatch, capsys):
    monkeypatch.setattr(
        alpaca.requests,
        "get",
        MagicMock(
            side_effect=requests.RequestException(f"network unavailable {API_KEY} {SECRET_KEY}")
        ),
    )

    assert alpaca.test_account_info(API_KEY, SECRET_KEY, alpaca.get_base_url()) is False

    captured = capsys.readouterr()
    assert "Network error" in captured.out
    _assert_secrets_hidden(captured)


def test_account_invalid_json_hides_credentials(monkeypatch, capsys):
    response = _response(200)
    response.json.side_effect = ValueError("invalid json")
    monkeypatch.setattr(alpaca.requests, "get", MagicMock(return_value=response))

    assert alpaca.test_account_info(API_KEY, SECRET_KEY, alpaca.get_base_url()) is False

    captured = capsys.readouterr()
    assert "Invalid or malformed response" in captured.out
    _assert_secrets_hidden(captured)


@pytest.mark.parametrize("payload", ([], {}, {"status": "ACTIVE"}))
def test_account_rejects_malformed_success_payload(monkeypatch, capsys, payload):
    monkeypatch.setattr(
        alpaca.requests,
        "get",
        MagicMock(return_value=_response(200, payload)),
    )

    assert alpaca.test_account_info(API_KEY, SECRET_KEY, alpaca.get_base_url()) is False

    captured = capsys.readouterr()
    assert "Invalid or malformed response" in captured.out
    _assert_secrets_hidden(captured)


@pytest.mark.parametrize(
    "positions",
    (
        [],
        [
            {
                "symbol": "AAPL",
                "qty": "2",
                "avg_entry_price": "100",
                "current_price": "110",
                "market_value": "220",
                "unrealized_pl": "20",
                "unrealized_plpc": "0.1",
            }
        ],
    ),
)
def test_positions_success(monkeypatch, capsys, positions):
    mock_get = MagicMock(return_value=_response(200, positions))
    monkeypatch.setattr(alpaca.requests, "get", mock_get)

    assert alpaca.test_positions(API_KEY, SECRET_KEY, alpaca.get_base_url()) is True

    captured = capsys.readouterr()
    assert "API connection successful" in captured.out
    _assert_secrets_hidden(captured)
    assert mock_get.call_args.kwargs["timeout"] == alpaca.REQUEST_TIMEOUT_SECONDS


def test_positions_http_and_network_errors(monkeypatch, capsys):
    mock_get = MagicMock(return_value=_response(503, text="unavailable"))
    monkeypatch.setattr(alpaca.requests, "get", mock_get)
    assert alpaca.test_positions(API_KEY, SECRET_KEY, alpaca.get_base_url()) is False

    mock_get.side_effect = requests.RequestException(f"network unavailable {API_KEY} {SECRET_KEY}")
    assert alpaca.test_positions(API_KEY, SECRET_KEY, alpaca.get_base_url()) is False

    captured = capsys.readouterr()
    assert "HTTP 503" in captured.err
    assert "Network error" in captured.out
    _assert_secrets_hidden(captured)


def test_positions_invalid_json_hides_credentials(monkeypatch, capsys):
    response = _response(200)
    response.json.side_effect = ValueError("invalid json")
    monkeypatch.setattr(alpaca.requests, "get", MagicMock(return_value=response))

    assert alpaca.test_positions(API_KEY, SECRET_KEY, alpaca.get_base_url()) is False

    captured = capsys.readouterr()
    assert "Invalid or malformed response" in captured.out
    _assert_secrets_hidden(captured)


@pytest.mark.parametrize("payload", ({}, [None], [{"symbol": "AAPL"}]))
def test_positions_rejects_malformed_success_payload(monkeypatch, capsys, payload):
    monkeypatch.setattr(
        alpaca.requests,
        "get",
        MagicMock(return_value=_response(200, payload)),
    )

    assert alpaca.test_positions(API_KEY, SECRET_KEY, alpaca.get_base_url()) is False

    captured = capsys.readouterr()
    assert "Invalid or malformed response" in captured.out
    _assert_secrets_hidden(captured)


@pytest.mark.parametrize("status_code", (200, 402, 500))
def test_market_data_responses_use_timeout_and_hide_credentials(monkeypatch, capsys, status_code):
    payload = {"quote": {"bp": 100.0, "ap": 100.5}} if status_code == 200 else {}
    mock_get = MagicMock(return_value=_response(status_code, payload))
    monkeypatch.setattr(alpaca.requests, "get", mock_get)

    alpaca.test_market_data(API_KEY, SECRET_KEY)

    captured = capsys.readouterr()
    _assert_secrets_hidden(captured)
    assert mock_get.call_args.kwargs["timeout"] == alpaca.REQUEST_TIMEOUT_SECONDS


def test_market_data_network_error_is_advisory(monkeypatch, capsys):
    monkeypatch.setattr(
        alpaca.requests,
        "get",
        MagicMock(
            side_effect=requests.RequestException(f"network unavailable {API_KEY} {SECRET_KEY}")
        ),
    )

    alpaca.test_market_data(API_KEY, SECRET_KEY)

    captured = capsys.readouterr()
    assert "Could not contact the market data API" in captured.out
    _assert_secrets_hidden(captured)


def test_market_data_invalid_json_is_advisory(monkeypatch, capsys):
    response = _response(200)
    response.json.side_effect = ValueError("invalid json")
    monkeypatch.setattr(alpaca.requests, "get", MagicMock(return_value=response))

    alpaca.test_market_data(API_KEY, SECRET_KEY)

    captured = capsys.readouterr()
    assert "invalid or malformed data" in captured.out
    _assert_secrets_hidden(captured)


@pytest.mark.parametrize("payload", ([], {}, {"quote": []}, {"quote": {}}))
def test_market_data_rejects_malformed_success_payload(monkeypatch, capsys, payload):
    monkeypatch.setattr(
        alpaca.requests,
        "get",
        MagicMock(return_value=_response(200, payload)),
    )

    alpaca.test_market_data(API_KEY, SECRET_KEY)

    captured = capsys.readouterr()
    assert "invalid or malformed data" in captured.out
    _assert_secrets_hidden(captured)


@pytest.mark.parametrize(
    ("account_ok", "positions_ok", "expected"),
    ((True, True, 0), (False, True, 1), (True, False, 1)),
)
def test_main_exit_contract_and_secret_redaction(
    monkeypatch, capsys, account_ok, positions_ok, expected
):
    monkeypatch.setattr(alpaca, "load_credentials", lambda: (API_KEY, SECRET_KEY, True))
    monkeypatch.setattr(alpaca, "test_account_info", lambda *_args: account_ok)
    monkeypatch.setattr(alpaca, "test_positions", lambda *_args: positions_ok)
    monkeypatch.setattr(alpaca, "test_market_data", lambda *_args: None)

    assert alpaca.main() == expected

    _assert_secrets_hidden(capsys.readouterr())


def test_missing_requests_exits_2_with_requirements_hint(monkeypatch, capsys):
    import runpy

    monkeypatch.setitem(__import__("sys").modules, "requests", None)
    with pytest.raises(SystemExit) as excinfo:
        runpy.run_path(alpaca.__file__, run_name="alpaca_import_probe")

    assert excinfo.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "requirements.txt" in captured.err
