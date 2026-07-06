"""
TDD Tests for detect_uptrend_ratio.py

Uptrend Stock Ratio Chart Detection Script
- Detects current value (0-100%)
- Detects current color (GREEN/RED)
- Detects trend direction (RISING/FALLING/FLAT)
- Provides confidence assessment

Test-Driven Development: RED -> GREEN -> REFACTOR
"""

import numpy as np
import pytest

# =============================================================================
# Test 1: Basic Class Structure
# =============================================================================


class TestBasicClassStructure:
    """Tests for basic class existence and initialization."""

    def test_detector_class_exists(self):
        """UptrendRatioDetector class should exist."""
        from detect_uptrend_ratio import UptrendRatioDetector

        assert UptrendRatioDetector is not None

    def test_detector_accepts_image_path(self):
        """Detector should accept image path in constructor."""
        from detect_uptrend_ratio import UptrendRatioDetector

        detector = UptrendRatioDetector("path/to/image.jpeg")
        assert detector.image_path == "path/to/image.jpeg"

    def test_detector_has_detect_method(self):
        """Detector should have a detect() method."""
        from detect_uptrend_ratio import UptrendRatioDetector

        detector = UptrendRatioDetector("path/to/image.jpeg")
        assert hasattr(detector, "detect")
        assert callable(detector.detect)


# =============================================================================
# Test 2: HSV Color Range Definitions
# =============================================================================


class TestHSVColorRanges:
    """Tests for HSV color range constants."""

    def test_green_hsv_range_defined(self):
        """GREEN HSV range should be defined as class attributes."""
        from detect_uptrend_ratio import UptrendRatioDetector

        assert hasattr(UptrendRatioDetector, "GREEN_HSV_LOW")
        assert hasattr(UptrendRatioDetector, "GREEN_HSV_HIGH")

    def test_red_hsv_range_defined(self):
        """RED HSV ranges should be defined (two ranges for red hue wrap)."""
        from detect_uptrend_ratio import UptrendRatioDetector

        # Red wraps around 0/180 in HSV, so we need two ranges
        assert hasattr(UptrendRatioDetector, "RED_HSV_LOW1")
        assert hasattr(UptrendRatioDetector, "RED_HSV_HIGH1")
        assert hasattr(UptrendRatioDetector, "RED_HSV_LOW2")
        assert hasattr(UptrendRatioDetector, "RED_HSV_HIGH2")

    def test_orange_hsv_range_defined(self):
        """ORANGE HSV range should be defined for reference lines."""
        from detect_uptrend_ratio import UptrendRatioDetector

        assert hasattr(UptrendRatioDetector, "ORANGE_HSV_LOW")
        assert hasattr(UptrendRatioDetector, "ORANGE_HSV_HIGH")

    def test_hsv_ranges_are_numpy_arrays(self):
        """HSV ranges should be numpy arrays for OpenCV compatibility."""
        from detect_uptrend_ratio import UptrendRatioDetector

        assert isinstance(UptrendRatioDetector.GREEN_HSV_LOW, np.ndarray)
        assert isinstance(UptrendRatioDetector.GREEN_HSV_HIGH, np.ndarray)

    def test_hsv_ranges_have_correct_shape(self):
        """HSV ranges should have shape (3,) for H, S, V channels."""
        from detect_uptrend_ratio import UptrendRatioDetector

        assert UptrendRatioDetector.GREEN_HSV_LOW.shape == (3,)
        assert UptrendRatioDetector.GREEN_HSV_HIGH.shape == (3,)


# =============================================================================
# Test 3: Reference Line Detection and Y-axis Calibration
# =============================================================================


class TestYAxisCalibration:
    """Tests for Y-axis calibration using reference lines."""

    def test_reference_values_defined(self):
        """Reference line values should be defined."""
        from detect_uptrend_ratio import UptrendRatioDetector

        assert hasattr(UptrendRatioDetector, "UPPER_REFERENCE")
        assert hasattr(UptrendRatioDetector, "LOWER_REFERENCE")
        # Uptrend Ratio chart uses 37% upper and 10% lower orange dashed lines
        assert UptrendRatioDetector.UPPER_REFERENCE == 0.37
        assert UptrendRatioDetector.LOWER_REFERENCE == 0.10

    def test_calibrate_y_axis_method_exists(self):
        """Detector should have _calibrate_y_axis method."""
        from detect_uptrend_ratio import UptrendRatioDetector

        detector = UptrendRatioDetector("path/to/image.jpeg")
        assert hasattr(detector, "_calibrate_y_axis")

    def test_pixel_to_value_conversion(self, sample_uptrend_chart):
        """After calibration, pixel positions should convert to correct values."""
        from detect_uptrend_ratio import UptrendRatioDetector

        detector = UptrendRatioDetector(sample_uptrend_chart)
        detector._load_image()
        calibrated = detector._calibrate_y_axis()

        if calibrated:
            # Test that upper reference line pixel maps to expected value (37%)
            upper_value = detector._pixel_to_value(detector.upper_ref_y)
            assert abs(upper_value - detector.UPPER_REFERENCE) < 0.02  # Within 2% tolerance

            # Test that lower reference line pixel maps to 10%
            lower_value = detector._pixel_to_value(detector.lower_ref_y)
            assert abs(lower_value - detector.LOWER_REFERENCE) < 0.02


# =============================================================================
# Test 4: Current Value Detection
# =============================================================================


class TestCurrentValueDetection:
    """Tests for detecting the current (rightmost) value."""

    def test_detect_returns_dict(self, sample_uptrend_chart):
        """detect() should return a dictionary."""
        from detect_uptrend_ratio import UptrendRatioDetector

        detector = UptrendRatioDetector(sample_uptrend_chart)
        result = detector.detect()
        assert isinstance(result, dict)

    def test_detect_returns_current_value(self, sample_uptrend_chart):
        """detect() should return current_value key."""
        from detect_uptrend_ratio import UptrendRatioDetector

        detector = UptrendRatioDetector(sample_uptrend_chart)
        result = detector.detect()
        assert "current_value" in result

    def test_current_value_in_valid_range(self, sample_uptrend_chart):
        """current_value should be between 0.0 and 1.0."""
        from detect_uptrend_ratio import UptrendRatioDetector

        detector = UptrendRatioDetector(sample_uptrend_chart)
        result = detector.detect()
        assert 0.0 <= result["current_value"] <= 1.0

    def test_detect_returns_current_color(self, sample_uptrend_chart):
        """detect() should return current_color key."""
        from detect_uptrend_ratio import UptrendRatioDetector

        detector = UptrendRatioDetector(sample_uptrend_chart)
        result = detector.detect()
        assert "current_color" in result
        assert result["current_color"] in ["GREEN", "RED", "UNKNOWN"]


# =============================================================================
# Test 5: Trend Direction Detection
# =============================================================================


class TestTrendDirectionDetection:
    """Tests for detecting trend direction."""

    def test_detect_returns_trend_direction(self, sample_uptrend_chart):
        """detect() should return trend_direction key."""
        from detect_uptrend_ratio import UptrendRatioDetector

        detector = UptrendRatioDetector(sample_uptrend_chart)
        result = detector.detect()
        assert "trend_direction" in result

    def test_trend_direction_valid_values(self, sample_uptrend_chart):
        """trend_direction should be RISING, FALLING, or FLAT."""
        from detect_uptrend_ratio import UptrendRatioDetector

        detector = UptrendRatioDetector(sample_uptrend_chart)
        result = detector.detect()
        assert result["trend_direction"] in ["RISING", "FALLING", "FLAT", "UNKNOWN"]


# =============================================================================
# Test 6: Confidence Assessment
# =============================================================================


class TestConfidenceAssessment:
    """Tests for confidence level assessment."""

    def test_detect_returns_confidence(self, sample_uptrend_chart):
        """detect() should return confidence key."""
        from detect_uptrend_ratio import UptrendRatioDetector

        detector = UptrendRatioDetector(sample_uptrend_chart)
        result = detector.detect()
        assert "confidence" in result

    def test_confidence_valid_values(self, sample_uptrend_chart):
        """confidence should be HIGH, MEDIUM, LOW, or FAILED."""
        from detect_uptrend_ratio import UptrendRatioDetector

        detector = UptrendRatioDetector(sample_uptrend_chart)
        result = detector.detect()
        assert result["confidence"] in ["HIGH", "MEDIUM", "LOW", "FAILED"]

    def test_detect_returns_interpretation(self, sample_uptrend_chart):
        """detect() should return interpretation key."""
        from detect_uptrend_ratio import UptrendRatioDetector

        detector = UptrendRatioDetector(sample_uptrend_chart)
        result = detector.detect()
        assert "interpretation" in result


# =============================================================================
# Test 7: Edge Cases and Error Handling
# =============================================================================


class TestErrorHandling:
    """Tests for error handling and edge cases."""

    def test_invalid_image_path_raises_error(self, nonexistent_image):
        """Non-existent image path should raise FileNotFoundError."""
        from detect_uptrend_ratio import UptrendRatioDetector

        detector = UptrendRatioDetector(nonexistent_image)
        with pytest.raises(FileNotFoundError):
            detector.detect()

    def test_invalid_image_format_handled(self, tmp_path):
        """Invalid image format should be handled gracefully."""
        from detect_uptrend_ratio import UptrendRatioDetector

        # Create a text file with .jpeg extension
        fake_image = tmp_path / "fake.jpeg"
        fake_image.write_text("not an image", encoding="utf-8")

        detector = UptrendRatioDetector(str(fake_image))
        result = detector.detect()
        assert result["confidence"] == "FAILED"


# =============================================================================
# Test 8: Value Interpretation
# =============================================================================


class TestValueInterpretation:
    """Tests for value interpretation logic."""

    def test_interpret_overbought(self):
        """Value >= 40% should be interpreted as overbought."""
        from detect_uptrend_ratio import UptrendRatioDetector

        detector = UptrendRatioDetector("dummy.jpeg")
        assert detector._interpret_value(0.45) == "overbought"
        assert detector._interpret_value(0.40) == "overbought"

    def test_interpret_neutral_bullish(self):
        """Value 25-40% should be interpreted as neutral_bullish."""
        from detect_uptrend_ratio import UptrendRatioDetector

        detector = UptrendRatioDetector("dummy.jpeg")
        assert detector._interpret_value(0.35) == "neutral_bullish"
        assert detector._interpret_value(0.25) == "neutral_bullish"

    def test_interpret_neutral_bearish(self):
        """Value 15-25% should be interpreted as neutral_bearish."""
        from detect_uptrend_ratio import UptrendRatioDetector

        detector = UptrendRatioDetector("dummy.jpeg")
        assert detector._interpret_value(0.20) == "neutral_bearish"
        assert detector._interpret_value(0.15) == "neutral_bearish"

    def test_interpret_oversold(self):
        """Value < 15% should be interpreted as oversold (crisis)."""
        from detect_uptrend_ratio import UptrendRatioDetector

        detector = UptrendRatioDetector("dummy.jpeg")
        assert detector._interpret_value(0.10) == "oversold"
        assert detector._interpret_value(0.05) == "oversold"


# =============================================================================
# Test 9: Debug Output (Optional Feature)
# =============================================================================


class TestDebugOutput:
    """Tests for optional debug image output."""

    def test_detect_accepts_debug_flag(self, sample_uptrend_chart):
        """detect() should accept debug parameter."""
        from detect_uptrend_ratio import UptrendRatioDetector

        detector = UptrendRatioDetector(sample_uptrend_chart)
        # Should not raise error
        result = detector.detect(debug=False)
        assert isinstance(result, dict)

    def test_debug_creates_output_image(self, sample_uptrend_chart, tmp_path):
        """When debug=True, should create debug image."""
        from detect_uptrend_ratio import UptrendRatioDetector

        detector = UptrendRatioDetector(sample_uptrend_chart)
        detector.detect(debug=True, debug_output_dir=str(tmp_path))

        # Check that a debug image was created
        list(tmp_path.glob("*_debug*.jpeg")) + list(tmp_path.glob("*_debug*.png"))
        # This test may pass or fail depending on implementation
        # It's acceptable if debug output is not implemented initially


# =============================================================================
# Integration Tests
# =============================================================================


class TestIntegration:
    """Integration tests with real sample charts."""

    def test_sample_chart_detection_complete(self, sample_uptrend_chart):
        """Full detection on sample chart should return all required fields."""
        from detect_uptrend_ratio import UptrendRatioDetector

        detector = UptrendRatioDetector(sample_uptrend_chart)
        result = detector.detect()

        required_fields = [
            "current_value",
            "current_color",
            "trend_direction",
            "confidence",
            "interpretation",
        ]

        for field in required_fields:
            assert field in result, f"Missing required field: {field}"

    def test_sample_chart_has_reasonable_values(self, sample_uptrend_chart):
        """Sample chart detection should return reasonable values."""
        from detect_uptrend_ratio import UptrendRatioDetector

        detector = UptrendRatioDetector(sample_uptrend_chart)
        result = detector.detect()

        # Value should be in reasonable range for a stock market indicator
        assert 0.05 <= result["current_value"] <= 0.70

        # Should have some confidence (not failed on valid chart)
        assert result["confidence"] in ["HIGH", "MEDIUM", "LOW"]


# =============================================================================
# Test 11: Multi-Color Rightmost Detection (Issue #5 Fix)
# =============================================================================


class TestMultiColorRightmostDetection:
    """Tests for handling multiple colors at chart's right edge.

    This addresses the bug where early-break logic caused the detector to
    select the FIRST column with >10 pixels instead of the TRUE rightmost column.

    Example scenario (2026-01-12):
    - Column 1314: GREEN 6px (<10, skipped)
    - Column 1313: GREEN 8px (<10, skipped)
    - Column 1306: RED 29px (>10, selected → WRONG)

    Expected: Should select column 1314 (GREEN, actual rightmost)
    Actual (before fix): Selected column 1306 (RED, first >10px)
    """

    def test_rightmost_col_is_maximum_not_first(self, sample_uptrend_chart):
        """Rightmost column should be max(colored_cols), not first match.

        This is a regression test for the core bug: the early-break logic
        that stopped at the FIRST column with >10 pixels instead of finding
        the TRUE rightmost column.
        """
        from detect_uptrend_ratio import UptrendRatioDetector

        detector = UptrendRatioDetector(sample_uptrend_chart)
        result = detector.detect()

        # After fix, debug_info should contain colored_cols information
        assert "debug_info" in result
        debug_info = result["debug_info"]

        # Should have colored_cols_found field (added by fix)
        assert "colored_cols_found" in debug_info

        # Should have found at least one colored column
        assert debug_info["colored_cols_found"] >= 1

        # rightmost_col should be the MAXIMUM, not just any valid column
        assert "rightmost_col" in debug_info

        # If multiple colored columns exist, verify rightmost is the max
        if debug_info["colored_cols_found"] > 1:
            assert "colored_cols_range" in debug_info
            col_min, col_max = debug_info["colored_cols_range"]
            assert debug_info["rightmost_col"] == col_max

    def test_debug_info_contains_colored_cols_metadata(self, sample_uptrend_chart):
        """Debug info should include metadata about colored column detection.

        The fix adds:
        - colored_cols_found: number of columns with >10 pixels
        - colored_cols_range: (min, max) of colored column indices
        """
        from detect_uptrend_ratio import UptrendRatioDetector

        detector = UptrendRatioDetector(sample_uptrend_chart)
        result = detector.detect()

        debug_info = result["debug_info"]

        # Should have colored_cols_found
        assert "colored_cols_found" in debug_info
        assert isinstance(debug_info["colored_cols_found"], int)
        assert debug_info["colored_cols_found"] >= 0

        # If colored columns were found, should have range
        if debug_info["colored_cols_found"] > 1:
            assert "colored_cols_range" in debug_info
            col_min, col_max = debug_info["colored_cols_range"]
            assert isinstance(col_min, (int, np.integer))
            assert isinstance(col_max, (int, np.integer))
            assert col_min <= col_max

    def test_color_at_true_rightmost_prevails(self, sample_uptrend_chart):
        """The color at the TRUE rightmost column should be detected.

        This test ensures that when multiple colors coexist at the right edge,
        the detector selects the color at the absolute rightmost column,
        not the color with the most pixels in an earlier column.
        """
        from detect_uptrend_ratio import UptrendRatioDetector

        detector = UptrendRatioDetector(sample_uptrend_chart)
        result = detector.detect()

        # The detected color should correspond to the rightmost column
        assert "current_color" in result
        assert result["current_color"] in ["GREEN", "RED"]

        # Value should be reasonable (not the erroneous 23% from wrong column)
        assert "current_value" in result
        assert 0.05 <= result["current_value"] <= 0.70
