"""Tests for get_economic_calendar.py"""

import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from unittest.mock import patch

import get_economic_calendar as _script_mod
import pytest
import requests

# Patch the vendored class via the script module's import binding.
FMPClient = _script_mod.FMPClient

# Add parent directory to path so we can import the script module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from get_economic_calendar import (
    fetch_economic_calendar,
    format_event_output,
    get_api_key,
    main,
    validate_date_range,
)

# ---------------------------------------------------------------------------
# Sample fixtures
# ---------------------------------------------------------------------------

SAMPLE_EVENTS = [
    {
        "date": "2025-01-15 14:30:00",
        "country": "US",
        "event": "Consumer Price Index (CPI) YoY",
        "currency": "USD",
        "previous": 2.6,
        "estimate": 2.7,
        "actual": None,
        "change": None,
        "impact": "High",
        "changePercentage": None,
    },
    {
        "date": "2025-01-16 10:00:00",
        "country": "EU",
        "event": "ECB Interest Rate Decision",
        "currency": "EUR",
        "previous": 4.5,
        "estimate": 4.5,
        "actual": None,
        "change": None,
        "impact": "High",
        "changePercentage": None,
    },
]


# ---------------------------------------------------------------------------
# get_api_key tests
# ---------------------------------------------------------------------------


class TestGetApiKey:
    def test_returns_key_when_set(self, monkeypatch):
        monkeypatch.setenv("FMP_API_KEY", "test_key_123")
        assert get_api_key() == "test_key_123"

    def test_returns_none_when_not_set(self, monkeypatch):
        monkeypatch.delenv("FMP_API_KEY", raising=False)
        assert get_api_key() is None


# ---------------------------------------------------------------------------
# fetch_economic_calendar tests
# ---------------------------------------------------------------------------


@dataclass
class RateFailure:
    """Shaped HTTP failure injected through the vendored client."""

    message: str


def patch_get(monkeypatch, outcome):
    """Patch FMPClient._rate_limited_get: outcome is a payload, RateFailure,
    or exception instance; returns captured calls."""

    calls = []

    def fake(self, url, params=None, quiet=False):
        calls.append({"url": url, "params": params, "quiet": quiet, "client": self})
        if isinstance(outcome, requests.exceptions.RequestException):
            # The real client catches transport exceptions internally and
            # surfaces them via _last_error ("request exception: <str>").
            self._last_error = f"request exception: {outcome}"
            return None
        if isinstance(outcome, Exception):
            raise outcome
        if isinstance(outcome, RateFailure):
            self._last_error = outcome.message
            return None
        self._last_error = None
        return outcome

    monkeypatch.setattr(_script_mod.FMPClient, "_rate_limited_get", fake)
    return calls


class TestFetchEconomicCalendar:
    def test_uses_singular_stable_endpoint(self, monkeypatch):
        calls = patch_get(monkeypatch, [])
        fetch_economic_calendar("2025-01-01", "2025-01-07", "test_key")

        assert calls[0]["url"] == "https://financialmodelingprep.com/stable/economic-calendar"
        assert "economics-calendar" not in calls[0]["url"]
        # Header auth (deliberate change, Issue #495): no apikey in the URL.
        assert "apikey" not in calls[0]["url"]

    def test_success_returns_events(self, monkeypatch):
        calls = patch_get(monkeypatch, SAMPLE_EVENTS)
        events = fetch_economic_calendar("2025-01-01", "2025-01-07", "test_key")

        assert events == SAMPLE_EVENTS
        assert calls[0]["client"].session.headers.get("apikey") == "test_key"

    def test_402_raises_clear_restricted_endpoint_error(self, monkeypatch):
        patch_get(
            monkeypatch,
            RateFailure("HTTP 402 - not available under your current subscription"),
        )
        with pytest.raises(ValueError, match="402|subscription|upgrade"):
            fetch_economic_calendar("2025-01-01", "2025-01-07", "test_key")

    def test_402_message_includes_upgrade_advice_and_body(self, monkeypatch):
        patch_get(
            monkeypatch,
            RateFailure("HTTP 402 - not available under your current subscription"),
        )
        with pytest.raises(ValueError) as excinfo:
            fetch_economic_calendar("2025-01-01", "2025-01-07", "test_key")
        assert "Upgrade your plan" in str(excinfo.value)
        assert "not available under your current subscription" in str(excinfo.value)

    def test_genuine_404_raises_instead_of_swallowing(self, monkeypatch):
        patch_get(monkeypatch, RateFailure('HTTP 404 - {"Error Message": "Not found"}'))
        with pytest.raises(ValueError, match="status code 404"):
            fetch_economic_calendar("2025-01-01", "2025-01-07", "test_key")

    def test_404_with_empty_array_body_no_longer_swallowed(self, monkeypatch):
        # Regression test: a 404 must never be silently treated as "zero events",
        # even if the error body happens to be "[]".
        patch_get(monkeypatch, RateFailure("HTTP 404 - []"))
        with pytest.raises(ValueError, match="status code 404"):
            fetch_economic_calendar("2025-01-01", "2025-01-07", "test_key")

    def test_non_200_response_fails_closed(self, monkeypatch):
        patch_get(monkeypatch, RateFailure("HTTP 503 - []"))
        with pytest.raises(ValueError, match="status code 503"):
            fetch_economic_calendar("2025-01-01", "2025-01-07", "test_key")

    def test_non_list_payload_fails_closed(self, monkeypatch):
        patch_get(monkeypatch, {"events": SAMPLE_EVENTS})
        with pytest.raises(ValueError, match="Unexpected API response format"):
            fetch_economic_calendar("2025-01-01", "2025-01-07", "test_key")

    def test_transport_error_has_clear_network_message(self, monkeypatch):
        patch_get(
            monkeypatch,
            requests.exceptions.ConnectionError("offline"),
        )
        with pytest.raises(ValueError, match="Network error: offline"):
            fetch_economic_calendar("2025-01-01", "2025-01-07", "test_key")


# ---------------------------------------------------------------------------
# validate_date_range tests
# ---------------------------------------------------------------------------


class TestValidateDateRange:
    def test_valid_range(self):
        validate_date_range("2025-01-01", "2025-01-31")

    def test_same_day(self):
        validate_date_range("2025-06-15", "2025-06-15")

    def test_max_90_days(self):
        validate_date_range("2025-01-01", "2025-03-31")  # 89 days

    def test_exceeds_90_days(self):
        with pytest.raises(ValueError, match="exceeds maximum of 90 days"):
            validate_date_range("2025-01-01", "2025-06-01")

    def test_start_after_end(self):
        with pytest.raises(ValueError, match="after end date"):
            validate_date_range("2025-03-01", "2025-01-01")

    def test_invalid_date_format(self):
        with pytest.raises(ValueError, match="Invalid date format"):
            validate_date_range("01-01-2025", "2025-01-31")

    def test_invalid_date_value(self):
        with pytest.raises(ValueError, match="Invalid date format"):
            validate_date_range("2025-13-01", "2025-14-01")

    def test_past_dates_warns(self, capsys):
        past = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        past_end = (datetime.now() - timedelta(days=20)).strftime("%Y-%m-%d")
        validate_date_range(past, past_end)
        captured = capsys.readouterr()
        assert "in the past" in captured.err


# ---------------------------------------------------------------------------
# format_event_output tests
# ---------------------------------------------------------------------------


class TestFormatEventOutput:
    def test_json_format_roundtrip(self):
        output = format_event_output(SAMPLE_EVENTS, "json")
        parsed = json.loads(output)
        assert len(parsed) == 2
        assert parsed[0]["event"] == "Consumer Price Index (CPI) YoY"

    def test_json_empty_list(self):
        output = format_event_output([], "json")
        assert json.loads(output) == []

    def test_text_format_header(self):
        output = format_event_output(SAMPLE_EVENTS, "text")
        assert "Total: 2" in output

    def test_text_format_contains_event_name(self):
        output = format_event_output(SAMPLE_EVENTS, "text")
        assert "Consumer Price Index (CPI) YoY" in output
        assert "ECB Interest Rate Decision" in output

    def test_text_format_shows_previous(self):
        output = format_event_output(SAMPLE_EVENTS, "text")
        assert "Previous: 2.6" in output

    def test_text_format_omits_none_actual(self):
        output = format_event_output(SAMPLE_EVENTS, "text")
        assert "Actual:" not in output

    def test_text_format_shows_actual_when_present(self):
        events = [
            {
                "date": "2025-01-10 14:30:00",
                "country": "US",
                "event": "NFP",
                "currency": "USD",
                "previous": 200,
                "estimate": 210,
                "actual": 256,
                "change": 56,
                "impact": "High",
                "changePercentage": 28.0,
            }
        ]
        output = format_event_output(events, "text")
        assert "Actual: 256" in output
        assert "Change: 56" in output
        assert "Change %: 28.0%" in output

    def test_unknown_format_raises(self):
        with pytest.raises(ValueError, match="Unknown output format"):
            format_event_output([], "csv")


class TestMain:
    def test_missing_key_exits_without_fetching(self, monkeypatch, capsys):
        monkeypatch.delenv("FMP_API_KEY", raising=False)
        monkeypatch.setattr(sys, "argv", ["get_economic_calendar.py"])

        with pytest.raises(SystemExit) as exc:
            main()

        assert exc.value.code == 1
        assert "FMP API key is required" in capsys.readouterr().err

    def test_success_writes_requested_output(self, monkeypatch, tmp_path, capsys):
        output_path = tmp_path / "calendar.json"
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "get_economic_calendar.py",
                "--api-key",
                "test-key",
                "--from",
                "2026-08-11",
                "--to",
                "2026-08-12",
                "--output",
                str(output_path),
            ],
        )

        with patch("get_economic_calendar.fetch_economic_calendar", return_value=SAMPLE_EVENTS):
            with pytest.raises(SystemExit) as exc:
                main()

        assert exc.value.code == 0
        assert json.loads(output_path.read_text(encoding="utf-8")) == SAMPLE_EVENTS
        assert "Retrieved 2 events" in capsys.readouterr().err

    def test_fetch_failure_exits_one(self, monkeypatch, capsys):
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "get_economic_calendar.py",
                "--api-key",
                "test-key",
                "--from",
                "2026-08-11",
                "--to",
                "2026-08-12",
            ],
        )

        with patch("get_economic_calendar.fetch_economic_calendar", side_effect=ValueError("bad")):
            with pytest.raises(SystemExit) as exc:
                main()

        assert exc.value.code == 1
        assert "Error: bad" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Issue #332: HTTP-200 event contract and safe CLI failures
# ---------------------------------------------------------------------------


def test_schema_preserves_normal_nulls_negative_values_and_extra_fields(monkeypatch):
    import copy

    rows = copy.deepcopy(SAMPLE_EVENTS)
    rows[0].update({"actual": -0.25, "unit": "%", "future_field": {"kept": True}, "impact": "None"})
    patch_get(monkeypatch, rows)
    result = fetch_economic_calendar("2026-10-01", "2026-10-07", "test-key")
    assert result is rows
    assert result[0]["future_field"] == {"kept": True}


@pytest.mark.parametrize(
    "field", [*_script_mod.REQUIRED_TEXT_FIELDS, *_script_mod.NULLABLE_NUMBER_FIELDS]
)
def test_each_missing_required_field_is_rejected(monkeypatch, field):
    row = dict(SAMPLE_EVENTS[0])
    del row[field]
    patch_get(monkeypatch, [row])
    with pytest.raises(_script_mod.EconomicCalendarSchemaError, match=field):
        fetch_economic_calendar("2026-10-01", "2026-10-07", "test-key")


@pytest.mark.parametrize("field", _script_mod.NULLABLE_NUMBER_FIELDS)
@pytest.mark.parametrize("value", [True, "2.7", float("nan"), float("inf"), float("-inf"), {}])
def test_numeric_schema_rejects_type_and_nonfinite_drift(monkeypatch, field, value):
    row = {**SAMPLE_EVENTS[0], field: value}
    patch_get(monkeypatch, [row])
    with pytest.raises(_script_mod.EconomicCalendarSchemaError, match=field):
        fetch_economic_calendar("2026-10-01", "2026-10-07", "test-key")


@pytest.mark.parametrize("field", _script_mod.REQUIRED_TEXT_FIELDS)
@pytest.mark.parametrize("value", [None, "", "  ", 123, False])
def test_required_text_cannot_disappear_or_change_type(monkeypatch, field, value):
    patch_get(monkeypatch, [{**SAMPLE_EVENTS[0], field: value}])
    with pytest.raises(_script_mod.EconomicCalendarSchemaError, match=field):
        fetch_economic_calendar("2026-10-01", "2026-10-07", "test-key")


@pytest.mark.parametrize(
    "value",
    [
        "2026-02-30 10:00:00",
        "2026-10-07 24:00:00",
        "2026-1-1 1:00:00",
        "not-a-date",
        "2026-10-07T10:00:00Z",
    ],
)
def test_invalid_event_timestamp_is_rejected(monkeypatch, value):
    patch_get(monkeypatch, [{**SAMPLE_EVENTS[0], "date": value}])
    with pytest.raises(_script_mod.EconomicCalendarSchemaError, match="invalid date"):
        fetch_economic_calendar("2026-10-01", "2026-10-07", "test-key")


@pytest.mark.parametrize("row", [None, "provider-secret", 123, ["row"]])
def test_malformed_row_is_rejected_without_echoing_provider_values(monkeypatch, row):
    patch_get(monkeypatch, [row])
    with pytest.raises(_script_mod.EconomicCalendarSchemaError) as error:
        fetch_economic_calendar("2026-10-01", "2026-10-07", "test-key")
    assert "provider-secret" not in str(error.value)


@pytest.mark.parametrize(
    "case,reason",
    [
        ("object", "economic_calendar_schema_drift"),
        ("string", "economic_calendar_schema_drift"),
        ("null", "calendar_fetch_failed"),
        ("invalid-json", "calendar_fetch_failed"),
        ("402", "calendar_fetch_failed"),
        ("503", "calendar_fetch_failed"),
        ("connection", "calendar_fetch_failed"),
        ("empty", "empty_calendar_unverified"),
        ("renamed", "economic_calendar_schema_drift"),
        ("bad-number", "economic_calendar_schema_drift"),
    ],
)
def test_real_client_transport_failures_preserve_output(
    monkeypatch, tmp_path, capsys, case, reason
):
    api_key = "economic-test-secret"  # pragma: allowlist secret
    output = tmp_path / "calendar.json"
    output.write_text("prior successful output", encoding="utf-8")
    calls = []

    class Response:
        status_code = int(case) if case in {"402", "503"} else 200
        text = f"Provider echoed {api_key}"

        def json(self):
            if case == "invalid-json":
                raise ValueError(f"Invalid JSON body echoed {api_key}")
            if case == "object":
                return {"error": api_key}
            if case == "string":
                return api_key
            if case == "null":
                return None
            if case == "empty":
                return []
            row = dict(SAMPLE_EVENTS[0])
            if case == "renamed":
                row["releaseName"] = row.pop("event")
            elif case == "bad-number":
                row["estimate"] = api_key
            return [row]

    def fake_get(session, url, params=None, timeout=None):
        calls.append((url, params, timeout))
        assert api_key not in url
        assert session.headers["apikey"] == api_key
        if case == "connection":
            raise requests.exceptions.ConnectionError(f"Connection failed: {api_key}")
        return Response()

    monkeypatch.setattr(requests.Session, "get", fake_get)
    monkeypatch.setattr(_script_mod.FMPClient, "RATE_LIMIT_DELAY", 0)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "get_economic_calendar.py",
            "--api-key",
            api_key,
            "--from",
            "2026-10-01",
            "--to",
            "2026-10-07",
            "--output",
            str(output),
        ],
    )
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.count(f"ZERO_RESULT_REASON={reason}") == 1
    assert api_key not in captured.err
    assert output.read_text(encoding="utf-8") == "prior successful output"
    assert len(calls) == (2 if case == "invalid-json" else 1)
    assert all(timeout == 30 for _, _, timeout in calls)


def test_empty_fetch_api_still_allows_caller_policy(monkeypatch):
    patch_get(monkeypatch, [])
    assert fetch_economic_calendar("2026-10-01", "2026-10-07", "test-key") == []
