"""Tuning knobs for the distribution correction trigger (uncalibrated; defaults = old behavior).

FTD_CORRECTION_DD_COUNT: integer 6..10, default 6.
FTD_CORRECTION_MIN_DRAWDOWN_PCT: float 0..9.99, default 0 (none).
"""

import pytest
from rally_tracker import resolve_parameters
from test_stateful_replay import distribution_bars, long_advance_history, run

COUNT = "FTD_CORRECTION_DD_COUNT"
DRAWDOWN = "FTD_CORRECTION_MIN_DRAWDOWN_PCT"


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in (COUNT, DRAWDOWN, "FTD_RESUME_NEW_HIGH"):
        monkeypatch.delenv(name, raising=False)


def history(n_dd):
    """A confirmed uptrend (SMA computable) followed by n_dd distribution days of -1.3%."""
    base = long_advance_history(80, step=0.002)
    return base, base + distribution_bars(base[-1]["close"], n_dd, step=0.013)


def test_defaults_reproduce_the_current_behavior():
    assert resolve_parameters() == {
        "resume_new_high": "pre_correction_high",
        "correction_dd_count": 6,
        "correction_min_drawdown_pct": 0.0,
    }
    _, bars = history(6)
    result = run(bars)
    assert result["state"] == "CORRECTION"
    assert result["cycle"]["previous_ftd"]["end_reason"] == "distribution"
    assert result["cycle"]["parameters"]["correction_dd_count"] == 6
    assert result["cycle"]["parameters"]["correction_min_drawdown_pct"] == 0.0
    _, five = history(5)
    assert run(five)["state"] == "FTD_CONFIRMED"


def test_the_dd_count_boundary(monkeypatch):
    monkeypatch.setenv(COUNT, "7")
    _, six = history(6)
    under = run(six)
    assert len(under["cycle"]["active_distribution_days"]) == 6
    assert under["state"] == "FTD_CONFIRMED"
    assert under["market_status"] == "uptrend_under_pressure"
    assert under["cycle"]["parameters"]["correction_dd_count"] == 7
    _, seven = history(7)
    over = run(seven)
    assert over["state"] == "CORRECTION"
    assert over["cycle"]["previous_ftd"]["end_reason"] == "distribution"


def test_the_pressure_count_is_not_changed_by_the_knob(monkeypatch):
    monkeypatch.setenv(COUNT, "10")
    _, five = history(5)
    assert run(five)["market_status"] == "uptrend_under_pressure"
    assert resolve_parameters()["correction_dd_count"] == 10


def drawdown_pct(bars, base):
    peak = max(bar["close"] for bar in base)
    return (1 - bars[-1]["close"] / peak) * 100


def test_the_minimum_drawdown_boundary(monkeypatch):
    base, bars = history(6)
    pct = drawdown_pct(bars, base)
    assert 5 < pct < 9.99
    monkeypatch.setenv(DRAWDOWN, repr(pct - 1e-6))  # at least that far below: it still ends
    assert run(bars)["state"] == "CORRECTION"
    monkeypatch.setenv(DRAWDOWN, repr(pct + 1e-6))  # not far enough below: it does not
    held = run(bars)
    assert held["state"] == "FTD_CONFIRMED"
    assert held["market_status"] == "uptrend_under_pressure"
    assert held["cycle"]["parameters"]["correction_min_drawdown_pct"] == pytest.approx(pct + 1e-6)
    # the drawdown condition is additive: a later DD that is deep enough ends it
    more = base + distribution_bars(base[-1]["close"], 7, step=0.013)
    assert run(more)["state"] == "CORRECTION"


def test_the_ten_percent_deep_drawdown_and_the_undercut_are_unchanged(monkeypatch):
    monkeypatch.setenv(COUNT, "10")
    monkeypatch.setenv(DRAWDOWN, "9.99")
    base = long_advance_history(60, step=0.005)
    peak = base[-1]["close"]
    from test_stateful_replay import B

    result = run(base + [B(peak * 0.9, vol=900_000)])
    assert result["cycle"]["previous_ftd"]["end_reason"] == "deep_drawdown"
    undercut = run(base + [B(peak, low=90.0, vol=900_000)])
    assert undercut["state"] == "FTD_INVALIDATED"


@pytest.mark.parametrize("value", ["5", "11", "7.5", "six", "", "-1", "nan"])
def test_invalid_dd_counts_warn_and_use_the_default(monkeypatch, capsys, value):
    monkeypatch.setenv(COUNT, value)
    params = resolve_parameters()
    assert params["correction_dd_count"] == 6
    err = capsys.readouterr().err
    if value != "":  # an empty variable counts as unset
        assert COUNT in err


@pytest.mark.parametrize("value,expected", [("6", 6), ("10", 10), (" 8 ", 8)])
def test_valid_dd_counts(monkeypatch, value, expected):
    monkeypatch.setenv(COUNT, value)
    assert resolve_parameters()["correction_dd_count"] == expected


@pytest.mark.parametrize("value", ["-0.1", "10", "10.0", "9.995", "nan", "inf", "abc"])
def test_invalid_drawdowns_warn_and_use_the_default(monkeypatch, capsys, value):
    monkeypatch.setenv(DRAWDOWN, value)
    assert resolve_parameters()["correction_min_drawdown_pct"] == 0.0
    assert DRAWDOWN in capsys.readouterr().err


@pytest.mark.parametrize("value,expected", [("0", 0.0), ("9.99", 9.99), ("3.5", 3.5)])
def test_valid_drawdowns(monkeypatch, value, expected):
    monkeypatch.setenv(DRAWDOWN, value)
    assert resolve_parameters()["correction_min_drawdown_pct"] == expected
