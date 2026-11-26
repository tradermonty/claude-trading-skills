"""The November-2026 report bug, tested with fictional evidence, not live prices."""

import copy

import pytest
from ftd_lifecycle import assess_lifecycle
from helpers import make_bar, make_rally_history
from post_ftd_monitor import assess_post_ftd_health
from rally_tracker import analyze_single_index, get_market_state


def bars():
    return [make_bar(120, low=115), make_bar(110, low=109, volume=900000)]


def test_ftd_low_warning_preserves_rally():
    result = assess_lifecycle(bars(), 0, 100)
    assert result["warning"] is True
    assert result["invalidated"] is False
    assert result["rally_low"] == 100
    assert result["ftd_low"] == 115


@pytest.mark.parametrize("low,failed", [(100, False), (99.99, True)])
def test_intraday_breach_fails_even_when_close_recovers(low, failed):
    data = bars()
    data[1]["low"] = low
    result = assess_lifecycle(data, 0, 100)
    assert result["invalidated"] is failed
    assert data[1]["close"] > 100


@pytest.mark.parametrize("reference", [None, False, 0, float("nan"), float("inf")])
def test_missing_or_invalid_anchor_is_unavailable(reference):
    result = assess_lifecycle(bars(), 0, reference)
    assert result["invalidated"] is None
    assert result["data_gap"] is True


@pytest.mark.parametrize("field", ["low", "close"])
def test_no_candle_fallback_for_missing_evidence(field):
    data = bars()
    del data[1][field]
    result = assess_lifecycle(data, 0, 100)
    assert result["data_gap"] is True


def test_full_state_machine_warns_without_erasing_event_or_sizing_portfolio():
    history, sl_idx, _, ftd = make_rally_history(rally_days=8, ftd_day=5, ftd_gain_pct=2.1)
    anchor = history[sl_idx]["low"]  # the correction low is the rally failure level
    warning_close = (anchor + history[ftd]["low"]) / 2
    history.append(make_bar(warning_close, low=(anchor + warning_close) / 2))
    state = analyze_single_index(history, "Fictional")
    assert state["ftd"]["ftd_detected"] is True
    assert state["state"] == "FTD_CONFIRMED"
    market = get_market_state(list(reversed(history)), [])
    assessed = assess_post_ftd_health(market, history, [])
    assert assessed["ftd_invalidation"]["warning"] is True
    assert assessed["quality_score"]["signal"] == "FTD under pressure"
    assert assessed["quality_score"]["total_score"] > 0
    assert assessed["quality_score"]["exposure_range"] == "Not assessed"

    failed = copy.deepcopy(history)
    failed[-1]["low"] = anchor - 0.01
    state = analyze_single_index(failed, "Fictional")
    assert state["state"] == "FTD_INVALIDATED"
    assert state["ftd"]["ftd_detected"] is True


def test_missing_event_lookup_does_not_leave_json_confirmed():
    data = bars()
    state = {
        "combined_state": "FTD_CONFIRMED",
        "dual_confirmation": False,
        "ftd_index": "S&P 500",
        "sp500": {
            "state": "FTD_CONFIRMED",
            "rally_attempt": {"day1_low": 100},
            "ftd": {
                "ftd_detected": True,
                "ftd_date": "not-in-history",
                "ftd_day_number": 4,
                "gain_pct": 2,
            },
        },
        "nasdaq": {},
    }
    assessed = assess_post_ftd_health(state, data, [])
    assert assessed["data_gap"] is True
    assert assessed["combined_state"] == "NO_SIGNAL"
    assert assessed["ftd_index"] is None
    assert assessed["quality_score"]["signal"] == "Unavailable: data gap"
    assert assessed["quality_score"]["exposure_range"] == "Not assessed"
