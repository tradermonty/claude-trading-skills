"""Average daily dollar volume (ADV) and a log-scale liquidity score.

ADV is the universe-side hard filter — anything below the floor is rejected
in ``invalidation_rules`` before scoring runs. The score returned here is
only used for the 10-point Liquidity factor inside the composite score.
"""

from __future__ import annotations

from math_helpers import log10_scale


def adv_dollars(closes: list[float], volumes: list[float], period: int = 20) -> float | None:
    """Average ``close * volume`` over the trailing ``period`` bars."""
    if period <= 0:
        raise ValueError(f"period must be positive, got {period}")
    if len(closes) < period or len(volumes) < period or len(closes) != len(volumes):
        return None
    pairs = list(zip(closes[-period:], volumes[-period:]))
    total = sum(c * v for c, v in pairs)
    return total / period


def latest_volume_ratio(volumes: list[float], period: int = 20) -> float | None:
    """Latest bar volume divided by the trailing-period average volume."""
    if len(volumes) < period + 1:
        return None
    avg = sum(volumes[-period - 1 : -1]) / period
    if avg <= 0:
        return None
    return volumes[-1] / avg


def calculate_liquidity(
    closes: list[float],
    volumes: list[float],
    period: int = 20,
    score_lo_log10: float = 7.0,
    score_hi_log10: float = 8.5,
) -> dict:
    """Aggregate liquidity metrics + log-scale score.

    Score endpoints default to ``$10M ADV → 0`` and ``$316M ADV → 10``.
    """
    adv = adv_dollars(closes, volumes, period=period)
    score = log10_scale(adv, score_lo_log10, score_hi_log10) if adv is not None else 0.0
    return {
        "adv_20d_usd": adv,
        "volume_ratio_20d": latest_volume_ratio(volumes, period=period),
        "liquidity_score_0_to_10": score,
    }
