"""IBD-style Distribution Day detection, enrichment, and counting.

All input histories must be most-recent-first (history[0] = evaluation session).
DD at history[k] has age_sessions = k. expired = age > expiration_sessions.

5% invalidation contract (C2):
- Display: high_since = max(high in history[0 : k+1]), DD day high INCLUDED.
- Invalidation: scan history[0 : k] within expiration window only,
  using rule.invalidation_price_source ("high" or "close"). DD day EXCLUDED.
- Today DD (k=0) -> no post-DD sessions -> invalidated = False, but
  high_since = DD day's intraday high (not None).
"""

from __future__ import annotations

import math

from models import DDRecord, DistributionDayRule

EPSILON = 1e-12


def detect_distribution_days(
    effective_history: list[dict],
    rule: DistributionDayRule,
) -> tuple[list[DDRecord], list[dict]]:
    """Detect raw Distribution Days (no enrichment).

    Returns (records, skipped_sessions). Records have only detection-time fields.
    """
    records: list[DDRecord] = []
    skipped: list[dict] = []

    for i in range(len(effective_history) - 1):
        today = effective_history[i]
        yesterday = effective_history[i + 1]
        if not _has_valid_detection_pair(today, yesterday):
            skipped.append({"date": today.get("date"), "reason": "missing_or_invalid_close_volume"})
            continue

        pct_change = today["close"] / yesterday["close"] - 1
        volume_up = today["volume"] > yesterday["volume"]
        if pct_change <= rule.min_decline_pct + EPSILON and volume_up:
            volume_change_pct = today["volume"] / yesterday["volume"] - 1
            records.append(
                DDRecord(
                    date=today["date"],
                    dd_index=i,
                    age_sessions=i,
                    close=today["close"],
                    pct_change=pct_change,
                    volume=today["volume"],
                    prev_volume=yesterday["volume"],
                    volume_change_pct=volume_change_pct,
                )
            )
    return records, skipped


def enrich_records(
    records: list[DDRecord],
    effective_history: list[dict],
    rule: DistributionDayRule,
) -> list[DDRecord]:
    """Fill display, invalidation, expiration, and status fields on each record."""
    for r in records:
        k = r.dd_index

        # --- Display: high_since includes DD day (history[0 : k+1]) ---
        sessions_on_or_after_dd = effective_history[0 : k + 1]
        valid_highs = [
            row["high"]
            for row in sessions_on_or_after_dd
            if row.get("high") is not None and row["high"] > 0
        ]
        r.high_since = max(valid_highs) if valid_highs else r.close

        # --- Invalidation: scan history[0 : k] within expiration window ---
        threshold = r.close * (1 + rule.invalidation_gain_pct)
        r.invalidation_price = threshold if math.isfinite(threshold) else None
        ev = _find_invalidation_event(effective_history, k, r.close, rule)
        r.invalidation_date = ev["date"] if ev else None
        r.invalidation_trigger_price = ev["trigger_price"] if ev else None
        r.invalidation_trigger_source = ev["trigger_source"] if ev else None

        # --- Status priority: invalidated > expired > active ---
        if ev is not None:
            r.status = "invalidated"
            r.removal_reason = "invalidated_5pct_gain"
        elif r.age_sessions > rule.expiration_sessions:
            r.status = "expired"
            r.removal_reason = "expired_25_sessions"
        else:
            r.status = "active"
            r.removal_reason = None

        r.expires_in_sessions = max(rule.expiration_sessions - r.age_sessions, 0)
    return records


def count_active_in_window(
    records: list[DDRecord],
    max_age_sessions: int,
) -> int:
    """Count active records within elapsed-session window (age <= max_age_sessions).

    Note: 'within N elapsed sessions' (age 0..N inclusive). NOT '直近 N 取引日'
    (which would be age 0..N-1).
    """
    return sum(1 for r in records if r.status == "active" and r.age_sessions <= max_age_sessions)


def _has_valid_detection_pair(today: dict, yesterday: dict) -> bool:
    """For DD detection: requires close, volume only (high not needed)."""
    for row in (today, yesterday):
        for key in ("close", "volume"):
            v = row.get(key)
            if v is None or v <= 0:
                return False
    return math.isfinite(today["close"] / yesterday["close"] - 1)


def _find_invalidation_event(
    effective_history: list[dict],
    dd_index: int,
    dd_close: float,
    rule: DistributionDayRule,
) -> dict | None:
    """Find the first chronological post-DD session where price crosses 5% threshold.

    Constraints:
    - Scans only post-DD sessions (effective_history[0 : dd_index]).
    - Restricts to expiration_sessions window: event_index >= dd_index - expiration.
    - Iterates oldest-first (chronological) to return the FIRST crossing.
    - Skips rows where row[source] is missing, None, or <= 0.
    - Today DD (dd_index <= 0) -> no scan, returns None.
    """
    if dd_index <= 0:
        return None

    source = rule.invalidation_price_source
    if source not in {"high", "close"}:
        raise ValueError(f"Unsupported invalidation_price_source: {source}")

    threshold = dd_close * (1 + rule.invalidation_gain_pct)
    if not math.isfinite(threshold):
        return None
    min_event_index = max(dd_index - rule.expiration_sessions, 0)

    # Most-recent-first: index dd_index-1 is newest post-DD, min_event_index is oldest in scan.
    # Chronological order = oldest -> newest = min_event_index -> dd_index-1.
    for event_index in range(dd_index - 1, min_event_index - 1, -1):
        row = effective_history[event_index]
        trigger_value = row.get(source)
        if trigger_value is None or trigger_value <= 0:
            continue
        if trigger_value >= threshold:
            return {
                "date": row["date"],
                "trigger_price": trigger_value,
                "trigger_source": source,
                "elapsed_sessions_since_dd": dd_index - event_index,
            }
    return None
