"""Shared data quality utilities for Institutional Flow Tracker.

Provides tradability filtering, share-class deduplication, and reliability
grading shared across track_institutional_flow.py and analyze_single_stock.py.

Data source (FMP /stable):
    - institutional-ownership/symbol-positions-summary -> per-quarter aggregate
      flows (investorsHolding, numberOf13Fshares, increasedPositions, ...),
      already reconciled server-side by FMP.
    - institutional-ownership/extract-analytics/holder -> per-investor rows
      (investorName, sharesNumber, changeInSharesNumber, isNew, isSoldOut, ...).

Reliability is graded from FMP's own coverage signals (holder breadth +
whether a comparable prior quarter exists), which is how institutional-flow
analysis is graded in practice (ownership breadth / dynamics). The legacy
per-holder genuine/coverage/match reconciliation was a client-side workaround
for the retired /api/v3 institutional-holder feed, which returned asymmetric
holder lists across quarters; the /stable summary endpoint reconciles those
deltas at source, so that machinery no longer applies.
"""

import re

# --- Known share-class groups for deduplication ---
# Each tuple: (base_symbol_pattern, group_key)
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

# Default breadth thresholds for coverage_grade(). A stock needs a comparable
# prior quarter and enough 13F holders for the aggregate change to be meaningful.
MIN_RELIABLE_HOLDERS = 50  # Grade A: dense, well-covered name
MIN_USABLE_HOLDERS = 10  # Grade B floor; below this -> Grade C (excluded)


def coverage_grade(
    investors_holding: int,
    last_investors_holding: int,
    *,
    min_reliable: int = MIN_RELIABLE_HOLDERS,
    min_usable: int = MIN_USABLE_HOLDERS,
) -> str:
    """Grade reliability of an aggregate 13F summary from FMP coverage signals.

    Institutional-flow signals are graded on ownership *breadth* (how many
    managers hold the name) and whether a comparable prior quarter exists to
    measure change against.

    Grades:
        A: prior quarter present AND breadth >= min_reliable
           -> dense coverage, safe for ranking.
        B: prior quarter present AND breadth >= min_usable
           -> usable but thin; reference only.
        C: no prior quarter (change not measurable) OR breadth < min_usable
           -> insufficient coverage; exclude from rankings.
    """
    if last_investors_holding <= 0 or investors_holding < min_usable:
        return "C"
    if investors_holding >= min_reliable:
        return "A"
    return "B"


def iter_quarters(year: int, quarter: int, count: int):
    """Yield ``count`` (year, quarter) tuples descending from (year, quarter).

    Example: iter_quarters(2026, 1, 3) -> (2026, 1), (2025, 4), (2025, 3).
    """
    y, q = year, quarter
    for _ in range(count):
        yield (y, q)
        q -= 1
        if q == 0:
            q = 4
            y -= 1


def current_quarter(as_of) -> tuple[int, int]:
    """Return the (year, quarter) of the calendar quarter containing ``as_of``.

    ``as_of`` is a datetime.date (or datetime). Used as the starting point for
    walking back to the most recent quarter that has 13F data filed.
    """
    return (as_of.year, (as_of.month - 1) // 3 + 1)


def quarter_end_date(year: int, quarter: int) -> str:
    """Return the calendar quarter-end date as 'YYYY-MM-DD'."""
    month, day = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}[quarter]
    return f"{year:04d}-{month:02d}-{day:02d}"


def normalize_holder(raw: dict) -> dict:
    """Map a /stable extract-analytics/holder row to a compact holder record.

    Returns keys: name, shares, change, is_new, is_sold_out. Investor names are
    occasionally blank in the feed (a CIK with no resolved name); those fall
    back to a 'CIK <id>' label, or 'Unknown' if the CIK is also missing.
    """
    name = (raw.get("investorName") or "").strip()
    if not name:
        cik = str(raw.get("cik") or "").strip()
        name = f"CIK {cik}" if cik else "Unknown"
    return {
        "name": name,
        "shares": raw.get("sharesNumber", 0) or 0,
        "change": raw.get("changeInSharesNumber", 0) or 0,
        "is_new": bool(raw.get("isNew", False)),
        "is_sold_out": bool(raw.get("isSoldOut", False)),
    }


def is_tradable_stock(profile: dict) -> bool:
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


def deduplicate_share_classes(results: list[dict]) -> list[dict]:
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
    groups: dict[str, list[int]] = {}
    for i, r in enumerate(results):
        group = _get_share_class_group(r.get("symbol", ""))
        if group:
            groups.setdefault(group, []).append(i)

    # Find indices to remove (keep the one with highest market_cap)
    remove_indices = set()
    for _group_key, indices in groups.items():
        if len(indices) <= 1:
            continue
        # Keep the one with highest market_cap
        best_idx = max(indices, key=lambda i: results[i].get("market_cap", 0))
        for idx in indices:
            if idx != best_idx:
                remove_indices.add(idx)

    return [r for i, r in enumerate(results) if i not in remove_indices]
