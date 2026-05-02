"""Alpaca implementation of MarketDataAdapter.

Reuses the same auth pattern and 404-graceful contract as
``alpaca_inventory_adapter.py``. The market data host is
``data.alpaca.markets`` for **both** paper and live accounts —
Alpaca's account class only affects the trading API host, not the
market data API.

Free paper accounts get the IEX feed (~15 min delay). The adapter
defaults to ``feed=iex``; pass ``feed='sip'`` if you have a paid
subscription.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, time, timedelta

try:
    import requests
except ImportError as e:  # pragma: no cover - environment check
    raise RuntimeError("alpaca_market_data_adapter requires the `requests` package") from e

from broker_short_inventory_adapter import BrokerNotConfiguredError
from market_clock import (
    ET,
    REGULAR_CLOSE_HOUR,
    REGULAR_CLOSE_MINUTE,
    REGULAR_OPEN_HOUR,
    REGULAR_OPEN_MINUTE,
    to_utc,
)
from market_data_adapter import MarketDataAdapter

DATA_BASE_URL = "https://data.alpaca.markets"
TIMEFRAME = "5Min"
BAR_DURATION = timedelta(minutes=5)

logger = logging.getLogger("parabolic_short.alpaca_market_data")


class AlpacaMarketDataAdapter(MarketDataAdapter):
    def __init__(
        self,
        api_key: str | None = None,
        secret_key: str | None = None,
        paper: bool = True,
        feed: str = "iex",
        timeout: float = 15.0,
    ) -> None:
        self.api_key = api_key or os.getenv("ALPACA_API_KEY")
        self.secret_key = secret_key or os.getenv("ALPACA_SECRET_KEY")
        if not self.api_key or not self.secret_key:
            raise BrokerNotConfiguredError(
                "ALPACA_API_KEY and ALPACA_SECRET_KEY must be set (env vars or constructor args)."
            )
        # Stored for symmetry with the trading adapter; market data
        # endpoint is the same for both account classes.
        self.paper = paper
        self.feed = feed
        self.timeout = timeout
        self.base_url = DATA_BASE_URL

    def _headers(self) -> dict[str, str]:
        return {
            "APCA-API-KEY-ID": self.api_key,
            "APCA-API-SECRET-KEY": self.secret_key,
        }

    def get_bars_5min(
        self,
        symbol: str,
        *,
        session_date: str,
        until_et: datetime,
    ) -> list[dict]:
        if until_et.tzinfo is None:
            raise ValueError("until_et must be timezone-aware")

        # Build the regular-session window in ET, convert to RFC3339 UTC.
        date_obj = datetime.strptime(session_date, "%Y-%m-%d").date()
        open_et = datetime.combine(
            date_obj, time(REGULAR_OPEN_HOUR, REGULAR_OPEN_MINUTE), tzinfo=ET
        )
        close_et = datetime.combine(
            date_obj, time(REGULAR_CLOSE_HOUR, REGULAR_CLOSE_MINUTE), tzinfo=ET
        )
        # End at the earlier of close_et and until_et — there's no point
        # asking Alpaca for bars we'd then discard.
        end_et = min(close_et, until_et)
        if end_et <= open_et:
            return []

        params_base = {
            "timeframe": TIMEFRAME,
            "start": _rfc3339_utc(open_et),
            "end": _rfc3339_utc(end_et),
            "adjustment": "raw",
            "feed": self.feed,
        }

        url = f"{self.base_url}/v2/stocks/{symbol}/bars"
        all_wire_bars: list[dict] = []
        page_token: str | None = None

        while True:
            params = dict(params_base)
            if page_token is not None:
                params["page_token"] = page_token

            response = requests.get(
                url, headers=self._headers(), params=params, timeout=self.timeout
            )

            if response.status_code == 404:
                logger.info(
                    "alpaca.assets_404: %s not in Alpaca asset universe; returning [] bars",
                    symbol,
                )
                return []

            response.raise_for_status()
            payload = response.json()
            page_bars = payload.get("bars") or []
            all_wire_bars.extend(page_bars)
            page_token = payload.get("next_page_token")
            if not page_token:
                break

        return _convert_and_filter(all_wire_bars, session_date=session_date, until_et=until_et)


def _rfc3339_utc(ts_et: datetime) -> str:
    """Convert an ET datetime to ``YYYY-MM-DDTHH:MM:SSZ`` (UTC)."""
    utc = to_utc(ts_et)
    return utc.strftime("%Y-%m-%dT%H:%M:%SZ")


def _convert_and_filter(
    wire_bars: list[dict],
    *,
    session_date: str,
    until_et: datetime,
) -> list[dict]:
    """Normalise Alpaca's wire shape and apply the contract filters.

    Alpaca's bar timestamp ``t`` is the **bar-open** instant (start of
    the 5-minute interval). A bar with ``t = 09:35:00`` covers
    09:35–09:40 and is **not yet confirmed at 09:35** — it confirms at
    09:40 when the next bar starts. The contract Phase 3 needs is
    "only evaluate confirmed bars", so we filter on ``bar_close =
    bar_start + 5 min`` instead of ``bar_start <= until_et``. ``ts_et``
    in the output dict is kept as the bar-open time (the convention the
    rest of the FSM uses for transition timestamps), with the explicit
    documented meaning of "the start of the bar that triggered the
    transition" (i.e. the 5-min interval whose close fired the move).
    """
    open_et = datetime.combine(
        datetime.strptime(session_date, "%Y-%m-%d").date(),
        time(REGULAR_OPEN_HOUR, REGULAR_OPEN_MINUTE),
        tzinfo=ET,
    )
    close_et = datetime.combine(
        datetime.strptime(session_date, "%Y-%m-%d").date(),
        time(REGULAR_CLOSE_HOUR, REGULAR_CLOSE_MINUTE),
        tzinfo=ET,
    )

    out: list[dict] = []
    for wire in wire_bars:
        ts_utc_str = wire["t"]
        # Alpaca returns "...Z" — fromisoformat in 3.11+ handles "Z",
        # but be defensive across Python versions.
        if ts_utc_str.endswith("Z"):
            ts_utc_str = ts_utc_str[:-1] + "+00:00"
        ts_utc = datetime.fromisoformat(ts_utc_str)
        ts_et = ts_utc.astimezone(ET)
        bar_close_et = ts_et + BAR_DURATION

        # Regular-session filter: 09:30 ≤ bar_start < 16:00 ET on the
        # requested session_date.
        if ts_et.date().isoformat() != session_date:
            continue
        if not (open_et <= ts_et < close_et):
            continue
        # Confirmation filter: only include bars whose CLOSE
        # (bar_start + 5 min) is at or before until_et.
        if bar_close_et > until_et:
            continue

        out.append(
            {
                "ts_et": ts_et.isoformat(),
                "o": float(wire["o"]),
                "h": float(wire["h"]),
                "l": float(wire["l"]),
                "c": float(wire["c"]),
                "v": int(wire["v"]),
            }
        )
    return out
