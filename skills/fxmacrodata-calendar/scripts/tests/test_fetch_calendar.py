"""Tests for fetch_calendar.py"""

import json
import os
import sys
import urllib.error
from typing import Any

import pytest

# Add parent directory to path so we can import the script module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import fetch_calendar  # noqa: E402

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


class _FakeResponse:
    """Fake urlopen() context manager returning a JSON-serializable payload."""

    def __init__(self, payload: Any):
        self._body = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def read(self):
        return self._body


def _events(tiers: list[Any]) -> list[dict[str, Any]]:
    return [{"event": f"event-{i}", "market_tier": tier} for i, tier in enumerate(tiers)]


# ---------------------------------------------------------------------------
# _tier_rank
# ---------------------------------------------------------------------------


class TestTierRank:
    def test_int_passthrough(self):
        assert fetch_calendar._tier_rank(1) == 1
        assert fetch_calendar._tier_rank(3) == 3

    def test_numeric_string_parses(self):
        assert fetch_calendar._tier_rank("2") == 2

    def test_non_numeric_string_falls_back_to_99(self):
        assert fetch_calendar._tier_rank("HIGH") == 99

    def test_none_falls_back_to_99(self):
        assert fetch_calendar._tier_rank(None) == 99

    def test_bool_falls_back_to_99(self):
        # bool is a subclass of int; treated as invalid input, not a tier value.
        assert fetch_calendar._tier_rank(True) == 99

    def test_arbitrary_object_falls_back_to_99(self):
        assert fetch_calendar._tier_rank(object()) == 99


# ---------------------------------------------------------------------------
# fetch_calendar
# ---------------------------------------------------------------------------


class TestFetchCalendar:
    @pytest.mark.parametrize("currency", ["us", "usd\nkey", "u$d", "円円円"])
    def test_invalid_currency_is_rejected_before_request(self, monkeypatch, currency):
        def unexpected_urlopen(*args, **kwargs):
            pytest.fail("urlopen must not run for an invalid currency")

        monkeypatch.setattr(fetch_calendar.urllib.request, "urlopen", unexpected_urlopen)

        with pytest.raises(RuntimeError, match="3-letter ASCII code"):
            fetch_calendar.fetch_calendar(currency, 50, 1)

    def test_numeric_tier_filter(self, monkeypatch):
        payload = {
            "currency": "USD",
            "timezone": "UTC",
            "data_quality": "official",
            "data": _events([1, 2, 3]),
        }
        monkeypatch.setattr(
            fetch_calendar.urllib.request, "urlopen", lambda *a, **k: _FakeResponse(payload)
        )
        result = fetch_calendar.fetch_calendar("usd", 50, 1)
        assert [e["market_tier"] for e in result["events"]] == [1]

    def test_non_int_tier_guard_does_not_raise_and_is_excluded(self, monkeypatch):
        # Regression: market_tier of "HIGH" / None / "weird" must not raise ValueError
        # (the old `int(x or 99)` implementation would crash on non-numeric strings).
        payload = {"data": _events(["HIGH", None, "weird", "2", 1])}
        monkeypatch.setattr(
            fetch_calendar.urllib.request, "urlopen", lambda *a, **k: _FakeResponse(payload)
        )
        result = fetch_calendar.fetch_calendar("usd", 50, 1)
        # Only tiers ranked <= 1 survive: "HIGH"/None/"weird" -> 99 (excluded),
        # "2" -> 2 (excluded), 1 -> 1 (included).
        tiers = [e["market_tier"] for e in result["events"]]
        assert tiers == [1]

    def test_numeric_string_tier_parses_and_is_comparable(self, monkeypatch):
        payload = {"data": _events(["2", 1])}
        monkeypatch.setattr(
            fetch_calendar.urllib.request, "urlopen", lambda *a, **k: _FakeResponse(payload)
        )
        result = fetch_calendar.fetch_calendar("usd", 50, 2)
        tiers = [e["market_tier"] for e in result["events"]]
        assert tiers == ["2", 1]

    def test_limit_clamped_above_100(self, monkeypatch):
        payload = {"data": _events([1] * 150)}
        monkeypatch.setattr(
            fetch_calendar.urllib.request, "urlopen", lambda *a, **k: _FakeResponse(payload)
        )
        result = fetch_calendar.fetch_calendar("usd", 500, None)
        assert len(result["events"]) == 100

    def test_limit_clamped_below_1(self, monkeypatch):
        payload = {"data": _events([1] * 5)}
        monkeypatch.setattr(
            fetch_calendar.urllib.request, "urlopen", lambda *a, **k: _FakeResponse(payload)
        )
        result = fetch_calendar.fetch_calendar("usd", 0, None)
        assert len(result["events"]) == 1

    def test_malformed_payload_not_dict_returns_empty_events(self, monkeypatch):
        monkeypatch.setattr(
            fetch_calendar.urllib.request,
            "urlopen",
            lambda *a, **k: _FakeResponse(["not", "a", "dict"]),
        )
        result = fetch_calendar.fetch_calendar("usd", 50, 1)
        assert result["events"] == []

    def test_malformed_payload_data_not_list_returns_empty_events(self, monkeypatch):
        payload = {"data": "not-a-list"}
        monkeypatch.setattr(
            fetch_calendar.urllib.request, "urlopen", lambda *a, **k: _FakeResponse(payload)
        )
        result = fetch_calendar.fetch_calendar("usd", 50, 1)
        assert result["events"] == []

    def test_malformed_payload_data_list_of_non_dicts_does_not_crash(self, monkeypatch):
        # A list of non-dict items must not raise AttributeError on the
        # market_tier access in the min_tier filter (default --min-tier=1).
        payload = {"data": ["oops", 3, None]}
        monkeypatch.setattr(
            fetch_calendar.urllib.request, "urlopen", lambda *a, **k: _FakeResponse(payload)
        )
        result = fetch_calendar.fetch_calendar("usd", 50, 1)
        assert result["events"] == []


# ---------------------------------------------------------------------------
# main() error handling / key redaction
# ---------------------------------------------------------------------------


class TestMainErrorHandling:
    def test_invalid_currency_never_leaks_api_key_or_traceback(self, monkeypatch, capsys):
        monkeypatch.setenv("FXMACRODATA_API_KEY", "REVIEW_SECRET_123")
        monkeypatch.setattr(
            sys,
            "argv",
            ["fetch_calendar.py", "--currency", "usd\napi_key=REVIEW_SECRET_123"],
        )

        with pytest.raises(SystemExit) as exc_info:
            fetch_calendar.main()

        assert exc_info.value.code != 0
        captured = capsys.readouterr()
        assert "REVIEW_SECRET_123" not in captured.err
        assert "REVIEW_SECRET_123" not in captured.out
        assert "Traceback" not in captured.err
        assert "3-letter ASCII code" in captured.err

    def test_http_error_exits_nonzero_and_never_leaks_api_key(self, monkeypatch, capsys):
        secret_url = f"{fetch_calendar.FXMACRODATA_BASE_URL}/calendar/usd?api_key=SECRET"

        def fake_urlopen(*a, **k):
            raise urllib.error.HTTPError(secret_url, 401, "Unauthorized", None, None)

        monkeypatch.setenv("FXMACRODATA_API_KEY", "SECRET")
        monkeypatch.setattr(fetch_calendar.urllib.request, "urlopen", fake_urlopen)
        monkeypatch.setattr(sys, "argv", ["fetch_calendar.py", "--currency", "usd"])

        with pytest.raises(SystemExit) as exc_info:
            fetch_calendar.main()

        assert exc_info.value.code != 0
        captured = capsys.readouterr()
        assert "SECRET" not in captured.err
        assert "SECRET" not in captured.out

    def test_url_error_exits_nonzero(self, monkeypatch, capsys):
        def fake_urlopen(*a, **k):
            raise urllib.error.URLError("connection refused")

        monkeypatch.setattr(fetch_calendar.urllib.request, "urlopen", fake_urlopen)
        monkeypatch.setattr(sys, "argv", ["fetch_calendar.py", "--currency", "usd"])

        with pytest.raises(SystemExit) as exc_info:
            fetch_calendar.main()

        assert exc_info.value.code != 0
        captured = capsys.readouterr()
        assert "connection refused" in captured.err
