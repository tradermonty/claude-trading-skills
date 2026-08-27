"""Executable replay coverage for trade-memory-loop (Issue #294)."""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime
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
    generate_goldens,
    load_yaml,
)

SPEC = ROOT / "examples" / "workflows" / "trade-memory-loop" / "replay.yaml"
COVERAGE = ROOT / "examples" / "workflows" / "replay-coverage.yaml"


def test_trade_memory_spec_has_honest_executor_evidence() -> None:
    summary = replay_module.validate_spec(ROOT, SPEC)

    assert summary["workflow_id"] == "trade-memory-loop"
    assert summary["native_steps"] == [1, 4]
    assert summary["composite_steps"] == [2, 3, 5]
    assert summary["manual_contract_steps"] == []
    assert summary["executor_components"] == {
        2: ["native_api", "manual_contract"],
        3: ["native_cli", "manual_contract"],
        5: ["native_api", "manual_contract"],
    }


def test_coverage_includes_trade_memory_at_four_of_eleven() -> None:
    summary = replay_module.validate_coverage(ROOT, COVERAGE)

    assert summary["covered"] == [
        "market-regime-daily",
        "stockbee-20pct-study-daily",
        "stockbee-fluency-loop",
        "trade-memory-loop",
    ]
    assert len(summary["deferred"]) == 7
    assert "trade-memory-loop" not in summary["deferred"]


def test_required_only_closes_classifies_and_journals(tmp_path: Path) -> None:
    output = tmp_path / "required"
    report = execute_replay(ROOT, SPEC, "required-only", output)

    assert report["status"] == "completed"
    assert [step["step"] for step in report["steps"]] == [1, 2, 5]
    assert [step["executor_mode"] for step in report["steps"]] == [
        "native_cli",
        "composite",
        "composite",
    ]
    closed = load_yaml(output / "01_closed_thesis_record.yaml")
    findings = json.loads((output / "02_postmortem_findings.json").read_text())
    updated = load_yaml(output / "05_closed_thesis_with_lessons.yaml")
    lessons = (output / "05_lessons_log_entry.md").read_text()

    assert closed["status"] == "CLOSED"
    assert closed["outcome"]["pnl_dollars"] == pytest.approx(1841.0)
    created_at = datetime.fromisoformat(closed["created_at"])
    idea_at = datetime.fromisoformat(closed["status_history"][0]["at"])
    entered_at = datetime.fromisoformat(closed["entry"]["actual_date"])
    assert created_at == idea_at
    assert created_at <= entered_at
    assert findings["native_postmortem"]["outcome_category"] == "TRUE_POSITIVE"
    assert findings["manual_root_cause"]["classification"] == "thesis_quality"
    assert findings["provenance"]["native_classification_basis"] == (
        "fixture_supplied_realized_returns"
    )
    assert findings["source_snapshot"]["closed_thesis_record"] == closed
    assert updated["outcome"]["lessons_learned"] in lessons
    assert updated["outcome"]["mae_pct"] is None
    assert updated["outcome"]["mfe_pct"] is None
    assert updated["created_at"] == closed["created_at"] == closed["status_history"][0]["at"]
    assert datetime.fromisoformat(updated["created_at"]) <= datetime.fromisoformat(
        updated["entry"]["actual_date"]
    )

    manifest = load_yaml(output / "manifest.yaml")
    assert manifest["completed_steps"] == [1, 2, 5]
    assert [item["step"] for item in manifest["optional_steps_skipped"]] == [3, 4]
    assert manifest["execution_evidence_limitations"]


def test_full_path_runs_coach_and_evaluates_fixture_metrics(tmp_path: Path) -> None:
    output = tmp_path / "full"
    report = execute_replay(ROOT, SPEC, "full-path", output)

    assert [step["step"] for step in report["steps"]] == [1, 2, 3, 4, 5]
    assert report["steps"][2]["executor_components"] == [
        "native_cli",
        "manual_contract",
    ]
    coach = json.loads((output / "03_performance_coach_report.json").read_text())
    rules = load_yaml(output / "03_next_session_operating_rules.yaml")
    backtest = json.loads((output / "04_backtest_validation.json").read_text())
    updated = load_yaml(output / "05_closed_thesis_with_lessons.yaml")

    assert coach["review_id"] == "trade-memory-loop-fictional-exmpl"
    assert coach["overall_verdict"] == "REVIEW_REQUIRED"
    assert coach["summary"]["confidence"] == "low"
    assert coach["scores"]["review_quality_score"] == 52
    assert coach["risk_manager_notes"][0]["severity"] == "warning"
    assert coach["behavioral_pattern_tags"][0]["tag"] == "unknown_size_discipline"
    assert rules["human_approved"] is True
    assert rules["action"] == "accept_rules"
    assert (
        rules["provenance"]["coach_report_sha256"]
        == hashlib.sha256((output / "03_performance_coach_report.json").read_bytes()).hexdigest()
    )
    assert backtest["provenance"]["execution"] == "native_cli_evaluated_fixture_metrics"
    assert "postmortem_source_sha256" in backtest["provenance"]["adapter_bound_source_sha256"]
    assert updated["outcome"]["lessons_learned"] == (
        "Keep the 10-EMA trail as a research rule with the evaluated caveats; "
        "do not treat this fictional sample as live validation."
    )
    closed = load_yaml(output / "01_closed_thesis_record.yaml")
    assert updated["created_at"] == closed["created_at"] == closed["status_history"][0]["at"]
    assert datetime.fromisoformat(updated["created_at"]) <= datetime.fromisoformat(
        updated["entry"]["actual_date"]
    )


@pytest.mark.parametrize(
    "input_name",
    ["active_thesis", "realized_returns", "root_cause_decision"],
)
def test_invalid_or_stale_postmortem_inputs_fail_without_publication(
    input_name: str, tmp_path: Path
) -> None:
    original = (
        SPEC.parent
        / "replay-inputs"
        / {
            "active_thesis": "active_thesis.yaml",
            "realized_returns": "realized_returns.json",
            "root_cause_decision": "root_cause_decision.yaml",
        }[input_name]
    )
    altered = tmp_path / original.name
    if input_name == "active_thesis":
        altered.write_text("status: ACTIVE\n", encoding="utf-8")
    elif input_name == "realized_returns":
        payload = json.loads(original.read_text())
        payload["returns"]["5d"] = -0.5
        altered.write_text(json.dumps(payload), encoding="utf-8")
    else:
        payload = load_yaml(original)
        payload["expected_source_sha256"]["native_postmortem_record"] = "0" * 64
        altered.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    output = tmp_path / "published"
    output.mkdir()
    sentinel = output / "existing.txt"
    sentinel.write_bytes(b"unchanged\n")

    with pytest.raises(ReplayError):
        execute_replay(
            ROOT,
            SPEC,
            "required-only",
            output,
            input_overrides={input_name: altered},
        )

    assert sentinel.read_bytes() == b"unchanged\n"
    assert {path.name for path in output.iterdir()} == {"existing.txt"}


def test_full_lessons_approval_cannot_be_used_for_required_only(tmp_path: Path) -> None:
    with pytest.raises(ReplayError, match="lessons decision variant"):
        execute_replay(
            ROOT,
            SPEC,
            "required-only",
            tmp_path / "published",
            input_overrides={
                "lessons_required": SPEC.parent / "replay-inputs" / "lessons_full.yaml"
            },
        )


def test_corrupt_postmortem_handoff_stops_before_optional_consumers(tmp_path: Path) -> None:
    output = tmp_path / "published"

    def corrupt_after_postmortem(step: int, artifacts: dict[str, dict]) -> None:
        if step == 2:
            path = Path(artifacts["postmortem_findings"]["files"]["canonical"])
            path.write_text("{not-json\n", encoding="utf-8")

    with pytest.raises(ReplayError) as exc_info:
        execute_replay(
            ROOT,
            SPEC,
            "full-path",
            output,
            after_step=corrupt_after_postmortem,
        )

    assert exc_info.value.completed_steps == [1, 2]
    assert not output.exists()


def test_tampered_closed_snapshot_fails_before_journal_publication(tmp_path: Path) -> None:
    output = tmp_path / "published"
    output.mkdir()
    sentinel = output / "existing.txt"
    sentinel.write_bytes(b"unchanged\n")
    input_dir = tmp_path / "inputs"
    input_dir.mkdir()
    lessons_path = input_dir / "lessons.yaml"
    lessons = load_yaml(SPEC.parent / "replay-inputs" / "lessons_required.yaml")

    def tamper_snapshot(step: int, artifacts: dict[str, dict]) -> None:
        if step == 2:
            path = Path(artifacts["postmortem_findings"]["files"]["canonical"])
            payload = json.loads(path.read_text())
            payload["source_snapshot"]["closed_thesis_record"]["ticker"] = "TAMPER"
            path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            lessons["source_sha256"]["postmortem_findings"] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
            lessons_path.write_text(yaml.safe_dump(lessons, sort_keys=False), encoding="utf-8")

    with pytest.raises(ReplayError, match="snapshot SHA-256 mismatch") as exc_info:
        execute_replay(
            ROOT,
            SPEC,
            "required-only",
            output,
            input_overrides={"lessons_required": lessons_path},
            after_step=tamper_snapshot,
        )

    assert exc_info.value.completed_steps == [1, 2]
    assert sentinel.read_bytes() == b"unchanged\n"
    assert {path.name for path in output.iterdir()} == {"existing.txt"}


def test_stale_coach_decision_and_malformed_metrics_fail_closed(tmp_path: Path) -> None:
    coach = load_yaml(SPEC.parent / "replay-inputs" / "coach_decision.yaml")
    coach["expected_source_sha256"]["coach_report"] = "0" * 64
    coach_input_dir = tmp_path / "inputs" / "coach"
    coach_input_dir.mkdir(parents=True)
    stale_coach = coach_input_dir / "stale-coach.yaml"
    stale_coach.write_text(yaml.safe_dump(coach, sort_keys=False), encoding="utf-8")

    with pytest.raises(ReplayError, match="coach decision source_sha256") as exc_info:
        execute_replay(
            ROOT,
            SPEC,
            "full-path",
            tmp_path / "outputs" / "coach",
            input_overrides={"coach_decision": stale_coach},
        )
    assert exc_info.value.completed_steps == [1, 2]

    coach = load_yaml(SPEC.parent / "replay-inputs" / "coach_decision.yaml")
    coach["action"] = "journal_only"
    inconsistent_action = coach_input_dir / "inconsistent-action.yaml"
    inconsistent_action.write_text(yaml.safe_dump(coach, sort_keys=False), encoding="utf-8")
    with pytest.raises(ReplayError, match="cannot accept rules") as exc_info:
        execute_replay(
            ROOT,
            SPEC,
            "full-path",
            tmp_path / "outputs" / "inconsistent-action",
            input_overrides={"coach_decision": inconsistent_action},
        )
    assert exc_info.value.completed_steps == [1, 2]

    coach = load_yaml(SPEC.parent / "replay-inputs" / "coach_decision.yaml")
    coach["accepted_rules"] = ["Invent a rule that the native coach did not propose."]
    invented_rule = coach_input_dir / "invented-rule.yaml"
    invented_rule.write_text(yaml.safe_dump(coach, sort_keys=False), encoding="utf-8")
    with pytest.raises(ReplayError, match="must come from the native coach report") as exc_info:
        execute_replay(
            ROOT,
            SPEC,
            "full-path",
            tmp_path / "outputs" / "invented-rule",
            input_overrides={"coach_decision": invented_rule},
        )
    assert exc_info.value.completed_steps == [1, 2]

    metrics_input_dir = tmp_path / "inputs" / "metrics"
    metrics_input_dir.mkdir(parents=True)
    bad_metrics = metrics_input_dir / "bad-metrics.json"
    bad_metrics.write_text('{"total_trades": 87}\n', encoding="utf-8")
    with pytest.raises(ReplayError, match="backtest metrics") as exc_info:
        execute_replay(
            ROOT,
            SPEC,
            "full-path",
            tmp_path / "outputs" / "metrics",
            input_overrides={"backtest_metrics": bad_metrics},
        )
    assert exc_info.value.completed_steps == [1, 2, 3]


def test_manual_and_offline_contracts_reject_invalid_values(tmp_path: Path) -> None:
    input_dir = tmp_path / "inputs"
    input_dir.mkdir()
    realized = json.loads((SPEC.parent / "replay-inputs" / "realized_returns.json").read_text())
    realized["returns"]["5d"] = float("nan")
    bad_realized = input_dir / "bad-realized.json"
    bad_realized.write_text(json.dumps(realized), encoding="utf-8")
    with pytest.raises(ReplayError, match="realized returns 5d must be finite"):
        execute_replay(
            ROOT,
            SPEC,
            "required-only",
            tmp_path / "outputs" / "realized",
            input_overrides={"realized_returns": bad_realized},
        )

    root_cause = load_yaml(SPEC.parent / "replay-inputs" / "root_cause_decision.yaml")
    root_cause["classification"] = "luck"
    bad_root_cause = input_dir / "bad-root-cause.yaml"
    bad_root_cause.write_text(yaml.safe_dump(root_cause, sort_keys=False), encoding="utf-8")
    with pytest.raises(ReplayError, match="classification is invalid"):
        execute_replay(
            ROOT,
            SPEC,
            "required-only",
            tmp_path / "outputs" / "root-cause",
            input_overrides={"root_cause_decision": bad_root_cause},
        )

    metrics = json.loads((SPEC.parent / "replay-inputs" / "backtest_metrics.json").read_text())
    metrics["win_rate"] = 101
    bad_metrics = input_dir / "bad-range-metrics.json"
    bad_metrics.write_text(json.dumps(metrics), encoding="utf-8")
    with pytest.raises(ReplayError, match="backtest win_rate must be <= 100"):
        execute_replay(
            ROOT,
            SPEC,
            "full-path",
            tmp_path / "outputs" / "metric-range",
            input_overrides={"backtest_metrics": bad_metrics},
        )


def test_step_five_failure_preserves_existing_destination(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    output = tmp_path / "published"
    output.mkdir()
    sentinel = output / "existing.txt"
    sentinel.write_bytes(b"unchanged\n")
    registration = EXECUTORS["trade_memory_lessons"]

    def fail_after_write(*args, **kwargs):
        registration.run(*args, **kwargs)
        raise ReplayError("injected journal failure")

    monkeypatch.setitem(
        EXECUTORS,
        "trade_memory_lessons",
        replay_module.ExecutorRegistration(
            mode=registration.mode,
            run=fail_after_write,
            components=registration.components,
        ),
    )

    with pytest.raises(ReplayError, match="injected journal failure"):
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


def test_trade_memory_goldens_are_byte_reproducible(tmp_path: Path) -> None:
    for variant, golden_name in (
        ("required-only", "sample-run"),
        ("full-path", "sample-run-full-path"),
    ):
        actual = tmp_path / variant
        execute_replay(ROOT, SPEC, variant, actual)
        assert compare_trees(actual, SPEC.parent / golden_name) == []


def test_generate_stages_all_covered_goldens_without_publishing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Main check is the production command; this assertion makes the dedicated
    # test fail loudly if generation ceases to stage every covered variant. Keep
    # the unit test read-only; the external verification command tests publication.
    staged_destinations: list[str] = []

    def capture_publication(staged_trees: list[tuple[Path, Path]]) -> None:
        staged_destinations.extend(destination.name for _stage, destination in staged_trees)

    monkeypatch.setattr(replay_module, "_publish_trees_transactionally", capture_publication)
    result = generate_goldens(ROOT, COVERAGE)
    assert result["generated"] == [
        "market-regime-daily:required-only",
        "market-regime-daily:full-path",
        "stockbee-20pct-study-daily:required-only",
        "stockbee-20pct-study-daily:full-path",
        "stockbee-fluency-loop:required-only",
        "stockbee-fluency-loop:full-path",
        "trade-memory-loop:required-only",
        "trade-memory-loop:full-path",
    ]
    assert staged_destinations == [
        "sample-run",
        "sample-run-full-path",
        "sample-run",
        "sample-run-full-path",
        "sample-run",
        "sample-run-full-path",
        "sample-run",
        "sample-run-full-path",
    ]
