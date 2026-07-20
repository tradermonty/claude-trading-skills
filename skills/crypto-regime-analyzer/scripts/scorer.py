#!/usr/bin/env python3
"""
Crypto Regime Analyzer - Composite Scoring Engine

Combines 6 component scores into a weighted composite (0-100).
Score direction: 100 = Risk-on health, 0 = Critical risk-off.

Component Weights:
1. BTC Trend Structure:            25%
2. Alt Breadth Participation:      20%
3. BTC Dominance Regime:           15%
4. Perpetual Funding Regime:       15%
5. Drawdown & Volatility Position: 15%
6. Momentum Thrust / Washout:      10%
Total: 100%

When a component has data_available=False, its weight is proportionally
redistributed only when at least four components representing at least 65%
of the original model weight remain. Sparser inputs fail closed as UNKNOWN.

Regime Zone Mapping (100 = Risk-on):
  80-100: RISK_ON  - Broad risk-on conditions observed
  40-79:  NEUTRAL  - Mixed conditions; no strong regime conclusion
  0-39:   RISK_OFF - Defensive market conditions observed
"""

COMPONENT_WEIGHTS = {
    "btc_trend": 0.25,
    "alt_breadth": 0.20,
    "dominance": 0.15,
    "funding": 0.15,
    "drawdown_vol": 0.15,
    "momentum_thrust": 0.10,
}

COMPONENT_LABELS = {
    "btc_trend": "BTC Trend Structure",
    "alt_breadth": "Alt Breadth Participation",
    "dominance": "BTC Dominance Regime",
    "funding": "Perpetual Funding Regime",
    "drawdown_vol": "Drawdown & Volatility Position",
    "momentum_thrust": "Momentum Thrust / Washout",
}

MIN_AVAILABLE_COMPONENTS = 4
MIN_AVAILABLE_WEIGHT = 0.65

ZONES = [
    (80, "RISK_ON", "Broad risk-on conditions observed; review risk limits before decisions"),
    (40, "NEUTRAL", "Mixed conditions observed; no strong regime conclusion"),
    (0, "RISK_OFF", "Defensive market conditions observed; review existing risk controls"),
]


def calculate_composite_score(components: dict) -> dict:
    """
    Weighted composite over available components.

    Args:
        components: {component_id: result dict with score + data_available}.

    Returns:
        Dict with composite score, zone, guidance, and effective weights.
    """
    available = {
        cid: comp
        for cid, comp in components.items()
        if cid in COMPONENT_WEIGHTS and comp.get("data_available", False)
    }
    total_weight = sum(COMPONENT_WEIGHTS[cid] for cid in available)
    if len(available) < MIN_AVAILABLE_COMPONENTS or total_weight < MIN_AVAILABLE_WEIGHT:
        return {
            "score": None,
            "zone": "UNKNOWN",
            "guidance": (
                "Insufficient component coverage for a regime classification "
                f"({len(available)}/{len(COMPONENT_WEIGHTS)} components, "
                f"{total_weight:.0%} model weight)"
            ),
            "effective_weights": {},
            "components_available": len(available),
            "components_total": len(COMPONENT_WEIGHTS),
            "available_weight": round(total_weight, 4),
        }

    effective = {cid: COMPONENT_WEIGHTS[cid] / total_weight for cid in available}
    score = sum(available[cid]["score"] * w for cid, w in effective.items())
    score = round(max(0.0, min(100.0, score)), 1)

    zone, guidance = ZONES[-1][1], ZONES[-1][2]
    for threshold, z, g in ZONES:
        if score >= threshold:
            zone, guidance = z, g
            break

    return {
        "score": score,
        "zone": zone,
        "guidance": guidance,
        "effective_weights": {k: round(v, 4) for k, v in effective.items()},
        "components_available": len(available),
        "components_total": len(COMPONENT_WEIGHTS),
        "available_weight": round(total_weight, 4),
    }
