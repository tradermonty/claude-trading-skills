"""Short-term acceleration metrics for parabolic detection.

Captures three ideas Qullamaggie flags as "exhaustion":

- ``return_n_days_pct``: total return over a recent N-day window. Inputs
  use chronological order so the latest close is at the end.
- ``consecutive_green_days``: how many consecutive bars closed up over
  the most recent run. A streak of 3-5+ is the canonical Parabolic Short
  setup.
- ``acceleration_ratio``: average daily return over the last 3 sessions
  divided by the average daily return over the last 10 sessions. Values
  > 1.5 mean the move is *accelerating* — the curve is bending up, not
  just trending.
"""

from __future__ import annotations


def return_pct(closes: list[float], days: int) -> float | None:
    """Total return over the trailing ``days`` bars, in percent.

    Returns ``None`` if there are not enough closes (we need at least
    ``days + 1`` to compute a return). Returns ``None`` if the reference
    close is non-positive.
    """
    if days <= 0:
        raise ValueError(f"days must be positive, got {days}")
    if len(closes) < days + 1:
        return None
    base = closes[-days - 1]
    if base <= 0:
        return None
    latest = closes[-1]
    return (latest - base) / base * 100.0


def consecutive_green_days(opens: list[float], closes: list[float]) -> int:
    """Count consecutive bars with ``close > open`` from the latest backwards."""
    if len(opens) != len(closes) or not closes:
        return 0
    streak = 0
    for o, c in zip(reversed(opens), reversed(closes)):
        if c > o:
            streak += 1
        else:
            break
    return streak


def _avg_daily_return(closes: list[float], window: int) -> float | None:
    if len(closes) < window + 1:
        return None
    base = closes[-window - 1]
    if base <= 0:
        return None
    # Geometric-ish: simple average of daily simple returns (sufficient for ranking)
    rets = []
    for i in range(-window, 0):
        prev = closes[i - 1]
        curr = closes[i]
        if prev <= 0:
            continue
        rets.append((curr - prev) / prev)
    if not rets:
        return None
    return sum(rets) / len(rets)


def acceleration_ratio(
    closes: list[float], short_window: int = 3, long_window: int = 10
) -> float | None:
    """Ratio of recent average daily return over a longer-window average.

    Returns ``None`` if either window cannot be computed or the long-window
    average is non-positive (no acceleration if the move was flat / down).
    """
    short_avg = _avg_daily_return(closes, short_window)
    long_avg = _avg_daily_return(closes, long_window)
    if short_avg is None or long_avg is None or long_avg <= 0:
        return None
    return short_avg / long_avg


def calculate_acceleration(
    opens: list[float],
    closes: list[float],
) -> dict:
    """Aggregate acceleration metrics into one dict for downstream scoring."""
    return {
        "return_3d_pct": return_pct(closes, 3),
        "return_5d_pct": return_pct(closes, 5),
        "return_10d_pct": return_pct(closes, 10),
        "return_15d_pct": return_pct(closes, 15),
        "consecutive_green_days": consecutive_green_days(opens, closes),
        "acceleration_ratio_3_over_10": acceleration_ratio(closes, 3, 10),
    }
