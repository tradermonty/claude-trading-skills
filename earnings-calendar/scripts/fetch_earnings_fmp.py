#!/usr/bin/env python3
"""
FMP Earnings Calendar Fetcher

Retrieves upcoming earnings announcements from Financial Modeling Prep API,
filters by market cap (>$2B), and outputs structured JSON data.

Usage:
    # With environment variable
    export FMP_API_KEY="your-key"
    python fetch_earnings_fmp.py 2025-11-03 2025-11-09

    # With API key as argument
    python fetch_earnings_fmp.py 2025-11-03 2025-11-09 YOUR_API_KEY

    # Help
    python fetch_earnings_fmp.py --help
"""

import sys
import os
import json
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Optional


class FMPEarningsCalendar:
    """FMP Earnings Calendar API client"""

    BASE_URL = "https://financialmodelingprep.com/api/v3"
    MIN_MARKET_CAP = 2_000_000_000  # $2B
    US_EXCHANGES = ['NYSE', 'NASDAQ', 'AMEX', 'NYSEArca', 'BATS', 'NMS', 'NGM', 'NCM']

    def __init__(self, api_key: str, us_only: bool = True):
        """
        Initialize FMP client

        Args:
            api_key: FMP API key
            us_only: If True, filter for US stocks only (default: True)
        """
        self.api_key = api_key
        self.us_only = us_only

    def fetch_earnings_calendar(self, start_date: str, end_date: str) -> Optional[List[Dict]]:
        """
        Fetch earnings calendar from FMP API

        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)

        Returns:
            List of earnings announcements or None on error
        """
        url = f"{self.BASE_URL}/earning_calendar"
        params = {
            "apikey": self.api_key,
            "from": start_date,
            "to": end_date
        }

        try:
            response = requests.get(url, params=params, timeout=30)

            if response.status_code == 401:
                print("❌ ERROR: Invalid API key", file=sys.stderr)
                print("Get free API key: https://site.financialmodelingprep.com/developer/docs", file=sys.stderr)
                return None

            if response.status_code == 429:
                print("❌ ERROR: Rate limit exceeded", file=sys.stderr)
                print("Free tier: 250 calls/day. Consider upgrading.", file=sys.stderr)
                return None

            response.raise_for_status()
            data = response.json()

            # Check if response is error message
            if isinstance(data, dict) and "Error Message" in data:
                print(f"❌ API Error: {data['Error Message']}", file=sys.stderr)
                return None

            print(f"✓ Retrieved {len(data)} earnings announcements", file=sys.stderr)
            return data

        except requests.exceptions.Timeout:
            print("❌ ERROR: Request timeout. Please try again.", file=sys.stderr)
            return None

        except requests.exceptions.ConnectionError:
            print("❌ ERROR: Connection error. Check your internet connection.", file=sys.stderr)
            return None

        except Exception as e:
            print(f"❌ ERROR: Unexpected error: {str(e)}", file=sys.stderr)
            return None

    def fetch_company_profiles(self, symbols: List[str]) -> Dict[str, Dict]:
        """
        Fetch company profiles for multiple symbols (batch)

        Args:
            symbols: List of ticker symbols

        Returns:
            Dictionary mapping symbol to profile data
        """
        profiles = {}
        batch_size = 100  # FMP allows batch requests

        print(f"✓ Fetching profiles for {len(symbols)} companies...", file=sys.stderr)

        for i in range(0, len(symbols), batch_size):
            batch = symbols[i:i+batch_size]
            symbols_str = ",".join(batch)

            url = f"{self.BASE_URL}/profile/{symbols_str}"
            params = {"apikey": self.api_key}

            try:
                response = requests.get(url, params=params, timeout=30)
                response.raise_for_status()

                for profile in response.json():
                    if isinstance(profile, dict):
                        profiles[profile.get("symbol")] = profile

                print(f"  ✓ Batch {i//batch_size + 1}: {len(batch)} profiles", file=sys.stderr)

            except Exception as e:
                print(f"  ⚠️  Warning: Failed to fetch batch {i//batch_size + 1}: {str(e)}", file=sys.stderr)
                continue

        print(f"✓ Retrieved {len(profiles)} company profiles", file=sys.stderr)
        return profiles

    def filter_by_market_cap(self, earnings: List[Dict], profiles: Dict[str, Dict]) -> List[Dict]:
        """
        Filter earnings by minimum market cap and enrich with company data

        Args:
            earnings: List of earnings announcements
            profiles: Dictionary of company profiles

        Returns:
            Filtered and enriched list of earnings
        """
        filtered = []

        for earning in earnings:
            symbol = earning.get("symbol")
            if not symbol:
                continue

            profile = profiles.get(symbol)

            # Filter by market cap and exchange
            if profile:
                market_cap = profile.get("mktCap", 0)
                if market_cap < self.MIN_MARKET_CAP:
                    continue

                exchange = profile.get("exchangeShortName", "N/A")

                # Filter by US exchanges if us_only is True
                if self.us_only and exchange not in self.US_EXCHANGES:
                    continue

                # Enrich with profile data
                earning["marketCap"] = market_cap
                earning["companyName"] = profile.get("companyName", symbol)
                earning["sector"] = profile.get("sector", "N/A")
                earning["industry"] = profile.get("industry", "N/A")
                earning["exchange"] = exchange

                filtered.append(earning)

        if self.us_only:
            print(f"✓ Filtered to {len(filtered)} US mid-cap+ companies (>${self.MIN_MARKET_CAP/1e9:.0f}B)", file=sys.stderr)
        else:
            print(f"✓ Filtered to {len(filtered)} mid-cap+ companies (>${self.MIN_MARKET_CAP/1e9:.0f}B)", file=sys.stderr)

        return filtered

    def normalize_timing(self, time_value: Optional[str]) -> str:
        """
        Normalize timing values to BMO/AMC/TAS

        Args:
            time_value: Raw time value from API

        Returns:
            Normalized timing: BMO, AMC, or TAS
        """
        if not time_value:
            return "TAS"

        time_lower = time_value.lower()

        if time_lower in ["bmo", "pre-market", "before market open"]:
            return "BMO"
        elif time_lower in ["amc", "after-market", "after market close"]:
            return "AMC"
        else:
            return "TAS"

    def format_market_cap(self, market_cap: float) -> str:
        """
        Format market cap in human-readable format

        Args:
            market_cap: Market cap in dollars

        Returns:
            Formatted string (e.g., "$3.0T", "$150B")
        """
        if market_cap >= 1e12:
            return f"${market_cap/1e12:.1f}T"
        elif market_cap >= 1e9:
            return f"${market_cap/1e9:.1f}B"
        elif market_cap >= 1e6:
            return f"${market_cap/1e6:.0f}M"
        else:
            return f"${market_cap:,.0f}"

    def process_earnings(self, earnings: List[Dict]) -> List[Dict]:
        """
        Process and standardize earnings data

        Args:
            earnings: Raw earnings data

        Returns:
            Processed earnings data
        """
        processed = []

        for earning in earnings:
            # Normalize timing
            timing = self.normalize_timing(earning.get("time"))

            # Format market cap
            market_cap = earning.get("marketCap", 0)
            market_cap_formatted = self.format_market_cap(market_cap)

            processed_earning = {
                "symbol": earning.get("symbol"),
                "companyName": earning.get("companyName", earning.get("symbol")),
                "date": earning.get("date"),
                "timing": timing,
                "marketCap": market_cap,
                "marketCapFormatted": market_cap_formatted,
                "sector": earning.get("sector", "N/A"),
                "industry": earning.get("industry", "N/A"),
                "epsEstimated": earning.get("epsEstimated"),
                "revenueEstimated": earning.get("revenueEstimated"),
                "fiscalDateEnding": earning.get("fiscalDateEnding"),
                "exchange": earning.get("exchange", "N/A")
            }

            processed.append(processed_earning)

        return processed

    def sort_earnings(self, earnings: List[Dict]) -> List[Dict]:
        """
        Sort earnings by date, timing, and market cap

        Args:
            earnings: Processed earnings data

        Returns:
            Sorted earnings data
        """
        # Define timing order
        timing_order = {"BMO": 1, "AMC": 2, "TAS": 3}

        return sorted(
            earnings,
            key=lambda x: (
                x.get("date", ""),
                timing_order.get(x.get("timing", "TAS"), 3),
                -x.get("marketCap", 0)  # Descending market cap
            )
        )


def get_api_key() -> Optional[str]:
    """
    Get API key from environment or command line

    Returns:
        API key or None
    """
    # Method 1: Command line argument (position 3)
    if len(sys.argv) >= 4:
        api_key = sys.argv[3]
        print("✓ API key provided via command line argument", file=sys.stderr)
        return api_key

    # Method 2: Environment variable
    api_key = os.environ.get('FMP_API_KEY')
    if api_key:
        print("✓ API key loaded from FMP_API_KEY environment variable", file=sys.stderr)
        return api_key

    # Not found
    print("❌ ERROR: No API key found", file=sys.stderr)
    print("", file=sys.stderr)
    print("Options:", file=sys.stderr)
    print("1. Set environment variable: export FMP_API_KEY='your-key'", file=sys.stderr)
    print("2. Pass as argument: python fetch_earnings_fmp.py START END YOUR_KEY", file=sys.stderr)
    print("3. Get free API key: https://site.financialmodelingprep.com/developer/docs", file=sys.stderr)
    return None


def validate_date(date_str: str) -> bool:
    """
    Validate date format (YYYY-MM-DD)

    Args:
        date_str: Date string

    Returns:
        True if valid, False otherwise
    """
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def print_usage():
    """Print usage instructions"""
    print("Usage:", file=sys.stderr)
    print("  python fetch_earnings_fmp.py START_DATE END_DATE [API_KEY]", file=sys.stderr)
    print("", file=sys.stderr)
    print("Arguments:", file=sys.stderr)
    print("  START_DATE  Start date in YYYY-MM-DD format", file=sys.stderr)
    print("  END_DATE    End date in YYYY-MM-DD format", file=sys.stderr)
    print("  API_KEY     (Optional) FMP API key (or use FMP_API_KEY env var)", file=sys.stderr)
    print("", file=sys.stderr)
    print("Examples:", file=sys.stderr)
    print("  export FMP_API_KEY='your-key'", file=sys.stderr)
    print("  python fetch_earnings_fmp.py 2025-11-03 2025-11-09", file=sys.stderr)
    print("", file=sys.stderr)
    print("  python fetch_earnings_fmp.py 2025-11-03 2025-11-09 your-key", file=sys.stderr)
    print("", file=sys.stderr)
    print("Output:", file=sys.stderr)
    print("  JSON data is written to stdout", file=sys.stderr)
    print("  Progress messages are written to stderr", file=sys.stderr)


def main():
    """Main execution"""
    # Check for help flag
    if len(sys.argv) > 1 and sys.argv[1] in ["-h", "--help", "help"]:
        print_usage()
        sys.exit(0)

    # Validate arguments
    if len(sys.argv) < 3:
        print("❌ ERROR: Missing required arguments", file=sys.stderr)
        print("", file=sys.stderr)
        print_usage()
        sys.exit(1)

    start_date = sys.argv[1]
    end_date = sys.argv[2]

    # Validate dates
    if not validate_date(start_date):
        print(f"❌ ERROR: Invalid start date format: {start_date}", file=sys.stderr)
        print("Expected format: YYYY-MM-DD", file=sys.stderr)
        sys.exit(1)

    if not validate_date(end_date):
        print(f"❌ ERROR: Invalid end date format: {end_date}", file=sys.stderr)
        print("Expected format: YYYY-MM-DD", file=sys.stderr)
        sys.exit(1)

    # Get API key
    api_key = get_api_key()
    if not api_key:
        sys.exit(1)

    print(f"", file=sys.stderr)
    print(f"📅 Fetching earnings calendar: {start_date} to {end_date}", file=sys.stderr)
    print(f"", file=sys.stderr)

    # Initialize client
    client = FMPEarningsCalendar(api_key)

    # Step 1: Fetch earnings calendar
    print("Step 1: Fetching earnings calendar...", file=sys.stderr)
    earnings = client.fetch_earnings_calendar(start_date, end_date)
    if earnings is None:
        sys.exit(1)

    if len(earnings) == 0:
        print("⚠️  Warning: No earnings announcements found for date range", file=sys.stderr)
        print(json.dumps([], indent=2))
        sys.exit(0)

    # Step 2: Fetch company profiles
    print("", file=sys.stderr)
    print("Step 2: Fetching company profiles...", file=sys.stderr)
    symbols = list(set([e.get("symbol") for e in earnings if e.get("symbol")]))
    profiles = client.fetch_company_profiles(symbols)

    # Step 3: Filter by market cap
    print("", file=sys.stderr)
    print("Step 3: Filtering by market cap...", file=sys.stderr)
    filtered_earnings = client.filter_by_market_cap(earnings, profiles)

    if len(filtered_earnings) == 0:
        print("⚠️  Warning: No companies with market cap >$2B found", file=sys.stderr)
        print(json.dumps([], indent=2))
        sys.exit(0)

    # Step 4: Process earnings data
    print("", file=sys.stderr)
    print("Step 4: Processing earnings data...", file=sys.stderr)
    processed_earnings = client.process_earnings(filtered_earnings)

    # Step 5: Sort earnings
    print("", file=sys.stderr)
    print("Step 5: Sorting by date, timing, and market cap...", file=sys.stderr)
    sorted_earnings = client.sort_earnings(processed_earnings)

    print(f"✓ Final dataset: {len(sorted_earnings)} companies", file=sys.stderr)

    # Output JSON to stdout
    print("", file=sys.stderr)
    print("✓ Complete! Writing JSON output...", file=sys.stderr)
    print(json.dumps(sorted_earnings, indent=2))


if __name__ == "__main__":
    main()
