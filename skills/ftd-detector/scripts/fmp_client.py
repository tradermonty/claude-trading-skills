#!/usr/bin/env python3
"""
FMP API Client for Market Top Detector

Provides rate-limited access to Financial Modeling Prep API endpoints
for market top detection analysis.

Features:
- Rate limiting (0.3s between requests)
- Automatic retry on 429 errors
- Session caching for duplicate requests
- Batch quote support for ETF baskets
"""

import os
import sys
import time
from typing import Dict, List, Optional

try:
    import requests
except ImportError:
    print("ERROR: requests library not found. Install with: pip install requests", file=sys.stderr)
    sys.exit(1)


class FMPClient:
    """Client for Financial Modeling Prep API with rate limiting and caching"""

    BASE_URL = "https://financialmodelingprep.com/api/v3"
    RATE_LIMIT_DELAY = 0.3  # 300ms between requests

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("FMP_API_KEY")
        if not self.api_key:
            raise ValueError(
                "FMP API key required. Set FMP_API_KEY environment variable "
                "or pass api_key parameter."
            )
        self.session = requests.Session()
        self.cache = {}
        self.last_call_time = 0
        self.rate_limit_reached = False
        self.retry_count = 0
        self.max_retries = 1
        self.api_calls_made = 0

    def _rate_limited_get(self, url: str, params: Optional[Dict] = None) -> Optional[Dict]:
        if self.rate_limit_reached:
            return None

        if params is None:
            params = {}
        params['apikey'] = self.api_key

        elapsed = time.time() - self.last_call_time
        if elapsed < self.RATE_LIMIT_DELAY:
            time.sleep(self.RATE_LIMIT_DELAY - elapsed)

        try:
            response = self.session.get(url, params=params, timeout=30)
            self.last_call_time = time.time()
            self.api_calls_made += 1

            if response.status_code == 200:
                self.retry_count = 0
                return response.json()
            elif response.status_code == 429:
                self.retry_count += 1
                if self.retry_count <= self.max_retries:
                    print("WARNING: Rate limit exceeded. Waiting 60 seconds...", file=sys.stderr)
                    time.sleep(60)
                    return self._rate_limited_get(url, params)
                else:
                    print("ERROR: Daily API rate limit reached.", file=sys.stderr)
                    self.rate_limit_reached = True
                    return None
            else:
                print(f"ERROR: API request failed: {response.status_code} - {response.text[:200]}",
                      file=sys.stderr)
                return None
        except requests.exceptions.RequestException as e:
            print(f"ERROR: Request exception: {e}", file=sys.stderr)
            return None

    def get_quote(self, symbols: str) -> Optional[List[Dict]]:
        """Fetch real-time quote data for one or more symbols (comma-separated)"""
        cache_key = f"quote_{symbols}"
        if cache_key in self.cache:
            return self.cache[cache_key]

        url = f"{self.BASE_URL}/quote/{symbols}"
        data = self._rate_limited_get(url)
        if data:
            self.cache[cache_key] = data
        return data

    def get_historical_prices(self, symbol: str, days: int = 365) -> Optional[Dict]:
        """Fetch historical daily OHLCV data"""
        cache_key = f"prices_{symbol}_{days}"
        if cache_key in self.cache:
            return self.cache[cache_key]

        url = f"{self.BASE_URL}/historical-price-full/{symbol}"
        params = {"timeseries": days}
        data = self._rate_limited_get(url, params)
        if data:
            self.cache[cache_key] = data
        return data

    def get_batch_quotes(self, symbols: List[str]) -> Dict[str, Dict]:
        """Fetch quotes for a list of symbols, batching up to 5 per request"""
        results = {}
        # FMP supports comma-separated symbols in quote endpoint
        batch_size = 5
        for i in range(0, len(symbols), batch_size):
            batch = symbols[i:i+batch_size]
            batch_str = ",".join(batch)
            quotes = self.get_quote(batch_str)
            if quotes:
                for q in quotes:
                    results[q['symbol']] = q
        return results

    def get_batch_historical(self, symbols: List[str], days: int = 50) -> Dict[str, List[Dict]]:
        """Fetch historical prices for multiple symbols"""
        results = {}
        for symbol in symbols:
            data = self.get_historical_prices(symbol, days=days)
            if data and 'historical' in data:
                results[symbol] = data['historical']
        return results

    def calculate_ema(self, prices: List[float], period: int) -> float:
        """Calculate Exponential Moving Average from a list of prices (most recent first)"""
        if len(prices) < period:
            return sum(prices) / len(prices)

        prices_reversed = prices[::-1]
        sma = sum(prices_reversed[:period]) / period
        ema = sma
        k = 2 / (period + 1)
        for price in prices_reversed[period:]:
            ema = price * k + ema * (1 - k)
        return ema

    def calculate_sma(self, prices: List[float], period: int) -> float:
        """Calculate Simple Moving Average from a list of prices (most recent first)"""
        if len(prices) < period:
            return sum(prices) / len(prices)
        return sum(prices[:period]) / period

    def get_api_stats(self) -> Dict:
        return {
            "cache_entries": len(self.cache),
            "api_calls_made": self.api_calls_made,
            "rate_limit_reached": self.rate_limit_reached,
        }
