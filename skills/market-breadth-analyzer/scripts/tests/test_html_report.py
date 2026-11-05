"""Tests for the HTML report: same data as the Markdown report plus a
'how to read' explanation and a plain-language reading of every value."""

import pytest
from html_report import (
    explain_8ma_level,
    explain_bearish,
    explain_cycle,
    explain_divergence_window,
    explain_gap,
    explain_percentile,
    generate_html_report,
)
from test_report_generator import _base_analysis


def _render(tmp_path, analysis=None):
    path = tmp_path / "report.html"
    generate_html_report(analysis or _base_analysis(), str(path))
    return path.read_text(encoding="utf-8")


# --- Plain-language readings ---


@pytest.mark.parametrize(
    "value,keyword",
    [
        (0.75, "very strong"),
        (0.64, "healthy"),
        (0.55, "about half"),
        (0.45, "weakening"),
        (0.30, "extreme weakness"),
        (0.15, "crisis"),
    ],
)
def test_explain_8ma_level_bands(value, keyword):
    assert keyword in explain_8ma_level(value).lower()


def test_explain_8ma_level_shows_percent():
    assert "64%" in explain_8ma_level(0.639)


def test_explain_8ma_level_missing():
    assert explain_8ma_level(None) == "No data."


def test_explain_gap_above_and_below():
    assert "above" in explain_gap(0.03, "rising").lower()
    assert "below" in explain_gap(-0.04, "falling").lower()


def test_explain_gap_flags_early_signals():
    assert "early recovery" in explain_gap(-0.02, "rising").lower()
    assert "early deterioration" in explain_gap(0.02, "falling").lower()


def test_explain_cycle_peak_and_trough():
    assert "peak" in explain_cycle("PEAK", 42, "rising").lower()
    assert "42" in explain_cycle("PEAK", 42, "rising")
    assert "trough" in explain_cycle("TROUGH", 10, "rising").lower()
    assert explain_cycle(None, None, None) == "No peak or trough found yet."


def test_explain_bearish_states():
    assert "no warning" in explain_bearish(False, -1, False).lower()
    assert "active" in explain_bearish(True, -1, False).lower()
    assert "pink zone" in explain_bearish(False, -1, True).lower()


def test_explain_percentile_bands():
    assert "weak" in explain_percentile(15).lower()
    assert "strong" in explain_percentile(85).lower()
    assert "37" in explain_percentile(37.3)


@pytest.mark.parametrize(
    "sp,breadth,keyword",
    [
        (3.0, 0.05, "healthy"),
        (3.0, -0.05, "narrow"),
        (-2.0, 0.05, "bottom"),
        (-2.0, -0.05, "both falling"),
        (0.1, 0.002, "flat"),
    ],
)
def test_explain_divergence_window(sp, breadth, keyword):
    assert keyword in explain_divergence_window(sp, breadth).lower()


# --- Rendered document ---


def test_html_is_complete_document(tmp_path):
    content = _render(tmp_path)
    assert content.startswith("<!doctype html>")
    assert "<title>" in content
    assert "</html>" in content


def test_html_has_main_sections(tmp_path):
    content = _render(tmp_path)
    for heading in (
        "How to read this report",
        "Overall Assessment",
        "Component Scores",
        "Component Details",
        "Key Levels to Watch",
        "Recommended Actions",
    ):
        assert heading in content


def test_html_tables_have_explanation_columns(tmp_path):
    content = _render(tmp_path)
    assert "What it measures" in content
    assert "Today" in content


def test_html_shows_values(tmp_path):
    content = _render(tmp_path)
    assert "60.0" in content  # composite score
    assert "65.0%" in content  # 8MA as a percentage
    assert "Healthy" in content


def test_html_shows_score_trend_when_history(tmp_path):
    analysis = _base_analysis(
        trend_summary={
            "direction": "improving",
            "delta": 3.6,
            "entries": [
                {"data_date": "2025-01-13", "composite_score": 56.4},
                {"data_date": "2025-01-14", "composite_score": 60.0},
            ],
        }
    )
    content = _render(tmp_path, analysis)
    assert "Score Trend" in content
    assert "2025-01-13" in content


def test_html_freshness_warning_shown(tmp_path):
    analysis = _base_analysis()
    analysis["metadata"]["data_freshness"]["warning"] = "Data is 7 days old"
    assert "Data is 7 days old" in _render(tmp_path, analysis)


def test_html_escapes_text(tmp_path):
    analysis = _base_analysis()
    analysis["composite"]["guidance"] = "<script>alert(1)</script>"
    content = _render(tmp_path, analysis)
    assert "<script>alert(1)</script>" not in content
    assert "&lt;script&gt;" in content


def test_html_survives_missing_components(tmp_path):
    analysis = _base_analysis()
    analysis["components"] = {}
    content = _render(tmp_path, analysis)
    assert "Overall Assessment" in content


def test_html_report_write_error(tmp_path):
    bad_path = str(tmp_path / "nonexistent_dir" / "report.html")
    with pytest.raises(OSError):
        generate_html_report(_base_analysis(), bad_path)
