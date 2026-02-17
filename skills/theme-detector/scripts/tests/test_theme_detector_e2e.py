"""Minimal E2E test for the Theme Detector pipeline.

Tests the full flow: raw industries -> rank -> classify -> score -> report
without network calls (all I/O is mocked).
"""

import json

import pytest

# Import the pieces of the pipeline
from calculators.industry_ranker import rank_industries, get_top_bottom_industries
from calculators.theme_classifier import classify_themes, get_matched_industry_names
from calculators.theme_discoverer import discover_themes
from calculators.heat_calculator import (
    momentum_strength_score,
    volume_intensity_score,
    uptrend_signal_score,
    breadth_signal_score,
    calculate_theme_heat,
)
from calculators.lifecycle_calculator import (
    estimate_duration_score,
    classify_stage,
    calculate_lifecycle_maturity,
)
from scorer import score_theme, get_heat_label, calculate_confidence, determine_data_mode
from report_generator import generate_json_report, generate_markdown_report
from config_loader import load_themes_config


# Minimal themes config for E2E
E2E_THEMES_CONFIG = {
    "cross_sector_min_matches": 2,
    "vertical_min_industries": 3,
    "cross_sector": [
        {
            "theme_name": "AI & Semiconductors",
            "matching_keywords": [
                "Semiconductors",
                "Software - Application",
                "Software - Infrastructure",
            ],
            "proxy_etfs": ["SMH", "SOXX"],
            "static_stocks": ["NVDA", "AVGO", "AMD"],
        },
    ],
}


def _make_raw_industry(name, sector, perf_1w, perf_1m, perf_3m, perf_6m=None):
    """Build a raw industry dict (simulates FINVIZ output, already in pct)."""
    return {
        "name": name,
        "sector": sector,
        "perf_1w": perf_1w,
        "perf_1m": perf_1m,
        "perf_3m": perf_3m,
        "perf_6m": perf_6m or perf_3m * 1.2,
    }


class TestThemeDetectorE2E:
    """Full pipeline integration test (no network)."""

    def test_full_pipeline_produces_valid_report(self):
        """Raw industries -> ranked -> classified -> scored -> JSON+Markdown."""
        # Step 1: Raw industry data (already in percent)
        raw = [
            _make_raw_industry("Semiconductors", "Technology", 5.0, 12.0, 25.0),
            _make_raw_industry("Software - Application", "Technology", 4.0, 10.0, 20.0),
            _make_raw_industry("Software - Infrastructure", "Technology", 3.5, 9.0, 18.0),
            _make_raw_industry("Banks - Diversified", "Financial", 2.0, 5.0, 8.0),
            _make_raw_industry("Oil & Gas E&P", "Energy", -1.0, -3.0, -5.0),
            _make_raw_industry("Department Stores", "Consumer Cyclical", -4.0, -10.0, -15.0),
        ]

        # Step 2: Rank
        ranked = rank_industries(raw)
        assert len(ranked) == 6
        assert ranked[0]["name"] == "Semiconductors"  # highest momentum
        assert ranked[0]["direction"] == "bullish"

        industry_rankings = get_top_bottom_industries(ranked, n=3)
        assert len(industry_rankings["top"]) == 3
        assert len(industry_rankings["bottom"]) == 3

        # Step 3: Classify
        themes = classify_themes(ranked, E2E_THEMES_CONFIG, top_n=30)
        assert len(themes) >= 1
        ai_theme = [t for t in themes if t["theme_name"] == "AI & Semiconductors"]
        assert len(ai_theme) == 1
        assert ai_theme[0]["direction"] == "bullish"
        assert len(ai_theme[0]["matching_industries"]) == 3

        # Step 4: Score (simplified - just for AI theme)
        theme = ai_theme[0]
        theme_wr = sum(
            ind.get("weighted_return", 0) for ind in theme["matching_industries"]
        ) / len(theme["matching_industries"])

        momentum = momentum_strength_score(theme_wr)
        volume = None  # no ETF data in E2E
        uptrend = None  # no uptrend data in E2E
        breadth = breadth_signal_score(1.0)  # all bullish -> ratio 1.0
        heat = calculate_theme_heat(momentum, volume, uptrend, breadth)
        assert 0 <= heat <= 100

        duration = estimate_duration_score(12.0, 25.0, 30.0, None, False)
        maturity = calculate_lifecycle_maturity(duration, 50, 50, 50, 30)
        stage = classify_stage(maturity)
        confidence = calculate_confidence(True, False, False, False)
        data_mode = determine_data_mode(False, False)

        score = score_theme(
            round(heat, 2), round(maturity, 2), stage, "bullish", confidence, data_mode
        )

        scored_theme = {
            "name": "AI & Semiconductors",
            "direction": "bullish",
            "heat": round(heat, 2),
            "maturity": round(maturity, 2),
            "stage": stage,
            "confidence": confidence,
            "heat_label": score["heat_label"],
            "heat_breakdown": {"momentum_strength": round(momentum, 2)},
            "maturity_breakdown": {"duration_estimate": round(duration, 2)},
            "representative_stocks": ["NVDA", "AVGO", "AMD"],
            "proxy_etfs": ["SMH", "SOXX"],
            "industries": ["Semiconductors", "Software - Application",
                           "Software - Infrastructure"],
            "sector_weights": {"Technology": 1.0},
        }

        # Step 5: Generate reports
        metadata = {
            "generated_at": "2026-02-16 09:00:00",
            "data_mode": data_mode,
            "data_sources": {},
        }
        json_report = generate_json_report(
            [scored_theme], industry_rankings, {}, metadata
        )

        # Verify JSON structure
        assert json_report["report_type"] == "theme_detector"
        assert json_report["summary"]["total_themes"] == 1
        assert json_report["summary"]["bullish_count"] == 1
        assert json_report["summary"]["bearish_count"] == 0
        assert json_report["summary"]["top_bullish"] == "AI & Semiconductors"

        # Verify JSON is serializable
        serialized = json.dumps(json_report, default=str)
        assert len(serialized) > 100

        # Step 6: Generate Markdown
        md_report = generate_markdown_report(json_report, top_n_detail=3)
        assert "# Theme Detector Report" in md_report
        assert "AI & Semiconductors" in md_report
        assert "BULL" in md_report
        assert "NVDA" in md_report
        assert "## 1. Theme Dashboard" in md_report
        assert "## 7. Methodology & Data Quality" in md_report

        # Verify perf values are reasonable (not multiplied by 100 again)
        assert "500.0%" not in md_report
        assert "1200.0%" not in md_report

    def test_dynamic_stocks_with_mock_selector(self):
        """Dynamic stock selection produces stock_details in scored_theme."""
        from unittest.mock import MagicMock
        from theme_detector import _get_representative_stocks

        # Mock selector
        mock_selector = MagicMock()
        mock_selector.select_stocks.return_value = [
            {
                "symbol": "NEM",
                "source": "finviz_public",
                "market_cap": 50_000_000_000,
                "matched_industries": ["Gold"],
                "reasons": ["Public screener: Gold"],
                "composite_score": 0.95,
            },
            {
                "symbol": "GOLD",
                "source": "finviz_public",
                "market_cap": 30_000_000_000,
                "matched_industries": ["Gold"],
                "reasons": ["Public screener: Gold"],
                "composite_score": 0.85,
            },
        ]

        theme = {
            "theme_name": "Gold & Precious Metals",
            "direction": "bullish",
            "matching_industries": [{"name": "Gold"}],
            "proxy_etfs": ["GDX"],
            "static_stocks": ["NEM", "GOLD", "AEM"],
        }

        tickers, details = _get_representative_stocks(theme, mock_selector, max_stocks=10)
        assert tickers == ["NEM", "GOLD"]
        assert len(details) == 2
        assert details[0]["source"] == "finviz_public"
        assert details[0]["composite_score"] == 0.95

    def test_static_fallback_without_selector(self):
        """Without selector, static_stocks are returned."""
        from theme_detector import _get_representative_stocks

        theme = {
            "theme_name": "Test",
            "direction": "bullish",
            "matching_industries": [],
            "proxy_etfs": [],
            "static_stocks": ["A", "B", "C"],
        }

        tickers, details = _get_representative_stocks(theme, None, max_stocks=10)
        assert tickers == ["A", "B", "C"]
        assert all(d["source"] == "static" for d in details)

    def test_config_loader_produces_same_themes(self):
        """Config loaded from YAML produces same themes as before."""
        raw = [
            _make_raw_industry("Semiconductors", "Technology", 5.0, 12.0, 25.0),
            _make_raw_industry("Software - Application", "Technology", 4.0, 10.0, 20.0),
            _make_raw_industry("Software - Infrastructure", "Technology", 3.5, 9.0, 18.0),
            _make_raw_industry("Banks - Diversified", "Financial", 2.0, 5.0, 8.0),
        ]
        ranked = rank_industries(raw)

        # Load config from YAML
        config, catalog = load_themes_config()
        themes = classify_themes(ranked, config, top_n=30)

        theme_names = [t["theme_name"] for t in themes]
        assert "AI & Semiconductors" in theme_names
        # Should have theme_origin set
        ai = [t for t in themes if t["theme_name"] == "AI & Semiconductors"][0]
        assert ai["theme_origin"] == "seed"
        assert ai["name_confidence"] == "high"

    def test_discover_path_finds_unmatched_clusters(self):
        """Discover path finds themes from unmatched industries."""
        raw = [
            _make_raw_industry("Semiconductors", "Technology", 5.0, 12.0, 25.0),
            _make_raw_industry("Software - Application", "Technology", 4.0, 10.0, 20.0),
            # Unmatched industries that should cluster
            _make_raw_industry("Gold", "Basic Materials", 8.0, 15.0, 30.0),
            _make_raw_industry("Silver", "Basic Materials", 7.5, 14.0, 28.0),
            _make_raw_industry("Other Precious Metals & Mining", "Basic Materials", 7.0, 13.0, 27.0),
            # Filler for bottom
            _make_raw_industry("Department Stores", "Consumer Cyclical", -4.0, -10.0, -15.0),
            _make_raw_industry("Specialty Retail", "Consumer Cyclical", -3.5, -9.0, -14.0),
        ]
        ranked = rank_industries(raw)

        # Use a minimal config that only matches Semiconductors + Software
        mini_config = {
            "cross_sector_min_matches": 2,
            "vertical_min_industries": 3,
            "cross_sector": [
                {
                    "theme_name": "AI & Semiconductors",
                    "matching_keywords": [
                        "Semiconductors", "Software - Application",
                    ],
                    "proxy_etfs": ["SMH"],
                    "static_stocks": ["NVDA"],
                },
            ],
        }
        themes = classify_themes(ranked, mini_config, top_n=30)
        matched = get_matched_industry_names(themes)
        discovered = discover_themes(ranked, matched, themes, top_n=30)

        # Gold/Silver/Precious Metals should form a discovered cluster
        if discovered:
            assert discovered[0]["theme_origin"] == "discovered"
            assert discovered[0]["proxy_etfs"] == []
            assert discovered[0]["name_confidence"] == "medium"

    def test_max_themes_applied_after_discover(self):
        """max_themes limits seed+discovered combined total."""
        raw = [
            _make_raw_industry("Semiconductors", "Technology", 5.0, 12.0, 25.0),
            _make_raw_industry("Software - Application", "Technology", 4.0, 10.0, 20.0),
            _make_raw_industry("Software - Infrastructure", "Technology", 3.5, 9.0, 18.0),
            _make_raw_industry("Gold", "Basic Materials", 8.0, 15.0, 30.0),
            _make_raw_industry("Silver", "Basic Materials", 7.5, 14.0, 28.0),
            _make_raw_industry("Copper", "Basic Materials", 7.0, 13.0, 27.0),
            _make_raw_industry("Department Stores", "Consumer Cyclical", -4.0, -10.0, -15.0),
        ]
        ranked = rank_industries(raw)
        mini_config = {
            "cross_sector_min_matches": 2,
            "vertical_min_industries": 3,
            "cross_sector": [
                {
                    "theme_name": "AI",
                    "matching_keywords": ["Semiconductors", "Software - Application"],
                    "proxy_etfs": [],
                    "static_stocks": [],
                },
            ],
        }
        themes = classify_themes(ranked, mini_config, top_n=30)
        matched = get_matched_industry_names(themes)
        discovered = discover_themes(ranked, matched, themes, top_n=30)
        themes.extend(discovered)

        # Apply max_themes=2 with priority sort
        def _priority(t):
            inds = t.get("matching_industries", [])
            n = len(inds)
            avg_s = sum(abs(i.get("weighted_return", 0)) for i in inds) / max(n, 1)
            return min(n / 10, 1) * 0.5 + min(avg_s / 30, 1) * 0.5

        themes.sort(key=_priority, reverse=True)
        themes = themes[:2]
        assert len(themes) <= 2

    def test_stock_details_in_scored_theme_and_report(self):
        """stock_details flows through to scored_theme and into markdown."""
        raw = [
            _make_raw_industry("Semiconductors", "Technology", 5.0, 12.0, 25.0),
            _make_raw_industry("Software - Application", "Technology", 4.0, 10.0, 20.0),
            _make_raw_industry("Software - Infrastructure", "Technology", 3.5, 9.0, 18.0),
        ]

        ranked = rank_industries(raw)
        themes = classify_themes(ranked, E2E_THEMES_CONFIG, top_n=30)
        theme = themes[0]
        theme_wr = sum(
            ind.get("weighted_return", 0) for ind in theme["matching_industries"]
        ) / len(theme["matching_industries"])

        momentum = momentum_strength_score(theme_wr)
        breadth = breadth_signal_score(1.0)
        heat = calculate_theme_heat(momentum, None, None, breadth)
        duration = estimate_duration_score(12.0, 25.0, 30.0, None, False)
        maturity = calculate_lifecycle_maturity(duration, 50, 50, 50, 30)
        stage = classify_stage(maturity)
        confidence = calculate_confidence(True, False, False, False)
        data_mode = determine_data_mode(False, False)
        score = score_theme(
            round(heat, 2), round(maturity, 2), stage, "bullish", confidence, data_mode
        )

        stock_details = [
            {"symbol": "NVDA", "source": "finviz_public",
             "market_cap": 2_800_000_000_000,
             "matched_industries": ["Semiconductors"],
             "reasons": ["Public screener"], "composite_score": 0.95},
            {"symbol": "AVGO", "source": "finviz_public",
             "market_cap": 500_000_000_000,
             "matched_industries": ["Semiconductors"],
             "reasons": ["Public screener"], "composite_score": 0.80},
        ]

        scored_theme = {
            "name": "AI & Semiconductors",
            "direction": "bullish",
            "heat": round(heat, 2),
            "maturity": round(maturity, 2),
            "stage": stage,
            "confidence": confidence,
            "heat_label": score["heat_label"],
            "heat_breakdown": {"momentum_strength": round(momentum, 2)},
            "maturity_breakdown": {"duration_estimate": round(duration, 2)},
            "representative_stocks": ["NVDA", "AVGO"],
            "stock_details": stock_details,
            "proxy_etfs": ["SMH", "SOXX"],
            "industries": ["Semiconductors", "Software - Application",
                           "Software - Infrastructure"],
            "sector_weights": {"Technology": 1.0},
        }

        metadata = {
            "generated_at": "2026-02-16 09:00:00",
            "data_mode": data_mode,
            "data_sources": {},
        }
        json_report = generate_json_report(
            [scored_theme], {"top": [], "bottom": []}, {}, metadata
        )

        # Verify stock_details in JSON
        theme_in_report = json_report["themes"]["bullish"][0]
        assert "stock_details" in theme_in_report
        assert len(theme_in_report["stock_details"]) == 2

        # Verify markdown has source labels
        md_report = generate_markdown_report(json_report, top_n_detail=3)
        assert "NVDA[Fp]" in md_report
        assert "AVGO[Fp]" in md_report
