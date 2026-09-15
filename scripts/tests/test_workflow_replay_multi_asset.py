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
    for row in sized["sized"]:
        assert row["constraints_applied"] == [
            {
                "binding": False,
                "limit": 20.0,
                "max_shares": row["shares"],
                "type": "max_position_pct",
            }
        ]

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


def test_all_rejected_gate_halts_before_sizing_and_preserves_output(tmp_path: Path) -> None:
    decision = load_yaml(INPUTS / "gate-decision.yaml")
    decision["accepted"] = []
    decision["rejected"] = ["H-EXMPL-01", "H-EXMPL-02", "H-FX-01"]
    override = tmp_path / "overrides" / "gate-decision.yaml"
    override.parent.mkdir()
    override.write_text(yaml.safe_dump(decision, sort_keys=False), encoding="utf-8")

    output = tmp_path / "published"
    output.mkdir()
    sentinel = output / "existing.txt"
    sentinel.write_bytes(b"unchanged\n")

    with pytest.raises(ReplayError, match="hypothesis gate produced no actionable cards") as exc:
        execute_replay(
            ROOT,
            SPEC,
            "required-only",
            output,
            input_overrides={"gate_decision": override},
        )

    assert exc.value.completed_steps == [1, 2]
    assert sentinel.read_bytes() == b"unchanged\n"
    assert {path.name for path in output.iterdir()} == {"existing.txt"}


def test_rejected_equity_is_excluded_without_reloading_raw_fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gate = load_yaml(INPUTS / "gate-decision.yaml")
    gate["accepted"] = ["H-EXMPL-01"]
    gate["rejected"] = ["H-EXMPL-02", "H-FX-01"]
    sizing = json.loads((INPUTS / "sizing-params.json").read_text(encoding="utf-8"))
    sizing["cards"] = [card for card in sizing["cards"] if card["hypothesis_id"] == "H-EXMPL-01"]
    registration = load_yaml(INPUTS / "register-decision.yaml")
    registration["entry_ready"] = []
    registration["rejected"] = ["H-EXMPL-02", "H-FX-01"]

    overrides = tmp_path / "overrides"
    overrides.mkdir()
    gate_path = overrides / "gate-decision.yaml"
    gate_path.write_text(yaml.safe_dump(gate, sort_keys=False), encoding="utf-8")
    sizing_path = overrides / "sizing-params.json"
    sizing_path.write_text(json.dumps(sizing), encoding="utf-8")
    registration_path = overrides / "register-decision.yaml"
    registration_path.write_text(yaml.safe_dump(registration, sort_keys=False), encoding="utf-8")

    raw_path = (INPUTS / "raw-hypotheses.json").resolve()
    raw_loads = 0
    original_load_json = replay_module._load_json

    def count_raw_loads(path: Path, label: str):
        nonlocal raw_loads
        if Path(path).resolve() == raw_path:
            raw_loads += 1
        return original_load_json(path, label)

    monkeypatch.setattr(replay_module, "_load_json", count_raw_loads)
    output = tmp_path / "published"
    execute_replay(
        ROOT,
        SPEC,
        "required-only",
        output,
        input_overrides={
            "gate_decision": gate_path,
            "sizing_params": sizing_path,
            "register_decision": registration_path,
        },
    )

    cards = json.loads((output / "04_hypothesis_cards.json").read_text(encoding="utf-8"))
    assert [row["hypothesis_id"] for row in cards["hypotheses"]] == ["H-EXMPL-01"]
    assert {row["hypothesis_id"] for row in cards["excluded"]} == {
        "H-EXMPL-02",
        "H-FX-01",
    }
    sized = json.loads((output / "05_sized_hypotheses.json").read_text(encoding="utf-8"))
    assert [row["hypothesis_id"] for row in sized["sized"]] == ["H-EXMPL-01"]
    journal = json.loads(
        (output / "06_opportunity_journal_entries.json").read_text(encoding="utf-8")
    )
    assert {row["hypothesis_id"] for row in journal["entries"] if row["status"] == "rejected"} == {
        "H-EXMPL-02",
        "H-FX-01",
    }
    assert raw_loads == 1


def test_corrupt_hypothesis_handoff_halts_sizing_and_preserves_output(tmp_path: Path) -> None:
    output = tmp_path / "published"
    output.mkdir()
    sentinel = output / "existing.txt"
    sentinel.write_bytes(b"unchanged\n")

    def corrupt_after_hypothesis(step: int, artifacts: dict[str, dict]) -> None:
        if step == 4:
            path = Path(artifacts["hypothesis_cards"]["files"]["canonical"])
            path.write_text("{not json\n", encoding="utf-8")

    with pytest.raises(ReplayError) as exc:
        execute_replay(
            ROOT,
            SPEC,
            "required-only",
            output,
            after_step=corrupt_after_hypothesis,
        )

    assert exc.value.completed_steps == [1, 2, 4]
    assert sentinel.read_bytes() == b"unchanged\n"
    assert {path.name for path in output.iterdir()} == {"existing.txt"}


def test_register_revalidates_sized_contract_before_trader_memory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stage = tmp_path / "stage"
    stage.mkdir()
    cards_path = stage / "04_hypothesis_cards.json"
    cards_path.write_text(
        (SPEC.parent / "replay-run" / cards_path.name).read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    sized_path = stage / "05_sized_hypotheses.json"
    sized = json.loads((SPEC.parent / "replay-run" / sized_path.name).read_text(encoding="utf-8"))
    sized["sized"][0]["constraints_applied"] = ["not-an-object"]
    sized_path.write_text(json.dumps(sized), encoding="utf-8")
    consumed = {
        "hypothesis_cards": {"files": {"canonical": str(cards_path)}},
        "sized_hypotheses": {"files": {"canonical": str(sized_path)}},
    }
    spec = load_yaml(SPEC)
    step = next(row for row in spec["steps"] if row["step"] == 6)

    def unexpected_repo_module(*_args, **_kwargs):
        raise AssertionError("trader-memory modules must not load before contract validation")

    monkeypatch.setattr(replay_module, "_repo_module", unexpected_repo_module)
    with pytest.raises(ReplayError, match="invalid multi-asset sized_hypotheses contract"):
        replay_module._multi_register(
            ROOT,
            spec,
            step,
            {"register_decision": INPUTS / "register-decision.yaml"},
            consumed,
            tmp_path / "work",
            stage,
        )


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


def test_raw_hypotheses_duplicate_fails_closed(tmp_path: Path) -> None:
    raw = json.loads((INPUTS / "raw-hypotheses.json").read_text(encoding="utf-8"))
    raw["hypotheses"].append({**raw["hypotheses"][0]})
    override = tmp_path / "overrides" / "raw-hypotheses.json"
    override.parent.mkdir()
    override.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ReplayError, match="duplicate hypothesis ids"):
        execute_replay(
            ROOT,
            SPEC,
            "required-only",
            tmp_path / "out",
            input_overrides={"raw_hypotheses": override},
        )


def test_failed_run_preserves_existing_output_tree(tmp_path: Path) -> None:
    output = tmp_path / "output"
    execute_replay(ROOT, SPEC, "required-only", output)

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
            output,
            input_overrides={"gate_decision": override},
        )

    assert compare_trees(output, SPEC.parent / "replay-run") == []


def test_failed_run_into_missing_dir_creates_nothing(tmp_path: Path) -> None:
    output = tmp_path / "never-created"
    decision = load_yaml(INPUTS / "register-decision.yaml")
    decision["idea"].append("H-FX-01")
    override = tmp_path / "overrides" / "register-decision.yaml"
    override.parent.mkdir()
    override.write_text(yaml.safe_dump(decision, sort_keys=False), encoding="utf-8")

    with pytest.raises(ReplayError):
        execute_replay(
            ROOT,
            SPEC,
            "required-only",
            output,
            input_overrides={"register_decision": override},
        )

    assert not output.exists()


def test_sized_hypotheses_apply_max_position_cap(tmp_path: Path) -> None:
    params = json.loads((INPUTS / "sizing-params.json").read_text(encoding="utf-8"))
    params["account_size"] = 10000
    params["max_position_pct"] = 1.0
    override = tmp_path / "overrides" / "sizing-params.json"
    override.parent.mkdir()
    override.write_text(json.dumps(params), encoding="utf-8")

    output = tmp_path / "out"
    execute_replay(
        ROOT,
        SPEC,
        "required-only",
        output,
        input_overrides={"sizing_params": override},
    )

    sized = json.loads((output / "05_sized_hypotheses.json").read_text(encoding="utf-8"))
    assert [(row["shares"], row["position_value"]) for row in sized["sized"]] == [
        (1, 100.0),
        (2, 100.0),
    ]
    for row in sized["sized"]:
        assert row["constraints_applied"] == [
            {
                "binding": True,
                "limit": 1.0,
                "max_shares": row["shares"],
                "type": "max_position_pct",
            }
        ]
