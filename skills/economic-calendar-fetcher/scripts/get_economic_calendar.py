#!/usr/bin/env python3
"""
Economic Calendar Fetcher using FMP API
Retrieves economic events and data releases for specified date range
"""

import argparse
import json
import math
import os
import re
import sys
from datetime import datetime, timedelta
from typing import Optional

from fmp_client import FMPClient

# Mirror the versioned economic-calendar contract without a repo-only import:
# this script also runs inside the standalone .skill archive. Repository tests
# bind these names/types/nullability to the recorded provider contract.
REQUIRED_TEXT_FIELDS = ("date", "country", "event", "currency", "impact")
NULLABLE_NUMBER_FIELDS = ("previous", "estimate", "actual", "change", "changePercentage")


class EconomicCalendarSchemaError(ValueError):
    """A response cannot be safely presented as economic event data."""


def validate_economic_events(events: list[dict]) -> None:
    """Validate all rows before formatting or opening any output file.

    Null readings are normal for scheduled/unreported events. Rejecting a
    malformed row rather than dropping it prevents schema drift from quietly
    reducing the event set. Errors contain only trusted field names/row indexes,
    never provider values or payloads.
    """
    if not isinstance(events, list):
        raise EconomicCalendarSchemaError("Economic calendar response must be a JSON array")
    for index, row in enumerate(events):
        if not isinstance(row, dict):
            raise EconomicCalendarSchemaError(f"Economic calendar row {index} must be an object")
        for field in REQUIRED_TEXT_FIELDS:
            value = row.get(field)
            if not isinstance(value, str) or not value.strip():
                raise EconomicCalendarSchemaError(
                    f"Economic calendar row {index}: missing or invalid {field}"
                )
        timestamp = row["date"]
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", timestamp):
            raise EconomicCalendarSchemaError(f"Economic calendar row {index}: invalid date")
        try:
            datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            raise EconomicCalendarSchemaError(
                f"Economic calendar row {index}: invalid date"
            ) from None
        for field in NULLABLE_NUMBER_FIELDS:
            if field not in row:
                raise EconomicCalendarSchemaError(f"Economic calendar row {index}: missing {field}")
            value = row[field]
            if value is not None and (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or (isinstance(value, float) and not math.isfinite(value))
            ):
                raise EconomicCalendarSchemaError(
                    f"Economic calendar row {index}: invalid numeric {field}"
                )


def get_api_key() -> Optional[str]:
    """
    Get FMP API key from environment variable.

    Returns:
        API key string or None if not found
    """
    api_key = os.environ.get("FMP_API_KEY")
    if not api_key:
        print("Warning: FMP_API_KEY environment variable not set", file=sys.stderr)
    return api_key


def fetch_economic_calendar(from_date: str, to_date: str, api_key: str) -> list[dict]:
    """
    Fetch economic calendar data from FMP API.

    HTTP/auth/retry live in the vendored ``fmp_client.py`` (generated,
    Issue #495). The client's ``get_economic_calendar`` extension keeps the
    raise semantics the old urllib implementation pinned: 402 → the exact
    upgrade-required ``ValueError``; other HTTP failures → ``API returned
    status code {code}``; transport failures → ``Network error: ...``;
    non-list 200 payload → ``Unexpected API response format``. Header auth
    (deliberate change from query-param): the key never appears in a URL.

    Args:
        from_date: Start date in YYYY-MM-DD format
        to_date: End date in YYYY-MM-DD format
        api_key: FMP API key

    Returns:
        List of economic event dictionaries

    Raises:
        ValueError: If response is invalid, transport fails, or the endpoint
            is restricted (402)
    """
    client = FMPClient(api_key=api_key)
    try:
        events = client.get_economic_calendar(from_date, to_date)
    except ValueError as exc:
        # The generated client reports non-null, non-list HTTP-200 JSON shapes
        # explicitly. Null and malformed JSON use its generic acquisition-failure
        # API and remain calendar_fetch_failed; do not pretend we can distinguish
        # their underlying HTTP/body state here.
        if str(exc).startswith("Unexpected API response format:"):
            raise EconomicCalendarSchemaError(
                "Unexpected API response format: economic calendar must be a JSON array"
            ) from None
        raise
    validate_economic_events(events)
    return events


def validate_date_range(from_date: str, to_date: str) -> None:
    """
    Validate date range is within FMP API limits (max 90 days).

    Args:
        from_date: Start date in YYYY-MM-DD format
        to_date: End date in YYYY-MM-DD format

    Raises:
        ValueError: If date range is invalid or exceeds 90 days
    """
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

    # Warn if querying past dates
    today = datetime.now().date()
    if end.date() < today:
        print(f"Warning: End date {to_date} is in the past", file=sys.stderr)


def format_event_output(events: list[dict], output_format: str = "json") -> str:
    """
    Format economic events for output.

    Args:
        events: List of event dictionaries from FMP API
        output_format: Output format ('json' or 'text')

    Returns:
        Formatted string
    """
    if output_format == "json":
        return json.dumps(events, indent=2, ensure_ascii=False)

    elif output_format == "text":
        lines = []
        lines.append(f"Economic Calendar Events (Total: {len(events)})")
        lines.append("=" * 80)

        for event in events:
            lines.append(f"\nDate: {event.get('date', 'N/A')}")
            lines.append(f"Country: {event.get('country', 'N/A')}")
            lines.append(f"Event: {event.get('event', 'N/A')}")
            lines.append(f"Currency: {event.get('currency', 'N/A')}")
            lines.append(f"Impact: {event.get('impact', 'N/A')}")

            previous = event.get("previous")
            estimate = event.get("estimate")
            actual = event.get("actual")

            if previous is not None:
                lines.append(f"Previous: {previous}")
            if estimate is not None:
                lines.append(f"Estimate: {estimate}")
            if actual is not None:
                lines.append(f"Actual: {actual}")

            change = event.get("change")
            change_pct = event.get("changePercentage")
            if change is not None:
                lines.append(f"Change: {change}")
            if change_pct is not None:
                lines.append(f"Change %: {change_pct}%")

            lines.append("-" * 80)

        return "\n".join(lines)

    else:
        raise ValueError(f"Unknown output format: {output_format}")


def main():
    """Main execution function."""
    parser = argparse.ArgumentParser(
        description="Fetch economic calendar events from FMP API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Fetch events for next 7 days (default)
  python get_economic_calendar.py

  # Fetch events for specific date range
  python get_economic_calendar.py --from 2025-01-01 --to 2025-01-31

  # Provide API key via argument (overrides environment variable)
  python get_economic_calendar.py --api-key YOUR_KEY_HERE

  # Output as formatted text instead of JSON
  python get_economic_calendar.py --format text

  # Save output to file
  python get_economic_calendar.py --output calendar.json
        """,
    )

    # Date range arguments
    today = datetime.now().date()
    default_from = today.strftime("%Y-%m-%d")
    default_to = (today + timedelta(days=7)).strftime("%Y-%m-%d")

    parser.add_argument(
        "--from",
        dest="from_date",
        default=default_from,
        help=f"Start date in YYYY-MM-DD format (default: {default_from})",
    )
    parser.add_argument(
        "--to",
        dest="to_date",
        default=default_to,
        help=f"End date in YYYY-MM-DD format (default: {default_to})",
    )

    # API key argument
    parser.add_argument(
        "--api-key", dest="api_key", help="FMP API key (overrides FMP_API_KEY environment variable)"
    )

    # Output format
    parser.add_argument(
        "--format", choices=["json", "text"], default="json", help="Output format (default: json)"
    )

    # Output file
    parser.add_argument("--output", "-o", help="Output file path (default: stdout)")

    # Parse arguments
    args = parser.parse_args()

    # Get API key
    api_key = args.api_key or get_api_key()
    if not api_key:
        print(
            "Error: FMP API key is required. Set FMP_API_KEY environment variable or use --api-key",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        # Validate date range
        validate_date_range(args.from_date, args.to_date)

        # Fetch events
        print(
            f"Fetching economic calendar from {args.from_date} to {args.to_date}...",
            file=sys.stderr,
        )
        try:
            events = fetch_economic_calendar(args.from_date, args.to_date, api_key)
        except EconomicCalendarSchemaError:
            print("ZERO_RESULT_REASON=economic_calendar_schema_drift", file=sys.stderr)
            raise
        except Exception:
            print("ZERO_RESULT_REASON=calendar_fetch_failed", file=sys.stderr)
            raise
        if not events:
            print(
                "ZERO_RESULT_REASON=empty_calendar_unverified",  # pragma: allowlist secret
                file=sys.stderr,
            )
            raise ValueError(
                "FMP returned no economic events; completeness is unverified. "
                "Check the provider and date window before reporting a quiet calendar."
            )

        print(f"Retrieved {len(events)} events", file=sys.stderr)

        # Format output
        output = format_event_output(events, args.format)

        # Write output
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(output)
            print(f"Output written to {args.output}", file=sys.stderr)
        else:
            print(output)

        sys.exit(0)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
