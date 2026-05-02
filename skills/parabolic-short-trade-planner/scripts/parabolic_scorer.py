"""Composite scorer for parabolic-short-trade-planner.

Mirrors the structure of skills/earnings-trade-analyzer/scripts/scorer.py:
fixed dict of weights, threshold table for letter grades, guidance per
grade.
"""

from __future__ import annotations

COMPONENT_WEIGHTS = {
    "ma_extension": 0.30,
    "acceleration": 0.25,
    "volume_climax": 0.20,
    "range_expansion": 0.15,
    "liquidity": 0.10,
}

GRADE_THRESHOLDS = [
    (85, "A", "High-conviction parabolic exhaustion. Wait for trigger."),
    (70, "B", "Solid parabolic candidate. Strict trigger discipline required."),
    (50, "C", "Marginal — watch only, do not generate trade plan by default."),
    (0, "D", "Weak setup, exclude."),
]

GRADE_GUIDANCE = {
    "A": "Build watchlist position. Plan ORL / first-red-5min / VWAP-fail triggers. Confirm borrow.",
    "B": "Watchlist only. Trade if a clean intraday trigger fires AND blocking_manual_reasons is empty.",
    "C": "Monitor for setup degradation. Default screener excludes from pre-market plans.",
    "D": "Do not trade. Likely insufficient extension or no acceleration.",
}

DEFAULT_TRADABLE_MIN_GRADE = "B"
DEFAULT_WATCH_MIN_GRADE = "C"

GRADE_ORDER = ["A", "B", "C", "D"]


def calculate_composite_score(components: dict) -> dict:
    """Apply weights to the component sub-scores and assign a letter grade.

    Args:
        components: dict with keys ``ma_extension``, ``acceleration``,
            ``volume_climax``, ``range_expansion``, ``liquidity``. Values are
            sub-scores in [0, 100].

    Returns:
        dict with ``score``, ``grade``, ``grade_description``, ``guidance``,
        ``component_breakdown``, ``weakest_component``, ``strongest_component``.
    """
    weighted = {
        name: comp * COMPONENT_WEIGHTS[name]
        for name, comp in components.items()
        if name in COMPONENT_WEIGHTS
    }
    score = round(sum(weighted.values()), 1)

    grade = "D"
    description = GRADE_THRESHOLDS[-1][2]
    for threshold, g, desc in GRADE_THRESHOLDS:
        if score >= threshold:
            grade = g
            description = desc
            break

    weakest = min(components, key=lambda k: components[k]) if components else None
    strongest = max(components, key=lambda k: components[k]) if components else None

    return {
        "score": score,
        "grade": grade,
        "grade_description": description,
        "guidance": GRADE_GUIDANCE.get(grade, ""),
        "component_breakdown": {
            name: {
                "score": round(comp, 1),
                "weight": COMPONENT_WEIGHTS[name],
                "weighted_score": round(comp * COMPONENT_WEIGHTS[name], 1),
            }
            for name, comp in components.items()
            if name in COMPONENT_WEIGHTS
        },
        "weakest_component": weakest,
        "strongest_component": strongest,
    }


def grade_at_or_above(grade: str, threshold: str) -> bool:
    """Return True if ``grade`` is the same or stronger letter as ``threshold``."""
    if grade not in GRADE_ORDER or threshold not in GRADE_ORDER:
        return False
    return GRADE_ORDER.index(grade) <= GRADE_ORDER.index(threshold)
