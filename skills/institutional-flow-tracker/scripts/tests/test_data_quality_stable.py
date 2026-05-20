"""Tests for the /stable aggregate helpers in data_quality.

Covers coverage_grade (breadth-based reliability), the quarter-walk-back
helpers (current_quarter, iter_quarters, quarter_end_date), and normalize_holder.
"""

import datetime

from data_quality import (
    coverage_grade,
    current_quarter,
    iter_quarters,
    normalize_holder,
    quarter_end_date,
)


class TestCoverageGrade:
    """coverage_grade grades reliability from holder breadth + prior quarter."""

    def test_grade_a_dense_with_prior(self):
        assert coverage_grade(6000, 6300) == "A"

    def test_grade_a_boundary(self):
        # Exactly 50 holders with a prior quarter -> A
        assert coverage_grade(50, 40) == "A"

    def test_grade_b_thin_but_usable(self):
        assert coverage_grade(20, 18) == "B"

    def test_grade_b_boundary(self):
        # Exactly 10 holders -> still usable (B)
        assert coverage_grade(10, 8) == "B"

    def test_grade_c_no_prior_quarter(self):
        # No comparable prior quarter -> change not measurable -> C
        assert coverage_grade(500, 0) == "C"

    def test_grade_c_too_few_holders(self):
        assert coverage_grade(9, 8) == "C"

    def test_grade_c_zero_holders(self):
        assert coverage_grade(0, 0) == "C"

    def test_custom_thresholds(self):
        assert coverage_grade(30, 25, min_reliable=20) == "A"
        assert coverage_grade(15, 12, min_usable=20) == "C"


class TestIterQuarters:
    def test_descends_across_year_boundary(self):
        assert list(iter_quarters(2026, 1, 3)) == [(2026, 1), (2025, 4), (2025, 3)]

    def test_single_quarter(self):
        assert list(iter_quarters(2025, 3, 1)) == [(2025, 3)]

    def test_wraps_multiple_years(self):
        result = list(iter_quarters(2026, 2, 6))
        assert result == [(2026, 2), (2026, 1), (2025, 4), (2025, 3), (2025, 2), (2025, 1)]


class TestCurrentQuarter:
    def test_q1(self):
        assert current_quarter(datetime.date(2026, 2, 15)) == (2026, 1)

    def test_q2(self):
        assert current_quarter(datetime.date(2026, 5, 20)) == (2026, 2)

    def test_q4(self):
        assert current_quarter(datetime.date(2025, 12, 31)) == (2025, 4)


class TestQuarterEndDate:
    def test_q1(self):
        assert quarter_end_date(2026, 1) == "2026-03-31"

    def test_q4(self):
        assert quarter_end_date(2025, 4) == "2025-12-31"


class TestNormalizeHolder:
    def test_maps_stable_fields(self):
        raw = {
            "investorName": "BLACKROCK, INC.",
            "sharesNumber": 1_144_695_425,
            "changeInSharesNumber": -9_970_306,
            "isNew": False,
            "isSoldOut": False,
        }
        h = normalize_holder(raw)
        assert h == {
            "name": "BLACKROCK, INC.",
            "shares": 1_144_695_425,
            "change": -9_970_306,
            "is_new": False,
            "is_sold_out": False,
        }

    def test_blank_name_becomes_unknown(self):
        h = normalize_holder({"investorName": "", "sharesNumber": 100, "changeInSharesNumber": 10})
        assert h["name"] == "Unknown"

    def test_blank_name_falls_back_to_cik(self):
        h = normalize_holder({"investorName": "", "cik": "0002012383", "sharesNumber": 100})
        assert h["name"] == "CIK 0002012383"

    def test_missing_fields_default_to_zero(self):
        h = normalize_holder({"investorName": "Acme"})
        assert h["shares"] == 0
        assert h["change"] == 0
        assert h["is_new"] is False
