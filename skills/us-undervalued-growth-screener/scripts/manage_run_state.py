#!/usr/bin/env python3
"""Atomic checkpoint/resume manager for schema-3 / contract-3.5 GARP screening runs.

The manager keeps the tiered listing/candidate-pool audit, selected-symbol set,
verified candidate checkpoints, and unprocessed list mathematically
consistent. It performs no network access.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
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


RUN_STATE_SCHEMA_VERSION = 2
SNAPSHOT_SCHEMA_VERSION = 3
AUDIT_SCHEMA_VERSION = 3
SYMBOL_RE = re.compile(r"^[A-Za-z0-9.\-^]{1,20}$")


class RunStateError(ValueError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _text(value: Any) -> str | None:
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return None


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise RunStateError(f"cannot read {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise RunStateError(f"invalid JSON in {path}: {exc}") from exc


def _atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, path)


def _append_event(run_dir: Path, event: Mapping[str, Any]) -> None:
    path = run_dir / "events.ndjson"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(dict(event), ensure_ascii=False) + "\n")


def _state_path(run_dir: Path) -> Path:
    return run_dir / "run_state.json"


def _load_state(run_dir: Path) -> dict[str, Any]:
    path = _state_path(run_dir)
    if not path.is_file():
        raise RunStateError(f"run state not found: {path}")
    state = _read_json(path)
    if not isinstance(state, Mapping):
        raise RunStateError("run_state.json must be an object")
    state = dict(state)
    if state.get("schema_version") != RUN_STATE_SCHEMA_VERSION:
        raise RunStateError(f"run-state schema_version must be {RUN_STATE_SCHEMA_VERSION}")
    return state


def _save_state(run_dir: Path, state: Mapping[str, Any]) -> None:
    payload = dict(state)
    payload["updated_at"] = _now()
    _atomic_write_json(_state_path(run_dir), payload)


def _validate_symbol(symbol: str) -> str:
    normalized = symbol.strip().upper()
    if not SYMBOL_RE.fullmatch(normalized):
        raise RunStateError(f"invalid symbol: {symbol!r}")
    return normalized


def _selected_symbols(state: Mapping[str, Any]) -> set[str]:
    audit = _mapping(state.get("screening_audit"))
    return {_validate_symbol(str(value)) for value in audit.get("selected_symbols", [])}


def _verified_symbols(state: Mapping[str, Any]) -> set[str]:
    result: set[str] = set()
    for symbol, metadata_raw in _mapping(state.get("candidates")).items():
        if _mapping(metadata_raw).get("stage") == "verified":
            result.add(_validate_symbol(symbol))
    return result


def _state_invariants(state: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    audit = _mapping(state.get("screening_audit"))
    selected = _selected_symbols(state) if audit else set()
    verified = _verified_symbols(state)
    declared = {_validate_symbol(str(value)) for value in state.get("unprocessed_candidates", [])}
    expected = selected - verified
    if declared != expected:
        errors.append(
            "unprocessed_candidates must equal selected minus verified: "
            f"declared={sorted(declared)}, expected={sorted(expected)}"
        )
    unexpected_verified = verified - selected
    if unexpected_verified:
        errors.append(
            "verified candidates were not selected: " + ", ".join(sorted(unexpected_verified))
        )

    funnel = _mapping(state.get("screening_funnel"))
    if audit:
        universe = _mapping(audit.get("universe"))
        candidate_pool = _mapping(audit.get("candidate_pool"))
        expected_funnel = {
            "universe_count": int(universe.get("row_count") or 0),
            "listing_in_scope_count": int(universe.get("in_scope_count") or 0),
            "candidate_pool_count": int(candidate_pool.get("row_count") or 0),
            "discovery_evaluable_count": int(candidate_pool.get("discovery_evaluable_count") or 0),
            "deep_dive_selected_count": len(selected),
            "deep_dive_completed_count": len(verified & selected),
        }
        for key, value in expected_funnel.items():
            if int(funnel.get(key) or 0) != value:
                errors.append(f"screening_funnel.{key} does not match attached audit/run state")

    outcome = (_text(audit.get("selection_outcome")) or "").lower()
    pool_status = (_text(audit.get("candidate_pool_status")) or "").lower()
    if pool_status == "sufficient":
        if not selected or outcome != "selected":
            errors.append(
                "candidate_pool_status=sufficient requires selected symbols and selection_outcome=selected"
            )
    elif pool_status == "sufficient_pending_enrichment":
        if not selected or outcome != "selected_pending_enrichment":
            errors.append(
                "candidate_pool_status=sufficient_pending_enrichment requires selected symbols and selection_outcome=selected_pending_enrichment"
            )
    elif pool_status == "no_qualifying_candidates":
        if selected or outcome != "no_candidates":
            errors.append(
                "no_qualifying_candidates requires no selected symbols and selection_outcome=no_candidates"
            )
    elif pool_status == "no_qualifying_candidates_in_bounded_pool":
        if selected or outcome != "no_candidates_in_bounded_pool":
            errors.append(
                "bounded-pool no-candidates requires no selected symbols and the scoped selection outcome"
            )
    elif pool_status == "insufficient_data":
        if selected or outcome != "insufficient_data":
            errors.append(
                "insufficient_data requires no selected symbols and selection_outcome=insufficient_data"
            )
    elif audit:
        errors.append("screening_audit.candidate_pool_status is invalid")
    return errors


def cmd_init(args: argparse.Namespace) -> int:
    run_dir: Path = args.run_dir
    if _state_path(run_dir).exists() and not args.force:
        raise RunStateError(f"run already exists: {run_dir}; use --force to replace")
    config = _read_json(args.config) if args.config else {}
    market_context = _read_json(args.market_context)
    global_sources = _read_json(args.global_sources)
    if not isinstance(config, Mapping) or not isinstance(market_context, Mapping):
        raise RunStateError("config and market-context files must contain JSON objects")
    if not isinstance(global_sources, list):
        raise RunStateError("global-sources file must contain a JSON array")
    summary = _text(market_context.get("summary"))
    if not summary or "replace this" in summary.lower() or "placeholder" in summary.lower():
        raise RunStateError(
            "market context must be populated with current data; example placeholders are rejected"
        )
    if (
        not isinstance(market_context.get("source_ids"), list)
        or len(market_context["source_ids"]) < 2
    ):
        raise RunStateError("market context must reference at least two global source IDs")
    state = {
        "schema_version": RUN_STATE_SCHEMA_VERSION,
        "runtime": runtime_metadata(),
        "run_id": args.run_id or run_dir.name,
        "created_at": _now(),
        "updated_at": _now(),
        "status": "partial",
        "analysis_as_of": args.analysis_as_of,
        "base_repository_commit": args.base_commit,
        "price_basis": {
            "as_of": args.price_as_of,
            "session": args.session,
            "timezone": args.timezone,
            "source_id": args.price_source_id,
        },
        "config": dict(config),
        "market_context": dict(market_context),
        "global_sources": list(global_sources),
        "screening_funnel": {},
        "screening_audit": {},
        "candidates": {},
        "unprocessed_candidates": [],
    }
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "candidates").mkdir(exist_ok=True)
    (run_dir / "audit").mkdir(exist_ok=True)
    _save_state(run_dir, state)
    _append_event(run_dir, {"at": _now(), "event": "run_initialized", "run_id": state["run_id"]})
    print(f"initialized: {run_dir}")
    return 0


def _verify_and_copy_artifact(
    run_dir: Path,
    section: Mapping[str, Any],
    source_path: Path,
    target_name: str,
    label: str,
) -> dict[str, Any]:
    if not source_path.is_file():
        raise RunStateError(f"{label} artifact not found: {source_path}")
    actual_sha = hashlib.sha256(source_path.read_bytes()).hexdigest()
    expected_sha = _text(section.get("artifact_sha256"))
    if expected_sha != actual_sha:
        raise RunStateError(f"{label} artifact SHA-256 does not match audit JSON")
    audit_dir = run_dir / "audit"
    audit_dir.mkdir(parents=True, exist_ok=True)
    target = audit_dir / target_name
    shutil.copyfile(source_path, target)
    normalized = dict(section)
    normalized["artifact_path"] = target.relative_to(run_dir).as_posix()
    normalized["artifact_sha256"] = actual_sha
    return normalized


def _resolve_artifact_argument(
    explicit: Path | None,
    section: Mapping[str, Any],
    audit_path: Path,
    *,
    label: str,
) -> Path:
    if explicit is not None:
        return explicit
    relative = _text(section.get("artifact_path"))
    if not relative:
        raise RunStateError(f"{label} artifact path is required")
    candidate = (audit_path.parent / relative).resolve()
    if not candidate.is_file():
        raise RunStateError(f"{label} artifact not found beside audit JSON: {candidate}")
    return candidate


def cmd_set_screening_audit(args: argparse.Namespace) -> int:
    run_dir: Path = args.run_dir
    state = _load_state(run_dir)
    audit = _read_json(args.audit)
    if not isinstance(audit, Mapping):
        raise RunStateError("audit file must contain a JSON object")
    audit = dict(audit)
    if audit.get("audit_schema_version") != AUDIT_SCHEMA_VERSION:
        raise RunStateError(f"audit_schema_version must be {AUDIT_SCHEMA_VERSION}")
    if (_text(audit.get("contract_revision")) or "") != CONTRACT_REVISION:
        raise RunStateError(f"contract_revision must be {CONTRACT_REVISION!r}")
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
            raise RunStateError(
                f"audit runtime {key} does not match installed skill v{SKILL_VERSION}"
            )

    universe_section = _mapping(audit.get("universe"))
    candidate_section = _mapping(audit.get("candidate_pool"))
    listing_path = _resolve_artifact_argument(
        args.universe_artifact or args.listing_artifact,
        universe_section,
        args.audit,
        label="universe",
    )
    candidate_path = _resolve_artifact_argument(
        args.candidate_artifact or args.artifact,
        candidate_section,
        args.audit,
        label="candidate-pool",
    )

    normalized = dict(audit)
    normalized["universe"] = _verify_and_copy_artifact(
        run_dir, universe_section, listing_path, "universe-audit-results.jsonl", "universe"
    )
    normalized["candidate_pool"] = _verify_and_copy_artifact(
        run_dir, candidate_section, candidate_path, "broad-screen-results.jsonl", "candidate-pool"
    )
    # The discovery-stage artifacts (enrichment queue, provider-prefilter pool)
    # are referenced by bare file names relative to the audit JSON. Copy them
    # into run/audit/ and rewrite their paths to the same run-relative base as
    # universe/candidate_pool, so prepublish_audit --artifact-root <run> resolves
    # every artifact from one root.
    enrichment_section = _mapping(normalized.get("enrichment"))
    if _text(enrichment_section.get("artifact_path")):
        enrichment_path = _resolve_artifact_argument(
            None, enrichment_section, args.audit, label="enrichment"
        )
        normalized["enrichment"] = _verify_and_copy_artifact(
            run_dir, enrichment_section, enrichment_path, enrichment_path.name, "enrichment"
        )
    generation_section = _mapping(normalized["candidate_pool"].get("generation_audit"))
    if generation_section and _text(generation_section.get("artifact_path")):
        generation_path = _resolve_artifact_argument(
            None, generation_section, args.audit, label="candidate-pool generation"
        )
        normalized["candidate_pool"]["generation_audit"] = _verify_and_copy_artifact(
            run_dir,
            generation_section,
            generation_path,
            generation_path.name,
            "candidate-pool generation",
        )
    selected = audit.get("selected_symbols")
    if not isinstance(selected, list) or not all(
        isinstance(value, str) and value.strip() for value in selected
    ):
        raise RunStateError("audit selected_symbols must be an array of symbols")
    normalized["selected_symbols"] = sorted({_validate_symbol(value) for value in selected})
    deep_plan = _mapping(normalized.get("deep_dive_plan"))
    planned = sorted({_validate_symbol(value) for value in deep_plan.get("selected_symbols", [])})
    if planned != normalized["selected_symbols"]:
        raise RunStateError("deep_dive_plan.selected_symbols must match selected_symbols")
    if int(deep_plan.get("selected_count") or -1) != len(normalized["selected_symbols"]):
        raise RunStateError("deep_dive_plan.selected_count must match selected_symbols")
    for key in (
        "all_selected_must_be_resolved",
        "budget_locked",
        "budget_change_requires_rescreen",
        "selected_set_is_committed",
    ):
        if deep_plan.get(key) is not True:
            raise RunStateError(f"deep_dive_plan.{key} must be true")
    for key in ("user_confirmation_required", "user_continue_instruction_allowed"):
        if deep_plan.get(key) is not False:
            raise RunStateError(f"deep_dive_plan.{key} must be false")
    max_deep_dives = int(deep_plan.get("max_deep_dive_candidates") or -1)
    if max_deep_dives != int(
        _mapping(normalized.get("filters")).get("max_deep_dive_candidates") or -2
    ):
        raise RunStateError("deep_dive_plan.max_deep_dive_candidates must match filters")
    expected_payload = {
        "analysis_as_of": _text(normalized.get("analysis_as_of")),
        "max_deep_dive_candidates": max_deep_dives,
        "selected_symbols": normalized["selected_symbols"],
    }
    if _mapping(deep_plan.get("commitment_payload")) != expected_payload:
        raise RunStateError(
            "deep_dive_plan.commitment_payload must match the committed selected set"
        )
    expected_sha = hashlib.sha256(
        json.dumps(expected_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    if (_text(deep_plan.get("selected_set_sha256")) or "").lower() != expected_sha:
        raise RunStateError("deep_dive_plan.selected_set_sha256 does not match commitment payload")

    pool_status = (_text(normalized.get("candidate_pool_status")) or "").lower()
    outcome = (_text(normalized.get("selection_outcome")) or "").lower()
    expected_outcome = {
        "sufficient": "selected",
        "sufficient_pending_enrichment": "selected_pending_enrichment",
        "no_qualifying_candidates": "no_candidates",
        "no_qualifying_candidates_in_bounded_pool": "no_candidates_in_bounded_pool",
        "insufficient_data": "insufficient_data",
    }.get(pool_status)
    if expected_outcome is None:
        raise RunStateError("candidate_pool_status is invalid")
    if outcome != expected_outcome:
        raise RunStateError(f"selection_outcome must be {expected_outcome!r}")
    if (
        pool_status in {"sufficient", "sufficient_pending_enrichment"}
        and not normalized["selected_symbols"]
    ):
        raise RunStateError(f"candidate_pool_status={pool_status} requires selected symbols")
    if (
        pool_status not in {"sufficient", "sufficient_pending_enrichment"}
        and normalized["selected_symbols"]
    ):
        raise RunStateError(f"candidate_pool_status={pool_status} cannot have selected symbols")

    _atomic_write_json(run_dir / "audit" / "broad-screen-audit.json", normalized)
    state["screening_audit"] = normalized
    state["screening_funnel"] = {
        "universe_count": int(_mapping(normalized.get("universe")).get("row_count") or 0),
        "listing_in_scope_count": int(
            _mapping(normalized.get("universe")).get("in_scope_count") or 0
        ),
        "candidate_pool_count": int(
            _mapping(normalized.get("candidate_pool")).get("row_count") or 0
        ),
        "discovery_evaluable_count": int(
            _mapping(normalized.get("candidate_pool")).get("discovery_evaluable_count") or 0
        ),
        "deep_dive_selected_count": len(normalized["selected_symbols"]),
        "preflight_passed_count": 0,
        "deep_dive_completed_count": 0,
    }
    selected_set = set(normalized["selected_symbols"])
    state["unprocessed_candidates"] = sorted(selected_set - _verified_symbols(state))
    state["status"] = "partial"
    _save_state(run_dir, state)
    _append_event(
        run_dir,
        {
            "at": _now(),
            "event": "screening_audit_attached",
            "selected_symbols": normalized["selected_symbols"],
            "selection_outcome": outcome,
            "candidate_pool_status": pool_status,
        },
    )
    print(f"attached: {run_dir / 'audit' / 'broad-screen-audit.json'}")
    return 0


def cmd_save_candidate(args: argparse.Namespace) -> int:
    run_dir: Path = args.run_dir
    state = _load_state(run_dir)
    candidate = _read_json(args.candidate)
    if not isinstance(candidate, Mapping):
        raise RunStateError("candidate file must contain a JSON object")
    identity = _mapping(candidate.get("identity"))
    symbol_text = _text(identity.get("symbol"))
    if not symbol_text:
        raise RunStateError("candidate.identity.symbol is required")
    symbol = _validate_symbol(symbol_text)
    selected = _selected_symbols(state)
    if symbol not in selected and not args.allow_unselected:
        raise RunStateError(f"candidate {symbol} was not selected by the verified screening audit")
    candidate = dict(candidate)
    candidate.setdefault("identity", {})["symbol"] = symbol
    target = run_dir / "candidates" / f"{symbol}.json"
    _atomic_write_json(target, candidate)
    candidates = _mapping(state.get("candidates"))
    candidates[symbol] = {
        "path": str(target.relative_to(run_dir)),
        "stage": args.stage,
        "updated_at": _now(),
        "company_name": _text(identity.get("company_name")),
    }
    state["candidates"] = candidates
    state["unprocessed_candidates"] = sorted(selected - _verified_symbols(state))
    funnel = _mapping(state.get("screening_funnel"))
    funnel["deep_dive_completed_count"] = len(_verified_symbols(state) & selected)
    state["screening_funnel"] = funnel
    _save_state(run_dir, state)
    _append_event(
        run_dir, {"at": _now(), "event": "candidate_saved", "symbol": symbol, "stage": args.stage}
    )
    print(f"saved: {target}")
    return 0


def cmd_set_funnel(args: argparse.Namespace) -> int:
    run_dir: Path = args.run_dir
    state = _load_state(run_dir)
    funnel = _mapping(state.get("screening_funnel"))
    if args.preflight_passed_count is not None:
        if args.preflight_passed_count < 0:
            raise RunStateError("preflight_passed_count must be non-negative")
        selected_count = int(funnel.get("deep_dive_selected_count") or 0)
        if args.preflight_passed_count > selected_count:
            raise RunStateError("preflight_passed_count cannot exceed deep_dive_selected_count")
        funnel["preflight_passed_count"] = args.preflight_passed_count
    if args.note:
        notes = list(funnel.get("notes") or [])
        notes.extend(args.note)
        funnel["notes"] = notes
    state["screening_funnel"] = funnel
    _save_state(run_dir, state)
    _append_event(run_dir, {"at": _now(), "event": "funnel_updated", "funnel": funnel})
    print(json.dumps(funnel, ensure_ascii=False, indent=2))
    return 0


def cmd_set_unprocessed(args: argparse.Namespace) -> int:
    """Validate, not override, the mathematically expected unprocessed set."""
    run_dir: Path = args.run_dir
    state = _load_state(run_dir)
    supplied = {_validate_symbol(value) for value in args.symbols}
    expected = _selected_symbols(state) - _verified_symbols(state)
    if supplied != expected:
        raise RunStateError(
            "cannot set an inconsistent unprocessed list; expected " + json.dumps(sorted(expected))
        )
    state["unprocessed_candidates"] = sorted(expected)
    if expected:
        state["status"] = "partial"
    _save_state(run_dir, state)
    print(json.dumps(sorted(expected), ensure_ascii=False))
    return 0


def cmd_set_status(args: argparse.Namespace) -> int:
    run_dir: Path = args.run_dir
    state = _load_state(run_dir)
    if args.status == "complete":
        audit = _mapping(state.get("screening_audit"))
        if not audit:
            raise RunStateError(
                "cannot mark complete before a verified tiered screening audit is attached"
            )
        invariants = _state_invariants(state)
        if invariants:
            raise RunStateError("cannot mark complete: " + "; ".join(invariants))
        if _mapping(audit.get("scope")).get("screening_scope_ready") is not True:
            raise RunStateError(
                "cannot mark complete: requested scope is neither fully enumerated nor covered by an audited full-range stratified pool"
            )
        pool_status = (_text(audit.get("candidate_pool_status")) or "").lower()
        if pool_status in {"insufficient_data", "sufficient_pending_enrichment"}:
            raise RunStateError("cannot mark complete: candidate pool is unresolved")
        if pool_status not in {
            "sufficient",
            "no_qualifying_candidates",
            "no_qualifying_candidates_in_bounded_pool",
        }:
            raise RunStateError("cannot mark complete: candidate_pool_status is invalid")
        enrichment = _mapping(audit.get("enrichment"))
        if enrichment.get("candidate_pool_exhausted") is not True:
            raise RunStateError("cannot mark complete: candidate pool is not exhausted")
        if (
            enrichment.get("all_rows_resolved") is not True
            or int(enrichment.get("unresolved_count") or 0) != 0
        ):
            raise RunStateError("cannot mark complete: unresolved candidate rows remain")
        if int(enrichment.get("queue_count") or 0) != 0:
            raise RunStateError("cannot mark complete: enrichment queue is not empty")
        selected = _selected_symbols(state)
        verified = _verified_symbols(state)
        if pool_status == "sufficient" and selected != verified:
            missing = sorted(selected - verified)
            raise RunStateError(
                "cannot mark complete; selected symbols are not verified: " + ", ".join(missing)
            )
        if pool_status in {
            "no_qualifying_candidates",
            "no_qualifying_candidates_in_bounded_pool",
        } and (selected or verified):
            raise RunStateError(
                "no-qualifying-candidates completion cannot contain selected/verified names"
            )
    state["status"] = args.status
    _save_state(run_dir, state)
    _append_event(run_dir, {"at": _now(), "event": "status_updated", "status": args.status})
    print(f"status: {args.status}")
    return 0


def _candidate_paths(run_dir: Path, state: Mapping[str, Any], include_drafts: bool) -> list[Path]:
    paths: list[Path] = []
    selected = _selected_symbols(state)
    for symbol, metadata_value in sorted(_mapping(state.get("candidates")).items()):
        if symbol not in selected:
            continue
        metadata = _mapping(metadata_value)
        if not include_drafts and metadata.get("stage") != "verified":
            continue
        relative = _text(metadata.get("path"))
        if not relative:
            raise RunStateError(f"candidate {symbol} has no path")
        path = run_dir / relative
        if not path.is_file():
            raise RunStateError(f"candidate checkpoint missing: {path}")
        paths.append(path)
    return paths


def cmd_assemble(args: argparse.Namespace) -> int:
    run_dir: Path = args.run_dir
    state = _load_state(run_dir)
    invariants = _state_invariants(state)
    if invariants:
        raise RunStateError("run state is inconsistent: " + "; ".join(invariants))
    candidates: list[Any] = []
    for path in _candidate_paths(run_dir, state, args.include_drafts):
        candidate = _read_json(path)
        if not isinstance(candidate, Mapping):
            raise RunStateError(f"candidate checkpoint must be an object: {path}")
        candidates.append(candidate)
    selected = _selected_symbols(state)
    audit = _mapping(state.get("screening_audit"))
    pool_status = (_text(audit.get("candidate_pool_status")) or "").lower()
    if selected and not candidates:
        raise RunStateError("no selected candidate checkpoints are available for assembly")
    if not selected and not (
        state.get("status") == "complete"
        and pool_status in {"no_qualifying_candidates", "no_qualifying_candidates_in_bounded_pool"}
    ):
        raise RunStateError(
            "zero-candidate snapshot is valid only after a complete no-qualifying-candidates screen"
        )
    payload = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "runtime": runtime_metadata(),
        "analysis_as_of": state.get("analysis_as_of"),
        "run_metadata": {
            "run_id": state.get("run_id"),
            "status": state.get("status", "partial"),
            "base_repository_commit": state.get("base_repository_commit"),
            "selected_symbols": sorted(selected),
            "unprocessed_candidates": state.get("unprocessed_candidates", []),
            "checkpoint_generated_at": _now(),
        },
        "price_basis": state.get("price_basis", {}),
        "config": state.get("config", {}),
        "global_sources": state.get("global_sources", []),
        "market_context": state.get("market_context", {}),
        "screening_funnel": state.get("screening_funnel", {}),
        "screening_audit": state.get("screening_audit", {}),
        "candidates": candidates,
    }
    _atomic_write_json(args.output, payload)
    _append_event(
        run_dir,
        {
            "at": _now(),
            "event": "snapshot_assembled",
            "output": str(args.output),
            "candidate_count": len(candidates),
        },
    )
    print(f"assembled: {args.output}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    run_dir: Path = args.run_dir
    state = _load_state(run_dir)
    candidates = _mapping(state.get("candidates"))
    stage_counts: dict[str, int] = {}
    for metadata in candidates.values():
        stage = _text(_mapping(metadata).get("stage")) or "unknown"
        stage_counts[stage] = stage_counts.get(stage, 0) + 1
    audit = _mapping(state.get("screening_audit"))
    invariants = _state_invariants(state)
    summary = {
        "run_id": state.get("run_id"),
        "status": state.get("status"),
        "updated_at": state.get("updated_at"),
        "candidate_count": len(candidates),
        "stage_counts": stage_counts,
        "unprocessed_candidates": state.get("unprocessed_candidates", []),
        "screening_funnel": state.get("screening_funnel", {}),
        "screening_audit_attached": bool(audit),
        "selection_outcome": audit.get("selection_outcome"),
        "candidate_pool_status": audit.get("candidate_pool_status"),
        "selected_symbols": audit.get("selected_symbols", []),
        "state_consistent": not invariants,
        "invariant_errors": invariants,
        "next_action": _next_action_payload(state),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 2 if args.strict and invariants else 0


def _next_action_payload(state: Mapping[str, Any]) -> dict[str, Any]:
    audit = _mapping(state.get("screening_audit"))
    selected = sorted(_selected_symbols(state)) if audit else []
    verified = sorted(_verified_symbols(state))
    remaining = sorted(set(selected) - set(verified))
    pool_status = (_text(audit.get("candidate_pool_status")) or "").lower()
    enrichment = _mapping(audit.get("enrichment"))
    if not audit:
        action = "attach_screening_audit"
        symbols: list[str] = []
    elif (
        int(enrichment.get("queue_count") or 0) > 0
        or enrichment.get("all_rows_resolved") is not True
    ):
        action = "continue_candidate_pool_enrichment"
        symbols = sorted(str(v).upper() for v in enrichment.get("queue_symbols", []))
    elif remaining:
        action = "complete_all_selected_deep_dives"
        symbols = remaining
    elif state.get("status") != "complete":
        action = "mark_complete_and_assemble"
        symbols = []
    else:
        action = "assemble_and_run_strict_evaluation"
        symbols = []
    return {
        "action": action,
        "symbols": symbols,
        "selected_symbols": selected,
        "verified_symbols": verified,
        "candidate_pool_status": pool_status,
        "user_confirmation_required": False,
        "instruction": (
            "Continue in the same execution. Never ask the user which selected symbols to process. "
            "A budget change requires rerunning the deterministic broad screen before any selected symbol is dropped."
        ),
    }


def cmd_next_action(args: argparse.Namespace) -> int:
    state = _load_state(args.run_dir)
    invariants = _state_invariants(state)
    payload = _next_action_payload(state)
    payload["state_consistent"] = not invariants
    payload["invariant_errors"] = invariants
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 2 if invariants else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Checkpoint and resume schema-3 / contract-3.5 undervalued-growth runs."
    )
    parser.add_argument(
        "--version", action="store_true", help="Print installed skill/runtime metadata and exit"
    )
    sub = parser.add_subparsers(dest="command")

    init = sub.add_parser("init")
    init.add_argument("--run-dir", type=Path, required=True)
    init.add_argument("--run-id")
    init.add_argument("--analysis-as-of", required=True)
    init.add_argument("--price-as-of", required=True)
    init.add_argument(
        "--session",
        choices=("regular_close", "pre_market", "after_hours", "intraday"),
        required=True,
    )
    init.add_argument("--timezone", default="America/New_York")
    init.add_argument("--price-source-id", required=True)
    init.add_argument("--base-commit")
    init.add_argument("--config", type=Path)
    init.add_argument("--market-context", type=Path, required=True)
    init.add_argument("--global-sources", type=Path, required=True)
    init.add_argument("--force", action="store_true")
    init.set_defaults(func=cmd_init)

    audit = sub.add_parser("set-screening-audit")
    audit.add_argument("--run-dir", type=Path, required=True)
    audit.add_argument("--audit", type=Path, required=True)
    audit.add_argument("--universe-artifact", type=Path)
    audit.add_argument("--listing-artifact", type=Path, help="Alias for --universe-artifact")
    audit.add_argument("--candidate-artifact", type=Path)
    audit.add_argument("--artifact", type=Path, help="Legacy alias for --candidate-artifact")
    audit.set_defaults(func=cmd_set_screening_audit)

    save = sub.add_parser("save-candidate")
    save.add_argument("--run-dir", type=Path, required=True)
    save.add_argument("--candidate", type=Path, required=True)
    save.add_argument("--stage", choices=("draft", "verified"), default="draft")
    save.add_argument("--allow-unselected", action="store_true")
    save.set_defaults(func=cmd_save_candidate)

    funnel = sub.add_parser("set-funnel")
    funnel.add_argument("--run-dir", type=Path, required=True)
    funnel.add_argument("--preflight-passed-count", type=int)
    funnel.add_argument("--note", action="append")
    funnel.set_defaults(func=cmd_set_funnel)

    unprocessed = sub.add_parser("set-unprocessed")
    unprocessed.add_argument("--run-dir", type=Path, required=True)
    unprocessed.add_argument("symbols", nargs="*")
    unprocessed.set_defaults(func=cmd_set_unprocessed)

    status = sub.add_parser("set-status")
    status.add_argument("--run-dir", type=Path, required=True)
    status.add_argument("status", choices=("partial", "complete"))
    status.set_defaults(func=cmd_set_status)

    assemble = sub.add_parser("assemble")
    assemble.add_argument("--run-dir", type=Path, required=True)
    assemble.add_argument("--output", type=Path, required=True)
    assemble.add_argument("--include-drafts", action="store_true")
    assemble.set_defaults(func=cmd_assemble)

    next_action = sub.add_parser("next-action")
    next_action.add_argument("--run-dir", type=Path, required=True)
    next_action.set_defaults(func=cmd_next_action)

    show = sub.add_parser("status")
    show.add_argument("--run-dir", type=Path, required=True)
    show.add_argument("--strict", action="store_true")
    show.set_defaults(func=cmd_status)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.version:
        print(json.dumps(runtime_metadata(), sort_keys=True))
        return 0
    if not args.command:
        parser.error("the following arguments are required: command")
    try:
        return int(args.func(args))
    except (OSError, RunStateError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
