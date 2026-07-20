#!/usr/bin/env python3
"""Fetch FXMacroData release-calendar events."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlencode

FXMACRODATA_BASE_URL = "https://fxmacrodata.com/api/v1"


def _tier_rank(value: Any) -> int:
    """Coerce a market_tier value into a comparable int rank.

    The live FXMacroData API always returns market_tier as an int (1/2/3);
    string importance labels (low/medium/high) live in a separate
    event_importance field, one-to-one with tier. This function does not
    implement any label-to-tier mapping. It only guards against unexpected
    non-int input by excluding it under a restrictive --min-tier: bools and
    anything that cannot be parsed as an int are ranked 99 (i.e. filtered
    out unless min_tier is set very high).
    """
    if isinstance(value, bool):
        return 99
    if isinstance(value, int):
        return value
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return 99


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
    limit_count = max(1, min(int(limit), 100))
    params = {"limit": str(limit_count)}
    api_key = os.getenv("FXMACRODATA_API_KEY")
    if api_key:
        params["api_key"] = api_key

    url = f"{FXMACRODATA_BASE_URL}/calendar/{currency.lower()}?{urlencode(params)}"
    request = urllib.request.Request(
        url, headers={"User-Agent": "claude-trading-skills-fxmacrodata/1.0"}
    )

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(
            f"FXMacroData API request failed for currency={currency.lower()}: HTTP {exc.code}"
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"FXMacroData API request failed for currency={currency.lower()}: {exc.reason}"
        ) from exc
    except TimeoutError as exc:
        raise RuntimeError(
            f"FXMacroData API request timed out for currency={currency.lower()}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"FXMacroData API returned invalid JSON for currency={currency.lower()}"
        ) from exc

    if not isinstance(payload, dict):
        payload = {}

    data = payload.get("data", [])
    # Keep only dict rows: a malformed payload with non-dict list items must
    # not crash on event.get(...) below (event_importance/market_tier access).
    events = [event for event in data if isinstance(event, dict)] if isinstance(data, list) else []

    if min_tier is not None:
        events = [event for event in events if _tier_rank(event.get("market_tier")) <= min_tier]

    events = events[:limit_count]
    return {
        "currency": payload.get("currency", currency.upper()),
        "timezone": payload.get("timezone"),
        "data_quality": payload.get("data_quality"),
        "events": events,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--currency", default="usd")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--min-tier", type=int, default=1)
    args = parser.parse_args()

    try:
        result = fetch_calendar(args.currency, args.limit, args.min_tier)
    except RuntimeError as exc:
        print(_redact(f"Error: {exc}"), file=sys.stderr)
        sys.exit(1)

    print(json.dumps(result, indent=2))
    sys.exit(0)


if __name__ == "__main__":
    main()
