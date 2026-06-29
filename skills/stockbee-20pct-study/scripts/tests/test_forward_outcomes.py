import importlib.util
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "run_20pct_study.py"
spec = importlib.util.spec_from_file_location("run_20pct_study", SCRIPT)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def bars_from_rows(rows):
    return [
        mod.Bar(date=row_date, open=open_, high=high, low=low, close=close, volume=1000)
        for row_date, open_, high, low, close in rows
    ]


def test_update_forward_outcomes_for_up_event():
    prices = {
        "UPCO": bars_from_rows(
            [
                ("2026-01-01", 100, 101, 99, 100),
                ("2026-01-02", 120, 123, 118, 120),
                ("2026-01-03", 121, 130, 119, 128),
                ("2026-01-04", 128, 132, 124, 126),
                ("2026-01-05", 126, 135, 125, 134),
            ]
        )
    }
    records = [
        {
            "record_id": "UPCO:2026-01-02:UP:1D",
            "symbol": "UPCO",
            "event_date": "2026-01-02",
            "direction": "UP",
            "outcomes": {},
        }
    ]

    updated, metadata = mod.update_forward_outcomes(records, prices, horizons=[1, 3])

    outcome_1d = updated[0]["outcomes"]["1d"]
    outcome_3d = updated[0]["outcomes"]["3d"]
    assert outcome_1d["status"] == "MATURED"
    assert round(outcome_1d["close_return_pct"], 2) == 6.67
    assert outcome_3d["directional_mfe_pct"] == 12.5
    assert outcome_3d["outcome_tag"] in {"STRONG_CONTINUATION", "CONTINUED"}
    assert metadata["counts"]["matured"] == 2


def test_update_forward_outcomes_for_down_event_directional_return():
    prices = {
        "DNCO": bars_from_rows(
            [
                ("2026-01-01", 100, 101, 99, 100),
                ("2026-01-02", 80, 82, 78, 80),
                ("2026-01-03", 78, 79, 70, 72),
                ("2026-01-04", 73, 74, 68, 70),
            ]
        )
    }
    records = [
        {
            "record_id": "DNCO:2026-01-02:DOWN:1D",
            "symbol": "DNCO",
            "event_date": "2026-01-02",
            "direction": "DOWN",
            "outcomes": {},
        }
    ]

    updated, _ = mod.update_forward_outcomes(records, prices, horizons=[2])

    outcome = updated[0]["outcomes"]["2d"]
    assert outcome["status"] == "MATURED"
    assert outcome["close_return_pct"] < 0
    assert outcome["directional_close_return_pct"] > 0
    assert outcome["directional_mfe_pct"] > 0


def test_down_event_directional_excursions_use_entry_close_denominator():
    prices = {
        "DNCO": bars_from_rows(
            [
                ("2026-01-01", 100, 101, 99, 100),
                ("2026-01-02", 80, 82, 78, 80),
                ("2026-01-03", 82, 90, 70, 72),
            ]
        )
    }
    records = [
        {
            "record_id": "DNCO:2026-01-02:DOWN:1D",
            "symbol": "DNCO",
            "event_date": "2026-01-02",
            "direction": "DOWN",
            "outcomes": {},
        }
    ]

    updated, _ = mod.update_forward_outcomes(records, prices, horizons=[1])

    outcome = updated[0]["outcomes"]["1d"]
    assert outcome["directional_close_return_pct"] == 10.0
    assert outcome["directional_mfe_pct"] == 12.5
    assert outcome["directional_mae_pct"] == -12.5


def test_update_forward_outcomes_marks_incomplete_window_pending():
    prices = {
        "UPCO": bars_from_rows(
            [
                ("2026-01-01", 100, 101, 99, 100),
                ("2026-01-02", 120, 123, 118, 120),
                ("2026-01-03", 121, 130, 119, 128),
            ]
        )
    }
    records = [
        {
            "record_id": "UPCO:2026-01-02:UP:1D",
            "symbol": "UPCO",
            "event_date": "2026-01-02",
            "direction": "UP",
            "outcomes": {},
        }
    ]

    updated, metadata = mod.update_forward_outcomes(records, prices, horizons=[1, 3])

    assert updated[0]["outcomes"]["1d"]["status"] == "MATURED"
    assert updated[0]["outcomes"]["3d"]["status"] == "PENDING"
    assert updated[0]["outcomes"]["3d"]["future_bars_available"] == 1
    assert metadata["counts"]["pending"] == 1
