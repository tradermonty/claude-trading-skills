"""Step adapters for the stockbee-fluency-loop workflow."""

from __future__ import annotations

import hashlib
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .artifacts import _artifact_paths, _latest_report
from .common import (
    ReplayError,
    _dump_yaml_with_digest_allowlist,
    _load_json,
    _run_cli,
    _schema_error_details,
    _write_json,
    load_yaml,
)
from .constants import MANUAL_LESSONS_SCHEMA
from .normalize import _canonicalize, _normalize_json_file, _normalize_jsonl_file


def _validate_manual_contract(payload: Any, definition: str) -> None:
    schema = _load_json(MANUAL_LESSONS_SCHEMA, "manual-lessons schema")
    selected = {
        "$schema": schema["$schema"],
        "$defs": schema["$defs"],
        "$ref": f"#/$defs/{definition}",
    }
    errors = _schema_error_details(selected, payload)
    if errors:
        raise ReplayError(f"invalid manual lessons {definition} schema:\n- " + "\n- ".join(errors))


def _stockbee_ingest(
    repo_root: Path,
    spec: Mapping[str, Any],
    step: Mapping[str, Any],
    inputs: Mapping[str, Path],
    _consumed: Mapping[str, dict[str, Any]],
    work: Path,
    stage: Path,
) -> dict[str, dict[str, Any]]:
    _load_json(inputs["screener"], "screener")
    state = work / "model_book.jsonl"
    reports = work / "reports"
    reports.mkdir(parents=True)
    script = (
        repo_root / "skills" / "stockbee-setup-fluency-trainer" / "scripts" / "build_model_book.py"
    )
    _run_cli(
        [
            sys.executable,
            str(script),
            "ingest",
            "--screener-json",
            str(inputs["screener"]),
            "--model-book",
            str(state),
            "--output-dir",
            str(reports),
        ],
        repo_root,
    )
    artifacts = _artifact_paths(stage, step["output_files"])
    report_out = Path(artifacts["model_book_ingest"]["files"]["canonical"])
    state_out = Path(artifacts["model_book_ingest"]["files"]["state"])
    replacements = {
        str(inputs["screener"]): "$INPUT/screener.json",
        str(state): "$STATE/model_book.jsonl",
        str(reports): "$WORK/reports",
    }
    _normalize_json_file(
        _latest_report(reports, "stockbee_setup_fluency_ingest_*.json"),
        report_out,
        spec["fixed_timestamp"],
        replacements,
    )
    _normalize_jsonl_file(state, state_out, spec["fixed_timestamp"], replacements)
    return artifacts


def _stockbee_update(
    repo_root: Path,
    spec: Mapping[str, Any],
    step: Mapping[str, Any],
    inputs: Mapping[str, Path],
    consumed: Mapping[str, dict[str, Any]],
    work: Path,
    stage: Path,
) -> dict[str, dict[str, Any]]:
    _load_json(inputs["prices"], "prices")
    source_state = Path(consumed["model_book_ingest"]["files"]["state"])
    state = work / "model_book.jsonl"
    _normalize_jsonl_file(source_state, state, spec["fixed_timestamp"], {})
    reports = work / "reports"
    reports.mkdir(parents=True)
    script = (
        repo_root / "skills" / "stockbee-setup-fluency-trainer" / "scripts" / "build_model_book.py"
    )
    _run_cli(
        [
            sys.executable,
            str(script),
            "update",
            "--model-book",
            str(state),
            "--prices-json",
            str(inputs["prices"]),
            "--horizons",
            "3,5",
            "--output-dir",
            str(reports),
        ],
        repo_root,
    )
    artifacts = _artifact_paths(stage, step["output_files"])
    report_out = Path(artifacts["matured_setup_outcomes"]["files"]["canonical"])
    state_out = Path(artifacts["matured_setup_outcomes"]["files"]["state"])
    replacements = {
        str(inputs["prices"]): "$INPUT/prices.json",
        str(state): "$STATE/model_book.jsonl",
        str(reports): "$WORK/reports",
    }
    _normalize_json_file(
        _latest_report(reports, "stockbee_setup_fluency_update_*.json"),
        report_out,
        spec["fixed_timestamp"],
        replacements,
    )
    _normalize_jsonl_file(state, state_out, spec["fixed_timestamp"], replacements)
    return artifacts


def _stockbee_summarize(
    repo_root: Path,
    spec: Mapping[str, Any],
    step: Mapping[str, Any],
    _inputs: Mapping[str, Path],
    consumed: Mapping[str, dict[str, Any]],
    work: Path,
    stage: Path,
) -> dict[str, dict[str, Any]]:
    source_state = Path(consumed["matured_setup_outcomes"]["files"]["state"])
    state = work / "model_book.jsonl"
    _normalize_jsonl_file(source_state, state, spec["fixed_timestamp"], {})
    reports = work / "reports"
    reports.mkdir(parents=True)
    script = (
        repo_root / "skills" / "stockbee-setup-fluency-trainer" / "scripts" / "build_model_book.py"
    )
    _run_cli(
        [
            sys.executable,
            str(script),
            "summarize",
            "--model-book",
            str(state),
            "--group-by",
            "rating,primary_trigger,setup_tags",
            "--min-sample",
            "5",
            "--output-dir",
            str(reports),
        ],
        repo_root,
    )
    artifacts = _artifact_paths(stage, step["output_files"])
    summary_source = _latest_report(reports, "stockbee_setup_fluency_summary_*.json")
    replacements = {str(state): "$STATE/model_book.jsonl", str(reports): "$WORK/reports"}
    normalized = _canonicalize(
        _load_json(summary_source, "summary"), spec["fixed_timestamp"], replacements
    )
    summary_out = Path(artifacts["setup_fluency_summary"]["files"]["canonical"])
    rules_out = Path(artifacts["rule_candidates"]["files"]["canonical"])
    _write_json(summary_out, normalized)
    _write_json(
        rules_out,
        {
            "schema_version": normalized["schema_version"],
            "generated_at": spec["fixed_timestamp"],
            "rule_candidates": normalized.get("rule_candidates", []),
        },
    )
    return artifacts


def _manual_lessons(
    _repo_root: Path,
    spec: Mapping[str, Any],
    step: Mapping[str, Any],
    inputs: Mapping[str, Path],
    consumed: Mapping[str, dict[str, Any]],
    _work: Path,
    stage: Path,
) -> dict[str, dict[str, Any]]:
    source = load_yaml(inputs["accepted_lessons"])
    _validate_manual_contract(source, "input")
    expected_sources = ["setup_fluency_summary", "rule_candidates"]
    if source.get("human_approved") is not True:
        raise ReplayError("accepted_lessons manual contract requires human_approved: true")
    if source.get("source_artifacts") != expected_sources:
        raise ReplayError(
            f"accepted_lessons source_artifacts must be {expected_sources}, "
            f"got {source.get('source_artifacts')!r}"
        )
    if set(consumed) != set(expected_sources):
        raise ReplayError("manual lessons did not receive both declared consumed artifacts")
    summary_path = Path(consumed["setup_fluency_summary"]["files"]["canonical"])
    rules_path = Path(consumed["rule_candidates"]["files"]["canonical"])
    summary_payload = _load_json(summary_path, "setup_fluency_summary handoff")
    rules_payload = _load_json(rules_path, "rule_candidates handoff")
    if not isinstance(summary_payload, dict) or not isinstance(rules_payload, dict):
        raise ReplayError("manual lessons consumed artifacts must be JSON objects")
    if rules_payload.get("rule_candidates") != summary_payload.get("rule_candidates"):
        raise ReplayError("rule_candidates handoff does not match setup_fluency_summary evidence")
    source_sha256 = {
        "setup_fluency_summary": hashlib.sha256(summary_path.read_bytes()).hexdigest(),
        "rule_candidates": hashlib.sha256(rules_path.read_bytes()).hexdigest(),
    }
    if source["source_sha256"] != source_sha256:
        raise ReplayError(
            "accepted_lessons source_sha256 does not match the replayed step-3 evidence"
        )
    payload = {
        "schema_version": 1,
        "workflow_id": spec["workflow_id"],
        "recorded_at": spec["fixed_timestamp"],
        "source_artifacts": expected_sources,
        "lessons": source.get("lessons") or [],
        "provenance": {
            "execution_mode": "manual_contract",
            "native_trader_memory_validated": False,
            "source_sha256": source_sha256,
            "note": "Human-approved fixture staged by replay harness; no trader-memory-core append API was executed.",
        },
    }
    _validate_manual_contract(payload, "output")
    artifacts = _artifact_paths(stage, step["output_files"])
    output = Path(artifacts["accepted_lessons_log"]["files"]["canonical"])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(_dump_yaml_with_digest_allowlist(payload), encoding="utf-8", newline="\n")
    return artifacts
