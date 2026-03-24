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

import requests
try:
    from finvizfinance.screener.overview import Overview
except ImportError:
    Overview = None  # type: ignore

import sys as _sys
_fmp_scripts = str(Path(__file__).resolve().parents[2] / "skills/vcp-screener/scripts")
if _fmp_scripts not in _sys.path:
    _sys.path.insert(0, _fmp_scripts)
try:
    from fmp_client import FMPClient
except ImportError:
    FMPClient = None  # type: ignore

if TYPE_CHECKING:
    pass


class UniverseBuilder:
    """Builds and caches the tradeable stock universe for each non-US market.

    Inject ibkr_client in production. Pass request_delay=0 in tests.
    """

    _FINVIZ_FILTERS = {
        '50-Day Simple Moving Average': 'Price above SMA50',
        '200-Day Simple Moving Average': 'Price above SMA200',
        'Average Volume': 'Over 500K',
        'Performance': 'Quarter +10%',
    }

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

    def build_queue(self, finnhub_api_key: str = "") -> list[dict]:
        """Scrape FINVIZ for quality stocks, score by Finnhub sentiment, write universe-queue.json."""
        if Overview is None:
            print("[universe_builder] finvizfinance not installed — skipping queue build", file=sys.stderr)
            return []

        try:
            fvscreen = Overview()
            fvscreen.set_filter(filters_dict=self._FINVIZ_FILTERS)
        except Exception as e:
            print(f"[universe_builder] FINVIZ filter setup failed: {e} — falling back to unfiltered", file=sys.stderr)
            fvscreen = Overview()

        try:
            rows = fvscreen.screener_view(columns=["Ticker", "Price", "Volume"])
        except Exception as e:
            print(f"[universe_builder] FINVIZ scrape failed: {e}", file=sys.stderr)
            return []

        if not rows:
            print("[universe_builder] FINVIZ returned 0 candidates", file=sys.stderr)
            return []

        symbols = []
        for row in rows:
            if isinstance(row, dict):
                ticker = row.get("Ticker") or row.get("ticker")
            else:
                ticker = getattr(row, "Ticker", None)
            if ticker:
                symbols.append(str(ticker).upper())

        candidates = []
        for symbol in symbols:
            score = self._get_finnhub_sentiment(symbol, finnhub_api_key)
            candidates.append({"symbol": symbol, "sentiment_score": score, "status": "pending"})

        candidates.sort(key=lambda c: c["sentiment_score"], reverse=True)

        output = {
            "updated": datetime.now(timezone.utc).isoformat(),
            "candidates": candidates,
            "scanned_count": 0,
        }
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        queue_file = self._cache_dir / "universe-queue.json"
        queue_file.write_text(json.dumps(output, indent=2))
        print(f"[universe_builder] queue built: {len(candidates)} candidates", file=sys.stderr)
        return candidates

    def _get_finnhub_sentiment(self, symbol: str, api_key: str) -> float:
        """Fetch Finnhub news sentiment score. Returns 0.5 if unavailable."""
        if not api_key:
            return 0.5
        try:
            url = f"https://finnhub.io/api/v1/news-sentiment?symbol={symbol}&token={api_key}"
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                return float(resp.json().get("companyNewsScore", 0.5))
        except Exception:
            pass
        return 0.5

    def run_nightly_batch(self, fmp_api_key: str, batch_size: int = 20) -> list[dict]:
        """Scan next batch from queue + re-check weakening stocks. Updates vcp-universe.json."""
        if FMPClient is None:
            print("[universe_builder] fmp_client not available — skipping nightly batch", file=sys.stderr)
            return []

        fmp = FMPClient(api_key=fmp_api_key)

        universe_file = self._cache_dir / "vcp-universe.json"
        queue_file = self._cache_dir / "universe-queue.json"

        existing: list[dict] = []
        if universe_file.exists():
            try:
                existing = json.loads(universe_file.read_text()).get("symbols", [])
            except Exception:
                existing = []

        queue_data: dict = {}
        pending: list[dict] = []
        if queue_file.exists():
            try:
                queue_data = json.loads(queue_file.read_text())
                pending = [c for c in queue_data.get("candidates", []) if c.get("status") == "pending"]
            except Exception:
                pending = []

        # Phase 1: re-check weakening stocks first
        weakening = [s for s in existing if s.get("status") == "weakening"]
        to_recheck = [s["symbol"] for s in weakening]

        # Phase 2: take next batch_size slots from pending queue
        slots = max(0, batch_size - len(to_recheck))
        to_scan = [c["symbol"] for c in pending[:slots]]

        # Also include active stocks so we can re-check them against fresh FMP data
        active_symbols = [s["symbol"] for s in existing if s.get("status") == "active"]
        all_symbols = list(dict.fromkeys(to_recheck + to_scan + active_symbols))

        if not all_symbols:
            print("[universe_builder] nothing to scan", file=sys.stderr)
            return existing

        quotes = fmp.get_batch_quotes(all_symbols)
        histories = fmp.get_batch_historical(all_symbols, days=260)

        def _passes_criteria(symbol: str) -> bool:
            quote = quotes.get(symbol, {})
            bars = histories.get(symbol, [])
            if not quote or not bars or len(bars) < 50:
                return False
            price = float(quote.get("price", 0))
            avg_vol = float(quote.get("avgVolume", 0))
            if avg_vol < 500_000:
                return False
            closes = [float(b["close"]) for b in bars]
            ma50 = sum(closes[-50:]) / 50
            ma200 = sum(closes[-200:]) / 200 if len(closes) >= 200 else sum(closes) / len(closes)
            return price > ma50 and price > ma200

        updated_universe: list[dict] = []

        # Process weakening re-checks
        for entry in weakening:
            sym = entry["symbol"]
            if _passes_criteria(sym):
                updated = dict(entry)
                updated["status"] = "active"
                updated_universe.append(updated)
            # else: fails again → dropped (not added)

        # Keep active stocks — re-check those for which we have fresh FMP data
        for entry in existing:
            if entry.get("status") != "active":
                continue
            if entry["symbol"] in to_recheck:
                continue
            sym = entry["symbol"]
            if sym in quotes and not _passes_criteria(sym):
                # Failing today → weakening
                updated = dict(entry)
                updated["status"] = "weakening"
                updated_universe.append(updated)
            else:
                updated_universe.append(entry)

        # Process new scans from queue
        scanned_count = queue_data.get("scanned_count", 0)
        for sym in to_scan:
            candidate = next((c for c in pending if c["symbol"] == sym), {})
            if _passes_criteria(sym):
                updated_universe.append({
                    "symbol": sym,
                    "status": "active",
                    "sentiment_score": candidate.get("sentiment_score", 0.5),
                })
            scanned_count += 1

        # Mark scanned candidates as done in queue
        for c in queue_data.get("candidates", []):
            if c["symbol"] in to_scan:
                c["status"] = "scanned"
        queue_data["scanned_count"] = scanned_count
        if queue_file.exists():
            queue_file.write_text(json.dumps(queue_data, indent=2))

        self._cache_dir.mkdir(parents=True, exist_ok=True)
        output = {
            "updated": datetime.now(timezone.utc).isoformat(),
            "symbols": updated_universe,
        }
        universe_file.write_text(json.dumps(output, indent=2))
        active = sum(1 for s in updated_universe if s["status"] == "active")
        weakening_count = sum(1 for s in updated_universe if s["status"] == "weakening")
        print(
            f"[universe_builder] universe updated: {active} active, {weakening_count} weakening",
            file=sys.stderr,
        )
        return updated_universe

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
