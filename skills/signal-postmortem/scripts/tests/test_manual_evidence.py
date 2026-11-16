"""Manual outcomes must retain source evidence and actual return semantics."""

import copy
import json
import math
import sys

import postmortem_analyzer as analyzer
import postmortem_recorder as recorder
import pytest


@pytest.fixture
def signal():
    return {
        "signal_id": "sig_demo_20261019_001",
        "ticker": "DEMO",
        "signal_date": "2026-10-19",
        "predicted_direction": "LONG",
        "source_skill": "manual-example",
        "entry_price": 50.0,
        "regime": "RISK_ON",
    }


def run_manual(
    monkeypatch, tmp_path, signal, *, data=None, exit_price="56", exit_date="2026-11-03"
):
    source = tmp_path / "signals.json"
    if not source.exists():
        source.write_text(json.dumps(data if data is not None else {"signals": [signal]}))
    monkeypatch.setenv("FMP_API_KEY", "fictional-key")  # pragma: allowlist secret

    def forbidden(*args, **kwargs):
        raise AssertionError("Manual recording must never fetch prices")

    monkeypatch.setattr(recorder, "fetch_price_data", forbidden)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            recorder.__file__,
            "--signals-file",
            str(source),
            "--signal-id",
            signal["signal_id"],
            "--exit-price",
            str(exit_price),
            "--exit-date",
            exit_date,
            "--outcome-notes",
            "closed with evidence",
            "--output-dir",
            str(tmp_path / "out"),
        ],
    )
    result = recorder.main()
    record = json.loads(
        (tmp_path / "out/postmortems" / f"pm_{signal['signal_id']}.json").read_text()
    )
    return result, record


@pytest.mark.parametrize("wrapped", [False, True])
@pytest.mark.parametrize(
    "direction,exit_price,category",
    [
        ("LONG", 56, "TRUE_POSITIVE"),
        ("SHORT", 44, "TRUE_POSITIVE"),
        ("LONG", 44, "FALSE_POSITIVE_SEVERE"),
        ("LONG", 50, "NEUTRAL"),
    ],
)
def test_manual_uses_exact_saved_signal(
    monkeypatch, tmp_path, signal, wrapped, direction, exit_price, category
):
    signal["predicted_direction"] = direction
    original = copy.deepcopy(signal)
    unrelated = {**signal, "signal_id": "unrelated", "entry_price": 9000}
    rows = [unrelated, signal]
    source = tmp_path / "signals.json"
    source.write_text(json.dumps({"signals": rows} if wrapped else rows, indent=3) + "\n")
    source_bytes = source.read_bytes()
    result, record = run_manual(
        monkeypatch,
        tmp_path,
        signal,
        data={"signals": rows} if wrapped else rows,
        exit_price=exit_price,
    )
    assert result is None
    for field in (
        "signal_id",
        "ticker",
        "signal_date",
        "source_skill",
        "predicted_direction",
        "entry_price",
    ):
        assert record[field] == signal[field]
    assert record["holding_days"] == 15
    assert record["exit_date"] == "2026-11-03"
    assert record["exit_price"] == exit_price
    assert record["outcome_notes"] == "closed with evidence"
    assert record["return_basis"] == "actual_exit"
    assert record["realized_returns"] == pytest.approx({"actual": (exit_price - 50) / 50})
    assert "5d" not in record["realized_returns"]
    assert record["outcome_category"] == category
    assert json.loads((tmp_path / "signals.json").read_text()) == (
        {"signals": rows} if wrapped else rows
    )
    assert signal == original
    assert source.read_bytes() == source_bytes


@pytest.mark.parametrize(
    "field,value",
    [
        ("entry_price", 0),
        ("entry_price", -1),
        ("entry_price", True),
        ("entry_price", "50"),
        ("entry_price", None),
        ("entry_price", float("nan")),
        ("entry_price", float("inf")),
        ("entry_price", 10**400),
        ("signal_date", "20261019"),
        ("signal_date", "2026-2-19"),
        ("signal_date", "2026-02-30"),
        ("signal_date", None),
        ("ticker", ""),
        ("source_skill", None),
        ("predicted_direction", "BUY"),
        ("signal_id", "../../outside"),
    ],
)
def test_invalid_source_does_not_overwrite(monkeypatch, tmp_path, signal, field, value):
    signal[field] = value
    out = tmp_path / "out/postmortems"
    out.mkdir(parents=True)
    saved = out / "pm_sig_demo_20261019_001.json"
    saved.write_text('{"existing":"preserve"}')
    before = {p: p.read_bytes() for p in out.iterdir()}
    with pytest.raises(SystemExit) as error:
        run_manual(monkeypatch, tmp_path, signal)
    assert error.value.code == 1
    assert {p: p.read_bytes() for p in out.iterdir()} == before
    assert not (tmp_path / "outside.json").exists()


@pytest.mark.parametrize(
    "exit_price,exit_date",
    [
        (0, "2026-11-03"),
        (-1, "2026-11-03"),
        ("nan", "2026-11-03"),
        ("inf", "2026-11-03"),
        (56, "20261103"),
        (56, "2026-10-18"),
        (56, "bad"),
    ],
)
def test_invalid_exit_leaves_no_record(monkeypatch, tmp_path, signal, exit_price, exit_date):
    with pytest.raises(SystemExit) as error:
        run_manual(monkeypatch, tmp_path, signal, exit_price=exit_price, exit_date=exit_date)
    assert error.value.code == 1
    assert not list((tmp_path / "out").rglob("*.json"))


@pytest.mark.parametrize(
    "data", [[], {}, {"signals": {}}, [None], {"signals": [{"signal_id": "other"}]}]
)
def test_missing_or_malformed_match_rejected(monkeypatch, tmp_path, signal, data):
    with pytest.raises(SystemExit) as error:
        run_manual(monkeypatch, tmp_path, signal, data=data)
    assert error.value.code == 1
    assert not list((tmp_path / "out").rglob("*.json"))


def test_duplicate_match_rejected(monkeypatch, tmp_path, signal):
    with pytest.raises(SystemExit) as error:
        run_manual(monkeypatch, tmp_path, signal, data=[signal, signal])
    assert error.value.code == 1
    assert not list((tmp_path / "out").rglob("*.json"))


def test_malformed_json_and_missing_file_have_controlled_error(monkeypatch, tmp_path, signal):
    (tmp_path / "signals.json").write_text("{broken")
    with pytest.raises(SystemExit) as error:
        run_manual(monkeypatch, tmp_path, signal)
    assert error.value.code == 1
    (tmp_path / "signals.json").unlink()
    monkeypatch.setattr(
        sys,
        "argv",
        [
            recorder.__file__,
            "--signal-id",
            signal["signal_id"],
            "--signals-file",
            str(tmp_path / "missing.json"),
            "--exit-price",
            "56",
            "--exit-date",
            "2026-11-03",
            "--output-dir",
            str(tmp_path / "out"),
        ],
    )
    with pytest.raises(SystemExit) as error:
        recorder.main()
    assert error.value.code == 1
    assert not list((tmp_path / "out").rglob("*.json"))


def test_source_file_required(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            recorder.__file__,
            "--signal-id",
            "example",
            "--exit-price",
            "56",
            "--exit-date",
            "2026-11-03",
            "--output-dir",
            str(tmp_path),
        ],
    )
    with pytest.raises(SystemExit) as error:
        recorder.main()
    assert error.value.code == 1
    assert "--signals-file" in capsys.readouterr().err
    assert not list(tmp_path.rglob("*.json"))


def test_actual_return_overflow_rejected(monkeypatch, tmp_path, signal):
    signal["entry_price"] = 1e-308
    with pytest.raises(SystemExit) as error:
        run_manual(monkeypatch, tmp_path, signal, exit_price=1e308)
    assert error.value.code == 1
    assert not list((tmp_path / "out").rglob("*.json"))


def test_same_day_exit_uses_zero_calendar_holding_days(monkeypatch, tmp_path, signal):
    _, record = run_manual(monkeypatch, tmp_path, signal, exit_date=signal["signal_date"])
    assert record["holding_days"] == 0
    assert record["realized_returns"]["actual"] == pytest.approx(0.12)


def test_manual_to_analyzer_retains_skill_month_and_real_accuracy(
    monkeypatch, tmp_path, signal, capsys
):
    _, record = run_manual(monkeypatch, tmp_path, signal)
    metrics = analyzer.calculate_skill_metrics([record])
    data = metrics[signal["source_skill"]]
    assert data["accuracy"] == 1
    assert data["avg_return_5d"] is None
    assert data["return_samples_5d"] == 0
    summary = analyzer.generate_summary(metrics, [record], ["skill", "month"])
    assert "| 2026-10 | 1 | 100.0% |" in summary
    assert "| manual-example | 1 | 100.0% | 0.0% | N/A |" in summary
    monkeypatch.setattr(
        sys,
        "argv",
        [
            analyzer.__file__,
            "--postmortems-dir",
            str(tmp_path / "out/postmortems"),
            "--output-dir",
            str(tmp_path / "analysis"),
        ],
    )
    analyzer.main()
    assert "Avg Return (5d): N/A" in capsys.readouterr().out


@pytest.mark.parametrize(
    "unmeasured",
    [
        {"actual": 0.12},
        {},
        {"5d": None},
        {"5d": True},
        {"5d": "0.1"},
        {"5d": float("nan")},
        {"5d": float("inf")},
        {"5d": 10**400},
    ],
)
def test_unmeasured_values_do_not_dilute_five_day_average(unmeasured):
    base = {"source_skill": "fixture", "outcome_category": "TRUE_POSITIVE"}
    metrics = analyzer.calculate_skill_metrics(
        [{**base, "realized_returns": {"5d": 0.1}}, {**base, "realized_returns": unmeasured}]
    )["fixture"]
    assert metrics["sample_size"] == 2
    assert metrics["accuracy"] == 1
    assert metrics["avg_return_5d"] == pytest.approx(0.1)
    assert metrics["return_samples_5d"] == 1


@pytest.mark.parametrize(
    "returns,expected",
    [
        ([1e308, 1e308], 1e308),
        ([sys.float_info.max] * 3, sys.float_info.max),
        ([sys.float_info.max, -sys.float_info.max], 0.0),
    ],
)
def test_average_is_finite_even_with_extreme_inputs(returns, expected):
    metrics = analyzer.calculate_skill_metrics(
        [
            {
                "source_skill": "fixture",
                "outcome_category": "TRUE_POSITIVE",
                "realized_returns": {"5d": r},
            }
            for r in returns
        ]
    )["fixture"]
    assert math.isfinite(metrics["avg_return_5d"])
    assert metrics["avg_return_5d"] == pytest.approx(expected)
    assert metrics["return_samples_5d"] == len(returns)


@pytest.mark.parametrize("alias", ["exact", "symlink", "hardlink"])
def test_source_output_collision_preserves_original_bytes(monkeypatch, tmp_path, signal, alias):
    target = tmp_path / "out/postmortems" / f"pm_{signal['signal_id']}.json"
    target.parent.mkdir(parents=True)
    source = target if alias == "exact" else tmp_path / "signals.json"
    source.write_text(json.dumps({"signals": [signal]}, indent=3) + "\n")
    if alias == "symlink":
        target.symlink_to(source)
    elif alias == "hardlink":
        target.hardlink_to(source)
    before = source.read_bytes()
    monkeypatch.setattr(
        sys,
        "argv",
        [
            recorder.__file__,
            "--signals-file",
            str(source),
            "--signal-id",
            signal["signal_id"],
            "--exit-price",
            "56",
            "--exit-date",
            "2026-11-03",
            "--output-dir",
            str(tmp_path / "out"),
        ],
    )
    with pytest.raises(SystemExit) as error:
        recorder.main()
    assert error.value.code == 1
    assert source.read_bytes() == before
    assert target.read_bytes() == before
