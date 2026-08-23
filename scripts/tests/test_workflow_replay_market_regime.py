"""Executable replay coverage for market-regime-daily (Issue #294)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import workflow_replay as replay_module  # noqa: E402
from workflow_replay import (  # noqa: E402
    ReplayError,
    compare_trees,
    execute_replay,
    generate_goldens,
    load_yaml,
)

SPEC = ROOT / "examples" / "workflows" / "market-regime-daily" / "replay.yaml"
COVERAGE = ROOT / "examples" / "workflows" / "replay-coverage.yaml"


def test_market_regime_spec_records_fixture_backed_native_evidence() -> None:
    summary = replay_module.validate_spec(ROOT, SPEC)

    assert summary["workflow_id"] == "market-regime-daily"
    assert summary["native_steps"] == [4]
    assert summary["native_api_steps"] == [1, 2, 3]
    assert summary["manual_contract_steps"] == []
    assert summary["composite_steps"] == []


@pytest.mark.parametrize(
    ("variant", "steps", "expected_score", "recommendation", "confidence"),
    [
        ("required-only", [1, 2, 4], 48.5, "REDUCE_ONLY", "LOW"),
        ("full-path", [1, 2, 3, 4], 55.9, "NEW_ENTRY_ALLOWED", "MEDIUM"),
    ],
)
def test_market_regime_variants_execute_native_handoff(
    variant: str,
    steps: list[int],
    expected_score: float,
    recommendation: str,
    confidence: str,
    tmp_path: Path,
) -> None:
    output = tmp_path / variant
    report = execute_replay(ROOT, SPEC, variant, output)

    assert report["status"] == "completed"
    assert [row["step"] for row in report["steps"]] == steps
    assert [row["executor_mode"] for row in report["steps"]] == [
        "native_api" if step != 4 else "native_cli" for step in steps
    ]
    decision = json.loads((output / "04_exposure_decision.json").read_text())
    assert decision["composite_score"] == expected_score
    assert decision["recommendation"] == recommendation
    assert decision["confidence"] == confidence
    assert decision["generated_at"] == "2026-01-15T13:08:00+00:00"
    assert set(decision["component_scores"]) == (
        {"breadth_score", "uptrend_score"}
        if variant == "required-only"
        else {"breadth_score", "uptrend_score", "top_risk_score"}
    )

    manifest = load_yaml(output / "manifest.yaml")
    assert manifest["completed_steps"] == steps
    assert manifest["execution_evidence_limitations"]
    if variant == "required-only":
        assert [row["step"] for row in manifest["optional_steps_skipped"]] == [3]
        assert not (output / "03_top_risk_report.json").exists()
    else:
        assert manifest["optional_steps_skipped"] == []


@pytest.mark.parametrize("variant", ["required-only", "full-path"])
def test_market_regime_outputs_match_committed_goldens(variant: str, tmp_path: Path) -> None:
    output = tmp_path / variant
    execute_replay(ROOT, SPEC, variant, output)
    golden = SPEC.parent / ("sample-run" if variant == "required-only" else "sample-run-full-path")
    assert compare_trees(output, golden) == []


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda payload: payload.update({"as_of": "2026-01-20T00:00:00+00:00"}), "later"),
        (lambda payload: payload.update({"as_of": "2025-12-01T00:00:00+00:00"}), "stale"),
        (
            lambda payload: payload["component_scores"].update({"breadth_level_trend": 101}),
            "<= 100",
        ),
        (
            lambda payload: payload["data_availability"].update({"breadth_level_trend": False}),
            "insufficient component evidence",
        ),
    ],
)
def test_invalid_breadth_fixture_fails_before_publication(
    mutation,
    message: str,
    tmp_path: Path,
) -> None:
    original = SPEC.parent / "replay-inputs" / "breadth-components.json"
    payload = json.loads(original.read_text())
    mutation(payload)
    changed = tmp_path / "inputs" / "breadth.json"
    changed.parent.mkdir()
    changed.write_text(json.dumps(payload), encoding="utf-8")
    output = tmp_path / "published"
    output.mkdir()
    sentinel = output / "keep.txt"
    sentinel.write_text("keep\n", encoding="utf-8")

    with pytest.raises(ReplayError, match=message) as exc_info:
        execute_replay(
            ROOT,
            SPEC,
            "required-only",
            output,
            input_overrides={"market_breadth_components": changed},
        )

    assert exc_info.value.completed_steps == []
    assert {path.name for path in output.iterdir()} == {"keep.txt"}


def test_malformed_nonfinite_and_inconsistent_fixture_dates_fail_closed(tmp_path: Path) -> None:
    inputs_dir = tmp_path / "inputs"
    inputs_dir.mkdir()
    malformed = inputs_dir / "malformed.json"
    malformed.write_text("{not-json\n", encoding="utf-8")
    with pytest.raises(ReplayError):
        execute_replay(
            ROOT,
            SPEC,
            "required-only",
            tmp_path / "malformed-output",
            input_overrides={"market_uptrend_components": malformed},
        )

    breadth = json.loads((SPEC.parent / "replay-inputs" / "breadth-components.json").read_text())
    breadth["component_scores"]["breadth_level_trend"] = float("nan")
    nonfinite = inputs_dir / "nonfinite.json"
    nonfinite.write_text(json.dumps(breadth), encoding="utf-8")
    with pytest.raises(ReplayError, match="finite"):
        execute_replay(
            ROOT,
            SPEC,
            "required-only",
            tmp_path / "nonfinite-output",
            input_overrides={"market_breadth_components": nonfinite},
        )

    breadth["component_scores"]["breadth_level_trend"] = 72
    breadth["as_of"] = "2026-01-14T20:00:00+00:00"
    inconsistent = inputs_dir / "inconsistent.json"
    inconsistent.write_text(json.dumps(breadth), encoding="utf-8")
    with pytest.raises(ReplayError, match="consistent as_of"):
        execute_replay(
            ROOT,
            SPEC,
            "required-only",
            tmp_path / "inconsistent-output",
            input_overrides={"market_breadth_components": inconsistent},
        )


def test_required_only_does_not_depend_on_optional_top_risk_fixture(tmp_path: Path) -> None:
    invalid_optional = tmp_path / "inputs" / "top-risk.json"
    invalid_optional.parent.mkdir()
    invalid_optional.write_text("{not-json\n", encoding="utf-8")

    report = execute_replay(
        ROOT,
        SPEC,
        "required-only",
        tmp_path / "published",
        input_overrides={"market_top_risk_components": invalid_optional},
    )

    assert [step["step"] for step in report["steps"]] == [1, 2, 4]


def test_corrupt_handoff_stops_before_exposure_and_preserves_destination(tmp_path: Path) -> None:
    output = tmp_path / "published"
    output.mkdir()
    sentinel = output / "keep.txt"
    sentinel.write_text("keep\n", encoding="utf-8")

    def corrupt_after_uptrend(step: int, artifacts: dict[str, dict]) -> None:
        if step == 2:
            path = Path(artifacts["market_breadth_report"]["files"]["canonical"])
            path.write_text("{not-json\n", encoding="utf-8")

    with pytest.raises(ReplayError) as exc_info:
        execute_replay(
            ROOT,
            SPEC,
            "required-only",
            output,
            after_step=corrupt_after_uptrend,
        )

    assert exc_info.value.completed_steps == [1, 2]
    assert {path.name for path in output.iterdir()} == {"keep.txt"}


def test_corrupt_final_handoff_stops_before_publication(tmp_path: Path) -> None:
    output = tmp_path / "published"
    output.mkdir()
    sentinel = output / "keep.txt"
    sentinel.write_text("keep\n", encoding="utf-8")

    def corrupt_after_exposure(step: int, artifacts: dict[str, dict]) -> None:
        if step == 4:
            path = Path(artifacts["exposure_decision"]["files"]["canonical"])
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["recommendation"] = "TAMPERED"
            path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    with pytest.raises(ReplayError, match="final artifact integrity mismatch") as exc_info:
        execute_replay(
            ROOT,
            SPEC,
            "required-only",
            output,
            after_step=corrupt_after_exposure,
        )

    assert exc_info.value.completed_steps == [1, 2, 4]
    assert {path.name for path in output.iterdir()} == {"keep.txt"}


@pytest.mark.parametrize(
    "failure",
    [
        "scorer-exception",
        "scorer-nonmapping",
        "scorer-nonfinite",
        "scorer-out-of-range",
        "report-exception",
        "report-invalid-output",
    ],
)
def test_native_api_failures_do_not_publish(
    failure: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_modules = replay_module._market_modules

    def broken_modules(repo_root: Path, kind: str):
        scorer, reporter = real_modules(repo_root, kind)
        if kind != "breadth":
            return scorer, reporter
        if failure == "scorer-exception":
            broken_scorer = SimpleNamespace(
                calculate_composite_score=lambda *_args: (_ for _ in ()).throw(
                    ValueError("injected")
                )
            )
            return broken_scorer, reporter
        if failure == "scorer-nonmapping":
            return SimpleNamespace(calculate_composite_score=lambda *_args: []), reporter
        if failure == "scorer-nonfinite":
            return (
                SimpleNamespace(
                    calculate_composite_score=lambda *_args: {"composite_score": float("nan")}
                ),
                reporter,
            )
        if failure == "scorer-out-of-range":
            return (
                SimpleNamespace(
                    calculate_composite_score=lambda *_args: {"composite_score": 101.0}
                ),
                reporter,
            )
        if failure == "report-exception":
            broken = SimpleNamespace(
                generate_json_report=lambda *_args: (_ for _ in ()).throw(OSError("injected"))
            )
        else:
            broken = SimpleNamespace(
                generate_json_report=lambda _analysis, path: Path(path).write_text(
                    "{}\n", encoding="utf-8"
                )
            )
        return scorer, broken

    monkeypatch.setattr(replay_module, "_market_modules", broken_modules)
    output = tmp_path / "published"
    output.mkdir()
    (output / "keep.txt").write_text("keep\n", encoding="utf-8")

    with pytest.raises(ReplayError):
        execute_replay(ROOT, SPEC, "required-only", output)
    assert {path.name for path in output.iterdir()} == {"keep.txt"}


@pytest.mark.parametrize("failure", ["missing", "multiple", "invalid", "schema", "mismatch"])
def test_successful_exposure_cli_with_bad_outputs_fails_closed(
    failure: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_run = replay_module._run_cli

    def bad_run(command: list[str], repo_root: Path):
        reports = Path(command[command.index("--output-dir") + 1])
        if failure == "missing":
            return subprocess.CompletedProcess(command, 0, "", "")
        if failure == "multiple":
            (reports / "exposure_posture_a.json").write_text("{}\n", encoding="utf-8")
            (reports / "exposure_posture_b.json").write_text("{}\n", encoding="utf-8")
        elif failure == "invalid":
            (reports / "exposure_posture_bad.json").write_text("{bad\n", encoding="utf-8")
        elif failure == "schema":
            (reports / "exposure_posture_bad.json").write_text("{}\n", encoding="utf-8")
        else:
            real_run(command, repo_root)
            path = next(reports.glob("exposure_posture_*.json"))
            payload = json.loads(path.read_text())
            payload["composite_score"] = 99.0
            path.write_text(json.dumps(payload), encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(replay_module, "_run_cli", bad_run)
    output = tmp_path / "published"
    output.mkdir()
    (output / "keep.txt").write_text("keep\n", encoding="utf-8")
    with pytest.raises(ReplayError):
        execute_replay(ROOT, SPEC, "required-only", output)
    assert {path.name for path in output.iterdir()} == {"keep.txt"}


def test_exposure_cli_nonzero_failure_preserves_destination(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        replay_module.subprocess,
        "run",
        lambda command, **_kwargs: subprocess.CompletedProcess(command, 9, "", "injected"),
    )
    output = tmp_path / "published"
    output.mkdir()
    sentinel = output / "keep.txt"
    sentinel.write_text("keep\n", encoding="utf-8")

    with pytest.raises(ReplayError, match="native CLI failed") as exc_info:
        execute_replay(ROOT, SPEC, "required-only", output)

    assert exc_info.value.completed_steps == [1, 2]
    assert {path.name for path in output.iterdir()} == {"keep.txt"}


def test_exposure_cli_scrubs_sensitive_env_and_uses_no_provider_flags(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[tuple[list[str], dict[str, str]]] = []
    real_run = replay_module.subprocess.run
    monkeypatch.setenv("REPLAY_API_KEY", "secret")
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.invalid")

    def capture(command, *args, **kwargs):
        captured.append((list(command), dict(kwargs["env"])))
        return real_run(command, *args, **kwargs)

    monkeypatch.setattr(replay_module.subprocess, "run", capture)
    execute_replay(ROOT, SPEC, "full-path", tmp_path / "published")

    assert len(captured) == 1
    command, env = captured[0]
    assert command[1].endswith("skills/exposure-coach/scripts/calculate_exposure.py")
    assert "--api-key" not in command
    assert not any("API_KEY" in key or "PROXY" in key for key in env)


def test_generate_stages_both_market_regime_variants_without_publishing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    staged: list[tuple[Path, Path]] = []
    monkeypatch.setattr(
        replay_module,
        "_publish_trees_transactionally",
        lambda trees: staged.extend(trees),
    )

    result = generate_goldens(ROOT, COVERAGE)
    assert "market-regime-daily:required-only" in result["generated"]
    assert "market-regime-daily:full-path" in result["generated"]
    market_destinations = [
        destination.name for _source, destination in staged if destination.parent == SPEC.parent
    ]
    assert market_destinations == ["sample-run", "sample-run-full-path"]
