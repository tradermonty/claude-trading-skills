#!/usr/bin/env python3
"""
Tests for industry_ranker module.

Covers momentum_strength_score sigmoid, weighted return calculation,
ranking, direction classification, and top/bottom extraction.
"""

import math

from calculators.industry_ranker import (
    TIMEFRAME_WEIGHTS,
    get_top_bottom_industries,
    momentum_strength_score,
    rank_industries,
)

# ---------------------------------------------------------------------------
# momentum_strength_score tests
# ---------------------------------------------------------------------------


class TestMomentumStrengthScore:
    """Test the direction-neutral sigmoid scoring function."""

    def test_zero_return_gives_about_32(self):
        """abs(0%) -> ~32 (sigmoid at -5.0 midpoint)."""
        score = momentum_strength_score(0.0)
        assert 30 <= score <= 34, f"Expected ~32, got {score}"

    def test_five_pct_gives_50(self):
        """abs(5%) is the midpoint -> exactly 50."""
        score = momentum_strength_score(5.0)
        assert abs(score - 50.0) < 0.1, f"Expected 50, got {score}"

    def test_ten_pct_gives_about_68(self):
        """abs(10%) -> ~68."""
        score = momentum_strength_score(10.0)
        assert 66 <= score <= 70, f"Expected ~68, got {score}"

    def test_fifteen_pct_gives_about_82(self):
        """abs(15%) -> ~82."""
        score = momentum_strength_score(15.0)
        assert 80 <= score <= 84, f"Expected ~82, got {score}"

    def test_twenty_pct_gives_about_90(self):
        """abs(20%) -> ~90."""
        score = momentum_strength_score(20.0)
        assert 88 <= score <= 92, f"Expected ~90, got {score}"

    def test_negative_return_same_as_positive(self):
        """Negative and positive returns with same magnitude give same score."""
        pos = momentum_strength_score(12.0)
        neg = momentum_strength_score(-12.0)
        assert abs(pos - neg) < 0.01

    def test_large_return_caps_near_100(self):
        """Very large returns approach but don't exceed 100."""
        score = momentum_strength_score(50.0)
        assert 99 <= score <= 100

    def test_score_always_between_0_and_100(self):
        """Score is bounded [0, 100] for any input."""
        for ret in [-100, -50, -10, 0, 10, 50, 100]:
            score = momentum_strength_score(ret)
            assert 0 <= score <= 100, f"Out of bounds for {ret}: {score}"

    def test_monotonically_increasing_with_abs(self):
        """Higher absolute return -> higher score."""
        s1 = momentum_strength_score(5.0)
        s2 = momentum_strength_score(10.0)
        s3 = momentum_strength_score(20.0)
        assert s1 < s2 < s3


# ---------------------------------------------------------------------------
# TIMEFRAME_WEIGHTS validation
# ---------------------------------------------------------------------------


class TestTimeframeWeights:
    """Verify timeframe weights are correct and sum to 1.0."""

    def test_weights_sum_to_one(self):
        total = sum(TIMEFRAME_WEIGHTS.values())
        assert abs(total - 1.0) < 0.001

    def test_expected_keys(self):
        expected = {"perf_1w", "perf_1m", "perf_3m", "perf_6m"}
        assert set(TIMEFRAME_WEIGHTS.keys()) == expected

    def test_expected_values(self):
        assert TIMEFRAME_WEIGHTS["perf_1w"] == 0.10
        assert TIMEFRAME_WEIGHTS["perf_1m"] == 0.25
        assert TIMEFRAME_WEIGHTS["perf_3m"] == 0.35
        assert TIMEFRAME_WEIGHTS["perf_6m"] == 0.30


# ---------------------------------------------------------------------------
# rank_industries tests
# ---------------------------------------------------------------------------


def _make_industry(name, perf_1w=0.0, perf_1m=0.0, perf_3m=0.0, perf_6m=0.0):
    """Helper to build a synthetic industry dict."""
    return {
        "name": name,
        "perf_1w": perf_1w,
        "perf_1m": perf_1m,
        "perf_3m": perf_3m,
        "perf_6m": perf_6m,
    }


class TestRankIndustries:
    """Test rank_industries function."""

    def test_adds_required_fields(self):
        """Each result dict gets momentum_score, weighted_return, direction, rank."""
        industries = [_make_industry("Tech", 5, 10, 15, 20)]
        ranked = rank_industries(industries)
        assert len(ranked) == 1
        item = ranked[0]
        assert "momentum_score" in item
        assert "weighted_return" in item
        assert "direction" in item
        assert "rank" in item

    def test_weighted_return_calculation(self):
        """Verify weighted return = sum(perf_x * weight_x)."""
        ind = _make_industry("Test", perf_1w=10.0, perf_1m=20.0, perf_3m=30.0, perf_6m=40.0)
        ranked = rank_industries([ind])
        expected = 10 * 0.10 + 20 * 0.25 + 30 * 0.35 + 40 * 0.30
        assert abs(ranked[0]["weighted_return"] - expected) < 0.01

    def test_sorted_by_momentum_score_desc(self):
        """Industries are sorted by momentum_score descending."""
        industries = [
            _make_industry("Low", perf_1w=1, perf_1m=1, perf_3m=1, perf_6m=1),
            _make_industry("High", perf_1w=20, perf_1m=30, perf_3m=40, perf_6m=50),
            _make_industry("Mid", perf_1w=5, perf_1m=10, perf_3m=10, perf_6m=10),
        ]
        ranked = rank_industries(industries)
        assert ranked[0]["name"] == "High"
        assert ranked[-1]["name"] == "Low"
        # Verify descending order
        scores = [r["momentum_score"] for r in ranked]
        assert scores == sorted(scores, reverse=True)

    def test_rank_starts_at_one(self):
        """Rank should be 1-based."""
        industries = [
            _make_industry("A", perf_3m=10),
            _make_industry("B", perf_3m=20),
        ]
        ranked = rank_industries(industries)
        assert ranked[0]["rank"] == 1
        assert ranked[1]["rank"] == 2

    def test_bullish_direction_for_positive_return(self):
        """Positive weighted return -> direction='bullish'."""
        ranked = rank_industries([_make_industry("Up", perf_3m=15, perf_6m=10)])
        assert ranked[0]["direction"] == "bullish"

    def test_bearish_direction_for_negative_return(self):
        """Negative weighted return -> direction='bearish'."""
        ranked = rank_industries([_make_industry("Down", perf_3m=-15, perf_6m=-10)])
        assert ranked[0]["direction"] == "bearish"

    def test_zero_return_direction(self):
        """Zero weighted return -> direction='bearish' (non-positive)."""
        ranked = rank_industries([_make_industry("Flat")])
        assert ranked[0]["direction"] == "bearish"

    def test_empty_list_returns_empty(self):
        """Empty input returns empty list."""
        assert rank_industries([]) == []

    def test_preserves_original_fields(self):
        """Original industry dict fields are preserved in output."""
        ind = _make_industry("Test", perf_1w=5, perf_1m=10, perf_3m=15, perf_6m=20)
        ind["sector"] = "Technology"  # extra field
        ranked = rank_industries([ind])
        assert ranked[0]["name"] == "Test"
        assert ranked[0]["perf_1w"] == 5
        assert ranked[0]["sector"] == "Technology"

    def test_mixed_bullish_bearish(self):
        """Mix of positive and negative returns handled correctly."""
        industries = [
            _make_industry("Bull", perf_1w=10, perf_1m=15, perf_3m=20, perf_6m=25),
            _make_industry("Bear", perf_1w=-10, perf_1m=-15, perf_3m=-20, perf_6m=-25),
        ]
        ranked = rank_industries(industries)
        # Both should have same momentum_score (direction-neutral)
        assert abs(ranked[0]["momentum_score"] - ranked[1]["momentum_score"]) < 0.01
        # But different directions
        directions = {r["name"]: r["direction"] for r in ranked}
        assert directions["Bull"] == "bullish"
        assert directions["Bear"] == "bearish"


# ---------------------------------------------------------------------------
# get_top_bottom_industries tests
# ---------------------------------------------------------------------------


class TestGetTopBottomIndustries:
    """Test top/bottom extraction."""

    def test_top_and_bottom_n(self):
        """Returns correct top N and bottom N."""
        industries = [
            _make_industry(f"Ind{i}", perf_3m=20 - i * 2, perf_6m=15 - i)
            for i in range(10)
        ]
        ranked = rank_industries(industries)
        result = get_top_bottom_industries(ranked, n=3)
        assert len(result["top"]) == 3
        assert len(result["bottom"]) == 3
        # Top should have rank 1,2,3
        assert result["top"][0]["rank"] == 1
        assert result["top"][2]["rank"] == 3
        # Bottom should have rank 8,9,10
        assert result["bottom"][0]["rank"] == 8
        assert result["bottom"][2]["rank"] == 10

    def test_n_greater_than_half(self):
        """When n > len/2, top and bottom may overlap; should handle gracefully."""
        industries = [_make_industry(f"I{i}", perf_3m=i) for i in range(4)]
        ranked = rank_industries(industries)
        result = get_top_bottom_industries(ranked, n=3)
        assert len(result["top"]) == 3
        assert len(result["bottom"]) == 3

    def test_empty_ranked_list(self):
        """Empty input returns empty top and bottom."""
        result = get_top_bottom_industries([], n=5)
        assert result["top"] == []
        assert result["bottom"] == []

    def test_n_exceeds_list_length(self):
        """n > len(ranked) returns all available."""
        industries = [_make_industry(f"I{i}", perf_3m=i * 5) for i in range(3)]
        ranked = rank_industries(industries)
        result = get_top_bottom_industries(ranked, n=10)
        assert len(result["top"]) == 3
        assert len(result["bottom"]) == 3

    def test_default_n_is_5(self):
        """Default n should be 5."""
        industries = [_make_industry(f"I{i}", perf_3m=i * 3) for i in range(20)]
        ranked = rank_industries(industries)
        result = get_top_bottom_industries(ranked)
        assert len(result["top"]) == 5
        assert len(result["bottom"]) == 5
