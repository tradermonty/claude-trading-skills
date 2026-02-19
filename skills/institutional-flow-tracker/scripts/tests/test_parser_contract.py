"""FMP v3 field contract tests for data_quality module.

Verifies that the shared module uses correct FMP API field names
(shares/change) and does NOT depend on nonexistent fields
(totalShares/totalInvested).
"""

import pytest
from data_quality import (
    classify_holder,
    calculate_filtered_metrics,
    reliability_grade,
)


# --- Realistic FMP v3 holder records ---

def _make_holder(holder, shares, change, date="2025-09-30"):
    """Create a holder record matching FMP v3 institutional-holder schema."""
    return {
        "holder": holder,
        "shares": shares,
        "change": change,
        "dateReported": date,
    }


class TestClassifyHolder:
    """classify_holder must use 'shares' and 'change' fields only."""

    def test_genuine_holder_small_change(self):
        h = _make_holder("Vanguard", 100_000, 5_000)
        assert classify_holder(h) == "genuine"

    def test_genuine_holder_negative_change(self):
        h = _make_holder("Fidelity", 200_000, -10_000)
        assert classify_holder(h) == "genuine"

    def test_new_full_position(self):
        """change == shares > 0 means a brand-new full position."""
        h = _make_holder("NewFund", 50_000, 50_000)
        assert classify_holder(h) == "new_full"

    def test_exited_position(self):
        """shares == 0 means the holder has fully exited."""
        h = _make_holder("ExitFund", 0, -30_000)
        assert classify_holder(h) == "exited"

    def test_zero_shares_zero_change(self):
        h = _make_holder("Ghost", 0, 0)
        assert classify_holder(h) == "exited"

    def test_does_not_reference_totalShares(self):
        """Holder with totalShares but no shares should still work via 'shares' key."""
        h = {"holder": "Legacy", "shares": 100, "change": 10, "totalShares": 9999}
        result = classify_holder(h)
        assert result == "genuine"

    def test_missing_change_field_defaults_to_unknown(self):
        """If 'change' field is missing, classification should be 'unknown'."""
        h = {"holder": "Broken", "shares": 100}
        assert classify_holder(h) == "unknown"


class TestCalculateFilteredMetrics:
    """calculate_filtered_metrics should use only genuine holders."""

    def test_genuine_only_metrics(self):
        holders = [
            _make_holder("Vanguard", 100_000, 5_000),
            _make_holder("Fidelity", 200_000, -10_000),
            _make_holder("NewFund", 50_000, 50_000),  # new_full -> excluded
        ]
        metrics = calculate_filtered_metrics(holders)
        # Only Vanguard + Fidelity are genuine
        assert metrics["genuine_count"] == 2
        assert metrics["net_change"] == 5_000 + (-10_000)  # -5000
        assert metrics["total_shares_genuine"] == 100_000 + 200_000

    def test_all_new_full_returns_zero_metrics(self):
        holders = [
            _make_holder("A", 100, 100),
            _make_holder("B", 200, 200),
        ]
        metrics = calculate_filtered_metrics(holders)
        assert metrics["genuine_count"] == 0
        assert metrics["net_change"] == 0

    def test_empty_holders(self):
        metrics = calculate_filtered_metrics([])
        assert metrics["genuine_count"] == 0
        assert metrics["net_change"] == 0
        assert metrics["pct_change"] == 0.0

    def test_pct_change_calculation(self):
        """pct_change = net_change / (total_shares_genuine - net_change) * 100"""
        holders = [
            _make_holder("Vanguard", 1000, 100),  # genuine
            _make_holder("Fidelity", 2000, -200),  # genuine
        ]
        metrics = calculate_filtered_metrics(holders)
        # net_change = 100 + (-200) = -100
        # total_shares_genuine = 3000
        # previous = 3000 - (-100) = 3100
        # pct_change = -100 / 3100 * 100 = -3.226...
        assert abs(metrics["pct_change"] - (-100 / 3100 * 100)) < 0.01


class TestReliabilityGrade:
    """reliability_grade uses coverage_ratio, match_ratio, genuine_ratio."""

    def test_grade_a_high_quality(self):
        # coverage < 3, genuine >= 0.7
        assert reliability_grade(1.5, 0.8, 0.9) == "A"

    def test_grade_b_moderate_quality(self):
        # genuine >= 0.3 but fails A criteria
        assert reliability_grade(5.0, 0.5, 0.5) == "B"

    def test_grade_c_unreliable(self):
        # genuine < 0.3
        assert reliability_grade(10.0, 0.1, 0.1) == "C"

    def test_grade_c_when_coverage_high_but_genuine_low(self):
        # coverage > 3 and genuine < 0.3
        assert reliability_grade(27.0, 0.05, 0.01) == "C"

    def test_grade_a_boundary(self):
        # Exactly at boundary: coverage = 3 should NOT be A
        assert reliability_grade(3.0, 0.8, 0.7) != "A"

    def test_grade_b_boundary(self):
        # genuine = 0.3 should be B
        assert reliability_grade(5.0, 0.5, 0.3) == "B"

    def test_grade_a_requires_match_ratio(self):
        """Grade A requires match_ratio >= 0.5 in addition to other criteria."""
        # coverage < 3, genuine >= 0.7, but match_ratio < 0.5 -> NOT A
        assert reliability_grade(1.5, 0.3, 0.9) == "B"

    def test_grade_a_with_sufficient_match_ratio(self):
        """Grade A is granted when match_ratio >= 0.5."""
        assert reliability_grade(1.5, 0.5, 0.9) == "A"
