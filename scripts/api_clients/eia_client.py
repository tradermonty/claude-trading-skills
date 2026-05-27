"""EIA (US Energy Information Administration) client.

Powers the Power Infrastructure & AI Energy Demand theme directly:
    - Electricity demand by region (PJM, ERCOT, CAISO, NYISO, MISO)
    - Generation by fuel source (natural gas, coal, nuclear, renewables)
    - Wholesale electricity prices (LMPs)
    - Natural gas spot + futures prices (for spark spread calculation)
    - Petroleum products

Free tier: unlimited within reason; key required.
Docs: https://www.eia.gov/opendata/documentation.php
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

try:
    import requests
except ImportError as e:
    raise ImportError("eia_client requires `requests`. Install: pip install requests") from e

from .load_env import get_api_key

BASE = "https://api.eia.gov/v2"

# Region codes for electricity demand
REGIONS = {
    "PJM": "PJM",  # Mid-Atlantic
    "ERCOT": "ERCO",  # Texas
    "CAISO": "CISO",  # California
    "NYISO": "NYIS",  # New York
    "MISO": "MISO",  # Midwest
    "ISONE": "ISNE",  # New England
    "SPP": "SWPP",  # Southwest
    "US48": "US48",  # Contiguous US total
}


@dataclass
class EnergyPoint:
    """Single time-series observation."""

    period: str  # ISO-ish: "2026-05-26" or "2026-05-26T14"
    value: float
    unit: str
    series_label: str

    @property
    def datetime(self) -> datetime:
        if "T" in self.period:
            return datetime.fromisoformat(self.period)
        return datetime.fromisoformat(self.period + "T00:00:00")


class EIAClient:
    """EIA v2 API client.

    Example:
        client = EIAClient()
        pjm_demand = client.electricity_demand("PJM", days=7)
        gas_price = client.natural_gas_spot(days=30)
        spread = client.spark_spread_indicator("PJM")
    """

    def __init__(self, api_key: str | None = None, timeout: int = 30):
        self.api_key = api_key or get_api_key("EIA_API_KEY")
        self.timeout = timeout
        self._session = requests.Session()

    def _get(self, path: str, params: dict | None = None) -> dict:
        params = dict(params or {})
        params["api_key"] = self.api_key
        r = self._session.get(f"{BASE}{path}", params=params, timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    # ── electricity ─────────────────────────────────────────────────

    def electricity_demand(
        self, region: str, *, days: int = 7, hourly: bool = False
    ) -> list[EnergyPoint]:
        """Megawatt-hours of demand by region.

        Args:
            region: "PJM" / "ERCOT" / "CAISO" / "NYISO" / "MISO" / "ISONE" / "SPP" / "US48"
            days: lookback window
            hourly: True for hourly resolution, False for daily

        Returns: list of EnergyPoint, oldest -> newest.
        """
        code = REGIONS.get(region.upper(), region.upper())
        endpoint = (
            "/electricity/rto/region-data/data"
            if hourly
            else "/electricity/rto/daily-region-data/data"
        )
        params = {
            "frequency": "hourly" if hourly else "daily",
            "data[]": "value",
            "facets[respondent][]": code,
            "facets[type][]": "D",  # D = Demand
            "sort[0][column]": "period",
            "sort[0][direction]": "desc",
            "length": days * (24 if hourly else 1),
        }
        data = self._get(endpoint, params)
        rows = (data.get("response") or {}).get("data") or []
        return [
            EnergyPoint(
                period=row["period"],
                value=float(row.get("value") or 0),
                unit=row.get("value-units", "MWh"),
                series_label=f"{region} demand",
            )
            for row in reversed(rows)
        ]

    def electricity_generation_by_fuel(
        self, region: str = "US48", *, days: int = 7
    ) -> dict[str, list[EnergyPoint]]:
        """Daily generation broken down by fuel type.

        Returns dict: {"natural_gas": [...], "nuclear": [...], "coal": [...], ...}
        """
        code = REGIONS.get(region.upper(), region.upper())
        params = {
            "frequency": "daily",
            "data[]": "value",
            "facets[respondent][]": code,
            "sort[0][column]": "period",
            "sort[0][direction]": "desc",
            "length": days * 10,  # multiple fuel rows per day
        }
        data = self._get("/electricity/rto/daily-fuel-type-data/data", params)
        rows = (data.get("response") or {}).get("data") or []
        out: dict[str, list[EnergyPoint]] = {}
        for r in rows:
            fuel = (r.get("fueltype") or "unknown").lower().replace(" ", "_")
            out.setdefault(fuel, []).append(
                EnergyPoint(
                    period=r["period"],
                    value=float(r.get("value") or 0),
                    unit=r.get("value-units", "MWh"),
                    series_label=f"{region} {fuel}",
                )
            )
        return out

    # ── natural gas (input cost for spark spread) ──────────────────

    def natural_gas_spot(self, *, days: int = 30) -> list[EnergyPoint]:
        """Henry Hub daily natural gas spot price ($/MMBtu).

        This is the gas input cost for the spark spread:
            spark_spread = power_price - (gas_price * heat_rate)
        """
        params = {
            "frequency": "daily",
            "data[]": "value",
            "facets[series][]": "RNGWHHD",  # Henry Hub spot
            "sort[0][column]": "period",
            "sort[0][direction]": "desc",
            "length": days,
        }
        data = self._get("/natural-gas/pri/fut/data", params)
        rows = (data.get("response") or {}).get("data") or []
        return [
            EnergyPoint(
                period=r["period"],
                value=float(r.get("value") or 0),
                unit="$/MMBtu",
                series_label="Henry Hub spot",
            )
            for r in reversed(rows)
        ]

    # ── derived analytics ──────────────────────────────────────────

    def power_demand_yoy(self, region: str = "US48") -> dict[str, Any]:
        """Year-over-year demand growth — the core AI/data-center thesis.

        Returns:
            {region, latest_period, latest_demand_mwh, yoy_demand_mwh, yoy_change_pct}
        """
        # Get this week and same week year ago (approx by 365 days back)
        # Simple approach: pull last 400 days and compare last 7 to 7 from 365 days ago
        points = self.electricity_demand(region, days=400, hourly=False)
        if len(points) < 365:
            return {"region": region, "error": "insufficient_history"}
        latest_7 = points[-7:]
        prior_7 = points[-372:-365]
        latest_avg = sum(p.value for p in latest_7) / len(latest_7) if latest_7 else 0
        prior_avg = sum(p.value for p in prior_7) / len(prior_7) if prior_7 else 0
        if prior_avg == 0:
            return {"region": region, "error": "no_baseline"}
        return {
            "region": region,
            "latest_period": latest_7[-1].period,
            "latest_demand_mwh": round(latest_avg, 0),
            "yoy_demand_mwh": round(prior_avg, 0),
            "yoy_change_pct": round((latest_avg - prior_avg) / prior_avg * 100, 2),
        }
