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


# Sector-to-representative-stocks mapping for vertical theme enrichment
SECTOR_REPRESENTATIVE_STOCKS: Dict[str, List[str]] = {
    "Technology": ["AAPL", "MSFT", "NVDA", "AVGO", "CRM"],
    "Consumer Cyclical": ["AMZN", "TSLA", "HD", "MCD", "NKE"],
    "Consumer Defensive": ["PG", "KO", "PEP", "WMT", "COST"],
    "Industrials": ["CAT", "HON", "UPS", "GE", "RTX"],
    "Healthcare": ["UNH", "JNJ", "LLY", "PFE", "ABBV"],
    "Financial": ["JPM", "BAC", "GS", "V", "MA"],
    "Energy": ["XOM", "CVX", "COP", "SLB", "EOG"],
    "Basic Materials": ["LIN", "APD", "NEM", "FCX", "NUE"],
    "Communication Services": ["META", "GOOGL", "NFLX", "DIS", "TMUS"],
    "Real Estate": ["PLD", "AMT", "EQIX", "SPG", "O"],
    "Utilities": ["NEE", "DUK", "SO", "D", "AEP"],
}

# Sector-to-ETF mapping for vertical theme enrichment
SECTOR_ETFS: Dict[str, List[str]] = {
    "Energy": ["XLE"],
    "Technology": ["XLK"],
    "Basic Materials": ["XLB"],
    "Industrials": ["XLI"],
    "Consumer Cyclical": ["XLY"],
    "Consumer Defensive": ["XLP"],
    "Healthcare": ["XLV"],
    "Financial": ["XLF"],
    "Communication Services": ["XLC"],
    "Real Estate": ["XLRE"],
    "Utilities": ["XLU"],
}


def _industry_overlap_ratio(theme_a: Dict, theme_b: Dict) -> float:
    """Calculate industry name overlap ratio between two themes.

    Returns the Jaccard-like ratio: |intersection| / |smaller set|.
    """
    names_a = {ind.get("name") for ind in theme_a.get("matching_industries", [])}
    names_b = {ind.get("name") for ind in theme_b.get("matching_industries", [])}
    if not names_a or not names_b:
        return 0.0
    intersection = names_a & names_b
    smaller = min(len(names_a), len(names_b))
    return len(intersection) / smaller if smaller > 0 else 0.0


def enrich_vertical_themes(themes: List[Dict]) -> None:
    """Add ETFs and stocks to vertical themes from overlapping seeds or sector mapping.

    Mutates vertical themes in place:
    1. If a seed theme shares >= 50% industry overlap, inherit its ETFs/stocks.
    2. Otherwise, assign sector ETF from SECTOR_ETFS mapping.
    """
    seed_themes = [t for t in themes if t.get("theme_origin") == "seed"]

    for theme in themes:
        if theme.get("theme_origin") != "vertical":
            continue
        if theme.get("proxy_etfs"):
            continue  # already has ETFs

        # Try inheriting from overlapping seed theme
        best_seed = None
        best_overlap = 0.0
        for seed in seed_themes:
            overlap = _industry_overlap_ratio(theme, seed)
            if overlap > best_overlap:
                best_overlap = overlap
                best_seed = seed

        if best_seed and best_overlap >= 0.5:
            theme["proxy_etfs"] = list(best_seed.get("proxy_etfs", []))
            theme["static_stocks"] = list(best_seed.get("static_stocks", []))
            continue

        # Sector ETF fallback
        sector_weights = theme.get("sector_weights", {})
        if sector_weights:
            primary_sector = max(sector_weights, key=sector_weights.get)
            etfs = SECTOR_ETFS.get(primary_sector, [])
            if etfs:
                theme["proxy_etfs"] = list(etfs)
        else:
            # Infer sector from matching industries
            sectors = [ind.get("sector") for ind in theme.get("matching_industries", [])
                       if ind.get("sector")]
            if sectors:
                primary = max(set(sectors), key=sectors.count)
                etfs = SECTOR_ETFS.get(primary, [])
                if etfs:
                    theme["proxy_etfs"] = list(etfs)

    # Fill empty static_stocks for vertical themes from sector mapping
    for theme in themes:
        if theme.get("theme_origin") != "vertical":
            continue
        if theme.get("static_stocks"):
            continue  # already has stocks

        sector_weights = theme.get("sector_weights", {})
        if sector_weights:
            primary_sector = max(sector_weights, key=sector_weights.get)
        else:
            sectors = [ind.get("sector") for ind in theme.get("matching_industries", [])
                       if ind.get("sector")]
            primary_sector = max(set(sectors), key=sectors.count) if sectors else None

        if primary_sector:
            stocks = SECTOR_REPRESENTATIVE_STOCKS.get(primary_sector, [])
            if stocks:
                theme["static_stocks"] = list(stocks)


def deduplicate_themes(themes: List[Dict], overlap_threshold: float = 0.5) -> List[Dict]:
    """Remove vertical themes that duplicate seed themes.

    A vertical theme is removed if:
    - Same direction as a seed theme
    - Industry overlap ratio >= overlap_threshold

    Seed themes are always kept. Returns a new list.
    """
    seed_themes = [t for t in themes if t.get("theme_origin") == "seed"]
    result = list(seed_themes)

    for theme in themes:
        if theme.get("theme_origin") == "seed":
            continue

        is_duplicate = False
        for seed in seed_themes:
            if theme.get("direction") != seed.get("direction"):
                continue
            overlap = _industry_overlap_ratio(theme, seed)
            if overlap >= overlap_threshold:
                is_duplicate = True
                break

        if not is_duplicate:
            result.append(theme)

    return result


def _majority_direction(industries: List[Dict]) -> str:
    """Determine majority direction from rank_direction (falls back to direction)."""
    bullish = sum(
        1 for ind in industries
        if ind.get("rank_direction", ind.get("direction")) == "bullish"
    )
    bearish = len(industries) - bullish
    return "bullish" if bullish > bearish else "bearish"
