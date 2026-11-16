"""The bounded discover stage (execute_pipeline) for run_pipeline."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from build_provider_prefilter_pool import ALLOWED_LANES, build_pool
from coverage_semantics import build_coverage_block, classify_ranking_scope
from fmp_client import FMPClient
from pipeline_common import PipelineResult, _symbol, _text, _write_json, _write_jsonl
from pipeline_enrichment import (
    _is_foreign_private_issuer,
    apply_bulk_liquidity,
    apply_quality_probe,
    apply_symbol_liquidity,
    build_fmp_packet,
    compact_candidate,
    lane_memberships,
    mark_sector_profile_exhaustion,
    mark_unit_reconciliation_exhaustion,
    select_liquidity_targets,
    select_quality_probe_targets,
)
from pipeline_universe import (
    _coverage_count,
    collect_bulk_annual_estimates,
    collect_listing_universe,
    compute_effective_seed_limit,
    diversified_seed,
    economic_scope_complete,
    enrich_listing_from_bulk,
    merge_bulk_rows,
    normalize_estimate_frame,
)
from screen_universe import DEFAULTS as SCREEN_DEFAULTS
from screen_universe import _canonical_line, run_layered
from skill_version import runtime_metadata


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
