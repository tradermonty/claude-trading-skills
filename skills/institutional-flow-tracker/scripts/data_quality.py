"""Shared data quality utilities for Institutional Flow Tracker.

Provides holder classification, reliability grading, and filtering logic
shared across track_institutional_flow.py, analyze_single_stock.py, and
track_institution_portfolio.py.

All functions use FMP v3 field names: 'shares', 'change', 'holder'.
The nonexistent fields 'totalShares' and 'totalInvested' are never referenced.
"""

from typing import Dict, List
import re


# --- Known share-class groups for deduplication ---
# Each tuple: (base_symbol_pattern, list_of_variants)
SHARE_CLASS_GROUPS = [
    (re.compile(r"^BRK[.-]?[AB]$"), "BRK"),
    (re.compile(r"^GOOG[L]?$"), "GOOG"),
    (re.compile(r"^PBR[.-]?A?$"), "PBR"),
    (re.compile(r"^RDS[.-]?[AB]$"), "RDS"),
    (re.compile(r"^FCAU?$"), "FCA"),
    (re.compile(r"^(LBTYA|LBTYB|LBTYK)$"), "LBTY"),
    (re.compile(r"^FOX[A]?$"), "FOX"),
    (re.compile(r"^(DISCA|DISCB|DISCK)$"), "DISC"),
    (re.compile(r"^NWS[A]?$"), "NWS"),
    (re.compile(r"^(VIACA|VIAC)$"), "VIAC"),
]


def classify_holder(holder: Dict) -> str:
    """Classify a holder record as genuine, new_full, exited, or unknown.

    Uses FMP v3 fields:
      - 'shares': current position size
      - 'change': QoQ change in shares (provided by FMP)

    Classification rules (applied in order):
      - 'change' key missing -> 'unknown'
      - shares == 0 -> 'exited'
      - change == shares > 0 -> 'new_full' (first appearance, entire position is change)
      - otherwise -> 'genuine' (change != shares, i.e., partial position change)
    """
    shares = holder.get("shares", 0)
    if "change" not in holder:
        return "unknown"
    change = holder.get("change", 0)

    if shares == 0:
        return "exited"

    if shares > 0 and change == shares:
        return "new_full"

    return "genuine"


def calculate_coverage_ratio(
    current_holders: List[Dict], previous_holders: List[Dict]
) -> float:
    """Calculate ratio of current to previous holder counts.

    A high ratio (e.g., 27x) indicates highly asymmetric data where
    most current-quarter holders are new entries, making aggregate
    metrics unreliable.

    Returns:
        float: current_count / previous_count, or inf if previous is empty.
    """
    current_count = len(current_holders)
    previous_count = len(previous_holders)

    if previous_count == 0:
        return float("inf") if current_count > 0 else 0.0
    return current_count / previous_count


def calculate_match_ratio(
    current_holders: List[Dict], previous_holders: List[Dict]
) -> float:
    """Calculate fraction of current holders that also appear in previous quarter.

    Uses the 'holder' field (institution name) for matching.

    Returns:
        float: matched_count / current_count, or 0.0 if no current holders.
    """
    if not current_holders:
        return 0.0

    current_names = {h.get("holder", "") for h in current_holders}
    previous_names = {h.get("holder", "") for h in previous_holders}

    matched = current_names & previous_names
    return len(matched) / len(current_names)


def calculate_filtered_metrics(holders: List[Dict]) -> Dict:
    """Calculate ownership metrics using only genuine holders.

    Filters out new_full and exited holders to avoid inflated
    percent_change from asymmetric data.

    Returns dict with:
        genuine_count: number of genuine holders
        net_change: sum of change for genuine holders
        total_shares_genuine: sum of shares for genuine holders
        pct_change: net_change / previous_total * 100
        buyers: genuine holders with positive change
        sellers: genuine holders with negative change
    """
    genuine = [h for h in holders if classify_holder(h) == "genuine"]

    genuine_count = len(genuine)
    net_change = sum(h.get("change", 0) for h in genuine)
    total_shares = sum(h.get("shares", 0) for h in genuine)

    # previous total = current total - net change
    previous_total = total_shares - net_change
    if previous_total > 0:
        pct_change = (net_change / previous_total) * 100
    else:
        pct_change = 0.0

    buyers = sum(1 for h in genuine if h.get("change", 0) > 0)
    sellers = sum(1 for h in genuine if h.get("change", 0) < 0)

    return {
        "genuine_count": genuine_count,
        "net_change": net_change,
        "total_shares_genuine": total_shares,
        "pct_change": pct_change,
        "buyers": buyers,
        "sellers": sellers,
    }


def reliability_grade(
    coverage_ratio: float, match_ratio: float, genuine_ratio: float
) -> str:
    """Determine data reliability grade based on quality metrics.

    Grades:
        A: coverage_ratio < 3 AND match_ratio >= 0.5 AND genuine_ratio >= 0.7
           -> Safe for investment decisions
        B: genuine_ratio >= 0.3
           -> Reference only (display with warning)
        C: everything else
           -> UNRELIABLE (exclude from rankings)
    """
    if coverage_ratio < 3 and match_ratio >= 0.5 and genuine_ratio >= 0.7:
        return "A"
    if genuine_ratio >= 0.3:
        return "B"
    return "C"


def is_tradable_stock(profile: Dict) -> bool:
    """Check if a stock profile represents a tradable common stock.

    Excludes:
        - ETFs (isEtf == True)
        - Funds (isFund == True)
        - Inactive / delisted stocks (isActivelyTrading == False)
        - Empty profiles (no symbol)
    """
    if not profile or not profile.get("symbol"):
        return False

    if profile.get("isEtf", False):
        return False
    if profile.get("isFund", False):
        return False
    if profile.get("isActivelyTrading", True) is False:
        return False

    return True


def _get_share_class_group(symbol: str) -> str:
    """Return the group key for a symbol if it's a known share class variant."""
    for pattern, group_key in SHARE_CLASS_GROUPS:
        if pattern.match(symbol):
            return group_key
    return ""


def deduplicate_share_classes(results: List[Dict]) -> List[Dict]:
    """Remove duplicate share class entries, keeping the one with higher market_cap.

    Known share class groups: BRK-A/B, GOOG/GOOGL, PBR/PBR-A, etc.

    Args:
        results: list of dicts with at least 'symbol' and 'market_cap' keys.

    Returns:
        Deduplicated list preserving original order for non-duplicate entries.
    """
    if not results:
        return []

    # Group by share class
    groups: Dict[str, List[int]] = {}
    for i, r in enumerate(results):
        group = _get_share_class_group(r.get("symbol", ""))
        if group:
            groups.setdefault(group, []).append(i)

    # Find indices to remove (keep the one with highest market_cap)
    remove_indices = set()
    for group_key, indices in groups.items():
        if len(indices) <= 1:
            continue
        # Keep the one with highest market_cap
        best_idx = max(indices, key=lambda i: results[i].get("market_cap", 0))
        for idx in indices:
            if idx != best_idx:
                remove_indices.add(idx)

    return [r for i, r in enumerate(results) if i not in remove_indices]
