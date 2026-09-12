#!/usr/bin/env python3
"""Validate and rank normalized US undervalued-growth candidates (schema v3, contract v3.5).

The evaluator performs no network access. Upstream research must prepare a
source-linked JSON snapshot matching references/data-contract.md. The script
normalizes cash flow, verifies forecast arithmetic, blocks accounting-basis
mixing, validates corporate-action preflight evidence, calculates valuation
scenarios, routes candidates fail-closed, and writes audit-ready JSON/Markdown.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from collections.abc import Iterable, Mapping, Sequence
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from coverage_semantics import derive_ranking_scope_from_audit

try:
    from skill_version import (
        CONTRACT_REVISION,
        RUNTIME_FINGERPRINT,
        SCHEMA_VERSION,
        SKILL_VERSION,
        runtime_metadata,
    )
except ModuleNotFoundError:  # Supports importlib-based unit loading.
    import importlib.util as _importlib_util

    _version_path = Path(__file__).with_name("skill_version.py")
    _version_spec = _importlib_util.spec_from_file_location("skill_version", _version_path)
    if _version_spec is None or _version_spec.loader is None:
        raise
    _version_module = _importlib_util.module_from_spec(_version_spec)
    _version_spec.loader.exec_module(_version_module)
    CONTRACT_REVISION = _version_module.CONTRACT_REVISION
    RUNTIME_FINGERPRINT = _version_module.RUNTIME_FINGERPRINT
    SCHEMA_VERSION = _version_module.SCHEMA_VERSION
    SKILL_VERSION = _version_module.SKILL_VERSION
    runtime_metadata = _version_module.runtime_metadata


try:
    from research_contract import ContractError, validate_and_normalize_snapshot
except ModuleNotFoundError:  # Supports importlib-based unit loading.
    import importlib.util

    _contract_path = Path(__file__).with_name("research_contract.py")
    _contract_spec = importlib.util.spec_from_file_location("research_contract", _contract_path)
    if _contract_spec is None or _contract_spec.loader is None:
        raise
    _contract_module = importlib.util.module_from_spec(_contract_spec)
    _contract_spec.loader.exec_module(_contract_module)
    ContractError = _contract_module.ContractError
    validate_and_normalize_snapshot = _contract_module.validate_and_normalize_snapshot

DEFAULT_CONFIG: dict[str, Any] = {
    "min_market_cap": 500_000_000,
    "max_market_cap": 20_000_000_000,
    "min_price": 5.0,
    "min_average_daily_dollar_volume": 5_000_000,
    "hard_min_average_daily_dollar_volume": 1_000_000,
    "minimum_listing_data_coverage_pct": 95.0,
    "minimum_discovery_analyst_count": 2,
    "maximum_enrichment_attempts": 60,
    "max_candidates": 10,
    "minimum_data_quality_score": 70,
    "minimum_final_score_for_eligible": 70.0,
    "minimum_sbc_adjusted_fcf_yield_pct_for_eligible": 3.0,
    "maximum_ev_to_fcf_for_eligible": 30.0,
    "minimum_roic_pct_for_eligible": 8.0,
    "maximum_net_debt_to_ebitda_for_eligible": 3.0,
    "maximum_dilution_pct_for_eligible": 5.0,
    "minimum_low_case_upside_pct_for_eligible": 15.0,
    "maximum_quality_gate_failures_for_conditional": 2,
    "severe_loe_stress_downside_pct": -25.0,
    "final_three_minimum_score": 75.0,
    "final_three_minimum_data_quality": 80,
    "final_three_minimum_stress_upside_pct": 0.0,
    "final_three_minimum_sbc_adjusted_fcf_yield_pct": 5.0,
    "final_three_maximum_ev_to_fcf": 20.0,
    "final_three_minimum_low_case_upside_pct": 20.0,
    "minimum_constant_multiple_upside_pct": 30.0,
    "minimum_stressed_upside_pct": 0.0,
    "multiple_contraction_pct": 20.0,
    "maximum_cyclicality_without_normalization": 2,
    "allow_special_cases": True,
    "require_minimum_upside": True,
    "require_positive_stress_case": False,
    "max_quote_age_days": 7,
    "max_estimate_age_days": 45,
    "max_corporate_action_check_age_days": 14,
    "forecast_bridge_tolerance_pct": 2.0,
    "gaap_reconciliation_tolerance_pct": 2.0,
    "fcf_reconciliation_tolerance_pct": 5.0,
    "cash_consistency_tolerance_pct": 3.0,
    "max_market_context_age_days": 14,
    "max_policy_rate_source_age_days": 60,
    "max_market_rate_source_age_days": 7,
    "max_inflation_source_age_days": 45,
    "max_gdp_source_age_days": 120,
    "max_market_valuation_source_age_days": 14,
    "max_small_mid_context_source_age_days": 14,
    "minimum_analyst_count_for_ranked_horizon": 3,
    "require_forward_current_metric": True,
    "require_peer_set": True,
    "require_market_context": True,
    "require_screening_audit": True,
    "biopharma_loe_stress_multiples": [6.0, 8.0],
}

ALLOWED_EXCHANGES = {
    "NYSE",
    "NASDAQ",
    "NYSE AMERICAN",
    "NYSEAMERICAN",
    "AMEX",
}
ALLOWED_SPECIAL_CASES = {"none", "bank", "insurance", "reit", "bdc", "mlp"}
ALLOWED_VALUATION_BASES: dict[str, set[str]] = {
    "none": {"eps", "fcf_per_share", "ebit_per_share"},
    "bank": {"tbv_per_share", "book_value_per_share", "eps"},
    "insurance": {"book_value_per_share", "tbv_per_share", "eps"},
    "reit": {"affo_per_share", "nav_per_share"},
    "bdc": {"nav_per_share", "book_value_per_share", "nii_per_share"},
    "mlp": {"fcf_per_unit", "dcf_per_unit"},
}
ALLOWED_METRIC_BASES = {"gaap", "company_adjusted", "analyst_normalized", "sector_defined"}
ALLOWED_SOURCE_TYPES = {
    "reported_fact",
    "company_guidance",
    "market_consensus",
    "analyst_estimate",
}
ALLOWED_PERIOD_KINDS = {"ttm", "ntm", "fy1", "fy2", "fy3", "normalized", "other"}
ALLOWED_SESSIONS = {"regular_close", "pre_market", "after_hours", "intraday"}
ALLOWED_SCREENING_STATUSES = {
    "passed",
    "exception_admitted",
    "selected",
    "near_miss_review",
    "sector_review_required",
    "screened_out",
}
ALLOWED_CASH_FLOW_METHODS = {
    "reported_ttm",
    "sum_4_discrete",
    "fy_plus_current_ytd_minus_prior_ytd",
}
ALLOWED_MNA_STATUSES = {"none", "rumored", "pending", "completed", "terminated", "unknown"}
ALLOWED_LISTING_STATUSES = {"active", "suspended", "delisted", "unknown"}

SCORE_LIMITS: dict[str, float] = {
    "growth_sustainability": 20.0,
    "valuation_attractiveness": 20.0,
    "financial_quality": 15.0,
    "fcf_earnings_quality": 15.0,
    "competitive_advantage": 10.0,
    "capital_allocation": 10.0,
    "catalyst_risk_balance": 10.0,
}

QUALITY_WEIGHTS: dict[str, int] = {
    "quote_verified": 5,
    "latest_earnings_verified": 7,
    "sec_financials_verified": 10,
    "guidance_consensus_labeled": 8,
    "forecast_bridge_verified": 15,
    "diluted_shares_verified": 8,
    "sbc_verified": 8,
    "peer_set_verified": 8,
    "gaap_non_gaap_reconciled": 8,
    "corporate_actions_verified": 4,
    "cyclical_normalization_verified": 5,
    "cash_classification_verified": 5,
    "roic_ebitda_evidence_verified": 4,
    "sector_risk_verified": 5,
}

HARD_FLAG_LABELS: dict[str, str] = {
    "otc": "OTC listing",
    "penny_stock": "penny-stock characteristics",
    "spac_or_shell": "SPAC or shell company",
    "pre_revenue_or_development_stage": "pre-revenue or development-stage economics",
    "repeated_equity_financing": "repeated equity financing dependence",
    "pending_mna": "pending M&A / merger-arbitrage situation",
    "unresolved_material_weakness": "unresolved material weakness",
    "sec_investigation": "active or unresolved SEC investigation",
    "meme_only": "meme-driven valuation without operating support",
    "restatement_unresolved": "unresolved restatement",
    "extreme_illiquidity": "extreme illiquidity",
}


class InputError(ValueError):
    """Raised when the top-level input cannot be evaluated."""


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _text(value: Any) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        numeric = float(value)
        if math.isfinite(numeric):
            return numeric
    return None


def _integer(value: Any) -> int | None:
    numeric = _number(value)
    if numeric is None or not numeric.is_integer():
        return None
    return int(numeric)


def _round(value: float | None, digits: int = 4) -> float | None:
    return round(value, digits) if value is not None and math.isfinite(value) else None


def parse_iso8601(value: Any, field_name: str, *, required: bool = False) -> datetime | None:
    text = _text(value)
    if text is None:
        if required:
            raise InputError(f"{field_name} is required")
        return None
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise InputError(f"{field_name} must be ISO-8601: {text!r}") from exc
    if parsed.tzinfo is None:
        raise InputError(f"{field_name} must include a timezone: {text!r}")
    return parsed


def _parse_date(value: Any) -> datetime | None:
    text = _text(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text + "T00:00:00+00:00")
    except ValueError:
        return None


def _years_between(start: datetime, end: datetime) -> float:
    return max((end - start).total_seconds() / (365.2425 * 24 * 60 * 60), 0.0)


def _pct(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator * 100.0


def _cagr(start: float | None, end: float | None, years: float | None) -> float | None:
    if start is None or end is None or years is None or years <= 0 or start <= 0 or end < 0:
        return None
    return ((end / start) ** (1.0 / years) - 1.0) * 100.0


def _history_cagr(records: Any) -> dict[str, Any]:
    clean: list[dict[str, Any]] = []
    for item in _list(records):
        row = _mapping(item)
        value = _number(row.get("value"))
        if value is None:
            continue
        clean.append(
            {
                "value": value,
                "date": _parse_date(row.get("date")),
                "period": _text(row.get("period")),
            }
        )
    if len(clean) < 2:
        return {"cagr_pct": None, "years": None, "start": None, "end": None, "count": len(clean)}
    if all(row["date"] is not None for row in clean):
        clean.sort(key=lambda row: row["date"])
        years = _years_between(clean[0]["date"], clean[-1]["date"])
    else:
        years = float(len(clean) - 1)
    return {
        "cagr_pct": _cagr(clean[0]["value"], clean[-1]["value"], years),
        "years": years,
        "start": clean[0]["value"],
        "end": clean[-1]["value"],
        "count": len(clean),
        "start_period": clean[0]["period"],
        "end_period": clean[-1]["period"],
    }


def _format_number(value: Any, digits: int = 1, missing: str = "—") -> str:
    numeric = _number(value)
    if numeric is None:
        return missing
    abs_value = abs(numeric)
    if abs_value >= 1_000_000_000:
        return f"{numeric / 1_000_000_000:.{digits}f}B"
    if abs_value >= 1_000_000:
        return f"{numeric / 1_000_000:.{digits}f}M"
    if abs_value >= 1_000:
        return f"{numeric:,.{digits}f}"
    return f"{numeric:.{digits}f}"


def _format_pct(value: Any, digits: int = 1, missing: str = "—") -> str:
    numeric = _number(value)
    if numeric is None:
        return missing
    return f"{numeric:+.{digits}f}%"


def _format_price(value: Any, currency: str = "USD", missing: str = "—") -> str:
    numeric = _number(value)
    if numeric is None:
        return missing
    prefix = "$" if currency.upper() == "USD" else f"{currency.upper()} "
    return f"{prefix}{numeric:,.2f}"


def _deep_merge(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(base))
    for key, value in override.items():
        if isinstance(value, Mapping) and isinstance(result.get(key), Mapping):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _scenario(
    metric: float | None, multiple: float | None, price: float | None, years: float | None
) -> dict[str, Any] | None:
    if metric is None or multiple is None or price is None or years is None:
        return None
    if metric <= 0 or multiple <= 0 or price <= 0 or years <= 0:
        return None
    target = metric * multiple
    upside = (target / price - 1.0) * 100.0
    annualized = ((target / price) ** (1.0 / years) - 1.0) * 100.0
    return {
        "metric": _round(metric),
        "multiple": _round(multiple),
        "years": _round(years),
        "implied_price": _round(target),
        "upside_pct": _round(upside),
        "cagr_pct": _round(annualized),
    }


def _min_valid(values: Iterable[int | None]) -> int | None:
    valid = [value for value in values if value is not None and value >= 0]
    return min(valid) if valid else None


def _estimate_breadth_penalty(count: int | None) -> int:
    if count is None:
        return 5
    if count >= 5:
        return 0
    if count >= 3:
        return 2
    if count >= 1:
        return 4
    return 5


def _estimate_dispersion_penalty(dispersion_pct: float | None) -> int:
    if dispersion_pct is None:
        return 0
    if dispersion_pct > 50:
        return 4
    if dispersion_pct > 30:
        return 2
    if dispersion_pct > 15:
        return 1
    return 0


def _data_quality_penalty(score: int) -> int:
    if score >= 85:
        return 0
    if score >= 70:
        return 2
    if score >= 55:
        return 5
    return 10


def _cyclicality_penalty(score: int | None) -> int:
    return {1: 0, 2: 0, 3: 2, 4: 5, 5: 8}.get(score or 0, 5)


def _sbc_penalty(sbc_revenue_pct: float | None) -> int:
    if sbc_revenue_pct is None:
        return 2
    if sbc_revenue_pct > 25:
        return 8
    if sbc_revenue_pct > 15:
        return 5
    if sbc_revenue_pct > 10:
        return 3
    if sbc_revenue_pct > 5:
        return 1
    return 0


def _dilution_penalty(annualized_pct: float | None) -> int:
    if annualized_pct is None:
        return 2
    if annualized_pct <= 3:
        return 0
    if annualized_pct <= 5:
        return 2
    if annualized_pct <= 10:
        return 5
    return 8


def _dispersion_from_bounds(
    low: float | None, high: float | None, midpoint: float | None
) -> float | None:
    if low is None or high is None or midpoint is None or midpoint == 0 or high < low:
        return None
    return (high - low) / abs(midpoint) * 100.0


def _source_index(candidate: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for source in _list(candidate.get("sources")):
        item = _mapping(source)
        source_id = _text(item.get("id"))
        if source_id:
            index[source_id] = item
    return index


def _evidence_ids(candidate: Mapping[str, Any], field: str) -> list[str]:
    ids: list[str] = []
    evidence = _mapping(candidate.get("evidence"))
    for value in _list(evidence.get(field)):
        source_id = _text(value)
        if source_id and source_id not in ids:
            ids.append(source_id)
    for source in _list(candidate.get("sources")):
        item = _mapping(source)
        source_id = _text(item.get("id"))
        supports = {_text(value) for value in _list(item.get("supports"))}
        if source_id and field in supports and source_id not in ids:
            ids.append(source_id)
    return ids


def _resolved_sources(
    source_ids: Iterable[str | None], source_index: Mapping[str, Mapping[str, Any]]
) -> list[Mapping[str, Any]]:
    return [
        source_index[source_id]
        for source_id in source_ids
        if source_id and source_id in source_index
    ]


def _sources_resolve(
    source_ids: Iterable[str | None], source_index: Mapping[str, Mapping[str, Any]]
) -> bool:
    ids = [source_id for source_id in source_ids if source_id]
    return bool(ids) and all(source_id in source_index for source_id in ids)


def _has_tier(
    source_ids: Iterable[str | None], source_index: Mapping[str, Mapping[str, Any]], tiers: set[int]
) -> bool:
    return any(
        _integer(source.get("tier")) in tiers
        for source in _resolved_sources(source_ids, source_index)
    )


def _has_primary_source(source_index: Mapping[str, Mapping[str, Any]]) -> bool:
    return any(_integer(source.get("tier")) in {1, 2} for source in source_index.values())


def _candidate_source_ids(
    candidate: Mapping[str, Any], field: str, explicit: Any = None
) -> list[str]:
    ids = _evidence_ids(candidate, field)
    for item in _list(explicit):
        source_id = _text(item)
        if source_id and source_id not in ids:
            ids.append(source_id)
    return ids


def _validate_corporate_action(
    candidate: Mapping[str, Any],
    source_index: Mapping[str, Mapping[str, Any]],
    analysis_as_of: datetime,
    config: Mapping[str, Any],
) -> tuple[dict[str, Any], list[str], list[str], list[str]]:
    check = _mapping(candidate.get("corporate_action_check"))
    warnings: list[str] = []
    review: list[str] = []
    hard: list[str] = []

    checked_at = None
    try:
        checked_at = parse_iso8601(check.get("checked_at"), "corporate_action_check.checked_at")
    except InputError as exc:
        review.append(str(exc))

    source_ids = _candidate_source_ids(candidate, "corporate_action_check", check.get("source_ids"))
    evidence_ok = _sources_resolve(source_ids, source_index)
    if not evidence_ok:
        review.append("corporate-action preflight lacks resolving source evidence")

    listing_status = (_text(check.get("listing_status")) or "unknown").lower()
    mna_status = (_text(check.get("mna_status")) or "unknown").lower()
    symbol_active = check.get("symbol_active")

    if listing_status not in ALLOWED_LISTING_STATUSES:
        review.append(f"invalid corporate-action listing_status: {listing_status!r}")
    if mna_status not in ALLOWED_MNA_STATUSES:
        review.append(f"invalid corporate-action mna_status: {mna_status!r}")

    if listing_status in {"delisted", "suspended"}:
        hard.append(f"listing status is {listing_status}")
    if symbol_active is False:
        hard.append("symbol is not active")
    if mna_status in {"pending", "completed"}:
        hard.append(f"M&A status is {mna_status}; treat as special-situation pricing")
    elif mna_status == "rumored":
        review.append("M&A status is rumored and requires event-risk resolution")
    elif mna_status == "unknown":
        review.append("M&A status is unknown")
    if listing_status == "unknown":
        review.append("listing status is unknown")
    if symbol_active is not True:
        review.append("symbol_active is not positively verified")

    age_days = None
    if checked_at is not None:
        age_days = (analysis_as_of - checked_at).total_seconds() / 86_400
        if age_days < -1:
            review.append("corporate-action check timestamp is after analysis_as_of")
        max_age = _number(config.get("max_corporate_action_check_age_days")) or 14.0
        if age_days > max_age:
            review.append(
                f"corporate-action check is stale ({age_days:.1f} days old; maximum {max_age:.0f})"
            )

    return (
        {
            "checked_at": _text(check.get("checked_at")),
            "age_days": _round(age_days),
            "listing_status": listing_status,
            "mna_status": mna_status,
            "symbol_active": symbol_active is True,
            "latest_material_event_at": _text(check.get("latest_material_event_at")),
            "source_ids": source_ids,
            "evidence_ok": evidence_ok,
        },
        warnings,
        review,
        hard,
    )


def _cash_flow_component(
    row: Mapping[str, Any], label: str
) -> tuple[float | None, float | None, list[str]]:
    warnings: list[str] = []
    ocf = _number(row.get("operating_cash_flow"))
    capex = _number(row.get("capex_cash_outflow"))
    if capex is not None and capex < 0:
        warnings.append(f"{label}.capex_cash_outflow must be non-negative; received {capex}")
        capex = None
    return ocf, capex, warnings


def _cash_flow_sources_support_period(
    source_ids: Sequence[Any],
    source_index: Mapping[str, Mapping[str, Any]],
    *,
    support_path: str,
) -> bool:
    ids = [_text(value) for value in source_ids if _text(value)]
    if not ids or not all(source_id in source_index for source_id in ids):
        return False
    for source_id in ids:
        supports = {_text(value) for value in _list(source_index[source_id].get("supports"))}
        if support_path in supports:
            return True
    return False


def _reconstruct_ttm_cash_flow(
    financials: Mapping[str, Any],
    tolerance_pct: float,
    source_index: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, Any], list[str], list[str]]:
    ttm = _mapping(financials.get("cash_flow_ttm"))
    method = (_text(ttm.get("method")) or "").lower()
    warnings: list[str] = []
    review: list[str] = []
    source_checks: dict[str, bool] = {}

    supplied_ocf, supplied_capex, component_warnings = _cash_flow_component(
        ttm, "financials.cash_flow_ttm"
    )
    warnings.extend(component_warnings)
    supplied_fcf = _number(ttm.get("standard_fcf"))
    reconstructed_ocf: float | None = None
    reconstructed_capex: float | None = None
    used_periods: list[str] = []

    if method not in ALLOWED_CASH_FLOW_METHODS:
        review.append("cash_flow_ttm.method is missing or invalid")
    elif method == "reported_ttm":
        reconstructed_ocf = supplied_ocf
        reconstructed_capex = supplied_capex
        source_checks["reported_ttm"] = _cash_flow_sources_support_period(
            _list(ttm.get("source_ids")),
            source_index,
            support_path="financials.cash_flow_ttm.reported_ttm",
        )
        if not source_checks["reported_ttm"]:
            review.append(
                "reported_ttm cash flow requires a source explicitly supporting financials.cash_flow_ttm.reported_ttm"
            )
    elif method == "sum_4_discrete":
        periods: list[tuple[datetime, Mapping[str, Any]]] = []
        for item in _list(financials.get("cash_flow_periods")):
            row = _mapping(item)
            if (_text(row.get("period_type")) or "").lower() != "discrete_quarter":
                continue
            period_end = _parse_date(row.get("period_end"))
            if period_end is not None:
                periods.append((period_end, row))
        periods.sort(key=lambda pair: pair[0])
        selected = periods[-4:]
        if len(selected) != 4 or len({pair[0] for pair in selected}) != 4:
            review.append("sum_4_discrete requires four unique discrete quarters")
        else:
            ocf_values: list[float] = []
            capex_values: list[float] = []
            for _, row in selected:
                period_label = _text(row.get("period")) or _text(row.get("period_end")) or "unknown"
                period_end_label = _text(row.get("period_end")) or period_label
                support_path = f"financials.cash_flow_periods.{period_end_label}"
                source_checks[period_label] = _cash_flow_sources_support_period(
                    _list(row.get("source_ids")), source_index, support_path=support_path
                )
                if not source_checks[period_label]:
                    review.append(
                        f"cash-flow period {period_label} requires a source explicitly supporting {support_path}"
                    )
                ocf, capex, row_warnings = _cash_flow_component(
                    row, f"cash_flow_periods[{row.get('period')}]"
                )
                warnings.extend(row_warnings)
                if ocf is None or capex is None:
                    review.append(
                        "sum_4_discrete contains a quarter with missing/invalid OCF or capex"
                    )
                    break
                ocf_values.append(ocf)
                capex_values.append(capex)
                used_periods.append(
                    _text(row.get("period")) or _text(row.get("period_end")) or "unknown"
                )
            if len(ocf_values) == 4:
                reconstructed_ocf = sum(ocf_values)
                reconstructed_capex = sum(capex_values)
    elif method == "fy_plus_current_ytd_minus_prior_ytd":
        reconstruction = _mapping(financials.get("ttm_reconstruction"))
        parts: dict[str, tuple[float | None, float | None]] = {}
        for key in ("latest_fy", "current_ytd", "prior_ytd"):
            row = _mapping(reconstruction.get(key))
            support_path = f"financials.ttm_reconstruction.{key}"
            source_checks[key] = _cash_flow_sources_support_period(
                _list(row.get("source_ids")), source_index, support_path=support_path
            )
            if not source_checks[key]:
                review.append(
                    f"ttm_reconstruction.{key} requires a source explicitly supporting {support_path}"
                )
            ocf, capex, row_warnings = _cash_flow_component(row, f"ttm_reconstruction.{key}")
            warnings.extend(row_warnings)
            parts[key] = (ocf, capex)
            used_periods.append(_text(row.get("period")) or key)
        if all(parts[key][0] is not None and parts[key][1] is not None for key in parts):
            reconstructed_ocf = (
                parts["latest_fy"][0] + parts["current_ytd"][0] - parts["prior_ytd"][0]
            )
            reconstructed_capex = (
                parts["latest_fy"][1] + parts["current_ytd"][1] - parts["prior_ytd"][1]
            )
            if reconstructed_capex < 0:
                review.append(
                    "YTD reconstruction produced negative capex cash outflow; period inputs are likely inconsistent"
                )
                reconstructed_capex = None
        else:
            review.append(
                "fy_plus_current_ytd_minus_prior_ytd requires complete latest_fy/current_ytd/prior_ytd values"
            )

    canonical_ocf = reconstructed_ocf if reconstructed_ocf is not None else supplied_ocf
    canonical_capex = reconstructed_capex if reconstructed_capex is not None else supplied_capex
    calculated_fcf = (
        canonical_ocf - canonical_capex
        if canonical_ocf is not None and canonical_capex is not None
        else None
    )

    tolerance = max(float(tolerance_pct), 0.0)
    for supplied, calculated, label in (
        (supplied_ocf, reconstructed_ocf, "operating cash flow"),
        (supplied_capex, reconstructed_capex, "capex cash outflow"),
        (supplied_fcf, calculated_fcf, "standard FCF"),
    ):
        if supplied is None or calculated is None:
            continue
        denominator = max(abs(supplied), abs(calculated), 1.0)
        mismatch = abs(supplied - calculated) / denominator * 100.0
        if mismatch > tolerance:
            warnings.append(f"supplied {label} differs from reconstructed value by {mismatch:.1f}%")
            if mismatch > max(10.0, tolerance * 2):
                review.append(f"{label} reconciliation exceeds fail-closed tolerance")

    company_adjusted = _number(ttm.get("company_adjusted_fcf"))
    adjusted_definition = _text(ttm.get("company_adjusted_fcf_definition"))
    if company_adjusted is not None and not adjusted_definition:
        review.append("company_adjusted_fcf is present without a definition")

    return (
        {
            "method": method or None,
            "operating_cash_flow": _round(canonical_ocf),
            "capex_cash_outflow": _round(canonical_capex),
            "standard_fcf": _round(calculated_fcf),
            "supplied_standard_fcf": _round(supplied_fcf),
            "company_adjusted_fcf": _round(company_adjusted),
            "company_adjusted_fcf_definition": adjusted_definition,
            "used_periods": used_periods,
            "source_evidence": source_checks,
            "source_evidence_ok": bool(source_checks) and all(source_checks.values()),
        },
        warnings,
        review,
    )


def _calculate_financial_metrics(
    candidate: Mapping[str, Any],
    config: Mapping[str, Any],
    source_index: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, Any], list[str], list[str], list[str]]:
    identity = _mapping(candidate.get("identity"))
    financials = _mapping(candidate.get("financials"))
    histories = _mapping(financials.get("histories"))
    warnings: list[str] = []
    review: list[str] = []
    unresolved: list[str] = []

    market_cap = _number(identity.get("market_cap"))
    revenue = _number(financials.get("revenue_ttm"))
    cash_flow, cash_warnings, cash_review = _reconstruct_ttm_cash_flow(
        financials,
        _number(config.get("fcf_reconciliation_tolerance_pct")) or 5.0,
        source_index,
    )
    warnings.extend(cash_warnings)
    review.extend(cash_review)
    ocf = _number(cash_flow.get("operating_cash_flow"))
    standard_fcf = _number(cash_flow.get("standard_fcf"))

    sbc = _number(financials.get("sbc_ttm"))
    sbc_adjusted_fcf = standard_fcf - sbc if standard_fcf is not None and sbc is not None else None
    total_debt = _number(financials.get("total_debt"))
    cash_class = _mapping(financials.get("cash_classification"))
    corporate_cash = _number(cash_class.get("corporate_cash"))
    if corporate_cash is None:
        corporate_cash = _number(cash_class.get("cash_and_equivalents"))
    marketable_securities = _number(cash_class.get("marketable_securities")) or 0.0
    customer_funds = _number(cash_class.get("customer_or_settlement_funds"))
    restricted_cash = _number(cash_class.get("restricted_cash"))
    usable_cash = corporate_cash + marketable_securities if corporate_cash is not None else None
    ebitda = _number(financials.get("ebitda_ttm"))
    net_debt = (
        total_debt - usable_cash if total_debt is not None and usable_cash is not None else None
    )
    net_debt_ebitda = (
        net_debt / ebitda if net_debt is not None and ebitda is not None and ebitda > 0 else None
    )
    enterprise_value = (
        market_cap + total_debt - usable_cash
        if market_cap is not None and total_debt is not None and usable_cash is not None
        else None
    )
    ev_to_fcf = (
        enterprise_value / standard_fcf
        if enterprise_value is not None and standard_fcf is not None and standard_fcf > 0
        else None
    )
    ev_to_ebitda = (
        enterprise_value / ebitda
        if enterprise_value is not None and ebitda is not None and ebitda > 0
        else None
    )

    revenue_history = _history_cagr(histories.get("revenue"))
    eps_history = _history_cagr(histories.get("gaap_eps"))
    fcf_ps_history = _history_cagr(histories.get("fcf_per_share"))
    share_history = _history_cagr(histories.get("diluted_shares"))

    for name, value in (
        ("financials.revenue_ttm", revenue),
        ("financials.cash_flow_ttm.standard_fcf", standard_fcf),
        ("financials.sbc_ttm", sbc),
        ("identity.market_cap", market_cap),
        ("financials.cash_classification.corporate_cash", corporate_cash),
    ):
        if value is None:
            unresolved.append(name)

    metrics = {
        "cash_flow_ttm": cash_flow,
        "standard_fcf": _round(standard_fcf),
        "company_adjusted_fcf": cash_flow.get("company_adjusted_fcf"),
        "sbc_adjusted_fcf": _round(sbc_adjusted_fcf),
        "fcf_yield_pct": _round(_pct(standard_fcf, market_cap)),
        "sbc_adjusted_fcf_yield_pct": _round(_pct(sbc_adjusted_fcf, market_cap)),
        "fcf_margin_pct": _round(_pct(standard_fcf, revenue)),
        "sbc_revenue_pct": _round(_pct(sbc, revenue)),
        "sbc_ocf_pct": _round(_pct(sbc, ocf)),
        "cash_definition": "corporate_cash_plus_marketable_securities",
        "cash_classification_method": cash_class.get("classification_method"),
        "cash_classification_derived": cash_class.get("corporate_cash_derived") is True,
        "corporate_cash": _round(corporate_cash),
        "marketable_securities": _round(marketable_securities),
        "usable_corporate_cash": _round(usable_cash),
        "customer_or_settlement_funds": _round(customer_funds),
        "restricted_cash": _round(restricted_cash),
        "total_debt": _round(total_debt),
        "enterprise_value": _round(enterprise_value),
        "ev_to_fcf": _round(ev_to_fcf),
        "ev_to_ebitda": _round(ev_to_ebitda),
        "net_debt": _round(net_debt),
        "net_debt_to_ebitda": _round(net_debt_ebitda),
        "roic_pct": _round(_number(financials.get("roic_pct"))),
        "roe_pct": _round(_number(financials.get("roe_pct"))),
        "revenue_cagr_pct": _round(revenue_history.get("cagr_pct")),
        "gaap_eps_cagr_pct": _round(eps_history.get("cagr_pct")),
        "fcf_per_share_cagr_pct": _round(fcf_ps_history.get("cagr_pct")),
        "diluted_share_cagr_pct": _round(share_history.get("cagr_pct")),
        "history_details": {
            "revenue": {
                key: _round(value) if isinstance(value, float) else value
                for key, value in revenue_history.items()
            },
            "gaap_eps": {
                key: _round(value) if isinstance(value, float) else value
                for key, value in eps_history.items()
            },
            "fcf_per_share": {
                key: _round(value) if isinstance(value, float) else value
                for key, value in fcf_ps_history.items()
            },
            "diluted_shares": {
                key: _round(value) if isinstance(value, float) else value
                for key, value in share_history.items()
            },
        },
    }
    return metrics, warnings, review, unresolved


def _period_record(valuation: Mapping[str, Any], key: str) -> dict[str, Any]:
    return _mapping(_mapping(valuation.get("periods")).get(key))


def _validate_forecast_bridge(
    candidate: Mapping[str, Any],
    valuation_basis: str,
    valuation_periods: Mapping[str, Mapping[str, Any]],
    source_index: Mapping[str, Mapping[str, Any]],
    tolerance_pct: float,
) -> tuple[bool, dict[str, Any], list[str]]:
    """Rebuild future per-share metrics from operating drivers.

    ``metric_numerator / metric_denominator`` is retained only as an optional
    cross-check. It is never the primary calculation because reverse-engineering
    the numerator from consensus EPS would create a circular bridge.
    """
    bridge = _mapping(candidate.get("forecast_bridge"))
    bridge_periods = _mapping(bridge.get("periods"))
    reconciliation_periods = _mapping(_mapping(candidate.get("gaap_reconciliation")).get("periods"))
    details: dict[str, Any] = {}
    reasons: list[str] = []
    all_ok = True

    def pct_value(value: float | None) -> float | None:
        return value / 100.0 if value is not None else None

    for key in ("year_2", "year_3"):
        target = _mapping(valuation_periods.get(key))
        target_metric = _number(target.get("metric"))
        if target_metric is None:
            details[key] = {"required": False, "valid": True, "reason": "target metric unavailable"}
            continue

        row = _mapping(bridge_periods.get(key))
        drivers = _mapping(row.get("drivers"))
        driver_provenance = _mapping(row.get("driver_provenance"))
        construction_method = (_text(row.get("construction_method")) or "").lower()
        source_ids = [_text(value) for value in _list(row.get("source_ids")) if _text(value)]
        source_ok = _sources_resolve(source_ids, source_index)
        target_basis = (_text(target.get("metric_basis")) or "").lower()
        basis_ok = (_text(row.get("metric_basis")) or "").lower() == target_basis
        calculated_numerator: float | None = None
        calculated_denominator: float | None = None
        driver_chain: dict[str, Any] = {}
        drivers_ok = False
        driver_provenance_ok = False
        driver_provenance_details: dict[str, Any] = {}
        adjustment_bridge_ok = True
        adjustment_bridge_details: dict[str, Any] = {}

        if valuation_basis == "eps":
            revenue = _number(drivers.get("revenue"))
            operating_margin = _number(drivers.get("operating_margin_pct"))
            tax_rate = _number(drivers.get("tax_rate_pct"))
            diluted_shares = _number(drivers.get("diluted_shares"))
            net_interest_income = _number(drivers.get("net_interest_income"))
            net_interest_expense = _number(drivers.get("net_interest_expense"))
            other_pre_tax_income = _number(drivers.get("other_pre_tax_income"))
            after_tax_adjustments = _number(drivers.get("after_tax_adjustments"))
            interest_explicit = net_interest_income is not None or net_interest_expense is not None
            if net_interest_income is None:
                net_interest_income = 0.0
            if net_interest_expense is None:
                net_interest_expense = 0.0
            if other_pre_tax_income is None:
                other_pre_tax_income = 0.0
            adjustment_required = target_basis not in {"gaap", "sector_defined"}
            adjustment_ok = after_tax_adjustments is not None if adjustment_required else True
            if after_tax_adjustments is None:
                after_tax_adjustments = 0.0
            drivers_ok = (
                all(
                    value is not None
                    for value in (revenue, operating_margin, tax_rate, diluted_shares)
                )
                and interest_explicit
                and adjustment_ok
                and diluted_shares > 0
                and 0 <= tax_rate <= 100
            )
            if drivers_ok:
                operating_income = revenue * (operating_margin / 100.0)
                pre_tax_income = (
                    operating_income
                    + net_interest_income
                    - net_interest_expense
                    + other_pre_tax_income
                )
                gaap_net_income = pre_tax_income * (1.0 - tax_rate / 100.0)
                calculated_numerator = gaap_net_income + after_tax_adjustments
                calculated_denominator = diluted_shares
                driver_chain = {
                    "revenue": revenue,
                    "operating_margin_pct": operating_margin,
                    "operating_income": operating_income,
                    "net_interest_income": net_interest_income,
                    "net_interest_expense": net_interest_expense,
                    "other_pre_tax_income": other_pre_tax_income,
                    "pre_tax_income": pre_tax_income,
                    "tax_rate_pct": tax_rate,
                    "gaap_net_income": gaap_net_income,
                    "after_tax_adjustments": after_tax_adjustments,
                    "forecast_net_income": calculated_numerator,
                    "diluted_shares": diluted_shares,
                }
                if adjustment_required:
                    reconciliation_row = _mapping(reconciliation_periods.get(key))
                    reconciliation_gaap_metric = _number(reconciliation_row.get("gaap_metric"))
                    adjustment_rows = _list(reconciliation_row.get("adjustments"))
                    reconciliation_adjustment_per_share = 0.0
                    reconciliation_adjustments_ok = bool(adjustment_rows)
                    for item in adjustment_rows:
                        amount = _number(_mapping(item).get("amount"))
                        if amount is None:
                            reconciliation_adjustments_ok = False
                            break
                        reconciliation_adjustment_per_share += amount
                    expected_after_tax_adjustments = (
                        reconciliation_adjustment_per_share * diluted_shares
                        if reconciliation_adjustments_ok
                        else None
                    )
                    driver_gaap_metric = gaap_net_income / diluted_shares
                    gaap_diff_pct = (
                        abs(driver_gaap_metric - reconciliation_gaap_metric)
                        / max(abs(reconciliation_gaap_metric), 1e-12)
                        * 100.0
                        if reconciliation_gaap_metric is not None
                        else None
                    )
                    adjustment_diff_pct = (
                        abs(after_tax_adjustments - expected_after_tax_adjustments)
                        / max(abs(expected_after_tax_adjustments), 1.0)
                        * 100.0
                        if expected_after_tax_adjustments is not None
                        else None
                    )
                    adjustment_bridge_ok = bool(
                        reconciliation_adjustments_ok
                        and reconciliation_gaap_metric is not None
                        and gaap_diff_pct is not None
                        and gaap_diff_pct <= tolerance_pct
                        and adjustment_diff_pct is not None
                        and adjustment_diff_pct <= tolerance_pct
                    )
                    adjustment_bridge_details = {
                        "reconciliation_gaap_metric": _round(reconciliation_gaap_metric),
                        "driver_gaap_metric": _round(driver_gaap_metric),
                        "gaap_difference_pct": _round(gaap_diff_pct),
                        "reconciliation_adjustment_per_share": _round(
                            reconciliation_adjustment_per_share
                        ),
                        "expected_after_tax_adjustments": _round(expected_after_tax_adjustments),
                        "driver_after_tax_adjustments": _round(after_tax_adjustments),
                        "adjustment_difference_pct": _round(adjustment_diff_pct),
                    }
        elif valuation_basis == "fcf_per_share":
            diluted_shares = _number(drivers.get("diluted_shares"))
            operating_cash_flow = _number(drivers.get("operating_cash_flow"))
            capex = _number(drivers.get("capex_cash_outflow"))
            revenue = _number(drivers.get("revenue"))
            fcf_margin = _number(drivers.get("fcf_margin_pct"))
            if operating_cash_flow is not None and capex is not None and capex >= 0:
                calculated_numerator = operating_cash_flow - capex
                method = "operating_cash_flow_minus_capex"
            elif revenue is not None and fcf_margin is not None:
                calculated_numerator = revenue * (fcf_margin / 100.0)
                method = "revenue_times_fcf_margin"
            else:
                method = None
            calculated_denominator = diluted_shares
            drivers_ok = (
                calculated_numerator is not None
                and diluted_shares is not None
                and diluted_shares > 0
            )
            driver_chain = {
                "method": method,
                "revenue": revenue,
                "fcf_margin_pct": fcf_margin,
                "operating_cash_flow": operating_cash_flow,
                "capex_cash_outflow": capex,
                "standard_fcf": calculated_numerator,
                "diluted_shares": diluted_shares,
            }
        elif valuation_basis == "ebit_per_share":
            revenue = _number(drivers.get("revenue"))
            operating_margin = _number(drivers.get("operating_margin_pct"))
            diluted_shares = _number(drivers.get("diluted_shares"))
            drivers_ok = (
                all(value is not None for value in (revenue, operating_margin, diluted_shares))
                and diluted_shares > 0
            )
            if drivers_ok:
                calculated_numerator = revenue * (operating_margin / 100.0)
                calculated_denominator = diluted_shares
                driver_chain = {
                    "revenue": revenue,
                    "operating_margin_pct": operating_margin,
                    "forecast_ebit": calculated_numerator,
                    "diluted_shares": diluted_shares,
                }
        else:
            # Sector-defined metrics may not have an income-statement bridge,
            # but they must state a formula and provide independently sourced
            # numerator/denominator inputs.
            calculated_numerator = _number(row.get("metric_numerator"))
            calculated_denominator = _number(row.get("metric_denominator"))
            formula = _text(row.get("calculation_formula"))
            drivers_ok = (
                calculated_numerator is not None
                and calculated_denominator is not None
                and calculated_denominator > 0
                and bool(formula)
                and len(drivers) >= 2
            )
            driver_chain = {"calculation_formula": formula, **deepcopy(drivers)}

        required_driver_names: list[str] = []
        if valuation_basis == "eps":
            required_driver_names = [
                "revenue",
                "operating_margin_pct",
                "tax_rate_pct",
                "diluted_shares",
            ]
            if _number(drivers.get("net_interest_income")) is not None:
                required_driver_names.append("net_interest_income")
            elif _number(drivers.get("net_interest_expense")) is not None:
                required_driver_names.append("net_interest_expense")
            else:
                required_driver_names.append("net_interest_income_or_expense")
            if target_basis not in {"gaap", "sector_defined"}:
                required_driver_names.append("after_tax_adjustments")
        elif valuation_basis == "fcf_per_share":
            required_driver_names = ["diluted_shares"]
            if _number(drivers.get("operating_cash_flow")) is not None:
                required_driver_names.extend(["operating_cash_flow", "capex_cash_outflow"])
            else:
                required_driver_names.extend(["revenue", "fcf_margin_pct"])
        elif valuation_basis == "ebit_per_share":
            required_driver_names = ["revenue", "operating_margin_pct", "diluted_shares"]
        else:
            required_driver_names = sorted(driver_provenance)

        allowed_origins = {
            "company_guidance",
            "market_consensus",
            "historical_run_rate",
            "company_target",
            "analyst_assumption",
            "primary_source_calculation",
        }
        provenance_failures: list[str] = []
        for driver_name in required_driver_names:
            if driver_name == "net_interest_income_or_expense":
                provenance_candidates = [
                    _mapping(driver_provenance.get("net_interest_income")),
                    _mapping(driver_provenance.get("net_interest_expense")),
                ]
                item = next((candidate for candidate in provenance_candidates if candidate), {})
            else:
                item = _mapping(driver_provenance.get(driver_name))
            origin = (_text(item.get("origin")) or "").lower()
            ids = [_text(value) for value in _list(item.get("source_ids")) if _text(value)]
            target_solved = (
                item.get("target_solved") is True or item.get("derived_from_target_metric") is True
            )
            valid_item = (
                bool(item)
                and origin in allowed_origins
                and _sources_resolve(ids, source_index)
                and not target_solved
            )
            driver_provenance_details[driver_name] = {
                "origin": origin or None,
                "source_ids": ids,
                "target_solved": target_solved,
                "valid": valid_item,
            }
            if not valid_item:
                provenance_failures.append(driver_name)
        driver_provenance_ok = (
            construction_method == "independent_driver_model"
            and bool(required_driver_names)
            and not provenance_failures
        )

        calculated_metric = (
            calculated_numerator / calculated_denominator
            if calculated_numerator is not None
            and calculated_denominator is not None
            and calculated_denominator > 0
            else None
        )
        diff_pct = None
        arithmetic_ok = False
        if calculated_metric is not None:
            denominator = max(abs(target_metric), 1e-12)
            diff_pct = abs(calculated_metric - target_metric) / denominator * 100.0
            arithmetic_ok = diff_pct <= tolerance_pct

        supplied_numerator = _number(row.get("metric_numerator"))
        supplied_denominator = _number(row.get("metric_denominator"))
        numerator_crosscheck_ok = True
        denominator_crosscheck_ok = True
        if supplied_numerator is not None and calculated_numerator is not None:
            numerator_diff = (
                abs(supplied_numerator - calculated_numerator)
                / max(abs(calculated_numerator), 1.0)
                * 100.0
            )
            numerator_crosscheck_ok = numerator_diff <= tolerance_pct
        else:
            numerator_diff = None
        if supplied_denominator is not None and calculated_denominator is not None:
            denominator_diff = (
                abs(supplied_denominator - calculated_denominator)
                / max(abs(calculated_denominator), 1.0)
                * 100.0
            )
            denominator_crosscheck_ok = denominator_diff <= tolerance_pct
        else:
            denominator_diff = None

        valid = (
            arithmetic_ok
            and source_ok
            and basis_ok
            and drivers_ok
            and driver_provenance_ok
            and numerator_crosscheck_ok
            and denominator_crosscheck_ok
            and adjustment_bridge_ok
        )
        if not valid:
            all_ok = False
            if not drivers_ok:
                reasons.append(f"{key} forecast bridge lacks a complete driver-derived model")
            if not driver_provenance_ok:
                reasons.append(
                    f"{key} forecast bridge drivers are not independently sourced or are target-solved"
                )
            if not arithmetic_ok:
                reasons.append(
                    f"{key} driver-derived forecast does not tie to the valuation metric"
                )
            if not source_ok:
                reasons.append(f"{key} forecast bridge source IDs do not resolve")
            if not basis_ok:
                reasons.append(f"{key} forecast bridge metric basis differs from valuation period")
            if not numerator_crosscheck_ok:
                reasons.append(
                    f"{key} supplied metric_numerator is not supported by the operating-driver model"
                )
            if not denominator_crosscheck_ok:
                reasons.append(
                    f"{key} supplied metric_denominator differs from driver diluted shares"
                )
            if not adjustment_bridge_ok:
                reasons.append(
                    f"{key} adjusted forecast bridge does not reconcile driver GAAP EPS and after-tax adjustments"
                )

        details[key] = {
            "required": True,
            "valid": valid,
            "calculation_method": "driver_derived",
            "calculated_numerator": _round(calculated_numerator),
            "calculated_denominator": _round(calculated_denominator),
            "calculated_metric": _round(calculated_metric),
            "target_metric": _round(target_metric),
            "difference_pct": _round(diff_pct),
            "arithmetic_ok": arithmetic_ok,
            "source_ok": source_ok,
            "basis_ok": basis_ok,
            "drivers_ok": drivers_ok,
            "construction_method": construction_method or None,
            "driver_provenance_ok": driver_provenance_ok,
            "driver_provenance": driver_provenance_details,
            "numerator_crosscheck_ok": numerator_crosscheck_ok,
            "numerator_difference_pct": _round(numerator_diff),
            "denominator_crosscheck_ok": denominator_crosscheck_ok,
            "denominator_difference_pct": _round(denominator_diff),
            "adjustment_bridge_ok": adjustment_bridge_ok,
            "adjustment_bridge_details": adjustment_bridge_details,
            "source_ids": source_ids,
            "drivers": deepcopy(drivers),
            "driver_chain": {
                k: _round(v) if isinstance(v, float) else v for k, v in driver_chain.items()
            },
        }

    return all_ok, details, list(dict.fromkeys(reasons))


def _validate_gaap_reconciliation(
    candidate: Mapping[str, Any],
    valuation_periods: Mapping[str, Mapping[str, Any]],
    source_index: Mapping[str, Mapping[str, Any]],
    tolerance_pct: float,
) -> tuple[bool, dict[str, Any], list[str]]:
    reconciliation = _mapping(candidate.get("gaap_reconciliation"))
    rows = _mapping(reconciliation.get("periods"))
    details: dict[str, Any] = {}
    reasons: list[str] = []
    all_ok = True

    for key in ("current", "year_2", "year_3"):
        target = _mapping(valuation_periods.get(key))
        target_metric = _number(target.get("metric"))
        basis = (_text(target.get("metric_basis")) or "").lower()
        if target_metric is None:
            details[key] = {"required": False, "valid": True, "reason": "metric unavailable"}
            continue
        if basis in {"gaap", "sector_defined"}:
            details[key] = {
                "required": False,
                "valid": True,
                "reason": f"{basis} requires no adjustment bridge",
            }
            continue
        row = _mapping(rows.get(key))
        gaap_metric = _number(row.get("gaap_metric"))
        adjustments = _list(row.get("adjustments"))
        adjustment_total = 0.0
        adjustments_ok = bool(adjustments)
        normalized_adjustments: list[dict[str, Any]] = []
        for item in adjustments:
            adjustment = _mapping(item)
            amount = _number(adjustment.get("amount"))
            label = _text(adjustment.get("label"))
            recurring = adjustment.get("recurring")
            if amount is None or not label or recurring not in {True, False}:
                adjustments_ok = False
                continue
            adjustment_total += amount
            normalized_adjustments.append(
                {"label": label, "amount": _round(amount), "recurring": recurring}
            )
        calculated = (
            gaap_metric + adjustment_total if gaap_metric is not None and adjustments_ok else None
        )
        diff_pct = None
        arithmetic_ok = False
        if calculated is not None and target_metric != 0:
            diff_pct = abs(calculated - target_metric) / abs(target_metric) * 100.0
            arithmetic_ok = diff_pct <= tolerance_pct
        source_ids = [_text(value) for value in _list(row.get("source_ids"))]
        source_ok = _sources_resolve(source_ids, source_index)
        valid = arithmetic_ok and source_ok and adjustments_ok
        if not valid:
            all_ok = False
            if not adjustments_ok:
                reasons.append(f"{key} GAAP reconciliation lacks complete adjustment rows")
            if not arithmetic_ok:
                reasons.append(f"{key} GAAP reconciliation does not tie to valuation metric")
            if not source_ok:
                reasons.append(f"{key} GAAP reconciliation source IDs do not resolve")
        details[key] = {
            "required": True,
            "valid": valid,
            "gaap_metric": _round(gaap_metric),
            "adjustments": normalized_adjustments,
            "calculated_metric": _round(calculated),
            "target_metric": _round(target_metric),
            "difference_pct": _round(diff_pct),
            "source_ids": [value for value in source_ids if value],
        }
    return all_ok, details, list(dict.fromkeys(reasons))


def _calculate_valuation(
    candidate: Mapping[str, Any],
    config: Mapping[str, Any],
    analysis_as_of: datetime,
    source_index: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, Any], list[str], list[str], list[str]]:
    identity = _mapping(candidate.get("identity"))
    valuation = _mapping(candidate.get("valuation_case"))
    warnings: list[str] = []
    review: list[str] = []
    hard: list[str] = []

    price = _number(identity.get("price"))
    special_case = (_text(identity.get("special_case")) or "none").lower()
    basis = (_text(valuation.get("basis")) or "").lower()
    if special_case not in ALLOWED_SPECIAL_CASES:
        hard.append(f"invalid special_case: {special_case!r}")
    elif basis not in ALLOWED_VALUATION_BASES[special_case]:
        hard.append(f"valuation basis {basis!r} is invalid for special_case {special_case!r}")

    raw_periods = _mapping(valuation.get("periods"))
    periods: dict[str, dict[str, Any]] = {}
    bases: list[str] = []
    min_count = _integer(config.get("minimum_analyst_count_for_ranked_horizon")) or 3
    for key in ("current", "year_2", "year_3"):
        row = _mapping(raw_periods.get(key))
        metric = _number(row.get("metric"))
        metric_basis = (_text(row.get("metric_basis")) or "").lower()
        source_type = (_text(row.get("source_type")) or "").lower()
        period_kind = (_text(row.get("period_kind")) or "other").lower()
        if metric is not None and metric <= 0:
            review.append(f"valuation_case.periods.{key}.metric must be positive")
        if metric is not None and metric_basis not in ALLOWED_METRIC_BASES:
            review.append(f"valuation_case.periods.{key}.metric_basis is missing or invalid")
        if metric is not None and source_type not in ALLOWED_SOURCE_TYPES:
            review.append(f"valuation_case.periods.{key}.source_type is missing or invalid")
        if metric is not None and period_kind not in ALLOWED_PERIOD_KINDS:
            review.append(f"valuation_case.periods.{key}.period_kind is invalid")
        source_ids = [_text(value) for value in _list(row.get("source_ids"))]
        if metric is not None and not _sources_resolve(source_ids, source_index):
            review.append(f"valuation_case.periods.{key} source IDs do not resolve")
        retrieved_at = None
        age_days = None
        try:
            retrieved_at = parse_iso8601(
                row.get("retrieved_at"), f"valuation_case.periods.{key}.retrieved_at"
            )
        except InputError as exc:
            if source_type in {"market_consensus", "analyst_estimate", "company_guidance"}:
                review.append(str(exc))
        if retrieved_at is not None:
            age_days = (analysis_as_of - retrieved_at).total_seconds() / 86_400
            max_age = _number(config.get("max_estimate_age_days")) or 45.0
            if age_days < -1:
                review.append(f"{key} estimate retrieval timestamp is after analysis_as_of")
            if source_type in {"market_consensus", "analyst_estimate"} and age_days > max_age:
                review.append(
                    f"{key} estimate is stale ({age_days:.1f} days old; maximum {max_age:.0f})"
                )
        low = _number(row.get("estimate_low"))
        high = _number(row.get("estimate_high"))
        dispersion = _dispersion_from_bounds(low, high, metric)
        if dispersion is not None and dispersion > 30:
            warnings.append(f"{key} estimate dispersion is high at {dispersion:.1f}%")
        years = _number(row.get("years"))
        analyst_count = _integer(row.get("analyst_count"))
        rankable = row.get("rankable") is True
        if key == "current":
            rankable = period_kind in {"ntm", "fy1"}
            if not rankable and bool(config.get("require_forward_current_metric", True)):
                review.append(
                    "formal constant-multiple analysis requires NTM or FY1 current metric; TTM is supplemental only"
                )
            if (
                source_type in {"market_consensus", "analyst_estimate"}
                and (analyst_count or 0) < min_count
                and row.get("independent_model") is not True
            ):
                review.append(f"current forward metric has fewer than {min_count} analysts")
        periods[key] = {
            "label": _text(row.get("label")),
            "period_kind": period_kind,
            "period_end": _text(row.get("period_end")),
            "metric": _round(metric),
            "metric_basis": metric_basis,
            "source_type": source_type,
            "retrieved_at": _text(row.get("retrieved_at")),
            "age_days": _round(age_days),
            "source_ids": [value for value in source_ids if value],
            "analyst_count": analyst_count,
            "estimate_low": _round(low),
            "estimate_high": _round(high),
            "dispersion_pct": _round(dispersion),
            "years": years,
            "independent_model": row.get("independent_model") is True,
            "rankable": rankable,
        }
        if metric is not None and metric_basis:
            bases.append(metric_basis)

    current_metric = _number(periods["current"].get("metric"))
    if price is None or price <= 0:
        hard.append("current price must be positive")
    if current_metric is None or current_metric <= 0:
        hard.append("current per-share valuation metric must be positive")

    basis_consistent = len(set(bases)) <= 1 and bool(bases)
    if not basis_consistent:
        review.append("current and future valuation periods do not use one consistent metric basis")
    forward_current_valid = (
        periods["current"].get("period_kind") in {"ntm", "fy1"}
        and periods["current"].get("rankable") is True
    )
    current_multiple = (
        price / current_metric if price and current_metric and current_metric > 0 else None
    )
    supplied_multiple = _number(valuation.get("supplied_current_multiple"))
    multiple_diff_pct = None
    if supplied_multiple is not None and current_multiple is not None:
        multiple_diff_pct = abs(supplied_multiple - current_multiple) / current_multiple * 100.0
        if multiple_diff_pct > 10:
            warnings.append(
                f"supplied current multiple differs from price/current metric by {multiple_diff_pct:.1f}%"
            )
        if multiple_diff_pct > 25:
            review.append(
                "supplied current multiple materially conflicts with price/current metric"
            )

    contraction_pct = _number(config.get("multiple_contraction_pct")) or 20.0
    stress_multiple = current_multiple * (1 - contraction_pct / 100.0) if current_multiple else None
    y2_metric = _number(periods["year_2"].get("metric"))
    y3_metric = _number(periods["year_3"].get("metric"))
    y2_years = _number(periods["year_2"].get("years")) or 2.0
    y3_years = _number(periods["year_3"].get("years")) or 3.0

    formal_valid = basis_consistent and forward_current_valid
    if formal_valid:
        constant_2 = _scenario(y2_metric, current_multiple, price, y2_years)
        constant_3 = _scenario(y3_metric, current_multiple, price, y3_years)
        stress_2 = _scenario(y2_metric, stress_multiple, price, y2_years)
        stress_3 = _scenario(y3_metric, stress_multiple, price, y3_years)
    else:
        constant_2 = constant_3 = stress_2 = stress_3 = None

    peers = _list(candidate.get("peers"))
    peer_multiples: list[float] = []
    peer_checks: list[bool] = []
    current_basis = _text(periods["current"].get("metric_basis"))
    current_period_kind = _text(periods["current"].get("period_kind"))
    for peer in peers:
        row = _mapping(peer)
        multiple = _number(row.get("multiple"))
        source_ok = _sources_resolve([_text(row.get("source_id"))], source_index)
        valid = (
            multiple is not None
            and multiple > 0
            and bool(_text(row.get("selection_reason")))
            and (_text(row.get("metric_basis")) or "").lower() == (current_basis or "").lower()
            and (_text(row.get("multiple_period_kind")) or "").lower()
            == (current_period_kind or "").lower()
            and source_ok
        )
        peer_checks.append(valid)
        if valid:
            peer_multiples.append(multiple)
    calculated_peer_median = statistics.median(peer_multiples) if len(peer_multiples) >= 3 else None
    supplied_peer = _mapping(valuation.get("peer_median_multiple"))
    supplied_peer_value = _number(supplied_peer.get("value"))
    peer_source_ids = [_text(value) for value in _list(supplied_peer.get("source_ids"))]
    supplied_peer_ok = (
        supplied_peer_value is not None
        and supplied_peer_value > 0
        and (_text(supplied_peer.get("metric_basis")) or "").lower()
        == (current_basis or "").lower()
        and (_text(supplied_peer.get("multiple_period_kind")) or "").lower()
        == (current_period_kind or "").lower()
        and _sources_resolve(peer_source_ids, source_index)
    )
    peer_median = supplied_peer_value if supplied_peer_ok else calculated_peer_median
    peer_valid = formal_valid and len(peer_multiples) >= 3 and all(peer_checks)
    if bool(config.get("require_peer_set", True)) and not peer_valid:
        review.append("three to five sourced genuine peers on the same forward basis are required")
    peer_2 = _scenario(y2_metric, peer_median, price, y2_years) if peer_valid else None
    peer_3 = _scenario(y3_metric, peer_median, price, y3_years) if peer_valid else None

    forecast_ok, forecast_details, forecast_reasons = _validate_forecast_bridge(
        candidate,
        basis,
        periods,
        source_index,
        _number(config.get("forecast_bridge_tolerance_pct")) or 2.0,
    )
    reconciliation_ok, reconciliation_details, reconciliation_reasons = (
        _validate_gaap_reconciliation(
            candidate,
            periods,
            source_index,
            _number(config.get("gaap_reconciliation_tolerance_pct")) or 2.0,
        )
    )

    rankable_horizons: dict[str, bool] = {}
    for key in ("year_2", "year_3"):
        row = periods[key]
        rankable = row.get("rankable") is True
        if row.get("independent_model") is True:
            rankable = rankable and forecast_ok
        rankable_horizons[key] = bool(rankable and formal_valid)
    if not any(rankable_horizons.values()):
        review.append("no rankable two- or three-year forward scenario")

    future_counts = [
        _integer(periods[key].get("analyst_count"))
        for key in ("year_2", "year_3")
        if rankable_horizons.get(key) and _number(periods[key].get("metric")) is not None
    ]
    minimum_analyst_count = _min_valid(future_counts)
    valid_dispersions = [
        _number(periods[key].get("dispersion_pct"))
        for key in ("year_2", "year_3")
        if rankable_horizons.get(key)
    ]
    valid_dispersions = [value for value in valid_dispersions if value is not None]
    maximum_dispersion = max(valid_dispersions) if valid_dispersions else None

    return (
        {
            "basis": basis,
            "periods": periods,
            "metric_basis_consistent": basis_consistent,
            "forward_current_valid": forward_current_valid,
            "formal_forward_scenario_valid": formal_valid,
            "rankable_horizons": rankable_horizons,
            "current_metric": _round(current_metric),
            "current_metric_basis": current_basis,
            "current_period_kind": current_period_kind,
            "current_multiple": _round(current_multiple),
            "supplied_current_multiple": _round(supplied_multiple),
            "current_multiple_difference_pct": _round(multiple_diff_pct),
            "multiple_contraction_pct": _round(contraction_pct),
            "stress_multiple": _round(stress_multiple),
            "peer_median_multiple": _round(peer_median),
            "calculated_peer_median_multiple": _round(calculated_peer_median),
            "peer_set_basis_valid": peer_valid,
            "minimum_analyst_count": minimum_analyst_count,
            "maximum_estimate_dispersion_pct": _round(maximum_dispersion),
            "forecast_bridge_valid": forecast_ok,
            "forecast_bridge_details": forecast_details,
            "gaap_reconciliation_valid": reconciliation_ok,
            "gaap_reconciliation_details": reconciliation_details,
            "constant_multiple": {"year_2": constant_2, "year_3": constant_3},
            "multiple_contraction": {"year_2": stress_2, "year_3": stress_3},
            "peer_median": {"year_2": peer_2, "year_3": peer_3},
        },
        warnings,
        list(dict.fromkeys(review + forecast_reasons + reconciliation_reasons)),
        hard,
    )


def _validate_sector_profile(
    candidate: Mapping[str, Any],
    financial_metrics: Mapping[str, Any],
    valuation: Mapping[str, Any],
    analysis_as_of: datetime,
    source_index: Mapping[str, Mapping[str, Any]],
    config: Mapping[str, Any],
    strict: bool,
) -> tuple[dict[str, Any], list[str], list[str], int]:
    profile = _mapping(candidate.get("sector_profile"))
    raw_profile_type = (_text(profile.get("type")) or "general").lower()
    profile_aliases = {
        "biopharma": "commercial_biopharma",
        "pharma": "commercial_biopharma",
        "biotechnology": "commercial_biopharma",
        "royalty_biopharma": "commercial_biopharma",
        "drug_delivery_platform": "commercial_biopharma",
    }
    profile_type = profile_aliases.get(raw_profile_type, raw_profile_type)
    kpis = _mapping(profile.get("kpis"))
    warnings: list[str] = []
    review: list[str] = []
    penalty = 0
    details: dict[str, Any] = {
        "type": profile_type,
        "raw_type": raw_profile_type,
        "type_normalized": profile_type != raw_profile_type,
        "kpis": deepcopy(kpis),
    }

    source_ids = [_text(value) for value in _list(kpis.get("source_ids"))]
    sector_sources_ok = _sources_resolve(source_ids, source_index) if source_ids else False
    details["source_ids"] = [value for value in source_ids if value]
    details["source_evidence_ok"] = sector_sources_ok

    if profile_type == "commercial_biopharma":
        concentration = _number(kpis.get("top_product_revenue_pct"))
        if concentration is None:
            concentration = _number(kpis.get("top_revenue_stream_pct"))
        if concentration is None:
            concentration = _number(kpis.get("top_program_revenue_pct"))
        top_revenue = _number(kpis.get("top_product_revenue"))
        if top_revenue is None:
            top_revenue = _number(kpis.get("top_revenue_stream"))
        total_revenue = _number(kpis.get("total_revenue"))
        if (
            concentration is None
            and top_revenue is not None
            and total_revenue
            and total_revenue > 0
        ):
            concentration = top_revenue / total_revenue * 100.0
            details["concentration_derived"] = True
        details["top_product_revenue_pct"] = _round(concentration)
        loe_value = kpis.get("nearest_material_loe_date") or kpis.get("nearest_loe_date")
        loe_date = _parse_date(loe_value)
        loe_years = (
            _years_between(analysis_as_of.astimezone(timezone.utc), loe_date) if loe_date else None
        )
        details["nearest_material_loe_date"] = _text(loe_value)
        details["years_to_nearest_loe"] = _round(loe_years)
        if concentration is None or loe_date is None or not sector_sources_ok:
            if strict:
                review.append(
                    "commercial biopharma requires sourced product concentration and nearest material LOE evidence"
                )
        elif loe_years is not None and loe_years <= 5 and concentration >= 50:
            warnings.append(
                f"high product concentration ({concentration:.1f}%) with nearest LOE in {loe_years:.1f} years"
            )
            penalty = 4 if loe_years <= 3 else 2
            multiples = [
                _number(value)
                for value in _list(config.get("biopharma_loe_stress_multiples"))
                if _number(value) is not None and _number(value) > 0
            ]
            price = _number(_mapping(candidate.get("identity")).get("price"))
            y3_metric = _number(
                _mapping(_mapping(valuation.get("periods")).get("year_3")).get("metric")
            )
            y3_years = (
                _number(_mapping(_mapping(valuation.get("periods")).get("year_3")).get("years"))
                or 3.0
            )
            details["loe_stress_scenarios"] = [
                {"multiple": multiple, **(_scenario(y3_metric, multiple, price, y3_years) or {})}
                for multiple in sorted(set(multiples))
            ]
    elif profile_type == "payments":
        cash = _mapping(_mapping(candidate.get("financials")).get("cash_classification"))
        if (
            _number(cash.get("corporate_cash")) is None
            or _number(cash.get("customer_or_settlement_funds")) is None
            or not sector_sources_ok
        ):
            if strict:
                review.append(
                    "payments company requires sourced corporate cash separated from customer/settlement funds"
                )
        take_rate = _number(kpis.get("gross_profit_to_tpv_pct"))
        if take_rate is None:
            take_rate = _number(kpis.get("gross_profit_take_rate_pct"))
        prior_take_rate = _number(kpis.get("gross_profit_to_tpv_prior_pct"))
        if prior_take_rate is None:
            prior_take_rate = _number(kpis.get("gross_profit_take_rate_prior_pct"))
        details["gross_profit_to_tpv_pct"] = _round(take_rate)
        details["gross_profit_to_tpv_prior_pct"] = _round(prior_take_rate)
        if take_rate is not None and prior_take_rate is not None and take_rate < prior_take_rate:
            warnings.append("gross-profit take rate declined versus the comparison period")
    elif profile_type == "auto_dealership":
        adjusted = _number(kpis.get("adjusted_net_debt_to_ebitda"))
        details["adjusted_net_debt_to_ebitda"] = _round(adjusted)
        details["floorplan_debt_excluded"] = kpis.get("floorplan_debt_excluded") is True
        if (
            adjusted is None
            or kpis.get("floorplan_debt_excluded") is not True
            or not sector_sources_ok
        ):
            if strict:
                review.append(
                    "auto dealership requires sourced leverage adjusted for floorplan debt"
                )
        elif adjusted > 2.5:
            warnings.append(f"sector-adjusted net debt/EBITDA is elevated at {adjusted:.2f}x")
            penalty = max(penalty, 2)
    return details, warnings, review, penalty


def _calculate_score_components(
    candidate: Mapping[str, Any],
) -> tuple[float, dict[str, float | None], list[str]]:
    supplied = _mapping(candidate.get("score_components"))
    normalized: dict[str, float | None] = {}
    warnings: list[str] = []
    total = 0.0
    for key, maximum in SCORE_LIMITS.items():
        value = _number(supplied.get(key))
        if value is None:
            normalized[key] = None
            warnings.append(f"score component {key} is missing")
            continue
        if value < 0 or value > maximum:
            normalized[key] = None
            warnings.append(f"score component {key} must be between 0 and {maximum:g}")
            continue
        normalized[key] = _round(value, 2)
        total += value
    return total, normalized, warnings


def _calculate_data_quality(
    candidate: Mapping[str, Any],
    source_index: Mapping[str, Mapping[str, Any]],
    price_source_id: str | None,
    valuation: Mapping[str, Any],
    financial_metrics: Mapping[str, Any],
    sector_profile: Mapping[str, Any],
    cyclicality_score: int | None,
    corporate_action: Mapping[str, Any],
    contract: Mapping[str, Any],
) -> tuple[int, dict[str, dict[str, Any]], list[str]]:
    latest = _mapping(candidate.get("latest_earnings"))
    financials = _mapping(candidate.get("financials"))
    histories = _mapping(financials.get("histories"))
    warnings: list[str] = []
    details: dict[str, dict[str, Any]] = {}

    def award(key: str, evidence_ok: bool, reason: str, evidence: Any = None) -> None:
        details[key] = {
            "evidence_ok": evidence_ok,
            "awarded": evidence_ok,
            "weight": QUALITY_WEIGHTS[key],
            "reason": reason,
            "evidence": evidence,
        }

    quote_ids = _candidate_source_ids(
        candidate, "identity.price", [price_source_id] if price_source_id else []
    )
    quote_ok = _sources_resolve(quote_ids, source_index)
    award("quote_verified", quote_ok, "price evidence resolves in source ledger", quote_ids)

    latest_ids = _candidate_source_ids(candidate, "latest_earnings", latest.get("source_ids"))
    latest_ok = (
        contract.get("latest_earnings_valid") is True
        and _sources_resolve(latest_ids, source_index)
        and _has_tier(latest_ids, source_index, {1, 2})
    )
    award(
        "latest_earnings_verified",
        latest_ok,
        "latest quarter/full-year records are separated and sourced",
        latest_ids,
    )

    core_fields = [
        "financials.revenue_ttm",
        "financials.cash_flow_ttm",
        "financials.sbc_ttm",
        "financials.total_debt",
        "financials.cash_classification",
        "financials.histories.diluted_shares",
    ]
    core_checks = {
        field: _has_tier(_candidate_source_ids(candidate, field), source_index, {1, 2})
        for field in core_fields
    }
    cash_flow_source_ok = (
        _mapping(financial_metrics.get("cash_flow_ttm")).get("source_evidence_ok") is True
    )
    core_checks["cash_flow_period_sources"] = cash_flow_source_ok
    award(
        "sec_financials_verified",
        all(core_checks.values()),
        "core financial fields and TTM cash-flow periods have primary-source evidence",
        core_checks,
    )

    period_rows = _mapping(valuation.get("periods"))
    estimate_checks: dict[str, bool] = {}
    for key in ("current", "year_2", "year_3"):
        row = _mapping(period_rows.get(key))
        if _number(row.get("metric")) is None:
            continue
        estimate_checks[key] = (
            (_text(row.get("source_type")) or "") in ALLOWED_SOURCE_TYPES
            and bool(_text(row.get("retrieved_at")))
            and _sources_resolve(_list(row.get("source_ids")), source_index)
        )
    award(
        "guidance_consensus_labeled",
        bool(estimate_checks) and all(estimate_checks.values()),
        "each valuation period is classified, dated, and sourced",
        estimate_checks,
    )

    award(
        "forecast_bridge_verified",
        valuation.get("forecast_bridge_valid") is True,
        "year-2/year-3 forecast arithmetic and source evidence pass",
        valuation.get("forecast_bridge_details"),
    )
    diluted_ids = _candidate_source_ids(candidate, "financials.histories.diluted_shares")
    award(
        "diluted_shares_verified",
        len(_list(histories.get("diluted_shares"))) >= 2
        and _has_tier(diluted_ids, source_index, {1, 2}),
        "diluted-share history has primary-source evidence",
        diluted_ids,
    )
    sbc_ids = _candidate_source_ids(candidate, "financials.sbc_ttm")
    award(
        "sbc_verified",
        _number(financials.get("sbc_ttm")) is not None and _has_tier(sbc_ids, source_index, {1, 2}),
        "TTM SBC has primary-source evidence",
        sbc_ids,
    )

    peers_ok = valuation.get("peer_set_basis_valid") is True
    award(
        "peer_set_verified",
        peers_ok,
        "three or more genuine peers have reasons, consistent forward basis, and sources",
        valuation.get("calculated_peer_median_multiple"),
    )
    award(
        "gaap_non_gaap_reconciled",
        valuation.get("gaap_reconciliation_valid") is True,
        "all non-GAAP/normalized periods reconcile to GAAP",
        valuation.get("gaap_reconciliation_details"),
    )
    corporate_ok = (
        corporate_action.get("evidence_ok") is True
        and corporate_action.get("listing_status") == "active"
        and corporate_action.get("mna_status") in {"none", "terminated"}
        and corporate_action.get("symbol_active") is True
    )
    award(
        "corporate_actions_verified",
        corporate_ok,
        "fresh listing/M&A preflight has resolving evidence",
        corporate_action.get("source_ids"),
    )

    cyclicality = _mapping(candidate.get("cyclicality"))
    peak_profit = cyclicality.get("peak_profit_risk") is True
    cycle_required = peak_profit or not (cyclicality_score is not None and cyclicality_score <= 2)
    if not cycle_required:
        cycle_ok = True
        cycle_evidence: Any = "not required for low cyclicality without peak-profit risk"
    else:
        normalization = _mapping(cyclicality.get("normalization"))
        normalization_ids = [_text(value) for value in _list(normalization.get("source_ids"))]
        cycle_ok = (
            _number(normalization.get("normalized_metric")) is not None
            and bool(_text(normalization.get("method")))
            and _sources_resolve(normalization_ids, source_index)
        )
        cycle_evidence = normalization
    award(
        "cyclical_normalization_verified",
        cycle_ok,
        "mid-cycle normalization is evidenced whenever cyclicality or peak-profit risk requires it",
        cycle_evidence,
    )

    cash = _mapping(financials.get("cash_classification"))
    cash_ids = _candidate_source_ids(candidate, "financials.cash_classification")
    profile_type = (_text(sector_profile.get("type")) or "general").lower()
    cash_ok = _number(cash.get("corporate_cash")) is not None and _has_tier(
        cash_ids, source_index, {1, 2}
    )
    if profile_type == "payments":
        cash_ok = cash_ok and _number(cash.get("customer_or_settlement_funds")) is not None
    award(
        "cash_classification_verified",
        cash_ok,
        "corporate cash is source-backed and separated from restricted/customer funds where applicable",
        cash_ids,
    )

    roic_ids = _candidate_source_ids(candidate, "financials.roic_pct")
    ebitda_ids = _candidate_source_ids(candidate, "financials.ebitda_ttm")
    roic_ok = _number(financials.get("roic_pct")) is not None and _has_tier(
        roic_ids, source_index, {1, 2, 4}
    )
    ebitda_ok = _number(financials.get("ebitda_ttm")) is not None and _has_tier(
        ebitda_ids, source_index, {1, 2, 4}
    )
    award(
        "roic_ebitda_evidence_verified",
        roic_ok and ebitda_ok,
        "ROIC and EBITDA are calculated or reported with resolving evidence",
        {"roic": roic_ids, "ebitda": ebitda_ids},
    )

    sector_required = profile_type in {"commercial_biopharma", "payments", "auto_dealership"}
    if not sector_required:
        sector_ok = True
        sector_evidence: Any = "not required for general profile"
    elif profile_type == "commercial_biopharma":
        sector_ok = (
            sector_profile.get("source_evidence_ok") is True
            and _number(sector_profile.get("top_product_revenue_pct")) is not None
            and bool(_text(sector_profile.get("nearest_material_loe_date")))
            and bool(_list(sector_profile.get("loe_stress_scenarios")))
        )
        sector_evidence = sector_profile
    elif profile_type == "payments":
        sector_ok = sector_profile.get("source_evidence_ok") is True and cash_ok
        sector_evidence = sector_profile
    else:
        sector_ok = (
            sector_profile.get("source_evidence_ok") is True
            and sector_profile.get("floorplan_debt_excluded") is True
        )
        sector_evidence = sector_profile
    award(
        "sector_risk_verified",
        sector_ok,
        "material sector-specific risks and stress cases are source-backed",
        sector_evidence,
    )

    raw_score = sum(detail["weight"] for detail in details.values() if detail["awarded"])
    caps = [
        _integer(item.get("cap"))
        for item in _list(contract.get("quality_caps"))
        if _integer(item.get("cap")) is not None
    ]
    intrinsic_caps: list[dict[str, Any]] = []
    for key, cap, reason in (
        ("forecast_bridge_verified", 60, "forecast bridge is not independently driver-derived"),
        ("sec_financials_verified", 65, "core financial or TTM cash-flow evidence is incomplete"),
        ("cash_classification_verified", 70, "corporate cash classification is incomplete"),
        ("cyclical_normalization_verified", 65, "required mid-cycle normalization is missing"),
        ("sector_risk_verified", 65, "required sector-specific risk/LOE stress is missing"),
        ("roic_ebitda_evidence_verified", 65, "ROIC/EBITDA evidence is incomplete"),
    ):
        if details.get(key, {}).get("evidence_ok") is not True:
            caps.append(cap)
            intrinsic_caps.append({"cap": cap, "reason": reason})
    applied_cap = min(caps) if caps else 100
    score = min(raw_score, applied_cap)
    details["_quality_cap"] = {
        "evidence_ok": applied_cap == 100,
        "awarded": True,
        "weight": 0,
        "reason": "quality score is capped by global and candidate contract failures",
        "evidence": deepcopy(_list(contract.get("quality_caps"))) + intrinsic_caps,
        "raw_score": raw_score,
        "applied_cap": applied_cap,
    }
    for key, detail in details.items():
        if key != "_quality_cap" and not detail["evidence_ok"]:
            warnings.append(f"data-quality item failed: {key}")
    if applied_cap < raw_score:
        warnings.append(f"data-quality score capped at {applied_cap} from raw {raw_score}")
    return int(score), details, warnings


def _highest_scenario_upside(valuation: Mapping[str, Any], scenario_key: str) -> float | None:
    scenario = _mapping(valuation.get(scenario_key))
    rankable = _mapping(valuation.get("rankable_horizons"))
    values = [
        _number(_mapping(scenario.get(key)).get("upside_pct"))
        for key in ("year_2", "year_3")
        if rankable.get(key) is True
    ]
    valid = [value for value in values if value is not None]
    return max(valid) if valid else None


def _preferred_three_year_upside(valuation: Mapping[str, Any], scenario_key: str) -> float | None:
    scenario = _mapping(valuation.get(scenario_key))
    rankable = _mapping(valuation.get("rankable_horizons"))
    if rankable.get("year_3") is True:
        value = _number(_mapping(scenario.get("year_3")).get("upside_pct"))
        if value is not None:
            return value
    if rankable.get("year_2") is True:
        return _number(_mapping(scenario.get("year_2")).get("upside_pct"))
    return None


def _estimate_range_scenarios(
    valuation: Mapping[str, Any],
    *,
    price: float | None,
) -> dict[str, dict[str, Any]]:
    """Calculate low/high consensus scenarios using the same current multiple.

    The base scenario can overstate robustness when analyst ranges are wide.
    These scenarios are not alternative forecasts; they are deterministic
    sensitivity checks using reported consensus bounds.
    """
    current_multiple = _number(valuation.get("current_multiple"))
    periods = _mapping(valuation.get("periods"))
    output: dict[str, dict[str, Any]] = {}
    for key in ("year_2", "year_3"):
        row = _mapping(periods.get(key))
        years = _number(row.get("years"))
        low = _number(row.get("estimate_low"))
        high = _number(row.get("estimate_high"))
        output[key] = {
            "low": _scenario(low, current_multiple, price, years)
            if low is not None and low > 0
            else None,
            "high": _scenario(high, current_multiple, price, years)
            if high is not None and high > 0
            else None,
        }
    return output


def _best_low_case_upside(valuation: Mapping[str, Any]) -> float | None:
    rankable = _mapping(valuation.get("rankable_horizons"))
    ranges = _mapping(valuation.get("estimate_range_scenarios"))
    values: list[float] = []
    for key in ("year_2", "year_3"):
        if rankable.get(key) is not True:
            continue
        value = _number(_mapping(_mapping(ranges.get(key)).get("low")).get("upside_pct"))
        if value is not None:
            values.append(value)
    return max(values) if values else None


def _quality_eligibility_gate(
    *,
    financial_metrics: Mapping[str, Any],
    valuation: Mapping[str, Any],
    sector_profile: Mapping[str, Any],
    final_score: float,
    config: Mapping[str, Any],
) -> tuple[list[str], list[str]]:
    """Return (ordinary failures, severe failures) for formal eligibility.

    The screen may surface low-P/E transition stories, but a final ranked name
    must also show credible cash-flow support, acceptable capital efficiency,
    and downside resilience.  Failing this gate routes the name to conditional
    or review-required rather than presenting a weak candidate as a formal win.
    """
    failures: list[str] = []
    severe: list[str] = []
    if final_score < float(config.get("minimum_final_score_for_eligible", 70.0)):
        failures.append("final_score_below_eligible_floor")

    adj_yield = _number(financial_metrics.get("sbc_adjusted_fcf_yield_pct"))
    ev_to_fcf = _number(financial_metrics.get("ev_to_fcf"))
    min_adj_yield = float(config.get("minimum_sbc_adjusted_fcf_yield_pct_for_eligible", 3.0))
    max_ev_fcf = float(config.get("maximum_ev_to_fcf_for_eligible", 30.0))
    cashflow_supported = (adj_yield is not None and adj_yield >= min_adj_yield) or (
        ev_to_fcf is not None and ev_to_fcf <= max_ev_fcf
    )
    if not cashflow_supported:
        failures.append("valuation_not_supported_by_sbc_adjusted_fcf")
        if (adj_yield is not None and adj_yield < 1.0) or (
            ev_to_fcf is not None and ev_to_fcf > 50.0
        ):
            severe.append("severely_weak_fcf_support")

    roic = _number(financial_metrics.get("roic_pct"))
    if roic is None or roic < float(config.get("minimum_roic_pct_for_eligible", 8.0)):
        failures.append("roic_below_eligible_floor")

    leverage = _number(financial_metrics.get("net_debt_to_ebitda"))
    if leverage is not None and leverage > float(
        config.get("maximum_net_debt_to_ebitda_for_eligible", 3.0)
    ):
        failures.append("leverage_above_eligible_floor")

    dilution = _number(financial_metrics.get("diluted_share_cagr_pct"))
    if dilution is not None and dilution > float(
        config.get("maximum_dilution_pct_for_eligible", 5.0)
    ):
        failures.append("dilution_above_eligible_floor")

    low_case = _best_low_case_upside(valuation)
    min_low = float(config.get("minimum_low_case_upside_pct_for_eligible", 15.0))
    if low_case is None or low_case < min_low:
        failures.append("consensus_low_case_upside_below_eligible_floor")

    loe_scenarios = _list(sector_profile.get("loe_stress_scenarios"))
    loe_downsides = [
        _number(_mapping(row).get("upside_pct"))
        for row in loe_scenarios
        if _number(_mapping(row).get("upside_pct")) is not None
    ]
    if loe_downsides and min(loe_downsides) < float(
        config.get("severe_loe_stress_downside_pct", -25.0)
    ):
        failures.append("material_loe_tail_risk")
        severe.append("material_loe_tail_risk")

    return list(dict.fromkeys(failures)), list(dict.fromkeys(severe))


def _screened_out_result(candidate: Mapping[str, Any]) -> dict[str, Any]:
    identity = _mapping(candidate.get("identity"))
    decision = _mapping(candidate.get("screening_decision"))
    reasons = [str(value) for value in _list(decision.get("reasons")) if str(value).strip()]
    return {
        "symbol": _text(identity.get("symbol")) or "UNKNOWN",
        "company_name": _text(identity.get("company_name")) or "Unknown company",
        "status": "screened_out",
        "screening_reasons": reasons or ["broad-screen economics did not qualify"],
        "identity": deepcopy(identity),
        "sources": deepcopy(_list(candidate.get("sources"))),
    }


def evaluate_candidate(
    candidate: Mapping[str, Any],
    *,
    config: Mapping[str, Any],
    analysis_as_of: datetime,
    price_basis: Mapping[str, Any],
    strict: bool,
) -> dict[str, Any]:
    identity = _mapping(candidate.get("identity"))
    symbol = _text(identity.get("symbol")) or "UNKNOWN"
    company_name = _text(identity.get("company_name")) or "Unknown company"
    screening = _mapping(candidate.get("screening_decision"))
    screening_status = (_text(screening.get("status")) or "passed").lower()
    if screening_status == "screened_out":
        return _screened_out_result(candidate)

    contract = _mapping(candidate.get("_contract"))
    hard: list[str] = []
    review: list[str] = list(_list(contract.get("review_reasons")))
    warnings: list[str] = list(_list(contract.get("warnings")))
    unresolved: list[str] = []

    if screening_status not in ALLOWED_SCREENING_STATUSES:
        review.append(f"invalid screening_decision.status: {screening_status!r}")
    elif screening_status == "exception_admitted":
        warnings.append("candidate was admitted as an explicit broad-screen exception")
    elif screening_status == "near_miss_review":
        warnings.append("candidate advanced from the broad-screen near-miss review lane")
    elif screening_status == "sector_review_required":
        warnings.append("candidate advanced with mandatory sector/cycle deep-dive requirements")

    exchange = (_text(identity.get("exchange")) or "").upper()
    if exchange not in ALLOWED_EXCHANGES:
        hard.append(f"exchange {exchange!r} is outside NYSE/Nasdaq/NYSE American")
    special_case = (_text(identity.get("special_case")) or "none").lower()
    if special_case != "none" and not bool(config.get("allow_special_cases", True)):
        hard.append(f"special-case sector {special_case!r} is disabled by configuration")

    price = _number(identity.get("price"))
    market_cap = _number(identity.get("market_cap"))
    adv = _number(identity.get("average_daily_dollar_volume"))
    if price is None or price <= 0:
        hard.append("price must be positive")
    if market_cap is None or market_cap <= 0:
        hard.append("market cap must be positive")
    min_price = _number(config.get("min_price")) or 5.0
    if price is not None and price < min_price:
        hard.append(f"price {price:.2f} is below configured minimum {min_price:.2f}")
    hard_liquidity = _number(config.get("hard_min_average_daily_dollar_volume")) or 1_000_000
    liquidity_penalty = 0
    if adv is None:
        review.append("average daily dollar volume is not verified")
        liquidity_penalty = 2
    elif adv < hard_liquidity:
        hard.append(
            f"average daily dollar volume {adv:.0f} is below hard minimum {hard_liquidity:.0f}"
        )
    elif adv < (_number(config.get("min_average_daily_dollar_volume")) or 5_000_000):
        warnings.append("liquidity is below the preferred threshold")
        liquidity_penalty = 2

    min_cap = _number(config.get("min_market_cap")) or 500_000_000
    max_cap = _number(config.get("max_market_cap")) or 20_000_000_000
    if market_cap is not None and not (min_cap <= market_cap <= max_cap):
        exception_reason = _text(screening.get("exception_reason"))
        if not exception_reason:
            review.append(
                "market cap is outside the focus range without an explicit exception reason"
            )
        else:
            warnings.append(f"market-cap exception: {exception_reason}")

    flags = _mapping(candidate.get("flags"))
    for key, label in HARD_FLAG_LABELS.items():
        if flags.get(key) is True:
            hard.append(label)

    source_index = _source_index(candidate)
    if not _has_primary_source(source_index):
        review.append("no Tier 1 or Tier 2 primary source is present")

    corporate_action, corp_warnings, corp_review, corp_hard = _validate_corporate_action(
        candidate, source_index, analysis_as_of, config
    )
    warnings.extend(corp_warnings)
    review.extend(corp_review)
    hard.extend(corp_hard)

    price_as_of = None
    try:
        price_as_of = parse_iso8601(price_basis.get("as_of"), "price_basis.as_of", required=True)
    except InputError as exc:
        review.append(str(exc))
    session = (_text(price_basis.get("session")) or "").lower()
    if session not in ALLOWED_SESSIONS:
        review.append("price_basis.session is missing or invalid")
    if price_as_of is not None:
        quote_age_days = (analysis_as_of - price_as_of).total_seconds() / 86_400
        max_quote_age = _number(config.get("max_quote_age_days")) or 7.0
        if quote_age_days > max_quote_age:
            message = f"price snapshot is stale ({quote_age_days:.1f} days old; maximum {max_quote_age:.0f})"
            warnings.append(message)
            if strict:
                review.append(message)
        if quote_age_days < -1:
            review.append("price snapshot timestamp is after analysis_as_of")

    latest = _mapping(candidate.get("latest_earnings"))
    latest_records = _mapping(candidate.get("latest_earnings_records"))
    latest_published = None
    if _text(contract.get("latest_published_at")):
        try:
            latest_published = parse_iso8601(
                contract.get("latest_published_at"), "latest_published_at"
            )
        except InputError as exc:
            review.append(str(exc))
    if latest_published and price_as_of and latest_published > price_as_of:
        message = "price snapshot predates the latest earnings release"
        warnings.append(message)
        if strict:
            review.append(message)
    material_event = (
        parse_iso8601(
            corporate_action.get("latest_material_event_at"),
            "corporate_action_check.latest_material_event_at",
        )
        if _text(corporate_action.get("latest_material_event_at"))
        else None
    )
    if material_event and price_as_of and material_event > price_as_of:
        message = "price snapshot predates a material corporate action"
        warnings.append(message)
        if strict:
            review.append(message)

    financial_metrics, fin_warnings, fin_review, fin_unresolved = _calculate_financial_metrics(
        candidate, config, source_index
    )
    warnings.extend(fin_warnings)
    if strict:
        review.extend(fin_review)
    unresolved.extend(fin_unresolved)

    valuation, val_warnings, val_review, val_hard = _calculate_valuation(
        candidate, config, analysis_as_of, source_index
    )
    valuation["estimate_range_scenarios"] = _estimate_range_scenarios(valuation, price=price)
    warnings.extend(val_warnings)
    if strict:
        review.extend(val_review)
    hard.extend(val_hard)

    cyclicality = _mapping(candidate.get("cyclicality"))
    cyclicality_score = _integer(cyclicality.get("score"))
    if cyclicality_score not in {1, 2, 3, 4, 5}:
        review.append("cyclicality score must be an integer from 1 to 5")
        cyclicality_score = None
    max_without_normalization = (
        _integer(config.get("maximum_cyclicality_without_normalization")) or 2
    )
    normalization_required = (
        cyclicality.get("normalization_required") is True
        or cyclicality.get("peak_profit_risk") is True
        or (cyclicality_score is not None and cyclicality_score > max_without_normalization)
    )
    normalization = _mapping(cyclicality.get("normalization"))
    normalization_valid = not normalization_required or (
        _number(normalization.get("normalized_metric")) is not None
        and bool(_text(normalization.get("method")))
        and _sources_resolve(_list(normalization.get("source_ids")), source_index)
    )
    if strict and normalization_required and not normalization_valid:
        review.append("cyclical normalization is required but not evidenced")

    sector_profile, sector_warnings, sector_review, sector_penalty = _validate_sector_profile(
        candidate, financial_metrics, valuation, analysis_as_of, source_index, config, strict
    )
    warnings.extend(sector_warnings)
    review.extend(sector_review)

    price_source_id = _text(identity.get("price_source_id")) or _text(price_basis.get("source_id"))
    quality_score, quality_details, quality_warnings = _calculate_data_quality(
        candidate,
        source_index,
        price_source_id,
        valuation,
        financial_metrics,
        sector_profile,
        cyclicality_score,
        corporate_action,
        contract,
    )
    warnings.extend(quality_warnings)
    minimum_quality = _integer(config.get("minimum_data_quality_score")) or 70
    if quality_score < minimum_quality:
        review.append(
            f"data-quality score {quality_score} is below configured minimum {minimum_quality}"
        )

    score_total, score_components, score_warnings = _calculate_score_components(candidate)
    warnings.extend(score_warnings)
    if score_warnings and strict:
        review.append("one or more raw score components are missing or invalid")

    best_constant = _highest_scenario_upside(valuation, "constant_multiple")
    best_stress = _highest_scenario_upside(valuation, "multiple_contraction")
    min_upside = _number(config.get("minimum_constant_multiple_upside_pct")) or 30.0
    if bool(config.get("require_minimum_upside", True)) and (
        best_constant is None or best_constant < min_upside
    ):
        review.append(
            f"rankable forward constant-multiple upside does not reach configured minimum {min_upside:.1f}%"
        )
    min_stress = _number(config.get("minimum_stressed_upside_pct")) or 0.0
    if bool(config.get("require_positive_stress_case", False)) and (
        best_stress is None or best_stress < min_stress
    ):
        review.append(
            f"multiple-contraction stress upside does not reach configured minimum {min_stress:.1f}%"
        )

    minimum_analyst_count = _integer(valuation.get("minimum_analyst_count"))
    max_dispersion = _number(valuation.get("maximum_estimate_dispersion_pct"))
    penalties = {
        "data_quality": _data_quality_penalty(quality_score),
        "cyclicality": _cyclicality_penalty(cyclicality_score),
        "estimate_breadth": _estimate_breadth_penalty(minimum_analyst_count),
        "estimate_dispersion": _estimate_dispersion_penalty(max_dispersion),
        "sbc": _sbc_penalty(_number(financial_metrics.get("sbc_revenue_pct"))),
        "dilution": _dilution_penalty(_number(financial_metrics.get("diluted_share_cagr_pct"))),
        "liquidity": liquidity_penalty,
        "sector_specific_risk": sector_penalty,
    }
    total_penalty = sum(penalties.values())
    final_score = max(0.0, min(100.0, score_total - total_penalty))

    quality_gate_failures, severe_quality_gate_failures = _quality_eligibility_gate(
        financial_metrics=financial_metrics,
        valuation=valuation,
        sector_profile=sector_profile,
        final_score=final_score,
        config=config,
    )

    hard = list(dict.fromkeys(hard))
    review = [reason for reason in dict.fromkeys(review) if reason not in hard]
    warnings = list(dict.fromkeys(warnings))
    unresolved = list(dict.fromkeys(unresolved))
    if hard:
        status = "excluded"
    elif review:
        status = "review_required"
    elif severe_quality_gate_failures:
        status = "review_required"
        review.extend(severe_quality_gate_failures)
    elif quality_gate_failures:
        maximum_conditional = int(config.get("maximum_quality_gate_failures_for_conditional", 2))
        if len(quality_gate_failures) <= maximum_conditional:
            status = "conditional"
        else:
            status = "review_required"
            review.extend(quality_gate_failures)
    else:
        status = "eligible"

    if status == "eligible" and quality_score >= 85 and (minimum_analyst_count or 0) >= 5:
        confidence = "high"
    elif status == "eligible":
        confidence = "medium"
    elif status == "conditional":
        confidence = "low"
    elif status == "review_required":
        confidence = "low"
    else:
        confidence = "not_ranked"

    return {
        "symbol": symbol,
        "company_name": company_name,
        "status": status,
        "status_reasons": hard
        if status == "excluded"
        else review
        if status == "review_required"
        else quality_gate_failures
        if status == "conditional"
        else [],
        "hard_exclusion_reasons": hard,
        "review_reasons": review,
        "conditional_reasons": quality_gate_failures,
        "quality_gate_failures": quality_gate_failures,
        "severe_quality_gate_failures": severe_quality_gate_failures,
        "warnings": warnings,
        "unresolved_fields": unresolved,
        "confidence": confidence,
        "identity": deepcopy(identity),
        "screening_decision": deepcopy(screening),
        "corporate_action_check": corporate_action,
        "latest_earnings": deepcopy(latest),
        "latest_earnings_records": deepcopy(latest_records),
        "financial_metrics": financial_metrics,
        "valuation": valuation,
        "cash_consistency": deepcopy(_mapping(contract.get("cash_consistency"))),
        "cyclicality": {
            "score": cyclicality_score,
            "position": _text(cyclicality.get("position")),
            "peak_profit_risk": cyclicality.get("peak_profit_risk") is True,
            "normalization_required": normalization_required,
            "normalization_valid": normalization_valid,
            "normalization": deepcopy(normalization),
        },
        "sector_profile": sector_profile,
        "data_quality_score": quality_score,
        "data_quality_details": quality_details,
        "raw_score": _round(score_total, 2),
        "score_components": score_components,
        "penalties": penalties,
        "total_penalty": total_penalty,
        "final_score": _round(final_score, 2),
        "qualitative": deepcopy(_mapping(candidate.get("qualitative"))),
        "peers": deepcopy(_list(candidate.get("peers"))),
        "sources": deepcopy(_list(candidate.get("sources"))),
        "contract": deepcopy(contract),
    }


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


def _label(language: str, en: str, ja: str) -> str:
    return ja if language == "ja" else en


def _missing(language: str) -> str:
    return "確認できず" if language == "ja" else "not verified"


def _md_escape(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ") if value is not None else ""


def _scenario_value(result: Mapping[str, Any], scenario: str, horizon: str, key: str) -> Any:
    return _mapping(_mapping(_mapping(result.get("valuation")).get(scenario)).get(horizon)).get(key)


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


def _render_list(values: Any, missing: str) -> str:
    rows = [str(value).strip() for value in _list(values) if str(value).strip()]
    return "; ".join(rows) if rows else missing


def _render_latest_earnings(language: str, records: Mapping[str, Any], missing: str) -> list[str]:
    lines: list[str] = []
    for key, en, ja in (
        ("quarter", "Latest quarter", "直近四半期"),
        ("full_year", "Latest full year", "直近通期"),
    ):
        record = _mapping(records.get(key))
        if not record:
            continue
        metrics = _mapping(record.get("metrics"))
        lines.append(f"**{_label(language, en, ja)} — {record.get('period', missing)}**")
        lines.extend(
            [
                f"- **{_label(language, 'Period end / published', '期末／発表日時')}:** {record.get('period_end', missing)} / {record.get('published_at', missing)}",
                f"- **{_label(language, 'Revenue / YoY', '売上高／前年比')}:** {_format_number(metrics.get('revenue'), 1, missing)} / {_format_pct(metrics.get('revenue_yoy_pct'), 1, missing)}",
                f"- **{_label(language, 'GAAP operating income / margin', 'GAAP営業利益／利益率')}:** {_format_number(metrics.get('gaap_operating_income'), 1, missing)} / {_format_pct(metrics.get('gaap_operating_margin_pct'), 1, missing)}",
                f"- **GAAP / Adjusted EPS:** {_format_number(metrics.get('gaap_eps'), 2, missing)} / {_format_number(metrics.get('adjusted_eps'), 2, missing)}",
                f"- **{_label(language, 'OCF / standard FCF', '営業CF／標準FCF')}:** {_format_number(metrics.get('operating_cash_flow'), 1, missing)} / {_format_number(metrics.get('standard_fcf'), 1, missing)}",
                f"- **{_label(language, 'Growth state', '成長状態')}:** {record.get('growth_state') or record.get('derived_growth_state') or missing}",
                f"- **{_label(language, 'Guidance', 'ガイダンス')}:** {_render_list(record.get('guidance'), missing)}",
                f"- **KPI:** {_render_list(record.get('key_kpis'), missing)}",
                f"- **{_label(language, 'One-time items', '一時項目')}:** {_render_list(record.get('one_time_items'), missing)}",
            ]
        )
    return lines or [missing]


def _render_peers(language: str, peers: Sequence[Any], missing: str) -> list[str]:
    lines = [
        "| Ticker | Company | Multiple | Basis | Period | Selection reason |",
        "|---|---|---:|---|---|---|",
    ]
    if not peers:
        lines.append(f"| {missing} | {missing} | {missing} | {missing} | {missing} | {missing} |")
        return lines
    for item in peers:
        peer = _mapping(item)
        lines.append(
            "| {symbol} | {company} | {multiple} | {basis} | {period} | {reason} |".format(
                symbol=_md_escape(peer.get("symbol", missing)),
                company=_md_escape(peer.get("company_name", missing)),
                multiple=_format_number(peer.get("multiple"), 2, missing),
                basis=_md_escape(peer.get("metric_basis", missing)),
                period=_md_escape(peer.get("multiple_period_kind", missing)),
                reason=_md_escape(peer.get("selection_reason", missing)),
            )
        )
    return lines


def _render_score_table(row: Mapping[str, Any], missing: str) -> list[str]:
    components = _mapping(row.get("score_components"))
    penalties = _mapping(row.get("penalties"))
    lines = ["| Component | Score | Maximum |", "|---|---:|---:|"]
    for key, maximum in SCORE_LIMITS.items():
        lines.append(f"| {key} | {_format_number(components.get(key), 1, missing)} | {maximum:g} |")
    lines.append(f"| Raw score | {_format_number(row.get('raw_score'), 1, missing)} | 100 |")
    lines.append(f"| Penalties | -{_format_number(row.get('total_penalty'), 1, missing)} | — |")
    lines.append(f"| Final score | {_format_number(row.get('final_score'), 1, missing)} | 100 |")
    lines.append("")
    lines.append(
        "**Penalty breakdown:** " + ", ".join(f"{key}={value}" for key, value in penalties.items())
    )
    return lines


def _render_candidate_detail(language: str, row: Mapping[str, Any]) -> list[str]:
    missing = _missing(language)
    identity = _mapping(row.get("identity"))
    metrics = _mapping(row.get("financial_metrics"))
    cash_flow = _mapping(metrics.get("cash_flow_ttm"))
    valuation = _mapping(row.get("valuation"))
    periods = _mapping(valuation.get("periods"))
    qualitative = _mapping(row.get("qualitative"))
    latest_records = _mapping(row.get("latest_earnings_records"))
    cyclicality = _mapping(row.get("cyclicality"))
    lines: list[str] = []

    lines.append(f"### {row.get('rank')}. {row.get('company_name')} ({row.get('symbol')})")
    lines.append("")
    lines.append(f"#### 1. {_label(language, 'Basic Information', '基本情報')}")
    lines.extend(
        [
            f"- **{_label(language, 'Exchange / sector / industry', '取引所／セクター／業種')}:** {identity.get('exchange', missing)} / {identity.get('sector', missing)} / {identity.get('industry', missing)}",
            f"- **{_label(language, 'Price / market cap', '株価／時価総額')}:** {_format_price(identity.get('price'), identity.get('currency', 'USD'), missing)} / {_format_number(identity.get('market_cap'), 1, missing)}",
            f"- **{_label(language, 'Liquidity', '流動性')}:** {_format_number(identity.get('average_daily_dollar_volume'), 1, missing)}",
            f"- **{_label(language, 'Business overview', '企業概要')}:** {qualitative.get('business_overview', missing)}",
        ]
    )
    lines.append("")
    lines.append(f"#### 2. {_label(language, 'Investment Thesis', '投資仮説')}")
    lines.append(str(qualitative.get("investment_thesis") or missing))
    lines.append("")
    lines.append(f"#### 3. {_label(language, 'Valuation', 'バリュエーション')}")
    lines.extend(
        [
            f"- **{_label(language, 'Valuation basis', '評価基準')}:** {valuation.get('basis', missing)} / {valuation.get('current_metric_basis', missing)} / {valuation.get('current_period_kind', missing)}",
            f"- **{_label(language, 'Current metric / multiple', '現在指標／倍率')}:** {_format_number(valuation.get('current_metric'), 2, missing)} / {_format_number(valuation.get('current_multiple'), 2, missing)}x",
            f"- **{_label(language, 'Peer median multiple', '同業中央値倍率')}:** {_format_number(valuation.get('peer_median_multiple'), 2, missing)}x",
            f"- **{_label(language, 'EV/FCF', 'EV/FCF')}:** {_format_number(metrics.get('ev_to_fcf'), 2, missing)}x",
            f"- **{_label(language, 'Enterprise value / cash definition', '企業価値／現金定義')}:** {_format_number(metrics.get('enterprise_value'), 1, missing)} / {metrics.get('cash_definition', missing)}",
            f"- **{_label(language, 'Standard / SBC-adjusted FCF yield', '標準／SBC調整後FCF利回り')}:** {_format_pct(metrics.get('fcf_yield_pct'), 1, missing)} / {_format_pct(metrics.get('sbc_adjusted_fcf_yield_pct'), 1, missing)}",
        ]
    )
    lines.append("")
    lines.append(f"#### 4. {_label(language, 'Growth History and Forecasts', '成長実績と予想')}")
    lines.extend(
        [
            f"- **{_label(language, 'Revenue CAGR', '売上CAGR')}:** {_format_pct(metrics.get('revenue_cagr_pct'), 1, missing)}",
            f"- **{_label(language, 'GAAP EPS CAGR', 'GAAP EPS CAGR')}:** {_format_pct(metrics.get('gaap_eps_cagr_pct'), 1, missing)}",
            f"- **{_label(language, 'FCF/share CAGR', 'FCF per share CAGR')}:** {_format_pct(metrics.get('fcf_per_share_cagr_pct'), 1, missing)}",
            f"- **{_label(language, 'Current / year-2 / year-3 metric', '現在／2年後／3年後指標')}:** {_format_number(_mapping(periods.get('current')).get('metric'), 2, missing)} / {_format_number(_mapping(periods.get('year_2')).get('metric'), 2, missing)} / {_format_number(_mapping(periods.get('year_3')).get('metric'), 2, missing)}",
            f"- **{_label(language, 'Forecast bridge', '予想ブリッジ')}:** {'PASS' if valuation.get('forecast_bridge_valid') else 'FAIL'}",
        ]
    )
    lines.append("")
    lines.append(f"#### 5. {_label(language, 'Latest Earnings', '直近決算')}")
    lines.extend(_render_latest_earnings(language, latest_records, missing))
    lines.append("")
    lines.append(f"#### 6. {_label(language, 'Growth Drivers', '成長ドライバー')}")
    lines.append(_render_list(qualitative.get("growth_drivers"), missing))
    lines.append("")
    lines.append(f"#### 7. {_label(language, 'Peer Comparison', '同業他社比較')}")
    lines.extend(_render_peers(language, _list(row.get("peers")), missing))
    lines.append("")
    lines.append(f"#### 8. {_label(language, 'Why the Stock Is Discounted', 'なぜ割安なのか')}")
    lines.extend(
        [
            f"- **{_label(language, 'Market concerns', '市場の懸念')}:** {_render_list(qualitative.get('discount_reasons'), missing)}",
            f"- **{_label(language, 'Temporary or structural', '一時的か構造的か')}:** {qualitative.get('discount_classification', missing)}",
            f"- **{_label(language, 'How the market may be right', '市場評価が妥当な可能性')}:** {qualitative.get('market_may_be_right', missing)}",
            f"- **{_label(language, 'Conditions for discount closure', 'ディスカウント縮小条件')}:** {_render_list(qualitative.get('rerating_conditions'), missing)}",
        ]
    )
    lines.append("")
    lines.append(
        f"#### 9. {_label(language, 'Constant-Multiple Scenario', '倍率据え置きシナリオ')}"
    )
    lines.append("| Item | Current | Year 2 | Year 3 |")
    lines.append("|---|---:|---:|---:|")
    lines.append(
        f"| Metric | {_format_number(valuation.get('current_metric'), 2, missing)} | {_format_number(_mapping(periods.get('year_2')).get('metric'), 2, missing)} | {_format_number(_mapping(periods.get('year_3')).get('metric'), 2, missing)} |"
    )
    lines.append(
        f"| Multiple | {_format_number(valuation.get('current_multiple'), 2, missing)}x | {_format_number(valuation.get('current_multiple'), 2, missing)}x | {_format_number(valuation.get('current_multiple'), 2, missing)}x |"
    )
    lines.append(
        f"| Implied price | {_format_price(identity.get('price'), identity.get('currency', 'USD'), missing)} | {_format_price(_scenario_value(row, 'constant_multiple', 'year_2', 'implied_price'), identity.get('currency', 'USD'), missing)} | {_format_price(_scenario_value(row, 'constant_multiple', 'year_3', 'implied_price'), identity.get('currency', 'USD'), missing)} |"
    )
    lines.append(
        f"| Upside | — | {_format_pct(_scenario_value(row, 'constant_multiple', 'year_2', 'upside_pct'), 1, missing)} | {_format_pct(_scenario_value(row, 'constant_multiple', 'year_3', 'upside_pct'), 1, missing)} |"
    )
    lines.append(
        f"| Annualized return | — | {_format_pct(_scenario_value(row, 'constant_multiple', 'year_2', 'cagr_pct'), 1, missing)} | {_format_pct(_scenario_value(row, 'constant_multiple', 'year_3', 'cagr_pct'), 1, missing)} |"
    )
    lines.append("")
    lines.append(
        f"#### 10. {_label(language, '20% Multiple-Contraction Scenario', '倍率20％低下シナリオ')}"
    )
    lines.append(
        f"- **2-year:** {_format_price(_scenario_value(row, 'multiple_contraction', 'year_2', 'implied_price'), identity.get('currency', 'USD'), missing)} / {_format_pct(_scenario_value(row, 'multiple_contraction', 'year_2', 'upside_pct'), 1, missing)}"
    )
    lines.append(
        f"- **3-year:** {_format_price(_scenario_value(row, 'multiple_contraction', 'year_3', 'implied_price'), identity.get('currency', 'USD'), missing)} / {_format_pct(_scenario_value(row, 'multiple_contraction', 'year_3', 'upside_pct'), 1, missing)}"
    )
    lines.append("")
    lines.append(f"#### 11. {_label(language, 'Catalysts', 'カタリスト')}")
    lines.append(_render_list(qualitative.get("catalysts"), missing))
    lines.append("")
    lines.append(f"#### 12. {_label(language, 'Largest Risk', '最大のリスク')}")
    lines.append(str(qualitative.get("maximum_risk") or missing))
    lines.append("")
    lines.append(f"#### 13. {_label(language, 'Invalidation Conditions', '投資仮説の無効化条件')}")
    lines.append(_render_list(qualitative.get("invalidation_conditions"), missing))
    lines.append("")
    lines.append(f"#### 14. {_label(language, 'Cyclicality', 'シクリカル評価')}")
    lines.extend(
        [
            f"- **{_label(language, 'Cyclicality score', 'シクリカル度')}:** {cyclicality.get('score', missing)}/5",
            f"- **{_label(language, 'Cycle position', '現在のサイクル位置')}:** {cyclicality.get('position', missing)}",
            f"- **{_label(language, 'Peak-profit risk', 'ピーク利益リスク')}:** {cyclicality.get('peak_profit_risk', missing)}",
            f"- **{_label(language, 'Normalized metric', '平準化指標')}:** {_format_number(_mapping(cyclicality.get('normalization')).get('normalized_metric'), 2, missing)}",
        ]
    )
    lines.append("")
    lines.append(f"#### 15. {_label(language, 'Overall Score', '総合評価')}")
    lines.extend(_render_score_table(row, missing))
    lines.append("")
    lines.append(
        f"#### 16. {_label(language, 'Cash-Flow and Evidence Audit', 'キャッシュフロー・証拠監査')}"
    )
    lines.extend(
        [
            f"- **{_label(language, 'TTM method', 'TTM再構築方法')}:** {cash_flow.get('method', missing)}",
            f"- **{_label(language, 'OCF / capex / standard FCF', '営業CF／設備投資／標準FCF')}:** {_format_number(cash_flow.get('operating_cash_flow'), 1, missing)} / {_format_number(cash_flow.get('capex_cash_outflow'), 1, missing)} / {_format_number(cash_flow.get('standard_fcf'), 1, missing)}",
            f"- **{_label(language, 'Company adjusted FCF', '会社Adjusted FCF')}:** {_format_number(cash_flow.get('company_adjusted_fcf'), 1, missing)} ({cash_flow.get('company_adjusted_fcf_definition', missing)})",
            f"- **{_label(language, 'Data quality', 'データ品質')}:** {row.get('data_quality_score')}/100",
            f"- **{_label(language, 'Cash consistency', '現金・負債整合性')}:** {_md_escape(row.get('cash_consistency'))}",
            f"- **{_label(language, 'Warnings', '警告')}:** {_render_list(row.get('warnings'), missing)}",
            f"- **{_label(language, 'Unresolved', '未解決')}:** {_render_list(row.get('unresolved_fields'), missing)}",
        ]
    )
    lines.append("")
    return lines


def render_markdown(report: Mapping[str, Any], *, language: str = "en") -> str:
    missing = _missing(language)
    ranked = _list(report.get("ranked_candidates"))
    conditional = _list(report.get("conditional"))
    review = _list(report.get("review_required"))
    screened_out = _list(report.get("screened_out"))
    excluded = _list(report.get("excluded"))
    broad = _mapping(report.get("broad_screen"))
    broad_counts = _mapping(broad.get("counts"))
    counts = _mapping(report.get("counts"))
    funnel = _mapping(report.get("screening_funnel"))
    price_basis = _mapping(report.get("price_basis"))
    lines: list[str] = []

    title = _label(
        language,
        "US Undervalued Growth Screening Report",
        "米国株・割安成長株スクリーニングレポート",
    )
    coverage = _mapping(report.get("coverage"))
    ranking_scope = _text(report.get("ranking_scope"))
    if ranking_scope == "final_scoped":
        evaluated = coverage.get("economic_attempt_count", "?")
        listed = coverage.get("listing_universe_count", "?")
        title += _label(
            language,
            f" — Scoped Pilot ({evaluated} of {listed} listed names economically attempted)",
            f" — 限定パイロット（上場{listed}銘柄中{evaluated}銘柄のみ経済評価を試行）",
        )
    elif ranking_scope == "diagnostic":
        title += _label(language, " — DIAGNOSTIC (incomplete scope)", " — 診断用（範囲未完了）")
    if report.get("ranking_status") != "final":
        title += _label(language, " — PROVISIONAL", " — 暫定")
    lines.append(f"# {title}")
    lines.append("")
    if ranking_scope and ranking_scope != "final_marketwide":
        attempt_pct = coverage.get("economic_attempt_coverage_pct")
        attempt_pct_text = f"{float(attempt_pct):.2f}%" if attempt_pct is not None else missing
        evaluable_pct = coverage.get("economically_evaluable_coverage_pct")
        evaluable_pct_text = (
            f"{float(evaluable_pct):.2f}%" if evaluable_pct is not None else missing
        )
        lines.append(
            f"- **{_label(language, 'Ranking scope', 'ランキング範囲')}:** {ranking_scope} — "
            + _label(
                language,
                (
                    f"conclusions bind ONLY to the {coverage.get('economic_attempt_count', '?')} names whose estimate "
                    f"acquisition was attempted ({attempt_pct_text} of "
                    f"{coverage.get('listing_universe_count', '?')} listed; economically evaluable {coverage.get('economically_evaluable_count', '?')} = {evaluable_pct_text}; quality probe {coverage.get('quality_probe_count', '?')}, "
                    f"deep dive {coverage.get('deep_dive_count', '?')}). This is NOT a market-wide ranking."
                ),
                (
                    f"結論は予想取得を試行した{coverage.get('economic_attempt_count', '?')}銘柄"
                    f"（上場{coverage.get('listing_universe_count', '?')}銘柄の{attempt_pct_text}、"
                    f"評価可能{coverage.get('economically_evaluable_count', '?')}銘柄・{evaluable_pct_text}、品質プローブ{coverage.get('quality_probe_count', '?')}銘柄、詳細分析{coverage.get('deep_dive_count', '?')}銘柄）"
                    "に限定され、市場全体ランキングではありません。"
                ),
            )
        )
    lines.append(
        f"- **{_label(language, 'Analysis as of', '分析実施日時')}:** {report.get('analysis_as_of')}"
    )
    lines.append(
        f"- **{_label(language, 'Price basis', '株価基準')}:** {price_basis.get('as_of', missing)} / {price_basis.get('session', missing)}"
    )
    lines.append(
        f"- **{_label(language, 'Ranking status', 'ランキング状態')}:** {report.get('ranking_status')}"
    )
    lines.append(
        f"- **{_label(language, 'Strict mode', '厳格モード')}:** {report.get('strict_mode')}"
    )
    lines.append(
        f"- **{_label(language, 'Deep-dive input / ranked / conditional / review / screened out / excluded', '詳細調査入力／ランキング／条件付き／要確認／スクリーニング落ち／除外')}:** {counts.get('input_candidates')} / {counts.get('ranked')} / {counts.get('conditional', 0)} / {counts.get('review_required')} / {counts.get('screened_out')} / {counts.get('excluded')}"
    )
    lines.append(
        f"- **{_label(language, 'Broad-screen selected / deferred / unresolved / screened out / excluded / unavailable', '一次選定／予算繰越／未解決／一次落ち／除外／取得不能')}:** {broad_counts.get('selected', 0)} / {broad_counts.get('deferred_by_budget', 0)} / {broad_counts.get('review_required', 0)} / {broad_counts.get('screened_out', 0)} / {broad_counts.get('excluded', 0)} / {broad_counts.get('unavailable_after_enrichment', 0)}"
    )
    lines.append("")

    lines.append(
        f"## {_label(language, 'Screening Funnel and Market Context', 'スクリーニング・ファネルと市場前提')}"
    )
    lines.append("")
    lines.append(f"- **Listing universe:** {funnel.get('universe_count', missing)}")
    lines.append(f"- **Listing rows in scope:** {funnel.get('listing_in_scope_count', missing)}")
    lines.append(
        f"- **Fundamental/estimate candidate pool:** {funnel.get('candidate_pool_count', missing)}"
    )
    lines.append(
        f"- **Discovery-evaluable candidates:** {funnel.get('discovery_evaluable_count', missing)}"
    )
    lines.append(f"- **Deep dives selected:** {funnel.get('deep_dive_selected_count', missing)}")
    lines.append(
        f"- **Corporate-action preflight passed:** {funnel.get('preflight_passed_count', missing)}"
    )
    lines.append(f"- **Deep dives completed:** {funnel.get('deep_dive_completed_count', missing)}")
    market = _mapping(report.get("market_context"))
    audit = _mapping(report.get("screening_audit"))
    scope = _mapping(audit.get("scope"))
    lines.append(
        f"- **{_label(language, 'Candidate-generation mode', '候補生成モード')}:** {audit.get('candidate_generation_mode', missing)}"
    )
    lines.append(
        f"- **{_label(language, 'Candidate-pool status', '候補プール状態')}:** {audit.get('candidate_pool_status', missing)}"
    )
    lines.append(
        f"- **{_label(language, 'Selection outcome', '候補選定結果')}:** {audit.get('selection_outcome', missing)}"
    )
    lines.append(
        f"- **{_label(language, 'Listing-data coverage', '上場・価格データカバレッジ')}:** {_format_pct(audit.get('actual_listing_data_complete_pct'), 1, missing)}"
    )
    lines.append(
        f"- **{_label(language, 'Candidate-pool discovery coverage', '候補プール経済評価可能カバレッジ')}:** {_format_pct(audit.get('actual_candidate_pool_discovery_evaluable_pct'), 1, missing)}"
    )
    lines.append(
        f"- **{_label(language, 'Candidate-pool full-fundamental coverage (informational)', '候補プール完全財務カバレッジ（参考）')}:** {_format_pct(audit.get('actual_candidate_pool_fundamental_complete_pct'), 1, missing)}"
    )
    lines.append(
        f"- **{_label(language, 'Listing enumeration', 'リスティング列挙')}:** complete={scope.get('scope_complete', False)} / requested ${scope.get('requested_min_market_cap', missing)}-${scope.get('requested_max_market_cap', missing)} / retrieved ${scope.get('retrieval_min_market_cap', missing)}-${scope.get('retrieval_max_market_cap', missing)}"
    )
    generation = _mapping(_mapping(audit.get("candidate_pool")).get("generation_audit"))
    if generation:
        universe_total = _integer(_mapping(audit.get("universe")).get("row_count"))
        mode = _text(generation.get("estimate_acquisition_mode")) or missing
        bulk = _mapping(generation.get("bulk_estimate_audit"))
        covered = _integer(bulk.get("covered_symbol_count"))
        seeds = _integer(generation.get("economic_attempt_count"))
        if mode == "analyst_estimates_bulk" and covered is not None and universe_total:
            coverage = f"{covered} / {universe_total} ({covered / universe_total * 100.0:.1f}%)"
            status = "complete" if covered >= universe_total else "partial"
        elif seeds is not None and universe_total:
            coverage = f"{seeds} / {universe_total} ({seeds / universe_total * 100.0:.1f}%)"
            status = "partial"
        else:
            coverage = missing
            status = "partial"
        lines.append(
            f"- **{_label(language, 'Economic estimate coverage', '経済スクリーン範囲')}:** {status} / mode={mode} / {coverage} -- {_label(language, 'never a market-wide conclusion under', '以下の範囲での結論に限定')} conclusion_scope={audit.get('conclusion_scope', missing)}"
        )
    lines.append(
        f"- **{_label(language, 'Market assumptions', '市場前提')}:** {market.get('summary', missing)}"
    )
    lines.append(
        f"- **Policy / 10Y / Inflation / Market Fwd P/E:** {_format_pct(market.get('policy_rate_pct'), 2, missing)} / {_format_pct(market.get('treasury_10y_yield_pct'), 2, missing)} / {_format_pct(market.get('inflation_yoy_pct'), 2, missing)} / {_format_number(market.get('market_forward_pe'), 2, missing)}x"
    )
    lines.append(
        f"- **{_label(language, 'Universe audit SHA-256', '上場母集団監査SHA-256')}:** {audit.get('actual_universe_sha256', missing)}"
    )
    enrichment = _mapping(audit.get("enrichment"))
    lines.append(
        f"- **{_label(language, 'Candidate-pool audit SHA-256', '候補プール監査SHA-256')}:** {audit.get('actual_candidate_pool_sha256', missing)} / valid={audit.get('valid', False)}"
    )
    lines.append(
        f"- **{_label(language, 'Enrichment resolved / unresolved / exhausted', 'エンリッチメント解決済み／未解決／プール枯渇')}:** {audit.get('actual_enrichment_resolved_count', missing)} / {audit.get('actual_enrichment_unresolved_count', missing)} / {audit.get('actual_candidate_pool_exhausted', False)}"
    )
    lines.append(
        f"- **{_label(language, 'Next action', '次の処理')}:** {enrichment.get('next_action', missing)}"
    )
    lines.append("")

    lines.append(f"## A. {_label(language, 'Ranking', 'ランキング一覧')}")
    lines.append("")
    if ranked:
        lines.append(
            "| Rank | Company | Ticker | Price | Market Cap | Forward Basis | Forward Multiple | EV/FCF | FCF Yield | ROIC | Diluted Share CAGR | Cyclicality | Rankable 3Y/2Y Upside | Score | DQ |"
        )
        lines.append("|---:|---|---|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
        for row in ranked:
            identity = _mapping(row.get("identity"))
            metrics = _mapping(row.get("financial_metrics"))
            valuation = _mapping(row.get("valuation"))
            lines.append(
                "| {rank} | {company} | {symbol} | {price} | {cap} | {basis} | {multiple} | {evfcf} | {fcf} | {roic} | {dilution} | {cycle} | {upside} | {score} | {dq} |".format(
                    rank=row.get("rank"),
                    company=_md_escape(row.get("company_name")),
                    symbol=row.get("symbol"),
                    price=_format_price(
                        identity.get("price"), identity.get("currency", "USD"), missing
                    ),
                    cap=_format_number(identity.get("market_cap"), 1, missing),
                    basis=f"{valuation.get('basis', missing)}/{valuation.get('current_metric_basis', missing)}",
                    multiple=_format_number(valuation.get("current_multiple"), 2, missing),
                    evfcf=_format_number(metrics.get("ev_to_fcf"), 2, missing),
                    fcf=_format_pct(metrics.get("fcf_yield_pct"), 1, missing),
                    roic=_format_pct(metrics.get("roic_pct"), 1, missing),
                    dilution=_format_pct(metrics.get("diluted_share_cagr_pct"), 1, missing),
                    cycle=_mapping(row.get("cyclicality")).get("score", missing),
                    upside=_format_pct(
                        _preferred_three_year_upside(valuation, "constant_multiple"), 1, missing
                    ),
                    score=_format_number(row.get("final_score"), 1, missing),
                    dq=row.get("data_quality_score", missing),
                )
            )
    else:
        pool_status = _text(_mapping(report.get("contract")).get("candidate_pool_status"))
        if report.get("ranking_status") == "final" and pool_status == "no_qualifying_candidates":
            lines.append(
                _label(
                    language,
                    "No qualifying candidates in the audited full universe.",
                    "監査済みの全対象ユニバースでは現時点で該当なし。",
                )
            )
        elif (
            report.get("ranking_status") == "final"
            and pool_status == "no_qualifying_candidates_in_bounded_pool"
        ):
            cov = _mapping(report.get("coverage"))
            lines.append(
                _label(
                    language,
                    (
                        f"No qualifying candidates among the {cov.get('deep_dive_count', '?')} deep-dived names "
                        f"selected from the {cov.get('economic_attempt_count', '?')} economically attempted "
                        f"(of {cov.get('listing_universe_count', '?')} listed); the remaining names were never "
                        "economically compared — this is not a market-wide conclusion."
                    ),
                    (
                        f"経済評価を試行した{cov.get('economic_attempt_count', '?')}銘柄から選定した"
                        f"{cov.get('deep_dive_count', '?')}銘柄の詳細分析では該当なし"
                        f"（上場{cov.get('listing_universe_count', '?')}銘柄の残りは未審査であり、"
                        "市場全体の該当なしを意味しません）。"
                    ),
                )
            )
        else:
            lines.append(
                _label(
                    language,
                    "Ranking withheld: candidate-pool research is incomplete.",
                    "ランキング保留：候補プールの調査が未完了です。",
                )
            )
    lines.append("")

    lines.append(f"## B. {_label(language, 'Scenario Table', 'シナリオ表')}")
    lines.append("")
    lines.append(
        "| Ticker | Current Metric | Current Multiple | 2Y Price | 2Y Upside | 2Y Stress Price | 2Y Stress Upside | 3Y Price | 3Y Upside | 3Y Stress Price | 3Y Stress Upside | Peer 3Y Price |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for row in ranked:
        valuation = _mapping(row.get("valuation"))
        currency = _mapping(row.get("identity")).get("currency", "USD")
        lines.append(
            f"| {row.get('symbol')} | {_format_number(valuation.get('current_metric'), 2, missing)} | {_format_number(valuation.get('current_multiple'), 2, missing)} | {_format_price(_scenario_value(row, 'constant_multiple', 'year_2', 'implied_price'), currency, missing)} | {_format_pct(_scenario_value(row, 'constant_multiple', 'year_2', 'upside_pct'), 1, missing)} | {_format_price(_scenario_value(row, 'multiple_contraction', 'year_2', 'implied_price'), currency, missing)} | {_format_pct(_scenario_value(row, 'multiple_contraction', 'year_2', 'upside_pct'), 1, missing)} | {_format_price(_scenario_value(row, 'constant_multiple', 'year_3', 'implied_price'), currency, missing)} | {_format_pct(_scenario_value(row, 'constant_multiple', 'year_3', 'upside_pct'), 1, missing)} | {_format_price(_scenario_value(row, 'multiple_contraction', 'year_3', 'implied_price'), currency, missing)} | {_format_pct(_scenario_value(row, 'multiple_contraction', 'year_3', 'upside_pct'), 1, missing)} | {_format_price(_scenario_value(row, 'peer_median', 'year_3', 'implied_price'), currency, missing)} |"
        )
    lines.append("")

    lines.append(f"## C. {_label(language, 'Candidate Details', '各銘柄の詳細')}")
    lines.append("")
    for row in ranked:
        lines.extend(_render_candidate_detail(language, row))

    lines.append(f"## D. {_label(language, 'Conditional Candidates', '条件付き候補')}")
    lines.append("")
    if conditional:
        lines.append("| Ticker | Company | Final Score | Conditions | Low-case Upside |")
        lines.append("|---|---|---:|---|---:|")
        for row in conditional:
            lines.append(
                f"| {row.get('symbol')} | {_md_escape(row.get('company_name'))} | {_format_number(row.get('final_score'), 1, missing)} | {_md_escape('; '.join(row.get('conditional_reasons') or []))} | {_format_pct(_best_low_case_upside(_mapping(row.get('valuation'))), 1, missing)} |"
            )
    else:
        lines.append(_label(language, "None.", "なし。"))
    lines.append("")

    lines.append(f"## E. {_label(language, 'Review Required', '追加確認が必要な候補')}")
    lines.append("")
    if review:
        lines.append(f"### {_label(language, 'Deep-dive review blockers', '詳細調査の要確認')}")
        lines.append("| Ticker | Company | Final Score | Blockers | Evidence Needed |")
        lines.append("|---|---|---:|---|---|")
        for row in review:
            lines.append(
                f"| {row.get('symbol')} | {_md_escape(row.get('company_name'))} | {_format_number(row.get('final_score'), 1, missing)} | {_md_escape('; '.join(row.get('review_reasons') or []))} | {_md_escape('; '.join(row.get('unresolved_fields') or []) or missing)} |"
            )
        lines.append("")
    broad_review = _list(broad.get("review_required"))
    broad_deferred = _list(broad.get("deferred_by_budget"))
    broad_selected = _list(broad.get("selected"))
    broad_unavailable = _list(broad.get("unavailable_after_enrichment"))
    if broad_selected or broad_deferred or broad_review or broad_unavailable:
        lines.append(
            f"### {_label(language, 'Broad-screen dispositions requiring or deferring work', '一次スクリーニングの要確認・繰越')}"
        )
        lines.append(
            "| Ticker | Company | Status | Fwd P/E | Revenue Growth | Per-share Growth | Priority | Reasons / Requirements |"
        )
        lines.append("|---|---|---|---:|---:|---:|---:|---|")
        for row in broad_selected + broad_deferred + broad_review + broad_unavailable:
            metrics = _mapping(row.get("metrics"))
            reasons = list(row.get("review_reasons") or []) + list(
                row.get("deep_dive_requirements") or []
            )
            lines.append(
                f"| {row.get('symbol')} | {_md_escape(row.get('company_name'))} | {row.get('status')} | {_format_number(metrics.get('forward_pe'), 2, missing)} | {_format_pct(metrics.get('revenue_growth_pct'), 1, missing)} | {_format_pct(metrics.get('per_share_growth_pct'), 1, missing)} | {_format_number(row.get('deep_dive_priority_score'), 1, missing)} | {_md_escape('; '.join(dict.fromkeys(reasons)) or missing)} |"
            )
    elif not review:
        lines.append(_label(language, "None.", "なし。"))
    lines.append("")

    lines.append(f"## F. {_label(language, 'Screened-Out Log', 'スクリーニング落ちログ')}")
    lines.append("")
    if screened_out:
        lines.append(
            f"### {_label(language, 'Deep-dive screened out', '詳細調査でのスクリーニング落ち')}"
        )
        lines.append("| Ticker | Company | Reason |")
        lines.append("|---|---|---|")
        for row in screened_out:
            lines.append(
                f"| {row.get('symbol')} | {_md_escape(row.get('company_name'))} | {_md_escape('; '.join(row.get('screening_reasons') or []))} |"
            )
        lines.append("")
    broad_screened = _list(broad.get("screened_out"))
    if broad_screened:
        lines.append(
            f"### {_label(language, 'Broad-screen screened out', '一次スクリーニング落ち')}"
        )
        lines.append(
            "| Ticker | Company | Fwd P/E | Revenue Growth | Per-share Growth | Guideline Misses | Screen-Fail Reasons |"
        )
        lines.append("|---|---|---:|---:|---:|---|---|")
        for row in broad_screened:
            metrics = _mapping(row.get("metrics"))
            lines.append(
                f"| {row.get('symbol')} | {_md_escape(row.get('company_name'))} | {_format_number(metrics.get('forward_pe'), 2, missing)} | {_format_pct(metrics.get('revenue_growth_pct'), 1, missing)} | {_format_pct(metrics.get('per_share_growth_pct'), 1, missing)} | {_md_escape('; '.join(row.get('guideline_misses') or []) or missing)} | {_md_escape('; '.join(row.get('screen_fail_reasons') or []) or missing)} |"
            )
    elif not screened_out:
        lines.append(_label(language, "None.", "なし。"))
    lines.append("")

    lines.append(f"## G. {_label(language, 'Hard Exclusion Log', 'ハード除外ログ')}")
    lines.append("")
    broad_excluded = _list(broad.get("excluded"))
    if excluded or broad_excluded:
        lines.append("| Stage | Ticker | Company | Reason |")
        lines.append("|---|---|---|---|")
        for row in excluded:
            lines.append(
                f"| deep_dive | {row.get('symbol')} | {_md_escape(row.get('company_name'))} | {_md_escape('; '.join(row.get('hard_exclusion_reasons') or []))} |"
            )
        for row in broad_excluded:
            reasons = list(row.get("review_reasons") or []) + list(
                row.get("screen_fail_reasons") or []
            )
            lines.append(
                f"| broad_screen | {row.get('symbol')} | {_md_escape(row.get('company_name'))} | {_md_escape('; '.join(reasons) or missing)} |"
            )
    else:
        lines.append(_label(language, "None.", "なし。"))
    lines.append("")

    lines.append(f"## H. {_label(language, 'Final Three', '最終選定3銘柄')}")
    lines.append("")
    categories = [
        ("highest_conviction", "Highest conviction", "最も確度が高い"),
        ("most_undervalued", "Most undervalued", "最も割安"),
        ("largest_upside", "Largest upside", "最も上昇余地が大きい"),
    ]
    for key, en, ja in categories:
        entry = _mapping(_mapping(report.get("final_three")).get(key))
        lines.append(f"### {_label(language, en, ja)}")
        if not entry:
            lines.append(missing)
            lines.append("")
            continue
        lines.extend(
            [
                f"- **Ticker:** {entry.get('symbol')} — {entry.get('company_name')}",
                f"- **{_label(language, 'Why it qualifies', '最も有望と判断した理由')}:** {entry.get('investment_thesis') or missing}",
                f"- **{_label(language, 'Per-share growth upside', 'EPS/FCF成長だけの上昇余地')}:** {_format_pct(entry.get('constant_multiple_upside_pct'), 1, missing)}",
                f"- **{_label(language, 'What the market may miss', '市場が見落としている可能性')}:** {entry.get('market_may_be_missing') or missing}",
                f"- **{_label(language, 'Best catalyst', '最有力カタリスト')}:** {entry.get('best_catalyst') or missing}",
                f"- **{_label(language, 'Largest risk', '最大のリスク')}:** {entry.get('maximum_risk') or missing}",
                f"- **{_label(language, 'Reason not to buy now', '今買わない理由')}:** {entry.get('do_not_buy_reason') or missing}",
                f"- **{_label(language, 'Bear case', '弱気シナリオ')}:** {entry.get('bear_case') or missing}",
                f"- **{_label(language, 'Invalidation', '無効化条件')}:** {_render_list(entry.get('invalidation_conditions'), missing)}",
                f"- **{_label(language, 'Next earnings KPIs', '次回決算KPI')}:** {_render_list(entry.get('next_earnings_kpis'), missing)}",
            ]
        )
        lines.append("")

    source_rows: dict[str, Mapping[str, Any]] = {}
    for source in _list(report.get("global_sources")):
        item = _mapping(source)
        source_id = _text(item.get("id"))
        if source_id:
            source_rows[source_id] = item
    for row in ranked + review + screened_out + excluded:
        for source in _list(row.get("sources")):
            item = _mapping(source)
            source_id = _text(item.get("id"))
            if source_id:
                source_rows[source_id] = item
    lines.append(f"## I. {_label(language, 'Source Ledger', '情報源台帳')}")
    lines.append("")
    if source_rows:
        lines.append("| Source ID | Tier | Kind | Published | Retrieved | Supports |")
        lines.append("|---|---:|---|---|---|---|")
        for source_id in sorted(source_rows):
            source = source_rows[source_id]
            lines.append(
                f"| {_md_escape(source_id)} | {source.get('tier', missing)} | {_md_escape(source.get('kind', missing))} | {_md_escape(source.get('published_at', missing))} | {_md_escape(source.get('retrieved_at', missing))} | {_md_escape(', '.join(str(value) for value in _list(source.get('supports'))))} |"
            )
    else:
        lines.append(missing)
    lines.append("")

    lines.append(
        f"## J. {_label(language, 'Unresolved Data and Global Warnings', '未解決データと全体警告')}"
    )
    lines.append("")
    warnings = _list(report.get("global_warnings"))
    if warnings:
        for warning in warnings:
            lines.append(f"- {warning}")
    else:
        lines.append(_label(language, "None.", "なし。"))
    lines.append("")
    lines.append(
        _label(
            language,
            "This report is a research screen, not an automatic order or guarantee of return.",
            "本レポートは調査用スクリーニングであり、自動発注や収益保証ではありません。",
        )
    )
    lines.append("")
    return "\n".join(lines)


def _timestamp_for_filename(report: Mapping[str, Any]) -> str:
    generated = _text(report.get("generated_at"))
    if generated:
        try:
            parsed = parse_iso8601(generated, "generated_at")
            if parsed:
                return parsed.astimezone(timezone.utc).strftime("%Y%m%d_%H%M%S")
        except InputError:
            pass
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def write_outputs(
    report: Mapping[str, Any], output_dir: Path, *, language: str
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = _timestamp_for_filename(report)
    json_path = output_dir / f"us_undervalued_growth_{stamp}.json"
    md_path = output_dir / f"us_undervalued_growth_{stamp}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(report, language=language), encoding="utf-8")
    return json_path, md_path


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate, score, and rank normalized US undervalued-growth candidates (schema v3, contract v3.5)."
    )
    parser.add_argument(
        "--input",
        required=True,
        type=Path,
        help="Normalized schema-3 / contract-3.5 candidate JSON input",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("reports/us-undervalued-growth-screener"),
        help="Output directory for JSON and Markdown reports",
    )
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=None,
        help="Root used to resolve and hash broad-screen audit artifacts; defaults to input directory",
    )
    parser.add_argument("--top", type=int, default=None, help="Maximum ranked candidates")
    parser.add_argument("--language", choices=("en", "ja"), default="en")
    parser.add_argument("--strict", action="store_true", help="Enable fail-closed research gates")
    parser.add_argument("--stdout", action="store_true", help="Print the Markdown report to stdout")
    parser.add_argument(
        "--require-final",
        action="store_true",
        help="Return exit code 2 after writing outputs when the run is provisional or the global contract is invalid",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    raw_argv = list(argv) if argv is not None else sys.argv[1:]
    if "--version" in raw_argv:
        print(json.dumps(runtime_metadata(), sort_keys=True))
        return 0
    args = parse_args(raw_argv)
    try:
        payload = json.loads(args.input.read_text(encoding="utf-8"))
        if not isinstance(payload, Mapping):
            raise InputError("top-level JSON must be an object")
        artifact_root = args.artifact_root or args.input.parent
        report = evaluate_snapshot(
            payload, strict=args.strict, top=args.top, artifact_root=artifact_root
        )
        json_path, md_path = write_outputs(report, args.output_dir, language=args.language)
    except (OSError, json.JSONDecodeError, InputError, ContractError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"wrote: {json_path}")
    print(f"wrote: {md_path}")
    if args.stdout:
        print()
        print(md_path.read_text(encoding="utf-8"))
    if args.require_final and (
        report.get("ranking_status") != "final" or not _mapping(report.get("contract")).get("valid")
    ):
        print(
            "ERROR: final-run gate failed; see generated report for contract blockers",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
