"""Polygon.io client — institutional market data.

Replaces yfinance scraping across the project. Provides:
    - OHLCV aggregates (intraday + daily, any timeframe)
    - Ticker details + fundamentals
    - News articles by ticker
    - Market status (open/closed/extended)
    - Real-time quotes (subscription dependent)

Free tier: 5 calls/min, end-of-day data, 2 years history.
Stocks Starter ($29/mo): 100 calls/min, real-time, 5 years.

Docs: https://polygon.io/docs
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any

try:
    import requests
except ImportError as e:
    raise ImportError("polygon_client requires `requests`. Install: pip install requests") from e

from .load_env import get_api_key

BASE = "https://api.polygon.io"


@dataclass
class Bar:
    """OHLCV bar from /v2/aggs endpoint."""

    timestamp_ms: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    vwap: float | None = None
    transactions: int | None = None

    @property
    def datetime(self) -> datetime:
        return datetime.fromtimestamp(self.timestamp_ms / 1000)


class PolygonClient:
    """Polygon.io REST client.

    Example:
        client = PolygonClient()
        bars = client.get_aggs("AAPL", "day", "2026-01-01", "2026-05-27")
        news = client.get_ticker_news("NVDA", limit=10)
    """

    def __init__(
        self,
        api_key: str | None = None,
        rate_limit_sec: float = 0.0,
        timeout: int = 30,
    ):
        self.api_key = api_key or get_api_key("POLYGON_API_KEY")
        self.rate_limit_sec = rate_limit_sec
        self.timeout = timeout
        self._last_request = 0.0
        self._session = requests.Session()

    # ── internal ────────────────────────────────────────────────────

    def _throttle(self) -> None:
        if self.rate_limit_sec > 0:
            elapsed = time.time() - self._last_request
            if elapsed < self.rate_limit_sec:
                time.sleep(self.rate_limit_sec - elapsed)
        self._last_request = time.time()

    def _get(self, path: str, params: dict | None = None) -> dict:
        self._throttle()
        params = dict(params or {})
        params["apiKey"] = self.api_key
        url = f"{BASE}{path}"
        r = self._session.get(url, params=params, timeout=self.timeout)
        if r.status_code == 429:
            time.sleep(60)
            r = self._session.get(url, params=params, timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    # ── public API ──────────────────────────────────────────────────

    def get_aggs(
        self,
        ticker: str,
        timespan: str,
        from_date: str,
        to_date: str,
        *,
        multiplier: int = 1,
        adjusted: bool = True,
        limit: int = 5000,
    ) -> list[Bar]:
        """Get OHLCV aggregate bars.

        Args:
            ticker: stock symbol (e.g. "AAPL")
            timespan: minute / hour / day / week / month / quarter / year
            from_date: ISO date "YYYY-MM-DD"
            to_date: ISO date "YYYY-MM-DD"
            multiplier: number of timespans per bar (e.g. 5-minute = multiplier=5, timespan="minute")
            adjusted: split/dividend adjusted prices
            limit: max bars returned (Polygon hard cap 50000)

        Returns:
            list[Bar] sorted oldest -> newest
        """
        path = (
            f"/v2/aggs/ticker/{ticker.upper()}/range/{multiplier}/{timespan}/{from_date}/{to_date}"
        )
        params = {"adjusted": str(adjusted).lower(), "sort": "asc", "limit": limit}
        data = self._get(path, params)
        results = data.get("results") or []
        return [
            Bar(
                timestamp_ms=r["t"],
                open=r["o"],
                high=r["h"],
                low=r["l"],
                close=r["c"],
                volume=r["v"],
                vwap=r.get("vw"),
                transactions=r.get("n"),
            )
            for r in results
        ]

    def get_ticker_details(self, ticker: str) -> dict[str, Any]:
        """Company name, market cap, sector, employees, description."""
        data = self._get(f"/v3/reference/tickers/{ticker.upper()}")
        return data.get("results", {})

    def get_ticker_news(
        self,
        ticker: str | None = None,
        *,
        limit: int = 10,
        order: str = "desc",
        published_gte: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get news articles. If ticker omitted, returns market-wide news.

        Returns each article with: title, publisher, author, published_utc,
        article_url, tickers, description, keywords, insights.
        """
        params: dict[str, Any] = {"limit": limit, "order": order}
        if ticker:
            params["ticker"] = ticker.upper()
        if published_gte:
            params["published_utc.gte"] = published_gte
        data = self._get("/v2/reference/news", params)
        return data.get("results") or []

    def get_market_status(self) -> dict[str, Any]:
        """Current market open/closed state across all venues."""
        return self._get("/v1/marketstatus/now")

    def get_previous_close(self, ticker: str, adjusted: bool = True) -> Bar | None:
        """Yesterday's OHLCV."""
        path = f"/v2/aggs/ticker/{ticker.upper()}/prev"
        data = self._get(path, {"adjusted": str(adjusted).lower()})
        results = data.get("results") or []
        if not results:
            return None
        r = results[0]
        return Bar(
            timestamp_ms=r["t"],
            open=r["o"],
            high=r["h"],
            low=r["l"],
            close=r["c"],
            volume=r["v"],
            vwap=r.get("vw"),
            transactions=r.get("n"),
        )

    def get_grouped_daily(self, date: str, adjusted: bool = True) -> list[dict]:
        """All US stocks' OHLCV for a single date — useful for breadth scans.

        Returns: list of {T (ticker), o, h, l, c, v, vw, n} dicts.
        """
        path = f"/v2/aggs/grouped/locale/us/market/stocks/{date}"
        data = self._get(path, {"adjusted": str(adjusted).lower()})
        return data.get("results") or []

    def search_tickers(
        self,
        *,
        market: str = "stocks",
        active: bool = True,
        ticker_search: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """Search/list tickers. Used by screeners."""
        params: dict[str, Any] = {"market": market, "active": str(active).lower(), "limit": limit}
        if ticker_search:
            params["search"] = ticker_search
        data = self._get("/v3/reference/tickers", params)
        return data.get("results") or []
