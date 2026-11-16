"""Full-universe estimate collection and full-snapshot screening stages for run_pipeline."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import estimate_snapshot as snapshot_store
from build_provider_prefilter_pool import ALLOWED_LANES, build_pool
from coverage_semantics import build_coverage_block, classify_ranking_scope
from fmp_client import ApiCallBudgetExceeded, FMPClient
from pipeline_common import (
    PipelineResult,
    _first_number,
    _invalidate_candidate_decisions,
    _invalidate_final_screen_audit,
    _OperationTrackingClient,
    _ordered_unique_symbols,
    _persist_partial_snapshot_diagnostic,
    _require_fresh_screen_output_dir,
    _symbol,
    _text,
    _write_json,
    _write_jsonl,
)
from pipeline_enrichment import (
    _is_foreign_private_issuer,
    apply_quality_probe,
    apply_symbol_liquidity,
    build_fmp_packet,
    compact_candidate,
    lane_memberships,
    mark_sector_profile_exhaustion,
    mark_unit_reconciliation_exhaustion,
    select_liquidity_targets,
)
from pipeline_universe import _coverage_count, collect_listing_universe, normalize_estimate_frame
from screen_universe import DEFAULTS as SCREEN_DEFAULTS
from screen_universe import _canonical_line, requires_unit_reconciliation, run_layered
from skill_version import runtime_metadata


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

    _require_fresh_screen_output_dir(output_dir)
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
    ordered_liquidity_targets = _ordered_unique_symbols(ordered_liquidity_targets)
    required_liquidity_days = int(config["minimum_average_volume_period_days"])
    enriched_rows = [dict(row) for row in evaluable_rows]
    liquidity_targets: list[str] = []
    liquidity_attempted: list[str] = []
    liquidity_completed: set[str] = set()
    valid_liquidity_symbols: set[str] = set()
    # Backfill past failed/empty histories. A short pool can claim exhaustion
    # only after every economically eligible symbol has an explicit outcome.
    for symbol in ordered_liquidity_targets:
        liquidity_attempted.append(symbol)
        try:
            enriched_rows = apply_symbol_liquidity(
                client,
                enriched_rows,
                as_of=analysis_as_of.date(),
                source_id=f"fmp-historical-eod-{analysis_as_of.date().isoformat()}",
                limit=1,
                required_days=required_liquidity_days,
                target_symbols=[symbol],
            )
        except ApiCallBudgetExceeded as exc:
            return _persist_partial_snapshot_diagnostic(
                output_dir=output_dir,
                audit_dir=audit_dir,
                snapshot_id=snapshot_id,
                verification_digest=verification_digest,
                stage="liquidity",
                progress={
                    "target_symbols": ordered_liquidity_targets,
                    "attempted_symbols": liquidity_attempted,
                    "completed_symbols": [
                        value for value in ordered_liquidity_targets if value in liquidity_completed
                    ],
                    "pending_symbols": [
                        value
                        for value in ordered_liquidity_targets
                        if value not in liquidity_completed
                    ],
                    "interrupted_symbols": [symbol],
                    "interrupted_at": {
                        "symbol": symbol,
                        "operation": "get_historical_prices",
                    },
                },
                error=str(exc),
                client=client,
                partial_rows=enriched_rows,
            )
        liquidity_completed.add(symbol)
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
        return_partial_on_budget=True,
    )
    if quality_probe_audit.get("budget_exhausted"):
        _write_json(audit_dir / "quality-probe-audit.json", quality_probe_audit)
        return _persist_partial_snapshot_diagnostic(
            output_dir=output_dir,
            audit_dir=audit_dir,
            snapshot_id=snapshot_id,
            verification_digest=verification_digest,
            stage="quality_probe",
            progress={
                "target_symbols": _ordered_unique_symbols(probe_symbols),
                "attempted_symbols": quality_probe_audit.get("attempted_symbols", []),
                "completed_symbols": quality_probe_audit.get("completed_symbols", []),
                "pending_symbols": quality_probe_audit.get("pending_symbols", []),
                "interrupted_symbols": quality_probe_audit.get("interrupted_symbols", []),
                "interrupted_at": quality_probe_audit.get("interrupted_at"),
            },
            error=str(quality_probe_audit.get("error") or "provider API call budget exhausted"),
            client=client,
            partial_rows=probed_rows,
            preserved_artifact_paths=[audit_dir / "quality-probe-audit.json"],
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
        packet_targets = _ordered_unique_symbols(selected)
        packet_attempted: list[str] = []
        packet_completed: set[str] = set()
        packet_client = _OperationTrackingClient(client)
        for symbol in packet_targets:
            packet_attempted.append(symbol)
            packet_client.last_operation = None
            try:
                packet_paths.append(
                    str(build_fmp_packet(packet_client, selected_rows[symbol], packet_dir))
                )
            except ApiCallBudgetExceeded as exc:
                invalidated_audit = _invalidate_final_screen_audit(audit)
                invalidated_audit["partial_run"] = {
                    "status": "provider_budget_exhausted",
                    "stage": "candidate_packets",
                    "commit_marker": "audit/partial-run-diagnostic.json",
                    "candidate_artifact_rewrite": "pending",
                }
                invalidated_candidates = _invalidate_candidate_decisions(candidate_decisions)
                # Publish the non-authoritative audit first. If the process
                # stops during the row rewrite, no audit can still authorize
                # the old selected rows.
                invalidated_audit["candidate_pool"]["artifact_sha256"] = None
                _write_json(audit_dir / "broad-screen-audit.json", invalidated_audit)
                candidate_sha = _write_jsonl(candidate_path, invalidated_candidates)
                invalidated_audit["candidate_pool"]["decision_counts"] = {
                    status: sum(
                        1
                        for row in invalidated_candidates
                        if str((row.get("decision") or {}).get("status") or "") == status
                    )
                    for status in sorted(
                        {
                            str((row.get("decision") or {}).get("status") or "")
                            for row in invalidated_candidates
                        }
                    )
                }
                invalidated_audit["candidate_pool"]["artifact_sha256"] = candidate_sha
                invalidated_audit["partial_run"]["candidate_artifact_rewrite"] = "complete"
                _write_json(audit_dir / "broad-screen-audit.json", invalidated_audit)
                return _persist_partial_snapshot_diagnostic(
                    output_dir=output_dir,
                    audit_dir=audit_dir,
                    snapshot_id=snapshot_id,
                    verification_digest=verification_digest,
                    stage="candidate_packets",
                    progress={
                        "target_symbols": packet_targets,
                        "attempted_symbols": packet_attempted,
                        "completed_symbols": [
                            value for value in packet_targets if value in packet_completed
                        ],
                        "pending_symbols": [
                            value for value in packet_targets if value not in packet_completed
                        ],
                        "interrupted_symbols": [symbol],
                        "interrupted_at": {
                            "symbol": symbol,
                            "operation": packet_client.last_operation or "build_fmp_packet",
                            "partial_packet_written": False,
                        },
                    },
                    error=str(exc),
                    client=client,
                    partial_rows=probed_rows,
                    preserved_artifact_paths=[
                        *(Path(path) for path in packet_paths),
                        audit_dir / "broad-screen-audit.json",
                    ],
                )
            packet_completed.add(symbol)

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
