#!/usr/bin/env python3
"""
Uptrend Analyzer - Composite Scoring Engine

Combines 5 component scores into a weighted composite (0-100).
Higher score = healthier market (opposite of Market Top Detector).

Component Weights:
1. Market Breadth (Overall):   30%
2. Sector Participation:       25%
3. Sector Rotation:            15%
4. Momentum:                   20%
5. Historical Context:         10%
Total: 100%

Scoring Zones (higher = better):
  80-100: Strong Bull   - Full Exposure (100%)
  60-79:  Bull          - Normal Exposure (80-100%)
  40-59:  Neutral       - Reduced Exposure (60-80%)
  20-39:  Cautious      - Defensive (30-60%)
  0-19:   Bear          - Capital Preservation (0-30%)
"""

from typing import Dict, List, Optional


COMPONENT_WEIGHTS = {
    "market_breadth": 0.30,
    "sector_participation": 0.25,
    "sector_rotation": 0.15,
    "momentum": 0.20,
    "historical_context": 0.10,
}

COMPONENT_LABELS = {
    "market_breadth": "Market Breadth (Overall)",
    "sector_participation": "Sector Participation",
    "sector_rotation": "Sector Rotation",
    "momentum": "Momentum",
    "historical_context": "Historical Context",
}


def calculate_composite_score(component_scores: Dict[str, float],
                              data_availability: Optional[Dict[str, bool]] = None,
                              warning_flags: Optional[Dict[str, bool]] = None) -> Dict:
    """
    Calculate weighted composite market health score.

    Args:
        component_scores: Dict with keys matching COMPONENT_WEIGHTS,
                         each value 0-100
        data_availability: Optional dict mapping component key -> bool indicating
                          if data was actually available (vs neutral default)
        warning_flags: Optional dict of component warning flags, e.g.
                      {"late_cycle": True, "high_spread": True}

    Returns:
        Dict with composite_score, zone, exposure_guidance, guidance,
        strongest/weakest components, component breakdown, data_quality,
        and active_warnings
    """
    if data_availability is None:
        data_availability = {}
    if warning_flags is None:
        warning_flags = {}

    # Calculate weighted composite
    composite = 0.0
    for key, weight in COMPONENT_WEIGHTS.items():
        score = component_scores.get(key, 0)
        composite += score * weight

    composite = round(composite, 1)

    # Identify strongest and weakest components
    valid_scores = {k: v for k, v in component_scores.items()
                    if k in COMPONENT_WEIGHTS}

    if valid_scores:
        strongest = max(valid_scores, key=valid_scores.get)
        weakest = min(valid_scores, key=valid_scores.get)
    else:
        strongest = "N/A"
        weakest = "N/A"

    # Get zone interpretation
    zone_info = _interpret_zone(composite)

    # Overlay warning-specific adjustments
    active_warnings = _apply_warning_overlays(zone_info, warning_flags)

    # Calculate data quality
    available_count = sum(
        1 for k in COMPONENT_WEIGHTS
        if data_availability.get(k, True)
    )
    total_components = len(COMPONENT_WEIGHTS)
    missing_components = [
        COMPONENT_LABELS[k] for k in COMPONENT_WEIGHTS
        if not data_availability.get(k, True)
    ]

    if available_count == total_components:
        quality_label = f"Complete ({available_count}/{total_components} components)"
    elif available_count >= total_components - 1:
        quality_label = (f"Partial ({available_count}/{total_components} components)"
                        " - interpret with caution")
    else:
        quality_label = (f"Limited ({available_count}/{total_components} components)"
                        " - low confidence")

    data_quality = {
        "available_count": available_count,
        "total_components": total_components,
        "label": quality_label,
        "missing_components": missing_components,
    }

    return {
        "composite_score": composite,
        "zone": zone_info["zone"],
        "zone_color": zone_info["color"],
        "exposure_guidance": zone_info["exposure_guidance"],
        "guidance": zone_info["guidance"],
        "actions": zone_info["actions"],
        "active_warnings": active_warnings,
        "strongest_component": {
            "component": strongest,
            "label": COMPONENT_LABELS.get(strongest, strongest),
            "score": valid_scores.get(strongest, 0),
        },
        "weakest_component": {
            "component": weakest,
            "label": COMPONENT_LABELS.get(weakest, weakest),
            "score": valid_scores.get(weakest, 0),
        },
        "data_quality": data_quality,
        "component_scores": {
            k: {
                "score": component_scores.get(k, 0),
                "weight": w,
                "weighted_contribution": round(component_scores.get(k, 0) * w, 1),
                "label": COMPONENT_LABELS[k],
            }
            for k, w in COMPONENT_WEIGHTS.items()
        },
    }


def _apply_warning_overlays(zone_info: Dict,
                            warning_flags: Dict[str, bool]) -> List[Dict]:
    """Apply warning-driven adjustments to zone guidance and actions.

    When component-level warnings (e.g. late_cycle, high_spread) are active,
    tighten the exposure guidance and prepend cautionary actions even if the
    composite score places the market in a bullish zone.

    Returns:
        List of active warning dicts with label, description, and extra actions
    """
    active = []

    if warning_flags.get("late_cycle"):
        active.append({
            "flag": "late_cycle",
            "label": "LATE CYCLE WARNING",
            "description": ("Commodity sectors leading both cyclical and defensive groups. "
                            "Historically associated with late-cycle inflation or sector rotation "
                            "preceding broader market weakness."),
            "actions": [
                "Favor lower end of exposure range (e.g. 80% if guidance is 80-100%)",
                "New entries limited to A-grade setups only",
                "Tighten stops on commodity/cyclical positions",
                "Monitor for commodity rollover as potential broad market lead indicator",
            ],
        })

    if warning_flags.get("high_spread"):
        active.append({
            "flag": "high_spread",
            "label": "HIGH SELECTIVITY WARNING",
            "description": ("Wide spread between strongest and weakest sectors indicates "
                            "highly selective market. Breadth may be masking narrowing leadership."),
            "actions": [
                "Concentrate on sectors with ratio above 10MA",
                "Avoid lagging sectors even if trend is nominally 'up'",
                "Reduce position count to highest-conviction ideas",
            ],
        })

    # If any warning is active, tighten exposure guidance for bullish zones
    if active and zone_info["zone"] in ("Strong Bull", "Bull"):
        original = zone_info["exposure_guidance"]
        if zone_info["zone"] == "Strong Bull":
            zone_info["exposure_guidance"] = "Full Exposure with Caution (90-100%)"
        elif zone_info["zone"] == "Bull":
            zone_info["exposure_guidance"] = "Normal Exposure, Lower End (80-90%)"
        zone_info["guidance"] += (
            f" However, active warnings suggest operating at the conservative "
            f"end of the range."
        )

    return active


def _interpret_zone(composite: float) -> Dict:
    """Map composite score to health zone (higher = healthier)"""
    if composite >= 80:
        return {
            "zone": "Strong Bull",
            "color": "green",
            "exposure_guidance": "Full Exposure (100%)",
            "guidance": "Broad market participation with strong momentum. Ideal environment for new positions.",
            "actions": [
                "Full equity exposure allowed",
                "Aggressive position sizing for breakout entries",
                "Add to winning positions on pullbacks",
                "Minimal hedging needed",
            ],
        }
    elif composite >= 60:
        return {
            "zone": "Bull",
            "color": "light_green",
            "exposure_guidance": "Normal Exposure (80-100%)",
            "guidance": "Healthy market breadth supporting equity allocation. Standard position management.",
            "actions": [
                "Normal position sizing",
                "New entries on quality setups",
                "Standard stop-loss levels",
                "Monitor sector rotation for early warnings",
            ],
        }
    elif composite >= 40:
        return {
            "zone": "Neutral",
            "color": "yellow",
            "exposure_guidance": "Reduced Exposure (60-80%)",
            "guidance": "Mixed signals. Participate selectively with tighter risk controls.",
            "actions": [
                "Reduce position sizes by 20-30%",
                "Focus on strongest sectors only",
                "Tighten stop-losses",
                "Avoid low-quality setups",
                "Increase cash allocation gradually",
            ],
        }
    elif composite >= 20:
        return {
            "zone": "Cautious",
            "color": "orange",
            "exposure_guidance": "Defensive (30-60%)",
            "guidance": "Weak breadth environment. Prioritize capital preservation over gains.",
            "actions": [
                "Significant cash allocation (40-70%)",
                "Only hold strongest leaders in uptrending sectors",
                "Tight stops on all positions",
                "Consider defensive sector allocation",
                "No new aggressive entries",
            ],
        }
    else:
        return {
            "zone": "Bear",
            "color": "red",
            "exposure_guidance": "Capital Preservation (0-30%)",
            "guidance": "Severe breadth deterioration. Maximum defensive posture.",
            "actions": [
                "Maximum cash (70-100%)",
                "Exit most equity positions",
                "Only ultra-high-conviction holdings",
                "Consider hedges (inverse ETFs, puts)",
                "Wait for breadth recovery before re-entry",
            ],
        }
