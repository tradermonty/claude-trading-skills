#!/usr/bin/env python3
"""
I Component - Institutional Sponsorship Calculator (Full Implementation)

Calculates CANSLIM 'I' component score based on institutional holder count and ownership percentage.

O'Neil's Rule: "You need some of the big boys on your side. Look for stocks with increasing
institutional sponsorship, but not too much. The sweet spot is 50-100 institutional holders
with 30-60% ownership."

Key Principles:
- 50-100 holders: Enough interest, not overcrowded
- 30-60% ownership: Strong backing without lock-up
- <30%: Underowned (potential upside, but may lack institutional support)
- >80%: Overcrowded (no buying power left, vulnerable to selling)
- Superinvestors (Berkshire, Baupost, etc.): Quality signal

Scoring:
- 100 points: 50-100 holders + 30-60% ownership (O'Neil's sweet spot)
- 90 points: Superinvestor present + good holder count
- 80 points: 30-50 holders + 20-40% ownership OR 100-150 holders + 40-70% ownership
- 60 points: Acceptable but suboptimal ranges
- 40 points: <20% or >80% ownership
- 20 points: <10% or >90% ownership
- 0 points: Institutional data unavailable or extreme ranges
"""

from typing import Dict, List, Optional
import sys
import os

# Optional: Import Finviz client for fallback data (requires finviz library)
try:
    # Add parent directory to path to import finviz_stock_client
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from finviz_stock_client import FinvizStockClient
    FINVIZ_AVAILABLE = True
except ImportError:
    FINVIZ_AVAILABLE = False
    print("INFO: finviz library not available. Install with 'pip install finviz' for improved institutional data.", file=sys.stderr)


# List of superinvestors (legendary value investors whose presence signals quality)
SUPERINVESTORS = [
    "BERKSHIRE HATHAWAY",
    "BAUPOST GROUP",
    "PERSHING SQUARE",
    "GREENLIGHT CAPITAL",
    "THIRD POINT",
    "APPALOOSA MANAGEMENT",
    "VIKING GLOBAL",
    "SCION ASSET MANAGEMENT",  # Michael Burry
    "BRIDGEWATER ASSOCIATES",  # Ray Dalio
    "RENAISSANCE TECHNOLOGIES"
]


def calculate_institutional_sponsorship(
    institutional_holders: List[Dict],
    profile: Optional[Dict] = None,
    symbol: Optional[str] = None,
    use_finviz_fallback: bool = True
) -> Dict:
    """
    Calculate institutional sponsorship score (Full Implementation with Finviz fallback)

    Args:
        institutional_holders: List of institutional holders from FMP API
                              Each entry: {"holder": str, "shares": int, "dateReported": str, "change": int}
        profile: Company profile dict (optional, for shares outstanding)
        symbol: Stock ticker symbol (optional, required for Finviz fallback)
        use_finviz_fallback: If True, use Finviz data when FMP ownership % unavailable (default: True)

    Returns:
        Dict with:
            - score: 0-100 points
            - num_holders: Number of institutional holders
            - ownership_pct: Institutional ownership percentage
            - superinvestor_present: True if superinvestor detected
            - superinvestors: List of superinvestors holding the stock
            - total_shares_held: Total shares held by institutions
            - shares_outstanding: Total shares outstanding (from profile)
            - interpretation: Human-readable interpretation
            - quality_warning: Warning if data quality issues
            - error: Error message if calculation failed

    Example:
        >>> holders = client.get_institutional_holders("NVDA")
        >>> profile = client.get_profile("NVDA")[0]
        >>> result = calculate_institutional_sponsorship(holders, profile)
        >>> print(f"I Score: {result['score']}, Holders: {result['num_holders']}, Ownership: {result['ownership_pct']:.1f}%")
    """
    # Validate input
    if not institutional_holders:
        return {
            "score": 0,
            "error": "No institutional holder data available",
            "num_holders": 0,
            "ownership_pct": None,
            "superinvestor_present": False,
            "superinvestors": [],
            "total_shares_held": None,
            "shares_outstanding": None,
            "interpretation": "Data unavailable"
        }

    # Count institutional holders
    num_holders = len(institutional_holders)

    # Check for superinvestors
    superinvestors_found = []
    for holder_entry in institutional_holders:
        holder_name = holder_entry.get("holder", "").upper()
        for superinvestor in SUPERINVESTORS:
            if superinvestor in holder_name:
                superinvestors_found.append(holder_entry.get("holder"))
                break

    superinvestor_present = len(superinvestors_found) > 0

    # Calculate total shares held by institutions
    total_shares_held = sum(
        holder.get("shares", 0) for holder in institutional_holders
    )

    # Calculate ownership percentage (requires shares outstanding from profile)
    ownership_pct = None
    shares_outstanding = None
    quality_warning = None
    data_source = "FMP"  # Track data source

    if profile:
        # Try to get shares outstanding (different field names possible)
        shares_outstanding = profile.get("sharesOutstanding")

        # Fallback: calculate from market cap and price
        if not shares_outstanding:
            market_cap = profile.get("marketCap")
            price = profile.get("price")
            if market_cap and price and price > 0:
                shares_outstanding = market_cap / price

        if shares_outstanding and shares_outstanding > 0:
            ownership_pct = (total_shares_held / shares_outstanding) * 100
        else:
            quality_warning = "Shares outstanding unavailable from FMP."
    else:
        quality_warning = "Company profile not provided."

    # Finviz fallback: If ownership % still unavailable, try Finviz
    if ownership_pct is None and use_finviz_fallback and FINVIZ_AVAILABLE and symbol:
        try:
            finviz_client = FinvizStockClient(rate_limit_seconds=1.0)
            finviz_data = finviz_client.get_institutional_ownership(symbol)

            if finviz_data and finviz_data.get('inst_own_pct') is not None:
                ownership_pct = finviz_data['inst_own_pct']
                data_source = "Finviz"
                quality_warning = f"Using Finviz institutional ownership data ({ownership_pct:.1f}%) - FMP shares outstanding unavailable."
                print(f"✅ Using Finviz institutional ownership for {symbol}: {ownership_pct:.1f}%", file=sys.stderr)
            else:
                quality_warning += " Finviz fallback also unavailable. Score reduced by 50%."
        except Exception as e:
            print(f"WARNING: Finviz fallback failed for {symbol}: {e}", file=sys.stderr)
            quality_warning += " Finviz fallback failed. Score reduced by 50%."

    # Final warning if ownership % still unavailable
    if ownership_pct is None:
        if not quality_warning:
            quality_warning = "Ownership % unavailable from all sources. Score reduced by 50%."
        else:
            quality_warning += " Score reduced by 50%."

    # Score institutional sponsorship
    score = score_institutional_sponsorship(
        num_holders, ownership_pct, superinvestor_present, quality_warning
    )

    # Generate interpretation
    interpretation = interpret_institutional_sponsorship(
        num_holders, ownership_pct, superinvestor_present, superinvestors_found
    )

    return {
        "score": score,
        "num_holders": num_holders,
        "ownership_pct": ownership_pct,
        "superinvestor_present": superinvestor_present,
        "superinvestors": superinvestors_found,
        "total_shares_held": total_shares_held,
        "shares_outstanding": shares_outstanding,
        "interpretation": interpretation,
        "quality_warning": quality_warning,
        "data_source": data_source  # "FMP" or "Finviz"
    }


def score_institutional_sponsorship(
    num_holders: int,
    ownership_pct: Optional[float],
    superinvestor_present: bool,
    quality_warning: Optional[str]
) -> int:
    """
    Score institutional sponsorship based on O'Neil's criteria

    Args:
        num_holders: Number of institutional holders
        ownership_pct: Institutional ownership percentage (None if unavailable)
        superinvestor_present: True if superinvestor detected
        quality_warning: Data quality warning

    Returns:
        int: Score from 0-100
    """
    # If ownership % unavailable, score on holder count only (reduced scale)
    if ownership_pct is None:
        if num_holders >= 50 and num_holders <= 100:
            base_score = 50  # Half of ideal score
        elif num_holders >= 30 and num_holders < 50:
            base_score = 40
        elif num_holders > 100 and num_holders <= 150:
            base_score = 35
        elif num_holders > 150:
            base_score = 20
        else:
            base_score = 10

        # Superinvestor bonus (even without ownership %)
        if superinvestor_present:
            base_score += 15

        return min(base_score, 70)  # Cap at 70 when ownership % unavailable

    # Full scoring with ownership %
    base_score = 0

    # O'Neil's Sweet Spot: 50-100 holders + 30-60% ownership
    if 50 <= num_holders <= 100 and 30 <= ownership_pct <= 60:
        base_score = 100
    # Superinvestor present + good holder count
    elif superinvestor_present and 30 <= num_holders <= 150:
        base_score = 90
    # Good ranges (slightly outside sweet spot)
    elif (30 <= num_holders < 50 and 20 <= ownership_pct <= 40) or \
         (100 < num_holders <= 150 and 40 <= ownership_pct <= 70):
        base_score = 80
    # Acceptable ranges
    elif (20 <= num_holders < 30 and 20 <= ownership_pct <= 50) or \
         (50 <= num_holders <= 150 and 20 <= ownership_pct <= 70):
        base_score = 60
    # Suboptimal ownership
    elif ownership_pct < 20 or ownership_pct > 80:
        base_score = 40
    # Extreme ownership
    elif ownership_pct < 10 or ownership_pct > 90:
        base_score = 20
    else:
        base_score = 50  # Default for other combinations

    # Superinvestor bonus
    if superinvestor_present and base_score < 100:
        base_score = min(base_score + 10, 100)

    return base_score


def interpret_institutional_sponsorship(
    num_holders: int,
    ownership_pct: Optional[float],
    superinvestor_present: bool,
    superinvestors: List[str]
) -> str:
    """
    Generate human-readable interpretation

    Args:
        num_holders: Number of institutional holders
        ownership_pct: Institutional ownership percentage
        superinvestor_present: True if superinvestor detected
        superinvestors: List of superinvestor names

    Returns:
        str: Interpretation string
    """
    # Holder count assessment
    if 50 <= num_holders <= 100:
        holder_msg = f"{num_holders} holders (O'Neil's sweet spot)"
    elif 30 <= num_holders < 50:
        holder_msg = f"{num_holders} holders (good, but could grow)"
    elif num_holders > 100 and num_holders <= 150:
        holder_msg = f"{num_holders} holders (getting crowded)"
    elif num_holders > 150:
        holder_msg = f"{num_holders} holders (overcrowded)"
    else:
        holder_msg = f"{num_holders} holders (underowned)"

    # Ownership assessment
    if ownership_pct is None:
        ownership_msg = "ownership % unavailable"
    elif 30 <= ownership_pct <= 60:
        ownership_msg = f"{ownership_pct:.1f}% ownership (ideal range)"
    elif 20 <= ownership_pct < 30 or 60 < ownership_pct <= 80:
        ownership_msg = f"{ownership_pct:.1f}% ownership (acceptable)"
    elif ownership_pct < 20:
        ownership_msg = f"{ownership_pct:.1f}% ownership (underowned, potential upside)"
    else:
        ownership_msg = f"{ownership_pct:.1f}% ownership (overcrowded, vulnerable)"

    # Superinvestor note
    if superinvestor_present:
        superinvestor_names = ", ".join(superinvestors[:2])  # Show first 2
        if len(superinvestors) > 2:
            superinvestor_names += f" +{len(superinvestors)-2} more"
        superinvestor_msg = f" ⭐ Superinvestors: {superinvestor_names}"
    else:
        superinvestor_msg = ""

    return f"{holder_msg}, {ownership_msg}.{superinvestor_msg}"


# Example usage
if __name__ == "__main__":
    # Test with sample data
    sample_holders = [
        {"holder": "Vanguard Group Inc", "shares": 1000000000, "dateReported": "2024-09-30", "change": 5000000},
        {"holder": "BERKSHIRE HATHAWAY INC", "shares": 500000000, "dateReported": "2024-09-30", "change": 0},
    ] + [
        {"holder": f"Institution {i}", "shares": 10000000, "dateReported": "2024-09-30", "change": 0}
        for i in range(3, 75)  # Total 74 holders
    ]

    sample_profile = {
        "symbol": "TEST",
        "sharesOutstanding": 5000000000,
        "price": 150.0
    }

    result = calculate_institutional_sponsorship(sample_holders, sample_profile)

    print("I Component Test Results:")
    print(f"  Score: {result['score']}/100")
    print(f"  Holders: {result['num_holders']}")
    print(f"  Ownership: {result['ownership_pct']:.1f}%")
    print(f"  Superinvestor: {result['superinvestor_present']}")
    print(f"  Superinvestors: {result['superinvestors']}")
    print(f"  Interpretation: {result['interpretation']}")
