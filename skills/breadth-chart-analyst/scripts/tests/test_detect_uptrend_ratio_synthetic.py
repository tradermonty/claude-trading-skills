"""Behavior tests for detect_uptrend_ratio.py using synthetic charts built at runtime."""

import json
import sys

import cv2
import detect_uptrend_ratio as dur
import numpy as np
import pytest
from detect_uptrend_ratio import UptrendRatioDetector, format_result_for_human

W, H = 400, 300
UPPER_Y, LOWER_Y = 60, 240  # reference lines for 37% and 10%
BOTTOM = 280


def _bgr_from_hsv(h, s, v):
    px = np.uint8([[[h, s, v]]])
    return tuple(int(c) for c in cv2.cvtColor(px, cv2.COLOR_HSV2BGR)[0, 0])


ORANGE = _bgr_from_hsv(15, 150, 230)
GREEN = _bgr_from_hsv(60, 200, 200)
RED = _bgr_from_hsv(0, 180, 230)


def y_for(value, upper_y=UPPER_Y, lower_y=LOWER_Y):
    return round(upper_y + (0.37 - value) / 0.27 * (lower_y - upper_y))


def make_chart(
    path,
    value=lambda x: 0.25,
    color=lambda x: GREEN,
    right_end=W - 5,
    upper_y=UPPER_Y,
    lower_y=LOWER_Y,
    refs=(True, True),
):
    img = np.full((H, W, 3), 255, dtype=np.uint8)
    for x in range(0, right_end):
        top = max(0, y_for(value(x), upper_y, lower_y))
        img[top:BOTTOM, x] = color(x)
    if refs[0]:
        cv2.line(img, (0, upper_y), (W - 1, upper_y), ORANGE, 3)
    if refs[1]:
        cv2.line(img, (0, lower_y), (W - 1, lower_y), ORANGE, 3)
    cv2.imwrite(str(path), img)
    return str(path)


@pytest.fixture
def green_chart(tmp_path):
    return make_chart(tmp_path / "up.png", value=lambda x: 0.25)


class TestLoadImage:
    def test_missing_file_raises(self, tmp_path):
        d = UptrendRatioDetector(str(tmp_path / "nope.png"))
        with pytest.raises(FileNotFoundError, match="Image file not found"):
            d.detect()

    def test_unreadable_image_returns_failed(self, tmp_path):
        bad = tmp_path / "bad.png"
        bad.write_bytes(b"junk")
        result = UptrendRatioDetector(str(bad)).detect()
        assert result["confidence"] == "FAILED"
        assert result["current_value"] is None
        assert result["current_value_percent"] is None
        assert result["interpretation"] is None
        assert result["current_color"] == "UNKNOWN"
        assert "Could not read image" in result["debug_info"]["error"]

    def test_opencv_missing_returns_failed(self, green_chart, monkeypatch):
        monkeypatch.setattr(dur, "cv2", None)
        result = UptrendRatioDetector(green_chart).detect()
        assert result["confidence"] == "FAILED"
        assert result["debug_info"]["error"] == "OpenCV not installed"


class TestHelpers:
    def test_uncalibrated_conversions_return_zero(self):
        d = UptrendRatioDetector("x.png")
        assert d._pixel_to_value(100) == 0.0
        assert d._value_to_pixel(0.3) == 0

    def test_conversions_roundtrip_after_calibration(self, green_chart):
        d = UptrendRatioDetector(green_chart)
        assert d._load_image() is True
        assert d._calibrate_y_axis() is True
        assert d._pixel_to_value(d.upper_ref_y) == pytest.approx(0.37)
        assert d._pixel_to_value(d.lower_ref_y) == pytest.approx(0.10)
        assert d._value_to_pixel(0.25) == pytest.approx(y_for(0.25), abs=1)

    def test_find_horizontal_line_empty_and_grouping(self, green_chart):
        d = UptrendRatioDetector(green_chart)
        d._load_image()
        mask = np.zeros((H, W), dtype=np.uint8)
        assert d._find_horizontal_line_y(mask) is None
        mask[50, :] = 255
        mask[100:103, :] = 255
        assert d._find_horizontal_line_y(mask) == 101
        # y_range restricts the search to the first line
        assert d._find_horizontal_line_y(mask, y_range=(0, 80)) == 50

    @pytest.mark.parametrize(
        "value,expected",
        [
            (0.55, "overbought"),
            (0.40, "overbought"),
            (0.30, "neutral_bullish"),
            (0.25, "neutral_bullish"),
            (0.20, "neutral_bearish"),
            (0.15, "neutral_bearish"),
            (0.149, "oversold"),
            (0.0, "oversold"),
        ],
    )
    def test_interpret_value_boundaries(self, value, expected):
        assert UptrendRatioDetector("x.png")._interpret_value(value) == expected


class TestCalibrationFallbacks:
    def _calibrate(self, path):
        d = UptrendRatioDetector(path)
        d._load_image()
        ok = d._calibrate_y_axis()
        return d, ok

    def test_both_lines_detected(self, green_chart):
        d, ok = self._calibrate(green_chart)
        assert ok and d.calibration_success
        assert d._ref_lines_detected == (True, True)
        assert abs(d.upper_ref_y - UPPER_Y) <= 1
        assert abs(d.lower_ref_y - LOWER_Y) <= 1

    def test_no_lines_uses_estimated_positions(self, tmp_path):
        path = make_chart(tmp_path / "c.png", refs=(False, False))
        d, ok = self._calibrate(path)
        top, bottom = int(H * 0.12), int(H * 0.85)
        rng = bottom - top
        assert ok
        assert d._ref_lines_detected == (False, False)
        assert d.upper_ref_y == top + int(rng * 0.20)
        assert d.lower_ref_y == top + int(rng * 0.80)

    def test_only_upper_line_estimates_lower(self, tmp_path):
        path = make_chart(tmp_path / "c.png", refs=(True, False))
        d, ok = self._calibrate(path)
        top, bottom = int(H * 0.12), int(H * 0.85)
        assert ok
        assert d._ref_lines_detected == (True, False)
        assert abs(d.upper_ref_y - UPPER_Y) <= 1
        assert d.lower_ref_y == top + int((bottom - top) * 0.80)

    def test_only_lower_line_estimates_upper(self, tmp_path):
        path = make_chart(tmp_path / "c.png", refs=(False, True))
        d, ok = self._calibrate(path)
        top, bottom = int(H * 0.12), int(H * 0.85)
        assert ok
        assert d._ref_lines_detected == (False, True)
        assert abs(d.lower_ref_y - LOWER_Y) <= 1
        assert d.upper_ref_y == top + int((bottom - top) * 0.20)

    def test_two_lines_in_same_half_use_cluster_fallback(self, tmp_path):
        path = make_chart(tmp_path / "c.png", upper_y=40, lower_y=110)
        d, ok = self._calibrate(path)
        assert ok
        assert d._ref_lines_detected == (True, True)
        assert abs(d.upper_ref_y - 40) <= 1
        assert abs(d.lower_ref_y - 110) <= 1
        assert d.y_scale == pytest.approx(-0.27 / (d.lower_ref_y - d.upper_ref_y))

    def test_swapped_references_are_reordered(self, green_chart):
        d = UptrendRatioDetector(green_chart)
        d._load_image()

        def fake_detect():
            d.upper_ref_y, d.lower_ref_y = 200, 100
            return True, True

        d._detect_reference_lines = fake_detect
        assert d._calibrate_y_axis() is True
        assert (d.upper_ref_y, d.lower_ref_y) == (100, 200)
        assert d.y_scale < 0

    def test_zero_pixel_diff_fails(self, green_chart):
        d = UptrendRatioDetector(green_chart)
        d._load_image()

        def fake_detect():
            d.upper_ref_y = d.lower_ref_y = 120
            return True, True

        d._detect_reference_lines = fake_detect
        assert d._calibrate_y_axis() is False
        assert d.calibration_success is False
        assert d.y_scale is None

    def test_calibration_failure_skips_detection(self, green_chart, monkeypatch):
        d = UptrendRatioDetector(green_chart)
        monkeypatch.setattr(d, "_calibrate_y_axis", lambda: False)
        result = d.detect()
        assert result["current_value"] is None
        assert result["confidence"] == "FAILED"
        assert result["trend_direction"] == "UNKNOWN"
        assert result["calibration"]["calibration_success"] is False


class TestValueColorTrend:
    def test_green_flat(self, green_chart):
        result = UptrendRatioDetector(green_chart).detect()
        assert result["current_value"] == pytest.approx(0.25, abs=0.01)
        assert result["current_value_percent"].endswith("%")
        assert result["current_color"] == "GREEN"
        assert result["trend_direction"] == "FLAT"
        assert result["interpretation"] == "neutral_bullish"
        assert result["confidence"] in {"MEDIUM", "HIGH"}
        assert result["calibration"]["calibration_success"] is True
        assert result["image"] == {"path": green_chart, "width": W, "height": H}
        assert result["debug_info"]["rightmost_col"] == W - 6

    def test_red_falling(self, tmp_path):
        path = make_chart(
            tmp_path / "c.png",
            value=lambda x: 0.35 - 0.25 * x / W,
            color=lambda x: RED,
        )
        result = UptrendRatioDetector(path).detect()
        assert result["current_color"] == "RED"
        assert result["trend_direction"] == "FALLING"
        assert result["current_value"] == pytest.approx(0.35 - 0.25 * (W - 6) / W, abs=0.015)
        assert result["interpretation"] == "oversold"

    def test_green_rising(self, tmp_path):
        path = make_chart(tmp_path / "c.png", value=lambda x: 0.12 + 0.25 * x / W)
        result = UptrendRatioDetector(path).detect()
        assert result["trend_direction"] == "RISING"
        assert result["current_color"] == "GREEN"
        assert result["debug_info"]["trend_samples"][0] < result["debug_info"]["trend_samples"][-1]

    def test_rightmost_column_color_wins_over_older_data(self, tmp_path):
        # Older columns RED, last few columns GREEN: true rightmost must be GREEN.
        path = make_chart(tmp_path / "c.png", color=lambda x: GREEN if x >= W - 12 else RED)
        result = UptrendRatioDetector(path).detect()
        assert result["current_color"] == "GREEN"

    def test_red_dominates_when_more_red_pixels_in_column(self, tmp_path):
        path = make_chart(tmp_path / "c.png", right_end=0)
        img = cv2.imread(path)
        # last column: tall red (rows 100-200) over a short green (rows 200-215)
        img[100:200, W - 6] = RED
        img[200:215, W - 6] = GREEN
        cv2.imwrite(path, img)
        d = UptrendRatioDetector(path)
        d._load_image()
        d._calibrate_y_axis()
        value, color = d._detect_current_value_and_color()
        assert color == "RED"
        assert value == pytest.approx(d._pixel_to_value(100), abs=0.002)

    def test_green_dominates_when_more_green_pixels_in_column(self, tmp_path):
        path = make_chart(tmp_path / "c.png", right_end=0)
        img = cv2.imread(path)
        img[100:110, W - 6] = RED
        img[110:200, W - 6] = GREEN
        cv2.imwrite(path, img)
        d = UptrendRatioDetector(path)
        d._load_image()
        d._calibrate_y_axis()
        value, color = d._detect_current_value_and_color()
        assert color == "GREEN"
        # top edge comes from the green mask only
        assert value == pytest.approx(d._pixel_to_value(110), abs=0.002)

    def test_tie_prefers_red(self, tmp_path):
        path = make_chart(tmp_path / "c.png", right_end=0)
        img = cv2.imread(path)
        img[100:120, W - 6] = RED
        img[150:170, W - 6] = GREEN
        cv2.imwrite(path, img)
        d = UptrendRatioDetector(path)
        d._load_image()
        d._calibrate_y_axis()
        _, color = d._detect_current_value_and_color()
        assert color == "RED"

    def test_no_colored_pixels_gives_unknown(self, tmp_path):
        path = make_chart(tmp_path / "c.png", right_end=0)
        result = UptrendRatioDetector(path).detect()
        assert result["current_value"] is None
        assert result["current_color"] == "UNKNOWN"
        assert result["trend_direction"] == "UNKNOWN"
        assert result["confidence"] == "FAILED"
        assert result["debug_info"]["colored_cols_found"] == 0

    def test_value_clamped_to_upper_bound(self, tmp_path):
        path = make_chart(tmp_path / "c.png", value=lambda x: 0.60, upper_y=150, lower_y=270)
        result = UptrendRatioDetector(path).detect()
        assert result["current_value"] == 0.55
        assert result["interpretation"] == "overbought"

    def test_zero_value_is_reported_not_none(self, tmp_path):
        # Value far below the 10% line clamps to 0.0, which must stay a valid value.
        path = make_chart(tmp_path / "c.png", value=lambda x: -0.035, upper_y=60, lower_y=160)
        result = UptrendRatioDetector(path).detect()
        assert result["current_value"] == 0.0
        assert result["current_value_percent"] == "0.0%"
        assert result["interpretation"] == "oversold"


class TestConfidence:
    def _detector(self, value, calibrated=True, refs=(True, True), green=0, red=0):
        d = UptrendRatioDetector("x.png")
        d._current_value = value
        d.calibration_success = calibrated
        d._ref_lines_detected = refs
        d.debug_info["green_pixel_count_right"] = green
        d.debug_info["red_pixel_count_right"] = red
        return d

    def test_no_value_is_failed(self):
        assert self._detector(None)._assess_confidence() == "FAILED"

    def test_high_with_many_pixels(self):
        assert self._detector(0.25, green=1200)._assess_confidence() == "HIGH"

    def test_medium_with_few_pixels(self):
        # 2 (calibrated) + 1 (both refs) + 1 (range) = 4
        assert self._detector(0.25, green=50)._assess_confidence() == "MEDIUM"

    def test_mid_pixel_count_adds_one_point(self):
        # 4 + 1 (>200 pixels) = 5 -> HIGH
        assert self._detector(0.25, green=300)._assess_confidence() == "HIGH"

    def test_color_dominance_bonus(self):
        # 2 + 0 (no refs) + 1 (range) + 0 pixels + 1 dominance (ratio > 5) = 4
        d = self._detector(0.25, refs=(False, False), green=60, red=10)
        assert d._assess_confidence() == "MEDIUM"
        # ratio exactly 2 gives no bonus: score 3 -> still MEDIUM; with out-of-range -> LOW
        d = self._detector(0.0, refs=(False, False), green=20, red=10)
        assert d._assess_confidence() == "LOW"

    def test_uncalibrated_in_range_is_low(self):
        assert self._detector(0.25, calibrated=False)._assess_confidence() == "LOW"

    def test_uncalibrated_out_of_range_is_failed(self):
        assert self._detector(0.0, calibrated=False)._assess_confidence() == "FAILED"


class TestDebugAndBuildResult:
    def test_debug_writes_images(self, tmp_path, capsys):
        path = make_chart(tmp_path / "c.png")
        out_dir = tmp_path / "dbg"
        out_dir.mkdir()
        result = UptrendRatioDetector(path).detect(debug=True, debug_output_dir=str(out_dir))
        assert "Debug image saved to" in capsys.readouterr().out
        assert (out_dir / "c_debug_detection.jpeg").exists()
        assert (out_dir / "c_debug_green_mask.png").exists()
        assert (out_dir / "c_debug_red_mask.png").exists()
        assert result["current_color"] == "GREEN"

    def test_debug_defaults_to_image_directory_red(self, tmp_path):
        path = make_chart(tmp_path / "c.png", color=lambda x: RED)
        UptrendRatioDetector(path).detect(debug=True)
        assert (tmp_path / "c_debug_detection.jpeg").exists()

    def test_debug_without_value_or_refs(self, tmp_path):
        path = make_chart(tmp_path / "c.png", right_end=0, refs=(False, False))
        d = UptrendRatioDetector(path)
        d.detect(debug=True)
        assert (tmp_path / "c_debug_detection.jpeg").exists()

    def test_build_result_zero_value(self):
        d = UptrendRatioDetector("x.png")
        d._current_value = 0.0
        d._current_color = "RED"
        result = d._build_result()
        assert result["current_value"] == 0.0
        assert result["current_value_percent"] == "0.0%"
        assert result["interpretation"] == "oversold"
        assert result["current_color"] == "RED"


class TestFormatAndMain:
    def test_format_with_value(self, green_chart):
        result = UptrendRatioDetector(green_chart).detect()
        text = format_result_for_human(result)
        assert "Uptrend Ratio Detection Results" in text
        assert f"Current Value: {result['current_value_percent']} (neutral_bullish)" in text
        assert "Current Color: GREEN" in text
        assert "Upper reference (37%) Y-pixel" in text
        assert "Lower reference (10%) Y-pixel" in text
        assert "Calibration successful: True" in text

    def test_format_not_detected(self, tmp_path):
        path = make_chart(tmp_path / "c.png", right_end=0)
        text = format_result_for_human(UptrendRatioDetector(path).detect())
        assert "Current Value: NOT DETECTED" in text
        assert "Confidence: FAILED" in text

    def test_main_json(self, green_chart, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["prog", green_chart, "--json"])
        dur.main()
        data = json.loads(capsys.readouterr().out)
        assert data["current_color"] == "GREEN"
        assert data["debug_info"]["rightmost_col"] == W - 6

    def test_main_json_with_debug_masks(self, green_chart, monkeypatch, capsys):
        # Regression: debug_info holds numpy ints and mask arrays, which used to
        # make --json fail with "Object of type int64 is not JSON serializable".
        monkeypatch.setattr(sys, "argv", ["prog", green_chart, "--json", "--debug"])
        dur.main()
        out = capsys.readouterr().out
        data = json.loads(out[out.index("{") :])
        assert data["debug_info"]["green_mask"] == f"<ndarray shape={[H, W]}>"

    def test_json_default_rejects_unknown_types(self):
        with pytest.raises(TypeError, match="not JSON serializable"):
            dur._json_default(object())

    def test_main_json_on_sample_chart(self, sample_uptrend_chart, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["prog", sample_uptrend_chart, "--json"])
        dur.main()
        data = json.loads(capsys.readouterr().out)
        assert data["current_color"] in {"GREEN", "RED"}

    def test_main_human(self, green_chart, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["prog", green_chart])
        dur.main()
        assert "Uptrend Ratio Detection Results" in capsys.readouterr().out

    def test_main_missing_file(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["prog", str(tmp_path / "nope.png")])
        with pytest.raises(SystemExit) as exc:
            dur.main()
        assert exc.value.code == 1
        assert "File not found" in capsys.readouterr().err

    def test_main_failed_detection_exits_1(self, tmp_path, monkeypatch, capsys):
        path = make_chart(tmp_path / "c.png", right_end=0)
        monkeypatch.setattr(sys, "argv", ["prog", path])
        with pytest.raises(SystemExit) as exc:
            dur.main()
        assert exc.value.code == 1
        assert "Confidence: FAILED" in capsys.readouterr().out

    def test_main_file_not_found_from_detector(self, green_chart, monkeypatch, capsys):
        def boom(self, debug=False, debug_output_dir=None):
            raise FileNotFoundError("vanished")

        monkeypatch.setattr(UptrendRatioDetector, "detect", boom)
        monkeypatch.setattr(sys, "argv", ["prog", green_chart])
        with pytest.raises(SystemExit) as exc:
            dur.main()
        assert exc.value.code == 1
        assert "Error: vanished" in capsys.readouterr().err

    @pytest.mark.parametrize("debug", [False, True])
    def test_main_unexpected_error(self, green_chart, monkeypatch, capsys, debug):
        def boom(self, debug=False, debug_output_dir=None):
            raise RuntimeError("kaput")

        monkeypatch.setattr(UptrendRatioDetector, "detect", boom)
        argv = ["prog", green_chart] + (["--debug"] if debug else [])
        monkeypatch.setattr(sys, "argv", argv)
        with pytest.raises(SystemExit) as exc:
            dur.main()
        assert exc.value.code == 1
        err = capsys.readouterr().err
        assert "Error: kaput" in err
        assert ("Traceback" in err) is debug
