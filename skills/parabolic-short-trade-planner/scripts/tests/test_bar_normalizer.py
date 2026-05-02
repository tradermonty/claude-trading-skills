"""Tests for bar_normalizer.normalize_bars(bars, output_order=...).

The normalizer is the single boundary between FMP raw output and calculator
input. Calculators always receive chronological order; the FMP client itself
does not normalize.
"""

import pytest
from bar_normalizer import normalize_bars


class TestOutputOrder:
    def test_chronological_returns_oldest_first(self, parabolic_bars_recent_first):
        out = normalize_bars(parabolic_bars_recent_first, output_order="chronological")
        dates = [b["date"] for b in out]
        assert dates == sorted(dates), "chronological output must be oldest-first"

    def test_recent_first_returns_newest_first(self, parabolic_bars_chrono):
        out = normalize_bars(parabolic_bars_chrono, output_order="recent_first")
        dates = [b["date"] for b in out]
        assert dates == sorted(dates, reverse=True), "recent_first must be newest-first"


class TestIdempotent:
    def test_chronological_input_chronological_output_unchanged(self, parabolic_bars_chrono):
        out1 = normalize_bars(parabolic_bars_chrono, output_order="chronological")
        out2 = normalize_bars(out1, output_order="chronological")
        assert out1 == out2


class TestDuplicateRemoval:
    def test_keeps_last_occurrence(self, bars_with_duplicate_dates):
        out = normalize_bars(bars_with_duplicate_dates, output_order="chronological")
        dates = [b["date"] for b in out]
        # 04-01, 04-02 (de-duped), 04-03 → 3 unique dates
        assert len(dates) == 3
        # The kept 04-02 row should be the higher-volume one (last seen)
        d2 = [b for b in out if b["date"] == "2026-04-02"][0]
        assert d2["volume"] == 2_000_000
        assert d2["close"] == 101


class TestGapWarning:
    def test_warns_on_missing_calendar_day_but_keeps_bars(self, bars_with_gaps, recwarn):
        out = normalize_bars(bars_with_gaps, output_order="chronological", warn_on_gaps=True)
        # No bars are dropped — calendar gaps may include holidays/weekends
        assert len(out) == len(bars_with_gaps)


class TestInvalidArgs:
    def test_unknown_order_raises(self, parabolic_bars_chrono):
        with pytest.raises(ValueError):
            normalize_bars(parabolic_bars_chrono, output_order="ascending")
