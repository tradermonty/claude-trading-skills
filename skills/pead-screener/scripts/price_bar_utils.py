"""Fail closed on consumed PEAD price-bar gaps."""

from _price_bars import find_bar_gaps, read_price


class PriceBarGap(ValueError):
    """A consumed bar cannot support a PEAD signal."""


def require_bars(bars, fields, *, date_key="date"):
    gaps = find_bar_gaps(bars, fields, zero_ok=("volume",), order="newest_first", date_key=date_key)
    if gaps["bad_bars"]:
        raise PriceBarGap(
            f"Unavailable: missing or invalid {', '.join(fields)}; "
            f"bar dates: {', '.join(gaps['bad_dates'])}"
        )


def require_price(bar, field, *, date_key="date"):
    require_bars([bar], [field], date_key=date_key)
    return read_price(bar, field, allow_zero=field == "volume")
