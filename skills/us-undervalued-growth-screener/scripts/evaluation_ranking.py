"""Ranking, final-three selection, funnel validation and snapshot evaluation for evaluate_candidates."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from coverage_semantics import derive_ranking_scope_from_audit
from evaluation_candidate import (
    _best_low_case_upside,
    _preferred_three_year_upside,
    evaluate_candidate,
)
from evaluation_common import (
    ALLOWED_SESSIONS,
    DEFAULT_CONFIG,
    SCHEMA_VERSION,
    ContractError,
    InputError,
    _deep_merge,
    _integer,
    _list,
    _mapping,
    _number,
    _text,
    parse_iso8601,
    runtime_metadata,
    validate_and_normalize_snapshot,
)


def _sort_key(result: Mapping[str, Any]) -> tuple[float, float, float, float, float, str]:
    valuation = _mapping(result.get("valuation"))
    constant_upside = _preferred_three_year_upside(valuation, "constant_multiple")
    stress_upside = _preferred_three_year_upside(valuation, "multiple_contraction")
    dilution = _number(_mapping(result.get("financial_metrics")).get("diluted_share_cagr_pct"))
    return (
        -(_number(result.get("final_score")) or 0.0),
        -(constant_upside if constant_upside is not None else -10_000.0),
        -(stress_upside if stress_upside is not None else -10_000.0),
        -(_number(result.get("data_quality_score")) or 0.0),
        dilution if dilution is not None else 10_000.0,
        _text(result.get("symbol")) or "",
    )


def _review_sort_key(result: Mapping[str, Any]) -> tuple[float, float, str]:
    return (
        -(_number(result.get("final_score")) or 0.0),
        -(
            _preferred_three_year_upside(_mapping(result.get("valuation")), "constant_multiple")
            or -10_000
        ),
        _text(result.get("symbol")) or "",
    )


def _select_final_three(
    ranked: Sequence[Mapping[str, Any]],
    *,
    ranking_status: str,
    config: Mapping[str, Any],
) -> dict[str, Any]:
    if not ranked or ranking_status != "final":
        return {"highest_conviction": None, "most_undervalued": None, "largest_upside": None}

    def summary(row: Mapping[str, Any]) -> dict[str, Any]:
        valuation = _mapping(row.get("valuation"))
        qualitative = _mapping(row.get("qualitative"))
        return {
            "symbol": row.get("symbol"),
            "company_name": row.get("company_name"),
            "final_score": row.get("final_score"),
            "constant_multiple_upside_pct": _preferred_three_year_upside(
                valuation, "constant_multiple"
            ),
            "stress_upside_pct": _preferred_three_year_upside(valuation, "multiple_contraction"),
            "low_case_upside_pct": _best_low_case_upside(valuation),
            "data_quality_score": row.get("data_quality_score"),
            "investment_thesis": qualitative.get("investment_thesis"),
            "market_may_be_missing": qualitative.get("market_may_be_missing"),
            "best_catalyst": qualitative.get("best_catalyst"),
            "maximum_risk": qualitative.get("maximum_risk"),
            "do_not_buy_reason": qualitative.get("do_not_buy_reason"),
            "bear_case": qualitative.get("bear_case"),
            "invalidation_conditions": qualitative.get("invalidation_conditions"),
            "next_earnings_kpis": qualitative.get("next_earnings_kpis"),
        }

    min_score = float(config.get("final_three_minimum_score", 75.0))
    min_dq = int(config.get("final_three_minimum_data_quality", 80))
    min_stress = float(config.get("final_three_minimum_stress_upside_pct", 0.0))
    min_adj_yield = float(config.get("final_three_minimum_sbc_adjusted_fcf_yield_pct", 5.0))
    max_ev_fcf = float(config.get("final_three_maximum_ev_to_fcf", 20.0))
    min_low_case = float(config.get("final_three_minimum_low_case_upside_pct", 20.0))

    conviction_pool = [
        row
        for row in ranked
        if (_number(row.get("final_score")) or 0.0) >= min_score
        and (_number(row.get("data_quality_score")) or 0.0) >= min_dq
        and (
            _preferred_three_year_upside(_mapping(row.get("valuation")), "multiple_contraction")
            or -10_000
        )
        >= min_stress
    ]
    undervalued_pool = [
        row
        for row in ranked
        if (
            (
                _number(_mapping(row.get("financial_metrics")).get("sbc_adjusted_fcf_yield_pct"))
                or -10_000
            )
            >= min_adj_yield
            or (_number(_mapping(row.get("financial_metrics")).get("ev_to_fcf")) or 10_000)
            <= max_ev_fcf
        )
    ]
    upside_pool = [
        row
        for row in ranked
        if (_best_low_case_upside(_mapping(row.get("valuation"))) or -10_000) >= min_low_case
    ]

    highest_conviction = max(
        conviction_pool,
        key=lambda row: (
            _number(row.get("final_score")) or 0,
            _number(row.get("data_quality_score")) or 0,
            1 if row.get("confidence") == "high" else 0,
        ),
        default=None,
    )
    most_undervalued = max(
        undervalued_pool,
        key=lambda row: (
            _number(_mapping(row.get("financial_metrics")).get("sbc_adjusted_fcf_yield_pct"))
            or -10_000,
            -(_number(_mapping(row.get("financial_metrics")).get("ev_to_fcf")) or 10_000),
        ),
        default=None,
    )
    largest_upside = max(
        upside_pool,
        key=lambda row: (
            _preferred_three_year_upside(_mapping(row.get("valuation")), "constant_multiple")
            or -10_000
        ),
        default=None,
    )
    return {
        "highest_conviction": summary(highest_conviction) if highest_conviction else None,
        "most_undervalued": summary(most_undervalued) if most_undervalued else None,
        "largest_upside": summary(largest_upside) if largest_upside else None,
    }


def _validate_funnel(funnel: Mapping[str, Any], strict: bool) -> list[str]:
    warnings: list[str] = []
    required = (
        "universe_count",
        "listing_in_scope_count",
        "candidate_pool_count",
        "discovery_evaluable_count",
        "deep_dive_selected_count",
        "deep_dive_completed_count",
    )
    values: dict[str, int | None] = {}
    for key in required:
        values[key] = _integer(funnel.get(key))
        if values[key] is None:
            warnings.append(f"screening_funnel.{key} is missing")
    if all(values[key] is not None for key in required):
        universe = int(values["universe_count"] or 0)
        in_scope = int(values["listing_in_scope_count"] or 0)
        pool = int(values["candidate_pool_count"] or 0)
        evaluable = int(values["discovery_evaluable_count"] or 0)
        selected = int(values["deep_dive_selected_count"] or 0)
        completed = int(values["deep_dive_completed_count"] or 0)
        if in_scope > universe:
            warnings.append("listing_in_scope_count exceeds universe_count")
        if pool > universe:
            warnings.append("candidate_pool_count exceeds universe_count")
        if evaluable > pool:
            warnings.append("discovery_evaluable_count exceeds candidate_pool_count")
        if selected > evaluable:
            warnings.append("deep_dive_selected_count exceeds discovery_evaluable_count")
        if completed > selected:
            warnings.append("deep_dive_completed_count exceeds deep_dive_selected_count")
    preflight = _integer(funnel.get("preflight_passed_count"))
    selected = values.get("deep_dive_selected_count")
    if preflight is not None and selected is not None and preflight > selected:
        warnings.append("preflight_passed_count exceeds deep_dive_selected_count")
    if strict and not funnel:
        warnings.append("screening_funnel is absent; tiered coverage cannot be audited")
    return warnings


def evaluate_snapshot(
    payload: Mapping[str, Any],
    *,
    strict: bool = False,
    top: int | None = None,
    artifact_root: Path | None = None,
) -> dict[str, Any]:
    try:
        normalized_payload, contract = validate_and_normalize_snapshot(
            payload, artifact_root=artifact_root
        )
    except ContractError as exc:
        raise InputError(str(exc)) from exc
    analysis_as_of = parse_iso8601(
        normalized_payload.get("analysis_as_of"), "analysis_as_of", required=True
    )
    assert analysis_as_of is not None
    price_basis = _mapping(normalized_payload.get("price_basis"))
    session = (_text(price_basis.get("session")) or "").lower()
    if session not in ALLOWED_SESSIONS:
        raise InputError("price_basis.session is missing or invalid")
    parse_iso8601(price_basis.get("as_of"), "price_basis.as_of", required=True)

    config = _deep_merge(DEFAULT_CONFIG, _mapping(normalized_payload.get("config")))
    max_candidates = top if top is not None else _integer(config.get("max_candidates")) or 10
    if max_candidates <= 0:
        raise InputError("max candidates must be positive")
    candidates = _list(normalized_payload.get("candidates"))
    candidate_pool_status = (_text(contract.get("candidate_pool_status")) or "").lower()
    no_qualifying_candidates = candidate_pool_status in {
        "no_qualifying_candidates",
        "no_qualifying_candidates_in_bounded_pool",
    }
    unresolved_pool_statuses = {"insufficient_data", "sufficient_pending_enrichment"}
    if (
        not candidates
        and not no_qualifying_candidates
        and candidate_pool_status not in unresolved_pool_statuses
    ):
        raise InputError(
            "candidates must contain selected candidate records unless the audited pool is unresolved or found no qualifying candidates"
        )

    results = [
        evaluate_candidate(
            _mapping(candidate),
            config=config,
            analysis_as_of=analysis_as_of,
            price_basis=price_basis,
            strict=strict,
        )
        for candidate in candidates
    ]
    eligible = sorted((row for row in results if row.get("status") == "eligible"), key=_sort_key)
    conditional = sorted(
        (row for row in results if row.get("status") == "conditional"), key=_review_sort_key
    )
    review = sorted(
        (row for row in results if row.get("status") == "review_required"), key=_review_sort_key
    )
    screened_out = sorted(
        (row for row in results if row.get("status") == "screened_out"),
        key=lambda row: row.get("symbol") or "",
    )
    excluded = sorted(
        (row for row in results if row.get("status") == "excluded"),
        key=lambda row: row.get("symbol") or "",
    )
    ranked = eligible[:max_candidates]
    for index, row in enumerate(ranked, start=1):
        row["rank"] = index

    funnel = _mapping(normalized_payload.get("screening_funnel"))
    selected_symbol_set = {
        str(value).upper()
        for value in _list(contract.get("selected_symbols"))
        if str(value).strip()
    }
    selected_results = [
        row for row in results if str(row.get("symbol") or "").upper() in selected_symbol_set
    ]
    actual_preflight = sum(
        1
        for row in selected_results
        if _mapping(row.get("corporate_action_check")).get("evidence_ok") is True
        and _mapping(row.get("corporate_action_check")).get("listing_status") == "active"
        and _mapping(row.get("corporate_action_check")).get("mna_status") in {"none", "terminated"}
        and _mapping(row.get("corporate_action_check")).get("symbol_active") is True
    )
    funnel_contract_errors: list[str] = []
    declared_preflight = _integer(funnel.get("preflight_passed_count"))
    if declared_preflight != actual_preflight:
        funnel_contract_errors.append(
            f"screening_funnel.preflight_passed_count={declared_preflight!r} does not equal verified selected-candidate preflight count {actual_preflight}"
        )
    declared_completed = _integer(funnel.get("deep_dive_completed_count"))
    actual_completed = len(selected_results)
    if declared_completed != actual_completed:
        funnel_contract_errors.append(
            f"screening_funnel.deep_dive_completed_count={declared_completed!r} does not equal selected candidate record count {actual_completed}"
        )
    if funnel_contract_errors:
        contract["valid"] = False
        contract.setdefault("review_reasons", []).extend(funnel_contract_errors)

    run_metadata = _mapping(normalized_payload.get("run_metadata"))
    declared_status = (_text(run_metadata.get("status")) or "partial").lower()
    unprocessed = [str(value) for value in _list(run_metadata.get("unprocessed_candidates"))]
    ranking_status = (
        "final"
        if declared_status == "complete" and not unprocessed and contract.get("valid") is True
        else "provisional"
    )
    global_warnings = _validate_funnel(funnel, strict)
    global_warnings.extend(_list(contract.get("warnings")))
    global_warnings.extend(_list(contract.get("review_reasons")))
    if ranking_status == "provisional":
        global_warnings.append(
            "run contract is incomplete; ranking and final-three selection are provisional"
        )
    if not ranked:
        if ranking_status == "final" and no_qualifying_candidates:
            if candidate_pool_status == "no_qualifying_candidates_in_bounded_pool":
                global_warnings.append(
                    "completed bounded candidate pool contained no qualifying company; this is not a market-wide no-candidates claim"
                )
            else:
                global_warnings.append(
                    "completed full-universe candidate pool contained no company that qualified under the configured GARP gates"
                )
        elif candidate_pool_status in unresolved_pool_statuses:
            global_warnings.append(
                "candidate-pool research is unresolved; no-candidates conclusion is prohibited"
            )
        else:
            global_warnings.append("no candidate cleared all strict ranking gates")

    broad_rows = _list(
        _mapping(normalized_payload.get("screening_audit")).get("actual_candidate_rows")
    )
    broad_groups: dict[str, list[dict[str, Any]]] = {
        "selected": [],
        "deferred_by_budget": [],
        "review_required": [],
        "screened_out": [],
        "excluded": [],
        "unavailable_after_enrichment": [],
    }
    for raw in broad_rows:
        row = _mapping(raw)
        decision = _mapping(row.get("decision"))
        status = (_text(decision.get("status")) or "").lower()
        entry = {
            "symbol": row.get("symbol"),
            "company_name": row.get("company_name"),
            "status": status,
            "preselection_status": decision.get("preselection_status"),
            "broad_score": row.get("broad_score"),
            "deep_dive_priority_score": row.get("deep_dive_priority_score"),
            "review_reasons": decision.get("review_reasons") or [],
            "guideline_misses": decision.get("guideline_misses") or [],
            "screen_fail_reasons": decision.get("screen_fail_reasons") or [],
            "deep_dive_requirements": decision.get("deep_dive_requirements") or [],
            "metrics": deepcopy(_mapping(row.get("metrics"))),
        }
        if status == "selected":
            broad_groups["selected"].append(entry)
        elif status == "deferred_by_budget":
            broad_groups["deferred_by_budget"].append(entry)
        elif status in {
            "needs_enrichment",
            "sector_review_required",
            "near_miss_review",
            "review_required",
        }:
            broad_groups["review_required"].append(entry)
        elif status == "screened_out":
            broad_groups["screened_out"].append(entry)
        elif status == "excluded":
            broad_groups["excluded"].append(entry)
        elif status == "unavailable_after_enrichment":
            broad_groups["unavailable_after_enrichment"].append(entry)
    for values in broad_groups.values():
        values.sort(key=lambda row: str(row.get("symbol") or ""))
    broad_counts = {key: len(value) for key, value in broad_groups.items()}

    coverage_info = _derive_ranking_scope(
        _mapping(normalized_payload.get("screening_audit")), deep_dive_count=len(candidates)
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "runtime": runtime_metadata(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "analysis_as_of": analysis_as_of.isoformat(),
        "strict_mode": strict,
        "run_metadata": deepcopy(run_metadata),
        "ranking_status": ranking_status,
        "ranking_scope": coverage_info.get("ranking_scope"),
        "coverage": coverage_info,
        "price_basis": deepcopy(price_basis),
        "config": config,
        "global_sources": deepcopy(_list(normalized_payload.get("global_sources"))),
        "market_context": deepcopy(_mapping(normalized_payload.get("market_context"))),
        "screening_funnel": deepcopy(_mapping(normalized_payload.get("screening_funnel"))),
        "screening_audit": deepcopy(_mapping(normalized_payload.get("screening_audit"))),
        "broad_screen": {"counts": broad_counts, **broad_groups},
        "contract": deepcopy(contract),
        "counts": {
            "input_candidates": len(candidates),
            "eligible": len(eligible),
            "ranked": len(ranked),
            "conditional": len(conditional),
            "review_required": len(review),
            "screened_out": len(screened_out),
            "excluded": len(excluded),
        },
        "ranked_candidates": ranked,
        "conditional": conditional,
        "review_required": review,
        "screened_out": screened_out,
        "excluded": excluded,
        "final_three": _select_final_three(ranked, ranking_status=ranking_status, config=config),
        "global_warnings": list(dict.fromkeys(global_warnings)),
    }


def _derive_ranking_scope(audit: Mapping[str, Any], *, deep_dive_count: int) -> dict[str, Any]:
    """Classify how far the run's conclusion may be generalized, with coverage.

    ``final_marketwide`` requires estimate acquisition attempted for EVERY
    listing-universe symbol (exact counts); a bounded but fully processed
    subset is ``final_scoped`` (conclusions bind only to that subset); an
    unresolved enrichment queue makes the output ``diagnostic``. Listing
    enumeration completeness alone never yields a market-wide ranking.
    """
    # Delegated to the shared coverage-semantics module (used by discovery
    # too) so the tri-state semantics cannot drift between the two sides.
    return derive_ranking_scope_from_audit(audit, deep_dive_count=deep_dive_count)
