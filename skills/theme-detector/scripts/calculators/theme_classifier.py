#!/usr/bin/env python3
"""
Theme Classifier - Detect cross-sector and vertical themes from ranked industries.

Cross-sector themes match industries against keyword templates (min 2 matches).
Vertical themes detect sector concentration (min 3 same-sector industries in top/bottom).

themes_config format:
{
    "cross_sector": [
        {
            "theme_name": str,
            "matching_keywords": [str, ...],
            "proxy_etfs": [str, ...],
            "static_stocks": [str, ...],
        },
        ...
    ],
    "vertical_min_industries": int,   # default 3
    "cross_sector_min_matches": int,  # default 2
}
"""

from collections import Counter
from typing import Dict, List


def classify_themes(
    ranked_industries: List[Dict],
    themes_config: Dict,
) -> List[Dict]:
    """
    Match ranked industries to cross-sector and vertical themes.

    Args:
        ranked_industries: Output of rank_industries (sorted by momentum_score desc).
        themes_config: Theme definitions with cross_sector templates and thresholds.

    Returns:
        List of theme result dicts, each with:
            theme_name, direction, matching_industries, sector_weights,
            proxy_etfs, static_stocks
    """
    if not ranked_industries:
        return []

    cross_sector_min = themes_config.get("cross_sector_min_matches", 2)
    vertical_min = themes_config.get("vertical_min_industries", 3)
    cross_sector_defs = themes_config.get("cross_sector", [])

    themes = []

    # 1. Cross-sector theme matching
    industry_names = {ind["name"] for ind in ranked_industries}
    industry_by_name = {ind["name"]: ind for ind in ranked_industries}

    for theme_def in cross_sector_defs:
        keywords = theme_def.get("matching_keywords", [])
        matches = [kw for kw in keywords if kw in industry_names]

        if len(matches) >= cross_sector_min:
            matching_inds = [industry_by_name[m] for m in matches]
            direction = _majority_direction(matching_inds)
            sector_weights = get_theme_sector_weights(
                {"matching_industries": matching_inds}
            )

            themes.append({
                "theme_name": theme_def["theme_name"],
                "direction": direction,
                "matching_industries": matching_inds,
                "sector_weights": sector_weights,
                "proxy_etfs": theme_def.get("proxy_etfs", []),
                "static_stocks": theme_def.get("static_stocks", []),
            })

    # 2. Vertical (single-sector) theme detection
    # Count industries per sector in the full ranked list
    sector_groups: Dict[str, List[Dict]] = {}
    for ind in ranked_industries:
        sector = ind.get("sector")
        if sector is None:
            continue
        sector_groups.setdefault(sector, []).append(ind)

    for sector, inds in sector_groups.items():
        if len(inds) >= vertical_min:
            direction = _majority_direction(inds)
            sector_weights = get_theme_sector_weights(
                {"matching_industries": inds}
            )
            themes.append({
                "theme_name": f"{sector} Sector Concentration",
                "direction": direction,
                "matching_industries": inds,
                "sector_weights": sector_weights,
                "proxy_etfs": [],
                "static_stocks": [],
            })

    return themes


def get_theme_sector_weights(theme: Dict) -> Dict[str, float]:
    """
    Calculate sector weight distribution for a theme's matching industries.

    Args:
        theme: Dict with "matching_industries" key containing industry dicts
               (each may have a "sector" field).

    Returns:
        Dict mapping sector name to its proportion (0.0-1.0).
        Industries without a sector field are excluded.
    """
    matching = theme.get("matching_industries", [])
    sectors = [ind["sector"] for ind in matching if "sector" in ind]

    if not sectors:
        return {}

    counts = Counter(sectors)
    total = sum(counts.values())

    return {sector: count / total for sector, count in counts.items()}


def _majority_direction(industries: List[Dict]) -> str:
    """Determine majority direction from a list of industries."""
    bullish = sum(1 for ind in industries if ind.get("direction") == "bullish")
    bearish = len(industries) - bullish
    return "bullish" if bullish > bearish else "bearish"
