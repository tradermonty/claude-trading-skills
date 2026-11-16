"""Exhaustion marks, quality probe, liquidity, lane membership and FMP packets for run_pipeline."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from build_provider_prefilter_pool import ALLOWED_LANES, _lane_score
from fmp_client import ApiCallBudgetExceeded, FMPClient
from normalize_estimates import apply_verified_actual_eps
from pipeline_common import (
    SEC_FILING_TZ,
    _first_number,
    _ordered_unique_symbols,
    _symbol,
    _text,
    _write_json,
)
from pipeline_universe import pre_enrichment_score
from screen_universe import SECTOR_PROFILES, requires_unit_reconciliation
from skill_version import runtime_metadata

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
    return_partial_on_budget: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Enrich the top-ranked lane candidates with TTM quality metrics.

    A failed/empty probe (4xx or no data) is recorded as
    ``quality_probe_resolved: False`` on that row rather than failing the run.
    Full-snapshot screening may opt into returning rows and progress when the
    provider call budget is exhausted; the bounded pipeline keeps the historic
    exception behavior by default. Counts use FMP provider-budget counter deltas
    (including consumed retries, excluding cache hits and unsent refusals). Clients
    without that counter fall back to completed logical calls.
    """
    ordered_targets = _ordered_unique_symbols(target_symbols)
    targets = set(ordered_targets)
    attempted: list[str] = []
    resolved: list[str] = []
    actual_resolved: list[str] = []
    actual_calls = 0
    metrics_calls = 0
    completed: set[str] = set()
    interrupted: list[str] = []
    budget_error: str | None = None
    interrupted_at: dict[str, str] | None = None
    output: list[dict[str, Any]] = []
    actual_required = analysis_as_of is not None and hasattr(client, "get_income_statement")
    for raw in rows:
        row = dict(raw)
        symbol = _symbol(row)
        if symbol in targets:
            if budget_error is not None:
                row.setdefault("quality_probe_attempted", False)
                row.setdefault("quality_probe_resolved", False)
                row.setdefault("quality_probe_complete", False)
                output.append(row)
                continue
            attempted.append(symbol)
            row["quality_probe_attempted"] = True
            row["quality_probe_complete"] = False
            calls_before = getattr(client, "api_calls_made", None)
            completed_call = False
            try:
                payload = client.get_key_metrics_ttm(symbol)
                completed_call = True
            except ApiCallBudgetExceeded as exc:
                if not return_partial_on_budget:
                    raise
                budget_error = str(exc)
                interrupted.append(symbol)
                interrupted_at = {"symbol": symbol, "operation": "get_key_metrics_ttm"}
                row["quality_probe_budget_exhausted"] = True
                row["quality_probe_resolved"] = False
                output.append(row)
                continue
            finally:
                metrics_calls += (
                    client.api_calls_made - calls_before
                    if calls_before is not None
                    else int(completed_call)
                )
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
            if actual_required:
                calls_before = getattr(client, "api_calls_made", None)
                completed_call = False
                try:
                    statements = client.get_income_statement(symbol, period="annual", limit=2)
                    completed_call = True
                except ApiCallBudgetExceeded as exc:
                    if not return_partial_on_budget:
                        raise
                    budget_error = str(exc)
                    interrupted.append(symbol)
                    interrupted_at = {"symbol": symbol, "operation": "get_income_statement"}
                    row["quality_probe_budget_exhausted"] = True
                    output.append(row)
                    continue
                finally:
                    actual_calls += (
                        client.api_calls_made - calls_before
                        if calls_before is not None
                        else int(completed_call)
                    )
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
            row["quality_probe_complete"] = True
            completed.add(symbol)
        else:
            row.setdefault("quality_probe_attempted", False)
            row.setdefault("quality_probe_resolved", False)
            row.setdefault("quality_probe_complete", False)
        output.append(row)
    attempted_symbols = [symbol for symbol in ordered_targets if symbol in set(attempted)]
    completed_symbols = [symbol for symbol in ordered_targets if symbol in completed]
    pending_symbols = [symbol for symbol in ordered_targets if symbol not in completed]
    interrupted_symbols = [symbol for symbol in ordered_targets if symbol in set(interrupted)]
    audit = {
        "attempted": attempted_symbols,
        "resolved": resolved,
        "symbols": attempted_symbols,
        "source_id": source_id,
        "calls_used": metrics_calls + actual_calls,
        "actual_eps_source_id": actual_source_id,
        "actual_eps_calls": actual_calls,
        "actual_eps_resolved": actual_resolved,
        "budget_exhausted": budget_error is not None,
        "attempted_symbols": attempted_symbols,
        "completed_symbols": completed_symbols,
        "pending_symbols": pending_symbols,
        "interrupted_symbols": interrupted_symbols,
        "interrupted_at": interrupted_at,
        "error": budget_error,
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
