"""IBD resumes a confirmed uptrend without an FTD when an index closes at a new high.

Synthetic bars only. The reference series is the stateful-replay ``prefix`` (peak 106,
correction low 98.9 / intraday 98.0) followed by a +0.7% a day rise that never qualifies
as an FTD.
"""

import pytest
from helpers import assign_session_dates
from rally_tracker import analyze_single_index, get_market_state, resolve_parameters
from test_stateful_replay import B, advance, distribution_bars, prefix, run

ENV = "FTD_RESUME_NEW_HIGH"


def lead_bars(n=62):
    return [B(105.0 + 0.05 * (k % 2)) for k in range(n)]


def rise_bars(n=12, start=98.9, step=1.007):
    return [B(start * step**k) for k in range(1, n + 1)]


def first_new_high(rise, peak=106.0):
    return next(i for i, bar in enumerate(rise) if bar["close"] > peak)


def resumed_history(extra=()):
    """Long enough for the 50-session SMA; the last rise bar is the first new high."""
    rise = rise_bars()
    cut = first_new_high(rise) + 1
    return lead_bars() + prefix()[8:] + rise[:cut] + list(extra)


@pytest.fixture(autouse=True)
def default_mode(monkeypatch):
    monkeypatch.delenv(ENV, raising=False)


def test_default_mode_resumes_the_uptrend_on_a_close_above_the_pre_correction_high():
    rise = rise_bars()
    cut = first_new_high(rise)
    bars = prefix() + rise
    before = run(prefix() + rise[:cut])
    assert before["state"] == "FTD_WINDOW"
    assert before["market_status"] == "market_in_correction"
    result = run(prefix() + rise[: cut + 1])
    assert result["state"] == "UPTREND_RESUMED"
    assert result["market_status"] == "confirmed_uptrend"
    assert result["cycle"]["resumed_without_ftd"] is True
    assert result["cycle"]["phase"] == "confirmed"
    assert result["cycle"]["parameters"]["resume_new_high"] == "pre_correction_high"
    assert result["ftd"] is None
    assert "ftd_lifecycle" not in result
    # the failure reference is the active attempt's reference
    assert result["rally_attempt"]["reference_low"] == 98.0
    assert result["cycle"]["last_transition"]["to"] == "confirmed"
    later = run(bars)
    assert later["state"] == "UPTREND_RESUMED"


def test_resume_also_applies_during_a_failed_attempt_and_the_plain_correction_labels():
    # a Day-11 expiry (RALLY_FAILED), then a rise above the high, with a down close to arm
    expired = prefix() + [B(98.9 * 1.003**k) for k in range(1, 12)]
    assert run(expired)["state"] == "RALLY_FAILED"
    climb = [B(expired[-1]["close"] * 1.01**k) for k in range(1, 8)]
    result = run(expired + climb)
    assert result["state"] == "UPTREND_RESUMED"
    assert result["cycle"]["resumed_without_ftd"] is True
    # no attempt is active: the reference is the lowest low of the active segment
    assert result["rally_attempt"]["reference_low"] == expired[-1]["low"]


def test_off_never_resumes(monkeypatch):
    monkeypatch.setenv(ENV, "off")
    result = run(prefix() + rise_bars(16))
    assert result["state"] in ("RALLY_FAILED", "FTD_WINDOW")
    assert result["market_status"] == "market_in_correction"
    assert result["cycle"]["resumed_without_ftd"] is False


def high_then_correction_series():
    """A 130 high, a deep decline, an FTD, an advance and a 10% drawdown (correction
    measured from the lower post-FTD peak), then a gentle rise past that peak but far
    below 130."""
    from test_stateful_replay import old_deep_low_series

    bars = old_deep_low_series()
    close = bars[-1]["close"]
    rise = []
    for _ in range(40):
        close *= 1.004
        rise.append(B(close))
    return bars, rise


def test_replay_high_needs_the_highest_close_in_the_fetched_history(monkeypatch):
    bars, rise = high_then_correction_series()
    full = bars + rise
    assert run(bars)["state"] == "CORRECTION"
    default = run(full)  # above the post-FTD peak the correction was measured from
    assert default["state"] == "UPTREND_RESUMED"
    monkeypatch.setenv(ENV, "replay_high")
    replay_high = run(full)
    assert replay_high["state"] != "UPTREND_RESUMED"
    assert replay_high["market_status"] == "market_in_correction"
    assert replay_high["cycle"]["parameters"]["resume_new_high"] == "replay_high"
    assert max(b["close"] for b in full) < 131  # the 130 lead-in close was never reached


def test_replay_high_resumes_above_every_prior_close(monkeypatch):
    monkeypatch.setenv(ENV, "replay_high")
    rise = rise_bars(14)
    # a close above the highest close of the whole history (106 in the prefix)
    result = run(prefix() + rise)
    assert result["state"] == "UPTREND_RESUMED"


def test_52w_needs_252_sessions_since_the_replay_start(monkeypatch):
    monkeypatch.setenv(ENV, "52w")
    short = run(prefix() + rise_bars(14))
    assert short["state"] != "UPTREND_RESUMED"  # fewer than 252 prior sessions: rule off
    assert short["market_status"] == "market_in_correction"
    long_bars = lead_bars(260) + prefix()[8:] + rise_bars(14)
    long_result = run(long_bars)
    assert long_result["state"] == "UPTREND_RESUMED"
    assert long_result["cycle"]["parameters"]["resume_new_high"] == "52w"


def test_every_mode_is_reported_in_cycle_parameters(monkeypatch):
    for mode in ("pre_correction_high", "52w", "replay_high", "off"):
        monkeypatch.setenv(ENV, mode)
        assert run(prefix())["cycle"]["parameters"]["resume_new_high"] == mode


def test_an_invalid_value_warns_on_stderr_and_uses_the_default(monkeypatch, capsys):
    monkeypatch.setenv(ENV, "sometimes")
    assert resolve_parameters()["resume_new_high"] == "pre_correction_high"
    err = capsys.readouterr().err
    assert ENV in err and "sometimes" in err
    result = run(prefix())
    assert result["cycle"]["parameters"]["resume_new_high"] == "pre_correction_high"


def test_parameters_are_read_when_analyzing_not_at_import(monkeypatch):
    bars = assign_session_dates(prefix() + rise_bars(14))
    monkeypatch.setenv(ENV, "off")
    off = analyze_single_index(bars, "X")
    monkeypatch.setenv(ENV, "pre_correction_high")
    on = analyze_single_index(bars, "X")
    assert off["state"] != "UPTREND_RESUMED"
    assert on["state"] == "UPTREND_RESUMED"


# --- the confirmed-phase rules apply to a resumed uptrend -------------------------------------


def test_distribution_puts_a_resumed_uptrend_under_pressure_without_an_ftd_low_cause():
    base = resumed_history()
    five = base + distribution_bars(base[-1]["close"], 5, step=0.004)
    result = run(five)
    assert result["state"] == "UPTREND_RESUMED"
    assert result["market_status"] == "uptrend_under_pressure"
    assert "distribution" in result["cycle"]["pressure_reasons"]
    assert "ftd_low_close_breach" not in result["cycle"]["pressure_reasons"]
    # a dip below the resume bar's own low is not an FTD-low breach
    dip = run(base + [B(base[-1]["close"] * 0.985, vol=900_000)])
    assert dip["market_status"] == "confirmed_uptrend"
    assert dip["cycle"]["pressure_reasons"] == []


def test_six_distribution_days_below_the_sma50_end_a_resumed_uptrend():
    base = resumed_history()
    bars = base + distribution_bars(base[-1]["close"], 6, step=0.009)
    result = run(bars)
    assert result["cycle"]["indicators"]["sma50_available"] is True
    assert result["state"] == "CORRECTION"
    assert result["market_status"] == "market_in_correction"
    previous = result["cycle"]["previous_ftd"]
    assert previous["end_reason"] == "distribution"
    assert previous["ftd"] is None
    assert previous["resumed_without_ftd"] is True
    assert result["cycle"]["resumed_without_ftd"] is False
    assert run(bars[:-1])["state"] == "UPTREND_RESUMED"  # 5 DDs: pressure only


def test_a_10_percent_drawdown_from_the_peak_since_the_resume_ends_it():
    base = resumed_history()
    up = advance(base[-1]["close"], 40, step=0.005)
    peak = up[-1]["close"]
    assert run(base + up)["state"] == "UPTREND_RESUMED"
    drop = B(peak * 0.9, vol=800_000)
    result = run(base + up + [drop])
    assert result["state"] == "CORRECTION"
    assert result["cycle"]["previous_ftd"]["end_reason"] == "deep_drawdown"
    assert run(base + up + [B(peak * 0.901, vol=800_000)])["state"] == "UPTREND_RESUMED"


def test_an_undercut_of_the_failure_reference_ends_it_as_a_correction():
    base = resumed_history()
    result = run(base + [B(base[-1]["close"], low=97.9)])  # below the attempt's 98.0
    assert result["state"] == "CORRECTION"
    assert result["state"] != "FTD_INVALIDATED"
    assert result["cycle"]["previous_ftd"]["end_reason"] == "undercut"
    assert result["rally_attempt"]["day1_idx"] is None
    holds = run(base + [B(base[-1]["close"], low=98.0)])  # equality holds
    assert holds["state"] == "UPTREND_RESUMED"


# --- consumers ------------------------------------------------------------------------------


def dated(bars):
    return assign_session_dates(list(bars))


def test_get_market_state_treats_a_resumed_index_as_confirmed_without_an_ftd():
    resumed = dated(prefix() + rise_bars(14))
    correction = dated(prefix())
    state = get_market_state(list(reversed(correction)), list(reversed(resumed)))
    assert state["nasdaq"]["state"] == "UPTREND_RESUMED"
    assert state["combined_state"] == "UPTREND_RESUMED"
    assert state["market_status"] == "confirmed_uptrend"
    assert state["ftd_index"] is None
    assert state["dual_confirmation"] is False
    both = get_market_state(list(reversed(resumed)), list(reversed(resumed)))
    assert both["combined_state"] == "UPTREND_RESUMED"
    assert both["dual_confirmation"] is False


def test_an_ftd_index_still_beats_a_resumed_index():
    from test_stateful_replay import ftd_history

    ftd = dated(ftd_history())
    resumed = dated(prefix() + rise_bars(14))
    state = get_market_state(list(reversed(resumed)), list(reversed(ftd)))
    assert state["combined_state"] == "FTD_CONFIRMED"
    assert state["ftd_index"] == "NASDAQ"
    assert state["dual_confirmation"] is False


def test_the_post_ftd_monitor_does_not_fabricate_an_ftd_for_a_resumed_uptrend():
    from post_ftd_monitor import assess_post_ftd_health

    bars = dated(prefix() + rise_bars(14))
    market = get_market_state(list(reversed(bars)), [])
    assessed = assess_post_ftd_health(market, bars, [])
    assert assessed["combined_state"] == "UPTREND_RESUMED"
    assert assessed["market_status"] == "confirmed_uptrend"
    assert assessed["quality_score"]["signal"] == "No FTD"
    assert assessed["quality_score"]["total_score"] == 0
    assert "ftd_invalidation" not in assessed
    assert "post_ftd_distribution" not in assessed


def test_the_report_names_a_resumed_uptrend_and_says_there_was_no_ftd(tmp_path):
    from post_ftd_monitor import assess_post_ftd_health
    from report_generator import generate_markdown_report

    bars = dated(prefix() + rise_bars(14))
    market = assess_post_ftd_health(get_market_state(list(reversed(bars)), []), bars, [])
    analysis = {
        "metadata": {},
        "market_state": {
            "combined_state": market["combined_state"],
            "market_status": market["market_status"],
        },
        "sp500": market["sp500"],
        "nasdaq": market["nasdaq"],
        "quality_score": market["quality_score"],
    }
    path = tmp_path / "report.md"
    generate_markdown_report(analysis, str(path))
    text = path.read_text(encoding="utf-8")
    assert "Uptrend Resumed" in text
    assert "without an FTD" in text
    assert "FTD Confirmed" not in text


# --- review findings: priorities, bar updates, replay_high gaps, tolerances ---------------------------


def assess(sp500_chrono, nasdaq_chrono):
    from post_ftd_monitor import assess_post_ftd_health

    market = get_market_state(list(reversed(sp500_chrono)), list(reversed(nasdaq_chrono)))
    return assess_post_ftd_health(market, sp500_chrono, nasdaq_chrono)


@pytest.mark.parametrize("resumed_first", [True, False], ids=["sp500_resumed", "nasdaq_resumed"])
def test_a_failed_ftd_on_the_other_index_does_not_override_a_resumed_uptrend(resumed_first):
    from test_stateful_replay import ftd_history

    resumed = dated(prefix() + rise_bars(14))
    failed = dated(ftd_history() + [B(100.0, low=97.9)])
    assert run(failed)["state"] == "FTD_INVALIDATED"
    sp, nq = (resumed, failed) if resumed_first else (failed, resumed)
    result = assess(sp, nq)
    assert result["combined_state"] == "UPTREND_RESUMED"
    assert result["market_status"] == "confirmed_uptrend"
    assert result["quality_score"]["signal"] == "No FTD"


def test_the_undercut_is_recorded_before_a_same_bar_resume():
    rise = rise_bars(9)  # Day 9, just under the 106 peak
    bar = B(107.0, low=97.0, high=107.5)  # Day 10: undercuts 98.0 and closes at a new high
    result = run(prefix() + rise + [bar])
    assert result["state"] == "UPTREND_RESUMED"
    attempt = result["rally_attempt"]
    assert attempt["end_reason"] == "undercut"
    assert attempt["reset_count"] == 1
    assert attempt["reference_low"] == 97.0  # the new segment low includes today's low
    assert run(prefix() + rise + [bar, B(107.2, low=97.5)])["state"] == "UPTREND_RESUMED"
    assert run(prefix() + rise + [bar, B(107.2, low=96.9)])["state"] == "CORRECTION"


def test_an_ftd_on_the_day_of_a_new_high_beats_the_resume():
    bars = prefix() + [
        B(102.0, low=100.0, high=102.5),  # Day 1
        B(104.0, low=103.0, high=104.2),
        B(105.0, low=104.0, high=105.2),
    ]
    day4 = B(105.0 * 1.015, vol=1_500_000)  # +1.5% on higher volume, above the 106 peak
    assert day4["close"] > 106.0
    result = run(bars + [day4])
    assert result["state"] == "FTD_CONFIRMED"
    assert result["ftd"]["ftd_detected"] is True
    assert result["ftd"]["ftd_day_number"] == 4
    assert result["cycle"]["resumed_without_ftd"] is False
    below = B(day4["low"] - 0.2)  # a later close below the FTD-day low
    pressured = run(bars + [day4, below])
    assert pressured["market_status"] == "uptrend_under_pressure"
    assert "ftd_low_close_breach" in pressured["cycle"]["pressure_reasons"]


def test_a_day_11_new_high_records_the_expiry_and_then_resumes():
    gentle = rise_bars(10, step=1.0065)  # Day 10 stays under the 106 peak
    assert gentle[-1]["close"] < 106.0
    day11 = B(107.0, vol=1_500_000)  # +1.4% on higher volume: not an FTD on Day 11
    result = run(prefix() + gentle + [day11])
    assert result["state"] == "UPTREND_RESUMED"
    attempt = result["rally_attempt"]
    assert attempt["end_reason"] == "expired"
    assert attempt["reset_count"] == 1
    assert attempt["reference_low"] == day11["low"]  # the expiry bar starts the new segment
    assert result["ftd"] is None


def test_a_resume_from_a_plain_correction_keeps_todays_low_in_the_reference():
    bars = prefix()  # a correction with no attempt: segment low 98.0
    bar = B(107.0, low=97.0, high=107.5)
    result = run(bars + [bar])
    assert result["state"] == "UPTREND_RESUMED"
    assert result["rally_attempt"]["reference_low"] == 97.0
    assert run(bars + [bar, B(107.2, low=97.5)])["state"] == "UPTREND_RESUMED"
    assert run(bars + [bar, B(107.2, low=96.9)])["state"] == "CORRECTION"


def test_replay_high_is_the_highest_valid_close_across_a_volume_gap(monkeypatch):
    before = [B(130.0 + 0.1 * (k % 2)) for k in range(70)]
    gap = B(130.0, vol=0)  # a volume-only gap: the replay restarts after it
    after = lead_bars(62) + prefix()[8:] + rise_bars(13)  # recovers to ~108, never to 130
    bars = before + [gap] + after
    assert max(b["close"] for b in after) < 110
    monkeypatch.setenv(ENV, "replay_high")
    result = run(bars)
    assert result["cycle"]["restarted_after_gap"] is True
    assert result["state"] != "UPTREND_RESUMED"
    monkeypatch.setenv(ENV, "pre_correction_high")
    assert run(bars)["state"] == "UPTREND_RESUMED"
    # a missing close is skipped, not read as the replay's maximum or as zero
    broken = [dict(b) for b in bars]
    del broken[10]["close"]
    monkeypatch.setenv(ENV, "replay_high")
    assert run(broken)["state"] != "UPTREND_RESUMED"


def test_52w_availability_boundary(monkeypatch):
    monkeypatch.setenv(ENV, "52w")
    tail = prefix()[8:]
    rise = rise_bars(14)
    fh = first_new_high(rise)

    def series(prior_sessions):
        lead = prior_sessions - len(tail) - fh
        bars = lead_bars(lead) + tail + rise[: fh + 1]
        assert len(bars) - 1 == prior_sessions  # the new-high bar has this many prior sessions
        return bars

    assert run(series(251))["state"] != "UPTREND_RESUMED"  # 251 prior sessions: rule off
    assert run(series(252))["state"] == "UPTREND_RESUMED"  # exactly 252: on


# --- tolerance on the drawdown comparisons --------------------------------------------------------


def exact_drawdown_history(closes):
    from test_stateful_replay import long_advance_history

    base = long_advance_history(120, step=0.0006)
    scale = 110.0 / base[-1]["close"]
    scaled = []
    for bar in base:
        scaled.append(
            {k: (v * scale if k in ("open", "high", "low", "close") else v) for k, v in bar.items()}
        )
    scaled[-1]["close"] = scaled[-1]["open"] = 110.0
    tail = [B(c, vol=1_100_000 + 100_000 * i) for i, c in enumerate(closes)]
    return scaled + tail


def test_an_exact_min_drawdown_counts_despite_float_noise(monkeypatch):
    monkeypatch.setenv("FTD_CORRECTION_MIN_DRAWDOWN_PCT", "3.5")
    bars = exact_drawdown_history([109.5, 109.0, 108.5, 108.0, 107.2, 106.15])
    assert 110.0 * (1 - 3.5 / 100) < 106.15  # the plain float cutoff is 106.14999999999999
    result = run(bars)
    assert result["cycle"]["indicators"]["sma50"] > 106.15
    assert result["state"] == "CORRECTION"
    assert result["cycle"]["previous_ftd"]["end_reason"] == "distribution"


def test_an_exact_10_percent_drawdown_counts_despite_float_noise():
    bars = exact_drawdown_history([99.0])
    result = run(bars)
    assert result["state"] == "CORRECTION"
    assert result["cycle"]["previous_ftd"]["end_reason"] == "deep_drawdown"


# --- guidance for a resumed uptrend ------------------------------------------------------------------


def test_the_guidance_for_a_resumed_uptrend_does_not_say_stay_defensive(tmp_path):
    from report_generator import generate_markdown_report

    bars = dated(prefix() + rise_bars(14))
    market = assess(bars, [])
    quality = market["quality_score"]
    assert quality["total_score"] == 0
    assert quality["signal"] == "No FTD"
    assert "Uptrend resumed on a new high" in quality["guidance"]
    assert "no FTD quality score applies" in quality["guidance"]
    assert "Stay defensive" not in quality["guidance"]
    analysis = {
        "metadata": {},
        "market_state": {"combined_state": market["combined_state"]},
        "sp500": market["sp500"],
        "nasdaq": market["nasdaq"],
        "quality_score": quality,
    }
    path = tmp_path / "report.md"
    generate_markdown_report(analysis, str(path))
    text = path.read_text(encoding="utf-8")
    assert "Uptrend resumed on a new high" in text
    assert "Stay defensive" not in text
