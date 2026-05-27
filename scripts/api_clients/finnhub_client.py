"""Finnhub client — economic calendar + earnings (free tier, no card).

Useful as a free alternative to FMP for the economic-calendar-fetcher and
earnings-calendar skills, which currently require FMP.

Free tier: 60 calls/min, US data only on free.
Docs: https://finnhub.io/docs/api
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Optional

try:
    import requests
except ImportError as e:
    raise ImportError("finnhub_client requires `requests`. Install: pip install requests") from e

from .load_env import get_api_key

BASE = "https://finnhub.io/api/v1"


@dataclass
class EconEvent:
    """Economic calendar entry."""

    country: str
    event: str
    time: datetime
    actual: Optional[float]
    estimate: Optional[float]
    previous: Optional[float]
    impact: str  # "low" / "medium" / "high"
    unit: Optional[str] = None


@dataclass
class EarningsEvent:
    """Earnings calendar entry."""

    symbol: str
    date: date
    hour: str  # "bmo" (before market open) / "amc" (after market close) / "dmh" (during market hours)
    eps_estimate: Optional[float]
    eps_actual: Optional[float]
    revenue_estimate: Optional[float]
    revenue_actual: Optional[float]
    year: int
    quarter: int


class FinnhubClient:
    """Finnhub REST client."""

    def __init__(self, api_key: Optional[str] = None, timeout: int = 20):
        self.api_key = api_key or get_api_key("FINNHUB_API_KEY")
        self.timeout = timeout
        self._session = requests.Session()

    def _get(self, path: str, params: Optional[dict] = None) -> Any:
        params = dict(params or {})
        params["token"] = self.api_key
        r = self._session.get(f"{BASE}{path}", params=params, timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    # ── calendars ───────────────────────────────────────────────────

    def economic_calendar(
        self, *, from_date: Optional[str] = None, to_date: Optional[str] = None
    ) -> list[EconEvent]:
        """Macro events (CPI, FOMC, employment) for date range.

        Default range: next 7 days from today.
        """
        if not from_date:
            from_date = date.today().isoformat()
        if not to_date:
            to_date = (date.today() + timedelta(days=7)).isoformat()
        data = self._get("/calendar/economic", {"from": from_date, "to": to_date})
        events = (data or {}).get("economicCalendar") or []
        out: list[EconEvent] = []
        for e in events:
            try:
                ts = datetime.fromisoformat(e["time"].replace(" ", "T"))
            except (KeyError, ValueError):
                ts = datetime.now()
            out.append(
                EconEvent(
                    country=e.get("country", ""),
                    event=e.get("event", ""),
                    time=ts,
                    actual=e.get("actual"),
                    estimate=e.get("estimate"),
                    previous=e.get("prev"),
                    impact=str(e.get("impact", "low")).lower(),
                    unit=e.get("unit"),
                )
            )
        return out

    def earnings_calendar(
        self,
        *,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        symbol: Optional[str] = None,
    ) -> list[EarningsEvent]:
        """Earnings reports for date range or single symbol."""
        if not from_date:
            from_date = date.today().isoformat()
        if not to_date:
            to_date = (date.today() + timedelta(days=7)).isoformat()
        params: dict[str, Any] = {"from": from_date, "to": to_date}
        if symbol:
            params["symbol"] = symbol.upper()
        data = self._get("/calendar/earnings", params)
        events = (data or {}).get("earningsCalendar") or []
        out: list[EarningsEvent] = []
        for e in events:
            try:
                d = date.fromisoformat(e["date"])
            except (KeyError, ValueError):
                continue
            out.append(
                EarningsEvent(
                    symbol=e.get("symbol", ""),
                    date=d,
                    hour=str(e.get("hour", "")).lower(),
                    eps_estimate=e.get("epsEstimate"),
                    eps_actual=e.get("epsActual"),
                    revenue_estimate=e.get("revenueEstimate"),
                    revenue_actual=e.get("revenueActual"),
                    year=int(e.get("year") or 0),
                    quarter=int(e.get("quarter") or 0),
                )
            )
        return out

    # ── company data ────────────────────────────────────────────────

    def company_news(self, symbol: str, *, days: int = 7) -> list[dict]:
        """Company-specific news from past N days."""
        end = date.today()
        start = end - timedelta(days=days)
        return self._get(
            "/company-news",
            {"symbol": symbol.upper(), "from": start.isoformat(), "to": end.isoformat()},
        ) or []

    def quote(self, symbol: str) -> dict[str, Any]:
        """Real-time quote: c (current), h (high), l (low), o (open), pc (prev close), t (timestamp)."""
        return self._get("/quote", {"symbol": symbol.upper()}) or {}
