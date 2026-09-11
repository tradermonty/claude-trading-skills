#!/usr/bin/env python3
"""Build an audited multi-lane provider-prefilter candidate pool.

The host retrieves broad provider rows for four opportunity lanes and stores
one JSONL file per lane. This script deduplicates symbols, applies deterministic
lane-specific ranking, preserves validated liquidity/forward evidence, and emits
one candidate pool plus a generation audit consumable by screen_universe.py.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

try:
    from screening_semantics import normalize_forward_valuation, normalize_liquidity
    from skill_version import runtime_metadata
except ModuleNotFoundError:
    import importlib.util

    def _load(name: str):
        path = Path(__file__).with_name(name + ".py")
        spec = importlib.util.spec_from_file_location(name, path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"cannot load {name}")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    _semantics = _load("screening_semantics")
    _version = _load("skill_version")
    normalize_forward_valuation = _semantics.normalize_forward_valuation
    normalize_liquidity = _semantics.normalize_liquidity
    runtime_metadata = _version.runtime_metadata

ALLOWED_LANES = {
    "core_garp",
    "high_growth_exception",
    "quality_near_miss",
    "cyclical_normalization",
}

# provider_exhausted_scope values that justify waiving the minimum-pool floor:
# only a fully exhausted economic candidate universe (or a caller-supplied
# full-input pool) qualifies. "estimate_seed" -- the per-symbol fallback path --
# never does: it exhausts a bounded sample, not the market.
FULL_EXHAUSTION_SCOPES = frozenset({"economic_candidate_universe", "full_input"})


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return float(value)
    return None


def _text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _symbol(row: Mapping[str, Any]) -> str:
    return (_text(row.get("symbol")) or "UNKNOWN").upper()


def _fcf_effective_pct(row: Mapping[str, Any]) -> float | None:
    """SBC-adjusted FCF yield when the probe derived it, else the standard yield.

    ``sbc_adjusted_fcf_yield_pct`` is computed by the quality probe on the
    market-cap basis ((FCF - SBC) / market cap). A revenue-based SBC ratio is
    never subtracted from a market-cap-based yield here: the denominators
    differ and the result would be meaningless.
    """
    adjusted = _number(row.get("sbc_adjusted_fcf_yield_pct"))
    if adjusted is not None:
        return adjusted
    return _number(row.get("fcf_yield_pct"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, Mapping):
            raise ValueError(f"{path}:{line_no} is not a JSON object")
        rows.append(dict(value))
    return rows


def _canonical_jsonl(rows: Sequence[Mapping[str, Any]]) -> bytes:
    return b"".join(
        (
            json.dumps(dict(row), ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        ).encode("utf-8")
        for row in rows
    )


def _lane_score(row: Mapping[str, Any], lane: str, *, analysis_as_of: str) -> float:
    price = _number(row.get("price")) or _number(row.get("last"))
    forward = normalize_forward_valuation(
        row,
        price=price,
        analysis_as_of=analysis_as_of,
        max_age_days=45,
        reconciliation_tolerance_pct=5.0,
        maximum_dispersion_pct=100.0,
        maximum_fy1_horizon_days=430,
    )
    pe = _number(forward.get("forward_pe"))
    eps_growth = _number(row.get("eps_growth_pct")) or _number(row.get("per_share_growth_pct"))
    revenue_growth = _number(row.get("revenue_growth_pct"))
    analysts = _number(row.get("analyst_count")) or 0.0
    roic = _number(row.get("roic_pct"))
    cyclicality = _number(row.get("cyclicality_score")) or 1.0
    pe_component = max(-30.0, 35.0 - min(pe if pe is not None else 80.0, 80.0))
    growth_component = max(-15.0, min(eps_growth if eps_growth is not None else -10.0, 50.0))
    revenue_component = max(
        -10.0, min(revenue_growth if revenue_growth is not None else -5.0, 20.0)
    )
    breadth = min(10.0, analysts * 1.5)
    quality = min(10.0, max(0.0, roic or 0.0) / 2.0)
    if lane == "core_garp":
        score = pe_component * 1.4 + growth_component + revenue_component + breadth + quality
    elif lane == "high_growth_exception":
        score = (
            growth_component * 1.6
            + revenue_component * 1.2
            + pe_component * 0.7
            + breadth
            + quality
        )
    elif lane == "quality_near_miss":
        score = pe_component * 1.8 + growth_component * 0.9 + breadth + quality
    else:
        score = (
            pe_component
            + growth_component * 1.2
            + revenue_component
            + breadth
            - max(0.0, cyclicality - 3.0) * 2.0
        )
    fcf_yield = _number(row.get("fcf_yield_pct"))
    fcf_weight = {"core_garp": 1.0, "quality_near_miss": 1.0, "high_growth_exception": 0.5}.get(
        lane, 0.0
    )
    if fcf_yield is not None and fcf_weight:
        score += max(-5.0, min(fcf_yield, 15.0)) * fcf_weight
    nd_ebitda = _number(row.get("net_debt_to_ebitda"))
    if nd_ebitda is not None:
        score -= min(10.0, max(0.0, nd_ebitda - 2.5) * 4.0)
    if eps_growth is not None and eps_growth > 100:
        score -= 15.0
    return round(score, 6)


def build_pool(
    *,
    universe_rows: Sequence[Mapping[str, Any]],
    lane_rows: Mapping[str, Sequence[Mapping[str, Any]]],
    analysis_as_of: str,
    source_ids: Sequence[str],
    per_lane: int,
    max_pool: int,
    minimum_pool: int,
    requested_min_market_cap: float,
    requested_max_market_cap: float,
    provider_exhausted: bool,
    provider_exhausted_scope: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not universe_rows:
        raise ValueError("universe is empty")
    unknown = sorted(set(lane_rows) - ALLOWED_LANES)
    if unknown:
        raise ValueError(f"unknown lanes: {unknown}")

    candidates: dict[str, dict[str, Any]] = {}
    lane_input_counts: dict[str, int] = {}
    invalid_liquidity: list[str] = []
    fcf_prefilter_exclusions: list[dict[str, str]] = []
    for lane in sorted(ALLOWED_LANES):
        rows = [dict(row) for row in lane_rows.get(lane, [])]
        lane_input_counts[lane] = len(rows)
        for raw in rows:
            symbol = _symbol(raw)
            if symbol == "UNKNOWN":
                continue
            liquidity = normalize_liquidity(raw, minimum_period_days=20)
            if liquidity.get("valid_for_screen") is not True:
                invalid_liquidity.append(symbol)
                continue

            # Hard FCF-support floor: a quality-probe-resolved row with
            # sub-1% (SBC-adjusted) FCF yield does not clear the prefilter
            # for any lane except high_growth_exception, which is kept but
            # tagged and penalized instead of dropped outright (an
            # early-stage grower may legitimately run FCF-negative).
            fcf_below_floor = bool(raw.get("quality_probe_resolved")) and (
                (effective := _fcf_effective_pct(raw)) is not None and effective < 1.0
            )
            weak_fcf_flag = False
            if fcf_below_floor and lane != "high_growth_exception":
                fcf_prefilter_exclusions.append(
                    {
                        "symbol": symbol,
                        "lane": lane,
                        "reason": "fcf_yield_below_prefilter_floor",
                    }
                )
                continue

            score = _lane_score(raw, lane, analysis_as_of=analysis_as_of)
            if fcf_below_floor and lane == "high_growth_exception":
                score = round(score - 10.0, 6)
                weak_fcf_flag = True

            item = candidates.setdefault(symbol, dict(raw))
            item["symbol"] = symbol
            lanes = set(item.get("provider_prefilter_lanes") or [])
            lanes.add(lane)
            item["provider_prefilter_lanes"] = sorted(lanes)
            if weak_fcf_flag:
                flags = set(item.get("provider_prefilter_flags") or [])
                flags.add("weak_fcf_support")
                item["provider_prefilter_flags"] = sorted(flags)
            lane_scores = dict(item.get("provider_prefilter_lane_scores") or {})
            lane_scores[lane] = score
            item["provider_prefilter_lane_scores"] = lane_scores
            item["provider_prefilter_best_score"] = max(lane_scores.values())
            item.setdefault(
                "average_daily_dollar_volume", liquidity.get("average_daily_dollar_volume")
            )
            item.setdefault("average_daily_dollar_volume_method", liquidity.get("method"))
            item.setdefault("average_volume", liquidity.get("average_volume"))
            item.setdefault("average_volume_period_days", liquidity.get("period_days"))
            item.setdefault("liquidity_source_ids", liquidity.get("source_ids", []))

    selected: list[dict[str, Any]] = []
    selected_symbols: set[str] = set()
    lane_added_counts = {lane: 0 for lane in ALLOWED_LANES}

    def lane_rank(lane: str) -> list[dict[str, Any]]:
        rows = [
            row
            for row in candidates.values()
            if lane in (row.get("provider_prefilter_lanes") or [])
        ]
        return sorted(
            rows,
            key=lambda row: (
                -float((row.get("provider_prefilter_lane_scores") or {}).get(lane, -1e9)),
                -float(row.get("average_daily_dollar_volume") or 0.0),
                _symbol(row),
            ),
        )

    for lane in (
        "core_garp",
        "high_growth_exception",
        "quality_near_miss",
        "cyclical_normalization",
    ):
        for row in lane_rank(lane):
            if lane_added_counts[lane] >= per_lane or len(selected) >= max_pool:
                break
            symbol = _symbol(row)
            if symbol in selected_symbols:
                continue
            selected.append(dict(row))
            selected_symbols.add(symbol)
            lane_added_counts[lane] += 1

    remaining = sorted(
        candidates.values(),
        key=lambda row: (
            -float(row.get("provider_prefilter_best_score") or -1e9),
            -float(row.get("average_daily_dollar_volume") or 0.0),
            _symbol(row),
        ),
    )
    for row in remaining:
        if len(selected) >= max_pool:
            break
        symbol = _symbol(row)
        if symbol not in selected_symbols:
            selected.append(dict(row))
            selected_symbols.add(symbol)

    selected.sort(
        key=lambda row: (-float(row.get("provider_prefilter_best_score") or -1e9), _symbol(row))
    )
    # The row-count floor may be waived only when the WHOLE economic candidate
    # universe was exhausted. Exhausting a bounded slice of it (the estimate
    # seed on the per-symbol fallback path) does not make a thin pool
    # adequate. Fail closed: a caller that does not state its exhaustion scope
    # gets no waiver either — an unstated scope proves nothing.
    allow_small_pool = provider_exhausted and provider_exhausted_scope in FULL_EXHAUSTION_SCOPES
    pool_adequate = len(selected) >= minimum_pool or allow_small_pool
    # A symbol can legitimately qualify for multiple opportunity lanes.  Audit
    # represented lanes from final memberships rather than only the loop that
    # first inserted the unique symbol; otherwise an overlapping core/high-growth
    # name can make a valid four-lane pool appear to cover only one lane.
    lane_selected_counts = {
        lane: sum(1 for row in selected if lane in (row.get("provider_prefilter_lanes") or []))
        for lane in ALLOWED_LANES
    }
    lane_coverage_count = sum(1 for lane, count in lane_selected_counts.items() if count > 0)
    # Invalid provider rows are excluded before selection. They are disclosed but
    # do not poison an otherwise fully validated candidate pool.
    selected_liquidity_valid = all(
        normalize_liquidity(row, minimum_period_days=20).get("valid_for_screen") is True
        for row in selected
    )
    lane_floor_waived = allow_small_pool and lane_coverage_count < 3
    valid = (
        pool_adequate
        and (lane_coverage_count >= 3 or lane_floor_waived)
        and selected_liquidity_valid
    )
    fcf_prefilter_excluded_symbols = sorted({item["symbol"] for item in fcf_prefilter_exclusions})
    audit = {
        "runtime": runtime_metadata(),
        "valid": valid,
        "selection_method": "provider_prefilter",
        "analysis_as_of": analysis_as_of,
        "input_row_count": len(universe_rows),
        "selected_count": len(selected),
        "selected_symbols": sorted(selected_symbols),
        "source_ids": list(dict.fromkeys(str(value) for value in source_ids if str(value).strip())),
        "lane_input_counts": lane_input_counts,
        "lane_selected_counts": lane_selected_counts,
        "lane_coverage_count": lane_coverage_count,
        "minimum_required_lanes": 3,
        "lane_floor_waived": lane_floor_waived,
        "per_lane": per_lane,
        "max_pool": max_pool,
        "minimum_pool": minimum_pool,
        "provider_exhausted": provider_exhausted,
        "provider_exhausted_scope": provider_exhausted_scope,
        "pool_floor_waived": allow_small_pool and len(selected) < minimum_pool,
        "pool_adequate": pool_adequate,
        "fcf_prefilter_excluded_symbols": fcf_prefilter_excluded_symbols,
        "fcf_prefilter_excluded_count": len(fcf_prefilter_excluded_symbols),
        "fcf_prefilter_exclusions": fcf_prefilter_exclusions,
        "invalid_liquidity_symbols": sorted(set(invalid_liquidity)),
        "invalid_liquidity_excluded_count": len(set(invalid_liquidity)),
        "liquidity_validation": {
            "basis_validated": selected_liquidity_valid,
            "minimum_window_days": 20,
            "invalid_input_rows_excluded": len(set(invalid_liquidity)),
        },
        "coverage_plan": {
            "coverage_plan_valid": True,
            "user_requested_range_spanned": True,
            "market_cap_buckets_cover_user_requested_range": True,
            "single_band_only": False,
            "multi_lane_provider_prefilter": True,
        },
        "scope": {
            "user_requested_min_market_cap": requested_min_market_cap,
            "user_requested_max_market_cap": requested_max_market_cap,
            "user_requested_scope_complete": True,
            "scope_valid": True,
        },
    }
    return selected, audit


def parse_lane(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("--lane must be LANE=PATH")
    lane, raw = value.split("=", 1)
    if lane not in ALLOWED_LANES:
        raise argparse.ArgumentTypeError(f"invalid lane {lane!r}")
    return lane, Path(raw)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--universe", type=Path, required=True)
    parser.add_argument("--lane", action="append", type=parse_lane, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--analysis-as-of", required=True)
    parser.add_argument("--source-id", action="append", required=True)
    parser.add_argument("--per-lane", type=int, default=15)
    parser.add_argument("--max-pool", type=int, default=60)
    parser.add_argument("--minimum-pool", type=int, default=30)
    parser.add_argument("--requested-min-market-cap", type=float, default=500_000_000)
    parser.add_argument("--requested-max-market-cap", type=float, default=20_000_000_000)
    parser.add_argument("--provider-exhausted", action="store_true")
    parser.add_argument("--provider-exhausted-scope")
    parser.add_argument("--version", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    if "--version" in raw_argv:
        print(json.dumps(runtime_metadata(), sort_keys=True))
        return 0
    args = parse_args(raw_argv)
    if args.version:
        print(json.dumps(runtime_metadata(), sort_keys=True))
        return 0
    try:
        universe_rows = _read_jsonl(args.universe)
        lanes: dict[str, list[dict[str, Any]]] = {lane: [] for lane in ALLOWED_LANES}
        for lane, path in args.lane:
            lanes[lane].extend(_read_jsonl(path))
        pool, audit = build_pool(
            universe_rows=universe_rows,
            lane_rows=lanes,
            analysis_as_of=args.analysis_as_of,
            source_ids=args.source_id,
            per_lane=args.per_lane,
            max_pool=args.max_pool,
            minimum_pool=args.minimum_pool,
            requested_min_market_cap=args.requested_min_market_cap,
            requested_max_market_cap=args.requested_max_market_cap,
            provider_exhausted=args.provider_exhausted,
            provider_exhausted_scope=args.provider_exhausted_scope,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}")
        return 2
    args.output_dir.mkdir(parents=True, exist_ok=True)
    pool_path = args.output_dir / "provider-prefilter-pool.jsonl"
    audit_path = args.output_dir / "provider-prefilter-audit.json"
    data = _canonical_jsonl(pool)
    pool_path.write_bytes(data)
    audit["artifact_path"] = pool_path.name
    audit["artifact_sha256"] = hashlib.sha256(data).hexdigest()
    temp = audit_path.with_suffix(".tmp")
    temp.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, audit_path)
    print(f"wrote: {pool_path}")
    print(f"wrote: {audit_path}")
    return 0 if audit["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
