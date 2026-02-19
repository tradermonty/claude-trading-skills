#!/usr/bin/env python3
"""
Industry Ranker - Momentum scoring and ranking for industries.

Calculates direction-neutral momentum strength using a sigmoid function,
then ranks industries by weighted multi-timeframe returns.

Timeframe Weights:
- 1W:  10%
- 1M:  25%
- 3M:  35%
- 6M:  30%
Total: 100%
"""

import math
from typing import Dict, List


TIMEFRAME_WEIGHTS: Dict[str, float] = {
    "perf_1w": 0.10,
    "perf_1m": 0.25,
    "perf_3m": 0.35,
    "perf_6m": 0.30,
}


def momentum_strength_score(weighted_return_pct: float) -> float:
    """
    Direction-neutral sigmoid momentum score.

    Formula: 100 / (1 + exp(-0.15 * (abs(weighted_return) - 5.0)))

    Returns a score in [0, 100] where:
        |0%|  -> ~32
        |5%|  -> 50 (midpoint)
        |10%| -> ~68
        |15%| -> ~82
        |20%| -> ~90
    """
    x = abs(weighted_return_pct)
    return 100.0 / (1.0 + math.exp(-0.15 * (x - 5.0)))


def rank_industries(industries: List[Dict]) -> List[Dict]:
    """
    Rank industries by momentum strength score.

    Each input dict must have keys: name, perf_1w, perf_1m, perf_3m, perf_6m.
    Additional keys are preserved.

    Adds fields: weighted_return, momentum_score, direction, rank.
    Returns list sorted by momentum_score descending.
    """
    if not industries:
        return []

    scored = []
    for ind in industries:
        weighted_return = sum(
            ind.get(key, 0.0) * weight
            for key, weight in TIMEFRAME_WEIGHTS.items()
        )
        score = momentum_strength_score(weighted_return)
        direction = "bullish" if weighted_return > 0 else "bearish"

        entry = dict(ind)
        entry["weighted_return"] = round(weighted_return, 4)
        entry["momentum_score"] = round(score, 2)
        entry["direction"] = direction
        scored.append(entry)

    scored.sort(key=lambda x: x["momentum_score"], reverse=True)

    mid = len(scored) // 2
    for i, entry in enumerate(scored, start=1):
        entry["rank"] = i
        entry["rank_direction"] = "bullish" if i <= mid else "bearish"

    return scored


def get_top_bottom_industries(ranked: List[Dict], n: int = 5) -> Dict[str, List[Dict]]:
    """
    Extract top N and bottom N industries from a ranked list.

    Args:
        ranked: List sorted by momentum_score descending (output of rank_industries).
        n: Number of industries for each group.

    Returns:
        {"top": [...], "bottom": [...]}
    """
    if not ranked:
        return {"top": [], "bottom": []}

    top = ranked[:n]
    bottom = ranked[-n:] if len(ranked) >= n else ranked[:]

    return {"top": top, "bottom": bottom}
