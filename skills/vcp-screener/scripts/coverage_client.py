"""VCP-only failure accounting without changing the generated FMP client."""

from __future__ import annotations

import math
from datetime import date

from fmp_client import FMPClient

# The longest RS return needs 252 sessions plus its initial close; the
# 200-session moving-average comparison also needs 22 earlier sessions.
MIN_SCREEN_HISTORY = 253


class CoverageFMPClient(FMPClient):
    """Retain only reason codes, never provider bodies, keys or request URLs."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.coverage_failures = {}
        self._coverage_attempts = []

    def _warn_fallback(self, base_url, is_last, reason):
        if reason:
            if "HTTP 402" in reason or (
                "HTTP 403" in reason and "legacy endpoint" in reason.lower()
            ):
                code = "plan_gated"
            elif any(text in reason for text in ("HTTP ", "request exception", "rate limit")):
                code = "provider_error"
            elif "no rows" in reason:
                code = "missing_data"
            else:
                code = "invalid_data"
            self._coverage_attempts.append(code)
        super()._warn_fallback(base_url, is_last, reason)

    def _request_with_fallback(self, endpoint_key, symbols_str, extra_params=None):
        self._coverage_attempts = []
        data = super()._request_with_fallback(endpoint_key, symbols_str, extra_params)
        codes = self._coverage_attempts
        default = "provider_error" if self._disabled_endpoints else "missing_data"
        reason = next(
            (c for c in ("plan_gated", "provider_error", "invalid_data") if c in codes), default
        )
        for symbol in symbols_str.split(","):
            key = (endpoint_key, symbol)
            if data:
                self.coverage_failures.pop(key, None)
            else:
                self.coverage_failures[key] = reason
        return data


def failure_reason(client, endpoint, symbol, default="missing_data"):
    return getattr(client, "coverage_failures", {}).get((endpoint, symbol), default)


def _valid_number(value, *, positive=True):
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and (value > 0 if positive else value >= 0)
    )


def quote_problem(quote):
    """Distinguish incomplete quote evidence from a valid pre-filter rejection."""
    if not isinstance(quote, dict):
        return "missing_data"
    values = [quote.get(k) for k in ("price", "yearHigh", "yearLow")]
    volume = quote.get("avgVolume") or quote.get("volume")
    if any(value is None for value in values) or volume is None:
        return "missing_data"
    if not all(_valid_number(value) for value in values) or not _valid_number(
        volume, positive=False
    ):
        return "invalid_data"
    return None


def _session_date(value):
    """Parse a strict ISO YYYY-MM-DD session date; None when not canonical."""
    if not isinstance(value, str) or len(value) != 10:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def history_problem(rows, *, benchmark=False, check_values=True):
    """Require 253 distinct, newest-first dated sessions with finite observations.

    Failures return fixed codes only: missing_data, invalid_data, insufficient_history,
    duplicate_sessions, unordered_history. Row contents are never echoed.
    Screening defers values to each calculator's consumed window with check_values=False.
    """
    if not rows:
        return "missing_data"
    if not isinstance(rows, list):
        return "invalid_data"
    if len(rows) < MIN_SCREEN_HISTORY:
        return "insufficient_history"
    previous = None
    for row in rows:
        if not isinstance(row, dict):
            return "invalid_data"
        session = row.get("date")
        if session is None:
            return "missing_data"
        session = _session_date(session)
        if session is None:
            return "invalid_data"
        # Calculators index bar[0] as the newest bar, so require strictly newest-first
        # dates: an equal date is not a new session, a later one is out of order.
        if previous is not None:
            if session == previous:
                return "duplicate_sessions"
            if session > previous:
                return "unordered_history"
        previous = session
        if not check_values:
            continue
        prices = [row.get("close", row.get("adjClose"))]
        if not benchmark:
            prices += [row.get("high"), row.get("low")]
        if any(value is None for value in prices) or (not benchmark and row.get("volume") is None):
            return "missing_data"
        if not all(_valid_number(value) for value in prices):
            return "invalid_data"
        if not benchmark and not _valid_number(row["volume"], positive=False):
            return "invalid_data"
    return None
