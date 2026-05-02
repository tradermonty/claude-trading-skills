"""SEC Rule 201 (Short Sale Restriction) state tracker.

Rule 201 fires whenever a security drops 10 % or more from its prior-day
regular-session close. While active it bans short sales at or below the
national best bid for the rest of that day **and** the next trading day,
which Phase 2 must surface as a blocking reason.

Contract notes:
- ``prior_regular_close`` is the **regular-session 4:00 PM ET close**, not
  the after-hours quote. The screener inherits this value from Phase 1's
  ``key_levels.prior_close`` (which comes from
  ``historical-price-eod/full``). Phase 2 never re-pulls the previous day's
  close from FMP's ``quote`` endpoint because that field can drift to the
  aftermarket value.
- The state file lives in ``state/parabolic_short/ssr_state_<date>.json``
  so a re-run of generate_pre_market_plan can roll yesterday's
  ``ssr_triggered_today`` forward into today's
  ``ssr_carryover_from_prior_day`` deterministically.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

SSR_DROP_THRESHOLD_PCT = 10.0


def evaluate_ssr(
    *,
    prior_regular_close: float,
    current_price: float,
    prior_day_state: dict | None = None,
) -> dict:
    """Compute the SSR state for a single symbol on the trading day.

    Args:
        prior_regular_close: yesterday's 4:00 PM ET close (regular session).
        current_price: latest known intraday or premarket print.
        prior_day_state: yesterday's stored SSR state, if any. When
            ``ssr_triggered_today`` was True yesterday, today inherits
            ``ssr_carryover_from_prior_day=True`` per Rule 201.
    """
    if prior_regular_close <= 0:
        raise ValueError(f"prior_regular_close must be positive: {prior_regular_close}")

    drop_pct = (prior_regular_close - current_price) / prior_regular_close * 100.0
    triggered_today = drop_pct >= SSR_DROP_THRESHOLD_PCT

    carryover = bool(prior_day_state and prior_day_state.get("ssr_triggered_today"))

    return {
        "ssr_triggered_today": triggered_today,
        "ssr_carryover_from_prior_day": carryover,
        "prior_regular_close": prior_regular_close,
        "prior_regular_close_source": "phase1_inherit",
        "uptick_rule_active": triggered_today or carryover,
        "drop_from_prior_close_pct": round(drop_pct, 2),
    }


def state_path(state_dir: str | Path, ticker: str, as_of: str) -> Path:
    """Where today's per-symbol SSR state file lives."""
    return Path(state_dir) / f"ssr_state_{ticker}_{as_of}.json"


def load_prior_day_state(state_dir: str | Path, ticker: str, as_of: str) -> dict | None:
    """Read yesterday's state file (if any) so today can compute carryover.

    Calendar-day arithmetic is fine here — Rule 201 carryover is
    "next trading day" but a strict trading-calendar lookup is overkill
    for a planner that runs daily. If yesterday is a weekend, no file
    exists and we return ``None``.
    """
    try:
        prior = (date.fromisoformat(as_of) - timedelta(days=1)).isoformat()
    except (TypeError, ValueError):
        return None
    p = state_path(state_dir, ticker, prior)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def save_state(state_dir: str | Path, ticker: str, as_of: str, state: dict) -> Path:
    """Persist today's state for tomorrow's carryover lookup."""
    p = state_path(state_dir, ticker, as_of)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(state)
    payload["written_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    p.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return p
