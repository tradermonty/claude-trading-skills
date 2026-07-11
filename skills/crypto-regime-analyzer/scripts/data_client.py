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
import os
import time
from datetime import datetime, timezone

try:
    import requests
except ImportError:  # pragma: no cover - exercised only without requests
    requests = None

COINGECKO_BASE = "https://api.coingecko.com/api/v3"
BINANCE_FAPI_BASE = "https://fapi.binance.com"
REQUEST_DELAY_S = 6.5
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
        if requests is None:
            raise RuntimeError("The 'requests' library is required for live fetches")
        resp = requests.get(url, params=params or {}, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def _log(self, msg: str):
        if not self.quiet:
            print(msg)

    # ------------------------------------------------------------------
    # Fetchers
    # ------------------------------------------------------------------
    def fetch_universe(self) -> list:
        """Top-N non-stable, non-wrapped coins by market cap."""
        cached = self._cached("universe")
        if cached:
            return cached
        raw = self._get(
            f"{COINGECKO_BASE}/coins/markets",
            {
                "vs_currency": "usd",
                "order": "market_cap_desc",
                "per_page": self.top_n + len(STABLECOIN_IDS) + len(WRAPPED_OR_STAKED_IDS),
                "page": 1,
                "sparkline": "false",
            },
        )
        excluded = STABLECOIN_IDS | WRAPPED_OR_STAKED_IDS
        universe = [
            {"id": c["id"], "symbol": c["symbol"].upper()} for c in raw if c["id"] not in excluded
        ][: self.top_n]
        self._store("universe", universe)
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
        """Accumulated daily dominance history, oldest -> newest."""
        path = self._dominance_history_path()
        if not os.path.exists(path):
            return []
        with open(path) as f:
            history = json.load(f)
        return [history[k] for k in sorted(history.keys())]

    def fetch_funding(self, symbols: list) -> dict:
        """Latest 8h funding rate per USDT perp symbol."""
        cached = self._cached("funding")
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
        self._store("funding", funding)
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
            series[coin["symbol"]] = self.fetch_history(coin["id"])

        self._log("Fetching BTC dominance...")
        self.fetch_dominance()
        dominance_series = self.load_dominance_series()

        self._log("Fetching Binance funding rates...")
        funding = self.fetch_funding([c["symbol"] for c in universe[:10]])

        return {
            "as_of": datetime.now(timezone.utc).isoformat(),
            "series": series,
            "dominance_series": dominance_series,
            "funding": funding,
        }


def load_snapshot_from_json(path: str) -> dict:
    """Offline path: load a pre-built snapshot (schema in references/)."""
    with open(path) as f:
        snapshot = json.load(f)
    for key in ("series", "dominance_series", "funding"):
        if key not in snapshot:
            raise ValueError(f"Snapshot missing required key: '{key}'")
    if "BTC" not in snapshot["series"]:
        raise ValueError("Snapshot 'series' must include a 'BTC' entry")
    return snapshot
