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
from typing import Dict, List, Set


def classify_themes(
    ranked_industries: List[Dict],
    themes_config: Dict,
    top_n: int = 30,
) -> List[Dict]:
    """
    Match ranked industries to cross-sector and vertical themes.

    Only the top N and bottom N industries (by momentum rank) are considered
    for theme matching. This prevents themes from always matching when using
    the full ~145 industry universe.

    Args:
        ranked_industries: Output of rank_industries (sorted by momentum_score desc).
        themes_config: Theme definitions with cross_sector templates and thresholds.
        top_n: Number of top/bottom industries to consider (default 30).

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

    # Build active set from top N + bottom N (deduplicated)
    top = ranked_industries[:top_n]
    bottom = ranked_industries[-top_n:] if len(ranked_industries) > top_n else []
    active_set: Dict[str, Dict] = {ind["name"]: ind for ind in top}
    for ind in bottom:
        if ind["name"] not in active_set:
            active_set[ind["name"]] = ind

    themes = []

    # 1. Cross-sector theme matching (active set only)
    for theme_def in cross_sector_defs:
        keywords = theme_def.get("matching_keywords", [])
        matches = [kw for kw in keywords if kw in active_set]

        if len(matches) >= cross_sector_min:
            matching_inds = [active_set[m] for m in matches]
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
                "theme_origin": "seed",
                "name_confidence": "high",
            })

    # 2. Vertical (single-sector) theme detection
    # Count industries per sector in top N and bottom N separately
    top_set = set(ind["name"] for ind in top)
    bottom_set = set(ind["name"] for ind in bottom) - top_set

    # Top N sector groups
    top_sector_groups: Dict[str, List[Dict]] = {}
    for ind in top:
        sector = ind.get("sector")
        if sector is None:
            continue
        top_sector_groups.setdefault(sector, []).append(ind)

    for sector, inds in top_sector_groups.items():
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
                "theme_origin": "vertical",
                "name_confidence": "high",
            })

    # Bottom N sector groups (excluding industries already in top N)
    bottom_sector_groups: Dict[str, List[Dict]] = {}
    for ind in bottom:
        if ind["name"] in top_set:
            continue
        sector = ind.get("sector")
        if sector is None:
            continue
        bottom_sector_groups.setdefault(sector, []).append(ind)

    for sector, inds in bottom_sector_groups.items():
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
                "theme_origin": "vertical",
                "name_confidence": "high",
            })

    return themes


def get_matched_industry_names(themes: List[Dict]) -> Set[str]:
    """Return the set of all matched industry names across classified themes.

    Args:
        themes: Output of classify_themes().

    Returns:
        Set of industry name strings.
    """
    names: Set[str] = set()
    for theme in themes:
        for ind in theme.get("matching_industries", []):
            name = ind.get("name", "")
            if name:
                names.add(name)
    return names


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
