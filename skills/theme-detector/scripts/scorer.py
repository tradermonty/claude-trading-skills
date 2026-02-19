"""
Theme Detector - Scoring, Labeling & Confidence

Combines theme heat and lifecycle maturity into a final theme score dict.
Follows the pattern from macro-regime-detector/scripts/scorer.py.

Design Note on Confidence Levels:
    narrative_confirmed is intentionally set to False in the script output.
    This is by design: Claude performs WebSearch-based narrative confirmation
    as a post-processing step. Script-only output therefore has a maximum
    confidence of "Medium" (quant_confirmed + breadth_confirmed = 2 layers).
    After Claude confirms narrative alignment, confidence can reach "High".
"""

from typing import Dict


HEAT_LABELS = {
    80: "Hot",
    60: "Warm",
    40: "Neutral",
    20: "Cool",
    0: "Cold",
}


def get_heat_label(heat_score: float) -> str:
    """Map heat score to label: Hot/Warm/Neutral/Cool/Cold."""
    if heat_score >= 80:
        return "Hot"
    elif heat_score >= 60:
        return "Warm"
    elif heat_score >= 40:
        return "Neutral"
    elif heat_score >= 20:
        return "Cool"
    else:
        return "Cold"


def calculate_confidence(quant_confirmed: bool,
                         breadth_confirmed: bool,
                         narrative_confirmed: bool,
                         stale_data_penalty: bool) -> str:
    """Determine confidence level from confirmation layers.

    3 layers confirmed => High
    2 layers confirmed => Medium
    1 or 0 layers     => Low
    stale_data_penalty downgrades by 1 level (High->Medium, Medium->Low).
    """
    confirmed_count = sum([quant_confirmed, breadth_confirmed, narrative_confirmed])

    if confirmed_count >= 3:
        level = "High"
    elif confirmed_count >= 2:
        level = "Medium"
    else:
        level = "Low"

    if stale_data_penalty and level != "Low":
        level = "Medium" if level == "High" else "Low"

    return level


def determine_data_mode(fmp_available: bool, finviz_elite: bool) -> str:
    """Describe available data sources."""
    if fmp_available and finviz_elite:
        return "FINVIZ-Elite+FMP"
    elif fmp_available and not finviz_elite:
        return "FMP-only"
    elif not fmp_available and finviz_elite:
        return "FINVIZ-Elite"
    else:
        return "FINVIZ-Public"


def score_theme(theme_heat: float,
                lifecycle_maturity: float,
                lifecycle_stage: str,
                direction: str,
                confidence: str,
                data_mode: str) -> Dict:
    """Combine all dimensions into final theme score dict."""
    return {
        "theme_heat": theme_heat,
        "heat_label": get_heat_label(theme_heat),
        "lifecycle_maturity": lifecycle_maturity,
        "lifecycle_stage": lifecycle_stage,
        "direction": direction,
        "confidence": confidence,
        "data_mode": data_mode,
    }
