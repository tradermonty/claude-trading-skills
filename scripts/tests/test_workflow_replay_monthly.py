"""Executable replay coverage for monthly-performance-review (Issue #294)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import workflow_replay as replay_module  # noqa: E402
from workflow_replay import (  # noqa: E402
    EXECUTORS,
    ReplayError,
    compare_trees,
    execute_replay,
    load_yaml,
)

SPEC = ROOT / "examples" / "workflows" / "monthly-performance-review" / "replay.yaml"
INPUTS = SPEC.parent / "replay-inputs"


def test_monthly_spec_has_honest_executor_evidence() -> None:
    summary = replay_module.validate_spec(ROOT, SPEC)

    assert summary["workflow_id"] == "monthly-performance-review"
    assert summary["variants"] == ["required-only", "full-path"]
    assert summary["native_steps"] == [4, 5]
    assert summary["composite_steps"] == [2, 3, 6]
    assert summary["manual_contract_steps"] == []
    assert summary["executor_components"] == {
        2: ["native_api", "manual_contract"],
        3: ["native_cli", "manual_contract"],
        6: ["native_api", "manual_contract"],
    }


def test_required_only_aggregates_and_documents_rule_changes(tmp_path: Path) -> None:
    output = tmp_path / "required"
    report = execute_replay(ROOT, SPEC, "required-only", output)

    assert report["status"] == "completed"
    assert [step["step"] for step in report["steps"]] == [1, 2, 6]
    assert [step["executor_mode"] for step in report["steps"]] == [
        "native_api",
        "composite",
        "composite",
    ]

    aggregate = json.loads((output / "01_monthly_aggregate.json").read_text())
    postmortem = json.loads((output / "02_aggregate_postmortem.json").read_text())
    rule_changes = load_yaml(output / "06_rule_changes_for_next_month.yaml")

    assert aggregate["review_type"] == "monthly_aggregate"
    assert aggregate["summary"]["closed_trades"] == 5
    assert aggregate["summary"]["realized_pnl"] == 500.0
    assert aggregate["summary"]["win_rate_pct"] == 40.0
    assert aggregate["postmortem"]["root_cause"] == "thesis_quality"
    assert aggregate["monthly"]["consecutive_losses"] == 2
    assert "TRADE-001" in aggregate["monthly"]["trades"]

    assert postmortem["decision"] == "documented"
    assert postmortem["category_counts"] == {
        "execution": 1,
        "market_environment": 0,
        "randomness": 1,
        "thesis_quality": 2,
    }
    assert postmortem["native_skill_metrics"]["vcp-screener"]["accuracy"] == 0.0
    assert postmortem["provenance"]["postmortem_records"] == 5

    assert rule_changes["schema_version"] == 1
    assert rule_changes["trade_rule_changes"][0].startswith("Enforce the confirmed-pivot rule")
    assert any(
        "regime-gate" in note
        for item in rule_changes["repo_improvements"]
        for note in item.values()
    )
    assert not (output / "03_monthly_performance_coach_report.json").exists()
    assert not (output / "04_hypothesis_revalidation.json").exists()

    manifest = load_yaml(output / "manifest.yaml")
    assert manifest["completed_steps"] == [1, 2, 6]
    assert [item["step"] for item in manifest["optional_steps_skipped"]] == [3, 4, 5]


def test_full_path_runs_coach_backtest_and_reviews_skill(tmp_path: Path) -> None:
    output = tmp_path / "full"
    report = execute_replay(ROOT, SPEC, "full-path", output)

    assert [step["step"] for step in report["steps"]] == [1, 2, 3, 4, 5, 6]
    assert report["steps"][2]["executor_components"] == ["native_cli", "manual_contract"]
    assert report["steps"][3]["executor_mode"] == "native_cli"
    assert report["steps"][4]["executor_mode"] == "native_cli"

    coach = json.loads((output / "03_monthly_performance_coach_report.json").read_text())
    patterns = json.loads((output / "03_monthly_behavior_patterns.json").read_text())
    backtest = json.loads((output / "04_hypothesis_revalidation.json").read_text())
    skill = json.loads((output / "05_skill_review_findings.json").read_text())

    assert coach["review_id"] == "monthly_2026-05_fictional"
    assert coach["overall_verdict"] == "REVIEW_REQUIRED"
    assert coach["summary"]["confidence"] == "medium"
    assert coach["summary"]["primary_root_cause"] == "thesis_quality"
    assert coach["scores"]["review_quality_score"] == 76
    assert patterns["primary_root_cause"] == "thesis_quality"
    assert patterns["behavioral_pattern_tags"][0]["tag"] == "unknown_size_discipline"

    assert backtest["hypothesis_id"] == "confirmation-pivot-entry"
    assert "total_score" in backtest["evaluation"]
    assert backtest["evaluation"]["verdict"]

    assert skill["skill_name"] == "vcp-screener"
    assert skill["selection_mode"] == "manual"
    assert skill["final_score"] == 93

    decision = json.loads((output / "06_monthly_decision_log.json").read_text())
    assert set(decision["provenance"].keys()) == {
        "aggregate_postmortem",
        "hypothesis_revalidation",
        "skill_review_findings",
    }
    assert len(decision["rule_changes"]) == 3


def test_missing_period_in_closed_theses_fails_without_publication(tmp_path: Path) -> None:
    input_dir = tmp_path / "inputs"
    input_dir.mkdir()
    original = INPUTS / "closed_theses.json"
    altered = input_dir / original.name
    payload = json.loads(original.read_text())
    del payload["period"]
    altered.write_text(json.dumps(payload), encoding="utf-8")

    output = tmp_path / "published"
    output.mkdir()
    sentinel = output / "existing.txt"
    sentinel.write_bytes(b"unchanged\n")

    with pytest.raises(ReplayError) as exc_info:
        execute_replay(
            ROOT,
            SPEC,
            "required-only",
            output,
            input_overrides={"closed_theses": altered},
        )

    assert exc_info.value.completed_steps == []
    assert sentinel.read_bytes() == b"unchanged\n"
    assert {path.name for path in output.iterdir()} == {"existing.txt"}


def test_bad_coach_action_fails_closed(tmp_path: Path) -> None:
    input_dir = tmp_path / "inputs"
    input_dir.mkdir()
    original = INPUTS / "coach_decision.yaml"
    altered = input_dir / original.name
    decision = load_yaml(original)
    decision["action"] = "bogus"
    altered.write_text(yaml.safe_dump(decision, sort_keys=False), encoding="utf-8")

    with pytest.raises(ReplayError, match="not in coach allowed actions") as exc_info:
        execute_replay(
            ROOT,
            SPEC,
            "full-path",
            tmp_path / "outputs" / "coach",
            input_overrides={"coach_decision": altered},
        )

    assert exc_info.value.completed_steps == [1, 2]


def test_invalid_backtest_metrics_fail_closed(tmp_path: Path) -> None:
    input_dir = tmp_path / "inputs"
    input_dir.mkdir()
    original = INPUTS / "backtest_params.json"
    altered = input_dir / original.name
    payload = json.loads(original.read_text())
    payload["win_rate"] = 150
    altered.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ReplayError):
        execute_replay(
            ROOT,
            SPEC,
            "full-path",
            tmp_path / "outputs" / "metrics",
            input_overrides={"backtest_params": altered},
        )


def test_step_six_failure_preserves_existing_destination(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    output = tmp_path / "published"
    output.mkdir()
    sentinel = output / "existing.txt"
    sentinel.write_bytes(b"unchanged\n")
    registration = EXECUTORS["monthly_decision_log"]

    def fail_after_write(*args, **kwargs):
        registration.run(*args, **kwargs)
        raise ReplayError("injected decision-log failure")

    monkeypatch.setitem(
        EXECUTORS,
        "monthly_decision_log",
        replay_module.ExecutorRegistration(
            mode=registration.mode,
            run=fail_after_write,
            components=registration.components,
        ),
    )

    with pytest.raises(ReplayError, match="injected decision-log failure"):
        execute_replay(ROOT, SPEC, "required-only", output)

    assert sentinel.read_bytes() == b"unchanged\n"
    assert {path.name for path in output.iterdir()} == {"existing.txt"}


def test_native_commands_are_offline_and_do_not_launch_uv(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    commands: list[list[str]] = []
    environments: list[dict[str, str]] = []
    real_run = replay_module.subprocess.run

    def capture(command, **kwargs):
        commands.append([str(part) for part in command])
        environments.append(dict(kwargs["env"]))
        return real_run(command, **kwargs)

    monkeypatch.setattr(replay_module.subprocess, "run", capture)
    execute_replay(ROOT, SPEC, "full-path", tmp_path / "published")

    assert commands
    assert all(Path(command[0]).name != "uv" for command in commands)
    assert all(
        not any("http://" in part or "https://" in part for part in command) for command in commands
    )
    assert all(
        not any(
            marker in key.upper()
            for key in environment
            for marker in replay_module.SENSITIVE_ENV_MARKERS
        )
        for environment in environments
    )


def test_monthly_goldens_are_byte_reproducible(tmp_path: Path) -> None:
    for variant, golden_name in (
        ("required-only", "replay-run"),
        ("full-path", "replay-run-full-path"),
    ):
        actual = tmp_path / variant
        execute_replay(ROOT, SPEC, variant, actual)
        assert compare_trees(actual, SPEC.parent / golden_name) == []
