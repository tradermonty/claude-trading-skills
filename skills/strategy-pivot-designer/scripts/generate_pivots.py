#!/usr/bin/env python3
"""Generate strategy pivot proposals from stagnation diagnosis."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

# --- Constants ---

EXPORTABLE_FAMILIES = {"pivot_breakout", "gap_up_continuation"}

ARCHETYPE_CATALOG = {
    "trend_following_breakout": {
        "hypothesis_type": "breakout",
        "mechanism_tag": "behavior",
        "entry_family": "pivot_breakout",
        "default_horizon_days": 30,
        "default_stop_loss_pct": 0.08,
        "default_take_profit_rr": 3.0,
        "default_time_stop_days": 20,
        "default_conditions": ["close > high20_prev", "rel_volume >= 1.5", "close > ma50 > ma200"],
        "default_trend_filter": ["price > sma_200", "price > sma_50", "sma_50 > sma_200"],
        "compatible_pivots_from": [
            "mean_reversion_pullback",
            "volatility_contraction",
            "sector_rotation_momentum",
        ],
        "typical_failure_modes": [
            "Whipsaws in range-bound markets",
            "Late entries after extended moves",
            "Gap-downs through stop levels",
        ],
    },
    "mean_reversion_pullback": {
        "hypothesis_type": "mean_reversion",
        "mechanism_tag": "statistical",
        "entry_family": "research_only",
        "default_horizon_days": 7,
        "default_stop_loss_pct": 0.04,
        "default_take_profit_rr": 2.0,
        "default_time_stop_days": 7,
        "default_conditions": ["rsi_14 < 30", "price > sma_200", "price < sma_20"],
        "default_trend_filter": ["sma_50 > sma_200"],
        "compatible_pivots_from": [
            "trend_following_breakout",
            "volatility_contraction",
            "earnings_drift_pead",
        ],
        "typical_failure_modes": [
            "Catching falling knives in trend changes",
            "Insufficient recovery within time stop",
        ],
    },
    "earnings_drift_pead": {
        "hypothesis_type": "earnings_drift",
        "mechanism_tag": "information",
        "entry_family": "gap_up_continuation",
        "default_horizon_days": 20,
        "default_stop_loss_pct": 0.06,
        "default_take_profit_rr": 2.5,
        "default_time_stop_days": 20,
        "default_conditions": [
            "gap_up_detected",
            "close_above_gap_day_high",
            "volume > 2.0 * avg_volume_50",
        ],
        "default_trend_filter": ["price > sma_200", "price > sma_50", "sma_50 > sma_200"],
        "compatible_pivots_from": [
            "event_driven_fade",
            "trend_following_breakout",
            "mean_reversion_pullback",
        ],
        "typical_failure_modes": ["One-day gap fills", "Market-wide selloffs overwhelming drift"],
    },
    "volatility_contraction": {
        "hypothesis_type": "breakout",
        "mechanism_tag": "structural",
        "entry_family": "pivot_breakout",
        "default_horizon_days": 25,
        "default_stop_loss_pct": 0.05,
        "default_take_profit_rr": 3.0,
        "default_time_stop_days": 20,
        "default_conditions": [
            "volatility_contraction_detected",
            "close > pivot_point",
            "rel_volume >= 1.3",
        ],
        "default_trend_filter": ["price > sma_200", "sma_50 > sma_200"],
        "compatible_pivots_from": [
            "trend_following_breakout",
            "mean_reversion_pullback",
            "statistical_pairs",
        ],
        "typical_failure_modes": [
            "False breakouts from contraction zones",
            "Extended contraction draining capital",
        ],
    },
    "regime_conditional_carry": {
        "hypothesis_type": "regime",
        "mechanism_tag": "macro",
        "entry_family": "research_only",
        "default_horizon_days": 60,
        "default_stop_loss_pct": 0.07,
        "default_take_profit_rr": 2.5,
        "default_time_stop_days": 60,
        "default_conditions": ["regime_favorable", "carry_positive", "trend_aligned"],
        "default_trend_filter": ["macro_regime == risk_on"],
        "compatible_pivots_from": [
            "sector_rotation_momentum",
            "event_driven_fade",
            "statistical_pairs",
        ],
        "typical_failure_modes": ["Regime detection lag", "Whipsaws during transitions"],
    },
    "sector_rotation_momentum": {
        "hypothesis_type": "momentum",
        "mechanism_tag": "behavior",
        "entry_family": "research_only",
        "default_horizon_days": 40,
        "default_stop_loss_pct": 0.06,
        "default_take_profit_rr": 2.5,
        "default_time_stop_days": 30,
        "default_conditions": [
            "sector_rs_rank <= 3",
            "sector_momentum_positive",
            "relative_strength > 1.0",
        ],
        "default_trend_filter": ["market_breadth > 50%"],
        "compatible_pivots_from": [
            "trend_following_breakout",
            "regime_conditional_carry",
            "earnings_drift_pead",
        ],
        "typical_failure_modes": [
            "Momentum reversals during rotation shifts",
            "Crowded sector trades",
        ],
    },
    "event_driven_fade": {
        "hypothesis_type": "mean_reversion",
        "mechanism_tag": "information",
        "entry_family": "research_only",
        "default_horizon_days": 5,
        "default_stop_loss_pct": 0.03,
        "default_take_profit_rr": 2.0,
        "default_time_stop_days": 5,
        "default_conditions": [
            "event_overreaction_detected",
            "price_deviation > 2_sigma",
            "volume_spike",
        ],
        "default_trend_filter": ["no_regime_change_confirmed"],
        "compatible_pivots_from": [
            "earnings_drift_pead",
            "mean_reversion_pullback",
            "volatility_contraction",
        ],
        "typical_failure_modes": [
            "Genuine regime changes misread as overreactions",
            "Cascading events",
        ],
    },
    "statistical_pairs": {
        "hypothesis_type": "mean_reversion",
        "mechanism_tag": "statistical",
        "entry_family": "research_only",
        "default_horizon_days": 20,
        "default_stop_loss_pct": 0.06,
        "default_take_profit_rr": 2.0,
        "default_time_stop_days": 20,
        "default_conditions": ["cointegration_pvalue < 0.05", "zscore > 2.0", "half_life < 30"],
        "default_trend_filter": ["sector_correlation > 0.7"],
        "compatible_pivots_from": [
            "mean_reversion_pullback",
            "volatility_contraction",
            "regime_conditional_carry",
        ],
        "typical_failure_modes": ["Cointegration breakdown", "Extended spread divergence"],
    },
}

# Inversion rules: (trigger) -> list of module changes
INVERSION_MAP = {
    "cost_defeat": [
        {
            "module": "horizon",
            "change": "shorten",
            "new_time_stop_days": 7,
            "reason": "Reduce friction exposure",
        },
        {"module": "universe", "change": "high_liquidity", "reason": "Reduce slippage impact"},
    ],
    "tail_risk": [
        {
            "module": "risk",
            "change": "tighten",
            "new_stop_loss_pct": 0.04,
            "new_risk_per_trade": 0.005,
            "reason": "Reduce tail exposure",
        },
        {"module": "structure", "change": "market_neutral", "reason": "Hedge directional risk"},
    ],
    "improvement_plateau": [
        {
            "module": "signal",
            "change": "volume_based",
            "reason": "Change signal source from price to volume",
        },
        {"module": "entry", "change": "timing_shift", "reason": "Change entry timing mechanism"},
    ],
    "overfitting_proxy": [
        {
            "module": "complexity",
            "change": "simplify",
            "reason": "Reduce parameters and model complexity",
        },
        {
            "module": "validation",
            "change": "extend_period",
            "reason": "Extend test period and add regime subsamples",
        },
    ],
}

# Quality potential: (trigger, archetype) -> score 0-1
QUALITY_TABLE = {
    # cost_defeat: shorter horizon / higher liquidity archetypes score well
    ("cost_defeat", "mean_reversion_pullback"): 0.8,
    ("cost_defeat", "event_driven_fade"): 0.75,
    ("cost_defeat", "statistical_pairs"): 0.7,
    ("cost_defeat", "volatility_contraction"): 0.5,
    ("cost_defeat", "trend_following_breakout"): 0.4,
    ("cost_defeat", "earnings_drift_pead"): 0.6,
    ("cost_defeat", "sector_rotation_momentum"): 0.3,
    ("cost_defeat", "regime_conditional_carry"): 0.2,
    # tail_risk: low-risk / hedged archetypes score well
    ("tail_risk", "statistical_pairs"): 0.85,
    ("tail_risk", "event_driven_fade"): 0.7,
    ("tail_risk", "mean_reversion_pullback"): 0.75,
    ("tail_risk", "volatility_contraction"): 0.6,
    ("tail_risk", "trend_following_breakout"): 0.3,
    ("tail_risk", "earnings_drift_pead"): 0.4,
    ("tail_risk", "sector_rotation_momentum"): 0.35,
    ("tail_risk", "regime_conditional_carry"): 0.5,
    # improvement_plateau: structurally different signal sources score well
    ("improvement_plateau", "mean_reversion_pullback"): 0.7,
    ("improvement_plateau", "earnings_drift_pead"): 0.75,
    ("improvement_plateau", "event_driven_fade"): 0.65,
    ("improvement_plateau", "sector_rotation_momentum"): 0.7,
    ("improvement_plateau", "regime_conditional_carry"): 0.6,
    ("improvement_plateau", "statistical_pairs"): 0.65,
    ("improvement_plateau", "volatility_contraction"): 0.5,
    ("improvement_plateau", "trend_following_breakout"): 0.4,
    # overfitting_proxy: simpler / fewer-parameter archetypes score well
    ("overfitting_proxy", "mean_reversion_pullback"): 0.75,
    ("overfitting_proxy", "event_driven_fade"): 0.7,
    ("overfitting_proxy", "trend_following_breakout"): 0.65,
    ("overfitting_proxy", "volatility_contraction"): 0.6,
    ("overfitting_proxy", "earnings_drift_pead"): 0.55,
    ("overfitting_proxy", "statistical_pairs"): 0.4,
    ("overfitting_proxy", "sector_rotation_momentum"): 0.5,
    ("overfitting_proxy", "regime_conditional_carry"): 0.35,
}

# Objective reframe mappings
REFRAME_MAP = {
    "tail_risk": {
        "new_criteria": ["max_drawdown_pct < 25", "expected_value_after_costs > 0"],
        "exit_adjustments": {"stop_loss_pct": 0.04, "take_profit_rr": 1.5},
        "reason": "Reframe from return maximization to drawdown minimization",
    },
    "cost_defeat": {
        "new_criteria": ["win_rate > 55", "expected_value_after_costs > 0"],
        "exit_adjustments": {"stop_loss_pct": 0.03, "take_profit_rr": 1.5, "time_stop_days": 5},
        "reason": "Reframe to win rate maximization with smaller targets",
    },
    "improvement_plateau": {
        "new_criteria": [
            "risk_adjusted_return_per_exposure > 0.5",
            "expected_value_after_costs > 0",
        ],
        "exit_adjustments": {},
        "reason": "Reframe to risk-adjusted return per unit exposure",
    },
    "overfitting_proxy": {
        "new_criteria": ["expected_value_after_costs > 0", "stable across regimes and subperiods"],
        "exit_adjustments": {},
        "reason": "Simplify to fewer optimization targets",
    },
}

DEFAULT_QUALITY = 0.3


# --- ID Sanitization ---


def sanitize_identifier(value: str) -> str:
    """Convert free text into a safe identifier (same as design_strategy_drafts.py:84)."""
    lowered = "".join(ch.lower() if ch.isalnum() else "_" for ch in value)
    compact = "_".join(part for part in lowered.split("_") if part)
    return compact or "pivot"


# --- Archetype Identification ---


def identify_current_archetype(draft: dict[str, Any]) -> str | None:
    """Identify current strategy's archetype from its fields."""
    h_type = draft.get("hypothesis_type", "")
    m_tag = draft.get("mechanism_tag", "")
    e_family = draft.get("entry_family", "")

    # Exact match attempts
    for arch_id, arch in ARCHETYPE_CATALOG.items():
        if (
            arch["hypothesis_type"] == h_type
            and arch["mechanism_tag"] == m_tag
            and arch["entry_family"] == e_family
        ):
            return arch_id

    # Partial match: hypothesis_type + mechanism_tag
    for arch_id, arch in ARCHETYPE_CATALOG.items():
        if arch["hypothesis_type"] == h_type and arch["mechanism_tag"] == m_tag:
            return arch_id

    # Partial match: hypothesis_type only
    for arch_id, arch in ARCHETYPE_CATALOG.items():
        if arch["hypothesis_type"] == h_type:
            return arch_id

    return None


# --- Module Set for Novelty ---


def compute_module_set(draft: dict[str, Any]) -> set[tuple[str, str]]:
    """Build normalized module set for Jaccard distance."""
    modules: set[tuple[str, str]] = set()

    modules.add(("hypothesis_type", str(draft.get("hypothesis_type", ""))))
    modules.add(("mechanism_tag", str(draft.get("mechanism_tag", ""))))
    modules.add(("regime", str(draft.get("regime", ""))))
    modules.add(("entry_family", str(draft.get("entry_family", ""))))

    # Horizon classification
    exit_data = draft.get("exit", {})
    time_stop = exit_data.get("time_stop_days", 20)
    if time_stop <= 7:
        horizon = "short"
    elif time_stop <= 30:
        horizon = "medium"
    else:
        horizon = "long"
    modules.add(("horizon", horizon))

    # Risk style classification
    stop_loss = exit_data.get("stop_loss_pct", 0.07)
    if stop_loss <= 0.04:
        risk_style = "tight"
    elif stop_loss <= 0.08:
        risk_style = "normal"
    else:
        risk_style = "wide"
    modules.add(("risk_style", risk_style))

    return modules


# --- Scoring ---


def score_novelty(source_set: set, target_set: set) -> float:
    """Jaccard distance between module sets (0=identical, 1=no overlap)."""
    if not source_set and not target_set:
        return 0.0
    intersection = source_set & target_set
    union = source_set | target_set
    if not union:
        return 0.0
    return 1.0 - len(intersection) / len(union)


def score_quality_potential(trigger: str, archetype: str) -> float:
    """Look up quality potential from QUALITY_TABLE."""
    return QUALITY_TABLE.get((trigger, archetype), DEFAULT_QUALITY)


def compute_combined_score(quality: float, novelty: float) -> float:
    """Combined score: 0.6 * quality + 0.4 * novelty."""
    return round(0.6 * quality + 0.4 * novelty, 4)


# --- Pivot Generation ---


def generate_inversions(
    draft: dict[str, Any],
    triggers_fired: list[dict],
    source_archetype: str | None,
) -> list[dict[str, Any]]:
    """Generate assumption inversion proposals."""
    proposals: list[dict[str, Any]] = []
    source_id = draft.get("id", "unknown")

    for trigger_info in triggers_fired:
        trigger = trigger_info["trigger"]
        inversions = INVERSION_MAP.get(trigger, [])

        for inv in inversions:
            # For each archetype in the catalog (excluding current)
            for arch_id, arch in ARCHETYPE_CATALOG.items():
                if arch_id == source_archetype:
                    continue

                proposal_id = sanitize_identifier(f"pivot_{source_id}_inv_{trigger}_{arch_id}")

                # Build draft based on archetype defaults with inversion applied
                new_draft = _build_base_draft(draft, arch_id, arch, proposal_id)

                # Apply inversion-specific adjustments
                if inv.get("new_time_stop_days"):
                    new_draft["exit"]["time_stop_days"] = inv["new_time_stop_days"]
                if inv.get("new_stop_loss_pct"):
                    new_draft["exit"]["stop_loss_pct"] = inv["new_stop_loss_pct"]
                if inv.get("new_risk_per_trade"):
                    new_draft["risk"]["risk_per_trade"] = inv["new_risk_per_trade"]

                new_draft["pivot_metadata"] = {
                    "pivot_technique": "assumption_inversion",
                    "source_strategy_id": source_id,
                    "target_archetype": arch_id,
                    "what_changed": {
                        "signal": f"Inversion: {inv['module']} -> {inv['change']}",
                        "horizon": f"{draft.get('exit', {}).get('time_stop_days', '?')}d -> {new_draft['exit']['time_stop_days']}d",
                        "risk": f"stop {draft.get('exit', {}).get('stop_loss_pct', '?')} -> {new_draft['exit']['stop_loss_pct']}",
                    },
                    "why": inv["reason"],
                    "targeted_triggers": [trigger],
                    "expected_failure_modes": arch.get("typical_failure_modes", [])[:2],
                }

                proposals.append(new_draft)

    return proposals


def generate_archetype_switches(
    draft: dict[str, Any],
    source_archetype: str | None,
    triggers_fired: list[dict],
) -> list[dict[str, Any]]:
    """Generate archetype switch proposals."""
    if source_archetype is None or source_archetype not in ARCHETYPE_CATALOG:
        return []

    source_arch = ARCHETYPE_CATALOG[source_archetype]
    compatible = source_arch.get("compatible_pivots_from", [])
    source_id = draft.get("id", "unknown")
    trigger_ids = [t["trigger"] for t in triggers_fired]

    proposals: list[dict[str, Any]] = []
    for target_id in compatible:
        if target_id not in ARCHETYPE_CATALOG:
            continue

        target_arch = ARCHETYPE_CATALOG[target_id]
        proposal_id = sanitize_identifier(f"pivot_{source_id}_switch_{target_id}")

        new_draft = _build_base_draft(draft, target_id, target_arch, proposal_id)

        new_draft["pivot_metadata"] = {
            "pivot_technique": "archetype_switch",
            "source_strategy_id": source_id,
            "target_archetype": target_id,
            "what_changed": {
                "signal": f"Architecture switch: {source_archetype} -> {target_id}",
                "horizon": f"{draft.get('exit', {}).get('time_stop_days', '?')}d -> {new_draft['exit']['time_stop_days']}d",
                "risk": f"stop {draft.get('exit', {}).get('stop_loss_pct', '?')} -> {new_draft['exit']['stop_loss_pct']}",
            },
            "why": f"Structural pivot from {source_archetype} to {target_id} to address {', '.join(trigger_ids)}",
            "targeted_triggers": trigger_ids,
            "expected_failure_modes": target_arch.get("typical_failure_modes", [])[:2],
        }

        proposals.append(new_draft)

    return proposals


def generate_objective_reframes(
    draft: dict[str, Any],
    triggers_fired: list[dict],
    source_archetype: str | None,
) -> list[dict[str, Any]]:
    """Generate objective reframe proposals."""
    proposals: list[dict[str, Any]] = []
    source_id = draft.get("id", "unknown")

    for trigger_info in triggers_fired:
        trigger = trigger_info["trigger"]
        reframe = REFRAME_MAP.get(trigger)
        if not reframe:
            continue

        # Apply reframe to each compatible archetype
        current_arch = source_archetype or "unknown"
        compatible_archetypes: list[str] = []
        if current_arch in ARCHETYPE_CATALOG:
            compatible_archetypes = ARCHETYPE_CATALOG[current_arch].get(
                "compatible_pivots_from", []
            )

        # Also reframe the current archetype
        if current_arch in ARCHETYPE_CATALOG:
            target_archetypes = [current_arch] + compatible_archetypes
        else:
            target_archetypes = list(ARCHETYPE_CATALOG.keys())[:3]

        for arch_id in target_archetypes:
            if arch_id not in ARCHETYPE_CATALOG:
                continue
            arch = ARCHETYPE_CATALOG[arch_id]

            proposal_id = sanitize_identifier(f"pivot_{source_id}_reframe_{trigger}_{arch_id}")
            new_draft = _build_base_draft(draft, arch_id, arch, proposal_id)

            # Apply reframe adjustments
            if reframe.get("exit_adjustments"):
                for k, v in reframe["exit_adjustments"].items():
                    new_draft["exit"][k] = v

            if reframe.get("new_criteria"):
                new_draft["validation_plan"]["success_criteria"] = reframe["new_criteria"]

            new_draft["pivot_metadata"] = {
                "pivot_technique": "objective_reframe",
                "source_strategy_id": source_id,
                "target_archetype": arch_id,
                "what_changed": {
                    "signal": f"Objective reframe for {trigger}",
                    "horizon": f"{draft.get('exit', {}).get('time_stop_days', '?')}d -> {new_draft['exit']['time_stop_days']}d",
                    "risk": f"Criteria: {', '.join(reframe.get('new_criteria', [])[:2])}",
                },
                "why": reframe["reason"],
                "targeted_triggers": [trigger],
                "expected_failure_modes": arch.get("typical_failure_modes", [])[:2],
            }

            proposals.append(new_draft)

    return proposals


def _build_base_draft(
    source_draft: dict[str, Any],
    arch_id: str,
    arch: dict[str, Any],
    proposal_id: str,
) -> dict[str, Any]:
    """Build base pivot draft from archetype defaults."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    entry_family = arch["entry_family"]
    export_ready = entry_family in EXPORTABLE_FAMILIES

    return {
        "id": proposal_id,
        "as_of": today,
        "concept_id": source_draft.get("concept_id", ""),
        "variant": "research_probe",
        "name": f"{arch_id.replace('_', ' ').title()} (pivoted from {source_draft.get('id', 'unknown')})",
        "hypothesis_type": arch["hypothesis_type"],
        "mechanism_tag": arch["mechanism_tag"],
        "regime": source_draft.get("regime", "Neutral"),
        "export_ready_v1": export_ready,
        "entry_family": entry_family,
        "entry": {
            "conditions": arch.get("default_conditions", []),
            "trend_filter": arch.get("default_trend_filter", []),
            "note": "Probe setup with small size for hypothesis validation.",
        },
        "exit": {
            "stop_loss_pct": arch.get("default_stop_loss_pct", 0.07),
            "take_profit_rr": arch.get("default_take_profit_rr", 3.0),
            "time_stop_days": arch.get("default_time_stop_days", 20),
        },
        "risk": {
            "position_sizing": "fixed_risk",
            "risk_per_trade": 0.005,
            "max_positions": 5,
            "max_sector_exposure": 0.3,
        },
        "validation_plan": {
            "period": "2016-01-01 to latest",
            "entry_timing": "next_open",
            "hold_days": [3, 7, 14]
            if arch.get("default_time_stop_days", 20) <= 14
            else [5, 20, 60],
            "success_criteria": [
                "expected_value_after_costs > 0",
                "max_drawdown_pct < 25",
            ],
        },
        "thesis": source_draft.get("thesis", ""),
        "invalidation_signals": source_draft.get("invalidation_signals", []),
    }


# --- Ranking & Selection ---


def rank_and_select(
    proposals: list[dict[str, Any]],
    source_draft: dict[str, Any],
    triggers_fired: list[dict],
    max_pivots: int = 3,
) -> list[dict[str, Any]]:
    """Rank proposals and select top candidates with diversity constraint."""
    source_modules = compute_module_set(source_draft)

    scored: list[tuple[float, float, str, dict[str, Any]]] = []
    for p in proposals:
        target_modules = compute_module_set(p)
        novelty = score_novelty(source_modules, target_modules)

        # Average quality across all targeted triggers
        target_arch = p.get("pivot_metadata", {}).get("target_archetype", "")
        targeted = p.get("pivot_metadata", {}).get("targeted_triggers", [])
        if targeted:
            quality = sum(score_quality_potential(t, target_arch) for t in targeted) / len(targeted)
        else:
            quality = DEFAULT_QUALITY

        combined = compute_combined_score(quality, novelty)

        p["pivot_metadata"]["scores"] = {
            "quality_potential": round(quality, 4),
            "novelty": round(novelty, 4),
            "combined": combined,
        }

        scored.append((combined, novelty, p["id"], p))

    # Sort: combined DESC, novelty DESC, id ASC (deterministic tiebreak)
    scored.sort(key=lambda x: (-x[0], -x[1], x[2]))

    # Diversity constraint: max 1 per target_archetype
    seen_archetypes: set[str] = set()
    selected: list[dict[str, Any]] = []

    for _, _, _, proposal in scored:
        target = proposal.get("pivot_metadata", {}).get("target_archetype", "")
        if target in seen_archetypes:
            continue
        seen_archetypes.add(target)
        selected.append(proposal)
        if len(selected) >= max_pivots:
            break

    return selected


# --- Export Ticket ---


def build_export_ticket_if_eligible(draft: dict[str, Any]) -> dict[str, Any] | None:
    """Build export ticket if entry_family is exportable. Returns None otherwise."""
    entry_family = draft.get("entry_family", "")
    if entry_family not in EXPORTABLE_FAMILIES:
        return None

    ticket_id = sanitize_identifier(draft["id"].replace("pivot_", "edge_"))
    hypothesis_type = str(draft.get("hypothesis_type", "unknown"))

    if entry_family == "pivot_breakout" and hypothesis_type == "unknown":
        hypothesis_type = "breakout"
    if entry_family == "gap_up_continuation" and hypothesis_type == "unknown":
        hypothesis_type = "earnings_drift"

    ticket = {
        "id": ticket_id,
        "name": draft.get("name", ""),
        "description": f"Pivot-derived ticket from {draft.get('pivot_metadata', {}).get('source_strategy_id', 'unknown')}.",
        "hypothesis_type": hypothesis_type,
        "entry_family": entry_family,
        "mechanism_tag": draft.get("mechanism_tag", "uncertain"),
        "regime": draft.get("regime", "Neutral"),
        "holding_horizon": f"{draft.get('exit', {}).get('time_stop_days', 20)}D",
        "entry": {
            "conditions": draft.get("entry", {}).get("conditions", []),
            "trend_filter": draft.get("entry", {}).get("trend_filter", []),
        },
        "risk": draft.get("risk", {}),
        "exit": {
            "stop_loss_pct": draft.get("exit", {}).get("stop_loss_pct", 0.07),
            "take_profit_rr": draft.get("exit", {}).get("take_profit_rr", 3.0),
        },
        "cost_model": {
            "commission_per_share": 0.0,
            "slippage_bps": 5,
        },
    }

    # Minimal validation
    errors = _validate_ticket_minimal(ticket)
    if errors:
        return None

    return ticket


def _validate_ticket_minimal(ticket: dict[str, Any]) -> list[str]:
    """Minimal ticket validation (mirrors candidate_contract.validate_ticket_payload).

    Kept deliberately in sync with ``candidate_contract.py``.  The cross-
    validation test in ``test_generate_pivots.py::TestCrossValidation``
    detects drift between the two implementations.
    """
    errors: list[str] = []
    for key in ("id", "hypothesis_type", "entry_family"):
        value = ticket.get(key)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"ticket.{key} must be a non-empty string")

    entry_family = ticket.get("entry_family")
    if isinstance(entry_family, str) and entry_family not in EXPORTABLE_FAMILIES:
        errors.append(
            f"ticket.entry_family must be one of: {', '.join(sorted(EXPORTABLE_FAMILIES))}"
        )

    # Mirror candidate_contract validation constraints
    validation = ticket.get("validation")
    if validation is not None:
        if not isinstance(validation, dict):
            errors.append("ticket.validation must be a mapping when provided")
        else:
            method = validation.get("method", "full_sample")
            if method != "full_sample":
                errors.append("ticket.validation.method must be 'full_sample' for Phase I")
            if validation.get("oos_ratio") is not None:
                errors.append("ticket.validation.oos_ratio must be omitted or null for Phase I")

    return errors


# --- Output ---


def write_outputs(
    selected: list[dict[str, Any]],
    diagnosis: dict[str, Any],
    source_draft: dict[str, Any],
    output_dir: Path,
) -> dict[str, Any]:
    """Write pivot drafts, tickets, report, and manifest."""
    timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    strategy_id = diagnosis.get("strategy_id", "unknown")

    # Create directory structure
    research_dir = output_dir / "pivot_drafts" / "research_only"
    exportable_dir = output_dir / "pivot_drafts" / "exportable"
    research_dir.mkdir(parents=True, exist_ok=True)
    exportable_dir.mkdir(parents=True, exist_ok=True)

    manifest_drafts: list[dict[str, Any]] = []
    errors: list[str] = []

    for draft in selected:
        entry_family = draft.get("entry_family", "")
        is_exportable = entry_family in EXPORTABLE_FAMILIES

        # Remove pivot_metadata from the YAML file (store separately)
        pivot_meta = draft.pop("pivot_metadata", {})
        draft_with_meta = {**draft, "pivot_metadata": pivot_meta}

        # Choose directory
        if is_exportable:
            target_dir = exportable_dir
            category = "exportable"
        else:
            target_dir = research_dir
            category = "research_only"

        # Write draft YAML (include timestamp to avoid overwrite on re-run)
        draft_filename = f"{draft['id']}_{timestamp_str}.yaml"
        draft_path = target_dir / draft_filename
        draft_path.write_text(yaml.safe_dump(draft_with_meta, sort_keys=False, allow_unicode=True))

        draft_entry: dict[str, Any] = {
            "id": draft["id"],
            "path": str(draft_path.relative_to(output_dir)),
            "category": category,
            "ticket_path": None,
            "scores": pivot_meta.get("scores", {}),
        }

        # Build ticket if exportable
        if is_exportable:
            ticket = build_export_ticket_if_eligible(draft_with_meta)
            if ticket:
                ticket_filename = f"ticket_{draft['id'].replace('pivot_', '')}_{timestamp_str}.yaml"
                ticket_path = exportable_dir / ticket_filename
                ticket_path.write_text(yaml.safe_dump(ticket, sort_keys=False, allow_unicode=True))
                draft_entry["ticket_path"] = str(ticket_path.relative_to(output_dir))
            else:
                errors.append(f"Ticket validation failed for {draft['id']}")

        # Restore pivot_metadata
        draft["pivot_metadata"] = pivot_meta
        manifest_drafts.append(draft_entry)

    # Write manifest
    manifest = {
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "strategy_id": strategy_id,
        "diagnosis_file": str(diagnosis.get("_source_path", "")),
        "strategy_file": str(source_draft.get("_source_path", "")),
        "triggers_fired": [t["trigger"] for t in diagnosis.get("triggers_fired", [])],
        "total_pivots_generated": len(selected),
        "exportable_count": sum(1 for d in manifest_drafts if d["category"] == "exportable"),
        "research_only_count": sum(1 for d in manifest_drafts if d["category"] == "research_only"),
        "drafts": manifest_drafts,
        "errors": errors,
    }

    manifest_path = output_dir / f"pivot_manifest_{strategy_id}_{timestamp_str}.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, default=str))

    # Write report
    report = _build_report(selected, diagnosis, source_draft, manifest)
    report_path = output_dir / f"pivot_report_{strategy_id}_{timestamp_str}.md"
    report_path.write_text(report)

    return manifest


def _build_report(
    selected: list[dict[str, Any]],
    diagnosis: dict[str, Any],
    source_draft: dict[str, Any],
    manifest: dict[str, Any],
) -> str:
    """Build markdown report from pivot results."""
    lines = [
        f"# Pivot Report: {diagnosis.get('strategy_id', 'unknown')}",
        "",
        f"**Generated**: {manifest['generated_at_utc']}",
        f"**Source Strategy**: {source_draft.get('id', 'unknown')}",
        f"**Recommendation**: {diagnosis.get('recommendation', 'unknown')}",
        "",
        "---",
        "",
        "## Stagnation Diagnosis",
        "",
        f"**Triggers Fired**: {len(diagnosis.get('triggers_fired', []))}",
        f"**Score Trajectory**: {diagnosis.get('score_trajectory', [])}",
        "",
    ]

    for t in diagnosis.get("triggers_fired", []):
        lines.append(f"- **{t['trigger']}** [{t['severity']}]: {t['message']}")

    lines.extend(["", "---", "", "## Pivot Proposals", ""])

    for i, draft in enumerate(selected, 1):
        meta = draft.get("pivot_metadata", {})
        scores = meta.get("scores", {})
        lines.extend(
            [
                f"### {i}. {draft.get('id', 'unknown')}",
                "",
                f"**Technique**: {meta.get('pivot_technique', 'unknown')}",
                f"**Target Archetype**: {meta.get('target_archetype', 'unknown')}",
                f"**Entry Family**: {draft.get('entry_family', 'unknown')}",
                "",
                "**What Changed**:",
            ]
        )
        for k, v in meta.get("what_changed", {}).items():
            lines.append(f"- {k}: {v}")
        lines.extend(
            [
                "",
                f"**Why**: {meta.get('why', '')}",
                "",
                f"**Scores**: quality={scores.get('quality_potential', 0):.2f}, novelty={scores.get('novelty', 0):.2f}, combined={scores.get('combined', 0):.2f}",
                "",
            ]
        )

    # Summary table
    lines.extend(
        [
            "---",
            "",
            "## Summary",
            "",
            "| Rank | Proposal | Archetype | Combined | Category |",
            "|------|----------|-----------|----------|----------|",
        ]
    )
    for i, draft in enumerate(selected, 1):
        meta = draft.get("pivot_metadata", {})
        scores = meta.get("scores", {})
        category = (
            "exportable"
            if draft.get("entry_family", "") in EXPORTABLE_FAMILIES
            else "research_only"
        )
        lines.append(
            f"| {i} | {draft['id']} | {meta.get('target_archetype', '')} | {scores.get('combined', 0):.2f} | {category} |"
        )

    lines.append("")
    return "\n".join(lines)


# --- CLI ---


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate strategy pivot proposals from stagnation diagnosis."
    )
    parser.add_argument("--diagnosis", required=True, help="Path to pivot_diagnosis JSON")
    parser.add_argument("--strategy", required=True, help="Path to source strategy draft YAML")
    parser.add_argument("--max-pivots", type=int, default=3, help="Maximum pivot proposals")
    parser.add_argument("--output-dir", default="reports/", help="Output directory")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    diagnosis_path = Path(args.diagnosis).resolve()
    strategy_path = Path(args.strategy).resolve()

    if not diagnosis_path.exists():
        print(f"[ERROR] diagnosis file not found: {diagnosis_path}")
        return 1
    if not strategy_path.exists():
        print(f"[ERROR] strategy file not found: {strategy_path}")
        return 1

    diagnosis = json.loads(diagnosis_path.read_text())
    source_draft = yaml.safe_load(strategy_path.read_text())

    if not isinstance(source_draft, dict):
        print("[ERROR] strategy file must be a YAML mapping")
        return 1

    # Tag source paths for manifest
    diagnosis["_source_path"] = str(diagnosis_path)
    source_draft["_source_path"] = str(strategy_path)

    triggers_fired = diagnosis.get("triggers_fired", [])
    if not triggers_fired:
        print("[INFO] No triggers fired -- no pivots to generate")
        return 0

    source_archetype = identify_current_archetype(source_draft)

    # Generate proposals from all techniques
    all_proposals: list[dict[str, Any]] = []
    all_proposals.extend(generate_inversions(source_draft, triggers_fired, source_archetype))
    all_proposals.extend(
        generate_archetype_switches(source_draft, source_archetype, triggers_fired)
    )
    all_proposals.extend(
        generate_objective_reframes(source_draft, triggers_fired, source_archetype)
    )

    # Rank and select
    selected = rank_and_select(
        all_proposals, source_draft, triggers_fired, max_pivots=args.max_pivots
    )

    # Write outputs
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest = write_outputs(selected, diagnosis, source_draft, output_dir)

    print(f"[OK] Generated {manifest['total_pivots_generated']} pivot proposals")
    print(
        f"  exportable={manifest['exportable_count']} research_only={manifest['research_only_count']}"
    )
    for d in manifest["drafts"]:
        print(f"  - {d['id']} ({d['category']}) combined={d['scores'].get('combined', 0):.2f}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
