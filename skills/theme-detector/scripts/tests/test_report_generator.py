"""Tests for report_generator module."""

import json
import os
import tempfile
from datetime import datetime

import pytest

from report_generator import (
    generate_json_report,
    generate_markdown_report,
    save_reports,
)


# --- Fixtures ---

@pytest.fixture
def sample_themes():
    """Sample theme data for testing."""
    return [
        {
            "name": "AI / Semiconductors",
            "direction": "bullish",
            "heat": 8.5,
            "maturity": 6.2,
            "stage": "growth",
            "confidence": 85,
            "industries": ["Semiconductors", "Software - Infrastructure",
                           "Information Technology Services"],
            "heat_breakdown": {
                "performance_momentum": 7.5,
                "volume_confirmation": 8.0,
                "breadth_score": 9.0,
            },
            "maturity_breakdown": {
                "duration_score": 6.0,
                "crowding_score": 5.5,
                "acceleration": 7.0,
            },
            "representative_stocks": ["NVDA", "AVGO", "AMD", "MSFT"],
            "proxy_etfs": ["SMH", "SOXX", "XLK"],
        },
        {
            "name": "Energy Transition",
            "direction": "bullish",
            "heat": 6.3,
            "maturity": 4.1,
            "stage": "early",
            "confidence": 70,
            "industries": ["Solar", "Uranium"],
            "heat_breakdown": {
                "performance_momentum": 6.0,
                "volume_confirmation": 5.5,
                "breadth_score": 7.0,
            },
            "maturity_breakdown": {},
            "representative_stocks": ["FSLR", "ENPH"],
            "proxy_etfs": ["TAN", "URA"],
        },
        {
            "name": "Traditional Retail",
            "direction": "bearish",
            "heat": 5.8,
            "maturity": 7.5,
            "stage": "decline",
            "confidence": 65,
            "industries": ["Specialty Retail", "Department Stores"],
            "heat_breakdown": {
                "performance_momentum": -4.0,
                "volume_confirmation": 3.0,
                "breadth_score": 2.5,
            },
            "maturity_breakdown": {},
            "representative_stocks": ["M", "KSS"],
            "proxy_etfs": ["XRT"],
        },
    ]


@pytest.fixture
def sample_industry_rankings():
    """Sample industry rankings."""
    return {
        "top": [
            {"name": "Semiconductors", "perf_1w": 0.05, "perf_1m": 0.12,
             "perf_3m": 0.25, "composite_score": 0.89},
            {"name": "Software - Infrastructure", "perf_1w": 0.03,
             "perf_1m": 0.08, "perf_3m": 0.18, "composite_score": 0.75},
        ],
        "bottom": [
            {"name": "Department Stores", "perf_1w": -0.04, "perf_1m": -0.10,
             "perf_3m": -0.15, "composite_score": -0.65},
            {"name": "Specialty Retail", "perf_1w": -0.03, "perf_1m": -0.07,
             "perf_3m": -0.12, "composite_score": -0.50},
        ],
    }


@pytest.fixture
def sample_sector_uptrend():
    """Sample sector uptrend data."""
    return {
        "Technology": {
            "ratio": 0.35,
            "ma_10": 0.32,
            "slope": 0.0025,
            "trend": "up",
            "latest_date": "2026-02-14",
        },
        "Healthcare": {
            "ratio": 0.22,
            "ma_10": 0.24,
            "slope": -0.0015,
            "trend": "down",
            "latest_date": "2026-02-14",
        },
    }


@pytest.fixture
def sample_metadata():
    """Sample metadata."""
    return {
        "generated_at": "2026-02-16 10:00:00",
        "data_sources": {
            "finviz": "ok",
            "uptrend": "ok",
        },
    }


@pytest.fixture
def sample_json_report(sample_themes, sample_industry_rankings,
                        sample_sector_uptrend, sample_metadata):
    """Full JSON report generated from sample data."""
    return generate_json_report(
        sample_themes, sample_industry_rankings,
        sample_sector_uptrend, sample_metadata,
    )


# --- Tests for generate_json_report ---

class TestGenerateJsonReport:

    def test_report_structure(self, sample_json_report):
        """JSON report has all required top-level keys."""
        required_keys = [
            "report_type", "generated_at", "metadata", "summary",
            "themes", "industry_rankings", "sector_uptrend", "data_quality",
        ]
        for key in required_keys:
            assert key in sample_json_report, f"Missing key: {key}"

    def test_report_type(self, sample_json_report):
        assert sample_json_report["report_type"] == "theme_detector"

    def test_summary_counts(self, sample_json_report):
        summary = sample_json_report["summary"]
        assert summary["total_themes"] == 3
        assert summary["bullish_count"] == 2
        assert summary["bearish_count"] == 1
        assert summary["top_bullish"] == "AI / Semiconductors"
        assert summary["top_bearish"] == "Traditional Retail"

    def test_themes_grouped(self, sample_json_report):
        themes = sample_json_report["themes"]
        assert "all" in themes
        assert "bullish" in themes
        assert "bearish" in themes
        assert len(themes["all"]) == 3
        assert len(themes["bullish"]) == 2
        assert len(themes["bearish"]) == 1

    def test_bullish_sorted_by_heat(self, sample_json_report):
        bullish = sample_json_report["themes"]["bullish"]
        heats = [t["heat"] for t in bullish]
        assert heats == sorted(heats, reverse=True)

    def test_data_quality_ok(self, sample_json_report):
        dq = sample_json_report["data_quality"]
        assert dq["status"] == "ok"
        assert dq["flags"] == []

    def test_empty_themes(self, sample_industry_rankings,
                          sample_sector_uptrend, sample_metadata):
        """Empty themes list produces warning, not error."""
        report = generate_json_report(
            [], sample_industry_rankings,
            sample_sector_uptrend, sample_metadata,
        )
        assert report["summary"]["total_themes"] == 0
        assert report["summary"]["top_bullish"] is None
        assert report["data_quality"]["status"] == "warning"
        assert any("No themes" in f for f in report["data_quality"]["flags"])

    def test_json_serializable(self, sample_json_report):
        """Report can be serialized to JSON."""
        serialized = json.dumps(sample_json_report, default=str)
        deserialized = json.loads(serialized)
        assert deserialized["report_type"] == "theme_detector"


# --- Tests for generate_markdown_report ---

class TestGenerateMarkdownReport:

    def test_contains_all_sections(self, sample_json_report):
        """Markdown contains all 7 required sections."""
        md = generate_markdown_report(sample_json_report)
        assert "## 1. Theme Dashboard" in md
        assert "## 2. Bullish Themes (Top 3)" in md
        assert "## 3. Bearish Themes (Top 3)" in md
        assert "## 4. All Themes Summary" in md
        assert "## 5. Industry Rankings" in md
        assert "## 6. Sector Uptrend Ratios" in md
        assert "## 7. Methodology & Data Quality" in md

    def test_header_info(self, sample_json_report):
        md = generate_markdown_report(sample_json_report)
        assert "# Theme Detector Report" in md
        assert "2026-02-16 10:00:00" in md

    def test_theme_dashboard_table(self, sample_json_report):
        md = generate_markdown_report(sample_json_report)
        assert "AI / Semiconductors" in md
        assert "BULL" in md
        assert "BEAR" in md

    def test_bullish_detail_stocks(self, sample_json_report):
        md = generate_markdown_report(sample_json_report)
        assert "NVDA" in md
        assert "SMH" in md

    def test_industry_rankings_present(self, sample_json_report):
        md = generate_markdown_report(sample_json_report)
        assert "Semiconductors" in md
        assert "Department Stores" in md
        assert "Top 15" in md
        assert "Bottom 15" in md

    def test_sector_uptrend_table(self, sample_json_report):
        md = generate_markdown_report(sample_json_report)
        assert "Technology" in md
        assert "Healthcare" in md
        assert "35.0%" in md  # Technology ratio

    def test_methodology_present(self, sample_json_report):
        md = generate_markdown_report(sample_json_report)
        assert "Methodology" in md
        assert "Disclaimer" in md

    def test_empty_themes_warning(self, sample_industry_rankings,
                                   sample_sector_uptrend, sample_metadata):
        """Empty themes show warning, not crash."""
        report = generate_json_report(
            [], sample_industry_rankings,
            sample_sector_uptrend, sample_metadata,
        )
        md = generate_markdown_report(report)
        assert "WARNING" in md or "No themes" in md

    def test_no_industry_data(self, sample_themes, sample_sector_uptrend,
                               sample_metadata):
        """Missing industry rankings handled gracefully."""
        report = generate_json_report(
            sample_themes, {"top": [], "bottom": []},
            sample_sector_uptrend, sample_metadata,
        )
        md = generate_markdown_report(report)
        assert "## 5. Industry Rankings" in md
        assert "unavailable" in md.lower() or "Industry" in md


# --- Tests for save_reports ---

class TestSaveReports:

    def test_save_creates_files(self, sample_json_report):
        """save_reports creates both JSON and MD files."""
        md = generate_markdown_report(sample_json_report)
        with tempfile.TemporaryDirectory() as tmpdir:
            paths = save_reports(sample_json_report, md, tmpdir)
            assert os.path.exists(paths["json"])
            assert os.path.exists(paths["markdown"])

    def test_filename_convention(self, sample_json_report):
        """Filenames follow theme_detector_YYYY-MM-DD_HHMMSS pattern."""
        md = generate_markdown_report(sample_json_report)
        with tempfile.TemporaryDirectory() as tmpdir:
            paths = save_reports(sample_json_report, md, tmpdir)
            json_name = os.path.basename(paths["json"])
            md_name = os.path.basename(paths["markdown"])
            assert json_name.startswith("theme_detector_")
            assert json_name.endswith(".json")
            assert md_name.startswith("theme_detector_")
            assert md_name.endswith(".md")

    def test_json_file_valid(self, sample_json_report):
        """Saved JSON file is valid JSON."""
        md = generate_markdown_report(sample_json_report)
        with tempfile.TemporaryDirectory() as tmpdir:
            paths = save_reports(sample_json_report, md, tmpdir)
            with open(paths["json"]) as f:
                loaded = json.load(f)
            assert loaded["report_type"] == "theme_detector"

    def test_creates_output_dir(self, sample_json_report):
        """save_reports creates output dir if it doesn't exist."""
        md = generate_markdown_report(sample_json_report)
        with tempfile.TemporaryDirectory() as tmpdir:
            nested = os.path.join(tmpdir, "reports", "sub")
            paths = save_reports(sample_json_report, md, nested)
            assert os.path.exists(paths["json"])
