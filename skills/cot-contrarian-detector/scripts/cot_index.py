#!/usr/bin/env python3
"""Pure COT Index calculation module (Jason Shapiro contrarian methodology, step 1).

No I/O, no network calls — every function takes plain dicts/lists and returns
plain values so it is trivially unit-testable. See
references/cot-index-calculation.md for the formula, lookback rationale, and a
glossary of the FMP CFTC legacy-report field names consumed here.
"""

from __future__ import annotations


def compute_net_position(row: dict) -> int:
    """Net large-speculator ("non-commercial") position for one weekly report row.

    net = noncommPositionsLongAll - noncommPositionsShortAll. Positive = net
    long, negative = net short. Missing fields are treated as 0.
    """
    long_pos = row.get("noncommPositionsLongAll") or 0
    short_pos = row.get("noncommPositionsShortAll") or 0
    return int(long_pos) - int(short_pos)


def compute_cot_index(net_series: list[float], lookback_weeks: int) -> float | None:
    """Classic COT Index: (current - min) / (max - min) * 100 over a lookback window.

    `net_series` must be ordered oldest -> newest; the last element is treated
    as "current". Returns None when there is less than `lookback_weeks` of
    history, or when the window is flat (max == min, the index is undefined).
    """
    if len(net_series) < lookback_weeks:
        return None
    window = net_series[-lookback_weeks:]
    current = window[-1]
    lo = min(window)
    hi = max(window)
    if hi == lo:
        return None
    return (current - lo) / (hi - lo) * 100.0


def compute_oi_normalized_net(row: dict) -> float | None:
    """Net large-speculator position as a fraction of total open interest.

    Returns None when open interest is zero, missing, or non-numeric.
    """
    oi = row.get("openInterestAll")
    try:
        oi = float(oi)
    except (TypeError, ValueError):
        return None
    if oi == 0:
        return None
    return compute_net_position(row) / oi


def classify_extreme(
    index_3y: float | None, threshold_high: float = 90.0, threshold_low: float = 10.0
) -> str:
    """Classify a COT Index value as CROWDED_LONG / CROWDED_SHORT / NEUTRAL.

    Boundaries are inclusive: index_3y == threshold_high -> CROWDED_LONG,
    index_3y == threshold_low -> CROWDED_SHORT. A None index (insufficient
    history) is treated as NEUTRAL — callers that need to distinguish
    "no data" from "not extreme" should check for None before calling this.
    """
    if index_3y is None:
        return "NEUTRAL"
    if index_3y >= threshold_high:
        return "CROWDED_LONG"
    if index_3y <= threshold_low:
        return "CROWDED_SHORT"
    return "NEUTRAL"


def sort_dedupe_rows(rows: list[dict]) -> list[dict]:
    """Sort report rows ascending by `date`, deduping same-date rows.

    When two rows share the same `date` string, the later one in the input
    list wins (assumed to be the more recently fetched / corrected value).
    Rows without a `date` key are dropped rather than silently kept out of
    order.
    """
    by_date: dict[str, dict] = {}
    for row in rows:
        date_key = row.get("date")
        if date_key is None:
            continue
        by_date[date_key] = row
    return [by_date[d] for d in sorted(by_date)]


def compute_week_over_week_change(net_series: list[float]) -> float | None:
    """Change in net position from the prior week to the current (last) week.

    Returns None when fewer than 2 data points are available.
    """
    if len(net_series) < 2:
        return None
    return net_series[-1] - net_series[-2]
