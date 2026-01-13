#!/usr/bin/env python3
"""
CANSLIM Composite Scoring Engine - Phase 1 MVP

Combines individual component scores (C, A, N, M) into weighted composite score.

Phase 1 MVP Weights:
- C (Current Earnings): 27%
- A (Annual Growth): 36%
- N (Newness): 27%
- M (Market Direction): 10%
Total: 100%

Interpretation Bands:
- 90-100: Exceptional+ (rare multi-bagger setup)
- 80-89: Exceptional (outstanding fundamentals)
- 70-79: Strong (solid across all components)
- 60-69: Above Average (meets thresholds)
- 50-59: Average (marginal)
- 40-49: Below Average (one or more weak)
- <40: Weak (fails CANSLIM criteria)
"""

from typing import Dict


# Phase 1 MVP component weights (renormalized from original CANSLIM)
WEIGHTS_PHASE1 = {
    "C": 0.27,  # Current Earnings (original 15%, renormalized to 27%)
    "A": 0.36,  # Annual Growth (original 20%, renormalized to 36%)
    "N": 0.27,  # Newness (original 15%, renormalized to 27%)
    "M": 0.10   # Market Direction (original 5%, renormalized to 10%)
}

# Phase 2 component weights (6 components, renormalized excluding L)
WEIGHTS_PHASE2 = {
    "C": 0.19,  # Current Earnings (15% / 0.80 = 0.1875 ≈ 0.19)
    "A": 0.25,  # Annual Growth (20% / 0.80 = 0.25)
    "N": 0.19,  # Newness (15% / 0.80 = 0.1875 ≈ 0.19)
    "S": 0.19,  # Supply/Demand (15% / 0.80 = 0.1875 ≈ 0.19)
    "I": 0.13,  # Institutional (10% / 0.80 = 0.125 ≈ 0.13)
    "M": 0.06   # Market Direction (5% / 0.80 = 0.0625 ≈ 0.06)
}

# Phase 3 component weights (7 components, FULL CANSLIM - Original O'Neil weights)
WEIGHTS_PHASE3 = {
    "C": 0.15,  # Current Earnings - 15%
    "A": 0.20,  # Annual Growth - 20%
    "N": 0.15,  # Newness - 15%
    "S": 0.15,  # Supply/Demand - 15%
    "L": 0.20,  # Leadership/RS Rank - 20% (LARGEST component!)
    "I": 0.10,  # Institutional - 10%
    "M": 0.05   # Market Direction - 5%
}


def calculate_composite_score(c_score: float,
                              a_score: float,
                              n_score: float,
                              m_score: float) -> Dict:
    """
    Calculate weighted composite CANSLIM score for Phase 1 MVP

    Args:
        c_score: Current Earnings component score (0-100)
        a_score: Annual Growth component score (0-100)
        n_score: Newness component score (0-100)
        m_score: Market Direction component score (0-100)

    Returns:
        Dict with:
            - composite_score: Weighted average (0-100)
            - rating: "Exceptional+", "Exceptional", "Strong", etc.
            - rating_description: What the rating means
            - guidance: Recommended action
            - weakest_component: Component with lowest score
            - weakest_score: Score of weakest component

    Example:
        >>> result = calculate_composite_score(c_score=95, a_score=90, n_score=88, m_score=100)
        >>> print(f"{result['composite_score']:.1f} - {result['rating']}")
        91.2 - Exceptional+
    """
    # Calculate weighted composite
    composite = (
        c_score * WEIGHTS_PHASE1["C"] +
        a_score * WEIGHTS_PHASE1["A"] +
        n_score * WEIGHTS_PHASE1["N"] +
        m_score * WEIGHTS_PHASE1["M"]
    )

    # Identify weakest component
    components = {"C": c_score, "A": a_score, "N": n_score, "M": m_score}
    weakest_component = min(components, key=components.get)
    weakest_score = components[weakest_component]

    # Get rating and interpretation
    rating_info = interpret_composite_score(composite)

    return {
        "composite_score": round(composite, 1),
        "rating": rating_info["rating"],
        "rating_description": rating_info["description"],
        "guidance": rating_info["guidance"],
        "weakest_component": weakest_component,
        "weakest_score": weakest_score,
        "component_scores": {
            "C": c_score,
            "A": a_score,
            "N": n_score,
            "M": m_score
        }
    }


def interpret_composite_score(composite: float) -> Dict:
    """
    Interpret composite score and provide rating/guidance

    Args:
        composite: Composite score (0-100)

    Returns:
        Dict with rating, description, guidance
    """
    if composite >= 90:
        return {
            "rating": "Exceptional+",
            "description": "Rare multi-bagger setup - all components near-perfect",
            "guidance": "Immediate buy, aggressive position sizing (15-20% of portfolio)"
        }
    elif composite >= 80:
        return {
            "rating": "Exceptional",
            "description": "Outstanding fundamentals + strong momentum",
            "guidance": "Strong buy, standard sizing (10-15% of portfolio)"
        }
    elif composite >= 70:
        return {
            "rating": "Strong",
            "description": "Solid across all components, minor weaknesses",
            "guidance": "Buy, standard sizing (8-12% of portfolio)"
        }
    elif composite >= 60:
        return {
            "rating": "Above Average",
            "description": "Meets thresholds, one component weak",
            "guidance": "Buy on pullback, conservative sizing (5-8% of portfolio)"
        }
    elif composite >= 50:
        return {
            "rating": "Average",
            "description": "Marginal CANSLIM candidate",
            "guidance": "Watchlist only, consider 3-5% if high conviction"
        }
    elif composite >= 40:
        return {
            "rating": "Below Average",
            "description": "Fails one or more key thresholds",
            "guidance": "Monitor, do not buy"
        }
    else:
        return {
            "rating": "Weak",
            "description": "Does not meet CANSLIM criteria",
            "guidance": "Avoid"
        }


def check_minimum_thresholds(c_score: float,
                             a_score: float,
                             n_score: float,
                             m_score: float) -> Dict:
    """
    Check if stock meets minimum CANSLIM thresholds

    Minimum thresholds for "buy" consideration:
    - C >= 60 (18%+ quarterly EPS growth)
    - A >= 50 (25%+ annual EPS CAGR)
    - N >= 40 (within 25% of 52-week high)
    - M >= 40 (market not in downtrend)

    Args:
        c_score, a_score, n_score, m_score: Component scores

    Returns:
        Dict with:
            - passes_all: Boolean - True if all thresholds met
            - failed_components: List of components below threshold
            - recommendation: "buy", "watchlist", or "avoid"
    """
    thresholds = {"C": 60, "A": 50, "N": 40, "M": 40}
    scores = {"C": c_score, "A": a_score, "N": n_score, "M": m_score}

    failed = [comp for comp, threshold in thresholds.items()
             if scores[comp] < threshold]

    # Special case: M score = 0 (bear market) overrides everything
    if m_score == 0:
        return {
            "passes_all": False,
            "failed_components": ["M"],
            "recommendation": "avoid",
            "reason": "Bear market - M component = 0. Do NOT buy regardless of C, A, N scores."
        }

    if not failed:
        return {
            "passes_all": True,
            "failed_components": [],
            "recommendation": "buy",
            "reason": "All minimum thresholds met"
        }
    elif len(failed) == 1:
        return {
            "passes_all": False,
            "failed_components": failed,
            "recommendation": "watchlist",
            "reason": f"One component below threshold: {failed[0]}"
        }
    else:
        return {
            "passes_all": False,
            "failed_components": failed,
            "recommendation": "avoid",
            "reason": f"Multiple components below threshold: {', '.join(failed)}"
        }


def calculate_composite_score_phase2(c_score: float,
                                     a_score: float,
                                     n_score: float,
                                     s_score: float,
                                     i_score: float,
                                     m_score: float) -> Dict:
    """
    Calculate weighted composite CANSLIM score for Phase 2 (6 components)

    Args:
        c_score: Current Earnings component score (0-100)
        a_score: Annual Growth component score (0-100)
        n_score: Newness component score (0-100)
        s_score: Supply/Demand component score (0-100)
        i_score: Institutional component score (0-100)
        m_score: Market Direction component score (0-100)

    Returns:
        Dict with:
            - composite_score: Weighted average (0-100)
            - rating: "Exceptional+", "Exceptional", "Strong", etc.
            - rating_description: What the rating means
            - guidance: Recommended action
            - weakest_component: Component with lowest score
            - weakest_score: Score of weakest component

    Example:
        >>> result = calculate_composite_score_phase2(
        ...     c_score=95, a_score=90, n_score=88, s_score=85, i_score=92, m_score=100
        ... )
        >>> print(f"{result['composite_score']:.1f} - {result['rating']}")
        91.0 - Exceptional+
    """
    # Calculate weighted composite
    composite = (
        c_score * WEIGHTS_PHASE2["C"] +
        a_score * WEIGHTS_PHASE2["A"] +
        n_score * WEIGHTS_PHASE2["N"] +
        s_score * WEIGHTS_PHASE2["S"] +
        i_score * WEIGHTS_PHASE2["I"] +
        m_score * WEIGHTS_PHASE2["M"]
    )

    # Identify weakest component
    components = {
        "C": c_score, "A": a_score, "N": n_score,
        "S": s_score, "I": i_score, "M": m_score
    }
    weakest_component = min(components, key=components.get)
    weakest_score = components[weakest_component]

    # Get rating and interpretation
    rating_info = interpret_composite_score(composite)

    return {
        "composite_score": round(composite, 1),
        "rating": rating_info["rating"],
        "rating_description": rating_info["description"],
        "guidance": rating_info["guidance"],
        "weakest_component": weakest_component,
        "weakest_score": weakest_score,
        "component_scores": {
            "C": c_score,
            "A": a_score,
            "N": n_score,
            "S": s_score,
            "I": i_score,
            "M": m_score
        }
    }


def check_minimum_thresholds_phase2(c_score: float,
                                    a_score: float,
                                    n_score: float,
                                    s_score: float,
                                    i_score: float,
                                    m_score: float) -> Dict:
    """
    Check if stock meets minimum CANSLIM thresholds (Phase 2: 6 components)

    Minimum thresholds for "buy" consideration:
    - C >= 60 (18%+ quarterly EPS growth)
    - A >= 50 (25%+ annual EPS CAGR)
    - N >= 40 (within 25% of 52-week high)
    - S >= 40 (accumulation pattern, ratio ≥ 1.0)
    - I >= 40 (30+ holders or 20%+ ownership)
    - M >= 40 (market not in downtrend)

    Args:
        c_score, a_score, n_score, s_score, i_score, m_score: Component scores

    Returns:
        Dict with:
            - passes_all: Boolean - True if all thresholds met
            - failed_components: List of components below threshold
            - recommendation: "buy", "watchlist", or "avoid"
    """
    thresholds = {"C": 60, "A": 50, "N": 40, "S": 40, "I": 40, "M": 40}
    scores = {
        "C": c_score, "A": a_score, "N": n_score,
        "S": s_score, "I": i_score, "M": m_score
    }

    failed = [comp for comp, threshold in thresholds.items()
             if scores[comp] < threshold]

    # Special case: M score = 0 (bear market) overrides everything
    if m_score == 0:
        return {
            "passes_all": False,
            "failed_components": ["M"],
            "recommendation": "avoid",
            "reason": "Bear market - M component = 0. Do NOT buy regardless of other scores."
        }

    if not failed:
        return {
            "passes_all": True,
            "failed_components": [],
            "recommendation": "buy",
            "reason": "All minimum thresholds met"
        }
    elif len(failed) == 1:
        return {
            "passes_all": False,
            "failed_components": failed,
            "recommendation": "watchlist",
            "reason": f"One component below threshold: {failed[0]}"
        }
    else:
        return {
            "passes_all": False,
            "failed_components": failed,
            "recommendation": "avoid",
            "reason": f"Multiple components below threshold: {', '.join(failed)}"
        }


def calculate_composite_score_phase3(c_score: float,
                                     a_score: float,
                                     n_score: float,
                                     s_score: float,
                                     l_score: float,
                                     i_score: float,
                                     m_score: float) -> Dict:
    """
    Calculate weighted composite CANSLIM score for Phase 3 (FULL 7 components)

    This is the complete CANSLIM implementation with O'Neil's original weights.

    Args:
        c_score: Current Earnings component score (0-100)
        a_score: Annual Growth component score (0-100)
        n_score: Newness component score (0-100)
        s_score: Supply/Demand component score (0-100)
        l_score: Leadership/RS Rank component score (0-100)
        i_score: Institutional component score (0-100)
        m_score: Market Direction component score (0-100)

    Returns:
        Dict with:
            - composite_score: Weighted average (0-100)
            - rating: "Exceptional+", "Exceptional", "Strong", etc.
            - rating_description: What the rating means
            - guidance: Recommended action
            - weakest_component: Component with lowest score
            - weakest_score: Score of weakest component

    Example:
        >>> result = calculate_composite_score_phase3(
        ...     c_score=95, a_score=90, n_score=88, s_score=85,
        ...     l_score=92, i_score=80, m_score=100
        ... )
        >>> print(f"{result['composite_score']:.1f} - {result['rating']}")
        89.7 - Exceptional
    """
    # Calculate weighted composite using FULL CANSLIM weights
    composite = (
        c_score * WEIGHTS_PHASE3["C"] +
        a_score * WEIGHTS_PHASE3["A"] +
        n_score * WEIGHTS_PHASE3["N"] +
        s_score * WEIGHTS_PHASE3["S"] +
        l_score * WEIGHTS_PHASE3["L"] +
        i_score * WEIGHTS_PHASE3["I"] +
        m_score * WEIGHTS_PHASE3["M"]
    )

    # Identify weakest component
    components = {
        "C": c_score, "A": a_score, "N": n_score,
        "S": s_score, "L": l_score, "I": i_score, "M": m_score
    }
    weakest_component = min(components, key=components.get)
    weakest_score = components[weakest_component]

    # Get rating and interpretation
    rating_info = interpret_composite_score(composite)

    return {
        "composite_score": round(composite, 1),
        "rating": rating_info["rating"],
        "rating_description": rating_info["description"],
        "guidance": rating_info["guidance"],
        "weakest_component": weakest_component,
        "weakest_score": weakest_score,
        "component_scores": {
            "C": c_score,
            "A": a_score,
            "N": n_score,
            "S": s_score,
            "L": l_score,
            "I": i_score,
            "M": m_score
        }
    }


def check_minimum_thresholds_phase3(c_score: float,
                                    a_score: float,
                                    n_score: float,
                                    s_score: float,
                                    l_score: float,
                                    i_score: float,
                                    m_score: float) -> Dict:
    """
    Check if stock meets minimum CANSLIM thresholds (Phase 3: FULL 7 components)

    Minimum thresholds for "buy" consideration:
    - C >= 60 (18%+ quarterly EPS growth)
    - A >= 50 (25%+ annual EPS CAGR)
    - N >= 40 (within 25% of 52-week high)
    - S >= 40 (accumulation pattern, ratio >= 1.0)
    - L >= 50 (RS Rank 60+, outperforming market)
    - I >= 40 (30+ holders or 20%+ ownership)
    - M >= 40 (market not in downtrend)

    Args:
        c_score, a_score, n_score, s_score, l_score, i_score, m_score: Component scores

    Returns:
        Dict with:
            - passes_all: Boolean - True if all thresholds met
            - failed_components: List of components below threshold
            - recommendation: "buy", "watchlist", or "avoid"
    """
    thresholds = {
        "C": 60, "A": 50, "N": 40,
        "S": 40, "L": 50, "I": 40, "M": 40
    }
    scores = {
        "C": c_score, "A": a_score, "N": n_score,
        "S": s_score, "L": l_score, "I": i_score, "M": m_score
    }

    failed = [comp for comp, threshold in thresholds.items()
             if scores[comp] < threshold]

    # Special case: M score = 0 (bear market) overrides everything
    if m_score == 0:
        return {
            "passes_all": False,
            "failed_components": ["M"],
            "recommendation": "avoid",
            "reason": "Bear market - M component = 0. Do NOT buy regardless of other scores."
        }

    # Special case: L score < 40 (major laggard) - strong warning
    if l_score < 40:
        if "L" not in failed:
            failed.append("L")
        return {
            "passes_all": False,
            "failed_components": failed,
            "recommendation": "avoid",
            "reason": f"Stock significantly underperforming market (L={l_score}). CANSLIM requires market leaders."
        }

    if not failed:
        return {
            "passes_all": True,
            "failed_components": [],
            "recommendation": "buy",
            "reason": "All 7 CANSLIM thresholds met - Full methodology validation"
        }
    elif len(failed) == 1:
        return {
            "passes_all": False,
            "failed_components": failed,
            "recommendation": "watchlist",
            "reason": f"One component below threshold: {failed[0]}"
        }
    else:
        return {
            "passes_all": False,
            "failed_components": failed,
            "recommendation": "avoid",
            "reason": f"Multiple components below threshold: {', '.join(failed)}"
        }


def compare_to_full_canslim(phase1_score: float) -> Dict:
    """
    Estimate what Phase 1 MVP score would be with full 7-component CANSLIM

    Phase 1 (4 components) represents 55% of full CANSLIM methodology.
    This function estimates the equivalent full CANSLIM score.

    Args:
        phase1_score: Phase 1 composite score (0-100)

    Returns:
        Dict with:
            - estimated_full_score: Estimated score with all 7 components (0-200 scale)
            - equivalent_rating: Rating on full CANSLIM scale
            - note: Explanation of estimation
    """
    # Phase 1 score 80+ typically indicates exceptional fundamentals
    # In full CANSLIM, this would likely score 140-160+ (top tier)
    if phase1_score >= 90:
        estimated_range = "160-200"
        equivalent_rating = "Exceptional"
    elif phase1_score >= 80:
        estimated_range = "140-159"
        equivalent_rating = "Strong"
    elif phase1_score >= 70:
        estimated_range = "120-139"
        equivalent_rating = "Above Average"
    elif phase1_score >= 60:
        estimated_range = "105-119"
        equivalent_rating = "Average"
    else:
        estimated_range = "<105"
        equivalent_rating = "Below Average"

    return {
        "phase1_score": phase1_score,
        "estimated_full_range": estimated_range,
        "equivalent_rating": equivalent_rating,
        "note": ("Phase 1 implements 4 of 7 components (55% of methodology). "
                "Full CANSLIM (Phases 2-3) will add S, L, I components.")
    }


# Example usage and testing
if __name__ == "__main__":
    print("Testing CANSLIM Scorer (Phase 1 MVP)...\n")

    # Test 1: Exceptional stock (NVDA-like)
    print("Test 1: Exceptional Stock (All Components Strong)")
    result1 = calculate_composite_score(c_score=100, a_score=95, n_score=98, m_score=100)
    print(f"  Composite Score: {result1['composite_score']}/100")
    print(f"  Rating: {result1['rating']}")
    print(f"  Description: {result1['rating_description']}")
    print(f"  Guidance: {result1['guidance']}")
    print(f"  Weakest Component: {result1['weakest_component']} ({result1['weakest_score']})\n")

    full1 = compare_to_full_canslim(result1['composite_score'])
    print(f"  Estimated Full CANSLIM Range: {full1['estimated_full_range']}\n")

    # Test 2: Strong stock (META-like)
    print("Test 2: Strong Stock (Most Components Good)")
    result2 = calculate_composite_score(c_score=85, a_score=78, n_score=88, m_score=80)
    print(f"  Composite Score: {result2['composite_score']}/100")
    print(f"  Rating: {result2['rating']}")
    print(f"  Weakest Component: {result2['weakest_component']} ({result2['weakest_score']})\n")

    # Test 3: Average stock (marginal)
    print("Test 3: Average Stock (Meets Minimums)")
    result3 = calculate_composite_score(c_score=60, a_score=55, n_score=65, m_score=60)
    print(f"  Composite Score: {result3['composite_score']}/100")
    print(f"  Rating: {result3['rating']}")
    print(f"  Guidance: {result3['guidance']}\n")

    # Test 4: Bear market scenario (M=0)
    print("Test 4: Bear Market Scenario (M=0 Override)")
    result4 = calculate_composite_score(c_score=95, a_score=90, n_score=92, m_score=0)
    print(f"  Composite Score: {result4['composite_score']}/100")
    print(f"  Rating: {result4['rating']}")

    threshold_check = check_minimum_thresholds(c_score=95, a_score=90, n_score=92, m_score=0)
    print(f"  Threshold Check: {threshold_check['recommendation']}")
    print(f"  Reason: {threshold_check['reason']}\n")

    # Test 5: Minimum threshold checking
    print("Test 5: Threshold Validation")
    threshold_pass = check_minimum_thresholds(c_score=70, a_score=60, n_score=65, m_score=70)
    print(f"  All thresholds met: {threshold_pass['passes_all']}")
    print(f"  Recommendation: {threshold_pass['recommendation']}\n")

    threshold_fail = check_minimum_thresholds(c_score=50, a_score=45, n_score=35, m_score=60)
    print(f"  All thresholds met: {threshold_fail['passes_all']}")
    print(f"  Failed components: {threshold_fail['failed_components']}")
    print(f"  Recommendation: {threshold_fail['recommendation']}")

    print("\n✓ All tests completed")
