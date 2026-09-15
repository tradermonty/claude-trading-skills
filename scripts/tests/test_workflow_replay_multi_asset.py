"""Executable replay coverage for multi-asset-opportunity-daily (Issue #294)."""

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

SPEC = ROOT / "examples" / "workflows" / "multi-asset-opportunity-daily" / "replay.yaml"
INPUTS = SPEC.parent / "replay-inputs"
FIXED_DATE = "2026-08-06"


def test_multi_asset_spec_has_honest_executor_evidence() -> None:
    summary = replay_module.validate_spec(ROOT, SPEC)

    assert summary["workflow_id"] == "multi-asset-opportunity-daily"
    assert summary["variants"] == ["required-only", "full-path"]
    assert summary["native_steps"] == [5]
    assert summary["native_api_steps"] == [1]
    assert summary["manual_contract_steps"] == [2, 3]
    assert summary["composite_steps"] == [4, 6]
    assert summary["executor_components"] == {
        4: ["native_cli", "manual_contract"],
        6: ["manual_contract", "native_api"],
    }


def test_required_only_runs_only_required_steps(tmp_path: Path) -> None:
    output = tmp_path / "required"
    report = execute_replay(ROOT, SPEC, "required-only", output)

    assert report["status"] == "completed"
    assert [row["step"] for row in report["steps"]] == [1, 2, 4, 5, 6]
    assert report["artifact_ids"] == [
        "hot_themes",
        "hypothesis_cards",
        "macro_regime_brief",
        "opportunity_journal_entries",
        "sized_hypotheses",
    ]
    assert report["network_policy"] == "offline-input-required"

    manifest = load_yaml(output / "manifest.yaml")
    assert manifest["completed_steps"] == [1, 2, 4, 5, 6]
    assert manifest["required_steps_not_executed"] == []
    assert [row["step"] for row in manifest["optional_steps_skipped"]] == [3]


def test_full_path_goldens_match_committed_trees(tmp_path: Path) -> None:
    for variant, golden_name in (
        ("required-only", "replay-run"),
        ("full-path", "replay-run-full-path"),
    ):
        actual = tmp_path / variant
        execute_replay(ROOT, SPEC, variant, actual)
        assert compare_trees(actual, SPEC.parent / golden_name) == []


def test_rejected_cards_are_excluded_from_sizing_and_registration(tmp_path: Path) -> None:
    output = tmp_path / "required"
    execute_replay(ROOT, SPEC, "required-only", output)

    cards = json.loads((output / "04_hypothesis_cards.json").read_text(encoding="utf-8"))
    actionable = {row["hypothesis_id"] for row in cards["hypotheses"]}
    excluded = {row["hypothesis_id"] for row in cards["excluded"]}
    assert actionable == {"H-EXMPL-01", "H-EXMPL-02"}
    assert excluded == {"H-FX-01"}
    assert actionable.isdisjoint(excluded)

    sized = json.loads((output / "05_sized_hypotheses.json").read_text(encoding="utf-8"))
    assert {row["hypothesis_id"] for row in sized["sized"]} == actionable

    journal = json.loads(
        (output / "06_opportunity_journal_entries.json").read_text(encoding="utf-8")
    )
    by_id = {row["hypothesis_id"]: row for row in journal["entries"]}
    assert by_id["H-EXMPL-01"]["status"] == "IDEA"
    assert by_id["H-EXMPL-02"]["status"] == "ENTRY_READY"
    assert by_id["H-FX-01"]["status"] == "rejected"
    assert by_id["H-FX-01"]["thesis_id"] is None
    assert by_id["H-FX-01"]["research_only"] is True
    assert all(row["status"] != "ACTIVE" for row in journal["entries"])


def test_gate_accepting_forex_fails_closed(tmp_path: Path) -> None:
    decision = load_yaml(INPUTS / "gate-decision.yaml")
    decision["accepted"].append("H-FX-01")
    decision["rejected"] = []
    override = tmp_path / "overrides" / "gate-decision.yaml"
    override.parent.mkdir()
    override.write_text(yaml.safe_dump(decision, sort_keys=False), encoding="utf-8")

    with pytest.raises(ReplayError, match="research-only"):
        execute_replay(
            ROOT,
            SPEC,
            "required-only",
            tmp_path / "out",
            input_overrides={"gate_decision": override},
        )


def test_theme_contract_requires_human_approval(tmp_path: Path) -> None:
    payload = json.loads((INPUTS / "theme-evidence.json").read_text(encoding="utf-8"))
    payload["human_approved"] = False
    override = tmp_path / "overrides" / "theme-evidence.json"
    override.parent.mkdir()
    override.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ReplayError, match="human_approved"):
        execute_replay(
            ROOT,
            SPEC,
            "required-only",
            tmp_path / "out",
            input_overrides={"theme_evidence": override},
        )


def test_registration_pins_fixed_date_and_stays_idea(tmp_path: Path) -> None:
    output = tmp_path / "full"
    execute_replay(ROOT, SPEC, "full-path", output)

    record = json.loads(
        (output / "06_opportunity_journal_entries.json").read_text(encoding="utf-8")
    )
    assert [row["hypothesis_id"] for row in record["entries"]] == [
        "H-EXMPL-01",
        "H-EXMPL-02",
        "H-FX-01",
    ]
    for row in record["entries"]:
        if row["status"] == "rejected":
            continue
        assert row["linked_reports"], f"missing evidence links for {row['hypothesis_id']}"
    assert record["recorded_at"].startswith(FIXED_DATE)


def test_hypothesis_cards_carry_no_raw_timestamps(tmp_path: Path) -> None:
    output = tmp_path / "full"
    execute_replay(ROOT, SPEC, "full-path", output)

    text = (output / "04_hypothesis_cards.json").read_text(encoding="utf-8")
    assert "generated_at_utc" not in text


def test_source_binding_mismatch_fails_closed(tmp_path: Path) -> None:
    bundle = json.loads((INPUTS / "hypotheses-bundle.json").read_text(encoding="utf-8"))
    bundle["source_binding"]["macro_regime_brief"] = "0" * 64
    override = tmp_path / "overrides" / "hypotheses-bundle.json"
    override.parent.mkdir()
    override.write_text(json.dumps(bundle), encoding="utf-8")

    with pytest.raises(ReplayError, match="source_binding mismatch"):
        execute_replay(
            ROOT,
            SPEC,
            "required-only",
            tmp_path / "out",
            input_overrides={"hypotheses_bundle": override},
        )


def test_register_partition_violation_fails_closed(tmp_path: Path) -> None:
    decision = load_yaml(INPUTS / "register-decision.yaml")
    decision["idea"].append("H-FX-01")
    override = tmp_path / "overrides" / "register-decision.yaml"
    override.parent.mkdir()
    override.write_text(yaml.safe_dump(decision, sort_keys=False), encoding="utf-8")

    with pytest.raises(ReplayError, match="partition exactly"):
        execute_replay(
            ROOT,
            SPEC,
            "required-only",
            tmp_path / "out",
            input_overrides={"register_decision": override},
        )
