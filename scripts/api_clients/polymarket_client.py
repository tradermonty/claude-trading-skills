"""Polymarket client — prediction market consensus pricing.

Powers the "what-is-priced-in" framework from trade-hypothesis-ideator.
When a binary catalyst is upcoming (election, rate decision, earnings beat),
Polymarket's contract prices give you the *implied probability* the market
assigns. Compare your own model to this and you have the consensus gap.

Polymarket has TWO APIs:
    - CLOB (Central Limit Order Book) — public, no key needed, market data
    - Gamma — public REST, market metadata + event listing

The POLYMARKET_API_KEY in the secrets file is a JWT for the Bigdata/research
endpoint, not the trading API. We use the public Gamma + CLOB endpoints here
since they don't require auth for read access.

Docs:
    - Gamma:  https://docs.polymarket.com/developers/gamma-markets-api/overview
    - CLOB:   https://docs.polymarket.com/developers/CLOB/overview
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

try:
    import requests
except ImportError as e:
    raise ImportError("polymarket_client requires `requests`. Install: pip install requests") from e

from .load_env import get_api_key

GAMMA_BASE = "https://gamma-api.polymarket.com"
CLOB_BASE = "https://clob.polymarket.com"


@dataclass
class Market:
    """Polymarket binary contract."""

    id: str
    question: str
    slug: str
    end_date: Optional[datetime]
    yes_price: Optional[float]  # 0.0 .. 1.0 = implied probability
    no_price: Optional[float]
    volume_24h: float
    liquidity: float
    category: Optional[str] = None
    tags: list[str] = field(default_factory=list)

    @property
    def implied_probability(self) -> Optional[float]:
        """Market's implied probability the YES outcome occurs."""
        return self.yes_price


class PolymarketClient:
    """Read-only Polymarket data client.

    Example:
        client = PolymarketClient()
        # Find markets about upcoming Fed decisions
        fed = client.search_markets("Fed rate cut", active=True)
        # Current implied probability:
        for m in fed[:5]:
            print(f"{m.question}: {m.implied_probability:.0%}")
    """

    def __init__(self, jwt_token: Optional[str] = None, timeout: int = 20):
        # JWT only used by research API; public Gamma/CLOB endpoints don't need it
        self.jwt = jwt_token or get_api_key("POLYMARKET_API_KEY", required=False)
        self.timeout = timeout
        self._session = requests.Session()

    def _get(self, base: str, path: str, params: Optional[dict] = None) -> Any:
        url = f"{base}{path}"
        r = self._session.get(url, params=params or {}, timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    @staticmethod
    def _parse_market(raw: dict) -> Market:
        # Gamma returns prices as strings in outcomePrices for some endpoints
        outcomes = raw.get("outcomePrices") or raw.get("outcomes_prices") or []
        if isinstance(outcomes, str):
            # comma-separated string
            try:
                outcomes = [float(x) for x in outcomes.strip("[]").split(",")]
            except ValueError:
                outcomes = []
        yes_price = float(outcomes[0]) if outcomes and len(outcomes) > 0 else None
        no_price = float(outcomes[1]) if outcomes and len(outcomes) > 1 else None

        end_iso = raw.get("endDate") or raw.get("end_date_iso")
        end_dt: Optional[datetime] = None
        if end_iso:
            try:
                end_dt = datetime.fromisoformat(end_iso.replace("Z", "+00:00"))
            except ValueError:
                end_dt = None

        return Market(
            id=str(raw.get("id") or raw.get("conditionId") or ""),
            question=raw.get("question") or raw.get("title", ""),
            slug=raw.get("slug", ""),
            end_date=end_dt,
            yes_price=yes_price,
            no_price=no_price,
            volume_24h=float(raw.get("volume24hr") or raw.get("volume_24h") or 0),
            liquidity=float(raw.get("liquidity") or 0),
            category=raw.get("category"),
            tags=raw.get("tags") or [],
        )

    # ── public API ──────────────────────────────────────────────────

    def search_markets(
        self,
        query: str,
        *,
        active: bool = True,
        closed: bool = False,
        limit: int = 20,
    ) -> list[Market]:
        """Keyword search for binary markets.

        Args:
            query: search text (matches question/title)
            active: only currently-tradeable markets
            closed: include resolved markets
            limit: max results

        Returns:
            list[Market] sorted by 24h volume desc
        """
        params: dict[str, Any] = {
            "active": str(active).lower(),
            "closed": str(closed).lower(),
            "limit": limit,
            "order": "volume24hr",
            "ascending": "false",
        }
        # Gamma supports `q=` for full-text search
        if query:
            params["q"] = query
        try:
            data = self._get(GAMMA_BASE, "/markets", params)
        except requests.HTTPError:
            return []
        items = data if isinstance(data, list) else data.get("data") or []
        return [self._parse_market(m) for m in items if m]

    def get_top_markets_by_volume(self, *, limit: int = 25) -> list[Market]:
        """Most-traded active markets — useful for finding consensus on hot topics."""
        params = {
            "active": "true",
            "closed": "false",
            "limit": limit,
            "order": "volume24hr",
            "ascending": "false",
        }
        try:
            data = self._get(GAMMA_BASE, "/markets", params)
        except requests.HTTPError:
            return []
        items = data if isinstance(data, list) else data.get("data") or []
        return [self._parse_market(m) for m in items if m]

    def get_event_markets(self, event_slug: str) -> list[Market]:
        """All markets within an event (e.g. all rate-cut outcomes for an FOMC meeting)."""
        try:
            data = self._get(GAMMA_BASE, f"/events/{event_slug}")
        except requests.HTTPError:
            return []
        markets = (data or {}).get("markets") or []
        return [self._parse_market(m) for m in markets]
