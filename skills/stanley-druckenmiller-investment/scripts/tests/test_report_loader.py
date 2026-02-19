"""Tests for report_loader.py"""

import os
import pytest

from report_loader import (
    find_latest_report,
    load_all_reports,
    extract_signal,
    REQUIRED_SKILLS,
    OPTIONAL_SKILLS,
)


class TestFindLatestReport:
    """Tests for find_latest_report()."""

    def test_finds_most_recent(self, tmp_reports, sample_breadth, make_report_fn):
        """Should return the most recently timestamped file."""
        make_report_fn("market_breadth_", {"old": True}, tmp_reports, age_hours=5)
        make_report_fn("market_breadth_", sample_breadth, tmp_reports, age_hours=0)
        make_report_fn("market_breadth_", {"mid": True}, tmp_reports, age_hours=2)

        result = find_latest_report(tmp_reports, "market_breadth_")
        assert result is not None
        path, data = result
        assert data.get("composite", {}).get("composite_score") == 62.8

    def test_returns_none_when_no_match(self, tmp_reports):
        """Should return None if no files match the prefix."""
        result = find_latest_report(tmp_reports, "nonexistent_")
        assert result is None

    def test_ignores_non_json(self, tmp_reports):
        """Should ignore .md files with matching prefix."""
        md_path = os.path.join(tmp_reports, "market_breadth_2026-02-19.md")
        with open(md_path, "w") as f:
            f.write("# Report")
        result = find_latest_report(tmp_reports, "market_breadth_")
        assert result is None

    def test_respects_max_age(self, tmp_reports, sample_breadth, make_report_fn):
        """Should reject reports older than max_age_hours."""
        make_report_fn("market_breadth_", sample_breadth, tmp_reports, age_hours=100)
        result = find_latest_report(tmp_reports, "market_breadth_", max_age_hours=72)
        assert result is None

    def test_accepts_within_max_age(self, tmp_reports, sample_breadth, make_report_fn):
        """Should accept reports within max_age_hours."""
        make_report_fn("market_breadth_", sample_breadth, tmp_reports, age_hours=24)
        result = find_latest_report(tmp_reports, "market_breadth_", max_age_hours=72)
        assert result is not None


class TestLoadAllReports:
    """Tests for load_all_reports()."""

    def test_loads_all_required(self, all_required_reports):
        """Should load all 5 required skill reports."""
        reports = load_all_reports(all_required_reports)
        assert "market_breadth" in reports
        assert "uptrend_analysis" in reports
        assert "market_top" in reports
        assert "macro_regime" in reports
        assert "ftd_detector" in reports

    def test_loads_optional_when_present(self, full_reports):
        """Should include optional reports when available."""
        reports = load_all_reports(full_reports)
        assert "vcp_screener" in reports
        assert "theme_detector" in reports
        assert "canslim_screener" in reports

    def test_missing_required_raises(self, tmp_reports, sample_breadth, make_report_fn):
        """Should raise ValueError when required report is missing."""
        make_report_fn("market_breadth_", sample_breadth, tmp_reports)
        with pytest.raises(ValueError, match="required"):
            load_all_reports(tmp_reports)

    def test_missing_optional_ok(self, all_required_reports):
        """Should succeed even without optional reports."""
        reports = load_all_reports(all_required_reports)
        assert "vcp_screener" not in reports
        assert "theme_detector" not in reports
        assert "canslim_screener" not in reports
        assert len(reports) == 5

    def test_stale_required_raises(self, tmp_reports, sample_breadth,
                                   sample_uptrend, sample_market_top,
                                   sample_macro_regime, sample_ftd,
                                   make_report_fn):
        """Should raise if required report exceeds max_age_hours."""
        make_report_fn("market_breadth_", sample_breadth, tmp_reports, age_hours=100)
        make_report_fn("uptrend_analysis_", sample_uptrend, tmp_reports)
        make_report_fn("market_top_", sample_market_top, tmp_reports)
        make_report_fn("macro_regime_", sample_macro_regime, tmp_reports)
        make_report_fn("ftd_detector_", sample_ftd, tmp_reports)
        with pytest.raises(ValueError, match="required"):
            load_all_reports(tmp_reports, max_age_hours=72)


class TestExtractSignal:
    """Tests for extract_signal() signal extraction from each skill."""

    def test_breadth_signal(self, sample_breadth):
        sig = extract_signal("market_breadth", sample_breadth)
        assert sig["composite_score"] == 62.8
        assert sig["zone"] == "Healthy"
        assert "source" in sig

    def test_uptrend_signal(self, sample_uptrend):
        sig = extract_signal("uptrend_analysis", sample_uptrend)
        assert sig["composite_score"] == 66.0
        assert sig["zone"] == "Bull"

    def test_market_top_signal(self, sample_market_top):
        sig = extract_signal("market_top", sample_market_top)
        assert sig["composite_score"] == 59.2

    def test_macro_regime_signal(self, sample_macro_regime):
        sig = extract_signal("macro_regime", sample_macro_regime)
        assert sig["composite_score"] == 49.0
        assert sig["regime"] == "broadening"
        assert sig["confidence"] == "medium"

    def test_ftd_signal(self, sample_ftd):
        sig = extract_signal("ftd_detector", sample_ftd)
        assert sig["state"] == "FTD_CONFIRMED"
        assert sig["quality_score"] == 85
        assert sig["dual_confirmation"] is True

    def test_vcp_derived_score(self, sample_vcp):
        """VCP score should be derived from rating distribution + funnel health."""
        sig = extract_signal("vcp_screener", sample_vcp)
        assert 0 <= sig["derived_score"] <= 100
        assert sig["textbook_count"] == 0
        assert sig["strong_count"] == 2

    def test_theme_derived_score(self, sample_theme):
        """Theme score should be derived from hot themes + lifecycle."""
        sig = extract_signal("theme_detector", sample_theme)
        assert 0 <= sig["derived_score"] <= 100
        assert sig["hot_count"] >= 0

    def test_canslim_signal(self, sample_canslim):
        """CANSLIM signal extracts composite_score directly + M component."""
        sig = extract_signal("canslim_screener", sample_canslim)
        assert 0 <= sig["derived_score"] <= 100
        assert sig["m_score"] == 100
        assert sig["m_trend"] == "strong_uptrend"

    def test_vcp_empty_results(self):
        """VCP with no results should yield low score."""
        data = {"metadata": {"funnel": {"universe": 500, "trend_template_passed": 0,
                                        "vcp_candidates": 0}},
                "results": []}
        sig = extract_signal("vcp_screener", data)
        assert sig["derived_score"] <= 15

    def test_theme_all_exhausting(self):
        """Themes all in exhaustion should get penalty."""
        data = {
            "summary": {"total_themes": 3, "bullish_count": 3, "bearish_count": 0},
            "themes": {"all": [
                {"name": "T1", "direction": "bullish", "heat": 90, "stage": "Exhausting", "confidence": "Low"},
                {"name": "T2", "direction": "bullish", "heat": 80, "stage": "Exhausting", "confidence": "Low"},
                {"name": "T3", "direction": "bullish", "heat": 70, "stage": "Exhausting", "confidence": "Low"},
            ]},
        }
        sig = extract_signal("theme_detector", data)
        assert sig["derived_score"] < 60  # Exhaustion penalty applied
