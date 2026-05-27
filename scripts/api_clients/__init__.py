"""Centralized API client layer for TraderMonty.

Replaces scraper-based data collection (yfinance, finvizfinance, WebSearch)
with structured API access. Single entry point for env loading and rate
limiting across all providers.

Available clients:
    - PolygonClient      : OHLCV, fundamentals, news, market status
    - NewsClient         : Marketeaux + Newsdata IO with auto-fallback
    - EIAClient          : Energy/power data (US Energy Information Admin)
    - PolymarketClient   : Prediction market consensus (for what-is-priced-in)
    - FinnhubClient      : Economic calendar + earnings (free tier)

OFF-LIMITS per project hard-constraints:
    - OANDA   : forex broker (separate project) — never import here
    - Binance : no auto-trade; crypto execution outside project scope

Usage:
    from scripts.api_clients import PolygonClient
    client = PolygonClient()  # auto-loads ~/.claude/secrets/tradermonty.env
    bars = client.get_aggs("AAPL", "day", "2026-01-01", "2026-05-27")
"""

from .eia_client import EIAClient  # noqa: F401
from .finnhub_client import FinnhubClient  # noqa: F401
from .load_env import get_api_key, load_env  # noqa: F401
from .news_client import NewsClient  # noqa: F401
from .polygon_client import PolygonClient  # noqa: F401
from .polymarket_client import PolymarketClient  # noqa: F401

__all__ = [
    "PolygonClient",
    "NewsClient",
    "EIAClient",
    "PolymarketClient",
    "FinnhubClient",
    "get_api_key",
    "load_env",
]
