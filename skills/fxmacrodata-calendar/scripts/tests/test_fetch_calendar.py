"""Tests for fetch_calendar.py"""

from __future__ import annotations

import http.client
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


class _ReadErrorResponse:
    """Fake urlopen() context manager that fails while reading the body."""

    def __init__(self, error: BaseException):
        self._error = error

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def read(self):
        raise self._error


SAFE_DATA_QUALITY = {
    "is_official": True,
    "is_proxy": False,
    "is_fallback": False,
    "is_stale": False,
    "has_announcement_datetime": True,
    "point_in_time_safe": True,
    "source_type": "official",
}


def _events(tiers: list[Any]) -> list[dict[str, Any]]:
    return [
        {
            "announcement_datetime": 1_800_000_000 + i,
            "release": f"event_{i}",
            "market_tier": tier,
        }
        for i, tier in enumerate(tiers)
    ]


def _payload(
    data: list[Any] | None = None,
    *,
    currency: Any = "USD",
    data_quality: Any = None,
) -> dict[str, Any]:
    return {
        "currency": currency,
        "timezone": "UTC",
        "data_quality": (dict(SAFE_DATA_QUALITY) if data_quality is None else data_quality),
        "data": [] if data is None else data,
    }


def _deeply_nested(value: Any, depth: int) -> Any:
    nested = value
    for _ in range(depth):
        nested = [nested]
    return nested


# ---------------------------------------------------------------------------
# _tier_rank
# ---------------------------------------------------------------------------


class TestTierRank:
    def test_int_passthrough(self):
        assert fetch_calendar._tier_rank(1) == 1
        assert fetch_calendar._tier_rank(3) == 3

    @pytest.mark.parametrize(
        "value",
        [0, -1, 4, 99, True, "2", "HIGH", None],
    )
    def test_only_supported_live_response_tiers_are_accepted(self, value):
        assert fetch_calendar._tier_rank(value) is None


# ---------------------------------------------------------------------------
# response-contract validators
# ---------------------------------------------------------------------------


class TestResponseContract:
    def test_safe_empty_calendar_is_valid(self):
        result = fetch_calendar._validate_calendar_payload(_payload(), "USD")

        assert result["data"] == []

    @pytest.mark.parametrize("currency", [None, 123, "", "usd", "JPY"])
    def test_currency_must_be_required_string_and_exact_match(self, currency):
        with pytest.raises(RuntimeError, match="currency"):
            fetch_calendar._validate_calendar_payload(_payload(currency=currency), "USD")

    def test_currency_field_is_required(self):
        payload = _payload()
        del payload["currency"]

        with pytest.raises(RuntimeError, match="currency"):
            fetch_calendar._validate_calendar_payload(payload, "USD")

    @pytest.mark.parametrize("data_quality", [None, "official", [], 123])
    def test_data_quality_must_be_present_object(self, data_quality):
        payload = _payload()
        if data_quality is None:
            del payload["data_quality"]
        else:
            payload["data_quality"] = data_quality

        with pytest.raises(RuntimeError, match="data_quality"):
            fetch_calendar._validate_calendar_payload(payload, "USD")

    @pytest.mark.parametrize(
        "field",
        [
            "is_official",
            "is_proxy",
            "is_fallback",
            "is_stale",
            "has_announcement_datetime",
            "point_in_time_safe",
        ],
    )
    def test_required_quality_boolean_cannot_be_missing(self, field):
        quality = dict(SAFE_DATA_QUALITY)
        del quality[field]

        with pytest.raises(RuntimeError, match=field):
            fetch_calendar._validate_calendar_payload(_payload(data_quality=quality), "USD")

    @pytest.mark.parametrize("bad_value", [0, 1, None, "true", []])
    def test_required_quality_booleans_are_strictly_typed(self, bad_value):
        quality = dict(SAFE_DATA_QUALITY, is_stale=bad_value)

        with pytest.raises(RuntimeError, match="is_stale must be a boolean"):
            fetch_calendar._validate_calendar_payload(_payload(data_quality=quality), "USD")

    @pytest.mark.parametrize(
        "field",
        [
            "is_official",
            "is_proxy",
            "is_fallback",
            "is_stale",
            "has_announcement_datetime",
            "point_in_time_safe",
        ],
    )
    def test_every_quality_boolean_rejects_non_boolean_values(self, field):
        quality = dict(SAFE_DATA_QUALITY, **{field: "false"})

        with pytest.raises(RuntimeError, match=f"{field} must be a boolean"):
            fetch_calendar._validate_calendar_payload(_payload(data_quality=quality), "USD")

    @pytest.mark.parametrize("source_type", [None, 1, "", "public", "derived"])
    def test_source_type_must_be_present_and_official(self, source_type):
        quality = dict(SAFE_DATA_QUALITY)
        if source_type is None:
            del quality["source_type"]
        else:
            quality["source_type"] = source_type

        with pytest.raises(RuntimeError, match="source_type"):
            fetch_calendar._validate_calendar_payload(_payload(data_quality=quality), "USD")

    @pytest.mark.parametrize(
        ("field", "unsafe_value"),
        [
            ("is_official", False),
            ("is_proxy", True),
            ("is_fallback", True),
            ("is_stale", True),
            ("has_announcement_datetime", False),
            ("point_in_time_safe", False),
            ("source_type", "fallback"),
        ],
    )
    def test_unsafe_quality_fails_closed_even_when_data_is_empty(self, field, unsafe_value):
        quality = dict(SAFE_DATA_QUALITY, **{field: unsafe_value})

        with pytest.raises(RuntimeError, match=field):
            fetch_calendar._validate_calendar_payload(_payload(data_quality=quality), "USD")

    @pytest.mark.parametrize("announcement_datetime", [None, True, "1800000000"])
    def test_event_requires_integer_announcement_datetime(self, announcement_datetime):
        event = _events([1])[0]
        event["announcement_datetime"] = announcement_datetime

        with pytest.raises(RuntimeError, match="announcement_datetime"):
            fetch_calendar._validate_calendar_payload(_payload([event]), "USD")

    def test_event_requires_announcement_datetime_field(self):
        event = _events([1])[0]
        del event["announcement_datetime"]

        with pytest.raises(RuntimeError, match="announcement_datetime"):
            fetch_calendar._validate_calendar_payload(_payload([event]), "USD")

    @pytest.mark.parametrize("release", [None, 123, "", "   "])
    def test_event_requires_non_empty_release(self, release):
        event = _events([1])[0]
        event["release"] = release

        with pytest.raises(RuntimeError, match="release"):
            fetch_calendar._validate_calendar_payload(_payload([event]), "USD")

    def test_event_requires_release_field(self):
        event = _events([1])[0]
        del event["release"]

        with pytest.raises(RuntimeError, match="release"):
            fetch_calendar._validate_calendar_payload(_payload([event]), "USD")

    def test_iterative_finite_validator_accepts_deep_finite_value(self):
        fetch_calendar._validate_finite_json(_deeply_nested(1.0, 1_500))

    def test_iterative_finite_validator_rejects_deep_non_finite_value(self):
        with pytest.raises(RuntimeError, match="non-finite number"):
            fetch_calendar._validate_finite_json(_deeply_nested(float("inf"), 1_500))


# ---------------------------------------------------------------------------
# fetch_calendar
# ---------------------------------------------------------------------------


class TestFetchCalendar:
    @pytest.mark.parametrize(
        "read_error",
        [
            http.client.IncompleteRead(b"partial", 100),
            ConnectionResetError("connection reset; api_key=PURE_SECRET"),
            OSError("socket read failed; api_key=PURE_SECRET"),
        ],
        ids=("incomplete-read", "connection-reset", "os-error"),
    )
    def test_response_read_error_is_sanitized_runtime_error(self, monkeypatch, read_error):
        monkeypatch.setenv("FXMACRODATA_API_KEY", "PURE_SECRET")
        monkeypatch.setattr(
            fetch_calendar.urllib.request,
            "urlopen",
            lambda *a, **k: _ReadErrorResponse(read_error),
        )

        with pytest.raises(RuntimeError, match="response body could not be read") as exc_info:
            fetch_calendar.fetch_calendar("usd", 50, 1)

        assert "PURE_SECRET" not in str(exc_info.value)
        assert exc_info.value.__cause__ is read_error

    @pytest.mark.parametrize("currency", ["us", "usd\nkey", "u$d", "円円円"])
    def test_invalid_currency_is_rejected_before_request(self, monkeypatch, currency):
        def unexpected_urlopen(*args, **kwargs):
            pytest.fail("urlopen must not run for an invalid currency")

        monkeypatch.setattr(fetch_calendar.urllib.request, "urlopen", unexpected_urlopen)

        with pytest.raises(RuntimeError, match="3-letter ASCII code"):
            fetch_calendar.fetch_calendar(currency, 50, 1)

    def test_numeric_tier_filter(self, monkeypatch):
        payload = _payload(_events([1, 2, 3]))
        monkeypatch.setattr(
            fetch_calendar.urllib.request, "urlopen", lambda *a, **k: _FakeResponse(payload)
        )
        result = fetch_calendar.fetch_calendar("usd", 50, 1)
        assert [e["market_tier"] for e in result["events"]] == [1]

    @pytest.mark.parametrize("tier", [0, -1, 4, 99, True, "2", "HIGH", None])
    def test_out_of_contract_tier_fails_closed(self, monkeypatch, tier):
        payload = _payload(_events([tier]))
        monkeypatch.setattr(
            fetch_calendar.urllib.request, "urlopen", lambda *a, **k: _FakeResponse(payload)
        )

        with pytest.raises(RuntimeError, match="invalid market_tier"):
            fetch_calendar.fetch_calendar("usd", 50, 3)

    def test_invalid_min_tier_fails_before_request(self, monkeypatch):
        def unexpected_urlopen(*args, **kwargs):
            pytest.fail("urlopen must not run for an invalid min_tier")

        monkeypatch.setattr(fetch_calendar.urllib.request, "urlopen", unexpected_urlopen)

        for min_tier in (0, -1, 4, 99, True):
            with pytest.raises(RuntimeError, match="min_tier must be one of"):
                fetch_calendar.fetch_calendar("usd", 50, min_tier)

    def test_limit_clamped_above_100(self, monkeypatch):
        payload = _payload(_events([1] * 150))
        monkeypatch.setattr(
            fetch_calendar.urllib.request, "urlopen", lambda *a, **k: _FakeResponse(payload)
        )
        result = fetch_calendar.fetch_calendar("usd", 500, None)
        assert len(result["events"]) == 100

    def test_limit_clamped_below_1(self, monkeypatch):
        payload = _payload(_events([1] * 5))
        monkeypatch.setattr(
            fetch_calendar.urllib.request, "urlopen", lambda *a, **k: _FakeResponse(payload)
        )
        result = fetch_calendar.fetch_calendar("usd", 0, None)
        assert len(result["events"]) == 1

    def test_valid_empty_data_returns_empty_events(self, monkeypatch):
        monkeypatch.setattr(
            fetch_calendar.urllib.request,
            "urlopen",
            lambda *a, **k: _FakeResponse(_payload()),
        )
        result = fetch_calendar.fetch_calendar("usd", 50, 1)
        assert result["events"] == []

    def test_malformed_payload_not_dict_fails_closed(self, monkeypatch):
        monkeypatch.setattr(
            fetch_calendar.urllib.request,
            "urlopen",
            lambda *a, **k: _FakeResponse(["not", "a", "dict"]),
        )

        with pytest.raises(RuntimeError, match="top-level JSON must be an object"):
            fetch_calendar.fetch_calendar("usd", 50, 1)

    def test_missing_data_fails_closed(self, monkeypatch):
        payload = _payload()
        del payload["data"]
        monkeypatch.setattr(
            fetch_calendar.urllib.request,
            "urlopen",
            lambda *a, **k: _FakeResponse(payload),
        )

        with pytest.raises(RuntimeError, match="missing required data field"):
            fetch_calendar.fetch_calendar("usd", 50, 1)

    def test_malformed_payload_data_not_list_fails_closed(self, monkeypatch):
        payload = _payload()
        payload["data"] = "not-a-list"
        monkeypatch.setattr(
            fetch_calendar.urllib.request, "urlopen", lambda *a, **k: _FakeResponse(payload)
        )

        with pytest.raises(RuntimeError, match="data field must be an array"):
            fetch_calendar.fetch_calendar("usd", 50, 1)

    def test_malformed_payload_data_list_of_non_dicts_fails_closed(self, monkeypatch):
        payload = _payload(["oops", 3, None])
        monkeypatch.setattr(
            fetch_calendar.urllib.request, "urlopen", lambda *a, **k: _FakeResponse(payload)
        )

        with pytest.raises(RuntimeError, match=r"data\[0\] must be an object"):
            fetch_calendar.fetch_calendar("usd", 50, 1)

    @pytest.mark.parametrize("non_finite", [float("nan"), float("inf"), float("-inf")])
    def test_non_finite_number_in_event_fails_closed(self, monkeypatch, non_finite):
        payload = _payload(
            [
                {
                    "announcement_datetime": 1_800_000_000,
                    "release": "inflation",
                    "market_tier": 1,
                    "details": {"actual": non_finite},
                }
            ]
        )
        monkeypatch.setattr(
            fetch_calendar.urllib.request, "urlopen", lambda *a, **k: _FakeResponse(payload)
        )

        with pytest.raises(RuntimeError, match="non-finite number"):
            fetch_calendar.fetch_calendar("usd", 50, 1)

    def test_overflowed_json_number_fails_closed(self, monkeypatch):
        body = json.dumps(
            _payload(
                [
                    {
                        "announcement_datetime": 1_800_000_000,
                        "release": "inflation",
                        "market_tier": 1,
                        "actual": 0,
                    }
                ]
            )
        ).replace('"actual": 0', '"actual": 1e309')

        class RawResponse:
            def __enter__(self):
                return self

            def __exit__(self, *exc_info):
                return False

            def read(self):
                return body.encode("utf-8")

        monkeypatch.setattr(fetch_calendar.urllib.request, "urlopen", lambda *a, **k: RawResponse())

        with pytest.raises(RuntimeError, match="non-finite number"):
            fetch_calendar.fetch_calendar("usd", 50, 1)

    def test_uses_canonical_api_host(self, monkeypatch):
        seen_urls = []

        def fake_urlopen(request, **kwargs):
            seen_urls.append(request.full_url)
            return _FakeResponse(_payload())

        monkeypatch.setattr(fetch_calendar.urllib.request, "urlopen", fake_urlopen)

        fetch_calendar.fetch_calendar("usd", 50, 1)

        assert seen_urls[0].startswith("https://api.fxmacrodata.com/v1/calendar/usd?")


# ---------------------------------------------------------------------------
# main() error handling / key redaction
# ---------------------------------------------------------------------------


class TestMainErrorHandling:
    @pytest.mark.parametrize(
        "read_error",
        [
            http.client.IncompleteRead(b"partial", 100),
            ConnectionResetError("connection reset; api_key=CLI_SECRET"),
            OSError("socket read failed; api_key=CLI_SECRET"),
        ],
        ids=("incomplete-read", "connection-reset", "os-error"),
    )
    def test_response_read_error_exits_cleanly_without_key_leak(
        self, monkeypatch, capsys, read_error
    ):
        monkeypatch.setenv("FXMACRODATA_API_KEY", "CLI_SECRET")
        monkeypatch.setattr(
            fetch_calendar.urllib.request,
            "urlopen",
            lambda *a, **k: _ReadErrorResponse(read_error),
        )
        monkeypatch.setattr(sys, "argv", ["fetch_calendar.py", "--currency", "usd"])

        with pytest.raises(SystemExit) as exc_info:
            fetch_calendar.main()

        assert exc_info.value.code != 0
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "Error:" in captured.err
        assert "response body could not be read" in captured.err
        assert "Traceback" not in captured.err
        assert "CLI_SECRET" not in captured.err

    def test_cli_rejects_out_of_range_min_tier(self, monkeypatch, capsys):
        monkeypatch.setattr(
            sys,
            "argv",
            ["fetch_calendar.py", "--currency", "usd", "--min-tier", "99"],
        )

        with pytest.raises(SystemExit) as exc_info:
            fetch_calendar.main()

        assert exc_info.value.code != 0
        assert "invalid choice" in capsys.readouterr().err

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

    @pytest.mark.parametrize(
        "payload",
        [
            _payload(currency="JPY"),
            _payload(data_quality=dict(SAFE_DATA_QUALITY, is_stale=True)),
            _payload(data_quality=dict(SAFE_DATA_QUALITY, is_official=False)),
            _payload(data_quality=dict(SAFE_DATA_QUALITY, is_fallback=True)),
            _payload(data_quality=dict(SAFE_DATA_QUALITY, is_proxy=True)),
            _payload(data_quality=dict(SAFE_DATA_QUALITY, has_announcement_datetime=False)),
            _payload(data_quality=dict(SAFE_DATA_QUALITY, point_in_time_safe=False)),
            _payload([{"market_tier": 1, "release": "inflation"}]),
        ],
    )
    def test_contract_violation_exits_nonzero_without_traceback(self, monkeypatch, capsys, payload):
        monkeypatch.setattr(
            fetch_calendar.urllib.request,
            "urlopen",
            lambda *a, **k: _FakeResponse(payload),
        )
        monkeypatch.setattr(sys, "argv", ["fetch_calendar.py", "--currency", "usd"])

        with pytest.raises(SystemExit) as exc_info:
            fetch_calendar.main()

        assert exc_info.value.code != 0
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "Error:" in captured.err
        assert "Traceback" not in captured.err

    def test_deep_finite_value_is_checked_iteratively_at_cli_level(self, monkeypatch, capsys):
        payload = _payload()
        payload["extra"] = _deeply_nested(1.0, 1_500)
        monkeypatch.setattr(fetch_calendar.json, "load", lambda *a, **k: payload)
        monkeypatch.setattr(
            fetch_calendar.urllib.request,
            "urlopen",
            lambda *a, **k: _FakeResponse(_payload()),
        )
        monkeypatch.setattr(sys, "argv", ["fetch_calendar.py", "--currency", "usd"])

        with pytest.raises(SystemExit) as exc_info:
            fetch_calendar.main()

        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert '"events": []' in captured.out
        assert captured.err == ""

    def test_deep_non_finite_value_exits_nonzero_without_traceback(self, monkeypatch, capsys):
        payload = _payload()
        payload["extra"] = _deeply_nested(float("inf"), 1_500)
        monkeypatch.setattr(fetch_calendar.json, "load", lambda *a, **k: payload)
        monkeypatch.setattr(
            fetch_calendar.urllib.request,
            "urlopen",
            lambda *a, **k: _FakeResponse(_payload()),
        )
        monkeypatch.setattr(sys, "argv", ["fetch_calendar.py", "--currency", "usd"])

        with pytest.raises(SystemExit) as exc_info:
            fetch_calendar.main()

        assert exc_info.value.code != 0
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "non-finite number" in captured.err
        assert "Traceback" not in captured.err

    def test_decoder_recursion_limit_exits_nonzero_without_traceback(self, monkeypatch, capsys):
        body = ("[" * 2_000 + "0" + "]" * 2_000).encode("utf-8")

        class RawResponse:
            def __enter__(self):
                return self

            def __exit__(self, *exc_info):
                return False

            def read(self):
                return body

        def decoder_limit(*args, **kwargs):
            # Python 3.9 raises here for deeply nested JSON; newer C decoders
            # accept greater depth, so inject the documented decoder failure
            # to keep the CLI error contract deterministic across runtimes.
            raise RecursionError("maximum recursion depth exceeded while decoding JSON")

        monkeypatch.setattr(
            fetch_calendar.urllib.request,
            "urlopen",
            lambda *a, **k: RawResponse(),
        )
        monkeypatch.setattr(fetch_calendar.json, "load", decoder_limit)
        monkeypatch.setattr(sys, "argv", ["fetch_calendar.py", "--currency", "usd"])

        with pytest.raises(SystemExit) as exc_info:
            fetch_calendar.main()

        assert exc_info.value.code != 0
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "invalid JSON" in captured.err
        assert "Traceback" not in captured.err

    def test_non_finite_api_value_exits_nonzero_without_invalid_json(self, monkeypatch, capsys):
        payload = _payload(
            [
                {
                    "announcement_datetime": 1_800_000_000,
                    "release": "inflation",
                    "market_tier": 1,
                    "actual": float("nan"),
                }
            ]
        )
        monkeypatch.setattr(
            fetch_calendar.urllib.request, "urlopen", lambda *a, **k: _FakeResponse(payload)
        )
        monkeypatch.setattr(sys, "argv", ["fetch_calendar.py", "--currency", "usd"])

        with pytest.raises(SystemExit) as exc_info:
            fetch_calendar.main()

        assert exc_info.value.code != 0
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "non-finite number" in captured.err
        assert "NaN" not in captured.out
        assert "Infinity" not in captured.out

    def test_allow_nan_false_is_a_serialization_backstop(self, monkeypatch, capsys):
        monkeypatch.setattr(
            fetch_calendar,
            "fetch_calendar",
            lambda *a, **k: {"events": [], "actual": float("nan")},
        )
        monkeypatch.setattr(sys, "argv", ["fetch_calendar.py", "--currency", "usd"])

        with pytest.raises(SystemExit) as exc_info:
            fetch_calendar.main()

        assert exc_info.value.code != 0
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "could not be serialized" in captured.err
