"""FTD event health: a warning candle and a failed rally are different facts."""

from _price_bars import find_bar_gaps, read_price


def assess_lifecycle(history, ftd_idx, rally_low=None):
    """Use the explicit rally low; never infer a rally anchor from the FTD.

    ``rally_low`` is the attempt's frozen reference: the lowest intraday low of
    the pullback segment the attempt started from, through Day 1. Intraday
    lows strictly below it fail the rally (equality holds). A close below
    the FTD candle low is a warning only. Missing evidence is unavailable.
    """
    window = history[ftd_idx:]
    reference = read_price({"low": rally_low}, "low")
    gaps = find_bar_gaps(window, ("close", "low"), order="chronological")
    if not window or reference is None or gaps["bad_bars"]:
        return {
            "invalidated": None,
            "warning": None,
            "rally_low": reference,
            "ftd_low": None,
            "data_gap": True,
            "reason": "Data gap: FTD lifecycle unavailable: valid rally reference low and post-FTD close/low required",
        }
    ftd_low = window[0]["low"]
    result = {
        "ftd_date": window[0].get("date"),
        "invalidated": False,
        "warning": False,
        "rally_low": reference,
        "ftd_low": ftd_low,
        "days_since_ftd": len(window) - 1,
        "failure_basis": "intraday low below the rally low",
        "warning_basis": "close below FTD-day low",
    }
    for offset, bar in enumerate(window[1:], 1):
        if not result["warning"] and bar["close"] < ftd_low:
            result.update(warning=True, warning_date=bar.get("date"))
        if bar["low"] < reference:
            result.update(
                invalidated=True,
                invalidation_date=bar.get("date"),
                invalidation_close=bar["close"],
                invalidation_low=bar["low"],
                days_after_ftd=offset,
            )
            break
    return result


def select_ftd_source(market_state):
    """Prefer a still-valid event; use a failed event only if neither is valid."""
    # A failed event must not displace an active, unconfirmed rally elsewhere.
    active = any(
        (market_state.get(key) or {}).get("state") in ("FTD_WINDOW", "RALLY_ATTEMPT")
        for key in ("sp500", "nasdaq")
    )
    detected = [
        key
        for key in ("sp500", "nasdaq")
        if (market_state.get(key, {}).get("ftd") or {}).get("ftd_detected")
    ]
    return next(
        (key for key in detected if market_state[key].get("state") != "FTD_INVALIDATED"),
        detected[0] if detected and not active else None,
    )
