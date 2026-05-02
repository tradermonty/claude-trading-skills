"""Pure-Python numeric helpers for parabolic-short-trade-planner.

No external dependencies (pandas/numpy intentionally avoided to keep the
skill installable as a standalone .skill bundle).
"""

from __future__ import annotations

import math


def sma(values: list[float], period: int) -> float | None:
    """Simple moving average over the most recent ``period`` values.

    Args:
        values: Chronologically ordered numbers (oldest first).
        period: Window size in number of bars.

    Returns:
        The arithmetic mean of the last ``period`` values, or ``None`` if
        ``values`` has fewer than ``period`` entries.
    """
    if period <= 0:
        raise ValueError(f"period must be positive, got {period}")
    if len(values) < period:
        return None
    window = values[-period:]
    return sum(window) / period


def ema(values: list[float], period: int) -> float | None:
    """Exponential moving average using the standard ``2/(period+1)`` smoother.

    The seed is the simple average of the first ``period`` values; subsequent
    bars update the EMA as ``ema = price * alpha + ema_prev * (1 - alpha)``.

    Returns ``None`` if there are fewer than ``period`` values.
    """
    if period <= 0:
        raise ValueError(f"period must be positive, got {period}")
    if len(values) < period:
        return None
    alpha = 2.0 / (period + 1)
    seed = sum(values[:period]) / period
    ema_value = seed
    for v in values[period:]:
        ema_value = v * alpha + ema_value * (1 - alpha)
    return ema_value


def rolling_mean(values: list[float], period: int) -> list[float]:
    """Rolling window mean.

    Returns a list of length ``len(values) - period + 1`` (or empty if the
    series is too short). Each element ``out[i]`` is the mean of
    ``values[i:i + period]``.
    """
    if period <= 0:
        raise ValueError(f"period must be positive, got {period}")
    if len(values) < period:
        return []
    out: list[float] = []
    for i in range(len(values) - period + 1):
        window = values[i : i + period]
        out.append(sum(window) / period)
    return out


def log10_scale(value: float, lo: float, hi: float, max_score: float = 10.0) -> float:
    """Map ``log10(value)`` linearly onto ``[0, max_score]``.

    ``value`` is treated as the underlying (e.g. ADV in dollars). ``lo`` and
    ``hi`` are log-base-10 endpoints (so ``lo=7.0`` means $10M and ``hi=8.5``
    means ~$316M). Values at or below ``lo`` clamp to 0; at or above ``hi``
    clamp to ``max_score``. Non-positive ``value`` clamps to 0.
    """
    if hi <= lo:
        raise ValueError(f"hi ({hi}) must be greater than lo ({lo})")
    if value <= 0:
        return 0.0
    log_v = math.log10(value)
    if log_v <= lo:
        return 0.0
    if log_v >= hi:
        return max_score
    return max_score * (log_v - lo) / (hi - lo)
