"""Tests for report_generator module."""

import json
import os
import tempfile

import pytest
from report_generator import (
    _fmt_pct,
    _format_stock_list,
    _origin_label,
    generate_json_report,
    generate_markdown_report,
    save_reports,
)

# --- Fixtures ---


@pytest.fixture
def sample_themes():
    """Sample theme data for testing (0-100 scale for heat/maturity)."""
    return [
        {
            "name": "AI / Semiconductors",
            "direction": "bullish",
            "heat": 85.0,
            "maturity": 62.0,
            "stage": "growth",
            "confidence": "High",
            "industries": [
                "Semiconductors",
                "Software - Infrastructure",
                "Information Technology Services",
            ],
            "heat_breakdown": {
                "performance_momentum": 75.0,
                "volume_confirmation": 80.0,
                "breadth_score": 90.0,
            },
            "maturity_breakdown": {
                "duration_score": 60.0,
                "crowding_score": 55.0,
                "acceleration": 70.0,
            },
            "representative_stocks": ["NVDA", "AVGO", "AMD", "MSFT"],
            "proxy_etfs": ["SMH", "SOXX", "XLK"],
        },
        {
            "name": "Energy Transition",
            "direction": "bullish",
            "heat": 63.0,
            "maturity": 41.0,
            "stage": "early",
            "confidence": "Medium",
            "industries": ["Solar", "Uranium"],
            "heat_breakdown": {
                "performance_momentum": 60.0,
                "volume_confirmation": 55.0,
                "breadth_score": 70.0,
            },
            "maturity_breakdown": {},
            "representative_stocks": ["FSLR", "ENPH"],
            "proxy_etfs": ["TAN", "URA"],
        },
        {
            "name": "Traditional Retail",
            "direction": "bearish",
            "heat": 58.0,
            "maturity": 75.0,
            "stage": "decline",
            "confidence": "Low",
            "industries": ["Specialty Retail", "Department Stores"],
            "heat_breakdown": {
                "performance_momentum": -40.0,
                "volume_confirmation": 30.0,
                "breadth_score": 25.0,
            },
            "maturity_breakdown": {},
            "representative_stocks": ["M", "KSS"],
            "proxy_etfs": ["XRT"],
        },
    ]


@pytest.fixture
def sample_industry_rankings():
    """Sample industry rankings (perf values in percent, score is momentum_score)."""
    return {
        "top": [
            {
                "name": "Semiconductors",
                "perf_1w": 5.0,
                "perf_1m": 12.0,
                "perf_3m": 25.0,
                "momentum_score": 0.89,
            },
            {
                "name": "Software - Infrastructure",
                "perf_1w": 3.0,
                "perf_1m": 8.0,
                "perf_3m": 18.0,
                "momentum_score": 0.75,
            },
        ],
        "bottom": [
            {
                "name": "Department Stores",
                "perf_1w": -4.0,
                "perf_1m": -10.0,
                "perf_3m": -15.0,
                "momentum_score": -0.65,
            },
            {
                "name": "Specialty Retail",
                "perf_1w": -3.0,
                "perf_1m": -7.0,
                "perf_3m": -12.0,
                "momentum_score": -0.50,
            },
        ],
    }


@pytest.fixture
def sample_sector_uptrend():
    """Sample sector uptrend data."""
    from datetime import datetime, timedelta

    recent_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    return {
        "Technology": {
            "ratio": 0.35,
            "ma_10": 0.32,
            "slope": 0.0025,
            "trend": "up",
            "latest_date": recent_date,
        },
        "Healthcare": {
            "ratio": 0.22,
            "ma_10": 0.24,
            "slope": -0.0015,
            "trend": "down",
            "latest_date": recent_date,
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
def sample_json_report(
    sample_themes, sample_industry_rankings, sample_sector_uptrend, sample_metadata
):
    """Full JSON report generated from sample data."""
    return generate_json_report(
        sample_themes,
        sample_industry_rankings,
        sample_sector_uptrend,
        sample_metadata,
    )


# --- Tests for generate_json_report ---


class TestGenerateJsonReport:
    def test_report_structure(self, sample_json_report):
        """JSON report has all required top-level keys."""
        required_keys = [
            "report_type",
            "generated_at",
            "metadata",
            "summary",
            "themes",
            "industry_rankings",
            "sector_uptrend",
            "data_quality",
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

    def test_empty_themes(self, sample_industry_rankings, sample_sector_uptrend, sample_metadata):
        """Empty themes list produces warning, not error."""
        report = generate_json_report(
            [],
            sample_industry_rankings,
            sample_sector_uptrend,
            sample_metadata,
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
        assert "## 2. Leading Themes (Top 3)" in md
        assert "## 3. Lagging Themes (Top 3)" in md
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
        assert "LEAD" in md
        assert "LAG" in md

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

    def test_empty_themes_warning(
        self, sample_industry_rankings, sample_sector_uptrend, sample_metadata
    ):
        """Empty themes show warning, not crash."""
        report = generate_json_report(
            [],
            sample_industry_rankings,
            sample_sector_uptrend,
            sample_metadata,
        )
        md = generate_markdown_report(report)
        assert "WARNING" in md or "No themes" in md

    def test_no_industry_data(self, sample_themes, sample_sector_uptrend, sample_metadata):
        """Missing industry rankings handled gracefully."""
        report = generate_json_report(
            sample_themes,
            {"top": [], "bottom": []},
            sample_sector_uptrend,
            sample_metadata,
        )
        md = generate_markdown_report(report)
        assert "## 5. Industry Rankings" in md
        assert "unavailable" in md.lower() or "Industry" in md

    def test_top_n_detail_default_3(self, sample_json_report):
        """Default top_n_detail=3 shows 'Top 3' in section headers."""
        md = generate_markdown_report(sample_json_report)
        assert "## 2. Leading Themes (Top 3)" in md
        assert "## 3. Lagging Themes (Top 3)" in md

    def test_top_n_detail_custom(self, sample_json_report):
        """Custom top_n_detail changes section headers and limits themes."""
        md = generate_markdown_report(sample_json_report, top_n_detail=5)
        assert "## 2. Leading Themes (Top 5)" in md
        assert "## 3. Lagging Themes (Top 5)" in md

    def test_top_n_detail_1(self, sample_json_report):
        """top_n_detail=1 only shows 1 theme per direction."""
        md = generate_markdown_report(sample_json_report, top_n_detail=1)
        assert "## 2. Leading Themes (Top 1)" in md
        # Only the top bullish theme detail section should appear
        # AI / Semiconductors (heat 85) should appear, Energy Transition (heat 63) should not
        assert "### AI / Semiconductors" in md
        assert "### Energy Transition" not in md


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


# --- Tests for _fmt_pct ---


class TestFmtPct:
    """_fmt_pct formats percent values directly (no *100 conversion)."""

    def test_positive_value(self):
        assert _fmt_pct(5.0) == "+5.0%"

    def test_negative_value(self):
        assert _fmt_pct(-3.2) == "-3.2%"

    def test_zero(self):
        assert _fmt_pct(0.0) == "+0.0%"

    def test_none_returns_na(self):
        assert _fmt_pct(None) == "N/A"

    def test_large_value(self):
        assert _fmt_pct(25.7) == "+25.7%"

    def test_small_negative(self):
        assert _fmt_pct(-0.5) == "-0.5%"


# --- Tests for Industry Rankings key usage ---


class TestIndustryRankingsKey:
    """Verify industry rankings use momentum_score, not composite_score."""

    def test_top_industries_show_momentum_score(self, sample_json_report):
        md = generate_markdown_report(sample_json_report)
        # momentum_score=0.89 should appear, not composite_score
        assert "0.89" in md

    def test_bottom_industries_show_momentum_score(self, sample_json_report):
        md = generate_markdown_report(sample_json_report)
        assert "-0.65" in md

    def test_industry_perf_not_multiplied(self, sample_json_report):
        """Perf values should appear as-is (already in percent)."""
        md = generate_markdown_report(sample_json_report)
        # 5.0% should appear, not 500.0%
        assert "+5.0%" in md
        assert "500.0%" not in md


# --- Tests for _format_stock_list ---


class TestFormatStockList:
    def test_no_details_uses_tickers(self):
        """Without stock_details, plain tickers are shown."""
        theme = {"representative_stocks": ["NVDA", "AMD", "AVGO"]}
        assert _format_stock_list(theme) == "NVDA, AMD, AVGO"

    def test_empty_stocks_returns_na(self):
        theme = {"representative_stocks": []}
        assert _format_stock_list(theme) == "N/A"

    def test_finviz_public_labels(self):
        """stock_details with finviz_public source shows [Fp] labels."""
        theme = {
            "representative_stocks": ["NEM", "GOLD"],
            "stock_details": [
                {"symbol": "NEM", "source": "finviz_public"},
                {"symbol": "GOLD", "source": "finviz_public"},
            ],
        }
        result = _format_stock_list(theme)
        assert "NEM[Fp]" in result
        assert "GOLD[Fp]" in result

    def test_finviz_elite_labels(self):
        theme = {
            "representative_stocks": ["NVDA"],
            "stock_details": [
                {"symbol": "NVDA", "source": "finviz_elite"},
            ],
        }
        assert "NVDA[Fe]" in _format_stock_list(theme)

    def test_etf_holdings_labels(self):
        theme = {
            "representative_stocks": ["AAPL"],
            "stock_details": [
                {"symbol": "AAPL", "source": "etf_holdings"},
            ],
        }
        assert "AAPL[E]" in _format_stock_list(theme)

    def test_static_labels(self):
        theme = {
            "representative_stocks": ["XOM"],
            "stock_details": [
                {"symbol": "XOM", "source": "static"},
            ],
        }
        assert "XOM[S]" in _format_stock_list(theme)

    def test_mixed_sources(self):
        theme = {
            "representative_stocks": ["NVDA", "AAPL", "XOM"],
            "stock_details": [
                {"symbol": "NVDA", "source": "finviz_public"},
                {"symbol": "AAPL", "source": "etf_holdings"},
                {"symbol": "XOM", "source": "static"},
            ],
        }
        result = _format_stock_list(theme)
        assert "NVDA[Fp]" in result
        assert "AAPL[E]" in result
        assert "XOM[S]" in result

    def test_unknown_source_shows_question_mark(self):
        theme = {
            "representative_stocks": ["X"],
            "stock_details": [
                {"symbol": "X", "source": "unknown_source"},
            ],
        }
        assert "X[?]" in _format_stock_list(theme)


class TestMarkdownWithStockDetails:
    def test_markdown_shows_source_labels(self):
        """Markdown report includes source labels when stock_details present."""
        themes = [
            {
                "name": "Gold Theme",
                "direction": "bullish",
                "heat": 70.0,
                "maturity": 40.0,
                "stage": "growth",
                "confidence": "Medium",
                "industries": ["Gold"],
                "heat_breakdown": {},
                "maturity_breakdown": {},
                "representative_stocks": ["NEM", "GOLD"],
                "stock_details": [
                    {"symbol": "NEM", "source": "finviz_public"},
                    {"symbol": "GOLD", "source": "finviz_public"},
                ],
                "proxy_etfs": ["GDX"],
            },
        ]
        metadata = {"generated_at": "2026-02-16 10:00:00", "data_sources": {}}
        report = generate_json_report(themes, {"top": [], "bottom": []}, {}, metadata)
        md = generate_markdown_report(report)
        assert "NEM[Fp]" in md
        assert "GOLD[Fp]" in md

    def test_markdown_no_details_plain_tickers(self):
        """Without stock_details, plain tickers are shown in markdown."""
        themes = [
            {
                "name": "Test Theme",
                "direction": "bullish",
                "heat": 60.0,
                "maturity": 30.0,
                "stage": "early",
                "confidence": "Low",
                "industries": ["Tech"],
                "heat_breakdown": {},
                "maturity_breakdown": {},
                "representative_stocks": ["AAPL", "MSFT"],
                "proxy_etfs": [],
            },
        ]
        metadata = {"generated_at": "2026-02-16 10:00:00", "data_sources": {}}
        report = generate_json_report(themes, {"top": [], "bottom": []}, {}, metadata)
        md = generate_markdown_report(report)
        assert "AAPL, MSFT" in md
        assert "[Fp]" not in md
        assert "[S]" not in md


# --- Tests for theme origin display ---


class TestOriginLabel:
    def test_seed_label(self):
        assert _origin_label("seed") == "Seed"

    def test_vertical_label(self):
        assert _origin_label("vertical") == "Vertical"

    def test_discovered_label(self):
        assert _origin_label("discovered") == "*NEW*"

    def test_none_defaults_to_seed(self):
        assert _origin_label(None) == "Seed"

    def test_unknown_defaults_to_seed(self):
        assert _origin_label("unknown") == "Seed"


class TestOriginInDashboard:
    def test_dashboard_shows_origin_column(self):
        themes = [
            {
                "name": "Seed Theme",
                "direction": "bullish",
                "heat": 70.0,
                "maturity": 40.0,
                "stage": "growth",
                "confidence": "Medium",
                "industries": ["Tech"],
                "heat_breakdown": {},
                "maturity_breakdown": {},
                "representative_stocks": ["AAPL"],
                "proxy_etfs": [],
                "theme_origin": "seed",
            },
            {
                "name": "New Theme",
                "direction": "bullish",
                "heat": 60.0,
                "maturity": 30.0,
                "stage": "early",
                "confidence": "Low",
                "industries": ["Mining"],
                "heat_breakdown": {},
                "maturity_breakdown": {},
                "representative_stocks": ["NEM"],
                "proxy_etfs": [],
                "theme_origin": "discovered",
                "name_confidence": "medium",
            },
        ]
        metadata = {"generated_at": "2026-02-16", "data_sources": {}}
        report = generate_json_report(themes, {"top": [], "bottom": []}, {}, metadata)
        md = generate_markdown_report(report)
        assert "| Origin |" in md
        assert "| Seed |" in md
        assert "| *NEW* |" in md

    def test_discovered_detail_shows_origin_line(self):
        themes = [
            {
                "name": "Discovered Theme",
                "direction": "bullish",
                "heat": 65.0,
                "maturity": 35.0,
                "stage": "early",
                "confidence": "Low",
                "industries": ["X"],
                "heat_breakdown": {},
                "maturity_breakdown": {},
                "representative_stocks": ["XYZ"],
                "proxy_etfs": [],
                "theme_origin": "discovered",
                "name_confidence": "medium",
            },
        ]
        metadata = {"generated_at": "2026-02-16", "data_sources": {}}
        report = generate_json_report(themes, {"top": [], "bottom": []}, {}, metadata)
        md = generate_markdown_report(report)
        assert "**Origin:** Discovered (name confidence: medium)" in md

    def test_seed_detail_no_origin_line(self):
        themes = [
            {
                "name": "Seed Theme",
                "direction": "bullish",
                "heat": 70.0,
                "maturity": 40.0,
                "stage": "growth",
                "confidence": "Medium",
                "industries": ["Tech"],
                "heat_breakdown": {},
                "maturity_breakdown": {},
                "representative_stocks": ["AAPL"],
                "proxy_etfs": [],
                "theme_origin": "seed",
            },
        ]
        metadata = {"generated_at": "2026-02-16", "data_sources": {}}
        report = generate_json_report(themes, {"top": [], "bottom": []}, {}, metadata)
        md = generate_markdown_report(report)
        assert "**Origin:**" not in md
