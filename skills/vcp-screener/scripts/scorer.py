#!/usr/bin/env python3
"""
VCP Screener - 5-Component Composite Scoring Engine

Combines component scores into a weighted composite (0-100).

Component Weights:
1. Trend Template:      25%
2. Contraction Quality: 25%
3. Volume Pattern:      20%
4. Pivot Proximity:     15%
5. Relative Strength:   15%
Total: 100%

Rating Bands:
  90-100: Textbook VCP  - Buy at pivot, aggressive sizing
  80-89:  Strong VCP    - Buy at pivot, standard sizing
  70-79:  Good VCP      - Buy on volume confirmation
  60-69:  Developing    - Watchlist, wait for tighter pivot
  50-59:  Weak VCP      - Monitor only
  <50:    No VCP        - Not a VCP setup
"""

from typing import Dict


COMPONENT_WEIGHTS = {
    "trend_template": 0.25,
    "contraction_quality": 0.25,
    "volume_pattern": 0.20,
    "pivot_proximity": 0.15,
    "relative_strength": 0.15,
}

COMPONENT_LABELS = {
    "trend_template": "Trend Template (Stage 2)",
    "contraction_quality": "Contraction Quality",
    "volume_pattern": "Volume Pattern",
    "pivot_proximity": "Pivot Proximity",
    "relative_strength": "Relative Strength",
}


def calculate_composite_score(
    trend_score: float,
    contraction_score: float,
    volume_score: float,
    pivot_score: float,
    rs_score: float,
    valid_vcp: bool = True,
) -> Dict:
    """
    Calculate weighted composite VCP score.

    Args:
        trend_score: Trend Template score (0-100)
        contraction_score: VCP contraction quality score (0-100)
        volume_score: Volume dry-up pattern score (0-100)
        pivot_score: Pivot proximity score (0-100)
        rs_score: Relative Strength score (0-100)
        valid_vcp: Whether VCP pattern passed validation (contraction ratios)

    Returns:
        Dict with composite_score, rating, guidance, component breakdown
    """
    component_scores = {
        "trend_template": trend_score,
        "contraction_quality": contraction_score,
        "volume_pattern": volume_score,
        "pivot_proximity": pivot_score,
        "relative_strength": rs_score,
    }

    # Calculate weighted composite
    composite = 0.0
    for key, weight in COMPONENT_WEIGHTS.items():
        composite += component_scores[key] * weight

    composite = round(composite, 1)

    # Find weakest and strongest
    weakest_key = min(component_scores, key=component_scores.get)
    strongest_key = max(component_scores, key=component_scores.get)

    # Rating
    rating_info = _get_rating(composite)

    # Override rating when VCP pattern is not validated (e.g. expanding contractions)
    if not valid_vcp and composite >= 70:
        rating_info = {
            "rating": "Developing VCP",
            "description": "VCP pattern not confirmed - contractions do not meet criteria",
            "guidance": "Watchlist only - VCP pattern not validated, do not buy",
        }

    return {
        "composite_score": composite,
        "rating": rating_info["rating"],
        "rating_description": rating_info["description"],
        "guidance": rating_info["guidance"],
        "valid_vcp": valid_vcp,
        "weakest_component": COMPONENT_LABELS[weakest_key],
        "weakest_score": component_scores[weakest_key],
        "strongest_component": COMPONENT_LABELS[strongest_key],
        "strongest_score": component_scores[strongest_key],
        "component_breakdown": {
            k: {
                "score": component_scores[k],
                "weight": w,
                "weighted": round(component_scores[k] * w, 1),
                "label": COMPONENT_LABELS[k],
            }
            for k, w in COMPONENT_WEIGHTS.items()
        },
    }


def _get_rating(composite: float) -> Dict:
    """Map composite score to rating and guidance."""
    if composite >= 90:
        return {
            "rating": "Textbook VCP",
            "description": "Ideal VCP setup with all components aligned",
            "guidance": "Buy at pivot, aggressive position sizing (1.5-2x normal)",
        }
    elif composite >= 80:
        return {
            "rating": "Strong VCP",
            "description": "High-quality VCP with minor imperfections",
            "guidance": "Buy at pivot, standard position sizing",
        }
    elif composite >= 70:
        return {
            "rating": "Good VCP",
            "description": "Solid VCP pattern developing",
            "guidance": "Buy on volume confirmation above pivot",
        }
    elif composite >= 60:
        return {
            "rating": "Developing VCP",
            "description": "VCP forming but not yet actionable",
            "guidance": "Watchlist - wait for tighter contraction near pivot",
        }
    elif composite >= 50:
        return {
            "rating": "Weak VCP",
            "description": "Some VCP characteristics but incomplete",
            "guidance": "Monitor only - pattern needs more development",
        }
    else:
        return {
            "rating": "No VCP",
            "description": "Does not qualify as a VCP setup",
            "guidance": "Not actionable as VCP",
        }
