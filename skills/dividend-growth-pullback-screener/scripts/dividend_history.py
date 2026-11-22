"""Bundled regular-dividend eligibility contract for both dividend screeners.

Explicit labels only: do not infer special cash or split adjustments from amounts.
"""

from __future__ import annotations

import math
from datetime import date

_SPECIAL = ("special", "supplemental", "one-time", "one time", "extra")


def regular_dividends(payload, as_of: date, *, completed_only=False):
    """Return dated positive regular cash rows, or None for unusable evidence."""
    if not isinstance(as_of, date) or not isinstance(payload, dict):
        return None
    rows = payload.get("historical")
    if not isinstance(rows, list):
        return None
    result = []
    for row in rows:
        if not isinstance(row, dict):
            return None
        tags = [row.get("label"), row.get("frequency")]
        if any(word in tag.lower() for tag in tags if isinstance(tag, str) for word in _SPECIAL):
            continue
        try:
            day = date.fromisoformat(str(row.get("date", ""))[:10])
        except ValueError:
            return None
        if day > as_of or (completed_only and day.year >= as_of.year):
            continue
        value = row.get("dividend")
        if isinstance(value, bool) or not isinstance(value, (str, int, float)):
            return None
        try:
            amount = float(value)
        except (ValueError, OverflowError):
            return None
        if not math.isfinite(amount) or amount <= 0:
            return None
        result.append((day, amount, row.get("frequency")))
    return sorted(result, key=lambda row: row[0])


def annual_totals(rows):
    """Aggregate eligible cash without changing the year or overflowing sums."""
    buckets = {}
    for day, amount, _ in rows:
        buckets.setdefault(day.year, []).append(amount)
    try:
        result = {year: math.fsum(amounts) for year, amounts in buckets.items()}
    except OverflowError:
        return None
    return result if all(math.isfinite(value) and value > 0 for value in result.values()) else None
