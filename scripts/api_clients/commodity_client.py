"""CommodityPriceAPI client — spot prices for oil, gold, metals, agriculture.

Powers:
    - Oil & Gas theme (Brent/WTI levels confirm energy thesis)
    - Power Infrastructure theme (gas already via EIA, but oil cross-check here)
    - Gold theme (risk-off proxy, USD inverse)
    - Druckenmiller skill (commodity / equity divergence signals)

Auth: X-API-KEY header (not query param)
Free tier: 100 calls/month, EOD data.
Docs: https://www.commoditypriceapi.com/docs
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as date_type
from typing import Any

try:
    import requests
except ImportError as e:
    raise ImportError("commodity_client requires `requests`. Install: pip install requests") from e

from .load_env import get_api_key

BASE = "https://api.commoditypriceapi.com/v2"

# Common symbols (CommodityPriceAPI uses "-SPOT" / "-FUT" suffix convention).
# Default to SPOT where available (more representative of current market price).
SYMBOLS = {
    "BRENT": "BRENTOIL-SPOT",
    "WTI": "WTIOIL-SPOT",
    "NATURAL_GAS": "NG-SPOT",
    "GOLD": "XAU",
    "SILVER": "XAG",
    "COPPER": "HG-SPOT",
    "PLATINUM": "PL",
    "PALLADIUM": "PA",
    "URANIUM": "UXA",
    "COAL": "COAL",
    "LNG": "LNG",
    "GASOLINE": "RB-SPOT",
    "HEATING_OIL": "HO-SPOT",
}


@dataclass
class CommodityPrice:
    """Single commodity price point in USD."""

    symbol: str  # e.g. "BRENTOIL"
    common_name: str  # e.g. "Brent crude"
    date: str  # ISO YYYY-MM-DD
    usd_price: float  # price of 1 unit in USD (commodities-api returns rate vs base)
    unit: str  # e.g. "barrel", "troy ounce"


# Display names (units come back in the API response metadata block)
_NAMES: dict[str, str] = {
    "BRENTOIL-SPOT": "Brent crude",
    "BRENTOIL-FUT": "Brent crude (futures)",
    "WTIOIL-SPOT": "WTI crude",
    "WTIOIL-FUT": "WTI crude (futures)",
    "NG-SPOT": "Natural gas (US)",
    "NG-FUT": "Natural gas (futures)",
    "NG-EU": "Natural gas (EU)",
    "TTF-GAS": "TTF gas",
    "UK-GAS": "UK gas",
    "XAU": "Gold",
    "XAG": "Silver",
    "HG-SPOT": "Copper",
    "PL": "Platinum",
    "PA": "Palladium",
    "UXA": "Uranium",
    "COAL": "Coal",
    "LNG": "LNG (Japan)",
    "RB-SPOT": "RBOB gasoline",
    "HO-SPOT": "Heating oil",
}


class CommodityClient:
    """Commodities-API client.

    Example:
        client = CommodityClient()
        # Get latest oil + gold spot
        prices = client.latest(["BRENT", "GOLD"])
        # Historical Brent for the last 30 days
        history = client.time_series("BRENT", "2026-05-01", "2026-05-27")
    """

    def __init__(self, api_key: str | None = None, timeout: int = 20):
        self.api_key = api_key or get_api_key("COMMODITY_API_KEY")
        self.timeout = timeout
        self._session = requests.Session()

    @staticmethod
    def _resolve(symbol: str) -> str:
        """Map friendly name (e.g. "BRENT") to API code (e.g. "BRENTOIL-SPOT")."""
        return SYMBOLS.get(symbol.upper(), symbol.upper())

    @staticmethod
    def _name(code: str) -> str:
        return _NAMES.get(code, code)

    def _get(self, path: str, params: dict | None = None) -> Any:
        # CommodityPriceAPI uses X-API-KEY header (not query param)
        r = self._session.get(
            f"{BASE}{path}",
            params=params or {},
            headers={"X-API-KEY": self.api_key},
            timeout=self.timeout,
        )
        r.raise_for_status()
        return r.json()

    # ── public API ──────────────────────────────────────────────────

    def latest(self, symbols: list[str], *, base: str = "USD") -> list[CommodityPrice]:
        """Latest spot prices for one or more commodities.

        Args:
            symbols: friendly names ("BRENT", "GOLD") or API codes ("BRENTOIL-SPOT")
            base: quote currency, default USD

        Returns:
            list[CommodityPrice]. Prices are direct (USD per unit), no inversion.
        """
        codes = [self._resolve(s) for s in symbols]
        data = self._get("/rates/latest", {"symbols": ",".join(codes), "base": base})
        if not data.get("success"):
            return []
        rates = data.get("rates") or {}
        meta = data.get("metadata") or {}
        ts_epoch = data.get("timestamp")
        ts = (
            date_type.fromtimestamp(ts_epoch).isoformat()
            if isinstance(ts_epoch, (int, float))
            else date_type.today().isoformat()
        )
        out: list[CommodityPrice] = []
        for code in codes:
            price = rates.get(code)
            if price in (None, 0):
                continue
            try:
                price_f = float(price)
            except (TypeError, ValueError):
                continue
            unit = (meta.get(code) or {}).get("unit", "unit")
            out.append(
                CommodityPrice(
                    symbol=code,
                    common_name=self._name(code),
                    date=ts,
                    usd_price=round(price_f, 4),
                    unit=unit,
                )
            )
        return out

    def time_series(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        *,
        base: str = "USD",
    ) -> list[CommodityPrice]:
        """Historical EOD series for a single commodity.

        Args:
            symbol: friendly name or code
            start_date: ISO YYYY-MM-DD
            end_date: ISO YYYY-MM-DD
            base: quote currency
        """
        code = self._resolve(symbol)
        data = self._get(
            "/rates/time-series",
            {
                "startDate": start_date,
                "endDate": end_date,
                "symbols": code,
                "base": base,
            },
        )
        if not data.get("success"):
            return []
        meta = (data.get("metadata") or {}).get(code) or {}
        unit = meta.get("unit", "unit")
        name = self._name(code)
        out: list[CommodityPrice] = []
        for day, rates in sorted((data.get("rates") or {}).items()):
            price = rates.get(code) if isinstance(rates, dict) else None
            if price in (None, 0):
                continue
            try:
                price_f = float(price)
            except (TypeError, ValueError):
                continue
            out.append(
                CommodityPrice(
                    symbol=code,
                    common_name=name,
                    date=day,
                    usd_price=round(price_f, 4),
                    unit=unit,
                )
            )
        return out
