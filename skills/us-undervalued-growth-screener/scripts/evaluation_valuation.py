"""Valuation scenarios, sector-profile checks, score components and data quality for evaluate_candidates."""

from __future__ import annotations

import statistics
from collections.abc import Mapping
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from evaluation_common import (
    ALLOWED_METRIC_BASES,
    ALLOWED_PERIOD_KINDS,
    ALLOWED_SOURCE_TYPES,
    ALLOWED_SPECIAL_CASES,
    ALLOWED_VALUATION_BASES,
    QUALITY_WEIGHTS,
    SCORE_LIMITS,
    InputError,
    _candidate_source_ids,
    _dispersion_from_bounds,
    _has_tier,
    _integer,
    _list,
    _mapping,
    _min_valid,
    _number,
    _parse_date,
    _round,
    _scenario,
    _sources_resolve,
    _text,
    _years_between,
    parse_iso8601,
)
from evaluation_financials import _validate_forecast_bridge, _validate_gaap_reconciliation


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
