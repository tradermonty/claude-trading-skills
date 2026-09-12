"""Executable replay coverage for swing-opportunity-daily (Issue #294)."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import workflow_replay as replay_module  # noqa: E402
from workflow_replay import (  # noqa: E402
    ReplayError,
    compare_trees,
    execute_replay,
    load_yaml,
)

SPEC = ROOT / "examples" / "workflows" / "swing-opportunity-daily" / "replay.yaml"
COVERAGE = ROOT / "examples" / "workflows" / "replay-coverage.yaml"


def test_swing_spec_runs_three_native_cli_steps_and_manual_screens() -> None:
    summary = replay_module.validate_spec(ROOT, SPEC)

    assert summary["workflow_id"] == "swing-opportunity-daily"
    assert summary["native_steps"] == [1, 8, 11]
    assert summary["manual_contract_steps"] == [2, 3, 4, 5, 6, 7, 9, 10]


def test_required_only_replays_core_steps_and_skips_optional(tmp_path: Path) -> None:
    output = tmp_path / "required"
    report = execute_replay(ROOT, SPEC, "required-only", output)

    assert report["status"] == "completed"
    assert report["network_policy"] == "offline-input-required"
    assert [step["executor_mode"] for step in report["steps"]] == [
        "native_cli",
        "manual_contract",
        "manual_contract",
        "native_cli",
        "manual_contract",
        "native_cli",
    ]
    assert [step["gate_policy"] for step in report["steps"]] == ["continue"] * 6

    circuit = json.loads((output / "01_circuit_breaker_decision.json").read_text())
    vcp = json.loads((output / "02_vcp_candidates.json").read_text())
    validated = json.loads((output / "07_validated_setups.json").read_text())
    sizing = json.loads((output / "08_position_sizing.json").read_text())
    journal = load_yaml(output / "10_candidate_journal_entry.yaml")
    discipline = json.loads((output / "11_pre_trade_discipline_decision.json").read_text())

    assert circuit["recommendation"] == "TRADING_ALLOWED"
    assert vcp["candidates"][0]["symbol"] == "EXMPL"
    assert validated["inputs_provided"] == ["vcp_candidates"]
    assert validated["inputs_missing"] == [
        "momentum_burst_candidates",
        "exhaustion_hammer_candidates",
        "canslim_candidates",
        "theme_candidates",
    ]
    assert sizing["final_recommended_shares"] == 200
    assert journal["thesis_id"] == "th_exmpl_gro_20260629_ab12"
    assert journal["origin"]["skill"] == "vcp-screener"
    assert journal["evidence"] == [
        "VCP contractions narrowed from 18% to 10% to 5%.",
        "Manual weekly-chart review passed.",
    ]
    assert discipline["overall_decision"] == "NO_GO"
    assert discipline["candidate_results"][0]["thesis_id"] == "th_exmpl_gro_20260629_ab12"
    assert discipline["candidate_results"][0]["link_status"] == "skipped_no_state_dir"
    assert not (output / "09_trade_plans.json").exists()

    manifest = load_yaml(output / "manifest.yaml")
    assert manifest["completed_steps"] == [1, 2, 7, 8, 10, 11]
    assert manifest["optional_steps_skipped"] == [
        {
            "step": 3,
            "skill": "stockbee-momentum-burst-screener",
            "reason": "required-only executable replay",
        },
        {
            "step": 4,
            "skill": "stockbee-exhaustion-hammer-screener",
            "reason": "required-only executable replay",
        },
        {"step": 5, "skill": "canslim-screener", "reason": "required-only executable replay"},
        {"step": 6, "skill": "theme-detector", "reason": "required-only executable replay"},
        {"step": 9, "skill": "breakout-trade-planner", "reason": "required-only executable replay"},
    ]


def test_full_path_builds_trade_plan_and_corroborating_evidence(tmp_path: Path) -> None:
    output = tmp_path / "full"
    report = execute_replay(ROOT, SPEC, "full-path", output)

    assert report["status"] == "completed"
    plan = json.loads((output / "09_trade_plans.json").read_text())
    journal = load_yaml(output / "10_candidate_journal_entry.yaml")

    assert plan["plans"][0]["limit_price"] == 50.25
    assert plan["plans"][0]["risk_reward_ratio"] == 2.0
    assert plan["plans"][0]["order_status"] == "PROPOSED_NOT_SUBMITTED"
    assert journal["thesis_id"] == "th_exmpl_gro_20260629_cd34"
    assert journal["origin"]["skill"] == "breakout-trade-planner"
    assert journal["evidence"] == [
        "VCP contractions narrowed from 18% to 10% to 5%.",
        "Momentum, CANSLIM, and fictional-theme screens corroborated the candidate.",
        "Manual weekly-chart review passed.",
    ]


def test_invalid_offline_input_fails_without_partial_publication(
    tmp_path: Path,
) -> None:
    input_dir = tmp_path / "inputs"
    input_dir.mkdir()
    invalid = input_dir / "invalid-sizing.json"
    invalid.write_text("{not json\n", encoding="utf-8")
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
            input_overrides={"sizing_parameters": invalid},
        )

    assert exc_info.value.completed_steps == []
    assert sentinel.read_bytes() == b"unchanged\n"
    assert {path.name for path in output.iterdir()} == {"existing.txt"}


def test_mismatched_validated_setup_cross_check_halts(tmp_path: Path) -> None:
    validated = json.loads((SPEC.parent / "replay-inputs/validated-setups.json").read_text())
    validated["setups"][0]["entry_price"] = 51.0
    input_dir = tmp_path / "inputs"
    input_dir.mkdir()
    override = input_dir / "validated-setups.json"
    override.write_text(json.dumps(validated), encoding="utf-8")

    with pytest.raises(ReplayError, match="validated setup entry"):
        execute_replay(
            ROOT,
            SPEC,
            "required-only",
            tmp_path / "published",
            input_overrides={"validated_setups": override},
        )

    assert not (tmp_path / "published").exists()


def test_vcp_candidate_symbol_mismatch_halts_validate_setups(tmp_path: Path) -> None:
    vcp = json.loads((SPEC.parent / "replay-inputs/vcp-scan.json").read_text())
    vcp["candidates"][0]["symbol"] = "OTHER"
    input_dir = tmp_path / "inputs"
    input_dir.mkdir()
    override = input_dir / "vcp-scan.json"
    override.write_text(json.dumps(vcp), encoding="utf-8")

    with pytest.raises(ReplayError, match="does not match any VCP candidate"):
        execute_replay(
            ROOT,
            SPEC,
            "required-only",
            tmp_path / "published",
            input_overrides={"vcp_scan": override},
        )

    assert not (tmp_path / "published").exists()


def test_trade_plan_price_mismatch_halts_discipline_fail_closed(tmp_path: Path) -> None:
    def tamper_after_plan(step: int, artifacts: dict[str, dict]) -> None:
        if step == 9:
            path = Path(artifacts["trade_plans"]["files"]["canonical"])
            plan = json.loads(path.read_text())
            plan["plans"][0]["entry_price"] = 99.0
            path.write_text(json.dumps(plan), encoding="utf-8")

    with pytest.raises(ReplayError, match="trade plan.*inconsistent"):
        execute_replay(
            ROOT,
            SPEC,
            "full-path",
            tmp_path / "published",
            after_step=tamper_after_plan,
        )

    assert not (tmp_path / "published").exists()


def test_required_only_discipline_fails_closed_without_plan(tmp_path: Path) -> None:
    output = tmp_path / "required"
    execute_replay(ROOT, SPEC, "required-only", output)
    discipline = json.loads((output / "11_pre_trade_discipline_decision.json").read_text())

    assert discipline["overall_decision"] == "NO_GO"
    checklist = discipline["candidate_results"][0]["checklist_answers"]
    assert checklist["entry_in_written_plan"] is False
    assert checklist["stop_predefined"] is False
    assert checklist["size_within_plan"] is False


def test_corrupt_state_handoff_stops_before_downstream_and_preserves_output(
    tmp_path: Path,
) -> None:
    output = tmp_path / "published"
    output.mkdir()
    sentinel = output / "existing.txt"
    sentinel.write_bytes(b"unchanged\n")

    def corrupt_after_scan(step: int, artifacts: dict[str, dict]) -> None:
        if step == 7:
            state = Path(artifacts["validated_setups"]["files"]["canonical"])
            state.write_text("{not json\n", encoding="utf-8")

    with pytest.raises(ReplayError) as exc_info:
        execute_replay(
            ROOT,
            SPEC,
            "required-only",
            output,
            after_step=corrupt_after_scan,
        )

    assert exc_info.value.completed_steps == [1, 2, 7]
    assert sentinel.read_bytes() == b"unchanged\n"
    assert {path.name for path in output.iterdir()} == {"existing.txt"}


def test_native_commands_use_only_offline_inputs_and_scrub_sensitive_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[tuple[list[str], dict[str, str]]] = []
    real_run = replay_module.subprocess.run
    monkeypatch.setenv("REPLAY_API_KEY", "secret-value")
    monkeypatch.setenv("REPLAY_PROXY", "http://proxy.invalid")

    def capture_run(command, *args, **kwargs):
        captured.append((list(command), dict(kwargs["env"])))
        return real_run(command, *args, **kwargs)

    monkeypatch.setattr(replay_module.subprocess, "run", capture_run)
    execute_replay(ROOT, SPEC, "required-only", tmp_path / "published")

    assert [command[1].split("/")[-1] for command, _env in captured] == [
        "check_circuit_breaker.py",
        "position_sizer.py",
        "check_pre_trade_discipline.py",
    ]
    for command, env in captured:
        assert not {"--symbols", "--fmp-universe", "--api-key"} & set(command)
        assert "REPLAY_API_KEY" not in env
        assert "REPLAY_PROXY" not in env


@pytest.mark.parametrize(
    ("variant", "golden_dir"),
    (("required-only", "replay-run"), ("full-path", "replay-run-full-path")),
)
def test_swing_goldens_are_byte_reproducible(
    variant: str,
    golden_dir: str,
    tmp_path: Path,
) -> None:
    generated = tmp_path / "generated"
    execute_replay(ROOT, SPEC, variant, generated)
    assert compare_trees(generated, SPEC.parent / golden_dir) == []

    altered = tmp_path / "altered"
    shutil.copytree(SPEC.parent / golden_dir, altered)
    candidate = next(altered.glob("0*_*.json"))
    candidate.write_text("{}\n", encoding="utf-8")
    assert compare_trees(generated, altered)


@pytest.mark.parametrize(
    "output_dir",
    [
        ROOT,
        SPEC,
        SPEC.parent,
        SPEC.parent / "replay-inputs",
        SPEC.parent / "sample-run",
        SPEC.parent / "sample-run-full-path",
        SPEC.parent / "replay-run",
        SPEC.parent / "replay-run-full-path",
    ],
)
def test_runtime_output_cannot_overlap_repo_sources_or_goldens(
    output_dir: Path,
    tmp_path: Path,
) -> None:
    protected_files = [
        SPEC,
        SPEC.parent / "replay-inputs/exposure-decision.json",
        SPEC.parent / "sample-run/manifest.yaml",
        SPEC.parent / "sample-run-full-path/manifest.yaml",
        SPEC.parent / "replay-run/manifest.yaml",
        SPEC.parent / "replay-run-full-path/manifest.yaml",
    ]
    before = {path: path.read_bytes() for path in protected_files}

    with pytest.raises(ReplayError, match="output_dir (?:overlaps protected|must be a directory)"):
        execute_replay(ROOT, SPEC, "required-only", output_dir)

    assert {path: path.read_bytes() for path in protected_files} == before
