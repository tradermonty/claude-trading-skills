"""Tests for Composite Scorer and FTD Detection"""

from scorer import (
    COMPONENT_WEIGHTS,
    calculate_composite_score,
    detect_follow_through_day,
)


class TestCompositeScore:
    """Test composite scoring."""

    def test_all_zeros(self):
        scores = {k: 0 for k in COMPONENT_WEIGHTS}
        result = calculate_composite_score(scores)
        assert result["composite_score"] == 0
        assert "Green" in result["zone"]

    def test_all_100(self):
        scores = {k: 100 for k in COMPONENT_WEIGHTS}
        result = calculate_composite_score(scores)
        assert result["composite_score"] == 100.0
        assert "Critical" in result["zone"]

    def test_moderate_risk(self):
        """Calibration target: ~48-50 for moderate risk."""
        scores = {
            "distribution_days": 45,
            "leading_stocks": 52,
            "defensive_rotation": 82,
            "breadth_divergence": 20,
            "index_technical": 42,
            "sentiment": 62,
        }
        result = calculate_composite_score(scores)
        assert 40 <= result["composite_score"] <= 55

    def test_weights_sum_to_1(self):
        total = sum(COMPONENT_WEIGHTS.values())
        assert abs(total - 1.0) < 0.001

    def test_strongest_weakest(self):
        scores = {
            "distribution_days": 90,
            "leading_stocks": 10,
            "defensive_rotation": 50,
            "breadth_divergence": 50,
            "index_technical": 50,
            "sentiment": 50,
        }
        result = calculate_composite_score(scores)
        assert result["strongest_warning"]["component"] == "distribution_days"
        assert result["weakest_warning"]["component"] == "leading_stocks"


class TestDataQuality:
    """Test data quality tracking."""

    def test_all_available(self):
        scores = {k: 50 for k in COMPONENT_WEIGHTS}
        avail = {k: True for k in COMPONENT_WEIGHTS}
        result = calculate_composite_score(scores, avail)
        dq = result["data_quality"]
        assert dq["available_count"] == 6
        assert "Complete" in dq["label"]
        assert dq["missing_components"] == []

    def test_some_missing(self):
        scores = {k: 50 for k in COMPONENT_WEIGHTS}
        avail = {k: True for k in COMPONENT_WEIGHTS}
        avail["breadth_divergence"] = False
        avail["sentiment"] = False
        result = calculate_composite_score(scores, avail)
        dq = result["data_quality"]
        assert dq["available_count"] == 4
        assert "Partial" in dq["label"]
        assert len(dq["missing_components"]) == 2

    def test_many_missing(self):
        scores = {k: 50 for k in COMPONENT_WEIGHTS}
        avail = {k: False for k in COMPONENT_WEIGHTS}
        avail["distribution_days"] = True
        avail["leading_stocks"] = True
        result = calculate_composite_score(scores, avail)
        dq = result["data_quality"]
        assert dq["available_count"] == 2
        assert "Limited" in dq["label"]

    def test_backward_compat_no_availability(self):
        """Without data_availability, all assumed available."""
        scores = {k: 50 for k in COMPONENT_WEIGHTS}
        result = calculate_composite_score(scores)
        dq = result["data_quality"]
        assert dq["available_count"] == 6
        assert "Complete" in dq["label"]


class TestFollowThroughDay:
    """Test O'Neil-strict FTD detection."""

    def test_not_applicable_below_40(self):
        result = detect_follow_through_day([], 30.0)
        assert result["applicable"] is False

    def test_insufficient_data(self):
        result = detect_follow_through_day([{"close": 100}] * 5, 50.0)
        assert result["ftd_detected"] is False

    def test_no_swing_low(self):
        """Flat market → no swing low found."""
        history = [{"close": 100, "volume": 1000000, "date": f"day-{i}"} for i in range(30)]
        result = detect_follow_through_day(history, 50.0)
        assert result["ftd_detected"] is False

    def test_ftd_detected_on_clear_pattern(self):
        """
        Create a clear pattern:
        - Days 0-9: prices rise from 100 to 109 (establishing high)
        - Days 10-14: decline from 109 to 100 (5+ down days, ~8% drop)
        - Day 15: swing low at 100
        - Day 16: rally day 1 (up from 100 to 101)
        - Day 17-18: rally continues (101.5, 102)
        - Day 19 (rally day 4): FTD - big gain +2% on higher volume

        History is most-recent-first, so reversed.
        """
        bars = []
        # Build chronologically, then reverse
        # Days 0-9: uptrend
        for i in range(10):
            bars.append({"close": 100 + i, "volume": 1000000, "date": f"2026-01-{i + 1:02d}"})

        # Days 10-14: decline (5 down days from 109)
        decline_prices = [107, 105, 103, 101, 100]
        for i, p in enumerate(decline_prices):
            bars.append({"close": p, "volume": 1100000, "date": f"2026-01-{11 + i:02d}"})

        # Day 15: swing low
        bars.append({"close": 99.5, "volume": 1200000, "date": "2026-01-16"})

        # Day 16: rally day 1
        bars.append({"close": 101, "volume": 1000000, "date": "2026-01-17"})

        # Day 17-18: rally continues
        bars.append({"close": 101.5, "volume": 1000000, "date": "2026-01-18"})
        bars.append({"close": 102, "volume": 1000000, "date": "2026-01-19"})

        # Day 19: FTD - +2% gain on higher volume
        bars.append({"close": 104.04, "volume": 1500000, "date": "2026-01-20"})

        # Reverse to most-recent-first
        history = list(reversed(bars))

        result = detect_follow_through_day(history, 55.0)
        assert result["ftd_detected"] is True
        assert result["rally_day_count"] >= 4

    def test_rally_reset_below_swing_low(self):
        """Rally resets if price drops below swing low."""
        bars = []
        # Uptrend
        for i in range(10):
            bars.append({"close": 100 + i, "volume": 1000000, "date": f"d-{i}"})
        # Decline
        for i, p in enumerate([107, 105, 103, 101, 100]):
            bars.append({"close": p, "volume": 1100000, "date": f"d-{10 + i}"})
        # Swing low
        bars.append({"close": 99, "volume": 1200000, "date": "d-15"})
        # Brief rally
        bars.append({"close": 100, "volume": 1000000, "date": "d-16"})
        # Drop below swing low → reset
        bars.append({"close": 98, "volume": 1000000, "date": "d-17"})
        # New rally from lower base
        bars.append({"close": 99, "volume": 1000000, "date": "d-18"})
        bars.append({"close": 99.5, "volume": 1000000, "date": "d-19"})

        history = list(reversed(bars))
        result = detect_follow_through_day(history, 55.0)
        # FTD should NOT be detected (rally reset, new rally too short)
        assert result["ftd_detected"] is False
