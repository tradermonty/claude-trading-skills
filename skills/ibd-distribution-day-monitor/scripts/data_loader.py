"""FMP wrapper + OHLCV quality validation.

Returns most-recent-first list[dict] (no pandas). Records data quality
issues as audit_flags / skipped_sessions for the report layer.
"""

from __future__ import annotations

import math
from typing import Any


def coerce_close(value: Any) -> float | None:
    """Return a finite positive close, excluding booleans and unsupported types."""
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        number = float(value)
    except (ValueError, OverflowError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def _history_rows(payload: Any) -> list[dict]:
    if isinstance(payload, dict):
        return list(payload.get("historical") or [])
    if isinstance(payload, list):
        return list(payload)
    return []


def normalize_history(payload: Any) -> list[dict]:
    """Copy rows, normalize closes, and preserve dated session slots across gaps."""
    return [dict(row, close=coerce_close(row.get("close"))) for row in _history_rows(payload)]


def validate_history_quality(history: list[dict]) -> tuple[list[str], list[dict]]:
    """Identify data quality problems.

    Returns (audit_flags, skipped_sessions). Each skipped session has
    {date, reason}. The caller's downstream code is expected to treat
    skipped sessions as no-op (no DD detection / enrichment for them).
    """
    flags: list[str] = []
    skipped: list[dict] = []
    for row in history:
        date = row.get("date")
        close = row.get("close")
        volume = row.get("volume")

        if close is None:
            skipped.append({"date": date, "reason": "missing_close"})
        elif coerce_close(close) is None:
            skipped.append({"date": date, "reason": "invalid_close"})

        if volume is None:
            skipped.append({"date": date, "reason": "missing_volume"})
        elif volume <= 0:
            skipped.append({"date": date, "reason": "invalid_volume"})

    if skipped:
        flags.append("data_quality_warnings")
    return flags, skipped


def fetch_ohlcv(
    client: Any,
    symbol: str,
    days: int,
) -> tuple[list[dict], dict]:
    """Fetch most-recent-first OHLCV for `symbol` via the provided FMP client.

    Returns (history, audit) where audit has:
        - data_source: "fmp"
        - symbol: str
        - days_requested: int
        - sessions_loaded: int
        - audit_flags: list[str]
        - skipped_sessions: list[dict]
    """
    audit: dict = {
        "data_source": "fmp",
        "symbol": symbol,
        "days_requested": days,
        "sessions_loaded": 0,
        "audit_flags": [],
        "skipped_sessions": [],
    }

    payload = client.get_historical_prices(symbol, days=days)
    raw_history = _history_rows(payload)
    history = normalize_history(raw_history)

    if not history:
        audit["audit_flags"].append("no_data_returned")
        return [], audit

    flags, skipped = validate_history_quality(raw_history)
    audit["sessions_loaded"] = len(history)
    audit["audit_flags"].extend(flags)
    audit["skipped_sessions"] = skipped
    return history, audit


def build_fmp_client(api_key: str | None = None, max_api_calls: int = 200):
    """Lazy import to avoid pulling requests in unit tests that mock the client."""
    from fmp_client import FMPClient

    return FMPClient(api_key=api_key, max_api_calls=max_api_calls)
