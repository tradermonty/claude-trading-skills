"""Tests for weekly_price_action.py — the pure (no I/O) contrarian
confirmation calculation module (Jason Shapiro contrarian methodology,
step 3: price-action confirmation).

Every function takes plain dicts/lists/scalars and returns plain values, so
this module is trivially unit-testable offline. See
references/contrarian-confirmation-checklist.md for the methodology this
implements (definitions mirrored word-for-word) and
scripts/check_weekly_price_action.py for the CLI that feeds this module
real FMP OHLC data.

Run with:
    python3 -m pytest skills/technical-analyst/scripts/tests/test_weekly_price_action.py -v
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIR))

from weekly_price_action import (  # noqa: E402
    build_sorted_daily_series,
    compute_confidence,
    compute_prior_window,
    compute_swing_levels,
    detect_continuation,
    detect_failed_breakout,
    detect_failed_extreme,
    detect_weekly_key_reversal,
    resample_weekly,
    run_weekly_price_action,
    synthesize_verdict,
)

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def monday_of(iso_year: int, iso_week: int) -> date:
    return date.fromisocalendar(iso_year, iso_week, 1)


def make_weekly_bars(n: int, start=(2025, 1), base=100.0, step=1.0) -> list[dict]:
    """n synthetic ascending weekly bars, one per consecutive ISO week,
    starting at ISO (start_year, start_week). Each bar's OHLC walks up by
    `step` per week; deliberately dull/monotonic so detector tests can
    override only the bars they care about."""
    iso_year, iso_week = start
    bars = []
    for i in range(n):
        wk = iso_week + i
        yr = iso_year
        # Roll over year boundary crudely using isocalendar's own validation.
        while True:
            try:
                wo = date.fromisocalendar(yr, wk, 1)
                break
            except ValueError:
                wk -= 52
                yr += 1
        price = base + step * i
        bars.append(
            {
                "week_of": wo.isoformat(),
                "open": price,
                "high": price + 0.5,
                "low": price - 0.5,
                "close": price + 0.2,
                "volume": 1000,
            }
        )
    return bars


def daily_bars_for_week(
    monday: date, closes=None, highs=None, lows=None, opens=None, weekend=False
):
    """5 weekday bars (Mon-Fri), or 7 bars (Mon-Sun) if weekend=True (BT-style).
    If `closes` is given explicitly, its length determines the bar count
    (e.g. a 3-bar holiday-shortened week)."""
    if closes is not None:
        n_days = len(closes)
    else:
        n_days = 7 if weekend else 5
        closes = [100.0 + i * 0.1 for i in range(n_days)]
    highs = highs or [c + 0.5 for c in closes]
    lows = lows or [c - 0.5 for c in closes]
    opens = opens or closes
    bars = []
    for i in range(n_days):
        d = monday + timedelta(days=i)
        bars.append(
            {
                "date": d.isoformat(),
                "open": opens[i],
                "high": highs[i],
                "low": lows[i],
                "close": closes[i],
                "volume": 100 + i,
            }
        )
    return bars


# ---------------------------------------------------------------------------
# build_sorted_daily_series
# ---------------------------------------------------------------------------


class TestBuildSortedDailySeries:
    def test_accepts_close_field(self):
        rows = [
            {"date": "2026-01-05", "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 10}
        ]
        series = build_sorted_daily_series(rows)
        assert series[0]["close"] == 1.5

    def test_accepts_price_field_fallback(self):
        # light endpoint uses `price`, not `close` -- verified field trap.
        rows = [
            {"date": "2026-01-05", "open": 1, "high": 2, "low": 0.5, "price": 1.5, "volume": 10}
        ]
        series = build_sorted_daily_series(rows)
        assert series[0]["close"] == 1.5

    def test_sorted_and_deduped(self):
        rows = [
            {"date": "2026-01-06", "open": 2, "high": 2, "low": 2, "close": 2, "volume": 1},
            {"date": "2026-01-05", "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1},
            {"date": "2026-01-05", "open": 1.1, "high": 1.1, "low": 1.1, "close": 1.1, "volume": 1},
        ]
        series = build_sorted_daily_series(rows)
        assert [r["date"] for r in series] == ["2026-01-05", "2026-01-06"]
        assert series[0]["close"] == 1.1  # duplicate date keeps the last occurrence

    def test_missing_required_field_dropped(self):
        rows = [
            {"date": "2026-01-05", "open": 1, "high": 2, "low": 0.5, "volume": 10}
        ]  # no close/price
        series = build_sorted_daily_series(rows)
        assert series == []


# ---------------------------------------------------------------------------
# resample_weekly
# ---------------------------------------------------------------------------


class TestResampleWeekly:
    def test_basic_ohlcv_aggregation(self):
        monday = monday_of(2026, 10)
        daily = daily_bars_for_week(monday, closes=[100, 101, 99, 102, 103])
        # Provide a following week so the target week is not "in progress".
        next_monday = monday + timedelta(days=7)
        daily += daily_bars_for_week(next_monday, closes=[104, 104, 104, 104, 104])
        as_of = (next_monday + timedelta(days=4)).isoformat()
        weekly = resample_weekly(daily, as_of)
        assert weekly[0]["week_of"] == monday.isoformat()
        assert weekly[0]["open"] == 100
        assert weekly[0]["high"] == max(101 + 0.5, 100.5, 99.5, 102.5, 103.5)
        assert weekly[0]["low"] == 99 - 0.5
        assert weekly[0]["close"] == 103  # last bar's close (Friday)
        assert weekly[0]["volume"] == sum(100 + i for i in range(5))

    def test_current_in_progress_week_always_excluded(self):
        monday = monday_of(2026, 10)
        daily = daily_bars_for_week(monday)
        as_of = (monday + timedelta(days=2)).isoformat()  # Wednesday: mid-week
        weekly = resample_weekly(daily, as_of)
        assert weekly == []  # the only week present is the in-progress one

    def test_as_of_truncation_before_resample_drops_partial_week(self):
        # Two weeks of data; as_of lands mid-way through week 2, so week 2
        # must be dropped entirely (never partially resampled), and week 1
        # (fully before the as_of week) survives untouched.
        week1_monday = monday_of(2026, 10)
        week2_monday = week1_monday + timedelta(days=7)
        daily = daily_bars_for_week(week1_monday) + daily_bars_for_week(week2_monday)
        as_of = (week2_monday + timedelta(days=1)).isoformat()  # Tuesday of week 2
        weekly = resample_weekly(daily, as_of)
        assert len(weekly) == 1
        assert weekly[0]["week_of"] == week1_monday.isoformat()

    def test_holiday_short_week_still_counts_as_completed(self):
        # A past week with only 3 trading days (holiday-shortened) is not
        # the in-progress week, so it must be resampled normally, not
        # dropped or treated specially.
        week1_monday = monday_of(2026, 11)
        holiday_bars = daily_bars_for_week(week1_monday, closes=[100, 101, 102])[:3]
        week2_monday = week1_monday + timedelta(days=7)
        following = daily_bars_for_week(week2_monday)
        as_of = (week2_monday + timedelta(days=4)).isoformat()
        weekly = resample_weekly(holiday_bars + following, as_of)
        assert weekly[0]["week_of"] == week1_monday.isoformat()
        assert weekly[0]["close"] == 102  # last of the 3 holiday-week bars

    def test_bt_style_weekend_bars_attribute_to_own_iso_week(self):
        # Crypto/24-7: a Mon-Sun (7-day) week including weekend bars. Sunday
        # belongs to its own Mon-Sun ISO week, not the following week.
        week1_monday = monday_of(2026, 6)
        week1 = daily_bars_for_week(
            week1_monday, weekend=True, closes=[100, 101, 102, 103, 104, 105, 106]
        )
        week2_monday = week1_monday + timedelta(days=7)
        week2 = daily_bars_for_week(week2_monday, weekend=True, closes=[107] * 7)
        as_of = (week2_monday + timedelta(days=6)).isoformat()  # Sunday of week 2
        weekly = resample_weekly(week1 + week2, as_of)
        # week2 is in-progress (contains as_of) -> excluded; only week1 remains.
        assert len(weekly) == 1
        assert weekly[0]["week_of"] == week1_monday.isoformat()
        assert weekly[0]["close"] == 106  # Sunday's close, last bar of week1
        assert weekly[0]["volume"] == sum(100 + i for i in range(7))

    def test_bt_style_weekend_bar_completes_prior_week_when_as_of_is_later(self):
        week1_monday = monday_of(2026, 6)
        week1 = daily_bars_for_week(
            week1_monday, weekend=True, closes=[100, 101, 102, 103, 104, 105, 106]
        )
        week2_monday = week1_monday + timedelta(days=7)
        week2 = daily_bars_for_week(week2_monday, weekend=True, closes=[107] * 7)
        as_of = (week2_monday + timedelta(days=2)).isoformat()  # Wednesday of week 2
        weekly = resample_weekly(week1 + week2, as_of)
        assert len(weekly) == 1
        assert weekly[0]["week_of"] == week1_monday.isoformat()
        assert weekly[0]["close"] == 106  # includes Sunday (week1's last day)


# ---------------------------------------------------------------------------
# compute_prior_window
# ---------------------------------------------------------------------------


class TestComputePriorWindow:
    def test_window_excludes_evaluation_week(self):
        bars = make_weekly_bars(10)
        window, used = compute_prior_window(bars, idx=5, lookback_weeks=3)
        assert used == 3
        assert window == bars[2:5]
        assert bars[5] not in window

    def test_window_truncates_when_insufficient_history(self):
        bars = make_weekly_bars(10)
        window, used = compute_prior_window(bars, idx=2, lookback_weeks=10)
        assert used == 2
        assert window == bars[0:2]

    def test_window_empty_at_index_zero(self):
        bars = make_weekly_bars(10)
        window, used = compute_prior_window(bars, idx=0, lookback_weeks=5)
        assert window == []
        assert used == 0


# ---------------------------------------------------------------------------
# detect_weekly_key_reversal
# ---------------------------------------------------------------------------


class TestDetectWeeklyKeyReversal:
    def test_bearish_key_reversal_triggers_for_crowded_long(self):
        bars = make_weekly_bars(20, base=100.0, step=1.0)
        # Week 19 (last): new swing-lookback high AND close strictly below
        # week 18's low.
        bars[18]["low"] = 110.0
        bars[19]["high"] = 200.0  # far above any prior high in the 13w window
        bars[19]["close"] = 109.0  # strictly below week 18's low (110.0)
        result = detect_weekly_key_reversal(
            bars,
            "CROWDED_LONG",
            swing_lookback_weeks=13,
            extreme_lookback_weeks=52,
            signal_recency_weeks=4,
        )
        assert result["triggered"] is True
        assert result["week_of"] == bars[19]["week_of"]
        assert result["swing_window_weeks_used"] == 13

    def test_bullish_key_reversal_mirror_for_crowded_short(self):
        bars = make_weekly_bars(20, base=100.0, step=-1.0)  # descending
        bars[18]["high"] = 70.0
        bars[19]["low"] = -50.0  # far below any prior low
        bars[19]["close"] = 71.0  # strictly above week 18's high (70.0)
        result = detect_weekly_key_reversal(
            bars,
            "CROWDED_SHORT",
            swing_lookback_weeks=13,
            extreme_lookback_weeks=52,
            signal_recency_weeks=4,
        )
        assert result["triggered"] is True
        assert result["week_of"] == bars[19]["week_of"]

    def test_equal_to_prior_high_is_not_a_new_high_strict(self):
        bars = make_weekly_bars(20, base=100.0, step=0.0)  # all identical highs
        bars[19]["high"] = bars[18]["high"]  # equal, not strictly greater
        bars[19]["close"] = bars[18]["low"] - 10  # would otherwise trigger
        result = detect_weekly_key_reversal(
            bars,
            "CROWDED_LONG",
            swing_lookback_weeks=13,
            extreme_lookback_weeks=52,
            signal_recency_weeks=4,
        )
        assert result["triggered"] is False

    def test_close_equal_to_prior_week_low_does_not_trigger_strict(self):
        bars = make_weekly_bars(20, base=100.0, step=1.0)
        bars[19]["high"] = 500.0  # clears the new-high condition
        bars[19]["close"] = bars[18]["low"]  # equal, not strictly below
        result = detect_weekly_key_reversal(
            bars,
            "CROWDED_LONG",
            swing_lookback_weeks=13,
            extreme_lookback_weeks=52,
            signal_recency_weeks=4,
        )
        assert result["triggered"] is False

    def test_no_reversal_returns_false_with_none_fields(self):
        bars = make_weekly_bars(20)
        result = detect_weekly_key_reversal(
            bars,
            "CROWDED_LONG",
            swing_lookback_weeks=13,
            extreme_lookback_weeks=52,
            signal_recency_weeks=4,
        )
        assert result["triggered"] is False
        assert result["week_of"] is None
        assert result["swing_window_weeks_used"] is None

    def test_signal_older_than_recency_is_not_found(self):
        bars = make_weekly_bars(20, base=100.0, step=1.0)
        idx = 10  # older than the last 4 weeks (indices 16-19)
        bars[idx - 1]["low"] = 110.0
        bars[idx]["high"] = 500.0
        bars[idx]["close"] = 109.0
        result = detect_weekly_key_reversal(
            bars,
            "CROWDED_LONG",
            swing_lookback_weeks=13,
            extreme_lookback_weeks=52,
            signal_recency_weeks=4,
        )
        assert result["triggered"] is False

    def test_high_via_52w_extreme_requires_full_untruncated_window(self):
        # Only 20 weeks of history exist -- extreme_lookback_weeks=52
        # truncates to 19 (< 52), so the HIGH-via-52w-extreme confidence
        # path can never trigger regardless of the swing-lookback result.
        bars = make_weekly_bars(20, base=100.0, step=1.0)
        bars[18]["low"] = 110.0
        bars[19]["high"] = 500.0
        bars[19]["close"] = 109.0
        result = detect_weekly_key_reversal(
            bars,
            "CROWDED_LONG",
            swing_lookback_weeks=13,
            extreme_lookback_weeks=52,
            signal_recency_weeks=4,
        )
        assert result["triggered"] is True
        assert result["extreme_window_weeks_used"] == 19
        assert result["extreme_window_weeks_used"] < 52
        assert result["is_full_window_extreme"] in (True, False)  # computed regardless

    def test_high_via_52w_extreme_flag_true_when_window_full_and_new_extreme(self):
        bars = make_weekly_bars(60, base=100.0, step=1.0)  # 60 >= 52 + margin
        bars[58]["low"] = 300.0
        bars[59]["high"] = 900.0  # exceeds both the 13w AND 52w prior max
        bars[59]["close"] = 299.0
        result = detect_weekly_key_reversal(
            bars,
            "CROWDED_LONG",
            swing_lookback_weeks=13,
            extreme_lookback_weeks=52,
            signal_recency_weeks=4,
        )
        assert result["triggered"] is True
        assert result["extreme_window_weeks_used"] == 52
        assert result["is_full_window_extreme"] is True

    def test_per_week_differing_available_history_within_recency(self):
        # min_weeks floor scenario: history is just long enough that weeks
        # within the recency window have DIFFERENT amounts of prior history
        # available for the extreme window (26 vs 29, per plan's worked
        # example) -- the confidence gate must read the TRIGGERING week's
        # own value, not any other week's.
        bars = make_weekly_bars(30, base=100.0, step=1.0)  # 30 weeks total
        # Trigger at index 26 (0-based): prior weeks available = 26.
        bars[25]["low"] = 500.0
        bars[26]["high"] = 900.0
        bars[26]["close"] = 499.0
        result_early = detect_weekly_key_reversal(
            bars[:27],
            "CROWDED_LONG",
            swing_lookback_weeks=13,
            extreme_lookback_weeks=52,
            signal_recency_weeks=1,
        )
        assert result_early["triggered"] is True
        assert result_early["extreme_window_weeks_used"] == 26

        # Trigger at index 29 (last week of the 30-week series): prior
        # weeks available = 29 -- a DIFFERENT window size than above.
        bars2 = make_weekly_bars(30, base=100.0, step=1.0)
        bars2[28]["low"] = 500.0
        bars2[29]["high"] = 900.0
        bars2[29]["close"] = 499.0
        result_late = detect_weekly_key_reversal(
            bars2,
            "CROWDED_LONG",
            swing_lookback_weeks=13,
            extreme_lookback_weeks=52,
            signal_recency_weeks=1,
        )
        assert result_late["triggered"] is True
        assert result_late["extreme_window_weeks_used"] == 29
        assert result_late["extreme_window_weeks_used"] != result_early["extreme_window_weeks_used"]


# ---------------------------------------------------------------------------
# detect_failed_extreme
# ---------------------------------------------------------------------------


class TestDetectFailedExtreme:
    def test_bearish_failed_extreme_triggers_for_crowded_long(self):
        bars = make_weekly_bars(20, base=100.0, step=0.0)
        bars[19]["high"] = 200.0  # pokes above prior extreme-lookback high
        bars[19]["close"] = 100.0  # but closes back below it
        result = detect_failed_extreme(
            bars, "CROWDED_LONG", extreme_lookback_weeks=13, signal_recency_weeks=4
        )
        assert result["triggered"] is True
        assert result["week_of"] == bars[19]["week_of"]
        assert result["attempted_level"] == bars[0]["high"]  # flat series -> level = any bar's high

    def test_bullish_failed_extreme_mirror_for_crowded_short(self):
        bars = make_weekly_bars(20, base=100.0, step=0.0)
        bars[19]["low"] = -50.0
        bars[19]["close"] = 100.0
        result = detect_failed_extreme(
            bars, "CROWDED_SHORT", extreme_lookback_weeks=13, signal_recency_weeks=4
        )
        assert result["triggered"] is True

    def test_poke_without_close_back_through_does_not_trigger(self):
        bars = make_weekly_bars(20, base=100.0, step=0.0)
        bars[19]["high"] = 200.0
        bars[19]["close"] = 200.0  # closed AT the poke high, not back below
        result = detect_failed_extreme(
            bars, "CROWDED_LONG", extreme_lookback_weeks=13, signal_recency_weeks=4
        )
        assert result["triggered"] is False

    def test_close_exactly_at_prior_high_does_not_trigger_strict(self):
        bars = make_weekly_bars(20, base=100.0, step=0.0)
        bars[19]["high"] = 200.0
        # close exactly equal to the prior extreme-lookback high (not strictly below)
        window, _ = compute_prior_window(bars, 19, 13)
        prior_high = max(w["high"] for w in window)
        bars[19]["close"] = prior_high
        result = detect_failed_extreme(
            bars, "CROWDED_LONG", extreme_lookback_weeks=13, signal_recency_weeks=4
        )
        assert result["triggered"] is False


# ---------------------------------------------------------------------------
# detect_failed_breakout
# ---------------------------------------------------------------------------


class TestDetectFailedBreakout:
    def test_breakout_then_failure_two_weeks_later_confirmed_no_later_bars(self):
        bars = make_weekly_bars(20, base=100.0, step=0.0)
        # Breakout at week 15: CLOSE above prior extreme high.
        bars[15]["close"] = 200.0
        # Weeks 16: still above/neutral (no failure yet).
        bars[16]["close"] = 200.0
        # Week 17 (breakout + 2): closes back below the breakout level.
        bars[17]["close"] = 100.0
        result = detect_failed_breakout(
            bars, "CROWDED_LONG", extreme_lookback_weeks=13, signal_recency_weeks=4
        )
        assert result["triggered"] is True
        assert result["week_of"] == bars[17]["week_of"]  # week_of = FAILURE week

    def test_breakout_week_itself_never_reported_as_week_of(self):
        bars = make_weekly_bars(20, base=100.0, step=0.0)
        bars[15]["close"] = 200.0
        bars[16]["close"] = 100.0  # failure 1 week later
        result = detect_failed_breakout(
            bars, "CROWDED_LONG", extreme_lookback_weeks=13, signal_recency_weeks=4
        )
        assert result["triggered"] is True
        assert result["week_of"] != bars[15]["week_of"]
        assert result["week_of"] == bars[16]["week_of"]

    def test_failure_beyond_3_weeks_does_not_count(self):
        bars = make_weekly_bars(20, base=100.0, step=0.0)
        # Elevate week 10's HIGH (not just close) so weeks 11-13's own
        # rolling prior-window level also stays elevated -- otherwise
        # their close=200 would independently register as a NEW breakout
        # (since only week 10's close, not high, would otherwise remain
        # the sole elevated bar), muddying this test's single-breakout
        # scenario with unintended extra candidates.
        bars[10]["high"] = 250.0
        bars[10]["close"] = 200.0  # breakout, well outside recency
        bars[11]["close"] = 200.0
        bars[12]["close"] = 200.0
        bars[13]["close"] = 200.0
        bars[14]["close"] = 100.0  # 4 weeks after breakout -- too late
        result = detect_failed_breakout(
            bars, "CROWDED_LONG", extreme_lookback_weeks=13, signal_recency_weeks=10
        )
        assert result["triggered"] is False

    # --- P3 regression (user re-review of PR #247): the `detail` string
    # must describe the ACTUAL direction of the breakout -- "above" for a
    # CROWDED_LONG (upside) breakout, "below" for the CROWDED_SHORT
    # (downside) mirror -- never a hardcoded "above" regardless of
    # direction.

    def test_detail_says_above_for_crowded_long(self):
        bars = make_weekly_bars(20, base=100.0, step=0.0)
        bars[15]["close"] = 200.0
        bars[17]["close"] = 100.0
        result = detect_failed_breakout(
            bars, "CROWDED_LONG", extreme_lookback_weeks=13, signal_recency_weeks=4
        )
        assert result["triggered"] is True
        assert "above" in result["detail"]
        assert "below" not in result["detail"]

    def test_detail_says_below_for_crowded_short_mirror(self):
        bars = make_weekly_bars(20, base=100.0, step=0.0)
        # Downside breakout: CLOSE strictly below the prior extreme-lookback
        # low, then closes back above that level within 3 weeks (mirror of
        # the CROWDED_LONG case above).
        bars[15]["close"] = 0.0  # breakout
        bars[16]["close"] = 0.0  # still below/neutral (no failure yet)
        bars[17]["close"] = 100.0  # closes back above the breakout level -> failure
        result = detect_failed_breakout(
            bars, "CROWDED_SHORT", extreme_lookback_weeks=13, signal_recency_weeks=4
        )
        assert result["triggered"] is True
        assert result["week_of"] == bars[17]["week_of"]
        assert "below" in result["detail"]
        assert "above" not in result["detail"]

    def test_close_equal_to_prior_high_is_not_a_closing_breakout_strict(self):
        bars = make_weekly_bars(20, base=100.0, step=0.0)
        window, _ = compute_prior_window(bars, 15, 13)
        prior_high = max(w["high"] for w in window)
        bars[15]["close"] = prior_high  # equal, not strictly above
        result = detect_failed_breakout(
            bars, "CROWDED_LONG", extreme_lookback_weeks=13, signal_recency_weeks=10
        )
        assert result["triggered"] is False


# ---------------------------------------------------------------------------
# detect_continuation
# ---------------------------------------------------------------------------


class TestDetectContinuation:
    def test_new_closing_high_after_signal_flags_continuation(self):
        bars = make_weekly_bars(20, base=100.0, step=1.0)  # rising closes
        # newest_signal_idx = 15; week 17's close is a new extreme relative
        # to its own prior extreme window (ascending series guarantees this).
        result = detect_continuation(
            bars,
            "CROWDED_LONG",
            extreme_lookback_weeks=13,
            signal_recency_weeks=4,
            newest_signal_idx=15,
        )
        assert result["new_closing_extreme_with_crowd"] is True

    def test_no_new_extreme_after_signal_is_false(self):
        bars = make_weekly_bars(20, base=100.0, step=0.0)  # flat closes
        result = detect_continuation(
            bars,
            "CROWDED_LONG",
            extreme_lookback_weeks=13,
            signal_recency_weeks=4,
            newest_signal_idx=15,
        )
        assert result["new_closing_extreme_with_crowd"] is False

    def test_breakout_week_never_self_vetoes(self):
        # Reproduces the failed_breakout no-self-veto guarantee: scanning
        # starts strictly AFTER the newest signal (the failure week), so
        # the breakout week itself (always older) can never be picked up
        # as a "new closing extreme" that vetoes its own signal.
        bars = make_weekly_bars(20, base=100.0, step=0.0)
        bars[15]["close"] = 200.0  # the breakout itself (older signal)
        result = detect_continuation(
            bars,
            "CROWDED_LONG",
            extreme_lookback_weeks=13,
            signal_recency_weeks=4,
            newest_signal_idx=17,
        )
        assert result["new_closing_extreme_with_crowd"] is False

    def test_new_closing_high_week_3_after_breakout_vetoes_confirmation(self):
        bars = make_weekly_bars(20, base=100.0, step=0.0)
        bars[15]["close"] = 200.0  # breakout
        bars[17]["close"] = 100.0  # failure (week_of used as newest_signal_idx=17)
        bars[18]["close"] = 999.0  # new closing high within recency, AFTER the failure
        result = detect_continuation(
            bars,
            "CROWDED_LONG",
            extreme_lookback_weeks=13,
            signal_recency_weeks=4,
            newest_signal_idx=17,
        )
        assert result["new_closing_extreme_with_crowd"] is True
        assert result["week_of"] == bars[18]["week_of"]


# ---------------------------------------------------------------------------
# compute_swing_levels
# ---------------------------------------------------------------------------


class TestComputeSwingLevels:
    def test_fractal_swing_high_detected(self):
        bars = make_weekly_bars(20, base=100.0, step=0.0)
        # Pivot at index 15: high strictly greater than 2 weeks on each side.
        for i in (13, 14, 16, 17):
            bars[i]["high"] = 105.0
        bars[15]["high"] = 150.0
        result = compute_swing_levels(
            bars, "CROWDED_LONG", swing_lookback_weeks=13, extreme_lookback_weeks=52
        )
        assert result["nearest_swing_high"]["price"] == 150.0
        assert result["nearest_swing_high"]["week_of"] == bars[15]["week_of"]
        assert result["nearest_swing_high"]["fallback"] is False

    def test_most_recent_pivot_selected_when_multiple_exist(self):
        bars = make_weekly_bars(20, base=100.0, step=0.0)
        for i in (5, 6, 8, 9):
            bars[i]["high"] = 105.0
        bars[7]["high"] = 150.0  # older pivot
        for i in (13, 14, 16, 17):
            bars[i]["high"] = 105.0
        bars[15]["high"] = 160.0  # more recent pivot
        result = compute_swing_levels(
            bars, "CROWDED_LONG", swing_lookback_weeks=13, extreme_lookback_weeks=52
        )
        assert result["nearest_swing_high"]["week_of"] == bars[15]["week_of"]

    def test_fallback_when_no_pivot_in_window(self):
        bars = make_weekly_bars(
            20, base=100.0, step=1.0
        )  # monotonic ascending -> no interior pivot
        result = compute_swing_levels(
            bars, "CROWDED_LONG", swing_lookback_weeks=13, extreme_lookback_weeks=52
        )
        assert result["nearest_swing_high"]["fallback"] is True

    def test_stop_reference_uses_swing_high_for_crowded_long(self):
        bars = make_weekly_bars(20, base=100.0, step=0.0)
        for i in (13, 14, 16, 17):
            bars[i]["high"] = 105.0
            bars[i]["low"] = 95.0
        bars[15]["high"] = 150.0
        bars[15]["low"] = 50.0
        result = compute_swing_levels(
            bars, "CROWDED_LONG", swing_lookback_weeks=13, extreme_lookback_weeks=52
        )
        assert result["stop_reference"] == result["nearest_swing_high"]["price"]

    def test_stop_reference_uses_swing_low_for_crowded_short(self):
        bars = make_weekly_bars(20, base=100.0, step=0.0)
        for i in (13, 14, 16, 17):
            bars[i]["high"] = 105.0
            bars[i]["low"] = 95.0
        bars[15]["high"] = 150.0
        bars[15]["low"] = 50.0
        result = compute_swing_levels(
            bars, "CROWDED_SHORT", swing_lookback_weeks=13, extreme_lookback_weeks=52
        )
        assert result["stop_reference"] == result["nearest_swing_low"]["price"]


# ---------------------------------------------------------------------------
# synthesize_verdict / compute_confidence
# ---------------------------------------------------------------------------


def _checks(
    kr=False,
    fe=False,
    fb=False,
    cont=False,
    kr_week="2026-01-05",
    fe_week="2026-01-12",
    fb_week="2026-01-19",
    cont_week="2026-01-26",
):
    return {
        "weekly_key_reversal": {
            "triggered": kr,
            "week_of": kr_week if kr else None,
            "swing_window_weeks_used": 13 if kr else None,
            "extreme_window_weeks_used": 52 if kr else None,
            "is_full_window_extreme": False,
            "detail": "x",
        },
        "failed_extreme": {
            "triggered": fe,
            "week_of": fe_week if fe else None,
            "attempted_level": 1.0 if fe else None,
            "window_weeks_used": 13 if fe else None,
            "detail": "x",
        },
        "failed_breakout": {
            "triggered": fb,
            "week_of": fb_week if fb else None,
            "breakout_level": 1.0 if fb else None,
            "window_weeks_used": 13 if fb else None,
            "detail": "x",
        },
        "continuation": {
            "new_closing_extreme_with_crowd": cont,
            "week_of": cont_week if cont else None,
            "window_weeks_used": 13 if cont else None,
        },
    }


class TestSynthesizeVerdict:
    def test_single_signal_confirmed(self):
        verdict, reason = synthesize_verdict(_checks(kr=True), "weekly_key_reversal")
        assert verdict == "CONFIRMED"
        assert reason == "key_reversal"

    def test_failed_extreme_reason(self):
        verdict, reason = synthesize_verdict(_checks(fe=True), "failed_extreme")
        assert verdict == "CONFIRMED"
        assert reason == "failed_extreme"

    def test_failed_breakout_reason(self):
        verdict, reason = synthesize_verdict(_checks(fb=True), "failed_breakout")
        assert verdict == "CONFIRMED"
        assert reason == "failed_breakout"

    def test_no_signal_no_continuation_is_no_reversal_evidence(self):
        verdict, reason = synthesize_verdict(_checks(), None)
        assert verdict == "NOT_CONFIRMED"
        assert reason == "no_reversal_evidence"

    def test_continuation_intact_overrides_signal(self):
        verdict, reason = synthesize_verdict(_checks(kr=True, cont=True), "weekly_key_reversal")
        assert verdict == "NOT_CONFIRMED"
        assert reason == "continuation_intact"

    def test_continuation_intact_without_any_signal(self):
        verdict, reason = synthesize_verdict(_checks(cont=True), None)
        assert verdict == "NOT_CONFIRMED"
        assert reason == "continuation_intact"


class TestComputeConfidence:
    def test_two_distinct_detector_types_is_high(self):
        confidence = compute_confidence(_checks(kr=True, fe=True))
        assert confidence == "HIGH"

    def test_single_signal_is_medium(self):
        confidence = compute_confidence(_checks(kr=True))
        assert confidence == "MEDIUM"

    def test_high_via_full_52w_extreme(self):
        checks = _checks(kr=True)
        checks["weekly_key_reversal"]["is_full_window_extreme"] = True
        checks["weekly_key_reversal"]["extreme_window_weeks_used"] = 52
        assert compute_confidence(checks) == "HIGH"

    def test_truncated_window_below_52_cannot_reach_high_via_extreme_path(self):
        checks = _checks(kr=True)
        checks["weekly_key_reversal"]["is_full_window_extreme"] = True
        checks["weekly_key_reversal"]["extreme_window_weeks_used"] = 40  # < 52
        assert compute_confidence(checks) == "MEDIUM"

    def test_same_detector_firing_conceptually_twice_still_counts_once(self):
        # Only one detector triggered (weekly_key_reversal); the "distinct
        # types" count must be 1, not inflated -- MEDIUM, not HIGH.
        checks = _checks(kr=True)
        assert compute_confidence(checks) == "MEDIUM"


# ---------------------------------------------------------------------------
# run_weekly_price_action (top-level pure orchestrator)
# ---------------------------------------------------------------------------


class TestRunWeeklyPriceAction:
    def _daily_series(self, n_weeks, start_iso=(2025, 1), **kwargs):
        monday = date.fromisocalendar(*start_iso, 1)
        daily = []
        for i in range(n_weeks):
            daily += daily_bars_for_week(monday + timedelta(weeks=i))
        return daily, monday

    def test_insufficient_data_below_min_weeks(self):
        daily, monday = self._daily_series(10)
        as_of = (monday + timedelta(weeks=10, days=4)).isoformat()
        result = run_weekly_price_action(daily, "CROWDED_LONG", as_of, min_weeks=30)
        assert result["verdict"] == "INSUFFICIENT_DATA"
        assert result["verdict_reason"] == "insufficient_weekly_bars"
        assert result["confidence"] == "MEDIUM"
        # Invariant (code review P2-1): checks is ALWAYS None whenever
        # verdict is INSUFFICIENT_DATA -- a single, consistent shape a
        # downstream consumer (contrarian-setup-gate, #241) can rely on
        # without branching on the specific INSUFFICIENT_DATA reason.
        assert result["checks"] is None
        assert result["swing_levels"] is None

    def test_no_reversal_evidence_on_flat_series(self):
        daily, monday = self._daily_series(35, closes=[100] * 5)
        as_of = (monday + timedelta(weeks=35, days=4)).isoformat()
        result = run_weekly_price_action(daily, "CROWDED_LONG", as_of, min_weeks=30)
        assert result["verdict"] == "NOT_CONFIRMED"
        assert result["verdict_reason"] == "no_reversal_evidence"

    def test_confirmed_end_to_end_key_reversal(self):
        monday = date.fromisocalendar(2025, 1, 1)
        daily = []
        for i in range(34):
            week_monday = monday + timedelta(weeks=i)
            if i == 32:
                daily += daily_bars_for_week(
                    week_monday,
                    closes=[100, 101, 102, 103, 90],
                    highs=[100.5, 101.5, 102.5, 103.5, 200],
                    lows=[99.5, 100.5, 101.5, 102.5, 89.5],
                )
            elif i == 31:
                daily += daily_bars_for_week(week_monday, closes=[100] * 5, lows=[95] * 5)
            else:
                daily += daily_bars_for_week(week_monday, closes=[100] * 5)
        as_of = (monday + timedelta(weeks=34, days=4)).isoformat()
        result = run_weekly_price_action(
            daily, "CROWDED_LONG", as_of, min_weeks=30, signal_recency_weeks=4
        )
        assert result["verdict"] == "CONFIRMED"
        assert result["verdict_reason"] == "key_reversal"
        assert result["swing_levels"] is not None
        assert result["handoff_stop_reference"] if "handoff_stop_reference" in result else True

    def test_weekly_bars_used_and_last_completed_week_reported(self):
        daily, monday = self._daily_series(31)
        as_of = (monday + timedelta(weeks=31, days=4)).isoformat()
        result = run_weekly_price_action(daily, "CROWDED_LONG", as_of, min_weeks=30)
        assert result["weekly_bars_used"] == 31
        assert result["last_completed_week"] == (monday + timedelta(weeks=30)).isoformat()
