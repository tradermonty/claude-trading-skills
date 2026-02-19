"""Shared fixtures for Druckenmiller Strategy Synthesizer tests."""

import os
import sys
import json
import pytest
from datetime import datetime, timedelta


FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")

# Add parent dir (scripts/) to path so tests can import modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def make_report(prefix: str, data: dict, reports_dir: str,
                age_hours: int = 0) -> str:
    """Write a JSON report file with a given age offset.

    Sets both the filename timestamp and the file mtime so that
    find_latest_report's age check works correctly.
    """
    ts = datetime.now() - timedelta(hours=age_hours)
    filename = f"{prefix}{ts.strftime('%Y-%m-%d_%H%M%S')}.json"
    path = os.path.join(reports_dir, filename)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    # Set file mtime to match the age offset
    mtime = ts.timestamp()
    os.utime(path, (mtime, mtime))
    return path


@pytest.fixture
def make_report_fn():
    """Expose make_report helper as a fixture."""
    return make_report


@pytest.fixture
def tmp_reports(tmp_path):
    """Return a temporary reports directory path."""
    d = tmp_path / "reports"
    d.mkdir()
    return str(d)


@pytest.fixture
def sample_breadth():
    """Minimal market_breadth report data."""
    return {
        "composite": {
            "composite_score": 62.8,
            "zone": "Healthy",
            "zone_color": "blue",
            "exposure_guidance": "75-90%",
        },
    }


@pytest.fixture
def sample_uptrend():
    """Minimal uptrend_analysis report data."""
    return {
        "composite": {
            "composite_score": 66.0,
            "zone": "Bull",
            "zone_color": "light_green",
            "exposure_guidance": "Normal Exposure, Lower End (80-90%)",
        },
    }


@pytest.fixture
def sample_market_top():
    """Minimal market_top report data."""
    return {
        "composite": {
            "composite_score": 59.2,
            "zone": "Orange (Elevated Risk)",
            "zone_color": "orange",
            "risk_budget": "60-75%",
        },
    }


@pytest.fixture
def sample_macro_regime():
    """Minimal macro_regime report data."""
    return {
        "composite": {
            "composite_score": 49.0,
            "zone": "Transition Zone (Preparing)",
            "zone_color": "orange",
        },
        "regime": {
            "current_regime": "broadening",
            "regime_label": "Broadening",
            "confidence": "medium",
            "transition_probability": {
                "level": "moderate",
                "probability_range": "30-50%",
            },
        },
    }


@pytest.fixture
def sample_ftd():
    """Minimal ftd_detector report data."""
    return {
        "market_state": {
            "combined_state": "FTD_CONFIRMED",
            "dual_confirmation": True,
            "ftd_index": "Both",
        },
        "quality_score": {
            "total_score": 85,
            "signal": "Strong FTD",
            "exposure_range": "75-100%",
        },
        "post_ftd_distribution": {
            "distribution_count": 0,
            "days_monitored": 3,
        },
    }


@pytest.fixture
def sample_vcp():
    """Minimal vcp_screener report data."""
    return {
        "metadata": {
            "funnel": {
                "universe": 503,
                "trend_template_passed": 95,
                "vcp_candidates": 95,
            },
        },
        "results": [
            {"symbol": "DG", "composite_score": 81.0, "rating": "Strong VCP",
             "valid_vcp": True},
            {"symbol": "PLTR", "composite_score": 75.0, "rating": "Strong VCP",
             "valid_vcp": True},
            {"symbol": "AXON", "composite_score": 70.0, "rating": "Good VCP",
             "valid_vcp": True},
            {"symbol": "META", "composite_score": 55.0, "rating": "Developing",
             "valid_vcp": True},
        ],
    }


@pytest.fixture
def sample_theme():
    """Minimal theme_detector report data."""
    return {
        "summary": {
            "total_themes": 10,
            "bullish_count": 8,
            "bearish_count": 2,
        },
        "themes": {
            "all": [
                {"name": "AI & Semiconductors", "direction": "bullish",
                 "heat": 92.0, "stage": "Mid",
                 "confidence": "High"},
                {"name": "Oil & Gas", "direction": "bullish",
                 "heat": 85.0, "stage": "Exhausting",
                 "confidence": "Medium"},
                {"name": "Biotech", "direction": "bullish",
                 "heat": 60.0, "stage": "Early",
                 "confidence": "Low"},
            ],
        },
    }


@pytest.fixture
def sample_canslim():
    """Minimal canslim_screener report data."""
    return {
        "metadata": {
            "market_condition": {
                "trend": "strong_uptrend",
                "M_score": 100,
            },
            "candidates_analyzed": 35,
        },
        "results": [
            {"symbol": "NVDA", "composite_score": 97.2,
             "rating": "Exceptional+", "m_component": {"score": 100, "trend": "strong_uptrend"}},
            {"symbol": "PLTR", "composite_score": 82.0,
             "rating": "Exceptional", "m_component": {"score": 100, "trend": "strong_uptrend"}},
            {"symbol": "CRWD", "composite_score": 71.0,
             "rating": "Strong", "m_component": {"score": 80, "trend": "uptrend"}},
        ],
        "summary": {
            "total_stocks": 35,
            "exceptional": 3,
            "strong": 5,
        },
    }


@pytest.fixture
def all_required_reports(tmp_reports, sample_breadth, sample_uptrend,
                         sample_market_top, sample_macro_regime, sample_ftd):
    """Create all 5 required reports in tmp dir and return the dir."""
    make_report("market_breadth_", sample_breadth, tmp_reports)
    make_report("uptrend_analysis_", sample_uptrend, tmp_reports)
    make_report("market_top_", sample_market_top, tmp_reports)
    make_report("macro_regime_", sample_macro_regime, tmp_reports)
    make_report("ftd_detector_", sample_ftd, tmp_reports)
    return tmp_reports


@pytest.fixture
def full_reports(all_required_reports, sample_vcp, sample_theme, sample_canslim):
    """Create all 8 reports (5 required + 3 optional) and return the dir."""
    make_report("vcp_screener_", sample_vcp, all_required_reports)
    make_report("theme_detector_", sample_theme, all_required_reports)
    make_report("canslim_screener_", sample_canslim, all_required_reports)
    return all_required_reports
