"""Offline EP replay: native classification, handoffs and atomic failure gates."""

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
import workflow_replay as replay  # noqa: E402

SPEC = ROOT / "examples/workflows/stockbee-ep-daily/replay.yaml"


def override(tmp_path, name, mutate):
    payload = json.loads((SPEC.parent / "replay-inputs" / f"{name}.json").read_text())
    mutate(payload)
    path = tmp_path / "overrides" / f"{name}.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return {name: path}


def read(output, name):
    return json.loads((output / name).read_text())


def test_evidence_modes():
    result = replay.validate_spec(ROOT, SPEC)
    assert result["native_steps"] == [1, 4, 6]
    assert result["manual_contract_steps"] == [2, 3, 5, 7]
    assert result["composite_steps"] == [8, 9]


@pytest.mark.parametrize(
    "variant,golden,decision,steps",
    [
        ("required-only", "replay-run", "NO_GO", [1, 4, 5, 6, 8, 9]),
        ("full-path", "replay-run-full-path", "GO", list(range(1, 10))),
    ],
)
def test_native_roundtrip_and_goldens(tmp_path, variant, golden, decision, steps):
    output = tmp_path / "out"
    report = replay.execute_replay(ROOT, SPEC, variant, output)
    assert [s["step"] for s in report["steps"]] == steps
    assert replay.compare_trees(output, SPEC.parent / golden) == []
    analysis = read(output, "04_episodic_pivot_candidates.json")
    assert {r["symbol"]: r["state"] for r in analysis["results"]} == {
        "EXMPL": "ACTIONABLE_DAY1",
        "EXWIDE": "DELAYED_EP_WATCH",
    }
    assert analysis["metadata"]["api_stats"] is None
    assert [r["symbol"] for r in read(output, "04_delayed_ep_watchlist.json")["candidates"]] == [
        "EXWIDE"
    ]
    assert "EXWIDE" in [
        r["symbol"] for r in read(output, "04_pead_handoff_candidates.json")["candidates"]
    ]
    journal = read(output, "08_ep_journal_entry.json")
    assert journal["ticker"] == "EXMPL"
    assert journal["status"] == "IDEA"
    assert journal["entry"]["actual_price"] is None
    assert journal["entry"]["actual_date"] is None
    assert journal["execution_authorized"] is False
    assert journal["position"]["shares"] == 217
    for source in journal["sources"].values():
        file = output / source["file"].removeprefix("$ARTIFACT/")
        assert hashlib.sha256(file.read_bytes()).hexdigest() == source["sha256"]
    gate = read(output, "09_pre_trade_discipline_decision.json")
    assert gate["overall_decision"] == decision
    assert gate["execution_authorized"] is False
    watch = next(r for r in gate["candidate_results"] if r["symbol"] == "EXWIDE")
    assert watch["decision"] == "NO_ACTIONABLE_ORDERS"
    assert watch["actionable"] is False
    for file in output.glob("*.json"):
        assert "workflow-replay-" not in file.read_text()
        assert "/private/" not in file.read_text()


@pytest.mark.parametrize(
    "name,mutate,last_step",
    [
        ("decision", lambda p: p.update(human_approved=False), 0),
        ("decision", lambda p: p["data"].update(risk_pct=True), 0),
        ("decision", lambda p: p["data"].update(account_size=float("inf")), 0),
        ("exposure", lambda p: p["data"].update(recommendation="CASH_PRIORITY"), 0),
        ("exposure", lambda p: p["data"].update(generated_at="2020-01-01"), 0),
        ("earnings", lambda p: p["data"]["results"][0].update(symbol="OTHER"), 1),
        ("momentum", lambda p: p["data"]["results"][0].update(setup_date="2020-01-01"), 2),
        ("events", lambda p: p["data"]["events"][0].update(event_date="2020-01-01"), 3),
        ("prices", lambda p: p["data"]["prices"].pop("EXMPL"), 3),
        ("prices", lambda p: p["data"]["prices"]["EXMPL"][-1].update(close=True), 3),
        ("prices", lambda p: p["data"]["prices"]["EXMPL"][-1].update(date="2020-01-01"), 3),
        (
            "prices",
            lambda p: p["data"]["prices"]["EXMPL"].append(p["data"]["prices"]["EXMPL"][-1]),
            3,
        ),
        ("decision", lambda p: p["data"].update(symbol="EXWIDE"), 3),
        ("chart", lambda p: p["data"].update(verdict="NOT_CONFIRMED"), 4),
        ("chart", lambda p: p["data"].update(symbol="EXWIDE"), 4),
        ("chart", lambda p: p["data"].update(stop_price=52), 4),
        ("chart", lambda p: p["data"].update(target_price=True), 4),
        ("chart", lambda p: p.update(as_of="2020-01-01"), 4),
        ("checklist", lambda p: p["data"].update(symbol="OTHER"), 8),
        ("checklist", lambda p: p["data"].update(size_within_plan=1), 8),
    ],
)
def test_invalid_evidence_preserves_output(tmp_path, name, mutate, last_step):
    output = tmp_path / "out"
    output.mkdir()
    (output / "existing.txt").write_text("preserve")
    with pytest.raises(replay.ReplayError) as exc:
        replay.execute_replay(
            ROOT, SPEC, "full-path", output, input_overrides=override(tmp_path, name, mutate)
        )
    assert exc.value.completed_steps == list(range(1, last_step + 1))
    assert [p.name for p in output.iterdir()] == ["existing.txt"]
    assert (output / "existing.txt").read_text() == "preserve"


@pytest.mark.parametrize(
    "step,artifact,mutate",
    [
        (
            5,
            "episodic_pivot_candidates",
            lambda p: p["results"][0].update(state="DELAYED_EP_WATCH"),
        ),
        (6, "validated_ep_setups", lambda p: p["setups"][0].update(symbol="OTHER")),
        (7, "ep_position_sizing", lambda p: p.update(final_risk_dollars=99999)),
        (8, "ep_position_sizing", lambda p: p["parameters"].update(entry_price=58)),
        (9, "ep_trade_plan", lambda p: p["plans"][0].update(entry_price=58)),
        (9, "ep_journal_entry", lambda p: p["position"].update(shares=999)),
        (9, "circuit_breaker_decision", lambda p: p.update(recommendation="HALTED")),
    ],
)
def test_tampered_handoff_stops_before_downstream(tmp_path, step, artifact, mutate):
    def before(number, artifacts):
        if number == step:
            path = Path(artifacts[artifact]["files"]["canonical"])
            payload = json.loads(path.read_text())
            mutate(payload)
            path.write_text(json.dumps(payload))

    with pytest.raises(replay.ReplayError) as exc:
        replay.execute_replay(ROOT, SPEC, "full-path", tmp_path / "out", before_step=before)
    assert step not in exc.value.completed_steps
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(
            lambda p: p["results"][0].update(
                trade_plan_inpt=p["results"][0].pop("trade_plan_inputs")
            ),
            id="rename-trade_plan_inputs",
        ),
        pytest.param(
            lambda p: p["results"][0]["trade_plan_inputs"].update(
                entry_ref=p["results"][0]["trade_plan_inputs"].pop("entry_reference")
            ),
            id="rename-entry_reference",
        ),
    ],
)
def test_native_report_contract_drift_is_replay_error_not_keyerror(tmp_path, mutate):
    def before(number, artifacts):
        if number == 5:
            path = Path(artifacts["episodic_pivot_candidates"]["files"]["canonical"])
            payload = json.loads(path.read_text())
            mutate(payload)
            path.write_text(json.dumps(payload))

    with pytest.raises(
        replay.ReplayError, match="invalid stockbee-ep analyze report contract"
    ) as exc:
        replay.execute_replay(ROOT, SPEC, "full-path", tmp_path / "out", before_step=before)
    assert 5 not in exc.value.completed_steps
    assert not (tmp_path / "out").exists()


def loss(pnl):
    at = "2026-08-14T15:00:00-04:00"
    return dict(
        thesis_id="th_fixture_0",
        ticker="EXLOSS",
        created_at="2026-08-01T12:00:00+00:00",
        updated_at=at,
        thesis_type="growth_momentum",
        status="CLOSED",
        status_history=[dict(status="CLOSED", at=at, reason="manual")],
        thesis_statement="Fictional losing position for replay gate verification.",
        origin=dict(skill="test", output_file="fixture.json"),
        outcome=dict(pnl_dollars=pnl, pnl_pct=pnl / 1000),
        exit=dict(actual_date=at, actual_price=100, exit_reason="manual"),
    )


def test_native_account_halt_never_analyzes(tmp_path):
    pytest.importorskip(
        "pandas_market_calendars",
        reason="Account-halt cooldown requires pandas-market-calendars; install the market-calendar or ci extra",
    )
    with pytest.raises(replay.ReplayError, match="circuit breaker halted") as exc:
        replay.execute_replay(
            ROOT,
            SPEC,
            "full-path",
            tmp_path / "out",
            input_overrides=override(
                tmp_path, "account_state", lambda p: p["data"].append(loss(-5000))
            ),
        )
    assert exc.value.completed_steps == []
    assert not (tmp_path / "out").exists()


def test_small_recent_loss_reaches_native_discipline(tmp_path):
    output = tmp_path / "out"
    replay.execute_replay(
        ROOT,
        SPEC,
        "full-path",
        output,
        input_overrides=override(tmp_path, "account_state", lambda p: p["data"].append(loss(-100))),
    )
    assert read(output, "01_circuit_breaker_decision.json")["recommendation"] == "TRADING_ALLOWED"
    gate = read(output, "09_pre_trade_discipline_decision.json")
    assert gate["overall_decision"] == "NO_GO"
    assert any(
        "recent losing" in reason for row in gate["candidate_results"] for reason in row["reasons"]
    )
    assert gate["metrics"]["theses_scanned"] == 1


def test_declined_manual_checklist_is_not_overridden(tmp_path):
    output = tmp_path / "out"
    replay.execute_replay(
        ROOT,
        SPEC,
        "full-path",
        output,
        input_overrides=override(
            tmp_path, "checklist", lambda p: p["data"].update(entry_in_written_plan=False)
        ),
    )
    assert read(output, "09_pre_trade_discipline_decision.json")["overall_decision"] == "NO_GO"


def test_journal_write_failure_never_publishes(tmp_path, monkeypatch):
    store = replay._repo_module(ROOT, "thesis_store", ROOT / "skills/trader-memory-core/scripts")

    def fail(*args, **kwargs):
        raise OSError("injected journal failure")

    monkeypatch.setattr(store, "_save_thesis", fail)
    with pytest.raises(replay.ReplayError, match="injected journal failure") as exc:
        replay.execute_replay(ROOT, SPEC, "required-only", tmp_path / "out")
    assert exc.value.completed_steps == [1, 4, 5, 6]
    assert not (tmp_path / "out").exists()


def test_nested_paths_resolve_in_journal_and_manifest(tmp_path):
    directory = tmp_path / "spec"
    shutil.copytree(SPEC.parent, directory)
    spec_path = directory / "replay.yaml"
    spec = yaml.safe_load(spec_path.read_text())
    for step in spec["steps"]:
        for roles in step["output_files"].values():
            roles["canonical"] = "nested/" + roles["canonical"]
    spec_path.write_text(yaml.safe_dump(spec))
    output = tmp_path / "out"
    replay.execute_replay(ROOT, spec_path, "full-path", output)
    record = read(output, "nested/08_ep_journal_entry.json")
    for link in record["linked_reports"]:
        assert link["file"].startswith("$ARTIFACT/nested/")
        assert (output / link["file"].removeprefix("$ARTIFACT/")).is_file()
    for artifact in yaml.safe_load((output / "manifest.yaml").read_text())["artifacts"]:
        for path in artifact["files"].values():
            assert (output / path).is_file()


def test_native_ep_command_uses_only_offline_handoffs(tmp_path, monkeypatch):
    calls = []
    original = replay._run_cli

    def capture(command, repo_root):
        calls.append(command)
        return original(command, repo_root)

    monkeypatch.setattr(replay, "_run_cli", capture)
    replay.execute_replay(ROOT, SPEC, "full-path", tmp_path / "out")
    command = next(c for c in calls if c[1].endswith("/analyze_ep.py"))
    assert command[command.index("--max-api-calls") + 1] == "0"
    for flag in ["--events-json", "--prices-json", "--earnings-json", "--momentum-json"]:
        assert flag in command
    assert "--api-key" not in command
    assert "02_earnings_candidates.json" in command[command.index("--earnings-json") + 1]
    assert "03_momentum_burst_candidates.json" in command[command.index("--momentum-json") + 1]


def test_unidentified_account_record_never_clears_gate(tmp_path):
    with pytest.raises(replay.ReplayError, match="account state") as exc:
        replay.execute_replay(
            ROOT,
            SPEC,
            "full-path",
            tmp_path / "out",
            input_overrides=override(tmp_path, "account_state", lambda p: p["data"].append({})),
        )
    assert exc.value.completed_steps == []
    assert not (tmp_path / "out").exists()


def test_malformed_prices_never_publish(tmp_path):
    path = tmp_path / "overrides" / "prices.json"
    path.parent.mkdir()
    path.write_text("{invalid JSON")
    with pytest.raises(replay.ReplayError) as exc:
        replay.execute_replay(
            ROOT, SPEC, "required-only", tmp_path / "out", input_overrides={"prices": path}
        )
    assert exc.value.completed_steps == [1]
    assert not (tmp_path / "out").exists()
