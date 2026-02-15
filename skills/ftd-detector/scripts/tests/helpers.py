"""Importable test helpers for FTD Detector tests"""


def make_bar(close, volume=1_000_000, date="2026-01-15", open_=None, high=None, low=None):
    """Create a single OHLCV bar dict."""
    if open_ is None:
        open_ = close
    if high is None:
        high = close * 1.005
    if low is None:
        low = close * 0.995
    return {
        "date": date,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }


def make_correction_history(peak=100.0, decline_pct=5.0, down_days=5, base_volume=1_000_000):
    """
    Build a synthetic chronological history with a clear correction.

    Returns history with: flat lead-in -> peak -> decline -> swing low.
    Total length ~ 20 bars (enough for find_swing_low lookback).
    """
    bars = []
    day = 0

    # 10-day flat lead-in near peak
    for i in range(10):
        price = peak * (0.98 + 0.02 * (i / 10))
        bars.append(make_bar(price, base_volume, date=f"day-{day:03d}"))
        day += 1

    # Peak day
    bars.append(make_bar(peak, base_volume, date=f"day-{day:03d}"))
    day += 1

    # Decline phase: down_days of steady decline to reach target
    low_price = peak * (1 - decline_pct / 100)
    step = (peak - low_price) / down_days
    for i in range(1, down_days + 1):
        price = peak - step * i
        bars.append(make_bar(price, base_volume, date=f"day-{day:03d}"))
        day += 1

    return bars, day


def make_rally_history(
    peak=100.0,
    decline_pct=5.0,
    down_days=5,
    rally_days=10,
    rally_gain_per_day=0.3,
    base_volume=1_000_000,
    ftd_day=None,
    ftd_gain_pct=1.5,
    ftd_volume_mult=1.5,
):
    """
    Build a full correction -> rally history with optional FTD.

    Args:
        ftd_day: If set, inject an FTD-qualifying day at this rally day number.
        ftd_gain_pct: Gain percentage for the FTD day.
        ftd_volume_mult: Volume multiplier for FTD day vs previous day.

    Returns (history, swing_low_idx, day1_idx, ftd_day_idx).
    """
    bars, day = make_correction_history(peak, decline_pct, down_days, base_volume)
    swing_low_idx = len(bars) - 1
    swing_low_price = bars[-1]["close"]

    day1_idx = None
    ftd_day_idx = None
    prev_close = swing_low_price

    for rally_num in range(1, rally_days + 1):
        vol = base_volume

        if ftd_day is not None and rally_num == ftd_day:
            # FTD day: large gain, higher volume than previous day
            gain = ftd_gain_pct / 100
            price = prev_close * (1 + gain)
            vol = int(base_volume * ftd_volume_mult)
            ftd_day_idx = len(bars)
        else:
            price = prev_close * (1 + rally_gain_per_day / 100)

        bars.append(
            make_bar(
                price,
                vol,
                date=f"day-{day:03d}",
                low=price * 0.997,
            )
        )
        if day1_idx is None and price > prev_close:
            day1_idx = len(bars) - 1
        prev_close = price
        day += 1

    return bars, swing_low_idx, day1_idx, ftd_day_idx
