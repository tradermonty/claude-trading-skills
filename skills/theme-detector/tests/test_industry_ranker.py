"""Tests for industry_ranker module."""

from calculators.industry_ranker import rank_industries, get_top_bottom_industries


def _make_industry(name, perf_1w=0.0, perf_1m=0.0, perf_3m=0.0, perf_6m=0.0,
                   sector="Technology"):
    return {
        "name": name,
        "perf_1w": perf_1w,
        "perf_1m": perf_1m,
        "perf_3m": perf_3m,
        "perf_6m": perf_6m,
        "sector": sector,
    }


class TestRankIndustries:
    def test_empty_input(self):
        assert rank_industries([]) == []

    def test_basic_ranking(self):
        industries = [
            _make_industry("A", 5.0, 10.0, 15.0, 20.0),
            _make_industry("B", 1.0, 2.0, 3.0, 4.0),
        ]
        ranked = rank_industries(industries)
        assert ranked[0]["name"] == "A"
        assert ranked[1]["name"] == "B"
        assert ranked[0]["rank"] == 1
        assert ranked[1]["rank"] == 2

    def test_direction_field(self):
        industries = [
            _make_industry("Positive", 5.0, 10.0, 15.0, 20.0),
            _make_industry("Negative", -5.0, -10.0, -15.0, -20.0),
        ]
        ranked = rank_industries(industries)
        positive = next(r for r in ranked if r["name"] == "Positive")
        negative = next(r for r in ranked if r["name"] == "Negative")
        assert positive["direction"] == "bullish"
        assert negative["direction"] == "bearish"

    def test_rank_direction_field_exists(self):
        """rank_direction should be present on all ranked industries."""
        industries = [
            _make_industry("A", 5.0, 10.0, 15.0, 20.0),
            _make_industry("B", 1.0, 2.0, 3.0, 4.0),
            _make_industry("C", -1.0, -2.0, -3.0, -4.0),
            _make_industry("D", -5.0, -10.0, -15.0, -20.0),
        ]
        ranked = rank_industries(industries)
        for r in ranked:
            assert "rank_direction" in r

    def test_rank_direction_top_half_bullish(self):
        """Top half of ranked list should have rank_direction='bullish'."""
        industries = [
            _make_industry("Strong", 20.0, 20.0, 20.0, 20.0),
            _make_industry("Medium", 5.0, 5.0, 5.0, 5.0),
            _make_industry("Weak", -5.0, -5.0, -5.0, -5.0),
            _make_industry("Weakest", -20.0, -20.0, -20.0, -20.0),
        ]
        ranked = rank_industries(industries)
        # Rank 1 and 2 should be bullish, 3 and 4 should be bearish
        assert ranked[0]["rank_direction"] == "bullish"
        assert ranked[1]["rank_direction"] == "bullish"
        assert ranked[2]["rank_direction"] == "bearish"
        assert ranked[3]["rank_direction"] == "bearish"

    def test_rank_direction_all_positive_still_has_bearish(self):
        """Even when all weighted_returns are positive, bottom half should be bearish by rank."""
        industries = [
            _make_industry("A", 20.0, 20.0, 20.0, 20.0),
            _make_industry("B", 15.0, 15.0, 15.0, 15.0),
            _make_industry("C", 10.0, 10.0, 10.0, 10.0),
            _make_industry("D", 5.0, 5.0, 5.0, 5.0),
        ]
        ranked = rank_industries(industries)
        bearish_count = sum(1 for r in ranked if r["rank_direction"] == "bearish")
        assert bearish_count == 2, "Bottom half should be bearish even if all returns are positive"

    def test_rank_direction_odd_count(self):
        """With odd number, mid point should divide correctly."""
        industries = [
            _make_industry("A", 20.0, 20.0, 20.0, 20.0),
            _make_industry("B", 10.0, 10.0, 10.0, 10.0),
            _make_industry("C", -10.0, -10.0, -10.0, -10.0),
        ]
        ranked = rank_industries(industries)
        # mid = 3 // 2 = 1, so only rank 1 is bullish
        assert ranked[0]["rank_direction"] == "bullish"
        assert ranked[1]["rank_direction"] == "bearish"
        assert ranked[2]["rank_direction"] == "bearish"


class TestGetTopBottomIndustries:
    def test_basic(self):
        industries = [_make_industry(f"I{i}", i, i, i, i) for i in range(10)]
        ranked = rank_industries(industries)
        result = get_top_bottom_industries(ranked, n=3)
        assert len(result["top"]) == 3
        assert len(result["bottom"]) == 3
        assert result["top"][0]["rank"] == 1

    def test_empty(self):
        result = get_top_bottom_industries([], n=5)
        assert result["top"] == []
        assert result["bottom"] == []
