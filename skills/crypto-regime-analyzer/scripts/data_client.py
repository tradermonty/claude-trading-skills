#!/usr/bin/env python3
"""
Crypto Regime Analyzer - Data Client

Fetches all required inputs from free, keyless public endpoints:

  CoinGecko public API (no key):
    /global                    -> current BTC dominance
    /coins/markets             -> top-N universe by market cap
    /coins/{id}/market_chart   -> daily close history per coin

  Binance USDT-M futures public API (no key):
    /fapi/v1/premiumIndex      -> latest funding rate per perp

Dominance history note: CoinGecko's free tier only exposes *current*
dominance, so this client maintains its own dominance history in the
cache directory (one observation per run-day). The dominance component
reports data_available=False until >= 31 daily observations accumulate,
and the scorer redistributes its weight in the meantime. Seed history
faster via --input-json if desired.

Rate limits: CoinGecko free tier allows roughly 5-15 req/min. History
fetches are throttled (REQUEST_DELAY_S) and cached per UTC day, so the
first run of the day is slow (~2-4 min at top_n=20) and re-runs are
instant.

Offline mode: load_snapshot_from_json() accepts a snapshot file matching
the schema in references/crypto_regime_methodology.md so the analyzer
runs with zero network access.
"""

import json
import math
import os
import time
from datetime import datetime, timedelta, timezone
from hashlib import sha256

from numeric_utils import MAX_ABS_FUNDING_RATE

try:
    import requests
except ImportError:  # pragma: no cover - exercised only without requests
    requests = None

COINGECKO_BASE = "https://api.coingecko.com/api/v3"
BINANCE_FAPI_BASE = "https://fapi.binance.com"
REQUEST_DELAY_S = 8.0
MAX_RETRIES = 4
BACKOFF_BASE_S = 15
HISTORY_DAYS = 365  # public API cap; auto-daily granularity above 90 days
STABLECOIN_IDS = {
    "tether",
    "usd-coin",
    "dai",
    "first-digital-usd",
    "ethena-usde",
    "usds",
    "paypal-usd",
    "true-usd",
    "frax",
    "binance-usd",
}
WRAPPED_OR_STAKED_IDS = {
    "wrapped-bitcoin",
    "wrapped-steth",
    "staked-ether",
    "weth",
    "coinbase-wrapped-btc",
    "wrapped-eeth",
    "rocket-pool-eth",
    "wrapped-beacon-eth",
    "susds",
}
NON_CRYPTO_BETA_IDS = {
    "figure-heloc",
    "blackrock-usd-institutional-digital-liquidity-fund",
}


class DataClient:
    """Fetch + cache market data for the crypto regime analysis."""

    def __init__(self, cache_dir: str, top_n: int = 20, quiet: bool = False):
        self.cache_dir = cache_dir
        self.top_n = top_n
        self.quiet = quiet
        os.makedirs(cache_dir, exist_ok=True)

    # ------------------------------------------------------------------
    # Cache helpers
    # ------------------------------------------------------------------
    def _cache_path(self, name: str) -> str:
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return os.path.join(self.cache_dir, f"{day}_{name}.json")

    def _cached(self, name: str):
        path = self._cache_path(name)
        if os.path.exists(path):
            with open(path) as f:
                return json.load(f)
        return None

    def _store(self, name: str, data):
        with open(self._cache_path(name), "w") as f:
            json.dump(data, f)

    def _get(self, url: str, params: dict = None):
        """GET with 429-aware exponential backoff (respects Retry-After)."""
        if requests is None:
            raise RuntimeError("The 'requests' library is required for live fetches")
        resp = None
        for attempt in range(MAX_RETRIES):
            resp = requests.get(url, params=params or {}, timeout=30)
            if resp.status_code != 429:
                resp.raise_for_status()
                return resp.json()
            retry_after = resp.headers.get("Retry-After", "")
            delay = (
                float(retry_after)
                if retry_after.replace(".", "", 1).isdigit()
                else BACKOFF_BASE_S * (2**attempt)
            )
            self._log(f"  rate limited (429); backing off {delay:.0f}s...")
            time.sleep(delay)
        resp.raise_for_status()

    def _log(self, msg: str):
        if not self.quiet:
            print(msg)

    # ------------------------------------------------------------------
    # Fetchers
    # ------------------------------------------------------------------
    def fetch_universe(self) -> list:
        """Top-N non-stable, non-wrapped coins by market cap."""
        cache_key = f"universe_top{self.top_n}"
        cached = self._cached(cache_key)
        if cached:
            return cached
        raw = self._get(
            f"{COINGECKO_BASE}/coins/markets",
            {
                "vs_currency": "usd",
                "order": "market_cap_desc",
                "per_page": self.top_n
                + len(STABLECOIN_IDS)
                + len(WRAPPED_OR_STAKED_IDS)
                + len(NON_CRYPTO_BETA_IDS),
                "page": 1,
                "sparkline": "false",
            },
        )
        excluded = STABLECOIN_IDS | WRAPPED_OR_STAKED_IDS | NON_CRYPTO_BETA_IDS
        universe = [
            {"id": c["id"], "symbol": c["symbol"].upper()} for c in raw if c["id"] not in excluded
        ][: self.top_n]
        self._store(cache_key, universe)
        return universe

    def fetch_history(self, coin_id: str) -> list:
        """Daily closes (oldest -> newest) for one coin."""
        cached = self._cached(f"hist_{coin_id}")
        if cached:
            return cached
        raw = self._get(
            f"{COINGECKO_BASE}/coins/{coin_id}/market_chart",
            {"vs_currency": "usd", "days": HISTORY_DAYS},
        )
        closes = [p[1] for p in raw.get("prices", [])]
        self._store(f"hist_{coin_id}", closes)
        time.sleep(REQUEST_DELAY_S)
        return closes

    def fetch_dominance(self) -> float:
        """Current BTC dominance % and append to local history file."""
        cached = self._cached("dominance_now")
        if cached is not None:
            return cached
        raw = self._get(f"{COINGECKO_BASE}/global")
        dom = raw["data"]["market_cap_percentage"]["btc"]
        self._store("dominance_now", dom)
        self._append_dominance_history(dom)
        return dom

    def _dominance_history_path(self) -> str:
        return os.path.join(self.cache_dir, "dominance_history.json")

    def _append_dominance_history(self, dom: float):
        path = self._dominance_history_path()
        history = {}
        if os.path.exists(path):
            with open(path) as f:
                history = json.load(f)
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        history[day] = dom
        with open(path, "w") as f:
            json.dump(history, f, indent=2)

    def load_dominance_series(self) -> list:
        """Return a contiguous 31-calendar-day dominance window, oldest first."""
        path = self._dominance_history_path()
        if not os.path.exists(path):
            return []
        with open(path) as f:
            history = json.load(f)
        today = datetime.now(timezone.utc).date()
        required_days = [today - timedelta(days=offset) for offset in range(30, -1, -1)]
        required_keys = [day.isoformat() for day in required_days]
        if any(key not in history for key in required_keys):
            return []
        return [history[key] for key in required_keys]

    @staticmethod
    def _funding_cache_key(symbols: list) -> str:
        cohort = ",".join(sorted(set(symbols)))
        digest = sha256(cohort.encode()).hexdigest()[:16]
        return f"funding_{digest}"

    def fetch_funding(self, symbols: list) -> dict:
        """Latest 8h funding rate per USDT perp symbol."""
        cache_key = self._funding_cache_key(symbols)
        cached = self._cached(cache_key)
        if cached:
            return cached
        funding = {}
        try:
            raw = self._get(f"{BINANCE_FAPI_BASE}/fapi/v1/premiumIndex")
            by_symbol = {r["symbol"]: r for r in raw}
            for sym in symbols:
                perp = f"{sym}USDT"
                if perp in by_symbol:
                    funding[perp] = float(by_symbol[perp]["lastFundingRate"])
        except Exception as exc:  # funding is best-effort
            self._log(f"  WARN: funding fetch failed ({exc}); component will be skipped")
        self._store(cache_key, funding)
        return funding

    # ------------------------------------------------------------------
    # Snapshot assembly
    # ------------------------------------------------------------------
    def build_snapshot(self) -> dict:
        """Fetch everything and return the analyzer input snapshot."""
        self._log(f"Fetching top-{self.top_n} universe from CoinGecko...")
        universe = self.fetch_universe()

        series = {}
        for i, coin in enumerate(universe, 1):
            self._log(f"  [{i}/{len(universe)}] history: {coin['symbol']}")
            try:
                closes = self.fetch_history(coin["id"])
                _validate_price_series(coin["symbol"], closes)
                series[coin["symbol"]] = closes
            except Exception as exc:
                self._log(f"  WARN: {coin['symbol']} history failed ({exc}); skipping coin")

        self._log("Fetching BTC dominance...")
        try:
            self.fetch_dominance()
            dominance_series = self.load_dominance_series()
            _validate_dominance_series(dominance_series)
        except Exception as exc:
            self._log(f"  WARN: dominance fetch failed ({exc}); component will be skipped")
            dominance_series = []

        self._log("Fetching Binance funding rates...")
        raw_funding = self.fetch_funding([c["symbol"] for c in universe[:10]])
        funding = {}
        if not isinstance(raw_funding, dict):
            self._log("  WARN: funding response was not an object; component will be skipped")
        else:
            for symbol, rate in raw_funding.items():
                try:
                    _validate_funding_rate(symbol, rate)
                    funding[symbol] = rate
                except ValueError as exc:
                    self._log(f"  WARN: invalid funding row skipped ({exc})")

        return validate_snapshot(
            {
                "as_of": datetime.now(timezone.utc).isoformat(),
                "series": series,
                "dominance_series": dominance_series,
                "funding": funding,
            }
        )


def _require_finite_number(value, path: str, *, positive: bool = False) -> None:
    """Reject bools, non-numeric values, and non-finite market data."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"Snapshot '{path}' must be a number")
    if not math.isfinite(value):
        raise ValueError(f"Snapshot '{path}' must be finite")
    if positive and value <= 0:
        raise ValueError(f"Snapshot '{path}' must be positive")


def _validate_price_series(symbol, closes) -> None:
    if not isinstance(symbol, str) or not symbol.strip():
        raise ValueError("Snapshot 'series' keys must be non-empty strings")
    if not isinstance(closes, list) or not closes:
        raise ValueError(f"Snapshot 'series.{symbol}' must be a non-empty array")
    for index, close in enumerate(closes):
        _require_finite_number(close, f"series.{symbol}[{index}]", positive=True)


def _validate_dominance_series(dominance_series) -> None:
    if not isinstance(dominance_series, list):
        raise ValueError("Snapshot 'dominance_series' must be an array")
    for index, dominance in enumerate(dominance_series):
        _require_finite_number(dominance, f"dominance_series[{index}]", positive=True)
        if dominance > 100:
            raise ValueError(f"Snapshot 'dominance_series[{index}]' must be <= 100")


def _validate_funding_rate(symbol, rate) -> None:
    if not isinstance(symbol, str) or not symbol.strip():
        raise ValueError("Snapshot 'funding' keys must be non-empty strings")
    _require_finite_number(rate, f"funding.{symbol}")
    if abs(rate) > MAX_ABS_FUNDING_RATE:
        raise ValueError(
            f"Snapshot 'funding.{symbol}' must be between "
            f"-{MAX_ABS_FUNDING_RATE:g} and {MAX_ABS_FUNDING_RATE:g}"
        )


def validate_snapshot(snapshot: dict) -> dict:
    """Validate snapshot structure and numeric market-data boundaries."""
    if not isinstance(snapshot, dict):
        raise ValueError("Snapshot must be a JSON object")

    for key in ("series", "dominance_series", "funding"):
        if key not in snapshot:
            raise ValueError(f"Snapshot missing required key: '{key}'")

    series = snapshot["series"]
    if not isinstance(series, dict):
        raise ValueError("Snapshot 'series' must be an object")
    if "BTC" not in series:
        raise ValueError("Snapshot 'series' must include a 'BTC' entry")
    for symbol, closes in series.items():
        _validate_price_series(symbol, closes)

    dominance_series = snapshot["dominance_series"]
    _validate_dominance_series(dominance_series)

    funding = snapshot["funding"]
    if not isinstance(funding, dict):
        raise ValueError("Snapshot 'funding' must be an object")
    for symbol, rate in funding.items():
        _validate_funding_rate(symbol, rate)

    return snapshot


def load_snapshot_from_json(path: str) -> dict:
    """Offline path: load a pre-built snapshot (schema in references/)."""
    with open(path) as f:
        snapshot = json.load(f)
    return validate_snapshot(snapshot)
