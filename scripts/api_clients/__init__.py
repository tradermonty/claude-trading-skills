"""Repo-level API client layer (Claude-Code / repo tooling ONLY).

**Scope:** ad-hoc research, exploration, and orchestration from the repo
root. **Not** for direct import from packaged `.skill` runtimes.

`scripts/package_skills.py` bundles only a single `skills/<name>/` tree
into each `.skill` ZIP. A skill that did `from scripts.api_clients import …`
would `ImportError` once installed from its packaged form. Per-skill API
consolidation is a separate effort (vendor / generator approach, see
Issue #115).

Available clients:
    - PolygonClient      : OHLCV, fundamentals, news, market status
    - NewsClient         : Marketeaux + Newsdata IO with auto-fallback
    - EIAClient          : Energy/power data (US Energy Information Admin)
    - PolymarketClient   : Prediction market consensus (for what-is-priced-in)
    - FinnhubClient      : Economic calendar + earnings (free tier)
    - BEAClient          : US GDP, savings rate, consumer spending (BEA)
    - CommodityClient    : Oil, gold, metals, agriculture spot prices
    - EStatClient        : Japan macro stats (CPI, retail sales, etc.)
    - BISClient          : Central bank policy rates, 49 countries (FREE, no key)
    - BLSClient          : US unemployment, NFP, CPI, PPI (FREE, no key)

OFF-LIMITS per project hard-constraints:
    - OANDA   : forex broker (separate project) — never import here
    - Binance : no auto-trade; crypto execution outside project scope

Usage (from a repo-root Claude-Code session or notebook):
    from scripts.api_clients.polygon_client import PolygonClient
    client = PolygonClient()  # auto-loads ~/.claude/secrets/tradermonty.env
    bars = client.get_aggs("AAPL", "day", "2026-01-01", "2026-05-27")
"""

from .bea_client import BEAClient  # noqa: F401
from .bis_client import BISClient  # noqa: F401
from .bls_client import BLSClient  # noqa: F401
from .commodity_client import CommodityClient  # noqa: F401
from .eia_client import EIAClient  # noqa: F401
from .estat_client import EStatClient  # noqa: F401
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
    "BEAClient",
    "CommodityClient",
    "EStatClient",
    "BISClient",
    "BLSClient",
    "get_api_key",
    "load_env",
]
