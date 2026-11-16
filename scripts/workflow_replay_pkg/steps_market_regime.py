"""Step adapters for the market-regime-daily workflow."""

from __future__ import annotations

import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .artifacts import _artifact_paths, _latest_report
from .common import (
    ReplayError,
    _assert_finite_json,
    _load_json,
    _load_module_from_path,
    _parse_rfc3339,
    _require_finite_number,
    _require_mapping_keys,
    _require_rfc3339,
    _run_cli,
    _write_json,
)
from .constants import MARKET_COMPONENT_CONFIG, REPO_ROOT


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


MARKET_PROVENANCE_RUN_ID = "fictional-market-regime-daily-run-001"


def _market_analysis(
    scorer: Any,
    kind: str,
    fixture: Mapping[str, Any],
    fixed_timestamp: str,
) -> dict[str, Any]:
    result = {
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

    if kind in {"breadth", "uptrend"}:
        contract = _load_module_from_path(
            REPO_ROOT / "skills" / "exposure-coach" / "scripts" / "provenance_contract.py",
            "market_provenance_contract",
        )
        result["data_provenance"] = contract.build_provenance(
            provider="fictional-fixture",
            endpoint=f"market-regime-{kind}-component-fixture",
            retrieved_at=fixed_timestamp,
            as_of=fixture["as_of"],
            run_id=MARKET_PROVENANCE_RUN_ID,
        )
        result["data_provenance"]["scope"] = (
            "fictional component fixture only; provider fetch not executed"
        )
    return result


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
        required={"schema_version", "metadata", "composite", "components", "provenance"}
        | ({"data_provenance"} if kind in {"breadth", "uptrend"} else set()),
        optional={"evaluation_coverage"},
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
    result = {
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

    result["input_lineage"] = module.validate_market_inputs(
        consumed_payloads.get("market_breadth_report"),
        consumed_payloads.get("uptrend_report"),
        run_id=MARKET_PROVENANCE_RUN_ID,
        evaluation=fixed_timestamp,
        max_age_days=3,
    )
    return result


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
    command.extend(
        [
            "--output-dir",
            str(reports),
            "--json-only",
            "--require-provenance",
            "--run-id",
            MARKET_PROVENANCE_RUN_ID,
            "--as-of",
            spec["fixed_timestamp"],
        ]
    )
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
