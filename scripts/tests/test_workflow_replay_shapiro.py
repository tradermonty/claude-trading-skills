"""Shapiro replay handoffs, native execution, and atomic failure boundaries."""

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

SPEC = ROOT / "examples/workflows/shapiro-contrarian/replay.yaml"


def override(tmp_path, name, mutate):
    payload = json.loads((SPEC.parent / "replay-inputs" / f"{name}.json").read_text())
    mutate(payload)
    path = tmp_path / "overrides" / f"{name}.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return {name: path}


def test_evidence_modes():
    summary = replay.validate_spec(ROOT, SPEC)
    assert summary["manual_contract_steps"] == [1, 2, 3]
    assert summary["native_steps"] == [4, 5]
    assert summary["composite_steps"] == [6]


@pytest.mark.parametrize(
    "variant,golden", [("required-only", "replay-run"), ("full-path", "replay-run-full-path")]
)
def test_native_roundtrip_and_goldens(tmp_path, variant, golden):
    output = tmp_path / "out"
    report = replay.execute_replay(ROOT, SPEC, variant, output)
    assert report["status"] == "completed"
    assert [s["step"] for s in report["steps"]] == [1, 2, 3, 4, 5, 6]
    assert replay.compare_trees(output, SPEC.parent / golden) == []
    record = json.loads((output / "06_contrarian_thesis_entry.json").read_text())
    assert record["status"] == "IDEA"
    assert record["entry"]["actual_price"] is None
    assert record["entry"]["actual_date"] is None
    assert record["execution_authorized"] is False
    assert record["position"]["quantity"] == 2
    assert record["position"]["total_risk_usd"] == 1000
    assert record["created_at"].startswith("2026-08-15")
    assert len(record["sources"]) == 5
    for source in record["sources"].values():
        path = output / source["file"].removeprefix("$ARTIFACT/")
        assert hashlib.sha256(path.read_bytes()).hexdigest() == source["sha256"]
    assert "/private/" not in json.dumps(record)
    assert "workflow-replay-" not in json.dumps(record)


@pytest.mark.parametrize(
    "name,mutate,last_step",
    [
        ("crowding", lambda p: p.update(human_approved=False), 0),
        ("crowding", lambda p: p["report"]["markets"][0].update(classification="NEUTRAL"), 0),
        ("crowding", lambda p: p["report"]["markets"][0].update(data_date="2020-01-01"), 0),
        ("crowding", lambda p: p["report"]["markets"].append(dict(p["report"]["markets"][0])), 0),
        ("news", lambda p: p["report"].update(verdict="INSUFFICIENT_EVIDENCE"), 1),
        ("news", lambda p: p["report"].update(verdict="NOT_CONFIRMED"), 1),
        ("news", lambda p: p["report"].update(symbol="ES"), 1),
        ("news", lambda p: p["report"].update(direction="CROWDED_LONG"), 1),
        ("news", lambda p: p["report"]["run_context"].update(as_of="2020-01-01"), 1),
        ("price", lambda p: p["report"].update(verdict="INSUFFICIENT_DATA"), 2),
        ("price", lambda p: p["report"].update(symbol="ES"), 2),
        ("price", lambda p: p["report"]["swing_levels"].update(stop_reference=True), 2),
        ("decision", lambda p: p.update(human_approved=False), 0),
        ("decision", lambda p: p.update(risk_pct=True), 0),
        ("decision", lambda p: p.update(entry=float("inf")), 0),
        ("decision", lambda p: p.update(as_of="2026-08-16"), 0),
    ],
)
def test_invalid_evidence_fails_before_downstream_and_preserves_output(
    tmp_path, name, mutate, last_step
):
    output = tmp_path / "out"
    output.mkdir()
    (output / "existing.txt").write_text("preserve")
    with pytest.raises(replay.ReplayError) as exc:
        replay.execute_replay(
            ROOT, SPEC, "full-path", output, input_overrides=override(tmp_path, name, mutate)
        )
    assert exc.value.completed_steps == list(range(1, last_step + 1))
    assert list(p.name for p in output.iterdir()) == ["existing.txt"]
    assert (output / "existing.txt").read_text() == "preserve"


@pytest.mark.parametrize("name", ["crowding", "news", "price"])
def test_malformed_json_never_publishes(tmp_path, name):
    path = tmp_path / "overrides" / "bad.json"
    path.parent.mkdir()
    path.write_text("{invalid json")
    output = tmp_path / "out"
    with pytest.raises(replay.ReplayError) as exc:
        replay.execute_replay(ROOT, SPEC, "required-only", output, input_overrides={name: path})
    assert exc.value.completed_steps == list(range(1, {"crowding": 1, "news": 2, "price": 3}[name]))
    assert not output.exists()


def test_no_trade_sizing_never_registers(tmp_path):
    with pytest.raises(replay.ReplayError, match="Shapiro sizing halted") as exc:
        replay.execute_replay(
            ROOT,
            SPEC,
            "required-only",
            tmp_path / "out",
            input_overrides=override(tmp_path, "decision", lambda p: p.update(account_size=100)),
        )
    assert exc.value.completed_steps == [1, 2, 3, 4]
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize(
    "step,artifact,mutate",
    [
        (4, "news_failure_verdict", lambda p: p.update(verdict="NOT_CONFIRMED")),
        (5, "contrarian_setup_gate_report", lambda p: p.update(setup_status="REJECTED")),
        (6, "futures_position_size", lambda p: p.update(sizing_status="NO_TRADE")),
        (6, "futures_position_size", lambda p: p.update(symbol="ES")),
        (
            6,
            "contrarian_setup_gate_report",
            lambda p: p["replay_sources"]["cot_crowding_report"].update(sha256="0" * 64),
        ),
    ],
)
def test_tampered_handoff_is_not_accepted(tmp_path, step, artifact, mutate):
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


def test_native_journal_write_failure_does_not_publish(tmp_path, monkeypatch):
    store = replay._repo_module(ROOT, "thesis_store", ROOT / "skills/trader-memory-core/scripts")

    def fail(*args, **kwargs):
        raise OSError("injected journal failure")

    monkeypatch.setattr(store, "_save_thesis", fail)
    with pytest.raises(replay.ReplayError, match="injected journal failure") as exc:
        replay.execute_replay(ROOT, SPEC, "required-only", tmp_path / "out")
    assert exc.value.completed_steps == [1, 2, 3, 4, 5]
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
    record = json.loads((output / "nested/06_contrarian_thesis_entry.json").read_text())
    for link in record["linked_reports"]:
        assert link["file"].startswith("$ARTIFACT/nested/")
        assert (output / link["file"].removeprefix("$ARTIFACT/")).is_file()
    for artifact in yaml.safe_load((output / "manifest.yaml").read_text())["artifacts"]:
        for path in artifact["files"].values():
            assert (output / path).is_file()
