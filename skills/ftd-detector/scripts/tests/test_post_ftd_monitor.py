"""Tests for post_ftd_monitor.py — distribution counting, invalidation, quality score."""

from helpers import make_bar, make_rally_history
from post_ftd_monitor import (
    assess_post_ftd_health,
    calculate_ftd_quality_score,
    check_ftd_invalidation,
    count_post_ftd_distribution,
)

# ─── Helpers ──────────────────────────────────────────────────────────────────


def _build_post_ftd_bars(ftd_close=100.0, ftd_low=99.5, ftd_volume=1_000_000, post_days=None):
    """
    Build a minimal history around an FTD day for post-FTD testing.

    Args:
        post_days: List of (close, volume) tuples for days after FTD.

    Returns (history, ftd_idx).
    """
    if post_days is None:
        post_days = []

    bars = []
    # Pre-FTD bar (needed for volume comparison)
    bars.append(
        make_bar(ftd_close * 0.99, volume=ftd_volume, date="pre-ftd", low=ftd_close * 0.985)
    )
    # FTD bar
    bars.append(make_bar(ftd_close, volume=ftd_volume, date="ftd-day", low=ftd_low))
    ftd_idx = 1

    # Post-FTD bars
    for i, (close, volume) in enumerate(post_days):
        bars.append(make_bar(close, volume=volume, date=f"post-{i + 1}", low=close * 0.997))

    return bars, ftd_idx


# ─── Test 1: Distribution day counting ───────────────────────────────────────


class TestCountPostFTDDistribution:
    def test_distribution_day_detected(self):
        """Day 1 post-FTD: down on higher volume -> count=1, earliest=1."""
        bars, ftd_idx = _build_post_ftd_bars(
            ftd_close=100,
            ftd_volume=1_000_000,
            post_days=[
                (99.5, 1_200_000),  # Day 1: -0.5% on higher volume = distribution
            ],
        )
        result = count_post_ftd_distribution(bars, ftd_idx)
        assert result["distribution_count"] == 1
        assert result["earliest_distribution_day"] == 1
        assert result["days_monitored"] == 1

    def test_no_distribution_clean_days(self):
        """5 clean days (up or down on lower volume) -> count=0."""
        bars, ftd_idx = _build_post_ftd_bars(
            ftd_close=100,
            ftd_volume=1_000_000,
            post_days=[
                (100.5, 900_000),  # Day 1: up, lower vol
                (101.0, 950_000),  # Day 2: up, lower vol
                (100.8, 800_000),  # Day 3: down but lower volume
                (101.5, 850_000),  # Day 4: up, lower vol
                (102.0, 900_000),  # Day 5: up, lower vol
            ],
        )
        result = count_post_ftd_distribution(bars, ftd_idx)
        assert result["distribution_count"] == 0
        assert result["days_monitored"] == 5
        assert result["earliest_distribution_day"] is None

    def test_multiple_distribution_days(self):
        """Days 2 and 4 are distribution -> count=2, earliest=2."""
        bars, ftd_idx = _build_post_ftd_bars(
            ftd_close=100,
            ftd_volume=1_000_000,
            post_days=[
                (100.5, 900_000),  # Day 1: up
                (99.0, 1_100_000),  # Day 2: down on higher vol = dist
                (99.5, 800_000),  # Day 3: up, lower vol
                (98.5, 1_300_000),  # Day 4: down on higher vol = dist
                (99.0, 900_000),  # Day 5: up, lower vol
            ],
        )
        result = count_post_ftd_distribution(bars, ftd_idx)
        assert result["distribution_count"] == 2
        assert result["earliest_distribution_day"] == 2

    def test_ftd_at_end_of_history(self):
        """FTD on last day of history -> 0 days monitored."""
        bars, ftd_idx = _build_post_ftd_bars(ftd_close=100, post_days=[])
        result = count_post_ftd_distribution(bars, ftd_idx)
        assert result["distribution_count"] == 0
        assert result["days_monitored"] == 0


# ─── Test 2: FTD invalidation ────────────────────────────────────────────────


class TestCheckFTDInvalidation:
    def test_invalidated_close_below_ftd_low(self):
        """Close below FTD day's low -> invalidated=True."""
        bars, ftd_idx = _build_post_ftd_bars(
            ftd_close=100,
            ftd_low=99.0,
            post_days=[
                (100.5, 1_000_000),  # Day 1: above
                (98.5, 1_000_000),  # Day 2: below FTD low 99.0
            ],
        )
        result = check_ftd_invalidation(bars, ftd_idx)
        assert result["invalidated"] is True
        assert result["days_after_ftd"] == 2

    def test_not_invalidated_holds_above_ftd_low(self):
        """Price stays above FTD low -> invalidated=False."""
        bars, ftd_idx = _build_post_ftd_bars(
            ftd_close=100,
            ftd_low=99.0,
            post_days=[
                (100.5, 1_000_000),
                (99.5, 1_000_000),  # Above FTD low
                (101.0, 1_000_000),
            ],
        )
        result = check_ftd_invalidation(bars, ftd_idx)
        assert result["invalidated"] is False
        assert result["days_since_ftd"] == 3


# ─── Test 3: Fix 3 verification — data missing -> +0 not +10 ─────────────────


class TestQualityScoreDataMissing:
    def test_empty_post_ftd_gives_zero_not_ten(self):
        """
        Fix 3 verification: When post_ftd_distribution is empty {},
        days_monitored defaults to 0 -> score adjustment should be +0.
        """
        market_state = {
            "sp500": {
                "ftd": {
                    "ftd_detected": True,
                    "ftd_day_number": 5,
                    "gain_pct": 1.6,
                    "volume_above_avg": True,
                },
            },
            "nasdaq": {"ftd": {}},
            "dual_confirmation": False,
            "post_ftd_distribution": {},  # Empty — no data yet
        }
        result = calculate_ftd_quality_score(market_state)
        breakdown = result["breakdown"]

        # Must say "not yet available" and +0
        assert "+0" in breakdown["post_ftd"]
        assert "not yet available" in breakdown["post_ftd"].lower()

    def test_monitored_days_with_no_distribution_gives_ten(self):
        """When days_monitored > 0 and dist_count == 0, should give +10."""
        market_state = {
            "sp500": {
                "ftd": {
                    "ftd_detected": True,
                    "ftd_day_number": 5,
                    "gain_pct": 1.6,
                    "volume_above_avg": True,
                },
            },
            "nasdaq": {"ftd": {}},
            "dual_confirmation": False,
            "post_ftd_distribution": {
                "distribution_count": 0,
                "days_monitored": 3,
                "earliest_distribution_day": None,
            },
        }
        result = calculate_ftd_quality_score(market_state)
        breakdown = result["breakdown"]
        assert "+10" in breakdown["post_ftd"]
        assert "3 days clean" in breakdown["post_ftd"]


# ─── Test 4: Quality score full ──────────────────────────────────────────────


class TestQualityScoreFull:
    def test_maximum_score(self):
        """Day 5 + 2.0% gain + above avg vol + dual + clean 5 days -> 100."""
        market_state = {
            "sp500": {
                "ftd": {
                    "ftd_detected": True,
                    "ftd_day_number": 5,
                    "gain_pct": 2.0,
                    "volume_above_avg": True,
                },
            },
            "nasdaq": {
                "ftd": {
                    "ftd_detected": True,
                    "ftd_day_number": 6,
                    "gain_pct": 1.8,
                    "volume_above_avg": True,
                },
            },
            "dual_confirmation": True,
            "post_ftd_distribution": {
                "distribution_count": 0,
                "days_monitored": 5,
                "earliest_distribution_day": None,
            },
        }
        result = calculate_ftd_quality_score(market_state)
        # 60 (base) + 15 (gain) + 10 (volume) + 15 (dual) + 10 (clean) = 110 -> clamped to 100
        assert result["total_score"] == 100

    def test_minimum_score(self):
        """Day 10 + 1.25% gain + below avg vol + single + dist day 2 -> low score."""
        market_state = {
            "sp500": {
                "ftd": {
                    "ftd_detected": True,
                    "ftd_day_number": 10,
                    "gain_pct": 1.25,
                    "volume_above_avg": False,
                },
            },
            "nasdaq": {"ftd": {}},
            "dual_confirmation": False,
            "post_ftd_distribution": {
                "distribution_count": 1,
                "days_monitored": 2,
                "earliest_distribution_day": 2,
            },
        }
        result = calculate_ftd_quality_score(market_state)
        # 50 (base day 10) + 5 (gain 1.25%) + 0 (vol below) + 0 (single) - 30 (dist day 2) = 25
        assert result["total_score"] == 25

    def test_no_ftd_returns_zero(self):
        """No FTD detected -> score 0."""
        market_state = {
            "sp500": {"ftd": {}},
            "nasdaq": {"ftd": {}},
            "dual_confirmation": False,
        }
        result = calculate_ftd_quality_score(market_state)
        assert result["total_score"] == 0
        assert result["signal"] == "No FTD"


# ─── Test 5: Fix 2 verification — dual-index consistency ─────────────────────


class TestDualIndexConsistency:
    def test_assess_uses_first_ftd_index_only(self):
        """
        Fix 2 verification: When both indices have confirmed FTDs,
        assess_post_ftd_health should use S&P 500 (first in loop) and
        NOT overwrite with NASDAQ data.
        """
        # Build separate histories for each index
        sp_bars, sp_swing, _, _ = make_rally_history(
            peak=100,
            decline_pct=5.0,
            down_days=5,
            rally_days=8,
            ftd_day=5,
            ftd_gain_pct=1.6,
            ftd_volume_mult=1.5,
        )
        nq_bars, nq_swing, _, _ = make_rally_history(
            peak=200,
            decline_pct=6.0,
            down_days=5,
            rally_days=8,
            ftd_day=6,
            ftd_gain_pct=2.0,
            ftd_volume_mult=1.8,
        )

        # Use get_market_state to build initial state (expects reversed/API order)
        from rally_tracker import get_market_state

        sp_reversed = list(reversed(sp_bars))
        nq_reversed = list(reversed(nq_bars))
        market_state = get_market_state(sp_reversed, nq_reversed)

        # Both should have FTD
        assert market_state["sp500"]["ftd"]["ftd_detected"] is True
        assert market_state["nasdaq"]["ftd"]["ftd_detected"] is True

        # Run post-FTD assessment
        enriched = assess_post_ftd_health(market_state, sp_bars, nq_bars)

        # The quality score should use S&P 500 as the source (first in loop)
        qs = enriched.get("quality_score", {})
        assert qs.get("ftd_source") == "S&P 500"

        # post_ftd_distribution should be based on S&P 500 history
        # (If Fix 2 not applied, NASDAQ would overwrite this)
        dist = enriched.get("post_ftd_distribution", {})
        assert "days_monitored" in dist
