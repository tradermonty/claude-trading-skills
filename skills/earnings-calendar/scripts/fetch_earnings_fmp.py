#!/usr/bin/env python3
"""
Finnhub Earnings Calendar Fetcher

Replaces FMP API with Finnhub (free tier, 60 calls/min).
Retrieves upcoming earnings announcements, filters by market cap (>$2B),
and outputs structured JSON data to stdout.

Usage:
    # With environment variable
    export FINNHUB_API_KEY="your-key"
    python fetch_earnings_fmp.py 2026-03-23 2026-03-30

    # With API key as argument
    python fetch_earnings_fmp.py 2026-03-23 2026-03-30 YOUR_API_KEY
"""

import json
import os
import sys
import time
from datetime import datetime
from typing import Optional

try:
    import finnhub
except ImportError:
    print("Error: finnhub-python not installed. Run: pip install finnhub-python", file=sys.stderr)
    sys.exit(1)


MIN_MARKET_CAP = 2_000_000_000  # $2B
US_EXCHANGES = {"NYSE", "NASDAQ", "AMEX", "NYSEArca", "BATS", "NMS", "NGM", "NCM"}


def get_api_key() -> Optional[str]:
    if len(sys.argv) >= 4:
        print("API key provided via command line argument", file=sys.stderr)
        return sys.argv[3]
    api_key = os.environ.get("FINNHUB_API_KEY")
    if api_key:
        print("API key loaded from FINNHUB_API_KEY environment variable", file=sys.stderr)
        return api_key
    print("ERROR: No API key found.", file=sys.stderr)
    print("Set FINNHUB_API_KEY environment variable or pass as third argument.", file=sys.stderr)
    return None


def validate_date(date_str: str) -> bool:
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def normalize_timing(hour: Optional[int]) -> str:
    """Normalize earnings hour to BMO/AMC/TAS."""
    if hour is None:
        return "TAS"
    if hour < 12:
        return "BMO"
    return "AMC"


def format_market_cap(market_cap: float) -> str:
    if market_cap >= 1e12:
        return f"${market_cap / 1e12:.1f}T"
    elif market_cap >= 1e9:
        return f"${market_cap / 1e9:.1f}B"
    elif market_cap >= 1e6:
        return f"${market_cap / 1e6:.0f}M"
    return f"${market_cap:,.0f}"


def fetch_earnings(client: finnhub.Client, start_date: str, end_date: str) -> list[dict]:
    """Fetch earnings calendar from Finnhub."""
    try:
        result = client.earnings_calendar(_from=start_date, to=end_date, symbol="", international=False)
        earnings_list = result.get("earningsCalendar", []) if isinstance(result, dict) else []
        print(f"Retrieved {len(earnings_list)} earnings entries", file=sys.stderr)
        return earnings_list
    except Exception as e:
        print(f"ERROR fetching earnings calendar: {e}", file=sys.stderr)
        return []


def fetch_profile(client: finnhub.Client, symbol: str) -> Optional[dict]:
    """Fetch company profile from Finnhub."""
    try:
        return client.company_profile2(symbol=symbol)
    except Exception as e:
        print(f"WARNING: Profile fetch failed for {symbol}: {e}", file=sys.stderr)
        return None


def main():
    if len(sys.argv) > 1 and sys.argv[1] in ["-h", "--help"]:
        print("Usage: python fetch_earnings_fmp.py START_DATE END_DATE [API_KEY]", file=sys.stderr)
        sys.exit(0)

    if len(sys.argv) < 3:
        print("ERROR: Missing required arguments: START_DATE END_DATE", file=sys.stderr)
        sys.exit(1)

    start_date = sys.argv[1]
    end_date = sys.argv[2]

    if not validate_date(start_date):
        print(f"ERROR: Invalid start date: {start_date} (expected YYYY-MM-DD)", file=sys.stderr)
        sys.exit(1)
    if not validate_date(end_date):
        print(f"ERROR: Invalid end date: {end_date} (expected YYYY-MM-DD)", file=sys.stderr)
        sys.exit(1)

    api_key = get_api_key()
    if not api_key:
        sys.exit(1)

    print(f"Fetching earnings calendar: {start_date} to {end_date}", file=sys.stderr)
    client = finnhub.Client(api_key=api_key)

    # Step 1: Fetch earnings calendar
    print("Step 1: Fetching earnings calendar...", file=sys.stderr)
    earnings = fetch_earnings(client, start_date, end_date)
    if not earnings:
        print(json.dumps([]))
        sys.exit(0)

    # Step 2: Fetch company profiles and filter by market cap
    print("Step 2: Fetching company profiles...", file=sys.stderr)
    symbols = list(set(e.get("symbol", "") for e in earnings if e.get("symbol")))
    profiles = {}
    for i, symbol in enumerate(symbols):
        profile = fetch_profile(client, symbol)
        if profile:
            profiles[symbol] = profile
        # Rate limit: 60 calls/min on free tier
        if i > 0 and i % 55 == 0:
            print(f"  Rate limit pause at {i} symbols...", file=sys.stderr)
            time.sleep(60)
        else:
            time.sleep(1.1)

    print(f"Retrieved {len(profiles)} company profiles", file=sys.stderr)

    # Step 3: Filter and enrich
    print("Step 3: Filtering by market cap...", file=sys.stderr)
    filtered = []
    for entry in earnings:
        symbol = entry.get("symbol", "")
        if not symbol:
            continue
        profile = profiles.get(symbol)
        if not profile:
            continue
        market_cap = profile.get("marketCapitalization", 0)
        # Finnhub returns marketCapitalization in millions
        market_cap_usd = market_cap * 1_000_000 if market_cap else 0
        if market_cap_usd < MIN_MARKET_CAP:
            continue
        exchange = profile.get("exchange", "")
        if exchange not in US_EXCHANGES:
            continue

        timing = normalize_timing(entry.get("hour"))
        filtered.append({
            "symbol": symbol,
            "companyName": profile.get("name", symbol),
            "date": entry.get("date", ""),
            "timing": timing,
            "marketCap": market_cap_usd,
            "marketCapFormatted": format_market_cap(market_cap_usd),
            "sector": profile.get("finnhubIndustry", "N/A"),
            "industry": profile.get("finnhubIndustry", "N/A"),
            "epsEstimated": entry.get("epsEstimate"),
            "revenueEstimated": entry.get("revenueEstimate"),
            "fiscalDateEnding": entry.get("date", ""),
            "exchange": exchange,
        })

    print(f"Filtered to {len(filtered)} US mid-cap+ companies (>$2B)", file=sys.stderr)

    # Step 4: Sort by date, timing, market cap
    timing_order = {"BMO": 1, "AMC": 2, "TAS": 3}
    filtered.sort(key=lambda x: (
        x.get("date", ""),
        timing_order.get(x.get("timing", "TAS"), 3),
        -x.get("marketCap", 0),
    ))

    print(f"Final dataset: {len(filtered)} companies", file=sys.stderr)
    print(json.dumps(filtered, indent=2))


if __name__ == "__main__":
    main()
