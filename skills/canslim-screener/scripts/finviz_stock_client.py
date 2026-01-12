#!/usr/bin/env python3
"""
Finviz Stock Data Client

Fetches individual stock data from Finviz including institutional ownership.
Uses simple web scraping with BeautifulSoup (no API key required).

Install: pip install beautifulsoup4 requests lxml

Usage:
    from finviz_stock_client import FinvizStockClient

    client = FinvizStockClient()
    data = client.get_institutional_ownership("AAPL")
    print(f"Inst Own: {data['inst_own_pct']}%")
"""

import sys
import time
import re
from typing import Dict, Optional

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("ERROR: required libraries not found. Install with: pip install beautifulsoup4 requests lxml", file=sys.stderr)
    sys.exit(1)


class FinvizStockClient:
    """Client for fetching stock data from Finviz"""

    BASE_URL = "https://finviz.com/quote.ashx"

    def __init__(self, rate_limit_seconds: float = 2.0):
        """
        Initialize Finviz client

        Args:
            rate_limit_seconds: Delay between requests to avoid rate limiting (default: 2.0s)
        """
        self.rate_limit_seconds = rate_limit_seconds
        self.last_request_time = 0.0
        self.cache = {}
        self.session = requests.Session()
        # Use a realistic user agent to avoid blocking
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        })

    def _rate_limited_fetch(self, symbol: str) -> Optional[Dict]:
        """
        Fetch stock data with rate limiting

        Args:
            symbol: Stock ticker symbol

        Returns:
            Dict with stock data, or None if fetch failed
        """
        # Respect rate limit
        elapsed = time.time() - self.last_request_time
        if elapsed < self.rate_limit_seconds:
            time.sleep(self.rate_limit_seconds - elapsed)

        try:
            url = f"{self.BASE_URL}?t={symbol}"
            response = self.session.get(url, timeout=15)
            self.last_request_time = time.time()

            if response.status_code == 200:
                return self._parse_finviz_page(response.text)
            else:
                print(f"WARNING: Finviz request failed with status {response.status_code} for {symbol}", file=sys.stderr)
                return None

        except Exception as e:
            print(f"WARNING: Failed to fetch Finviz data for {symbol}: {e}", file=sys.stderr)
            self.last_request_time = time.time()
            return None

    def _parse_finviz_page(self, html: str) -> Dict:
        """
        Parse Finviz stock page HTML

        Args:
            html: HTML content

        Returns:
            Dict with extracted data fields
        """
        soup = BeautifulSoup(html, 'lxml')

        # Finviz uses a table structure with label-value pairs
        data = {}

        # Find all table rows containing data
        tables = soup.find_all('table', {'class': 'snapshot-table2'})

        for table in tables:
            rows = table.find_all('tr')
            for row in rows:
                cells = row.find_all('td')
                # Each row has pairs of (label, value, label, value, ...)
                for i in range(0, len(cells), 2):
                    if i + 1 < len(cells):
                        label = cells[i].get_text(strip=True)
                        value = cells[i + 1].get_text(strip=True)
                        data[label] = value

        return data

    def get_institutional_ownership(self, symbol: str) -> Dict:
        """
        Get institutional ownership data from Finviz

        Args:
            symbol: Stock ticker symbol

        Returns:
            Dict with:
                - inst_own_pct: Institutional ownership percentage (float, or None)
                - inst_trans_pct: Institutional transactions percentage (float, or None)
                - error: Error message if data unavailable

        Example:
            >>> client = FinvizStockClient()
            >>> data = client.get_institutional_ownership("AAPL")
            >>> print(f"Inst Own: {data['inst_own_pct']}%")
            Inst Own: 60.5%
        """
        # Check cache first
        cache_key = f"finviz_inst_{symbol}"
        if cache_key in self.cache:
            return self.cache[cache_key]

        # Fetch from Finviz
        stock_data = self._rate_limited_fetch(symbol)

        if not stock_data:
            result = {
                "inst_own_pct": None,
                "inst_trans_pct": None,
                "error": f"Failed to fetch data from Finviz for {symbol}"
            }
            self.cache[cache_key] = result
            return result

        # Extract institutional data
        # Finviz returns strings like "60.50%" or "-" if unavailable
        inst_own_str = stock_data.get("Inst Own", "-")
        inst_trans_str = stock_data.get("Inst Trans", "-")

        # Parse percentage strings
        inst_own_pct = self._parse_percentage(inst_own_str)
        inst_trans_pct = self._parse_percentage(inst_trans_str)

        result = {
            "inst_own_pct": inst_own_pct,
            "inst_trans_pct": inst_trans_pct,
            "error": None
        }

        # Cache result
        self.cache[cache_key] = result
        return result

    @staticmethod
    def _parse_percentage(pct_str: str) -> Optional[float]:
        """
        Parse percentage string from Finviz

        Args:
            pct_str: Percentage string like "60.50%" or "-"

        Returns:
            Float percentage value (60.50), or None if unavailable
        """
        if not pct_str or pct_str == "-":
            return None

        try:
            # Remove '%' and convert to float
            return float(pct_str.rstrip('%'))
        except (ValueError, AttributeError):
            return None

    def get_stock_data(self, symbol: str) -> Optional[Dict]:
        """
        Get full stock data dict from Finviz

        Args:
            symbol: Stock ticker symbol

        Returns:
            Dict with all Finviz data fields, or None if unavailable
        """
        cache_key = f"finviz_full_{symbol}"
        if cache_key in self.cache:
            return self.cache[cache_key]

        stock_data = self._rate_limited_fetch(symbol)
        if stock_data:
            self.cache[cache_key] = stock_data

        return stock_data


# Example usage
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Test Finviz institutional ownership fetcher")
    parser.add_argument("symbol", help="Stock ticker symbol")
    args = parser.parse_args()

    client = FinvizStockClient()
    data = client.get_institutional_ownership(args.symbol)

    print("\nFinviz Institutional Ownership Data:")
    print(f"  Symbol: {args.symbol}")
    print(f"  Inst Own: {data['inst_own_pct']}%" if data['inst_own_pct'] is not None else "  Inst Own: N/A")
    print(f"  Inst Trans: {data['inst_trans_pct']}%" if data['inst_trans_pct'] is not None else "  Inst Trans: N/A")

    if data.get('error'):
        print(f"  Error: {data['error']}")
