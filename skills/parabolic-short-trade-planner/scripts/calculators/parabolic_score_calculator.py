"""Aggregate the 5 component scores (each 0-100) used by the composite scorer.

Each component takes the raw metrics computed in Day 1 and maps them to a
single 0-100 sub-score. The composite scorer in ``scorer.py`` then applies
weights (30/25/20/15/10) and converts the result to a letter grade.

These mappings are intentionally simple piecewise-linear functions so they
are predictable and easy to test. Tuning is left to ``screen_parabolic.py``
CLI knobs (e.g. ``--min-roc-5d``).
"""

from __future__ import annotations

from acceleration_calculator import calculate_acceleration
from liquidity_metrics_calculator import calculate_liquidity
from ma_extension_calculator import calculate_ma_extension
from range_expansion_calculator import calculate_range_expansion


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def _linear(x: float | None, x_lo: float, x_hi: float) -> float:
    """Map x linearly from [x_lo, x_hi] -> [0, 100], clamped at the edges."""
    if x is None:
        return 0.0
    if x <= x_lo:
        return 0.0
    if x >= x_hi:
        return 100.0
    return (x - x_lo) / (x_hi - x_lo) * 100.0


def score_ma_extension(metrics: dict) -> float:
    """Use the larger of (20DMA % distance, 20DMA ATR distance)."""
    pct = metrics.get("ext_20dma_pct") or 0.0
    atr_units = metrics.get("ext_20dma_atr") or 0.0
    pct_score = _linear(pct, 20.0, 120.0)
    atr_score = _linear(atr_units, 3.0, 10.0)
    # Combine: 50/50 — both signals matter. ATR-units matters for vol-adjustment;
    # raw % matters for absolute climax.
    return _clamp(0.5 * pct_score + 0.5 * atr_score)


def score_acceleration(metrics: dict) -> float:
    r5 = metrics.get("return_5d_pct") or 0.0
    r3 = metrics.get("return_3d_pct") or 0.0
    streak = metrics.get("consecutive_green_days") or 0
    accel = metrics.get("acceleration_ratio_3_over_10") or 0.0

    return_score = _linear(r5, 20.0, 100.0)
    streak_score = _linear(streak, 2, 5)
    accel_score = _linear(accel, 1.0, 2.0)
    short_burst_score = _linear(r3, 10.0, 50.0)
    return _clamp(
        0.4 * return_score + 0.2 * streak_score + 0.2 * accel_score + 0.2 * short_burst_score
    )


def score_volume_climax(volume_ratio: float | None) -> float:
    return _linear(volume_ratio, 1.5, 5.0)


def score_range_expansion(expansion_ratio: float | None) -> float:
    return _linear(expansion_ratio, 1.2, 3.0)


def score_liquidity(liquidity_score_0_to_10: float) -> float:
    """Map the 0-10 ADV log-scale score onto 0-100."""
    return _clamp(liquidity_score_0_to_10 * 10.0)


def calculate_component_scores(
    closes: list[float],
    opens: list[float],
    highs: list[float],
    lows: list[float],
    volumes: list[float],
) -> dict:
    """Compute the 5 component sub-scores (each 0-100) plus raw metrics.

    Used by ``scorer.py`` and exposed in the screener output for transparency.
    """
    ma_metrics = calculate_ma_extension(closes=closes, highs=highs, lows=lows)
    accel_metrics = calculate_acceleration(opens=opens, closes=closes)
    range_metrics = calculate_range_expansion(highs=highs, lows=lows, closes=closes)
    liq_metrics = calculate_liquidity(closes=closes, volumes=volumes)

    return {
        "components": {
            "ma_extension": score_ma_extension(ma_metrics),
            "acceleration": score_acceleration(accel_metrics),
            "volume_climax": score_volume_climax(liq_metrics.get("volume_ratio_20d")),
            "range_expansion": score_range_expansion(range_metrics.get("expansion_ratio")),
            "liquidity": score_liquidity(liq_metrics.get("liquidity_score_0_to_10", 0.0)),
        },
        "raw_metrics": {
            **{k: v for k, v in ma_metrics.items()},
            **{k: v for k, v in accel_metrics.items()},
            **{k: v for k, v in range_metrics.items()},
            **{k: v for k, v in liq_metrics.items()},
        },
    }
