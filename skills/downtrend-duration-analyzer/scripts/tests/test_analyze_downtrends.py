"""
Tests for analyze_downtrends.py

Tests peak/trough detection, downtrend identification, and statistics computation.
"""

import pandas as pd
from analyze_downtrends import (
    compute_statistics,
    detect_peaks_troughs,
    find_downtrends,
    get_market_cap_tier,
    group_statistics,
)


class TestGetMarketCapTier:
    """Tests for market cap tier classification."""

    def test_mega_cap(self):
        """Test mega cap classification."""
        assert get_market_cap_tier(250_000_000_000) == "Mega"
        assert get_market_cap_tier(200_000_000_000) == "Mega"

    def test_large_cap(self):
        """Test large cap classification."""
        assert get_market_cap_tier(100_000_000_000) == "Large"
        assert get_market_cap_tier(10_000_000_000) == "Large"

    def test_mid_cap(self):
        """Test mid cap classification."""
        assert get_market_cap_tier(5_000_000_000) == "Mid"
        assert get_market_cap_tier(2_000_000_000) == "Mid"

    def test_small_cap(self):
        """Test small cap classification."""
        assert get_market_cap_tier(1_000_000_000) == "Small"
        assert get_market_cap_tier(100_000_000) == "Small"

    def test_none_market_cap(self):
        """Test None market cap returns Unknown."""
        assert get_market_cap_tier(None) == "Unknown"


class TestDetectPeaksTroughs:
    """Tests for peak and trough detection algorithm."""

    def test_simple_peak_detection(self):
        """Test detection of a simple peak."""
        # Create data with a clear peak at index 5
        dates = pd.date_range("2024-01-01", periods=11)
        closes = [100, 102, 104, 106, 108, 110, 108, 106, 104, 102, 100]
        prices = pd.DataFrame({"date": dates, "close": closes})

        peaks, troughs = detect_peaks_troughs(prices, peak_window=2, trough_window=2)

        assert 5 in peaks  # Peak at 110

    def test_simple_trough_detection(self):
        """Test detection of a simple trough."""
        # Create data with a clear trough at index 5
        dates = pd.date_range("2024-01-01", periods=11)
        closes = [100, 98, 96, 94, 92, 90, 92, 94, 96, 98, 100]
        prices = pd.DataFrame({"date": dates, "close": closes})

        peaks, troughs = detect_peaks_troughs(prices, peak_window=2, trough_window=2)

        assert 5 in troughs  # Trough at 90

    def test_multiple_peaks_troughs(self):
        """Test detection of multiple peaks and troughs."""
        # Create oscillating data
        dates = pd.date_range("2024-01-01", periods=21)
        closes = [
            100,
            105,
            110,
            105,
            100,
            95,
            90,
            95,
            100,
            105,
            110,
            105,
            100,
            95,
            90,
            95,
            100,
            105,
            110,
            105,
            100,
        ]
        prices = pd.DataFrame({"date": dates, "close": closes})

        peaks, troughs = detect_peaks_troughs(prices, peak_window=2, trough_window=2)

        # Should find peaks at 110 and troughs at 90
        assert len(peaks) >= 2
        assert len(troughs) >= 2

    def test_insufficient_data(self):
        """Test that insufficient data returns empty lists."""
        dates = pd.date_range("2024-01-01", periods=5)
        closes = [100, 102, 104, 102, 100]
        prices = pd.DataFrame({"date": dates, "close": closes})

        peaks, troughs = detect_peaks_troughs(prices, peak_window=10, trough_window=10)

        assert peaks == []
        assert troughs == []


class TestFindDowntrends:
    """Tests for downtrend identification."""

    def test_identify_downtrend(self):
        """Test identification of a downtrend period."""
        dates = pd.date_range("2024-01-01", periods=21)
        # Peak at index 5 (110), trough at index 15 (90)
        closes = [
            100,
            102,
            104,
            106,
            108,
            110,
            108,
            106,
            104,
            102,
            100,
            98,
            96,
            94,
            92,
            90,
            92,
            94,
            96,
            98,
            100,
        ]
        prices = pd.DataFrame({"date": dates, "close": closes})

        peaks = [5]
        troughs = [15]

        downtrends = find_downtrends(prices, peaks, troughs, min_depth_pct=5.0, min_duration_days=3)

        assert len(downtrends) == 1
        assert downtrends[0]["duration_days"] == 10
        assert downtrends[0]["depth_pct"] < 0  # Negative because it's a decline

    def test_filter_shallow_downtrend(self):
        """Test that shallow downtrends are filtered out."""
        dates = pd.date_range("2024-01-01", periods=11)
        # Only 2% decline - should be filtered with 5% threshold
        closes = [100, 101, 102, 101, 100, 99, 98, 99, 100, 101, 102]
        prices = pd.DataFrame({"date": dates, "close": closes})

        peaks = [2]
        troughs = [6]

        downtrends = find_downtrends(prices, peaks, troughs, min_depth_pct=5.0, min_duration_days=1)

        assert len(downtrends) == 0

    def test_filter_short_downtrend(self):
        """Test that very short downtrends are filtered out."""
        dates = pd.date_range("2024-01-01", periods=11)
        closes = [100, 105, 110, 100, 90, 95, 100, 105, 110, 105, 100]
        prices = pd.DataFrame({"date": dates, "close": closes})

        peaks = [2]
        troughs = [4]

        # 2 days duration should be filtered with min_duration_days=3
        downtrends = find_downtrends(prices, peaks, troughs, min_depth_pct=5.0, min_duration_days=3)

        assert len(downtrends) == 0


class TestComputeStatistics:
    """Tests for statistics computation."""

    def test_empty_downtrends(self):
        """Test statistics for empty input."""
        stats = compute_statistics([])

        assert stats["total_downtrends"] == 0
        assert stats["median_duration_days"] == 0
        assert stats["mean_duration_days"] == 0

    def test_single_downtrend(self):
        """Test statistics for single downtrend."""
        downtrends = [{"duration_days": 20, "depth_pct": -10.0}]

        stats = compute_statistics(downtrends)

        assert stats["total_downtrends"] == 1
        assert stats["median_duration_days"] == 20
        assert stats["mean_duration_days"] == 20.0

    def test_multiple_downtrends(self):
        """Test statistics for multiple downtrends."""
        downtrends = [
            {"duration_days": 10},
            {"duration_days": 20},
            {"duration_days": 30},
            {"duration_days": 40},
            {"duration_days": 50},
        ]

        stats = compute_statistics(downtrends)

        assert stats["total_downtrends"] == 5
        assert stats["median_duration_days"] == 30
        assert stats["mean_duration_days"] == 30.0
        assert stats["p25_duration_days"] == 20
        assert stats["p75_duration_days"] == 40


class TestGroupStatistics:
    """Tests for grouped statistics computation."""

    def test_group_by_sector(self):
        """Test grouping by sector."""
        downtrends = [
            {"sector": "Technology", "duration_days": 10},
            {"sector": "Technology", "duration_days": 20},
            {"sector": "Healthcare", "duration_days": 30},
        ]

        grouped = group_statistics(downtrends, "sector")

        assert "Technology" in grouped
        assert "Healthcare" in grouped
        assert grouped["Technology"]["count"] == 2
        assert grouped["Healthcare"]["count"] == 1

    def test_group_by_market_cap(self):
        """Test grouping by market cap tier."""
        downtrends = [
            {"market_cap_tier": "Mega", "duration_days": 10},
            {"market_cap_tier": "Mega", "duration_days": 15},
            {"market_cap_tier": "Small", "duration_days": 30},
        ]

        grouped = group_statistics(downtrends, "market_cap_tier")

        assert "Mega" in grouped
        assert "Small" in grouped
        assert grouped["Mega"]["median_days"] == 12  # (10 + 15) / 2 rounded
        assert grouped["Small"]["median_days"] == 30
