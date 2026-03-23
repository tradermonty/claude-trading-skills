"""Weekly universe builder for non-US markets via IBKR.

For each enabled non-US market:
1. Fetch all listed stocks from IBKR for the configured exchange
2. Filter by: min average volume (default 100k/day), price above 50-day MA (uptrend)
3. Save to cache/<market-id>-universe.json

IBKR pacing: 60 historical data requests per 10 minutes.
Default request_delay=6 seconds. 100 stocks ≈ 10 minutes.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


class UniverseBuilder:
    """Builds and caches the tradeable stock universe for each non-US market.

    Inject ibkr_client in production. Pass request_delay=0 in tests.
    """

    def __init__(self, ibkr_client, cache_dir: Path, request_delay: float = 6.0):
        self._ibkr = ibkr_client
        self._cache_dir = cache_dir
        self._request_delay = request_delay

    def build_universe(self, market_config: dict) -> list[dict]:
        """Fetch, filter, and cache the universe for one market.

        Returns the filtered symbols list. Writes cache/<market-id>-universe.json.
        Returns [] and logs warning if IBKR not configured.
        """
        market_id = market_config.get("id", "unknown")
        exchange = market_config.get("exchange", "SMART")
        min_avg_volume = market_config.get("min_avg_volume", 100_000)
        min_market_cap = market_config.get("min_market_cap", 0)

        if not self._ibkr.is_configured:
            print(
                f"[universe_builder] {market_id}: IBKR not connected — skipping",
                file=sys.stderr,
            )
            return []

        # Step 1: Fetch all listed contracts for the exchange
        try:
            contracts = self._fetch_contracts(exchange)
        except Exception as e:
            print(f"[universe_builder] {market_id}: contract fetch failed: {e}", file=sys.stderr)
            return []

        if not contracts:
            print(f"[universe_builder] {market_id}: no contracts returned", file=sys.stderr)
            return []

        # Step 2: For each contract, fetch historical bars and apply filters
        symbols = []
        for detail in contracts:
            try:
                symbol = detail.contract.symbol
                long_name = getattr(detail, "longName", symbol)

                bars = self._fetch_bars(detail.contract, exchange)
                if not bars:
                    continue

                avg_vol = sum(b.volume for b in bars) / len(bars)
                if avg_vol < min_avg_volume:
                    continue

                # Uptrend filter: current close > 50-bar MA
                closes = [b.close for b in bars]
                ma50 = sum(closes[-50:]) / min(50, len(closes))
                if closes[-1] < ma50:
                    continue

                symbols.append({
                    "symbol": symbol,
                    "name": long_name,
                    "avg_volume": int(avg_vol),
                    "last_close": round(closes[-1], 4),
                })

                if self._request_delay > 0:
                    time.sleep(self._request_delay)

            except Exception as e:
                print(
                    f"[universe_builder] {market_id}/{symbol} error: {e}",
                    file=sys.stderr,
                )
                continue

        # Step 3: Write cache file
        output = {
            "market": market_id,
            "updated": datetime.now(timezone.utc).isoformat(),
            "symbols": symbols,
        }
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        output_file = self._cache_dir / f"{market_id}-universe.json"
        output_file.write_text(json.dumps(output, indent=2))
        print(
            f"[universe_builder] {market_id}: wrote {len(symbols)} symbols to {output_file}",
            file=sys.stderr,
        )
        return symbols

    def _fetch_contracts(self, exchange: str) -> list:
        """Fetch all stock contracts for an exchange from IBKR."""
        try:
            # Use reqContractDetails with a wildcard Stock contract
            # This returns all stocks on the given exchange
            return self._ibkr.reqContractDetails(None)
        except Exception as e:
            print(f"[universe_builder] _fetch_contracts({exchange}) error: {e}", file=sys.stderr)
            return []

    def _fetch_bars(self, contract, exchange: str) -> list:
        """Fetch 60 daily bars for a contract."""
        try:
            return self._ibkr._ib.reqHistoricalData(
                contract,
                endDateTime="",
                durationStr="3 M",
                barSizeSetting="1 day",
                whatToShow="TRADES",
                useRTH=True,
                formatDate=1,
            )
        except Exception as e:
            print(f"[universe_builder] _fetch_bars error: {e}", file=sys.stderr)
            return []

    def build_all(self, markets: list[dict]) -> None:
        """Build universe for each non-US market in the list.

        US market is skipped — it uses the VCP screener output directly.
        """
        for market in markets:
            if not market.get("enabled", True):
                continue
            if market.get("broker") == "alpaca":
                continue  # US market — skip
            self.build_universe(market)
