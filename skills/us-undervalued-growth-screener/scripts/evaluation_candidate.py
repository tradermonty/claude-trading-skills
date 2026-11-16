"""Quality eligibility gate and per-candidate evaluation for evaluate_candidates."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from datetime import datetime
from typing import Any

from evaluation_common import (
    ALLOWED_EXCHANGES,
    ALLOWED_SCREENING_STATUSES,
    ALLOWED_SESSIONS,
    HARD_FLAG_LABELS,
    InputError,
    _cyclicality_penalty,
    _data_quality_penalty,
    _dilution_penalty,
    _estimate_breadth_penalty,
    _estimate_dispersion_penalty,
    _has_primary_source,
    _integer,
    _list,
    _mapping,
    _number,
    _round,
    _sbc_penalty,
    _scenario,
    _source_index,
    _sources_resolve,
    _text,
    parse_iso8601,
)
from evaluation_financials import _calculate_financial_metrics, _validate_corporate_action
from evaluation_valuation import (
    _calculate_data_quality,
    _calculate_score_components,
    _calculate_valuation,
    _validate_sector_profile,
)


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
