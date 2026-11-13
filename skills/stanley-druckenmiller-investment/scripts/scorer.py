#!/usr/bin/env python3
"""
Strategy Synthesizer - Conviction Scoring Engine

Combines 7 component scores into a weighted composite conviction score (0-100).
Maps to conviction zones and classifies into 4 Druckenmiller patterns.

Component Weights:
1. Market Structure:      18%  (Breadth + Uptrend)
2. Distribution Risk:     18%  (Market Top - inverted)
3. Bottom Confirmation:   12%  (FTD Detector)
4. Macro Alignment:       18%  (Macro Regime)
5. Theme Quality:         12%  (Theme Detector)
6. Setup Availability:    10%  (VCP + CANSLIM)
7. Signal Convergence:    12%  (Cross-skill agreement)
Total: 100%

Conviction Zones:
  80-100: Maximum Conviction  - Exposure: 90-100%
  60-79:  High Conviction     - Exposure: 70-90%
  40-59:  Moderate Conviction - Exposure: 50-70%
  20-39:  Low Conviction      - Exposure: 20-50%
   0-19:  Capital Preservation - Exposure: 0-20%
"""

from typing import Optional

COMPONENT_WEIGHTS = {
    "market_structure": 0.18,
    "distribution_risk": 0.18,
    "bottom_confirmation": 0.12,
    "macro_alignment": 0.18,
    "theme_quality": 0.12,
    "setup_availability": 0.10,
    "signal_convergence": 0.12,
}

COMPONENT_LABELS = {
    "market_structure": "Market Structure (Breadth + Uptrend)",
    "distribution_risk": "Distribution Risk (Market Top, inverted)",
    "bottom_confirmation": "Bottom Confirmation (FTD Detector)",
    "macro_alignment": "Macro Alignment (Regime)",
    "theme_quality": "Theme Quality (Theme Detector)",
    "setup_availability": "Setup Availability (VCP + CANSLIM)",
    "signal_convergence": "Signal Convergence (Cross-Skill Agreement)",
}


# ---------------------------------------------------------------------------
# Component calculators
# ---------------------------------------------------------------------------


def calculate_market_structure(signals: dict) -> float:
    """Breadth health * 0.5 + Uptrend health * 0.5, with divergence adjustment."""
    breadth = signals.get("market_breadth", {})
    uptrend = signals.get("uptrend_analysis", {})

    b_score = breadth.get("composite_score", 50)
    u_score = uptrend.get("composite_score", 50)

    base = b_score * 0.5 + u_score * 0.5

    # Divergence penalty: if breadth and uptrend disagree significantly
    divergence = abs(b_score - u_score)
    if divergence > 30:
        base -= (divergence - 30) * 0.3

    return max(0, min(round(base, 1), 100))


def calculate_distribution_risk(signals: dict) -> float:
    """Inverted market top score: high top risk = low conviction."""
    top = signals.get("market_top", {})
    top_score = top.get("composite_score", 0)
    return round(max(0, min(100 - top_score, 100)), 1)


def calculate_bottom_confirmation(signals: dict) -> float:
    """FTD state-based scoring for bottom confirmation / re-entry signal."""
    ftd = signals.get("ftd_detector", {})
    state = ftd.get("state", "NO_SIGNAL")
    quality = ftd.get("quality_score", 0)
    dual = ftd.get("dual_confirmation", False)
    dist_count = ftd.get("post_ftd_distribution_count", 0)

    state_scores = {
        "FTD_CONFIRMED": 80,
        "FTD_WINDOW": 60,
        "RALLY_ATTEMPT": 55,
        "NO_SIGNAL": 40,
        "CORRECTION": 35,
        "FTD_INVALIDATED": 15,
        "RALLY_FAILED": 10,
        # ftd-detector data gap (issue #655): no usable confirmation, scored as
        # low as a failed rally so a gap can never raise bottom confirmation.
        "DATA_GAP": 10,
    }

    base = state_scores.get(state, 40)

    # Quality bonus for confirmed FTD
    if state == "FTD_CONFIRMED":
        quality_bonus = (quality - 50) * 0.2  # -10 to +10
        base += quality_bonus
        if dual:
            base += 5
        # Post-FTD distribution penalty
        base -= dist_count * 5

    return round(max(0, min(base, 100)), 1)


def calculate_macro_alignment(signals: dict) -> float:
    """Regime-based conviction scoring."""
    macro = signals.get("macro_regime", {})
    regime = macro.get("regime", "unknown")
    composite = macro.get("composite_score", 50)
    confidence = macro.get("confidence", "unknown")

    regime_base = {
        "broadening": 85,
        "concentration": 65,
        "transitional": 50,
        "inflationary": 35,
        "contraction": 20,
    }

    base = regime_base.get(regime, 50)

    # Adjust by transition score
    transition_adj = (composite - 50) * 0.2
    base += transition_adj

    # Confidence modifier
    confidence_mult = {"high": 1.1, "medium": 1.0, "low": 0.9}
    base *= confidence_mult.get(confidence, 1.0)

    return round(max(0, min(base, 100)), 1)


def calculate_theme_quality(signals: dict) -> float:
    """Theme-derived score with lifecycle adjustment."""
    theme = signals.get("theme_detector", {})
    derived = theme.get("derived_score", 50)
    return round(max(0, min(derived, 100)), 1)


def calculate_setup_availability(signals: dict) -> float:
    """
    VCP + CANSLIM derived scores averaged when both available.
    Fat pitch detection: exceptional setups = bonus.
    """
    vcp = signals.get("vcp_screener", {})
    canslim = signals.get("canslim_screener", {})

    scores = []
    fat_pitch_bonus = 0

    if vcp:
        scores.append(vcp.get("derived_score", 0))
        if vcp.get("textbook_count", 0) >= 2:
            fat_pitch_bonus += 10

    if canslim:
        scores.append(canslim.get("derived_score", 0))
        if canslim.get("exceptional_count", 0) >= 3:
            fat_pitch_bonus += 10

    if not scores:
        return 50.0  # Neutral default when no setup data

    base = sum(scores) / len(scores) + fat_pitch_bonus
    return round(max(0, min(base, 100)), 1)


def calculate_signal_convergence(signals: dict) -> float:
    """
    Measure agreement among the 5 required skills.
    "Ducks in a row" - Druckenmiller's key conviction criterion.
    """
    required_scores = []

    # Collect normalized bullish scores (higher = more bullish)
    breadth = signals.get("market_breadth", {})
    if breadth:
        required_scores.append(breadth.get("composite_score", 50))

    uptrend = signals.get("uptrend_analysis", {})
    if uptrend:
        required_scores.append(uptrend.get("composite_score", 50))

    top = signals.get("market_top", {})
    if top:
        # Invert: low top risk = bullish
        required_scores.append(100 - top.get("composite_score", 50))

    macro = signals.get("macro_regime", {})
    if macro:
        required_scores.append(macro.get("composite_score", 50))

    ftd = signals.get("ftd_detector", {})
    # A DATA_GAP report contributes quality 0, exactly what a healed failed /
    # invalidated / no-FTD run contributes. Leaving it out instead was measured
    # to RAISE convergence (and the composite) versus the healed run in ~15% of
    # gapped cases (issue #655), because removing a 0 outlier tightens agreement.
    if ftd:
        required_scores.append(ftd.get("quality_score", 50))

    if len(required_scores) < 3:
        return 50.0  # Insufficient data

    # Calculate agreement: low standard deviation = high convergence
    mean = sum(required_scores) / len(required_scores)
    variance = sum((s - mean) ** 2 for s in required_scores) / len(required_scores)
    std_dev = variance**0.5

    # Convert std_dev to convergence score
    # std_dev 0 -> 100 (perfect agreement)
    # std_dev 30+ -> 0 (complete disagreement)
    convergence = max(0, 100 - std_dev * 3.33)

    # Directional adjustment based on consensus
    all_bullish = all(s > 55 for s in required_scores)
    all_bearish = all(s < 45 for s in required_scores)
    if all_bullish:
        convergence = min(convergence + 15, 100)
    elif all_bearish:
        convergence = max(convergence - 15, 0)

    return round(convergence, 1)


# ---------------------------------------------------------------------------
# Composite scorer
# ---------------------------------------------------------------------------


def calculate_composite_conviction(
    signals: dict,
    data_availability: Optional[dict[str, bool]] = None,
) -> dict:
    """
    Calculate weighted composite conviction score from extracted signals.

    Args:
        signals: Dict mapping skill_name -> extracted signal dict
        data_availability: Optional dict mapping component -> bool

    Returns:
        Dict with conviction_score, zone, exposure, guidance, etc.
    """
    if data_availability is None:
        data_availability = {}

    # Determine which optional components have real data
    has_theme = "theme_detector" in signals
    has_setup = "vcp_screener" in signals or "canslim_screener" in signals

    # Calculate each component
    raw_scores = {
        "market_structure": calculate_market_structure(signals),
        "distribution_risk": calculate_distribution_risk(signals),
        "bottom_confirmation": calculate_bottom_confirmation(signals),
        "macro_alignment": calculate_macro_alignment(signals),
        "theme_quality": calculate_theme_quality(signals),
        "setup_availability": calculate_setup_availability(signals),
        "signal_convergence": calculate_signal_convergence(signals),
    }

    # Determine availability per component
    availability = {k: True for k in COMPONENT_WEIGHTS}
    if not has_theme:
        availability["theme_quality"] = False
    if not has_setup:
        availability["setup_availability"] = False

    # Weight redistribution: proportionally allocate unavailable weight
    available_components = {k for k, v in availability.items() if v}
    base_weight_sum = sum(COMPONENT_WEIGHTS[k] for k in available_components)

    effective_weights = {}
    for k in COMPONENT_WEIGHTS:
        if k in available_components and base_weight_sum > 0:
            effective_weights[k] = COMPONENT_WEIGHTS[k] / base_weight_sum
        else:
            effective_weights[k] = 0.0

    # Weighted composite using effective weights
    composite = 0.0
    for key in COMPONENT_WEIGHTS:
        composite += raw_scores[key] * effective_weights[key]

    composite = round(composite, 1)

    # Zone interpretation
    zone_info = _interpret_conviction_zone(composite)

    # Strongest / weakest from available components only
    available_scores = {k: v for k, v in raw_scores.items() if availability[k]}
    strongest = max(available_scores, key=available_scores.get)
    weakest = min(available_scores, key=available_scores.get)

    # Data quality
    available_count = sum(1 for v in availability.values() if v)

    return {
        "conviction_score": composite,
        "zone": zone_info["zone"],
        "zone_color": zone_info["color"],
        "exposure_range": zone_info["exposure"],
        "guidance": zone_info["guidance"],
        "actions": zone_info["actions"],
        "strongest_component": {
            "component": strongest,
            "label": COMPONENT_LABELS.get(strongest, strongest),
            "score": raw_scores[strongest],
        },
        "weakest_component": {
            "component": weakest,
            "label": COMPONENT_LABELS.get(weakest, weakest),
            "score": raw_scores[weakest],
        },
        "data_quality": {
            "available_count": available_count,
            "total_components": len(COMPONENT_WEIGHTS),
        },
        "component_scores": {
            k: {
                "score": raw_scores.get(k, 0),
                "weight": w,
                "effective_weight": round(effective_weights[k], 4),
                "available": availability[k],
                "weighted_contribution": round(raw_scores.get(k, 0) * effective_weights[k], 1),
                "label": COMPONENT_LABELS[k],
            }
            for k, w in COMPONENT_WEIGHTS.items()
        },
    }


def _interpret_conviction_zone(composite: float) -> dict:
    """Map composite conviction to zone."""
    if composite >= 80:
        return {
            "zone": "Maximum Conviction",
            "color": "green",
            "exposure": "90-100%",
            "guidance": "All signals aligned. Druckenmiller 'fat pitch' - swing hard.",
            "actions": [
                "Maximum equity exposure (90-100%)",
                "Concentrated positions in strongest setups",
                "Aggressive position sizing on breakouts",
                "Use leverage selectively on highest-conviction ideas",
            ],
        }
    elif composite >= 60:
        return {
            "zone": "High Conviction",
            "color": "light_green",
            "exposure": "70-90%",
            "guidance": "Multiple signals confirm. Strong equity posture, standard risk management.",
            "actions": [
                "Above-average equity allocation (70-90%)",
                "Standard position sizing on quality setups",
                "New entries on VCP/CANSLIM signals",
                "Maintain stop-losses at normal levels",
            ],
        }
    elif composite >= 40:
        return {
            "zone": "Moderate Conviction",
            "color": "yellow",
            "exposure": "50-70%",
            "guidance": "Mixed signals. Maintain exposure but reduce position sizes.",
            "actions": [
                "Moderate equity allocation (50-70%)",
                "Reduced position sizes (half normal)",
                "Only A-grade setups",
                "Tighter stop-losses",
                "Raise cash allocation to 30-50%",
            ],
        }
    elif composite >= 20:
        return {
            "zone": "Low Conviction",
            "color": "orange",
            "exposure": "20-50%",
            "guidance": "Unclear outlook. Preserve capital, minimal new risk.",
            "actions": [
                "Defensive posture (20-50% equity)",
                "No new entries except rare opportunities",
                "Profit-taking on weaker positions",
                "High cash allocation (50-80%)",
                "Monitor for signal improvement",
            ],
        }
    else:
        return {
            "zone": "Capital Preservation",
            "color": "red",
            "exposure": "0-20%",
            "guidance": "Extreme caution. Druckenmiller: 'When you don't see it, don't swing.'",
            "actions": [
                "Maximum defensive posture (0-20% equity)",
                "Close most positions",
                "High cash / Treasuries / Gold",
                "Watch for FTD signal for re-entry",
                "Preserve capital as primary objective",
            ],
        }


# ---------------------------------------------------------------------------
# Pattern classification
# ---------------------------------------------------------------------------

PATTERN_DEFINITIONS = {
    "policy_pivot_anticipation": {
        "label": "Policy Pivot Anticipation",
        "description": "Central bank policy at inflection point. Market hasn't priced the turn.",
    },
    "unsustainable_distortion": {
        "label": "Unsustainable Distortion",
        "description": "Market structure is fragile. Distribution signals + macro contraction.",
    },
    "extreme_sentiment_contrarian": {
        "label": "Extreme Sentiment Contrarian",
        "description": "Bottom confirmed after extreme bearishness. Druckenmiller's bear market profit.",
    },
    "wait_and_observe": {
        "label": "Wait & Observe",
        "description": "Mixed signals, unclear direction. Preserve capital, wait for clarity.",
    },
}


def classify_pattern(signals: dict, component_scores: dict, conviction_score: float) -> dict:
    """
    Classify the current market into one of 4 Druckenmiller patterns.
    Returns the best-matching pattern with match strength.
    """
    macro = signals.get("macro_regime", {})
    top = signals.get("market_top", {})
    ftd = signals.get("ftd_detector", {})
    breadth = signals.get("market_breadth", {})

    regime = macro.get("regime", "unknown")
    transition_level = macro.get("transition_level", "unknown")
    top_score = top.get("composite_score", 0)
    ftd_state = ftd.get("state", "NO_SIGNAL")
    ftd_quality = ftd.get("quality_score", 0)
    breadth_score = breadth.get("composite_score", 50)

    pattern_scores = {}

    # Pattern 1: Policy Pivot Anticipation
    p1 = 0
    if regime == "transitional":
        p1 += 40
    if transition_level in ("high", "moderate"):
        p1 += 25
    if top_score < 40:  # No imminent top
        p1 += 15
    macro_composite = macro.get("composite_score", 0)
    if macro_composite >= 50:
        p1 += 20
    pattern_scores["policy_pivot_anticipation"] = min(p1, 100)

    # Pattern 2: Unsustainable Distortion
    p2 = 0
    if top_score >= 60:
        p2 += 35
    if regime in ("contraction", "inflationary"):
        p2 += 30
    theme = signals.get("theme_detector", {})
    if theme.get("exhaustion_count", 0) >= 2:
        p2 += 20
    if breadth_score < 40:
        p2 += 15
    pattern_scores["unsustainable_distortion"] = min(p2, 100)

    # Pattern 3: Extreme Sentiment Contrarian (FTD-driven)
    p3 = 0
    if ftd_state == "FTD_CONFIRMED":
        p3 += 40
        if ftd_quality >= 70:
            p3 += 15
    if top_score >= 70:
        p3 += 20  # Came from high top risk
    if breadth_score < 35:
        p3 += 15  # Extreme pessimism in breadth
    convergence = component_scores.get("signal_convergence", {})
    conv_score = convergence.get("score", 50) if isinstance(convergence, dict) else convergence
    if conv_score < 30:  # Bearish convergence that's now reversing
        p3 += 10
    pattern_scores["extreme_sentiment_contrarian"] = min(p3, 100)

    # Pattern 4: Wait & Observe (default when nothing strong)
    p4 = 0
    if conviction_score < 40:
        p4 += 40
    # Mixed signals indicator
    scores_list = [
        v.get("score", 50) if isinstance(v, dict) else 50 for v in component_scores.values()
    ]
    if scores_list:
        spread = max(scores_list) - min(scores_list)
        if spread > 40:
            p4 += 30
    if regime == "transitional" and top_score >= 40 and top_score <= 60:
        p4 += 20
    pattern_scores["wait_and_observe"] = min(p4, 100)

    # Select best pattern
    best_pattern = max(pattern_scores, key=pattern_scores.get)
    best_score = pattern_scores[best_pattern]

    # If no strong match, default to wait_and_observe
    if best_score < 40:
        best_pattern = "wait_and_observe"
        best_score = max(best_score, 50)

    definition = PATTERN_DEFINITIONS[best_pattern]

    return {
        "pattern": best_pattern,
        "label": definition["label"],
        "description": definition["description"],
        "match_strength": best_score,
        "all_pattern_scores": pattern_scores,
    }
