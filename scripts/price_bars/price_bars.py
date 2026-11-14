"""Read OHLCV price-bar fields without turning missing data into zero (issue #655).

Standard library only. Vendored into each consumer skill as
``scripts/_price_bars.py`` by ``scripts/generate_price_bars.py``.

A field is *valid* when it is a real number (``numbers.Real``, never ``bool``),
finite, and greater than zero (or at least zero when zero is allowed, as for
volume). Missing keys, ``None``, strings, NaN, +/-inf and non-positive prices are
all *invalid*; callers must treat them as missing data, never as ``0``.
"""

from __future__ import annotations

import math
import numbers
from collections.abc import Iterable, Mapping, Sequence

MAX_BAD_DATES = 10
ORDERS = ("chronological", "newest_first")


def read_price(bar: object, field: str, *, allow_zero: bool = False):
    """Return ``bar[field]`` when it is a valid number, otherwise ``None``.

    The original value (and type) is returned unchanged when valid.
    """
    if not isinstance(bar, Mapping):
        return None
    value = bar.get(field)
    if isinstance(value, bool) or not isinstance(value, numbers.Real):
        return None
    try:
        if not math.isfinite(value):
            return None
    except (TypeError, ValueError, OverflowError):
        return None
    if value > 0 or (allow_zero and value == 0):
        return value
    return None


def _bar_label(bar: object, index: int, date_key: str) -> str:
    if isinstance(bar, Mapping):
        date = bar.get(date_key)
        if date is not None:
            return str(date)
    return f"index {index}"


def find_bar_gaps(
    bars: Sequence[object],
    required: Iterable[str],
    *,
    zero_ok: Iterable[str] = (),
    order: str,
    date_key: str = "date",
) -> dict:
    """Report the bars whose ``required`` fields are missing or invalid.

    Args:
        bars: The exact slice of bars the caller is about to read.
        required: Fields that must be valid on every bar.
        zero_ok: Fields for which ``0`` is valid (typically ``volume``).
        order: ``"chronological"`` (oldest first) or ``"newest_first"``.
            It decides which bad bar is the latest one.
        date_key: Key used to label bad bars (falls back to ``index N``).

    Returns:
        ``{"checked_bars", "bad_bars", "bad_indices", "bad_dates", "latest_bad",
        "required"}``. ``bad_indices`` index into ``bars``; ``bad_dates`` holds
        at most the 10 most recent bad labels in input order; ``latest_bad`` is
        the label of the most recent bad bar, or ``None`` when every bar is valid.
    """
    if order not in ORDERS:
        raise ValueError(f"order must be one of {ORDERS}, got {order!r}")
    fields = list(required)
    zero_fields = set(zero_ok)
    bad_indices = [
        index
        for index, bar in enumerate(bars)
        if any(read_price(bar, field, allow_zero=field in zero_fields) is None for field in fields)
    ]
    labels = [_bar_label(bars[index], index, date_key) for index in bad_indices]
    if order == "chronological":
        bad_dates = labels[-MAX_BAD_DATES:]
        latest_bad = labels[-1] if labels else None
    else:
        bad_dates = labels[:MAX_BAD_DATES]
        latest_bad = labels[0] if labels else None
    return {
        "checked_bars": len(bars),
        "bad_bars": len(bad_indices),
        "bad_indices": bad_indices,
        "bad_dates": bad_dates,
        "latest_bad": latest_bad,
        "required": fields,
    }
