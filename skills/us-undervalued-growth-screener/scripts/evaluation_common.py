"""Shared constants, input coercion, formatting and source helpers for evaluate_candidates."""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

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
