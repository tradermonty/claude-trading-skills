"""Offline detector-to-generator CLI regressions for Issue #293."""

import json
import sys
from datetime import datetime

import detect_stagnation as detector
import generate_pivots as generator
import pytest
import requests
import yaml
from helpers import make_eval


@pytest.fixture(autouse=True)
def offline_clock(monkeypatch):
    monkeypatch.delenv("FMP_API_KEY", raising=False)

    def forbidden(*args, **kwargs):
        raise AssertionError("unexpected HTTP request")

    monkeypatch.setattr(requests.sessions.Session, "request", forbidden)

    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 10, 4, 12, 0, tzinfo=tz)

    monkeypatch.setattr(detector, "datetime", FixedDatetime)
    monkeypatch.setattr(generator, "datetime", FixedDatetime)


def _run(module, monkeypatch, *args):
    monkeypatch.setattr(sys, "argv", [module.__name__, *map(str, args)])
    return module.main()


def _source_draft(strategy_id):
    return {
        "id": strategy_id,
        "concept_id": "fictional_cli_probe",
        "hypothesis_type": "breakout",
        "mechanism_tag": "behavior",
        "entry_family": "pivot_breakout",
        "regime": "Bull",
        "exit": {"stop_loss_pct": 0.08, "take_profit_rr": 3.0, "time_stop_days": 20},
        "risk": {"position_sizing": "fixed_risk", "risk_per_trade": 0.01, "max_positions": 5},
        "entry": {
            "conditions": ["close > high20_prev", "rel_volume >= 1.5"],
            "trend_filter": ["price > sma_200"],
        },
        "thesis": "Fictional breakout probe.",
        "invalidation_signals": ["close < sma_200"],
    }


@pytest.mark.parametrize("max_pivots", [1, 8])
def test_detector_to_generator_persists_ranked_drafts_and_manifest(
    tmp_path, monkeypatch, sample_iteration_history, max_pivots, capsys
):
    history = tmp_path / "history.json"
    history.write_text(json.dumps(sample_iteration_history))
    diagnosis_dir = tmp_path / "diagnoses"
    assert _run(detector, monkeypatch, "--history", history, "--output-dir", diagnosis_dir) == 0
    diagnosis_path = diagnosis_dir / "pivot_diagnosis_mean_revert_v2_20261004_120000.json"
    diagnosis = json.loads(diagnosis_path.read_text())
    assert diagnosis["recommendation"] == "pivot"
    assert diagnosis["iteration_count"] == 5
    assert diagnosis["score_trajectory"] == [45, 62, 72, 73, 72]
    assert "improvement_plateau" in [t["trigger"] for t in diagnosis["triggers_fired"]]
    assert diagnosis["diagnosed_at_utc"] == "2026-10-04T12:00:00+00:00"

    source = tmp_path / "draft.yaml"
    source.write_text(yaml.safe_dump(_source_draft(diagnosis["strategy_id"])))
    before = (history.read_bytes(), source.read_bytes(), diagnosis_path.read_bytes())
    output = tmp_path / "proposals"
    assert (
        _run(
            generator,
            monkeypatch,
            "--diagnosis",
            diagnosis_path,
            "--strategy",
            source,
            "--max-pivots",
            max_pivots,
            "--output-dir",
            output,
        )
        == 0
    )
    manifest = json.loads(
        (output / "pivot_manifest_mean_revert_v2_20261004_120000.json").read_text()
    )
    drafts = manifest["drafts"]
    assert manifest["total_pivots_generated"] == len(drafts)
    assert 1 <= len(drafts) <= max_pivots
    if max_pivots == 1:
        assert len(drafts) == 1
    else:
        assert len(drafts) > 1
        assert manifest["exportable_count"] > 0
        assert manifest["research_only_count"] > 0
    assert manifest["exportable_count"] + manifest["research_only_count"] == len(drafts)
    assert manifest["errors"] == []
    assert manifest["diagnosis_file"] == str(diagnosis_path)
    assert manifest["strategy_file"] == str(source)
    assert manifest["generated_at_utc"] == "2026-10-04T12:00:00+00:00"
    scores = [row["scores"]["combined"] for row in drafts]
    assert scores == sorted(scores, reverse=True)
    targets = []
    report = (output / "pivot_report_mean_revert_v2_20261004_120000.md").read_text()
    for index, row in enumerate(drafts, 1):
        path = output / row["path"]
        payload = yaml.safe_load(path.read_text())
        assert payload["id"] == row["id"]
        assert payload["pivot_metadata"]["source_strategy_id"] == diagnosis["strategy_id"]
        assert payload["pivot_metadata"]["scores"] == row["scores"]
        targets.append(payload["pivot_metadata"]["target_archetype"])
        assert f"### {index}. {row['id']}" in report
        assert path.parent.name == row["category"]
        if row["category"] == "exportable":
            ticket = yaml.safe_load((output / row["ticket_path"]).read_text())
            assert ticket["entry_family"] == payload["entry_family"]
            assert ticket["entry"]["conditions"] == payload["entry"]["conditions"]
        else:
            assert row["ticket_path"] is None
    assert len(set(targets)) == len(targets)
    assert before == (history.read_bytes(), source.read_bytes(), diagnosis_path.read_bytes())
    assert f"Generated {len(drafts)} pivot proposals" in capsys.readouterr().out


def test_no_trigger_diagnosis_is_saved_but_generator_creates_no_proposals(
    tmp_path, monkeypatch, healthy_history, capsys
):
    history = tmp_path / "history.json"
    history.write_text(json.dumps(healthy_history))
    diagnostics = tmp_path / "diagnoses"
    assert _run(detector, monkeypatch, "--history", history, "--output-dir", diagnostics) == 0
    diagnosis_path = next(diagnostics.glob("*.json"))
    diagnosis = json.loads(diagnosis_path.read_text())
    assert diagnosis["recommendation"] == "continue"
    assert diagnosis["triggers_fired"] == []
    source = tmp_path / "draft.yaml"
    source.write_text(yaml.safe_dump(_source_draft(healthy_history["strategy_id"])))
    output = tmp_path / "proposals"
    assert (
        _run(
            generator,
            monkeypatch,
            "--diagnosis",
            diagnosis_path,
            "--strategy",
            source,
            "--output-dir",
            output,
        )
        == 0
    )
    assert not output.exists()
    assert "No triggers fired" in capsys.readouterr().out


def test_review_required_diagnosis_does_not_generate_pivots(tmp_path, monkeypatch, capsys):
    diagnosis_path = tmp_path / "diagnosis.json"
    diagnosis_path.write_text(
        json.dumps(
            {
                "strategy_id": "demo",
                "recommendation": "review_required",
                "triggers_fired": [{"trigger": "insufficient_profit_factor", "severity": "high"}],
            }
        )
    )
    source = tmp_path / "draft.yaml"
    source.write_text(yaml.safe_dump(_source_draft("demo")))
    output = tmp_path / "proposals"
    assert (
        _run(
            generator,
            monkeypatch,
            "--diagnosis",
            diagnosis_path,
            "--strategy",
            source,
            "--output-dir",
            output,
        )
        == 0
    )
    assert not output.exists()
    assert "Evaluation needs review" in capsys.readouterr().out


def test_detector_cli_threshold_override_changes_plateau_decision(
    tmp_path, monkeypatch, sample_iteration_history
):
    history = tmp_path / "history.json"
    history.write_text(json.dumps(sample_iteration_history))
    output = tmp_path / "diagnoses"
    assert (
        _run(
            detector,
            monkeypatch,
            "--history",
            history,
            "--plateau-k",
            3,
            "--plateau-threshold",
            1,
            "--output-dir",
            output,
        )
        == 0
    )
    diagnosis = json.loads(next(output.glob("*.json")).read_text())
    assert "improvement_plateau" not in [t["trigger"] for t in diagnosis["triggers_fired"]]


def test_append_cli_creates_history_then_preserves_prior_iteration(tmp_path, monkeypatch):
    history = tmp_path / "history.json"
    evaluation = tmp_path / "eval.json"
    first = make_eval(45)
    evaluation.write_text(json.dumps(first))
    assert (
        _run(
            detector,
            monkeypatch,
            "--history",
            history,
            "--append-eval",
            evaluation,
            "--strategy-id",
            "demo",
            "--changes",
            "Initial probe",
        )
        == 0
    )
    original = json.loads(history.read_text())["iterations"][0]
    second = make_eval(62)
    evaluation.write_text(json.dumps(second))
    assert (
        _run(
            detector,
            monkeypatch,
            "--history",
            history,
            "--append-eval",
            evaluation,
            "--strategy-id",
            "demo",
            "--changes",
            "Tighten entry",
        )
        == 0
    )
    persisted = json.loads(history.read_text())
    assert persisted["strategy_id"] == "demo"
    assert persisted["iterations"][0] == original
    assert [it["iteration"] for it in persisted["iterations"]] == [1, 2]
    assert persisted["iterations"][1] == {
        "iteration": 2,
        "timestamp": "2026-10-04T12:00:00+00:00",
        "changes_from_previous": "Tighten entry",
        "eval": second,
    }


@pytest.mark.parametrize(
    "case,message",
    [
        ("missing", "history file not found"),
        ("json", "Invalid JSON"),
        ("schema", "strategy_id"),
    ],
)
def test_detector_input_errors_leave_no_output(tmp_path, monkeypatch, case, message, capsys):
    history = tmp_path / "history.json"
    if case != "missing":
        history.write_text("{" if case == "json" else "{}")
    output = tmp_path / "diagnoses"
    assert _run(detector, monkeypatch, "--history", history, "--output-dir", output) == 1
    assert message in capsys.readouterr().out
    assert not output.exists()


@pytest.mark.parametrize(
    "case,message",
    [
        ("id", "--strategy-id required"),
        ("missing", "eval file not found"),
        ("mismatch", "strategy_id mismatch"),
        ("json", "Expecting"),
    ],
)
def test_append_errors_preserve_history(tmp_path, monkeypatch, case, message, capsys):
    history = tmp_path / "history.json"
    history.write_text(json.dumps({"strategy_id": "existing", "iterations": []}))
    original = history.read_bytes()
    evaluation = tmp_path / "eval.json"
    if case != "missing":
        evaluation.write_text("{" if case == "json" else json.dumps(make_eval(45)))
    arguments = ["--history", history, "--append-eval", evaluation]
    if case != "id":
        arguments += ["--strategy-id", "other" if case == "mismatch" else "existing"]
    assert _run(detector, monkeypatch, *arguments) == 1
    assert message in capsys.readouterr().out
    assert history.read_bytes() == original


@pytest.mark.parametrize(
    "case,message",
    [
        ("diagnosis", "diagnosis file not found"),
        ("strategy", "strategy file not found"),
        ("mapping", "strategy file must be a YAML mapping"),
    ],
)
def test_generator_input_errors_leave_no_output(tmp_path, monkeypatch, case, message, capsys):
    diagnosis = tmp_path / "diagnosis.json"
    source = tmp_path / "draft.yaml"
    if case != "diagnosis":
        diagnosis.write_text("{}")
    if case != "strategy":
        source.write_text("[]" if case == "mapping" else yaml.safe_dump(_source_draft("demo")))
    output = tmp_path / "proposals"
    assert (
        _run(
            generator,
            monkeypatch,
            "--diagnosis",
            diagnosis,
            "--strategy",
            source,
            "--output-dir",
            output,
        )
        == 1
    )
    assert message in capsys.readouterr().out
    assert not output.exists()
