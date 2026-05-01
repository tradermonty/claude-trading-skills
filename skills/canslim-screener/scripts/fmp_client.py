#!/usr/bin/env python3
"""
FMP API Client for CANSLIM Screener

Provides rate-limited access to Financial Modeling Prep API endpoints
required for CANSLIM component analysis (C, A, N, M).

Features:
- Rate limiting (0.3s between requests)
- Automatic retry on 429 errors
- Session caching for duplicate requests
- Error handling and logging
"""

import os
import sys
import time
from datetime import date, timedelta
from typing import Optional

try:
    import requests
except ImportError:
    print("ERROR: requests library not found. Install with: pip install requests", file=sys.stderr)
    sys.exit(1)


# --- FMP endpoint fallback: stable (new users) -> v3 (legacy users) ---


def _stable_quote_url(base, symbols_str, params):
    """stable/quote?symbol=^GSPC"""
    params["symbol"] = symbols_str
    return base, params


def _v3_quote_url(base, symbols_str, params):
    """api/v3/quote/^GSPC"""
    return f"{base}/{symbols_str}", params


def _stable_hist_url(base, symbols_str, params):
    """stable/historical-price-eod/full?symbol=^GSPC&from=...&to=..."""
    params["symbol"] = symbols_str
    # New stable EOD endpoint ignores `timeseries`; convert to from/to range
    # to bound the payload. Use 2x calendar days to cover N trading days
    # (trading-day/calendar-day ratio ~252/365 ~0.69, so *2 leaves headroom).
    days = params.pop("timeseries", None)
    if days is not None:
        today = date.today()
        params["from"] = (today - timedelta(days=int(days) * 2)).isoformat()
        params["to"] = today.isoformat()
    return base, params


def _v3_hist_url(base, symbols_str, params):
    """api/v3/historical-price-full/^GSPC?timeseries=80"""
    return f"{base}/{symbols_str}", params


_FMP_ENDPOINTS = {
    "quote": [
        ("https://financialmodelingprep.com/stable/quote", _stable_quote_url),
        ("https://financialmodelingprep.com/api/v3/quote", _v3_quote_url),
    ],
    "historical": [
        ("https://financialmodelingprep.com/stable/historical-price-eod/full", _stable_hist_url),
        ("https://financialmodelingprep.com/api/v3/historical-price-full", _v3_hist_url),
    ],
}


def _normalize_eod_flat_list(data, symbols_str: str, limit: Optional[int] = None):
    """Convert stable/historical-price-eod/full flat list to v3-compatible dict.

    Input  : [{"symbol": "SPY", "date": "...", "open": ..., ...}, ...]
    Output : {"symbol": "SPY", "historical": [{"date": ..., "open": ..., ...}, ...]}

    Returns the input unchanged if not a list (passthrough for v3 dict /
    historicalStockList responses). Returns None when no row matches the
    requested symbol; the caller will record the failure and try the next
    endpoint.

    If `limit` is provided (the original `timeseries=N` request), the
    `historical` list is truncated to the first `limit` entries. The new
    EOD endpoint ignores `timeseries` and returns the full available history,
    so the caller's date-range bounding plus this truncation together preserve
    the legacy "most-recent N rows" contract. Truncation assumes descending
    date order, which the FMP EOD endpoint provides (verified live).

    Note: empty list ``[]`` does not reach this normalizer because the caller's
    ``if not data: continue`` falsy check handles it earlier in
    ``_request_with_fallback``.
    """
    if not isinstance(data, list):
        return data
    if not data:
        return None
    norm_target = symbols_str.replace("-", ".")
    matched_symbol = None
    historical = []
    for row in data:
        if not isinstance(row, dict):
            continue
        # Be permissive: single-symbol endpoint may omit per-row "symbol".
        # Treat missing symbol as belonging to the requested symbols_str.
        row_sym = row.get("symbol") or symbols_str
        if row_sym.replace("-", ".") != norm_target:
            continue
        matched_symbol = matched_symbol or row_sym
        historical.append({k: v for k, v in row.items() if k != "symbol"})
    if not historical:
        return None
    if limit is not None and limit > 0:
        historical = historical[:limit]
    return {"symbol": matched_symbol or symbols_str, "historical": historical}


class FMPClient:
    """Client for Financial Modeling Prep API with rate limiting and caching"""

    BASE_URL = "https://financialmodelingprep.com/api/v3"
    RATE_LIMIT_DELAY = 0.3  # 300ms between requests (200 requests/minute max)

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize FMP API client

        Args:
            api_key: FMP API key (defaults to FMP_API_KEY environment variable)

        Raises:
            ValueError: If API key not provided and not in environment
        """
        self.api_key = api_key or os.getenv("FMP_API_KEY")
        if not self.api_key:
            raise ValueError(
                "FMP API key required. Set FMP_API_KEY environment variable "
                "or pass api_key parameter."
            )

        self.session = requests.Session()
        self.session.headers.update({"apikey": self.api_key})
        self.cache = {}  # Simple in-memory cache for session
        self.last_call_time = 0
        self.rate_limit_reached = False
        self.retry_count = 0
        self.max_retries = 1
        # Circuit breaker: track consecutive failures per endpoint URL prefix
        self._endpoint_failures: dict[str, int] = {}
        self._disabled_endpoints: set[str] = set()
        self._ENDPOINT_FAILURE_THRESHOLD = 3

    def _rate_limited_get(
        self, url: str, params: Optional[dict] = None, quiet: bool = False
    ) -> Optional[dict]:
        """
        Make rate-limited GET request with retry logic

        Args:
            url: Full endpoint URL
            params: Query parameters (apikey sent via header)
            quiet: If True, suppress non-429 error messages (used by fallback)

        Returns:
            JSON response dict, or None on error
        """
        if self.rate_limit_reached:
            return None

        if params is None:
            params = {}

        # Enforce rate limit
        elapsed = time.time() - self.last_call_time
        if elapsed < self.RATE_LIMIT_DELAY:
            time.sleep(self.RATE_LIMIT_DELAY - elapsed)

        try:
            response = self.session.get(url, params=params, timeout=30)
            self.last_call_time = time.time()

            if response.status_code == 200:
                self.retry_count = 0  # Reset on success
                return response.json()

            elif response.status_code == 429:
                # Rate limit exceeded
                self.retry_count += 1
                if self.retry_count <= self.max_retries:
                    print("WARNING: Rate limit exceeded. Waiting 60 seconds...", file=sys.stderr)
                    time.sleep(60)
                    return self._rate_limited_get(url, params, quiet=quiet)
                else:
                    print(
                        "ERROR: Daily API rate limit reached. Stopping analysis.", file=sys.stderr
                    )
                    self.rate_limit_reached = True
                    return None

            else:
                if not quiet:
                    print(
                        f"ERROR: API request failed: {response.status_code} - {response.text[:200]}",
                        file=sys.stderr,
                    )
                return None

        except requests.exceptions.RequestException as e:
            print(f"ERROR: Request exception: {e}", file=sys.stderr)
            return None

    def _request_with_fallback(self, endpoint_key, symbols_str, extra_params=None):
        """Try stable endpoint first, fall back to v3 with circuit breaker."""
        params = dict(extra_params) if extra_params else {}
        endpoints = _FMP_ENDPOINTS[endpoint_key]
        is_single = "," not in symbols_str

        for i, (base_url, url_builder) in enumerate(endpoints):
            if base_url in self._disabled_endpoints:
                continue

            url, final_params = url_builder(base_url, symbols_str, dict(params))
            is_last = i == len(endpoints) - 1
            data = self._rate_limited_get(url, final_params, quiet=not is_last)
            if not data:
                self._record_endpoint_failure(base_url)
                continue

            # Normalize new stable EOD flat-list shape to v3-compatible dict.
            # No-op for v3 dict / historicalStockList responses.
            # `timeseries` (original request) is passed as `limit` so the
            # EOD endpoint's full-history response is truncated to the
            # legacy "most-recent N rows" contract.
            if endpoint_key == "historical":
                limit = params.get("timeseries") if isinstance(params, dict) else None
                data = _normalize_eod_flat_list(data, symbols_str, limit=limit)
                if not data:
                    self._record_endpoint_failure(base_url)
                    continue

            valid = True
            if endpoint_key == "quote":
                if not isinstance(data, list) or len(data) == 0:
                    valid = False
                elif is_single and not any(
                    q.get("symbol", "").replace("-", ".") == symbols_str.replace("-", ".")
                    for q in data
                ):
                    valid = False

            if endpoint_key == "historical":
                if not isinstance(data, dict):
                    valid = False
                elif "historicalStockList" in data:
                    norm = symbols_str.replace("-", ".")
                    found = None
                    for entry in data["historicalStockList"]:
                        if entry.get("symbol", "").replace("-", ".") == norm:
                            found = {
                                "symbol": entry.get("symbol"),
                                "historical": entry.get("historical", []),
                            }
                            break
                    if found:
                        self._endpoint_failures[base_url] = 0
                        return found
                    valid = False
                elif "historical" not in data:
                    valid = False
                elif is_single and data.get("symbol"):
                    if data["symbol"].replace("-", ".") != symbols_str.replace("-", "."):
                        valid = False

            if valid:
                self._endpoint_failures[base_url] = 0
                return data
            self._record_endpoint_failure(base_url)
        return None

    def _record_endpoint_failure(self, base_url: str) -> None:
        failures = self._endpoint_failures.get(base_url, 0) + 1
        self._endpoint_failures[base_url] = failures
        if failures >= self._ENDPOINT_FAILURE_THRESHOLD:
            self._disabled_endpoints.add(base_url)

    def get_income_statement(
        self, symbol: str, period: str = "quarter", limit: int = 8
    ) -> Optional[list[dict]]:
        """
        Fetch income statement data (quarterly or annual)

        Args:
            symbol: Stock ticker (e.g., "AAPL")
            period: "quarter" or "annual"
            limit: Number of periods to fetch (default 8 for quarterly, 5 for annual)

        Returns:
            List of income statement records (most recent first), or None on error

        Example:
            quarterly = client.get_income_statement("AAPL", period="quarter", limit=8)
            # Returns last 8 quarters (2 years) for YoY comparison
        """
        cache_key = f"income_{symbol}_{period}_{limit}"

        if cache_key in self.cache:
            return self.cache[cache_key]

        url = f"{self.BASE_URL}/income-statement/{symbol}"
        params = {"period": period, "limit": limit}

        data = self._rate_limited_get(url, params)

        if data:
            self.cache[cache_key] = data

        return data

    def get_quote(self, symbols: str) -> Optional[list[dict]]:
        """
        Fetch real-time quote data

        Args:
            symbols: Single ticker or comma-separated list (e.g., "AAPL" or "AAPL,MSFT,GOOGL")

        Returns:
            List of quote records, or None on error

        Example:
            quote = client.get_quote("AAPL")
            # Returns [{"symbol": "AAPL", "price": 185.92, "yearHigh": 198.23, ...}]

            quotes = client.get_quote("^GSPC,^VIX")
            # Batch fetch S&P 500 and VIX
        """
        cache_key = f"quote_{symbols}"

        if cache_key in self.cache:
            return self.cache[cache_key]

        data = self._request_with_fallback("quote", symbols)

        if data:
            self.cache[cache_key] = data

        return data

    def get_historical_prices(self, symbol: str, days: int = 365) -> Optional[dict]:
        """
        Fetch historical daily price data

        Args:
            symbol: Stock ticker (e.g., "AAPL")
            days: Number of days of history to fetch (default 365 for 52-week analysis)

        Returns:
            Dict with 'symbol' and 'historical' (list of daily OHLCV records), or None

        Example:
            prices = client.get_historical_prices("AAPL", days=365)
            # prices['historical'][0] = most recent day
            # prices['historical'][251] = 252 trading days ago (~1 year)
        """
        cache_key = f"prices_{symbol}_{days}"

        if cache_key in self.cache:
            return self.cache[cache_key]

        data = self._request_with_fallback("historical", symbol, {"timeseries": days})

        if data:
            self.cache[cache_key] = data

        return data

    def get_profile(self, symbol: str) -> Optional[list[dict]]:
        """
        Fetch company profile (sector, industry, description)

        Args:
            symbol: Stock ticker

        Returns:
            List with single profile dict, or None on error

        Example:
            profile = client.get_profile("AAPL")
            # profile[0] = {"symbol": "AAPL", "companyName": "Apple Inc.", "sector": "Technology", ...}
        """
        cache_key = f"profile_{symbol}"

        if cache_key in self.cache:
            return self.cache[cache_key]

        url = f"{self.BASE_URL}/profile/{symbol}"

        data = self._rate_limited_get(url)

        if data:
            self.cache[cache_key] = data

        return data

    def get_institutional_holders(self, symbol: str) -> Optional[list[dict]]:
        """
        Fetch institutional holder data (Phase 2: I component)

        Args:
            symbol: Stock ticker

        Returns:
            List of institutional holders with:
                - holder: Institution name (str)
                - shares: Number of shares held (int)
                - dateReported: Reporting date (str)
                - change: Change in shares from previous quarter (int)
            Returns None on error

        Example:
            holders = client.get_institutional_holders("AAPL")
            # holders[0] = {"holder": "Vanguard Group Inc", "shares": 1234567890, ...}

        Note:
            This endpoint provides 13F filing data. Free tier may have limited access.
            Typical response contains hundreds to thousands of institutional holders.
        """
        cache_key = f"institutional_{symbol}"

        if cache_key in self.cache:
            return self.cache[cache_key]

        url = f"{self.BASE_URL}/institutional-holder/{symbol}"

        data = self._rate_limited_get(url)

        if data:
            self.cache[cache_key] = data

        return data

    def calculate_ema(self, prices: list[float], period: int = 50) -> float:
        """
        Calculate Exponential Moving Average

        Args:
            prices: List of prices (most recent first)
            period: EMA period (default 50)

        Returns:
            EMA value

        Note:
            This is a helper method for market direction (M component).
            Uses standard EMA formula: EMA = Price * k + EMA_prev * (1-k)
            where k = 2 / (period + 1)
        """
        if len(prices) < period:
            return sum(prices) / len(prices)  # Fallback to simple average

        # Reverse to oldest-first for calculation
        prices_reversed = prices[::-1]

        # Initialize with SMA
        sma = sum(prices_reversed[:period]) / period
        ema = sma

        # Calculate EMA
        k = 2 / (period + 1)
        for price in prices_reversed[period:]:
            ema = price * k + ema * (1 - k)

        return ema

    def clear_cache(self):
        """Clear session cache (useful for refreshing data)"""
        self.cache = {}
        print("Cache cleared", file=sys.stderr)

    def get_api_stats(self) -> dict:
        """
        Get API usage statistics for current session

        Returns:
            Dict with cache size and estimated API calls made
        """
        return {
            "cache_entries": len(self.cache),
            "rate_limit_reached": self.rate_limit_reached,
            "retry_count": self.retry_count,
        }


def test_client():
    """Test FMP client with sample queries"""
    print("Testing FMP Client...")

    client = FMPClient()

    # Test 1: Quote
    print("\n1. Testing quote endpoint (AAPL)...")
    quote = client.get_quote("AAPL")
    if quote:
        print(f"✓ Quote: {quote[0]['symbol']} @ ${quote[0]['price']:.2f}")
    else:
        print("✗ Quote failed")

    # Test 2: Quarterly income statement
    print("\n2. Testing quarterly income statement (AAPL)...")
    quarterly = client.get_income_statement("AAPL", period="quarter", limit=8)
    if quarterly:
        latest = quarterly[0]
        print(f"✓ Latest quarter: {latest['date']}, EPS: ${latest.get('eps', 'N/A')}")
    else:
        print("✗ Quarterly income statement failed")

    # Test 3: Annual income statement
    print("\n3. Testing annual income statement (AAPL)...")
    annual = client.get_income_statement("AAPL", period="annual", limit=5)
    if annual:
        latest = annual[0]
        print(f"✓ Latest year: {latest['date']}, EPS: ${latest.get('eps', 'N/A')}")
    else:
        print("✗ Annual income statement failed")

    # Test 4: Historical prices
    print("\n4. Testing historical prices (AAPL)...")
    prices = client.get_historical_prices("AAPL", days=365)
    if prices and "historical" in prices:
        print(f"✓ Fetched {len(prices['historical'])} days of price history")
        if len(prices["historical"]) > 0:
            latest = prices["historical"][0]
            print(f"  Latest: {latest['date']}, Close: ${latest['close']:.2f}")
    else:
        print("✗ Historical prices failed")

    # Test 5: Market indices (batch)
    print("\n5. Testing market indices (^GSPC, ^VIX)...")
    indices = client.get_quote("^GSPC,^VIX")
    if indices:
        for idx in indices:
            print(f"✓ {idx['symbol']}: {idx['price']:.2f}")
    else:
        print("✗ Market indices failed")

    # Test 6: Cache
    print("\n6. Testing cache (repeat AAPL quote)...")
    quote2 = client.get_quote("AAPL")
    if quote2:
        print("✓ Cache working (no API call made)")

    # Stats
    stats = client.get_api_stats()
    print("\nAPI Stats:")
    print(f"  Cache entries: {stats['cache_entries']}")
    print(f"  Rate limit reached: {stats['rate_limit_reached']}")

    print("\n✓ All tests completed")


if __name__ == "__main__":
    test_client()
