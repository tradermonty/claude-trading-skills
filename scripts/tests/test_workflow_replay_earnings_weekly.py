"""Offline replay contract for the earnings-weekly workflow (Issue #216)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from workflow_replay import ReplayError, execute_replay, validate_spec  # noqa: E402

SPEC = ROOT / "examples/workflows/earnings-weekly/replay.yaml"
INPUTS = SPEC.parent / "replay-inputs"
RUNNER = ROOT / "scripts/replay_offline_fmp_cli.py"
FIXTURE = INPUTS / "fmp-fixture.json"


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _override(tmp_path: Path, name: str, payload: dict) -> Path:
    path = tmp_path / "inputs" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    return path


def test_spec_matches_manifest_and_classifies_executor_evidence() -> None:
    summary = validate_spec(ROOT, SPEC)

    assert summary["workflow_id"] == "earnings-weekly"
    assert summary["native_steps"] == [1, 2, 3, 5, 7]
    assert summary["manual_contract_steps"] == [4]
    assert summary["composite_steps"] == [6]
    assert summary["executor_components"] == {6: ["manual_contract", "native_api"]}


def test_replay_runs_real_clis_on_the_fictional_fixture_and_binds_every_handoff(
    tmp_path: Path,
) -> None:
    output = tmp_path / "replay"
    report = execute_replay(ROOT, SPEC, "required-only", output)

    assert report["status"] == "completed"
    assert [step["step"] for step in report["steps"]] == [1, 2, 3, 4, 5, 6, 7]

    analysis = _load_json(output / "02_earnings_trade_analysis.json")
    pead = _load_json(output / "03_pead_screen.json")
    validated = _load_json(output / "04_validated_earnings_setups.json")
    sizing = _load_json(output / "05_earnings_position_sizing.json")
    journal = _load_json(output / "06_earnings_journal_entry.json")
    decision = _load_json(output / "07_pre_trade_discipline_decision.json")

    # The analyzer drops the sub-floor market cap name; PEAD Mode B drops the D grade.
    analysis_symbols = {row["symbol"] for row in analysis["results"]}
    assert analysis_symbols == {"EXMA", "EXMB", "EXMC", "EXMD"}
    assert pead["metadata"]["mode"] == "B"
    stages = {row["symbol"]: row["stage"] for row in pead["results"]}
    assert stages == {"EXMA": "BREAKOUT", "EXMB": "SIGNAL_READY", "EXMC": "MONITORING"}

    # Chart review: only the BREAKOUT name is validated; the others stay on watch.
    (setup,) = validated["setups"]
    breakout = next(row for row in pead["results"] if row["symbol"] == "EXMA")
    assert setup["symbol"] == "EXMA"
    assert setup["entry_price"] == breakout["entry_price"]
    assert setup["stop_price"] == breakout["stop_price"]
    assert {row["symbol"] for row in validated["rejected"]} == {"EXMB", "EXMC"}

    # Sizing and journal agree with the validated setup.
    assert sizing["parameters"]["entry_price"] == setup["entry_price"]
    assert sizing["parameters"]["stop_price"] == setup["stop_price"]
    (thesis,) = journal["theses"]
    assert thesis["ticker"] == "EXMA"
    assert thesis["status"] == "IDEA"
    assert thesis["thesis_type"] == "earnings_drift"
    assert thesis["origin_skill"] == "pead-screener"
    assert thesis["entry_target_price"] == setup["entry_price"]
    assert thesis["stop_loss"] == setup["stop_price"]
    assert journal["order_submitted"] is False

    # The native discipline gate evaluates the plan; it never places an order.
    assert decision["overall_decision"] == "GO"
    assert report["network_policy"] == "offline-input-required"


def test_required_only_and_full_path_execute_identical_steps(tmp_path: Path) -> None:
    required = execute_replay(ROOT, SPEC, "required-only", tmp_path / "required")
    full = execute_replay(ROOT, SPEC, "full-path", tmp_path / "full")

    assert [s["step"] for s in required["steps"]] == [s["step"] for s in full["steps"]]
    artifacts = sorted(p.name for p in (tmp_path / "required").iterdir() if p.name[0].isdigit())
    assert len(artifacts) == 8
    for name in artifacts:
        assert (tmp_path / "required" / name).read_bytes() == (
            tmp_path / "full" / name
        ).read_bytes()


def test_replay_rejects_a_validated_setup_that_is_not_a_pead_breakout(tmp_path: Path) -> None:
    review = _load_json(INPUTS / "technical-review.json")
    review["setups"][0]["symbol"] = "EXMB"
    bad = _override(tmp_path, "technical-review.json", review)

    with pytest.raises(ReplayError, match="BREAKOUT"):
        execute_replay(
            ROOT,
            SPEC,
            "required-only",
            tmp_path / "replay",
            input_overrides={"technical_review": bad},
        )


def test_replay_rejects_a_validated_setup_whose_stop_differs_from_pead(tmp_path: Path) -> None:
    review = _load_json(INPUTS / "technical-review.json")
    review["setups"][0]["stop_price"] = review["setups"][0]["stop_price"] - 1.0
    bad = _override(tmp_path, "technical-review.json", review)

    with pytest.raises(ReplayError, match="stop"):
        execute_replay(
            ROOT,
            SPEC,
            "required-only",
            tmp_path / "replay",
            input_overrides={"technical_review": bad},
        )


def test_replay_rejects_journal_registration_of_an_unvalidated_symbol(tmp_path: Path) -> None:
    decision = yaml.safe_load((INPUTS / "journal-decision.yaml").read_text(encoding="utf-8"))
    decision["register"] = ["EXMB"]
    bad = tmp_path / "inputs" / "journal-decision.yaml"
    bad.parent.mkdir(parents=True, exist_ok=True)
    bad.write_text(yaml.safe_dump(decision), encoding="utf-8")

    with pytest.raises(ReplayError, match="validated"):
        execute_replay(
            ROOT,
            SPEC,
            "required-only",
            tmp_path / "replay",
            input_overrides={"journal_decision": bad},
        )


def test_discipline_gate_blocks_when_the_market_regime_forbids_new_risk(tmp_path: Path) -> None:
    exposure = _load_json(INPUTS / "exposure-decision.json")
    exposure["recommendation"] = "CASH_PRIORITY"
    blocked = _override(tmp_path, "exposure-decision.json", exposure)

    execute_replay(
        ROOT,
        SPEC,
        "required-only",
        tmp_path / "replay",
        input_overrides={"exposure_decision": blocked},
    )
    decision = _load_json(tmp_path / "replay/07_pre_trade_discipline_decision.json")
    assert decision["overall_decision"] == "NO_GO"


def test_offline_runner_blocks_http_and_fixture_is_fictional() -> None:
    import replay_offline_fmp_cli as runner
    import requests

    original = requests.sessions.Session.request
    try:
        runner._block_network()
        with pytest.raises(AssertionError, match="forbids HTTP"):
            requests.get("http://127.0.0.1:9/never")
    finally:
        requests.sessions.Session.request = original

    fixture = _load_json(FIXTURE)
    assert set(fixture) >= {"earnings_calendar", "profiles", "prices"}
    assert all(symbol.startswith("EXM") for symbol in fixture["profiles"])
    assert "invented" in fixture["description"]


def test_offline_runner_refuses_unknown_scripts() -> None:
    unknown = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "--skill-dir",
            str(ROOT / "skills/pead-screener/scripts"),
            "--script",
            "fmp_client.py",
            "--fixture",
            str(FIXTURE),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert unknown.returncode != 0
    assert "unsupported script" in unknown.stderr
