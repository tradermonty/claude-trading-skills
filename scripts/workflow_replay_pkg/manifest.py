"""Coverage manifest and replay spec loading and validation."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .common import ReplayError, _load_json, _require_rfc3339, _schema_error_details, load_yaml
from .constants import FROZEN_DEFERRED_WORKFLOWS, SPEC_SCHEMA, VARIANTS
from .normalize import _paths_overlap, _safe_relative
from .registry import EXECUTORS


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
            "deferred workflows must match the frozen coverage 14/14 deferred set; "
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
    provenance_declaration_owners: dict[str, int] = {}
    for number, step in workflow_steps.items():
        replay_step = spec_steps[number]
        expected_outputs = set(step.get("produces") or [])
        configured_outputs = set((replay_step.get("output_files") or {}).keys())
        if expected_outputs != configured_outputs:
            raise ReplayError(
                f"step {number} output_files must match produces: "
                f"expected {sorted(expected_outputs)}, got {sorted(configured_outputs)}"
            )
        for artifact_id in replay_step.get("required_provenance", []):
            roles = replay_step["output_files"].get(artifact_id)
            canonical = roles.get("canonical") if roles else None
            if not canonical or Path(canonical).suffix.lower() not in {".json", ".yaml", ".yml"}:
                raise ReplayError(
                    f"step {number} required_provenance {artifact_id!r} must name a produced "
                    "artifact with a canonical JSON/YAML file"
                )
            previous_step = provenance_declaration_owners.get(artifact_id)
            if previous_step is not None:
                raise ReplayError(
                    f"duplicate required_provenance declaration for artifact {artifact_id!r}: "
                    f"step {previous_step} and step {number}"
                )
            provenance_declaration_owners[artifact_id] = number
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
        "strategy_research_detect_initial": {"ohlcv"},
        "strategy_research_detect_final": {"ohlcv"},
        "strategy_research_hold": {"backtest_metrics"},
        "earnings_circuit": {"sizing_parameters"},
        "earnings_analyze": {"fmp_fixture"},
        "earnings_pead": {"fmp_fixture"},
        "earnings_validate": {"technical_review"},
        "earnings_size": {"sizing_parameters"},
        "earnings_journal": {"journal_decision"},
        "earnings_discipline": {"exposure_decision"},
        "trade_memory_lessons": {"lessons_required", "lessons_full"},
        "market_regime_breadth": {"market_breadth_components"},
        "market_regime_uptrend": {"market_uptrend_components"},
        "market_regime_top_risk": {"market_top_risk_components"},
        "market_regime_exposure": {
            "market_breadth_components",
            "market_uptrend_components",
            "market_top_risk_components",
        },
        "core_portfolio_snapshot": {"holdings_snapshot"},
        "portfolio_holdings_review": {"holdings_csv", "review_context"},
        "core_portfolio_allocation": {"allocation_decision"},
        "core_portfolio_dividend": {"dividend_enrichment"},
        "core_portfolio_rebalance": {
            "rebalance_decision_required",
            "rebalance_decision_full",
        },
        "core_portfolio_journal": {
            "journal_decision_required",
            "journal_decision_full",
        },
        "monthly_aggregate": {"closed_theses"},
        "monthly_postmortem": {"postmortems", "pattern_decision"},
        "monthly_coach": {"coach_decision"},
        "monthly_backtest": {"backtest_params"},
        "monthly_skill_review": {"skill_review_target"},
        "monthly_decision_log": {"rule_change_decision"},
        "swing_circuit_breaker": {"sizing_parameters"},
        "swing_vcp_screen": {"vcp_scan"},
        "swing_momentum_burst": {"momentum_burst"},
        "swing_exhaustion_hammer": {"exhaustion_hammer"},
        "swing_canslim": {"canslim"},
        "swing_theme": {"theme"},
        "swing_validate_setups": {"validated_setups"},
        "swing_position_size": {"sizing_parameters"},
        "swing_journal": {"journal"},
        "swing_discipline": {"exposure_decision"},
        "kanchi_high_yield_screen": {"high_yield_candidates"},
        "kanchi_pullback_screen": {"pullback_candidates"},
        "kanchi_underwrite": {"underwriting_evidence", "underwriting_decision"},
        "kanchi_tax_advice": {"tax_holdings"},
        "kanchi_review_queue": {"review_monitor"},
        "kanchi_register_thesis": {"register_decision"},
        "multi_macro_regime": {"macro_components"},
        "multi_theme": {"theme_evidence"},
        "multi_news_brief": {"news_brief"},
        "multi_hypotheses": {"hypotheses_bundle", "raw_hypotheses", "gate_decision"},
        "multi_position_size": {"sizing_params"},
        "multi_register": {"register_decision"},
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
