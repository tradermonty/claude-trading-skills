#!/usr/bin/env python3
"""
Test FMP institutional-holder endpoint availability
Critical decision point for Phase 2 implementation
"""

import os
import sys
from datetime import date

import requests


def _latest_completed_quarter(as_of=None):
    """(year, quarter) of the most recent completed calendar quarter."""
    d = as_of or date.today()
    year = d.year
    quarter = (d.month - 1) // 3  # current quarter (1-4) minus 1 = last completed
    if quarter == 0:
        quarter, year = 4, year - 1
    return year, quarter


def check_institutional_endpoint():
    """
    Test if /stable institutional-ownership data is available with the API key.

    The skill sources the CANSLIM 'I' component from /stable
    institutional-ownership (symbol-positions-summary for the holder count +
    ownership %), with a v3 fallback handled automatically in FMPClient. This
    is just an availability probe.

    Returns:
        bool: True if institutional data is reachable, False otherwise.
    """
    api_key = os.environ.get("FMP_API_KEY")

    if not api_key:
        print("ERROR: FMP_API_KEY environment variable not set", file=sys.stderr)
        print("Please set it with: export FMP_API_KEY=your_key")
        return False

    print(f"Testing /stable institutional-ownership with API key (length: {len(api_key)})...")
    print()

    test_symbol = "AAPL"
    year, quarter = _latest_completed_quarter()
    url = (
        "https://financialmodelingprep.com/stable/institutional-ownership/symbol-positions-summary"
    )
    params = {"symbol": test_symbol, "year": year, "quarter": quarter, "apikey": api_key}

    try:
        response = requests.get(url, params=params, timeout=10)

        print(f"Status Code: {response.status_code} (year={year} Q{quarter})")
        print(f"Response length: {len(response.text)} bytes")
        print()

        if response.status_code == 200:
            data = response.json()
            if isinstance(data, list) and data and data[0].get("investorsHolding"):
                summary = data[0]
                print("✅ RESULT: Institutional data AVAILABLE")
                print(
                    f"   {test_symbol}: {summary.get('investorsHolding')} holders, "
                    f"ownership {summary.get('ownershipPercent')}%"
                )
                return True
            print("⚠️  RESULT: No institutional data for the latest quarter")
            print(f"   Data: {str(data)[:200]}")
            return False

        if response.status_code in (401, 403):
            print("❌ RESULT: RESTRICTED (401/403) — check subscription/key")
            return False

        print(f"⚠️  RESULT: Unexpected status code {response.status_code}")
        return False

    except requests.exceptions.RequestException as e:
        print(f"❌ ERROR: Request failed - {e}", file=sys.stderr)
        return False


if __name__ == "__main__":
    print("=" * 70)
    print("FMP Institutional-Holder Endpoint Availability Test")
    print("=" * 70)
    print()

    result = check_institutional_endpoint()

    print()
    print("=" * 70)

    sys.exit(0 if result else 1)
