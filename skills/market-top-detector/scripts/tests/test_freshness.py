"""Tests for Data Freshness Management"""

from datetime import date, timedelta


class TestDataFreshness:
    """Test data freshness computation."""

    def test_today_returns_1(self):
        """Data from today -> freshness factor 1.0."""
        from market_top_detector import compute_data_freshness
        today = date.today().isoformat()
        result = compute_data_freshness({"breadth_200dma_date": today})
        assert result["breadth_200dma"]["factor"] == 1.0

    def test_two_days_returns_095(self):
        """Data from 2 days ago -> 0.95."""
        from market_top_detector import compute_data_freshness
        d = (date.today() - timedelta(days=2)).isoformat()
        result = compute_data_freshness({"breadth_200dma_date": d})
        assert result["breadth_200dma"]["factor"] == 0.95

    def test_five_days_returns_085(self):
        """Data from 5 days ago -> 0.85."""
        from market_top_detector import compute_data_freshness
        d = (date.today() - timedelta(days=5)).isoformat()
        result = compute_data_freshness({"breadth_200dma_date": d})
        assert result["breadth_200dma"]["factor"] == 0.85

    def test_ten_days_returns_070(self):
        """Data from 10 days ago -> 0.70."""
        from market_top_detector import compute_data_freshness
        d = (date.today() - timedelta(days=10)).isoformat()
        result = compute_data_freshness({"breadth_200dma_date": d})
        assert result["breadth_200dma"]["factor"] == 0.70

    def test_no_date_returns_1(self):
        """No date provided -> assume fresh (1.0)."""
        from market_top_detector import compute_data_freshness
        result = compute_data_freshness({})
        assert result["overall_confidence"] == 1.0

    def test_no_value_returns_none(self):
        """Date given but no value -> entry should still compute."""
        from market_top_detector import compute_data_freshness
        d = date.today().isoformat()
        result = compute_data_freshness({"put_call_date": d})
        assert result["put_call"]["factor"] == 1.0

    def test_overall_confidence_is_min(self):
        """Overall confidence = min of all provided factors."""
        from market_top_detector import compute_data_freshness
        today = date.today().isoformat()
        old = (date.today() - timedelta(days=10)).isoformat()
        result = compute_data_freshness({
            "breadth_200dma_date": today,
            "put_call_date": old,
        })
        assert result["overall_confidence"] == 0.70
