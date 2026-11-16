"""Price validation at market-top component boundaries (issue #655)."""

from collections.abc import Mapping

from _price_bars import find_bar_gaps, read_price


def price(bar, field, fallback=None):
    # Retain an existing fallback only when the primary key is absent.
    if isinstance(bar, Mapping) and field not in bar and fallback:
        field = fallback
    return read_price(bar, field, allow_zero=field == "volume")


def gaps(rows, fields, fallbacks=None, *, order="newest_first"):
    fallbacks = fallbacks or {}
    normalized = []
    for row in rows:
        normalized.append(
            {
                "date": row.get("date") if isinstance(row, Mapping) else None,
                **{field: price(row, field, fallbacks.get(field)) for field in fields},
            }
        )
    result = find_bar_gaps(normalized, fields, zero_ok=("volume",), order=order)
    return result if result["bad_bars"] else None


def unavailable(result, data_gaps):
    return dict(
        result,
        score=50,
        data_available=False,
        data_gaps=data_gaps,
        signal="UNAVAILABLE: Invalid or missing price bars",
    )
