"""Step adapters for the stockbee-20pct-study-daily workflow."""

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
from .constants import TWENTY_PCT_LESSONS_SCHEMA
from .normalize import _canonicalize, _normalize_json_file, _normalize_jsonl_file


def _validate_twenty_pct_manual_contract(payload: Any, definition: str) -> None:
    schema = _load_json(TWENTY_PCT_LESSONS_SCHEMA, "twenty-percent lessons schema")
    selected = {
        "$schema": schema["$schema"],
        "$defs": schema["$defs"],
        "$ref": f"#/$defs/{definition}",
    }
    errors = _schema_error_details(selected, payload)
    if errors:
        raise ReplayError(
            f"invalid twenty-percent lessons {definition} schema:\n- " + "\n- ".join(errors)
        )


def _twenty_pct_script(repo_root: Path) -> Path:
    return repo_root / "skills" / "stockbee-20pct-study" / "scripts" / "run_20pct_study.py"


def _stage_state_handoff(
    source: Path,
    destination: Path,
    fixed_timestamp: str,
) -> None:
    _normalize_jsonl_file(source, destination, fixed_timestamp, {})


def _twenty_pct_scan(
    repo_root: Path,
    spec: Mapping[str, Any],
    step: Mapping[str, Any],
    inputs: Mapping[str, Path],
    _consumed: Mapping[str, dict[str, Any]],
    work: Path,
    stage: Path,
) -> dict[str, dict[str, Any]]:
    _load_json(inputs["prices"], "twenty-percent prices")
    state = work / "events.jsonl"
    reports = work / "reports"
    reports.mkdir(parents=True)
    _run_cli(
        [
            sys.executable,
            str(_twenty_pct_script(repo_root)),
            "scan",
            "--prices-json",
            str(inputs["prices"]),
            "--as-of",
            spec["fixed_timestamp"][:10],
            "--lookback-days",
            "5",
            "--min-price",
            "1",
            "--min-dollar-volume",
            "0",
            "--include-down-movers",
            "--state-file",
            str(state),
            "--output-dir",
            str(reports),
        ],
        repo_root,
    )
    artifacts = _artifact_paths(stage, step["output_files"])
    replacements = {
        str(inputs["prices"]): "$INPUT/prices.json",
        str(state): "$STATE/events.jsonl",
        str(reports): "$WORK/reports",
    }
    _normalize_json_file(
        _latest_report(reports, "stockbee_20pct_events_*.json"),
        Path(artifacts["twenty_pct_mover_events"]["files"]["canonical"]),
        spec["fixed_timestamp"],
        replacements,
    )
    _normalize_jsonl_file(
        state,
        Path(artifacts["twenty_pct_mover_events"]["files"]["state"]),
        spec["fixed_timestamp"],
        replacements,
    )
    return artifacts


def _twenty_pct_enrich(
    repo_root: Path,
    spec: Mapping[str, Any],
    step: Mapping[str, Any],
    inputs: Mapping[str, Path],
    consumed: Mapping[str, dict[str, Any]],
    work: Path,
    stage: Path,
) -> dict[str, dict[str, Any]]:
    _load_json(inputs["news"], "twenty-percent news")
    source = consumed["twenty_pct_mover_events"]
    events = Path(source["files"]["canonical"])
    _load_json(events, "twenty-percent mover events handoff")
    state = work / "events.jsonl"
    _stage_state_handoff(Path(source["files"]["state"]), state, spec["fixed_timestamp"])
    reports = work / "reports"
    reports.mkdir(parents=True)
    _run_cli(
        [
            sys.executable,
            str(_twenty_pct_script(repo_root)),
            "enrich",
            "--events-json",
            str(events),
            "--news-json",
            str(inputs["news"]),
            "--state-file",
            str(state),
            "--output-dir",
            str(reports),
        ],
        repo_root,
    )
    artifacts = _artifact_paths(stage, step["output_files"])
    replacements = {
        str(events): "$ARTIFACT/twenty_pct_mover_events.json",
        str(inputs["news"]): "$INPUT/news.json",
        str(state): "$STATE/events.jsonl",
        str(reports): "$WORK/reports",
    }
    _normalize_json_file(
        _latest_report(reports, "stockbee_20pct_enriched_*.json"),
        Path(artifacts["classified_event_study"]["files"]["canonical"]),
        spec["fixed_timestamp"],
        replacements,
    )
    _normalize_jsonl_file(
        state,
        Path(artifacts["classified_event_study"]["files"]["state"]),
        spec["fixed_timestamp"],
        replacements,
    )
    return artifacts


def _twenty_pct_update_outcomes(
    repo_root: Path,
    spec: Mapping[str, Any],
    step: Mapping[str, Any],
    inputs: Mapping[str, Path],
    consumed: Mapping[str, dict[str, Any]],
    work: Path,
    stage: Path,
) -> dict[str, dict[str, Any]]:
    _load_json(inputs["prices"], "twenty-percent prices")
    source = consumed["classified_event_study"]
    state = work / "events.jsonl"
    _stage_state_handoff(Path(source["files"]["state"]), state, spec["fixed_timestamp"])
    reports = work / "reports"
    reports.mkdir(parents=True)
    _run_cli(
        [
            sys.executable,
            str(_twenty_pct_script(repo_root)),
            "update-outcomes",
            "--prices-json",
            str(inputs["prices"]),
            "--horizons",
            "5",
            "--state-file",
            str(state),
            "--output-dir",
            str(reports),
        ],
        repo_root,
    )
    artifacts = _artifact_paths(stage, step["output_files"])
    replacements = {
        str(inputs["prices"]): "$INPUT/prices.json",
        str(state): "$STATE/events.jsonl",
        str(reports): "$WORK/reports",
    }
    _normalize_json_file(
        _latest_report(reports, "stockbee_20pct_outcome_update_*.json"),
        Path(artifacts["matured_event_outcomes"]["files"]["canonical"]),
        spec["fixed_timestamp"],
        replacements,
    )
    _normalize_jsonl_file(
        state,
        Path(artifacts["matured_event_outcomes"]["files"]["state"]),
        spec["fixed_timestamp"],
        replacements,
    )
    return artifacts


def _twenty_pct_summarize(
    repo_root: Path,
    spec: Mapping[str, Any],
    step: Mapping[str, Any],
    _inputs: Mapping[str, Path],
    consumed: Mapping[str, dict[str, Any]],
    work: Path,
    stage: Path,
) -> dict[str, dict[str, Any]]:
    source = consumed["matured_event_outcomes"]
    state = work / "events.jsonl"
    _stage_state_handoff(Path(source["files"]["state"]), state, spec["fixed_timestamp"])
    reports = work / "reports"
    reports.mkdir(parents=True)
    _run_cli(
        [
            sys.executable,
            str(_twenty_pct_script(repo_root)),
            "summarize",
            "--state-file",
            str(state),
            "--group-by",
            "direction,catalyst.label,technical_context.pattern_label,technical_context.close_quality",
            "--min-sample",
            "1",
            "--horizon",
            "5",
            "--output-dir",
            str(reports),
        ],
        repo_root,
    )
    summary_source = _latest_report(reports, "stockbee_20pct_cohort_summary_*.json")
    hints_source = _latest_report(reports, "stockbee_20pct_edge_hints_*.yaml")
    summary = _canonicalize(
        _load_json(summary_source, "twenty-percent cohort summary"),
        spec["fixed_timestamp"],
        {str(state): "$STATE/events.jsonl", str(reports): "$WORK/reports"},
    )
    hints = _canonicalize(
        _load_json(hints_source, "twenty-percent edge hints"),
        spec["fixed_timestamp"],
        {str(state): "$STATE/events.jsonl", str(reports): "$WORK/reports"},
    )
    if hints.get("edge_hints") != summary.get("rule_candidates"):
        raise ReplayError("edge_hints handoff does not match cohort summary rule_candidates")
    artifacts = _artifact_paths(stage, step["output_files"])
    _write_json(Path(artifacts["twenty_pct_cohort_summary"]["files"]["canonical"]), summary)
    _write_json(Path(artifacts["edge_hints_yaml"]["files"]["canonical"]), hints)
    return artifacts


def _manual_twenty_pct_lessons(
    _repo_root: Path,
    spec: Mapping[str, Any],
    step: Mapping[str, Any],
    inputs: Mapping[str, Path],
    consumed: Mapping[str, dict[str, Any]],
    _work: Path,
    stage: Path,
) -> dict[str, dict[str, Any]]:
    source = load_yaml(inputs["accepted_lessons"])
    _validate_twenty_pct_manual_contract(source, "input")
    expected_sources = ["twenty_pct_cohort_summary", "edge_hints_yaml"]
    if source.get("human_approved") is not True:
        raise ReplayError("twenty-percent lessons manual contract requires human_approved: true")
    if source.get("source_artifacts") != expected_sources:
        raise ReplayError(
            f"twenty-percent source_artifacts must be {expected_sources}, "
            f"got {source.get('source_artifacts')!r}"
        )
    if set(consumed) != set(expected_sources):
        raise ReplayError("twenty-percent lessons did not receive both declared artifacts")
    summary_path = Path(consumed["twenty_pct_cohort_summary"]["files"]["canonical"])
    hints_path = Path(consumed["edge_hints_yaml"]["files"]["canonical"])
    summary = _load_json(summary_path, "twenty_pct_cohort_summary handoff")
    hints = load_yaml(hints_path)
    if hints.get("edge_hints") != summary.get("rule_candidates"):
        raise ReplayError("edge_hints handoff does not match cohort summary evidence")
    source_sha256 = {
        "twenty_pct_cohort_summary": hashlib.sha256(summary_path.read_bytes()).hexdigest(),
        "edge_hints_yaml": hashlib.sha256(hints_path.read_bytes()).hexdigest(),
    }
    if source["source_sha256"] != source_sha256:
        raise ReplayError(
            "twenty-percent lessons source_sha256 does not match replayed step-4 evidence"
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
    _validate_twenty_pct_manual_contract(payload, "output")
    artifacts = _artifact_paths(stage, step["output_files"])
    output = Path(artifacts["accepted_lessons_log"]["files"]["canonical"])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(_dump_yaml_with_digest_allowlist(payload), encoding="utf-8", newline="\n")
    return artifacts
