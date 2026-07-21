#!/usr/bin/env python3
"""Fetch FXMacroData release-calendar events."""

from __future__ import annotations

import argparse
import http.client
import json
import math
import os
import sys
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlencode

FXMACRODATA_BASE_URL = "https://api.fxmacrodata.com/v1"
VALID_MARKET_TIERS = frozenset({1, 2, 3})
QUALITY_BOOLEAN_FIELDS = (
    "is_official",
    "is_proxy",
    "is_fallback",
    "is_stale",
    "has_announcement_datetime",
    "point_in_time_safe",
)
SAFE_QUALITY_VALUES = {
    "is_official": True,
    "is_proxy": False,
    "is_fallback": False,
    "is_stale": False,
    "has_announcement_datetime": True,
    "point_in_time_safe": True,
}


class _NonFiniteJSONValue(ValueError):
    """Raised when the JSON decoder encounters NaN or Infinity."""


def _normalize_currency(value: str) -> str:
    """Return a safe three-letter currency code without echoing bad input."""
    normalized = value.strip().lower()
    if len(normalized) != 3 or not normalized.isascii() or not normalized.isalpha():
        raise RuntimeError("currency must be a 3-letter ASCII code")
    return normalized


def _tier_rank(value: Any) -> int | None:
    """Return a supported live-response market tier, or None for invalid input."""
    if isinstance(value, int) and not isinstance(value, bool) and value in VALID_MARKET_TIERS:
        return value
    return None


def _reject_non_finite_constant(value: str) -> None:
    """Reject the non-standard JSON constants NaN and Infinity."""
    raise _NonFiniteJSONValue(value)


def _validate_finite_json(value: Any) -> None:
    """Iteratively reject numbers that decoded to NaN or Infinity."""
    pending = [value]
    while pending:
        current = pending.pop()
        if isinstance(current, float) and not math.isfinite(current):
            raise RuntimeError("FXMacroData API returned invalid response: non-finite number")
        if isinstance(current, dict):
            pending.extend(current.values())
        elif isinstance(current, list):
            pending.extend(current)


def _validate_data_quality(data_quality: Any) -> dict[str, Any]:
    """Require analysis-ready official, fresh, point-in-time-safe metadata."""
    if not isinstance(data_quality, dict):
        raise RuntimeError(
            "FXMacroData API returned invalid response: data_quality must be an object"
        )

    for field in QUALITY_BOOLEAN_FIELDS:
        if field not in data_quality:
            raise RuntimeError(
                f"FXMacroData API returned invalid response: data_quality.{field} is required"
            )
        if not isinstance(data_quality[field], bool):
            raise RuntimeError(
                f"FXMacroData API returned invalid response: data_quality.{field} must be a boolean"
            )
        if data_quality[field] is not SAFE_QUALITY_VALUES[field]:
            raise RuntimeError(
                "FXMacroData API returned unsafe response: "
                f"data_quality.{field} is not analysis-ready"
            )

    source_type = data_quality.get("source_type")
    if not isinstance(source_type, str):
        raise RuntimeError(
            "FXMacroData API returned invalid response: data_quality.source_type must be a string"
        )
    if source_type != "official":
        raise RuntimeError(
            "FXMacroData API returned unsafe response: data_quality.source_type must be official"
        )
    return data_quality


def _validate_calendar_payload(payload: Any, expected_currency: str) -> dict[str, Any]:
    """Validate the OpenAPI calendar contract and analysis-readiness policy."""
    _validate_finite_json(payload)
    if not isinstance(payload, dict):
        raise RuntimeError(
            "FXMacroData API returned invalid response: top-level JSON must be an object"
        )

    response_currency = payload.get("currency")
    if not isinstance(response_currency, str) or response_currency != expected_currency:
        raise RuntimeError(
            "FXMacroData API returned invalid response: "
            "currency must exactly match the requested currency"
        )

    _validate_data_quality(payload.get("data_quality"))

    if "data" not in payload:
        raise RuntimeError("FXMacroData API returned invalid response: missing required data field")
    data = payload["data"]
    if not isinstance(data, list):
        raise RuntimeError("FXMacroData API returned invalid response: data field must be an array")

    for index, event in enumerate(data):
        if not isinstance(event, dict):
            raise RuntimeError(
                f"FXMacroData API returned invalid response: data[{index}] must be an object"
            )
        announcement_datetime = event.get("announcement_datetime")
        if not isinstance(announcement_datetime, int) or isinstance(announcement_datetime, bool):
            raise RuntimeError(
                "FXMacroData API returned invalid response: "
                f"announcement_datetime at data[{index}] must be an integer"
            )
        release = event.get("release")
        if not isinstance(release, str) or not release.strip():
            raise RuntimeError(
                "FXMacroData API returned invalid response: "
                f"release at data[{index}] must be a non-empty string"
            )
        if _tier_rank(event.get("market_tier")) is None:
            raise RuntimeError(
                f"FXMacroData API returned invalid response: invalid market_tier at data[{index}]"
            )
    return payload


def _redact(text: str) -> str:
    """Redact an api_key query-param value from a string, as a backup.

    Primary defense against key leakage is never referencing the built
    request URL or HTTPError.url in error messages; this is a backup for
    any string that might still carry the key.
    """
    if "api_key=" not in text:
        return text
    prefix, _, rest = text.partition("api_key=")
    _, _, suffix = rest.partition("&")
    return f"{prefix}api_key=***{('&' + suffix) if suffix else ''}"


def fetch_calendar(currency: str, limit: int, min_tier: int | None) -> dict[str, Any]:
    normalized_currency = _normalize_currency(currency)
    if min_tier is not None and _tier_rank(min_tier) is None:
        raise RuntimeError("min_tier must be one of 1, 2, or 3")
    limit_count = max(1, min(int(limit), 100))
    params = {"limit": str(limit_count)}
    api_key = os.getenv("FXMACRODATA_API_KEY")
    if api_key:
        params["api_key"] = api_key

    try:
        url = f"{FXMACRODATA_BASE_URL}/calendar/{normalized_currency}?{urlencode(params)}"
        request = urllib.request.Request(
            url, headers={"User-Agent": "claude-trading-skills-fxmacrodata/1.0"}
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.load(response, parse_constant=_reject_non_finite_constant)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(
            f"FXMacroData API request failed for currency={normalized_currency}: HTTP {exc.code}"
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"FXMacroData API request failed for currency={normalized_currency}: {exc.reason}"
        ) from exc
    except TimeoutError as exc:
        raise RuntimeError(
            f"FXMacroData API request timed out for currency={normalized_currency}"
        ) from exc
    except _NonFiniteJSONValue as exc:
        raise RuntimeError("FXMacroData API returned invalid response: non-finite number") from exc
    except RecursionError as exc:
        raise RuntimeError(
            f"FXMacroData API returned invalid JSON for currency={normalized_currency}: "
            "nesting exceeds the decoder limit"
        ) from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise RuntimeError(
            f"FXMacroData API returned invalid JSON for currency={normalized_currency}"
        ) from exc
    except (http.client.InvalidURL, ValueError) as exc:
        raise RuntimeError(
            f"FXMacroData API request could not be built for currency={normalized_currency}"
        ) from exc
    except (http.client.HTTPException, OSError) as exc:
        raise RuntimeError(
            f"FXMacroData API response body could not be read for currency={normalized_currency}"
        ) from exc

    payload = _validate_calendar_payload(payload, normalized_currency.upper())
    data = payload["data"]

    events: list[dict[str, Any]] = []
    for event in data:
        tier: int = event["market_tier"]
        if min_tier is None or tier <= min_tier:
            events.append(event)

    events = events[:limit_count]
    return {
        "currency": payload["currency"],
        "timezone": payload.get("timezone"),
        "data_quality": payload["data_quality"],
        "events": events,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--currency", default="usd")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--min-tier", type=int, choices=(1, 2, 3), default=1)
    args = parser.parse_args()

    try:
        result = fetch_calendar(args.currency, args.limit, args.min_tier)
    except RuntimeError as exc:
        print(_redact(f"Error: {exc}"), file=sys.stderr)
        sys.exit(1)

    try:
        serialized = json.dumps(result, indent=2, allow_nan=False)
    except (RecursionError, TypeError, ValueError):
        print("Error: result could not be serialized as strict JSON", file=sys.stderr)
        sys.exit(1)

    print(serialized)
    sys.exit(0)


if __name__ == "__main__":
    main()
