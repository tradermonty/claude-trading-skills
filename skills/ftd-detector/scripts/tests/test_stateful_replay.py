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
    return {
        "open": close,
        "high": close * 1.004 if high is None else high,
        "low": close * 0.997 if low is None else low,
        "close": close,
        "volume": vol,
    }


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
    assert result["rally_attempt"]["reference_low"] == 97.5
    restarted = run(bars + [failure, B(103.5)])
    assert restarted["state"] == "RALLY_ATTEMPT"
    assert restarted["rally_attempt"]["current_day_count"] == 1
    assert restarted["rally_attempt"]["reset_count"] == 1


# --- 3. no re-anchoring on a higher low ----------------------------------------------


def test_higher_closing_low_after_failure_does_not_replace_the_correction_low():
    bars = prefix() + [B(100.5), B(100.8, low=97.9)]  # Day 2 undercuts 98.0
    bars += [B(100.2), B(99.9)]  # higher lows than 98.9, still inside the correction
    result = run(bars)
    assert result["state"] == "RALLY_FAILED"
    assert result["swing_low"]["swing_low_price"] == 98.9
    assert (
        result["swing_low"]["swing_low_date"]
        == assign_session_dates(copy.deepcopy(prefix()))[-1]["date"]
    )
    restarted = run(bars + [B(100.4)])
    assert restarted["state"] == "RALLY_ATTEMPT"
    assert restarted["swing_low"]["swing_low_price"] == 98.9
    assert restarted["rally_attempt"]["reference_low"] == 97.9


def test_higher_close_after_exhaustion_needs_a_down_close_to_rearm():
    bars = prefix() + [B(100.0 * 1.003**k) for k in range(11)]  # Day 1-11: no FTD
    result = run(bars)
    assert result["state"] == "RALLY_FAILED"
    assert result["rally_attempt"]["current_day_count"] == 11
    up = run(bars + [B(bars[-1]["close"] * 1.002)])
    assert up["state"] == "RALLY_FAILED"  # still disarmed: an up close is not Day 1
    down_then_up = run(bars + [B(bars[-1]["close"] * 0.999), B(bars[-1]["close"] * 1.001)])
    assert down_then_up["state"] == "RALLY_ATTEMPT"
    assert down_then_up["swing_low"]["swing_low_price"] == 98.9


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


def test_six_distribution_days_with_the_close_above_the_ema21_stay_under_pressure():
    base = long_advance_history(60, step=0.005)
    bars = base + distribution_bars(base[-1]["close"], 6, step=0.0025)
    result = run(bars)
    assert len(result["cycle"]["active_distribution_days"]) == 6
    assert result["cycle"]["indicators"]["ema21_available"] is True
    assert bars[-1]["close"] > result["cycle"]["indicators"]["ema21"]
    assert result["state"] == "FTD_CONFIRMED"
    assert result["market_status"] == "uptrend_under_pressure"


def test_six_distribution_days_with_the_close_below_the_ema21_is_a_correction():
    base = long_advance_history(60, step=0.005)
    bars = base + distribution_bars(base[-1]["close"], 9, step=0.009)
    before = run(bars[: len(base) + 5])
    assert before["market_status"] == "uptrend_under_pressure"  # 5 DDs: pressure only
    result = run(bars)
    assert result["state"] == "CORRECTION"
    assert result["market_status"] == "market_in_correction"
    assert result["ftd"] is None
    assert result["cycle"]["previous_ftd"]["end_reason"] == "distribution"
    assert result["cycle"]["previous_ftd"]["ftd"]["ftd_day_number"] == 4
    assert result["cycle"]["phase"] == "correction"
    # measured from the post-FTD peak, not from the pre-FTD correction
    assert result["swing_low"]["recent_high_price"] == pytest.approx(base[-1]["close"])


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
    assert run(bars[:-2])["state"] == "FTD_WINDOW"  # Day 10, price already above the peak
    assert run(bars[:-1])["state"] == "RALLY_FAILED"  # Day 11: window exhausted
    steady = bars + [B(bars[-1]["close"] * 1.004**k) for k in range(1, 9)]
    assert steady[-1]["close"] > 106.0 * 1.1
    for k in range(len(prefix()) + 1, len(steady) + 1):
        result = run(steady[:k])
        assert result["market_status"] == "market_in_correction", k
        assert result["state"] != "NO_SIGNAL", k
    assert run(steady)["state"] == "RALLY_FAILED"
    # a down close re-arms; a later qualifying FTD in the new attempt confirms the uptrend
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
    failed = run(bars + [B(98.8, low=97.5)])  # a later failure closing higher cannot raise it
    assert failed["state"] == "RALLY_FAILED"
    assert failed["swing_low"]["swing_low_price"] == 98.5


def test_down_close_on_the_exhaustion_bar_rearms_so_the_next_up_close_is_day1():
    bars = prefix() + attempt_bars(10)  # Day 1-10, no qualifying FTD
    assert run(bars)["state"] == "FTD_WINDOW"
    exhausted = bars + [B(bars[-1]["close"] * 0.999)]  # Day 11: down close
    result = run(exhausted)
    assert result["state"] == "RALLY_FAILED"  # the exhaustion bar is never Day 1
    assert result["rally_attempt"]["current_day_count"] == 11
    restarted = run(exhausted + [B(exhausted[-1]["close"] * 1.003)])  # Day 12: up close
    dated = assign_session_dates(copy.deepcopy(exhausted + [B(1.0)]))
    assert restarted["state"] == "RALLY_ATTEMPT"
    assert restarted["rally_attempt"]["current_day_count"] == 1
    assert restarted["rally_attempt"]["day1_date"] == dated[-1]["date"]
    assert restarted["rally_attempt"]["reset_count"] == 1


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
