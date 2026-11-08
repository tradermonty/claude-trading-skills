"""Selected COT market vintage must not be hidden by a fresh report date."""

import json
import socket
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_weekly_price_action as consumer  # noqa: E402

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
    direction, reason, ctx = consumer.resolve_direction_from_detector(
        report, symbol, "2026-07-08", 10
    )
    return direction == "CROWDED_LONG", reason, ctx.get("data_date"), ctx.get("detector_age_days")


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


def test_cli_emits_stale_refusal_before_any_provider_call(tmp_path, monkeypatch):
    path = tmp_path / "detector.json"
    path.write_text(json.dumps(mixed_report("2023-01-03")))
    monkeypatch.delenv("FMP_API_KEY", raising=False)
    blocked = Mock(side_effect=AssertionError("network forbidden"))
    monkeypatch.setattr(socket.socket, "connect", blocked)
    output = tmp_path / "reports"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "consumer",
            "--symbol",
            "GC",
            "--detector-json",
            str(path),
            "--as-of",
            "2026-07-08",
            "--output-dir",
            str(output),
            "--format",
            "json",
        ],
    )
    try:
        code = consumer.main()
    except SystemExit as exc:
        code = exc.code
    assert code in (None, 0)
    files = list(output.glob("*.json"))
    assert len(files) == 1
    report = json.loads(files[0].read_text())
    assert report["verdict"] == "INSUFFICIENT_DATA"
    assert report["verdict_reason"] == "detector_json_stale"
    blocked.assert_not_called()


def test_vintage_resolution_does_not_mutate_the_input():
    report = mixed_report("2026-06-30", {"market_data_dates": {"GC": "2026-07-07"}})
    before = json.dumps(report, sort_keys=True)
    assert resolve(report) == (True, None, "2026-06-30", 8)
    assert json.dumps(report, sort_keys=True) == before


@pytest.mark.parametrize("value", ["bad-date", []])
def test_explicit_invalid_selected_map_date_is_not_ignored(value):
    report = mixed_report("2026-07-07", {"market_data_dates": {"GC": value}})
    assert resolve(report)[1] == "detector_invalid_data_date"
