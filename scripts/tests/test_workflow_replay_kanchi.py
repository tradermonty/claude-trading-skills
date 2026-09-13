"""Executable replay coverage for kanchi-dividend-weekly (Issue #294)."""

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
    ReplayError,
    compare_trees,
    execute_replay,
    load_yaml,
)

SPEC = ROOT / "examples" / "workflows" / "kanchi-dividend-weekly" / "replay.yaml"
INPUTS = SPEC.parent / "replay-inputs"
FIXED_DATE = "2026-06-27"


def test_kanchi_spec_has_honest_executor_evidence() -> None:
    summary = replay_module.validate_spec(ROOT, SPEC)

    assert summary["workflow_id"] == "kanchi-dividend-weekly"
    assert summary["variants"] == ["required-only", "full-path"]
    assert summary["native_steps"] == [4, 5]
    assert summary["native_api_steps"] == []
    assert summary["manual_contract_steps"] == [1, 2]
    assert summary["composite_steps"] == [3, 6]
    assert summary["executor_components"] == {
        3: ["native_cli", "native_api", "manual_contract"],
        6: ["manual_contract", "native_api"],
    }


def test_required_only_runs_only_required_steps(tmp_path: Path) -> None:
    output = tmp_path / "required"
    report = execute_replay(ROOT, SPEC, "required-only", output)

    assert report["status"] == "completed"
    assert [row["step"] for row in report["steps"]] == [3, 6]
    assert report["artifact_ids"] == ["kanchi_candidates", "stock_memo", "thesis_record"]
    assert report["network_policy"] == "offline-input-required"

    manifest = load_yaml(output / "manifest.yaml")
    assert manifest["completed_steps"] == [3, 6]
    assert manifest["required_steps_not_executed"] == []
    assert [row["step"] for row in manifest["optional_steps_skipped"]] == [1, 2, 4, 5]


def test_full_path_goldens_match_committed_trees(tmp_path: Path) -> None:
    for variant, golden_name in (
        ("required-only", "sample-run"),
        ("full-path", "sample-run-full-path"),
    ):
        actual = tmp_path / variant
        execute_replay(ROOT, SPEC, variant, actual)
        assert compare_trees(actual, SPEC.parent / golden_name) == []


def test_non_actionable_candidates_are_excluded_from_handoff(tmp_path: Path) -> None:
    output = tmp_path / "required"
    execute_replay(ROOT, SPEC, "required-only", output)

    payload = json.loads((output / "03_kanchi_candidates.json").read_text(encoding="utf-8"))
    actionable = {row["ticker"] for row in payload["candidates"]}
    excluded = {row["ticker"] for row in payload["excluded"]}
    assert actionable == {"EXMPL", "EXMPLB", "EXMPLC"}
    assert excluded == {"EXMPLD", "EXMPLX"}
    assert actionable.isdisjoint(excluded)
    for row in payload["candidates"]:
        assert row["verdict"] in {"CLEAN-PASS", "PASS-CAUTION", "CONDITIONAL-PASS"}
    for row in payload["excluded"]:
        assert row["verdict"] in {"HOLD-REVIEW", "STEP1-RECHECK", "FAIL"}


def test_underwriting_fail_closed_on_verdict_mismatch(tmp_path: Path) -> None:
    evidence = json.loads((INPUTS / "underwriting-evidence.json").read_text(encoding="utf-8"))
    for row in evidence["candidates"]:
        if row["ticker"] == "EXMPL":
            row["step1_verdict"] = "STEP1-RECHECK"
    override = tmp_path / "overrides" / "underwriting-evidence.json"
    override.parent.mkdir()
    override.write_text(json.dumps(evidence), encoding="utf-8")

    with pytest.raises(ReplayError, match="expected_actionable"):
        execute_replay(
            ROOT,
            SPEC,
            "required-only",
            tmp_path / "out",
            input_overrides={"underwriting_evidence": override},
        )


def test_screener_contract_requires_human_approval(tmp_path: Path) -> None:
    payload = json.loads((INPUTS / "high-yield-candidates.json").read_text(encoding="utf-8"))
    payload["human_approved"] = False
    override = tmp_path / "overrides" / "high-yield-candidates.json"
    override.parent.mkdir()
    override.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ReplayError, match="human_approved"):
        execute_replay(
            ROOT,
            SPEC,
            "full-path",
            tmp_path / "out",
            input_overrides={"high_yield_candidates": override},
        )


def test_review_queue_requires_fixed_as_of(tmp_path: Path) -> None:
    payload = json.loads((INPUTS / "review-monitor.json").read_text(encoding="utf-8"))
    payload["as_of"] = "2026-01-01"
    override = tmp_path / "overrides" / "review-monitor.json"
    override.parent.mkdir()
    override.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ReplayError, match="as_of must match"):
        execute_replay(
            ROOT,
            SPEC,
            "full-path",
            tmp_path / "out",
            input_overrides={"review_monitor": override},
        )


def test_registration_pins_fixed_date_and_stays_idea(tmp_path: Path) -> None:
    output = tmp_path / "full"
    execute_replay(ROOT, SPEC, "full-path", output)

    record = json.loads((output / "06_thesis_record.json").read_text(encoding="utf-8"))
    assert [row["ticker"] for row in record["theses"]] == ["EXMPL", "EXMPLB", "EXMPLC"]
    for row in record["theses"]:
        assert row["status"] == "IDEA"
        assert row["created_at"] == f"{FIXED_DATE}T00:00:00+00:00"
        assert row["next_review_date"] == "2026-07-27"
        assert row["linked_reports"][0] == {
            "skill": "kanchi-dividend-sop",
            "file": "$ARTIFACT/03_stock_memo.md",
            "date": FIXED_DATE,
        }


def test_review_queue_never_proposes_a_sell(tmp_path: Path) -> None:
    output = tmp_path / "full"
    execute_replay(ROOT, SPEC, "full-path", output)

    payload = json.loads((output / "05_review_queue.json").read_text(encoding="utf-8"))
    actions = [action for row in payload["results"] for action in row["actions"]]
    assert actions
    assert all("sell" not in action.lower() for action in actions)


def _write_decision_override(tmp_path: Path, name: str, payload: dict) -> Path:
    override_dir = tmp_path / f"{name}-overrides"
    override_dir.mkdir()
    override = override_dir / name
    override.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return override


def test_underwriting_decision_requires_human_approval(tmp_path: Path) -> None:
    payload = load_yaml(INPUTS / "underwriting-decision.yaml")
    payload["human_approved"] = False
    override = _write_decision_override(tmp_path, "underwriting-decision.yaml", payload)

    with pytest.raises(ReplayError, match="human_approved"):
        execute_replay(
            ROOT,
            SPEC,
            "required-only",
            tmp_path / "out",
            input_overrides={"underwriting_decision": override},
        )


def test_register_decision_requires_human_approval(tmp_path: Path) -> None:
    payload = load_yaml(INPUTS / "register-decision.yaml")
    payload["human_approved"] = False
    override = _write_decision_override(tmp_path, "register-decision.yaml", payload)

    with pytest.raises(ReplayError, match="human_approved"):
        execute_replay(
            ROOT,
            SPEC,
            "required-only",
            tmp_path / "out",
            input_overrides={"register_decision": override},
        )


def test_register_decision_rejects_active_promotion(tmp_path: Path) -> None:
    payload = load_yaml(INPUTS / "register-decision.yaml")
    payload["expected_active"] = ["EXMPL"]
    override = _write_decision_override(tmp_path, "register-decision.yaml", payload)

    with pytest.raises(ReplayError, match="must not promote"):
        execute_replay(
            ROOT,
            SPEC,
            "required-only",
            tmp_path / "out",
            input_overrides={"register_decision": override},
        )


def test_manifest_records_native_execution_evidence(tmp_path: Path) -> None:
    required = execute_replay(ROOT, SPEC, "required-only", tmp_path / "required")
    full = execute_replay(ROOT, SPEC, "full-path", tmp_path / "full")
    assert required["status"] == "completed"
    assert full["status"] == "completed"

    required_evidence = load_yaml(tmp_path / "required" / "manifest.yaml")["execution_evidence"]
    assert required_evidence["native_kanchi_verdict_api_executed"] is True
    assert required_evidence["native_trader_memory_register_executed"] is True
    assert required_evidence["native_tax_planning_cli_executed"] is False
    assert required_evidence["native_review_queue_cli_executed"] is False
    assert required_evidence["broker_or_live_api_calls"] is False

    full_evidence = load_yaml(tmp_path / "full" / "manifest.yaml")["execution_evidence"]
    assert full_evidence["native_tax_planning_cli_executed"] is True
    assert full_evidence["native_review_queue_cli_executed"] is True
