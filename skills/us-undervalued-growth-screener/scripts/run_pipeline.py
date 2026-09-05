#!/usr/bin/env python3
"""Claude Code-native direct-FMP discovery pipeline for the US GARP skill.

Bulk provider payloads stay on disk.  The program prints one compact JSON summary
and emits auditable JSON/JSONL artifacts consumed by the existing contract-3.5
underwriting and evaluation workflow.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import estimate_snapshot as snapshot_store
from build_provider_prefilter_pool import ALLOWED_LANES, _lane_score, build_pool
from coverage_semantics import build_coverage_block, classify_ranking_scope
from fmp_client import ApiCallBudgetExceeded, FMPClient
from normalize_estimates import apply_verified_actual_eps, normalize_symbol
from screen_universe import DEFAULTS as SCREEN_DEFAULTS
from screen_universe import (
    SECTOR_PROFILES,
    _canonical_line,
    requires_unit_reconciliation,
    run_layered,
)
from skill_version import runtime_metadata

# SEC filing acceptance timestamps (FMP acceptedDate) are US/Eastern wall time.
SEC_FILING_TZ = ZoneInfo("America/New_York")

DEFAULT_CONFIG: dict[str, Any] = {
    "min_market_cap": 500_000_000,
    "max_market_cap": 20_000_000_000,
    "min_price": 5.0,
    "hard_min_average_daily_dollar_volume": 1_000_000,
    "min_average_daily_dollar_volume": 5_000_000,
    "max_api_calls": 350,
    "company_screener_limit": 1_000,
    "minimum_market_cap_band_width": 25_000_000,
    "maximum_market_cap_band_depth": 12,
    "bulk_estimate_years": 5,
    "bulk_estimate_minimum_coverage_pct": 20.0,
    "pre_enrichment_limit": 180,
    "seed_limit_cap": 200,
    "quality_probe_limit": 35,
    "candidate_packet_reserve_calls": 30,
    "retry_reserve_calls": 25,
    "exact_liquidity_limit": 40,
    "provider_prefilter_pool_size": 30,
    "provider_prefilter_minimum_pool": 12,
    "provider_prefilter_per_lane": 8,
    "max_deep_dive_candidates": 3,
    "full_snapshot_pool_size": 50,
    "full_snapshot_deep_dive_candidates": 5,
    "full_snapshot_max_staleness_days": 7,
    "full_snapshot_screening_clock_skew_seconds": 300,
    "full_snapshot_collection_clock_skew_seconds": 300,
    # Symbol -> profile pins for names the listing-frame taxonomy cannot
    # classify (e.g. BDCs filed under plain "Asset Management" whose name
    # carries no BDC marker: {"ARCC": "bdc"}).
    "sector_profile_overrides": {},
    "minimum_discovery_analyst_count": 2,
    "maximum_forward_eps_dispersion_pct": 100.0,
    "maximum_fy1_horizon_days": 430,
    "forward_pe_reconciliation_tolerance_pct": 5.0,
    "minimum_average_volume_period_days": 20,
    "minimum_revenue_growth_pct": 8.0,
    "minimum_per_share_growth_pct": 12.0,
    "preferred_forward_pe": 20.0,
    "high_growth_exception_max_forward_pe": 30.0,
    "high_growth_exception_growth_pct": 20.0,
    "near_miss_max_forward_pe": 22.0,
    "near_miss_min_per_share_growth_pct": 8.0,
    "preferred_ev_to_fcf": 20.0,
    "preferred_fcf_yield_pct": 5.0,
    "minimum_roic_pct": 8.0,
    "preferred_max_dilution_pct": 3.0,
    "preferred_max_net_debt_to_ebitda": 2.5,
    "hard_max_net_debt_to_ebitda": 4.0,
    "maximum_forward_pe_for_economic_screen": 60.0,
    "sector_review_selection_penalty": 5.0,
    "near_miss_selection_penalty": 4.0,
    "missing_deep_dive_field_penalty": 1.5,
    "selection_lane_quota_core_garp": 2,
    "selection_lane_quota_high_growth": 1,
    "selection_lane_quota_near_miss": 1,
    "selection_lane_quota_cyclical": 1,
    "maximum_selected_per_sector": 2,
    "maximum_enrichment_attempts": 80,
    "minimum_listing_data_coverage_pct": 95.0,
    "max_estimate_age_days": 45,
    "bulk_endpoints": {
        "ratios_ttm": "ratios-ttm-bulk",
        "key_metrics_ttm": "key-metrics-ttm-bulk",
        "income_growth": "income-statement-growth-bulk",
        "analyst_estimates": "analyst-estimates-bulk",
        "eod": "eod-bulk",
    },
    "cache": {"path": ".cache/us-garp/fmp-cache.sqlite3", "raw_store_dir": ".cache/us-garp/raw"},
    "compact_stdout_max_bytes": 20_000,
}

EXCHANGES = ("NASDAQ", "NYSE", "AMEX")
NON_COMMON_NAME = re.compile(
    r"\b(preferred|depositary shares?|warrants?|rights?|units?|notes?|debentures?|bonds?|closed[- ]end|income fund)\b",
    re.IGNORECASE,
)
NON_COMMON_SYMBOL = re.compile(r"(?:[-.](?:P[A-Z]?|WS|WT|W|U|R))$", re.IGNORECASE)

CYCLICAL_RULES: tuple[tuple[int, tuple[str, ...]], ...] = (
    (5, ("airline", "marine shipping", "oil tanker", "dry bulk", "steel", "coal", "iron ore")),
    (
        4,
        (
            "chemical",
            "mining",
            "oil & gas",
            "oilfield",
            "auto manufacturer",
            "auto parts",
            "homebuilding",
            "building materials",
            "forest products",
            "paper",
            "agricultural",
            "farm products",
            "meat products",
            "gold",
            "silver",
            "precious metal",
            "base metal",
            "copper",
            "uranium",
            "coal",
            "metals & mining",
            "metals and mining",
            "metal mining",
            "mineral",
        ),
    ),
    (
        3,
        (
            "machinery",
            "industrial distribution",
            "advertising",
            "staffing",
            "casino",
            "resort",
            "hotel",
            "transportation",
            "trucking",
            "railroad",
            "construction",
            "consumer cyclical",
            "aluminum",
            "semiconductor equipment",
        ),
    ),
)


@dataclass
class PipelineResult:
    summary: dict[str, Any]
    exit_code: int


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _first_number(row: Mapping[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = _number(row.get(key))
        if value is not None:
            return value
    return None


def _text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _symbol(row: Mapping[str, Any]) -> str:
    return (_text(row.get("symbol")) or _text(row.get("ticker")) or "UNKNOWN").upper()


def _canonical_jsonl(rows: Sequence[Mapping[str, Any]]) -> bytes:
    return b"".join(
        (
            json.dumps(dict(row), ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        ).encode("utf-8")
        for row in rows
    )


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, path)


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = _canonical_jsonl(rows)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_bytes(data)
    os.replace(temp, path)
    return hashlib.sha256(data).hexdigest()


def load_config(path: Path | None) -> dict[str, Any]:
    config = json.loads(json.dumps(DEFAULT_CONFIG))
    if path is None:
        return config
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError("pipeline config must be a JSON object")
    for key, item in value.items():
        if isinstance(item, Mapping) and isinstance(config.get(key), Mapping):
            config[key].update(item)
        else:
            config[key] = item
    return config


def is_common_stock(row: Mapping[str, Any]) -> bool:
    if bool(row.get("isEtf")) or bool(row.get("isFund")):
        return False
    if row.get("isActivelyTrading") is False:
        return False
    name = _text(row.get("companyName")) or _text(row.get("name")) or ""
    symbol = _symbol(row)
    if NON_COMMON_NAME.search(name) or NON_COMMON_SYMBOL.search(symbol):
        return False
    return symbol != "UNKNOWN"


# Explicit map over normalized FMP taxonomy labels (lowercased, single-spaced).
# Substring needles alone misroute real provider data: FMP's actual label is
# "Auto - Dealerships" (which the old "auto & truck dealership" needle never
# matched), and "Investment - Banking & Investment Services" is an
# advisory/capital-markets business, not a deposit bank valued on P/TBV and
# deposit betas.
INDUSTRY_PROFILE_MAP: dict[str, str] = {
    "auto - dealerships": "auto_dealership",
    "auto & truck dealerships": "auto_dealership",
    "investment - banking & investment services": "capital_markets",
    "financial - capital markets": "capital_markets",
    "capital markets": "capital_markets",
}
# Prefix rules over FMP's "Family - Subtype" industry labels.
_INDUSTRY_PREFIX_RULES: tuple[tuple[str, str], ...] = (
    ("reit", "reit"),
    ("banks", "bank"),
    ("insurance", "insurance"),
    ("business development", "bdc"),
    ("asset management", "asset_manager"),
)
# FMP files most BDCs under "Asset Management"; the company name is the only
# listing-frame signal. Best-effort — operators can pin the rest through the
# sector_profile_overrides config map.
_BDC_NAME_NEEDLES = ("business development", " bdc")
_MLP_NEEDLES = (" master limited partnership", " mlp")


def _normalize_taxonomy_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def infer_sector_profile_type(
    sector: str | None, industry: str | None, company_name: str | None = None
) -> str:
    """Map provider taxonomy onto screen_universe's sector-profile gates.

    Names whose standard company multiples are not comparable (mortgage REITs,
    insurers, banks, asset managers, BDCs, MLPs, auto dealers) must reach the
    broad screen tagged so that, absent sector-specific valuation evidence,
    they are routed to ``sector_specific_valuation_required`` instead of being
    scored (or excluded) on general-company metrics such as net debt/EBITDA.

    ``capital_markets`` (advisory / investment banking) is deliberately NOT a
    blocked sector profile: those firms are valued on ordinary earnings
    multiples — the label exists so they are never misrouted as deposit banks.
    """
    industry_norm = _normalize_taxonomy_text(industry)
    name_norm = f" {_normalize_taxonomy_text(company_name)} "
    if any(needle in name_norm for needle in _BDC_NAME_NEEDLES):
        return "bdc"
    if industry_norm in INDUSTRY_PROFILE_MAP:
        return INDUSTRY_PROFILE_MAP[industry_norm]
    for prefix, profile in _INDUSTRY_PREFIX_RULES:
        if industry_norm.startswith(prefix):
            return profile
    text = f" {_normalize_taxonomy_text(sector)} {industry_norm}{name_norm}"
    if any(needle in text for needle in _MLP_NEEDLES):
        return "mlp"
    if " reit " in f"{text} ":
        return "reit"
    return "general"


def normalize_listing(row: Mapping[str, Any], exchange: str) -> dict[str, Any] | None:
    price = _first_number(row, "price", "last")
    market_cap = _first_number(row, "marketCap", "mktCap", "market_cap")
    if price is None or market_cap is None:
        return None
    symbol = _symbol(row)
    return {
        "symbol": symbol,
        "company_name": _text(row.get("companyName")) or _text(row.get("name")) or symbol,
        "exchange": (
            _text(row.get("exchangeShortName")) or _text(row.get("exchange")) or exchange
        ).upper(),
        "sector": _text(row.get("sector")),
        "industry": _text(row.get("industry")),
        "price": price,
        "market_cap": market_cap,
        "volume": _first_number(row, "volume"),
        "is_actively_trading": row.get("isActivelyTrading", True) is not False,
        "is_common_stock": is_common_stock(row),
        "common_stock": is_common_stock(row),
        "currency": _text(row.get("currency")),
        "country": _text(row.get("country")),
        # Unit-context identity signals must survive normalization: the
        # fail-closed unit gate needs them, and a dropped ISIN silently
        # disabled the non-US-ISIN check in earlier versions.
        "isin": _text(row.get("isin")),
        "is_adr": row.get("isAdr") is True,
        "sector_profile_type": infer_sector_profile_type(
            _text(row.get("sector")),
            _text(row.get("industry")),
            _text(row.get("companyName")) or _text(row.get("name")),
        ),
    }


def _coverage_count(value: Any) -> int:
    """Length of a list-valued audit field, or the int it already is."""
    if isinstance(value, list):
        return len(value)
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


# classify_ranking_scope now lives in coverage_semantics (shared with the
# evaluator so the tri-state semantics cannot drift); imported above.


def collect_listing_universe(
    client: FMPClient,
    *,
    min_market_cap: float,
    max_market_cap: float,
    min_price: float,
    page_limit: int,
    minimum_band_width: float,
    maximum_depth: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Enumerate the listing frame with adaptive market-cap band splitting.

    FMP's company screener has no portable pagination contract across legacy and
    stable plans.  A saturated response is therefore split into overlapping
    market-cap bands until every leaf returns fewer rows than ``page_limit``.
    Provider payloads stay in the FMP client's raw store; only normalized rows
    and a compact enumeration audit are returned.
    """
    if page_limit <= 0:
        raise ValueError("company_screener_limit must be positive")
    if minimum_band_width <= 0 or max_market_cap <= min_market_cap:
        raise ValueError("invalid market-cap enumeration range")

    rows: list[dict[str, Any]] = []
    leaves: list[dict[str, Any]] = []
    query_count = 0
    saturated_leaves: list[dict[str, Any]] = []

    for exchange in EXCHANGES:
        stack: list[tuple[float, float, int]] = [(min_market_cap, max_market_cap, 0)]
        while stack:
            band_min, band_max, depth = stack.pop()
            payload = client.get_company_screener(
                exchange=exchange,
                min_market_cap=band_min,
                max_market_cap=band_max,
                min_price=min_price,
                limit=page_limit,
            )
            query_count += 1
            saturated = len(payload) >= page_limit
            can_split = depth < maximum_depth and (band_max - band_min) > minimum_band_width
            if saturated and can_split:
                midpoint = (band_min + band_max) / 2.0
                # The provider uses MoreThan/LowerThan semantics on some plans.
                # A one-dollar overlap prevents an exact-boundary omission; rows
                # are deterministically deduplicated after collection.
                stack.append((max(band_min, midpoint - 1.0), band_max, depth + 1))
                stack.append((band_min, min(band_max, midpoint + 1.0), depth + 1))
                continue

            leaf = {
                "exchange": exchange,
                "min_market_cap": band_min,
                "max_market_cap": band_max,
                "row_count": len(payload),
                # Contract 3.5 validators read `rows_fetched` per band.
                "rows_fetched": len(payload),
                "provider_exhausted": not saturated,
                "depth": depth,
            }
            leaves.append(leaf)
            if saturated:
                saturated_leaves.append(leaf)
            for item in payload:
                normalized = normalize_listing(item, exchange)
                if normalized is not None:
                    rows.append(normalized)

    # Prefer one canonical listing row per ticker.  Dual-listed or provider
    # duplicate rows are resolved by the requested exchange order, then by the
    # row with the larger market-cap observation.
    exchange_rank = {value: idx for idx, value in enumerate(EXCHANGES)}
    deduped: dict[str, dict[str, Any]] = {}
    for row in rows:
        symbol = _symbol(row)
        current = deduped.get(symbol)
        if current is None:
            deduped[symbol] = row
            continue
        new_key = (
            -exchange_rank.get(str(row.get("exchange") or "").upper(), 99),
            _first_number(row, "market_cap") or 0.0,
        )
        old_key = (
            -exchange_rank.get(str(current.get("exchange") or "").upper(), 99),
            _first_number(current, "market_cap") or 0.0,
        )
        if new_key > old_key:
            deduped[symbol] = row

    normalized_rows = sorted(deduped.values(), key=lambda row: _symbol(row))
    audit = {
        "method": "adaptive_market_cap_bands",
        "retrieval_scope_explicit": True,
        "pagination_exhausted": not saturated_leaves,
        "requested_exchanges": list(EXCHANGES),
        "retrieved_exchanges": sorted({str(row.get("exchange") or "").upper() for row in leaves}),
        "requested_min_market_cap": min_market_cap,
        "requested_max_market_cap": max_market_cap,
        "min_price": min_price,
        "page_limit": page_limit,
        "query_count": query_count,
        "row_count": len(normalized_rows),
        "bands": sorted(
            leaves,
            key=lambda row: (
                str(row["exchange"]),
                float(row["min_market_cap"]),
                float(row["max_market_cap"]),
            ),
        ),
        "saturated_leaf_count": len(saturated_leaves),
        "enumeration_verified": not saturated_leaves,
    }
    return normalized_rows, audit


def market_cap_bucket(value: float) -> str:
    bounds = (
        500_000_000,
        1_000_000_000,
        2_000_000_000,
        5_000_000_000,
        10_000_000_000,
        20_000_000_000,
    )
    for low, high in zip(bounds, bounds[1:]):
        if low <= value < high:
            return f"{low}-{high}"
    return "other"


def classify_cyclicality(sector: str | None, industry: str | None) -> int:
    text = f"{sector or ''} {industry or ''}".lower()
    for score, needles in CYCLICAL_RULES:
        if any(needle in text for needle in needles):
            return score
    if "financial" in text or "bank" in text or "insurance" in text:
        return 3
    return 2


def merge_bulk_rows(
    rows_by_dataset: Mapping[str, Sequence[Mapping[str, Any]]],
) -> dict[str, dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = defaultdict(dict)
    for dataset, rows in rows_by_dataset.items():
        for row in rows:
            symbol = _symbol(row)
            if symbol == "UNKNOWN":
                continue
            merged[symbol][dataset] = dict(row)
    return dict(merged)


def collect_bulk_annual_estimates(
    client: FMPClient,
    *,
    endpoint: str | None,
    universe_symbols: set[str],
    analysis_as_of: datetime,
    year_count: int,
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    """Collect annual estimate rows in bulk when the provider plan supports it."""
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    calls: list[dict[str, Any]] = []
    if not endpoint or year_count <= 0:
        return {}, {"available": False, "reason": "endpoint_not_configured", "calls": []}

    for year in range(analysis_as_of.year, analysis_as_of.year + year_count):
        rows = client.get_bulk_dataset(endpoint, year=year, period="annual")
        calls.append({"year": year, "row_count": len(rows)})
        for raw in rows:
            symbol = _symbol(raw)
            if symbol in universe_symbols:
                grouped[symbol].append(dict(raw))

    for values in grouped.values():
        values.sort(key=lambda row: str(row.get("date") or row.get("period_end") or ""))
    coverage_pct = (len(grouped) / len(universe_symbols) * 100.0) if universe_symbols else 0.0
    return dict(grouped), {
        "available": bool(grouped),
        "covered_symbol_count": len(grouped),
        "universe_symbol_count": len(universe_symbols),
        "coverage_pct": coverage_pct,
        "calls": calls,
    }


def normalize_estimate_frame(
    listings: Sequence[Mapping[str, Any]],
    estimates_by_symbol: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    analysis_as_of: datetime,
    source_id: str,
    config: Mapping[str, Any],
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for listing in listings:
        symbol = _symbol(listing)
        normalized = normalize_symbol(
            symbol,
            estimates_by_symbol.get(symbol, []),
            listing,
            analysis_as_of=analysis_as_of,
            estimate_as_of=analysis_as_of,
            source_ids=[source_id],
            minimum_analysts=int(config["minimum_discovery_analyst_count"]),
            max_dispersion_pct=float(config["maximum_forward_eps_dispersion_pct"]),
            max_fy1_horizon_days=int(config["maximum_fy1_horizon_days"]),
            forward_pe_tolerance_pct=float(config["forward_pe_reconciliation_tolerance_pct"]),
        )
        normalized["cyclicality_score"] = classify_cyclicality(
            _text(normalized.get("sector")), _text(normalized.get("industry"))
        )
        output.append(normalized)
    return output


def _metric_from_bulk(bundle: Mapping[str, Any], *keys: str) -> float | None:
    for dataset in ("ratios_ttm", "key_metrics_ttm", "income_growth"):
        row = bundle.get(dataset)
        if not isinstance(row, Mapping):
            continue
        value = _first_number(row, *keys)
        if value is not None:
            return value
    return None


def enrich_listing_from_bulk(row: Mapping[str, Any], bundle: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(row)
    result["roic_pct"] = _metric_from_bulk(
        bundle, "returnOnInvestedCapital", "roic", "returnOnInvestedCapitalTTM"
    )
    roic = _number(result.get("roic_pct"))
    if roic is not None and abs(roic) <= 2:
        result["roic_pct"] = roic * 100.0
    result["ev_to_fcf"] = _metric_from_bulk(
        bundle, "enterpriseValueOverFCF", "enterpriseValueOverFreeCashFlow", "evToFreeCashFlow"
    )
    result["net_debt_to_ebitda"] = _metric_from_bulk(bundle, "netDebtToEBITDA", "netDebtToEbitda")
    result["revenue_growth_pct"] = _metric_from_bulk(
        bundle, "growthRevenue", "revenueGrowth", "revenueGrowthTTM"
    )
    result["eps_growth_pct"] = _metric_from_bulk(bundle, "growthEPS", "epsgrowth", "epsGrowth")
    result["dilution_pct"] = _metric_from_bulk(
        bundle, "weightedAverageShsOutDilGrowth", "weightedAverageSharesGrowth"
    )
    fcf_yield = _metric_from_bulk(bundle, "freeCashFlowYield", "fcfYield")
    if fcf_yield is not None and abs(fcf_yield) <= 2:
        fcf_yield *= 100.0
    result["fcf_yield_pct"] = fcf_yield
    result["cyclicality_score"] = classify_cyclicality(
        _text(result.get("sector")), _text(result.get("industry"))
    )
    return result


def pre_enrichment_score(row: Mapping[str, Any]) -> float:
    score = 0.0
    pe = _first_number(row, "priceEarningsRatio", "peRatio", "pe")
    if pe is not None and pe > 0:
        score += max(-20.0, 30.0 - min(pe, 60.0))
    eps_growth = _first_number(row, "eps_growth_pct")
    revenue_growth = _first_number(row, "revenue_growth_pct")
    roic = _first_number(row, "roic_pct")
    fcf_yield = _first_number(row, "fcf_yield_pct")
    if eps_growth is not None:
        score += max(-10.0, min(eps_growth, 40.0))
    if revenue_growth is not None:
        score += max(-5.0, min(revenue_growth, 20.0)) * 0.5
    if roic is not None:
        score += max(-5.0, min(roic, 30.0)) * 0.3
    if fcf_yield is not None:
        score += max(-5.0, min(fcf_yield, 15.0))
    volume = _first_number(row, "volume") or 0.0
    price = _first_number(row, "price") or 0.0
    if volume > 0 and price > 0:
        # Uncapped: this is a ranking key for seed/liquidity selection, not a
        # bounded score, so large-cap/high-volume names must not tie here.
        score += math.log10(max(volume * price, 1.0))
    return round(score, 6)


def _cell_key(row: Mapping[str, Any]) -> tuple[str, str]:
    sector = (_text(row.get("sector")) or "Unknown").lower()
    cap = _first_number(row, "market_cap") or 0.0
    return sector, market_cap_bucket(cap)


def _stable_tie_break(symbol: str, run_salt: str) -> str:
    return hashlib.sha256(f"{run_salt}:{symbol}".encode()).hexdigest()


def _apportion_quota(
    sizes: Mapping[tuple[str, str], int], limit: int
) -> dict[tuple[str, str], int]:
    """Hamilton (largest-remainder) apportionment of ``limit`` seats across cells.

    Every non-empty cell gets at least one seat (capped by its own size);
    weight is ``sqrt(cell size)`` so large cells still get proportionally
    more seats without a single mega-cell crowding out everything else.
    Deterministic and independent of dict/cell iteration order.
    """
    keys = sorted(sizes)
    if not keys:
        return {}
    if limit < len(keys):
        ordered = sorted(keys, key=lambda key: (-sizes[key], key))
        chosen = set(ordered[:limit])
        return {key: (1 if key in chosen else 0) for key in keys}

    weights = {key: math.sqrt(max(sizes[key], 1)) for key in keys}
    total_weight = sum(weights.values()) or 1.0
    ideal = {key: weights[key] / total_weight * limit for key in keys}
    counts = {key: min(sizes[key], max(1, int(math.floor(ideal[key])))) for key in keys}

    allocated = sum(counts.values())
    remainder = limit - allocated
    if remainder > 0:
        # Largest fractional remainder first; skip cells already at capacity.
        by_fraction = sorted(keys, key=lambda key: (-(ideal[key] - math.floor(ideal[key])), key))
        while remainder > 0:
            progressed = False
            for key in by_fraction:
                if remainder <= 0:
                    break
                if counts[key] < sizes[key]:
                    counts[key] += 1
                    remainder -= 1
                    progressed = True
            if not progressed:
                break
    elif remainder < 0:
        # Defensive: only reachable if the min-1-per-cell floor overshot the
        # limit while sizes still permitted trimming (rare, tiny-cell case).
        by_excess = sorted(keys, key=lambda key: (-(counts[key] - 1), key))
        idx = 0
        while remainder < 0 and idx < len(by_excess) * 4:
            key = by_excess[idx % len(by_excess)]
            if counts[key] > 1:
                counts[key] -= 1
                remainder += 1
            idx += 1
    return counts


_ECONOMIC_SEED_FIELDS = ("eps_growth_pct", "revenue_growth_pct", "roic_pct", "fcf_yield_pct")


def diversified_seed(
    rows: Sequence[Mapping[str, Any]],
    limit: int,
    *,
    run_salt: str,
    seed_limit_configured: int | None = None,
    reserved_calls: int | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Stratified sector x market-cap seed selection for the estimate fallback path.

    Replaces the prior dict-order round-robin (which biased the tail of the
    seed toward alphabetically-early cells) with a deterministic
    sqrt-weighted Hamilton apportionment and a within-cell ranking that never
    falls back to the raw ticker string.
    """
    cells: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for raw in rows:
        row = dict(raw)
        cells[_cell_key(row)].append(row)

    sizes = {key: len(values) for key, values in cells.items()}
    quotas = _apportion_quota(sizes, limit)

    hash_tie_break_used_count = 0
    selected: list[dict[str, Any]] = []
    for key in sorted(cells):
        values = cells[key]

        def _sort_key(row: Mapping[str, Any]) -> tuple[float, float, float, int, str]:
            price = _first_number(row, "price") or 0.0
            volume = _first_number(row, "volume") or 0.0
            dollar_volume = price * volume
            market_cap = _first_number(row, "market_cap") or 0.0
            missing = sum(1 for field in ("price", "volume") if _first_number(row, field) is None)
            return (
                -pre_enrichment_score(row),
                -dollar_volume,
                -market_cap,
                missing,
                _stable_tie_break(_symbol(row), run_salt),
            )

        values.sort(key=_sort_key)
        quota = quotas.get(key, 0)
        # Count ties across the whole ranked cell (not just the chosen slice):
        # the hash decides ordering at the selection boundary too, so a tie
        # straddling `quota` still used the hash even though only one side
        # of it was kept.
        for idx in range(1, len(values)):
            base_prev = _sort_key(values[idx - 1])[:-1]
            base_cur = _sort_key(values[idx])[:-1]
            if base_prev == base_cur:
                hash_tie_break_used_count += 1
        selected.extend(values[:quota])

    economic_rows_with_data = sum(
        1
        for raw in rows
        if any(_first_number(raw, field) is not None for field in _ECONOMIC_SEED_FIELDS)
    )
    economic_metrics_available_for_seed = bool(rows) and (
        economic_rows_with_data / len(rows) >= 0.5
    )
    seed_audit = {
        "seed_selection_basis": (
            "stratified_economic_score"
            if economic_metrics_available_for_seed
            else "stratified_liquidity_proxy"
        ),
        "economic_metrics_available_for_seed": economic_metrics_available_for_seed,
        "cell_count": len(cells),
        "quota_method": "sqrt_hamilton",
        "alphabetic_tie_break_used_count": 0,
        "hash_tie_break_used_count": hash_tie_break_used_count,
        "seed_limit_configured": seed_limit_configured
        if seed_limit_configured is not None
        else limit,
        "seed_limit_effective": limit,
        "reserved_calls": reserved_calls if reserved_calls is not None else 0,
    }
    return selected, seed_audit


def compute_effective_seed_limit(
    *,
    pre_enrichment_limit: int,
    seed_limit_cap: int,
    max_api_calls: int,
    api_calls_made: int,
    quality_probe_limit: int,
    exact_liquidity_limit: int,
    candidate_packet_reserve_calls: int,
    retry_reserve_calls: int,
) -> int:
    """Bound the per-symbol estimate fallback seed by the remaining call budget.

    Reserves calls for the quality probe, exact-liquidity lookups, candidate
    packet generation, and retries so the seed step cannot starve the rest of
    the pipeline. Raises ``ValueError`` (caught by the existing failure-JSON
    path in ``main``) when the remaining budget cannot afford a floor of 20
    seeds -- silently truncating below that floor would make the discovery
    pool too thin to be meaningful.
    """
    reserved = (
        int(quality_probe_limit) * 2  # key-metrics-ttm + annual income statement
        + int(exact_liquidity_limit)
        + int(candidate_packet_reserve_calls)
        + int(retry_reserve_calls)
    )
    remaining = int(max_api_calls) - int(api_calls_made)
    effective = min(int(pre_enrichment_limit), int(seed_limit_cap), remaining - reserved)
    if effective < 20:
        raise ValueError(
            "estimate seed budget insufficient: effective_limit="
            f"{effective} < 20 (pre_enrichment_limit={pre_enrichment_limit}, "
            f"seed_limit_cap={seed_limit_cap}, remaining_calls={remaining}, "
            f"reserved_calls={reserved})"
        )
    return effective


def economic_scope_complete(
    *, estimate_acquisition_mode: str, covered_symbol_count: int, universe_symbol_count: int
) -> bool:
    """True only when bulk estimates covered EVERY listing-universe symbol.

    Completeness is an exact symbol-count equality, deliberately not a
    configurable percentage: any ratio threshold (99%, 99.99%, or a user
    lowering it to 20%) still declares "complete / exhausted" while uncovered
    symbols remain, which is the misstatement this field exists to prevent.
    Using the bulk route (allowed from ``bulk_estimate_minimum_coverage_pct``,
    20%) says nothing about completeness.
    """
    return (
        estimate_acquisition_mode == "analyst_estimates_bulk"
        and int(universe_symbol_count) > 0
        and int(covered_symbol_count) >= int(universe_symbol_count)
    )


_SECTOR_METRIC_FIELDS = (
    "sector_forward_multiple",
    "p_to_tbv",
    "p_to_affo",
    "p_to_book",
    "sector_per_share_growth_pct",
    "affo_per_share_growth_pct",
    "tbv_per_share_growth_pct",
    "sector_adjusted_net_debt_to_ebitda",
)


# Profiles whose missing sector metrics BLOCK screening (capital_markets is
# labelled but valued on ordinary multiples, so it is deliberately absent).
_BLOCKED_SECTOR_PROFILES = frozenset(SECTOR_PROFILES) | {"auto_dealership"}


def mark_sector_profile_exhaustion(
    rows: Sequence[Mapping[str, Any]], *, source_id: str
) -> list[dict[str, Any]]:
    """Declare enrichment exhaustion for sector-profile rows the provider cannot serve.

    Balance-sheet businesses (REITs, banks, insurers, BDCs, MLPs, asset
    managers, auto dealers) need sector-specific valuation evidence
    (P/FFO-AFFO, P/TBV, adjusted leverage) that the direct-FMP discovery path
    does not provide. Without this declaration such rows stay
    ``needs_enrichment`` forever and the run cannot complete; with it,
    ``screen_universe`` resolves them as ``unavailable_after_enrichment`` —
    still visible in the audit, honestly excluded from selection, and eligible
    for manual sector underwriting in a scoped follow-up.
    """
    output: list[dict[str, Any]] = []
    for raw in rows:
        row = dict(raw)
        profile = _text(row.get("sector_profile_type")) or "general"
        has_sector_metrics = any(
            _first_number(row, field) is not None for field in _SECTOR_METRIC_FIELDS
        )
        if profile in _BLOCKED_SECTOR_PROFILES and not has_sector_metrics:
            row.setdefault("enrichment_attempted", True)
            row["enrichment_exhausted"] = True
            row["enrichment_exhaustion_reason"] = (
                f"sector-specific valuation metrics for profile '{profile}' are not "
                "available from the direct-FMP discovery path"
            )
            sources = [
                value
                for value in (row.get("enrichment_source_ids") or [])
                if isinstance(value, str) and value.strip()
            ]
            if source_id not in sources:
                sources.append(source_id)
            row["enrichment_source_ids"] = sources
        output.append(row)
    return output


def mark_unit_reconciliation_exhaustion(
    rows: Sequence[Mapping[str, Any]], *, source_id: str
) -> list[dict[str, Any]]:
    """Declare exhaustion for foreign issuers the direct-FMP path cannot reconcile.

    A non-US issuer's USD listing price and local-currency (or differently
    ratioed ADS) statements make every valuation ratio meaningless until the
    listing/statement currencies and the ordinary-shares-per-ADS ratio are
    verified (QFIN: forward P/E 0.45x, FCF yield 94% — unit mismatch, not deep
    value). The direct-FMP discovery path carries no such evidence, so the
    ``unit_reconciliation_required`` blocking review would otherwise leave the
    row ``needs_enrichment`` forever; declaring exhaustion lets
    ``screen_universe`` resolve it as ``unavailable_after_enrichment`` —
    audited, excluded from selection, open to manual reconciliation.
    """
    output: list[dict[str, Any]] = []
    for raw in rows:
        row = dict(raw)
        if requires_unit_reconciliation(row):
            row.setdefault("enrichment_attempted", True)
            row["enrichment_exhausted"] = True
            row["enrichment_exhaustion_reason"] = (
                "listing/statement currency and ADS-unit reconciliation is not "
                "available from the direct-FMP discovery path"
            )
            sources = [
                value
                for value in (row.get("enrichment_source_ids") or [])
                if isinstance(value, str) and value.strip()
            ]
            if source_id not in sources:
                sources.append(source_id)
            row["enrichment_source_ids"] = sources
        output.append(row)
    return output


def _is_foreign_private_issuer(row: Mapping[str, Any]) -> bool:
    """Heuristic FPI flag: ISIN country prefix when available, else listing country."""
    isin = _text(row.get("isin"))
    if isin:
        return not isin.upper().startswith("US")
    country = _text(row.get("country"))
    if country:
        return country.upper() != "US"
    return False


def _verified_annual_actual(
    statements: Sequence[Mapping[str, Any]], *, analysis_as_of: datetime
) -> tuple[float | None, str | None]:
    """Latest reported annual diluted EPS whose period AND filing precede analysis_as_of."""
    best: tuple[str, float] | None = None
    for raw in statements:
        if not isinstance(raw, Mapping):
            continue
        if (_text(raw.get("period")) or "FY").upper() != "FY":
            continue
        period_end = _text(raw.get("date"))
        # Only acceptedDate qualifies, and only with a time-of-day component:
        # a bare date (or the filingDate field, which is date-only) cannot
        # prove the filing preceded an intraday analysis_as_of, so it is
        # treated as unknown and rejected (fail closed).
        accepted = _text(raw.get("acceptedDate"))
        eps = _first_number(raw, "epsDiluted", "eps")
        if not period_end or not accepted or eps is None:
            continue
        if len(accepted.strip()) < 16:
            continue
        try:
            end_dt = datetime.fromisoformat(period_end[:10]).replace(tzinfo=timezone.utc)
            acc_dt = datetime.fromisoformat(accepted[:19].replace(" ", "T"))
        except ValueError:
            continue
        if acc_dt.tzinfo is None:
            # FMP's acceptedDate is the SEC acceptance clock: US/Eastern.
            # Treating "17:23:10" as UTC would read it as 13:23 ET and leak a
            # filing 4-5 hours before it was actually public.
            acc_dt = acc_dt.replace(tzinfo=SEC_FILING_TZ)
        acc_dt = acc_dt.astimezone(timezone.utc)
        if end_dt > analysis_as_of or acc_dt > analysis_as_of:
            continue
        if best is None or period_end > best[0]:
            best = (period_end, float(eps))
    return (best[1], best[0]) if best else (None, None)


def apply_quality_probe(
    client: Any,
    rows: Sequence[Mapping[str, Any]],
    *,
    target_symbols: Sequence[str],
    source_id: str,
    analysis_as_of: datetime | None = None,
    actual_source_id: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Enrich the top-ranked lane candidates with TTM quality metrics.

    A failed/empty probe (4xx or no data) is recorded as
    ``quality_probe_resolved: False`` on that row rather than failing the run.
    """
    targets = {str(value).upper() for value in target_symbols}
    attempted: list[str] = []
    resolved: list[str] = []
    actual_resolved: list[str] = []
    actual_calls = 0
    output: list[dict[str, Any]] = []
    for raw in rows:
        row = dict(raw)
        symbol = _symbol(row)
        if symbol in targets:
            attempted.append(symbol)
            row["quality_probe_attempted"] = True
            payload = client.get_key_metrics_ttm(symbol)
            bundle = payload[0] if payload else None
            if isinstance(bundle, Mapping):
                roic = _first_number(bundle, "returnOnInvestedCapitalTTM")
                fcf_yield = _first_number(bundle, "freeCashFlowYieldTTM")
                ev_to_fcf = _first_number(bundle, "evToFreeCashFlowTTM")
                nd_ebitda = _first_number(bundle, "netDebtToEBITDATTM")
                sbc = _first_number(bundle, "stockBasedCompensationToRevenueTTM")
                if roic is not None:
                    row["roic_pct"] = roic * 100.0
                if fcf_yield is not None:
                    row["fcf_yield_pct"] = fcf_yield * 100.0
                if ev_to_fcf is not None:
                    row["ev_to_fcf"] = ev_to_fcf
                if nd_ebitda is not None:
                    row["net_debt_to_ebitda"] = nd_ebitda
                if sbc is not None:
                    row["sbc_revenue_pct"] = sbc * 100.0
                # SBC-adjusted FCF yield on the SAME denominator as fcf_yield
                # (market cap): (FCF - SBC) / mktcap = fcf_yield - SBC/revenue * revenue/mktcap,
                # with revenue recovered from EV / (EV/Sales). Never subtract a
                # revenue-based ratio from a market-cap-based yield directly.
                ev = _first_number(bundle, "enterpriseValueTTM")
                ev_to_sales = _first_number(bundle, "evToSalesTTM")
                market_cap = _first_number(row, "market_cap")
                if (
                    fcf_yield is not None
                    and sbc is not None
                    and ev is not None
                    and ev_to_sales
                    and market_cap
                ):
                    revenue = ev / ev_to_sales
                    row["sbc_adjusted_fcf_yield_pct"] = (
                        fcf_yield - sbc * revenue / market_cap
                    ) * 100.0
                row["quality_probe_source_ids"] = [source_id]
                row["quality_probe_resolved"] = True
                resolved.append(symbol)
            else:
                row["quality_probe_resolved"] = False
            # Verified reported EPS: one annual income-statement call, accepted
            # at or before analysis_as_of. Without it the growth-basis fields
            # stay fail-closed (unknown) rather than borrowing a consensus row.
            if analysis_as_of is not None and hasattr(client, "get_income_statement"):
                statements = client.get_income_statement(symbol, period="annual", limit=2)
                actual_calls += 1
                actual_eps, actual_end = _verified_annual_actual(
                    statements or [], analysis_as_of=analysis_as_of
                )
                row = apply_verified_actual_eps(
                    row,
                    actual_eps=actual_eps,
                    period_end=actual_end,
                    analysis_as_of=analysis_as_of,
                    source_ids=[actual_source_id] if actual_source_id else [],
                )
                if row.get("latest_actual_verified"):
                    actual_resolved.append(symbol)
        else:
            row.setdefault("quality_probe_attempted", False)
            row.setdefault("quality_probe_resolved", False)
        output.append(row)
    audit = {
        "attempted": attempted,
        "resolved": resolved,
        "symbols": attempted,
        "source_id": source_id,
        "calls_used": len(attempted) + actual_calls,
        "actual_eps_source_id": actual_source_id,
        "actual_eps_calls": actual_calls,
        "actual_eps_resolved": actual_resolved,
    }
    return output, audit


def _best_lane_score(row: Mapping[str, Any], lanes: Sequence[str], *, analysis_as_of: str) -> float:
    if not lanes:
        return float("-inf")
    return max(_lane_score(row, lane, analysis_as_of=analysis_as_of) for lane in lanes)


def select_quality_probe_targets(
    rows: Sequence[Mapping[str, Any]],
    lane_membership_map: Mapping[str, Sequence[str]],
    *,
    limit: int,
    analysis_as_of: str,
) -> list[str]:
    """Rank the union of lane rows by best lane score; return the top ``limit`` symbols."""
    ranked = sorted(
        (row for row in rows if lane_membership_map.get(_symbol(row))),
        key=lambda row: (
            -_best_lane_score(
                row, lane_membership_map.get(_symbol(row), []), analysis_as_of=analysis_as_of
            ),
            _symbol(row),
        ),
    )
    return [_symbol(row) for row in ranked[:limit]]


def prior_business_days(as_of: date, count: int) -> list[date]:
    days: list[date] = []
    current = as_of
    while len(days) < count:
        if current.weekday() < 5:
            days.append(current)
        current -= timedelta(days=1)
    return days


def apply_bulk_liquidity(
    client: FMPClient,
    rows: Sequence[Mapping[str, Any]],
    *,
    as_of: date,
    endpoint: str,
    source_id: str,
    required_days: int = 20,
) -> tuple[list[dict[str, Any]], bool]:
    volumes: dict[str, list[float]] = defaultdict(list)
    successful_dates = 0
    for day in prior_business_days(as_of, required_days + 8):
        data = client.get_bulk_dataset(endpoint, date=day.isoformat())
        if not data:
            if successful_dates == 0:
                return [dict(row) for row in rows], False
            continue
        successful_dates += 1
        for item in data:
            symbol = _symbol(item)
            volume = _first_number(item, "volume")
            if volume is not None and volume > 0:
                volumes[symbol].append(volume)
        if successful_dates >= required_days:
            break
    if successful_dates < required_days:
        return [dict(row) for row in rows], False
    output: list[dict[str, Any]] = []
    for raw in rows:
        row = dict(raw)
        symbol = _symbol(row)
        values = volumes.get(symbol, [])[:required_days]
        price = _first_number(row, "price")
        if len(values) >= required_days and price is not None and price > 0:
            avg = sum(values) / len(values)
            row.update(
                {
                    "average_volume": avg,
                    "average_volume_period_days": required_days,
                    "average_daily_dollar_volume": avg * price,
                    "average_daily_dollar_volume_method": "price_x_20d_average_volume",
                    "liquidity_source_ids": [source_id],
                }
            )
        output.append(row)
    return output, True


def apply_symbol_liquidity(
    client: FMPClient,
    rows: Sequence[Mapping[str, Any]],
    *,
    as_of: date,
    source_id: str,
    limit: int,
    required_days: int = 20,
    target_symbols: Sequence[str] | None = None,
) -> list[dict[str, Any]]:
    ranked = sorted(
        (dict(row) for row in rows), key=lambda row: (-pre_enrichment_score(row), _symbol(row))
    )
    chosen = (
        {str(value).upper() for value in target_symbols if str(value).strip()}
        if target_symbols is not None
        else {_symbol(row) for row in ranked[:limit]}
    )
    if len(chosen) > limit:
        ordered = [_symbol(row) for row in ranked if _symbol(row) in chosen]
        chosen = set(ordered[:limit])
    start = (as_of - timedelta(days=45)).isoformat()
    end = as_of.isoformat()
    output: list[dict[str, Any]] = []
    for raw in rows:
        row = dict(raw)
        symbol = _symbol(row)
        if symbol not in chosen:
            output.append(row)
            continue
        history = client.get_historical_prices(symbol, from_date=start, to_date=end)
        volumes = [
            value
            for item in history
            if (value := _first_number(item, "volume")) is not None and value > 0
        ][:required_days]
        price = _first_number(row, "price")
        if len(volumes) >= required_days and price is not None and price > 0:
            avg = sum(volumes) / len(volumes)
            row.update(
                {
                    "average_volume": avg,
                    "average_volume_period_days": required_days,
                    "average_daily_dollar_volume": avg * price,
                    "average_daily_dollar_volume_method": "price_x_20d_average_volume",
                    "liquidity_source_ids": [source_id],
                }
            )
        output.append(row)
    return output


def select_liquidity_targets(
    rows: Sequence[Mapping[str, Any]],
    config: Mapping[str, Any],
    *,
    limit: int,
) -> list[str]:
    """Choose exact-liquidity work by opportunity lane, not ticker order."""
    lane_rows: dict[str, list[dict[str, Any]]] = {lane: [] for lane in ALLOWED_LANES}
    for raw in rows:
        row = dict(raw)
        for lane in lane_memberships(row, config):
            lane_rows[lane].append(row)
    for lane in lane_rows:
        lane_rows[lane].sort(key=lambda row: (-pre_enrichment_score(row), _symbol(row)))

    selected: list[str] = []
    seen: set[str] = set()
    pointers = {lane: 0 for lane in ALLOWED_LANES}
    ordered_lanes = (
        "core_garp",
        "high_growth_exception",
        "quality_near_miss",
        "cyclical_normalization",
    )
    while len(selected) < limit:
        added = False
        for lane in ordered_lanes:
            values = lane_rows[lane]
            pointer = pointers[lane]
            while pointer < len(values) and _symbol(values[pointer]) in seen:
                pointer += 1
            pointers[lane] = pointer
            if pointer >= len(values):
                continue
            symbol = _symbol(values[pointer])
            pointers[lane] = pointer + 1
            selected.append(symbol)
            seen.add(symbol)
            added = True
            if len(selected) >= limit:
                break
        if not added:
            break

    if len(selected) < limit:
        remaining = sorted(rows, key=lambda row: (-pre_enrichment_score(row), _symbol(row)))
        for row in remaining:
            symbol = _symbol(row)
            if symbol not in seen:
                selected.append(symbol)
                seen.add(symbol)
                if len(selected) >= limit:
                    break
    return selected


def lane_memberships(row: Mapping[str, Any], config: Mapping[str, Any]) -> list[str]:
    pe = _first_number(row, "forward_pe", "fy1_pe")
    growth = _first_number(row, "eps_growth_pct", "per_share_growth_pct")
    revenue = _first_number(row, "revenue_growth_pct")
    cyclicality = int(_first_number(row, "cyclicality_score") or 2)
    lanes: list[str] = []
    if pe is not None and growth is not None:
        if pe <= float(config["preferred_forward_pe"]) and growth >= float(
            config["minimum_per_share_growth_pct"]
        ):
            lanes.append("core_garp")
        if pe <= float(config["high_growth_exception_max_forward_pe"]) and growth >= float(
            config["high_growth_exception_growth_pct"]
        ):
            lanes.append("high_growth_exception")
        if pe <= float(config["near_miss_max_forward_pe"]) and growth >= float(
            config["near_miss_min_per_share_growth_pct"]
        ):
            if (
                revenue is None
                or revenue < float(config["minimum_revenue_growth_pct"])
                or growth < float(config["minimum_per_share_growth_pct"])
            ):
                lanes.append("quality_near_miss")
        if (
            cyclicality >= 3
            and pe <= float(config["high_growth_exception_max_forward_pe"])
            and growth >= float(config["near_miss_min_per_share_growth_pct"])
        ):
            lanes.append("cyclical_normalization")

    # Trough-recovery names (FY1 dips below the latest actual before FY3
    # recovers) show a headline FY1->FY3 CAGR that masks a current-year
    # decline; they do not belong in core_garp but remain visible for
    # deep-dive review.
    growth_pattern = _text(row.get("growth_pattern"))
    lane_set = set(lanes)
    if growth_pattern == "trough_recovery" and "core_garp" in lane_set:
        lane_set.discard("core_garp")
        lane_set.add("quality_near_miss")
    return sorted(lane_set)


def compact_candidate(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "symbol": _symbol(row),
        "company_name": row.get("company_name"),
        "sector": row.get("sector"),
        "industry": row.get("industry"),
        "price": row.get("price"),
        "market_cap": row.get("market_cap"),
        "forward_pe": row.get("forward_pe"),
        "forward_eps": row.get("forward_eps"),
        "forward_fiscal_year": row.get("forward_fiscal_year"),
        "analyst_count": row.get("analyst_count"),
        "eps_growth_pct": row.get("eps_growth_pct"),
        "revenue_growth_pct": row.get("revenue_growth_pct"),
        "roic_pct": row.get("roic_pct"),
        "fcf_yield_pct": row.get("fcf_yield_pct"),
        "ev_to_fcf": row.get("ev_to_fcf"),
        "net_debt_to_ebitda": row.get("net_debt_to_ebitda"),
        "cyclicality_score": row.get("cyclicality_score"),
        "provider_prefilter_lanes": row.get("provider_prefilter_lanes", []),
    }


def _project_rows(
    rows: Sequence[Mapping[str, Any]],
    fields: Sequence[str],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for raw in list(rows)[:limit]:
        item = {key: raw.get(key) for key in fields if key in raw}
        output.append(item)
    return output


def _cash_flow_ttm_preview(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    quarters = list(rows)[:4]
    if len(quarters) < 4:
        return {"available": False, "reason": "fewer_than_four_provider_quarters"}
    ocf_values: list[float] = []
    capex_values: list[float] = []
    sbc_values: list[float] = []
    for row in quarters:
        ocf = _first_number(row, "operatingCashFlow", "netCashProvidedByOperatingActivities")
        capex = _first_number(row, "capitalExpenditure", "capitalExpenditures")
        if ocf is None or capex is None:
            return {"available": False, "reason": "provider_quarter_missing_ocf_or_capex"}
        ocf_values.append(ocf)
        capex_values.append(abs(capex))
        sbc_values.append(_first_number(row, "stockBasedCompensation") or 0.0)
    ocf_ttm = sum(ocf_values)
    capex_ttm = sum(capex_values)
    return {
        "available": True,
        "method": "sum_4_provider_quarters_preview",
        "primary_source_verified": False,
        "operating_cash_flow": ocf_ttm,
        "capex_cash_outflow": capex_ttm,
        "standard_fcf": ocf_ttm - capex_ttm,
        "stock_based_compensation": sum(sbc_values),
        "period_ends": [row.get("date") for row in quarters],
    }


def build_fmp_packet(client: FMPClient, row: Mapping[str, Any], output_dir: Path) -> Path:
    """Write a compact provider evidence packet and keep full payloads on disk."""
    symbol = _symbol(row)
    profile = client.get_profile(symbol)
    quote = client.get_quotes([symbol]).get(symbol)
    estimates = client.get_analyst_estimates(symbol, period="annual", limit=6)
    income_annual = client.get_income_statement(symbol, period="annual", limit=6)
    income_quarterly = client.get_income_statement(symbol, period="quarter", limit=8)
    balance_annual = client.get_balance_sheet(symbol, period="annual", limit=6)
    balance_quarterly = client.get_balance_sheet(symbol, period="quarter", limit=8)
    cash_flow_annual = client.get_cash_flow(symbol, period="annual", limit=6)
    cash_flow_quarterly = client.get_cash_flow(symbol, period="quarter", limit=8)
    key_metrics_ttm = client.get_key_metrics_ttm(symbol)
    ratios_ttm = client.get_ratios_ttm(symbol)
    peers = client.get_stock_peers(symbol)

    raw_dir = output_dir.parent / "provider" / "candidate-data" / symbol
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_payloads = {
        "profile": profile,
        "quote": quote,
        "analyst-estimates": estimates,
        "income-annual": income_annual,
        "income-quarterly": income_quarterly,
        "balance-annual": balance_annual,
        "balance-quarterly": balance_quarterly,
        "cash-flow-annual": cash_flow_annual,
        "cash-flow-quarterly": cash_flow_quarterly,
        "key-metrics-ttm": key_metrics_ttm,
        "ratios-ttm": ratios_ttm,
        "peers": peers,
    }
    evidence_paths: dict[str, str] = {}
    for name, payload in raw_payloads.items():
        target = raw_dir / f"{name}.json"
        _write_json(target, payload)
        evidence_paths[name] = str(target.relative_to(output_dir.parent))

    required_next_checks = [
        "corporate_action_preflight",
        "accession_specific_sec_or_official_ir_verification",
        "quarter_and_full_year_period_separation",
        "standard_fcf_primary_source_reconstruction",
        "independent_forecast_bridge",
        "peer_basis_alignment",
        "sector_and_cycle_normalization",
    ]
    if "foreign_private_issuer_review" in (row.get("provider_prefilter_flags") or []):
        required_next_checks.append("form_20f_6k_verification")

    income_fields = (
        "date",
        "calendarYear",
        "period",
        "reportedCurrency",
        "revenue",
        "grossProfit",
        "operatingIncome",
        "ebitda",
        "netIncome",
        "eps",
        "epsdiluted",
        "weightedAverageShsOut",
        "weightedAverageShsOutDil",
        "incomeTaxExpense",
        "interestExpense",
        "interestIncome",
    )
    cash_flow_fields = (
        "date",
        "calendarYear",
        "period",
        "reportedCurrency",
        "netIncome",
        "operatingCashFlow",
        "capitalExpenditure",
        "freeCashFlow",
        "stockBasedCompensation",
        "commonStockIssued",
        "commonStockRepurchased",
        "dividendsPaid",
        "acquisitionsNet",
    )
    balance_fields = (
        "date",
        "calendarYear",
        "period",
        "reportedCurrency",
        "cashAndCashEquivalents",
        "shortTermInvestments",
        "cashAndShortTermInvestments",
        "totalCurrentAssets",
        "totalAssets",
        "shortTermDebt",
        "longTermDebt",
        "totalDebt",
        "netDebt",
        "goodwill",
        "intangibleAssets",
        "totalStockholdersEquity",
    )
    estimate_fields = (
        "symbol",
        "date",
        "fiscalYear",
        "revenueAvg",
        "revenueLow",
        "revenueHigh",
        "epsAvg",
        "epsLow",
        "epsHigh",
        "numAnalystsRevenue",
        "numAnalystsEps",
        "ebitdaAvg",
        "ebitAvg",
        "netIncomeAvg",
        "sgaExpenseAvg",
    )

    packet = {
        "runtime": runtime_metadata(),
        "symbol": symbol,
        "purpose": "provider evidence preview for primary-source underwriting",
        "provider_data_is_not_primary_source_verified": True,
        "discovery": compact_candidate(row),
        "profile": profile,
        "quote": {
            key: quote.get(key)
            for key in (
                "symbol",
                "name",
                "price",
                "marketCap",
                "timestamp",
                "exchange",
                "yearHigh",
                "yearLow",
                "volume",
                "avgVolume",
            )
            if isinstance(quote, Mapping) and key in quote
        },
        "annual_estimates": _project_rows(estimates, estimate_fields, limit=6),
        "income_annual": _project_rows(income_annual, income_fields, limit=4),
        "income_quarterly": _project_rows(income_quarterly, income_fields, limit=8),
        "balance_latest": _project_rows(
            balance_quarterly or balance_annual, balance_fields, limit=2
        ),
        "cash_flow_annual": _project_rows(cash_flow_annual, cash_flow_fields, limit=4),
        "cash_flow_quarterly": _project_rows(cash_flow_quarterly, cash_flow_fields, limit=8),
        "cash_flow_ttm_preview": _cash_flow_ttm_preview(cash_flow_quarterly),
        "key_metrics_ttm": dict(key_metrics_ttm[0]) if key_metrics_ttm else None,
        "ratios_ttm": dict(ratios_ttm[0]) if ratios_ttm else None,
        "peer_symbols": peers[:10],
        "raw_evidence_paths": evidence_paths,
        "required_next_checks": required_next_checks,
    }
    path = output_dir / f"{symbol}.fmp-packet.json"
    _write_json(path, packet)
    return path


def execute_pipeline(
    client: FMPClient,
    config: Mapping[str, Any],
    *,
    analysis_as_of: datetime,
    output_dir: Path,
    include_packets: bool = True,
) -> PipelineResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    audit_dir = output_dir / "audit"
    raw_dir = output_dir / "provider"
    packet_dir = output_dir / "candidate-packets"
    audit_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)

    min_cap = float(config["min_market_cap"])
    max_cap = float(config["max_market_cap"])
    min_price = float(config["min_price"])

    universe_rows, enumeration_audit = collect_listing_universe(
        client,
        min_market_cap=min_cap,
        max_market_cap=max_cap,
        min_price=min_price,
        page_limit=int(config["company_screener_limit"]),
        minimum_band_width=float(config["minimum_market_cap_band_width"]),
        maximum_depth=int(config["maximum_market_cap_band_depth"]),
    )
    if not universe_rows:
        raise ValueError("FMP company screener returned no normalized listing rows")
    profile_overrides = {
        str(key).upper(): str(value)
        for key, value in (config.get("sector_profile_overrides") or {}).items()
    }
    if profile_overrides:
        for row in universe_rows:
            pinned = profile_overrides.get(str(row.get("symbol", "")).upper())
            if pinned:
                row["sector_profile_type"] = pinned
    _write_json(audit_dir / "listing-enumeration-audit.json", enumeration_audit)

    bulk_endpoints = dict(config.get("bulk_endpoints") or {})
    bulk_rows: dict[str, list[dict[str, Any]]] = {}
    year = analysis_as_of.year - 1
    for name, params in (
        ("ratios_ttm", {}),
        ("key_metrics_ttm", {}),
        ("income_growth", {"year": year, "period": "annual"}),
    ):
        endpoint = bulk_endpoints.get(name)
        bulk_rows[name] = client.get_bulk_dataset(endpoint, **params) if endpoint else []
        _write_json(raw_dir / f"{name}.json", bulk_rows[name])
    bulk_merged = merge_bulk_rows(bulk_rows)
    enriched_universe = [
        enrich_listing_from_bulk(row, bulk_merged.get(_symbol(row), {})) for row in universe_rows
    ]

    eod_endpoint = bulk_endpoints.get("eod")
    bulk_liquidity = False
    if eod_endpoint:
        enriched_universe, bulk_liquidity = apply_bulk_liquidity(
            client,
            enriched_universe,
            as_of=analysis_as_of.date(),
            endpoint=eod_endpoint,
            source_id=f"fmp-{eod_endpoint}-{analysis_as_of.date().isoformat()}",
            required_days=int(config["minimum_average_volume_period_days"]),
        )

    estimate_source = f"fmp-analyst-estimates-{analysis_as_of.date().isoformat()}"
    universe_symbols = {_symbol(row) for row in enriched_universe}
    bulk_estimates, bulk_estimate_audit = collect_bulk_annual_estimates(
        client,
        endpoint=_text(bulk_endpoints.get("analyst_estimates")),
        universe_symbols=universe_symbols,
        analysis_as_of=analysis_as_of,
        year_count=int(config["bulk_estimate_years"]),
    )
    _write_json(audit_dir / "bulk-estimates-audit.json", bulk_estimate_audit)

    bulk_coverage = float(bulk_estimate_audit.get("coverage_pct") or 0.0)
    use_bulk_estimates = bool(
        bulk_estimates and bulk_coverage >= float(config["bulk_estimate_minimum_coverage_pct"])
    )
    seed_audit: dict[str, Any] | None = None
    if use_bulk_estimates:
        estimate_frame = [row for row in enriched_universe if _symbol(row) in bulk_estimates]
        estimates_by_symbol = bulk_estimates
        estimate_acquisition_mode = "analyst_estimates_bulk"
    else:
        pre_enrichment_limit = int(config["pre_enrichment_limit"])
        effective_seed_limit = compute_effective_seed_limit(
            pre_enrichment_limit=pre_enrichment_limit,
            seed_limit_cap=int(config["seed_limit_cap"]),
            max_api_calls=int(client.max_api_calls),
            api_calls_made=int(client.api_calls_made),
            quality_probe_limit=int(config["quality_probe_limit"]),
            exact_liquidity_limit=int(config["exact_liquidity_limit"]),
            candidate_packet_reserve_calls=int(config["candidate_packet_reserve_calls"]),
            retry_reserve_calls=int(config["retry_reserve_calls"]),
        )
        estimate_frame, seed_audit = diversified_seed(
            enriched_universe,
            effective_seed_limit,
            run_salt=analysis_as_of.date().isoformat(),
            seed_limit_configured=pre_enrichment_limit,
            reserved_calls=(
                int(config["quality_probe_limit"]) * 2
                + int(config["exact_liquidity_limit"])
                + int(config["candidate_packet_reserve_calls"])
                + int(config["retry_reserve_calls"])
            ),
        )
        _write_json(audit_dir / "seed-audit.json", seed_audit)
        estimates_by_symbol: dict[str, list[dict[str, Any]]] = {}
        for row in estimate_frame:
            symbol = _symbol(row)
            estimates_by_symbol[symbol] = client.get_analyst_estimates(
                symbol, period="annual", limit=6
            )
        estimate_acquisition_mode = "bounded_per_symbol_fallback"

    normalized_estimates = normalize_estimate_frame(
        estimate_frame,
        estimates_by_symbol,
        analysis_as_of=analysis_as_of,
        source_id=estimate_source,
        config=config,
    )

    if not bulk_liquidity:
        liquidity_targets = select_liquidity_targets(
            normalized_estimates,
            config,
            limit=int(config["exact_liquidity_limit"]),
        )
        normalized_estimates = apply_symbol_liquidity(
            client,
            normalized_estimates,
            as_of=analysis_as_of.date(),
            source_id=f"fmp-historical-eod-{analysis_as_of.date().isoformat()}",
            limit=int(config["exact_liquidity_limit"]),
            required_days=int(config["minimum_average_volume_period_days"]),
            target_symbols=liquidity_targets,
        )
    else:
        liquidity_targets = [_symbol(row) for row in normalized_estimates]

    seed = estimate_frame
    universe_sha = _write_jsonl(audit_dir / "universe.jsonl", enriched_universe)

    # Quality probe (v3.6.1): rank the union of lane candidates by best lane
    # score and pull TTM quality metrics (ROIC, FCF yield, EV/FCF, leverage,
    # SBC/revenue) for the top slice before pool selection, so FCF-negative
    # candidates like a 126x-EV/FCF miss can be screened out ahead of the
    # deep-dive step instead of consuming one of its slots.
    lane_membership_map = {
        _symbol(row): lane_memberships(row, config) for row in normalized_estimates
    }
    quality_probe_limit = int(config["quality_probe_limit"])
    quality_probe_targets = select_quality_probe_targets(
        normalized_estimates,
        lane_membership_map,
        limit=quality_probe_limit,
        analysis_as_of=analysis_as_of.isoformat(),
    )
    quality_probe_source_id = f"fmp-key-metrics-ttm-{analysis_as_of.date().isoformat()}"
    normalized_estimates, quality_probe_audit = apply_quality_probe(
        client,
        normalized_estimates,
        target_symbols=quality_probe_targets,
        source_id=quality_probe_source_id,
        analysis_as_of=analysis_as_of,
        actual_source_id=f"fmp-income-statement-annual-{analysis_as_of.date().isoformat()}",
    )
    _write_json(audit_dir / "quality-probe-audit.json", quality_probe_audit)
    normalized_estimates = mark_sector_profile_exhaustion(
        normalized_estimates, source_id=quality_probe_source_id
    )
    normalized_estimates = mark_unit_reconciliation_exhaustion(
        normalized_estimates, source_id=quality_probe_source_id
    )
    # growth_pattern is fixed at normalization (consensus basis) and the probe
    # never relabels it; the recompute below is defensive so pool lane tags
    # always match what lane_memberships would produce for the final rows.
    lane_membership_map = {
        _symbol(row): lane_memberships(row, config) for row in normalized_estimates
    }

    enriched_sha = _write_jsonl(audit_dir / "enriched-estimates.jsonl", normalized_estimates)

    lanes: dict[str, list[dict[str, Any]]] = {lane: [] for lane in ALLOWED_LANES}
    for row in normalized_estimates:
        symbol = _symbol(row)
        growth_pattern = _text(row.get("growth_pattern"))
        is_fpi = _is_foreign_private_issuer(row)
        for lane in lane_membership_map.get(symbol, []):
            copy = dict(row)
            flags = set(copy.get("provider_prefilter_flags") or [])
            if growth_pattern == "trough_recovery":
                flags.add("earnings_recovery")
            if is_fpi:
                flags.add("foreign_private_issuer_review")
            if flags:
                copy["provider_prefilter_flags"] = sorted(flags)
            lanes[lane].append(copy)
    for lane, rows in lanes.items():
        _write_jsonl(audit_dir / f"lane-{lane}.jsonl", rows)

    pool, discovery_audit = build_pool(
        universe_rows=enriched_universe,
        lane_rows=lanes,
        analysis_as_of=analysis_as_of.isoformat(),
        source_ids=[estimate_source],
        per_lane=int(config["provider_prefilter_per_lane"]),
        max_pool=int(config["provider_prefilter_pool_size"]),
        minimum_pool=int(config["provider_prefilter_minimum_pool"]),
        requested_min_market_cap=min_cap,
        requested_max_market_cap=max_cap,
        provider_exhausted=True,
        provider_exhausted_scope="estimate_seed",
    )
    pool_sha = _write_jsonl(audit_dir / "provider-prefilter-pool.jsonl", pool)
    discovery_audit.update(
        {
            "artifact_path": "provider-prefilter-pool.jsonl",
            "artifact_sha256": pool_sha,
            "universe_artifact_sha256": universe_sha,
            "enriched_estimates_sha256": enriched_sha,
            "estimate_acquisition_mode": estimate_acquisition_mode,
            "bulk_estimate_audit": bulk_estimate_audit,
            "exact_liquidity_target_count": len(liquidity_targets),
            "quality_probe": quality_probe_audit,
            # ACTUAL attempted count (len of the estimate frame), never the
            # configured seed LIMIT: a 180 limit over a 50-name universe must
            # not fabricate 360% coverage.
            "economic_attempt_count": len(seed),
            "economic_attempt_coverage_pct": round(
                len(seed) / len(enriched_universe) * 100.0 if enriched_universe else 0.0, 6
            ),
            "economically_evaluable_count": sum(
                1
                for row in normalized_estimates
                if str(row.get("estimate_normalization_status") or "") == "valid"
            ),
            "economically_evaluable_coverage_pct": round(
                (
                    sum(
                        1
                        for row in normalized_estimates
                        if str(row.get("estimate_normalization_status") or "") == "valid"
                    )
                    / len(enriched_universe)
                    * 100.0
                    if enriched_universe
                    else 0.0
                ),
                6,
            ),
            "listing_provider_exhausted": True,
            "estimate_seed_exhausted": True,
            "economic_candidate_universe_exhausted": economic_scope_complete(
                estimate_acquisition_mode=estimate_acquisition_mode,
                covered_symbol_count=int(bulk_estimate_audit.get("covered_symbol_count") or 0),
                universe_symbol_count=int(bulk_estimate_audit.get("universe_symbol_count") or 0),
            ),
        }
    )
    if seed_audit is not None:
        discovery_audit["seed_audit"] = seed_audit
    _write_json(audit_dir / "provider-prefilter-audit.json", discovery_audit)

    screen_config = dict(SCREEN_DEFAULTS)
    screen_config.update(config)
    screen_config["max_deep_dive_candidates"] = int(config["max_deep_dive_candidates"])
    universe_decisions, candidate_decisions, audit, selected, queue = run_layered(
        enriched_universe,
        pool,
        screen_config,
        analysis_as_of=analysis_as_of.isoformat(),
        universe_source_ids=[f"fmp-company-screener-{analysis_as_of.date().isoformat()}"],
        candidate_source_ids=[estimate_source],
        candidate_generation_mode="provider_prefilter",
        retrieval_min_market_cap=min_cap,
        retrieval_max_market_cap=max_cap,
        requested_min_market_cap=min_cap,
        requested_max_market_cap=max_cap,
        retrieval_scope_explicit=True,
        candidate_pool_exhausted=True,
        provider_reported_total=None,
        pages_fetched=int(enumeration_audit["query_count"]),
        pagination_exhausted=bool(enumeration_audit["enumeration_verified"]),
        band_audit=enumeration_audit["bands"],
        discovery_audit=discovery_audit,
    )

    universe_decisions_path = audit_dir / "universe-audit-results.jsonl"
    candidate_decisions_path = audit_dir / "broad-screen-results.jsonl"
    queue_path = audit_dir / "enrichment-queue.json"
    universe_decisions_path.write_text(
        "".join(_canonical_line(row) for row in universe_decisions), encoding="utf-8"
    )
    candidate_decisions_path.write_text(
        "".join(_canonical_line(row) for row in candidate_decisions), encoding="utf-8"
    )
    _write_json(queue_path, queue)
    audit["universe"].update(
        {
            "artifact_path": universe_decisions_path.name,
            "artifact_sha256": hashlib.sha256(universe_decisions_path.read_bytes()).hexdigest(),
        }
    )
    audit["candidate_pool"].update(
        {
            "artifact_path": candidate_decisions_path.name,
            "artifact_sha256": hashlib.sha256(candidate_decisions_path.read_bytes()).hexdigest(),
        }
    )
    audit["enrichment"].update(
        {
            "artifact_path": queue_path.name,
            "artifact_sha256": hashlib.sha256(queue_path.read_bytes()).hexdigest(),
        }
    )
    _write_json(audit_dir / "broad-screen-audit.json", audit)

    selected_rows = {_symbol(row): row for row in pool if _symbol(row) in set(selected)}
    packet_paths: list[str] = []
    if include_packets:
        for symbol in selected:
            packet_paths.append(str(build_fmp_packet(client, selected_rows[symbol], packet_dir)))

    listing_universe_count = len(enriched_universe)
    estimate_seed_count = len(seed)
    estimate_seed_coverage_pct = (
        estimate_seed_count / listing_universe_count * 100.0 if listing_universe_count else 0.0
    )
    valid_estimate_count = sum(
        1
        for row in normalized_estimates
        if str(row.get("estimate_normalization_status") or "") == "valid"
    )
    valid_estimate_coverage_pct = (
        valid_estimate_count / listing_universe_count * 100.0 if listing_universe_count else 0.0
    )
    economic_screen_scope_complete = economic_scope_complete(
        estimate_acquisition_mode=estimate_acquisition_mode,
        covered_symbol_count=int(bulk_estimate_audit.get("covered_symbol_count") or 0),
        universe_symbol_count=int(bulk_estimate_audit.get("universe_symbol_count") or 0),
    )
    old_scope_complete = bool(audit.get("scope", {}).get("scope_complete"))
    quality_probe_count = _coverage_count(quality_probe_audit.get("attempted"))
    deep_dive_count = len(selected)
    ranking_scope = classify_ranking_scope(
        economic_attempt_count=estimate_seed_count,
        listing_universe_count=listing_universe_count,
        economic_scope_complete=economic_screen_scope_complete,
        unresolved_queue_count=len(queue),
    )
    coverage_block = build_coverage_block(
        ranking_scope=ranking_scope,
        listing_universe_count=listing_universe_count,
        economic_attempt_count=estimate_seed_count,
        economically_evaluable_count=valid_estimate_count,
        quality_probe_count=quality_probe_count,
        deep_dive_count=deep_dive_count,
    )
    # build_coverage_block also emits listing_universe_count; the summary
    # already carries it at top level, which is harmless duplication.
    coverage_block = {k: v for k, v in coverage_block.items() if k != "listing_universe_count"}

    pool_status = str(audit.get("candidate_pool_status") or "")
    selection_outcome = str(audit.get("selection_outcome") or "")
    if selected and pool_status == "sufficient":
        status = "ready_for_underwriting"
        action = "complete_primary_source_underwriting"
    elif not selected and pool_status == "no_qualifying_candidates":
        status = "no_candidates_in_scoped_pool"
        action = "publish_scoped_no_candidates"
    else:
        status = "needs_enrichment"
        action = "repair_discovery_or_enrichment_contract"

    next_action = {
        "runtime": runtime_metadata(),
        "action": action,
        "symbols": selected,
        "user_confirmation_required": False,
        "read_only": [
            "run-summary.json",
            "audit/broad-screen-audit.json",
            "candidate-packets/*.fmp-packet.json",
        ],
        "do_not_read_bulk_provider_payloads_into_model_context": True,
        "listing_enumeration_complete": old_scope_complete,
        "economic_screen_scope_complete": economic_screen_scope_complete,
        "listing_universe_count": listing_universe_count,
        "estimate_seed_count": estimate_seed_count,
        "estimate_seed_coverage_pct": round(estimate_seed_coverage_pct, 6),
        "valid_estimate_count": valid_estimate_count,
        "valid_estimate_coverage_pct": round(valid_estimate_coverage_pct, 6),
        **coverage_block,
        "required_after_underwriting": [
            "manage_run_state.py assemble",
            "evaluate_candidates.py --strict --require-final",
            "prepublish_audit.py",
            "bundle_run_artifacts.py",
        ],
    }
    _write_json(output_dir / "NEXT_ACTION.json", next_action)

    summary = {
        "runtime": runtime_metadata(),
        "run_id": output_dir.name,
        "status": status,
        "analysis_as_of": analysis_as_of.isoformat(),
        "conclusion_scope": audit.get("conclusion_scope"),
        # `scope_complete` communicates *listing enumeration* completeness
        # only -- it says nothing about economic (estimate/fundamental)
        # coverage. See `economic_screen_scope_complete` for that.
        "scope_complete": old_scope_complete,
        "scope_complete_deprecated_note": (
            "listing enumeration only; see economic_screen_scope_complete"
        ),
        "listing_enumeration_complete": old_scope_complete,
        "economic_screen_scope_complete": economic_screen_scope_complete,
        "listing_universe_count": listing_universe_count,
        "estimate_seed_count": estimate_seed_count,
        "estimate_seed_coverage_pct": round(estimate_seed_coverage_pct, 6),
        "valid_estimate_count": valid_estimate_count,
        "valid_estimate_coverage_pct": round(valid_estimate_coverage_pct, 6),
        **coverage_block,
        "listing_enumeration_verified": bool(enumeration_audit["enumeration_verified"]),
        "listing_query_count": int(enumeration_audit["query_count"]),
        "universe_count": len(enriched_universe),
        "seed_count": len(seed),
        "seed_audit": seed_audit,
        "normalized_estimate_count": len(normalized_estimates),
        "estimate_acquisition_mode": estimate_acquisition_mode,
        "bulk_estimate_coverage_pct": bulk_coverage,
        "exact_liquidity_target_count": len(liquidity_targets),
        "provider_prefilter_pool_count": len(pool),
        "selected_symbols": selected,
        "selected_candidates": [compact_candidate(selected_rows[symbol]) for symbol in selected],
        "enrichment_queue_count": len(queue),
        "candidate_pool_status": pool_status,
        "selection_outcome": selection_outcome,
        "bulk_liquidity_used": bulk_liquidity,
        "lane_counts": {lane: len(rows) for lane, rows in lanes.items()},
        "provider_diagnostics": client.diagnostics(),
        "artifacts": {
            "run_summary": "run-summary.json",
            "next_action": "NEXT_ACTION.json",
            "listing_enumeration_audit": "audit/listing-enumeration-audit.json",
            "provider_prefilter_audit": "audit/provider-prefilter-audit.json",
            "broad_screen_audit": "audit/broad-screen-audit.json",
            "candidate_packets": [str(Path(path).relative_to(output_dir)) for path in packet_paths],
            "raw_provider_dir": "provider",
        },
    }
    _write_json(output_dir / "run-summary.json", summary)
    exit_code = 0 if status in {"ready_for_underwriting", "no_candidates_in_scoped_pool"} else 2
    return PipelineResult(summary=summary, exit_code=exit_code)


def prepare_screen_full_snapshot(
    snapshot_dir: Path,
    *,
    analysis_as_of: datetime,
    config: Mapping[str, Any],
    screening_started_at: datetime | None = None,
) -> dict[str, Any]:
    """Read-only preflight for the current-only full-snapshot screen.

    Screen-time liquidity and TTM quality probes are current provider data.
    Historical replays must not mix that evidence into an old snapshot, so
    this stage accepts only an ``analysis_as_of`` close to its wall-clock
    start.  The preflight runs before FMPClient construction in ``main``;
    invalid snapshots therefore create no cache, raw-store, or run tree.
    """
    started = screening_started_at or datetime.now(timezone.utc)
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    if analysis_as_of.tzinfo is None:
        analysis_as_of = analysis_as_of.replace(tzinfo=timezone.utc)
    skew = float(config.get("full_snapshot_screening_clock_skew_seconds", 300))
    if skew < 0:
        raise ValueError("full_snapshot_screening_clock_skew_seconds must be non-negative")
    if abs((analysis_as_of - started).total_seconds()) > skew:
        raise ValueError(
            "screen-full-snapshot is current-only because its liquidity and quality "
            "enrichment use current provider evidence"
        )
    target_pool_size = int(config.get("full_snapshot_pool_size", 50))
    if not 30 <= target_pool_size <= 50:
        raise ValueError("full_snapshot_pool_size must be between 30 and 50")
    deep_dive_limit = int(config.get("full_snapshot_deep_dive_candidates", 5))
    if deep_dive_limit != 5:
        raise ValueError("full_snapshot_deep_dive_candidates must be 5")
    max_staleness = float(config.get("full_snapshot_max_staleness_days", 7))
    bundle = snapshot_store.load_verified_snapshot(
        snapshot_dir,
        screening_as_of=analysis_as_of,
        max_staleness_days=max_staleness,
        clock_skew_seconds=skew,
    )
    verdict = dict(bundle["verdict"])
    verdict.update(
        {
            "screening_started_at": started.astimezone(timezone.utc).isoformat(),
            "screening_clock_skew_seconds": skew,
        }
    )
    bundle["verdict"] = verdict
    if verdict.get("ready_for_screening") is not True:
        problems = verdict.get("problems") or []
        detail = "; ".join(str(value) for value in problems[:5]) or "readiness checks failed"
        raise ValueError(f"snapshot is not ready for screening: {detail}")
    enumeration = dict(verdict.get("listing_enumeration") or {})
    frozen_minimum = float(enumeration["requested_min_market_cap"])
    frozen_maximum = float(enumeration["requested_max_market_cap"])
    frozen_min_price = float(enumeration["min_price"])
    requested_minimum = float(config["min_market_cap"])
    requested_maximum = float(config["max_market_cap"])
    requested_min_price = float(config["min_price"])
    if (
        frozen_minimum > requested_minimum
        or frozen_maximum < requested_maximum
        or frozen_min_price > requested_min_price
    ):
        raise ValueError("snapshot listing enumeration does not cover the requested screen scope")
    for row in bundle.get("rows") or []:
        expected = snapshot_store.classify_symbol(
            row,
            row,
            requires_unit_reconciliation=requires_unit_reconciliation,
            minimum_plausible_forward_pe=float(config.get("minimum_plausible_forward_pe", 2.0)),
        )
        if row.get("snapshot_classification") != expected:
            raise ValueError(
                f"snapshot classification mismatch for {_symbol(row)}: "
                f"recorded {row.get('snapshot_classification')!r}, expected {expected!r}"
            )
    return bundle


def validate_current_snapshot_collection(
    *,
    analysis_as_of: datetime,
    config: Mapping[str, Any],
    collection_started_at: datetime | None = None,
) -> datetime:
    """Reject historical/future normalization bases before collection side effects."""
    started = collection_started_at or datetime.now(timezone.utc)
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    if analysis_as_of.tzinfo is None:
        analysis_as_of = analysis_as_of.replace(tzinfo=timezone.utc)
    skew = float(config.get("full_snapshot_collection_clock_skew_seconds", 300))
    if skew < 0:
        raise ValueError("full_snapshot_collection_clock_skew_seconds must be non-negative")
    if abs((analysis_as_of - started).total_seconds()) > skew:
        raise ValueError(
            "collect-estimates is current-only because analysis_as_of fixes the estimate "
            "normalization basis"
        )
    return started.astimezone(timezone.utc)


def _snapshot_lane_rows(
    rows: Sequence[Mapping[str, Any]],
    config: Mapping[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    lane_rows: dict[str, list[dict[str, Any]]] = {lane: [] for lane in ALLOWED_LANES}
    for raw in rows:
        row = dict(raw)
        symbol = _symbol(row)
        growth_pattern = _text(row.get("growth_pattern"))
        is_fpi = _is_foreign_private_issuer(row)
        for lane in lane_memberships(row, config):
            copy = dict(row)
            flags = set(copy.get("provider_prefilter_flags") or [])
            if growth_pattern == "trough_recovery":
                flags.add("earnings_recovery")
            if is_fpi:
                flags.add("foreign_private_issuer_review")
            if flags:
                copy["provider_prefilter_flags"] = sorted(flags)
            copy["symbol"] = symbol
            lane_rows[lane].append(copy)
    return lane_rows


def _attach_snapshot_attempts(
    decisions: Sequence[Mapping[str, Any]],
    snapshot_rows: Sequence[Mapping[str, Any]],
    *,
    snapshot_id: str,
    verification_digest: str,
) -> list[dict[str, Any]]:
    by_symbol = {_symbol(row): row for row in snapshot_rows}
    output: list[dict[str, Any]] = []
    for raw in decisions:
        row = dict(raw)
        source = by_symbol.get(_symbol(row))
        if source is None:
            raise ValueError(f"universe audit symbol {_symbol(row)} is absent from snapshot")
        row["estimate_attempt"] = {
            "snapshot_id": snapshot_id,
            "snapshot_verification_digest": verification_digest,
            "shard": source.get("snapshot_shard"),
            "retrieved_at": source.get("snapshot_retrieved_at"),
            "classification": source.get("snapshot_classification"),
            "served_from_cache": source.get("snapshot_served_from_cache"),
        }
        output.append(row)
    return output


def execute_screen_full_snapshot(
    client: FMPClient,
    config: Mapping[str, Any],
    *,
    analysis_as_of: datetime,
    output_dir: Path,
    prepared_snapshot: Mapping[str, Any],
    include_packets: bool = True,
) -> PipelineResult:
    """Screen a deeply verified, current full-universe estimate snapshot."""
    verdict = dict(prepared_snapshot.get("verdict") or {})
    snapshot_rows = [dict(row) for row in (prepared_snapshot.get("rows") or [])]
    verification_digest = str(prepared_snapshot.get("verification_digest") or "")
    if (
        verdict.get("ready_for_screening") is not True
        or len(verification_digest) != 64
        or not snapshot_rows
    ):
        raise ValueError("execute_screen_full_snapshot requires a prepared verified snapshot")

    output_dir.mkdir(parents=True, exist_ok=True)
    audit_dir = output_dir / "audit"
    packet_dir = output_dir / "candidate-packets"
    audit_dir.mkdir(parents=True, exist_ok=True)

    snapshot_id = str(verdict.get("snapshot_id") or "")
    universe_rows = sorted(snapshot_rows, key=_symbol)
    evaluable_rows = [
        dict(row) for row in universe_rows if row.get("snapshot_classification") == "evaluable"
    ]
    target_pool_size = int(config.get("full_snapshot_pool_size", 50))
    # The market-wide pool target and exact-liquidity work must move together;
    # retaining the bounded path's default 40 would silently cap a 50-name pool.
    eligible_rows = [row for row in evaluable_rows if lane_memberships(row, config)]
    ordered_liquidity_targets = select_liquidity_targets(
        eligible_rows,
        config,
        limit=len(eligible_rows),
    )
    required_liquidity_days = int(config["minimum_average_volume_period_days"])
    enriched_rows = [dict(row) for row in evaluable_rows]
    liquidity_targets: list[str] = []
    valid_liquidity_symbols: set[str] = set()
    # Backfill past failed/empty histories. A short pool can claim exhaustion
    # only after every economically eligible symbol has an explicit outcome.
    for symbol in ordered_liquidity_targets:
        enriched_rows = apply_symbol_liquidity(
            client,
            enriched_rows,
            as_of=analysis_as_of.date(),
            source_id=f"fmp-historical-eod-{analysis_as_of.date().isoformat()}",
            limit=1,
            required_days=required_liquidity_days,
            target_symbols=[symbol],
        )
        liquidity_targets.append(symbol)
        row = next(item for item in enriched_rows if _symbol(item) == symbol)
        if (
            _first_number(row, "average_daily_dollar_volume") is not None
            and int(_first_number(row, "average_volume_period_days") or 0)
            >= required_liquidity_days
        ):
            valid_liquidity_symbols.add(symbol)
        if len(valid_liquidity_symbols) >= target_pool_size:
            break
    eligible_liquidity_exhausted = len(liquidity_targets) == len(ordered_liquidity_targets)

    preliminary_pool, _ = build_pool(
        universe_rows=universe_rows,
        lane_rows=_snapshot_lane_rows(enriched_rows, config),
        analysis_as_of=analysis_as_of.isoformat(),
        source_ids=[f"snapshot:{snapshot_id}"],
        per_lane=int(config["provider_prefilter_per_lane"]),
        max_pool=target_pool_size,
        minimum_pool=min(30, target_pool_size),
        requested_min_market_cap=float(config["min_market_cap"]),
        requested_max_market_cap=float(config["max_market_cap"]),
        provider_exhausted=eligible_liquidity_exhausted,
        provider_exhausted_scope=(
            "economic_candidate_universe" if eligible_liquidity_exhausted else None
        ),
    )
    probe_symbols = [_symbol(row) for row in preliminary_pool]
    probed_rows, quality_probe_audit = apply_quality_probe(
        client,
        enriched_rows,
        target_symbols=probe_symbols,
        source_id=f"fmp-key-metrics-ttm-{analysis_as_of.date().isoformat()}",
        analysis_as_of=analysis_as_of,
        actual_source_id=f"fmp-income-statement-annual-{analysis_as_of.date().isoformat()}",
    )
    probed_rows = mark_sector_profile_exhaustion(
        probed_rows,
        source_id=f"fmp-key-metrics-ttm-{analysis_as_of.date().isoformat()}",
    )
    probed_rows = mark_unit_reconciliation_exhaustion(
        probed_rows,
        source_id=f"fmp-key-metrics-ttm-{analysis_as_of.date().isoformat()}",
    )
    # Never backfill the final pool with an unprobed name. If probes remove
    # names from a full preliminary pool, the short-pool proof stays false and
    # the stage fails closed instead of claiming exhaustion.
    probed_symbol_set = set(probe_symbols)
    final_input_rows = [row for row in probed_rows if _symbol(row) in probed_symbol_set]
    pool, discovery_audit = build_pool(
        universe_rows=universe_rows,
        lane_rows=_snapshot_lane_rows(final_input_rows, config),
        analysis_as_of=analysis_as_of.isoformat(),
        source_ids=[f"snapshot:{snapshot_id}"],
        per_lane=int(config["provider_prefilter_per_lane"]),
        max_pool=target_pool_size,
        minimum_pool=min(30, target_pool_size),
        requested_min_market_cap=float(config["min_market_cap"]),
        requested_max_market_cap=float(config["max_market_cap"]),
        provider_exhausted=eligible_liquidity_exhausted,
        provider_exhausted_scope=(
            "economic_candidate_universe" if eligible_liquidity_exhausted else None
        ),
    )

    pool_sha = _write_jsonl(audit_dir / "provider-prefilter-pool.jsonl", pool)
    classification_totals = dict(verdict.get("classified_totals") or {})
    eligible_pool_exhausted = len(pool) >= target_pool_size or eligible_liquidity_exhausted
    discovery_audit.update(
        {
            "valid": bool(discovery_audit.get("valid")) and eligible_pool_exhausted,
            "selection_method": "sharded_snapshot_multilane",
            "artifact_path": "provider-prefilter-pool.jsonl",
            "artifact_sha256": pool_sha,
            "input_row_count": len(universe_rows),
            "selected_count": len(pool),
            "selected_symbols": sorted(_symbol(row) for row in pool),
            "target_pool_size": target_pool_size,
            "preliminary_pool_count": len(preliminary_pool),
            "eligible_pool_exhausted": eligible_pool_exhausted,
            "estimate_acquisition_mode": "sharded_snapshot",
            "economic_attempt_count": len(universe_rows),
            "economically_evaluable_count": len(evaluable_rows),
            "snapshot_id": snapshot_id,
            "snapshot_verification_digest": verification_digest,
            "snapshot_verification": verdict,
            "snapshot_classification_totals": classification_totals,
            "quality_probe": quality_probe_audit,
            "exact_liquidity_target_count": len(liquidity_targets),
            "exact_liquidity_eligible_count": len(ordered_liquidity_targets),
            "exact_liquidity_valid_count": len(valid_liquidity_symbols),
            "economic_candidate_universe_exhausted": True,
        }
    )
    _write_json(audit_dir / "provider-prefilter-audit.json", discovery_audit)
    _write_json(audit_dir / "snapshot-verification.json", verdict)
    _write_json(audit_dir / "quality-probe-audit.json", quality_probe_audit)
    _write_jsonl(audit_dir / "enriched-estimates.jsonl", probed_rows)
    for lane, rows in _snapshot_lane_rows(final_input_rows, config).items():
        _write_jsonl(audit_dir / f"lane-{lane}.jsonl", rows)

    screen_config = dict(SCREEN_DEFAULTS)
    screen_config.update(config)
    screen_config["max_deep_dive_candidates"] = int(
        config.get("full_snapshot_deep_dive_candidates", 5)
    )
    enumeration = dict(verdict.get("listing_enumeration") or {})
    universe_decisions, candidate_decisions, audit, selected, queue = run_layered(
        universe_rows,
        pool,
        screen_config,
        analysis_as_of=analysis_as_of.isoformat(),
        universe_source_ids=[f"snapshot:{snapshot_id}"],
        candidate_source_ids=[f"snapshot:{snapshot_id}"],
        candidate_generation_mode="sharded_snapshot",
        retrieval_min_market_cap=float(enumeration["requested_min_market_cap"]),
        retrieval_max_market_cap=float(enumeration["requested_max_market_cap"]),
        requested_min_market_cap=float(config["min_market_cap"]),
        requested_max_market_cap=float(config["max_market_cap"]),
        retrieval_scope_explicit=True,
        candidate_pool_exhausted=True,
        provider_reported_total=int(enumeration.get("row_count") or 0),
        pages_fetched=int(enumeration.get("query_count") or 0),
        pagination_exhausted=enumeration.get("pagination_exhausted") is True,
        band_audit=enumeration.get("bands") or [],
        discovery_audit=discovery_audit,
    )
    universe_decisions = _attach_snapshot_attempts(
        universe_decisions,
        universe_rows,
        snapshot_id=snapshot_id,
        verification_digest=verification_digest,
    )

    universe_path = audit_dir / "universe-audit-results.jsonl"
    candidate_path = audit_dir / "broad-screen-results.jsonl"
    queue_path = audit_dir / "enrichment-queue.json"
    universe_path.write_text(
        "".join(_canonical_line(row) for row in universe_decisions), encoding="utf-8"
    )
    candidate_path.write_text(
        "".join(_canonical_line(row) for row in candidate_decisions), encoding="utf-8"
    )
    _write_json(queue_path, queue)
    audit["universe"].update(
        {
            "artifact_path": universe_path.name,
            "artifact_sha256": hashlib.sha256(universe_path.read_bytes()).hexdigest(),
            "snapshot_classification_totals": classification_totals,
        }
    )
    audit["candidate_pool"].update(
        {
            "artifact_path": candidate_path.name,
            "artifact_sha256": hashlib.sha256(candidate_path.read_bytes()).hexdigest(),
        }
    )
    audit["enrichment"].update(
        {
            "artifact_path": queue_path.name,
            "artifact_sha256": hashlib.sha256(queue_path.read_bytes()).hexdigest(),
        }
    )
    audit["snapshot_verification"] = verdict
    audit["snapshot_verification_digest"] = verification_digest
    _write_json(audit_dir / "broad-screen-audit.json", audit)

    selected_rows = {_symbol(row): row for row in pool if _symbol(row) in set(selected)}
    packet_paths: list[str] = []
    if include_packets:
        for symbol in selected:
            packet_paths.append(str(build_fmp_packet(client, selected_rows[symbol], packet_dir)))

    ranking_scope = classify_ranking_scope(
        economic_attempt_count=len(universe_rows),
        listing_universe_count=len(universe_rows),
        economic_scope_complete=bool(verdict.get("ready_for_screening")),
        unresolved_queue_count=len(queue),
    )
    if audit.get("conclusion_scope") != "full_listing_universe":
        ranking_scope = "diagnostic"
    coverage = build_coverage_block(
        ranking_scope=ranking_scope,
        listing_universe_count=len(universe_rows),
        economic_attempt_count=len(universe_rows),
        economically_evaluable_count=len(evaluable_rows),
        quality_probe_count=_coverage_count(quality_probe_audit.get("attempted")),
        deep_dive_count=len(selected),
    )
    pool_status = str(audit.get("candidate_pool_status") or "")
    if selected and pool_status == "sufficient" and ranking_scope == "final_marketwide":
        status = "ready_for_underwriting"
        action = "complete_primary_source_underwriting"
    elif (
        not selected
        and pool_status == "no_qualifying_candidates"
        and ranking_scope == "final_marketwide"
    ):
        status = "no_candidates_in_marketwide_snapshot"
        action = "publish_marketwide_no_candidates"
    else:
        status = "needs_enrichment"
        action = "repair_snapshot_screening_contract"

    common = {
        "runtime": runtime_metadata(),
        "run_id": output_dir.name,
        "status": status,
        "stage": "screen-full-snapshot",
        "analysis_as_of": analysis_as_of.isoformat(),
        "conclusion_scope": audit.get("conclusion_scope"),
        "economic_screen_scope_complete": bool(verdict.get("ready_for_screening")),
        "estimate_acquisition_mode": "sharded_snapshot",
        "snapshot_id": snapshot_id,
        "snapshot_verification_digest": verification_digest,
        "snapshot_verification": verdict,
        "snapshot_classification_totals": classification_totals,
        **coverage,
        "estimate_seed_count": len(universe_rows),
        "estimate_seed_coverage_pct": 100.0,
        "valid_estimate_count": len(evaluable_rows),
        "valid_estimate_coverage_pct": round(len(evaluable_rows) / len(universe_rows) * 100.0, 6),
        "provider_prefilter_pool_count": len(pool),
        "quality_probe_count": _coverage_count(quality_probe_audit.get("attempted")),
        "exact_liquidity_target_count": len(liquidity_targets),
        "selected_symbols": selected,
        "selected_candidates": [compact_candidate(selected_rows[symbol]) for symbol in selected],
        "enrichment_queue_count": len(queue),
        "candidate_pool_status": pool_status,
        "selection_outcome": audit.get("selection_outcome"),
        "provider_diagnostics": client.diagnostics(),
    }
    next_action = {
        **common,
        "action": action,
        "symbols": selected,
        "user_confirmation_required": False,
        "do_not_read_bulk_provider_payloads_into_model_context": True,
        "required_after_underwriting": [
            "manage_run_state.py assemble",
            "evaluate_candidates.py --strict --require-final",
            "prepublish_audit.py",
            "bundle_run_artifacts.py",
        ],
    }
    _write_json(output_dir / "NEXT_ACTION.json", next_action)
    summary = {
        **common,
        "artifacts": {
            "run_summary": "run-summary.json",
            "next_action": "NEXT_ACTION.json",
            "snapshot_verification": "audit/snapshot-verification.json",
            "provider_prefilter_audit": "audit/provider-prefilter-audit.json",
            "broad_screen_audit": "audit/broad-screen-audit.json",
            "candidate_packets": [str(Path(path).relative_to(output_dir)) for path in packet_paths],
        },
    }
    _write_json(output_dir / "run-summary.json", summary)
    return PipelineResult(
        summary=summary,
        exit_code=0
        if status in {"ready_for_underwriting", "no_candidates_in_marketwide_snapshot"}
        else 2,
    )


def execute_collect_estimates(
    client: FMPClient,
    config: Mapping[str, Any],
    *,
    analysis_as_of: datetime,
    snapshot_dir: Path,
    shard_index: int,
    shard_count: int,
    resume: bool,
    collection_started_at: datetime | None = None,
) -> PipelineResult:
    """Collect minimal FY1-FY3 estimates for one deterministic universe shard.

    First invocation freezes the listing universe into ``snapshot_dir``
    (``snapshot-manifest.json`` + ``universe.jsonl``); every later shard run
    writes into that frozen snapshot only. Each attempted symbol is
    normalized and classified (``evaluable / no_estimates / negative_eps /
    unit_mismatch / excluded``) so that, once every shard is complete, the
    classification counts sum exactly to the frozen universe — the
    precondition ``screen-full-snapshot`` will demand before ever emitting
    ``ranking_scope: final_marketwide``. Budget exhaustion mid-shard leaves
    the shard honestly ``partial`` (exit code 3) and is resumable.
    """
    validate_current_snapshot_collection(
        analysis_as_of=analysis_as_of,
        config=config,
        collection_started_at=collection_started_at,
    )
    if shard_count <= 0 or not (0 <= shard_index < shard_count):
        raise ValueError("shard_index must satisfy 0 <= shard_index < shard_count")
    if (snapshot_dir / snapshot_store.MANIFEST_NAME).exists():
        manifest = snapshot_store.load_manifest(snapshot_dir)
        if int(manifest.get("shard_count") or 0) != shard_count:
            raise ValueError(
                f"snapshot at {snapshot_dir} was created with shard_count="
                f"{manifest.get('shard_count')}; got {shard_count}"
            )
        # Re-verify the freeze before any API access or shard append: a
        # swapped universe.jsonl must never collect under the frozen id.
        universe_rows = snapshot_store.load_verified_universe(snapshot_dir, manifest)
    else:
        universe_rows, enumeration_audit = collect_listing_universe(
            client,
            min_market_cap=float(config["min_market_cap"]),
            max_market_cap=float(config["max_market_cap"]),
            min_price=float(config["min_price"]),
            page_limit=int(config["company_screener_limit"]),
            minimum_band_width=float(config["minimum_market_cap_band_width"]),
            maximum_depth=int(config["maximum_market_cap_band_depth"]),
        )
        if not universe_rows:
            raise ValueError("FMP company screener returned no normalized listing rows")
        profile_overrides = {
            str(key).upper(): str(value)
            for key, value in (config.get("sector_profile_overrides") or {}).items()
        }
        for row in universe_rows:
            pinned = profile_overrides.get(str(row.get("symbol", "")).upper())
            if pinned:
                row["sector_profile_type"] = pinned
        manifest = snapshot_store.create_snapshot(
            snapshot_dir,
            universe_rows,
            shard_count=shard_count,
            as_of=analysis_as_of,
            enumeration_audit=enumeration_audit,
        )

    shard_listings = [
        row
        for row in universe_rows
        if snapshot_store.stable_shard(_symbol(row), shard_count) == shard_index
    ]
    existing = snapshot_store.load_shard_rows(snapshot_dir, shard_index)
    if existing and not resume:
        raise ValueError(
            f"shard {shard_index} already has {len(existing)} rows; pass --resume to continue"
        )
    done = {str(row.get("symbol")) for row in existing}
    pending = [row for row in shard_listings if _symbol(row) not in done]

    source_id = f"fmp-analyst-estimates-{analysis_as_of.date().isoformat()}"
    calls_before = int(client.diagnostics().get("api_calls_made") or 0)
    buffered: list[dict[str, Any]] = []
    fetch_failed_symbols: list[str] = []
    budget_exhausted = False
    for listing in pending:
        symbol = _symbol(listing)
        try:
            fetched = client.get_analyst_estimates_detailed(symbol, period="annual", limit=6)
        except ApiCallBudgetExceeded:
            budget_exhausted = True
            break
        if str(fetched.get("status")) == "failed":
            # The client reports provider failures explicitly (HTTP errors,
            # offline misses, HTTP-200 error payloads, schema failures);
            # such a symbol stays UNCOLLECTED — a failure classified as
            # no_estimates would satisfy the marketwide invariant without
            # ever fetching anything.
            fetch_failed_symbols.append(symbol)
            continue
        estimates = [dict(row) for row in (fetched.get("rows") or [])]
        served_from_cache = bool(fetched.get("served_from_cache"))
        epoch = fetched.get("retrieved_at")
        # The stamp is the time the ADOPTED payload was actually fetched
        # over HTTP (a cache hit keeps the entry's creation time, reported
        # by the client for the exact response it returned). Unknown
        # provenance stays null — never back-filled with "now" (fail closed
        # for PR B's staleness gate).
        retrieved_at = (
            datetime.fromtimestamp(float(epoch), tz=timezone.utc).isoformat()
            if isinstance(epoch, (int, float))
            else None
        )
        [normalized] = normalize_estimate_frame(
            [listing],
            {symbol: estimates},
            analysis_as_of=analysis_as_of,
            source_id=source_id,
            config=config,
        )
        record = dict(normalized)
        record["snapshot_classification"] = snapshot_store.classify_symbol(
            listing,
            normalized,
            requires_unit_reconciliation=requires_unit_reconciliation,
            minimum_plausible_forward_pe=float(config.get("minimum_plausible_forward_pe", 2.0)),
        )
        record["snapshot_shard"] = shard_index
        record["snapshot_retrieved_at"] = retrieved_at
        record["snapshot_normalization_as_of"] = analysis_as_of.astimezone(timezone.utc).isoformat()
        record["snapshot_served_from_cache"] = served_from_cache
        buffered.append(record)
        if len(buffered) >= 25:
            snapshot_store.append_shard_rows(snapshot_dir, shard_index, buffered)
            buffered = []
    if buffered:
        snapshot_store.append_shard_rows(snapshot_dir, shard_index, buffered)

    all_rows = snapshot_store.load_shard_rows(snapshot_dir, shard_index)
    classified: dict[str, int] = {}
    retrieved_stamps: list[str] = []
    retrieval_time_unknown = 0
    normalization_stamps: list[str] = []
    normalization_time_unknown = 0
    for row in all_rows:
        name = str(row.get("snapshot_classification") or "no_estimates")
        classified[name] = classified.get(name, 0) + 1
        stamp = row.get("snapshot_retrieved_at")
        if isinstance(stamp, str) and stamp:
            retrieved_stamps.append(stamp)
        else:
            retrieval_time_unknown += 1
        normalization_stamp = row.get("snapshot_normalization_as_of")
        if isinstance(normalization_stamp, str) and normalization_stamp:
            normalization_stamps.append(normalization_stamp)
        else:
            normalization_time_unknown += 1
    collected_this_run = len(all_rows) - len(existing)
    shard_complete = (
        len(all_rows) >= len(shard_listings) and not budget_exhausted and not fetch_failed_symbols
    )
    previous_entry = manifest.get("shards", {}).get(str(shard_index)) or {}
    previous_calls = int(previous_entry.get("calls_used") or 0)
    calls_delta = int(client.diagnostics().get("api_calls_made") or 0) - calls_before
    if collected_this_run > 0 or not previous_entry.get("as_of"):
        shard_as_of = analysis_as_of.astimezone(timezone.utc).isoformat()
    else:
        # A run that collected nothing must not refresh the shard's
        # freshness stamp — PR B's staleness gate reads it.
        shard_as_of = str(previous_entry.get("as_of"))
    manifest = snapshot_store.update_shard(
        snapshot_dir,
        manifest,
        shard_index,
        status="complete" if shard_complete else "partial",
        as_of=shard_as_of,
        calls_used=previous_calls + calls_delta,
        classified=classified,
        attempted=len(all_rows),
        expected=len(shard_listings),
        fetch_failed=len(fetch_failed_symbols),
        oldest_retrieved_at=min(retrieved_stamps) if retrieved_stamps else None,
        newest_retrieved_at=max(retrieved_stamps) if retrieved_stamps else None,
        retrieval_time_unknown=retrieval_time_unknown,
        oldest_normalization_as_of=min(normalization_stamps) if normalization_stamps else None,
        newest_normalization_as_of=max(normalization_stamps) if normalization_stamps else None,
        normalization_time_unknown=normalization_time_unknown,
    )
    if shard_complete:
        status_label = "shard_complete"
    elif budget_exhausted:
        status_label = "shard_partial_budget"
    elif fetch_failed_symbols:
        status_label = "shard_partial_fetch_failures"
    else:
        status_label = "shard_partial"
    summary = {
        "runtime": runtime_metadata(),
        "status": status_label,
        "stage": "collect-estimates",
        "snapshot_dir": str(snapshot_dir),
        "shard_index": shard_index,
        "shard_count": shard_count,
        "shard_symbol_count": len(shard_listings),
        "collected_this_run": collected_this_run,
        "shard_classified": dict(sorted(classified.items())),
        "budget_exhausted": budget_exhausted,
        "fetch_failed_count": len(fetch_failed_symbols),
        "fetch_failed_symbols": fetch_failed_symbols[:50],
        "retrieval_time_unknown": retrieval_time_unknown,
        "normalization_time_unknown": normalization_time_unknown,
        "snapshot": snapshot_store.snapshot_status(manifest),
        "provider_diagnostics": client.diagnostics(),
    }
    _write_json(snapshot_dir / f"shard-{shard_index}-summary.json", summary)
    return PipelineResult(summary=summary, exit_code=0 if shard_complete else 3)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path)
    parser.add_argument(
        "--output-dir", type=Path, default=Path("reports/us-undervalued-growth-screener")
    )
    parser.add_argument("--analysis-as-of", help="ISO-8601 timestamp; defaults to now")
    parser.add_argument("--api-key", help="Defaults to FMP_API_KEY")
    parser.add_argument("--cache-path", type=Path)
    parser.add_argument("--raw-store-dir", type=Path)
    parser.add_argument("--max-api-calls", type=int)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--skip-candidate-packets", action="store_true")
    parser.add_argument(
        "--stage",
        choices=("discover", "collect-estimates", "screen-full-snapshot"),
        default="discover",
        help=(
            "discover = the bounded pilot pipeline (default); collect-estimates = "
            "one deterministic shard of the full-universe estimate snapshot; "
            "screen-full-snapshot = current-only screen of a deeply verified snapshot"
        ),
    )
    parser.add_argument("--shard-index", type=int, help="collect-estimates: shard to collect")
    parser.add_argument("--shard-count", type=int, help="collect-estimates: total shards")
    parser.add_argument(
        "--snapshot-dir",
        type=Path,
        help=(
            "snapshot directory (collect default: <output-dir>/estimate-snapshot; "
            "required for screen-full-snapshot)"
        ),
    )
    parser.add_argument(
        "--resume", action="store_true", help="collect-estimates: continue a partial shard"
    )
    parser.add_argument("--version", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.version:
        print(json.dumps(runtime_metadata(), sort_keys=True))
        return 0
    try:
        config = load_config(args.config)
        analysis_as_of = (
            datetime.fromisoformat(args.analysis_as_of.replace("Z", "+00:00"))
            if args.analysis_as_of
            else datetime.now(timezone.utc)
        )
        if analysis_as_of.tzinfo is None:
            analysis_as_of = analysis_as_of.replace(tzinfo=timezone.utc)
        prepared_snapshot: dict[str, Any] | None = None
        collection_started_at: datetime | None = None
        if args.stage == "collect-estimates":
            if args.shard_index is None or args.shard_count is None:
                raise ValueError(
                    "--shard-index and --shard-count are required for --stage collect-estimates"
                )
            collection_started_at = validate_current_snapshot_collection(
                analysis_as_of=analysis_as_of,
                config=config,
            )
        if args.stage == "screen-full-snapshot":
            if args.snapshot_dir is None:
                raise ValueError("--snapshot-dir is required for --stage screen-full-snapshot")
            if args.resume or args.shard_index is not None or args.shard_count is not None:
                raise ValueError(
                    "--resume/--shard-index/--shard-count are collect-estimates options"
                )
            # Read-only and intentionally before FMPClient construction: a bad
            # snapshot must not create cache/raw/run artifacts.
            prepared_snapshot = prepare_screen_full_snapshot(
                args.snapshot_dir,
                analysis_as_of=analysis_as_of,
                config=config,
            )
        run_id = f"run-{analysis_as_of.astimezone(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
        output_dir = args.output_dir / run_id
        cache_cfg = dict(config.get("cache") or {})
        cache_path = args.cache_path or Path(
            str(cache_cfg.get("path", ".cache/us-garp/fmp-cache.sqlite3"))
        )
        raw_store_dir = args.raw_store_dir or output_dir / "provider-raw"
        max_calls = args.max_api_calls or int(config["max_api_calls"])
        with FMPClient(
            api_key=args.api_key,
            max_api_calls=max_calls,
            cache_path=cache_path,
            raw_store_dir=raw_store_dir,
            offline=args.offline,
        ) as client:
            if args.stage == "collect-estimates":
                result = execute_collect_estimates(
                    client,
                    config,
                    analysis_as_of=analysis_as_of,
                    snapshot_dir=args.snapshot_dir or (args.output_dir / "estimate-snapshot"),
                    shard_index=int(args.shard_index),
                    shard_count=int(args.shard_count),
                    resume=bool(args.resume),
                    collection_started_at=collection_started_at,
                )
            elif args.stage == "screen-full-snapshot":
                if prepared_snapshot is None:  # defensive; preflight above is mandatory
                    raise ValueError("screen-full-snapshot preflight was not completed")
                result = execute_screen_full_snapshot(
                    client,
                    config,
                    analysis_as_of=analysis_as_of,
                    output_dir=output_dir,
                    prepared_snapshot=prepared_snapshot,
                    include_packets=not args.skip_candidate_packets,
                )
            else:
                result = execute_pipeline(
                    client,
                    config,
                    analysis_as_of=analysis_as_of,
                    output_dir=output_dir,
                    include_packets=not args.skip_candidate_packets,
                )
        encoded = json.dumps(result.summary, ensure_ascii=False, sort_keys=True)
        max_bytes = int(config.get("compact_stdout_max_bytes", 20_000))
        if len(encoded.encode("utf-8")) > max_bytes:
            compact = dict(result.summary)
            compact.pop("selected_candidates", None)
            compact["stdout_compacted"] = True
            compact["selected_candidate_details_path"] = str(output_dir / "run-summary.json")
            encoded = json.dumps(compact, ensure_ascii=False, sort_keys=True)
        print(encoded)
        return result.exit_code
    except ApiCallBudgetExceeded as exc:
        print(
            json.dumps(
                {
                    "runtime": runtime_metadata(),
                    "status": "provider_budget_exhausted",
                    "error": str(exc),
                },
                sort_keys=True,
            )
        )
        return 2
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(
            json.dumps(
                {"runtime": runtime_metadata(), "status": "failed", "error": str(exc)},
                sort_keys=True,
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
