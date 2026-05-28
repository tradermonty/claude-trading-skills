"""Japan e-Stat client — Statistics Bureau of Japan macro data.

Powers Japan-focused workflows:
    - CPI (national / Tokyo) — BOJ inflation context
    - Retail sales — consumer health
    - Unemployment, labor force
    - Industrial production
    - Wage indices

The skill set already supports JA reports, so this gives quantitative
backing for those workflows (e.g. JP CPI prints feeding JPY-tied trades).

Free tier: key required, generous limits.
Docs: https://www.e-stat.go.jp/api/api-info/e-stat-manual3-0
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

try:
    import requests
except ImportError as e:
    raise ImportError("estat_client requires `requests`. Install: pip install requests") from e

from .load_env import get_api_key

BASE = "https://api.e-stat.go.jp/rest/3.0/app/json"

# Well-known statsDataId values (Japan e-Stat catalog IDs)
# These are stable identifiers; verify against the e-Stat catalog at need.
STATS_IDS = {
    "cpi_national": "0003427113",  # Consumer Price Index — national
    "cpi_tokyo": "0003427112",  # Consumer Price Index — Tokyo area
    "retail_sales": "0003419934",  # Retail sales index (METI)
    "unemployment": "0003420537",  # Labor force survey
    "industrial_production": "0003420538",  # IIP
}


@dataclass
class JapanStat:
    """Single Japan macro observation."""

    stats_id: str
    series_label: str  # category / classification context
    time_period: str  # e.g. "2026-04" or "2026Q1"
    value: float
    unit: str  # e.g. "index" or "%"


class EStatClient:
    """Japan e-Stat REST client (read-only)."""

    def __init__(self, api_key: str | None = None, timeout: int = 30):
        self.api_key = api_key or get_api_key("ESTAT_API_KEY")
        self.timeout = timeout
        self._session = requests.Session()

    def _get(self, path: str, params: dict) -> Any:
        params = dict(params)
        params["appId"] = self.api_key
        r = self._session.get(f"{BASE}{path}", params=params, timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    # ── public API ──────────────────────────────────────────────────

    def get_stats_data(
        self,
        stats_data_id: str,
        *,
        start_position: int = 1,
        limit: int = 100,
    ) -> list[JapanStat]:
        """Fetch raw observations from a statsDataId.

        Args:
            stats_data_id: e-Stat dataset ID (see STATS_IDS for common ones)
            start_position: pagination offset (1-based)
            limit: max rows returned

        Returns:
            list[JapanStat]
        """
        data = self._get(
            "/getStatsData",
            {
                "statsDataId": stats_data_id,
                "startPosition": start_position,
                "limit": limit,
            },
        )
        results = (data.get("GET_STATS_DATA") or {}).get("STATISTICAL_DATA") or {}
        data_inf = (results.get("DATA_INF") or {}).get("VALUE") or []
        # `VALUE` can be a single dict (when one row) or a list of dicts
        if isinstance(data_inf, dict):
            data_inf = [data_inf]

        out: list[JapanStat] = []
        for row in data_inf:
            try:
                value = float(row.get("$") or 0)
            except (TypeError, ValueError):
                continue
            time_period = row.get("@time") or row.get("@cat02") or ""
            label_bits = [row.get(k, "") for k in ("@cat01", "@cat02", "@area") if row.get(k)]
            out.append(
                JapanStat(
                    stats_id=stats_data_id,
                    series_label=" / ".join(label_bits) if label_bits else "value",
                    time_period=str(time_period),
                    value=value,
                    unit=row.get("@unit", ""),
                )
            )
        return out

    # ── convenience ────────────────────────────────────────────────

    def cpi_national(self, *, limit: int = 12) -> list[JapanStat]:
        """Latest N months of national Japan CPI."""
        return self.get_stats_data(STATS_IDS["cpi_national"], limit=limit)

    def retail_sales(self, *, limit: int = 12) -> list[JapanStat]:
        """Japan retail sales index — consumer demand proxy."""
        return self.get_stats_data(STATS_IDS["retail_sales"], limit=limit)
