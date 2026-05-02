"""Range-expansion metric: latest 5-day average True Range divided by the
prior 20-day ATR.

A value > 2.0 means the current move's daily range has roughly doubled
versus the prior month's volatility — the canonical "blow-off" signature
for parabolic exhaustion.
"""

from __future__ import annotations

from atr_calculator import true_range


def calculate_range_expansion(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    short_window: int = 5,
    long_window: int = 20,
) -> dict:
    """Latest short-window ATR / prior long-window ATR.

    The two windows are non-overlapping by construction:
    - ``recent_avg_tr`` averages the last ``short_window`` true ranges
    - ``baseline_avg_tr`` averages the ``long_window`` true ranges that
      precede that recent block.

    Returns dict with ``recent_avg_tr``, ``baseline_avg_tr``, and
    ``expansion_ratio``. Any value that cannot be computed is ``None``.
    """
    n = len(highs)
    if n < short_window + long_window + 1 or len(lows) != n or len(closes) != n:
        return {
            "recent_avg_tr": None,
            "baseline_avg_tr": None,
            "expansion_ratio": None,
        }

    trs = [true_range(highs[i], lows[i], closes[i - 1]) for i in range(1, n)]
    recent = trs[-short_window:]
    baseline = trs[-(short_window + long_window) : -short_window]
    recent_avg = sum(recent) / short_window
    baseline_avg = sum(baseline) / long_window

    expansion_ratio: float | None = None
    if baseline_avg > 0:
        expansion_ratio = recent_avg / baseline_avg

    return {
        "recent_avg_tr": recent_avg,
        "baseline_avg_tr": baseline_avg,
        "expansion_ratio": expansion_ratio,
    }
