#!/usr/bin/env python3
"""
Strategy Synthesizer - Report Loader

Discovers, loads, and normalizes JSON output from 8 upstream skills.
5 required + 3 optional.

Required: market_breadth, uptrend_analysis, market_top, macro_regime, ftd_detector
Optional: vcp_screener, theme_detector, canslim_screener
"""

import glob
import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Skill definitions
# ---------------------------------------------------------------------------

REQUIRED_SKILLS = {
    "market_breadth":   {"prefix": "market_breadth_",   "role": "Market participation breadth"},
    "uptrend_analysis": {"prefix": "uptrend_analysis_", "role": "Sector uptrend ratios"},
    "market_top":       {"prefix": "market_top_",       "role": "Distribution / top risk (defense)"},
    "macro_regime":     {"prefix": "macro_regime_",     "role": "Macro regime transition (1-2Y structure)"},
    "ftd_detector":     {"prefix": "ftd_detector_",     "role": "Bottom confirmation / re-entry (offense)"},
}

OPTIONAL_SKILLS = {
    "vcp_screener":     {"prefix": "vcp_screener_",     "role": "Momentum stock setups (VCP)"},
    "theme_detector":   {"prefix": "theme_detector_",   "role": "Theme / sector momentum"},
    "canslim_screener": {"prefix": "canslim_screener_", "role": "Growth stock setups + M(Market Direction)"},
}

ALL_SKILLS = {**REQUIRED_SKILLS, **OPTIONAL_SKILLS}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def find_latest_report(
    reports_dir: str,
    prefix: str,
    max_age_hours: float = 0,
) -> Optional[Tuple[str, Dict]]:
    """
    Find the most recent JSON report matching *prefix* in *reports_dir*.

    Returns (file_path, parsed_data) or None if no qualifying file found.
    Files are matched by glob and sorted by filename (timestamp order).
    If max_age_hours > 0, files older than that threshold are rejected.
    """
    pattern = os.path.join(reports_dir, f"{prefix}*.json")
    matches = sorted(glob.glob(pattern))
    if not matches:
        return None

    # Most recent = last in sorted list (filenames contain timestamps)
    for path in reversed(matches):
        if max_age_hours > 0:
            mtime = os.path.getmtime(path)
            file_age_hours = (datetime.now().timestamp() - mtime) / 3600
            if file_age_hours > max_age_hours:
                continue
        try:
            with open(path, "r") as f:
                data = json.load(f)
            return (path, data)
        except (json.JSONDecodeError, OSError):
            continue

    return None


def load_all_reports(
    reports_dir: str,
    max_age_hours: float = 72,
) -> Dict[str, Dict]:
    """
    Load all upstream skill JSON reports from *reports_dir*.

    Returns dict mapping skill_name -> parsed JSON data.
    Raises ValueError if any required skill report is missing or stale.
    """
    reports = {}
    missing_required = []

    for skill_name, info in ALL_SKILLS.items():
        result = find_latest_report(reports_dir, info["prefix"], max_age_hours)
        if result is not None:
            _path, data = result
            reports[skill_name] = data
        elif skill_name in REQUIRED_SKILLS:
            missing_required.append(skill_name)

    if missing_required:
        raise ValueError(
            f"Missing required skill reports: {', '.join(missing_required)}. "
            f"Run these skills first or increase --max-age. "
            f"Searched in: {reports_dir}"
        )

    return reports


def extract_signal(skill_name: str, report_data: Dict) -> Dict:
    """
    Extract a normalized signal dict from a skill's JSON output.

    Each skill has its own extraction logic. For skills without a native
    composite_score (VCP, Theme, CANSLIM), a derived score is calculated.
    """
    extractors = {
        "market_breadth":   _extract_breadth,
        "uptrend_analysis": _extract_uptrend,
        "market_top":       _extract_market_top,
        "macro_regime":     _extract_macro_regime,
        "ftd_detector":     _extract_ftd,
        "vcp_screener":     _extract_vcp,
        "theme_detector":   _extract_theme,
        "canslim_screener": _extract_canslim,
    }
    extractor = extractors.get(skill_name)
    if extractor is None:
        raise ValueError(f"Unknown skill: {skill_name}")
    return extractor(report_data)


# ---------------------------------------------------------------------------
# Per-skill extractors
# ---------------------------------------------------------------------------

def _extract_breadth(data: Dict) -> Dict:
    composite = data.get("composite", {})
    return {
        "source": "market_breadth",
        "composite_score": composite.get("composite_score", 0),
        "zone": composite.get("zone", "Unknown"),
        "zone_color": composite.get("zone_color", ""),
        "exposure_guidance": composite.get("exposure_guidance", ""),
    }


def _extract_uptrend(data: Dict) -> Dict:
    composite = data.get("composite", {})
    warnings = composite.get("active_warnings", [])
    return {
        "source": "uptrend_analysis",
        "composite_score": composite.get("composite_score", 0),
        "zone": composite.get("zone", "Unknown"),
        "zone_color": composite.get("zone_color", ""),
        "exposure_guidance": composite.get("exposure_guidance", ""),
        "warning_flags": [w.get("flag", "") for w in warnings],
    }


def _extract_market_top(data: Dict) -> Dict:
    composite = data.get("composite", {})
    return {
        "source": "market_top",
        "composite_score": composite.get("composite_score", 0),
        "zone": composite.get("zone", "Unknown"),
        "zone_color": composite.get("zone_color", ""),
        "risk_budget": composite.get("risk_budget", ""),
        "strongest_warning": composite.get("strongest_warning", {}),
    }


def _extract_macro_regime(data: Dict) -> Dict:
    composite = data.get("composite", {})
    regime = data.get("regime", {})
    transition = regime.get("transition_probability", {})
    return {
        "source": "macro_regime",
        "composite_score": composite.get("composite_score", 0),
        "zone": composite.get("zone", "Unknown"),
        "regime": regime.get("current_regime", "unknown"),
        "regime_label": regime.get("regime_label", "Unknown"),
        "confidence": regime.get("confidence", "unknown"),
        "transition_level": transition.get("level", "unknown"),
        "transition_range": transition.get("probability_range", ""),
    }


def _extract_ftd(data: Dict) -> Dict:
    market_state = data.get("market_state", {})
    quality = data.get("quality_score", {})
    post_ftd = data.get("post_ftd_distribution", {})
    return {
        "source": "ftd_detector",
        "state": market_state.get("combined_state", "NO_SIGNAL"),
        "dual_confirmation": market_state.get("dual_confirmation", False),
        "ftd_index": market_state.get("ftd_index"),
        "quality_score": quality.get("total_score", 0),
        "signal": quality.get("signal", "No FTD"),
        "exposure_range": quality.get("exposure_range", "0-25%"),
        "post_ftd_distribution_count": post_ftd.get("distribution_count", 0),
    }


def _extract_vcp(data: Dict) -> Dict:
    """
    VCP screener lacks a composite_score. Derive one from:
    - Rating distribution: textbook*25 + strong*15 + good*10 + developing*3
    - Funnel health: trend_template_passed / universe ratio
    """
    results = data.get("results", [])
    funnel = data.get("metadata", {}).get("funnel", {})

    # Count by rating
    counts = {"textbook": 0, "strong": 0, "good": 0, "developing": 0}
    for r in results:
        rating = (r.get("rating") or "").lower()
        if "textbook" in rating:
            counts["textbook"] += 1
        elif "strong" in rating:
            counts["strong"] += 1
        elif "good" in rating:
            counts["good"] += 1
        elif "developing" in rating:
            counts["developing"] += 1

    # Weighted quality score (raw points, capped at 100)
    quality_raw = (
        counts["textbook"] * 25
        + counts["strong"] * 15
        + counts["good"] * 10
        + counts["developing"] * 3
    )
    quality_score = min(quality_raw, 100)

    # Funnel health: what % of universe passed trend template
    universe = funnel.get("universe", 1)
    tt_passed = funnel.get("trend_template_passed", 0)
    funnel_ratio = tt_passed / max(universe, 1)
    # Map funnel_ratio to 0-100: 20% pass rate = 100
    funnel_score = min(funnel_ratio / 0.20 * 100, 100)

    derived = round(quality_score * 0.6 + funnel_score * 0.4, 1)

    return {
        "source": "vcp_screener",
        "derived_score": min(derived, 100),
        "quality_score": quality_score,
        "funnel_score": round(funnel_score, 1),
        "textbook_count": counts["textbook"],
        "strong_count": counts["strong"],
        "good_count": counts["good"],
        "developing_count": counts["developing"],
        "total_candidates": len(results),
    }


def _extract_theme(data: Dict) -> Dict:
    """
    Theme detector lacks a composite_score. Derive one from:
    - Hot theme count (heat >= 70)
    - Early stage bonus
    - Exhaustion penalty
    """
    themes = data.get("themes", {}).get("all", [])
    summary = data.get("summary", {})
    bullish_count = summary.get("bullish_count", 0)

    hot_count = 0
    early_count = 0
    exhaustion_count = 0
    total_heat = 0

    for t in themes:
        heat = t.get("heat", 0)
        stage = (t.get("stage") or "").lower()
        direction = (t.get("direction") or "").lower()

        if direction == "bullish" and heat >= 70:
            hot_count += 1
        if stage == "early":
            early_count += 1
        if stage in ("exhausting", "exhaustion"):
            exhaustion_count += 1
        if direction == "bullish":
            total_heat += heat

    # Base score from average heat of bullish themes
    avg_heat = total_heat / max(bullish_count, 1)
    base_score = avg_heat * 0.7  # Scale to ~70 max from heat alone

    # Bonuses and penalties
    early_bonus = early_count * 5  # Up to ~25
    hot_bonus = hot_count * 3     # Up to ~15
    exhaustion_penalty = exhaustion_count * 8  # Up to ~40

    derived = round(base_score + early_bonus + hot_bonus - exhaustion_penalty, 1)
    derived = max(0, min(derived, 100))

    return {
        "source": "theme_detector",
        "derived_score": derived,
        "hot_count": hot_count,
        "early_count": early_count,
        "exhaustion_count": exhaustion_count,
        "bullish_count": bullish_count,
        "avg_heat": round(avg_heat, 1),
    }


def _extract_canslim(data: Dict) -> Dict:
    """
    CANSLIM screener has composite_score per stock.
    Derive overall score from top candidates + M component.
    """
    results = data.get("results", [])
    market = data.get("metadata", {}).get("market_condition", {})

    m_score = market.get("M_score", 50)
    m_trend = market.get("trend", "unknown")

    # Average composite of top 5 stocks (or fewer)
    top_scores = sorted(
        [r.get("composite_score", 0) for r in results],
        reverse=True,
    )[:5]
    avg_top = sum(top_scores) / max(len(top_scores), 1) if top_scores else 0

    # Count by quality tier
    exceptional_count = sum(1 for r in results if r.get("composite_score", 0) >= 90)
    strong_count = sum(1 for r in results if 80 <= r.get("composite_score", 0) < 90)

    # Derived score: average top quality + quality tier bonus
    tier_bonus = exceptional_count * 3 + strong_count * 1.5
    derived = round(min(avg_top * 0.7 + tier_bonus + m_score * 0.15, 100), 1)

    return {
        "source": "canslim_screener",
        "derived_score": derived,
        "m_score": m_score,
        "m_trend": m_trend,
        "top_avg_score": round(avg_top, 1),
        "exceptional_count": exceptional_count,
        "strong_count": strong_count,
        "total_candidates": len(results),
    }
