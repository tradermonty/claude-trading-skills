#!/usr/bin/env python3
"""Fetch FXMacroData release-calendar events."""

from __future__ import annotations

import argparse
import json
import os
from typing import Any, Optional
from urllib.parse import urlencode
from urllib.request import Request, urlopen

FXMACRODATA_BASE_URL = "https://fxmacrodata.com/api/v1"


def fetch_calendar(currency: str, limit: int, min_tier: Optional[int]) -> dict[str, Any]:
    limit_count = max(1, min(int(limit), 100))
    params = {"limit": str(limit_count)}
    api_key = os.getenv("FXMACRODATA_API_KEY")
    if api_key:
        params["api_key"] = api_key

    url = f"{FXMACRODATA_BASE_URL}/calendar/{currency.lower()}?{urlencode(params)}"
    request = Request(url, headers={"User-Agent": "claude-trading-skills-fxmacrodata/1.0"})
    with urlopen(request, timeout=20) as response:
        payload = json.load(response)

    events = payload.get("data", [])
    if min_tier is not None:
        events = [
            event
            for event in events
            if int(event.get("market_tier") or 99) <= min_tier
        ]

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
    print(json.dumps(fetch_calendar(args.currency, args.limit, args.min_tier), indent=2))


if __name__ == "__main__":
    main()
