"""ATR (Average True Range) and True Range helpers.

Adapted from skills/vcp-screener/scripts/calculators/vcp_pattern_calculator.py
(``_calculate_atr`` / ``_true_range``). Inputs are always in chronological
order (oldest first) — the bar_normalizer enforces this contract upstream.
"""

from __future__ import annotations


def true_range(high: float, low: float, prev_close: float) -> float:
    """Single-bar True Range.

    TR = max(high - low, |high - prev_close|, |low - prev_close|).
    """
    return max(high - low, abs(high - prev_close), abs(low - prev_close))


def calculate_atr(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    period: int = 14,
) -> float:
    """Average True Range over the most recent ``period`` bars.

    Args:
        highs: High prices in chronological order.
        lows: Low prices in chronological order.
        closes: Close prices in chronological order.
        period: ATR window in bars (default 14).

    Returns:
        ATR value, or ``0.0`` if there are fewer than ``period + 1`` bars.
    """
    n = len(highs)
    if n < period + 1 or len(lows) != n or len(closes) != n:
        return 0.0

    true_ranges = [true_range(highs[i], lows[i], closes[i - 1]) for i in range(1, n)]
    if len(true_ranges) < period:
        return 0.0
    return sum(true_ranges[-period:]) / period
