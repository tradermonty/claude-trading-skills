#!/usr/bin/env python3
"""
Institutional Flow Tracker - Portfolio Tracking

Track portfolio changes of specific institutional investors (hedge funds, mutual funds)
by analyzing their 13F filings over time. Follow superinvestors like Warren Buffett.

Usage:
    python3 track_institution_portfolio.py --cik 0001067983 --name "Berkshire Hathaway"
    python3 track_institution_portfolio.py --cik 0001579982 --name "ARK Investment"

Note: This is a simplified version. For full portfolio tracking, use WhaleWisdom or
      SEC EDGAR directly, as FMP API has limited institution-specific endpoints.
"""

import argparse
import os
import sys
from datetime import datetime

print(
    "ERROR: This script is not yet functional. "
    "See below for alternative resources.",
    file=sys.stderr,
)

print("""
================================================================================
TRACK INSTITUTION PORTFOLIO - NOT YET IMPLEMENTED
================================================================================

This script is a placeholder and does not provide functional portfolio tracking.

1. Use WhaleWisdom (free tier available): https://whalewisdom.com
2. Use SEC EDGAR directly: https://www.sec.gov/cgi-bin/browse-edgar
3. Use DataRoma for superinvestors: https://www.dataroma.com

FMP API has limited institution-specific portfolio endpoints. The institutional
holder data is organized by stock (not by institution), making it difficult to
efficiently reconstruct an institution's full portfolio.

Recommended Workflow:
--------------------
1. Visit WhaleWisdom or DataRoma
2. Search for your target institution by name or CIK
3. View their current portfolio and quarterly changes
4. Use this skill's other scripts to analyze specific stocks they hold

Notable Institutions to Track:
-----------------------------
- Berkshire Hathaway (CIK: 0001067983) - Warren Buffett
- Baupost Group (CIK: 0001061768) - Seth Klarman
- Pershing Square (CIK: 0001336528) - Bill Ackman
- Appaloosa Management (CIK: 0001079114) - David Tepper
- Third Point (CIK: 0001040273) - Dan Loeb
- ARK Investment (CIK: 0001579982) - Cathie Wood
- Fidelity Management (CIK: 0000315066)
- T. Rowe Price (CIK: 0001113169)
- Dodge & Cox (CIK: 0000922614)

Alternative Approach:
-------------------
If you know the top holdings of an institution, you can use the
analyze_single_stock.py script to see if they've changed their positions:

Example for Berkshire's top holdings:
    python3 analyze_single_stock.py AAPL  # Check if Berkshire changed position
    python3 analyze_single_stock.py KO    # Coca-Cola
    python3 analyze_single_stock.py BAC   # Bank of America

================================================================================
""")


def main():
    parser = argparse.ArgumentParser(
        description='Track institutional investor portfolio changes (simplified)'
    )

    parser.add_argument(
        '--cik',
        type=str,
        required=True,
        help='Central Index Key of the institution'
    )
    parser.add_argument(
        '--name',
        type=str,
        required=True,
        help='Institution name'
    )
    parser.add_argument(
        '--api-key',
        type=str,
        default=os.getenv('FMP_API_KEY'),
        help='FMP API key (currently not used in simplified version)'
    )

    args = parser.parse_args()

    print(f"Institution: {args.name}")
    print(f"CIK: {args.cik}")
    print()
    print("For detailed portfolio tracking, please use:")
    print(f"1. WhaleWisdom: https://whalewisdom.com/filer/{args.name.lower().replace(' ', '-')}")
    print(f"2. SEC EDGAR: https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={args.cik}&type=13F")
    print(f"3. DataRoma: https://www.dataroma.com (if superinvestor)")
    print()

    return 1


if __name__ == '__main__':
    sys.exit(main())
