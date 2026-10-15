"""Tests for extract_chart_right_edge.py using synthetic images."""

import sys

import extract_chart_right_edge as ecre
import pytest
from PIL import Image


def make_image(path, size=(200, 100)):
    img = Image.new("RGB", size, (255, 255, 255))
    # Mark the right-most column so crops are distinguishable
    for y in range(size[1]):
        img.putpixel((size[0] - 1, y), (255, 0, 0))
    img.save(path)
    return str(path)


class TestExtractRightEdge:
    def test_default_output_path_and_size(self, tmp_path):
        src = make_image(tmp_path / "chart.png")
        out = ecre.extract_right_edge(src)
        assert out == str(tmp_path / "chart_right_edge.png")
        with Image.open(out) as im:
            assert im.size == (50, 100)
            assert im.convert("RGB").getpixel((49, 0)) == (255, 0, 0)

    def test_custom_percent_and_output(self, tmp_path):
        src = make_image(tmp_path / "chart.png")
        dest = tmp_path / "out.png"
        out = ecre.extract_right_edge(src, 40, str(dest))
        assert out == str(dest)
        with Image.open(dest) as im:
            assert im.size == (80, 100)

    def test_jpeg_quality_save(self, tmp_path):
        src = make_image(tmp_path / "chart.jpg")
        out = ecre.extract_right_edge(src, 50)
        assert out.endswith("chart_right_edge.jpg")
        with Image.open(out) as im:
            assert im.size == (100, 100)


class TestExtractWithMarker:
    def test_creates_cropped_and_marked(self, tmp_path):
        src = make_image(tmp_path / "chart.png")
        cropped, marked = ecre.extract_right_edge_with_marker(src, 25)
        assert cropped == str(tmp_path / "chart_right_edge.png")
        assert marked == str(tmp_path / "chart_marked.png")
        with Image.open(cropped) as im:
            assert im.size == (50, 100)
        with Image.open(marked) as im:
            assert im.size == (200, 100)
            # boundary line drawn in red at x = 150
            assert im.convert("RGB").getpixel((150, 50)) == (255, 0, 0)

    def test_explicit_output_path(self, tmp_path):
        src = make_image(tmp_path / "chart.png")
        dest = tmp_path / "custom.png"
        cropped, _ = ecre.extract_right_edge_with_marker(src, 50, str(dest))
        assert cropped == str(dest)
        with Image.open(dest) as im:
            assert im.size == (100, 100)

    def test_font_fallback(self, tmp_path, monkeypatch):
        real_truetype = ecre.ImageFont.truetype

        def boom(font, *a, **k):
            if isinstance(font, str):
                raise OSError("no font")
            return real_truetype(font, *a, **k)

        monkeypatch.setattr(ecre.ImageFont, "truetype", boom)
        src = make_image(tmp_path / "chart.png")
        cropped, marked = ecre.extract_right_edge_with_marker(src)
        assert marked == str(tmp_path / "chart_marked.png")
        assert (tmp_path / "chart_marked.png").exists()
        assert cropped == str(tmp_path / "chart_right_edge.png")


class TestProcessBreadthCharts:
    def test_processes_images_skips_derived_and_non_images(self, tmp_path, capsys):
        make_image(tmp_path / "SP500_breadth.png")
        make_image(tmp_path / "random.png")
        make_image(tmp_path / "old_right_edge.png")
        make_image(tmp_path / "old_marked.png")
        (tmp_path / "notes.txt").write_text("x")
        results = ecre.process_breadth_charts(str(tmp_path), 25)
        assert sorted(results) == sorted(
            [str(tmp_path / "SP500_breadth.png"), str(tmp_path / "random.png")]
        )
        assert (tmp_path / "SP500_breadth_right_edge.png").exists()
        assert "Processed: SP500_breadth.png" in capsys.readouterr().out

    def test_corrupt_image_reported_on_stderr(self, tmp_path, capsys):
        (tmp_path / "broken.png").write_bytes(b"not an image")
        make_image(tmp_path / "good.png")
        results = ecre.process_breadth_charts(str(tmp_path))
        captured = capsys.readouterr()
        assert list(results) == [str(tmp_path / "good.png")]
        assert "Error processing broken.png" in captured.err


class TestMain:
    def _run(self, monkeypatch, *argv):
        monkeypatch.setattr(sys, "argv", ["prog", *argv])
        ecre.main()

    def test_single_image(self, tmp_path, monkeypatch, capsys):
        src = make_image(tmp_path / "chart.png")
        self._run(monkeypatch, src, "--percent", "50")
        out = capsys.readouterr().out
        assert "Extracting right 50%" in out
        assert "Saved to:" in out
        with Image.open(tmp_path / "chart_right_edge.png") as im:
            assert im.size == (100, 100)

    def test_single_image_mark(self, tmp_path, monkeypatch, capsys):
        src = make_image(tmp_path / "chart.png")
        self._run(monkeypatch, src, "--mark")
        out = capsys.readouterr().out
        assert "Cropped image saved to" in out
        assert "Marked image saved to" in out
        assert (tmp_path / "chart_marked.png").exists()

    def test_dir_mode(self, tmp_path, monkeypatch, capsys):
        make_image(tmp_path / "a.png")
        self._run(monkeypatch, "--dir", str(tmp_path))
        assert "Processed 1 images" in capsys.readouterr().out

    def test_dir_not_found(self, tmp_path, monkeypatch, capsys):
        with pytest.raises(SystemExit) as exc:
            self._run(monkeypatch, "--dir", str(tmp_path / "missing"))
        assert exc.value.code == 1
        assert "Directory not found" in capsys.readouterr().err

    def test_no_args_prints_help(self, monkeypatch, capsys):
        with pytest.raises(SystemExit) as exc:
            self._run(monkeypatch)
        assert exc.value.code == 1
        assert "usage:" in capsys.readouterr().out

    def test_file_not_found(self, tmp_path, monkeypatch, capsys):
        with pytest.raises(SystemExit) as exc:
            self._run(monkeypatch, str(tmp_path / "nope.png"))
        assert exc.value.code == 1
        assert "File not found" in capsys.readouterr().err
