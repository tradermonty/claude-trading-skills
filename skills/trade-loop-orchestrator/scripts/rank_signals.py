"""Rank + dedupe candidates using screener_weights.yaml.

Composite formula (see references/candidate_schema.md):
    composite = (strategy_score / 100) * weight * (1 + supporting_bonus) * confidence

Supporting bonus: +0.15 per distinct corroborating screener, capped at 3.
"""
from __future__ import annotations

from typing import Any


def _weight_for(primary: str, weights_cfg: dict[str, Any]) -> float:
    """Look up weight from screener_weights.yaml shape.

    Supports both:
        screeners:
          vcp-screener: {weight: 1.0}
    and flat:
        weights: {vcp-screener: 1.0}
    """
    screeners = weights_cfg.get("screeners") or {}
    if primary in screeners:
        entry = screeners[primary]
        if isinstance(entry, dict):
            return float(entry.get("weight", 1.0))
        return float(entry)
    flat = weights_cfg.get("weights") or {}
    return float(flat.get(primary, 1.0))


def compute_composite(cand: dict[str, Any], weights_cfg: dict[str, Any]) -> float:
    weight = _weight_for(cand["primary_screener"], weights_cfg)
    strategy_score = float(cand.get("strategy_score", 0))
    confidence = float(cand.get("confidence", 0.5))
    supporting = cand.get("supporting_screeners") or []
    supporting_bonus = 0.15 * min(len(supporting), 3)
    return (strategy_score / 100.0) * weight * (1 + supporting_bonus) * confidence


def dedupe_by_ticker(
    candidates: list[dict[str, Any]],
    weights_cfg: dict[str, Any],
) -> list[dict[str, Any]]:
    """Within a ticker, keep the highest-composite candidate and fold other
    screener names into supporting_screeners."""
    by_ticker: dict[str, list[dict[str, Any]]] = {}
    for c in candidates:
        by_ticker.setdefault(c["ticker"], []).append(c)

    merged: list[dict[str, Any]] = []
    for ticker, cands in by_ticker.items():
        scored = sorted(
            [(compute_composite(c, weights_cfg), c) for c in cands],
            key=lambda x: x[0],
            reverse=True,
        )
        top_score, top_cand = scored[0]
        others = [c["primary_screener"] for _, c in scored[1:]
                  if c["primary_screener"] != top_cand["primary_screener"]]
        supporting = list(dict.fromkeys(top_cand.get("supporting_screeners", []) + others))
        top_cand = {**top_cand, "supporting_screeners": supporting,
                    "composite_score": round(top_score, 4)}
        # Recompute composite with supporting bonus
        top_cand["composite_score"] = round(compute_composite(top_cand, weights_cfg), 4)
        merged.append(top_cand)

    merged.sort(key=lambda c: c["composite_score"], reverse=True)
    return merged


def apply_regime_gates(
    candidates: list[dict[str, Any]],
    regime: str | None,
    risk_on_score: float | None,
    weights_cfg: dict[str, Any],
) -> list[dict[str, Any]]:
    """Apply per-screener regime gates from screener_weights.yaml.

    Config shape:
        regime_gates:
          vcp-screener:
            allowed_regimes: [GOLDILOCKS, REFLATION, RECOVERY]
            min_risk_on: 40
    """
    gates = weights_cfg.get("regime_gates") or {}
    if not gates:
        return candidates
    kept = []
    for c in candidates:
        rules = gates.get(c["primary_screener"])
        if not rules:
            kept.append(c)
            continue
        allowed = rules.get("allowed_regimes")
        if allowed and regime and regime not in allowed:
            c = {**c, "rejected_reason": f"regime_gate: {regime} not in {allowed}"}
            continue
        min_risk = rules.get("min_risk_on")
        if min_risk is not None and risk_on_score is not None and risk_on_score < min_risk:
            c = {**c, "rejected_reason": f"risk_on {risk_on_score} < min {min_risk}"}
            continue
        kept.append(c)
    return kept


def rank_and_dedupe(
    candidates: list[dict[str, Any]],
    weights_cfg: dict[str, Any],
    regime: str | None = None,
    risk_on_score: float | None = None,
) -> list[dict[str, Any]]:
    gated = apply_regime_gates(candidates, regime, risk_on_score, weights_cfg)
    return dedupe_by_ticker(gated, weights_cfg)
