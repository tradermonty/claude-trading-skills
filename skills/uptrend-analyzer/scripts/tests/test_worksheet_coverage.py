"""evaluation_coverage accounting for the uptrend dashboard worksheets (#711)."""

import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data_fetcher import WORKSHEET_TO_DISPLAY  # noqa: E402
from uptrend_analyzer import build_worksheet_coverage  # noqa: E402


def _latest(ratio: Optional[float] = 0.30):
    return {"date": "2026-01-15", "ratio": ratio, "trend": "up", "slope": 0.001}


def _summary_row(sector, ratio: Optional[float] = 0.30):
    return {"Sector": sector, "Ratio": ratio, "10MA": 0.28, "Trend": "Up"}


def test_all_declared_worksheets_evaluated_is_complete():
    sector_latest = {worksheet: _latest() for worksheet in WORKSHEET_TO_DISPLAY}
    summary = [_summary_row(name) for name in WORKSHEET_TO_DISPLAY.values()]

    coverage = build_worksheet_coverage(_latest(), sector_latest, summary)

    assert coverage["universe_size"] == 12
    assert coverage["evaluated"] == 12
    assert coverage["verdict"] == "complete"
    assert coverage["not_evaluated_reasons"] == {}


def test_rows_without_a_usable_ratio_are_invalid_data():
    sector_latest = {worksheet: _latest(ratio=None) for worksheet in WORKSHEET_TO_DISPLAY}

    coverage = build_worksheet_coverage(_latest(), sector_latest, [])

    assert coverage["universe_size"] == 12
    assert coverage["evaluated"] == 1
    assert coverage["not_evaluated_reasons"] == {"invalid_data": 11}
    assert coverage["verdict"] == "partial"


def test_sector_summary_is_used_as_the_documented_fallback():
    sector_latest = {worksheet: _latest(ratio=None) for worksheet in WORKSHEET_TO_DISPLAY}
    summary = [_summary_row(name, ratio=0.25) for name in WORKSHEET_TO_DISPLAY.values()]

    coverage = build_worksheet_coverage(_latest(), sector_latest, summary)

    assert coverage["evaluated"] == 12
    assert coverage["verdict"] == "complete"


def test_absent_worksheets_are_missing_data():
    coverage = build_worksheet_coverage(_latest(), {}, [])

    assert coverage["universe_size"] == 12
    assert coverage["evaluated"] == 1
    assert coverage["not_evaluated_reasons"] == {"missing_data": 11}
    assert coverage["verdict"] == "partial"


def test_empty_primary_input_is_not_evaluable():
    coverage = build_worksheet_coverage(None, {}, [])

    assert coverage["universe_size"] == 12
    assert coverage["evaluated"] == 0
    assert coverage["not_evaluated_reasons"] == {"missing_data": 12}
    assert coverage["verdict"] == "not_evaluable"
