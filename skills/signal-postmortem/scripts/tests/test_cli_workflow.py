"""Deterministic recorder/analyzer CLI regressions with fictional market data."""

import json
import sys
from datetime import datetime, timezone

import postmortem_analyzer as analyzer
import postmortem_recorder as recorder
import pytest
import yaml
from requests.sessions import Session

NOW = datetime(2026, 10, 4, 12)


class FixedDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW if tz is None else NOW.replace(tzinfo=timezone.utc).astimezone(tz)

    @classmethod
    def utcnow(cls):
        return NOW


@pytest.fixture(autouse=True)
def offline_clock(monkeypatch):
    monkeypatch.setattr(recorder, "datetime", FixedDatetime)
    monkeypatch.setattr(analyzer, "datetime", FixedDatetime)
    monkeypatch.delenv("FMP_API_KEY", raising=False)

    def forbidden(*args, **kwargs):
        raise AssertionError("Unexpected network request")

    monkeypatch.setattr(Session, "request", forbidden)


def cli(monkeypatch, module, *args):
    monkeypatch.setattr(sys, "argv", [module.__file__, *map(str, args)])
    return module.main()


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def signal(index=0, **overrides):
    return {
        "signal_id": f"sig_{index}",
        "ticker": f"FICTION{index}",
        "signal_date": "2026-09-01",
        "source_skill": "fictional-breakout",
        "predicted_direction": "LONG",
        "entry_price": 100.0,
        "regime": "RISK_ON",
        **overrides,
    }


def test_recorder_to_analyzer_exports_real_feedback(monkeypatch, tmp_path, capsys):
    signals_path = tmp_path / "signals.json"
    write_json(signals_path, {"signals": [signal(i) for i in range(8)] + [signal(8, ticker="")]})
    original = signals_path.read_bytes()
    calls = []

    def prices(ticker, start, end, api_key):
        assert (start, end, api_key) == ("2026-09-01", "2026-09-26", "fictional-key")
        calls.append(ticker)
        positive = int(ticker.removeprefix("FICTION")) < 6
        # Day 5 is Sunday; the forward lookup must use Monday September 7.
        return {
            "2026-09-07": 110.0 if positive else 90.0,
            "2026-09-21": 120.0 if positive else 80.0,
        }

    monkeypatch.setattr(recorder, "fetch_price_data", prices)
    output = tmp_path / "recorded"
    assert (
        cli(
            monkeypatch,
            recorder,
            "--signals-file",
            signals_path,
            "--api-key",
            "fictional-key",
            "--holding-periods",
            "5,20",
            "--output-dir",
            output,
        )
        is None
    )
    captured = capsys.readouterr()
    assert "Processed 8/9 signals" in captured.out
    assert "TRUE_POSITIVE: 6" in captured.out
    assert "FALSE_POSITIVE_SEVERE: 2" in captured.out
    assert "missing ticker or date" in captured.err
    batch = read_json(output / "postmortem_batch_2026-10-04_120000.json")
    assert (batch["total_signals"], batch["processed"]) == (9, 8)
    assert batch["generated_at"] == "2026-10-04T12:00:00Z"
    assert batch["source_file"] == str(signals_path)
    records = batch["postmortems"]
    assert len(calls) == 8
    for index, record in enumerate(records):
        assert read_json(output / "postmortems" / f"pm_sig_{index}.json") == record
        assert record["recorded_at"] == "2026-10-04T12:00:00Z"
        assert record["exit_date"] == "2026-09-07"
        assert record["holding_days"] == 6
        assert record["realized_returns"] == pytest.approx(
            {"5d": 0.1 if index < 6 else -0.1, "20d": 0.2 if index < 6 else -0.2}
        )
        assert record["outcome_category"] == (
            "TRUE_POSITIVE" if index < 6 else "FALSE_POSITIVE_SEVERE"
        )

    pm_dir = output / "postmortems"
    write_json(pm_dir / "pm_stale.json", {**records[0], "recorded_at": "2020-01-01T00:00:00Z"})
    (pm_dir / "pm_broken.json").write_text("{broken", encoding="utf-8")
    before = {p.name: p.read_bytes() for p in pm_dir.iterdir()}
    analysis = tmp_path / "analysis"
    assert (
        cli(
            monkeypatch,
            analyzer,
            "--postmortems-dir",
            pm_dir,
            "--days-back",
            30,
            "--min-sample-size",
            8,
            "--generate-weight-feedback",
            "--generate-improvement-backlog",
            "--summary",
            "--output-dir",
            analysis,
        )
        is None
    )
    captured = capsys.readouterr()
    assert "Loaded 8 postmortems" in captured.out
    assert "Error loading" in captured.err
    feedback = read_json(analysis / "weight_feedback_2026-10-04.json")
    assert feedback["generated_at"] == "2026-10-04T12:00:00Z"
    assert feedback["min_sample_threshold"] == 8
    assert feedback["analysis_period"]["total_postmortems"] == 8
    assert feedback["confidence"] == "LOW"
    assert len(feedback["skill_adjustments"]) == 1
    adjustment = feedback["skill_adjustments"][0]
    assert (adjustment["skill"], adjustment["sample_size"]) == ("fictional-breakout", 8)
    assert adjustment["suggested_weight"] == 1.1
    assert adjustment["accuracy"] == 0.75
    assert adjustment["false_positive_rate"] == 0.25
    backlog = yaml.safe_load((analysis / "skill_improvement_backlog_2026-10-04.yaml").read_text())
    assert [b["issue_type"] for b in backlog] == ["overconfidence", "false_positive_cluster"]
    assert [b["priority_score"] for b in backlog] == [300, 200]
    assert backlog[0]["evidence"] == {
        "severe_fp_rate": 0.25,
        "severe_fp_count": 2,
        "sample_size": 8,
    }
    assert backlog[1]["evidence"]["regime_correlation"] == "RISK_ON"
    assert all(
        b["status"] == "pending" and b["generated_at"] == "2026-10-04T12:00:00Z" for b in backlog
    )
    summary = (analysis / "postmortem_summary_2026-10-04.md").read_text()
    assert "| Overall Accuracy | 75.0% |" in summary
    assert "| fictional-breakout | 8 | 75.0% | 25.0% | 5.00% |" in summary
    assert "| 2026-09 | 8 | 75.0% |" in summary
    assert "| FALSE_POSITIVE_SEVERE | 2 | 25.0% |" in summary
    assert signals_path.read_bytes() == original
    assert {p.name: p.read_bytes() for p in pm_dir.iterdir()} == before


def test_batch_without_key_records_neutral_and_skips_unusable_signals(
    monkeypatch, tmp_path, capsys
):
    source = tmp_path / "signals.json"
    write_json(source, [signal(), signal(1, entry_price=0), signal(2, signal_date="invalid")])
    output = tmp_path / "reports"
    cli(monkeypatch, recorder, "--signals-file", source, "--output-dir", output)
    batch = read_json(output / "postmortem_batch_2026-10-04_120000.json")
    assert (batch["processed"], batch["total_signals"]) == (1, 3)
    record = batch["postmortems"][0]
    assert record["realized_returns"] == {}
    assert record["outcome_category"] == "NEUTRAL"
    assert record["exit_price"] == 100.0
    assert record["exit_date"] == "2026-09-06"
    assert sorted(p.name for p in (output / "postmortems").iterdir()) == ["pm_sig_0.json"]
    captured = capsys.readouterr()
    assert "No FMP API key" in captured.err
    assert "No entry price" in captured.err
    assert "Invalid signal date" in captured.err


@pytest.mark.parametrize(
    "signal_id,ticker,date",
    [("sig_FICTION_2026-09-01", "FICTION", "2026-09-01"), ("manual", "UNKNOWN", "2026-10-04")],
)
def test_manual_recording_preserves_notes_without_inventing_returns(
    monkeypatch, tmp_path, capsys, signal_id, ticker, date
):
    cli(
        monkeypatch,
        recorder,
        "--signal-id",
        signal_id,
        "--exit-price",
        "105",
        "--exit-date",
        "2026-10-04",
        "--outcome-notes",
        "fictional manual observation",
        "--output-dir",
        tmp_path,
    )
    record = read_json(tmp_path / "postmortems" / f"pm_{signal_id}.json")
    assert (record["ticker"], record["signal_date"]) == (ticker, date)
    assert (record["exit_price"], record["entry_price"]) == (105, 0)
    assert record["realized_returns"] == {}
    assert record["outcome_category"] == "NEUTRAL"
    assert record["outcome_notes"] == "fictional manual observation"
    assert "Outcome: NEUTRAL" in capsys.readouterr().out


def test_list_ready_uses_fixed_cutoff_and_does_not_record(monkeypatch, tmp_path, capsys):
    source = tmp_path / "signals"
    write_json(
        source / "one.json", [signal(signal_date="2026-09-29"), signal(1, signal_date="2026-09-30")]
    )
    write_json(source / "two.json", {"signals": [signal(2, signal_date="2026-09-28")]})
    (source / "broken.json").write_text("{", encoding="utf-8")
    output = tmp_path / "reports"
    cli(
        monkeypatch,
        recorder,
        "--signals-dir",
        source,
        "--list-ready",
        "--min-days",
        "5",
        "--output-dir",
        output,
    )
    captured = capsys.readouterr()
    assert "Found 2 signals" in captured.out
    assert "sig_0:" in captured.out and "sig_2:" in captured.out
    assert "sig_1:" not in captured.out
    assert "Error reading" in captured.err
    assert not list(output.rglob("*.json"))


@pytest.mark.parametrize(
    "args,message",
    [
        ((), "--signals-file required"),
        (("--list-ready",), "--signals-dir required"),
        (("--signal-id", "manual"), "--exit-price and --exit-date required"),
        (("--signals-file", "missing.json"), "Signals file not found"),
        (("--signals-file", "empty.json"), "No signals found"),
    ],
)
def test_recorder_errors_write_no_records(monkeypatch, tmp_path, capsys, args, message):
    monkeypatch.chdir(tmp_path)
    write_json(tmp_path / "empty.json", {"signals": []})
    output = tmp_path / "reports"
    with pytest.raises(SystemExit) as error:
        cli(monkeypatch, recorder, *args, "--output-dir", output)
    assert error.value.code == 1
    assert message in capsys.readouterr().err
    assert not list(output.rglob("*.json"))


def analyzer_fixture(tmp_path):
    pm_dir = tmp_path / "postmortems"
    write_json(
        pm_dir / "pm_one.json",
        {
            "source_skill": "fictional-breakout",
            "signal_date": "2026-09-01",
            "outcome_category": "TRUE_POSITIVE",
            "realized_returns": {"5d": 0.1},
            "recorded_at": "2026-10-01T00:00:00Z",
        },
    )
    return pm_dir


def test_analyzer_default_metrics_and_group_selection(monkeypatch, tmp_path, capsys):
    pm_dir = analyzer_fixture(tmp_path)
    output = tmp_path / "analysis"
    cli(monkeypatch, analyzer, "--postmortems-dir", pm_dir, "--output-dir", output)
    captured = capsys.readouterr()
    assert "Samples: 1" in captured.out
    assert "Accuracy: 100.0%" in captured.out
    assert "FP Rate: 0.0%" in captured.out
    assert "Avg Return (5d): 10.00%" in captured.out
    assert list(output.iterdir()) == []
    cli(
        monkeypatch,
        analyzer,
        "--postmortems-dir",
        pm_dir,
        "--summary",
        "--group-by",
        "month",
        "--generate-weight-feedback",
        "--min-sample-size",
        "2",
        "--output-dir",
        output,
    )
    summary = (output / "postmortem_summary_2026-10-04.md").read_text()
    assert "## By Month" in summary
    assert "## By Skill" not in summary
    assert "| 2026-09 | 1 | 100.0% |" in summary
    assert read_json(output / "weight_feedback_2026-10-04.json")["skill_adjustments"] == []


@pytest.mark.parametrize("stale", [False, True])
def test_analyzer_empty_or_stale_inputs_create_no_output(monkeypatch, tmp_path, capsys, stale):
    pm_dir = tmp_path / "postmortems"
    if stale:
        write_json(pm_dir / "pm_stale.json", {"recorded_at": "2020-01-01T00:00:00Z"})
    output = tmp_path / "analysis"
    with pytest.raises(SystemExit) as error:
        cli(monkeypatch, analyzer, "--postmortems-dir", pm_dir, "--output-dir", output)
    assert error.value.code == 1
    assert "No postmortems found" in capsys.readouterr().err
    assert not output.exists()
