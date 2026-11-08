"""Selected COT market vintage must not be hidden by a fresh report date."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gate_logic as consumer  # noqa: E402

ABSENT = object()


def mixed_report(row_date="2026-07-07", provenance=ABSENT):
    row = {"symbol": "GC", "classification": "CROWDED_LONG", "status": "ok"}
    if row_date is not ABSENT:
        row["data_date"] = row_date
    report = {
        "schema_version": "1.0",
        "run_context": {"data_date": "2026-07-07"},
        "markets": [
            {"symbol": "ES", "classification": "CROWDED_LONG", "data_date": "2026-07-07"},
            row,
        ],
    }
    if provenance is not ABSENT:
        report["data_provenance"] = provenance
    return report


def resolve(report, symbol="GC"):
    value = consumer.normalize_crowding(
        report, None, symbol=symbol, as_of="2026-07-08", max_age_days=10
    )
    return value.state == consumer.STATE_CONFIRMED, value.reason, value.data_date, value.age_days


@pytest.mark.parametrize(
    "row_date,provenance,reason,date,age",
    [
        ("2023-01-03", ABSENT, "detector_json_stale", None, None),
        ("2026-07-09", ABSENT, "detector_future_data_date", None, None),
        (None, ABSENT, "detector_missing_data_date", None, None),
        ("", ABSENT, "detector_missing_data_date", None, None),
        (20260707, ABSENT, "detector_invalid_data_date", None, None),
        ([], ABSENT, "detector_invalid_data_date", None, None),
        ({}, ABSENT, "detector_invalid_data_date", None, None),
        ("bad-date", ABSENT, "detector_invalid_data_date", None, None),
        (ABSENT, ABSENT, None, "2026-07-07", 1),
        (ABSENT, {"market_data_dates": {"GC": "2023-01-03"}}, "detector_json_stale", None, None),
        (
            "2026-07-07",
            {"market_data_dates": {"GC": "2026-07-09"}},
            "detector_future_data_date",
            None,
            None,
        ),
        ("2026-07-07", {"market_data_dates": {"GC": "2026-06-30"}}, None, "2026-06-30", 8),
        ("2026-06-28", ABSENT, None, "2026-06-28", 10),
        ("2026-06-27", ABSENT, "detector_json_stale", None, None),
        ("2026-06-30", {"market_data_dates": {"ES": "2023-01-03"}}, None, "2026-06-30", 8),
        ("2026-07-07T00:00:00Z", ABSENT, None, "2026-07-07", 1),
        (ABSENT, {"market_data_dates": {"GC": None}}, "detector_missing_data_date", None, None),
        ("2026-07-07", {"market_data_dates": None}, "detector_invalid_data_date", None, None),
        ("2026-07-07", None, "detector_invalid_data_date", None, None),
    ],
)
def test_selected_market_vintage(row_date, provenance, reason, date, age):
    accepted, actual_reason, actual_date, actual_age = resolve(mixed_report(row_date, provenance))
    assert actual_reason == reason
    assert accepted == (reason is None)
    if reason is None:
        assert actual_date == date
        assert actual_age == age


def test_stale_market_does_not_poison_fresh_other_symbol():
    report = mixed_report(
        "2023-01-03", {"market_data_dates": {"GC": "2023-01-03", "ES": "2026-07-07"}}
    )
    assert resolve(report)[1] == "detector_json_stale"
    assert resolve(report, "ES") == (True, None, "2026-07-07", 1)


def test_fresh_row_cannot_bypass_stale_report_date():
    report = mixed_report()
    report["run_context"]["data_date"] = "2023-01-03"
    assert resolve(report)[1] == "detector_json_stale"


@pytest.mark.parametrize("row_date,expected", [("2023-01-03", "NO_TRADE"), ("2026-07-07", "SIZED")])
def test_selected_vintage_reaches_gate_and_sizer_cli(tmp_path, row_date, expected):
    import subprocess

    crowding = consumer.normalize_crowding(
        mixed_report(row_date), None, symbol="GC", as_of="2026-07-08", max_age_days=10
    )
    news = consumer.NormalizedInput(
        kind=consumer.STEP_NEWS,
        state=consumer.STATE_CONFIRMED,
        verdict="CONFIRMED",
        confidence="HIGH",
    )
    price = consumer.NormalizedInput(
        kind=consumer.STEP_PRICE,
        state=consumer.STATE_CONFIRMED,
        verdict="CONFIRMED",
        confidence="HIGH",
        stop_reference=2001.0,
        entry_trigger="key reversal",
    )
    gate = consumer.build_gate_result(
        symbol="GC",
        crowding=crowding,
        news=news,
        price=price,
        max_detector_age_days=10,
        max_report_age_days=3,
        as_of="2026-07-08",
    )
    assert gate["setup_status"] == (
        "READY_FOR_PLAN" if expected == "SIZED" else "INSUFFICIENT_EVIDENCE"
    )
    if expected == "NO_TRADE":
        assert gate["missing_confirmations"][0]["reason"] == "detector_json_stale"
    path = tmp_path / "gate.json"
    path.write_text(json.dumps(gate))
    root = Path(__file__).resolve().parents[4]
    script = root / "skills/futures-position-sizer/scripts/futures_position_sizer.py"
    output = tmp_path / "sizing"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--gate-json",
            str(path),
            "--entry",
            "2000",
            "--account-size",
            "100000",
            "--risk-pct",
            "1",
            "--as-of",
            "2026-07-08",
            "--output-dir",
            str(output),
            "--format",
            "json",
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads((output / "futures_position_size_GC_2026-07-08.json").read_text())
    assert payload["sizing_status"] == expected
    if expected == "NO_TRADE":
        assert payload["no_trade_reason"] == "gate_not_ready"


def test_vintage_resolution_does_not_mutate_the_input():
    report = mixed_report("2026-06-30", {"market_data_dates": {"GC": "2026-07-07"}})
    before = json.dumps(report, sort_keys=True)
    assert resolve(report) == (True, None, "2026-06-30", 8)
    assert json.dumps(report, sort_keys=True) == before


@pytest.mark.parametrize("value", ["bad-date", []])
def test_explicit_invalid_selected_map_date_is_not_ignored(value):
    report = mixed_report("2026-07-07", {"market_data_dates": {"GC": value}})
    assert resolve(report)[1] == "detector_invalid_data_date"


def test_selected_oldest_age_drives_gate_near_stale_warning():
    result = consumer.normalize_crowding(
        mixed_report("2026-06-30"), None, symbol="GC", as_of="2026-07-08", max_age_days=10
    )
    assert result.state == consumer.STATE_CONFIRMED
    assert result.age_days == 8
    assert "detector_near_stale" in result.warnings
    assert "detector_data_date_divergence" in result.warnings
