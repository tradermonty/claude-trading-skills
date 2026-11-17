import csv
import importlib.util
from datetime import date, timedelta
from pathlib import Path

import pytest
from build_entry_signals import build_entry_row, render_markdown, write_csv
from event_scanner import ScanResult


def row_with_history(special=True, n=24):
    history = [
        {
            "date": (date(2020, 1, 1) + timedelta(days=91 * i)).isoformat(),
            "dividend": 0.315,
            "label": "cash",
        }
        for i in range(n)
    ]
    if special:
        history.append({"date": "2023-02-10", "dividend": 2.5, "label": "special"})
    return build_entry_row(
        "ORI-LIKE",
        0.5,
        {"price": 39.68},
        {"lastDiv": 3.76},
        [{"dividendYield": 0.0699}] * 5,
        dividend_history=history,
    )


def test_special_inclusive_average_cannot_generate_regular_target():
    row = row_with_history()
    assert row["annual_dividend_per_share"] == 1.26
    assert row["buy_target_price"] is None
    assert row["target_yield_pct"] is None
    assert row["drop_needed_pct"] is None
    assert row["avg_5y_yield_pct"] is None
    assert row["signal"] == "ASSUMPTION-REQUIRED"
    assert row["annual_dividend_basis"] == "regular_only"
    assert row["historical_yield_basis"] == "provider_total_unverified"
    assert row["target_withheld_reason"] == "regular_only_average_unavailable"
    assert row["provider_avg_5y_yield_pct"] == 6.99
    assert row["t1_blocked"]


def test_short_history_cannot_prove_provider_average_regular_only():
    row = row_with_history(special=False, n=4)
    assert row["buy_target_price"] is None
    assert row["target_withheld_reason"] == "regular_only_average_unavailable"


def test_no_detected_special_is_not_proof_of_matching_five_year_basis():
    assert row_with_history(special=False)["buy_target_price"] is None


def test_legacy_provider_total_path_records_unverified_basis():
    row = build_entry_row(
        "LEGACY", 0.5, {"price": 100.0}, {"lastDiv": 4.0}, [{"dividendYield": 0.04}] * 5
    )
    assert row["buy_target_price"] == 88.89
    assert row["annual_dividend_basis"] == "provider_total_unverified"
    assert row["historical_yield_basis"] == "provider_total_unverified"
    assert row["yield_basis"] == "provider_total_unverified"


def test_csv_and_markdown_explain_withheld_target(tmp_path):
    row = row_with_history()
    path = tmp_path / "signals.csv"
    write_csv([row], path)
    with path.open() as f:
        saved = next(csv.DictReader(f))
    assert saved["buy_target_price"] == ""
    assert saved["target_withheld_reason"] == "regular_only_average_unavailable"
    assert saved["annual_dividend_basis"] == "regular_only"
    assert "regular_only_average_unavailable" in render_markdown([row], "2026-11-15", 0.5)


def test_explicit_empty_or_unusable_history_does_not_fall_back_to_profile():
    for history in ([], [{"date": "bad", "dividend": 0.3}]):
        row = build_entry_row(
            "EMPTY",
            0.5,
            {"price": 40.0},
            {"lastDiv": 3.0},
            [{"dividendYield": 0.07}] * 5,
            dividend_history=history,
        )
        assert row["buy_target_price"] is None
        assert row["target_withheld_reason"] == "regular_dividend_unavailable"
        assert row["t1_blocked"]


def growing_row(scan_result="NO_EVENT_FOUND", freeze=False):
    start = date(2022, 1, 1)
    history = [
        {
            "date": (start + timedelta(days=91 * i)).isoformat(),
            "dividend": 0.4 if freeze else 0.3 + 0.01 * i,
            "declarationDate": (start + timedelta(days=91 * i - 18)).isoformat(),
        }
        for i in range(16)
    ]
    return build_entry_row(
        "GROW",
        0.5,
        {"price": 30},
        {"lastDiv": 1.8},
        [{"dividendYield": 0.035}] * 5,
        dividend_history=history,
        floor_pct=3.0,
        as_of=history[-1]["date"],
        financials={
            "sector": "Consumer Defensive",
            "gaap_eps": 5,
            "adjusted_eps": 5,
            "adjusted_eps_source": "ISSUER_SUPPLEMENT",
            "fcf_per_share": 6,
        },
        event_scan=ScanResult(ticker="GROW", result=scan_result),
    )


@pytest.mark.parametrize(
    "scan_result",
    ["NO_EVENT_FOUND", "SKIPPED", "FAILED-DEGRADED", "CLEAN_CONFIRMED", "MINOR_EVENT_CAUTION"],
)
def test_withheld_target_stays_non_actionable_and_ingest_refuses(scan_result, monkeypatch):
    row = growing_row(scan_result)
    assert row["step1_verdict"] == "STEP1-PASS"
    assert row["payout_safety"]["safety_verdict"] == "PASS"
    assert row["verdict"] == "HOLD-REVIEW"
    assert row["t1_blocked"] is True
    assert "regular_only_average_unavailable" in row["verdict_reasons"]
    scripts = Path(__file__).resolve().parents[3] / "trader-memory-core" / "scripts"
    monkeypatch.syspath_prepend(str(scripts))
    spec = importlib.util.spec_from_file_location(
        "issue769_thesis_ingest", scripts / "thesis_ingest.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with pytest.raises(ValueError, match="not actionable"):
        module.ingest_kanchi(row, "synthetic-signals.json")


def test_provider_yield_present_is_not_reported_missing():
    row = growing_row()
    assert row["provider_avg_5y_yield_pct"] == 3.5
    assert "avg_5y_yield_missing" not in row["notes"]
    assert "regular_only_average_unavailable" in row["notes"]


def test_freeze_with_clean_safety_reports_entry_basis_blocker():
    row = growing_row("CLEAN_CONFIRMED", freeze=True)
    assert row["dividend_basis"]["freeze_flag"]
    assert row["payout_safety"]["safety_verdict"] == "PASS"
    assert row["verdict"] == "HOLD-REVIEW"
    assert "regular_only_average_unavailable" in row["verdict_reasons"]
    assert "dividend_freeze_unconfirmed_safety" not in row["verdict_reasons"]
