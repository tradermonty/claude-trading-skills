"""Daily price evidence via this skill's generated FMP transport.

The network client is loaded lazily; manual/keyless thesis operations stay offline.
"""

from __future__ import annotations

import importlib.util
import math
import os
import re
import sys
import urllib.error
from datetime import date
from pathlib import Path


def _client_class():
    """Load our adjacent generated client, never another skill's fmp_client."""
    name = "_trader_memory_core_generated_fmp"
    path = Path(__file__).resolve().with_name("fmp_client.py")
    module = sys.modules.get(name)
    if module is None or Path(module.__file__).resolve() != path:
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        try:
            spec.loader.exec_module(module)
        except BaseException:
            sys.modules.pop(name, None)
            raise
    return module.FMPClient


def _date(value):
    try:
        parsed = date.fromisoformat(value)
        if parsed.isoformat() == value:
            return parsed
    except (TypeError, ValueError):
        pass
    raise ValueError("Invalid FMP price date") from None


class FMPPriceAdapter:
    """Fetch daily closes (adjClose when supplied, otherwise provider close)."""

    def __init__(self, api_key: str | None = None):
        self.api_key = (api_key or os.environ.get("FMP_API_KEY") or "").strip()
        if not self.api_key:
            raise ValueError("FMP API key required. Set FMP_API_KEY env var or pass api_key.")

    def get_daily_closes(self, ticker: str, from_date: str, to_date: str) -> list[dict]:
        """Return validated in-range daily closes, oldest first.

        Use stable full history with the exact inclusive requested range. Empty
        history returns []; transport failures raise a fixed-message URLError;
        malformed evidence raises ValueError. No legacy endpoint fallback.
        """
        start, end = _date(from_date), _date(to_date)
        if start > end:
            raise ValueError("Invalid FMP price date range")
        if not isinstance(ticker, str) or not re.fullmatch(
            r"[A-Za-z0-9^][A-Za-z0-9.^=/:-]*", ticker
        ):
            raise ValueError("Invalid FMP price symbol")
        client = _client_class()(api_key=self.api_key)
        try:
            data = client.fetch_memory_history(ticker, from_date, to_date)
        finally:
            client.session.close()
        if data is None and client._last_error is not None:
            # The transport retains its shared redacted diagnostics. Do not
            # propagate its response/exception text into the calling review log.
            raise urllib.error.URLError("FMP price request failed") from None
        if not isinstance(data, list):
            raise ValueError("Invalid FMP price data")

        result = []
        seen = set()
        symbol = ticker.upper().replace("-", ".")
        try:
            for item in data:
                if not isinstance(item, dict):
                    raise ValueError
                observed_symbol = item.get("symbol", ticker)
                if (
                    not isinstance(observed_symbol, str)
                    or observed_symbol.upper().replace("-", ".") != symbol
                ):
                    raise ValueError
                day = _date(item.get("date"))
                if not start <= day <= end:
                    continue
                close = item["adjClose"] if "adjClose" in item else item["close"]
                if (
                    isinstance(close, bool)
                    or not isinstance(close, (int, float))
                    or not math.isfinite(close)
                    or close <= 0
                ):
                    raise ValueError
                if day in seen:
                    raise ValueError
                seen.add(day)
                result.append({"date": day.isoformat(), "close": float(close)})
        except (KeyError, TypeError, ValueError, OverflowError):
            raise ValueError("Invalid FMP price data") from None
        return sorted(result, key=lambda item: item["date"])
