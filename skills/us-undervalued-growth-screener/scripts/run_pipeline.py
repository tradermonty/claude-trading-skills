#!/usr/bin/env python3
"""Claude Code-native direct-FMP discovery pipeline for the US GARP skill.

Bulk provider payloads stay on disk.  The program prints one compact JSON summary
and emits auditable JSON/JSONL artifacts consumed by the existing contract-3.5
underwriting and evaluation workflow.
"""

# This file is the stable CLI entry point and import surface (Issue #502). The
# implementation lives in the pipeline_*.py stage modules next to this file,
# each importing only from the stages listed before it:
#   pipeline_common      constants, result types, I/O and artifact helpers, config
#   pipeline_universe    listing universe, taxonomy, bulk estimates, seeding
#   pipeline_enrichment  exhaustion marks, quality probe, liquidity, lanes, packets
#   pipeline_discover    execute_pipeline (the bounded discover stage)
#   pipeline_snapshot    full-universe collect-estimates and screen-full-snapshot
# Every name the monolithic module defined is re-exported here. A stage function
# reads globals from its own module, so a monkeypatch on this module does not
# reach callers inside the stages; patch the defining stage module instead.

from __future__ import annotations

import argparse
import hashlib  # noqa: F401
import json
import math  # noqa: F401
import os  # noqa: F401
import re  # noqa: F401
import uuid
from collections import defaultdict  # noqa: F401
from collections.abc import Mapping, Sequence  # noqa: F401
from copy import deepcopy  # noqa: F401
from dataclasses import dataclass  # noqa: F401
from datetime import date, datetime, timedelta, timezone  # noqa: F401
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo  # noqa: F401

import estimate_snapshot as snapshot_store  # noqa: F401
from build_provider_prefilter_pool import ALLOWED_LANES, _lane_score, build_pool  # noqa: F401
from coverage_semantics import build_coverage_block, classify_ranking_scope  # noqa: F401
from fmp_client import ApiCallBudgetExceeded, FMPClient
from normalize_estimates import apply_verified_actual_eps, normalize_symbol  # noqa: F401
from pipeline_common import (
    CYCLICAL_RULES,
    DEFAULT_CONFIG,
    EXCHANGES,
    NON_COMMON_NAME,
    NON_COMMON_SYMBOL,
    SEC_FILING_TZ,
    PipelineResult,
    _artifact_record,
    _canonical_jsonl,
    _first_number,
    _invalidate_candidate_decisions,
    _invalidate_final_screen_audit,
    _number,
    _OperationTrackingClient,
    _ordered_unique_symbols,
    _path_is_within,
    _persist_partial_snapshot_diagnostic,
    _require_fresh_screen_output_dir,
    _symbol,
    _text,
    _write_json,
    _write_jsonl,
    is_common_stock,
    load_config,
)
from pipeline_discover import (
    execute_pipeline,
)
from pipeline_enrichment import (
    _BLOCKED_SECTOR_PROFILES,
    _SECTOR_METRIC_FIELDS,
    _best_lane_score,
    _cash_flow_ttm_preview,
    _is_foreign_private_issuer,
    _project_rows,
    _verified_annual_actual,
    apply_bulk_liquidity,
    apply_quality_probe,
    apply_symbol_liquidity,
    build_fmp_packet,
    compact_candidate,
    lane_memberships,
    mark_sector_profile_exhaustion,
    mark_unit_reconciliation_exhaustion,
    prior_business_days,
    select_liquidity_targets,
    select_quality_probe_targets,
)
from pipeline_snapshot import (
    _attach_snapshot_attempts,
    _snapshot_lane_rows,
    execute_collect_estimates,
    execute_screen_full_snapshot,
    prepare_screen_full_snapshot,
    validate_current_snapshot_collection,
)
from pipeline_universe import (
    _BDC_NAME_NEEDLES,
    _ECONOMIC_SEED_FIELDS,
    _INDUSTRY_PREFIX_RULES,
    _MLP_NEEDLES,
    INDUSTRY_PROFILE_MAP,
    _apportion_quota,
    _cell_key,
    _coverage_count,
    _metric_from_bulk,
    _normalize_taxonomy_text,
    _stable_tie_break,
    classify_cyclicality,
    collect_bulk_annual_estimates,
    collect_listing_universe,
    compute_effective_seed_limit,
    diversified_seed,
    economic_scope_complete,
    enrich_listing_from_bulk,
    infer_sector_profile_type,
    market_cap_bucket,
    merge_bulk_rows,
    normalize_estimate_frame,
    normalize_listing,
    pre_enrichment_score,
)
from screen_universe import DEFAULTS as SCREEN_DEFAULTS  # noqa: F401
from screen_universe import (  # noqa: F401
    SECTOR_PROFILES,
    _canonical_line,
    requires_unit_reconciliation,
    run_layered,
)
from skill_version import runtime_metadata

__all__ = [
    "SEC_FILING_TZ",
    "DEFAULT_CONFIG",
    "EXCHANGES",
    "NON_COMMON_NAME",
    "NON_COMMON_SYMBOL",
    "CYCLICAL_RULES",
    "PipelineResult",
    "_ordered_unique_symbols",
    "_OperationTrackingClient",
    "_number",
    "_first_number",
    "_text",
    "_symbol",
    "_canonical_jsonl",
    "_write_json",
    "_write_jsonl",
    "_artifact_record",
    "_persist_partial_snapshot_diagnostic",
    "_invalidate_final_screen_audit",
    "_invalidate_candidate_decisions",
    "_require_fresh_screen_output_dir",
    "_path_is_within",
    "load_config",
    "is_common_stock",
    "INDUSTRY_PROFILE_MAP",
    "_INDUSTRY_PREFIX_RULES",
    "_BDC_NAME_NEEDLES",
    "_MLP_NEEDLES",
    "_normalize_taxonomy_text",
    "infer_sector_profile_type",
    "normalize_listing",
    "_coverage_count",
    "collect_listing_universe",
    "market_cap_bucket",
    "classify_cyclicality",
    "merge_bulk_rows",
    "collect_bulk_annual_estimates",
    "normalize_estimate_frame",
    "_metric_from_bulk",
    "enrich_listing_from_bulk",
    "pre_enrichment_score",
    "_cell_key",
    "_stable_tie_break",
    "_apportion_quota",
    "_ECONOMIC_SEED_FIELDS",
    "diversified_seed",
    "compute_effective_seed_limit",
    "economic_scope_complete",
    "_SECTOR_METRIC_FIELDS",
    "_BLOCKED_SECTOR_PROFILES",
    "mark_sector_profile_exhaustion",
    "mark_unit_reconciliation_exhaustion",
    "_is_foreign_private_issuer",
    "_verified_annual_actual",
    "apply_quality_probe",
    "_best_lane_score",
    "select_quality_probe_targets",
    "prior_business_days",
    "apply_bulk_liquidity",
    "apply_symbol_liquidity",
    "select_liquidity_targets",
    "lane_memberships",
    "compact_candidate",
    "_project_rows",
    "_cash_flow_ttm_preview",
    "build_fmp_packet",
    "execute_pipeline",
    "prepare_screen_full_snapshot",
    "validate_current_snapshot_collection",
    "_snapshot_lane_rows",
    "_attach_snapshot_attempts",
    "execute_screen_full_snapshot",
    "execute_collect_estimates",
    "parse_args",
    "main",
]


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
        run_id = (
            f"run-{analysis_as_of.astimezone(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
            f"-attempt-{uuid.uuid4().hex[:12]}"
        )
        output_dir = args.output_dir / run_id
        if args.stage == "screen-full-snapshot":
            _require_fresh_screen_output_dir(output_dir)
        cache_cfg = dict(config.get("cache") or {})
        cache_path = args.cache_path or Path(
            str(cache_cfg.get("path", ".cache/us-garp/fmp-cache.sqlite3"))
        )
        if args.raw_store_dir is not None:
            raw_store_dir = args.raw_store_dir
        elif args.stage == "screen-full-snapshot":
            raw_store_dir = args.output_dir / ".provider-raw" / run_id
        else:
            raw_store_dir = output_dir / "provider-raw"
        if args.stage == "screen-full-snapshot" and _path_is_within(raw_store_dir, output_dir):
            raise ValueError("screen-full-snapshot raw store must be outside the new run directory")
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
