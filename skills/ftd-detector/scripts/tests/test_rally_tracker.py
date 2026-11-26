"""Tests for rally_tracker.py through its public entry points (replay state machine)."""

from helpers import make_bar, make_correction_history, make_rally_history
from rally_tracker import (
    MarketState,
    analyze_single_index,
    get_market_state,
)

# ─── Correction qualification ────────────────────────────────────────────────


class TestCorrectionQualification:
    def test_qualifying_correction_is_found(self):
        """5% decline + 5 down days -> a correction with a swing low."""
        bars, _ = make_correction_history(peak=100, decline_pct=5.0, down_days=5)
        result = analyze_single_index(bars, "Test")
        assert result["state"] == MarketState.CORRECTION.value
        assert result["swing_low"]["decline_pct"] <= -3.0
        assert result["swing_low"]["down_days"] >= 3

    def test_no_correction_shallow_decline(self):
        """2% decline -> no qualifying correction."""
        bars, _ = make_correction_history(peak=100, decline_pct=2.0, down_days=4)
        assert analyze_single_index(bars, "Test")["state"] == MarketState.NO_SIGNAL.value

    def test_no_correction_insufficient_down_days(self):
        """5% decline but only 2 down days -> no qualifying correction."""
        bars, _ = make_correction_history(peak=100, decline_pct=5.0, down_days=2)
        assert analyze_single_index(bars, "Test")["state"] == MarketState.NO_SIGNAL.value

    def test_swing_low_returns_correct_fields(self):
        bars, _ = make_correction_history(peak=100, decline_pct=6.0, down_days=5)
        result = analyze_single_index(bars, "Test")
        for key in [
            "swing_low_idx",
            "swing_low_price",
            "swing_low_date",
            "swing_low_low",
            "recent_high_price",
            "recent_high_idx",
            "recent_high_date",
            "decline_pct",
            "down_days",
        ]:
            assert key in result["swing_low"], f"Missing key: {key}"


# ─── Rally tracking ──────────────────────────────────────────────────────────


class TestRallyAttempt:
    def test_day1_detected_on_up_close(self):
        bars, _, _, _ = make_rally_history(decline_pct=5.0, down_days=5, rally_days=3)
        result = analyze_single_index(bars, "Test")
        assert result["rally_attempt"]["day1_idx"] is not None
        assert result["rally_attempt"]["day1_date"] is not None
        assert result["rally_attempt"]["current_day_count"] >= 1

    def test_close_below_the_correction_closing_low_is_not_a_failure(self):
        """A lower close that holds the intraday correction low only moves the closing low."""
        bars, _ = make_correction_history(peak=100, decline_pct=5.0, down_days=5)
        low_bar = bars[-1]
        bars.append(make_bar(low_bar["close"] * 0.999, low=low_bar["low"] * 1.002))
        result = analyze_single_index(bars, "Test")
        assert result["state"] == MarketState.CORRECTION.value
        assert result["rally_attempt"]["invalidated"] is False

    def test_correction_low_undercut_invalidates_the_rally(self):
        bars, _ = make_correction_history(peak=100, decline_pct=5.0, down_days=5)
        correction_low = bars[-1]["low"]
        price = bars[-1]["close"]
        bars.append(
            make_bar(price * 1.03, low=price * 1.015)
        )  # Day 1, low above the correction low
        bars.append(make_bar(price * 1.02, low=correction_low - 0.5))  # undercut
        result = analyze_single_index(bars, "Test")
        assert result["state"] == MarketState.RALLY_FAILED.value
        assert result["rally_attempt"]["invalidated"] is True
        assert "below rally low" in result["rally_attempt"]["invalidation_reason"]

    def test_day1_low_breach_alone_does_not_invalidate(self):
        """Day 2 trading below the Day 1 low (above the correction low) keeps the attempt."""
        bars, _ = make_correction_history(peak=100, decline_pct=5.0, down_days=5)
        price = bars[-1]["close"]
        bars.append(make_bar(price * 1.03, low=price * 1.015))
        bars.append(make_bar(price * 1.005))  # low below the Day 1 low, above the correction low
        result = analyze_single_index(bars, "Test")
        assert result["state"] == MarketState.RALLY_ATTEMPT.value
        assert result["rally_attempt"]["current_day_count"] == 2

    def test_no_day1_without_up_close(self):
        """All post-low sessions making new closing lows never start a Day 1."""
        bars, _ = make_correction_history(peak=100, decline_pct=5.0, down_days=5)
        last_close = bars[-1]["close"]
        for _i in range(3):
            last_close *= 0.998
            bars.append(make_bar(last_close))
        result = analyze_single_index(bars, "Test")
        assert result["state"] == MarketState.CORRECTION.value
        assert result["rally_attempt"]["day1_idx"] is None


# ─── FTD detection ───────────────────────────────────────────────────────────


class TestFTD:
    def test_ftd_detected_day4_qualifying(self):
        bars, _, _, _ = make_rally_history(
            decline_pct=5.0,
            down_days=5,
            rally_days=6,
            ftd_day=4,
            ftd_gain_pct=1.5,
            ftd_volume_mult=1.5,
        )
        result = analyze_single_index(bars, "Test")
        assert result["state"] == MarketState.FTD_CONFIRMED.value
        assert result["ftd"]["ftd_detected"] is True
        assert result["ftd"]["ftd_day_number"] == 4
        assert result["ftd"]["gain_pct"] >= 1.25

    def test_ftd_not_detected_low_volume(self):
        """Gain OK but volume lower than the previous day -> no FTD."""
        bars, _, _, _ = make_rally_history(
            decline_pct=5.0,
            down_days=5,
            rally_days=6,
            ftd_day=4,
            ftd_gain_pct=1.5,
            ftd_volume_mult=0.8,
        )
        result = analyze_single_index(bars, "Test")
        assert result["state"] != MarketState.FTD_CONFIRMED.value
        assert result["ftd"]["ftd_detected"] is False

    def test_ftd_window_expired(self):
        """A rally past Day 10 without a qualifying FTD -> RALLY_FAILED."""
        bars, _, _, _ = make_rally_history(
            decline_pct=5.0,
            down_days=5,
            rally_days=12,
            rally_gain_per_day=0.2,
        )
        result = analyze_single_index(bars, "Test")
        assert result["state"] == MarketState.RALLY_FAILED.value
        assert result["market_status"] == "market_in_correction"

    def test_ftd_gain_tier_strong(self):
        bars, _, _, _ = make_rally_history(
            decline_pct=5.0,
            down_days=5,
            rally_days=6,
            ftd_day=5,
            ftd_gain_pct=2.5,
            ftd_volume_mult=1.5,
        )
        result = analyze_single_index(bars, "Test")
        assert result["ftd"]["gain_tier"] == "strong"

    def test_ftd_result_includes_ftd_low(self):
        bars, _, _, _ = make_rally_history(
            decline_pct=5.0,
            down_days=5,
            rally_days=6,
            ftd_day=4,
            ftd_gain_pct=1.5,
            ftd_volume_mult=1.5,
        )
        ftd = analyze_single_index(bars, "Test")["ftd"]
        assert "ftd_low" in ftd
        assert ftd["ftd_low"] > 0

    def test_ftd_volume_uses_point_in_time_average(self):
        """FTD volume comparison must use only pre-FTD data, not post-FTD bars."""
        bars, _, _, _ = make_rally_history(
            peak=100,
            decline_pct=5.0,
            down_days=5,
            rally_days=6,
            ftd_day=4,
            ftd_gain_pct=1.5,
            ftd_volume_mult=1.3,
            base_volume=1_000_000,
        )
        for i in range(10):
            bars.append(make_bar(bars[-1]["close"] * 1.001, volume=3_000_000, date=f"post-{i}"))
        result = analyze_single_index(bars, "Test")
        assert result["state"] == MarketState.FTD_CONFIRMED.value
        # True at FTD time; post-FTD 3M volume would flip it with look-ahead
        assert result["ftd"]["volume_above_avg"] is True


class TestPriceRecovery:
    def test_ftd_tracked_despite_recovery_near_highs(self):
        bars, _, _, _ = make_rally_history(
            peak=100,
            decline_pct=5.0,
            down_days=5,
            rally_days=8,
            rally_gain_per_day=0.6,
            ftd_day=5,
            ftd_gain_pct=1.8,
            ftd_volume_mult=1.5,
        )
        result = analyze_single_index(bars, "Test Recovery")
        assert result["state"] != MarketState.NO_SIGNAL.value

    def test_no_signal_when_no_correction(self):
        bars = [make_bar(100 + (i % 3) * 0.3, date=f"day-{i:03d}") for i in range(30)]
        result = analyze_single_index(bars, "Flat Market")
        assert result["state"] == MarketState.NO_SIGNAL.value
        assert result["market_status"] is None


# ─── Dual-index merge ────────────────────────────────────────────────────────


class TestDualIndexMerge:
    def test_dual_confirmation_both_ftd(self):
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
        result = get_market_state(list(reversed(bars_sp)), list(reversed(bars_nq)))
        assert result["combined_state"] == MarketState.FTD_CONFIRMED.value
        assert result["market_status"] == "confirmed_uptrend"
        assert result["dual_confirmation"] is True

    def test_single_ftd_no_dual(self):
        bars_sp, _, _, _ = make_rally_history(
            peak=100,
            decline_pct=5.0,
            down_days=5,
            rally_days=7,
            ftd_day=5,
            ftd_gain_pct=1.6,
            ftd_volume_mult=1.5,
        )
        bars_nq = [make_bar(200 + i * 0.1, date=f"day-{i:03d}") for i in range(30)]
        result = get_market_state(list(reversed(bars_sp)), list(reversed(bars_nq)))
        assert result["combined_state"] == MarketState.FTD_CONFIRMED.value
        assert result["dual_confirmation"] is False


# ─── FTD lifecycle through the replay ────────────────────────────────────────


class TestFTDLifecycle:
    def _ftd_bars(self):
        return make_rally_history(
            peak=100,
            decline_pct=5.0,
            down_days=5,
            rally_days=7,
            ftd_day=5,
            ftd_gain_pct=1.8,
            ftd_volume_mult=1.5,
        )

    def test_ftd_survives_post_ftd_pullback(self):
        """A 4.5% pullback that holds the correction low leaves the FTD confirmed."""
        bars, _, _, _ = self._ftd_bars()
        last_close = bars[-1]["close"]
        for i in range(10):
            last_close *= 1.008
            bars.append(make_bar(last_close, date=f"post-ftd-rally-{i}"))
        high_price = last_close
        for i in range(5):
            bars.append(make_bar(high_price * (1 - 0.009 * (i + 1)), date=f"pullback-{i}"))
        result = analyze_single_index(bars, "Pullback Test")
        assert result["state"] == MarketState.FTD_CONFIRMED.value

    def test_undercut_returns_ftd_invalidated_with_ftd_data(self):
        bars, _, _, _ = self._ftd_bars()
        correction_low = min(b["low"] for b in bars)
        bars.append(make_bar(correction_low - 1.0, date="invalidation-day"))
        result = analyze_single_index(bars, "Invalidation Test")
        assert result["state"] == MarketState.FTD_INVALIDATED.value
        assert result["market_status"] == "market_in_correction"
        assert result["ftd"]["ftd_detected"] is True

    def test_new_rally_attempt_overrides_old_invalidated_ftd(self):
        bars, _, _, _ = self._ftd_bars()
        correction_low = min(b["low"] for b in bars)
        bars.append(make_bar(correction_low - 2.0, date="invalidation-day"))
        last_close = bars[-1]["close"]
        for i in range(4):
            bars.append(make_bar(last_close * (1 - 0.01 * (i + 1)), date=f"new-decline-{i}"))
        new_low = bars[-1]["close"]
        for i in range(3):
            bars.append(make_bar(new_low * (1 + 0.005 * (i + 1)), date=f"new-rally-{i}"))
        result = analyze_single_index(bars, "New Rally Test")
        assert result["state"] in (
            MarketState.RALLY_ATTEMPT.value,
            MarketState.CORRECTION.value,
            MarketState.FTD_WINDOW.value,
        )

    def test_invalidated_ftd_is_not_resurrected_by_an_older_one(self):
        bars, _, _, _ = self._ftd_bars()
        for i in range(5):
            bars.append(make_bar(bars[-1]["close"] * 1.005, date=f"rise-{i}"))
        # an undercut of the original correction low fails the FTD for good
        bars.append(make_bar(min(b["low"] for b in bars) - 2.0, date="inv-day"))
        result = analyze_single_index(bars, "No Fallback Test")
        assert result["state"] != MarketState.FTD_CONFIRMED.value

    def test_ftd_invalidated_priority_above_correction(self):
        bars_sp, _, _, _ = self._ftd_bars()
        bars_sp.append(make_bar(min(b["low"] for b in bars_sp) - 1.0, date="inv-day"))
        bars_nq, _, _, _ = make_rally_history(peak=200, decline_pct=4.0, down_days=4, rally_days=2)
        result = get_market_state(list(reversed(bars_sp)), list(reversed(bars_nq)))
        assert result["combined_state"] in (
            MarketState.FTD_INVALIDATED.value,
            MarketState.RALLY_ATTEMPT.value,
        )
        assert result["market_status"] == "market_in_correction"
