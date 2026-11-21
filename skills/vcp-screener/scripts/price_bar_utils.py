"""VCP adapters for the shared price-bar reader and #798 diagnostics."""

from _price_bars import find_bar_gaps, read_price
from calculators.vcp_pattern_calculator import VCPPriceDataError


def close_bar(bar):
    """Use adjusted close only when the unadjusted close key is absent."""
    return {**bar, "close": bar.get("close", bar.get("adjClose"))}


def read_close(bar):
    return read_price(close_bar(bar), "close")


def find_close_gaps(bars, indices):
    return find_bar_gaps(
        [close_bar(bars[i]) for i in sorted(indices)], ["close"], order="newest_first"
    )


def unavailable_component(data_gaps, **fields):
    return {
        **fields,
        "score": 0,
        "data_available": False,
        "data_gaps": data_gaps,
        "error": str(VCPPriceDataError(data_gaps)),
    }
