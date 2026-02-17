"""Theme Discoverer - Automatic theme detection from unmatched industries.

Finds clusters of unmatched industries with similar performance patterns
and generates new theme entries compatible with classify_themes() output.

Algorithm:
1. Extract top_n and bottom_n from ranked_industries, exclude matched names.
2. Separate into bullish (top) and bearish (bottom) groups.
3. Sort each group by weighted_return.
4. Cluster adjacent industries that satisfy BOTH:
   a. weighted_return gap <= gap_threshold
   b. perf vector distance <= vector_threshold (normalized Euclidean)
5. Filter clusters by min_cluster_size.
6. Exclude clusters that overlap significantly with existing themes.
7. Auto-name clusters from industry name tokens.
"""

import math
from collections import Counter
from typing import Dict, List, Set, Tuple

from calculators.theme_classifier import get_theme_sector_weights

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_GAP_THRESHOLD_PCT = 3.0
_VECTOR_THRESHOLD = 0.5
_MIN_CLUSTER_SIZE = 2
_OVERLAP_THRESHOLD = 0.5

_STOP_WORDS = {
    "Services", "Products", "Equipment", "Materials", "General",
    "Other", "Specialty", "Diversified", "Regulated", "Independent",
    "&", "-", "and",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def discover_themes(
    ranked_industries: List[Dict],
    matched_names: Set[str],
    existing_themes: List[Dict],
    top_n: int = 30,
    gap_threshold: float = _GAP_THRESHOLD_PCT,
    vector_threshold: float = _VECTOR_THRESHOLD,
    min_cluster_size: int = _MIN_CLUSTER_SIZE,
) -> List[Dict]:
    """Discover new themes from unmatched industries.

    Args:
        ranked_industries: Full ranked list (sorted by momentum_score desc).
        matched_names: Set of industry names already matched by seed/vertical.
        existing_themes: List of existing theme dicts (for overlap detection).
        top_n: Number of top/bottom industries to consider.
        gap_threshold: Max weighted_return gap between adjacent industries.
        vector_threshold: Max normalized Euclidean distance for perf vectors.
        min_cluster_size: Minimum industries to form a cluster.

    Returns:
        List of theme dicts compatible with classify_themes() output,
        each with theme_origin="discovered" and name_confidence="medium".
    """
    bullish, bearish = _get_unmatched_industries(ranked_industries, matched_names, top_n)

    discovered = []
    for group, direction in [(bullish, "bullish"), (bearish, "bearish")]:
        clusters = _cluster_by_proximity(group, gap_threshold, vector_threshold)
        for cluster in clusters:
            if len(cluster) < min_cluster_size:
                continue
            if _is_duplicate_of_existing(cluster, direction, existing_themes):
                continue
            name = _auto_name_cluster(cluster)
            theme = _build_theme_dict(name, cluster)
            discovered.append(theme)

    return discovered


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_unmatched_industries(
    ranked: List[Dict],
    matched_names: Set[str],
    top_n: int,
) -> Tuple[List[Dict], List[Dict]]:
    """Extract unmatched industries from top N and bottom N.

    Returns:
        (bullish_unmatched, bearish_unmatched)
    """
    top = ranked[:top_n]
    bottom = ranked[-top_n:] if len(ranked) > top_n else []

    # Deduplicate: industries in both top and bottom only appear in top
    top_names = {ind["name"] for ind in top}

    bullish = [
        ind for ind in top
        if ind["name"] not in matched_names and ind.get("direction") == "bullish"
    ]
    bearish = [
        ind for ind in bottom
        if ind["name"] not in matched_names
        and ind["name"] not in top_names
        and ind.get("direction") == "bearish"
    ]

    return bullish, bearish


def _cluster_by_proximity(
    industries: List[Dict],
    gap_threshold: float,
    vector_threshold: float,
) -> List[List[Dict]]:
    """Cluster industries by weighted_return proximity and perf vector distance.

    Industries are sorted by weighted_return. Adjacent pairs are joined into
    the same cluster if BOTH conditions are met:
    1. abs(weighted_return difference) <= gap_threshold
    2. perf_vector_distance <= vector_threshold

    Returns:
        List of clusters (each cluster is a list of industry dicts).
        Only clusters with >= 2 members are returned.
    """
    if not industries:
        return []

    sorted_inds = sorted(industries, key=lambda x: x.get("weighted_return", 0), reverse=True)
    ranges = _compute_ranges(sorted_inds)

    clusters: List[List[Dict]] = [[sorted_inds[0]]]

    for i in range(1, len(sorted_inds)):
        prev = sorted_inds[i - 1]
        curr = sorted_inds[i]

        gap = abs(prev.get("weighted_return", 0) - curr.get("weighted_return", 0))
        vec_dist = _perf_vector_distance(prev, curr, ranges)

        if gap <= gap_threshold and vec_dist <= vector_threshold:
            clusters[-1].append(curr)
        else:
            clusters.append([curr])

    # Filter to min size 2
    return [c for c in clusters if len(c) >= 2]


def _perf_vector_distance(a: Dict, b: Dict, ranges: Dict) -> float:
    """Normalized Euclidean distance between perf vectors (1W, 1M, 3M).

    Each timeframe difference is normalized by the range (max - min) across
    all industries in the group. If range is 0, that dimension is ignored.

    Returns:
        0.0 (identical) to ~1.7 (maximally different across all 3 dimensions).
    """
    keys = ["perf_1w", "perf_1m", "perf_3m"]
    total = 0.0

    for key in keys:
        r = ranges.get(key, 0)
        if r == 0:
            continue
        diff = (a.get(key, 0) - b.get(key, 0)) / r
        total += diff * diff

    return math.sqrt(total)


def _compute_ranges(industries: List[Dict]) -> Dict[str, float]:
    """Compute value ranges for perf normalization."""
    keys = ["perf_1w", "perf_1m", "perf_3m"]
    ranges = {}
    for key in keys:
        vals = [ind.get(key, 0) for ind in industries]
        if vals:
            ranges[key] = max(vals) - min(vals)
        else:
            ranges[key] = 0
    return ranges


def _auto_name_cluster(industries: List[Dict]) -> str:
    """Generate a descriptive name for a cluster from industry name tokens.

    Tokenizes all industry names, removes stop words, picks the top 2
    most frequent tokens and joins them.
    """
    tokens: List[str] = []
    for ind in industries:
        name = ind.get("name", "")
        for token in name.split():
            cleaned = token.strip("(),")
            if cleaned and cleaned not in _STOP_WORDS:
                tokens.append(cleaned)

    if not tokens:
        return "Unknown Cluster"

    counts = Counter(tokens)
    top = counts.most_common(3)

    if len(top) >= 2:
        return f"{top[0][0]} & {top[1][0]} Related"
    elif len(top) == 1:
        return f"{top[0][0]} Related"
    return "Unknown Cluster"


def _is_duplicate_of_existing(
    cluster_industries: List[Dict],
    cluster_direction: str,
    existing_themes: List[Dict],
    overlap_threshold: float = _OVERLAP_THRESHOLD,
) -> bool:
    """Check if a discovered cluster duplicates an existing theme.

    A cluster is considered duplicate if:
    1. Direction matches an existing theme, AND
    2. Jaccard similarity of industry names >= threshold

    This uses industry overlap (not name-based matching) to catch
    renamed themes with the same constituent industries.
    """
    cluster_names = {ind.get("name", "") for ind in cluster_industries}
    if not cluster_names:
        return False

    for theme in existing_themes:
        if theme.get("direction") != cluster_direction:
            continue
        theme_names = {ind.get("name", "") for ind in theme.get("matching_industries", [])}
        if not theme_names:
            continue
        intersection = cluster_names & theme_names
        union = cluster_names | theme_names
        jaccard = len(intersection) / len(union) if union else 0
        if jaccard >= overlap_threshold:
            return True

    return False


def _build_theme_dict(name: str, industries: List[Dict]) -> Dict:
    """Build a theme dict compatible with classify_themes() output.

    Discovered themes have proxy_etfs=[], static_stocks=[],
    theme_origin="discovered", name_confidence="medium".
    """
    # Determine direction from majority
    bullish = sum(1 for ind in industries if ind.get("direction") == "bullish")
    bearish = len(industries) - bullish
    direction = "bullish" if bullish > bearish else "bearish"

    sector_weights = get_theme_sector_weights({"matching_industries": industries})

    return {
        "theme_name": name,
        "direction": direction,
        "matching_industries": industries,
        "sector_weights": sector_weights,
        "proxy_etfs": [],
        "static_stocks": [],
        "theme_origin": "discovered",
        "name_confidence": "medium",
    }
