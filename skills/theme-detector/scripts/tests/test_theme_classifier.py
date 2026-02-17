#!/usr/bin/env python3
"""
Tests for theme_classifier module.

Covers cross-sector theme matching, vertical (single-sector) theme detection,
sector weight calculation, and edge cases.
"""

from calculators.industry_ranker import rank_industries
from calculators.theme_classifier import (
    classify_themes,
    get_theme_sector_weights,
    get_matched_industry_names,
)

# ---------------------------------------------------------------------------
# Sample themes_config for testing
# ---------------------------------------------------------------------------

SAMPLE_THEMES_CONFIG = {
    "cross_sector": [
        {
            "theme_name": "AI & Automation",
            "matching_keywords": ["Semiconductor", "Software - Application", "IT Services"],
            "proxy_etfs": ["BOTZ", "ROBO"],
            "static_stocks": ["NVDA", "MSFT"],
        },
        {
            "theme_name": "Green Energy Transition",
            "matching_keywords": ["Solar", "Utilities - Renewable", "Auto Manufacturers"],
            "proxy_etfs": ["ICLN", "TAN"],
            "static_stocks": ["ENPH", "TSLA"],
        },
        {
            "theme_name": "Infrastructure Boom",
            "matching_keywords": ["Building Materials", "Engineering & Construction", "Steel"],
            "proxy_etfs": ["PAVE", "IFRA"],
            "static_stocks": ["VMC", "NUE"],
        },
    ],
    "vertical_min_industries": 3,
    "cross_sector_min_matches": 2,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ranked_industry(name, weighted_return, momentum_score, direction, rank, sector=None):
    """Build a ranked industry dict (simulates output of rank_industries)."""
    entry = {
        "name": name,
        "perf_1w": 0.0,
        "perf_1m": 0.0,
        "perf_3m": 0.0,
        "perf_6m": 0.0,
        "weighted_return": weighted_return,
        "momentum_score": momentum_score,
        "direction": direction,
        "rank": rank,
    }
    if sector is not None:
        entry["sector"] = sector
    return entry


# ---------------------------------------------------------------------------
# Cross-sector theme matching
# ---------------------------------------------------------------------------


class TestCrossSectorThemes:
    """Test cross-sector theme detection (min 2 matching industries)."""

    def test_ai_theme_detected_with_two_matches(self):
        """Two matching industries from AI theme -> theme detected."""
        ranked = [
            _make_ranked_industry("Semiconductor", 15.0, 82.0, "bullish", 1, "Technology"),
            _make_ranked_industry("Software - Application", 12.0, 75.0, "bullish", 2, "Technology"),
            _make_ranked_industry("Banks - Regional", 8.0, 65.0, "bullish", 3, "Financial Services"),
        ]
        themes = classify_themes(ranked, SAMPLE_THEMES_CONFIG)
        theme_names = [t["theme_name"] for t in themes]
        assert "AI & Automation" in theme_names

    def test_ai_theme_not_detected_with_one_match(self):
        """Only one matching industry -> theme NOT detected."""
        ranked = [
            _make_ranked_industry("Semiconductor", 15.0, 82.0, "bullish", 1, "Technology"),
            _make_ranked_industry("Banks - Regional", 8.0, 65.0, "bullish", 2, "Financial Services"),
            _make_ranked_industry("Oil & Gas E&P", 5.0, 55.0, "bullish", 3, "Energy"),
        ]
        themes = classify_themes(ranked, SAMPLE_THEMES_CONFIG)
        theme_names = [t["theme_name"] for t in themes]
        assert "AI & Automation" not in theme_names

    def test_all_three_matches(self):
        """All three keywords match -> theme detected with all three matching."""
        ranked = [
            _make_ranked_industry("Semiconductor", 15.0, 82.0, "bullish", 1, "Technology"),
            _make_ranked_industry("Software - Application", 12.0, 75.0, "bullish", 2, "Technology"),
            _make_ranked_industry("IT Services", 10.0, 70.0, "bullish", 3, "Technology"),
        ]
        themes = classify_themes(ranked, SAMPLE_THEMES_CONFIG)
        ai_theme = [t for t in themes if t["theme_name"] == "AI & Automation"][0]
        assert len(ai_theme["matching_industries"]) == 3

    def test_theme_direction_bullish(self):
        """Theme direction is bullish when matching industries are bullish."""
        ranked = [
            _make_ranked_industry("Semiconductor", 15.0, 82.0, "bullish", 1, "Technology"),
            _make_ranked_industry("Software - Application", 12.0, 75.0, "bullish", 2, "Technology"),
        ]
        themes = classify_themes(ranked, SAMPLE_THEMES_CONFIG)
        ai_theme = [t for t in themes if t["theme_name"] == "AI & Automation"][0]
        assert ai_theme["direction"] == "bullish"

    def test_theme_direction_bearish(self):
        """Theme direction is bearish when matching industries are bearish."""
        ranked = [
            _make_ranked_industry("Semiconductor", -15.0, 82.0, "bearish", 1, "Technology"),
            _make_ranked_industry("Software - Application", -12.0, 75.0, "bearish", 2, "Technology"),
        ]
        themes = classify_themes(ranked, SAMPLE_THEMES_CONFIG)
        ai_theme = [t for t in themes if t["theme_name"] == "AI & Automation"][0]
        assert ai_theme["direction"] == "bearish"

    def test_theme_direction_mixed(self):
        """Mixed directions -> majority determines theme direction."""
        ranked = [
            _make_ranked_industry("Semiconductor", 15.0, 82.0, "bullish", 1, "Technology"),
            _make_ranked_industry("Software - Application", -5.0, 50.0, "bearish", 5, "Technology"),
            _make_ranked_industry("IT Services", 8.0, 65.0, "bullish", 3, "Technology"),
        ]
        themes = classify_themes(ranked, SAMPLE_THEMES_CONFIG)
        ai_theme = [t for t in themes if t["theme_name"] == "AI & Automation"][0]
        # 2 bullish vs 1 bearish -> bullish
        assert ai_theme["direction"] == "bullish"

    def test_proxy_etfs_and_static_stocks_included(self):
        """Theme result includes proxy_etfs and static_stocks from config."""
        ranked = [
            _make_ranked_industry("Semiconductor", 15.0, 82.0, "bullish", 1, "Technology"),
            _make_ranked_industry("Software - Application", 12.0, 75.0, "bullish", 2, "Technology"),
        ]
        themes = classify_themes(ranked, SAMPLE_THEMES_CONFIG)
        ai_theme = [t for t in themes if t["theme_name"] == "AI & Automation"][0]
        assert ai_theme["proxy_etfs"] == ["BOTZ", "ROBO"]
        assert ai_theme["static_stocks"] == ["NVDA", "MSFT"]

    def test_multiple_themes_detected(self):
        """Multiple themes can be detected simultaneously."""
        ranked = [
            _make_ranked_industry("Semiconductor", 15.0, 82.0, "bullish", 1, "Technology"),
            _make_ranked_industry("Software - Application", 12.0, 75.0, "bullish", 2, "Technology"),
            _make_ranked_industry("Solar", 18.0, 85.0, "bullish", 3, "Energy"),
            _make_ranked_industry("Auto Manufacturers", 10.0, 70.0, "bullish", 4, "Consumer Cyclical"),
        ]
        themes = classify_themes(ranked, SAMPLE_THEMES_CONFIG)
        theme_names = [t["theme_name"] for t in themes]
        assert "AI & Automation" in theme_names
        assert "Green Energy Transition" in theme_names


# ---------------------------------------------------------------------------
# Vertical (single-sector) theme detection
# ---------------------------------------------------------------------------


class TestVerticalThemes:
    """Test vertical theme detection (min 3 same-sector industries in top/bottom)."""

    def test_vertical_theme_detected_with_three_same_sector(self):
        """3+ industries from same sector in top ranks -> vertical theme detected."""
        ranked = [
            _make_ranked_industry("Semiconductor", 20.0, 90.0, "bullish", 1, "Technology"),
            _make_ranked_industry("Software - Application", 18.0, 85.0, "bullish", 2, "Technology"),
            _make_ranked_industry("IT Services", 15.0, 82.0, "bullish", 3, "Technology"),
            _make_ranked_industry("Banks - Regional", 12.0, 75.0, "bullish", 4, "Financial Services"),
            _make_ranked_industry("Oil & Gas E&P", 10.0, 70.0, "bullish", 5, "Energy"),
        ]
        themes = classify_themes(ranked, SAMPLE_THEMES_CONFIG)
        vertical_names = [t["theme_name"] for t in themes if "Sector" in t["theme_name"]]
        assert any("Technology" in n for n in vertical_names)

    def test_vertical_theme_not_detected_with_two_same_sector(self):
        """Only 2 same-sector industries -> no vertical theme."""
        ranked = [
            _make_ranked_industry("Semiconductor", 20.0, 90.0, "bullish", 1, "Technology"),
            _make_ranked_industry("Software - Application", 18.0, 85.0, "bullish", 2, "Technology"),
            _make_ranked_industry("Banks - Regional", 12.0, 75.0, "bullish", 3, "Financial Services"),
            _make_ranked_industry("Oil & Gas E&P", 10.0, 70.0, "bullish", 4, "Energy"),
            _make_ranked_industry("Gold", 8.0, 65.0, "bullish", 5, "Basic Materials"),
        ]
        themes = classify_themes(ranked, SAMPLE_THEMES_CONFIG)
        vertical_names = [t["theme_name"] for t in themes if "Sector" in t["theme_name"]]
        assert not any("Technology" in n for n in vertical_names)

    def test_vertical_bearish_bottom_sector(self):
        """3+ same-sector industries at bottom -> bearish vertical theme."""
        ranked = [
            _make_ranked_industry("Banks - Regional", 12.0, 75.0, "bullish", 1, "Financial Services"),
            _make_ranked_industry("Oil & Gas E&P", 10.0, 70.0, "bullish", 2, "Energy"),
            # Bottom 3 are all Technology bearish
            _make_ranked_industry("IT Services", -10.0, 70.0, "bearish", 3, "Technology"),
            _make_ranked_industry("Software - Application", -15.0, 82.0, "bearish", 4, "Technology"),
            _make_ranked_industry("Semiconductor", -20.0, 90.0, "bearish", 5, "Technology"),
        ]
        themes = classify_themes(ranked, SAMPLE_THEMES_CONFIG)
        vertical_themes = [t for t in themes if "Sector" in t["theme_name"]]
        tech_vertical = [t for t in vertical_themes if "Technology" in t["theme_name"]]
        assert len(tech_vertical) >= 1
        assert tech_vertical[0]["direction"] == "bearish"

    def test_no_sector_field_skips_vertical(self):
        """Industries without sector field don't contribute to vertical themes."""
        ranked = [
            _make_ranked_industry("Semiconductor", 20.0, 90.0, "bullish", 1),
            _make_ranked_industry("Software - Application", 18.0, 85.0, "bullish", 2),
            _make_ranked_industry("IT Services", 15.0, 82.0, "bullish", 3),
        ]
        themes = classify_themes(ranked, SAMPLE_THEMES_CONFIG)
        vertical_themes = [t for t in themes if "Sector" in t["theme_name"]]
        assert len(vertical_themes) == 0


# ---------------------------------------------------------------------------
# get_theme_sector_weights
# ---------------------------------------------------------------------------


class TestGetThemeSectorWeights:
    """Test sector weight calculation for a theme."""

    def test_single_sector(self):
        """All matching industries from one sector -> 100% weight."""
        theme = {
            "matching_industries": [
                {"name": "Semiconductor", "sector": "Technology"},
                {"name": "Software - Application", "sector": "Technology"},
            ]
        }
        weights = get_theme_sector_weights(theme)
        assert weights == {"Technology": 1.0}

    def test_two_sectors_equal(self):
        """Two sectors with equal industries -> 50/50."""
        theme = {
            "matching_industries": [
                {"name": "Semiconductor", "sector": "Technology"},
                {"name": "Solar", "sector": "Energy"},
            ]
        }
        weights = get_theme_sector_weights(theme)
        assert abs(weights["Technology"] - 0.5) < 0.01
        assert abs(weights["Energy"] - 0.5) < 0.01

    def test_three_sectors_uneven(self):
        """3 industries: 2 Tech, 1 Energy -> Tech=0.67, Energy=0.33."""
        theme = {
            "matching_industries": [
                {"name": "Semiconductor", "sector": "Technology"},
                {"name": "Software - Application", "sector": "Technology"},
                {"name": "Solar", "sector": "Energy"},
            ]
        }
        weights = get_theme_sector_weights(theme)
        assert abs(weights["Technology"] - 2 / 3) < 0.01
        assert abs(weights["Energy"] - 1 / 3) < 0.01

    def test_empty_matching_industries(self):
        """No matching industries -> empty weights."""
        theme = {"matching_industries": []}
        weights = get_theme_sector_weights(theme)
        assert weights == {}

    def test_weights_sum_to_one(self):
        """Sector weights always sum to 1.0."""
        theme = {
            "matching_industries": [
                {"name": "A", "sector": "Tech"},
                {"name": "B", "sector": "Energy"},
                {"name": "C", "sector": "Tech"},
                {"name": "D", "sector": "Healthcare"},
            ]
        }
        weights = get_theme_sector_weights(theme)
        total = sum(weights.values())
        assert abs(total - 1.0) < 0.001

    def test_missing_sector_field_skipped(self):
        """Industries without sector field are excluded from weight calc."""
        theme = {
            "matching_industries": [
                {"name": "A", "sector": "Tech"},
                {"name": "B"},  # no sector
            ]
        }
        weights = get_theme_sector_weights(theme)
        assert weights == {"Tech": 1.0}


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestClassifyThemesEdgeCases:
    """Edge cases for classify_themes."""

    def test_empty_ranked_list(self):
        """Empty ranked list -> no themes detected."""
        themes = classify_themes([], SAMPLE_THEMES_CONFIG)
        assert themes == []

    def test_empty_themes_config(self):
        """Empty config -> no cross-sector themes but vertical may still detect."""
        ranked = [
            _make_ranked_industry("Semiconductor", 20.0, 90.0, "bullish", 1, "Technology"),
            _make_ranked_industry("Software - Application", 18.0, 85.0, "bullish", 2, "Technology"),
            _make_ranked_industry("IT Services", 15.0, 82.0, "bullish", 3, "Technology"),
        ]
        config = {"cross_sector": [], "vertical_min_industries": 3, "cross_sector_min_matches": 2}
        themes = classify_themes(ranked, config)
        # Only vertical themes possible
        theme_names = [t["theme_name"] for t in themes]
        assert any("Technology" in n for n in theme_names)

    def test_theme_result_has_sector_weights(self):
        """Each theme result includes sector_weights dict."""
        ranked = [
            _make_ranked_industry("Semiconductor", 15.0, 82.0, "bullish", 1, "Technology"),
            _make_ranked_industry("Software - Application", 12.0, 75.0, "bullish", 2, "Technology"),
        ]
        themes = classify_themes(ranked, SAMPLE_THEMES_CONFIG)
        ai_theme = [t for t in themes if t["theme_name"] == "AI & Automation"][0]
        assert "sector_weights" in ai_theme
        assert isinstance(ai_theme["sector_weights"], dict)

    def test_integration_with_rank_industries(self):
        """Test full pipeline: raw industries -> ranked -> classified."""
        raw_industries = [
            {"name": "Semiconductor", "perf_1w": 5, "perf_1m": 10, "perf_3m": 20, "perf_6m": 25, "sector": "Technology"},
            {"name": "Software - Application", "perf_1w": 4, "perf_1m": 8, "perf_3m": 15, "perf_6m": 20, "sector": "Technology"},
            {"name": "Banks - Regional", "perf_1w": 2, "perf_1m": 5, "perf_3m": 8, "perf_6m": 10, "sector": "Financial Services"},
        ]
        ranked = rank_industries(raw_industries)
        themes = classify_themes(ranked, SAMPLE_THEMES_CONFIG)
        theme_names = [t["theme_name"] for t in themes]
        assert "AI & Automation" in theme_names


# ---------------------------------------------------------------------------
# top_n filtering
# ---------------------------------------------------------------------------


class TestTopNFiltering:
    """Test that classify_themes only considers top/bottom N industries."""

    def test_middle_industries_excluded_with_small_top_n(self):
        """With 100 industries and top_n=5, middle industries are excluded."""
        # Build 100 industries: top 5 include AI keywords, bottom 5 include Green keywords
        # Middle 90 include Infrastructure keywords that should NOT match
        ranked = []

        # Top 5 (highest momentum)
        ranked.append(
            _make_ranked_industry("Semiconductor", 20.0, 95.0, "bullish", 1, "Technology"))
        ranked.append(
            _make_ranked_industry("Software - Application", 18.0, 90.0, "bullish", 2, "Technology"))
        ranked.append(
            _make_ranked_industry("IT Services", 16.0, 88.0, "bullish", 3, "Technology"))
        ranked.append(
            _make_ranked_industry("Banks - Diversified", 15.0, 85.0, "bullish", 4, "Financial"))
        ranked.append(
            _make_ranked_industry("Gold", 14.0, 82.0, "bullish", 5, "Basic Materials"))

        # Middle 90: include Building Materials and Steel (Infrastructure keywords)
        for i in range(6, 96):
            if i == 50:
                ranked.append(
                    _make_ranked_industry("Building Materials", 0.0, 50.0, "bullish", i, "Industrials"))
            elif i == 51:
                ranked.append(
                    _make_ranked_industry("Steel", -0.1, 49.0, "bearish", i, "Basic Materials"))
            elif i == 52:
                ranked.append(
                    _make_ranked_industry("Engineering & Construction", 0.1, 50.5, "bullish", i, "Industrials"))
            else:
                ranked.append(
                    _make_ranked_industry(f"Industry_{i}", 10.0 - i * 0.2, 80.0 - i * 0.3, "bullish", i, "Other"))

        # Bottom 5 (lowest momentum)
        ranked.append(
            _make_ranked_industry("Solar", -18.0, 10.0, "bearish", 96, "Energy"))
        ranked.append(
            _make_ranked_industry("Auto Manufacturers", -19.0, 8.0, "bearish", 97, "Consumer Cyclical"))
        ranked.append(
            _make_ranked_industry("Utilities - Renewable", -20.0, 5.0, "bearish", 98, "Utilities"))
        ranked.append(
            _make_ranked_industry("Retail_A", -21.0, 4.0, "bearish", 99, "Consumer Cyclical"))
        ranked.append(
            _make_ranked_industry("Retail_B", -22.0, 3.0, "bearish", 100, "Consumer Cyclical"))

        themes = classify_themes(ranked, SAMPLE_THEMES_CONFIG, top_n=5)
        theme_names = [t["theme_name"] for t in themes]

        # AI keywords (Semiconductor, Software - App) are in top 5 -> AI detected
        assert "AI & Automation" in theme_names

        # Green keywords (Solar, Auto Manufacturers) are in bottom 5 -> Green detected
        assert "Green Energy Transition" in theme_names

        # Infrastructure keywords (Building Materials, Steel, E&C) are in middle -> NOT detected
        assert "Infrastructure Boom" not in theme_names

    def test_top_n_default_30(self):
        """Default top_n=30 works for small datasets (< 30 items)."""
        ranked = [
            _make_ranked_industry("Semiconductor", 15.0, 82.0, "bullish", 1, "Technology"),
            _make_ranked_industry("Software - Application", 12.0, 75.0, "bullish", 2, "Technology"),
        ]
        # Default top_n=30, with only 2 items, all should be considered
        themes = classify_themes(ranked, SAMPLE_THEMES_CONFIG)
        theme_names = [t["theme_name"] for t in themes]
        assert "AI & Automation" in theme_names

    def test_vertical_theme_only_in_top_bottom(self):
        """Vertical themes only detected from top/bottom N, not middle."""
        ranked = []
        # Top 3: mixed sectors
        ranked.append(
            _make_ranked_industry("Gold", 20.0, 95.0, "bullish", 1, "Basic Materials"))
        ranked.append(
            _make_ranked_industry("Banks - Regional", 18.0, 90.0, "bullish", 2, "Financial"))
        ranked.append(
            _make_ranked_industry("Solar", 16.0, 88.0, "bullish", 3, "Energy"))

        # Middle: 3 Technology industries (would trigger vertical if not filtered)
        for i, name in enumerate(["Semiconductor", "Software - Application", "IT Services"], 4):
            ranked.append(
                _make_ranked_industry(name, 5.0, 50.0, "bullish", i, "Technology"))

        # Bottom 3: mixed sectors
        ranked.append(
            _make_ranked_industry("Oil & Gas E&P", -15.0, 10.0, "bearish", 7, "Energy"))
        ranked.append(
            _make_ranked_industry("Retail_A", -18.0, 8.0, "bearish", 8, "Consumer Cyclical"))
        ranked.append(
            _make_ranked_industry("Retail_B", -20.0, 5.0, "bearish", 9, "Consumer Cyclical"))

        themes = classify_themes(ranked, SAMPLE_THEMES_CONFIG, top_n=3)
        vertical_names = [t["theme_name"] for t in themes if "Sector" in t["theme_name"]]
        # Technology industries are in middle -> no Technology vertical theme
        assert not any("Technology" in n for n in vertical_names)


# ---------------------------------------------------------------------------
# get_matched_industry_names
# ---------------------------------------------------------------------------


class TestGetMatchedIndustryNames:
    """Test extraction of matched industry names from classified themes."""

    def test_returns_matched_names(self):
        themes = [
            {
                "theme_name": "AI",
                "matching_industries": [
                    {"name": "Semiconductors"},
                    {"name": "Software - Application"},
                ],
            },
        ]
        names = get_matched_industry_names(themes)
        assert names == {"Semiconductors", "Software - Application"}

    def test_multiple_themes_combined(self):
        themes = [
            {"theme_name": "A", "matching_industries": [{"name": "X"}]},
            {"theme_name": "B", "matching_industries": [{"name": "Y"}, {"name": "Z"}]},
        ]
        names = get_matched_industry_names(themes)
        assert names == {"X", "Y", "Z"}

    def test_empty_themes_returns_empty_set(self):
        assert get_matched_industry_names([]) == set()

    def test_no_matching_industries_key(self):
        themes = [{"theme_name": "A"}]
        assert get_matched_industry_names(themes) == set()

    def test_deduplicates_across_themes(self):
        themes = [
            {"theme_name": "A", "matching_industries": [{"name": "X"}, {"name": "Y"}]},
            {"theme_name": "B", "matching_industries": [{"name": "Y"}, {"name": "Z"}]},
        ]
        names = get_matched_industry_names(themes)
        assert names == {"X", "Y", "Z"}


# ---------------------------------------------------------------------------
# theme_origin and name_confidence
# ---------------------------------------------------------------------------


class TestThemeOrigin:
    """Test that theme_origin and name_confidence are set correctly."""

    def test_cross_sector_has_seed_origin(self):
        ranked = [
            _make_ranked_industry("Semiconductor", 15.0, 82.0, "bullish", 1, "Technology"),
            _make_ranked_industry("Software - Application", 12.0, 75.0, "bullish", 2, "Technology"),
        ]
        themes = classify_themes(ranked, SAMPLE_THEMES_CONFIG)
        ai_theme = [t for t in themes if t["theme_name"] == "AI & Automation"][0]
        assert ai_theme["theme_origin"] == "seed"
        assert ai_theme["name_confidence"] == "high"

    def test_vertical_has_vertical_origin(self):
        ranked = [
            _make_ranked_industry("Semiconductor", 20.0, 90.0, "bullish", 1, "Technology"),
            _make_ranked_industry("Software - Application", 18.0, 85.0, "bullish", 2, "Technology"),
            _make_ranked_industry("IT Services", 15.0, 82.0, "bullish", 3, "Technology"),
        ]
        themes = classify_themes(ranked, SAMPLE_THEMES_CONFIG)
        vertical = [t for t in themes if "Sector" in t["theme_name"]]
        assert len(vertical) >= 1
        assert vertical[0]["theme_origin"] == "vertical"
        assert vertical[0]["name_confidence"] == "high"
