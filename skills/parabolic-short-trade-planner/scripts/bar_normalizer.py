"""Bar order normalization — the single boundary between raw FMP output
and calculator input.

FMP's ``historical-price-eod/full`` returns rows in most-recent-first order.
Calculators in this skill expect chronological (oldest-first) input. Call
:func:`normalize_bars` once at the screen entry point so each calculator can
assume a consistent contract.

Other responsibilities handled here (kept on the boundary, not inside the
HTTP client):

- De-duplicate rows that share the same ``date``. The latest occurrence wins
  (a re-fetch arriving after a partial bar is preferred over the partial).
- Optionally warn when consecutive calendar days are missing. This is not an
  error (weekends/holidays are normal) — it's just a hook for callers that
  want to surface unusual gaps.
"""

from __future__ import annotations

import warnings
from datetime import date
from typing import Literal

OutputOrder = Literal["chronological", "recent_first"]


def normalize_bars(
    bars: list[dict],
    output_order: OutputOrder = "chronological",
    *,
    warn_on_gaps: bool = False,
) -> list[dict]:
    """Return ``bars`` sorted in ``output_order`` with duplicates removed.

    Args:
        bars: Iterable of dicts that each carry a ``date`` field formatted
            as ``YYYY-MM-DD`` (the shape FMP returns).
        output_order: ``"chronological"`` (oldest first) or ``"recent_first"``
            (newest first). The argument names the *output*, not the input,
            to remove ambiguity at call sites.
        warn_on_gaps: When ``True``, emit a :class:`UserWarning` for every
            calendar-day gap larger than three days (ignores typical
            weekends).

    Returns:
        A new list — the input is not mutated.

    Raises:
        ValueError: If ``output_order`` is not one of the supported values.
    """
    if output_order not in ("chronological", "recent_first"):
        raise ValueError(
            f"output_order must be 'chronological' or 'recent_first', got {output_order!r}"
        )

    by_date: dict[str, dict] = {}
    for row in bars:
        d = row.get("date")
        if not d:
            continue
        # Last occurrence wins so a fresh re-fetch beats a stale partial bar.
        by_date[d] = row

    chronological = sorted(by_date.values(), key=lambda r: r["date"])

    if warn_on_gaps and len(chronological) > 1:
        for prev, curr in zip(chronological, chronological[1:]):
            try:
                d_prev = date.fromisoformat(prev["date"])
                d_curr = date.fromisoformat(curr["date"])
            except (TypeError, ValueError):
                continue
            gap = (d_curr - d_prev).days
            if gap > 3:
                warnings.warn(
                    f"bar_normalizer: gap of {gap} calendar days between "
                    f"{prev['date']} and {curr['date']}",
                    stacklevel=2,
                )

    if output_order == "chronological":
        return chronological
    return list(reversed(chronological))
