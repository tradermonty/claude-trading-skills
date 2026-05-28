"""BLS (US Bureau of Labor Statistics) API client.

Powers US labor + inflation analysis:
    - Unemployment rate (U-3)
    - Nonfarm payrolls (NFP)
    - CPI headline + core
    - PPI final demand
    - Average hourly earnings
    - Labor force participation

Auth: works without a key (limited to 25 series/day, 10 yrs back).
With a free `BLS_API_KEY` registered: 500 series/day, 20 yrs back.

Useful for:
    - macro-regime-detector  (recession proxies via NFP trend + unemployment)
    - druckenmiller skill    (labor-market tightness, real wage growth)
    - market-environment-analysis  (CPI surprise, Fed-watching context)

Docs: https://www.bls.gov/developers/api_signature_v2.htm
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

try:
    import requests
except ImportError as e:
    raise ImportError("bls_client requires `requests`. Install: pip install requests") from e

from .load_env import get_api_key

BASE = "https://api.bls.gov/publicAPI/v2"

# Commonly used US-economy series IDs
SERIES = {
    # Labor
    "unemployment_rate": "LNS14000000",  # U-3 unemployment (seasonally adjusted)
    "nonfarm_payrolls": "CES0000000001",  # Total NFP, thousands
    "labor_participation": "LNS11300000",  # Labor force participation rate
    "avg_hourly_earnings": "CES0500000003",  # Avg hourly earnings, private nonfarm
    # Inflation
    "cpi_headline": "CUUR0000SA0",  # CPI All Items, urban, NSA
    "cpi_core": "CUUR0000SA0L1E",  # CPI less food & energy
    "ppi_final_demand": "WPSFD4",  # PPI final demand
    "ppi_core": "WPUFD49104",  # PPI less food & energy
}


@dataclass
class BLSObservation:
    """Single BLS time-series observation."""

    series_id: str
    period: str  # ISO-ish "YYYY-MM" or annual "YYYY"
    value: float
    period_name: str  # e.g. "April" or "Q2"
    footnotes: list[str]


class BLSClient:
    """BLS REST client.

    Example:
        client = BLSClient()
        # Latest unemployment readings
        ur = client.get_series(["LNS14000000"], start_year=2024, end_year=2026)
        # Use the friendly name dict
        nfp = client.get_named("nonfarm_payrolls", start_year=2024)
    """

    def __init__(self, api_key: str | None = None, timeout: int = 30):
        # Key is optional — without it, BLS allows public access with lower limits
        self.api_key = api_key or get_api_key("BLS_API_KEY", required=False)
        self.timeout = timeout
        self._session = requests.Session()

    # ── internal ────────────────────────────────────────────────────

    def _post(self, path: str, body: dict) -> Any:
        if self.api_key:
            body = {**body, "registrationkey": self.api_key}
        r = self._session.post(
            f"{BASE}{path}",
            json=body,
            timeout=self.timeout,
        )
        r.raise_for_status()
        data = r.json()
        # BLS reports errors via status="REQUEST_NOT_PROCESSED" + message[]
        if data.get("status") and data["status"] != "REQUEST_SUCCEEDED":
            messages = data.get("message") or []
            joined = "; ".join(str(m) for m in messages[:3])
            raise RuntimeError(f"BLS: {data['status']}: {joined}")
        return data

    @staticmethod
    def _parse_series(raw: dict) -> list[BLSObservation]:
        """Convert BLS v2 series response to flat observations."""
        out: list[BLSObservation] = []
        series_list = (raw.get("Results") or {}).get("series") or []
        for s in series_list:
            sid = s.get("seriesID", "")
            for d in s.get("data") or []:
                period = d.get("period", "")  # e.g. "M04"
                year = d.get("year", "")
                # Convert "M04" -> "04" for ISO-ish "YYYY-MM"
                if period.startswith("M") and len(period) >= 3:
                    iso = f"{year}-{period[1:3]}"
                elif period.startswith("Q") and len(period) >= 2:
                    iso = f"{year}Q{period[1:2]}"
                elif period == "A01" or period == "":
                    iso = str(year)
                else:
                    iso = f"{year}-{period}"
                try:
                    value = float(d.get("value") or 0)
                except (TypeError, ValueError):
                    continue
                fn_list = d.get("footnotes") or []
                footnotes = [
                    (f.get("text", "") if isinstance(f, dict) else str(f)) for f in fn_list if f
                ]
                out.append(
                    BLSObservation(
                        series_id=sid,
                        period=iso,
                        value=value,
                        period_name=d.get("periodName", ""),
                        footnotes=footnotes,
                    )
                )
        return out

    # ── public API ──────────────────────────────────────────────────

    def get_series(
        self,
        series_ids: list[str],
        *,
        start_year: int,
        end_year: int,
    ) -> list[BLSObservation]:
        """Fetch one or more series for a year range.

        Args:
            series_ids: list of BLS series IDs (e.g. ["LNS14000000", "CES0000000001"])
            start_year: 4-digit start year
            end_year: 4-digit end year (inclusive)

        Returns:
            list[BLSObservation] — flattened across all series.
        """
        body = {
            "seriesid": list(series_ids),
            "startyear": str(start_year),
            "endyear": str(end_year),
        }
        raw = self._post("/timeseries/data/", body)
        return self._parse_series(raw)

    def get_named(
        self,
        friendly_name: str,
        *,
        start_year: int,
        end_year: int | None = None,
    ) -> list[BLSObservation]:
        """Fetch a series by friendly name (see SERIES dict).

        Example:
            obs = client.get_named("unemployment_rate", start_year=2024)
        """
        if friendly_name not in SERIES:
            raise KeyError(
                f"Unknown series name {friendly_name!r}. Available: {sorted(SERIES.keys())}"
            )
        from datetime import date as _date

        if end_year is None:
            end_year = _date.today().year
        return self.get_series([SERIES[friendly_name]], start_year=start_year, end_year=end_year)
