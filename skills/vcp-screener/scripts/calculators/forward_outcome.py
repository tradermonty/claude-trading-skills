#!/usr/bin/env python3
"""Forward Outcome Calculator — what happened after the VCP was detected.

Used by the historical single-ticker scanner to label each detected VCP with
the trade-outcome it would have produced if entered at the pivot:

- ``breakout``         : close > pivot within max_window_days
- ``stop_hit``         : close < stop within window, before any breakout
- ``timeout``          : neither hit; window expired
- ``insufficient_data``: fewer than 1 forward bar available

Conventions:
- ``historical`` is most-recent-first (index 0 = most recent bar).
- ``as_of_offset`` is the MRF index treated as the detection day; forward bars
  are ``historical[0 : as_of_offset]`` walked oldest-to-newest.
- ``max_gain_pct`` and ``max_loss_pct`` are measured against the as-of close,
  not the pivot; they describe the trajectory regardless of outcome.
"""

from typing import Optional


def calculate_forward_outcome(
    historical_prices: list[dict],
    as_of_offset: int,
    pivot_price: float,
    stop_price: Optional[float] = None,
    max_window_days: int = 60,
) -> dict:
    """Compute the trade outcome for a VCP detected at ``historical_prices[as_of_offset]``.

    Args:
        historical_prices: Most-recent-first OHLCV bars.
        as_of_offset: Index of the detection bar. Forward window is the bars
            with smaller indices (i.e., more recent than the as-of bar).
        pivot_price: Breakout trigger. First forward bar whose close exceeds
            this is the breakout day.
        stop_price: Stop-loss level (typically the last contraction's low). If
            None, stop_hit is never reported. First forward bar whose close
            falls below this — before any breakout — is the stop-hit day.
        max_window_days: Number of forward bars to evaluate (default 60).

    Returns:
        Dict with the schema documented at the top of this module.
    """
    empty = {
        "outcome_type": "insufficient_data",
        "days_to_outcome": None,
        "exit_price": None,
        "exit_date": None,
        "max_gain_pct": None,
        "max_loss_pct": None,
        "pivot_price": pivot_price,
        "stop_price": stop_price,
        "bars_available": 0,
        "bars_evaluated": 0,
    }

    if not historical_prices or as_of_offset <= 0 or as_of_offset >= len(historical_prices):
        return empty

    as_of_close = historical_prices[as_of_offset].get("close")
    if as_of_close in (None, 0):
        return empty

    # Forward bars in oldest-to-newest order (start at the bar right after
    # the as-of bar and walk toward the present).
    forward = list(reversed(historical_prices[:as_of_offset]))
    bars_available = len(forward)
    if bars_available == 0:
        return empty

    window = forward[:max_window_days]

    outcome_type = "timeout"
    days_to_outcome: Optional[int] = None
    exit_price: Optional[float] = None
    exit_date: Optional[str] = None
    max_gain_pct: Optional[float] = None
    max_loss_pct: Optional[float] = None

    # Walk the entire forward window so max_gain / max_loss describe the full
    # trajectory regardless of where the outcome is triggered. The outcome
    # itself is set only at the first triggering bar.
    for i, bar in enumerate(window, start=1):
        close = bar.get("close")
        if close is None:
            continue

        gain_pct = (close - as_of_close) / as_of_close * 100
        if max_gain_pct is None or gain_pct > max_gain_pct:
            max_gain_pct = gain_pct
        if max_loss_pct is None or gain_pct < max_loss_pct:
            max_loss_pct = gain_pct

        if outcome_type == "timeout":
            if close > pivot_price:
                outcome_type = "breakout"
                days_to_outcome = i
                exit_price = close
                exit_date = bar.get("date")
            elif stop_price is not None and close < stop_price:
                outcome_type = "stop_hit"
                days_to_outcome = i
                exit_price = close
                exit_date = bar.get("date")

    return {
        "outcome_type": outcome_type,
        "days_to_outcome": days_to_outcome,
        "exit_price": round(exit_price, 4) if exit_price is not None else None,
        "exit_date": exit_date,
        "max_gain_pct": round(max_gain_pct, 4) if max_gain_pct is not None else None,
        "max_loss_pct": round(max_loss_pct, 4) if max_loss_pct is not None else None,
        "pivot_price": pivot_price,
        "stop_price": stop_price,
        "bars_available": bars_available,
        "bars_evaluated": len(window),
    }
