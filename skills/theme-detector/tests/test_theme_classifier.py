"""Tests for theme_classifier module."""

from calculators.theme_classifier import (
    classify_themes,
    get_theme_sector_weights,
    _majority_direction,
    enrich_vertical_themes,
    deduplicate_themes,
    SECTOR_REPRESENTATIVE_STOCKS,
)


def _make_ranked_industry(name, rank, weighted_return, direction, sector,
                          rank_direction=None, **kwargs):
    """Helper to create a ranked industry dict."""
    d = {
        "name": name,
        "rank": rank,
        "weighted_return": weighted_return,
        "direction": direction,
        "momentum_score": abs(weighted_return) * 2,
        "sector": sector,
        **kwargs,
    }
    if rank_direction is not None:
        d["rank_direction"] = rank_direction
    return d


class TestMajorityDirection:
    def test_uses_rank_direction_when_available(self):
        """_majority_direction should prefer rank_direction over direction."""
        industries = [
            {"direction": "bullish", "rank_direction": "bearish"},
            {"direction": "bullish", "rank_direction": "bearish"},
            {"direction": "bullish", "rank_direction": "bullish"},
        ]
        # 2 bearish rank_direction vs 1 bullish -> bearish
        assert _majority_direction(industries) == "bearish"

    def test_falls_back_to_direction(self):
        """Without rank_direction, should fall back to direction field."""
        industries = [
            {"direction": "bullish"},
            {"direction": "bullish"},
            {"direction": "bearish"},
        ]
        assert _majority_direction(industries) == "bullish"

    def test_all_bullish(self):
        industries = [
            {"rank_direction": "bullish"},
            {"rank_direction": "bullish"},
        ]
        assert _majority_direction(industries) == "bullish"

    def test_all_bearish(self):
        industries = [
            {"rank_direction": "bearish"},
            {"rank_direction": "bearish"},
        ]
        assert _majority_direction(industries) == "bearish"


class TestClassifyThemes:
    def _make_config(self):
        return {
            "cross_sector_min_matches": 2,
            "vertical_min_industries": 3,
            "cross_sector": [
                {
                    "theme_name": "Test Theme",
                    "matching_keywords": ["Ind A", "Ind B", "Ind C"],
                    "proxy_etfs": ["ETF1"],
                    "static_stocks": ["AAPL"],
                },
            ],
        }

    def test_cross_sector_bullish(self):
        ranked = [
            _make_ranked_industry("Ind A", 1, 10.0, "bullish", "Tech",
                                  rank_direction="bullish"),
            _make_ranked_industry("Ind B", 2, 8.0, "bullish", "Tech",
                                  rank_direction="bullish"),
            _make_ranked_industry("Ind C", 3, 5.0, "bullish", "Health",
                                  rank_direction="bullish"),
        ]
        config = self._make_config()
        themes = classify_themes(ranked, config, top_n=30)
        assert len(themes) >= 1
        test_theme = next(t for t in themes if t["theme_name"] == "Test Theme")
        assert test_theme["direction"] == "bullish"

    def test_bottom_vertical_theme_is_bearish(self):
        """Industries in bottom N with rank_direction=bearish should produce bearish vertical."""
        # 10 top industries (bullish) + 5 bottom Energy industries (bearish)
        ranked = []
        for i in range(10):
            ranked.append(_make_ranked_industry(
                f"Top {i}", i + 1, 10.0 - i, "bullish", "Technology",
                rank_direction="bullish",
            ))
        for i in range(5):
            ranked.append(_make_ranked_industry(
                f"Energy {i}", 11 + i, 2.0, "bullish", "Energy",
                rank_direction="bearish",
            ))

        config = {
            "cross_sector_min_matches": 2,
            "vertical_min_industries": 3,
            "cross_sector": [],
        }
        themes = classify_themes(ranked, config, top_n=10)

        # Should detect Energy Sector Concentration as bearish
        energy_themes = [t for t in themes if "Energy" in t["theme_name"]]
        assert len(energy_themes) >= 1
        assert energy_themes[0]["direction"] == "bearish"

    def test_cross_sector_bearish_with_rank_direction(self):
        """Cross-sector theme with rank_direction=bearish industries should be bearish."""
        ranked = [
            _make_ranked_industry("Ind A", 100, 3.0, "bullish", "Tech",
                                  rank_direction="bearish"),
            _make_ranked_industry("Ind B", 101, 2.0, "bullish", "Tech",
                                  rank_direction="bearish"),
            _make_ranked_industry("Ind C", 102, 1.0, "bullish", "Health",
                                  rank_direction="bearish"),
        ]
        config = self._make_config()
        themes = classify_themes(ranked, config, top_n=150)
        test_theme = next(t for t in themes if t["theme_name"] == "Test Theme")
        assert test_theme["direction"] == "bearish"


class TestEnrichVerticalThemes:
    def test_inherits_etf_from_overlapping_seed(self):
        """Vertical theme with >50% industry overlap should inherit seed ETFs/stocks."""
        seed_theme = {
            "theme_name": "Oil & Gas (Energy)",
            "direction": "bullish",
            "matching_industries": [
                {"name": "Oil & Gas E&P"}, {"name": "Oil & Gas Integrated"},
                {"name": "Oil & Gas Midstream"},
            ],
            "proxy_etfs": ["XLE", "XOP"],
            "static_stocks": ["XOM", "CVX"],
            "theme_origin": "seed",
        }
        vertical_theme = {
            "theme_name": "Energy Sector Concentration",
            "direction": "bullish",
            "matching_industries": [
                {"name": "Oil & Gas E&P"}, {"name": "Oil & Gas Integrated"},
                {"name": "Oil & Gas Drilling"},
            ],
            "proxy_etfs": [],
            "static_stocks": [],
            "theme_origin": "vertical",
        }
        themes = [seed_theme, vertical_theme]
        enrich_vertical_themes(themes)
        assert vertical_theme["proxy_etfs"] == ["XLE", "XOP"]
        assert vertical_theme["static_stocks"] == ["XOM", "CVX"]

    def test_sector_etf_fallback(self):
        """Vertical theme with no seed overlap should get sector ETF."""
        vertical_theme = {
            "theme_name": "Technology Sector Concentration",
            "direction": "bullish",
            "matching_industries": [
                {"name": "A", "sector": "Technology"},
                {"name": "B", "sector": "Technology"},
            ],
            "proxy_etfs": [],
            "static_stocks": [],
            "theme_origin": "vertical",
            "sector_weights": {"Technology": 1.0},
        }
        themes = [vertical_theme]
        enrich_vertical_themes(themes)
        assert "XLK" in vertical_theme["proxy_etfs"]

    def test_seed_theme_not_modified(self):
        """Seed themes should not be modified by enrich_vertical_themes."""
        seed_theme = {
            "theme_name": "Test Seed",
            "direction": "bullish",
            "matching_industries": [{"name": "A"}],
            "proxy_etfs": ["ETF1"],
            "static_stocks": ["AAPL"],
            "theme_origin": "seed",
        }
        enrich_vertical_themes([seed_theme])
        assert seed_theme["proxy_etfs"] == ["ETF1"]


class TestDeduplicateThemes:
    def test_removes_duplicate_vertical(self):
        """Vertical theme with same direction and >50% industry overlap should be removed."""
        seed_theme = {
            "theme_name": "Oil & Gas (Energy)",
            "direction": "bullish",
            "matching_industries": [
                {"name": "Oil & Gas E&P"}, {"name": "Oil & Gas Integrated"},
                {"name": "Oil & Gas Midstream"},
            ],
            "theme_origin": "seed",
        }
        vertical_theme = {
            "theme_name": "Energy Sector Concentration",
            "direction": "bullish",
            "matching_industries": [
                {"name": "Oil & Gas E&P"}, {"name": "Oil & Gas Integrated"},
                {"name": "Oil & Gas Drilling"},
            ],
            "theme_origin": "vertical",
        }
        themes = deduplicate_themes([seed_theme, vertical_theme])
        assert len(themes) == 1
        assert themes[0]["theme_origin"] == "seed"

    def test_keeps_different_direction(self):
        """Vertical with different direction should not be deduped."""
        seed_theme = {
            "theme_name": "Oil & Gas (Energy)",
            "direction": "bullish",
            "matching_industries": [
                {"name": "Oil & Gas E&P"}, {"name": "Oil & Gas Integrated"},
            ],
            "theme_origin": "seed",
        }
        vertical_theme = {
            "theme_name": "Energy Sector Concentration",
            "direction": "bearish",
            "matching_industries": [
                {"name": "Oil & Gas E&P"}, {"name": "Oil & Gas Integrated"},
            ],
            "theme_origin": "vertical",
        }
        themes = deduplicate_themes([seed_theme, vertical_theme])
        assert len(themes) == 2

    def test_keeps_low_overlap(self):
        """Vertical with <50% industry overlap should not be deduped."""
        seed_theme = {
            "theme_name": "Theme A",
            "direction": "bullish",
            "matching_industries": [
                {"name": "Ind A"}, {"name": "Ind B"}, {"name": "Ind C"}, {"name": "Ind D"},
            ],
            "theme_origin": "seed",
        }
        vertical_theme = {
            "theme_name": "Sector X Concentration",
            "direction": "bullish",
            "matching_industries": [
                {"name": "Ind A"}, {"name": "Ind E"}, {"name": "Ind F"}, {"name": "Ind G"},
            ],
            "theme_origin": "vertical",
        }
        themes = deduplicate_themes([seed_theme, vertical_theme])
        assert len(themes) == 2


class TestVerticalThemeStocks:
    def test_vertical_gets_sector_stocks(self):
        """Vertical theme with empty static_stocks should get sector representative stocks."""
        vertical_theme = {
            "theme_name": "Consumer Cyclical Sector Concentration",
            "direction": "bullish",
            "matching_industries": [
                {"name": "A", "sector": "Consumer Cyclical"},
                {"name": "B", "sector": "Consumer Cyclical"},
            ],
            "proxy_etfs": [],
            "static_stocks": [],
            "theme_origin": "vertical",
            "sector_weights": {"Consumer Cyclical": 1.0},
        }
        enrich_vertical_themes([vertical_theme])
        expected = SECTOR_REPRESENTATIVE_STOCKS["Consumer Cyclical"]
        assert vertical_theme["static_stocks"] == expected

    def test_existing_static_stocks_not_overwritten(self):
        """Vertical theme with existing static_stocks should keep them."""
        vertical_theme = {
            "theme_name": "Technology Sector Concentration",
            "direction": "bullish",
            "matching_industries": [
                {"name": "A", "sector": "Technology"},
            ],
            "proxy_etfs": [],
            "static_stocks": ["CUSTOM1", "CUSTOM2"],
            "theme_origin": "vertical",
            "sector_weights": {"Technology": 1.0},
        }
        enrich_vertical_themes([vertical_theme])
        assert vertical_theme["static_stocks"] == ["CUSTOM1", "CUSTOM2"]

    def test_seed_theme_stocks_not_modified(self):
        """Seed themes should not have static_stocks modified."""
        seed_theme = {
            "theme_name": "AI Theme",
            "direction": "bullish",
            "matching_industries": [{"name": "A", "sector": "Technology"}],
            "proxy_etfs": ["ETF1"],
            "static_stocks": ["NVDA"],
            "theme_origin": "seed",
        }
        enrich_vertical_themes([seed_theme])
        assert seed_theme["static_stocks"] == ["NVDA"]

    def test_vertical_infers_sector_from_industries(self):
        """Vertical theme without sector_weights should infer sector from industries."""
        vertical_theme = {
            "theme_name": "Industrials Sector Concentration",
            "direction": "bearish",
            "matching_industries": [
                {"name": "A", "sector": "Industrials"},
                {"name": "B", "sector": "Industrials"},
                {"name": "C", "sector": "Industrials"},
            ],
            "proxy_etfs": [],
            "static_stocks": [],
            "theme_origin": "vertical",
            "sector_weights": {},
        }
        enrich_vertical_themes([vertical_theme])
        expected = SECTOR_REPRESENTATIVE_STOCKS["Industrials"]
        assert vertical_theme["static_stocks"] == expected


class TestGetThemeSectorWeights:
    def test_single_sector(self):
        theme = {
            "matching_industries": [
                {"name": "A", "sector": "Tech"},
                {"name": "B", "sector": "Tech"},
            ]
        }
        weights = get_theme_sector_weights(theme)
        assert weights == {"Tech": 1.0}

    def test_multiple_sectors(self):
        theme = {
            "matching_industries": [
                {"name": "A", "sector": "Tech"},
                {"name": "B", "sector": "Health"},
            ]
        }
        weights = get_theme_sector_weights(theme)
        assert weights["Tech"] == 0.5
        assert weights["Health"] == 0.5

    def test_empty(self):
        assert get_theme_sector_weights({"matching_industries": []}) == {}
