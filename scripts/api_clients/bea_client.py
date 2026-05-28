"""US Bureau of Economic Analysis (BEA) client.

The BEA is the source of US GDP, personal income, savings rate, and regional
data. Useful for:
    - macro-regime-detector  (real GDP growth, recession proxies)
    - stanley-druckenmiller-investment (savings rate, consumer health)
    - market-environment-analysis (cycle position)

Free tier: unlimited within reason; key required.
Docs: https://apps.bea.gov/api/_pdf/bea_web_service_api_user_guide.pdf
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

try:
    import requests
except ImportError as e:
    raise ImportError("bea_client requires `requests`. Install: pip install requests") from e

from .load_env import get_api_key

BASE = "https://apps.bea.gov/api/data"


def _last_n_years(n: int = 5, *, lag: int = 0) -> str:
    """Return a comma-separated year list for the most recent N years.

    Args:
        n: how many years
        lag: how many years back from today to start. Useful for data with
            publication lag (e.g. BEA annual GDP lags ~1.5 years, so lag=2
            ensures we only request fully-published years).
    """
    this_year = date.today().year
    last = this_year - lag
    return ",".join(str(y) for y in range(last - n + 1, last + 1))


# Frequently used NIPA (National Income and Product Accounts) tables
NIPA_TABLES = {
    "real_gdp": "T10101",  # Real GDP, percent change from preceding period
    "gdp_nominal": "T10105",  # Gross domestic product
    "personal_income": "T20100",  # Personal income and outlays
    "savings_rate": "T20100",  # Same table, line 34 = personal saving rate
    "consumer_spending": "T20305",  # Personal consumption expenditures by major type
    "corporate_profits": "T11200",  # National income by sector
}


@dataclass
class BEAObservation:
    """Single time-series point from a BEA dataset."""

    table: str
    line_description: str  # e.g. "Gross domestic product"
    time_period: str  # e.g. "2025Q4" or "2025"
    value: float
    unit: str  # e.g. "Billions of dollars" or "Percent"


class BEAClient:
    """BEA REST client.

    Example:
        client = BEAClient()
        # Latest quarterly real GDP growth (annualized %)
        obs = client.get_nipa("T10101", frequency="Q", year="LAST5")
        # Personal saving rate (line 34 in T20100)
        savings = client.personal_saving_rate(year="LAST5")
    """

    def __init__(self, api_key: str | None = None, timeout: int = 30):
        self.api_key = api_key or get_api_key("US_BEA_API_KEY")
        self.timeout = timeout
        self._session = requests.Session()

    def _get(self, params: dict) -> Any:
        params = dict(params)
        params["UserID"] = self.api_key
        params["ResultFormat"] = "JSON"
        r = self._session.get(BASE, params=params, timeout=self.timeout)
        r.raise_for_status()
        data = r.json()
        # BEA reports errors either at BEAAPI.Error or BEAAPI.Results.Error
        api_block = data.get("BEAAPI") or {}
        top_err = api_block.get("Error")
        if top_err:
            desc = (
                top_err.get("APIErrorDescription") if isinstance(top_err, dict) else ""
            ) or "BEA API error"
            detail = ""
            err_detail = top_err.get("ErrorDetail") if isinstance(top_err, dict) else None
            if isinstance(err_detail, dict):
                detail = err_detail.get("Description", "")
            raise RuntimeError(f"BEA: {desc} ({detail})" if detail else f"BEA: {desc}")
        return data

    # ── dataset discovery ──────────────────────────────────────────

    def list_datasets(self) -> list[dict[str, str]]:
        """All BEA datasets (NIPA, GDPByIndustry, Regional, etc.)."""
        data = self._get({"method": "GETDATASETLIST"})
        results = (data.get("BEAAPI") or {}).get("Results") or {}
        return results.get("Dataset") or []

    # ── NIPA queries ────────────────────────────────────────────────

    def get_nipa(
        self,
        table_name: str,
        *,
        frequency: str = "Q",
        year: str | None = None,
    ) -> list[BEAObservation]:
        """Query NIPA dataset for a specific table.

        Args:
            table_name: e.g. "T10101" or use NIPA_TABLES dict
            frequency: "A" (annual), "Q" (quarterly), "M" (monthly where supported)
            year: "ALL", a single year "2025", or comma list "2024,2025".
                  Defaults to last 5 years.

        Returns: BEAObservation list, may include many lines per period.
        """
        if year is None:
            # Annual data lags ~1.5 yrs; quarterly lags ~1 quarter. Use lag=2 to be safe.
            year = _last_n_years(5, lag=2)
        params = {
            "method": "GetData",
            "DatasetName": "NIPA",
            "TableName": table_name,
            "Frequency": frequency,
            "Year": year,
        }
        data = self._get(params)
        results = (data.get("BEAAPI") or {}).get("Results") or {}
        rows = results.get("Data") or []
        unit_label = results.get("UnitOfMeasure") or ""
        return [
            BEAObservation(
                table=table_name,
                line_description=row.get("LineDescription", ""),
                time_period=row.get("TimePeriod", ""),
                value=float(str(row.get("DataValue", "0")).replace(",", "") or 0),
                unit=row.get("CL_UNIT") or unit_label,
            )
            for row in rows
        ]

    # ── high-level convenience ─────────────────────────────────────

    def real_gdp_growth(
        self,
        *,
        year: str | None = None,
        frequency: str = "A",
    ) -> list[BEAObservation]:
        """Real GDP percent change from preceding period.

        Args:
            year: e.g. "2024" or "2022,2023,2024". Defaults to the last 5
                completed years (excludes current year for Q data that's not
                yet published).
            frequency: "A" (annual, default) or "Q" (quarterly).
                Recession proxy: 2 consecutive negative quarters.
        """
        if year is None:
            # Annual data lags ~1.5 yrs; quarterly lags ~1 quarter. Use lag=2 to be safe.
            year = _last_n_years(5, lag=2)
        obs = self.get_nipa("T10101", frequency=frequency, year=year)
        # Line 1 in T10101 is the "Gross domestic product" total
        filtered = [o for o in obs if "Gross domestic product" in o.line_description]
        # If filter excluded everything (line label drift), return all rows
        return filtered or obs

    def personal_saving_rate(
        self,
        *,
        year: str | None = None,
        frequency: str = "A",
    ) -> list[BEAObservation]:
        """Personal saving as % of disposable income.

        Below 4% → late cycle, consumers stretched.
        Above 8% → early cycle / risk-off.
        """
        if year is None:
            # Annual data lags ~1.5 yrs; quarterly lags ~1 quarter. Use lag=2 to be safe.
            year = _last_n_years(5, lag=2)
        obs = self.get_nipa("T20100", frequency=frequency, year=year)
        filtered = [o for o in obs if "Personal saving as a percentage" in o.line_description]
        return filtered or obs
