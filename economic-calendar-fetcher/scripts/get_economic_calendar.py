#!/usr/bin/env python3
"""
Economic Calendar Fetcher using FMP API
Retrieves economic events and data releases for specified date range
"""

import os
import sys
import json
import argparse
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import urllib.request
import urllib.error
import urllib.parse


def get_api_key() -> Optional[str]:
    """
    Get FMP API key from environment variable.

    Returns:
        API key string or None if not found
    """
    api_key = os.environ.get('FMP_API_KEY')
    if not api_key:
        print("Warning: FMP_API_KEY environment variable not set", file=sys.stderr)
    return api_key


def fetch_economic_calendar(
    from_date: str,
    to_date: str,
    api_key: str
) -> List[Dict]:
    """
    Fetch economic calendar data from FMP API.

    Args:
        from_date: Start date in YYYY-MM-DD format
        to_date: End date in YYYY-MM-DD format
        api_key: FMP API key

    Returns:
        List of economic event dictionaries

    Raises:
        urllib.error.HTTPError: If API request fails
        ValueError: If response is invalid
    """
    base_url = "https://financialmodelingprep.com/api/v3/economic_calendar"

    # Build query parameters
    params = {
        'from': from_date,
        'to': to_date,
        'apikey': api_key
    }

    # Construct URL with parameters
    url = f"{base_url}?{urllib.parse.urlencode(params)}"

    try:
        # Make API request
        with urllib.request.urlopen(url) as response:
            if response.status != 200:
                raise ValueError(f"API returned status code {response.status}")

            data = json.loads(response.read().decode('utf-8'))

            if not isinstance(data, list):
                raise ValueError(f"Unexpected API response format: {type(data)}")

            return data

    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8') if e.fp else 'No error details'
        raise urllib.error.HTTPError(
            e.url, e.code, f"FMP API error: {e.reason}. Details: {error_body}",
            e.hdrs, e.fp
        )
    except urllib.error.URLError as e:
        raise ValueError(f"Network error: {e.reason}")


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
        start = datetime.strptime(from_date, '%Y-%m-%d')
        end = datetime.strptime(to_date, '%Y-%m-%d')
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


def format_event_output(events: List[Dict], output_format: str = 'json') -> str:
    """
    Format economic events for output.

    Args:
        events: List of event dictionaries from FMP API
        output_format: Output format ('json' or 'text')

    Returns:
        Formatted string
    """
    if output_format == 'json':
        return json.dumps(events, indent=2, ensure_ascii=False)

    elif output_format == 'text':
        lines = []
        lines.append(f"Economic Calendar Events (Total: {len(events)})")
        lines.append("=" * 80)

        for event in events:
            lines.append(f"\nDate: {event.get('date', 'N/A')}")
            lines.append(f"Country: {event.get('country', 'N/A')}")
            lines.append(f"Event: {event.get('event', 'N/A')}")
            lines.append(f"Currency: {event.get('currency', 'N/A')}")
            lines.append(f"Impact: {event.get('impact', 'N/A')}")

            previous = event.get('previous')
            estimate = event.get('estimate')
            actual = event.get('actual')

            if previous is not None:
                lines.append(f"Previous: {previous}")
            if estimate is not None:
                lines.append(f"Estimate: {estimate}")
            if actual is not None:
                lines.append(f"Actual: {actual}")

            change = event.get('change')
            change_pct = event.get('changePercentage')
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
        description='Fetch economic calendar events from FMP API',
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
        """
    )

    # Date range arguments
    today = datetime.now().date()
    default_from = today.strftime('%Y-%m-%d')
    default_to = (today + timedelta(days=7)).strftime('%Y-%m-%d')

    parser.add_argument(
        '--from', dest='from_date',
        default=default_from,
        help=f'Start date in YYYY-MM-DD format (default: {default_from})'
    )
    parser.add_argument(
        '--to', dest='to_date',
        default=default_to,
        help=f'End date in YYYY-MM-DD format (default: {default_to})'
    )

    # API key argument
    parser.add_argument(
        '--api-key', dest='api_key',
        help='FMP API key (overrides FMP_API_KEY environment variable)'
    )

    # Output format
    parser.add_argument(
        '--format', choices=['json', 'text'],
        default='json',
        help='Output format (default: json)'
    )

    # Output file
    parser.add_argument(
        '--output', '-o',
        help='Output file path (default: stdout)'
    )

    # Parse arguments
    args = parser.parse_args()

    # Get API key
    api_key = args.api_key or get_api_key()
    if not api_key:
        print("Error: FMP API key is required. Set FMP_API_KEY environment variable or use --api-key",
              file=sys.stderr)
        sys.exit(1)

    try:
        # Validate date range
        validate_date_range(args.from_date, args.to_date)

        # Fetch events
        print(f"Fetching economic calendar from {args.from_date} to {args.to_date}...",
              file=sys.stderr)
        events = fetch_economic_calendar(args.from_date, args.to_date, api_key)

        print(f"Retrieved {len(events)} events", file=sys.stderr)

        # Format output
        output = format_event_output(events, args.format)

        # Write output
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write(output)
            print(f"Output written to {args.output}", file=sys.stderr)
        else:
            print(output)

        sys.exit(0)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
