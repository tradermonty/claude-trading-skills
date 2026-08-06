#!/usr/bin/env python3
"""Deterministic workflow contract replay harness (Issue #294 Phase 1).

The pilot executes the real offline Stockbee fluency CLI for steps 1-3. The
optional human journal step is deliberately reported as ``manual_contract``;
it does not claim to execute trader-memory-core. Golden outputs are comparison
targets only and are never used as replay inputs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_COVERAGE = REPO_ROOT / "examples" / "workflows" / "replay-coverage.yaml"
SPEC_SCHEMA = REPO_ROOT / "examples" / "workflows" / "replay-spec.schema.json"
MANUAL_LESSONS_SCHEMA = REPO_ROOT / "examples" / "workflows" / "manual-lessons.schema.json"
VARIANTS = ("required-only", "full-path")

# Phase 1 deliberately covers one workflow. This frozen baseline prevents a
# newly introduced workflow from being waved through as another deferral.
PHASE1_DEFERRED_WORKFLOWS = frozenset(
    {
        "core-portfolio-weekly",
        "kanchi-dividend-weekly",
        "market-regime-daily",
        "monthly-performance-review",
        "multi-asset-opportunity-daily",
        "shapiro-contrarian",
        "stockbee-20pct-study-daily",
        "stockbee-ep-daily",
        "swing-opportunity-daily",
        "trade-memory-loop",
    }
)

TIMESTAMP_FIELDS = frozenset({"generated_at", "created_at", "updated_at", "last_outcome_update_at"})
SENSITIVE_ENV_MARKERS = ("API_KEY", "TOKEN", "SECRET", "PASSWORD", "PROXY")
RFC3339_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)


class ReplayError(RuntimeError):
    """Fail-closed replay error with an auditable completed-step boundary."""

    def __init__(self, message: str, completed_steps: list[int] | None = None):
        super().__init__(message)
        self.completed_steps = list(completed_steps or [])


@dataclass(frozen=True)
class ExecutorRegistration:
    """An executor and its non-overridable evidence classification."""

    mode: str
    run: Callable[..., dict[str, dict[str, Any]]]


def load_yaml(path: Path) -> dict[str, Any]:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ReplayError(f"cannot load YAML {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ReplayError(f"YAML root must be a mapping: {path}")
    return payload


def _load_json(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReplayError(f"invalid {label} JSON at {path}: {exc}") from exc


def _dump_yaml_with_digest_allowlist(payload: Any) -> str:
    """Serialize fixture evidence while marking deterministic hashes as non-secrets."""
    rendered = yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)
    digest_line = re.compile(
        r"^(\s+(?:setup_fluency_summary|rule_candidates): [0-9a-f]{64})$",
        re.MULTILINE,
    )
    return digest_line.sub(r"\1  # pragma: allowlist secret", rendered)


def _schema_error_details(schema: Mapping[str, Any], payload: Any) -> list[str]:
    errors = sorted(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(payload),
        key=lambda error: list(error.path),
    )
    return [f"{'.'.join(map(str, error.path)) or '<root>'}: {error.message}" for error in errors]


def _require_rfc3339(value: Any, label: str) -> None:
    if not isinstance(value, str) or not RFC3339_PATTERN.fullmatch(value):
        raise ReplayError(f"{label} must be an RFC 3339 date-time with timezone")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ReplayError(f"{label} must be a valid RFC 3339 date-time: {value!r}") from exc
    if parsed.utcoffset() is None:
        raise ReplayError(f"{label} must include an RFC 3339 timezone")


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


def coverage_errors(workflow_ids: set[str], coverage: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    covered = coverage.get("covered") or {}
    deferred = coverage.get("deferred") or {}
    if not isinstance(covered, dict):
        errors.append("covered must be a mapping")
        covered = {}
    if not isinstance(deferred, dict):
        errors.append("deferred must be a mapping")
        deferred = {}

    overlap = set(covered) & set(deferred)
    if overlap:
        errors.append(f"workflows cannot be both covered and deferred: {sorted(overlap)}")

    classified = set(covered) | set(deferred)
    missing = workflow_ids - classified
    unknown = classified - workflow_ids
    if missing:
        errors.append(f"missing replay coverage for workflows: {sorted(missing)}")
    if unknown:
        errors.append(f"coverage references unknown workflows: {sorted(unknown)}")

    if set(deferred) != PHASE1_DEFERRED_WORKFLOWS:
        errors.append(
            "deferred workflows must match the frozen Phase 1 deferred set; "
            f"expected {sorted(PHASE1_DEFERRED_WORKFLOWS)}, got {sorted(deferred)}"
        )
    for workflow_id, entry in deferred.items():
        if not isinstance(entry, dict):
            errors.append(f"deferred.{workflow_id} must be a mapping")
            continue
        if entry.get("issue") != 294:
            errors.append(f"deferred.{workflow_id}.issue must be 294")
        if not str(entry.get("reason") or "").strip():
            errors.append(f"deferred.{workflow_id}.reason is required")

    for workflow_id, entry in covered.items():
        if not isinstance(entry, dict):
            errors.append(f"covered.{workflow_id} must be a mapping")
            continue
        variants = entry.get("variants")
        if variants != list(VARIANTS):
            errors.append(
                f"covered.{workflow_id}.variants must be {list(VARIANTS)}, got {variants!r}"
            )
        if not str(entry.get("spec") or "").strip():
            errors.append(f"covered.{workflow_id}.spec is required")
    return errors


def validate_coverage(repo_root: Path, coverage_path: Path) -> dict[str, Any]:
    coverage = load_yaml(coverage_path)
    workflow_ids = {path.stem for path in (repo_root / "workflows").glob("*.yaml")}
    errors = coverage_errors(workflow_ids, coverage)
    covered = coverage.get("covered") or {}
    if not errors:
        for workflow_id, entry in covered.items():
            spec_path = (coverage_path.parent / entry["spec"]).resolve()
            summary = validate_spec(repo_root, spec_path)
            if summary["workflow_id"] != workflow_id:
                errors.append(
                    f"covered key {workflow_id!r} does not match spec workflow "
                    f"{summary['workflow_id']!r}"
                )
    if errors:
        raise ReplayError("invalid replay coverage:\n- " + "\n- ".join(errors))
    return {
        "covered": sorted(covered),
        "deferred": sorted(coverage.get("deferred") or {}),
        "variants": {workflow_id: entry["variants"] for workflow_id, entry in covered.items()},
    }


def _safe_relative(base: Path, value: str, label: str) -> Path:
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise ReplayError(f"{label} must be a safe relative path: {value!r}")
    resolved = (base / relative).resolve()
    try:
        resolved.relative_to(base.resolve())
    except ValueError as exc:
        raise ReplayError(f"{label} escapes {base}: {value!r}") from exc
    return resolved


def validate_spec(repo_root: Path, spec_path: Path) -> dict[str, Any]:
    spec = load_yaml(spec_path)
    schema = _load_json(SPEC_SCHEMA, "replay-spec schema")
    schema_errors = _schema_error_details(schema, spec)
    if schema_errors:
        raise ReplayError("invalid replay spec schema:\n- " + "\n- ".join(schema_errors))
    # jsonschema treats formats without optional validators as annotations.
    # Enforce the normalization anchor independently in every environment.
    _require_rfc3339(spec["fixed_timestamp"], "fixed_timestamp")

    workflow_id = spec["workflow_id"]
    workflow_path = repo_root / "workflows" / f"{workflow_id}.yaml"
    workflow = load_yaml(workflow_path)
    if workflow.get("id") != workflow_id:
        raise ReplayError(f"workflow id mismatch in {workflow_path}")

    workflow_steps = {int(step["step"]): step for step in workflow["steps"]}
    spec_steps = {int(step["step"]): step for step in spec["steps"]}
    if set(spec_steps) != set(workflow_steps):
        raise ReplayError(
            f"spec steps must exactly match workflow steps: expected {sorted(workflow_steps)}, "
            f"got {sorted(spec_steps)}"
        )

    native_steps: list[int] = []
    manual_steps: list[int] = []
    output_path_owners: dict[Path, str] = {}
    for number, step in workflow_steps.items():
        replay_step = spec_steps[number]
        expected_outputs = set(step.get("produces") or [])
        configured_outputs = set((replay_step.get("output_files") or {}).keys())
        if expected_outputs != configured_outputs:
            raise ReplayError(
                f"step {number} output_files must match produces: "
                f"expected {sorted(expected_outputs)}, got {sorted(configured_outputs)}"
            )
        expected_policy = (
            {"record_only", "continue", "halt"} if step.get("decision_gate") else {"continue"}
        )
        if replay_step["gate_policy"] not in expected_policy:
            raise ReplayError(
                f"step {number} gate_policy {replay_step['gate_policy']!r} is incompatible "
                f"with decision_gate={bool(step.get('decision_gate'))}"
            )
        executor_name = replay_step["executor"]
        registration = EXECUTORS.get(executor_name)
        if registration is None:
            raise ReplayError(f"step {number} references unknown executor {executor_name!r}")
        mode = registration.mode
        if replay_step["executor_mode"] != mode:
            raise ReplayError(
                f"step {number} executor_mode must be {mode!r} for executor "
                f"{executor_name!r}, got {replay_step['executor_mode']!r}"
            )
        if mode == "native_cli":
            native_steps.append(number)
        else:
            manual_steps.append(number)
        for artifact_id, roles in replay_step["output_files"].items():
            for role, filename in roles.items():
                output_path = _safe_relative(
                    Path("/safe"), filename, f"step {number} {artifact_id}.{role}"
                )
                owner = f"step {number} {artifact_id}.{role}"
                previous_owner = output_path_owners.get(output_path)
                if previous_owner:
                    raise ReplayError(
                        f"duplicate output path {filename!r}: {previous_owner} and {owner}"
                    )
                output_path_owners[output_path] = owner

    if spec_steps[2]["executor"] == "stockbee_fluency_update" and "prices" not in spec["inputs"]:
        raise ReplayError("stockbee_fluency_update requires an offline prices input")

    input_paths: dict[str, Path] = {}
    for name, value in spec["inputs"].items():
        input_path = _safe_relative(spec_path.parent, value, f"inputs.{name}")
        if not input_path.is_file():
            raise ReplayError(f"inputs.{name} does not exist: {input_path}")
        input_paths[name] = input_path

    expected_required = [
        number for number, step in workflow_steps.items() if not bool(step.get("optional"))
    ]
    expected_full = sorted(workflow_steps)
    variants = spec["variants"]
    if variants["required-only"]["enabled_steps"] != expected_required:
        raise ReplayError(
            "required-only enabled_steps must contain exactly the non-optional workflow steps"
        )
    if variants["full-path"]["enabled_steps"] != expected_full:
        raise ReplayError("full-path enabled_steps must contain every workflow step")
    for variant_name in VARIANTS:
        _safe_relative(
            spec_path.parent,
            variants[variant_name]["golden_dir"],
            f"variants.{variant_name}.golden_dir",
        )

    return {
        "workflow_id": workflow_id,
        "variants": list(variants),
        "native_steps": native_steps,
        "manual_contract_steps": manual_steps,
        "inputs": input_paths,
    }


def _canonicalize(value: Any, fixed_timestamp: str, replacements: Mapping[str, str]) -> Any:
    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        for key, child in value.items():
            if key in TIMESTAMP_FIELDS:
                normalized[key] = fixed_timestamp
            else:
                normalized[key] = _canonicalize(child, fixed_timestamp, replacements)
        return normalized
    if isinstance(value, list):
        return [_canonicalize(item, fixed_timestamp, replacements) for item in value]
    if isinstance(value, str):
        result = value
        for source, replacement in replacements.items():
            result = result.replace(source, replacement)
        return result
    return value


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _normalize_json_file(
    source: Path,
    destination: Path,
    fixed_timestamp: str,
    replacements: Mapping[str, str],
) -> None:
    payload = _load_json(source, source.name)
    _write_json(destination, _canonicalize(payload, fixed_timestamp, replacements))


def _normalize_jsonl_file(
    source: Path,
    destination: Path,
    fixed_timestamp: str,
    replacements: Mapping[str, str],
) -> None:
    records = []
    try:
        for line_number, line in enumerate(source.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ReplayError(
                    f"invalid staged model book JSONL at line {line_number}: {exc}"
                ) from exc
    except OSError as exc:
        raise ReplayError(f"cannot read staged model book {source}: {exc}") from exc
    destination.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(
        json.dumps(
            _canonicalize(record, fixed_timestamp, replacements),
            ensure_ascii=False,
            sort_keys=True,
        )
        + "\n"
        for record in records
    )
    destination.write_text(text, encoding="utf-8")


def _scrubbed_environment() -> dict[str, str]:
    return {
        key: value
        for key, value in os.environ.items()
        if not any(marker in key.upper() for marker in SENSITIVE_ENV_MARKERS)
    }


def _run_cli(command: list[str], repo_root: Path) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        cwd=repo_root,
        env=_scrubbed_environment(),
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "no CLI output"
        raise ReplayError(f"native CLI failed ({completed.returncode}): {detail}")
    return completed


def _latest_report(directory: Path, pattern: str) -> Path:
    matches = sorted(directory.glob(pattern))
    if len(matches) != 1:
        raise ReplayError(
            f"expected exactly one report matching {pattern!r} in {directory}, got {len(matches)}"
        )
    return matches[0]


def _artifact_paths(
    stage: Path, output_files: Mapping[str, Mapping[str, str]]
) -> dict[str, dict[str, Any]]:
    artifacts: dict[str, dict[str, Any]] = {}
    for artifact_id, roles in output_files.items():
        artifacts[artifact_id] = {
            "files": {role: str((stage / filename).resolve()) for role, filename in roles.items()}
        }
    return artifacts


def _validate_artifact_files(
    stage: Path,
    artifacts: Mapping[str, dict[str, Any]],
    label: str,
) -> None:
    stage_root = stage.resolve()
    seen: dict[Path, str] = {}
    for artifact_id, bundle in artifacts.items():
        files = bundle.get("files") if isinstance(bundle, dict) else None
        if not isinstance(files, dict) or not files:
            raise ReplayError(f"{label} artifact {artifact_id!r} has no declared files")
        for role, raw_path in files.items():
            path = Path(raw_path).resolve()
            try:
                path.relative_to(stage_root)
            except ValueError as exc:
                raise ReplayError(
                    f"{label} artifact {artifact_id}.{role} escapes staging: {path}"
                ) from exc
            if not path.is_file():
                raise ReplayError(
                    f"{label} artifact {artifact_id}.{role} is a missing staged file: {path}"
                )
            previous = seen.get(path)
            if previous:
                raise ReplayError(
                    f"{label} has duplicate staged file {path.name!r}: "
                    f"{previous} and {artifact_id}.{role}"
                )
            seen[path] = f"{artifact_id}.{role}"


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
    output.write_text(_dump_yaml_with_digest_allowlist(payload), encoding="utf-8")
    return artifacts


EXECUTORS: dict[str, ExecutorRegistration] = {
    "stockbee_fluency_ingest": ExecutorRegistration("native_cli", _stockbee_ingest),
    "stockbee_fluency_update": ExecutorRegistration("native_cli", _stockbee_update),
    "stockbee_fluency_summarize": ExecutorRegistration("native_cli", _stockbee_summarize),
    "manual_lessons_log": ExecutorRegistration("manual_contract", _manual_lessons),
}


def _prompt_text(workflow: Mapping[str, Any], variant: str) -> str:
    optional_text = (
        "Skip every optional step."
        if variant == "required-only"
        else "Run the optional human-approved lessons step after reviewing the cohort evidence."
    )
    return (
        f"# Prompt: {variant} {workflow['id']} replay\n\n"
        "Replay this workflow with the bundled fictional input data. "
        "This is not investment advice and must not submit orders or call live APIs.\n\n"
        f"{optional_text}\n"
    )


def _write_manifest(
    stage: Path,
    workflow: Mapping[str, Any],
    variant: str,
    report: Mapping[str, Any],
    artifacts: Mapping[str, dict[str, Any]],
) -> None:
    artifact_contract = {item["id"]: item for item in workflow["artifacts"]}
    step_contract = {int(item["step"]): item for item in workflow["steps"]}
    entries = []
    for artifact_id, bundle in artifacts.items():
        contract = artifact_contract[artifact_id]
        step_number = int(contract["produced_by_step"])
        entries.append(
            {
                "step": step_number,
                "artifact_id": artifact_id,
                "skill": step_contract[step_number]["skill"],
                "execution_mode": next(
                    item["executor_mode"] for item in report["steps"] if item["step"] == step_number
                ),
                "files": {role: Path(path).name for role, path in bundle["files"].items()},
            }
        )
    entries.sort(key=lambda item: (item["step"], item["artifact_id"]))
    enabled = {item["step"] for item in report["steps"]}
    skipped = [
        {
            "step": int(step["step"]),
            "skill": step["skill"],
            "reason": "required-only executable replay",
        }
        for step in workflow["steps"]
        if step.get("optional") and int(step["step"]) not in enabled
    ]
    payload = {
        "workflow_id": workflow["id"],
        "sample_type": variant,
        "illustrative": True,
        "generated_by": "scripts/workflow_replay.py generate",
        "prompt": "prompt.md",
        "network_policy": report["network_policy"],
        "optional_steps_skipped": skipped,
        "artifacts": entries,
    }
    (stage / "manifest.yaml").write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    (stage / "prompt.md").write_text(_prompt_text(workflow, variant), encoding="utf-8")


def _cleanup_backup(path: Path) -> None:
    shutil.rmtree(path)


def _publish_tree(stage: Path, destination: Path) -> None:
    destination = destination.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    candidate = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.candidate-", dir=destination.parent)
    )
    backup_root = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.backup-", dir=destination.parent)
    )
    backup = backup_root / "previous"
    committed = False
    try:
        shutil.copytree(stage, candidate, dirs_exist_ok=True)
        had_destination = destination.exists()
        if had_destination:
            os.replace(destination, backup)
        try:
            os.replace(candidate, destination)
        except Exception:
            if had_destination and backup.exists() and not destination.exists():
                os.replace(backup, destination)
            raise
        committed = True
    finally:
        if candidate.exists():
            shutil.rmtree(candidate)
        if committed:
            try:
                _cleanup_backup(backup_root)
            except OSError:
                # Publication already committed. Retain the uniquely named
                # backup for manual cleanup rather than report a false failure.
                pass
        elif backup_root.exists() and not backup.exists():
            shutil.rmtree(backup_root)


def execute_replay(
    repo_root: Path,
    spec_path: Path,
    variant: str,
    output_dir: Path,
    *,
    input_overrides: Mapping[str, Path] | None = None,
    before_step: Callable[[int, dict[str, dict[str, Any]]], None] | None = None,
    after_step: Callable[[int, dict[str, dict[str, Any]]], None] | None = None,
) -> dict[str, Any]:
    validation = validate_spec(repo_root, spec_path)
    if variant not in VARIANTS:
        raise ReplayError(f"unknown replay variant: {variant}")
    spec = load_yaml(spec_path)
    workflow = load_yaml(repo_root / "workflows" / f"{spec['workflow_id']}.yaml")
    workflow_steps = {int(item["step"]): item for item in workflow["steps"]}
    spec_steps = {int(item["step"]): item for item in spec["steps"]}
    inputs = dict(validation["inputs"])
    for name, path in (input_overrides or {}).items():
        if name not in inputs:
            raise ReplayError(f"unknown input override: {name}")
        inputs[name] = Path(path).resolve()

    completed_steps: list[int] = []
    artifacts: dict[str, dict[str, Any]] = {}
    step_reports: list[dict[str, Any]] = []
    status = "completed"
    with tempfile.TemporaryDirectory(prefix="workflow-replay-") as temp_name:
        temp = Path(temp_name)
        stage = temp / "published"
        stage.mkdir()
        try:
            for number in spec["variants"][variant]["enabled_steps"]:
                workflow_step = workflow_steps[number]
                replay_step = spec_steps[number]
                if before_step:
                    before_step(number, artifacts)
                _validate_artifact_files(stage, artifacts, "artifact store")
                consumed: dict[str, dict[str, Any]] = {}
                for artifact_id in workflow_step.get("consumes") or []:
                    if artifact_id in artifacts:
                        consumed[artifact_id] = artifacts[artifact_id]
                        continue
                    contract = next(
                        item for item in workflow["artifacts"] if item["id"] == artifact_id
                    )
                    producer = workflow_steps[int(contract["produced_by_step"])]
                    if not producer.get("optional"):
                        raise ReplayError(
                            f"step {number} missing required consumed artifact {artifact_id!r}",
                            completed_steps,
                        )
                executor_name = replay_step["executor"]
                registration = EXECUTORS.get(executor_name)
                if registration is None:
                    raise ReplayError(f"unknown executor {executor_name!r}", completed_steps)
                step_work = temp / "work" / f"step-{number}"
                step_work.mkdir(parents=True)
                produced = registration.run(
                    repo_root,
                    spec,
                    replay_step,
                    inputs,
                    consumed,
                    step_work,
                    stage,
                )
                if set(produced) != set(workflow_step.get("produces") or []):
                    raise ReplayError(
                        f"step {number} executor produced {sorted(produced)}, expected "
                        f"{sorted(workflow_step.get('produces') or [])}",
                        completed_steps,
                    )
                candidate_artifacts = dict(artifacts)
                candidate_artifacts.update(produced)
                _validate_artifact_files(stage, candidate_artifacts, f"step {number} output")
                artifacts = candidate_artifacts
                completed_steps.append(number)
                step_reports.append(
                    {
                        "step": number,
                        "skill": workflow_step["skill"],
                        "executor": executor_name,
                        "executor_mode": registration.mode,
                        "gate_policy": replay_step["gate_policy"],
                        "consumed": sorted(consumed),
                        "produced": sorted(produced),
                    }
                )
                if after_step:
                    after_step(number, artifacts)
                if replay_step["gate_policy"] == "halt":
                    status = "halted"
                    break

            report = {
                "schema_version": 1,
                "workflow_id": spec["workflow_id"],
                "variant": variant,
                "status": status,
                "network_policy": "offline-input-required",
                "steps": step_reports,
                "artifact_ids": sorted(artifacts),
            }
            _write_manifest(stage, workflow, variant, report, artifacts)
            _publish_tree(stage, output_dir)
            return report
        except ReplayError as exc:
            if not exc.completed_steps:
                exc.completed_steps = list(completed_steps)
            raise
        except Exception as exc:
            raise ReplayError(f"replay failed: {exc}", completed_steps) from exc


def compare_trees(actual: Path, expected: Path) -> list[str]:
    actual_files = {
        path.relative_to(actual).as_posix(): path for path in actual.rglob("*") if path.is_file()
    }
    expected_files = {
        path.relative_to(expected).as_posix(): path
        for path in expected.rglob("*")
        if path.is_file()
    }
    differences = []
    for name in sorted(set(actual_files) - set(expected_files)):
        differences.append(f"unexpected generated file: {name}")
    for name in sorted(set(expected_files) - set(actual_files)):
        differences.append(f"missing generated file: {name}")
    for name in sorted(set(actual_files) & set(expected_files)):
        if actual_files[name].read_bytes() != expected_files[name].read_bytes():
            differences.append(f"content drift: {name}")
    return differences


def _covered_specs(coverage_path: Path) -> list[tuple[str, Path, Mapping[str, Any]]]:
    coverage = load_yaml(coverage_path)
    result = []
    for workflow_id, entry in sorted((coverage.get("covered") or {}).items()):
        result.append((workflow_id, (coverage_path.parent / entry["spec"]).resolve(), entry))
    return result


def check_goldens(repo_root: Path, coverage_path: Path, report_path: Path | None) -> list[str]:
    rows = []
    all_differences: list[str] = []
    try:
        validate_coverage(repo_root, coverage_path)
        covered_specs = _covered_specs(coverage_path)
        with tempfile.TemporaryDirectory(prefix="workflow-replay-check-") as temp_name:
            temp = Path(temp_name)
            for workflow_id, spec_path, entry in covered_specs:
                spec = load_yaml(spec_path)
                for variant in entry["variants"]:
                    generated = temp / workflow_id / variant
                    try:
                        execution = execute_replay(repo_root, spec_path, variant, generated)
                        golden = (
                            spec_path.parent / spec["variants"][variant]["golden_dir"]
                        ).resolve()
                        differences = compare_trees(generated, golden)
                        rows.append(
                            {
                                "workflow_id": workflow_id,
                                "variant": variant,
                                "status": "pass" if not differences else "drift",
                                "execution": execution,
                                "differences": differences,
                            }
                        )
                        all_differences.extend(
                            f"{workflow_id}/{variant}: {difference}" for difference in differences
                        )
                    except Exception as exc:
                        difference = f"{workflow_id}/{variant}: execution error: {exc}"
                        all_differences.append(difference)
                        rows.append(
                            {
                                "workflow_id": workflow_id,
                                "variant": variant,
                                "status": "error",
                                "error": str(exc),
                                "completed_steps": list(getattr(exc, "completed_steps", []) or []),
                            }
                        )
    except Exception as exc:
        all_differences.append(f"coverage validation error: {exc}")
        rows.append(
            {
                "workflow_id": None,
                "variant": None,
                "status": "error",
                "stage": "validation",
                "error": str(exc),
                "completed_steps": list(getattr(exc, "completed_steps", []) or []),
            }
        )
    finally:
        if report_path:
            _write_json(
                report_path,
                {"schema_version": 1, "phase": 1, "issue": 294, "rows": rows},
            )
    return all_differences


def generate_goldens(repo_root: Path, coverage_path: Path) -> None:
    validate_coverage(repo_root, coverage_path)
    for _workflow_id, spec_path, entry in _covered_specs(coverage_path):
        spec = load_yaml(spec_path)
        for variant in entry["variants"]:
            destination = spec_path.parent / spec["variants"][variant]["golden_dir"]
            execute_replay(repo_root, spec_path, variant, destination)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate", help="Validate coverage and replay specs")
    validate.add_argument("--coverage", type=Path, default=DEFAULT_COVERAGE)

    run = subparsers.add_parser("run", help="Run one replay variant")
    run.add_argument("--spec", type=Path, required=True)
    run.add_argument("--variant", choices=VARIANTS, required=True)
    run.add_argument("--output-dir", type=Path, required=True)

    check = subparsers.add_parser("check", help="Regenerate in temp and compare goldens")
    check.add_argument("--coverage", type=Path, default=DEFAULT_COVERAGE)
    check.add_argument("--report", type=Path)

    generate = subparsers.add_parser(
        "generate", help="Regenerate committed example goldens from source inputs"
    )
    generate.add_argument("--coverage", type=Path, default=DEFAULT_COVERAGE)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "validate":
        summary = validate_coverage(REPO_ROOT, args.coverage.resolve())
        print(json.dumps(summary, indent=2))
        return 0
    if args.command == "run":
        report = execute_replay(
            REPO_ROOT, args.spec.resolve(), args.variant, args.output_dir.resolve()
        )
        print(json.dumps(report, indent=2))
        return 0
    if args.command == "check":
        differences = check_goldens(
            REPO_ROOT,
            args.coverage.resolve(),
            args.report.resolve() if args.report else None,
        )
        if differences:
            print("Workflow replay drift detected:", file=sys.stderr)
            for difference in differences:
                print(f"- {difference}", file=sys.stderr)
            return 1
        print("Workflow replay goldens are current.")
        return 0
    if args.command == "generate":
        generate_goldens(REPO_ROOT, args.coverage.resolve())
        print("Workflow replay goldens regenerated.")
        return 0
    raise AssertionError(f"unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
