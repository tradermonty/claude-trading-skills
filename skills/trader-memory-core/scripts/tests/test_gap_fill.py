"""Explicit acknowledgement records a real long gap fill without rewriting plan."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import thesis_store as store
import yaml

DATE = "2026-11-01T12:00:00+00:00"
END = "2026-11-02T12:00:00+00:00"


def snapshot(state):
    return {str(p.relative_to(state)): p.read_bytes() for p in state.rglob("*") if p.is_file()}


def ready(state, activate=True, stop=90):
    tid = store.register(
        state,
        {
            "ticker": "TEST",
            "thesis_type": "pivot_breakout",
            "thesis_statement": "Synthetic gap",
            "origin": {"skill": "test", "output_file": "synthetic.json"},
            "_source_date": "2026-11-01",
            "entry": {"target_price": 100},
            "exit": {"stop_loss": stop},
        },
    )
    if activate:
        store.transition(state, tid, "ENTRY_READY", "ready", event_date=DATE)
    return tid


@pytest.mark.parametrize("position_mode", ["direct", "attached"])
def test_acknowledged_gap_preserves_plan_audit_and_actual_pnl(tmp_path, position_mode):
    state = tmp_path / "theses"
    tid = ready(state)
    if position_mode == "attached":
        report = {
            "mode": "shares",
            "parameters": {"entry_price": 100, "stop_price": 90},
            "calculations": {"fixed_fractional": {"method": "fixed_fractional"}},
            "final_recommended_shares": 10,
            "final_position_value": 1000,
            "final_risk_dollars": 100,
            "final_risk_pct": 1,
        }
        report_path = tmp_path / "sizing.json"
        report_path.write_text(json.dumps(report))
        store.attach_position(state, tid, str(report_path))
    before = store.get(state, tid)
    kwargs = {"shares": 10} if position_mode == "direct" else {}
    result = store.open_position(
        state,
        tid,
        88,
        DATE,
        reason="broker confirmed fill",
        allow_gap_fill=True,
        event_date=DATE,
        **kwargs,
    )
    assert result["status"] == "ACTIVE"
    assert result["entry"]["actual_price"] == 88
    assert result["entry"]["actual_date"] == DATE
    assert result["entry"]["target_price"] == 100
    assert result["exit"]["stop_loss"] == 90
    assert result["origin"] == before["origin"]
    if position_mode == "attached":
        assert all(result["position"][k] == v for k, v in before["position"].items())
    reason = result["status_history"][-1]["reason"]
    assert reason.startswith("broker confirmed fill")
    assert "gap fill acknowledged" in reason
    assert "actual_price=88" in reason
    assert "planned_stop_loss=90" in reason
    assert result["status_history"][-1]["at"] == DATE
    saved = snapshot(state)
    with pytest.raises(ValueError, match="protected"):
        store.update(state, tid, {"status_history": []})
    assert snapshot(state) == saved
    closed = store.close(state, tid, "manual", 95, END)
    assert closed["outcome"]["pnl_dollars"] == 70
    assert closed["outcome"]["pnl_pct"] == pytest.approx(7.95)
    assert closed["exit"]["stop_loss"] == 90


def test_gap_acknowledgement_cannot_open_without_equity_quantity(tmp_path):
    """The gap acknowledgement must retain #703's quantity-required contract."""
    tid = ready(tmp_path)
    before = snapshot(tmp_path)
    with pytest.raises(ValueError, match="requires a share count"):
        store.open_position(tmp_path, tid, 88, DATE, allow_gap_fill=True)
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize("kwargs", [{}, {"allow_gap_fill": False}])
def test_gap_default_refusal_is_atomic(tmp_path, kwargs):
    tid = ready(tmp_path)
    before = snapshot(tmp_path)
    with pytest.raises(ValueError, match="long-only"):
        store.open_position(tmp_path, tid, 88, DATE, shares=10, **kwargs)
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize("flag", [None, 1, "yes", [], {}])
def test_gap_flag_requires_bool_without_state_mutation(tmp_path, flag):
    tid = ready(tmp_path)
    before = snapshot(tmp_path)
    with pytest.raises(ValueError):
        store.open_position(tmp_path, tid, 88, DATE, allow_gap_fill=flag)
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize(
    "field,value",
    [
        *[("actual_price", v) for v in [True, float("nan"), float("inf"), "88"]],
        *[("shares", v) for v in [True, 0, -1, float("nan"), float("inf"), "10"]],
        *[("reason", v) for v in [None, 7, []]],
        ("direction", "SHORT"),
        ("direction", "SELL"),
    ],
)
def test_gap_acknowledgement_never_bypasses_other_validation(tmp_path, field, value):
    tid = ready(tmp_path)
    before = snapshot(tmp_path)
    args = {"actual_price": 88, "shares": 10, "reason": "fill", "direction": "LONG"}
    args[field] = value
    with pytest.raises(ValueError):
        store.open_position(tmp_path, tid, actual_date=DATE, allow_gap_fill=True, **args)
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize("stop", [True, "90", float("nan"), float("inf")])
def test_gap_acknowledgement_does_not_bypass_malformed_stop(tmp_path, stop):
    tid = ready(tmp_path)
    thesis = store.get(tmp_path, tid)
    thesis["exit"]["stop_loss"] = stop
    (tmp_path / f"{tid}.yaml").write_text(yaml.safe_dump(thesis))
    before = snapshot(tmp_path)
    with pytest.raises(ValueError):
        store.open_position(tmp_path, tid, 88, DATE, allow_gap_fill=True)
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize("marker", ["position", "manual"])
def test_gap_acknowledgement_never_bypasses_legacy_short(tmp_path, marker):
    tid = ready(tmp_path)
    thesis = store.get(tmp_path, tid)
    if marker == "position":
        thesis["position"] = {"direction": "SHORT"}
    else:
        thesis["origin"].update(skill="manual", raw_provenance={"direction": "SHORT"})
    (tmp_path / f"{tid}.yaml").write_text(yaml.safe_dump(thesis))
    before = snapshot(tmp_path)
    with pytest.raises(ValueError, match="long-only"):
        store.open_position(tmp_path, tid, 88, DATE, allow_gap_fill=True)
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize("active", [False, True])
def test_gap_acknowledgement_requires_ready_state(tmp_path, active):
    tid = ready(tmp_path, activate=active)
    if active:
        store.open_position(tmp_path, tid, 100, DATE, shares=10)
    before = snapshot(tmp_path)
    with pytest.raises(ValueError, match="ENTRY_READY"):
        store.open_position(tmp_path, tid, 88, DATE, allow_gap_fill=True)
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize("price", [90, 100])
def test_gap_option_does_not_label_normal_fill_as_gap(tmp_path, price):
    tid = ready(tmp_path)
    result = store.open_position(
        tmp_path, tid, price, DATE, shares=10, allow_gap_fill=True, reason="normal"
    )
    assert result["status_history"][-1]["reason"] == "normal"


def test_gap_option_is_equity_only_and_direct_futures_unchanged(tmp_path):
    tid = ready(tmp_path, stop=110)
    before = snapshot(tmp_path)
    kwargs = {"contracts": 1, "multiplier": 10, "direction": "SHORT", "contract_currency": "USD"}
    with pytest.raises(ValueError, match="equity"):
        store.open_position(tmp_path, tid, 100, DATE, allow_gap_fill=True, **kwargs)
    assert snapshot(tmp_path) == before
    result = store.open_position(tmp_path, tid, 100, DATE, **kwargs)
    assert result["position"]["direction"] == "SHORT"


@pytest.mark.parametrize("launcher", [False, True])
def test_public_cli_records_gap_only_with_explicit_option(tmp_path, launcher):
    state = tmp_path / "theses"
    tid = ready(state)
    if launcher:
        args = [
            sys.executable,
            str(Path(store.__file__).with_name("trader_memory_cli.py")),
            "store",
        ]
    else:
        args = [sys.executable, store.__file__]
    args += [
        "--state-dir",
        str(state),
        "open-position",
        tid,
        "--actual-price",
        "88",
        "--actual-date",
        DATE,
        "--shares",
        "10",
    ]
    before = snapshot(state)
    refused = subprocess.run(
        args, capture_output=True, encoding="utf-8", env={**os.environ, "PYTHONIOENCODING": "utf-8"}
    )
    assert refused.returncode != 0
    assert snapshot(state) == before
    accepted = subprocess.run(
        [*args, "--allow-gap-fill"],
        capture_output=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    assert accepted.returncode == 0, accepted.stderr
    result = store.get(state, tid)
    assert result["status"] == "ACTIVE"
    assert result["entry"]["actual_price"] == 88
    assert result["exit"]["stop_loss"] == 90
    assert "gap fill acknowledged" in result["status_history"][-1]["reason"]


def test_gap_option_rejects_attached_futures_without_mutation(tmp_path):
    state = tmp_path / "theses"
    tid = ready(state, stop=110)
    report = {
        "schema_version": "1.0",
        "symbol": "TEST",
        "direction": "SHORT",
        "sizing_status": "SIZED",
        "entry": 100,
        "stop": 110,
        "contract_spec": {
            "multiplier": 10,
            "tick_size": 1,
            "tick_value": 10,
            "currency": "USD",
            "source": "synthetic",
            "verified": "2026-11-01",
        },
        "risk_per_contract_usd": 100,
        "risk_budget_usd": 100,
        "contracts": 1,
        "total_risk_usd": 100,
        "risk_pct_of_account": 1,
    }
    source = tmp_path / "future.json"
    source.write_text(json.dumps(report))
    store.attach_futures_position(state, tid, str(source))
    before = snapshot(state)
    with pytest.raises(ValueError, match="equity"):
        store.open_position(state, tid, 100, DATE, allow_gap_fill=True)
    assert snapshot(state) == before
    result = store.open_position(state, tid, 100, DATE)
    assert result["position"]["direction"] == "SHORT"


def test_gap_fill_trim_and_close_use_actual_fill_and_keep_original_ack(tmp_path):
    tid = ready(tmp_path)
    opened = store.open_position(
        tmp_path, tid, 88, DATE, shares=10, allow_gap_fill=True, event_date=DATE
    )
    ack = opened["status_history"][-1]["reason"]
    store.update(tmp_path, tid, {"exit": {"stop_loss": 92}})
    store.trim(tmp_path, tid, 5, 95, END, "confirmed partial fill")
    closed = store.close(tmp_path, tid, "manual", 96, END)
    assert closed["outcome"]["pnl_dollars"] == 75
    assert closed["entry"]["target_price"] == 100
    assert any(h["reason"] == ack for h in closed["status_history"])
    assert "planned_stop_loss=90" in ack
