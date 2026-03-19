"""Tests for generate_dashboard.py pure functions."""

from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

# Add parent to path so we can import the module
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from generate_dashboard import _safe_get, generate_markdown


class TestSafeGet(unittest.TestCase):
    def test_single_key(self):
        assert _safe_get({"a": 1}, "a") == 1

    def test_nested_keys(self):
        data = {"composite": {"score": 42, "zone": "Healthy"}}
        assert _safe_get(data, "composite", "score") == 42
        assert _safe_get(data, "composite", "zone") == "Healthy"

    def test_missing_key_returns_default(self):
        assert _safe_get({"a": 1}, "b") == "N/A"
        assert _safe_get({"a": 1}, "b", default=0) == 0

    def test_missing_nested_key(self):
        assert _safe_get({"a": {"b": 1}}, "a", "c") == "N/A"

    def test_none_data(self):
        assert _safe_get(None, "a") == "N/A"

    def test_non_dict_intermediate(self):
        assert _safe_get({"a": "string"}, "a", "b") == "N/A"

    def test_empty_dict(self):
        assert _safe_get({}, "a") == "N/A"


class TestGenerateMarkdown(unittest.TestCase):
    def _make_results(self, **overrides):
        """Build minimal skill results for testing."""
        base = {
            "FTD Detector": {"data": None},
            "Uptrend Analyzer": {"data": None},
            "Market Breadth": {"data": None},
            "Theme Detector": {"data": None},
            "VCP Screener": {"data": None},
        }
        base.update(overrides)
        return base

    def test_all_skills_missing(self):
        md = generate_markdown(self._make_results(), date(2026, 3, 18))
        assert "Daily Market Dashboard" in md
        assert "2026-03-18" in md
        assert "N/A" in md

    def test_title_contains_date(self):
        md = generate_markdown(self._make_results(), date(2026, 1, 15))
        assert "2026-01-15" in md

    def test_ftd_data_rendered(self):
        results = self._make_results(
            **{
                "FTD Detector": {
                    "data": {
                        "market_state": {"combined_state": "RALLY_ATTEMPT"},
                        "quality_score": {
                            "total_score": 65,
                            "signal": "Pending FTD",
                            "guidance": "Watch for FTD confirmation.",
                            "exposure_range": "25-50%",
                        },
                    }
                },
            }
        )
        md = generate_markdown(results, date(2026, 3, 18))
        assert "RALLY_ATTEMPT" in md
        assert "65" in md
        assert "Pending FTD" in md

    def test_breadth_data_rendered(self):
        results = self._make_results(
            **{
                "Market Breadth": {
                    "data": {
                        "composite": {"composite_score": 72.5, "zone": "Healthy"},
                    }
                },
            }
        )
        md = generate_markdown(results, date(2026, 3, 18))
        assert "72.5" in md
        assert "Healthy" in md

    def test_theme_data_rendered(self):
        results = self._make_results(
            **{
                "Theme Detector": {
                    "data": {
                        "summary": {"bullish_count": 3, "bearish_count": 2},
                        "themes": {
                            "bullish": [
                                {"name": "AI Chips", "stage": "Accelerating", "heat": 85.0},
                                {"name": "Oil", "stage": "Exhausting", "heat": 60.0},
                            ],
                            "bearish": [],
                        },
                    }
                },
            }
        )
        md = generate_markdown(results, date(2026, 3, 18))
        assert "3 bullish" in md
        assert "2 bearish" in md
        assert "AI Chips" in md
        assert "Accelerating" in md
        assert "Heat 85" in md

    def test_vcp_data_rendered(self):
        results = self._make_results(
            **{
                "VCP Screener": {
                    "data": {
                        "results": [
                            {
                                "symbol": "AAPL",
                                "composite_score": 78.5,
                                "rating": "Strong VCP",
                                "distance_from_pivot_pct": -1.2,
                            },
                        ],
                    }
                },
            }
        )
        md = generate_markdown(results, date(2026, 3, 18))
        assert "AAPL" in md
        assert "78.5" in md
        assert "Strong VCP" in md
        assert "-1.2%" in md

    def test_japanese_output(self):
        md = generate_markdown(self._make_results(), date(2026, 3, 18), lang="ja")
        assert "デイリーマーケットダッシュボード" in md
        assert "シグナル一覧" in md

    def test_note_section_present(self):
        md = generate_markdown(self._make_results(), date(2026, 3, 18))
        assert "Market Top Detector" in md
        assert "/economic-calendar-fetcher" in md


if __name__ == "__main__":
    unittest.main()
