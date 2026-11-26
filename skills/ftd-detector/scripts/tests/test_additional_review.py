"""Offline state-transition regressions from the additional #766 review."""

import copy

import pytest
from helpers import assign_session_dates, make_bar, make_rally_history
from post_ftd_monitor import assess_post_ftd_health
from rally_tracker import analyze_single_index, get_market_state


def append_rally(bars):
    for day in range(1, 5):
        price = bars[-1]["close"] * (1.021 if day == 4 else 1.003)
        bars.append(make_bar(price, low=price * 0.999, volume=1500000 if day == 4 else 1000000))


def restart_history():
    bars, sl_idx, _, _ = make_rally_history(rally_days=3)
    # Rally failure is an undercut of the correction low (not the Day 1 low).
    bars.append(make_bar(bars[-1]["close"] * 1.003, low=bars[sl_idx]["low"] - 0.2))
    boundary = len(bars) - 1
    append_rally(bars)
    return bars, boundary


def test_intraday_failure_and_recovered_close_allow_a_new_day4_ftd():
    bars, boundary = restart_history()
    assign_session_dates(bars)
    # No new closing-price minimum is available after the original correction.
    assert all(bars[i]["close"] > bars[i - 1]["close"] for i in range(boundary, len(bars)))
    result = analyze_single_index(bars, "Test")
    assert result["state"] == "FTD_CONFIRMED"
    assert result["ftd"]["ftd_day_number"] == 4
    assert result["ftd"]["ftd_date"] == bars[-1]["date"]
    assert result["rally_attempt"]["day1_date"] == bars[boundary + 1]["date"]
    assert result["rally_attempt"]["reset_count"] == 1


def test_repeated_restarts_retain_failed_ftd_evidence_without_reusing_its_days():
    bars, boundary = restart_history()
    previous_ftd_idx = len(bars) - 1
    bars.append(make_bar(bars[-1]["close"] * 1.003, low=bars[boundary]["low"] - 0.1))
    append_rally(bars)
    assign_session_dates(bars)
    result = analyze_single_index(bars, "Test")
    assert result["state"] == "FTD_CONFIRMED"
    assert result["ftd"]["ftd_day_number"] == 4
    assert result["rally_attempt"]["reset_count"] == 2
    assert (
        result["rally_attempt"]["prior_ftd_events"][0]["ftd"]["ftd_date"]
        == bars[previous_ftd_idx]["date"]
    )


def test_restarted_day1_missing_low_is_unavailable():
    bars, boundary = restart_history()
    del bars[boundary + 1]["low"]
    result = analyze_single_index(bars, "Test")
    assert result["data_gap"] is True
    assert result["state"] == "NO_SIGNAL"


@pytest.mark.parametrize("failed_key", ["sp500", "nasdaq"])
@pytest.mark.parametrize("active_days,expected", [(2, "RALLY_ATTEMPT"), (6, "FTD_WINDOW")])
def test_old_failed_event_never_overwrites_other_index_new_rally(failed_key, active_days, expected):
    failed, _, day1, _ = make_rally_history(rally_days=8, ftd_day=5, ftd_gain_pct=2.1)
    failed.append(make_bar(failed[day1]["low"] - 1))
    active, _, _, _ = make_rally_history(rally_days=active_days, ftd_day=None)
    assign_session_dates(failed)
    assign_session_dates(active)
    sp, nq = (failed, active) if failed_key == "sp500" else (active, failed)
    state = get_market_state(sp[::-1], nq[::-1])
    assert state["combined_state"] == expected
    state["ftd_invalidation"] = {"invalidated": True, "ftd_low": 1}
    result = assess_post_ftd_health(copy.deepcopy(state), sp, nq)
    assert result["combined_state"] == expected
    assert result["ftd_index"] is None
    assert "ftd_invalidation" not in result
    assert result[failed_key]["ftd"]["ftd_detected"] is True
    assert result[failed_key]["ftd_lifecycle"]["invalidated"] is True
    assert result["quality_score"]["signal"] == "No FTD"


def test_new_closing_pivot_retains_older_failed_event_separately():
    bars, _, day1, ftd = make_rally_history(rally_days=8, ftd_day=5, ftd_gain_pct=2.1)
    price = bars[day1]["low"] - 2
    for i in range(3):
        bars.append(make_bar(price * (1 - i * 0.01)))
    for _ in range(2):
        bars.append(make_bar(bars[-1]["close"] * 1.003))
    assign_session_dates(bars)
    result = analyze_single_index(bars, "Test")
    assert result["state"] == "RALLY_ATTEMPT"
    previous = result["rally_attempt"]["prior_ftd_events"]
    assert previous[0]["ftd"]["ftd_date"] == bars[ftd]["date"]
    assert previous[0]["status"] == "FTD_INVALIDATED"
