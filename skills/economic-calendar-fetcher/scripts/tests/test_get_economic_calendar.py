"""Tests for get_economic_calendar.py"""

import io
import json
import os
import sys
import urllib.error
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

# Add parent directory to path so we can import the script module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from get_economic_calendar import (
    fetch_economic_calendar,
    format_event_output,
    get_api_key,
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


def _fake_response(status: int, body: bytes):
    cm = MagicMock()
    cm.__enter__.return_value = cm
    cm.status = status
    cm.read.return_value = body
    return cm


class TestFetchEconomicCalendar:
    def test_uses_singular_stable_endpoint(self):
        captured = {}

        def fake_urlopen(request):
            captured["url"] = request.full_url
            return _fake_response(200, b"[]")

        with patch("get_economic_calendar.urllib.request.urlopen", side_effect=fake_urlopen):
            fetch_economic_calendar("2025-01-01", "2025-01-07", "test_key")

        assert captured["url"].startswith(
            "https://financialmodelingprep.com/stable/economic-calendar?"
        )
        assert "economics-calendar" not in captured["url"]

    def test_success_returns_events(self):
        payload = json.dumps(SAMPLE_EVENTS).encode("utf-8")

        with patch(
            "get_economic_calendar.urllib.request.urlopen",
            side_effect=lambda request: _fake_response(200, payload),
        ):
            events = fetch_economic_calendar("2025-01-01", "2025-01-07", "test_key")

        assert events == SAMPLE_EVENTS

    def test_402_raises_clear_restricted_endpoint_error(self):
        def fake_urlopen(request):
            raise urllib.error.HTTPError(
                request.full_url,
                402,
                "Payment Required",
                hdrs=None,
                fp=io.BytesIO(
                    b"Restricted Endpoint: not available under your current subscription"
                ),
            )

        with patch("get_economic_calendar.urllib.request.urlopen", side_effect=fake_urlopen):
            with pytest.raises(ValueError, match="402|subscription|upgrade"):
                fetch_economic_calendar("2025-01-01", "2025-01-07", "test_key")

    def test_genuine_404_raises_instead_of_swallowing(self):
        def fake_urlopen(request):
            raise urllib.error.HTTPError(
                request.full_url,
                404,
                "Not Found",
                hdrs=None,
                fp=io.BytesIO(b'{"Error Message": "Not found"}'),
            )

        with patch("get_economic_calendar.urllib.request.urlopen", side_effect=fake_urlopen):
            with pytest.raises(urllib.error.HTTPError):
                fetch_economic_calendar("2025-01-01", "2025-01-07", "test_key")

    def test_404_with_empty_array_body_no_longer_swallowed(self):
        # Regression test: a 404 must never be silently treated as "zero events",
        # even if the error body happens to be "[]".
        def fake_urlopen(request):
            raise urllib.error.HTTPError(
                request.full_url, 404, "Not Found", hdrs=None, fp=io.BytesIO(b"[]")
            )

        with patch("get_economic_calendar.urllib.request.urlopen", side_effect=fake_urlopen):
            with pytest.raises(urllib.error.HTTPError):
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
