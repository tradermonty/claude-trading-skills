"""Stateful forward replay: rally attempt, correction low, FTD lifecycle, data gaps.

All bars are synthetic (built in code). ``B`` builds a bar whose default close sits
in the lower half of its range, so no bar is an upper-half Day 1 by accident.
"""

import copy

import pytest
from ftd_lifecycle import assess_lifecycle
from helpers import assign_session_dates
from rally_tracker import _Replay, analyze_single_index

VOL = 1_000_000


def B(close, low=None, high=None, vol=VOL):
    bar = {
        "open": close,
        "high": close * 1.004 if high is None else high,
        "low": close * 0.997 if low is None else low,
        "close": close,
        "volume": vol,
    }
    # Every synthetic candle must be possible: low <= open/close <= high.
    assert bar["low"] <= min(bar["open"], bar["close"]), bar
    assert max(bar["open"], bar["close"]) <= bar["high"], bar
    return bar


def prefix(low_bar=None):
    """Flat lead-in, peak 106, decline to a closing low of 98.9 (intraday low 98.0).

    The last bar is the correction closing low L (index returned by ``len(p) - 1``).
    """
    bars = [B(105.0) for _ in range(8)] + [B(106.0)]
    bars += [B(104.0), B(102.5), B(101.0), B(99.5)]
    bars.append(low_bar or B(98.9, low=98.0, high=100.0))
    return bars


def run(bars):
    return analyze_single_index(assign_session_dates(copy.deepcopy(bars)), "Synthetic")


def attempt_bars(n_days=3, start=100.5):
    """Day 1 plus n_days - 1 gentle up days after the prefix (no FTD: gains < 1.25%)."""
    out, price = [], start
    for _ in range(n_days):
        out.append(B(price))
        price *= 1.002
    return out


def ftd_history(post_bars=()):
    """Prefix, Day 1-3, an FTD on Day 4, then ``post_bars``."""
    bars = prefix() + attempt_bars(3)
    bars.append(B(bars[-1]["close"] * 1.015, vol=1_500_000))
    return bars + list(post_bars)


# --- 1. acceptance shape ---------------------------------------------------------


def acceptance_bars():
    bars = [B(112.0) for _ in range(8)] + [B(113.0), B(110.0), B(107.5), B(105.0), B(103.0)]
    # L: correction closing low, close in the lower half of its range
    bars.append(B(100.0, low=99.6, high=100.9))
    bars.append(B(104.7, low=103.5, high=105.0, vol=1_300_000))  # Day 1, +4.7%
    bars.append(B(104.9, low=103.3, high=105.2))  # Day 2: low below Day 1 low
    bars.append(B(103.9, low=101.0, high=105.0))  # Day 3: down close, holds the correction low
    return bars


def test_down_close_below_day1_low_keeps_the_attempt_alive():
    bars = acceptance_bars()
    result = run(bars)
    assert result["state"] == "RALLY_ATTEMPT"
    attempt = result["rally_attempt"]
    assert attempt["day1_date"] == assign_session_dates(copy.deepcopy(bars))[-3]["date"]
    assert attempt["current_day_count"] == 3
    assert attempt["reference_low"] == 99.6
    assert attempt["reset_count"] == 0
    assert (
        result["swing_low"]["swing_low_date"]
        == assign_session_dates(copy.deepcopy(bars))[-4]["date"]
    )
    assert result["swing_low"]["swing_low_price"] == 100.0


# --- 2 / 10. no reset mid attempt, the latest bar is never a confirmed low --------


def test_consecutive_down_closes_holding_the_reference_keep_counting():
    bars = prefix() + [B(100.5), B(100.9), B(100.4), B(100.1), B(99.8)]
    for k in range(len(prefix()) + 1, len(bars) + 1):
        result = run(bars[:k])
        day = k - len(prefix())
        assert result["rally_attempt"]["current_day_count"] == day
        expected = "RALLY_ATTEMPT" if day < 4 else "FTD_WINDOW"
        assert result["state"] == expected
        assert (
            result["rally_attempt"]["day1_date"]
            == run(bars[: len(prefix()) + 1])["rally_attempt"]["day1_date"]
        )


def test_day1_low_100_shape_counts_one_to_four_without_reset():
    base = [B(105.0) for _ in range(8)] + [B(106.0), B(104.0), B(102.5), B(101.0), B(99.5)]
    base.append(B(98.9, low=98.0, high=100.0))
    rally = [
        B(102.0, low=100.0, high=102.5),
        B(104.0, low=103.0, high=104.2),
        B(103.0, low=101.0, high=104.0),
        B(104.0, low=103.0, high=104.2),
    ]
    for day in range(1, 5):
        result = run(base + rally[:day])
        assert result["rally_attempt"]["current_day_count"] == day
        assert result["state"] == ("FTD_WINDOW" if day == 4 else "RALLY_ATTEMPT")
        assert result["rally_attempt"]["day1_low"] == 100.0


# --- 1b. Day 1 on the low day or a later day ---------------------------------------


def test_day1_on_the_low_day_with_an_upper_half_close():
    bars = prefix(B(98.9, low=98.0, high=99.0))  # close at 90% of the range
    result = run(bars)
    assert result["state"] == "RALLY_ATTEMPT"
    dates = assign_session_dates(copy.deepcopy(bars))
    assert result["rally_attempt"]["day1_date"] == dates[-1]["date"]
    assert result["rally_attempt"]["current_day_count"] == 1
    assert result["swing_low"]["swing_low_date"] == dates[-1]["date"]
    assert result["rally_attempt"]["reference_low"] == 98.0


def test_new_closing_low_in_the_lower_half_is_not_day1():
    bars = prefix(B(98.9, low=98.0, high=100.0))  # close at 45% of the range
    result = run(bars)
    assert result["state"] == "CORRECTION"
    assert result["rally_attempt"]["day1_idx"] is None


def test_day1_on_a_later_day_up_close():
    bars = prefix() + [B(99.2)]
    result = run(bars)
    dates = assign_session_dates(copy.deepcopy(bars))
    assert result["state"] == "RALLY_ATTEMPT"
    assert result["rally_attempt"]["day1_date"] == dates[-1]["date"]
    assert result["swing_low"]["swing_low_date"] == dates[-2]["date"]


def test_failure_bar_is_never_day1_but_the_next_up_close_is():
    bars = prefix() + [B(100.5), B(100.9)]
    failure = B(103.0, low=97.5, high=103.1)  # undercuts 98.0, closes in the upper half
    result = run(bars + [failure])
    assert result["state"] == "RALLY_FAILED"
    assert result["rally_attempt"]["invalidated"] is True
    assert result["rally_attempt"]["reference_low"] == 98.0  # the failed attempt's own reference
    restarted = run(bars + [failure, B(103.5)])
    assert restarted["state"] == "RALLY_ATTEMPT"
    assert restarted["rally_attempt"]["current_day_count"] == 1
    assert restarted["rally_attempt"]["reference_low"] == 97.5  # low since the failure bar
    assert restarted["rally_attempt"]["reset_count"] == 1


# --- 3. no re-anchoring on a higher low ----------------------------------------------


def test_failure_starts_a_new_segment_and_a_higher_close_never_replaces_its_low():
    bars = prefix() + [B(100.5), B(100.8, low=97.9)]  # Day 2 undercuts 98.0: a new segment
    bars += [B(100.2), B(99.9)]  # new closing lows of the new segment
    result = run(bars)
    assert result["state"] == "RALLY_FAILED"
    assert result["swing_low"]["swing_low_price"] == 99.9
    restarted = run(bars + [B(100.4), B(100.6), B(100.0)])  # higher closes, then a dip
    assert restarted["state"] == "RALLY_ATTEMPT"
    assert restarted["swing_low"]["swing_low_price"] == 99.9
    assert (
        restarted["rally_attempt"]["reference_low"] == 97.9
    )  # the lowest low since the failure bar


# --- 4. undercut is strict ------------------------------------------------------------


@pytest.mark.parametrize("low,state", [(98.0, "RALLY_ATTEMPT"), (97.99, "RALLY_FAILED")])
def test_correction_low_undercut_is_strict(low, state):
    result = run(prefix() + [B(100.5), B(100.9, low=low)])
    assert result["state"] == state


# --- 5. FTD stays confirmed ------------------------------------------------------------


def advance(start_close, n, step=0.001, vol=VOL):
    out, price = [], start_close
    for _ in range(n):
        price *= 1 + step
        out.append(B(price, vol=vol))
    return out


def test_ftd_is_found_on_day_4_to_10():
    result = run(ftd_history())
    assert result["state"] == "FTD_CONFIRMED"
    assert result["ftd"]["ftd_day_number"] == 4
    assert result["ftd"]["ftd_detected"] is True
    assert result["cycle"]["uptrend_status"] == "confirmed"


def test_confirmed_ftd_survives_120_sessions_of_advance():
    base = ftd_history()
    bars = base + advance(base[-1]["close"], 120)
    result = run(bars)
    assert result["state"] == "FTD_CONFIRMED"
    assert result["cycle"]["uptrend_status"] == "confirmed"
    assert result["cycle"]["active_distribution_days"] == []
    assert result["ftd"]["_ftd_idx"] == len(base) - 1
    assert result["ftd_lifecycle"]["invalidated"] is False


# --- 6. distribution plus a qualifying decline ends the confirmed uptrend ---------------


def distribution_bars(start_close, n, step=0.005):
    out, price = [], start_close
    for k in range(n):
        price *= 1 - step
        out.append(B(price, vol=1_100_000 + 100_000 * k))
    return out


def pressured_history(n_dd):
    base = ftd_history()
    peak_bars = advance(base[-1]["close"], 20, step=0.004)
    return base + peak_bars + distribution_bars(peak_bars[-1]["close"], n_dd)


def long_advance_history(sessions=60, step=0.005):
    base = ftd_history()
    return base + advance(base[-1]["close"], sessions, step=step)


def check(bars, **expected):
    result = run(bars)
    got = {
        "state": result["state"],
        "market_status": result["market_status"],
        "uptrend_status": result["cycle"]["uptrend_status"],
    }
    for key, value in expected.items():
        assert got[key] == value, (key, got)
    return result


def test_market_status_maps_every_phase():
    assert run(long_advance_history(60))["market_status"] == "confirmed_uptrend"
    assert run(prefix())["market_status"] == "market_in_correction"
    warm = run([B(105.0 + 0.1 * (k % 2)) for k in range(30)])
    assert warm["state"] == "NO_SIGNAL"
    assert warm["market_status"] is None
    assert run([B(100.0)] * 5)["market_status"] is None  # insufficient data


def test_five_distribution_days_put_the_uptrend_under_pressure():
    result = check(
        pressured_history(5),
        state="FTD_CONFIRMED",
        market_status="uptrend_under_pressure",
        uptrend_status="under_pressure",
    )
    assert len(result["cycle"]["active_distribution_days"]) == 5


def test_four_distribution_days_keep_the_uptrend_confirmed():
    check(pressured_history(4), market_status="confirmed_uptrend", uptrend_status="confirmed")


def test_3pct_pullback_without_distribution_stays_confirmed():
    base = ftd_history()
    peak = advance(base[-1]["close"], 20, step=0.004)
    pullback = [
        B(peak[-1]["close"] * (1 - 0.006 * k), vol=900_000 - 10_000 * k) for k in range(1, 8)
    ]
    assert pullback[-1]["close"] <= peak[-1]["close"] * 0.97
    check(base + peak + pullback, state="FTD_CONFIRMED", market_status="confirmed_uptrend")


def ema_of(bars, period=21):
    """Test-local EMA of closes seeded with the SMA of the first `period` closes."""
    closes = [bar["close"] for bar in bars]
    value = sum(closes[:period]) / period
    k = 2 / (period + 1)
    for close in closes[period:]:
        value = close * k + value * (1 - k)
    return value


def test_six_distribution_days_below_the_ema21_but_above_the_sma50_stay_under_pressure():
    """The shallow-pullback case the 21-EMA trigger used to turn into a correction."""
    base = long_advance_history(60, step=0.005)
    bars = base + distribution_bars(base[-1]["close"], 6, step=0.01)
    result = run(bars)
    sma = result["cycle"]["indicators"]["sma50"]
    assert len(result["cycle"]["active_distribution_days"]) == 6
    assert bars[-1]["close"] < ema_of(bars)  # would have ended the uptrend before
    assert bars[-1]["close"] > sma
    assert result["state"] == "FTD_CONFIRMED"
    assert result["market_status"] == "uptrend_under_pressure"
    assert result["cycle"]["pressure_reasons"] == ["distribution"]


def slow_distribution_history(n_dd):
    base = long_advance_history(80, step=0.002)
    return base + distribution_bars(base[-1]["close"], n_dd, step=0.013)


def test_six_distribution_days_below_the_sma50_is_a_correction():
    bars = slow_distribution_history(6)
    result = run(bars)
    assert result["state"] == "CORRECTION"
    assert result["market_status"] == "market_in_correction"
    assert result["ftd"] is None
    assert result["cycle"]["previous_ftd"]["end_reason"] == "distribution"
    assert result["cycle"]["previous_ftd"]["ftd"]["ftd_day_number"] == 4
    assert result["cycle"]["phase"] == "correction"
    assert result["cycle"]["last_transition"]["from"] == "confirmed"
    # measured from the post-FTD peak, not from the pre-FTD correction
    peak = long_advance_history(80, step=0.002)[-1]["close"]
    assert result["swing_low"]["recent_high_price"] == pytest.approx(peak)
    assert bars[-1]["close"] > peak * 0.9  # the 10% drawdown trigger did not fire


def test_five_distribution_days_below_the_sma50_are_not_a_correction():
    bars = slow_distribution_history(5)
    result = run(bars)
    assert len(result["cycle"]["active_distribution_days"]) == 5
    assert bars[-1]["close"] < result["cycle"]["indicators"]["sma50"]
    assert result["state"] == "FTD_CONFIRMED"
    assert result["market_status"] == "uptrend_under_pressure"


def test_the_distribution_trigger_does_not_need_the_sma50_to_have_been_regained():
    bars = below_sma_ftd_history()
    # the first bar follows the 1.5M FTD volume, so it is not a DD: 7 bars give 6 DDs
    bars += distribution_bars(bars[-1]["close"], 7, step=0.005)
    result = run(bars)
    assert result["cycle"]["regained_50sma_since_ftd"] is None  # no longer confirmed
    assert result["state"] == "CORRECTION"
    assert result["cycle"]["previous_ftd"]["end_reason"] == "distribution"
    before = run(bars[:-1])  # 5 DDs: pressure, and never above the SMA since the FTD
    assert before["cycle"]["regained_50sma_since_ftd"] is False
    assert before["market_status"] == "uptrend_under_pressure"


def test_an_uncomputable_sma50_never_ends_the_uptrend():
    base = ftd_history()  # fewer than 50 bars: no SMA
    bars = base + distribution_bars(base[-1]["close"], 8, step=0.004)
    result = run(bars)
    assert result["cycle"]["indicators"]["sma50_available"] is False
    assert result["state"] == "FTD_CONFIRMED"
    assert result["market_status"] == "uptrend_under_pressure"


def test_sma50_break_without_distribution_is_pressure_not_correction():
    base = long_advance_history(80, step=0.002)
    pullback = [
        B(base[-1]["close"] * (1 - 0.008 * k), vol=900_000 - 10_000 * k) for k in range(1, 9)
    ]
    result = run(base + pullback)
    assert result["cycle"]["indicators"]["sma50_available"] is True
    assert pullback[-1]["close"] < result["cycle"]["indicators"]["sma50"]
    assert result["cycle"]["active_distribution_days"] == []
    assert result["state"] == "FTD_CONFIRMED"
    assert result["market_status"] == "uptrend_under_pressure"


def test_pressure_returns_to_confirmed_when_distribution_ages_off_and_the_sma50_is_regained():
    base = long_advance_history(60, step=0.002)
    pressure = distribution_bars(base[-1]["close"], 5, step=0.004)
    assert run(base + pressure)["market_status"] == "uptrend_under_pressure"
    # Slow recovery: no later high gets 5% above a DD close, so DDs leave by aging only.
    recovery = advance(pressure[-1]["close"], 40, step=0.0005)
    bars = base + pressure + recovery
    first_dd = len(base)  # index of the first distribution day
    still = run(bars[: first_dd + 26])  # last session is 25 sessions after the first DD
    assert still["market_status"] == "uptrend_under_pressure"
    assert len(still["cycle"]["active_distribution_days"]) == 5
    after = run(bars[: first_dd + 27])  # the 26th session: the first DD has expired
    assert len(after["cycle"]["active_distribution_days"]) == 4
    assert after["market_status"] == "confirmed_uptrend"
    result = run(bars)
    assert result["market_status"] == "confirmed_uptrend"
    assert result["cycle"]["previous_ftd"] is None  # no new FTD was needed
    assert result["ftd"]["_ftd_idx"] == len(ftd_history()) - 1


def test_uncomputable_averages_are_false_and_reported():
    result = run(ftd_history())
    assert result["cycle"]["indicators"]["sma50_available"] is False
    assert result["cycle"]["indicators"]["sma50"] is None
    assert result["market_status"] == "confirmed_uptrend"


# --- 7. deep drawdown without distribution ---------------------------------------------------


def test_deep_drawdown_without_distribution_ends_the_confirmed_uptrend():
    base = ftd_history()
    up = advance(base[-1]["close"], 60, step=0.005)
    peak = up[-1]["close"]
    down = [B(peak * (1 - 0.012 * k), vol=900_000 - 5_000 * k) for k in range(1, 10)]
    assert down[-1]["close"] <= peak * 0.9 < down[-2]["close"]
    mid = run(base + up + down[:-1])
    assert mid["state"] == "FTD_CONFIRMED"
    assert mid["cycle"]["active_distribution_days"] == []
    final = run(base + up + down)
    assert final["state"] == "CORRECTION"
    assert final["market_status"] == "market_in_correction"
    assert final["cycle"]["previous_ftd"]["end_reason"] == "deep_drawdown"


def test_correction_low_undercut_wins_over_the_other_triggers():
    base = long_advance_history(60, step=0.005)
    peak = base[-1]["close"]
    crash = B(peak * 0.85, low=90.0, vol=900_000)  # 10% drawdown and an undercut of 98.0
    result = run(base + [crash])
    assert result["state"] == "FTD_INVALIDATED"
    assert result["cycle"]["previous_ftd"] is None


# --- 8. distribution day expiry ------------------------------------------------------------


def one_dd_history(n_after):
    base = ftd_history()
    quiet = advance(base[-1]["close"], 3, step=0.001)
    dd = B(quiet[-1]["close"] * 0.99, vol=1_200_000)
    tail = advance(dd["close"], n_after, step=0.0005)
    return base + quiet + [dd] + tail


def test_distribution_day_expires_after_25_sessions():
    assert len(run(one_dd_history(25))["cycle"]["active_distribution_days"]) == 1
    expired = run(one_dd_history(26))
    assert expired["cycle"]["active_distribution_days"] == []
    assert expired["state"] == "FTD_CONFIRMED"


def test_distribution_day_expires_after_a_5pct_higher_high():
    bars = one_dd_history(2)
    dd_close = bars[-3]["close"]
    assert len(run(bars)["cycle"]["active_distribution_days"]) == 1
    jump = B(dd_close * 1.03, high=dd_close * 1.052)
    assert run(bars + [jump])["cycle"]["active_distribution_days"] == []


# --- 9. post-FTD undercut ---------------------------------------------------------------------


def test_post_ftd_undercut_of_the_correction_low_invalidates_and_lifecycle_agrees():
    base = ftd_history()
    holds = base + [B(base[-1]["close"] * 1.001, low=98.0)]  # equality holds
    assert run(holds)["state"] == "FTD_CONFIRMED"
    bars = base + advance(base[-1]["close"], 5) + [B(100.0, low=97.9)]
    result = run(bars)
    assert result["state"] == "FTD_INVALIDATED"
    assert result["ftd"]["ftd_detected"] is True
    assert result["ftd_lifecycle"]["invalidated"] is True
    assert result["swing_low"]["swing_low_price"] == 98.9
    dated = assign_session_dates(copy.deepcopy(bars))
    direct = assess_lifecycle(dated, result["ftd"]["_ftd_idx"], 98.0)
    assert direct["invalidated"] is True
    assert direct["invalidation_date"] == dated[-1]["date"]
    assert result["rally_attempt"]["prior_ftd_events"][0]["failure_date"] == dated[-1]["date"]


# --- 12. a rise above the old peak does not end a correction; only an FTD does -----------------


def test_rise_above_the_old_peak_without_ftd_stays_in_correction_until_an_ftd():
    gentle = [B(98.9 * 1.012**k) for k in range(1, 13)]  # +1.2% a day: never an FTD
    bars = prefix() + gentle
    assert run(bars[:-2])["state"] == "FTD_WINDOW"  # Day 10, already above the peak
    assert run(bars[:-1])["state"] == "RALLY_FAILED"  # Day 11: the window ended
    steady = bars + [B(bars[-1]["close"] * 1.004**k) for k in range(1, 9)]
    assert steady[-1]["close"] > 106.0 * 1.1
    for k in range(len(prefix()) + 1, len(steady) + 1):
        result = run(steady[:k])
        assert result["market_status"] == "market_in_correction", k
        assert result["state"] != "NO_SIGNAL", k
    assert run(steady)["state"] == "RALLY_FAILED"
    # a down close arms a new count; an FTD on day 4 of it confirms the uptrend
    close = steady[-1]["close"]
    retry = [B(close * 0.999), B(close * 1.002), B(close * 1.004), B(close * 1.006)]
    retry.append(B(retry[-1]["close"] * 1.015, vol=1_500_000))
    assert run(steady + retry[:2])["state"] == "RALLY_ATTEMPT"
    result = run(steady + retry)
    assert result["state"] == "FTD_CONFIRMED"
    assert result["market_status"] == "confirmed_uptrend"
    assert result["ftd"]["ftd_day_number"] == 4


# --- 11. data gaps --------------------------------------------------------------------------------


def long_history():
    lead = [B(105.0 + 0.05 * (k % 2)) for k in range(70)]
    return lead + prefix()[8:] + attempt_bars(3) + [B(105.0, vol=1_500_000)]


@pytest.mark.parametrize("field", ["close", "volume", "low"])
def test_gap_older_than_60_sessions_restarts_the_replay(field):
    bars = long_history()
    bars[10][field] = None
    result = run(bars)
    assert result.get("data_gap") is None
    cycle = result["cycle"]
    assert cycle["restarted_after_gap"] is True
    assert cycle["replay_start_date"] == assign_session_dates(copy.deepcopy(bars))[11]["date"]
    assert cycle["replay_sessions"] == len(bars) - 11


@pytest.mark.parametrize("offset", [10, 59])
def test_gap_inside_the_last_60_sessions_is_a_data_gap(offset):
    bars = long_history()
    bars[len(bars) - offset]["close"] = float("nan")
    result = run(bars)
    assert result["state"] == "NO_SIGNAL"
    assert result["data_gap"] is True
    assert result["error"].startswith("Data gap:")
    assert result["current_price"] is None


def test_clean_history_is_not_marked_restarted():
    result = run(long_history())
    assert result["cycle"]["restarted_after_gap"] is False
    assert result["cycle"]["replay_sessions"] == len(long_history())


# --- point-in-time consistency (no look-ahead) ----------------------------------------------------------


def lifecycle_series():
    bars = [B(105.0 + 0.05 * (k % 2)) for k in range(62)]
    bars += prefix()[8:]
    bars += [B(100.5), B(100.8)]
    bars.append(B(101.0, low=97.9))  # failure: undercuts the correction low
    bars += [B(101.3), B(101.6), B(101.9), B(102.1)]
    bars.append(B(103.9, vol=1_500_000))  # FTD on Day 5 of the restarted attempt
    bars += advance(bars[-1]["close"], 30, step=0.003)
    bars += distribution_bars(bars[-1]["close"], 8)  # distribution and a new correction
    bars += [B(bars[-1]["close"] * 1.004), B(bars[-1]["close"] * 1.008)]
    return assign_session_dates(bars)


def snapshot(state, status, attempt):
    attempt = attempt or {}
    return (
        state,
        status,
        attempt.get("day1_date"),
        attempt.get("current_day_count"),
        attempt.get("reference_low"),
    )


def test_every_prefix_analysis_matches_the_full_replay_after_that_bar():
    history = lifecycle_series()
    trace = {}

    def record(replay, idx):
        state = replay.state()
        trace[idx] = snapshot(
            state.value,
            replay.market_status(),
            replay.rally_attempt(state) if replay.phase != "uptrend_or_none" else None,
        )

    _Replay(history, 0).run(record)
    visited, statuses = set(), set()
    for t in range(60, len(history)):
        result = analyze_single_index(history[: t + 1], "Synthetic")
        got = snapshot(result["state"], result["market_status"], result["rally_attempt"])
        assert got == trace[t], f"look-ahead at bar {t}: prefix {got} vs replay {trace[t]}"
        visited.add(result["state"])
        statuses.add(result["market_status"])
    assert {"RALLY_ATTEMPT", "FTD_WINDOW", "RALLY_FAILED", "FTD_CONFIRMED", "CORRECTION"} <= visited
    assert {"confirmed_uptrend", "market_in_correction", None} <= statuses


# --- IBD sets one market status from either index (October 2019 shape) -------------------------


def scaled(bars, factor):
    out = copy.deepcopy(bars)
    for bar in out:
        for key in ("open", "high", "low", "close"):
            bar[key] *= factor
    return out


def index_history(day4_gain):
    bars = prefix() + attempt_bars(3)
    bars.append(B(bars[-1]["close"] * (1 + day4_gain), vol=1_500_000))
    ftd_idx = len(bars) - 1
    return bars + advance(bars[-1]["close"], 40, step=0.0015), ftd_idx


def test_one_confirmed_index_sets_the_market_status_for_both():
    from rally_tracker import get_market_state

    nasdaq, ftd_idx = index_history(0.015)  # qualifying FTD on Day 4
    sp500, _ = index_history(0.010)  # +1.00% on Day 4: never an FTD
    nasdaq = assign_session_dates(scaled(nasdaq, 2.0))
    sp500 = assign_session_dates(sp500)
    for k in range(ftd_idx + 1, len(nasdaq) + 1):
        state = get_market_state(list(reversed(sp500[:k])), list(reversed(nasdaq[:k])))
        assert state["combined_state"] == "FTD_CONFIRMED", k
        assert state["market_status"] == "confirmed_uptrend", k
        assert state["sp500"]["market_status"] == "market_in_correction", k
        assert state["nasdaq"]["market_status"] == "confirmed_uptrend", k
        assert state["sp500"]["state"] != "NO_SIGNAL", k


def test_combined_market_status_follows_the_data_gap_and_correction_rules():
    from rally_tracker import get_market_state

    quiet = assign_session_dates([B(100.0 + 0.1 * (k % 2)) for k in range(30)])
    correction = assign_session_dates(prefix())
    state = get_market_state(list(reversed(quiet)), list(reversed(correction)))
    assert state["combined_state"] == "CORRECTION"
    assert state["market_status"] == "market_in_correction"
    both_quiet = get_market_state(list(reversed(quiet)), list(reversed(quiet)))
    assert both_quiet["market_status"] is None
    gapped = copy.deepcopy(correction)
    gapped[-2]["close"] = None
    state = get_market_state(list(reversed(quiet)), list(reversed(gapped)))
    assert state["data_gap"] is True
    assert state["market_status"] is None


# --- close below the FTD-day low: pressure, never failure ------------------------------------------


def breach_history(flat_bars):
    base = ftd_history()
    ftd = base[-1]
    breach = B(
        ftd["low"] - 0.05, low=ftd["low"] - 0.2
    )  # close below the FTD-day low, low holds 98.0
    return base + [B(ftd["close"]) for _ in range(flat_bars)] + [breach], breach


def test_close_below_the_ftd_day_low_is_pressure_with_the_warning_set():
    from post_ftd_monitor import assess_post_ftd_health
    from rally_tracker import get_market_state

    bars, breach = breach_history(5)  # too short for the 50-session SMA: no other cause
    assert run(bars[:-1])["market_status"] == "confirmed_uptrend"
    result = run(bars)
    assert result["state"] == "FTD_CONFIRMED"
    assert result["market_status"] == "uptrend_under_pressure"
    assert result["cycle"]["uptrend_status"] == "under_pressure"
    assert result["cycle"]["pressure_reasons"] == ["ftd_low_close_breach"]
    assert result["ftd_lifecycle"]["warning"] is True
    assert result["ftd_lifecycle"]["invalidated"] is False
    dated = assign_session_dates(copy.deepcopy(bars))
    market = get_market_state(list(reversed(dated)), [])
    assessed = assess_post_ftd_health(market, dated, [])
    assert assessed["quality_score"]["signal"] == "FTD under pressure"
    assert assessed["quality_score"]["total_score"] <= 59
    assert assessed["combined_state"] == "FTD_CONFIRMED"


def test_pressure_from_the_ftd_low_breach_returns_to_confirmed_without_a_new_ftd():
    bars, breach = breach_history(41)
    pressured = run(bars)
    indicators = pressured["cycle"]["indicators"]
    assert indicators["sma50_available"] is True
    assert pressured["market_status"] == "uptrend_under_pressure"
    assert "ftd_low_close_breach" in pressured["cycle"]["pressure_reasons"]
    ftd_close = bars[len(ftd_history()) - 1]["close"]
    assert breach["close"] < indicators["sma50"] < ftd_close * 1.01
    # next session closes above the 50-session SMA with no distribution: back to confirmed
    recovered = run(bars + [B(ftd_close * 1.005)])
    assert recovered["state"] == "FTD_CONFIRMED"
    assert recovered["market_status"] == "confirmed_uptrend"
    assert recovered["cycle"]["pressure_reasons"] == []
    assert recovered["ftd_lifecycle"]["warning"] is True  # the warning field stays
    assert recovered["cycle"]["previous_ftd"] is None
    # a later close below the FTD-day low does not re-trigger the one-shot cause
    again = run(bars + [B(ftd_close * 1.005), B(breach["close"], low=breach["low"])])
    assert "ftd_low_close_breach" not in again["cycle"]["pressure_reasons"]


def test_pressure_reasons_name_the_active_cause():
    base = long_advance_history(60, step=0.005)
    bars = base + distribution_bars(base[-1]["close"], 5, step=0.0025)
    assert run(bars)["cycle"]["pressure_reasons"] == ["distribution"]


# --- review findings ----------------------------------------------------------------------------


def test_lower_close_holding_the_reference_lowers_the_closing_low_without_a_reset():
    bars = prefix() + [B(100.5), B(98.5, low=98.1)]
    result = run(bars)
    assert result["state"] == "RALLY_ATTEMPT"
    assert result["rally_attempt"]["current_day_count"] == 2
    assert result["swing_low"]["swing_low_price"] == 98.5
    assert result["rally_attempt"]["reference_low"] == 98.0
    failed = run(bars + [B(98.8, low=97.5)])  # the failure bar starts a new segment (inclusive)
    assert failed["state"] == "RALLY_FAILED"
    assert failed["swing_low"]["swing_low_price"] == 98.8
    assert failed["rally_attempt"]["reference_low"] == 98.0  # the failed attempt's own reference


def test_ftd_gain_is_compared_unrounded():
    base = prefix() + attempt_bars(3)
    close = base[-1]["close"]
    almost = run(base + [B(close * 1.01246, vol=1_500_000)])  # +1.246% rounds to 1.25
    assert almost["state"] == "FTD_WINDOW"
    assert almost["ftd"]["ftd_detected"] is False
    enough = run(base + [B(close * 1.0126, vol=1_500_000)])
    assert enough["state"] == "FTD_CONFIRMED"
    assert enough["ftd"]["gain_tier"] == "minimum"


def test_short_history_with_a_bad_bar_is_a_data_gap_not_insufficient_data():
    from rally_tracker import get_market_state

    short = assign_session_dates([B(100.0) for _ in range(9)])
    short[4]["close"] = None
    single = analyze_single_index(short, "X")
    assert single["data_gap"] is True
    assert single["market_status"] is None
    assert single["error"].startswith("Data gap:")
    clean = analyze_single_index(assign_session_dates([B(100.0) for _ in range(9)]), "X")
    assert clean["error"] == "Insufficient data"
    assert "data_gap" not in clean
    nasdaq = assign_session_dates(ftd_history())
    state = get_market_state(list(reversed(short)), list(reversed(nasdaq)))
    assert state["nasdaq"]["state"] == "FTD_CONFIRMED"
    assert state["data_gap"] is True
    assert state["combined_state"] == "NO_SIGNAL"
    assert state["market_status"] is None


def test_exact_minimum_gain_confirms_despite_float_noise():
    base = prefix() + attempt_bars(3)
    factor = 104.0 / base[-1]["close"]
    for bar in base:
        for key in ("open", "high", "low", "close"):
            if bar.get(key) is not None:
                bar[key] *= factor
    base[-1]["close"] = 104.0
    # 104.00 -> 105.30 is exactly +1.25% but computes as 1.2499999999999973.
    result = run(base + [B(105.30, vol=1_500_000)])
    assert result["state"] == "FTD_CONFIRMED"
    assert result["ftd"]["gain_tier"] == "minimum"


# --- the failure reference is the low of the pullback the attempt started from ----------------------


def test_acceptance_shape_with_an_earlier_failed_attempt():
    """The correction low L follows a failed attempt; Day 1 is next; the reference is L's low."""
    bars = prefix() + [B(100.5)]  # attempt 1 (Day 1) ...
    bars.append(B(100.0, low=97.5))  # ... fails: new segment starts at this bar
    bars += [B(99.0), B(97.5)]
    bars.append(B(96.0, low=95.5, high=97.0))  # L: the correction low, lower-half close
    bars.append(B(97.2, low=96.0, high=97.5))  # Day 1
    bars.append(B(97.4, low=95.8, high=97.6))  # Day 2: below the Day 1 low, above L's low
    bars.append(B(96.9, low=95.6, high=97.5))  # Day 3: down close that holds
    result = run(bars)
    dated = assign_session_dates(copy.deepcopy(bars))
    assert result["state"] == "RALLY_ATTEMPT"
    assert result["rally_attempt"]["current_day_count"] == 3
    assert result["rally_attempt"]["day1_date"] == dated[-3]["date"]
    assert result["rally_attempt"]["reference_low"] == 95.5
    assert result["rally_attempt"]["reference_low_date"] == dated[-4]["date"]
    assert result["swing_low"]["swing_low_date"] == dated[-4]["date"]


# --- the Day 4-10 window: an attempt expires on Day 11 but keeps its reference ------------------------


def expired_history(n_days=10):
    """L's low (98.0) is the reference; Day 1-10 without an FTD; then the Day-11 bar."""
    return prefix() + attempt_bars(n_days)


def test_ten_non_qualifying_days_stay_in_the_window_and_day_11_expires_the_attempt():
    bars = expired_history()
    window = run(bars)
    assert window["state"] == "FTD_WINDOW"
    assert window["rally_attempt"]["current_day_count"] == 10
    down = B(bars[-1]["close"] * 0.999)  # Day 11
    expired = run(bars + [down])
    assert expired["state"] == "RALLY_FAILED"
    assert expired["market_status"] == "market_in_correction"
    assert expired["rally_attempt"]["current_day_count"] == 11
    assert expired["rally_attempt"]["invalidation_reason"] == "No follow-through day by Day 10"
    assert expired["rally_attempt"]["reference_low"] == 98.0  # not moved
    assert expired["ftd"] is None or expired["ftd"]["ftd_detected"] is False


def test_a_day_11_gain_on_higher_volume_is_not_an_ftd():
    bars = expired_history()
    gain = B(bars[-1]["close"] * 1.014, vol=1_500_000)
    result = run(bars + [gain])
    assert result["state"] == "RALLY_FAILED"
    assert "ftd" not in result or result["ftd"] is None or not result["ftd"]["ftd_detected"]
    assert "late" not in (result["ftd"] or {})


def test_the_expiry_bar_is_never_day1_and_a_down_close_arms_the_new_count():
    bars = expired_history()
    up11 = B(bars[-1]["close"] * 1.003)  # an up close on Day 11 is not Day 1
    assert run(bars + [up11])["state"] == "RALLY_FAILED"
    up12 = B(up11["close"] * 1.003)  # still disarmed: no down close yet
    assert run(bars + [up11, up12])["state"] == "RALLY_FAILED"
    down12 = B(up11["close"] * 0.999)  # a down close arms the count ...
    assert run(bars + [up11, down12])["state"] == "RALLY_FAILED"
    restarted = run(bars + [up11, down12, B(down12["close"] * 1.003)])  # ... the next up close
    assert restarted["state"] == "RALLY_ATTEMPT"
    assert restarted["rally_attempt"]["current_day_count"] == 1


def test_a_down_close_on_the_expiry_bar_arms_so_the_next_up_close_is_day1():
    bars = expired_history()
    down11 = B(bars[-1]["close"] * 0.999)
    assert run(bars + [down11])["state"] == "RALLY_FAILED"
    restarted = run(bars + [down11, B(down11["close"] * 1.003)])
    dated = assign_session_dates(copy.deepcopy(bars + [down11, B(1.0)]))
    assert restarted["state"] == "RALLY_ATTEMPT"
    assert restarted["rally_attempt"]["current_day_count"] == 1
    assert restarted["rally_attempt"]["day1_date"] == dated[-1]["date"]
    assert restarted["rally_attempt"]["reset_count"] == 1  # the expiry counts


def test_expiry_keeps_the_reference_and_only_an_undercut_of_it_fails_the_next_attempt():
    bars = expired_history()
    down11 = B(bars[-1]["close"] * 0.999)
    day1 = B(down11["close"] * 1.003, low=down11["close"] * 1.0)  # shallow pre-expiry-style low
    attempt = run(bars + [down11, day1])
    dated = assign_session_dates(copy.deepcopy(prefix()))
    assert attempt["state"] == "RALLY_ATTEMPT"
    assert attempt["rally_attempt"]["reference_low"] == 98.0
    assert attempt["rally_attempt"]["reference_low_date"] == dated[-1]["date"]  # L's date
    # a dip below the shallow pullback low but above the reference does not fail it
    dip = B(day1["close"] * 1.001, low=99.0)
    still = run(bars + [down11, day1, dip])
    assert still["state"] == "RALLY_ATTEMPT"
    assert still["rally_attempt"]["current_day_count"] == 2
    assert still["rally_attempt"]["reference_low"] == 98.0
    # a dip below the reference fails it and restarts the segment
    broken = B(day1["close"], low=97.9)
    failed = run(bars + [down11, day1, dip, broken])
    assert failed["state"] == "RALLY_FAILED"
    assert "below rally low" in failed["rally_attempt"]["invalidation_reason"]
    restarted = run(bars + [down11, day1, dip, broken, B(day1["close"] * 1.002)])
    assert restarted["state"] == "RALLY_ATTEMPT"
    assert (
        restarted["rally_attempt"]["reference_low"] == 97.9
    )  # the segment restarted at the failure


def test_an_undercut_after_the_expiry_before_a_new_day1_restarts_the_segment():
    bars = expired_history()
    down11 = B(bars[-1]["close"] * 0.999)
    undercut = B(down11["close"] * 1.001, low=97.5)  # no attempt is active: the segment restarts
    after = run(bars + [down11, undercut, B(down11["close"] * 1.004)])
    assert after["state"] == "RALLY_ATTEMPT"
    assert after["rally_attempt"]["reference_low"] == 97.5


def test_a_qualifying_gain_on_day_5_of_the_new_count_confirms():
    bars = expired_history()
    down11 = B(bars[-1]["close"] * 0.999)
    count = [B(down11["close"] * 1.003)]  # new Day 1
    for _ in range(3):  # days 2-4
        count.append(B(count[-1]["close"] * 1.002))
    count.append(B(count[-1]["close"] * 1.015, vol=1_500_000))  # day 5
    result = run(bars + [down11] + count)
    assert result["state"] == "FTD_CONFIRMED"
    assert result["ftd"]["ftd_day_number"] == 5
    assert result["ftd"]["ftd_detected"] is True
    assert result["rally_attempt"]["reference_low"] == 98.0
    assert "late" not in result["ftd"]


def old_deep_low_series():
    """Synthetic 2019 shape: a deep low months earlier, an FTD and a long advance, then a
    10% drawdown from the post-FTD peak enters a new correction whose low is P1."""
    bars = [B(130.0 + 0.1 * (k % 2)) for k in range(40)]
    price = 130.0
    for _ in range(10):  # deep decline: close 80, low 79
        price -= 5.0
        bars.append(B(price))
    bars[-1] = B(80.0, low=79.0, high=80.5)
    close = 80.0
    for _k in range(3):  # Day 1-3
        close *= 1.004
        bars.append(B(close))
    close *= 1.015  # Day 4: FTD
    bars.append(B(close, vol=1_500_000))
    for _ in range(60):
        close *= 1.005
        bars.append(B(close))
    peak = close
    for k in range(1, 10):  # decreasing volume: no distribution; -10% ends the uptrend
        bars.append(B(peak * (1 - 0.012 * k), vol=900_000 - 5_000 * k))
    last = bars[-1]["close"]
    bars[-1] = B(last, low=last - 0.5, high=last + 1.0, vol=bars[-1]["volume"])  # P1
    return bars


def test_2019_shape_fails_the_attempt_on_the_recent_low_and_confirms_the_restart():
    bars = old_deep_low_series()
    deep_low = 79.0
    p1_low = bars[-1]["low"]
    entered = run(bars)
    assert entered["state"] == "CORRECTION"
    assert entered["cycle"]["previous_ftd"]["end_reason"] == "deep_drawdown"
    # attempt A: Day 1 and then gentle days, no FTD; its reference is P1, not the deep low
    day1 = bars[-1]["close"] * 1.004
    a_days = [B(day1 * 1.002**k) for k in range(9)]
    bars_a = bars + a_days
    attempt = run(bars_a)
    assert attempt["state"] == "FTD_WINDOW"
    assert attempt["rally_attempt"]["current_day_count"] == 9
    assert attempt["rally_attempt"]["reference_low"] == p1_low
    assert attempt["rally_attempt"]["reference_low"] > deep_low + 1
    # day 10: a pullback undercuts P1, so A fails on the recent low
    # a down close that holds above its own low, with an intraday low 0.5 under P1's low
    failure = B(p1_low + 0.1, low=p1_low - 0.5, high=a_days[-1]["close"])
    assert failure["close"] < a_days[-1]["close"]
    failed = run(bars_a + [failure])
    assert failed["state"] == "RALLY_FAILED"
    assert failed["rally_attempt"]["current_day_count"] == 10
    assert "below rally low" in failed["rally_attempt"]["invalidation_reason"]
    # the next bar closes in the upper half: Day 1 of attempt B
    day1_b = B(failure["close"] * 1.002, low=failure["low"] + 0.05, high=failure["close"] * 1.0025)
    assert (day1_b["close"] - day1_b["low"]) / (day1_b["high"] - day1_b["low"]) >= 0.5
    b_bars = [day1_b] + [B(day1_b["close"] * 1.002**k) for k in range(1, 5)]
    started = run(bars_a + [failure] + b_bars[:1])
    assert started["state"] == "RALLY_ATTEMPT"
    assert started["rally_attempt"]["current_day_count"] == 1
    assert started["rally_attempt"]["reference_low"] == failure["low"]
    # +1.34% on higher volume on day 6 of B: FTD
    day6 = B(b_bars[-1]["close"] * 1.0134, vol=1_500_000)
    confirmed = run(bars_a + [failure] + b_bars + [day6])
    assert confirmed["state"] == "FTD_CONFIRMED"
    assert confirmed["ftd"]["ftd_day_number"] == 6
    assert confirmed["rally_attempt"]["reference_low"] == failure["low"]
    assert confirmed["rally_attempt"]["reference_low"] != deep_low
    assert confirmed["rally_attempt"]["reference_low"] != p1_low


# --- maintainer review of PR #893 ----------------------------------------------------------------


def gap_history():
    lead = [B(105.0 + 0.05 * (k % 2)) for k in range(53)]
    bars = lead + prefix() + attempt_bars(3)
    bars.append(B(bars[-1]["close"] * 1.015, vol=1_500_000))  # FTD at idx 70
    assert len(bars) == 71
    bars += advance(bars[-1]["close"], 200, step=0.0005)
    assert len(bars) == 271
    return bars


def test_gap_restart_that_ends_in_warm_up_is_a_data_gap_not_no_signal():
    from rally_tracker import get_market_state

    bars = gap_history()
    healed = run(bars)
    assert healed["state"] == "FTD_CONFIRMED"
    gapped_bars = copy.deepcopy(bars)
    gapped_bars[150]["volume"] = 0  # older than 60 sessions: the replay restarts after it
    gapped = run(gapped_bars)
    assert gapped["cycle"]["restarted_after_gap"] is True
    assert gapped["state"] == "NO_SIGNAL"
    assert gapped["market_status"] is None
    assert gapped["data_gap"] is True
    assert gapped["error"].startswith("Data gap: replay restarted after a bad bar on")
    # a clean confirmed other index must not turn the combined result into a confirmation
    nasdaq = assign_session_dates(ftd_history())
    sp500 = assign_session_dates(gapped_bars)
    state = get_market_state(list(reversed(sp500)), list(reversed(nasdaq)))
    assert state["nasdaq"]["state"] == "FTD_CONFIRMED"
    assert state["combined_state"] == "NO_SIGNAL"
    assert state["data_gap"] is True
    assert state["market_status"] is None


def test_the_bar_that_ends_an_uptrend_is_never_day1():
    base = ftd_history()
    up = advance(base[-1]["close"], 60, step=0.005)
    peak = up[-1]["close"]
    down = [B(peak * (1 - 0.012 * k), vol=900_000 - 5_000 * k) for k in range(1, 9)]
    close = peak * 0.895  # -10.5%: a new closing low with an upper-half close
    last = B(close, low=close - 1.0, high=close + 0.2, vol=850_000)
    assert (last["close"] - last["low"]) / (last["high"] - last["low"]) >= 0.5
    result = run(base + up + down + [last])
    assert result["state"] == "CORRECTION"
    assert result["rally_attempt"]["day1_idx"] is None
    assert result["cycle"]["last_transition"]["from"] == "confirmed"
    assert result["cycle"]["last_transition"]["to"] == "correction"
    assert result["cycle"]["previous_ftd"]["end_reason"] == "deep_drawdown"
    # the next up close is the earliest Day 1
    nxt = run(base + up + down + [last, B(close * 1.004)])
    assert nxt["state"] == "RALLY_ATTEMPT"
    assert nxt["rally_attempt"]["current_day_count"] == 1


def test_drawdown_of_exactly_10_percent_ends_the_uptrend():
    base = ftd_history()
    up = advance(base[-1]["close"], 60, step=0.005)
    peak = up[-1]["close"]
    exact = run(base + up + [B(peak * (1 - 10.0 / 100), vol=900_000)])
    assert exact["state"] == "CORRECTION"
    assert exact["cycle"]["previous_ftd"]["end_reason"] == "deep_drawdown"
    inside = run(base + up + [B(peak * (1 - 9.99 / 100), vol=900_000)])
    assert inside["state"] == "FTD_CONFIRMED"


def test_equal_volume_is_not_a_distribution_day():
    base = ftd_history()
    peak = advance(base[-1]["close"], 20, step=0.004)
    close = peak[-1]["close"]
    equal = []
    for _ in range(5):  # down >= 0.2% each, but volume only equal to the previous session
        close *= 0.995
        equal.append(B(close, vol=VOL))
    result = run(base + peak + equal)
    assert result["cycle"]["active_distribution_days"] == []
    assert result["market_status"] == "confirmed_uptrend"
    higher = [dict(bar, volume=VOL + 1 + i) for i, bar in enumerate(equal)]
    counted = run(base + peak + higher)
    assert len(counted["cycle"]["active_distribution_days"]) == 5


def test_pressure_does_not_return_while_the_close_is_below_the_sma50():
    base = long_advance_history(80, step=0.002)
    pullback = [
        B(base[-1]["close"] * (1 - 0.008 * k), vol=900_000 - 10_000 * k) for k in range(1, 9)
    ]
    bars = base + pullback
    entered, below_checked = False, 0
    for k in range(len(base), len(bars) + 1):
        result = run(bars[:k])
        sma = result["cycle"]["indicators"]["sma50"]
        if result["market_status"] == "uptrend_under_pressure":
            entered = True
        if entered and sma is not None and bars[k - 1]["close"] < sma:
            below_checked += 1
            assert result["market_status"] == "uptrend_under_pressure", k
            assert result["cycle"]["active_distribution_days"] == []  # at most 4 DDs
    assert entered and below_checked >= 2


# --- the 50-SMA is a pressure cause only after the index has been above it since the FTD ------------


def below_sma_ftd_history(extra=()):
    """An FTD (idx 70) that closes below a computable 50-session SMA."""
    lead = [B(105.0 + 0.05 * (k % 2)) for k in range(53)]
    bars = lead + prefix() + attempt_bars(3)
    bars.append(B(bars[-1]["close"] * 1.015, vol=1_500_000))
    assert len(bars) == 71
    return bars + list(extra)


def test_ftd_below_the_sma50_is_confirmed_on_the_ftd_day_and_stays_so_without_distribution():
    bars = below_sma_ftd_history()
    on_ftd_day = run(bars)
    assert on_ftd_day["cycle"]["indicators"]["sma50_available"] is True
    assert on_ftd_day["cycle"]["indicators"]["sma50"] > bars[-1]["close"]
    assert on_ftd_day["state"] == "FTD_CONFIRMED"
    assert on_ftd_day["market_status"] == "confirmed_uptrend"
    assert on_ftd_day["cycle"]["regained_50sma_since_ftd"] is False
    close = bars[-1]["close"]
    flat = [B(close) for _ in range(6)]  # still below the SMA, no distribution
    later = run(bars + flat)
    assert later["cycle"]["indicators"]["sma50"] > close
    assert later["market_status"] == "confirmed_uptrend"
    assert later["cycle"]["pressure_reasons"] == []
    assert later["cycle"]["regained_50sma_since_ftd"] is False


def test_below_the_sma50_is_pressure_after_a_close_above_it_since_the_ftd():
    bars = below_sma_ftd_history()
    close = bars[-1]["close"]
    rise = advance(close, 12, step=0.005)  # climbs above the SMA
    regained = run(bars + rise)
    assert regained["cycle"]["regained_50sma_since_ftd"] is True
    assert regained["market_status"] == "confirmed_uptrend"
    top = rise[-1]["close"]
    dip = [B(top * (1 - 0.01 * k), vol=900_000 - 10_000 * k) for k in range(1, 6)]
    result = run(bars + rise + dip)
    sma = result["cycle"]["indicators"]["sma50"]
    assert dip[-1]["close"] < sma
    assert dip[-1]["close"] > bars[-1]["low"]  # the FTD-day low still holds
    assert result["cycle"]["active_distribution_days"] == []
    assert result["state"] == "FTD_CONFIRMED"
    assert result["market_status"] == "uptrend_under_pressure"
    assert result["cycle"]["pressure_reasons"] == ["below_50sma"]


def test_sma50_that_cannot_be_computed_is_never_a_cause():
    result = run(ftd_history())
    assert result["cycle"]["indicators"]["sma50_available"] is False
    assert result["cycle"]["regained_50sma_since_ftd"] is False
    assert result["market_status"] == "confirmed_uptrend"
    assert result["cycle"]["pressure_reasons"] == []
