"""Tests for determine_direction utility function"""

from calculators.utils import (
    compute_change,
    detect_crossover,
    determine_direction,
    score_transition_signal,
)


class TestDetermineDirection:
    def test_recent_golden_cross_confirmed(self):
        """Recent golden cross with positive ROC → positive label, confirmed."""
        crossover = {"type": "golden_cross", "bars_ago": 1}
        direction, qualifier = determine_direction(
            crossover,
            roc_3m=5.0,
            positive_label="risk_on",
            negative_label="risk_off",
        )
        assert direction == "risk_on"
        assert qualifier == "confirmed"

    def test_recent_death_cross_confirmed(self):
        """Recent death cross with negative ROC → negative label, confirmed."""
        crossover = {"type": "death_cross", "bars_ago": 1}
        direction, qualifier = determine_direction(
            crossover,
            roc_3m=-3.0,
            positive_label="risk_on",
            negative_label="risk_off",
        )
        assert direction == "risk_off"
        assert qualifier == "confirmed"

    def test_stale_golden_cross_reversing(self):
        """5-month-old golden cross with negative ROC → momentum overrides to negative."""
        crossover = {"type": "golden_cross", "bars_ago": 5}
        direction, qualifier = determine_direction(
            crossover,
            roc_3m=-13.0,
            positive_label="risk_on",
            negative_label="risk_off",
        )
        assert direction == "risk_off"
        assert qualifier == "reversing"

    def test_stale_death_cross_reversing(self):
        """Old death cross with positive ROC → momentum overrides to positive."""
        crossover = {"type": "death_cross", "bars_ago": 4}
        direction, qualifier = determine_direction(
            crossover,
            roc_3m=5.0,
            positive_label="easing",
            negative_label="tightening",
        )
        assert direction == "easing"
        assert qualifier == "reversing"

    def test_stale_golden_cross_confirmed(self):
        """Old golden cross but still positive ROC → positive label, confirmed."""
        crossover = {"type": "golden_cross", "bars_ago": 5}
        direction, qualifier = determine_direction(
            crossover,
            roc_3m=2.0,
            positive_label="risk_on",
            negative_label="risk_off",
        )
        assert direction == "risk_on"
        assert qualifier == "confirmed"

    def test_recent_cross_fading(self):
        """Recent golden cross but negative ROC (not stale) → positive, fading."""
        crossover = {"type": "golden_cross", "bars_ago": 1}
        direction, qualifier = determine_direction(
            crossover,
            roc_3m=-2.0,
            positive_label="risk_on",
            negative_label="risk_off",
        )
        assert direction == "risk_on"
        assert qualifier == "fading"

    def test_no_crossover_momentum_only(self):
        """No crossover, positive ROC → positive from momentum."""
        crossover = {"type": "none", "bars_ago": None}
        direction, qualifier = determine_direction(
            crossover,
            roc_3m=3.0,
            positive_label="small_cap_leading",
            negative_label="large_cap_leading",
        )
        assert direction == "small_cap_leading"
        assert qualifier == "N/A"

    def test_no_crossover_no_roc_neutral(self):
        """No crossover, no ROC → neutral."""
        crossover = {"type": "none", "bars_ago": None}
        direction, qualifier = determine_direction(
            crossover,
            roc_3m=None,
            positive_label="risk_on",
            negative_label="risk_off",
            neutral_label="neutral",
        )
        assert direction == "neutral"
        assert qualifier == "N/A"

    def test_converging_with_momentum(self):
        """Converging (not a cross) with positive momentum → positive from momentum."""
        crossover = {"type": "converging", "bars_ago": None}
        direction, qualifier = determine_direction(
            crossover,
            roc_3m=4.0,
            positive_label="risk_on",
            negative_label="risk_off",
        )
        assert direction == "risk_on"
        assert qualifier == "N/A"

    def test_custom_neutral_label(self):
        """Custom neutral label returned when no signals."""
        crossover = {"type": "none", "bars_ago": None}
        direction, qualifier = determine_direction(
            crossover,
            roc_3m=None,
            positive_label="easing",
            negative_label="tightening",
            neutral_label="stable",
        )
        assert direction == "stable"

    def test_stale_threshold_boundary(self):
        """bars_ago == 3 (exactly at threshold) is stale."""
        crossover = {"type": "golden_cross", "bars_ago": 3}
        direction, qualifier = determine_direction(
            crossover,
            roc_3m=-5.0,
            positive_label="risk_on",
            negative_label="risk_off",
        )
        assert direction == "risk_off"
        assert qualifier == "reversing"

    def test_bars_ago_just_below_threshold(self):
        """bars_ago == 2 (below threshold) is NOT stale → recent cross wins."""
        crossover = {"type": "golden_cross", "bars_ago": 2}
        direction, qualifier = determine_direction(
            crossover,
            roc_3m=-5.0,
            positive_label="risk_on",
            negative_label="risk_off",
        )
        assert direction == "risk_on"
        assert qualifier == "fading"


class TestSignedSeriesHelpers:
    """Regression tests for signed series in utils.py (Issue #880)."""

    def test_compute_change_signed_and_zero_past(self):
        assert compute_change([0.2, 0.05, -0.1, -0.3], 3) == 0.5
        assert compute_change([0.6, 0.4, 0.2, 0.0], 3) == 0.6
        assert compute_change([-0.7, -0.5, -0.3, -0.1], 3) == -0.6
        assert compute_change([0.1, 0.2], 3) is None

    def test_detect_crossover_negative_sma_long_sign_matches_direction(self):
        # Chronological spread rises -0.8 -> -0.1 (most recent first)
        spreads_chrono = [-0.8] * 16 + [-0.7, -0.6, -0.5, -0.4, -0.3, -0.2, -0.1, -0.1]
        values = list(reversed(spreads_chrono))
        cross_rel = detect_crossover(values)
        cross_abs = detect_crossover(values, use_absolute_gap=True, converging_threshold=0.10)
        assert cross_rel["type"] == "golden_cross"
        assert cross_rel["gap_pct"] > 0
        assert cross_abs["type"] == "golden_cross"
        assert cross_abs["gap_pct"] > 0

    def test_detect_crossover_absolute_gap_zero_long_sma_not_falsely_converging(self):
        # 12M SMA = 0.0, 6M SMA = 0.5 (all 12M prior also have 6M > 12M so no crossover in window)
        # Construct 24 points (oldest -> newest) where 6M > 12M throughout and final 12M SMA == 0.0
        chrono = [-1.0] * 12 + [-0.5] * 6 + [0.5] * 6
        values = list(reversed(chrono))
        # Final 12M SMA = (-0.5*6 + 0.5*6)/12 = 0.0, final 6M SMA = 0.5 -> gap = +0.5 >> 0.10
        cross = detect_crossover(values, use_absolute_gap=True, converging_threshold=0.10)
        assert cross["type"] != "converging"
        assert cross["gap_pct"] == 0.5

    def test_score_transition_signal_negative_sma_long_awards_gap_confirmation(self):
        # Golden cross 7 bars ago (+20), aligned ROC (+10), gap widening (+10) -> 60 total with accel
        cross = {"type": "golden_cross", "bars_ago": 7, "gap_pct": 0.288}
        score_abs = score_transition_signal(
            crossover=cross,
            roc_short=0.50,
            roc_long=1.00,
            sma_short=-0.175,
            sma_long=-0.462,
            use_absolute_gap=True,
            converging_threshold=0.10,
            momentum_cap=0.50,
            accel_threshold=0.30,
            gap_widening_threshold=0.05,
        )
        assert score_abs == 60

        # Even default percentage mode must use abs(sma_long) so negative sma_long doesn't negate gap
        score_rel = score_transition_signal(
            crossover={"type": "golden_cross", "bars_ago": 7, "gap_pct": 62.1},
            roc_short=5.0,
            roc_long=10.0,
            sma_short=-0.175,
            sma_long=-0.462,
        )
        assert score_rel == 60
