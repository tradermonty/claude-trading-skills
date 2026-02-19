"""Tests for lifecycle_calculator data quality check."""

from calculators.lifecycle_calculator import has_sufficient_lifecycle_data


class TestHasSufficientLifecycleData:
    def test_all_none_returns_false(self):
        """All None stock-based sub-scores means insufficient data."""
        assert has_sufficient_lifecycle_data(None, None, None) is False

    def test_any_present_returns_true(self):
        """Any non-None sub-score means sufficient data."""
        assert has_sufficient_lifecycle_data(50.0, None, None) is True
        assert has_sufficient_lifecycle_data(None, 60.0, None) is True
        assert has_sufficient_lifecycle_data(None, None, 40.0) is True

    def test_all_present_returns_true(self):
        assert has_sufficient_lifecycle_data(50.0, 60.0, 40.0) is True
