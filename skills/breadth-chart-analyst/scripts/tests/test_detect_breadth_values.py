"""Tests for detect_breadth_values.py using synthetic charts built at runtime."""

import json
import sys

import cv2
import detect_breadth_values as dbv
import numpy as np
import pytest
from detect_breadth_values import BreadthChartDetector, format_result_for_human

W, H = 400, 300
RED_Y, BLUE_Y = 60, 240  # pixel rows for the 0.73 and 0.23 reference lines
RED_BGR = (0, 0, 255)
BLUE_BGR = (255, 0, 0)
GREEN_BGR = (0, 200, 0)
ORANGE_BGR = (0, 128, 255)


def y_for(value: float) -> int:
    """Pixel row on the synthetic chart for a given 0-1 value."""
    return round(RED_Y + (0.73 - value) / 0.50 * (BLUE_Y - RED_Y))


def make_chart(path, green=0.60, orange=0.40, red=True, blue=True):
    img = np.full((H, W, 3), 255, dtype=np.uint8)
    if red:
        cv2.line(img, (0, RED_Y), (W - 1, RED_Y), RED_BGR, 3)
    if blue:
        cv2.line(img, (0, BLUE_Y), (W - 1, BLUE_Y), BLUE_BGR, 3)
    if green is not None:
        cv2.line(img, (W // 2, y_for(green)), (W - 1, y_for(green)), GREEN_BGR, 3)
    if orange is not None:
        cv2.line(img, (W // 2, y_for(orange)), (W - 1, y_for(orange)), ORANGE_BGR, 3)
    cv2.imwrite(str(path), img)
    return str(path)


@pytest.fixture
def chart(tmp_path):
    return make_chart(tmp_path / "chart.png")


class TestInit:
    def test_unreadable_image_raises(self, tmp_path):
        bad = tmp_path / "bad.png"
        bad.write_bytes(b"not an image")
        with pytest.raises(ValueError, match="Could not read image"):
            BreadthChartDetector(str(bad))

    def test_dimensions_recorded(self, chart):
        d = BreadthChartDetector(chart)
        assert (d.width, d.height) == (W, H)


class TestFindHorizontalLine:
    def test_empty_mask_returns_none(self, chart):
        d = BreadthChartDetector(chart)
        assert d._find_horizontal_line_y(np.zeros((H, W), dtype=np.uint8)) is None

    def test_thick_line_returns_center(self, chart):
        d = BreadthChartDetector(chart)
        mask = np.zeros((H, W), dtype=np.uint8)
        mask[100:105, :] = 255
        assert d._find_horizontal_line_y(mask) == 102

    def test_strongest_group_wins(self, chart):
        d = BreadthChartDetector(chart)
        mask = np.zeros((H, W), dtype=np.uint8)
        mask[50, : W // 4] = 255  # short line, below the min-width threshold
        mask[150, :] = 255  # weaker full-width line
        mask[200:203, :] = 255  # stronger thick line
        assert d._find_horizontal_line_y(mask) == 201


class TestCalibration:
    def test_detected_reference_lines(self, chart):
        d = BreadthChartDetector(chart)
        assert d._calibrate_y_axis() is True
        assert abs(d.red_line_y - RED_Y) <= 1
        assert abs(d.blue_line_y - BLUE_Y) <= 1
        assert d.y_scale == pytest.approx(-0.5 / (BLUE_Y - RED_Y), rel=0.02)
        assert d._pixel_y_to_value(d.red_line_y) == pytest.approx(0.73)
        assert d._pixel_y_to_value(d.blue_line_y) == pytest.approx(0.23)

    def test_missing_lines_use_estimated_calibration(self, tmp_path, capsys):
        path = make_chart(tmp_path / "nolines.png", red=False, blue=False)
        d = BreadthChartDetector(path)
        assert d._calibrate_y_axis() is True
        assert "Could not detect reference lines" in capsys.readouterr().out
        top, bottom = int(H * 0.1), int(H * 0.85)
        assert d.red_line_y == top + int((bottom - top) * (1 - 0.73))
        assert d.blue_line_y == top + int((bottom - top) * (1 - 0.23))

    def test_only_blue_missing_estimates_blue(self, tmp_path):
        path = make_chart(tmp_path / "noblue.png", blue=False)
        d = BreadthChartDetector(path)
        assert d._calibrate_y_axis() is True
        assert abs(d.red_line_y - RED_Y) <= 1
        top, bottom = int(H * 0.1), int(H * 0.85)
        assert d.blue_line_y == top + int((bottom - top) * (1 - 0.23))

    def test_swapped_lines_are_reordered(self, chart):
        d = BreadthChartDetector(chart)
        d._detect_reference_lines = lambda: (True, True)
        d.red_line_y, d.blue_line_y = 200, 100
        assert d._calibrate_y_axis() is True
        assert (d.red_line_y, d.blue_line_y) == (100, 200)

    def test_zero_pixel_diff_fails(self, chart):
        d = BreadthChartDetector(chart)
        d._detect_reference_lines = lambda: (True, True)
        d.red_line_y = d.blue_line_y = 150
        assert d._calibrate_y_axis() is False
        assert d.y_scale is None

    def test_pixel_y_to_value_requires_calibration(self, chart):
        d = BreadthChartDetector(chart)
        with pytest.raises(ValueError, match="not calibrated"):
            d._pixel_y_to_value(10)


class TestLineDetection:
    def test_no_pixels_returns_none(self, chart):
        d = BreadthChartDetector(chart)
        d._calibrate_y_axis()
        assert d._detect_line_at_right_edge(np.zeros((H, W), dtype=np.uint8)) is None

    def test_mode_used_on_large_discrepancy(self, chart):
        d = BreadthChartDetector(chart, debug=True)
        d._calibrate_y_axis()
        mask = np.zeros((H, W), dtype=np.uint8)
        mask[100, W - 50 : W - 5] = 255  # dense horizontal run -> mode
        mask[250:291, W - 1] = 255  # far outlier column at the rightmost edge
        d._detect_line_at_right_edge(mask, line_name="x")
        assert d.debug_info["x_mode_y"] == 100
        assert abs(d.debug_info["x_weighted_y"] - 100) > 20
        assert d.debug_info["x_final_y"] == 100

    def test_value_clamped_to_unit_interval(self, chart):
        d = BreadthChartDetector(chart)
        d._calibrate_y_axis()
        mask = np.zeros((H, W), dtype=np.uint8)
        mask[10, W - 20 :] = 255
        d.y_scale, d.y_offset = -0.01, 2.0  # raw value > 1
        assert d._detect_line_at_right_edge(mask) == 1.0
        d.y_scale, d.y_offset = 0.01, -5.0  # raw value < 0
        assert d._detect_line_at_right_edge(mask) == 0.0


class TestAnalyze:
    def test_values_detected_accurately(self, chart):
        result = BreadthChartDetector(chart).analyze()
        assert result["200ma"] == pytest.approx(0.60, abs=0.02)
        assert result["8ma"] == pytest.approx(0.40, abs=0.02)
        assert result["confidence"] == "high"
        assert result["calibration"]["calibrated"] is True
        assert result["image"] == {"path": chart, "width": W, "height": H}
        assert result["200ma_percent"].endswith("%")

    @pytest.mark.parametrize(
        "green,expected",
        [
            (0.65, "healthy (>=60%)"),
            (0.55, "narrow_rally (50-60%)"),
            (0.45, "caution (40-50%)"),
            (0.30, "weak (<40%)"),
        ],
    )
    def test_200ma_interpretation(self, tmp_path, green, expected):
        path = make_chart(tmp_path / "c.png", green=green, orange=0.5)
        assert BreadthChartDetector(path).analyze()["200ma_interpretation"] == expected

    @pytest.mark.parametrize(
        "orange,expected",
        [
            (0.78, "overbought (>=73%)"),
            (0.66, "healthy_bullish (60-73%)"),
            (0.50, "neutral (40-60%)"),
            (0.30, "weak (23-40%)"),
            (0.15, "oversold (<23%)"),
        ],
    )
    def test_8ma_interpretation(self, tmp_path, orange, expected):
        path = make_chart(tmp_path / "c.png", green=0.5, orange=orange)
        assert BreadthChartDetector(path).analyze()["8ma_interpretation"] == expected

    def test_nothing_detected_is_failed(self, tmp_path):
        path = make_chart(tmp_path / "c.png", green=None, orange=None)
        result = BreadthChartDetector(path).analyze()
        assert result["confidence"] == "failed"
        assert result["200ma"] is None and result["8ma"] is None
        assert result["200ma_percent"] is None
        assert "200ma_interpretation" not in result
        assert "8ma_interpretation" not in result

    def test_single_line_gives_medium_confidence(self, tmp_path):
        path = make_chart(tmp_path / "c.png", orange=None)
        result = BreadthChartDetector(path).analyze()
        assert result["8ma"] is None
        assert result["confidence"] == "medium"

    def test_out_of_range_value_is_low(self, tmp_path):
        path = make_chart(tmp_path / "c.png", green=0.08, orange=0.5)
        result = BreadthChartDetector(path).analyze()
        assert result["200ma"] < 0.1
        assert result["confidence"] == "low"

    def test_debug_mode_writes_images(self, tmp_path, capsys):
        path = make_chart(tmp_path / "c.png")
        result = BreadthChartDetector(path, debug=True).analyze()
        out = capsys.readouterr().out
        assert "Debug detection image saved to" in out
        assert (tmp_path / "c_debug_detection.png").exists()
        assert (tmp_path / "c_debug_green_mask.png").exists()
        assert (tmp_path / "c_debug_orange_mask.png").exists()
        assert result["debug"]["green_pixel_count"] > 0
        assert result["debug"]["orange_pixel_count"] > 0
        assert result["confidence"] == "high"

    def test_debug_low_pixel_count_degrades_to_medium(self, tmp_path):
        path = make_chart(tmp_path / "c.png")
        d = BreadthChartDetector(path, debug=True)
        d._calibrate_y_axis()
        d._detect_green_line()
        d._detect_orange_line()
        d.debug_info["green_pixel_count"] = 5
        assert d._assess_confidence(0.6, 0.4) == "medium"

    def test_debug_without_refs_is_low(self, tmp_path):
        path = make_chart(tmp_path / "c.png", red=False, blue=False)
        d = BreadthChartDetector(path, debug=True)
        d._calibrate_y_axis()
        assert d._assess_confidence(0.6, 0.4) == "low"
        assert d._assess_confidence(0.6, None) == "low"

    def test_assess_confidence_both_none_is_failed(self, chart):
        d = BreadthChartDetector(chart)
        assert d._assess_confidence(None, None) == "failed"


class TestFormatAndCli:
    def test_format_detected(self, chart):
        result = BreadthChartDetector(chart).analyze()
        text = format_result_for_human(result)
        assert "Confidence: HIGH" in text
        assert f"200-Day MA: {result['200ma_percent']}" in text
        assert "Calibration successful: True" in text
        assert "Debug Info" not in text

    def test_format_not_detected_and_debug(self):
        result = {
            "image": {"path": "x.png"},
            "confidence": "failed",
            "200ma": None,
            "8ma": None,
            "calibration": {"red_line_y": 1, "blue_line_y": 2, "calibrated": False},
            "debug": {"green_pixel_count": 3, "orange_pixel_count": 4},
        }
        text = format_result_for_human(result)
        assert "200-Day MA: NOT DETECTED" in text
        assert "8-Day MA:   NOT DETECTED" in text
        assert "Green pixels detected: 3" in text
        assert "Orange pixels detected: 4" in text

    def test_main_json_output(self, chart, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["prog", chart, "--json"])
        dbv.main()
        data = json.loads(capsys.readouterr().out)
        assert data["confidence"] == "high"
        assert data["200ma"] == pytest.approx(0.60, abs=0.02)

    def test_main_human_output(self, chart, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["prog", chart])
        dbv.main()
        out = capsys.readouterr().out
        assert "Breadth Chart Detection Results" in out
        assert "JSON output:" in out

    def test_main_missing_file(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["prog", str(tmp_path / "nope.png")])
        with pytest.raises(SystemExit) as exc:
            dbv.main()
        assert exc.value.code == 1
        assert "File not found" in capsys.readouterr().err

    def test_main_failed_detection_exits_1(self, tmp_path, monkeypatch, capsys):
        path = make_chart(tmp_path / "c.png", green=None, orange=None)
        monkeypatch.setattr(sys, "argv", ["prog", path, "--json"])
        with pytest.raises(SystemExit) as exc:
            dbv.main()
        assert exc.value.code == 1
        assert json.loads(capsys.readouterr().out)["confidence"] == "failed"

    @pytest.mark.parametrize("debug", [False, True])
    def test_main_unreadable_image(self, tmp_path, monkeypatch, capsys, debug):
        bad = tmp_path / "bad.png"
        bad.write_bytes(b"garbage")
        argv = ["prog", str(bad)] + (["--debug"] if debug else [])
        monkeypatch.setattr(sys, "argv", argv)
        with pytest.raises(SystemExit) as exc:
            dbv.main()
        assert exc.value.code == 1
        err = capsys.readouterr().err
        assert "Could not read image" in err
        assert ("Traceback" in err) is debug
