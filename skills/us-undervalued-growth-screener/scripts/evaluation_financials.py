"""Corporate-action, cash-flow, financial-metric and forecast-bridge checks for evaluate_candidates."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from datetime import datetime
from typing import Any

from evaluation_common import (
    ALLOWED_CASH_FLOW_METHODS,
    ALLOWED_LISTING_STATUSES,
    ALLOWED_MNA_STATUSES,
    InputError,
    _candidate_source_ids,
    _history_cagr,
    _list,
    _mapping,
    _number,
    _parse_date,
    _pct,
    _round,
    _sources_resolve,
    _text,
    parse_iso8601,
)


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
