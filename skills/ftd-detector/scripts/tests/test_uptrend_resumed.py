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
    assert result["cycle"]["parameters"] == {"resume_new_high": "pre_correction_high"}
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
    assert replay_high["cycle"]["parameters"] == {"resume_new_high": "replay_high"}
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
    assert long_result["cycle"]["parameters"] == {"resume_new_high": "52w"}


def test_every_mode_is_reported_in_cycle_parameters(monkeypatch):
    for mode in ("pre_correction_high", "52w", "replay_high", "off"):
        monkeypatch.setenv(ENV, mode)
        assert run(prefix())["cycle"]["parameters"] == {"resume_new_high": mode}


def test_an_invalid_value_warns_on_stderr_and_uses_the_default(monkeypatch, capsys):
    monkeypatch.setenv(ENV, "sometimes")
    assert resolve_parameters() == {"resume_new_high": "pre_correction_high"}
    err = capsys.readouterr().err
    assert ENV in err and "sometimes" in err
    result = run(prefix())
    assert result["cycle"]["parameters"] == {"resume_new_high": "pre_correction_high"}


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
