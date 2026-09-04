"""Executable replay coverage for core-portfolio-weekly (Issue #294)."""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import workflow_replay as replay_module  # noqa: E402
from workflow_replay import (  # noqa: E402
    ExecutorRegistration,
    ReplayError,
    compare_trees,
    execute_replay,
    load_yaml,
)

SPEC = ROOT / "examples" / "workflows" / "core-portfolio-weekly" / "replay.yaml"
INPUTS = SPEC.parent / "replay-inputs"


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def _write_yaml(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def test_core_portfolio_spec_preserves_evidence_classification() -> None:
    summary = replay_module.validate_spec(ROOT, SPEC)

    assert summary["workflow_id"] == "core-portfolio-weekly"
    assert summary["manual_contract_steps"] == [1, 2, 4, 5]
    assert summary["native_api_steps"] == [3]
    assert summary["native_steps"] == []
    assert summary["composite_steps"] == []


@pytest.mark.parametrize(
    ("variant", "expected_steps", "dividend_status", "native_dividend"),
    [
        ("required-only", [1, 2, 4, 5], "NOT_RUN", False),
        ("full-path", [1, 2, 3, 4, 5], "WARN", True),
    ],
)
def test_variants_replay_handoffs_without_authorizing_execution(
    variant: str,
    expected_steps: list[int],
    dividend_status: str,
    native_dividend: bool,
    tmp_path: Path,
) -> None:
    output = tmp_path / variant
    report = execute_replay(ROOT, SPEC, variant, output)

    assert report["status"] == "completed"
    assert [row["step"] for row in report["steps"]] == expected_steps
    rebalance = load_yaml(output / "04_rebalance_actions.yaml")
    journal = load_yaml(output / "05_weekly_journal_entry.yaml")
    manifest = load_yaml(output / "manifest.yaml")
    evidence = manifest["execution_evidence"]

    assert rebalance["dividend_review"]["status"] == dividend_status
    assert rebalance["manual_execution_required"] is True
    assert all(row["status"] == "PROPOSED_NOT_SUBMITTED" for row in rebalance["actions"])
    assert all(row["broker_status"] == "NOT_SUBMITTED" for row in journal["proposed_actions"])
    assert journal["human_confirmation"]["execution_authorized"] is False
    assert evidence == {
        "native_portfolio_manager_executed": False,
        "native_trader_memory_append_executed": False,
        "native_dividend_rule_api_executed": native_dividend,
        "broker_or_live_api_calls": False,
        "execution_authorized": False,
    }
    if variant == "full-path":
        expected_response = "PAUSE_OPTIONAL_ADDS_PENDING_HUMAN_REVIEW"
        assert rebalance["dividend_review"]["trigger"] == "T2"
        assert rebalance["dividend_review"]["response"] == expected_response
        assert journal["dividend_review"]["response"] == expected_response


@pytest.mark.parametrize("variant", ["required-only", "full-path"])
def test_generated_outputs_match_committed_goldens(variant: str, tmp_path: Path) -> None:
    output = tmp_path / variant
    execute_replay(ROOT, SPEC, variant, output)
    golden_name = "sample-run" if variant == "required-only" else "sample-run-full-path"
    assert compare_trees(output, SPEC.parent / golden_name) == []


def test_required_only_does_not_read_optional_dividend_input(tmp_path: Path) -> None:
    invalid = tmp_path / "inputs" / "dividend.json"
    invalid.parent.mkdir()
    invalid.write_text("{not-json\n", encoding="utf-8")

    report = execute_replay(
        ROOT,
        SPEC,
        "required-only",
        tmp_path / "published",
        input_overrides={"dividend_enrichment": invalid},
    )

    assert [row["step"] for row in report["steps"]] == [1, 2, 4, 5]


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda payload: payload.pop("as_of"), "as_of"),
        (lambda payload: payload["account"].update({"cash": True}), "cash"),
        (
            lambda payload: payload["positions"].append(dict(payload["positions"][0])),
            "symbols must be unique",
        ),
        (
            lambda payload: payload["positions"][0].update({"current_price": float("nan")}),
            "finite",
        ),
        (lambda payload: payload.update({"as_of": "2026-06-26"}), "fixed_timestamp"),
    ],
)
def test_invalid_snapshot_fails_before_publication(
    mutation,
    message: str,
    tmp_path: Path,
) -> None:
    payload = json.loads((INPUTS / "holdings-snapshot.json").read_text())
    mutation(payload)
    changed = _write_json(tmp_path / "inputs" / "snapshot.json", payload)
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
            input_overrides={"holdings_snapshot": changed},
        )

    assert exc_info.value.completed_steps == []
    assert {path.name: path.read_bytes() for path in output.iterdir()} == {"keep.txt": b"keep\n"}


def test_changed_snapshot_symbol_cannot_bypass_dividend_join(tmp_path: Path) -> None:
    snapshot = json.loads((INPUTS / "holdings-snapshot.json").read_text())
    snapshot["positions"][2]["symbol"] = "FICTD"
    snapshot_path = _write_json(tmp_path / "inputs" / "snapshot.json", snapshot)
    snapshot_sha = hashlib.sha256(snapshot_path.read_bytes()).hexdigest()
    allocation = load_yaml(INPUTS / "allocation-decision.yaml")
    allocation["snapshot_sha256"] = snapshot_sha
    allocation["targets"][2]["bucket"] = "FICTD"
    allocation_path = _write_yaml(tmp_path / "inputs" / "allocation.yaml", allocation)
    dividend = json.loads((INPUTS / "dividend-enrichment.json").read_text())
    dividend["snapshot_sha256"] = snapshot_sha
    dividend_path = _write_json(tmp_path / "inputs" / "dividend.json", dividend)

    with pytest.raises(ReplayError, match="snapshot symbol subset") as exc_info:
        execute_replay(
            ROOT,
            SPEC,
            "full-path",
            tmp_path / "published",
            input_overrides={
                "holdings_snapshot": snapshot_path,
                "allocation_decision": allocation_path,
                "dividend_enrichment": dividend_path,
            },
        )

    assert exc_info.value.completed_steps == [1, 2]


def test_snapshot_formatting_does_not_break_canonical_sha_binding(tmp_path: Path) -> None:
    snapshot = json.loads((INPUTS / "holdings-snapshot.json").read_text())
    snapshot_path = tmp_path / "inputs" / "snapshot-minified.json"
    snapshot_path.parent.mkdir()
    snapshot_path.write_text(json.dumps(snapshot, separators=(",", ":")), encoding="utf-8")

    report = execute_replay(
        ROOT,
        SPEC,
        "full-path",
        tmp_path / "published",
        input_overrides={"holdings_snapshot": snapshot_path},
    )

    assert report["status"] == "completed"
    assert [row["step"] for row in report["steps"]] == [1, 2, 3, 4, 5]


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda payload: payload.pop("as_of"), "as_of"),
        (lambda payload: payload.update({"as_of": "2026-06-26"}), "fixed_timestamp"),
        (lambda payload: payload.update({"holdings": []}), "non-empty"),
        (
            lambda payload: payload["holdings"][0]["cashflow"].update({"fcf": True}),
            "fcf",
        ),
        (
            lambda payload: payload["holdings"][0]["cashflow"].update({"fcf": float("inf")}),
            "finite",
        ),
        (
            lambda payload: payload["holdings"].append(dict(payload["holdings"][0])),
            "match covered_tickers exactly",
        ),
        (
            lambda payload: payload.update({"snapshot_sha256": "0" * 64}),
            "snapshot_sha256",
        ),
    ],
)
def test_invalid_dividend_enrichment_fails_closed(
    mutation,
    message: str,
    tmp_path: Path,
) -> None:
    payload = json.loads((INPUTS / "dividend-enrichment.json").read_text())
    mutation(payload)
    changed = _write_json(tmp_path / "inputs" / "dividend.json", payload)
    output = tmp_path / "published"
    output.mkdir()
    sentinel = output / "keep.txt"
    sentinel.write_text("keep\n", encoding="utf-8")

    with pytest.raises(ReplayError, match=message) as exc_info:
        execute_replay(
            ROOT,
            SPEC,
            "full-path",
            output,
            input_overrides={"dividend_enrichment": changed},
        )

    assert exc_info.value.completed_steps == [1, 2]
    assert sentinel.read_bytes() == b"keep\n"
    assert {path.name for path in output.iterdir()} == {"keep.txt"}


def test_corrupt_allocation_handoff_stops_before_rebalance(tmp_path: Path) -> None:
    output = tmp_path / "published"
    output.mkdir()
    (output / "keep.txt").write_text("keep\n", encoding="utf-8")

    def corrupt(step: int, artifacts: dict[str, dict]) -> None:
        if step == 2:
            path = Path(artifacts["allocation_report"]["files"]["canonical"])
            payload = json.loads(path.read_text())
            payload["allocation_total_pct"] = 99.0
            _write_json(path, payload)

    with pytest.raises(ReplayError, match="recomputed arithmetic") as exc_info:
        execute_replay(ROOT, SPEC, "full-path", output, after_step=corrupt)

    assert exc_info.value.completed_steps == [1, 2, 3]
    assert {path.name for path in output.iterdir()} == {"keep.txt"}


def test_tampered_dividend_handoff_stops_before_rebalance(tmp_path: Path) -> None:
    output = tmp_path / "published"
    output.mkdir()
    (output / "keep.txt").write_text("keep\n", encoding="utf-8")

    def corrupt(step: int, artifacts: dict[str, dict]) -> None:
        if step == 3:
            path = Path(artifacts["dividend_review_findings"]["files"]["canonical"])
            payload = json.loads(path.read_text())
            payload["results"][0]["status"] = "OK"
            _write_json(path, payload)

    with pytest.raises(ReplayError, match="native recomputation") as exc_info:
        execute_replay(ROOT, SPEC, "full-path", output, after_step=corrupt)

    assert exc_info.value.completed_steps == [1, 2, 3]
    assert {path.name for path in output.iterdir()} == {"keep.txt"}


def test_duplicate_rebalance_action_id_fails_closed(tmp_path: Path) -> None:
    decision = load_yaml(INPUTS / "rebalance-decision-required.yaml")
    decision["actions"].append(dict(decision["actions"][0]))
    changed = _write_yaml(tmp_path / "inputs" / "rebalance.yaml", decision)

    with pytest.raises(ReplayError, match="action_id values must be unique") as exc_info:
        execute_replay(
            ROOT,
            SPEC,
            "required-only",
            tmp_path / "published",
            input_overrides={"rebalance_decision_required": changed},
        )

    assert exc_info.value.completed_steps == [1, 2]


def test_required_only_rejects_optional_dividend_response(tmp_path: Path) -> None:
    decision = load_yaml(INPUTS / "rebalance-decision-required.yaml")
    decision["dividend_response"] = "PAUSE_OPTIONAL_ADDS_PENDING_HUMAN_REVIEW"
    changed = _write_yaml(tmp_path / "inputs" / "rebalance.yaml", decision)

    with pytest.raises(ReplayError, match="must not include.*dividend response") as exc_info:
        execute_replay(
            ROOT,
            SPEC,
            "required-only",
            tmp_path / "published",
            input_overrides={"rebalance_decision_required": changed},
        )

    assert exc_info.value.completed_steps == [1, 2]


def test_halted_full_path_does_not_claim_native_dividend_execution(tmp_path: Path) -> None:
    spec_dir = tmp_path / "spec"
    shutil.copytree(SPEC.parent / "replay-inputs", spec_dir / "replay-inputs")
    spec = load_yaml(SPEC)
    next(row for row in spec["steps"] if row["step"] == 2)["gate_policy"] = "halt"
    changed_spec = _write_yaml(spec_dir / "replay.yaml", spec)

    report = execute_replay(ROOT, changed_spec, "full-path", tmp_path / "published")
    manifest = load_yaml(tmp_path / "published" / "manifest.yaml")

    assert report["status"] == "halted"
    assert [row["step"] for row in report["steps"]] == [1, 2]
    assert manifest["execution_evidence"]["native_dividend_rule_api_executed"] is False


def test_final_journal_tamper_is_not_published(tmp_path: Path) -> None:
    output = tmp_path / "published"
    output.mkdir()
    (output / "keep.txt").write_text("keep\n", encoding="utf-8")

    def corrupt(step: int, artifacts: dict[str, dict]) -> None:
        if step == 5:
            path = Path(artifacts["weekly_journal_entry"]["files"]["canonical"])
            path.write_text(path.read_text() + "tampered: true\n", encoding="utf-8")

    with pytest.raises(ReplayError, match="final artifact integrity mismatch") as exc_info:
        execute_replay(ROOT, SPEC, "required-only", output, after_step=corrupt)

    assert exc_info.value.completed_steps == [1, 2, 4, 5]
    assert {path.name for path in output.iterdir()} == {"keep.txt"}


@pytest.mark.parametrize(
    ("variant", "completed"),
    [
        ("required-only", [1, 2, 4]),
        ("full-path", [1, 2, 3, 4]),
    ],
)
def test_journal_failure_preserves_existing_destination(
    variant: str,
    completed: list[int],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output = tmp_path / "published"
    output.mkdir()
    sentinel = output / "keep.txt"
    sentinel.write_text("keep\n", encoding="utf-8")

    def fail_journal(*_args, **_kwargs):
        raise ReplayError("injected journal write failure")

    monkeypatch.setitem(
        replay_module.EXECUTORS,
        "core_portfolio_journal",
        ExecutorRegistration("manual_contract", fail_journal),
    )
    with pytest.raises(ReplayError, match="injected journal write failure") as exc_info:
        execute_replay(ROOT, SPEC, variant, output)

    assert exc_info.value.completed_steps == completed
    assert {path.name: path.read_bytes() for path in output.iterdir()} == {"keep.txt": b"keep\n"}


def test_core_replay_never_uses_subprocess_or_live_broker(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def fail_subprocess(*_args, **_kwargs):
        raise AssertionError("core replay must not invoke a subprocess")

    monkeypatch.setattr(replay_module.subprocess, "run", fail_subprocess)
    execute_replay(ROOT, SPEC, "full-path", tmp_path / "published")
