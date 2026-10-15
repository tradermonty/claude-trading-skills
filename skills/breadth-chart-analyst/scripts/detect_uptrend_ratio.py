#!/usr/bin/env python3
"""
Uptrend Stock Ratio Chart Detector (OpenCV Version)

Automatically detects the current value, color (GREEN/RED), and trend direction
from US Stock Market Uptrend Ratio charts using OpenCV image processing.

This script analyzes chart images to:
1. Calibrate Y-axis using orange reference lines (0.40 upper, 0.10 lower)
2. Detect the rightmost filled area (GREEN = uptrend, RED = downtrend)
3. Find the top edge of the filled area to get the current percentage
4. Determine trend direction from recent data points

Requirements:
    pip install opencv-python numpy

Usage:
    python detect_uptrend_ratio.py <image_path>
    python detect_uptrend_ratio.py charts/2026-01-05/uptrend_ratio.jpeg
    python detect_uptrend_ratio.py charts/2026-01-05/uptrend_ratio.jpeg --debug

Output:
    {
        "current_value": 0.23,
        "current_color": "RED",
        "trend_direction": "FALLING",
        "confidence": "HIGH",
        "interpretation": "neutral_bearish"
    }
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None


class UptrendRatioDetector:
    """
    Detects current value and trend from US Stock Market Uptrend Ratio charts.

    The chart has:
    - GREEN filled area: Stocks in uptrend (above their moving average)
    - RED filled area: Stocks in downtrend (below their moving average)
    - Orange dashed lines: Reference at 0.40 (40%) upper and 0.10 (10%) lower
    """

    # Reference values for Y-axis calibration
    # NOTE: The actual chart uses 37% (not 40%) for the upper reference line
    UPPER_REFERENCE = 0.37  # Upper orange reference line (37%)
    LOWER_REFERENCE = 0.10  # Lower orange reference line (10%)

    # HSV color ranges for OpenCV (H: 0-179, S: 0-255, V: 0-255)
    # OpenCV uses H/2 (0-179 instead of 0-360)

    # Green area: Hue ~60-80 in OpenCV scale (bright green)
    # Saturation: 40+ to capture both bright and slightly faded greens
    GREEN_HSV_LOW = np.array([35, 40, 40])
    GREEN_HSV_HIGH = np.array([85, 255, 255])

    # Red area: Hue ~0-10 or 170-179 (red wraps around)
    # Chart uses coral/salmon red - moderate saturation to catch both bright and faded reds
    # Value (V) threshold at 60 to capture filled areas but not dark shadows
    RED_HSV_LOW1 = np.array([0, 70, 60])
    RED_HSV_HIGH1 = np.array([12, 255, 255])
    RED_HSV_LOW2 = np.array([168, 70, 60])
    RED_HSV_HIGH2 = np.array([179, 255, 255])

    # Orange reference lines: Hue ~10-25 (between red and yellow)
    # Lower saturation range for the beige/tan moving average line
    ORANGE_HSV_LOW = np.array([8, 50, 100])
    ORANGE_HSV_HIGH = np.array([25, 200, 255])

    # Gray/beige moving average line to EXCLUDE from detection
    # This line has low saturation and can interfere with color detection
    GRAY_HSV_LOW = np.array([0, 0, 100])
    GRAY_HSV_HIGH = np.array([30, 60, 220])

    def __init__(self, image_path: str):
        """
        Initialize the detector with an image path.

        Args:
            image_path: Path to the Uptrend Ratio chart image
        """
        self.image_path = image_path

        # Image data (loaded lazily)
        self.img_bgr = None
        self.img_hsv = None
        self.height = 0
        self.width = 0

        # Calibration results
        self.upper_ref_y: Optional[int] = None
        self.lower_ref_y: Optional[int] = None
        self.y_scale: Optional[float] = None
        self.y_offset: Optional[float] = None
        self.calibration_success = False
        self._ref_lines_detected: tuple[bool, bool] = (
            False,
            False,
        )  # Cache for reference line detection

        # Detection results
        self._current_value: Optional[float] = None
        self._current_color: Optional[str] = None
        self._trend_direction: Optional[str] = None
        self._confidence: str = "FAILED"

        # Debug info
        self.debug_info: dict[str, Any] = {}

    def _load_image(self) -> bool:
        """
        Load and validate the image.

        Returns:
            True if image loaded successfully

        Raises:
            FileNotFoundError: If image file doesn't exist
        """
        if not os.path.isfile(self.image_path):
            raise FileNotFoundError(f"Image file not found: {self.image_path}")

        if cv2 is None:
            self._confidence = "FAILED"
            self.debug_info["error"] = "OpenCV not installed"
            return False

        self.img_bgr = cv2.imread(self.image_path)

        if self.img_bgr is None:
            self._confidence = "FAILED"
            self.debug_info["error"] = f"Could not read image: {self.image_path}"
            return False

        self.height, self.width = self.img_bgr.shape[:2]
        self.img_hsv = cv2.cvtColor(self.img_bgr, cv2.COLOR_BGR2HSV)

        return True

    def _create_color_mask(
        self,
        hsv_low: np.ndarray,
        hsv_high: np.ndarray,
        hsv_low2: np.ndarray = None,
        hsv_high2: np.ndarray = None,
    ) -> np.ndarray:
        """
        Create a binary mask for pixels within the specified HSV range.

        Args:
            hsv_low: Lower HSV bounds
            hsv_high: Upper HSV bounds
            hsv_low2: Optional second lower bounds (for wraparound colors like red)
            hsv_high2: Optional second upper bounds

        Returns:
            Binary mask (255 where color matches, 0 elsewhere)
        """
        mask = cv2.inRange(self.img_hsv, hsv_low, hsv_high)

        if hsv_low2 is not None and hsv_high2 is not None:
            mask2 = cv2.inRange(self.img_hsv, hsv_low2, hsv_high2)
            mask = cv2.bitwise_or(mask, mask2)

        return mask

    def _find_horizontal_line_y(
        self, mask: np.ndarray, min_width_ratio: float = 0.15, y_range: tuple[int, int] = None
    ) -> Optional[int]:
        """
        Find the Y coordinate of a horizontal line in the mask.

        Args:
            mask: Binary mask of the target color
            min_width_ratio: Minimum ratio of image width the line should span
            y_range: Optional (y_min, y_max) to restrict search area

        Returns:
            Y coordinate of the detected line, or None
        """
        min_width = int(self.width * min_width_ratio)

        # Restrict to y_range if specified
        if y_range:
            search_mask = np.zeros_like(mask)
            search_mask[y_range[0] : y_range[1], :] = mask[y_range[0] : y_range[1], :]
            mask = search_mask

        # Calculate horizontal projection (sum of white pixels per row)
        h_projection = np.sum(mask > 0, axis=1)

        # Find rows with significant horizontal extent
        candidate_rows = np.where(h_projection >= min_width)[0]

        if len(candidate_rows) == 0:
            return None

        # Group consecutive rows and find the strongest group
        groups = []
        current_group = [candidate_rows[0]]

        for i in range(1, len(candidate_rows)):
            if candidate_rows[i] - candidate_rows[i - 1] <= 5:  # Allow 5px gaps
                current_group.append(candidate_rows[i])
            else:
                groups.append(current_group)
                current_group = [candidate_rows[i]]
        groups.append(current_group)

        # Find the group with the maximum total projection value
        best_group = max(groups, key=lambda g: sum(h_projection[y] for y in g))

        # Return the center of the best group
        return int(np.mean(best_group))

    def _detect_reference_lines(self) -> tuple[bool, bool]:
        """
        Detect the orange reference lines (40% and 10%) for Y-axis calibration.

        Returns:
            Tuple of (upper_detected, lower_detected)
        """
        orange_mask = self._create_color_mask(self.ORANGE_HSV_LOW, self.ORANGE_HSV_HIGH)

        if self.debug_info.get("save_masks"):
            self.debug_info["orange_mask"] = orange_mask

        # Find both reference lines
        # Upper line (40%) should be in upper half of image
        # Lower line (10%) should be in lower half of image
        mid_y = self.height // 2

        upper_y = self._find_horizontal_line_y(orange_mask, y_range=(0, mid_y))
        lower_y = self._find_horizontal_line_y(orange_mask, y_range=(mid_y, self.height))

        # Fallback: find top two lines if split search fails
        if upper_y is None or lower_y is None:
            # Try full search
            h_projection = np.sum(orange_mask > 0, axis=1)
            min_width = int(self.width * 0.12)
            candidate_rows = np.where(h_projection >= min_width)[0]

            if len(candidate_rows) > 0:
                # Group into clusters
                groups = []
                current_group = [candidate_rows[0]]

                for i in range(1, len(candidate_rows)):
                    if candidate_rows[i] - candidate_rows[i - 1] <= 10:
                        current_group.append(candidate_rows[i])
                    else:
                        groups.append(current_group)
                        current_group = [candidate_rows[i]]
                groups.append(current_group)

                # Sort groups by y position and take top 2
                group_centers = sorted([int(np.mean(g)) for g in groups if len(g) > 2])

                if len(group_centers) >= 2:
                    upper_y = group_centers[0]
                    lower_y = group_centers[-1]
                elif len(group_centers) == 1:
                    # Only one line found - determine which one
                    y = group_centers[0]
                    if y < mid_y:
                        upper_y = y
                    else:
                        lower_y = y

        self.upper_ref_y = upper_y
        self.lower_ref_y = lower_y

        return (upper_y is not None, lower_y is not None)

    def _calibrate_y_axis(self) -> bool:
        """
        Calibrate Y-axis using detected reference lines.

        The Y-axis is inverted in images (0 at top), so:
        - Upper line (0.40) should be at lower Y pixel value (higher in image)
        - Lower line (0.10) should be at higher Y pixel value (lower in image)

        Returns:
            True if calibration succeeded
        """
        upper_detected, lower_detected = self._detect_reference_lines()
        self._ref_lines_detected = (upper_detected, lower_detected)  # Cache result

        # Fallback estimation if reference lines not detected
        if not upper_detected or not lower_detected:
            # Estimate based on typical chart layout
            chart_top = int(self.height * 0.12)
            chart_bottom = int(self.height * 0.85)
            chart_range = chart_bottom - chart_top

            if not upper_detected:
                # 40% line should be ~20% from top of chart area (since range is 0-50%)
                self.upper_ref_y = chart_top + int(chart_range * 0.20)

            if not lower_detected:
                # 10% line should be ~80% from top of chart area
                self.lower_ref_y = chart_top + int(chart_range * 0.80)

        # Validate: upper should have lower Y than lower (images are Y-inverted)
        if self.upper_ref_y is not None and self.lower_ref_y is not None:
            if self.upper_ref_y > self.lower_ref_y:
                # Swap if reversed
                self.upper_ref_y, self.lower_ref_y = self.lower_ref_y, self.upper_ref_y

        # Calculate linear transformation: value = scale * pixel_y + offset
        if self.upper_ref_y is None or self.lower_ref_y is None:
            self.calibration_success = False
            return False

        pixel_diff = self.lower_ref_y - self.upper_ref_y
        value_diff = self.LOWER_REFERENCE - self.UPPER_REFERENCE  # 0.10 - 0.40 = -0.30

        if pixel_diff == 0:
            self.calibration_success = False
            return False

        self.y_scale = value_diff / pixel_diff
        self.y_offset = self.UPPER_REFERENCE - (self.y_scale * self.upper_ref_y)

        self.calibration_success = True
        return True

    def _pixel_to_value(self, pixel_y: int) -> float:
        """Convert pixel Y coordinate to percentage value (0-1)."""
        if self.y_scale is None or self.y_offset is None:
            return 0.0
        return self.y_scale * pixel_y + self.y_offset

    def _value_to_pixel(self, value: float) -> int:
        """Convert percentage value (0-1) to pixel Y coordinate."""
        if self.y_scale is None or self.y_offset is None:
            return 0
        return int((value - self.y_offset) / self.y_scale)

    def _detect_current_value_and_color(self) -> tuple[Optional[float], Optional[str]]:
        """
        Detect the current value and color at the right edge of the chart.

        Returns:
            Tuple of (value, color) where color is 'GREEN', 'RED', or 'UNKNOWN'
        """
        # Create masks for green and red areas
        green_mask = self._create_color_mask(self.GREEN_HSV_LOW, self.GREEN_HSV_HIGH)
        red_mask = self._create_color_mask(
            self.RED_HSV_LOW1, self.RED_HSV_HIGH1, self.RED_HSV_LOW2, self.RED_HSV_HIGH2
        )

        # Create gray exclusion mask (moving average line)
        gray_mask = self._create_color_mask(self.GRAY_HSV_LOW, self.GRAY_HSV_HIGH)

        # Remove gray areas from green and red masks to avoid detecting the MA line
        green_mask = cv2.bitwise_and(green_mask, cv2.bitwise_not(gray_mask))
        red_mask = cv2.bitwise_and(red_mask, cv2.bitwise_not(gray_mask))

        if self.debug_info.get("save_masks"):
            self.debug_info["green_mask"] = green_mask
            self.debug_info["red_mask"] = red_mask
            self.debug_info["gray_mask"] = gray_mask

        # Strategy: Find the EXACT rightmost column with data and analyze ONLY that column
        # The chart is filled from bottom, so we need to find where colored pixels END (top edge)

        # Find the rightmost column that has colored pixels
        combined_mask = cv2.bitwise_or(green_mask, red_mask)

        # FIX (Issue #5): Collect ALL colored columns, then select the TRUE rightmost
        # Previous bug: Early break selected FIRST column with >10 pixels, not the actual rightmost
        # This caused GREEN (4-8px) to be skipped and RED (29px) in an earlier column to be selected
        # FIX (Issue #5b): Lower threshold from 10 to 3 pixels to detect thin lines
        # Real case: 6px GREEN (true rightmost) was excluded, 29px RED (older data) was selected
        colored_cols = []
        for col in range(self.width - 1, max(0, self.width - 150), -1):
            col_pixels = np.sum(combined_mask[:, col] > 0)
            if col_pixels >= 3:  # At least 3 pixels of colored data (lowered from 10)
                colored_cols.append(col)

        # Select the absolute rightmost column (maximum index)
        if colored_cols:
            rightmost_col = max(colored_cols)
            self.debug_info["colored_cols_found"] = len(colored_cols)
            self.debug_info["colored_cols_range"] = (min(colored_cols), max(colored_cols))
        else:
            # Fallback: use last 5% of width
            rightmost_col = int(self.width * 0.95)
            self.debug_info["colored_cols_found"] = 0

        self.debug_info["rightmost_col"] = rightmost_col

        # Analyze ONLY the rightmost column (not a strip!) to get the current value
        # Using a strip would include older data points from columns to the left
        col_green = green_mask[:, rightmost_col]
        col_red = red_mask[:, rightmost_col]

        # Count pixels in just this column
        green_col_count = np.sum(col_green > 0)
        red_col_count = np.sum(col_red > 0)

        self.debug_info["green_pixel_count_right"] = green_col_count
        self.debug_info["red_pixel_count_right"] = red_col_count

        # Determine color at the rightmost point
        if red_col_count > green_col_count:
            dominant_color = "RED"
            col_mask = col_red
        elif green_col_count > red_col_count:
            dominant_color = "GREEN"
            col_mask = col_green
        elif red_col_count > 0:
            dominant_color = "RED"
            col_mask = col_red
        elif green_col_count > 0:
            dominant_color = "GREEN"
            col_mask = col_green
        else:
            return None, "UNKNOWN"

        # Find the top edge (minimum Y value where there are colored pixels)
        colored_rows = np.where(col_mask > 0)[0]

        if len(colored_rows) == 0:
            return None, dominant_color

        # The top edge (minimum Y) represents the current value
        # This is where the filled area ends (chart fills from bottom)
        top_edge_y = colored_rows.min()
        bottom_edge_y = colored_rows.max()

        self.debug_info["top_edge_y"] = top_edge_y
        self.debug_info["bottom_edge_y"] = bottom_edge_y

        # Convert pixel position to value
        value = self._pixel_to_value(top_edge_y)

        # Clamp to reasonable range (0-0.55 for Uptrend Ratio)
        value = max(0.0, min(0.55, value))

        self.debug_info["detected_value"] = value

        return round(value, 3), dominant_color

    def _detect_trend_direction(self) -> str:
        """
        Detect the trend direction based on recent values.

        Analyzes multiple points along the right portion of the chart
        to determine if the value is rising, falling, or flat.

        Returns:
            'RISING', 'FALLING', 'FLAT', or 'UNKNOWN'
        """
        # Create combined color mask with gray exclusion (Issue #4 fix)
        green_mask = self._create_color_mask(self.GREEN_HSV_LOW, self.GREEN_HSV_HIGH)
        red_mask = self._create_color_mask(
            self.RED_HSV_LOW1, self.RED_HSV_HIGH1, self.RED_HSV_LOW2, self.RED_HSV_HIGH2
        )

        # Exclude gray MA line to prevent false detection
        gray_mask = self._create_color_mask(self.GRAY_HSV_LOW, self.GRAY_HSV_HIGH)
        green_mask = cv2.bitwise_and(green_mask, cv2.bitwise_not(gray_mask))
        red_mask = cv2.bitwise_and(red_mask, cv2.bitwise_not(gray_mask))

        combined_mask = cv2.bitwise_or(green_mask, red_mask)

        # Sample points from right 30% of image
        sample_start = int(self.width * 0.70)
        sample_end = int(self.width * 0.98)
        num_samples = 5

        sample_values = []
        sample_xs = np.linspace(sample_start, sample_end, num_samples, dtype=int)

        for x in sample_xs:
            # Get column slice (+/- 3 pixels for stability)
            col_start = max(0, x - 3)
            col_end = min(self.width, x + 4)
            col_slice = combined_mask[:, col_start:col_end]

            colored_rows = np.where(np.any(col_slice > 0, axis=1))[0]

            if len(colored_rows) > 0:
                top_y = colored_rows.min()
                value = self._pixel_to_value(top_y)
                sample_values.append(value)

        if len(sample_values) < 3:
            return "UNKNOWN"

        self.debug_info["trend_samples"] = sample_values

        # Calculate trend: compare first half vs second half averages
        mid = len(sample_values) // 2
        early_avg = np.mean(sample_values[:mid])
        late_avg = np.mean(sample_values[mid:])

        diff = late_avg - early_avg

        # Determine direction based on difference
        # Use 2% threshold for significance
        if diff > 0.02:
            return "RISING"
        elif diff < -0.02:
            return "FALLING"
        else:
            return "FLAT"

    def _assess_confidence(self) -> str:
        """
        Assess confidence level of the detection.

        Returns:
            'HIGH', 'MEDIUM', 'LOW', or 'FAILED'
        """
        if self._current_value is None:
            return "FAILED"

        confidence_score = 0

        # Check calibration quality
        if self.calibration_success:
            confidence_score += 2

            # Extra point if both reference lines were detected (not estimated)
            # Use cached result to avoid re-computation and side effects
            upper_detected, lower_detected = self._ref_lines_detected
            if upper_detected and lower_detected:
                confidence_score += 1

        # Check if value is in reasonable range
        if 0.05 <= self._current_value <= 0.50:
            confidence_score += 1

        # Check pixel count
        green_count = self.debug_info.get("green_pixel_count_right", 0)
        red_count = self.debug_info.get("red_pixel_count_right", 0)
        total_count = green_count + red_count

        if total_count > 1000:
            confidence_score += 2
        elif total_count > 200:
            confidence_score += 1

        # Check color clarity
        if green_count > 0 and red_count > 0:
            ratio = max(green_count, red_count) / min(green_count, red_count)
            if ratio > 5:  # Clear color dominance
                confidence_score += 1

        # Map score to confidence level
        if confidence_score >= 5:
            return "HIGH"
        elif confidence_score >= 3:
            return "MEDIUM"
        elif confidence_score >= 1:
            return "LOW"
        else:
            return "FAILED"

    def _interpret_value(self, value: float) -> str:
        """
        Interpret the Uptrend Ratio value.

        Args:
            value: The detected value (0.0-1.0)

        Returns:
            Interpretation string
        """
        if value >= 0.40:
            return "overbought"
        elif value >= 0.25:
            return "neutral_bullish"
        elif value >= 0.15:
            return "neutral_bearish"
        else:
            return "oversold"

    def detect(self, debug: bool = False, debug_output_dir: str = None) -> dict[str, Any]:
        """
        Perform full detection on the Uptrend Ratio chart.

        Args:
            debug: If True, save debug images
            debug_output_dir: Directory for debug output (defaults to same as input image)

        Returns:
            Dictionary with detection results
        """
        self.debug_info["save_masks"] = debug

        # Load image
        try:
            if not self._load_image():
                return self._build_result()
        except FileNotFoundError as e:
            raise e

        # Calibrate Y-axis
        self._calibrate_y_axis()

        # Only proceed with detection if calibration succeeded
        # This prevents false positives when calibration fails (Issue #2 fix)
        if self.calibration_success:
            # Detect current value and color
            self._current_value, self._current_color = self._detect_current_value_and_color()

            # Detect trend direction
            self._trend_direction = self._detect_trend_direction()

        # Assess confidence (handles calibration failure internally)
        self._confidence = self._assess_confidence()

        # Save debug images if requested
        if debug:
            self._save_debug_images(debug_output_dir)

        return self._build_result()

    def _build_result(self) -> dict[str, Any]:
        """Build the result dictionary."""
        # Use 'is not None' check to properly handle 0.0 as a valid value (Issue #3 fix)
        result = {
            "current_value": self._current_value,
            "current_value_percent": f"{self._current_value * 100:.1f}%"
            if self._current_value is not None
            else None,
            "current_color": self._current_color or "UNKNOWN",
            "trend_direction": self._trend_direction or "UNKNOWN",
            "confidence": self._confidence,
            "interpretation": self._interpret_value(self._current_value)
            if self._current_value is not None
            else None,
            "calibration": {
                "upper_ref_y": self.upper_ref_y,
                "lower_ref_y": self.lower_ref_y,
                "y_scale": self.y_scale,
                "calibration_success": self.calibration_success,
            },
            "image": {"path": self.image_path, "width": self.width, "height": self.height},
            "debug_info": self.debug_info,  # Include debug info for testing and troubleshooting
        }

        return result

    def _save_debug_images(self, output_dir: str = None):
        """Save debug visualization images."""
        if output_dir is None:
            output_dir = os.path.dirname(self.image_path) or "."

        base_name = Path(self.image_path).stem

        # Create annotated image
        debug_img = self.img_bgr.copy()

        # Draw reference lines
        if self.upper_ref_y:
            cv2.line(
                debug_img, (0, self.upper_ref_y), (self.width, self.upper_ref_y), (0, 165, 255), 2
            )  # Orange in BGR
            cv2.putText(
                debug_img,
                f"{self.UPPER_REFERENCE:.0%} ref (y={self.upper_ref_y})",
                (10, self.upper_ref_y - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (0, 165, 255),
                1,
            )

        if self.lower_ref_y:
            cv2.line(
                debug_img, (0, self.lower_ref_y), (self.width, self.lower_ref_y), (0, 165, 255), 2
            )  # Orange in BGR
            cv2.putText(
                debug_img,
                f"{self.LOWER_REFERENCE:.0%} ref (y={self.lower_ref_y})",
                (10, self.lower_ref_y + 15),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (0, 165, 255),
                1,
            )

        # Mark detected value
        if self._current_value is not None:
            value_y = self._value_to_pixel(self._current_value)
            color = (0, 255, 0) if self._current_color == "GREEN" else (0, 0, 255)
            cv2.circle(debug_img, (self.width - 100, value_y), 15, color, 3)
            cv2.putText(
                debug_img,
                f"{self._current_value * 100:.1f}% {self._current_color}",
                (self.width - 250, value_y - 20),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                color,
                2,
            )

        # Save debug image
        debug_path = os.path.join(output_dir, f"{base_name}_debug_detection.jpeg")
        cv2.imwrite(debug_path, debug_img)
        print(f"Debug image saved to: {debug_path}")

        # Save masks if available
        if "green_mask" in self.debug_info:
            mask_path = os.path.join(output_dir, f"{base_name}_debug_green_mask.png")
            cv2.imwrite(mask_path, self.debug_info["green_mask"])

        if "red_mask" in self.debug_info:
            mask_path = os.path.join(output_dir, f"{base_name}_debug_red_mask.png")
            cv2.imwrite(mask_path, self.debug_info["red_mask"])


def _json_default(obj: Any) -> Any:
    """Make numpy values in debug_info JSON-serializable (arrays become a shape marker)."""
    if isinstance(obj, np.generic):
        return obj.item()
    if isinstance(obj, np.ndarray):
        return f"<ndarray shape={list(obj.shape)}>"
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def format_result_for_human(result: dict[str, Any]) -> str:
    """Format the detection result for human-readable output."""
    lines = []
    lines.append("=" * 60)
    lines.append("Uptrend Ratio Detection Results (OpenCV)")
    lines.append("=" * 60)

    lines.append(f"\nImage: {result['image']['path']}")
    lines.append(f"Confidence: {result['confidence']}")

    lines.append("\n--- Detected Values ---")
    if result["current_value"] is not None:
        lines.append(
            f"Current Value: {result['current_value_percent']} ({result['interpretation']})"
        )
        lines.append(f"Current Color: {result['current_color']}")
        lines.append(f"Trend Direction: {result['trend_direction']}")
    else:
        lines.append("Current Value: NOT DETECTED")

    lines.append("\n--- Calibration ---")
    cal = result["calibration"]
    lines.append(
        f"Upper reference ({UptrendRatioDetector.UPPER_REFERENCE:.0%}) Y-pixel: {cal['upper_ref_y']}"
    )
    lines.append(
        f"Lower reference ({UptrendRatioDetector.LOWER_REFERENCE:.0%}) Y-pixel: {cal['lower_ref_y']}"
    )
    lines.append(f"Calibration successful: {cal['calibration_success']}")

    lines.append("=" * 60)

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Detect current value and trend from US Stock Market Uptrend Ratio charts.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python detect_uptrend_ratio.py charts/2026-01-05/uptrend_ratio.jpeg
  python detect_uptrend_ratio.py charts/2026-01-05/uptrend_ratio.jpeg --debug
  python detect_uptrend_ratio.py charts/2026-01-05/uptrend_ratio.jpeg --json
        """,
    )

    parser.add_argument("image_path", help="Path to the Uptrend Ratio chart image")
    parser.add_argument(
        "--debug", action="store_true", help="Save debug images showing detection process"
    )
    parser.add_argument("--json", action="store_true", help="Output results as JSON only")

    args = parser.parse_args()

    if not os.path.isfile(args.image_path):
        print(f"Error: File not found: {args.image_path}", file=sys.stderr)
        sys.exit(1)

    try:
        detector = UptrendRatioDetector(args.image_path)
        result = detector.detect(debug=args.debug)

        if args.json:
            print(json.dumps(result, indent=2, default=_json_default))
        else:
            print(format_result_for_human(result))

        # Exit with error code if detection failed
        if result["confidence"] == "FAILED":
            sys.exit(1)

    except FileNotFoundError as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        if args.debug:
            import traceback

            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
