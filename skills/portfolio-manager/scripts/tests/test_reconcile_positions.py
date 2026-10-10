"""Offline comparison contract and CLI failure gates."""

import copy
import json
import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest
from reconcile_positions import main, reconcile, render_summary

SCRIPT = Path(__file__).resolve().parents[1] / "reconcile_positions.py"


def row(symbol="FICTA", quantity="10", direction="LONG"):
    return {"symbol": symbol, "quantity": quantity, "direction": direction, "asset_type": "equity"}


def snapshot(*positions):
    return {
        "schema_version": 1,
        "account_scope": "paper_demo",
        "as_of": "2026-10-09T12:00:00Z",
        "complete": True,
        "positions": list(positions),
    }


@pytest.mark.parametrize(
    ("broker", "memory", "status"),
    [
        (row(), row(), "MATCH"),
        (row(quantity="6"), row(), "QUANTITY_MISMATCH"),
        (row(quantity="0.1250"), row(quantity="0.125"), "MATCH"),
        (row(quantity="0.12500000000001"), row(quantity="0.125"), "QUANTITY_MISMATCH"),
        (row(direction="SHORT"), row(), "DIRECTION_MISMATCH"),
        (row(quantity="6", direction="SHORT"), row(), "DIRECTION_MISMATCH"),
        (row(), None, "BROKER_ONLY"),
        (None, row(), "MEMORY_ONLY"),
    ],
)
def test_position_statuses(broker, memory, status):
    report = reconcile(
        snapshot(*([broker] if broker else [])), snapshot(*([memory] if memory else []))
    )
    assert report["items"][0]["status"] == status
    assert report["requires_review"] is (status != "MATCH")
    assert report["can_continue"] is (status == "MATCH")
    assert status in render_summary(report)


def test_empty_complete_accounts_and_equivalent_timestamps():
    memory = snapshot()
    memory["as_of"] = "2026-10-09T05:00:00-07:00"
    assert reconcile(snapshot(), memory)["can_continue"] is True


@pytest.mark.parametrize(
    "quantity",
    [
        None,
        True,
        False,
        0,
        -1,
        "-1",
        "NaN",
        "Infinity",
        "-Infinity",
        "bad",
        [],
        {},
        "1e-13",
        "1e13",
        "1" * 65,
    ],
)
def test_invalid_quantity_blocks(quantity):
    report = reconcile(snapshot(row(quantity=quantity)), snapshot(row()))
    assert report["status"] == "INVALID_INPUT"
    assert report["requires_review"] is True
    assert report["can_continue"] is False
    assert report["items"] == []


@pytest.mark.parametrize(
    "change",
    [
        lambda p: p.pop("positions"),
        lambda p: p.update(positions=None),
        lambda p: p.update(complete=False),
        lambda p: p.update(schema_version=True),
        lambda p: p.update(schema_version=2),
        lambda p: p.update(account_scope="other"),
        lambda p: p.update(account_scope="bad|alias"),
        lambda p: p.update(as_of="2026-10-09"),
        lambda p: p.update(as_of="2026-10-10T12:00:00Z"),
        lambda p: p["positions"][0].pop("quantity"),
        lambda p: p["positions"][0].update(asset_type="futures"),
        lambda p: p["positions"][0].update(direction="SHORT"),
        lambda p: p["positions"].append(row(symbol=" ficta ")),
        lambda p: p["positions"][0].update(symbol="FICTA|BAD"),
        lambda p: p["positions"][0].update(direction=None),
    ],
)
def test_incomplete_or_incompatible_memory_blocks(change):
    memory = snapshot(row())
    change(memory)
    report = reconcile(snapshot(row()), memory)
    assert report["status"] == "INVALID_INPUT"
    assert report["can_continue"] is False


def test_duplicate_broker_identity_ignores_direction():
    report = reconcile(snapshot(row(), row(direction="SHORT")), snapshot(row()))
    assert report["status"] == "INVALID_INPUT"
    assert "duplicate" in report["errors"][0]


def test_deterministic_sorted_reports_and_no_input_mutation():
    broker = snapshot(row("FICTZ"), row("ficta", "1.50"))
    memory = snapshot(row("FICTA", "1.5"), row("FICTZ"))
    original = copy.deepcopy((broker, memory))
    first = reconcile(broker, memory)
    broker["positions"].reverse()
    second = reconcile(broker, memory)
    broker["positions"].reverse()
    assert (broker, memory) == original
    assert first == second
    assert [item["symbol"] for item in first["items"]] == ["FICTA", "FICTZ"]
    assert first["items"][0]["broker_quantity"] == "1.5"
    assert render_summary(first) == render_summary(second)


@pytest.mark.parametrize("mismatch", [False, True])
def test_cli_reports_without_network_or_source_writes(tmp_path, monkeypatch, capsys, mismatch):
    def block_network(*args, **kwargs):
        raise AssertionError("unexpected network use")

    monkeypatch.setattr(socket, "socket", block_network)
    monkeypatch.setattr(socket, "create_connection", block_network)
    broker = tmp_path / "broker.json"
    memory = tmp_path / "memory.json"
    broker.write_text(json.dumps(snapshot(row(quantity="6" if mismatch else "10"))))
    memory.write_text(json.dumps(snapshot(row())))
    original = [p.read_bytes() for p in (broker, memory)]
    output = tmp_path / "reports"
    result = main(["--broker", str(broker), "--memory", str(memory), "--output-dir", str(output)])
    assert result == int(mismatch)
    assert [p.read_bytes() for p in (broker, memory)] == original
    streams = capsys.readouterr()
    report = json.loads(streams.out)
    assert report["can_continue"] is (not mismatch)
    assert bool(streams.err) is mismatch
    assert json.loads((output / "reconciliation_report.json").read_text()) == report
    assert (output / "reconciliation_report.md").read_text() == render_summary(report)
    assert {p.name for p in tmp_path.iterdir()} == {"broker.json", "memory.json", "reports"}


@pytest.mark.parametrize(
    "invalid",
    [
        '{"schema_version":1,"schema_version":1}',
        "not json",
        "{}",
        '{"quantity":1e999999999999999999999}',
    ],
)
def test_invalid_cli_has_no_report_files(tmp_path, capsys, invalid):
    broker = tmp_path / "broker.json"
    memory = tmp_path / "memory.json"
    broker.write_text(invalid)
    memory.write_text(json.dumps(snapshot()))
    output = tmp_path / "reports"
    assert (
        main(["--broker", str(broker), "--memory", str(memory), "--output-dir", str(output)]) == 1
    )
    assert not output.exists()
    assert json.loads(capsys.readouterr().out)["can_continue"] is False


def test_cli_rejects_overwriting_input(tmp_path, capsys):
    broker = tmp_path / "reconciliation_report.json"
    memory = tmp_path / "memory.json"
    broker.write_text(json.dumps(snapshot()))
    memory.write_text(json.dumps(snapshot()))
    original = broker.read_bytes()
    assert (
        main(["--broker", str(broker), "--memory", str(memory), "--output-dir", str(tmp_path)]) == 1
    )
    assert broker.read_bytes() == original
    assert "overwrite" in capsys.readouterr().err


def test_real_entrypoint_exit_contract(tmp_path):
    broker = tmp_path / "broker.json"
    memory = tmp_path / "memory.json"
    for path in (broker, memory):
        path.write_text(json.dumps(snapshot(row())))
    command = [sys.executable, str(SCRIPT), "--broker", str(broker), "--memory", str(memory)]
    matched = subprocess.run(command, capture_output=True, text=True, check=False)
    assert matched.returncode == 0
    assert json.loads(matched.stdout)["status"] == "MATCH"
    memory.write_text(json.dumps(snapshot()))
    mismatch = subprocess.run(command, capture_output=True, text=True, check=False)
    assert mismatch.returncode == 1
    assert json.loads(mismatch.stdout)["status"] == "REVIEW_REQUIRED"
    assert "stop allocation" in mismatch.stderr


@pytest.mark.parametrize("extension", ["json", "md"])
@pytest.mark.parametrize("source_name", ["broker", "memory"])
def test_cli_rejects_hardlinked_output(tmp_path, capsys, extension, source_name):
    broker = tmp_path / "broker.json"
    memory = tmp_path / "memory.json"
    for path in (broker, memory):
        path.write_text(json.dumps(snapshot(row())))
    output = tmp_path / "reports"
    output.mkdir()
    source = broker if source_name == "broker" else memory
    os.link(source, output / f"reconciliation_report.{extension}")
    original = [p.read_bytes() for p in (broker, memory)]
    assert (
        main(["--broker", str(broker), "--memory", str(memory), "--output-dir", str(output)]) == 1
    )
    assert [p.read_bytes() for p in (broker, memory)] == original
    assert "overwrite" in capsys.readouterr().err
    assert {p.name for p in output.iterdir()} == {f"reconciliation_report.{extension}"}
