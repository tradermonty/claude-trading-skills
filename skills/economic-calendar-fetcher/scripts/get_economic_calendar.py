#!/usr/bin/env python3
"""
Economic Calendar Fetcher using Finnhub API

Replaces FMP API with Finnhub (free tier).
Retrieves US economic events for specified date range.

Note: Finnhub economic_calendar is a premium endpoint on the free plan.
This script falls back to a FRED-based approach for key macro series
(CPI, GDP, Fed Funds Rate, Unemployment) when Finnhub is unavailable.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from typing import Optional

try:
    import finnhub
except ImportError:
    print("Error: finnhub-python not installed. Run: pip install finnhub-python", file=sys.stderr)
    sys.exit(1)


# Key FRED series for macro context (actual values, not forward calendar)
FRED_MACRO_SERIES = {
    "CPI (YoY)": "CPIAUCSL",
    "Fed Funds Rate": "FEDFUNDS",
    "10Y Treasury Yield": "DGS10",
    "2Y Treasury Yield": "DGS2",
    "GDP Growth Rate": "A191RL1Q225SBEA",
    "Unemployment Rate": "UNRATE",
}


def get_api_key() -> Optional[str]:
    api_key = os.environ.get("FINNHUB_API_KEY")
    if api_key:
        return api_key
    print("Warning: FINNHUB_API_KEY not set — using FRED fallback", file=sys.stderr)
    return None


def fetch_finnhub_calendar(api_key: str, from_date: str, to_date: str) -> list[dict]:
    """Fetch economic calendar from Finnhub (premium endpoint)."""
    try:
        client = finnhub.Client(api_key=api_key)
        result = client.economic_calendar()
        if not isinstance(result, dict):
            return []
        events = result.get("economicCalendar", [])
        # Filter to date range and US events
        filtered = []
        for ev in events:
            ev_date = ev.get("time", "")[:10]
            country = ev.get("country", "")
            if ev_date >= from_date and ev_date <= to_date and country in ("US", "United States"):
                filtered.append({
                    "date": ev_date,
                    "time": ev.get("time", ""),
                    "country": "US",
                    "currency": "USD",
                    "event": ev.get("event", ""),
                    "impact": ev.get("impact", "").capitalize(),
                    "previous": ev.get("prev"),
                    "estimate": ev.get("estimate"),
                    "actual": ev.get("actual"),
                    "change": None,
                    "changePercentage": None,
                })
        return filtered
    except Exception as e:
        print(f"WARNING: Finnhub economic calendar failed: {e}", file=sys.stderr)
        return []


def fetch_fred_macro_context(from_date: str, to_date: str) -> list[dict]:
    """
    Fetch recent actual values for key macro series from FRED.
    Returns events in economic-calendar format showing the most recent release.
    """
    fred_key = os.environ.get("FRED_API_KEY", "")
    if not fred_key:
        print("WARNING: FRED_API_KEY not set — macro context unavailable", file=sys.stderr)
        return []

    try:
        from fredapi import Fred
        fred = Fred(api_key=fred_key)
    except Exception as e:
        print(f"WARNING: FRED init failed: {e}", file=sys.stderr)
        return []

    events = []
    for label, series_id in FRED_MACRO_SERIES.items():
        try:
            series = fred.get_series(series_id).dropna()
            if series.empty:
                continue
            latest_date = series.index[-1]
            latest_val = float(series.iloc[-1])
            prev_val = float(series.iloc[-2]) if len(series) >= 2 else None
            events.append({
                "date": str(latest_date.date()) if hasattr(latest_date, "date") else str(latest_date)[:10],
                "time": "",
                "country": "US",
                "currency": "USD",
                "event": f"{label} (FRED: {series_id})",
                "impact": "High",
                "previous": round(prev_val, 4) if prev_val is not None else None,
                "estimate": None,
                "actual": round(latest_val, 4),
                "change": round(latest_val - prev_val, 4) if prev_val is not None else None,
                "changePercentage": None,
                "source": "FRED",
            })
        except Exception as e:
            print(f"WARNING: FRED series {series_id} failed: {e}", file=sys.stderr)
            continue

    return events


def validate_date_range(from_date: str, to_date: str) -> None:
    try:
        start = datetime.strptime(from_date, "%Y-%m-%d")
        end = datetime.strptime(to_date, "%Y-%m-%d")
    except ValueError as e:
        raise ValueError(f"Invalid date format. Use YYYY-MM-DD: {e}")
    if start > end:
        raise ValueError(f"Start date {from_date} is after end date {to_date}")
    delta = (end - start).days
    if delta > 90:
        raise ValueError(f"Date range ({delta} days) exceeds maximum of 90 days")


def format_event_output(events: list[dict], output_format: str = "json") -> str:
    if output_format == "json":
        return json.dumps(events, indent=2, ensure_ascii=False)
    lines = [f"Economic Calendar Events (Total: {len(events)})", "=" * 80]
    for event in events:
        lines.append(f"\nDate: {event.get('date', 'N/A')}")
        lines.append(f"Country: {event.get('country', 'N/A')}")
        lines.append(f"Event: {event.get('event', 'N/A')}")
        lines.append(f"Impact: {event.get('impact', 'N/A')}")
        if event.get("previous") is not None:
            lines.append(f"Previous: {event['previous']}")
        if event.get("estimate") is not None:
            lines.append(f"Estimate: {event['estimate']}")
        if event.get("actual") is not None:
            lines.append(f"Actual: {event['actual']}")
        lines.append("-" * 80)
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Fetch economic calendar events (Finnhub + FRED fallback)",
    )
    today = datetime.now().date()
    default_from = today.strftime("%Y-%m-%d")
    default_to = (today + timedelta(days=7)).strftime("%Y-%m-%d")

    parser.add_argument("--from", dest="from_date", default=default_from)
    parser.add_argument("--to", dest="to_date", default=default_to)
    parser.add_argument("--api-key", dest="api_key", help="Finnhub API key (overrides FINNHUB_API_KEY)")
    parser.add_argument("--format", choices=["json", "text"], default="json")
    parser.add_argument("--output", "-o", help="Output file path (default: stdout)")

    args = parser.parse_args()

    try:
        validate_date_range(args.from_date, args.to_date)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    api_key = args.api_key or get_api_key()

    print(f"Fetching economic calendar from {args.from_date} to {args.to_date}...", file=sys.stderr)

    events = []
    if api_key:
        events = fetch_finnhub_calendar(api_key, args.from_date, args.to_date)

    # Always supplement with FRED macro context (actual release values)
    fred_events = fetch_fred_macro_context(args.from_date, args.to_date)
    events.extend(fred_events)

    # Sort by date
    events.sort(key=lambda x: x.get("date", ""))

    print(f"Retrieved {len(events)} events", file=sys.stderr)
    output = format_event_output(events, args.format)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"Output written to {args.output}", file=sys.stderr)
    else:
        print(output)

    sys.exit(0)


if __name__ == "__main__":
    main()
