"""BIS (Bank for International Settlements) Statistics API client.

Provides cross-country central bank policy rates and global liquidity series
for 49 countries. Useful for:
    - macro-regime-detector  (cross-asset rate differential context)
    - market-environment-analysis (Fed-vs-ECB-vs-BoJ rate gaps drive FX flows)
    - druckenmiller skill     (CB policy divergence as macro positioning signal)

Data: SDMX-JSON, monthly frequency, typically 1-2 months lagged.
Auth: none — public API, no key required.
Docs: https://stats.bis.org/api-doc/v1/
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

try:
    import requests
except ImportError as e:
    raise ImportError("bis_client requires `requests`. Install: pip install requests") from e

BASE = "https://stats.bis.org/api/v1"

# Common country codes (ISO 3166 alpha-2; BIS uses XM for the Eurozone)
COMMON_COUNTRIES = (
    "US",
    "XM",
    "GB",
    "JP",
    "CN",
    "AU",
    "CA",
    "NZ",
    "CH",
    "SE",
    "NO",
    "KR",
    "IN",
    "BR",
    "MX",
    "ZA",
    "ID",
    "TR",
    "RU",
    "SG",
)


@dataclass
class PolicyRateObservation:
    """One country's policy rate at a single period."""

    country_code: str
    country_name: str
    period: str  # ISO month "YYYY-MM"
    rate_pct: float  # e.g. 5.25 means 5.25%


class BISClient:
    """BIS Statistics REST client (read-only, no key)."""

    HEADERS = {"Accept": "application/vnd.sdmx.data+json;version=1.0.0"}

    def __init__(self, timeout: int = 20):
        self.timeout = timeout
        self._session = requests.Session()

    def _get(self, path: str, params: dict | None = None) -> Any:
        r = self._session.get(
            f"{BASE}{path}",
            params=params or {},
            headers=self.HEADERS,
            timeout=self.timeout,
        )
        r.raise_for_status()
        return r.json()

    # ── parsing helpers ────────────────────────────────────────────

    @staticmethod
    def _parse_sdmx_policy_rates(raw: dict) -> list[PolicyRateObservation]:
        """Convert SDMX-JSON CBPOL response to a flat observation list.

        SDMX-JSON shape:
            data.structure.dimensions.series  -> ordered list incl REF_AREA
            data.structure.dimensions.observation[0].values -> period axis
            data.dataSets[0].series[key].observations[period_idx] -> [value]
        """
        try:
            struct = raw["data"]["structure"]
            series_dims = struct["dimensions"]["series"]
            country_dim = next(d for d in series_dims if d["id"] == "REF_AREA")
            countries = country_dim["values"]
            period_values = struct["dimensions"]["observation"][0]["values"]
            datasets = raw["data"]["dataSets"][0]["series"]
        except (KeyError, IndexError, StopIteration, TypeError):
            return []

        out: list[PolicyRateObservation] = []
        for series_key, sv in datasets.items():
            # series_key format is "FREQ_idx:REF_AREA_idx[:more]"
            parts = series_key.split(":")
            if len(parts) < 2:
                continue
            try:
                country_idx = int(parts[1])
                country = countries[country_idx]
            except (ValueError, IndexError):
                continue
            country_code = country.get("id", "")
            country_name = country.get("name", country_code)

            for period_idx_str, obs_value in sv.get("observations", {}).items():
                try:
                    period_idx = int(period_idx_str)
                    period = period_values[period_idx]["id"]
                    rate = float(obs_value[0])
                except (ValueError, IndexError, TypeError, KeyError):
                    continue
                out.append(
                    PolicyRateObservation(
                        country_code=country_code,
                        country_name=country_name,
                        period=period,
                        rate_pct=rate,
                    )
                )
        return out

    # ── public API ──────────────────────────────────────────────────

    def get_policy_rates(self, *, last_n_observations: int = 12) -> list[PolicyRateObservation]:
        """All countries' central bank policy rates, last N monthly readings.

        Returns:
            list[PolicyRateObservation] — typically 49 countries × N periods.
        """
        raw = self._get(
            "/data/WS_CBPOL/M..",
            params={"lastNObservations": last_n_observations},
        )
        return self._parse_sdmx_policy_rates(raw)

    def latest_policy_rate(self, country_code: str) -> PolicyRateObservation | None:
        """Latest policy rate for a single country (most recent monthly reading).

        Args:
            country_code: ISO alpha-2 ("US", "JP", "AU"...).
                          For the Eurozone use "XM".
        """
        rows = self.get_policy_rates(last_n_observations=3)
        country_rows = [r for r in rows if r.country_code == country_code.upper()]
        if not country_rows:
            return None
        # Sort by period descending and return the most recent
        return sorted(country_rows, key=lambda r: r.period, reverse=True)[0]

    def rate_differential(self, country_a: str, country_b: str) -> dict[str, Any]:
        """Latest policy-rate spread (a - b) in percentage points.

        Useful for FX context: USD/JPY spread = US 5.25 - JP 0.10 = 5.15 pp.

        Returns:
            {country_a, rate_a, country_b, rate_b, spread_pp, period}
            or {error} on missing data.
        """
        a = self.latest_policy_rate(country_a)
        b = self.latest_policy_rate(country_b)
        if not a or not b:
            return {
                "error": "missing_data",
                "country_a": country_a,
                "country_b": country_b,
                "have_a": a is not None,
                "have_b": b is not None,
            }
        return {
            "country_a": a.country_code,
            "rate_a": a.rate_pct,
            "country_b": b.country_code,
            "rate_b": b.rate_pct,
            "spread_pp": round(a.rate_pct - b.rate_pct, 3),
            "period": a.period if a.period >= b.period else b.period,
        }
