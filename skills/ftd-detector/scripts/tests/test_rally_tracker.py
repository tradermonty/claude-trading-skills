"""Tests for rally_tracker.py — swing low, rally attempt, FTD detection."""

from helpers import make_bar, make_correction_history, make_rally_history
from rally_tracker import (
    MIN_CORRECTION_PCT,
    MarketState,
    analyze_single_index,
    detect_ftd,
    find_swing_low,
    get_market_state,
    track_rally_attempt,
)

# ─── Test 1: Swing low detection ─────────────────────────────────────────────


class TestFindSwingLow:
    def test_detects_qualifying_swing_low(self):
        """5% decline + 5 down days -> swing low detected."""
        bars, _ = make_correction_history(peak=100, decline_pct=5.0, down_days=5)
        result = find_swing_low(bars)
        assert result is not None
        assert result["decline_pct"] <= -MIN_CORRECTION_PCT
        assert result["down_days"] >= 3

    def test_no_swing_low_shallow_decline(self):
        """2% decline -> no qualifying swing low."""
        bars, _ = make_correction_history(peak=100, decline_pct=2.0, down_days=4)
        result = find_swing_low(bars)
        assert result is None

    def test_no_swing_low_insufficient_down_days(self):
        """5% decline but only 2 down days -> no qualifying swing low."""
        bars, _ = make_correction_history(peak=100, decline_pct=5.0, down_days=2)
        result = find_swing_low(bars)
        assert result is None

    def test_swing_low_returns_correct_fields(self):
        """Verify all expected fields are present in result."""
        bars, _ = make_correction_history(peak=100, decline_pct=6.0, down_days=5)
        result = find_swing_low(bars)
        assert result is not None
        expected_keys = [
            "swing_low_idx",
            "swing_low_price",
            "swing_low_date",
            "swing_low_low",
            "recent_high_price",
            "recent_high_idx",
            "recent_high_date",
            "decline_pct",
            "down_days",
        ]
        for key in expected_keys:
            assert key in result, f"Missing key: {key}"


# ─── Test 2-5: Rally tracking ────────────────────────────────────────────────


class TestTrackRallyAttempt:
    def test_day1_detected_on_up_close(self):
        """First up close after swing low sets day1_idx."""
        bars, swing_low_idx, day1_idx, _ = make_rally_history(
            decline_pct=5.0,
            down_days=5,
            rally_days=3,
        )
        result = track_rally_attempt(bars, swing_low_idx)
        assert result["day1_idx"] is not None
        assert result["day1_date"] is not None
        assert result["current_day_count"] >= 1

    def test_rally_invalidated_close_below_swing_low(self):
        """Close below swing low invalidates the rally."""
        bars, _ = make_correction_history(peak=100, decline_pct=5.0, down_days=5)
        swing_low_idx = len(bars) - 1
        swing_low_close = bars[swing_low_idx]["close"]

        # Add a day that closes below swing low
        bars.append(
            make_bar(
                swing_low_close * 0.99,
                date=f"day-{len(bars):03d}",
            )
        )
        result = track_rally_attempt(bars, swing_low_idx)
        assert result["invalidated"] is True
        assert "below swing low" in result["invalidation_reason"]

    def test_day1_low_breach_invalidates(self):
        """Day 2 close below Day 1 low (but above swing low) invalidates the rally."""
        bars, _ = make_correction_history(peak=100, decline_pct=5.0, down_days=5)
        swing_low_idx = len(bars) - 1
        swing_low_close = bars[swing_low_idx]["close"]

        # Day 1: strong up close with a high intraday low (well above swing low)
        day1_close = swing_low_close * 1.03  # 3% up from swing low
        day1_low = swing_low_close * 1.015  # Day 1 low well above swing low
        bars.append(
            make_bar(
                day1_close,
                date=f"day-{len(bars):03d}",
                low=day1_low,
            )
        )

        # Day 2: close below Day 1 low but still above swing low
        day2_close = swing_low_close * 1.005  # Above swing low
        assert day2_close < day1_low, "Day 2 close must be below Day 1 low"
        assert day2_close > swing_low_close, "Day 2 close must be above swing low"
        bars.append(
            make_bar(
                day2_close,
                date=f"day-{len(bars):03d}",
            )
        )

        result = track_rally_attempt(bars, swing_low_idx)
        assert result["invalidated"] is True
        assert "Day 1 low" in result["invalidation_reason"]

    def test_no_day1_if_no_up_close(self):
        """If all post-swing-low days are down, day1_idx is None."""
        bars, _ = make_correction_history(peak=100, decline_pct=5.0, down_days=5)
        swing_low_idx = len(bars) - 1
        last_close = bars[-1]["close"]

        # Add 3 down days
        for _i in range(3):
            last_close *= 0.998
            bars.append(make_bar(last_close, date=f"day-{len(bars):03d}"))

        result = track_rally_attempt(bars, swing_low_idx)
        # Either day1 is None or it got invalidated because it went below swing low
        assert result["day1_idx"] is None or result["invalidated"]


# ─── Test 6-8: FTD detection ─────────────────────────────────────────────────


class TestDetectFTD:
    def test_ftd_detected_day4_qualifying(self):
        """Day 4: 1.5% gain + higher volume -> ftd_detected=True."""
        bars, swing_low_idx, _, _ = make_rally_history(
            decline_pct=5.0,
            down_days=5,
            rally_days=6,
            ftd_day=4,
            ftd_gain_pct=1.5,
            ftd_volume_mult=1.5,
        )
        rally = track_rally_attempt(bars, swing_low_idx)
        assert not rally["invalidated"]
        ftd = detect_ftd(bars, rally)
        assert ftd["ftd_detected"] is True
        assert ftd["ftd_day_number"] == 4
        assert ftd["gain_pct"] >= 1.25

    def test_ftd_not_detected_low_volume(self):
        """Gain OK but volume lower than previous day -> no FTD."""
        bars, swing_low_idx, _, _ = make_rally_history(
            decline_pct=5.0,
            down_days=5,
            rally_days=6,
            ftd_day=4,
            ftd_gain_pct=1.5,
            ftd_volume_mult=0.8,  # Volume LOWER than previous
        )
        rally = track_rally_attempt(bars, swing_low_idx)
        ftd = detect_ftd(bars, rally)
        assert ftd["ftd_detected"] is False

    def test_ftd_window_expired(self):
        """Rally goes past day 10 without qualifying FTD -> RALLY_FAILED."""
        bars, swing_low_idx, _, _ = make_rally_history(
            decline_pct=5.0,
            down_days=5,
            rally_days=12,
            rally_gain_per_day=0.2,  # Small gains, no FTD
        )
        result = analyze_single_index(bars, "Test")
        # Should be RALLY_FAILED or FTD_WINDOW, not FTD_CONFIRMED
        assert result["state"] != MarketState.FTD_CONFIRMED.value

    def test_ftd_gain_tier_strong(self):
        """2.0%+ gain -> strong tier."""
        bars, swing_low_idx, _, _ = make_rally_history(
            decline_pct=5.0,
            down_days=5,
            rally_days=6,
            ftd_day=5,
            ftd_gain_pct=2.5,
            ftd_volume_mult=1.5,
        )
        rally = track_rally_attempt(bars, swing_low_idx)
        ftd = detect_ftd(bars, rally)
        if ftd["ftd_detected"]:
            assert ftd["gain_tier"] == "strong"


# ─── Test 9: Fix 1 verification — price recovery near highs ──────────────────


class TestPriceRecoveryFix:
    def test_ftd_tracked_despite_recovery_near_highs(self):
        """
        Fix 1 verification: After correction, if price rallies back near
        the lookback high (within 3%), FTD tracking must NOT be killed.

        Old behavior: correction_depth > -3% -> NO_SIGNAL (wrong).
        New behavior: swing_low found -> continue tracking.
        """
        bars, swing_low_idx, _, _ = make_rally_history(
            peak=100,
            decline_pct=5.0,
            down_days=5,
            rally_days=8,
            rally_gain_per_day=0.6,
            ftd_day=5,
            ftd_gain_pct=1.8,
            ftd_volume_mult=1.5,
        )

        # The rally should have brought price back near the peak
        current_price = bars[-1]["close"]
        peak = 100.0
        recovery_pct = (current_price - peak) / peak * 100

        result = analyze_single_index(bars, "Test Recovery")

        # Must NOT be NO_SIGNAL — should track the FTD
        assert result["state"] != MarketState.NO_SIGNAL.value, (
            f"Price recovered to {recovery_pct:+.1f}% from peak but state is "
            f"NO_SIGNAL. Fix 1 regression: early return on shallow correction_depth."
        )

    def test_no_signal_when_no_swing_low(self):
        """No qualifying swing low -> NO_SIGNAL (correct behavior)."""
        # Flat market with 1% variation — no swing low
        bars = []
        for i in range(30):
            price = 100 + (i % 3) * 0.3  # Tiny oscillation
            bars.append(make_bar(price, date=f"day-{i:03d}"))

        result = analyze_single_index(bars, "Flat Market")
        assert result["state"] == MarketState.NO_SIGNAL.value


# ─── Test 10: Dual-index merge ───────────────────────────────────────────────


class TestDualIndexMerge:
    def test_dual_confirmation_both_ftd(self):
        """Both S&P 500 and NASDAQ have FTD -> dual_confirmation=True."""
        bars_sp, _, _, _ = make_rally_history(
            peak=100,
            decline_pct=5.0,
            down_days=5,
            rally_days=7,
            ftd_day=5,
            ftd_gain_pct=1.6,
            ftd_volume_mult=1.5,
        )
        bars_nq, _, _, _ = make_rally_history(
            peak=200,
            decline_pct=6.0,
            down_days=5,
            rally_days=7,
            ftd_day=6,
            ftd_gain_pct=1.8,
            ftd_volume_mult=1.5,
        )

        # get_market_state expects API format (most recent first)
        sp_reversed = list(reversed(bars_sp))
        nq_reversed = list(reversed(bars_nq))

        result = get_market_state(sp_reversed, nq_reversed)
        assert result["combined_state"] == MarketState.FTD_CONFIRMED.value
        assert result["dual_confirmation"] is True

    def test_single_ftd_no_dual(self):
        """Only S&P 500 has FTD -> dual_confirmation=False."""
        bars_sp, _, _, _ = make_rally_history(
            peak=100,
            decline_pct=5.0,
            down_days=5,
            rally_days=7,
            ftd_day=5,
            ftd_gain_pct=1.6,
            ftd_volume_mult=1.5,
        )
        # NASDAQ: flat market, no swing low
        bars_nq = [make_bar(200 + i * 0.1, date=f"day-{i:03d}") for i in range(30)]

        sp_reversed = list(reversed(bars_sp))
        nq_reversed = list(reversed(bars_nq))

        result = get_market_state(sp_reversed, nq_reversed)
        assert result["combined_state"] == MarketState.FTD_CONFIRMED.value
        assert result["dual_confirmation"] is False
