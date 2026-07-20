"""Tests for cot_index.py — pure COT Index calculation module.

No network, no filesystem I/O. Run with:
    python3 -m pytest skills/cot-contrarian-detector/scripts/tests/ -v
"""

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIR))

from cot_index import (  # noqa: E402
    classify_extreme,
    compute_cot_index,
    compute_net_position,
    compute_oi_normalized_net,
    compute_week_over_week_change,
    sort_dedupe_rows,
)

# A real-shaped row using the exact FMP legacy COT report field names
# (see references/cot-index-calculation.md for the field glossary).
SAMPLE_ROW = {
    "date": "2026-07-07 00:00:00",
    "sector": "INDICES",
    "name": "S&P 500 E-Mini (ES)",
    "contractUnits": "$50 x Index",
    "openInterestAll": 2000000,
    "noncommPositionsLongAll": 100000,
    "noncommPositionsShortAll": 142891,
    "noncommPositionsSpreadAll": 50000,
    "commPositionsLongAll": 900000,
    "commPositionsShortAll": 850000,
    "nonreptPositionsLongAll": 30000,
    "nonreptPositionsShortAll": 25000,
    "changeInNoncommLongAll": 1500,
    "changeInNoncommShortAll": -800,
    "pctOfOiNoncommLongAll": 5.0,
    "pctOfOiNoncommShortAll": 7.1,
    "tradersNoncommLongAll": 120,
    "tradersNoncommShortAll": 95,
    "concNetLe4TdrLongAll": 12.5,
    "concNetLe4TdrShortAll": 15.0,
}


class TestComputeNetPosition:
    def test_net_position_from_fixture_row(self):
        # 100000 long - 142891 short = -42891 (net short)
        assert compute_net_position(SAMPLE_ROW) == -42891

    def test_net_position_all_long(self):
        row = {"noncommPositionsLongAll": 500, "noncommPositionsShortAll": 100}
        assert compute_net_position(row) == 400

    def test_net_position_missing_fields_treated_as_zero(self):
        assert compute_net_position({}) == 0


class TestComputeCotIndex:
    def test_index_100_at_max(self):
        # Current value equals the window max -> index 100
        series = [10.0, 20.0, 30.0, 40.0, 50.0]
        assert compute_cot_index(series, lookback_weeks=5) == 100.0

    def test_index_0_at_min(self):
        series = [50.0, 40.0, 30.0, 20.0, 10.0]
        assert compute_cot_index(series, lookback_weeks=5) == 0.0

    def test_index_50_at_midpoint(self):
        series = [0.0, 100.0, 50.0]
        assert compute_cot_index(series, lookback_weeks=3) == 50.0

    def test_insufficient_history_returns_none(self):
        series = [10.0, 20.0, 30.0]
        assert compute_cot_index(series, lookback_weeks=52) is None

    def test_max_equals_min_returns_none(self):
        series = [25.0, 25.0, 25.0, 25.0]
        assert compute_cot_index(series, lookback_weeks=4) is None

    def test_uses_only_the_lookback_window_not_full_history(self):
        # Older values outside the window must not affect the result.
        series = [-1000.0, -1000.0] + [10.0, 20.0, 30.0, 40.0, 50.0]
        assert compute_cot_index(series, lookback_weeks=5) == 100.0

    def test_exact_lookback_length_is_sufficient(self):
        series = [1.0, 2.0, 3.0]
        assert compute_cot_index(series, lookback_weeks=3) is not None


class TestComputeOiNormalizedNet:
    def test_normalized_net_from_fixture_row(self):
        expected = -42891 / 2000000
        assert compute_oi_normalized_net(SAMPLE_ROW) == expected

    def test_oi_zero_returns_none(self):
        row = {"openInterestAll": 0, "noncommPositionsLongAll": 10, "noncommPositionsShortAll": 5}
        assert compute_oi_normalized_net(row) is None

    def test_oi_missing_returns_none(self):
        row = {"noncommPositionsLongAll": 10, "noncommPositionsShortAll": 5}
        assert compute_oi_normalized_net(row) is None

    def test_oi_non_numeric_returns_none(self):
        row = {
            "openInterestAll": "n/a",
            "noncommPositionsLongAll": 10,
            "noncommPositionsShortAll": 5,
        }
        assert compute_oi_normalized_net(row) is None


class TestClassifyExtreme:
    def test_boundary_high_exactly_90_is_crowded_long(self):
        assert classify_extreme(90.0, threshold_high=90.0, threshold_low=10.0) == "CROWDED_LONG"

    def test_boundary_low_exactly_10_is_crowded_short(self):
        assert classify_extreme(10.0, threshold_high=90.0, threshold_low=10.0) == "CROWDED_SHORT"

    def test_just_above_low_threshold_is_neutral(self):
        assert classify_extreme(10.01, threshold_high=90.0, threshold_low=10.0) == "NEUTRAL"

    def test_just_below_high_threshold_is_neutral(self):
        assert classify_extreme(89.99, threshold_high=90.0, threshold_low=10.0) == "NEUTRAL"

    def test_midpoint_is_neutral(self):
        assert classify_extreme(50.0) == "NEUTRAL"

    def test_none_index_is_neutral(self):
        assert classify_extreme(None) == "NEUTRAL"

    def test_custom_thresholds(self):
        assert classify_extreme(80.0, threshold_high=75.0, threshold_low=25.0) == "CROWDED_LONG"
        assert classify_extreme(20.0, threshold_high=75.0, threshold_low=25.0) == "CROWDED_SHORT"


class TestSortDedupeRows:
    def test_sorts_ascending_by_date(self):
        rows = [
            {"date": "2026-06-16 00:00:00", "v": 2},
            {"date": "2026-06-02 00:00:00", "v": 1},
            {"date": "2026-06-09 00:00:00", "v": 1.5},
        ]
        result = sort_dedupe_rows(rows)
        assert [r["date"] for r in result] == [
            "2026-06-02 00:00:00",
            "2026-06-09 00:00:00",
            "2026-06-16 00:00:00",
        ]

    def test_dedupes_by_date_keeping_last_occurrence(self):
        rows = [
            {"date": "2026-06-02 00:00:00", "v": "stale"},
            {"date": "2026-06-02 00:00:00", "v": "fresh"},
        ]
        result = sort_dedupe_rows(rows)
        assert len(result) == 1
        assert result[0]["v"] == "fresh"

    def test_rows_missing_date_are_dropped(self):
        rows = [{"date": "2026-06-02 00:00:00", "v": 1}, {"v": "no date"}]
        result = sort_dedupe_rows(rows)
        assert len(result) == 1

    def test_empty_input(self):
        assert sort_dedupe_rows([]) == []


class TestComputeWeekOverWeekChange:
    def test_change_between_last_two_weeks(self):
        series = [10.0, 20.0, 35.0]
        assert compute_week_over_week_change(series) == 15.0

    def test_negative_change(self):
        series = [10.0, 20.0, 5.0]
        assert compute_week_over_week_change(series) == -15.0

    def test_insufficient_history_returns_none(self):
        assert compute_week_over_week_change([10.0]) is None
        assert compute_week_over_week_change([]) is None
