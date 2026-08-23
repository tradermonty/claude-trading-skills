#!/usr/bin/env python3
"""Deterministic workflow contract replay harness (Issue #294, coverage 4/11).

The harness executes real offline CLIs for the Stockbee fluency, 20% study,
trade-memory, and market-regime workflows. Human decisions and fixture-backed
native API evidence are reported separately from full skill execution. Golden
outputs are comparison targets only and are never used as replay inputs.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.util
import json
import math
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
TWENTY_PCT_LESSONS_SCHEMA = REPO_ROOT / "examples" / "workflows" / "twenty-pct-lessons.schema.json"
VARIANTS = ("required-only", "full-path")

# Coverage 4/11 leaves seven workflows deferred. This frozen baseline prevents a newly
# introduced workflow from being waved through as another deferral.
FROZEN_DEFERRED_WORKFLOWS = frozenset(
    {
        "core-portfolio-weekly",
        "kanchi-dividend-weekly",
        "monthly-performance-review",
        "multi-asset-opportunity-daily",
        "shapiro-contrarian",
        "stockbee-ep-daily",
        "swing-opportunity-daily",
    }
)

MARKET_COMPONENT_CONFIG = {
    "breadth": {
        "input": "market_breadth_components",
        "artifact": "market_breadth_report",
        "skill": "market-breadth-analyzer",
        "components": frozenset(
            {
                "breadth_level_trend",
                "ma_crossover",
                "cycle_position",
                "bearish_signal",
                "historical_percentile",
                "divergence",
            }
        ),
        "warning_flags": frozenset(),
    },
    "uptrend": {
        "input": "market_uptrend_components",
        "artifact": "uptrend_report",
        "skill": "uptrend-analyzer",
        "components": frozenset(
            {
                "market_breadth",
                "sector_participation",
                "sector_rotation",
                "momentum",
                "historical_context",
            }
        ),
        "warning_flags": frozenset({"late_cycle", "high_spread", "divergence"}),
    },
    "top_risk": {
        "input": "market_top_risk_components",
        "artifact": "top_risk_report",
        "skill": "market-top-detector",
        "components": frozenset(
            {
                "distribution_days",
                "leading_stocks",
                "defensive_rotation",
                "breadth_divergence",
                "index_technical",
                "sentiment",
            }
        ),
        "warning_flags": frozenset(),
    },
}

TIMESTAMP_FIELDS = frozenset(
    {"generated_at", "created_at", "updated_at", "last_outcome_update_at", "recorded_at"}
)
SENSITIVE_ENV_MARKERS = ("API_KEY", "TOKEN", "SECRET", "PASSWORD", "PROXY")
DIGEST_ALLOWLIST_KEYS = frozenset(
    {
        "setup_fluency_summary",
        "rule_candidates",
        "twenty_pct_cohort_summary",
        "edge_hints_yaml",
        "closed_thesis_record",
        "realized_returns",
        "native_postmortem_record",
        "coach_report",
        "coach_report_sha256",
        "postmortem_findings",
        "backtest_validation",
    }
)
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
    components: tuple[str, ...] = ()


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
    keys = "|".join(sorted(re.escape(key) for key in DIGEST_ALLOWLIST_KEYS))
    digest_line = re.compile(
        rf"^(\s+(?:{keys}): [0-9a-f]{{64}})$",
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

    if set(deferred) != FROZEN_DEFERRED_WORKFLOWS:
        errors.append(
            "deferred workflows must match the frozen coverage 4/11 deferred set; "
            f"expected {sorted(FROZEN_DEFERRED_WORKFLOWS)}, got {sorted(deferred)}"
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


def _paths_overlap(left: Path, right: Path) -> bool:
    """Return whether two resolved paths are equal or one contains the other."""
    left = left.resolve()
    right = right.resolve()
    return left == right or left in right.parents or right in left.parents


def _validate_golden_dirs(
    spec_path: Path,
    variants: Mapping[str, Any],
    input_paths: Mapping[str, Path],
) -> None:
    """Keep generated trees disjoint from replay sources and from each other."""
    spec_path = spec_path.resolve()
    spec_dir = spec_path.parent
    golden_paths: dict[str, Path] = {}
    for variant_name in VARIANTS:
        label = f"variants.{variant_name}.golden_dir"
        golden = _safe_relative(spec_dir, variants[variant_name]["golden_dir"], label)
        if golden == spec_dir or _paths_overlap(golden, spec_path):
            raise ReplayError(f"{label} overlaps replay source: {golden}")
        for input_name, input_path in input_paths.items():
            if _paths_overlap(golden, input_path.parent):
                raise ReplayError(
                    f"{label} overlaps replay source inputs.{input_name} parent: "
                    f"{input_path.parent}"
                )
        if golden.exists() and not golden.is_dir():
            raise ReplayError(f"{label} must resolve to a directory: {golden}")
        golden_paths[variant_name] = golden

    required = golden_paths["required-only"]
    full = golden_paths["full-path"]
    if _paths_overlap(required, full):
        raise ReplayError(
            f"variant golden_dir paths overlap: required-only={required}, full-path={full}"
        )


def _validate_runtime_output(
    repo_root: Path,
    spec_path: Path,
    spec: Mapping[str, Any],
    inputs: Mapping[str, Path],
    output_dir: Path,
) -> None:
    """Reject runtime destinations that could replace replay source data."""
    output = output_dir.resolve()
    if output.exists() and not output.is_dir():
        raise ReplayError(f"output_dir must be a directory: {output}")
    protected: dict[str, Path] = {
        "repository root": repo_root.resolve(),
        "replay spec": spec_path.resolve(),
        "replay spec directory": spec_path.resolve().parent,
    }
    for name, path in inputs.items():
        protected[f"inputs.{name} parent"] = path.resolve().parent
    for variant in VARIANTS:
        protected[f"variants.{variant}.golden_dir"] = _safe_relative(
            spec_path.resolve().parent,
            spec["variants"][variant]["golden_dir"],
            f"variants.{variant}.golden_dir",
        )
    for label, path in protected.items():
        if _paths_overlap(output, path):
            raise ReplayError(f"output_dir overlaps protected {label}: {path}")


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
    native_api_steps: list[int] = []
    manual_steps: list[int] = []
    composite_steps: list[int] = []
    executor_components: dict[int, list[str]] = {}
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
        configured_components = tuple(replay_step.get("executor_components") or [])
        if configured_components != registration.components:
            raise ReplayError(
                f"step {number} executor_components must be "
                f"{list(registration.components)!r} for executor {executor_name!r}, "
                f"got {list(configured_components)!r}"
            )
        if mode == "native_cli":
            native_steps.append(number)
        elif mode == "native_api":
            native_api_steps.append(number)
        elif mode == "manual_contract":
            manual_steps.append(number)
        elif mode == "composite":
            composite_steps.append(number)
            executor_components[number] = list(registration.components)
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

    input_paths: dict[str, Path] = {}
    for name, value in spec["inputs"].items():
        input_path = _safe_relative(spec_path.parent, value, f"inputs.{name}")
        if not input_path.is_file():
            raise ReplayError(f"inputs.{name} does not exist: {input_path}")
        input_paths[name] = input_path

    executor_required_inputs = {
        "stockbee_fluency_ingest": {"screener"},
        "stockbee_fluency_update": {"prices"},
        "manual_lessons_log": {"accepted_lessons"},
        "twenty_pct_scan": {"prices"},
        "twenty_pct_enrich": {"news"},
        "twenty_pct_update_outcomes": {"prices"},
        "manual_twenty_pct_lessons": {"accepted_lessons"},
        "trade_memory_close": {"active_thesis", "close_instruction"},
        "trade_memory_postmortem": {"realized_returns", "root_cause_decision"},
        "trade_memory_coach": {"coach_decision"},
        "trade_memory_backtest": {"backtest_metrics"},
        "trade_memory_lessons": {"lessons_required", "lessons_full"},
        "market_regime_breadth": {"market_breadth_components"},
        "market_regime_uptrend": {"market_uptrend_components"},
        "market_regime_top_risk": {"market_top_risk_components"},
        "market_regime_exposure": {
            "market_breadth_components",
            "market_uptrend_components",
            "market_top_risk_components",
        },
    }
    for number, replay_step in spec_steps.items():
        required_inputs = executor_required_inputs.get(replay_step["executor"], set())
        missing_inputs = required_inputs - set(input_paths)
        if missing_inputs:
            raise ReplayError(
                f"step {number} executor {replay_step['executor']!r} requires offline "
                f"inputs {sorted(missing_inputs)}"
            )

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
    _validate_golden_dirs(spec_path, variants, input_paths)

    return {
        "workflow_id": workflow_id,
        "variants": list(variants),
        "native_steps": native_steps,
        "native_api_steps": native_api_steps,
        "manual_contract_steps": manual_steps,
        "composite_steps": composite_steps,
        "executor_components": executor_components,
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


def _artifact_file_digests(
    artifacts: Mapping[str, dict[str, Any]],
) -> dict[str, str]:
    """Seal every declared artifact file by its stable artifact-role identity."""
    digests: dict[str, str] = {}
    for artifact_id, bundle in artifacts.items():
        for role, raw_path in bundle["files"].items():
            digests[f"{artifact_id}.{role}"] = _file_sha256(Path(raw_path))
    return digests


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
    output.write_text(_dump_yaml_with_digest_allowlist(payload), encoding="utf-8")
    return artifacts


def _repo_module(repo_root: Path, module_name: str, scripts_dir: Path) -> Any:
    """Import one repository script module without invoking the uv launcher."""
    scripts_text = str(scripts_dir.resolve())
    if scripts_text not in sys.path:
        sys.path.insert(0, scripts_text)
    importlib.invalidate_caches()
    module = importlib.import_module(module_name)
    module_path = Path(module.__file__).resolve()
    if scripts_dir.resolve() not in module_path.parents:
        raise ReplayError(
            f"refusing unexpected {module_name} import outside repository skill: {module_path}"
        )
    return module


def _trader_memory_modules(repo_root: Path) -> tuple[Any, Any]:
    scripts_dir = repo_root / "skills" / "trader-memory-core" / "scripts"
    store = _repo_module(repo_root, "thesis_store", scripts_dir)
    review = _repo_module(repo_root, "thesis_review", scripts_dir)
    return store, review


def _canonical_json_bytes(
    payload: Any,
    fixed_timestamp: str,
    replacements: Mapping[str, str] | None = None,
) -> bytes:
    canonical = _canonicalize(payload, fixed_timestamp, replacements or {})
    return (json.dumps(canonical, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode()


def _payload_sha256(
    payload: Any,
    fixed_timestamp: str,
    replacements: Mapping[str, str] | None = None,
) -> str:
    return hashlib.sha256(_canonical_json_bytes(payload, fixed_timestamp, replacements)).hexdigest()


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _exact_payload_sha256(payload: Any) -> str:
    rendered = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(rendered).hexdigest()


def _write_yaml(path: Path, payload: Any, *, digest_allowlist: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if digest_allowlist:
        text = _dump_yaml_with_digest_allowlist(payload)
    else:
        text = yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)
    path.write_text(text, encoding="utf-8")


def _require_mapping_keys(
    payload: Any,
    *,
    label: str,
    required: set[str],
    optional: set[str] | None = None,
) -> Mapping[str, Any]:
    if not isinstance(payload, dict):
        raise ReplayError(f"{label} must be a mapping")
    missing = required - set(payload)
    unexpected = set(payload) - required - set(optional or set())
    if missing or unexpected:
        raise ReplayError(
            f"invalid {label} keys: missing={sorted(missing)}, unexpected={sorted(unexpected)}"
        )
    return payload


def _require_non_empty_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReplayError(f"{label} must be a non-empty string")
    return value


def _require_finite_number(
    value: Any,
    label: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
    integer: bool = False,
) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ReplayError(f"{label} must be {'an integer' if integer else 'numeric'}")
    if integer and not isinstance(value, int):
        raise ReplayError(f"{label} must be an integer")
    if not math.isfinite(value):
        raise ReplayError(f"{label} must be finite")
    if minimum is not None and value < minimum:
        raise ReplayError(f"{label} must be >= {minimum:g}")
    if maximum is not None and value > maximum:
        raise ReplayError(f"{label} must be <= {maximum:g}")
    return value


def _trade_memory_close(
    repo_root: Path,
    spec: Mapping[str, Any],
    step: Mapping[str, Any],
    inputs: Mapping[str, Path],
    _consumed: Mapping[str, dict[str, Any]],
    work: Path,
    stage: Path,
) -> dict[str, dict[str, Any]]:
    active = load_yaml(inputs["active_thesis"])
    instruction = load_yaml(inputs["close_instruction"])
    instruction = _require_mapping_keys(
        instruction,
        label="close instruction",
        required={"thesis_id", "exit_reason", "actual_price", "actual_date", "event_date"},
    )
    thesis_store, _review = _trader_memory_modules(repo_root)
    try:
        thesis_store._validate_thesis(active)
    except Exception as exc:
        raise ReplayError(f"invalid active thesis: {exc}") from exc
    if active.get("status") != "ACTIVE":
        raise ReplayError("trade-memory close input must have status ACTIVE")
    if instruction["thesis_id"] != active.get("thesis_id"):
        raise ReplayError("close instruction thesis_id does not match active thesis")

    state_dir = work / "trade-memory-state"
    state_dir.mkdir(parents=True)
    source = state_dir / f"{active['thesis_id']}.yaml"
    _write_yaml(source, active)
    script = repo_root / "skills" / "trader-memory-core" / "scripts" / "thesis_store.py"
    _run_cli(
        [
            sys.executable,
            str(script),
            "--state-dir",
            str(state_dir),
            "close",
            str(instruction["thesis_id"]),
            "--exit-reason",
            str(instruction["exit_reason"]),
            "--actual-price",
            str(instruction["actual_price"]),
            "--actual-date",
            str(instruction["actual_date"]),
            "--event-date",
            str(instruction["event_date"]),
        ],
        repo_root,
    )
    closed = load_yaml(source)
    try:
        thesis_store._validate_thesis(closed)
    except Exception as exc:
        raise ReplayError(f"native close produced invalid thesis: {exc}") from exc
    if closed.get("status") != "CLOSED":
        raise ReplayError("native close did not produce CLOSED thesis")

    artifacts = _artifact_paths(stage, step["output_files"])
    output = Path(artifacts["closed_thesis_record"]["files"]["canonical"])
    canonical = _canonicalize(closed, spec["fixed_timestamp"], {str(state_dir): "$STATE"})
    canonical["created_at"] = closed["created_at"]
    try:
        thesis_store._validate_thesis(canonical)
    except Exception as exc:
        raise ReplayError(f"normalized close artifact is invalid: {exc}") from exc
    _write_yaml(output, canonical)
    return artifacts


def _trade_memory_postmortem(
    repo_root: Path,
    spec: Mapping[str, Any],
    step: Mapping[str, Any],
    inputs: Mapping[str, Path],
    consumed: Mapping[str, dict[str, Any]],
    _work: Path,
    stage: Path,
) -> dict[str, dict[str, Any]]:
    if set(consumed) != {"closed_thesis_record"}:
        raise ReplayError("trade-memory postmortem requires closed_thesis_record")
    closed_path = Path(consumed["closed_thesis_record"]["files"]["canonical"])
    closed = load_yaml(closed_path)
    realized = _load_json(inputs["realized_returns"], "realized returns")
    realized = _require_mapping_keys(
        realized,
        label="realized returns",
        required={"schema_version", "trade_direction", "returns", "regime_at_exit"},
    )
    if realized["schema_version"] != 1 or realized["trade_direction"] not in {"LONG", "SHORT"}:
        raise ReplayError("invalid realized returns contract")
    returns = realized["returns"]
    if not isinstance(returns, dict) or set(returns) != {"5d", "20d"}:
        raise ReplayError("realized returns must contain exactly 5d and 20d")
    for horizon, value in returns.items():
        _require_finite_number(value, f"realized returns {horizon}")
    _require_non_empty_string(realized["regime_at_exit"], "realized returns regime_at_exit")

    position = closed.get("position") or {}
    expected_direction = (
        position.get("direction") if position.get("asset_type") == "futures" else "LONG"
    )
    if realized["trade_direction"] != expected_direction:
        raise ReplayError("realized returns trade_direction does not match thesis position")
    if closed.get("status") != "CLOSED":
        raise ReplayError("postmortem input thesis must be CLOSED")
    entry = closed.get("entry") or {}
    exit_data = closed.get("exit") or {}
    signal = {
        "signal_id": closed["thesis_id"],
        "ticker": closed["ticker"],
        "signal_date": str(entry["actual_date"])[:10],
        "predicted_direction": realized["trade_direction"],
        "source_skill": closed["origin"]["skill"],
        "entry_price": entry["actual_price"],
        "regime": (closed.get("market_context") or {}).get("regime") or "UNKNOWN",
    }
    recorder = _repo_module(
        repo_root,
        "postmortem_recorder",
        repo_root / "skills" / "signal-postmortem" / "scripts",
    )
    native = recorder.create_postmortem_record(
        signal,
        returns,
        exit_data["actual_price"],
        str(exit_data["actual_date"])[:10],
        regime_at_exit=str(realized["regime_at_exit"]),
    )
    native = _canonicalize(native, spec["fixed_timestamp"], {})

    root_decision = load_yaml(inputs["root_cause_decision"])
    root_decision = _require_mapping_keys(
        root_decision,
        label="root cause decision",
        required={
            "human_approved",
            "thesis_id",
            "expected_native_classification",
            "expected_source_sha256",
            "classification",
            "summary",
        },
    )
    if root_decision["human_approved"] is not True:
        raise ReplayError("root cause decision requires human_approved: true")
    if root_decision["thesis_id"] != closed["thesis_id"]:
        raise ReplayError("root cause decision thesis_id mismatch")
    if root_decision["expected_native_classification"] != native["outcome_category"]:
        raise ReplayError("root cause decision native classification mismatch")
    if root_decision["classification"] not in {
        "thesis_quality",
        "execution",
        "market_environment",
        "randomness",
    }:
        raise ReplayError("root cause decision classification is invalid")
    _require_non_empty_string(root_decision["summary"], "root cause decision summary")
    expected_hashes = root_decision["expected_source_sha256"]
    actual_hashes = {
        "closed_thesis_record": _file_sha256(closed_path),
        "realized_returns": _payload_sha256(realized, spec["fixed_timestamp"]),
        "native_postmortem_record": _payload_sha256(native, spec["fixed_timestamp"]),
    }
    if expected_hashes != actual_hashes:
        raise ReplayError(
            f"root cause decision source_sha256 mismatch: expected {expected_hashes}, "
            f"actual {actual_hashes}"
        )

    payload = {
        "schema_version": 1,
        "source_snapshot": {"closed_thesis_record": closed},
        "native_postmortem": native,
        "manual_root_cause": {
            "human_approved": True,
            "classification": root_decision["classification"],
            "summary": root_decision["summary"],
        },
        "provenance": {
            "execution_mode": "composite",
            "components": ["native_api", "manual_contract"],
            "native_component": "signal-postmortem.create_postmortem_record",
            "native_classification_basis": "fixture_supplied_realized_returns",
            "source_sha256": actual_hashes,
            "source_snapshot_sha256": {"closed_thesis_record": _exact_payload_sha256(closed)},
            "limitation": "Root cause is a human-approved fixture decision, not native inference.",
        },
    }
    artifacts = _artifact_paths(stage, step["output_files"])
    _write_json(Path(artifacts["postmortem_findings"]["files"]["canonical"]), payload)
    return artifacts


def _trade_memory_coach(
    repo_root: Path,
    spec: Mapping[str, Any],
    step: Mapping[str, Any],
    inputs: Mapping[str, Path],
    consumed: Mapping[str, dict[str, Any]],
    work: Path,
    stage: Path,
) -> dict[str, dict[str, Any]]:
    if set(consumed) != {"closed_thesis_record", "postmortem_findings"}:
        raise ReplayError("trade-memory coach requires closed thesis and postmortem")
    closed = load_yaml(Path(consumed["closed_thesis_record"]["files"]["canonical"]))
    postmortem = _load_json(
        Path(consumed["postmortem_findings"]["files"]["canonical"]), "postmortem findings"
    )
    created_at = datetime.fromisoformat(str(closed["created_at"]).replace("Z", "+00:00"))
    entered_at = datetime.fromisoformat(str(closed["entry"]["actual_date"]).replace("Z", "+00:00"))
    coach_input = {
        "review_id": "trade-memory-loop-fictional-exmpl",
        "review_type": "single_trade",
        "trade_id": closed["thesis_id"],
        "outcome": postmortem["native_postmortem"]["outcome_category"],
        "planned": {
            "thesis": closed["thesis_statement"],
            "thesis_recorded_before_entry": created_at <= entered_at,
            "entry_price": closed["entry"]["actual_price"],
            "stop_price": closed["exit"]["stop_loss"],
            "market_regime": closed["market_context"]["regime"],
        },
        "actual": {
            "entry_price": closed["entry"]["actual_price"],
            "exit_price": closed["exit"]["actual_price"],
        },
        "postmortem": {
            "root_cause": postmortem["manual_root_cause"]["classification"],
            "root_cause_notes": postmortem["manual_root_cause"]["summary"],
        },
    }
    input_path = work / "coach-input.json"
    _write_json(input_path, coach_input)
    reports = work / "reports"
    script = (
        repo_root / "skills" / "trade-performance-coach" / "scripts" / "review_trade_performance.py"
    )
    _run_cli(
        [
            sys.executable,
            str(script),
            "--input",
            str(input_path),
            "--output-dir",
            str(reports),
            "--json-name",
            "coach.json",
        ],
        repo_root,
    )
    coach = _load_json(reports / "coach.json", "coach report")
    coach = _canonicalize(
        coach,
        spec["fixed_timestamp"],
        {str(input_path): "$INPUT/coach-input.json"},
    )

    decision = load_yaml(inputs["coach_decision"])
    decision = _require_mapping_keys(
        decision,
        label="coach decision",
        required={"human_approved", "action", "expected_source_sha256", "accepted_rules"},
    )
    coach_sha = _payload_sha256(coach, spec["fixed_timestamp"])
    if decision["human_approved"] is not True:
        raise ReplayError("coach decision requires human_approved: true")
    if decision["expected_source_sha256"] != {"coach_report": coach_sha}:
        raise ReplayError(
            f"coach decision source_sha256 mismatch: expected "
            f"{decision['expected_source_sha256']}, actual {{'coach_report': {coach_sha!r}}}"
        )
    if decision["action"] not in coach["human_decision_gate"]["allowed_actions"]:
        raise ReplayError("coach decision action is not allowed by native report")
    accepted_rules = decision["accepted_rules"]
    if not isinstance(accepted_rules, list) or not all(
        isinstance(rule, str) and rule.strip() for rule in accepted_rules
    ):
        raise ReplayError("coach decision accepted_rules must be a list of non-empty strings")
    native_rules = {
        item["rule"]
        for item in coach["next_session_operating_rules"]
        if isinstance(item, Mapping) and isinstance(item.get("rule"), str)
    }
    action = decision["action"]
    if action == "accept_rules" and (
        not accepted_rules or not set(accepted_rules).issubset(native_rules)
    ):
        raise ReplayError(
            "coach decision accepted_rules must come from the native coach report; "
            f"available={sorted(native_rules)}"
        )
    if action in {"defer", "journal_only"} and accepted_rules:
        raise ReplayError(f"coach decision action {action!r} cannot accept rules")
    if action == "modify_rules" and not accepted_rules:
        raise ReplayError("coach decision action 'modify_rules' requires modified rules")

    artifacts = _artifact_paths(stage, step["output_files"])
    coach_out = Path(artifacts["performance_coach_report"]["files"]["canonical"])
    _write_json(coach_out, coach)
    rules = {
        "human_approved": True,
        "action": decision["action"],
        "accepted_rules": accepted_rules,
        "provenance": {
            "execution_mode": "manual_contract",
            "coach_report_sha256": _file_sha256(coach_out),
            "native_coach_default_action": coach["human_decision_gate"]["default_action"],
        },
    }
    _write_yaml(
        Path(artifacts["next_session_operating_rules"]["files"]["canonical"]),
        rules,
        digest_allowlist=True,
    )
    return artifacts


def _trade_memory_backtest(
    repo_root: Path,
    spec: Mapping[str, Any],
    step: Mapping[str, Any],
    inputs: Mapping[str, Path],
    consumed: Mapping[str, dict[str, Any]],
    work: Path,
    stage: Path,
) -> dict[str, dict[str, Any]]:
    if set(consumed) != {"postmortem_findings"}:
        raise ReplayError("trade-memory backtest evaluation requires postmortem_findings")
    metrics = _load_json(inputs["backtest_metrics"], "backtest metrics")
    required = {
        "total_trades",
        "win_rate",
        "avg_win_pct",
        "avg_loss_pct",
        "max_drawdown_pct",
        "years_tested",
        "num_parameters",
        "slippage_tested",
    }
    metrics = _require_mapping_keys(metrics, label="backtest metrics", required=required)
    _require_finite_number(
        metrics["total_trades"], "backtest total_trades", minimum=0, integer=True
    )
    _require_finite_number(metrics["win_rate"], "backtest win_rate", minimum=0, maximum=100)
    _require_finite_number(metrics["avg_win_pct"], "backtest avg_win_pct", minimum=0)
    _require_finite_number(metrics["avg_loss_pct"], "backtest avg_loss_pct", minimum=0)
    _require_finite_number(
        metrics["max_drawdown_pct"], "backtest max_drawdown_pct", minimum=0, maximum=100
    )
    _require_finite_number(
        metrics["years_tested"], "backtest years_tested", minimum=0, integer=True
    )
    _require_finite_number(
        metrics["num_parameters"], "backtest num_parameters", minimum=0, integer=True
    )
    reports = work / "reports"
    script = repo_root / "skills" / "backtest-expert" / "scripts" / "evaluate_backtest.py"
    command = [
        sys.executable,
        str(script),
        "--total-trades",
        str(metrics["total_trades"]),
        "--win-rate",
        str(metrics["win_rate"]),
        "--avg-win-pct",
        str(metrics["avg_win_pct"]),
        "--avg-loss-pct",
        str(metrics["avg_loss_pct"]),
        "--max-drawdown-pct",
        str(metrics["max_drawdown_pct"]),
        "--years-tested",
        str(metrics["years_tested"]),
        "--num-parameters",
        str(metrics["num_parameters"]),
        "--output-dir",
        str(reports),
    ]
    if metrics["slippage_tested"] is True:
        command.append("--slippage-tested")
    elif metrics["slippage_tested"] is not False:
        raise ReplayError("backtest metrics slippage_tested must be boolean")
    _run_cli(command, repo_root)
    result_path = _latest_report(reports, "backtest_eval_*.json")
    result = _load_json(result_path, "backtest evaluation")
    postmortem_path = Path(consumed["postmortem_findings"]["files"]["canonical"])
    result["provenance"] = {
        "execution": "native_cli_evaluated_fixture_metrics",
        "metrics_source": "bundled fictional aggregate metrics",
        "adapter_bound_source_sha256": {"postmortem_source_sha256": _file_sha256(postmortem_path)},
        "limitation": (
            "The native CLI evaluated supplied aggregate metrics; it did not run a strategy "
            "backtest or consume the postmortem."
        ),
    }
    artifacts = _artifact_paths(stage, step["output_files"])
    _write_json(Path(artifacts["backtest_validation"]["files"]["canonical"]), result)
    return artifacts


def _without_lesson_side_effects(thesis: Mapping[str, Any]) -> dict[str, Any]:
    clone = json.loads(json.dumps(thesis))
    clone.pop("updated_at", None)
    outcome = clone.get("outcome") or {}
    for key in ("lessons_learned", "mae_pct", "mfe_pct", "mae_mfe_source"):
        outcome.pop(key, None)
    return clone


def _trade_memory_lessons(
    repo_root: Path,
    spec: Mapping[str, Any],
    step: Mapping[str, Any],
    inputs: Mapping[str, Path],
    consumed: Mapping[str, dict[str, Any]],
    work: Path,
    stage: Path,
) -> dict[str, dict[str, Any]]:
    if "postmortem_findings" not in consumed:
        raise ReplayError("trade-memory lessons requires postmortem_findings")
    unexpected = set(consumed) - {"postmortem_findings", "backtest_validation"}
    if unexpected:
        raise ReplayError(
            f"trade-memory lessons received unexpected artifacts: {sorted(unexpected)}"
        )
    variant = "full-path" if "backtest_validation" in consumed else "required-only"
    decision_key = "lessons_full" if variant == "full-path" else "lessons_required"
    decision = load_yaml(inputs[decision_key])
    decision = _require_mapping_keys(
        decision,
        label="lessons decision",
        required={
            "human_approved",
            "variant",
            "source_artifacts",
            "source_sha256",
            "decision",
            "lesson_text",
        },
    )
    if decision["human_approved"] is not True:
        raise ReplayError("lessons decision requires human_approved: true")
    if decision["variant"] != variant:
        raise ReplayError(
            f"lessons decision variant {decision['variant']!r} does not match {variant!r}"
        )
    expected_artifacts = ["postmortem_findings"]
    if variant == "full-path":
        expected_artifacts.append("backtest_validation")
    if decision["source_artifacts"] != expected_artifacts:
        raise ReplayError("lessons decision source_artifacts do not match executed variant")
    source_hashes = {
        artifact_id: _file_sha256(Path(consumed[artifact_id]["files"]["canonical"]))
        for artifact_id in expected_artifacts
    }
    if decision["source_sha256"] != source_hashes:
        raise ReplayError(
            f"lessons decision source_sha256 mismatch: expected "
            f"{decision['source_sha256']}, actual {source_hashes}"
        )
    if decision["decision"] not in {"journal_only", "research_rule"}:
        raise ReplayError("unsupported lessons decision")
    lesson_text = decision["lesson_text"]
    if not isinstance(lesson_text, str) or not lesson_text.strip():
        raise ReplayError("lessons decision lesson_text is required")

    thesis_store, thesis_review = _trader_memory_modules(repo_root)
    postmortem = _load_json(
        Path(consumed["postmortem_findings"]["files"]["canonical"]), "postmortem findings"
    )
    snapshot = _require_mapping_keys(
        postmortem.get("source_snapshot"),
        label="postmortem source_snapshot",
        required={"closed_thesis_record"},
    )
    closed = snapshot["closed_thesis_record"]
    if not isinstance(closed, dict):
        raise ReplayError("postmortem closed thesis snapshot must be a mapping")
    try:
        thesis_store._validate_thesis(closed)
    except Exception as exc:
        raise ReplayError(f"postmortem closed thesis snapshot is invalid: {exc}") from exc
    expected_closed_sha = (
        (postmortem.get("provenance") or {})
        .get("source_snapshot_sha256", {})
        .get("closed_thesis_record")
    )
    if _exact_payload_sha256(closed) != expected_closed_sha:
        raise ReplayError("postmortem closed thesis snapshot SHA-256 mismatch")
    thesis_id = postmortem["native_postmortem"]["signal_id"]
    if closed.get("thesis_id") != thesis_id:
        raise ReplayError("postmortem closed thesis snapshot thesis_id mismatch")
    state_dir = work / "trade-memory-state"
    state_dir.mkdir(parents=True)
    state_path = state_dir / f"{thesis_id}.yaml"
    _write_yaml(state_path, closed)
    try:
        thesis_store.update(
            state_dir,
            closed["thesis_id"],
            {"outcome": {"lessons_learned": lesson_text}},
        )
        journal_dir = work / "journal"
        journal_path = Path(
            thesis_review.generate_postmortem(
                closed["thesis_id"],
                str(state_dir),
                price_adapter=None,
                journal_dir=str(journal_dir),
            )
        )
        updated = load_yaml(state_path)
    except Exception as exc:
        raise ReplayError(f"trade-memory lessons native API failed: {exc}") from exc
    if _without_lesson_side_effects(updated) != _without_lesson_side_effects(closed):
        raise ReplayError("trade-memory lessons changed non-target thesis state")
    if updated["outcome"]["lessons_learned"] != lesson_text:
        raise ReplayError("trade-memory lessons did not persist approved text")

    artifacts = _artifact_paths(stage, step["output_files"])
    canonical = Path(artifacts["lessons_log_entry"]["files"]["canonical"])
    canonical.parent.mkdir(parents=True, exist_ok=True)
    canonical.write_bytes(journal_path.read_bytes())
    normalized = _canonicalize(updated, spec["fixed_timestamp"], {str(state_dir): "$STATE"})
    normalized["created_at"] = closed["created_at"]
    try:
        thesis_store._validate_thesis(normalized)
    except Exception as exc:
        raise ReplayError(f"normalized lessons state is invalid: {exc}") from exc
    _write_yaml(Path(artifacts["lessons_log_entry"]["files"]["state"]), normalized)
    provenance = {
        "human_approved": True,
        "variant": variant,
        "decision": decision["decision"],
        "source_sha256": source_hashes,
        "execution_mode": "composite",
        "components": ["native_api", "manual_contract"],
        "atomicity_scope": {
            "individual_state_files": "atomic replace by trader-memory-core",
            "temporary_state": "discarded on replay failure",
            "published_tree": "transactional replacement by workflow replay harness",
        },
    }
    _write_yaml(
        Path(artifacts["lessons_log_entry"]["files"]["provenance"]),
        provenance,
        digest_allowlist=True,
    )
    return artifacts


def _load_module_from_path(path: Path, label: str) -> Any:
    """Load same-named skill modules under a path-derived collision-free name."""
    path = path.resolve()
    if not path.is_file():
        raise ReplayError(f"missing native module for {label}: {path}")
    digest = hashlib.sha256(str(path).encode()).hexdigest()[:16]
    module_name = f"_workflow_replay_{re.sub(r'[^a-z0-9]+', '_', label.lower())}_{digest}"
    module_spec = importlib.util.spec_from_file_location(module_name, path)
    if module_spec is None or module_spec.loader is None:
        raise ReplayError(f"cannot load native module for {label}: {path}")
    module = importlib.util.module_from_spec(module_spec)
    try:
        module_spec.loader.exec_module(module)
    except Exception as exc:
        raise ReplayError(f"cannot initialize native module for {label}: {exc}") from exc
    return module


def _assert_finite_json(value: Any, label: str) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            _assert_finite_json(child, f"{label}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _assert_finite_json(child, f"{label}[{index}]")
    elif isinstance(value, float) and not math.isfinite(value):
        raise ReplayError(f"{label} must be finite")


def _parse_rfc3339(value: Any, label: str) -> datetime:
    _require_rfc3339(value, label)
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _validate_market_component_fixture(
    payload: Any,
    kind: str,
    fixed_timestamp: str,
) -> Mapping[str, Any]:
    config = MARKET_COMPONENT_CONFIG[kind]
    payload = _require_mapping_keys(
        payload,
        label=f"{kind} component fixture",
        required={
            "schema_version",
            "kind",
            "as_of",
            "max_age_days",
            "component_scores",
            "data_availability",
            "warning_flags",
        },
    )
    if payload["schema_version"] != 1 or payload["kind"] != kind:
        raise ReplayError(f"invalid {kind} component fixture identity")
    as_of = _parse_rfc3339(payload["as_of"], f"{kind}.as_of")
    fixed = _parse_rfc3339(fixed_timestamp, "fixed_timestamp")
    max_age_days = payload["max_age_days"]
    if (
        isinstance(max_age_days, bool)
        or not isinstance(max_age_days, int)
        or not 0 <= max_age_days <= 30
    ):
        raise ReplayError(f"{kind}.max_age_days must be an integer from 0 to 30")
    age_seconds = (fixed - as_of).total_seconds()
    if age_seconds < 0:
        raise ReplayError(f"{kind}.as_of cannot be later than fixed_timestamp")
    if age_seconds > max_age_days * 86400:
        raise ReplayError(f"{kind} component evidence is stale at fixed_timestamp")

    scores = payload["component_scores"]
    availability = payload["data_availability"]
    warning_flags = payload["warning_flags"]
    if not isinstance(scores, dict) or set(scores) != config["components"]:
        raise ReplayError(f"{kind}.component_scores must contain the canonical component set")
    if not isinstance(availability, dict) or set(availability) != config["components"]:
        raise ReplayError(f"{kind}.data_availability must contain the canonical component set")
    if not isinstance(warning_flags, dict) or set(warning_flags) != config["warning_flags"]:
        raise ReplayError(f"{kind}.warning_flags must contain the canonical flag set")
    for name, value in scores.items():
        _require_finite_number(value, f"{kind}.component_scores.{name}", minimum=0, maximum=100)
    for name, value in availability.items():
        if not isinstance(value, bool):
            raise ReplayError(f"{kind}.data_availability.{name} must be boolean")
        if not value:
            raise ReplayError(f"{kind} has insufficient component evidence: {name} unavailable")
    for name, value in warning_flags.items():
        if not isinstance(value, bool):
            raise ReplayError(f"{kind}.warning_flags.{name} must be boolean")
    return payload


def _load_market_fixture_set(
    inputs: Mapping[str, Path],
    spec: Mapping[str, Any],
    kinds: set[str] | None = None,
) -> dict[str, Mapping[str, Any]]:
    selected = kinds or set(MARKET_COMPONENT_CONFIG)
    fixtures = {
        kind: _validate_market_component_fixture(
            _load_json(inputs[config["input"]], f"{kind} component fixture"),
            kind,
            spec["fixed_timestamp"],
        )
        for kind, config in MARKET_COMPONENT_CONFIG.items()
        if kind in selected
    }
    as_of_values = {fixture["as_of"] for fixture in fixtures.values()}
    if len(as_of_values) != 1:
        raise ReplayError("market component fixtures must use one consistent as_of timestamp")
    return fixtures


def _market_modules(repo_root: Path, kind: str) -> tuple[Any, Any]:
    skill = MARKET_COMPONENT_CONFIG[kind]["skill"]
    scripts = repo_root / "skills" / skill / "scripts"
    scorer = _load_module_from_path(scripts / "scorer.py", f"{kind}_scorer")
    reporter = _load_module_from_path(scripts / "report_generator.py", f"{kind}_reporter")
    return scorer, reporter


def _market_composite(scorer: Any, kind: str, fixture: Mapping[str, Any]) -> dict[str, Any]:
    scores = dict(fixture["component_scores"])
    availability = dict(fixture["data_availability"])
    if kind == "uptrend":
        composite = scorer.calculate_composite_score(
            scores,
            availability,
            dict(fixture["warning_flags"]),
        )
    else:
        composite = scorer.calculate_composite_score(scores, availability)
    if not isinstance(composite, dict):
        raise ReplayError(f"{kind} native scorer returned a non-mapping result")
    _assert_finite_json(composite, f"{kind} native scorer result")
    score = composite.get("composite_score")
    _require_finite_number(score, f"{kind} composite_score", minimum=0, maximum=100)
    return composite


def _market_analysis(
    scorer: Any,
    kind: str,
    fixture: Mapping[str, Any],
    fixed_timestamp: str,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "metadata": {
            "generated_at": fixed_timestamp,
            "as_of": fixture["as_of"],
            "data_mode": "fictional offline component fixture",
        },
        "composite": _market_composite(scorer, kind, fixture),
        "components": {
            name: {"score": score, "data_available": fixture["data_availability"][name]}
            for name, score in fixture["component_scores"].items()
        },
        "provenance": {
            "execution_mode": "native_api",
            "native_surface": "scorer.calculate_composite_score + report_generator.generate_json_report",
            "fixture_boundaries": [
                "provider fetch not executed",
                "individual component calculators not executed",
                "live API failure not exercised",
            ],
        },
    }


def _validate_market_report(
    payload: Any,
    kind: str,
    fixture: Mapping[str, Any],
    scorer: Any,
    fixed_timestamp: str,
) -> Mapping[str, Any]:
    payload = _require_mapping_keys(
        payload,
        label=f"{kind} market artifact",
        required={"schema_version", "metadata", "composite", "components", "provenance"},
    )
    expected = _market_analysis(scorer, kind, fixture, fixed_timestamp)
    _assert_finite_json(payload, f"{kind} market artifact")
    if payload != expected:
        raise ReplayError(f"{kind} market artifact does not match native scorer recomputation")
    return payload


def _market_regime_component(
    repo_root: Path,
    spec: Mapping[str, Any],
    step: Mapping[str, Any],
    inputs: Mapping[str, Path],
    _consumed: Mapping[str, dict[str, Any]],
    _work: Path,
    stage: Path,
    *,
    kind: str,
) -> dict[str, dict[str, Any]]:
    fixture = _load_market_fixture_set(inputs, spec, {kind})[kind]
    scorer, reporter = _market_modules(repo_root, kind)
    analysis = _market_analysis(scorer, kind, fixture, spec["fixed_timestamp"])
    artifacts = _artifact_paths(stage, step["output_files"])
    artifact_id = MARKET_COMPONENT_CONFIG[kind]["artifact"]
    output = Path(artifacts[artifact_id]["files"]["canonical"])
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        reporter.generate_json_report(analysis, str(output))
    except Exception as exc:
        raise ReplayError(f"{kind} native report API failed: {exc}") from exc
    produced = _load_json(output, f"{kind} generated market artifact")
    _validate_market_report(produced, kind, fixture, scorer, spec["fixed_timestamp"])
    # Native report writers do not consistently append a final newline. Re-emit the
    # already validated payload in the harness's canonical JSON form for stable goldens.
    _write_json(output, produced)
    return artifacts


def _market_regime_breadth(*args: Any, **kwargs: Any) -> dict[str, dict[str, Any]]:
    return _market_regime_component(*args, **kwargs, kind="breadth")


def _market_regime_uptrend(*args: Any, **kwargs: Any) -> dict[str, dict[str, Any]]:
    return _market_regime_component(*args, **kwargs, kind="uptrend")


def _market_regime_top_risk(*args: Any, **kwargs: Any) -> dict[str, dict[str, Any]]:
    return _market_regime_component(*args, **kwargs, kind="top_risk")


def _expected_exposure_decision(
    repo_root: Path,
    consumed_payloads: Mapping[str, Mapping[str, Any]],
    fixed_timestamp: str,
) -> dict[str, Any]:
    module = _load_module_from_path(
        repo_root / "skills" / "exposure-coach" / "scripts" / "calculate_exposure.py",
        "exposure_coach",
    )
    scores: dict[str, Any] = {
        "breadth": module.extract_breadth_score(consumed_payloads.get("market_breadth_report")),
        "uptrend": module.extract_uptrend_score(consumed_payloads.get("uptrend_report")),
        "regime": None,
        "top_risk": module.extract_top_risk_score(consumed_payloads.get("top_risk_report")),
        "ftd": None,
        "theme": None,
        "sector": None,
        "institutional": None,
    }
    composite, provided, missing = module.calculate_composite_score(scores)
    missing_critical = len(set(missing) & module.CRITICAL_INPUTS)
    recommendation = module.determine_recommendation(
        composite, scores["top_risk"], missing_critical
    )
    bias = module.determine_bias("Unknown", scores["theme"], None, None)
    participation = module.determine_participation(scores["uptrend"], scores["breadth"], None)
    confidence = module.determine_confidence(provided, missing)
    return {
        "schema_version": "1.0",
        "generated_at": fixed_timestamp,
        "exposure_ceiling_pct": module.determine_exposure_ceiling(composite),
        "bias": bias,
        "participation": participation,
        "recommendation": recommendation,
        "confidence": confidence,
        "composite_score": round(composite, 1),
        "component_scores": {
            f"{key}_score": value for key, value in scores.items() if value is not None
        },
        "inputs_provided": provided,
        "inputs_missing": missing,
        "rationale": module.generate_rationale(
            composite, recommendation, participation, bias, scores, missing
        ),
    }


def _market_regime_exposure(
    repo_root: Path,
    spec: Mapping[str, Any],
    step: Mapping[str, Any],
    inputs: Mapping[str, Path],
    consumed: Mapping[str, dict[str, Any]],
    work: Path,
    stage: Path,
) -> dict[str, dict[str, Any]]:
    expected_artifacts = {"market_breadth_report", "uptrend_report"}
    if "top_risk_report" in consumed:
        expected_artifacts.add("top_risk_report")
    if set(consumed) != expected_artifacts:
        raise ReplayError(f"market exposure received unexpected artifacts: {sorted(consumed)}")

    kind_by_artifact = {
        "market_breadth_report": "breadth",
        "uptrend_report": "uptrend",
        "top_risk_report": "top_risk",
    }
    fixtures = _load_market_fixture_set(
        inputs,
        spec,
        {kind_by_artifact[artifact_id] for artifact_id in consumed},
    )
    payloads: dict[str, Mapping[str, Any]] = {}
    for artifact_id, bundle in consumed.items():
        kind = kind_by_artifact[artifact_id]
        path = Path(bundle["files"]["canonical"])
        payload = _load_json(path, f"{artifact_id} handoff")
        scorer, _reporter = _market_modules(repo_root, kind)
        payloads[artifact_id] = _validate_market_report(
            payload, kind, fixtures[kind], scorer, spec["fixed_timestamp"]
        )

    reports = work / "reports"
    reports.mkdir()
    command = [
        sys.executable,
        str(repo_root / "skills" / "exposure-coach" / "scripts" / "calculate_exposure.py"),
        "--breadth",
        str(Path(consumed["market_breadth_report"]["files"]["canonical"])),
        "--uptrend",
        str(Path(consumed["uptrend_report"]["files"]["canonical"])),
    ]
    if "top_risk_report" in consumed:
        command.extend(["--top-risk", str(Path(consumed["top_risk_report"]["files"]["canonical"]))])
    command.extend(["--output-dir", str(reports), "--json-only"])
    _run_cli(command, repo_root)
    source = _latest_report(reports, "exposure_posture_*.json")
    actual = _load_json(source, "exposure decision")
    _assert_finite_json(actual, "exposure decision")
    expected = _expected_exposure_decision(repo_root, payloads, spec["fixed_timestamp"])
    if not isinstance(actual, dict) or set(actual) != set(expected):
        raise ReplayError("exposure decision must contain the exact canonical schema")
    _require_rfc3339(actual.get("generated_at"), "exposure decision generated_at")
    canonical = dict(actual)
    canonical["generated_at"] = spec["fixed_timestamp"]
    if canonical != expected:
        raise ReplayError("exposure decision does not match native API recomputation")

    artifacts = _artifact_paths(stage, step["output_files"])
    _write_json(Path(artifacts["exposure_decision"]["files"]["canonical"]), canonical)
    return artifacts


EXECUTORS: dict[str, ExecutorRegistration] = {
    "stockbee_fluency_ingest": ExecutorRegistration("native_cli", _stockbee_ingest),
    "stockbee_fluency_update": ExecutorRegistration("native_cli", _stockbee_update),
    "stockbee_fluency_summarize": ExecutorRegistration("native_cli", _stockbee_summarize),
    "manual_lessons_log": ExecutorRegistration("manual_contract", _manual_lessons),
    "twenty_pct_scan": ExecutorRegistration("native_cli", _twenty_pct_scan),
    "twenty_pct_enrich": ExecutorRegistration("native_cli", _twenty_pct_enrich),
    "twenty_pct_update_outcomes": ExecutorRegistration("native_cli", _twenty_pct_update_outcomes),
    "twenty_pct_summarize": ExecutorRegistration("native_cli", _twenty_pct_summarize),
    "manual_twenty_pct_lessons": ExecutorRegistration(
        "manual_contract", _manual_twenty_pct_lessons
    ),
    "trade_memory_close": ExecutorRegistration("native_cli", _trade_memory_close),
    "trade_memory_postmortem": ExecutorRegistration(
        "composite",
        _trade_memory_postmortem,
        ("native_api", "manual_contract"),
    ),
    "trade_memory_coach": ExecutorRegistration(
        "composite",
        _trade_memory_coach,
        ("native_cli", "manual_contract"),
    ),
    "trade_memory_backtest": ExecutorRegistration("native_cli", _trade_memory_backtest),
    "trade_memory_lessons": ExecutorRegistration(
        "composite",
        _trade_memory_lessons,
        ("native_api", "manual_contract"),
    ),
    "market_regime_breadth": ExecutorRegistration("native_api", _market_regime_breadth),
    "market_regime_uptrend": ExecutorRegistration("native_api", _market_regime_uptrend),
    "market_regime_top_risk": ExecutorRegistration("native_api", _market_regime_top_risk),
    "market_regime_exposure": ExecutorRegistration("native_cli", _market_regime_exposure),
}


def _prompt_text(workflow: Mapping[str, Any], variant: str) -> str:
    if variant == "required-only":
        optional_text = "Skip every optional step."
    elif workflow["id"] == "stockbee-20pct-study-daily":
        optional_text = (
            "Run the optional human-approved lessons step after reviewing the 20% mover "
            "cohort evidence."
        )
    elif workflow["id"] == "trade-memory-loop":
        optional_text = (
            "Run the optional native coaching and fixture-metric evaluation steps before "
            "recording the separately human-approved lesson."
        )
    elif workflow["id"] == "market-regime-daily":
        optional_text = (
            "Include the optional fixture-backed market-top score before running the "
            "native exposure posture CLI."
        )
    else:
        optional_text = (
            "Run the optional human-approved lessons step after reviewing the cohort evidence."
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
        entry = {
            "step": step_number,
            "artifact_id": artifact_id,
            "skill": step_contract[step_number]["skill"],
            "execution_mode": next(
                item["executor_mode"] for item in report["steps"] if item["step"] == step_number
            ),
            "files": {role: Path(path).name for role, path in bundle["files"].items()},
        }
        report_step = next(item for item in report["steps"] if item["step"] == step_number)
        if report_step.get("executor_components"):
            entry["executor_components"] = report_step["executor_components"]
        entries.append(entry)
    entries.sort(key=lambda item: (item["step"], item["artifact_id"]))
    completed_steps = [int(item["step"]) for item in report["steps"]]
    completed = set(completed_steps)
    halted_after = completed_steps[-1] if report["status"] == "halted" else None
    required_steps_not_executed = [
        {
            "step": int(step["step"]),
            "skill": step["skill"],
            "reason": (
                f"halted after step {halted_after}" if halted_after is not None else "not executed"
            ),
        }
        for step in workflow["steps"]
        if not step.get("optional") and int(step["step"]) not in completed
    ]
    skipped = [
        {
            "step": int(step["step"]),
            "skill": step["skill"],
            "reason": "required-only executable replay",
        }
        for step in workflow["steps"]
        if step.get("optional") and variant == "required-only"
    ]
    payload = {
        "workflow_id": workflow["id"],
        "sample_type": variant,
        "status": report["status"],
        "completed_steps": completed_steps,
        "required_steps_not_executed": required_steps_not_executed,
        "illustrative": True,
        "generated_by": "scripts/workflow_replay.py generate",
        "prompt": "prompt.md",
        "network_policy": report["network_policy"],
        "optional_steps_skipped": skipped,
        "artifacts": entries,
    }
    if workflow["id"] == "trade-memory-loop":
        payload["execution_evidence_limitations"] = [
            "Root-cause and lesson decisions are human-approved fixtures bound by SHA-256.",
            "Backtest Expert evaluates bundled aggregate metrics; it does not run a strategy backtest.",
            "Only staged temporary trader-memory state is mutated; no user state is accessed.",
        ]
    elif workflow["id"] == "market-regime-daily":
        payload["execution_evidence_limitations"] = [
            "Breadth, uptrend, and top-risk provider fetches are not executed.",
            "Individual component calculators and live API failure paths are not executed.",
            "Native scorer and JSON report APIs consume complete fictional component fixtures.",
            "INSUFFICIENT_EVIDENCE is not a literal contract for these skills; unavailable fixture components fail closed before publication.",
            "Exposure Coach runs as the native CLI against the generated artifact handoffs.",
        ]
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


def _publish_trees_transactionally(staged_trees: list[tuple[Path, Path]]) -> None:
    """Publish multiple generated trees as one rollback-capable transaction."""
    destinations = [destination.resolve() for _stage, destination in staged_trees]
    for index, destination in enumerate(destinations):
        for other in destinations[index + 1 :]:
            if _paths_overlap(destination, other):
                raise ReplayError(f"transaction destinations overlap: {destination} and {other}")

    prepared: list[dict[str, Any]] = []
    succeeded = False
    try:
        for stage, raw_destination in staged_trees:
            destination = raw_destination.resolve()
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists() and not destination.is_dir():
                raise ReplayError(f"transaction destination must be a directory: {destination}")
            candidate = Path(
                tempfile.mkdtemp(prefix=f".{destination.name}.candidate-", dir=destination.parent)
            )
            backup_root = Path(
                tempfile.mkdtemp(prefix=f".{destination.name}.backup-", dir=destination.parent)
            )
            entry = {
                "destination": destination,
                "candidate": candidate,
                "backup_root": backup_root,
                "backup": backup_root / "previous",
                "backup_moved": False,
                "candidate_committed": False,
            }
            prepared.append(entry)
            shutil.copytree(stage, candidate, dirs_exist_ok=True)

        for entry in prepared:
            destination = entry["destination"]
            if destination.exists():
                os.replace(destination, entry["backup"])
                entry["backup_moved"] = True
            os.replace(entry["candidate"], destination)
            entry["candidate_committed"] = True
        succeeded = True
    except Exception as exc:
        rollback_errors: list[str] = []
        for entry in reversed(prepared):
            destination = entry["destination"]
            try:
                if entry["candidate_committed"] and destination.exists():
                    shutil.rmtree(destination)
                if entry["backup_moved"] and entry["backup"].exists():
                    os.replace(entry["backup"], destination)
            except Exception as rollback_exc:  # pragma: no cover - catastrophic filesystem path
                rollback_errors.append(f"{destination}: {rollback_exc}")
        if rollback_errors:
            raise ReplayError(
                f"golden publication failed ({exc}); rollback also failed: "
                + "; ".join(rollback_errors)
            ) from exc
        raise
    finally:
        for entry in prepared:
            candidate = entry["candidate"]
            backup_root = entry["backup_root"]
            backup = entry["backup"]
            if candidate.exists():
                shutil.rmtree(candidate)
            if succeeded:
                try:
                    _cleanup_backup(backup_root)
                except OSError:
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
    _validate_runtime_output(repo_root, spec_path, spec, inputs, output_dir)

    completed_steps: list[int] = []
    artifacts: dict[str, dict[str, Any]] = {}
    sealed_artifact_digests: dict[str, str] = {}
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
                produced_digests = _artifact_file_digests(produced)
                duplicate_seals = set(produced_digests) & set(sealed_artifact_digests)
                if duplicate_seals:
                    raise ReplayError(
                        f"step {number} replaced sealed artifacts: {sorted(duplicate_seals)}",
                        completed_steps,
                    )
                sealed_artifact_digests.update(produced_digests)
                artifacts = candidate_artifacts
                completed_steps.append(number)
                step_report = {
                    "step": number,
                    "skill": workflow_step["skill"],
                    "executor": executor_name,
                    "executor_mode": registration.mode,
                    "gate_policy": replay_step["gate_policy"],
                    "consumed": sorted(consumed),
                    "produced": sorted(produced),
                }
                if registration.components:
                    step_report["executor_components"] = list(registration.components)
                step_reports.append(step_report)
                if after_step:
                    after_step(number, artifacts)
                if replay_step["gate_policy"] == "halt":
                    status = "halted"
                    break

            _validate_artifact_files(stage, artifacts, "final artifact store")
            final_digests = _artifact_file_digests(artifacts)
            changed_artifacts = sorted(
                artifact_id
                for artifact_id in set(final_digests) | set(sealed_artifact_digests)
                if final_digests.get(artifact_id) != sealed_artifact_digests.get(artifact_id)
            )
            if changed_artifacts:
                raise ReplayError(
                    f"final artifact integrity mismatch: {changed_artifacts}", completed_steps
                )

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
                {
                    "schema_version": 1,
                    "coverage": {"covered": 4, "total": 11},
                    "issue": 294,
                    "rows": rows,
                },
            )
    return all_differences


def generate_goldens(repo_root: Path, coverage_path: Path) -> dict[str, list[str]]:
    validate_coverage(repo_root, coverage_path)
    staged_trees: list[tuple[Path, Path]] = []
    generated: list[str] = []
    with tempfile.TemporaryDirectory(prefix="workflow-replay-generate-") as temp_name:
        temp = Path(temp_name)
        for workflow_id, spec_path, entry in _covered_specs(coverage_path):
            spec = load_yaml(spec_path)
            for variant in entry["variants"]:
                staged = temp / workflow_id / variant
                execute_replay(repo_root, spec_path, variant, staged)
                destination = (spec_path.parent / spec["variants"][variant]["golden_dir"]).resolve()
                staged_trees.append((staged, destination))
                generated.append(f"{workflow_id}:{variant}")
        _publish_trees_transactionally(staged_trees)
    return {"generated": generated}


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
