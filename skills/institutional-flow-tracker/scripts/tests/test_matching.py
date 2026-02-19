"""Asymmetric data matching tests for data_quality module.

Verifies that non-symmetric holder counts between quarters
(e.g., 5415 current vs 201 previous) do not produce inflated
percent_change values.
"""

import pytest
from data_quality import (
    classify_holder,
    calculate_coverage_ratio,
    calculate_match_ratio,
    calculate_filtered_metrics,
    reliability_grade,
)


def _make_holder(holder, shares, change, date="2025-09-30"):
    return {
        "holder": holder,
        "shares": shares,
        "change": change,
        "dateReported": date,
    }


class TestCoverageRatio:

    def test_symmetric_coverage(self):
        current = [_make_holder(f"H{i}", 100, 10) for i in range(200)]
        previous = [_make_holder(f"H{i}", 90, 5) for i in range(200)]
        ratio = calculate_coverage_ratio(current, previous)
        assert ratio == 1.0

    def test_asymmetric_coverage_nflx_like(self):
        """NFLX-like: 5415 current vs 201 previous -> ratio ~27"""
        current = [_make_holder(f"H{i}", 100, 100) for i in range(5415)]
        previous = [_make_holder(f"H{i}", 100, 10) for i in range(201)]
        ratio = calculate_coverage_ratio(current, previous)
        assert ratio == pytest.approx(5415 / 201, rel=0.01)

    def test_no_previous_holders(self):
        current = [_make_holder("H1", 100, 100)]
        previous = []
        ratio = calculate_coverage_ratio(current, previous)
        assert ratio == float("inf")

    def test_no_current_holders(self):
        current = []
        previous = [_make_holder("H1", 100, 10)]
        ratio = calculate_coverage_ratio(current, previous)
        assert ratio == 0.0


class TestMatchRatio:

    def test_perfect_match(self):
        current = [_make_holder(f"H{i}", 100, 10) for i in range(100)]
        previous = [_make_holder(f"H{i}", 90, 5) for i in range(100)]
        ratio = calculate_match_ratio(current, previous)
        assert ratio == 1.0

    def test_no_match(self):
        current = [_make_holder(f"C{i}", 100, 100) for i in range(50)]
        previous = [_make_holder(f"P{i}", 100, 10) for i in range(50)]
        ratio = calculate_match_ratio(current, previous)
        assert ratio == 0.0

    def test_partial_match(self):
        current = [
            _make_holder("Shared1", 100, 10),
            _make_holder("Shared2", 200, -50),
            _make_holder("NewOnly", 50, 50),
        ]
        previous = [
            _make_holder("Shared1", 90, 5),
            _make_holder("Shared2", 250, -20),
            _make_holder("OldOnly", 100, 10),
        ]
        ratio = calculate_match_ratio(current, previous)
        # 2 shared names out of 3 current holders
        assert ratio == pytest.approx(2 / 3, rel=0.01)


class TestAAPLLikeData:
    """AAPL-like scenario: high genuine ratio (~91%), stable data."""

    @pytest.fixture
    def aapl_holders(self):
        holders = []
        # 91% genuine (small change relative to shares)
        for i in range(910):
            holders.append(_make_holder(f"Genuine{i}", 10_000, 500))
        # 5% new_full
        for i in range(50):
            holders.append(_make_holder(f"New{i}", 1_000, 1_000))
        # 4% exited
        for i in range(40):
            holders.append(_make_holder(f"Exited{i}", 0, -1_000))
        return holders

    def test_genuine_ratio_high(self, aapl_holders):
        metrics = calculate_filtered_metrics(aapl_holders)
        total = len(aapl_holders)
        genuine_ratio = metrics["genuine_count"] / total
        assert genuine_ratio >= 0.9

    def test_pct_change_not_inflated(self, aapl_holders):
        metrics = calculate_filtered_metrics(aapl_holders)
        # With genuine holders only, pct_change should be reasonable
        assert abs(metrics["pct_change"]) < 10  # not +400% etc.

    def test_reliability_grade_a(self, aapl_holders):
        metrics = calculate_filtered_metrics(aapl_holders)
        total = len(aapl_holders)
        genuine_ratio = metrics["genuine_count"] / total
        # For AAPL, coverage_ratio would be ~1.0 (symmetric)
        grade = reliability_grade(1.0, 0.9, genuine_ratio)
        assert grade == "A"


class TestNFLXLikeData:
    """NFLX-like scenario: very low genuine ratio (~1%), highly asymmetric."""

    @pytest.fixture
    def nflx_holders(self):
        holders = []
        # 99% new_full (change == shares)
        for i in range(5365):
            holders.append(_make_holder(f"New{i}", 1_000, 1_000))
        # 1% genuine
        for i in range(50):
            holders.append(_make_holder(f"Genuine{i}", 10_000, 200))
        return holders

    def test_genuine_ratio_very_low(self, nflx_holders):
        metrics = calculate_filtered_metrics(nflx_holders)
        total = len(nflx_holders)
        genuine_ratio = metrics["genuine_count"] / total
        assert genuine_ratio < 0.02

    def test_pct_change_uses_genuine_only(self, nflx_holders):
        """Even with 5000+ holders, pct_change is based on 50 genuine ones."""
        metrics = calculate_filtered_metrics(nflx_holders)
        # genuine: 50 holders, 10000 shares each, change 200 each
        # net_change = 50 * 200 = 10000
        # total_shares_genuine = 50 * 10000 = 500000
        # previous = 500000 - 10000 = 490000
        # pct_change = 10000/490000 * 100 = ~2.04%
        assert abs(metrics["pct_change"] - (10_000 / 490_000 * 100)) < 0.1

    def test_reliability_grade_c(self, nflx_holders):
        metrics = calculate_filtered_metrics(nflx_holders)
        total = len(nflx_holders)
        genuine_ratio = metrics["genuine_count"] / total
        grade = reliability_grade(27.0, 0.01, genuine_ratio)
        assert grade == "C"
