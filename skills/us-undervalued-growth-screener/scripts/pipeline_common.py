"""Shared constants, result types, artifact I/O and config helpers for run_pipeline."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

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


def _ordered_unique_symbols(values: Sequence[Any]) -> list[str]:
    """Return canonical, duplicate-free symbols while preserving input order."""
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value is None:
            continue
        symbol = str(value).strip().upper()
        if symbol and symbol not in seen:
            seen.add(symbol)
            output.append(symbol)
    return output


class _OperationTrackingClient:
    """Proxy provider calls so an interrupted packet identifies its operation."""

    def __init__(self, client: Any) -> None:
        self._client = client
        self.last_operation: str | None = None

    def __getattr__(self, name: str) -> Any:
        value = getattr(self._client, name)
        if not callable(value):
            return value

        def tracked(*args: Any, **kwargs: Any) -> Any:
            self.last_operation = name
            return value(*args, **kwargs)

        return tracked


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


def _artifact_record(path: Path, *, root: Path, row_count: int | None = None) -> dict[str, Any]:
    """Describe an existing artifact for the partial-run commit marker."""
    relative = str(path.relative_to(root))
    record: dict[str, Any] = {
        "path": relative,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "bytes": path.stat().st_size,
    }
    if row_count is not None:
        record["row_count"] = row_count
    return record


def _persist_partial_snapshot_diagnostic(
    *,
    output_dir: Path,
    audit_dir: Path,
    snapshot_id: str,
    verification_digest: str,
    stage: str,
    progress: Mapping[str, Any],
    error: str,
    client: Any,
    partial_rows: Sequence[Mapping[str, Any]],
    preserved_artifact_paths: Sequence[Path] = (),
) -> PipelineResult:
    """Persist a fail-closed partial screen result before returning exit 2.

    The diagnostic is deliberately written last.  It is the commit marker for
    the per-file atomic writes that precede it; consumers must verify the
    marker's hashes before reading any partial artifact.
    """
    partial_path = audit_dir / "enriched-estimates.partial.jsonl"
    partial_sha = _write_jsonl(partial_path, partial_rows)
    partial_record = _artifact_record(
        partial_path,
        root=output_dir,
        row_count=len(partial_rows),
    )
    preserved_records = [
        _artifact_record(path, root=output_dir)
        for path in preserved_artifact_paths
        if path.is_file()
    ]
    # Keep the explicit local variable as a guard against accidentally writing
    # a diagnostic whose hash does not describe the bytes just committed.
    if partial_record["sha256"] != partial_sha:
        raise OSError("partial enrichment artifact hash changed during write")

    common: dict[str, Any] = {
        "schema_version": 1,
        "runtime": runtime_metadata(),
        "run_id": output_dir.name,
        "status": "provider_budget_exhausted",
        "stage": stage,
        "snapshot_id": snapshot_id,
        "snapshot_verification_digest": verification_digest,
        "progress": dict(progress),
        "error": error,
        "provider_diagnostics": client.diagnostics(),
        "no_final_marketwide_conclusion": True,
        "recovery": {
            "resume_supported": False,
            "action": "rerun_screen_full_snapshot_after_provider_budget_reset",
            "same_verified_snapshot_required": True,
            "partial_artifact_is_not_a_final_conclusion": True,
        },
        "partial_diagnostic_path": "audit/partial-run-diagnostic.json",
    }
    summary = {
        **common,
        "artifacts": {
            "partial_enriched_estimates": partial_record,
            "preserved": preserved_records,
            "partial_diagnostic": {"path": "audit/partial-run-diagnostic.json"},
        },
    }
    next_action = {
        **common,
        "action": "rerun_screen_full_snapshot_after_provider_budget_reset",
        "partial_artifacts_are_authoritative_only_after_marker_verification": True,
        "artifacts": {
            "partial_diagnostic": "audit/partial-run-diagnostic.json",
            "partial_enriched_estimates": "audit/enriched-estimates.partial.jsonl",
        },
    }
    run_summary_path = output_dir / "run-summary.json"
    next_action_path = output_dir / "NEXT_ACTION.json"
    _write_json(run_summary_path, summary)
    _write_json(next_action_path, next_action)

    diagnostic = {
        **common,
        "commit_marker": "audit/partial-run-diagnostic.json",
        "artifacts": {
            "partial_enriched_estimates": partial_record,
            "run_summary": _artifact_record(run_summary_path, root=output_dir),
            "next_action": _artifact_record(next_action_path, root=output_dir),
            "preserved": preserved_records,
        },
    }
    # This must remain the final write in this helper.  A missing or invalid
    # marker makes the preceding partial summary non-authoritative.
    _write_json(audit_dir / "partial-run-diagnostic.json", diagnostic)
    return PipelineResult(summary=summary, exit_code=2)


def _invalidate_final_screen_audit(audit: Mapping[str, Any]) -> dict[str, Any]:
    """Make a pre-packet screen audit explicitly non-authoritative."""
    invalidated = dict(audit)
    invalidated.update(
        {
            "status": "incomplete",
            "conclusion_scope": "diagnostic",
            "ranking_scope": "diagnostic",
            "candidate_pool_status": "incomplete_budget_exhausted",
            "selection_outcome": "incomplete_budget_exhausted",
            "selected_symbols": [],
        }
    )
    plan = dict(invalidated.get("deep_dive_plan") or {})
    plan.update(
        {
            "status": "incomplete",
            "selected_symbols": [],
            "selected_count": 0,
            "selected_set_sha256": None,
            "commitment_payload": None,
            "selected_set_is_committed": False,
            "budget_locked": False,
            "lane_counts": {},
            "selection_method": "not_committed_due_to_provider_budget",
        }
    )
    invalidated["deep_dive_plan"] = plan
    candidate_pool = dict(invalidated.get("candidate_pool") or {})
    generation_audit = dict(candidate_pool.get("generation_audit") or {})
    generation_audit.update(
        {
            "valid": False,
            "selection_method": "not_committed_due_to_provider_budget",
            "selected_count": 0,
            "selected_symbols": [],
            "actual_selected_count": 0,
            "actual_selected_symbols": [],
            "selected_set_sha256": None,
            "commitment_payload": None,
            "selection_commitment": None,
            "lane_selected_counts": {},
            "lane_coverage_count": 0,
        }
    )
    candidate_pool.update(
        {
            "status": "incomplete",
            "selected_count": 0,
            "selection_eligible_count": 0,
            "selection_commitment": None,
            "generation_audit": generation_audit,
        }
    )
    invalidated["candidate_pool"] = candidate_pool
    return invalidated


def _invalidate_candidate_decisions(
    decisions: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Remove all active selection authority while retaining the original audit."""
    invalidated: list[dict[str, Any]] = []
    for raw in decisions:
        row = deepcopy(dict(raw))
        decision = dict(row.get("decision") or {})
        row.setdefault("prior_decision", deepcopy(decision))
        row.setdefault(
            "prior_selection",
            {
                key: deepcopy(row[key])
                for key in ("selection_eligible", "selection_lane")
                if key in row
            },
        )
        decision["status"] = "deferred_by_budget"
        decision["selection_eligible"] = False
        for key in ("preselection_status", "selection_lane", "selection_reason"):
            decision.pop(key, None)
        row["decision"] = decision
        row["selection_eligible"] = False
        row.pop("selection_lane", None)
        invalidated.append(row)
    return invalidated


def _require_fresh_screen_output_dir(output_dir: Path) -> None:
    """Prevent a retry from mixing partial artifacts with a prior run."""
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError(
            f"screen-full-snapshot output directory must be new and empty: {output_dir}"
        )


def _path_is_within(path: Path, parent: Path) -> bool:
    """Return whether ``path`` resolves below ``parent``."""
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


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
