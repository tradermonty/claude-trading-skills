"""Listing universe, sector taxonomy, bulk estimates and seed selection for run_pipeline."""

from __future__ import annotations

import hashlib
import math
import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from fmp_client import FMPClient
from normalize_estimates import normalize_symbol
from pipeline_common import (
    CYCLICAL_RULES,
    EXCHANGES,
    _first_number,
    _number,
    _symbol,
    _text,
    is_common_stock,
)

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
