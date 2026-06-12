#!/usr/bin/env python3
"""
FMP API Client for PEAD Screener

Provides rate-limited access to Financial Modeling Prep API endpoints
for PEAD (Post-Earnings Announcement Drift) screening.

Features:
- Rate limiting (0.3s between requests)
- Automatic retry on 429 errors
- Session caching for duplicate requests
- API call budget enforcement
- Batch company profile support
- Earnings calendar and historical price fetching
"""

import csv
import io
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

try:
    from _fmp_compat import v3_to_stable
except ModuleNotFoundError:  # loaded by file path (e.g. repo-level contract tests)
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from _fmp_compat import v3_to_stable

# --- FMP endpoint fallback: stable (new users) -> v3 (legacy users) ---


def _stable_hist_url(base, symbols_str, params):
    """stable/historical-price-eod/full?symbol=SPY&from=...&to=..."""
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
    """api/v3/historical-price-full/SPY?timeseries=90"""
    return f"{base}/{symbols_str}", params


_FMP_ENDPOINTS = {
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


class ApiCallBudgetExceeded(Exception):
    """Raised when the API call budget has been exhausted."""

    pass


class FMPClient:
    """Client for Financial Modeling Prep API with rate limiting, caching, and budget control"""

    BASE_URL = "https://financialmodelingprep.com/api/v3"
    STABLE_URL = "https://financialmodelingprep.com/stable"
    RATE_LIMIT_DELAY = 0.3  # 300ms between requests

    _ENDPOINT_FAILURE_THRESHOLD = 3  # disable endpoint after N consecutive failures
    _PROFILE_BULK_MAX_PARTS = 30  # safety cap on profile-bulk pagination

    def __init__(self, api_key: Optional[str] = None, max_api_calls: int = 200):
        self.api_key = api_key or os.getenv("FMP_API_KEY")
        if not self.api_key:
            raise ValueError(
                "FMP API key required. Set FMP_API_KEY environment variable "
                "or pass api_key parameter."
            )
        self.session = requests.Session()
        self.session.headers.update({"apikey": self.api_key})
        self.cache = {}
        self.last_call_time = 0
        self.rate_limit_reached = False
        self.retry_count = 0
        self.max_retries = 1
        self.api_calls_made = 0
        self.max_api_calls = max_api_calls
        # Circuit breaker: track consecutive failures per endpoint URL prefix
        self._endpoint_failures: dict[str, int] = {}
        self._disabled_endpoints: set[str] = set()
        # Lazily-loaded {SYMBOL: profile} map from /stable/profile-bulk
        self._profile_bulk: Optional[dict[str, dict]] = None

    def _rate_limited_get(
        self, url: str, params: Optional[dict] = None, quiet: bool = False, raw: bool = False
    ):
        """Make a rate-limited GET request with budget enforcement.

        Returns parsed JSON by default, or the raw response text when
        ``raw=True`` (used for the CSV profile-bulk endpoint).

        Raises:
            ApiCallBudgetExceeded: When api_calls_made >= max_api_calls
        """
        if self.api_calls_made >= self.max_api_calls:
            raise ApiCallBudgetExceeded(
                f"API call budget exhausted: {self.api_calls_made}/{self.max_api_calls} calls used"
            )

        if self.rate_limit_reached:
            return None

        if params is None:
            params = {}

        elapsed = time.time() - self.last_call_time
        if elapsed < self.RATE_LIMIT_DELAY:
            time.sleep(self.RATE_LIMIT_DELAY - elapsed)

        try:
            response = self.session.get(url, params=params, timeout=30)
            self.last_call_time = time.time()
            self.api_calls_made += 1

            if response.status_code == 200:
                self.retry_count = 0
                return response.text if raw else response.json()
            elif response.status_code == 429:
                self.retry_count += 1
                if self.retry_count <= self.max_retries:
                    print("WARNING: Rate limit exceeded. Waiting 60 seconds...", file=sys.stderr)
                    time.sleep(60)
                    return self._rate_limited_get(url, params, quiet=quiet, raw=raw)
                else:
                    print("ERROR: Daily API rate limit reached.", file=sys.stderr)
                    self.rate_limit_reached = True
                    return None
            else:
                if not quiet:
                    print(
                        f"ERROR: API request failed: {response.status_code} - {response.text[:200]}",
                        file=sys.stderr,
                    )
                return None
        except requests.exceptions.Timeout:
            print("ERROR: Request timed out", file=sys.stderr)
            return None
        except requests.exceptions.RequestException as e:
            print(f"ERROR: Request exception: {e}", file=sys.stderr)
            return None

    def _request_with_fallback(self, endpoint_key, symbols_str, extra_params=None):
        """Try stable endpoint first, fall back to v3 for legacy users.

        Returns parsed JSON in v3-compatible shape, or None if all fail.
        Non-last endpoints use quiet=True to suppress expected 403 stderr.
        """
        params = dict(extra_params) if extra_params else {}
        endpoints = _FMP_ENDPOINTS[endpoint_key]
        is_single = "," not in symbols_str

        for i, (base_url, url_builder) in enumerate(endpoints):
            # Circuit breaker: skip endpoints with too many consecutive failures
            if base_url in self._disabled_endpoints:
                continue

            url, final_params = url_builder(base_url, symbols_str, dict(params))
            is_last = i == len(endpoints) - 1
            data = self._rate_limited_get(url, final_params, quiet=not is_last)
            if not data:  # falsy (None, [], {}) -- try next endpoint
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

            # Shape validation: reject truthy-but-wrong-shape responses
            valid = True
            if endpoint_key == "historical":
                if not isinstance(data, dict):
                    valid = False
                elif "historicalStockList" in data:
                    # stable batch format -> v3 single format (exact match only)
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
        """Track consecutive failures and disable endpoint after threshold."""
        failures = self._endpoint_failures.get(base_url, 0) + 1
        self._endpoint_failures[base_url] = failures
        if failures >= self._ENDPOINT_FAILURE_THRESHOLD:
            self._disabled_endpoints.add(base_url)

    def get_earnings_calendar(self, from_date: str, to_date: str) -> Optional[list[dict]]:
        """Fetch earnings calendar for a date range.

        Args:
            from_date: Start date in YYYY-MM-DD format
            to_date: End date in YYYY-MM-DD format

        Returns:
            List of earnings event dicts or None on failure.
            Each dict contains: date, symbol, eps, epsEstimated, revenue,
            revenueEstimated, time (bmo/amc)
        """
        cache_key = f"earnings_{from_date}_{to_date}"
        if cache_key in self.cache:
            return self.cache[cache_key]

        # Hardcoded v3 URL bypasses the stable→v3 fallback list; rewrite here.
        url, params = v3_to_stable(
            f"{self.BASE_URL}/earning_calendar", {"from": from_date, "to": to_date}
        )
        data = self._rate_limited_get(url, params)
        if data:
            self.cache[cache_key] = data
        return data

    @staticmethod
    def _to_number(value):
        """Coerce a CSV/string numeric field to float; None/'' -> 0."""
        if value in (None, ""):
            return 0
        try:
            return float(value)
        except (TypeError, ValueError):
            return value

    @classmethod
    def _v3_compat_profile(cls, profile: dict) -> dict:
        """Add v3-compatible aliases so the screener's mktCap filter keeps working.

        /stable/profile (and profile-bulk) renamed v3 fields: marketCap ->
        mktCap, exchange -> exchangeShortName. screen_pead.py filters on
        ``mktCap``, so without the alias market_cap reads 0 on a /stable key and
        the market-cap gate drops every candidate. Numeric fields from the CSV
        bulk endpoint arrive as strings and are coerced here.
        """
        if "mktCap" not in profile and "marketCap" in profile:
            profile["mktCap"] = profile["marketCap"]
        if "exchangeShortName" not in profile and "exchange" in profile:
            profile["exchangeShortName"] = profile["exchange"]
        for key in ("mktCap", "marketCap", "price"):
            if key in profile:
                profile[key] = cls._to_number(profile[key])
        return profile

    def _load_profile_bulk(self) -> dict[str, dict]:
        """Download and cache the full {SYMBOL: profile} map from profile-bulk.

        /stable has no batch profile endpoint (comma-batched ?symbol= silently
        returns []), so a global symbol list is served from FMP's bulk CSV dump
        instead. The dump is paginated by ``part``; parts are fetched until one
        comes back empty/non-CSV (a handful of calls), then cached for the
        session. Returns {} when the bulk endpoint is unavailable (e.g. a legacy
        key), letting the caller fall back to the per-symbol profile endpoint.
        """
        if self._profile_bulk is not None:
            return self._profile_bulk

        table: dict[str, dict] = {}
        for part in range(self._PROFILE_BULK_MAX_PARTS):
            text = self._rate_limited_get(
                f"{self.STABLE_URL}/profile-bulk", {"part": part}, quiet=True, raw=True
            )
            if not text or not text.lstrip().startswith('"symbol"'):
                break  # no more parts (empty body or an error/JSON message)
            added = 0
            for row in csv.DictReader(io.StringIO(text)):
                sym = (row.get("symbol") or "").strip().upper()
                if sym:
                    table[sym] = self._v3_compat_profile(dict(row))
                    added += 1
            if added == 0:
                break
        self._profile_bulk = table
        return table

    def _get_company_profiles_per_symbol(self, symbols: list[str]) -> dict[str, dict]:
        """Per-symbol /stable/profile lookups (fallback when bulk is unavailable).

        This is #139's per-symbol path, with v3-compatible field aliasing applied
        so screen_pead.py's mktCap filter works on /stable keys.
        """
        results = {}
        for symbol in symbols:
            cache_key = f"profile_{symbol}"
            if cache_key in self.cache:
                cached = self.cache[cache_key]
                if isinstance(cached, dict):
                    results[symbol] = cached
                continue

            # Hardcoded v3 URL bypasses the stable→v3 fallback list; rewrite here.
            url, params = v3_to_stable(f"{self.BASE_URL}/profile/{symbol}")
            data = self._rate_limited_get(url, params)
            if data and isinstance(data, list) and data:
                profile = data[0]
                if isinstance(profile, dict) and "symbol" in profile:
                    profile = self._v3_compat_profile(profile)
                    self.cache[cache_key] = profile
                    results[profile["symbol"]] = profile
        return results

    def get_company_profiles(self, symbols: list[str]) -> dict[str, dict]:
        """Map ticker symbols to company profile data.

        /stable has no batch profile endpoint, so the full profile universe is
        downloaded once via /stable/profile-bulk (a handful of cached CSV calls)
        and the requested symbols are looked up locally — far cheaper than one
        request per symbol across a large earnings-calendar symbol set. Falls
        back to the per-symbol profile endpoint (#139's path) for legacy keys
        where profile-bulk is unavailable.

        Args:
            symbols: List of stock symbols

        Returns:
            Dict mapping symbol -> profile dict (with v3-compatible ``mktCap``).
        """
        bulk = self._load_profile_bulk()
        if bulk:
            results = {}
            for symbol in symbols:
                profile = bulk.get(symbol.strip().upper())
                if profile:
                    results[symbol] = profile
            if results:
                return results

        # Legacy fallback (e.g. a pre-cutover key where profile-bulk is unavailable)
        return self._get_company_profiles_per_symbol(symbols)

    def get_historical_prices(self, symbol: str, days: int = 90) -> Optional[dict]:
        """Fetch historical daily OHLCV data.

        Args:
            symbol: Stock symbol
            days: Number of trading days to fetch

        Returns:
            Dict with 'symbol' and 'historical' keys, where 'historical' is a
            list of price dicts (most-recent-first) with: date, open, high, low,
            close, adjClose, volume
        """
        cache_key = f"prices_{symbol}_{days}"
        if cache_key in self.cache:
            return self.cache[cache_key]

        data = self._request_with_fallback("historical", symbol, {"timeseries": days})
        if data:
            self.cache[cache_key] = data
        return data

    def get_api_stats(self) -> dict:
        """Return API usage statistics."""
        return {
            "cache_entries": len(self.cache),
            "api_calls_made": self.api_calls_made,
            "max_api_calls": self.max_api_calls,
            "rate_limit_reached": self.rate_limit_reached,
            "budget_remaining": max(0, self.max_api_calls - self.api_calls_made),
        }
