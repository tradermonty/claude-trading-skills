#!/usr/bin/env python3
"""Tiered broad screen for US undervalued-growth candidates (contract v3.5).

The screener separates two coverage layers:

1. Listing-universe audit: symbol, exchange, active/common-stock status, price,
   market capitalization, and liquidity for the full requested universe.
2. Economic candidate-pool screen: forward valuation and per-share growth for a
   bounded, transparently generated pool. Full statements are *not* required
   across the entire market; they are verified only for selected deep-dive names.

Rows with blocking missing data are never selected or ranked by an alphabetical
tie-break. Strong cyclicals may advance with a mid-cycle deep-dive requirement.
A run with no economically evaluable candidate pool is reported as
``insufficient_data`` rather than as ``no qualifying candidates``.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
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
    from screening_semantics import normalize_forward_valuation, normalize_liquidity
except ModuleNotFoundError:
    import importlib.util as _semantics_importlib_util

    _semantics_path = Path(__file__).with_name("screening_semantics.py")
    _semantics_spec = _semantics_importlib_util.spec_from_file_location(
        "screening_semantics", _semantics_path
    )
    if _semantics_spec is None or _semantics_spec.loader is None:
        raise
    _semantics_module = _semantics_importlib_util.module_from_spec(_semantics_spec)
    _semantics_spec.loader.exec_module(_semantics_module)
    normalize_forward_valuation = _semantics_module.normalize_forward_valuation
    normalize_liquidity = _semantics_module.normalize_liquidity

AUDIT_SCHEMA_VERSION = 3
DEFAULT_REQUESTED_MIN_MARKET_CAP = 500_000_000
DEFAULT_REQUESTED_MAX_MARKET_CAP = 20_000_000_000
ALLOWED_EXCHANGES = {"NYSE", "NASDAQ", "NYSE AMERICAN", "NYSEAMERICAN", "AMEX"}
CANDIDATE_GENERATION_MODES = {
    "full_universe_fundamentals",
    "provider_prefilter",
    "sharded_snapshot",
    "liquidity_stratified_estimates",
    "available_fundamentals",
    "user_supplied",
}
ESTIMATE_MODES = CANDIDATE_GENERATION_MODES - {"full_universe_fundamentals"}
SECTOR_PROFILES = {"bank", "insurance", "reit", "bdc", "mlp", "asset_manager"}

# ISIN prefixes that prove a US-domiciled security.
_US_ISIN_PREFIXES = ("US",)


def requires_unit_reconciliation(row: Mapping[str, Any]) -> bool:
    """Fail-closed unit-context gate shared by discovery and screening.

    Valuation ratios are trustworthy only when the listing price and the
    statement/estimate figures are provably in the same currency and share
    unit. That is the case only for a row PROVEN domestic (country US, no
    foreign ISIN, not an ADR/ADS, currency USD or unstated). Anything
    else — a missing country, a non-USD currency, a non-US ISIN, or an
    ADR/ADS flag — requires explicit ``unit_reconciliation_verified``
    evidence: an unknown unit context is treated as unreconciled, never as
    domestic (QFIN passed the old gate whenever the provider dropped the
    country field).
    """
    if row.get("unit_reconciliation_verified") is True:
        return False
    if row.get("is_adr") is True:
        return True
    country = (_text(row.get("country")) or "").upper()
    if country != "US":
        return True
    currency = (_text(row.get("currency")) or "").upper()
    if currency and currency != "USD":
        return True
    isin = (_text(row.get("isin")) or "").upper()
    if isin and not isin.startswith(_US_ISIN_PREFIXES):
        return True
    return False


DEFAULTS: dict[str, Any] = {
    "requested_min_market_cap": DEFAULT_REQUESTED_MIN_MARKET_CAP,
    "requested_max_market_cap": DEFAULT_REQUESTED_MAX_MARKET_CAP,
    "min_market_cap": 500_000_000,
    "max_market_cap": 20_000_000_000,
    "min_price": 5.0,
    "min_average_daily_dollar_volume": 5_000_000,
    "hard_min_average_daily_dollar_volume": 1_000_000,
    "minimum_average_volume_period_days": 20,
    "max_deep_dive_candidates": 5,
    "selection_lane_quota_core_garp": 2,
    "selection_lane_quota_high_growth": 1,
    "selection_lane_quota_near_miss": 1,
    "selection_lane_quota_cyclical": 1,
    "maximum_selected_per_sector": 2,
    "preferred_forward_pe": 20.0,
    "high_growth_exception_max_forward_pe": 30.0,
    "near_miss_max_forward_pe": 22.0,
    "preferred_ev_to_fcf": 20.0,
    "preferred_fcf_yield_pct": 5.0,
    "minimum_revenue_growth_pct": 8.0,
    "minimum_per_share_growth_pct": 12.0,
    "near_miss_min_per_share_growth_pct": 8.0,
    "high_growth_exception_growth_pct": 20.0,
    "minimum_roic_pct": 8.0,
    "preferred_max_dilution_pct": 3.0,
    "preferred_max_net_debt_to_ebitda": 2.5,
    "hard_max_net_debt_to_ebitda": 4.0,
    "maximum_forward_pe_for_economic_screen": 60.0,
    "minimum_listing_data_coverage_pct": 95.0,
    "minimum_discovery_analyst_count": 2,
    "maximum_enrichment_attempts": 60,
    "sector_review_selection_penalty": 5.0,
    "near_miss_selection_penalty": 4.0,
    "missing_deep_dive_field_penalty": 1.5,
    "forward_pe_reconciliation_tolerance_pct": 5.0,
    "maximum_forward_eps_dispersion_pct": 100.0,
    "max_estimate_age_days": 45,
    "maximum_fy1_horizon_days": 430,
}


class ScreenError(ValueError):
    """Raised when screening input or configuration is invalid."""


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _text(value: Any) -> str | None:
    if isinstance(value, str):
        result = value.strip()
        return result or None
    return None


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        result = float(value)
        return result if math.isfinite(result) else None
    if isinstance(value, str):
        try:
            result = float(value.replace(",", "").strip())
        except ValueError:
            return None
        return result if math.isfinite(result) else None
    return None


def _integer(value: Any) -> int | None:
    number = _number(value)
    return int(number) if number is not None and number.is_integer() else None


def _bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "y"}:
            return True
        if lowered in {"false", "0", "no", "n"}:
            return False
    return None


def _load_rows(path: Path) -> list[dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        with path.open(newline="", encoding="utf-8-sig") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    if suffix in {".jsonl", ".ndjson"}:
        rows: list[dict[str, Any]] = []
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, Mapping):
                raise ScreenError(f"line {line_no} is not an object")
            rows.append(dict(value))
        return rows
    value = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(value, list):
        return [_mapping(row) for row in value]
    if isinstance(value, Mapping) and isinstance(value.get("rows"), list):
        return [_mapping(row) for row in value["rows"]]
    raise ScreenError("input must be a JSON array, {rows:[...]}, JSONL, or CSV")


def _metric(row: Mapping[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = _number(row.get(key))
        if value is not None:
            return value
    return None


def _symbol(row: Mapping[str, Any]) -> str:
    return (_text(row.get("symbol")) or _text(row.get("ticker")) or "UNKNOWN").upper()


def _exchange(row: Mapping[str, Any]) -> str:
    return (_text(row.get("exchange")) or _text(row.get("exchangeShortName")) or "").upper()


def _liquidity(row: Mapping[str, Any], config: Mapping[str, Any]) -> dict[str, Any]:
    return normalize_liquidity(
        row,
        minimum_period_days=int(config.get("minimum_average_volume_period_days", 20)),
    )


def _adv(row: Mapping[str, Any], config: Mapping[str, Any]) -> float | None:
    return _liquidity(row, config).get("value")


def _active(row: Mapping[str, Any]) -> bool | None:
    if "is_actively_trading" in row:
        return _bool(row.get("is_actively_trading"))
    return _bool(row.get("isActivelyTrading"))


def _common(row: Mapping[str, Any]) -> bool | None:
    if "is_common_stock" in row:
        return _bool(row.get("is_common_stock"))
    if "common_stock" in row:
        return _bool(row.get("common_stock"))
    return None


def _listing_decision(row: Mapping[str, Any], config: Mapping[str, Any]) -> dict[str, Any]:
    symbol = _symbol(row)
    exchange = _exchange(row)
    price = _metric(row, "price", "last")
    market_cap = _metric(row, "market_cap", "marketCap")
    liquidity = _liquidity(row, config)
    adv = liquidity.get("value")
    active = _active(row)
    common = _common(row)
    reasons: list[str] = []
    status = "in_scope"

    if exchange not in ALLOWED_EXCHANGES:
        status, reasons = "out_of_scope", ["exchange_out_of_scope"]
    elif active is False:
        status, reasons = "excluded", ["inactive_symbol"]
    elif common is False:
        status, reasons = "excluded", ["not_common_stock"]
    elif price is None:
        status, reasons = "listing_data_incomplete", ["price_unavailable"]
    elif price < float(config["min_price"]):
        status, reasons = "out_of_scope", ["price_below_minimum"]
    elif market_cap is None:
        status, reasons = "listing_data_incomplete", ["market_cap_unavailable"]
    elif market_cap < float(config["min_market_cap"]) or market_cap > float(
        config["max_market_cap"]
    ):
        status, reasons = "out_of_scope", ["market_cap_out_of_range"]
    elif liquidity.get("valid_for_screen") is not True:
        status, reasons = (
            "liquidity_review",
            list(liquidity.get("reasons") or ["average_liquidity_evidence_required"]),
        )
    elif adv < float(config["hard_min_average_daily_dollar_volume"]):
        status, reasons = "excluded", ["extreme_illiquidity"]
    elif adv < float(config["min_average_daily_dollar_volume"]):
        status, reasons = "liquidity_review", ["liquidity_below_preferred"]

    listing_complete = (
        symbol != "UNKNOWN" and bool(exchange) and price is not None and market_cap is not None
    )
    return {
        "symbol": symbol,
        "company_name": _text(row.get("company_name"))
        or _text(row.get("companyName"))
        or _text(row.get("name")),
        "exchange": exchange,
        "sector": _text(row.get("sector")),
        "industry": _text(row.get("industry")),
        "listing_decision": {"status": status, "reasons": reasons},
        "listing_data_complete": listing_complete,
        "eligible_for_candidate_generation": status in {"in_scope", "liquidity_review"},
        "metrics": {
            "price": price,
            "market_cap": market_cap,
            "average_daily_dollar_volume": adv,
            "average_daily_dollar_volume_method": liquidity.get("method"),
            "average_volume_period_days": liquidity.get("period_days"),
            "liquidity_source_ids": liquidity.get("source_ids", []),
            "liquidity_valid_for_screen": liquidity.get("valid_for_screen"),
            "is_actively_trading": active,
            "is_common_stock": common,
        },
    }


def _candidate_decision(
    row: Mapping[str, Any], config: Mapping[str, Any], mode: str, analysis_as_of: str
) -> dict[str, Any]:
    """Classify one discovery row without treating guidelines as hard cutoffs.

    The broad screen answers two separate questions:

    1. Is there enough forward valuation/growth evidence to prioritize the name?
    2. What additional sector, cyclicality, and quality work is required before ranking?

    A cyclical normalization requirement is therefore a deep-dive requirement,
    not an automatic rejection. Missing bank/REIT/BDC/MLP-specific valuation or
    auto-dealer floorplan leverage remains blocking because the general-company
    multiples are not decision-useful for those profiles.
    """
    symbol = _symbol(row)
    exchange = _exchange(row)
    price = _metric(row, "price", "last")
    market_cap = _metric(row, "market_cap", "marketCap")
    liquidity = _liquidity(row, config)
    adv = liquidity.get("value")
    active = _active(row)
    common = _common(row)
    revenue_growth = _metric(row, "revenue_growth_pct", "revenue_growth", "fy1_revenue_growth_pct")
    eps_growth = _metric(row, "eps_growth_pct", "forward_eps_growth_pct", "fy1_eps_growth_pct")
    fcf_ps_growth = _metric(row, "fcf_per_share_growth_pct")
    explicit_per_share_growth = _metric(row, "per_share_growth_pct")
    per_share_values = [
        value
        for value in (eps_growth, fcf_ps_growth, explicit_per_share_growth)
        if value is not None
    ]
    per_share_growth = max(per_share_values) if per_share_values else None
    fcf = _metric(row, "standard_fcf", "free_cash_flow")
    roic = _metric(row, "roic_pct", "return_on_invested_capital_pct")
    forward = normalize_forward_valuation(
        row,
        price=price,
        analysis_as_of=analysis_as_of,
        max_age_days=int(config.get("max_estimate_age_days", 45)),
        reconciliation_tolerance_pct=float(
            config.get("forward_pe_reconciliation_tolerance_pct", 5.0)
        ),
        maximum_dispersion_pct=float(config.get("maximum_forward_eps_dispersion_pct", 100.0)),
        maximum_fy1_horizon_days=int(config.get("maximum_fy1_horizon_days", 430)),
    )
    forward_pe = _number(forward.get("forward_pe"))
    ev_to_fcf = _metric(row, "ev_to_fcf")
    fcf_yield = _metric(row, "fcf_yield_pct")
    dilution = _metric(row, "diluted_share_growth_pct", "dilution_pct")
    leverage = _metric(row, "net_debt_to_ebitda")
    analyst_count = (
        _integer(forward.get("analyst_count"))
        or _integer(row.get("analyst_count"))
        or _integer(row.get("fy1_analyst_count"))
    )
    profile_type = (_text(row.get("sector_profile_type")) or "general").lower()
    cyclicality = int(_metric(row, "cyclicality_score") or 1)
    normalized_metric = _metric(row, "normalized_eps", "normalized_fcf_per_share")

    hard: list[str] = []
    blocking_review: list[str] = []
    nonblocking_review: list[str] = []
    missing_discovery: list[str] = []
    hard_fail: list[str] = []
    guideline_misses: list[str] = []
    deep_dive_requirements: list[str] = []

    if exchange not in ALLOWED_EXCHANGES:
        hard.append("exchange_out_of_scope")
    if active is False:
        hard.append("inactive_symbol")
    if common is False:
        hard.append("not_common_stock")
    if price is None or price < float(config["min_price"]):
        hard.append("price_below_minimum")
    if (
        market_cap is None
        or market_cap < float(config["min_market_cap"])
        or market_cap > float(config["max_market_cap"])
    ):
        hard.append("market_cap_out_of_range")
    if liquidity.get("valid_for_screen") is not True:
        missing_discovery.extend(
            list(liquidity.get("reasons") or ["average_liquidity_evidence_required"])
        )
    elif adv < float(config["hard_min_average_daily_dollar_volume"]):
        hard.append("extreme_illiquidity")
    elif adv < float(config["min_average_daily_dollar_volume"]):
        deep_dive_requirements.append("liquidity_below_preferred")

    # Sector profiles whose standard company multiples are not comparable need
    # their own valuation metric before discovery scoring is meaningful.
    if profile_type in SECTOR_PROFILES:
        sector_multiple = _metric(
            row, "sector_forward_multiple", "p_to_tbv", "p_to_affo", "p_to_book"
        )
        sector_growth = _metric(
            row,
            "sector_per_share_growth_pct",
            "affo_per_share_growth_pct",
            "tbv_per_share_growth_pct",
        )
        if sector_multiple is None or sector_growth is None:
            blocking_review.append("sector_specific_valuation_required")
    if profile_type == "auto_dealership":
        adjusted = _metric(row, "sector_adjusted_net_debt_to_ebitda")
        floorplan_excluded = _bool(row.get("floorplan_debt_excluded"))
        if adjusted is None or floorplan_excluded is not True:
            blocking_review.append("sector_adjusted_leverage_required")
        else:
            leverage = adjusted
    # Unit-context gate (fail closed): a USD listing price against
    # local-currency (or differently ratioed ADS) statements produces
    # meaningless ratios until unit reconciliation is verified — and an
    # UNKNOWN context (missing country, non-USD currency, non-US ISIN,
    # ADR/ADS) counts as unreconciled, never as domestic.
    if requires_unit_reconciliation(row) or (
        "foreign_private_issuer_review" in (row.get("provider_prefilter_flags") or [])
        and _bool(row.get("unit_reconciliation_verified")) is not True
    ):
        blocking_review.append("unit_reconciliation_required")
    # Unit-anomaly circuit breakers (any issuer): impossible "cheapness" is a
    # suspected currency/ADS-unit mismatch, never deep value (QFIN: forward
    # P/E 0.45x, FCF yield 94% from CNY EPS against a USD ADS price).
    latest_actual_eps = _metric(row, "latest_actual_eps", "fy0_actual_eps")
    unit_anomaly = bool(
        (
            forward_pe is not None
            and 0 < forward_pe < float(config.get("minimum_plausible_forward_pe", 2.0))
        )
        or (
            fcf_yield is not None
            and fcf_yield > float(config.get("maximum_plausible_fcf_yield_pct", 50.0))
        )
        or (
            price is not None
            and price > 0
            and latest_actual_eps is not None
            and latest_actual_eps > 2.0 * price
        )
    )
    if unit_anomaly:
        hard_fail.append("unit_mismatch_suspected")

    if cyclicality > 2 and normalized_metric is None:
        nonblocking_review.append("mid_cycle_normalization_required")
        deep_dive_requirements.append("mid_cycle_normalization_required")

    estimate_mode = mode in ESTIMATE_MODES
    min_analysts = int(config.get("minimum_discovery_analyst_count", 2))
    if forward.get("valid") is not True:
        missing_discovery.extend(list(forward.get("reasons") or ["forward_valuation_invalid"]))
    if per_share_growth is None:
        missing_discovery.append("per_share_growth_unavailable")
    if estimate_mode and (analyst_count is None or analyst_count < min_analysts):
        missing_discovery.append("estimate_breadth_below_discovery_minimum")

    all_fundamentals = {
        "revenue_growth": revenue_growth,
        "per_share_growth": per_share_growth,
        "standard_fcf": fcf,
        "roic": roic,
        "forward_pe": forward_pe,
        "leverage": leverage,
        "dilution": dilution,
    }
    if estimate_mode:
        if revenue_growth is None:
            deep_dive_requirements.append("revenue_growth_to_verify")
        for key in ("standard_fcf", "roic", "leverage", "dilution"):
            if all_fundamentals[key] is None:
                deep_dive_requirements.append(f"{key}_to_verify")
    else:
        for key, value in all_fundamentals.items():
            if value is None:
                missing_discovery.append(f"{key}_unavailable")

    discovery_evaluable = not hard and not blocking_review and not missing_discovery

    # The prompt calls these figures guidelines rather than mechanical gates.
    if revenue_growth is not None and revenue_growth < float(config["minimum_revenue_growth_pct"]):
        guideline_misses.append("revenue_growth_below_guideline")
    if per_share_growth is not None and per_share_growth < float(
        config["minimum_per_share_growth_pct"]
    ):
        guideline_misses.append("per_share_growth_below_guideline")
    if roic is not None and roic < float(config["minimum_roic_pct"]):
        guideline_misses.append("roic_below_guideline")
    if leverage is not None and leverage > float(config["preferred_max_net_debt_to_ebitda"]):
        guideline_misses.append("leverage_above_guideline")

    # Only severe, economically disqualifying findings are broad-screen fails.
    if fcf is not None and fcf <= 0:
        hard_fail.append("non_positive_standard_fcf")
    if roic is not None and roic < 0:
        hard_fail.append("negative_roic")
    if (
        leverage is not None
        and leverage > float(config.get("hard_max_net_debt_to_ebitda", 4.0))
        # General-company net debt/EBITDA is meaningless for balance-sheet
        # businesses (mortgage REITs, banks, insurers, BDCs, MLPs, asset
        # managers): a mortgage REIT at 13x is normal, not a hard failure.
        # Those profiles are already routed to
        # sector_specific_valuation_required until sector metrics exist.
        and profile_type not in SECTOR_PROFILES
    ):
        hard_fail.append("excessive_leverage")
    if forward_pe is not None and forward_pe > float(
        config.get("maximum_forward_pe_for_economic_screen", 60.0)
    ):
        hard_fail.append("extreme_forward_valuation")
    if (
        revenue_growth is not None
        and revenue_growth < 0
        and per_share_growth is not None
        and per_share_growth < 0
    ):
        hard_fail.append("negative_forward_growth")

    normal_value = (
        (forward_pe is not None and forward_pe <= float(config["preferred_forward_pe"]))
        or (ev_to_fcf is not None and ev_to_fcf <= float(config["preferred_ev_to_fcf"]))
        or (fcf_yield is not None and fcf_yield >= float(config["preferred_fcf_yield_pct"]))
    )
    if estimate_mode:
        high_growth_exception = all(
            [
                forward_pe is not None
                and forward_pe <= float(config["high_growth_exception_max_forward_pe"]),
                per_share_growth is not None
                and per_share_growth >= float(config["high_growth_exception_growth_pct"]),
            ]
        )
    else:
        high_growth_exception = all(
            [
                forward_pe is not None
                and forward_pe <= float(config["high_growth_exception_max_forward_pe"]),
                per_share_growth is not None
                and per_share_growth >= float(config["high_growth_exception_growth_pct"]),
                roic is not None and roic >= 10,
                fcf is not None and fcf > 0,
                dilution is not None and dilution <= float(config["preferred_max_dilution_pct"]),
                leverage is not None
                and leverage <= float(config["preferred_max_net_debt_to_ebitda"]),
            ]
        )

    standard_growth_pass = per_share_growth is not None and per_share_growth >= float(
        config["minimum_per_share_growth_pct"]
    )
    near_miss = all(
        [
            normal_value,
            forward_pe is not None
            and forward_pe <= float(config.get("near_miss_max_forward_pe", 22.0)),
            per_share_growth is not None
            and per_share_growth >= float(config.get("near_miss_min_per_share_growth_pct", 8.0)),
            revenue_growth is None or revenue_growth >= 0,
        ]
    )
    economic_pass = normal_value and standard_growth_pass
    if forward_pe is not None and not normal_value and not high_growth_exception:
        hard_fail.append("valuation_not_supported_by_growth")

    exhaustion_reason = _text(row.get("enrichment_exhaustion_reason"))
    exhaustion_sources = row.get("enrichment_source_ids")
    exhaustion_evidenced = (
        _bool(row.get("enrichment_exhausted")) is True
        and bool(exhaustion_reason)
        and isinstance(exhaustion_sources, list)
        and bool(exhaustion_sources)
        and all(isinstance(value, str) and value.strip() for value in exhaustion_sources)
    )

    if hard:
        status = "excluded"
        selection_eligible = False
        resolution = "resolved"
    elif (blocking_review or missing_discovery) and exhaustion_evidenced:
        status = "unavailable_after_enrichment"
        selection_eligible = False
        resolution = "resolved"
    elif blocking_review or missing_discovery:
        status = "needs_enrichment"
        selection_eligible = False
        resolution = "unresolved"
    elif hard_fail:
        status = "screened_out"
        selection_eligible = False
        resolution = "resolved"
    elif high_growth_exception or economic_pass or near_miss:
        selection_eligible = True
        resolution = "resolved"
        if nonblocking_review:
            status = "sector_review_required"
        elif high_growth_exception and not normal_value:
            status = "passed_exception"
        elif near_miss and not economic_pass:
            status = "near_miss_review"
        else:
            status = "passed"
    else:
        status = "screened_out"
        selection_eligible = False
        resolution = "resolved"
        if not hard_fail:
            hard_fail.append("growth_and_valuation_combination_below_review_threshold")

    valuation_score = (
        max(0.0, 35.0 - min(float(forward_pe or 35.0), 100.0)) if forward_pe is not None else 0.0
    )
    if fcf_yield is not None:
        valuation_score += max(0.0, min(20.0, fcf_yield * 2.0))
    growth_score = max(0.0, min(35.0, per_share_growth or 0.0)) + max(
        0.0, min(15.0, revenue_growth or 0.0)
    )
    quality_score = max(0.0, min(20.0, roic or 0.0)) if roic is not None else 0.0
    dilution_score = (
        max(0.0, 10.0 - max(0.0, dilution or 0.0) * 2.0) if dilution is not None else 0.0
    )
    leverage_score = (
        max(0.0, 10.0 - max(0.0, leverage or 0.0) * 2.0) if leverage is not None else 0.0
    )
    breadth_score = min(10.0, float(analyst_count or 0) * 2.0)
    broad_score = (
        valuation_score
        + growth_score
        + quality_score
        + dilution_score
        + leverage_score
        + breadth_score
    )
    broad_score -= max(0, cyclicality - 2) * 2.0
    broad_score -= len(deep_dive_requirements) * float(
        config.get("missing_deep_dive_field_penalty", 1.5)
    )
    if nonblocking_review:
        broad_score -= float(config.get("sector_review_selection_penalty", 5.0))
    if near_miss and not economic_pass:
        broad_score -= float(config.get("near_miss_selection_penalty", 4.0))
    if per_share_growth is not None and per_share_growth > 100:
        broad_score -= 10.0  # likely base-effect or near-zero denominator; verify before ranking
    broad_score = max(0.0, broad_score)

    completeness_count = sum(value is not None for value in all_fundamentals.values())
    fundamental_complete = completeness_count == len(all_fundamentals)
    enrichment_attempted = _bool(row.get("enrichment_attempted")) is True or any(
        value is not None
        for value in (forward_pe, per_share_growth, revenue_growth, fcf, roic, leverage, dilution)
    )
    enrichment_resolved = resolution == "resolved"
    priority_score = broad_score
    if high_growth_exception:
        priority_score += 6.0
    if status == "near_miss_review":
        priority_score -= 2.0
    if status == "sector_review_required":
        priority_score -= max(0, cyclicality - 2) * 2.0

    return {
        "symbol": symbol,
        "company_name": _text(row.get("company_name"))
        or _text(row.get("companyName"))
        or _text(row.get("name")),
        "exchange": exchange,
        "sector": _text(row.get("sector")),
        "industry": _text(row.get("industry")),
        "candidate_generation_mode": mode,
        "decision": {
            "status": status,
            "preselection_status": status,
            "hard_reasons": sorted(set(hard)),
            "review_reasons": sorted(set(blocking_review + nonblocking_review + missing_discovery)),
            "blocking_review_reasons": sorted(set(blocking_review + missing_discovery)),
            "guideline_misses": sorted(set(guideline_misses)),
            "screen_fail_reasons": sorted(set(hard_fail)),
            "deep_dive_requirements": sorted(set(deep_dive_requirements)),
            "exception_admitted": high_growth_exception and not normal_value,
            "selection_eligible": selection_eligible,
            "resolution": resolution,
            "enrichment_exhausted": exhaustion_evidenced,
            "enrichment_exhaustion_reason": exhaustion_reason,
            "enrichment_source_ids": exhaustion_sources
            if isinstance(exhaustion_sources, list)
            else [],
        },
        "broad_score": round(broad_score, 4) if discovery_evaluable else None,
        "deep_dive_priority_score": round(priority_score, 4)
        if discovery_evaluable and selection_eligible
        else None,
        "discovery_evaluable": discovery_evaluable,
        "selection_eligible": selection_eligible,
        "enrichment_attempted": enrichment_attempted,
        "enrichment_resolved": enrichment_resolved,
        "fundamental_completeness_count": completeness_count,
        "fundamental_complete": fundamental_complete,
        "metrics": {
            "price": price,
            "market_cap": market_cap,
            "average_daily_dollar_volume": adv,
            "average_daily_dollar_volume_method": liquidity.get("method"),
            "average_volume": liquidity.get("average_volume"),
            "average_volume_period_days": liquidity.get("period_days"),
            "liquidity_source_ids": liquidity.get("source_ids", []),
            "liquidity_valid_for_screen": liquidity.get("valid_for_screen"),
            "liquidity_validation_reasons": liquidity.get("reasons", []),
            "revenue_growth_pct": revenue_growth,
            "per_share_growth_pct": per_share_growth,
            "standard_fcf": fcf,
            "roic_pct": roic,
            "forward_pe": forward_pe,
            "forward_eps": forward.get("forward_eps"),
            "forward_pe_period": forward.get("period"),
            "forward_fiscal_year": forward.get("fiscal_year"),
            "forward_period_end": forward.get("period_end"),
            "forward_horizon_days": forward.get("horizon_days"),
            "forward_metric_origin": forward.get("origin"),
            "forward_estimate_as_of": forward.get("estimate_as_of"),
            "forward_estimate_source_ids": forward.get("source_ids", []),
            "forward_eps_dispersion_pct": forward.get("dispersion_pct"),
            "forward_validation_reasons": forward.get("reasons", []),
            "ev_to_fcf": ev_to_fcf,
            "fcf_yield_pct": fcf_yield,
            "dilution_pct": dilution,
            "net_debt_to_ebitda": leverage,
            "analyst_count": analyst_count,
            "cyclicality_score": cyclicality,
            "growth_pattern": _text(row.get("growth_pattern")),
            "sector_profile_type": profile_type,
        },
    }


def _canonical_line(row: Mapping[str, Any]) -> str:
    return json.dumps(dict(row), ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"


def _merge_pool_rows(
    universe_rows: Sequence[Mapping[str, Any]], pool_rows: Sequence[Mapping[str, Any]]
) -> tuple[list[dict[str, Any]], list[str]]:
    universe_index = {_symbol(row): dict(row) for row in universe_rows if _symbol(row) != "UNKNOWN"}
    merged: list[dict[str, Any]] = []
    missing: list[str] = []
    seen: set[str] = set()
    for raw in pool_rows:
        symbol = _symbol(raw)
        if symbol in seen:
            raise ScreenError(f"candidate pool contains duplicate symbol {symbol}")
        seen.add(symbol)
        base = universe_index.get(symbol)
        if base is None:
            missing.append(symbol)
            merged.append(dict(raw))
            continue
        combined = dict(base)
        combined.update(dict(raw))
        combined["symbol"] = symbol
        merged.append(combined)
    return merged, sorted(missing)


def _enrichment_queue(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Return only unresolved rows, ordered by GARP information value.

    Liquidity is a tiebreaker, not the main ranking axis. A name with a credible
    forward valuation/growth combination is enriched before a liquid but
    economically implausible base-effect name.
    """
    queue: list[dict[str, Any]] = []
    for row in rows:
        if row.get("enrichment_resolved") is True:
            continue
        status = _text(_mapping(row.get("decision")).get("status")) or "needs_enrichment"
        metrics = _mapping(row.get("metrics"))
        forward_pe = _number(metrics.get("forward_pe"))
        per_share_growth = _number(metrics.get("per_share_growth_pct"))
        revenue_growth = _number(metrics.get("revenue_growth_pct"))
        analyst_count = _integer(metrics.get("analyst_count")) or 0
        cyclicality = _integer(metrics.get("cyclicality_score")) or 1
        reasons = _mapping(row.get("decision")).get("review_reasons") or []

        score = 0.0
        if forward_pe is not None:
            score += max(-20.0, 35.0 - min(forward_pe, 80.0))
        else:
            score -= 12.0
        if per_share_growth is not None:
            score += max(-10.0, min(35.0, per_share_growth))
            if per_share_growth > 100:
                score -= 12.0
        else:
            score -= 12.0
        if revenue_growth is not None:
            score += max(-10.0, min(15.0, revenue_growth))
        score += min(10.0, analyst_count * 1.5)
        score -= max(0, cyclicality - 2) * 2.0
        score -= len(reasons) * 1.5

        queue.append(
            {
                "symbol": row.get("symbol"),
                "status": status,
                "reasons": reasons,
                "enrichment_priority_score": round(score, 4),
                "forward_pe": forward_pe,
                "per_share_growth_pct": per_share_growth,
                "revenue_growth_pct": revenue_growth,
                "analyst_count": analyst_count,
                "cyclicality_score": cyclicality,
                "growth_pattern": _text(row.get("growth_pattern")),
                "average_daily_dollar_volume": metrics.get("average_daily_dollar_volume"),
                "fundamental_completeness_count": row.get("fundamental_completeness_count"),
            }
        )
    queue.sort(
        key=lambda row: (
            -float(row.get("enrichment_priority_score") or 0.0),
            -int(row.get("analyst_count") or 0),
            -float(row.get("average_daily_dollar_volume") or 0.0),
            str(row.get("symbol") or ""),
        )
    )
    return queue


def _validate_candidate_pool_scope(
    *,
    candidate_generation_mode: str,
    universe_rows: Sequence[Mapping[str, Any]],
    candidate_rows: Sequence[Mapping[str, Any]],
    candidate_pool_covers_in_scope: bool,
    discovery_audit: Mapping[str, Any] | None,
    requested_min_market_cap: float,
    requested_max_market_cap: float,
) -> tuple[bool, str, dict[str, Any], list[str]]:
    """Verify what population the economic candidate pool represents.

    Full-universe mode must cover every in-scope listing.  A bounded discovery
    pool may support a final *scoped* ranking only when its generation audit is
    reproducible, uses validated average liquidity, and its stratification plan
    spans the user's full requested market-cap range.  A convenient single band
    is not an acceptable substitute for the user's request.
    """
    audit = dict(discovery_audit or {})
    candidate_symbols = sorted(
        {_symbol(row) for row in candidate_rows if _symbol(row) != "UNKNOWN"}
    )
    universe_symbols = sorted({_symbol(row) for row in universe_rows if _symbol(row) != "UNKNOWN"})
    reasons: list[str] = []

    if candidate_generation_mode == "full_universe_fundamentals":
        valid = candidate_pool_covers_in_scope
        if not valid:
            reasons.append("full-universe candidate pool does not cover every in-scope listing")
        return (
            valid,
            "full_listing_universe",
            {
                "valid": valid,
                "selection_method": "full_universe_fundamentals",
                "input_row_count": len(universe_rows),
                "selected_count": len(candidate_rows),
                "selected_symbols": candidate_symbols,
                "coverage_plan": {
                    "coverage_plan_valid": valid,
                    "user_requested_range_spanned": valid,
                },
            },
            reasons,
        )

    if candidate_generation_mode == "sharded_snapshot":
        verification = _mapping(audit.get("snapshot_verification"))
        digest = _text(verification.get("snapshot_verification_digest"))
        classifications = _mapping(audit.get("snapshot_classification_totals"))
        classified_total = sum(
            value for raw in classifications.values() if (value := _integer(raw)) is not None
        )
        economic_attempt_count = _integer(audit.get("economic_attempt_count"))
        evaluable_count = _integer(audit.get("economically_evaluable_count"))
        input_count = _integer(audit.get("input_row_count"))
        selected_count = _integer(audit.get("selected_count"))
        declared_symbols = sorted(
            str(value).upper()
            for value in (audit.get("selected_symbols") or [])
            if str(value).strip()
        )
        source_ids = audit.get("source_ids")
        target_pool_size = _integer(audit.get("target_pool_size"))
        preliminary_pool_count = _integer(audit.get("preliminary_pool_count"))
        eligible_pool_exhausted = audit.get("eligible_pool_exhausted") is True
        runtime = _mapping(audit.get("runtime"))
        expected_runtime = runtime_metadata()

        if audit.get("selection_method") != "sharded_snapshot_multilane":
            reasons.append("sharded-snapshot audit has an incompatible selection_method")
        if audit.get("valid") is not True:
            reasons.append("sharded-snapshot generation audit is not valid")
        if input_count != len(universe_rows):
            reasons.append("sharded-snapshot input_row_count does not match frozen universe")
        if economic_attempt_count != len(universe_rows):
            reasons.append("sharded-snapshot economic attempts do not cover frozen universe")
        if classified_total != len(universe_rows):
            reasons.append("sharded-snapshot classifications do not cover frozen universe")
        allowed_classifications = {
            "evaluable",
            "no_estimates",
            "negative_eps",
            "unit_mismatch",
            "excluded",
        }
        if set(classifications) - allowed_classifications:
            reasons.append("sharded-snapshot audit has an unknown classification")
        if evaluable_count is None or evaluable_count < len(candidate_rows):
            reasons.append("sharded-snapshot evaluable count is smaller than its final pool")
        if any(row.get("snapshot_classification") != "evaluable" for row in candidate_rows):
            reasons.append("sharded-snapshot final pool contains a non-evaluable row")
        if any(row.get("quality_probe_attempted") is not True for row in candidate_rows):
            reasons.append("sharded-snapshot final pool contains an unprobed row")
        if selected_count != len(candidate_rows) or declared_symbols != candidate_symbols:
            reasons.append("sharded-snapshot selected rows do not match its generation audit")
        if target_pool_size is None or not 30 <= target_pool_size <= 50:
            reasons.append("sharded-snapshot target_pool_size must be between 30 and 50")
        elif len(candidate_rows) < target_pool_size and not (
            eligible_pool_exhausted
            and preliminary_pool_count is not None
            and preliminary_pool_count < target_pool_size
        ):
            reasons.append("a short sharded-snapshot pool must prove eligible-pool exhaustion")
        if not (
            verification.get("ready_for_screening") is True
            and verification.get("classification_matches_universe") is True
            and _integer(verification.get("classified_total")) == len(universe_rows)
            and digest is not None
            and len(digest) == 64
        ):
            reasons.append("sharded-snapshot verification is missing or not screen-ready")
        if audit.get("snapshot_verification_digest") != digest:
            reasons.append("sharded-snapshot digest does not match its verification verdict")
        if (
            not isinstance(source_ids, list)
            or not source_ids
            or not all(isinstance(value, str) and value.strip() for value in source_ids)
        ):
            reasons.append("sharded-snapshot audit requires source_ids")
        if not _text(audit.get("artifact_path")) or not _text(audit.get("artifact_sha256")):
            reasons.append("sharded-snapshot audit requires a bound pool artifact")
        for key in (
            "skill_name",
            "skill_version",
            "schema_version",
            "contract_revision",
            "runtime_fingerprint",
        ):
            if runtime.get(key) != expected_runtime.get(key):
                reasons.append(f"sharded-snapshot runtime {key} is stale or mismatched")

        valid = not reasons
        normalized = dict(audit)
        normalized.update(
            {
                "valid": valid,
                "coverage_scope": "full_listing_universe",
                "actual_input_row_count": len(universe_rows),
                "actual_selected_count": len(candidate_rows),
                "actual_selected_symbols": candidate_symbols,
                "universe_symbol_count": len(universe_symbols),
            }
        )
        return valid, "full_listing_universe", normalized, reasons

    expected_methods = {
        "liquidity_stratified_estimates": {
            "sector_market_cap_stratified_liquidity",
            "sector_market_cap_stratified_validated_liquidity",
        },
        "provider_prefilter": {"provider_prefilter", "provider_screen"},
        "available_fundamentals": {
            "available_fundamentals",
            "sector_market_cap_stratified_validated_liquidity",
        },
        "user_supplied": {"user_supplied"},
    }
    method = (_text(audit.get("selection_method")) or "").lower()
    declared_symbols = sorted(
        str(value).upper() for value in (audit.get("selected_symbols") or []) if str(value).strip()
    )
    input_count = _integer(audit.get("input_row_count"))
    selected_count = _integer(audit.get("selected_count"))
    source_ids = audit.get("source_ids")
    artifact_sha = _text(audit.get("artifact_sha256"))
    artifact_path = _text(audit.get("artifact_path"))

    if method not in expected_methods.get(candidate_generation_mode, set()):
        reasons.append("candidate-pool generation audit has an incompatible selection_method")
    if input_count != len(universe_rows):
        reasons.append(
            "candidate-pool generation audit input_row_count does not match listing frame"
        )
    if selected_count != len(candidate_rows):
        reasons.append(
            "candidate-pool generation audit selected_count does not match candidate pool"
        )
    if declared_symbols != candidate_symbols:
        reasons.append(
            "candidate-pool generation audit selected_symbols do not match candidate pool"
        )
    if (
        not isinstance(source_ids, list)
        or not source_ids
        or not all(isinstance(value, str) and value.strip() for value in source_ids)
    ):
        reasons.append("candidate-pool generation audit requires source_ids")
    if not artifact_sha or not artifact_path:
        reasons.append("candidate-pool generation audit requires artifact_path and artifact_sha256")
    if audit.get("valid") is not True:
        reasons.append("candidate-pool generation audit is not valid")

    runtime = _mapping(audit.get("runtime"))
    expected_runtime = runtime_metadata()
    for key in (
        "skill_name",
        "skill_version",
        "schema_version",
        "contract_revision",
        "runtime_fingerprint",
    ):
        if runtime.get(key) != expected_runtime.get(key):
            reasons.append(f"candidate-pool generation runtime {key} is stale or mismatched")

    if candidate_generation_mode == "provider_prefilter":
        if audit.get("provider_exhausted") is not True:
            reasons.append("provider-prefilter audit requires provider_exhausted=true")
        coverage_plan = _mapping(audit.get("coverage_plan"))
        if coverage_plan.get("multi_lane_provider_prefilter") is not True:
            reasons.append("provider-prefilter audit must combine multiple opportunity lanes")
        if (_integer(audit.get("lane_coverage_count")) or 0) < 3:
            reasons.append(
                "provider-prefilter audit requires at least three represented opportunity lanes"
            )
        if audit.get("pool_adequate") is not True:
            reasons.append(
                "provider-prefilter pool does not meet the minimum breadth or exhaustion rule"
            )
        liquidity_validation = _mapping(audit.get("liquidity_validation"))
        if liquidity_validation.get("basis_validated") is not True:
            reasons.append("provider-prefilter liquidity basis is not validated")

    if candidate_generation_mode in {"liquidity_stratified_estimates", "available_fundamentals"}:
        liquidity_validation = _mapping(audit.get("liquidity_validation"))
        if liquidity_validation.get("basis_validated") is not True:
            reasons.append("discovery-pool liquidity basis is not validated")
        if (_integer(liquidity_validation.get("minimum_window_days")) or 0) < int(
            DEFAULTS.get("minimum_average_volume_period_days", 20)
        ):
            reasons.append("discovery-pool liquidity window is below the minimum")

        coverage_plan = _mapping(audit.get("coverage_plan"))
        if coverage_plan.get("coverage_plan_valid") is not True:
            reasons.append("discovery-pool coverage plan is not valid")
        if coverage_plan.get("user_requested_range_spanned") is not True:
            reasons.append("discovery pool does not span the user-requested market-cap range")
        if coverage_plan.get("market_cap_buckets_cover_user_requested_range") is not True:
            reasons.append(
                "discovery-pool market-cap buckets do not cover the user-requested range"
            )
        if coverage_plan.get("single_band_only") is True:
            reasons.append("single-band discovery pool cannot stand in for the requested universe")

        scope = _mapping(audit.get("scope"))
        if _number(scope.get("user_requested_min_market_cap")) != requested_min_market_cap:
            reasons.append("discovery audit requested lower market-cap bound does not match")
        if _number(scope.get("user_requested_max_market_cap")) != requested_max_market_cap:
            reasons.append("discovery audit requested upper market-cap bound does not match")
        if scope.get("user_requested_scope_complete") is not True:
            reasons.append("discovery audit does not preserve the user-requested scope")
        if scope.get("scope_valid") is not True:
            reasons.append("discovery audit scope is invalid")

    scope_name = {
        "liquidity_stratified_estimates": "stratified_discovery_pool",
        "provider_prefilter": "provider_prefilter",
        "available_fundamentals": "bounded_available_fundamentals",
        "user_supplied": "user_supplied",
    }.get(candidate_generation_mode, "bounded_candidate_pool")
    valid = not reasons
    normalized = dict(audit)
    normalized.update(
        {
            "valid": valid,
            "coverage_scope": scope_name,
            "actual_input_row_count": len(universe_rows),
            "actual_selected_count": len(candidate_rows),
            "actual_selected_symbols": candidate_symbols,
            "universe_symbol_count": len(universe_symbols),
        }
    )
    return valid, scope_name, normalized, reasons


def _selection_lane(row: Mapping[str, Any]) -> str:
    """Assign one deterministic research lane to an economically reviewable row.

    Lanes prevent a low-cost global sort from filling the entire deep-dive budget
    with one style.  They preserve the prompt's four useful opportunity types:
    core GARP, high-growth exceptions, quality near misses, and cyclicals that
    require mid-cycle normalization.
    """
    decision = _mapping(row.get("decision"))
    preselection = (
        _text(decision.get("preselection_status")) or _text(decision.get("status")) or ""
    ).lower()
    metrics = _mapping(row.get("metrics"))
    cyclicality = int(_number(metrics.get("cyclicality_score")) or 1)
    if cyclicality >= 3 or "mid_cycle_normalization_required" in set(
        decision.get("deep_dive_requirements") or []
    ):
        return "cyclical_normalization"
    if preselection == "passed_exception" or decision.get("exception_admitted") is True:
        return "high_growth_exception"
    if preselection == "near_miss_review":
        return "quality_near_miss"
    growth_pattern = (
        _text(metrics.get("growth_pattern")) or _text(row.get("growth_pattern")) or ""
    ).lower()
    if growth_pattern == "trough_recovery":
        # FY1 sits below the latest actual: the FY1->FY3 CAGR is a recovery,
        # not compounding growth, so the name is reviewed as a near miss.
        return "quality_near_miss"
    return "core_garp"


def _select_multilane(
    selectable: Sequence[Mapping[str, Any]],
    *,
    limit: int,
    config: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Select a diversified deep-dive set using deterministic lane quotas.

    Quotas are minimum targets, not hard reservations: unused slots are
    backfilled by global priority.  A sector cap prevents one industry from
    consuming the entire research budget unless there are no alternatives.
    """
    ranked = [dict(row) for row in selectable]
    ranked.sort(
        key=lambda row: (
            -float(row.get("deep_dive_priority_score") or 0.0),
            -float(row.get("broad_score") or 0.0),
            -int(row.get("fundamental_completeness_count") or 0),
            -float(_mapping(row.get("metrics")).get("analyst_count") or 0),
            str(row.get("symbol") or ""),
        )
    )
    quotas = {
        "core_garp": int(config.get("selection_lane_quota_core_garp", 2)),
        "high_growth_exception": int(config.get("selection_lane_quota_high_growth", 1)),
        "quality_near_miss": int(config.get("selection_lane_quota_near_miss", 1)),
        "cyclical_normalization": int(config.get("selection_lane_quota_cyclical", 1)),
    }
    max_per_sector = max(1, int(config.get("maximum_selected_per_sector", 2)))
    selected: list[dict[str, Any]] = []
    selected_symbols: set[str] = set()
    sector_counts: dict[str, int] = {}
    lane_counts: dict[str, int] = {key: 0 for key in quotas}

    def can_add(row: Mapping[str, Any], *, ignore_sector_cap: bool = False) -> bool:
        symbol = str(row.get("symbol") or "")
        sector = (_text(row.get("sector")) or "UNKNOWN").upper()
        if not symbol or symbol in selected_symbols:
            return False
        return ignore_sector_cap or sector_counts.get(sector, 0) < max_per_sector

    def add(row: Mapping[str, Any]) -> None:
        item = dict(row)
        lane = _selection_lane(item)
        item["selection_lane"] = lane
        selected.append(item)
        selected_symbols.add(str(item.get("symbol") or ""))
        sector = (_text(item.get("sector")) or "UNKNOWN").upper()
        sector_counts[sector] = sector_counts.get(sector, 0) + 1
        lane_counts[lane] = lane_counts.get(lane, 0) + 1

    plan_total = sum(max(0, value) for value in quotas.values())
    if limit < plan_total:
        # Budget smaller than the lane plan (e.g. 3 deep dives vs a 2/1/1/1
        # plan): a lane-first fill would hand every slot to the first lanes in
        # plan order and never reach the cyclical lane even when its names
        # rank highest. Walk the priority order instead and treat each lane
        # quota as a cap, so every lane's best name competes on priority.
        for row in ranked:
            if len(selected) >= limit:
                break
            lane = _selection_lane(row)
            if lane_counts.get(lane, 0) >= max(0, quotas[lane]):
                continue
            if can_add(row):
                add(row)
    else:
        for lane in (
            "core_garp",
            "high_growth_exception",
            "quality_near_miss",
            "cyclical_normalization",
        ):
            target = max(0, quotas[lane])
            for row in ranked:
                if len(selected) >= limit or lane_counts.get(lane, 0) >= target:
                    break
                if _selection_lane(row) == lane and can_add(row):
                    add(row)

    for row in ranked:
        if len(selected) >= limit:
            break
        if can_add(row):
            add(row)

    # Do not leave budget unused solely because all remaining names share a
    # sector.  The cap is a diversification preference, not a hidden filter.
    for row in ranked:
        if len(selected) >= limit:
            break
        if can_add(row, ignore_sector_cap=True):
            add(row)

    return selected, lane_counts


def run_layered(
    universe_rows: Sequence[Mapping[str, Any]],
    candidate_rows: Sequence[Mapping[str, Any]],
    config: Mapping[str, Any],
    *,
    analysis_as_of: str,
    universe_source_ids: Sequence[str],
    candidate_source_ids: Sequence[str],
    candidate_generation_mode: str,
    retrieval_min_market_cap: float,
    retrieval_max_market_cap: float,
    requested_min_market_cap: float | None = None,
    requested_max_market_cap: float | None = None,
    retrieval_scope_explicit: bool = True,
    scope_override_authorized: bool = False,
    scope_reduction_reason: str | None = None,
    user_scope_evidence: str | None = None,
    candidate_pool_exhausted: bool = False,
    provider_reported_total: int | None = None,
    pages_fetched: int | None = None,
    pagination_exhausted: bool = False,
    band_audit: Sequence[Mapping[str, Any]] | None = None,
    discovery_audit: Mapping[str, Any] | None = None,
) -> tuple[
    list[dict[str, Any]], list[dict[str, Any]], dict[str, Any], list[str], list[dict[str, Any]]
]:
    if candidate_generation_mode not in CANDIDATE_GENERATION_MODES:
        raise ScreenError(f"invalid candidate generation mode: {candidate_generation_mode}")
    if not universe_rows:
        raise ScreenError("listing universe is empty")

    universe_decisions = [_listing_decision(row, config) for row in universe_rows]
    merged_candidates, pool_not_in_universe = _merge_pool_rows(universe_rows, candidate_rows)
    candidate_decisions = [
        _candidate_decision(row, config, candidate_generation_mode, analysis_as_of)
        for row in merged_candidates
    ]

    selectable = [
        row
        for row in candidate_decisions
        if row.get("selection_eligible") is True
        and row.get("discovery_evaluable") is True
        and row.get("deep_dive_priority_score") is not None
    ]
    limit = int(config["max_deep_dive_candidates"])
    selected_rows, selected_lane_counts = _select_multilane(selectable, limit=limit, config=config)
    selected = {str(row["symbol"]) for row in selected_rows}
    selected_lane_by_symbol = {
        str(row["symbol"]): str(row.get("selection_lane")) for row in selected_rows
    }
    selected_set_payload = {
        "analysis_as_of": analysis_as_of,
        "max_deep_dive_candidates": limit,
        "selected_symbols": sorted(selected),
    }
    selected_set_sha256 = hashlib.sha256(
        json.dumps(selected_set_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()

    # Every economically evaluable row receives a broad-screen disposition.
    for row in candidate_decisions:
        decision = _mapping(row.get("decision"))
        status = _text(decision.get("status")) or "needs_enrichment"
        if row.get("selection_eligible") is True:
            decision["preselection_status"] = status
            decision["status"] = "selected" if row["symbol"] in selected else "deferred_by_budget"
            if row["symbol"] in selected:
                lane = selected_lane_by_symbol.get(row["symbol"], _selection_lane(row))
                decision["selection_lane"] = lane
                decision["selection_reason"] = (
                    f"selected by deterministic multi-lane deep-dive plan: {lane}"
                )
            else:
                decision["selection_lane"] = _selection_lane(row)
                decision["selection_reason"] = (
                    "economically reviewable but outside the bounded multi-lane deep-dive budget"
                )
            row["decision"] = decision

    universe_counts: dict[str, int] = {}
    listing_complete = 0
    in_scope_count = 0
    for row in universe_decisions:
        status = row["listing_decision"]["status"]
        universe_counts[status] = universe_counts.get(status, 0) + 1
        listing_complete += int(bool(row["listing_data_complete"]))
        in_scope_count += int(status in {"in_scope", "liquidity_review"})

    discovery_evaluable_count = sum(
        int(row.get("discovery_evaluable") is True) for row in candidate_decisions
    )
    selection_eligible_count = sum(
        int(row.get("selection_eligible") is True) for row in candidate_decisions
    )
    fundamental_complete_count = sum(
        int(row.get("fundamental_complete") is True) for row in candidate_decisions
    )
    enrichment_attempted_count = sum(
        int(row.get("enrichment_attempted") is True) for row in candidate_decisions
    )
    enrichment_resolved_count = sum(
        int(row.get("enrichment_resolved") is True) for row in candidate_decisions
    )

    queue = _enrichment_queue(candidate_decisions)
    unresolved_count = len(queue)
    all_rows_resolved = unresolved_count == 0 and enrichment_resolved_count == len(
        candidate_decisions
    )

    requested_min = float(
        requested_min_market_cap
        if requested_min_market_cap is not None
        else DEFAULT_REQUESTED_MIN_MARKET_CAP
    )
    requested_max = float(
        requested_max_market_cap
        if requested_max_market_cap is not None
        else DEFAULT_REQUESTED_MAX_MARKET_CAP
    )
    retrieval_covers_requested = (
        retrieval_min_market_cap <= requested_min and retrieval_max_market_cap >= requested_max
    )

    normalized_bands = [dict(row) for row in (band_audit or []) if isinstance(row, Mapping)]
    normalized_band_ranges: list[tuple[float, float]] = []
    bands_well_formed = bool(normalized_bands)
    disallowed_listing_filter_terms = (
        "share volume",
        "volume>",
        "volume >=",
        "avgvolume",
        "average volume",
        '"min_volume"',
        '"minimum_volume"',
        '"average_volume"',
        '"avg_volume"',
    )

    def retrieval_filter_text(value: Any) -> str:
        if isinstance(value, Mapping):
            return json.dumps(dict(value), sort_keys=True, separators=(",", ":")).lower()
        if isinstance(value, list):
            return json.dumps(value, sort_keys=True, separators=(",", ":")).lower()
        return (_text(value) or "").lower()

    provider_listing_prefiltered = any(
        any(
            term in retrieval_filter_text(row.get("retrieval_filters"))
            for term in disallowed_listing_filter_terms
        )
        for row in normalized_bands
    )
    for row in normalized_bands:
        band_min = _number(row.get("min_market_cap"))
        band_max = _number(row.get("max_market_cap"))
        rows_fetched = _integer(row.get("rows_fetched"))
        if (
            band_min is None
            or band_max is None
            or band_min >= band_max
            or rows_fetched is None
            or rows_fetched < 0
            or _bool(row.get("provider_exhausted")) is not True
        ):
            bands_well_formed = False
            continue
        normalized_band_ranges.append((band_min, band_max))
    normalized_band_ranges.sort()
    bands_cover_requested = False
    if bands_well_formed and normalized_band_ranges:
        cursor = retrieval_min_market_cap
        bands_cover_requested = True
        for band_min, band_max in normalized_band_ranges:
            if band_max < retrieval_min_market_cap or band_min > retrieval_max_market_cap:
                continue
            clipped_min = max(band_min, retrieval_min_market_cap)
            clipped_max = min(band_max, retrieval_max_market_cap)
            if clipped_min > cursor:
                bands_cover_requested = False
                break
            cursor = max(cursor, clipped_max)
        bands_cover_requested = bands_cover_requested and cursor >= retrieval_max_market_cap
    bands_verified = bands_well_formed and bands_cover_requested
    pagination_verified = bool(pagination_exhausted or bands_verified)
    provider_total_consistent = (
        provider_reported_total is None or len(universe_rows) >= provider_reported_total
    )
    enumeration_verified = pagination_verified and provider_total_consistent

    scope_reduced = not retrieval_covers_requested
    scope_reduction_disclosed = (not scope_reduced) or bool(_text(scope_reduction_reason))
    executed_scope_complete = bool(retrieval_scope_explicit and enumeration_verified)
    user_requested_scope_complete = bool(
        retrieval_covers_requested and executed_scope_complete and not provider_listing_prefiltered
    )
    scope_reasons: list[str] = []
    if not retrieval_scope_explicit:
        scope_reasons.append("retrieval_scope_not_explicitly_recorded")
    if scope_reduced:
        scope_reasons.append("executed_scope_narrower_than_user_request")
        if not scope_reduction_disclosed:
            scope_reasons.append("scope_reduction_reason_required")
        if not scope_override_authorized:
            scope_reasons.append("reduced_scope_requires_explicit_user_authorization")
    if not enumeration_verified:
        scope_reasons.append("executed_scope_enumeration_not_verified")
    if provider_listing_prefiltered:
        scope_reasons.append("provider_listing_query_applied_share_volume_prefilter")
    if provider_reported_total is not None and not provider_total_consistent:
        scope_reasons.append("provider_reported_total_exceeds_rows_fetched")

    listing_coverage_pct = listing_complete / len(universe_decisions) * 100.0
    fundamental_pct = (
        fundamental_complete_count / len(candidate_decisions) * 100.0
        if candidate_decisions
        else 0.0
    )
    discovery_pct = (
        discovery_evaluable_count / len(candidate_decisions) * 100.0 if candidate_decisions else 0.0
    )
    resolution_pct = (
        enrichment_resolved_count / len(candidate_decisions) * 100.0 if candidate_decisions else 0.0
    )

    in_scope_symbols = {
        str(row.get("symbol") or "").upper()
        for row in universe_decisions
        if _text(_mapping(row.get("listing_decision")).get("status"))
        in {"in_scope", "liquidity_review"}
    }
    candidate_symbols = {str(row.get("symbol") or "").upper() for row in candidate_decisions}
    missing_in_scope_candidate_symbols = sorted(in_scope_symbols - candidate_symbols)
    candidate_pool_covers_in_scope = not missing_in_scope_candidate_symbols
    pool_scope_verified, conclusion_scope, normalized_discovery_audit, pool_scope_reasons = (
        _validate_candidate_pool_scope(
            candidate_generation_mode=candidate_generation_mode,
            universe_rows=universe_rows,
            candidate_rows=merged_candidates,
            candidate_pool_covers_in_scope=candidate_pool_covers_in_scope,
            discovery_audit=discovery_audit,
            requested_min_market_cap=requested_min,
            requested_max_market_cap=requested_max,
        )
    )
    if scope_reduced and conclusion_scope == "full_listing_universe":
        conclusion_scope = "executed_listing_universe"
    if provider_listing_prefiltered and conclusion_scope in {
        "full_listing_universe",
        "stratified_discovery_pool",
    }:
        conclusion_scope = "provider_prefilter"
    bounded_sampling_ready = bool(
        conclusion_scope
        in {
            "stratified_discovery_pool",
            "provider_prefilter",
            "bounded_available_fundamentals",
            "user_supplied",
        }
        and pool_scope_verified
        and retrieval_covers_requested
        and not scope_reduced
    )
    screening_scope_ready = bool(
        user_requested_scope_complete
        or bounded_sampling_ready
        or (scope_override_authorized and executed_scope_complete)
    )
    # Full enumeration and bounded-pool readiness are separate concepts.
    scope_complete = user_requested_scope_complete
    candidate_pool_exhaustion_verified = bool(
        candidate_pool_exhausted
        and all_rows_resolved
        and pool_scope_verified
        and screening_scope_ready
    )

    enrichment_status = "complete" if candidate_pool_exhaustion_verified else "pending"
    pool_complete = enrichment_status == "complete"

    candidate_counts: dict[str, int] = {}
    for row in candidate_decisions:
        status = row["decision"]["status"]
        candidate_counts[status] = candidate_counts.get(status, 0) + 1

    marketwide_snapshot_exhausted = bool(
        candidate_generation_mode == "sharded_snapshot" and pool_scope_verified
    )
    if selected and pool_complete:
        candidate_pool_status = "sufficient"
    elif selected:
        candidate_pool_status = "sufficient_pending_enrichment"
    elif pool_complete and (discovery_evaluable_count > 0 or marketwide_snapshot_exhausted):
        candidate_pool_status = (
            "no_qualifying_candidates"
            if conclusion_scope == "full_listing_universe"
            else "no_qualifying_candidates_in_bounded_pool"
        )
    else:
        candidate_pool_status = "insufficient_data"

    selection_outcome = {
        "sufficient": "selected",
        "sufficient_pending_enrichment": "selected_pending_enrichment",
        "no_qualifying_candidates": "no_candidates",
        "no_qualifying_candidates_in_bounded_pool": "no_candidates_in_bounded_pool",
        "insufficient_data": "insufficient_data",
    }[candidate_pool_status]

    if not candidate_decisions and marketwide_snapshot_exhausted:
        next_action = "publish_no_candidates"
    elif not candidate_decisions:
        next_action = "build_discovery_pool"
    elif not pool_scope_verified:
        next_action = "verify_candidate_pool_generation"
    elif queue:
        next_action = "enrich_queue"
    elif not candidate_pool_exhausted:
        next_action = "verify_candidate_pool_exhaustion"
    elif selected:
        next_action = "proceed_to_deep_dive"
    else:
        next_action = "publish_no_candidates"

    audit = {
        "audit_schema_version": AUDIT_SCHEMA_VERSION,
        "contract_revision": CONTRACT_REVISION,
        "runtime": runtime_metadata(),
        "conclusion_scope": conclusion_scope,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "analysis_as_of": analysis_as_of,
        "candidate_generation_mode": candidate_generation_mode,
        "candidate_pool_status": candidate_pool_status,
        "selection_outcome": selection_outcome,
        "selected_symbols": sorted(selected),
        "deep_dive_plan": {
            "selected_symbols": sorted(selected),
            "selected_count": len(selected),
            "all_selected_must_be_resolved": True,
            "budget_locked": True,
            "budget_change_requires_rescreen": True,
            "user_confirmation_required": False,
            "user_continue_instruction_allowed": False,
            "selected_set_is_committed": True,
            "max_deep_dive_candidates": limit,
            "selected_set_sha256": selected_set_sha256,
            "commitment_payload": selected_set_payload,
            "selection_method": "deterministic_multi_lane",
            "lane_counts": selected_lane_counts,
            "maximum_selected_per_sector": int(config.get("maximum_selected_per_sector", 2)),
        },
        "filters": dict(config),
        "scope": {
            "requested_min_market_cap": requested_min,
            "requested_max_market_cap": requested_max,
            "user_requested_scope": {
                "min_market_cap": requested_min,
                "max_market_cap": requested_max,
                "source": "explicit_user_request" if scope_override_authorized else "skill_default",
            },
            "retrieval_min_market_cap": retrieval_min_market_cap,
            "retrieval_max_market_cap": retrieval_max_market_cap,
            "retrieval_scope_explicit": retrieval_scope_explicit,
            "scope_override_authorized": scope_override_authorized,
            "scope_reduced": scope_reduced,
            "scope_reduction_mode": (
                "user_authorized" if scope_override_authorized else "invalid_internal_narrowing"
            )
            if scope_reduced
            else "none",
            "scope_reduction_disclosed": scope_reduction_disclosed,
            "scope_reduction_reason": scope_reduction_reason,
            "user_scope_evidence": user_scope_evidence,
            "user_requested_scope_complete": user_requested_scope_complete,
            "executed_scope_complete": executed_scope_complete,
            "bounded_sampling_ready": bounded_sampling_ready,
            "screening_scope_ready": screening_scope_ready,
            "executed_scope": {
                "min_market_cap": retrieval_min_market_cap,
                "max_market_cap": retrieval_max_market_cap,
            },
            "scope_complete": scope_complete,
            "reasons": scope_reasons,
            "enumeration": {
                "verified": enumeration_verified,
                "provider_reported_total": provider_reported_total,
                "rows_fetched": len(universe_rows),
                "pages_fetched": pages_fetched,
                "pagination_exhausted": pagination_exhausted,
                "band_audit": normalized_bands,
                "bands_well_formed": bands_well_formed,
                "bands_cover_executed_range": bands_cover_requested,
                "bands_cover_requested_range": bands_cover_requested
                if user_requested_scope_complete
                else False,
                "bands_verified": bands_verified,
                "provider_listing_prefiltered": provider_listing_prefiltered,
                "full_listing_enumeration_verified": enumeration_verified
                and not provider_listing_prefiltered,
            },
        },
        "universe": {
            "row_count": len(universe_decisions),
            "decision_counts": universe_counts,
            "listing_data_complete_count": listing_complete,
            "listing_data_complete_pct": round(listing_coverage_pct, 4),
            "in_scope_count": in_scope_count,
            "source_ids": list(universe_source_ids),
        },
        "candidate_pool": {
            "row_count": len(candidate_decisions),
            "decision_counts": candidate_counts,
            "discovery_evaluable_count": discovery_evaluable_count,
            "discovery_evaluable_pct": round(discovery_pct, 4),
            "selection_eligible_count": selection_eligible_count,
            "selected_count": len(selected),
            "in_scope_covered_count": len(in_scope_symbols & candidate_symbols),
            "in_scope_missing_count": len(missing_in_scope_candidate_symbols),
            "in_scope_missing_symbols": missing_in_scope_candidate_symbols,
            "coverage_complete": pool_scope_verified,
            "coverage_scope": conclusion_scope,
            "listing_coverage_complete": candidate_pool_covers_in_scope,
            "generation_audit": normalized_discovery_audit,
            "generation_review_reasons": pool_scope_reasons,
            "fundamental_complete_count": fundamental_complete_count,
            "fundamental_complete_pct": round(fundamental_pct, 4),
            "source_ids": list(candidate_source_ids),
            "symbols_not_in_universe": pool_not_in_universe,
        },
        "enrichment": {
            "status": enrichment_status,
            "next_action": next_action,
            "discovery_pool_required": not bool(candidate_decisions),
            "attempted_count": enrichment_attempted_count,
            "resolved_count": enrichment_resolved_count,
            "unresolved_count": unresolved_count,
            "resolution_pct": round(resolution_pct, 4),
            "all_rows_resolved": all_rows_resolved,
            "maximum_attempts": int(config.get("maximum_enrichment_attempts", 60)),
            "candidate_pool_exhaustion_declared": candidate_pool_exhausted,
            "candidate_pool_exhausted": candidate_pool_exhaustion_verified,
            "candidate_pool_covers_in_scope": candidate_pool_covers_in_scope,
            "candidate_pool_scope_verified": pool_scope_verified,
            "conclusion_scope": conclusion_scope,
            "queue_count": len(queue),
            "queue_symbols": [str(row["symbol"]) for row in queue],
        },
        "coverage_interpretation": {
            "listing_universe_audited": True,
            "universe_enumeration_verified": enumeration_verified,
            "full_listing_enumeration_verified": enumeration_verified
            and not provider_listing_prefiltered,
            "provider_listing_prefiltered": provider_listing_prefiltered,
            "full_universe_fundamentals_claimed": candidate_generation_mode
            == "full_universe_fundamentals",
            "candidate_pool_fundamentals_only": candidate_generation_mode
            != "full_universe_fundamentals",
            "full_market_fundamental_coverage_is_not_a_completion_gate": True,
            "no_candidates_requires_zero_unresolved_rows_and_exhausted_pool": True,
            "bounded_pool_final_ranking_allowed_when_generation_is_audited": True,
            "market_wide_no_candidates_requires_full_listing_universe_coverage": True,
        },
        "row_count": len(candidate_decisions),
        "decision_counts": candidate_counts,
        "source_ids": list(dict.fromkeys(list(universe_source_ids) + list(candidate_source_ids))),
    }
    return universe_decisions, candidate_decisions, audit, sorted(selected), queue


def run(
    rows: Sequence[Mapping[str, Any]],
    config: Mapping[str, Any],
    *,
    analysis_as_of: str,
    source_ids: Sequence[str],
    universe_query_min_cap: float | None = None,
    universe_query_max_cap: float | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any], list[str], list[dict[str, Any]]]:
    """Backward-compatible in-memory full-fundamentals screen used by tests."""
    query_min = float(
        config["min_market_cap"] if universe_query_min_cap is None else universe_query_min_cap
    )
    query_max = float(
        config["max_market_cap"] if universe_query_max_cap is None else universe_query_max_cap
    )
    _, decisions, audit, selected, queue = run_layered(
        rows,
        rows,
        config,
        analysis_as_of=analysis_as_of,
        universe_source_ids=source_ids,
        candidate_source_ids=source_ids,
        candidate_generation_mode="full_universe_fundamentals",
        retrieval_min_market_cap=query_min,
        retrieval_max_market_cap=query_max,
        retrieval_scope_explicit=True,
        candidate_pool_exhausted=True,
        provider_reported_total=len(rows),
        pages_fetched=1,
        pagination_exhausted=True,
    )
    return decisions, audit, selected, queue


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit the full listing universe and screen a bounded economic candidate pool."
    )
    parser.add_argument("--input", type=Path, required=True, help="Full listing universe.")
    parser.add_argument(
        "--candidate-pool",
        type=Path,
        help="Enriched candidate pool; otherwise available rows are used.",
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--analysis-as-of", required=True)
    parser.add_argument(
        "--source-id",
        action="append",
        required=True,
        help="Universe/listing source ID; repeatable.",
    )
    parser.add_argument(
        "--candidate-source-id", action="append", help="Candidate/estimate source ID; repeatable."
    )
    parser.add_argument("--candidate-generation-mode", choices=sorted(CANDIDATE_GENERATION_MODES))
    parser.add_argument("--retrieval-min-market-cap", type=float)
    parser.add_argument("--retrieval-max-market-cap", type=float)
    parser.add_argument("--user-requested-min-market-cap", type=float)
    parser.add_argument("--user-requested-max-market-cap", type=float)
    parser.add_argument("--user-scope-override-authorized", action="store_true")
    parser.add_argument("--user-scope-evidence")
    parser.add_argument("--scope-reduction-reason")
    parser.add_argument(
        "--allow-reduced-scope",
        action="store_true",
        help="Deprecated alias; never implies user authorization",
    )
    parser.add_argument("--candidate-pool-exhausted", action="store_true")
    parser.add_argument("--provider-reported-total", type=int)
    parser.add_argument("--pages-fetched", type=int)
    parser.add_argument("--pagination-exhausted", action="store_true")
    parser.add_argument(
        "--band-audit",
        type=Path,
        help="JSON array of retrieval bands with provider_exhausted flags",
    )
    parser.add_argument(
        "--discovery-audit",
        type=Path,
        help="Generation audit for a bounded discovery/prefilter pool",
    )
    parser.add_argument("--config", type=Path)
    parser.add_argument("--max-deep-dives", type=int)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    raw_argv = list(argv) if argv is not None else sys.argv[1:]
    if "--version" in raw_argv:
        print(json.dumps(runtime_metadata(), sort_keys=True))
        return 0
    args = parse_args(raw_argv)
    try:
        datetime.fromisoformat(args.analysis_as_of.replace("Z", "+00:00"))
        universe_rows = _load_rows(args.input)
        config = dict(DEFAULTS)
        if args.config:
            extra = json.loads(args.config.read_text(encoding="utf-8"))
            if not isinstance(extra, Mapping):
                raise ScreenError("config must be an object")
            config.update(extra)
        if args.max_deep_dives is not None:
            if args.max_deep_dives <= 0:
                raise ScreenError("max deep dives must be positive")
            config["max_deep_dive_candidates"] = args.max_deep_dives

        if args.candidate_pool:
            candidate_rows = _load_rows(args.candidate_pool)
            mode = args.candidate_generation_mode or "provider_prefilter"
        else:
            candidate_rows = [
                row
                for row in universe_rows
                if any(
                    _metric(row, key) is not None
                    for key in (
                        "forward_pe",
                        "fy1_pe",
                        "ntm_pe",
                        "eps_growth_pct",
                        "forward_eps_growth_pct",
                    )
                )
            ]
            mode = args.candidate_generation_mode or (
                "full_universe_fundamentals"
                if len(candidate_rows) == len(universe_rows)
                else "available_fundamentals"
            )
        candidate_source_ids = args.candidate_source_id or args.source_id
        explicit_scope = (
            args.retrieval_min_market_cap is not None and args.retrieval_max_market_cap is not None
        )
        # Config files may tune the executed retrieval/screening range, but
        # cannot rewrite the user's default request. Only explicit authorized
        # CLI arguments may change the request scope.
        requested_min = float(DEFAULT_REQUESTED_MIN_MARKET_CAP)
        requested_max = float(DEFAULT_REQUESTED_MAX_MARKET_CAP)
        if (
            args.user_requested_min_market_cap is not None
            or args.user_requested_max_market_cap is not None
        ):
            if not args.user_scope_override_authorized or not args.user_scope_evidence:
                raise ScreenError(
                    "changing the user-requested scope requires --user-scope-override-authorized and --user-scope-evidence"
                )
            requested_min = float(
                args.user_requested_min_market_cap
                if args.user_requested_min_market_cap is not None
                else requested_min
            )
            requested_max = float(
                args.user_requested_max_market_cap
                if args.user_requested_max_market_cap is not None
                else requested_max
            )
        if requested_min >= requested_max:
            raise ScreenError("user-requested market-cap bounds are invalid")
        retrieval_min = (
            args.retrieval_min_market_cap
            if args.retrieval_min_market_cap is not None
            else float(config["min_market_cap"])
        )
        retrieval_max = (
            args.retrieval_max_market_cap
            if args.retrieval_max_market_cap is not None
            else float(config["max_market_cap"])
        )

        discovery_audit: dict[str, Any] = {}
        if args.discovery_audit:
            discovery_value = json.loads(args.discovery_audit.read_text(encoding="utf-8"))
            if not isinstance(discovery_value, Mapping):
                raise ScreenError("discovery audit must be a JSON object")
            discovery_audit = dict(discovery_value)

        band_audit_rows: list[dict[str, Any]] = []
        if args.band_audit:
            band_value = json.loads(args.band_audit.read_text(encoding="utf-8"))
            if not isinstance(band_value, list) or not all(
                isinstance(row, Mapping) for row in band_value
            ):
                raise ScreenError("band audit must be a JSON array of objects")
            band_audit_rows = [dict(row) for row in band_value]

        universe_decisions, candidate_decisions, audit, selected, queue = run_layered(
            universe_rows,
            candidate_rows,
            config,
            analysis_as_of=args.analysis_as_of,
            universe_source_ids=args.source_id,
            candidate_source_ids=candidate_source_ids,
            candidate_generation_mode=mode,
            retrieval_min_market_cap=retrieval_min,
            retrieval_max_market_cap=retrieval_max,
            requested_min_market_cap=requested_min,
            requested_max_market_cap=requested_max,
            retrieval_scope_explicit=explicit_scope,
            scope_override_authorized=args.user_scope_override_authorized,
            scope_reduction_reason=args.scope_reduction_reason,
            user_scope_evidence=args.user_scope_evidence,
            candidate_pool_exhausted=args.candidate_pool_exhausted,
            provider_reported_total=args.provider_reported_total,
            pages_fetched=args.pages_fetched,
            pagination_exhausted=args.pagination_exhausted,
            band_audit=band_audit_rows,
            discovery_audit=discovery_audit,
        )
        args.output_dir.mkdir(parents=True, exist_ok=True)
        universe_artifact = args.output_dir / "universe-audit-results.jsonl"
        candidate_artifact = args.output_dir / "broad-screen-results.jsonl"
        enrichment_artifact = args.output_dir / "enrichment-queue.json"
        universe_artifact.write_text(
            "".join(_canonical_line(row) for row in universe_decisions), encoding="utf-8"
        )
        candidate_artifact.write_text(
            "".join(_canonical_line(row) for row in candidate_decisions), encoding="utf-8"
        )
        enrichment_artifact.write_text(
            json.dumps(queue, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        audit["universe"].update(
            {
                "artifact_path": universe_artifact.name,
                "artifact_sha256": hashlib.sha256(universe_artifact.read_bytes()).hexdigest(),
            }
        )
        audit["candidate_pool"].update(
            {
                "artifact_path": candidate_artifact.name,
                "artifact_sha256": hashlib.sha256(candidate_artifact.read_bytes()).hexdigest(),
            }
        )
        audit["enrichment"].update(
            {
                "artifact_path": enrichment_artifact.name,
                "artifact_sha256": hashlib.sha256(enrichment_artifact.read_bytes()).hexdigest(),
            }
        )
        audit_path = args.output_dir / "broad-screen-audit.json"
        audit_path.write_text(
            json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        shortlist_path = args.output_dir / "broad-screen-shortlist.json"
        shortlist_path.write_text(
            json.dumps(
                {
                    "runtime": runtime_metadata(),
                    "candidate_generation_mode": mode,
                    "candidate_pool_status": audit["candidate_pool_status"],
                    "selection_outcome": audit["selection_outcome"],
                    "selected_symbols": selected,
                    "deep_dive_plan": audit.get("deep_dive_plan", {}),
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    except (OSError, ValueError, json.JSONDecodeError, ScreenError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    for path in (
        universe_artifact,
        candidate_artifact,
        enrichment_artifact,
        audit_path,
        shortlist_path,
    ):
        print(f"wrote: {path}")
    incomplete_reasons: list[str] = []
    scope_section = _mapping(audit.get("scope"))
    if scope_section.get("screening_scope_ready") is not True:
        incomplete_reasons.append(
            "requested scope is neither fully enumerated nor covered by an audited full-range stratified pool"
        )
    if audit.get("candidate_pool_status") in {"insufficient_data", "sufficient_pending_enrichment"}:
        incomplete_reasons.append("candidate pool needs enrichment or exhaustion verification")
    if incomplete_reasons:
        print(
            "INCOMPLETE: "
            + "; ".join(incomplete_reasons)
            + "; build/enrich the bounded discovery pool and rerun with explicit retrieval bounds",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
