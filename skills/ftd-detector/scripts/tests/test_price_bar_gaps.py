"""Issue #655: a missing or non-finite OHLCV value must never become 0.

Every gap case is run twice: once with the field deleted and once with NaN.
The detector either keeps its clean result (the bad bar is not read) or reports
the derived signal as explicitly unavailable, with an int score of 0.
"""

import copy
import math

import pytest
from helpers import (
    assign_session_dates,
    make_bar,
    make_correction_history,
    make_long_ftd_history,
    make_rally_history,
)
from post_ftd_monitor import (
    assess_post_ftd_health,
    calculate_ftd_quality_score,
    check_ftd_invalidation,
    count_post_ftd_distribution,
    detect_power_trend,
)
from rally_tracker import (
    _is_swing_low,
    analyze_single_index,
    calculate_avg_volume,
    detect_ftd,
    find_swing_low,
    get_market_state,
    track_rally_attempt,
)


def _missing(bar, field):
    bar.pop(field, None)


def _nan(bar, field):
    bar[field] = math.nan


def _zero(bar, field):
    # For ^GSPC/QQQ a zero close or a zero session volume is provider missing data.
    bar[field] = 0


BREAKERS = pytest.mark.parametrize(
    "breaker", [_missing, _nan, _zero], ids=["missing", "nan", "zero"]
)


def broken(bars, idx, field, breaker):
    out = copy.deepcopy(bars)
    breaker(out[idx], field)
    return out


def assess(sp_chrono, nq_chrono):
    ms = get_market_state(list(reversed(sp_chrono)), list(reversed(nq_chrono)))
    return assess_post_ftd_health(ms, sp_chrono, nq_chrono)


def gap_probe_history():
    """scratchpad/probe_gap655.py: an 8-day +0.8% rally that never qualifies as an FTD."""
    bars, day = make_correction_history()
    price = bars[-1]["close"]
    for k in range(1, 9):
        price *= 1.008
        vol = 1_200_000 if k == 5 else 1_000_000
        bars.append(make_bar(price, vol, date=f"day-{day:03d}", low=price * 0.997))
        day += 1
    return bars, len(bars) - 8 + 3  # index of rally day 4


# --- 1. gap probe regression ------------------------------------------------


@BREAKERS
def test_mid_rally_gap_is_a_data_gap_not_an_ftd(breaker):
    bars, day4 = gap_probe_history()
    assert analyze_single_index(bars, "X")["state"] == "FTD_WINDOW"

    # Dropping the bar instead would fabricate an FTD (the reason bars are never dropped).
    dropped = bars[:day4] + bars[day4 + 1 :]
    assert analyze_single_index(dropped, "X")["state"] == "FTD_CONFIRMED"

    result = analyze_single_index(broken(bars, day4, "close", breaker), "X")
    assert result["state"] == "NO_SIGNAL"
    assert result["data_gap"] is True
    assert result["error"].startswith("Data gap: 1 bar(s) with missing or invalid close/volume")
    assert "in the last 24 sessions" in result["error"]
    assert result["error"].endswith(f"(latest bad: {bars[day4]['date']})")
    assert result["ftd"] is None and result["swing_low"] is None
    assert result["current_price"] is None
    assert result["lookback_high"] is None
    assert result["correction_depth_pct"] is None
    assert result["data_quality"]["bad_bars"] == 1


@BREAKERS
def test_bad_volume_inside_window_is_a_data_gap(breaker):
    bars, day4 = gap_probe_history()
    result = analyze_single_index(broken(bars, day4, "volume", breaker), "X")
    assert result["state"] == "NO_SIGNAL" and result["data_gap"] is True


def test_zero_volume_is_a_data_gap():
    """Index volume 0 is provider missing data, not a quiet session (round-2 review)."""
    bars, day4 = gap_probe_history()
    bars[day4]["volume"] = 0
    result = analyze_single_index(bars, "X")
    assert result["data_gap"] is True
    assert result["data_quality"]["bad_bars"] == 1


@pytest.mark.parametrize("breaker", [_zero, _missing], ids=["zero", "missing"])
def test_zero_volume_cannot_hide_a_distribution_day(breaker):
    """Review case (gen.py 3 600 8 #232): S&P volume 0 the day before a distribution day.

    Treated as valid, the zero made ``prev_volume <= 0`` skip the distribution day
    and raised the score (Weak 50 -> Moderate 70). It must be Unavailable instead.
    """
    bars, ftd_idx = make_long_ftd_history(post_days=8)
    dist_day = ftd_idx + 2
    bars[dist_day]["close"] = bars[dist_day - 1]["close"] * 0.99
    bars[dist_day]["low"] = bars[dist_day]["close"] * 0.999
    bars[dist_day]["volume"] = bars[dist_day - 1]["volume"] * 2
    healed = assess(copy.deepcopy(bars), [])
    assert healed["post_ftd_distribution"]["distribution_count"] == 1
    healed_score = healed["quality_score"]["total_score"]

    gapped_bars = broken(bars, dist_day - 1, "volume", breaker)
    market_state = get_market_state(list(reversed(bars)), [])
    market_state = assess_post_ftd_health(market_state, gapped_bars, [])
    assert market_state["post_ftd_distribution"]["data_gap"] is True
    quality = market_state["quality_score"]
    assert quality["signal"] == "Unavailable: data gap"
    assert quality["total_score"] == 0 <= healed_score

    # and through the full pipeline the gap is caught by the 60-session window
    full = assess(gapped_bars, [])
    assert full["quality_score"]["total_score"] == 0
    assert full["quality_score"]["signal"] == "Unavailable: data gap"


@pytest.mark.parametrize("breaker", [_zero, _missing], ids=["zero", "missing"])
def test_zero_volume_on_nasdaq_cannot_promote_an_older_ftd(breaker):
    """Simplified stand-in for review case gen.py 2 600 8 #533 (NASDAQ volume 0).

    There, a zero volume treated as valid killed a newer invalidated FTD, Step 2
    picked an older FTD and the healed "No FTD" became a 75 "Moderate FTD". The
    exact case is re-checked by the rv655b probe; here any NASDAQ zero/missing
    volume in the window must make the score Unavailable, never above healed.
    """
    sp = invalidated_history()
    nq = invalidated_history()
    healed = assess(copy.deepcopy(sp), copy.deepcopy(nq))
    gapped = assess(sp, broken(nq, len(nq) - 3, "volume", breaker))
    assert gapped["nasdaq"]["data_gap"] is True
    quality = gapped["quality_score"]
    assert quality["signal"] == "Unavailable: data gap"
    assert quality["total_score"] == 0 <= healed["quality_score"]["total_score"]


# --- 2. Issue repro -----------------------------------------------------------


def issue_bars():
    return [{"close": 100 + 0.2 * i, "volume": 1} for i in range(60)]


def test_issue_repro_clean_baseline():
    result = detect_power_trend(issue_bars())
    assert result["power_trend"] is True
    assert result["conditions_met"] == 3


@BREAKERS
@pytest.mark.parametrize("position", [-5, -30])
def test_issue_repro_power_trend_is_unavailable_not_flipped(breaker, position):
    bars = broken(issue_bars(), position, "close", breaker)
    result = detect_power_trend(bars)
    assert result["power_trend"] is None
    assert result["conditions_met"] == 0
    assert result["reason"].startswith("Data gap: missing or invalid close")
    assert result["ema_21"] is None and result["sma_50"] is None
    assert result["current_price"] is None
    assert result["bad_bars"] == 1

    market_state = assess(bars, [])
    assert market_state["sp500"]["state"] == "NO_SIGNAL"
    assert market_state["combined_state"] == "NO_SIGNAL"
    assert market_state["power_trend"]["power_trend"] is None
    assert market_state["data_gap"] is True
    quality = market_state["quality_score"]
    assert quality["total_score"] == 0
    assert quality["signal"] == "Unavailable: data gap"


# --- 3. bad bar outside the 60-session window ----------------------------------


@BREAKERS
def test_bad_bar_older_than_window_only_affects_power_trend(breaker):
    bars, _ = make_long_ftd_history()
    assert len(bars) == 80
    clean = assess(copy.deepcopy(bars), [])
    gapped = assess(broken(bars, 5, "close", breaker), [])

    assert gapped["sp500"]["state"] == clean["sp500"]["state"] == "FTD_CONFIRMED"
    assert gapped["combined_state"] == clean["combined_state"]
    assert gapped["sp500"]["ftd"] == clean["sp500"]["ftd"]
    assert gapped["quality_score"] == clean["quality_score"]
    assert gapped["power_trend"]["power_trend"] is None
    assert gapped["power_trend"]["reason"].startswith("Data gap: missing or invalid close")
    assert gapped["data_gap"] is False
    assert gapped["data_quality"]["sp500"]["bad_bars"] == 0
    assert gapped["data_quality"]["sp500"]["power_trend_bad_bars"] == 1


# --- 4. track_rally_attempt -----------------------------------------------------


@BREAKERS
@pytest.mark.parametrize("field", ["close", "volume"])
def test_track_rally_attempt_degrades_on_gap(breaker, field):
    bars, sl_idx, day1_idx, _ = make_rally_history(rally_days=6)
    clean = track_rally_attempt(bars, sl_idx)
    assert clean["day1_idx"] == day1_idx and len(clean["rally_days"]) == 6

    result = track_rally_attempt(broken(bars, sl_idx + 3, field, breaker), sl_idx)
    assert result["day1_idx"] is None
    assert result["day1_date"] is None and result["day1_low"] is None
    assert result["rally_days"] == []
    assert result["current_day_count"] == 0
    assert result["invalidated"] is False
    assert result["invalidation_reason"] is None
    assert result["data_gap"] is True
    assert result["reason"].startswith("Data gap:")

    # detect_ftd never runs comparisons on a degraded rally
    ftd = detect_ftd(bars, result)
    assert ftd["ftd_detected"] is False


@BREAKERS
@pytest.mark.parametrize("where", ["window", "lookback"])
def test_detect_ftd_degrades_when_its_bars_are_gapped(breaker, where):
    bars, sl_idx, _, ftd_idx = make_rally_history(rally_days=6, ftd_day=4)
    rally = track_rally_attempt(bars, sl_idx)
    assert detect_ftd(bars, rally)["ftd_detected"] is True
    bad_idx = ftd_idx - 1 if where == "window" else 2
    result = detect_ftd(broken(bars, bad_idx, "volume", breaker), rally)
    assert result["ftd_detected"] is False
    assert result["data_gap"] is True
    assert result["reason"].startswith("Data gap:")


# --- 5. _is_swing_low -----------------------------------------------------------


@BREAKERS
@pytest.mark.parametrize("offset", [-1, 1, -4])
def test_is_swing_low_with_bad_neighbour_returns_none(breaker, offset):
    bars, _ = make_correction_history()
    bars.append(make_bar(bars[-1]["close"] * 1.01))
    i = len(bars) - 2
    assert _is_swing_low(bars, i) is not None
    assert _is_swing_low(broken(bars, i + offset, "close", breaker), i) is None


def test_is_swing_low_ignores_bars_outside_its_read_range():
    bars, _ = make_correction_history()
    bars.append(make_bar(bars[-1]["close"] * 1.01))
    bars.append({"date": "later"})  # i + 2: never read
    i = len(bars) - 3
    assert _is_swing_low(bars, i) is not None


# --- 6. check_ftd_invalidation ---------------------------------------------------


@BREAKERS
@pytest.mark.parametrize("where", ["mid_window", "current"])
def test_invalidation_gap_makes_quality_unavailable(breaker, where):
    bars, ftd_idx = make_long_ftd_history(post_days=8)
    clean = assess(copy.deepcopy(bars), [])
    assert clean["quality_score"]["signal"] == "Strong FTD"

    bad_idx = ftd_idx + 8 if where == "mid_window" else len(bars) - 1
    gapped_bars = broken(bars, bad_idx, "close", breaker)
    inv = check_ftd_invalidation(gapped_bars, ftd_idx)
    assert inv["invalidated"] is None
    assert inv["data_gap"] is True
    assert inv["reason"].startswith("Data gap:")

    # The FTD itself came from clean data; only the post-FTD history is gapped.
    market_state = get_market_state(list(reversed(bars)), [])
    market_state = assess_post_ftd_health(market_state, gapped_bars, [])
    # neither confirmed nor invalidated: the combined state is unavailable
    assert market_state["combined_state"] == "NO_SIGNAL"
    assert market_state["ftd_index"] is None
    assert market_state["data_gap"] is True
    quality = market_state["quality_score"]
    assert quality["total_score"] == 0
    assert quality["signal"] == "Unavailable: data gap"
    assert quality["exposure_range"] == "0-25%"
    assert quality["breakdown"] == {}
    assert quality["data_gap"] is True
    assert "Data gap" in quality["guidance"]


def test_invalidation_low_falls_back_to_close():
    bars, ftd_idx = make_long_ftd_history(post_days=2)
    bars[ftd_idx]["low"] = math.nan
    inv = check_ftd_invalidation(bars, ftd_idx)
    assert inv["invalidated"] is False
    assert inv["ftd_low"] == bars[ftd_idx]["close"]


# --- 7. count_post_ftd_distribution ------------------------------------------------


@BREAKERS
def test_distribution_gap_is_int_zero_and_quality_unavailable(breaker):
    bars, ftd_idx = make_long_ftd_history(post_days=8)
    gapped_bars = broken(bars, ftd_idx + 2, "volume", breaker)
    dist = count_post_ftd_distribution(gapped_bars, ftd_idx)
    assert dist["distribution_count"] == 0
    assert type(dist["distribution_count"]) is int
    assert dist["data_gap"] is True
    assert dist["reason"].startswith("Data gap:")

    market_state = get_market_state(list(reversed(bars)), [])
    market_state = assess_post_ftd_health(market_state, gapped_bars, [])
    quality = market_state["quality_score"]
    assert quality["total_score"] == 0
    assert quality["signal"] == "Unavailable: data gap"
    assert quality["data_gap"] is True


def test_distribution_ignores_bars_beyond_five_days():
    bars, ftd_idx = make_long_ftd_history(post_days=8)
    bars[ftd_idx + 7].pop("volume")
    dist = count_post_ftd_distribution(bars, ftd_idx)
    assert "data_gap" not in dist
    assert dist["days_monitored"] == 5


# --- 8. Day-1 range rule with invalid high/low ---------------------------------------


def day1_range_history():
    """scratchpad/probe_hl655.py: a flat close at 30% of its range is not a Day 1."""
    bars, day = make_correction_history()
    sl_idx = len(bars) - 1
    sl = bars[-1]["close"]
    bar = make_bar(sl, 1_000_000, date=f"day-{day:03d}", high=sl * 1.01, low=sl * 0.99)
    bar["high"] = sl + (sl - bar["low"]) * (7 / 3)
    bars.append(bar)
    return bars, sl_idx


@BREAKERS
@pytest.mark.parametrize("field", ["high", "low"])
def test_invalid_high_or_low_skips_the_range_rule(breaker, field):
    bars, sl_idx = day1_range_history()
    assert track_rally_attempt(bars, sl_idx)["day1_idx"] is None
    result = track_rally_attempt(broken(bars, -1, field, breaker), sl_idx)
    assert result["day1_idx"] is None
    assert "data_gap" not in result


@BREAKERS
def test_up_close_still_qualifies_day1_without_high(breaker):
    bars, sl_idx = day1_range_history()
    bars[-1]["close"] = bars[sl_idx]["close"] * 1.002
    result = track_rally_attempt(broken(bars, -1, "high", breaker), sl_idx)
    assert result["day1_idx"] == len(bars) - 1


# --- 9. combined state and quality score ------------------------------------------


def dated_history(*, peak=100, confirmed=True):
    bars, _, _, _ = make_rally_history(
        peak=peak, rally_days=8, ftd_day=5 if confirmed else None, ftd_gain_pct=2.1
    )
    return assign_session_dates(bars)


def test_sp500_gapped_nasdaq_confirmed_is_unavailable():
    """A gapped index never lets the other index decide: the gap could hide an invalidation."""
    sp = broken(dated_history(), 12, "close", _missing)
    nq = dated_history(peak=400)
    market_state = assess(sp, nq)

    # the combined state is unavailable: NO_SIGNAL + data_gap, no FTD source ...
    assert market_state["combined_state"] == "NO_SIGNAL"
    assert market_state["dual_confirmation"] is False
    assert market_state["ftd_index"] is None
    assert market_state["data_gap"] is True
    # ... while each index's own analysis stays visible
    assert market_state["sp500"]["error"].startswith("Data gap:")
    assert market_state["sp500"]["data_gap"] is True
    assert market_state["nasdaq"]["state"] == "FTD_CONFIRMED"
    # no post-FTD checks ran from the other index
    assert "post_ftd_distribution" not in market_state
    assert "ftd_invalidation" not in market_state
    # ... and the score fails closed
    quality = market_state["quality_score"]
    assert quality["total_score"] == 0
    assert quality["signal"] == "Unavailable: data gap"
    assert quality["exposure_range"] == "0-25%"
    assert quality["data_gap"] is True
    assert "S&P 500" in quality["guidance"]


def invalidated_history():
    """S&P FTD on day 5, then a close below the FTD low (test_ftd_detector pattern)."""
    bars, _, _, ftd_idx = make_rally_history(rally_days=8, ftd_day=5, ftd_gain_pct=2.1)
    bars.append(make_bar(bars[ftd_idx]["low"] - 0.1, volume=2_000_000))
    return assign_session_dates(bars)


@BREAKERS
@pytest.mark.parametrize("field", ["close", "volume"])
def test_gap_never_raises_score_over_invalidated_sp500(breaker, field):
    """Review case_4841: S&P invalidated + NASDAQ confirmed + one S&P gap.

    On the clean data the S&P FTD is the quality source and is invalidated
    (score 0, "Failed/Invalidated"). A gap must not promote NASDAQ to an
    85-95 "Strong FTD"; it is Unavailable with score 0.
    """
    nq = dated_history(peak=400)
    healed = assess(invalidated_history(), copy.deepcopy(nq))
    assert healed["combined_state"] == "FTD_INVALIDATED"
    assert healed["quality_score"]["total_score"] == 0
    assert healed["quality_score"]["signal"] == "Failed/Invalidated"

    gapped = assess(broken(invalidated_history(), 12, field, breaker), nq)
    quality = gapped["quality_score"]
    assert quality["total_score"] == 0
    assert quality["total_score"] <= healed["quality_score"]["total_score"]
    assert quality["signal"] == "Unavailable: data gap"
    assert quality["exposure_range"] == "0-25%"
    assert gapped["data_gap"] is True


# Bullishness order of the headline state (rv655c compare.py). A gapped
# NO_SIGNAL means "state unavailable" and ranks below every real state.
STATE_RANK = {
    "NO_SIGNAL": 0,
    "RALLY_FAILED": 1,
    "CORRECTION": 2,
    "FTD_INVALIDATED": 3,
    "RALLY_ATTEMPT": 4,
    "FTD_WINDOW": 5,
    "FTD_CONFIRMED": 6,
}


def headline_rank(market_state):
    if market_state.get("data_gap"):
        assert market_state["combined_state"] == "NO_SIGNAL"
        return -1
    return STATE_RANK[market_state["combined_state"]] + (
        0.5 if market_state["dual_confirmation"] else 0
    )


def rally_attempt_history(peak=400):
    bars, _, _, _ = make_rally_history(peak=peak, rally_days=2)
    return assign_session_dates(bars)


@BREAKERS
@pytest.mark.parametrize("field", ["close", "volume"])
@pytest.mark.parametrize(
    "nasdaq,promoted",
    [
        (lambda: dated_history(peak=400), "FTD_CONFIRMED"),  # rv655c g14_172 shape
        (rally_attempt_history, "RALLY_ATTEMPT"),  # rv655c g91_1101 shape
    ],
    ids=["g14_172", "g91_1101"],
)
def test_gap_never_makes_headline_state_more_bullish(breaker, field, nasdaq, promoted):
    """Healed: S&P FTD_INVALIDATED wins. Gapped S&P used to promote NASDAQ's state."""
    healed = assess(invalidated_history(), nasdaq())
    assert healed["combined_state"] == "FTD_INVALIDATED"
    assert healed["nasdaq"]["state"] == promoted

    gapped = assess(broken(invalidated_history(), 12, field, breaker), nasdaq())
    assert gapped["combined_state"] == "NO_SIGNAL"
    assert gapped["data_gap"] is True
    assert gapped["ftd_index"] is None
    assert gapped["dual_confirmation"] is False
    assert gapped["nasdaq"]["state"] == promoted  # kept for transparency only
    assert headline_rank(gapped) <= headline_rank(healed)
    assert gapped["quality_score"]["total_score"] <= healed["quality_score"]["total_score"]


def test_hand_built_market_state_with_index_gap_is_not_promoted():
    """Direct callers of assess_post_ftd_health get the same rule."""
    bars = dated_history(peak=400)
    market_state = get_market_state([], list(reversed(bars)))
    market_state["sp500"] = {"state": "NO_SIGNAL", "data_gap": True, "error": "Data gap: x"}
    market_state["data_gap"] = False  # caller forgot to merge the flag
    result = assess_post_ftd_health(market_state, [], bars)
    assert result["combined_state"] == "NO_SIGNAL"
    assert result["ftd_index"] is None
    assert result["data_gap"] is True
    assert "ftd_invalidation" not in result
    assert result["quality_score"]["signal"] == "Unavailable: data gap"


@pytest.mark.parametrize("both", [False, True], ids=["sp500_only", "both"])
def test_gapped_index_without_any_confirmation_is_unavailable(both):
    sp = broken(dated_history(), 12, "close", _nan)
    nq = dated_history(peak=400, confirmed=False)
    if both:
        nq = broken(nq, 12, "volume", _missing)
    market_state = assess(sp, nq)
    quality = market_state["quality_score"]
    assert quality["total_score"] == 0
    assert quality["signal"] == "Unavailable: data gap"
    assert quality["exposure_range"] == "0-25%"
    assert quality["data_gap"] is True
    assert market_state["data_gap"] is True


def test_no_gap_is_unchanged():
    market_state = assess(dated_history(), dated_history(peak=400, confirmed=False))
    assert market_state["combined_state"] == "FTD_CONFIRMED"
    assert market_state["quality_score"]["total_score"] == 95
    assert market_state["quality_score"]["signal"] == "Strong FTD"
    assert market_state["data_gap"] is False
    assert "data_gap" not in market_state["quality_score"]
    assert "error" not in market_state["sp500"]


def test_insufficient_data_index_stays_no_ftd_not_unavailable():
    market_state = assess(dated_history(confirmed=False), [])
    assert market_state["nasdaq"]["error"] == "Insufficient data"
    quality = market_state["quality_score"]
    assert quality["signal"] == "No FTD"
    assert "data_gap" not in quality
    assert market_state["data_gap"] is False


def test_quality_gate_ignores_power_trend_but_not_the_other_index():
    market_state = {
        "sp500": {"ftd": {"ftd_detected": True, "ftd_day_number": 5, "gain_pct": 2.1}},
        "nasdaq": {"state": "NO_SIGNAL"},
        "dual_confirmation": False,
        "power_trend": {"power_trend": None, "reason": "Data gap: missing or invalid close"},
        "post_ftd_distribution": {"distribution_count": 0, "days_monitored": 3},
        "ftd_invalidation": {"invalidated": False},
    }
    quality = calculate_ftd_quality_score(copy.deepcopy(market_state))
    assert quality["signal"] == "Strong FTD"
    assert quality["total_score"] == 85

    market_state["nasdaq"] = {"state": "NO_SIGNAL", "data_gap": True, "error": "Data gap: x"}
    quality = calculate_ftd_quality_score(market_state)
    assert quality["signal"] == "Unavailable: data gap"
    assert quality["total_score"] == 0
    assert quality["reason"] == "NASDAQ: Data gap: x"


def test_quality_gate_on_selected_index_and_missing_invalidation():
    base = {
        "sp500": {"ftd": {"ftd_detected": True, "ftd_day_number": 5, "gain_pct": 2.1}},
        "nasdaq": {},
        "post_ftd_distribution": {"distribution_count": 0, "days_monitored": 3},
    }
    # ftd_invalidation absent (FTD date not found): not a gap
    assert calculate_ftd_quality_score(copy.deepcopy(base))["total_score"] == 85
    flagged = copy.deepcopy(base)
    flagged["sp500"]["data_gap"] = True
    assert calculate_ftd_quality_score(flagged)["signal"] == "Unavailable: data gap"
    flagged = copy.deepcopy(base)
    flagged["sp500"]["ftd"]["data_gap"] = True
    assert calculate_ftd_quality_score(flagged)["signal"] == "Unavailable: data gap"
    unknown = copy.deepcopy(base)
    unknown["ftd_invalidation"] = {"invalidated": None}
    quality = calculate_ftd_quality_score(unknown)
    assert quality["signal"] == "Unavailable: data gap"
    assert quality["total_score"] == 0
    assert "invalidation status unknown" in quality["reason"]


# --- 10b. Day-1 low fallback -------------------------------------------------------


@BREAKERS
def test_day1_low_falls_back_to_close_for_breach_check(breaker):
    bars, _ = make_correction_history()
    sl = len(bars) - 1
    price = bars[sl]["close"]
    day1 = make_bar(price * 1.01, low=price * 1.005)
    breaker(day1, "low")
    bars.append(day1)
    bars.append(make_bar(price * 1.002))  # below Day-1 close, above swing low
    result = track_rally_attempt(bars, sl)
    assert result["invalidated"] is True
    assert result["day1_low"] == day1["close"]


# --- functions without production callers ------------------------------------------


@BREAKERS
def test_avg_volume_and_find_swing_low_skip_bad_values(breaker):
    bars = [make_bar(100, volume=1000), make_bar(100, volume=3000)]
    assert calculate_avg_volume(broken(bars, 0, "volume", breaker)) == 3000
    history, _ = make_correction_history()
    history.append(make_bar(history[-1]["close"] * 1.01))
    assert find_swing_low(history) is not None
    assert find_swing_low(broken(history, len(history) - 2, "close", breaker)) is None
