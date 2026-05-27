"""News API client — replaces WebSearch dependency for market-news-analyst.

Wraps two complementary providers with automatic fallback:
    1. Marketaux  — financial news (free tier: 100 calls/day, 3 articles/call)
    2. Newsdata IO — broader news with industry filtering

Usage:
    client = NewsClient()
    items = client.get_market_news(tickers=["NVDA", "AAPL"], days=7)
    geopolitical = client.search_news("OPEC oil production cut", days=3)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

try:
    import requests
except ImportError as e:
    raise ImportError("news_client requires `requests`. Install: pip install requests") from e

from .load_env import get_api_key

MARKETAUX_BASE = "https://api.marketaux.com/v1/news"
NEWSDATA_BASE = "https://newsdata.io/api/1/latest"


@dataclass
class NewsItem:
    """Normalized news article across providers."""

    title: str
    description: str
    url: str
    source: str  # publisher name
    published_at: datetime
    provider: str  # "marketaux" / "newsdata"
    tickers: list[str] = field(default_factory=list)
    sentiment: Optional[float] = None  # -1.0 .. +1.0 (marketaux only)
    keywords: list[str] = field(default_factory=list)


def _parse_ts(s: str) -> datetime:
    """Parse ISO timestamps from either provider, always returning UTC-aware."""
    s = s.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        # Newsdata format: "2026-05-27 12:34:56"
        dt = datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


class NewsClient:
    """Combined news fetcher with provider fallback.

    Marketaux is preferred for ticker-tagged + sentiment-scored articles.
    Newsdata IO is used for broader keyword search and as fallback.
    """

    def __init__(
        self,
        marketaux_key: Optional[str] = None,
        newsdata_key: Optional[str] = None,
        timeout: int = 20,
    ):
        # Both keys optional — if one is missing, fall through to the other
        self.marketaux_key = marketaux_key or get_api_key("MARKETAUX_API_KEY", required=False)
        self.newsdata_key = newsdata_key or get_api_key("NEWSDATA_API_KEY", required=False)
        if not self.marketaux_key and not self.newsdata_key:
            raise RuntimeError(
                "NewsClient requires at least one of MARKETAUX_API_KEY or NEWSDATA_API_KEY"
            )
        self.timeout = timeout
        self._session = requests.Session()

    # ── Marketaux ───────────────────────────────────────────────────

    def _marketaux_call(
        self,
        *,
        symbols: Optional[list[str]] = None,
        search: Optional[str] = None,
        published_after: Optional[str] = None,
        limit: int = 10,
    ) -> list[NewsItem]:
        if not self.marketaux_key:
            return []
        params: dict[str, Any] = {
            "api_token": self.marketaux_key,
            "language": "en",
            "limit": min(limit, 100),
        }
        if symbols:
            params["symbols"] = ",".join(s.upper() for s in symbols)
        if search:
            params["search"] = search
        if published_after:
            params["published_after"] = published_after
        r = self._session.get(MARKETAUX_BASE + "/all", params=params, timeout=self.timeout)
        if r.status_code != 200:
            return []
        data = r.json().get("data") or []
        out: list[NewsItem] = []
        for art in data:
            entities = art.get("entities") or []
            sentiments = [e.get("sentiment_score") for e in entities if e.get("sentiment_score") is not None]
            avg_sent = sum(sentiments) / len(sentiments) if sentiments else None
            out.append(
                NewsItem(
                    title=art.get("title", ""),
                    description=art.get("description", "") or art.get("snippet", ""),
                    url=art.get("url", ""),
                    source=art.get("source", ""),
                    published_at=_parse_ts(art.get("published_at", "")),
                    provider="marketaux",
                    tickers=[e.get("symbol") for e in entities if e.get("symbol")],
                    sentiment=avg_sent,
                    keywords=art.get("keywords", "").split(",") if art.get("keywords") else [],
                )
            )
        return out

    # ── Newsdata IO ─────────────────────────────────────────────────

    def _newsdata_call(
        self,
        *,
        q: Optional[str] = None,
        category: Optional[str] = "business",
        country: Optional[str] = "us",
        limit: int = 10,
    ) -> list[NewsItem]:
        if not self.newsdata_key:
            return []
        params: dict[str, Any] = {
            "apikey": self.newsdata_key,
            "language": "en",
        }
        if q:
            params["q"] = q
        if category:
            params["category"] = category
        if country:
            params["country"] = country
        r = self._session.get(NEWSDATA_BASE, params=params, timeout=self.timeout)
        if r.status_code != 200:
            return []
        data = r.json().get("results") or []
        out: list[NewsItem] = []
        for art in data[:limit]:
            try:
                ts = _parse_ts(art.get("pubDate", ""))
            except (ValueError, TypeError):
                ts = datetime.now(timezone.utc)
            out.append(
                NewsItem(
                    title=art.get("title", ""),
                    description=art.get("description", "") or "",
                    url=art.get("link", ""),
                    source=art.get("source_id", ""),
                    published_at=ts,
                    provider="newsdata",
                    tickers=[],
                    sentiment=None,
                    keywords=art.get("keywords") or [],
                )
            )
        return out

    # ── public ──────────────────────────────────────────────────────

    def get_market_news(
        self,
        *,
        tickers: Optional[list[str]] = None,
        days: int = 7,
        limit: int = 25,
    ) -> list[NewsItem]:
        """Fetch ticker-specific or general market news from past N days.

        Uses Marketaux if tickers provided (for entity tagging + sentiment).
        Falls back to Newsdata if Marketaux unavailable or returns nothing.
        """
        published_after = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S")
        items = self._marketaux_call(symbols=tickers, published_after=published_after, limit=limit)
        if not items:
            q = " OR ".join(tickers) if tickers else None
            items = self._newsdata_call(q=q, limit=limit)
        return sorted(items, key=lambda x: x.published_at, reverse=True)

    def search_news(self, query: str, days: int = 7, limit: int = 25) -> list[NewsItem]:
        """Keyword search across both providers, deduplicated by URL."""
        published_after = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S")
        items = self._marketaux_call(search=query, published_after=published_after, limit=limit)
        items += self._newsdata_call(q=query, limit=limit)
        # Dedup by URL
        seen: set[str] = set()
        unique: list[NewsItem] = []
        for it in sorted(items, key=lambda x: x.published_at, reverse=True):
            if it.url and it.url not in seen:
                seen.add(it.url)
                unique.append(it)
        return unique
